"""
Packet-level work after every document has been read:
  * tax year of the packet and per-document year mismatches
  * taxpayer / spouse identity (Drake Screen 1) and the T/S owner code of every form
  * derived screens (Screen 1, Form 1116 foreign tax credit)
  * duplicates, zero-value forms, reconciliations and cross-form relationships
  * Drake record numbers ("record 2 of 3" on a screen) in packet order, and the module list
"""
import re
from collections import Counter, defaultdict

from . import catalog
from .extract import display, normalize, union_box
from .pdftext import money_value
from .validate import validate

TIN_KEYS = {"W-2": ("employee_ssn", "employee_name"), "SSA-1099": ("beneficiary_ssn", "beneficiary_name"),
            "1098": ("borrower_tin", "borrower_name"), "5498": ("participant_tin", "participant_name"),
            "1098-T": ("student_tin", "student_name")}
SUFFIXES = {"JR", "JR.", "SR", "SR.", "II", "III", "IV"}


def fval(doc, key):
    for f in doc["fields"]:
        if f["key"] == key:
            return f
    return None


def v(doc, key):
    f = fval(doc, key)
    return f["value"] if f else ""


def last4(tin):
    d = re.sub(r"\D", "", str(tin or ""))
    return d[-4:] if len(d) >= 4 else ""


def split_name(full):
    parts = [p for p in re.split(r"\s+", str(full or "").strip()) if p]
    suffix = ""
    if parts and parts[-1].upper() in SUFFIXES:
        suffix = parts.pop()
    if not parts:
        return "", "", "", suffix
    if len(parts) == 1:
        return parts[0], "", "", suffix
    first, last = parts[0], parts[-1]
    mi = parts[1][0] if len(parts) > 2 else ""
    return first, mi, last, suffix


def _src(f):
    return {"page": f["page"], "bbox": f["bbox"]} if f and f.get("page") else {"page": None, "bbox": None}


def make_field(key, value, src=None, how="derived from the forms"):
    d = next(x for x in catalog.DERIVED["TAXPAYER"]["fields"] + catalog.DERIVED["FOREIGN"]["fields"] if x["key"] == key)
    rec = {k: d[k] for k in ("key", "label", "type", "box", "section", "required", "aid", "control", "mode", "hint", "options", "ref", "pattern")}
    value = normalize(d["type"], value)
    rec.update({"raw": value, "value": value, "display": display(d["type"], value), "page": (src or {}).get("page"),
                "bbox": (src or {}).get("bbox"), "conf": 0.8 if value else 0.0, "how": how,
                "status": "extracted" if value else "not_found"})
    return rec


def identities(docs):
    groups = defaultdict(lambda: {"tins": [], "names": [], "docs": [], "addr": None, "src": {}})
    for d in docs:
        keys = TIN_KEYS.get(d["type"], ("recipient_tin", "recipient_name"))
        tf, nf = fval(d, keys[0]), fval(d, keys[1])
        if not tf or not tf["value"]:
            continue
        l4 = last4(tf["value"])
        if not l4:
            continue
        g = groups[l4]
        g["docs"].append(d)
        if re.fullmatch(r"\d{9}", str(tf["value"])):
            g["tins"].append((tf["value"], tf))
        if nf and nf["value"]:
            g["names"].append((nf["value"], nf, d["type"] == "W-2"))
        if d["type"] == "W-2" and fval(d, "employee_street") and v(d, "employee_street"):
            g["addr"] = g["addr"] or {k: fval(d, "employee_" + k) for k in ("street", "city", "state", "zip")}
        elif fval(d, "recipient_street") and v(d, "recipient_street") and not g["addr"]:
            m = re.match(r"^(.+?),?\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$", str(v(d, "recipient_cityline")))
            if m:
                cl = fval(d, "recipient_cityline")
                g["addr"] = {"street": fval(d, "recipient_street"),
                             "city": {**cl, "value": m.group(1)}, "state": {**cl, "value": m.group(2)}, "zip": {**cl, "value": m.group(3)}}
    ranked = sorted(groups.items(), key=lambda kv: (-len(kv[1]["docs"]), not any(x["type"] == "W-2" for x in kv[1]["docs"])))
    out = []
    for l4, g in ranked[:2]:
        names = sorted(g["names"], key=lambda n: (not n[2],))
        name = Counter(n[0] for n in names).most_common(1)[0][0] if names else ""
        name_f = next((n[1] for n in names if n[0] == name), None)
        tin, tin_f = (g["tins"][0] if g["tins"] else ("", None))
        out.append({"last4": l4, "ssn": tin, "ssn_f": tin_f, "name": name, "name_f": name_f, "addr": g["addr"], "count": len(g["docs"])})
    return out


