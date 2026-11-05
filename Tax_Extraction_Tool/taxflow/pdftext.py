"""
Positioned text model of a PDF.

Every word keeps its page and bounding box (PDF points, origin top-left — the same space pdf.js uses
at scale 1), so each extracted value can be traced back to the exact spot on the original page.

Scanned pages (no text layer) are OCR'd when pytesseract + Tesseract are installed; otherwise they are
reported as "needs OCR / manual entry" instead of being silently skipped.
"""
import re

import pdfplumber

LINE_TOL = 3.0          # words whose vertical centres differ by <= this many points share a line


class Word:
    __slots__ = ("text", "x0", "x1", "top", "bottom", "page")

    def __init__(self, text, x0, x1, top, bottom, page):
        self.text, self.x0, self.x1, self.top, self.bottom, self.page = text, x0, x1, top, bottom, page

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.top + self.bottom) / 2

    def box(self):
        return [round(self.x0, 1), round(self.top, 1), round(self.x1, 1), round(self.bottom, 1)]


class Line:
    def __init__(self, words):
        self.words = sorted(words, key=lambda w: w.x0)
        self.top = min(w.top for w in self.words)
        self.bottom = max(w.bottom for w in self.words)
        self.x0 = min(w.x0 for w in self.words)
        self.x1 = max(w.x1 for w in self.words)
        self.page = self.words[0].page
        parts, spans, pos = [], [], 0
        for w in self.words:
            spans.append((pos, pos + len(w.text)))
            parts.append(w.text)
            pos += len(w.text) + 1
        self.text = " ".join(parts)
        self.spans = spans

    @property
    def cy(self):
        return (self.top + self.bottom) / 2

    def words_in_span(self, a, b):
        return [w for w, (s, e) in zip(self.words, self.spans) if e > a and s < b]

    def subline(self, x0=None, x1=None):
        ws = [w for w in self.words if (x0 is None or w.cx >= x0) and (x1 is None or w.cx <= x1)]
        return Line(ws) if ws else None


class Region:
    """Rectangle on one page (used for side-by-side forms on brokerage composite pages)."""
    __slots__ = ("page", "x0", "top", "x1", "bottom")

    def __init__(self, page, x0=0.0, top=0.0, x1=1e9, bottom=1e9):
        self.page, self.x0, self.top, self.x1, self.bottom = page, x0, top, x1, bottom

    def contains(self, w):
        return self.x0 - 1 <= w.cx <= self.x1 + 1 and self.top - 1 <= w.cy <= self.bottom + 1

    def as_dict(self):
        return {"page": self.page, "x0": round(self.x0, 1), "top": round(self.top, 1),
                "x1": round(min(self.x1, 5000), 1), "bottom": round(min(self.bottom, 5000), 1)}


def build_lines(words):
    lines, cur = [], []
    for w in sorted(words, key=lambda w: (w.cy, w.x0)):
        if cur and abs(w.cy - sum(x.cy for x in cur) / len(cur)) > LINE_TOL:
            lines.append(Line(cur))
            cur = []
        cur.append(w)
    if cur:
        lines.append(Line(cur))
    return sorted(lines, key=lambda l: (l.top, l.x0))


class Page:
    def __init__(self, number, width, height, words, ocr=False, needs_ocr=False):
        self.number, self.width, self.height = number, width, height
        self.words = words
        self.lines = build_lines(words) if words else []
        self.text = "\n".join(l.text for l in self.lines)
        self.ocr = ocr
        self.needs_ocr = needs_ocr

    def lines_in(self, region=None):
        if region is None:
            return self.lines
        out = []
        for l in self.lines:
            ws = [w for w in l.words if region.contains(w)]
            if ws:
                out.append(l if len(ws) == len(l.words) else Line(ws))
        return out

    def words_in(self, region=None):
        return [w for w in self.words if region is None or region.contains(w)]

    def text_in(self, region=None):
        return "\n".join(l.text for l in self.lines_in(region))


def _ocr_words(pl_page, number):
    """Optional OCR for scanned pages. Returns [] when pytesseract/Tesseract are not available."""
    try:
        import pytesseract
    except Exception:
        return None
    try:
        res = 200
        img = pl_page.to_image(resolution=res).original
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    except Exception:
        return None
    k = 72.0 / res
    out = []
    for i, t in enumerate(data.get("text", [])):
        t = (t or "").strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if not t or conf < 35:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        out.append(Word(t, x * k, (x + w) * k, y * k, (y + h) * k, number))
    return out


