"""
Layout-independent extraction engine.

analyze_pdf(path) ->
  {
    "file", "total_pages", "tax_year", "taxpayer", "spouse",
    "pages":     [{page, kind, doc_ids, needs_ocr, ocr, label}],
    "documents": [document ...]   (packet order; record numbers per Drake screen)
    "checks":    [{level, text, doc}]
  }

A document is one tax form instance (a standalone IRS form, or one section of a brokerage composite
statement). Each document carries:
  fields      the catalog fields with the value read from the PDF, the page, the bounding box and a confidence
  pdf_fields  every value found on the PDF for this document — matched ones plus unmatched label/value pairs,
              so the reviewer can map anything the catalog did not anticipate
"""
import hashlib
import os
import re
import threading
from collections import Counter

from . import catalog
from .catalog import compiled
from .pdftext import (BOX_START_RE, CHECK_MARKS, Region, is_value_token, load_pages, looks_like_label,
                      money_value, token_type_ok)

BOUNDARY_RES = [r"SECTION 1256 CONTRACTS", r"RECONCILIATIONS, FEES", r"STATE TAX WITHHELD", r"Withholding\s+Amount$"]
IDENTITY_PREFIXES = ("payer_", "recipient_", "account")
_cache = {}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def file_key(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def union_box(words):
    return [round(min(w.x0 for w in words), 1), round(min(w.top for w in words), 1),
            round(max(w.x1 for w in words), 1), round(max(w.bottom for w in words), 1)]


def norm_label(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def normalize(ftype, raw):
    """PDF text -> the value Drake expects."""
    if isinstance(raw, bool):
        return raw
    s = "" if raw is None else str(raw).strip()
    if not s:
        return ""
    if ftype == "money":
        v = money_value(s)
        return "" if v is None else f"{v:.2f}"
    if ftype in ("ssn", "ein"):
        d = re.sub(r"\D", "", s)
        return d if len(d) == 9 else s.upper()
    if ftype == "tin":
        d = re.sub(r"\D", "", s)
        return d if len(d) == 9 else s.upper()
    if ftype == "zip":
        return re.sub(r"[^\d-]", "", s)
    if ftype in ("state", "code", "ts"):
        return s.upper()
    if ftype == "date":
        m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", s)
        if m:
            y = m.group(3)
            y = ("20" + y) if len(y) == 2 else y
            return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{y}"
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
        if m:
            return f"{m.group(2)}/{m.group(3)}/{m.group(1)}"
        return s
    if ftype == "percent":
        return s.replace(" ", "")
    if ftype in ("name", "text"):
        return re.sub(r"\s+", " ", s).upper()
    return s


def display(ftype, value):
    if isinstance(value, bool):
        return "Checked" if value else "Not checked"
    if ftype == "money" and value not in ("", None):
        try:
            return f"{float(value):,.2f}"
        except ValueError:
            return str(value)
    return "" if value is None else str(value)


# ---------------------------------------------------------------------------
# label search + value reading
# ---------------------------------------------------------------------------
class Hit:
    __slots__ = ("raw", "words", "page", "conf", "how", "label_box")

    def __init__(self, raw, words, page, conf, how, label_box=None):
        self.raw, self.words, self.page, self.conf, self.how, self.label_box = raw, words, page, conf, how, label_box

    def box(self):
        return union_box(self.words) if self.words else None


def find_labels(field, pages, regions):
    """Every place one of the field's label patterns occurs: [(page, line, label_words)]."""
    out = []
    for alias in field["aliases"]:
        rx = compiled(alias)
        for pg in pages:
            for line in pg.lines_in(regions.get(pg.number)):
                for m in rx.finditer(line.text):
                    ws = line.words_in_span(m.start(), m.end())
                    if ws:
                        out.append((pg, line, ws))
        if out:
            break             # aliases are ordered most specific first
    return out


ADDRESS_RE = re.compile(r"\b(?:street|st|ave|avenue|blvd|boulevard|road|rd|drive|dr|lane|ln|way|court|ct|plaza|trail|pkwy|parkway|"
                        r"hwy|highway|circle|cir|place|pl|terrace|suite|ste|apt|square|sq)\b\.?|\bP\.?\s*O\.?\s*Box\b|\b[A-Z]{2}\s+\d{5}\b", re.I)


def _is_box_label_start(words, i):
    w = words[i]
    if not BOX_START_RE.match(w.text):
        return False
    nxt = words[i + 1] if i + 1 < len(words) else None
    if not (nxt and nxt.x0 - w.x1 < 12 and (nxt.text[:1].isupper() or nxt.text[:1] == "(")):
        return False
    if w.text[:1].isdigit() and ADDRESS_RE.search(" ".join(x.text for x in words[i:i + 6])):
        return False          # "55 Industrial Way", "12 Oak Street" are addresses, not box labels
    return True


def column_for(pg, label_words, region):
    """x-range of the box a label belongs to: from the label to the next label on the same line."""
    lx0 = min(w.x0 for w in label_words)
    lx1 = max(w.x1 for w in label_words)
    cy = sum(w.cy for w in label_words) / len(label_words)
    row = sorted([w for w in pg.words_in(region) if abs(w.cy - cy) <= 3.5], key=lambda w: w.x0)
    right = [w for w in row if w.x0 >= lx1 - 0.5]
    x1 = region.x1 if region else pg.width
    prev = lx1
    for i, w in enumerate(right):
        gap = w.x0 - prev
        if gap >= 12 or _is_box_label_start(right, i):
            x1 = w.x0 - 2
            break
        prev = w.x1
    # a box letter/number printed just left of the label belongs to the same box ("a Employee's ...")
    left = [w for w in row if w.x1 <= lx0 + 0.5 and lx0 - w.x1 < 10 and BOX_START_RE.match(w.text)]
    x0 = min([lx0] + [w.x0 for w in left]) - 8
    return max(0, x0), x1


def _type_ok(field, text):
    if "{{" in text:
        return False
    pat = field.get("pattern")
    if pat and not re.match(pat, text):
        return False
    return token_type_ok(field["type"], text)


def _clean_token(t):
    return t.strip().rstrip(",;")


def read_same_line(field, pg, label_words, region):
    lx1 = max(w.x1 for w in label_words)
    cy = sum(w.cy for w in label_words) / len(label_words)
    ws = sorted([w for w in pg.words_in(region) if abs(w.cy - cy) <= 4.5 and w.x0 >= lx1 - 0.5 and w not in label_words],
                key=lambda w: w.x0)
    ftype = field["type"]
    if ftype in ("text", "name"):
        # Only a value that clearly follows the label: after a "Label:" colon, or after a visible gap.
        # Otherwise the words are just the rest of the printed label ("7 Foreign country or U.S. possession").
        start = None
        if label_words[-1].text.endswith(":") or (ws and ws[0].x0 - lx1 >= 8):
            start = 0
        else:
            for i, w in enumerate(ws[:8]):
                if _is_box_label_start(ws, i):
                    break
                if w.text.endswith(":"):
                    start = i + 1
                    break
        if start is None:
            return None
        ws = ws[start:]
        out, prev = [], (ws[0].x0 if ws else lx1)
        for i, w in enumerate(ws):
            if w.x0 - prev > (25 if not out else 14) or _is_box_label_start(ws, i) or is_value_token(w.text):
                break
            out.append(w)
            prev = w.x1
        txt = " ".join(w.text for w in out).strip(" :")
        if out and txt and "{{" not in txt and not looks_like_label(txt):
            return Hit(txt, out, pg.number, 0.8, "same line")
        return None
    for i, w in enumerate(ws):
        if i and _is_box_label_start(ws, i):
            break
        t = _clean_token(w.text)
        if t == "$" or t == "":
            continue
        if _type_ok(field, t):
            return Hit(t, [w], pg.number, 0.92, "same line")
    return None


def _segment(ws, x0, strict=False):
    """Words of one box: split at wide gaps and keep the piece that starts at the box's left edge.
    strict: return [] when no piece starts at the left edge (the words belong to another box further right)."""
    ws = sorted(ws, key=lambda w: w.x0)
    segs, cur = [], []
    for w in ws:
        if cur and w.x0 - cur[-1].x1 >= 12:
            segs.append(cur)
            cur = []
        cur.append(w)
    if cur:
        segs.append(cur)
    for s in segs:
        if s[0].x0 <= x0 + 30:
            return s
    return [] if strict else (segs[0] if segs else [])


def _crosses(line, ws, x0):
    """True when the column words are just the middle of a sentence running across the page."""
    if not ws:
        return False
    first = min(ws, key=lambda w: w.x0)
    return any(w not in ws and w.x1 <= first.x0 and first.x0 - w.x1 < 8 and w.x0 < x0 for w in line.words)


def read_below(field, pg, label_words, region, max_dist=44):
    x0, x1 = column_for(pg, label_words, region)
    lbottom = max(w.bottom for w in label_words)
    ftype = field["type"]
    if ftype in ("text", "name"):
        max_dist = min(max_dist, 24)          # free text must sit right under its label
    seen_value_line = False
    for line in pg.lines_in(region):
        ws = [w for w in line.words if x0 <= w.cx <= x1 and w not in label_words]
        if not ws:
            continue
        top = min(w.top for w in ws)                  # judge by the words in this box, not the whole merged line
        if top < lbottom - 2 or top - lbottom > max_dist:
            continue
        if _crosses(line, ws, x0):
            continue
        if ftype in ("text", "name"):
            ws = _segment(ws, x0)
        txt = " ".join(w.text for w in ws)
        if _is_box_label_start(ws, 0) and not seen_value_line:
            return None                       # reached the next box: this one is blank
        if looks_like_label(txt) or txt.lower().startswith(("not determined", "amount", "code(s)", "and telephone", "foreign postal")):
            if ftype in ("text", "name"):
                continue
        if ftype in ("text", "name"):
            if "{{" in txt or is_value_token(txt) and ftype == "name":
                continue
            return Hit(txt, ws, pg.number, 0.85, "below")
        for w in ws:
            t = _clean_token(w.text)
            if t in ("$", ""):
                continue
            if _type_ok(field, t):
                return Hit(t, [w], pg.number, 0.88, "below")
        seen_value_line = seen_value_line or any(is_value_token(w.text) for w in ws)
    return None


def read_block(field, pg, label_words, region):
    x0, x1 = column_for(pg, label_words, region)
    lbottom = max(w.bottom for w in label_words)
    out, last = [], lbottom
    for line in pg.lines_in(region):
        ws = [w for w in line.words if x0 <= w.cx <= x1 and w not in label_words]
        if not ws or min(w.top for w in ws) < lbottom - 2 or _crosses(line, ws, x0):
            continue
        ws = _segment(ws, x0, strict=True)
        if not ws:
            continue
        txt = " ".join(w.text for w in ws)
        gap = min(w.top for w in ws) - last
        if out and gap > 17:
            break
        if not out and gap > 40:
            break
        if looks_like_label(txt) or "TIN" in txt.split() or re.search(r"\b(?:TIN|identification number)\b", txt, re.I):
            if out:
                break
            continue
        if _is_box_label_start(ws, 0):
            break
        if "{{" in txt:
            continue
        out.append((txt, ws))
        last = max(w.bottom for w in ws)
        if len(out) >= 6:
            break
    if not out:
        return None
    words = [w for _, ws in out for w in ws]
    return Hit([t for t, _ in out], words, pg.number, 0.85, "block")


CITY_RE = re.compile(r"^(?P<city>.+?),?\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)$")
PHONE_RE = re.compile(r"^\(?\d{3}\)?[-.\s]?\d{3}-\d{4}$")


def split_block(lines):
    lines = [l.strip() for l in lines if l and l.strip()]
    lines = [l for l in lines if not PHONE_RE.match(l)]
    res = {"name": "", "name2": "", "street": "", "city": "", "state": "", "zip": ""}
    if not lines:
        return res
    ci = next((i for i in range(len(lines) - 1, -1, -1) if CITY_RE.match(lines[i])), None)
    if ci is not None:
        m = CITY_RE.match(lines[ci])
        res.update(city=m.group("city").strip(" ,"), state=m.group("state"), zip=m.group("zip"))
        head = lines[:ci]
    else:
        head = lines
    if head and re.match(r"^\d", head[0]):          # address-only block (no name line)
        res["street"] = " ".join(head)
    elif head:
        res["name"] = head[0]
        rest = head[1:]
        if len(rest) >= 2:
            res["name2"], res["street"] = rest[0], " ".join(rest[1:])
        elif rest:
            if re.match(r"^\d", rest[0]) or re.search(r"\b(?:street|st|ave|avenue|blvd|road|rd|drive|dr|lane|ln|box|suite|way|plaza|trail|court|ct)\b", rest[0], re.I):
                res["street"] = rest[0]
            else:
                res["name2"] = rest[0]
    return res


def read_check(field, pg, label_words, region):
    cy = sum(w.cy for w in label_words) / len(label_words)
    lx0, lx1 = min(w.x0 for w in label_words), max(w.x1 for w in label_words)
    lbottom = max(w.bottom for w in label_words)
    col_x1 = column_for(pg, label_words, region)[1]
    for w in pg.words_in(region):
        if w.text.strip() not in CHECK_MARKS:
            continue
        beside = abs(w.cy - cy) <= 7 and (lx0 - 40 <= w.x1 <= lx0 + 2 or lx1 - 2 <= w.x0 <= max(lx1 + 60, col_x1 + 30))
        under = 0 < w.top - lbottom <= 32 and lx0 - 15 <= w.cx <= lx1 + 25        # tick box printed under a stacked label
        if beside or under:
            return Hit(True, [w], pg.number, 0.9 if beside else 0.8, "check mark")
    return Hit(False, list(label_words), pg.number, 0.6, "no check mark printed")


def read_choice(field, pg, label_words, region):
    cy = sum(w.cy for w in label_words) / len(label_words)
    row = sorted([w for w in pg.words_in(region) if abs(w.cy - cy) <= 7], key=lambda w: w.x0)
    marks = [w for w in row if w.text.strip() in CHECK_MARKS]
    if not marks:
        return Hit("", list(label_words), pg.number, 0.5, "no option ticked")
    mk = marks[0]
    best, bd = None, 1e9
    for opt in field.get("options") or []:
        first = opt.split()[0]
        for i, w in enumerate(row):
            if w.text.strip().upper() != first.upper():
                continue
            # an option followed by more words (e.g. "Roth IRA") must match them all
            n = len(opt.split())
            if " ".join(x.text for x in row[i:i + n]).upper() != opt.upper():
                continue
            end = row[i + n - 1]
            d = (mk.x0 - end.x1) if end.x1 <= mk.x0 + 1 else (w.x0 - mk.x1) + 15
            if 0 <= d < bd:
                best, bd = opt, d
    return Hit(best or "", [mk], pg.number, 0.85 if best else 0.5, "ticked option")


def read_table(field, pages, regions):
    rrx, crx = compiled(field["row"]), compiled(field["col"])
    for pg in pages:
        region = regions.get(pg.number)
        lines = pg.lines_in(region)
        for li, line in enumerate(lines):
            if not rrx.search(line.text):
                continue
            # nearest header above the row that matches the column pattern
            header = None
            for hl in reversed(lines[:li]):
                if line.top - hl.top > 220:
                    break
                for i, w in enumerate(hl.words):
                    phrase = [w]
                    for nx in hl.words[i + 1:]:
                        if nx.x0 - phrase[-1].x1 > 7:
                            break
                        phrase.append(nx)
                    if crx.search(w.text) or crx.search(" ".join(p.text for p in phrase)):
                        header = phrase
                        break
                if header:
                    break
            if not header:
                continue
            hx = (min(w.x0 for w in header) + max(w.x1 for w in header)) / 2
            cands = [w for w in pg.words_in(region) if abs(w.cy - line.cy) <= 3.5 and token_type_ok("money", w.text)]
            if not cands:
                continue
            w = min(cands, key=lambda w: abs(w.cx - hx))
            if abs(w.cx - hx) <= 70:
                return Hit(w.text, [w], pg.number, 0.9, "table")
    return None


def extract_field(field, pages, regions):
    mode = field["mode"]
    if mode in ("manual", "part"):
        return None, False
    if mode == "table":
        h = read_table(field, pages, regions)
        return h, h is not None
    labels = find_labels(field, pages, regions)
    if not labels:
        return None, False
    for pg, line, lw in labels:
        region = regions.get(pg.number)
        h = None
        if mode == "check":
            h = read_check(field, pg, lw, region)
        elif mode == "choice":
            h = read_choice(field, pg, lw, region)
        elif mode == "block":
            h = read_block(field, pg, lw, region)
        elif mode == "same":
            h = read_same_line(field, pg, lw, region)
        elif mode == "below":
            h = read_below(field, pg, lw, region)
        else:
            h = read_same_line(field, pg, lw, region) or read_below(field, pg, lw, region)
        if h is not None and h.raw not in ("", None) or (h is not None and isinstance(h.raw, bool)):
            h.label_box = union_box(lw)
            return h, True
    pg, line, lw = labels[0]
    return Hit("", [], pg.number, 0.75, "label found, box is blank", union_box(lw)), True


# ---------------------------------------------------------------------------
# document detection
# ---------------------------------------------------------------------------
def detect_form(text):
    best, best_score = None, 0
    for ftype, d in catalog.FORMS.items():
        det = d["detect"]
        if any(compiled(r).search(text) for r in det.get("not", [])):
            continue
        if not all(compiled(r).search(text) for r in det.get("all", [])):
            continue
        score = 10 + 4 * sum(1 for r in det.get("any", []) if compiled(r).search(text))
        if not det.get("any") or score > 10:
            if score > best_score:
                best, best_score = ftype, score
    return best, best_score


PAGE_OF_RE = re.compile(r"\bPage\s+(\d+)\s+of\s+(\d+)\b", re.I)


def find_statements(pages):
    """Brokerage composite statements: 'Page 1 of N' ... 'Page N of N' (+ unnumbered continuation pages)."""
    stmts, i = [], 0
    while i < len(pages):
        m = PAGE_OF_RE.search(pages[i].text)
        if m and m.group(1) == "1" and int(m.group(2)) > 1:
            n = int(m.group(2))
            j = i + 1
            while j < len(pages):
                mm = PAGE_OF_RE.search(pages[j].text)
                if mm and (mm.group(1) == "1" or int(mm.group(2)) != n):
                    break
                j += 1
                if mm and int(mm.group(1)) == n:
                    break
            stmts.append((pages[i].number, pages[j - 1].number))
            i = j
        else:
            i += 1
    return stmts


def composite_sections(pages):
    """Section headers inside a composite statement -> [(ftype, page, Region)]."""
    heads = []
    for pg in pages:
        for line in pg.lines:
            for ftype, d in catalog.FORMS.items():
                rx = d.get("composite")
                if not rx:
                    continue
                for m in re.finditer(rx, line.text):
                    ws = line.words_in_span(m.start(), m.end())
                    if ws:
                        heads.append({"type": ftype, "page": pg.number, "x0": ws[0].x0, "top": min(w.top for w in ws)})
            for rx in BOUNDARY_RES:
                for m in re.finditer(rx, line.text):
                    ws = line.words_in_span(m.start(), m.end())
                    if ws:
                        heads.append({"type": None, "page": pg.number, "x0": ws[0].x0, "top": min(w.top for w in ws)})
    out = []
    for h in heads:
        if not h["type"]:
            continue
        pg = next(p for p in pages if p.number == h["page"])
        same = [o for o in heads if o["page"] == h["page"] and o is not h]
        x1 = min([o["x0"] - 3 for o in same if abs(o["top"] - h["top"]) < 8 and o["x0"] > h["x0"] + 20] + [pg.width])
        bottom = min([o["top"] - 1 for o in same if o["top"] > h["top"] + 8 and h["x0"] - 20 <= o["x0"] < x1] + [pg.height])
        out.append((h["type"], h["page"], Region(h["page"], max(0, h["x0"] - 6), h["top"] - 2, x1, bottom)))
    # one section per form type per statement (a section can continue on the next page)
    seen, res = set(), []
    for t, p, r in sorted(out, key=lambda x: (x[1], x[2].top, x[2].x0)):
        if t in seen:
            continue
        seen.add(t)
        res.append((t, p, r))
    return res


def statement_payer(pages):
    """Broker name from '<Broker> as agent' + the address block printed under that header on page 1."""
    name, pno, words = None, None, None
    for pg in pages:
        for line in pg.lines:
            m = re.match(r"^(.+?)\s+as agent\b", line.text)
            if m and "{{" not in m.group(1) and len(m.group(1)) > 3:
                name, pno, words = m.group(1).strip(), pg.number, line.words_in_span(m.start(1), m.end(1))
                break
        if name:
            break
    if not name:
        return None, None, None, []
    addr = []
    first = pages[0]
    head = next((l for l in first.lines[:8] if re.search(r"\bas agent\b", l.text)), None)
    if head:
        x0 = head.x0
        for line in first.lines:
            if line.top <= head.top or line.top - head.top > 50:
                continue
            seg = _segment([w for w in line.words if w.x0 >= x0 - 4], x0)
            txt = " ".join(w.text for w in seg)
            if not seg or txt.lower().startswith("for ") or "{{" in txt:
                continue
            addr.append((txt, seg))
            if CITY_RE.match(txt):
                break
        if not addr or not CITY_RE.match(addr[-1][0]):
            addr = []
    return name, pno, words, addr


# ---------------------------------------------------------------------------
# 1099-B sale lots (Form 8949 detail)
# ---------------------------------------------------------------------------
LOT_RE = re.compile(r"^(\d\d/\d\d/\d{4})\s+([\d,]+\.\d+)\s+([\d,]+\.\d\d)\s*([GN])?\s+(\d\d/\d\d/\d{4}|Various|VARIOUS)\s+([\d,]+\.\d\d)\s+"
                    r"([\d,]+\.\d\d)\s*([DW])?\s+(-?[\d,]+\.\d\d)(?:\s+(.*))?$")
SECTION_RE = re.compile(r"(SHORT|LONG) TERM TRANSACTIONS for (covered|noncovered) tax lots", re.I)
BOX_RE = re.compile(r"with Box ([A-F]) checked", re.I)
DESC_RE = re.compile(r"^[A-Za-z0-9].*\(([A-Z][A-Z.]{0,7})\)\s*$")


def parse_lots(pages):
    lots, section, desc = [], None, ""
    for pg in pages:
        for line in pg.lines:
            t = line.text.strip()
            m = SECTION_RE.search(t)
            if m:
                b = BOX_RE.search(t)
                section = {"term": "Short" if m.group(1).upper() == "SHORT" else "Long",
                           "box": b.group(1) if b else ("A" if m.group(1).upper() == "SHORT" else "D")}
                continue
            if not section:
                continue
            m = LOT_RE.match(t)
            if m:
                notes = (m.group(10) or "").strip()
                adj = money_value(m.group(7)) or 0.0
                code = m.group(8) or ("W" if "wash" in notes.lower() else ("D" if adj else ""))
                lots.append({"description": desc, "date_sold": m.group(1), "quantity": m.group(2),
                             "proceeds": m.group(3).replace(",", ""), "date_acquired": m.group(5),
                             "cost": m.group(6).replace(",", ""), "adjustment": f"{adj:.2f}", "adj_code": code if adj else "",
                             "gain": m.group(9).replace(",", ""), "term": section["term"], "box": section["box"],
                             "page": pg.number, "bbox": [round(line.x0, 1), round(line.top, 1), round(line.x1, 1), round(line.bottom, 1)]})
                continue
            d = DESC_RE.match(t)
            if d and not t.startswith(("Page", "Account")):
                desc = t
    return lots


# ---------------------------------------------------------------------------
# generic label/value pairs (for fields the catalog does not know)
# ---------------------------------------------------------------------------
def scan_pairs(pages, regions, used_boxes, limit=80):
    out = []

    def overlaps(b, page):
        for p, u in used_boxes:
            if p == page and not (b[2] < u[0] or b[0] > u[2] or b[3] < u[1] or b[1] > u[3]):
                return True
        return False

    for pg in pages:
        region = regions.get(pg.number)
        lines = pg.lines_in(region)
        for li, line in enumerate(lines):
            for wi, w in enumerate(line.words):
                t = _clean_token(w.text)
                if not is_value_token(t) or t in ("0.00", "$0.00"):
                    continue
                b = w.box()
                if overlaps(b, pg.number):
                    continue
                # label: words to the left on the same line, after the previous value
                lab = []
                for x in reversed(line.words[:wi]):
                    if is_value_token(x.text) or (lab and lab[0].x0 - x.x1 > 30):
                        break
                    lab.insert(0, x)
                label = " ".join(x.text for x in lab if x.text != "$").strip(" :")
                if len(label) < 3:
                    for up in reversed(lines[:li]):
                        if line.top - up.bottom > 16:
                            break
                        ws = [x for x in up.words if x.x0 <= w.x1 + 4 and x.x1 >= w.x0 - 60]
                        if ws and not any(is_value_token(x.text) for x in ws):
                            label = " ".join(x.text for x in ws)
                            break
                if not label or "{{" in label:
                    continue
                ftype = ("money" if token_type_ok("money", t) else "date" if token_type_ok("date", t)
                         else "ein" if token_type_ok("ein", t) else "ssn" if token_type_ok("ssn", t) else "text")
                out.append({"label": label[:70], "raw": t, "type": ftype, "page": pg.number, "bbox": b})
                if len(out) >= limit:
                    return out
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def _doc_year(pages, regions):
    cnt = Counter()
    for pg in pages:
        for line in pg.lines_in(regions.get(pg.number)):
            if re.search(r"\bRev\.|\bJanuary\b|/\d{4}", line.text):
                continue
            for m in re.finditer(r"\b(20[0-4]\d)\b", line.text):
                w = 3 if re.search(r"Form|Statement|Tax|W-2|1099|1098|5498|SSA|Benefits", line.text, re.I) else 1
                cnt[m.group(1)] += w
    return cnt.most_common(1)[0][0] if cnt else ""


def build_document(ftype, pages, regions, primary_page, learned, stmt=None):
    d = catalog.FORMS[ftype]
    fields = catalog.clone_fields(ftype)
    hits = {}
    used = []
    stmt_pages = stmt["pages"] if stmt else None
    for f in fields:
        if f["mode"] == "part":
            continue
        use_pages, use_regions = pages, regions
        if stmt_pages and (f["key"].startswith(IDENTITY_PREFIXES)):
            use_pages, use_regions = stmt_pages, {}
        h, found = extract_field(f, use_pages, use_regions)
        hits[f["key"]] = (h, found)
        if h is not None and h.words:
            used.append((h.page, h.box()))
    # composites: payer name from "<Broker> as agent"
    if stmt and "payer_block" in hits and not (hits["payer_block"][0] and hits["payer_block"][0].raw):
        name, pno, ws, addr = statement_payer(stmt_pages)
        if name:
            # the box drawn for the name stays on the page where the broker name is printed
            hits["payer_block"] = (Hit([name] + [t for t, _ in addr], ws, pno, 0.8, "statement header"), True)
            hits["payer_block"][0].words = ws

    out_fields, pdf_fields = [], []
    for f in fields:
        h, found = hits.get(f["key"], (None, False))
        raw, page, box, conf, how = "", None, None, 0.0, "not on the PDF"
        if f["mode"] == "part":
            bh, bfound = hits.get(f["block"], (None, False))
            if bh is not None and bh.raw:
                parts = split_block(bh.raw)
                raw = parts.get(f["part"], "")
                page, box, conf, how = bh.page, bh.box(), (bh.conf if raw else 0.75), "name/address block"
                # point at the exact line of the block
                if raw:
                    for ln_words in _block_lines(bh):
                        if " ".join(w.text for w in ln_words).find(raw.split(",")[0][:12]) >= 0 or raw in " ".join(w.text for w in ln_words):
                            box = union_box(ln_words)
                            break
                found = True
            else:
                found = bfound
        elif h is not None:
            raw, page, conf, how = h.raw, h.page, h.conf, h.how
            box = h.box() or h.label_box
        if f["mode"] == "block":
            continue
        value = normalize(f["type"], raw) if not isinstance(raw, bool) else raw
        if f["type"] == "bool" and raw == "":
            value = False
        status = "extracted" if (value not in ("", None) and value is not False) else ("blank" if found else "not_found")
        if f["type"] == "bool" and found:
            status = "extracted" if value else "blank"
        rec = {k: f[k] for k in ("key", "label", "type", "box", "section", "required", "aid", "control", "mode", "hint", "options", "ref", "pattern")}
        rec.update({"raw": raw if not isinstance(raw, list) else " / ".join(raw), "value": value, "display": display(f["type"], value),
                    "page": page, "bbox": box, "conf": round(conf, 2), "how": how, "status": status})
        out_fields.append(rec)
        if f["mode"] != "manual" and (status == "extracted" or (status == "blank" and box)):
            pdf_fields.append({"id": "f:" + f["key"], "label": (f"Box {f['box']} · " if f["box"] else "") + f["label"],
                               "value": value, "display": display(f["type"], value), "type": f["type"], "page": page,
                               "bbox": box, "conf": round(conf, 2), "auto": f["key"], "blank": status == "blank"})

    # extra label/value pairs the catalog did not claim
    extra = scan_pairs(pages, regions, used)
    rules = (learned or {}).get(ftype, {})
    by_key = {f["key"]: f for f in out_fields}
    for i, x in enumerate(extra, 1):
        auto = rules.get(norm_label(x["label"]))
        if auto and auto in by_key and by_key[auto]["status"] != "extracted":
            fld = by_key[auto]
            fld.update(raw=x["raw"], value=normalize(fld["type"], x["raw"]), page=x["page"], bbox=x["bbox"], conf=0.7,
                       how="learned mapping", status="extracted")
            fld["display"] = display(fld["type"], fld["value"])
        else:
            auto = None
        pdf_fields.append({"id": f"x:{i}", "label": x["label"], "value": normalize(x["type"], x["raw"]),
                           "display": display(x["type"], normalize(x["type"], x["raw"])), "type": x["type"], "page": x["page"],
                           "bbox": x["bbox"], "conf": 0.5, "auto": auto, "extra": True})

    vals = {f["key"]: f["value"] for f in out_fields}
    payer = vals.get(d.get("payer_key") or "", "") or ""
    amounts = [money_value(f["value"]) for f in out_fields if f["type"] == "money" and f["value"] not in ("", None)]
    return {
        "type": ftype, "form_name": d["name"], "module": d["module"], "screen": d["screen"], "screen_name": d["screen_name"],
        "informational": bool(d.get("informational")), "drake_verified": bool(d.get("drake_verified")),
        "page": primary_page, "pages": sorted({p.number for p in pages} | ({p.number for p in stmt_pages} if stmt_pages else set())),
        "regions": [r.as_dict() for r in regions.values()] if regions else [],
        "payer": payer, "payer_tin": vals.get(d.get("payer_tin_key") or "", ""),
        "recipient_tin": vals.get(d.get("recipient_tin_key") or "", ""),
        "key_amount": vals.get(d.get("key_amount") or "", ""),
        "zero_value": bool(amounts) and all(abs(a or 0) < 0.005 for a in amounts),
        "year": _doc_year(pages, regions) or (_doc_year(stmt_pages, {}) if stmt_pages else ""),
        "statement": stmt["range"] if stmt else None,
        "fields": out_fields, "pdf_fields": pdf_fields, "flags": [],
    }


def _block_lines(hit):
    rows = {}
    for w in hit.words:
        rows.setdefault(round(w.cy / 3), []).append(w)
    return [sorted(v, key=lambda w: w.x0) for _, v in sorted(rows.items())]


def unknown_document(pg, learned):
    pairs = scan_pairs([pg], {}, [])
    title = next((l.text for l in pg.lines[:6] if len(l.text) > 8), f"Page {pg.number}")
    return {
        "type": "UNKNOWN", "form_name": "Unrecognized document", "module": "Miscellaneous", "screen": "",
        "screen_name": "Unrecognized document — map manually", "informational": False, "drake_verified": False,
        "page": pg.number, "pages": [pg.number], "regions": [], "payer": title[:60], "payer_tin": "", "recipient_tin": "",
        "key_amount": "", "zero_value": False, "year": _doc_year([pg], {}), "statement": None, "fields": [],
        "pdf_fields": [{"id": f"x:{i}", "label": x["label"], "value": normalize(x["type"], x["raw"]),
                        "display": display(x["type"], normalize(x["type"], x["raw"])), "type": x["type"], "page": x["page"],
                        "bbox": x["bbox"], "conf": 0.5, "auto": None, "extra": True} for i, x in enumerate(pairs, 1)],
        "flags": [{"level": "warn", "text": "This page was not recognised as a supported tax form. Review it and map any values "
                                            "to a Drake screen manually, or exclude it."}] if not pg.needs_ocr else
                 [{"level": "warn", "text": "This page has no text layer (scanned image) and OCR is not installed. Enter its values manually."}],
    }


def analyze_pdf(path, learned=None, progress=None):
    """Full analysis. Page text is cached per file content; detection/extraction always re-runs so
    newly learned mappings apply immediately."""
    key = file_key(path)
    prog = progress or (lambda *a: None)
    prog("Reading every page", 5)
    with _cache_lock:
        pages = _cache.get(key)
    if pages is None:
        pages = load_pages(path)
        with _cache_lock:
            _cache.clear()
            _cache[key] = pages
    by_no = {p.number: p for p in pages}
    prog(f"Read {len(pages)} pages — finding the tax forms", 35)

    docs, page_info = [], {p.number: {"page": p.number, "kind": "unclassified", "docs": [], "ocr": p.ocr, "needs_ocr": p.needs_ocr,
                                       "label": ""} for p in pages}
    claimed = set()

    # 1) brokerage composite statements
    for a, b in find_statements(pages):
        sp = [by_no[n] for n in range(a, b + 1)]
        sections = composite_sections(sp)
        if not sections:
            continue
        stmt = {"pages": sp, "range": [a, b]}
        for ftype, pno, region in sections:
            doc = build_document(ftype, [by_no[pno]], {pno: region}, pno, learned, stmt=stmt)
            doc["composite"] = True
            if catalog.FORMS[ftype].get("lots"):
                doc["lots"] = parse_lots(sp)
            docs.append(doc)
        for n in range(a, b + 1):
            claimed.add(n)
            page_info[n]["kind"] = "statement"
            page_info[n]["label"] = f"Composite statement p.{a}–{b}"

    # 2) standalone forms, page by page
    prev_doc = None
    for pg in pages:
        if pg.number in claimed:
            prev_doc = None
            continue
        ftype, score = detect_form(pg.text)
        if ftype:
            doc = build_document(ftype, [pg], {}, pg.number, learned)
            doc["detect_score"] = score
            docs.append(doc)
            prev_doc = doc
            page_info[pg.number]["kind"] = "form"
            page_info[pg.number]["label"] = ftype
            continue
        if prev_doc and (re.search(r"continued|Instructions for (?:Recipient|Employee|Borrower|Participant)", pg.text, re.I)):
            prev_doc["pages"] = sorted(set(prev_doc["pages"] + [pg.number]))
            page_info[pg.number]["kind"] = "supporting"
            page_info[pg.number]["label"] = f"continues {prev_doc['type']} p.{prev_doc['page']}"
            continue
        if len(pg.text) < 40 and not pg.needs_ocr:
            page_info[pg.number]["kind"] = "blank"
            continue
        doc = unknown_document(pg, learned)
        docs.append(doc)
        page_info[pg.number]["kind"] = "unknown"
        page_info[pg.number]["label"] = "Unrecognized"
        prev_doc = None

    prog(f"Found {len(docs)} documents — checking them", 75)
    docs.sort(key=lambda d: (d["page"], (d["regions"][0]["top"] if d["regions"] else 0), (d["regions"][0]["x0"] if d["regions"] else 0)))
    for i, d in enumerate(docs, 1):
        d["id"] = f"d{i:02d}-{re.sub(r'[^A-Za-z0-9]', '', d['type'])}-p{d['page']}"
    for d in docs:
        for p in d["pages"]:
            page_info[p]["docs"].append(d["id"])

    result = {"file": os.path.basename(path), "file_key": key, "total_pages": len(pages), "documents": docs,
              "pages": [page_info[n] for n in sorted(page_info)]}
    from . import derive
    derive.finish(result, pages)
    prog("Analysis complete", 100)
    return result