def finish(result, pages):
    docs = result["documents"]
    by_no = {p.number: p for p in pages}
    checks = []

    # ---- tax year
    years = Counter(d["year"] for d in docs if d.get("year"))
    year = years.most_common(1)[0][0] if years else ""
    result["tax_year"] = year
    for d in docs:
        if d.get("year") and year and d["year"] != year:
            d["flags"].append({"level": "warn", "text": f"This form appears to be for {d['year']}, the packet is for {year}."})

    # ---- SSA variant
    for d in docs:
        if d["type"] == "SSA-1099":
            txt = "\n".join(by_no[p].text for p in d["pages"])
            variant = "SSA-1042S" if re.search(r"1042S", txt, re.I) else "SSA-1099"
            f = fval(d, "form_variant")
            if f:
                f.update(value=variant, display=variant, raw=variant, status="extracted", how="form title", conf=0.95)
            if variant == "SSA-1042S":
                d["flags"].append({"level": "warn", "text": "SSA-1042S is issued to nonresident aliens. If the taxpayer is a U.S. resident they "
                                                            "normally receive an SSA-1099 — confirm before entering it on Drake's SSA screen."})

    # ---- taxpayer / spouse
    ids = identities(docs)
    tp = ids[0] if ids else None
    sp = ids[1] if len(ids) > 1 and (ids[1]["ssn"] or ids[1]["name"]) else None
    result["taxpayer"] = {"name": tp["name"], "ssn": tp["ssn"], "last4": tp["last4"]} if tp else None
    result["spouse"] = {"name": sp["name"], "ssn": sp["ssn"], "last4": sp["last4"]} if sp else None
    for d in docs:
        f = fval(d, "ts")
        if not f:
            continue
        keys = TIN_KEYS.get(d["type"], ("recipient_tin",))
        l4 = last4(v(d, keys[0])) or last4(d.get("recipient_tin"))
        code = "S" if sp and l4 and l4 == sp["last4"] else "T"
        f.update(value=code, display=code, raw=code, status="extracted", conf=0.9 if l4 else 0.6,
                 how=("recipient SSN matches the spouse" if code == "S" else "recipient SSN matches the taxpayer") if l4 else "defaulted to taxpayer")
    if len(ids) > 2:
        checks.append({"level": "warn", "doc": None, "text": "Forms are addressed to more than two people (TINs ending "
                       + ", ".join(i["last4"] for i in ids) + ") — check that every form belongs to this return."})

    if tp:
        first, mi, last, _ = split_name(tp["name"])
        nsrc = _src(tp["name_f"])
        a = tp["addr"] or {}
        fields = [make_field("filing_status", ""), make_field("tp_first", first, nsrc), make_field("tp_mi", mi, nsrc), make_field("tp_last", last, nsrc),
                  make_field("tp_ssn", tp["ssn"], _src(tp["ssn_f"]))]
        if sp:
            sf, _, sl, _ = split_name(sp["name"])
            fields += [make_field("sp_first", sf, _src(sp["name_f"])), make_field("sp_last", sl, _src(sp["name_f"])),
                       make_field("sp_ssn", sp["ssn"], _src(sp["ssn_f"]))]
        else:
            fields += [make_field("sp_first", ""), make_field("sp_last", ""), make_field("sp_ssn", "")]
        for k in ("street", "city", "state", "zip"):
            fields.append(make_field(k, (a.get(k) or {}).get("value", ""), _src(a.get(k))))
        src_doc = next((d for d in docs if tp["name_f"] and fval(d, tp["name_f"]["key"]) is tp["name_f"]), None)
        pdf_fields = [{"id": "f:" + f["key"], "label": f["label"], "value": f["value"], "display": f["display"], "type": f["type"],
                       "page": f["page"], "bbox": f["bbox"], "conf": f["conf"], "auto": f["key"]} for f in fields if f["value"]]
        docs.insert(0, {"id": "d00-TAXPAYER", "type": "TAXPAYER", "form_name": "Taxpayer information (from the forms)", "module": "General",
                        "screen": "1", "screen_name": catalog.DERIVED["TAXPAYER"]["screen_name"], "informational": False,
                        "drake_verified": False, "page": (src_doc or docs[0])["page"] if docs else 1,
                        "pages": sorted({f["page"] for f in fields if f["page"]}) or [1], "regions": [], "payer": tp["name"],
                        "payer_tin": "", "recipient_tin": tp["ssn"], "key_amount": "", "zero_value": False, "year": year,
                        "statement": None, "fields": fields, "pdf_fields": pdf_fields, "derived": True,
                        "flags": [{"level": "info", "text": "Built from the names, SSNs and addresses printed on the forms. Drake opens (or creates) "
                                                            "the return with this SSN before anything is entered."}]})

    # ---- foreign tax (Form 1116) from brokerage statements
    for d in [x for x in docs if x["type"] == "1099-DIV" and (money_value(v(x, "box7")) or 0) > 0 and x.get("statement")]:
        a, b = d["statement"]
        sp_pages = [by_no[n] for n in range(a, b + 1)]
        tax_amt, tax_w, inc_amt, inc_w, countries = None, None, None, None, []
        for pg in sp_pages:
            for line in pg.lines:
                m = re.match(r"^Foreign Tax\s+([\d,]+\.\d\d)$", line.text)
                if m and tax_amt is None:
                    tax_amt, tax_w = m.group(1), (pg.number, union_box(line.words[-1:]))
                m = re.search(r"Total Foreign Source Income\*?\s+([\d,]+\.\d\d)", line.text)
                if m and inc_amt is None:
                    inc_amt, inc_w = m.group(1), (pg.number, union_box(line.words[-1:]))
                m = re.match(r"^Total ([A-Z][A-Z ]+?)\s+[\d,]+\.\d\d", line.text)
                if m and m.group(1).strip() not in ("FOREIGN", "INTEREST", "DIVIDENDS"):
                    countries.append(m.group(1).strip().title())
        f7 = fval(d, "box7")
        fields = [make_field("source", d["payer"], _src(fval(d, "payer_name"))),
                  make_field("foreign_tax_1099", f7["value"], _src(f7)),
                  make_field("foreign_tax_summary", tax_amt or "", {"page": tax_w[0], "bbox": tax_w[1]} if tax_w else None),
                  make_field("foreign_income", inc_amt or "", {"page": inc_w[0], "bbox": inc_w[1]} if inc_w else None),
                  make_field("countries", ", ".join(sorted(set(countries))))]
        fd = {"id": f"{d['id']}-1116", "type": "FOREIGN", "form_name": "Foreign tax credit (from the brokerage statement)", "module": "Foreign",
              "screen": "1116", "screen_name": catalog.DERIVED["FOREIGN"]["screen_name"], "informational": False, "drake_verified": False,
              "page": tax_w[0] if tax_w else d["page"], "pages": sorted({d["page"]} | ({tax_w[0]} if tax_w else set())), "regions": [],
              "payer": d["payer"], "payer_tin": d["payer_tin"], "recipient_tin": "", "key_amount": f7["value"], "zero_value": False,
              "year": year, "statement": d["statement"], "fields": fields, "derived": True, "derived_from": d["id"],
              "pdf_fields": [{"id": "f:" + f["key"], "label": f["label"], "value": f["value"], "display": f["display"], "type": f["type"],
                              "page": f["page"], "bbox": f["bbox"], "conf": f["conf"], "auto": f["key"]} for f in fields if f["value"]],
              "flags": []}
        if tax_amt and abs((money_value(tax_amt) or 0) - (money_value(f7["value"]) or 0)) >= 0.05:
            fd["flags"].append({"level": "warn", "text": f"Foreign tax on the 1099-DIV ({f7['display']}) differs from the per-country summary "
                                                         f"({tax_amt}). Decide which amount belongs on Form 1116."})
        docs.append(fd)

    # ---- 1099-B lot reconciliation
    for d in [x for x in docs if x.get("lots") is not None]:
        lots = d["lots"]
        for term, pre in (("Short", "st"), ("Long", "lt")):
            ls = [l for l in lots if l["term"] == term]
            p = sum(float(l["proceeds"]) for l in ls)
            c = sum(float(l["cost"]) for l in ls)
            ep, ec = money_value(v(d, pre + "_proceeds")), money_value(v(d, pre + "_cost"))
            if ep is None and not ls:
                continue
            ok = ep is not None and ec is not None and abs(p - ep) < 0.05 and abs(c - ec) < 0.05
            d["flags"].append({"level": "ok" if ok else "warn",
                               "text": f"{term}-term: {len(ls)} sale lots total proceeds {p:,.2f} / cost {c:,.2f} "
                                       + ("match the summary." if ok else f"do NOT match the summary ({(ep or 0):,.2f} / {(ec or 0):,.2f}).")})
        ws = [l for l in lots if l["adj_code"] == "W"]
        if ws:
            d["flags"].append({"level": "info", "text": f"{len(ws)} lot(s) with wash-sale loss disallowed "
                                                        f"(total {sum(float(l['adjustment']) for l in ws):,.2f}) — Form 8949 code W."})
        if lots:
            d["flags"].append({"level": "info", "text": f"{len(lots)} sale lots will be sent to Drake as a Form 8949 import file "
                                                        "(Drake: Screen 8949 → Import)."})

    # ---- duplicates + zero-value
    seen = {}
    for d in docs:
        if d.get("derived") or d["type"] == "UNKNOWN" or not d.get("key_amount"):
            continue
        k = (d["type"], re.sub(r"\D", "", d.get("payer_tin") or "") or (d.get("payer") or "").upper(), d["key_amount"], d.get("recipient_tin"))
        if k in seen:
            d["duplicate_of"] = seen[k]["id"]
            d["flags"].append({"level": "warn", "text": f"Looks like a duplicate of the {d['type']} on page {seen[k]['page']} "
                                                        "(same payer and amounts). It is excluded by default — include it only if it is a separate form."})
        else:
            seen[k] = d
    for d in docs:
        if d.get("zero_value"):
            d["flags"].append({"level": "info", "text": "Every amount on this form is 0.00 — nothing needs to be entered in Drake."})

    # ---- relationships
    for r in [x for x in docs if x["type"] == "1099-R"]:
        g = money_value(v(r, "box1"))
        for c in [x for x in docs if x["type"] == "5498" and money_value(v(x, "box3"))]:
            if g and abs(g - money_value(v(c, "box3"))) < 0.05:
                r["flags"].append({"level": "info", "text": f"The gross distribution equals the Roth conversion on the 5498 (page {c['page']}) — "
                                                            "report the conversion on Form 8606 Part II and check the distribution code."})
        acct = v(r, "account")
        if acct and v(r, "box7_ira") is not True and any(x["type"] == "5498" and v(x, "account") == acct for x in docs):
            r["flags"].append({"level": "warn", "text": f"This account ({acct}) also has a Form 5498 (IRA), but the IRA/SEP/SIMPLE box "
                                                        "was not read as ticked — verify."})
    for d in [x for x in docs if x["type"] == "1098" and money_value(v(x, "box10"))]:
        d["flags"].append({"level": "info", "text": f"Box 10 ({fval(d, 'box10')['display']}) is usually property tax paid from escrow — "
                                                    "it also belongs on Schedule A (taxes)."})
    for pinfo in result["pages"]:
        if pinfo["needs_ocr"]:
            checks.append({"level": "warn", "doc": None, "text": f"Page {pinfo['page']} is a scanned image without text. Install Tesseract OCR "
                                                                   "for automatic reading, or enter its values manually."})

    result["checks"] = checks
    number_and_group(result)