def load_pages(path):
    pages = []
    with pdfplumber.open(path) as pdf:
        for i, p in enumerate(pdf.pages, 1):
            try:
                raw = p.extract_words(keep_blank_chars=False, x_tolerance=1.5, y_tolerance=2, use_text_flow=False)
            except Exception:
                raw = []
            words = [Word(w["text"], float(w["x0"]), float(w["x1"]), float(w["top"]), float(w["bottom"]), i)
                     for w in raw if str(w.get("text", "")).strip()]
            ocr, needs = False, False
            if sum(len(w.text) for w in words) < 25:
                o = _ocr_words(p, i)
                if o:
                    words, ocr = o, True
                else:
                    needs = True
            pages.append(Page(i, float(p.width), float(p.height), words, ocr=ocr, needs_ocr=needs))
    return pages


# ---------------------------------------------------------------------------
# Value tokens
# ---------------------------------------------------------------------------
MONEY_RE = re.compile(r"^\(?-?\$?\(?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})\)?$|^\(?-?\$?\d{1,3}(?:,\d{3})+\)?$|^\$\d+$")
SSN_RE = re.compile(r"^(?:\d{3}-\d{2}-\d{4}|\d{9}|[*Xx]{3}-[*Xx]{2}-\d{4}|\*{5}\d{4}|X{5}\d{4})$")
EIN_RE = re.compile(r"^\d{2}-\d{7}$")
TIN_RE = re.compile(r"^(?:\d{2}-\d{7}|\d{3}-\d{2}-\d{4}|\d{9}|[*Xx]{3}-[*Xx]{2}-\d{4}|[*Xx]{5}\d{4})$")
DATE_RE = re.compile(r"^(?:\d{1,2}/\d{1,2}/(?:\d{2}|\d{4})|\d{4}-\d{2}-\d{2}|\d{1,2}-\d{1,2}-\d{4})$")
ZIP_RE = re.compile(r"^\d{5}(?:-\d{4})?$")
STATE_RE = re.compile(r"^[A-Z]{2}$")
YEAR_RE = re.compile(r"^(?:19|20)\d\d$")
PCT_RE = re.compile(r"^-?\d{1,3}(?:\.\d+)?%$")
INT_RE = re.compile(r"^\d{1,6}$")
CHECK_MARKS = {"✓", "✔", "☒", "■", "☑", "X", "x", "[X]", "[x]", "⊠"}
US_STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
                "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY AS GU MP PR VI".split())

# a token that starts another box label: "2", "2a", "12b", "2-", "b", "1a-" (followed by a capitalised word)
BOX_START_RE = re.compile(r"^(?:\d{1,2}[a-z]?|[a-f])[-.]?$")


def money_value(s):
    s = str(s or "").strip()
    neg = s.startswith("(") and s.endswith(")") or "-" in s[:2]
    d = re.sub(r"[^\d.]", "", s)
    if not d or d == ".":
        return None
    try:
        v = float(d)
    except ValueError:
        return None
    return -v if neg else v


def token_type_ok(ftype, tok):
    t = tok.strip()
    if ftype == "money":
        return bool(MONEY_RE.match(t))
    if ftype == "ssn":
        return bool(SSN_RE.match(t))
    if ftype == "ein":
        return bool(EIN_RE.match(t))
    if ftype == "tin":
        return bool(TIN_RE.match(t))
    if ftype == "date":
        return bool(DATE_RE.match(t))
    if ftype == "zip":
        return bool(ZIP_RE.match(t))
    if ftype == "state":
        return t in US_STATES
    if ftype == "year":
        return bool(YEAR_RE.match(t))
    if ftype == "percent":
        return bool(PCT_RE.match(t))
    if ftype == "int":
        return bool(INT_RE.match(t))
    if ftype == "code":
        return bool(re.match(r"^[A-Z0-9]{1,3}$", t))
    if ftype == "account":
        if ZIP_RE.match(t) or MONEY_RE.match(t) or DATE_RE.match(t) or TIN_RE.match(t):
            return False
        return bool(re.match(r"^(?=.*\d)(?:[*Xx#]+[\w-]*|[A-Za-z0-9-]{6,})$", t))
    return bool(t)


def is_value_token(tok):
    t = tok.strip()
    return bool(MONEY_RE.match(t) or TIN_RE.match(t) or DATE_RE.match(t) or PCT_RE.match(t))


LABEL_WORDS = {"name", "address", "street", "city", "town", "state", "zip", "code", "number", "postal", "telephone", "no.",
               "province", "country", "foreign", "including", "apt.", "identification", "instructions", "(see", "see",
               "copy", "omb", "tin", "payer's", "recipient's", "employer's", "employee's", "(including", "apt", "and",
               "or", "of", "the", "(ein)", "lender's", "borrower's", "trustee's", "issuer's", "participant's", "no."}


def looks_like_label(text):
    ws = [w.lower().strip(",.:;") for w in text.split()]
    if not ws:
        return False
    hits = sum(1 for w in ws if w in LABEL_WORDS or w.rstrip(".,") in LABEL_WORDS)
    return hits >= 2 and hits >= len(ws) * 0.5