def number_and_group(result):
    """Drake record numbers per screen (packet order), validation, and the module list."""
    docs = result["documents"]
    year = result.get("tax_year", "")
    order = {m: i for i, m in enumerate(catalog.MODULES)}
    docs.sort(key=lambda d: (order.get(d["module"], 99), 0 if d["type"] == "TAXPAYER" else 1, d["page"],
                             (d["regions"][0]["top"] if d.get("regions") else 0)))
    count, seen_n = Counter(d["screen"] or d["type"] for d in docs), Counter()
    for d in docs:
        k = d["screen"] or d["type"]
        seen_n[k] += 1
        d["record"], d["records"] = seen_n[k], count[k]
        d.setdefault("excluded_default", bool(d.get("duplicate_of")) or d["type"] in ("1095-B", "1095-C"))
        vals = {f["key"]: f["value"] for f in d["fields"]}
        d["issues"] = validate(d["type"], d["fields"], vals, year)
    modules = []
    for m in catalog.MODULES:
        ds = [d for d in docs if d["module"] == m]
        if ds:
            modules.append({"name": m, "docs": [d["id"] for d in ds],
                            "screens": sorted({d["screen"] for d in ds if d["screen"]}, key=lambda s: [d["screen"] for d in ds].index(s))})
    result["modules"] = modules
    result["absent_modules"] = [m for m in catalog.MODULES if m not in {x["name"] for x in modules}]
    result["counts"] = {"documents": len([d for d in docs if not d.get("derived")]),
                        "by_type": dict(Counter(d["type"] for d in docs if not d.get("derived")))}
