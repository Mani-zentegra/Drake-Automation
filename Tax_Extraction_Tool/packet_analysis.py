"""
Whole-packet analysis for the Drake-style module screens (/drake-modules).

* FORM_REGISTRY describes every supported form type once: which Drake Data Entry module (tab) and
  screen it belongs to, and which fields it has (key, box, label, type). The frontend draws every
  screen from this registry, so supporting a new form = add one registry entry (+ its extractor).
* analyze_packet() reads all pages: it reuses packet_extractor for the information returns, then
  adds what that extractor does not cover — 1099-B sale lots (Form 8949 detail), the detail-page
  totals used for reconciliation, the foreign income/tax summary and broker fees — and works out
  relationships and consistency checks between the forms.
* Nothing is hard-coded to this client: forms, pages, counts and values all come from the PDF.
"""
import os
import re
import threading

import pypdf
from flask import Blueprint, jsonify, render_template, request

import w2_mapping
from packet_extractor import extract_all_modules_from_packet

packet_bp = Blueprint("packet_analysis", __name__)
_cache = {}
_lock = threading.Lock()

# Drake Data Entry Menu tabs, in Drake's order. Only tabs that receive at least one form are shown.
MODULE_ORDER = ["General", "Income", "Adjustments", "Credits", "Taxes", "Health Care",
                "Other Forms", "Foreign", "Miscellaneous", "States"]

M, T, C, B, D, P = "money", "text", "code", "bool", "date", "percent"
FORM_REGISTRY = {
    "W-2": {"module": "Income", "screen": "W2", "button": "W2", "name": "Wages (W-2)", "transfer": "w2page",
            "fields": [("employer_name", "c", "Employer name", T), ("ein", "b", "Employer EIN", T),
                       ("employer_address", "c", "Employer address", T), ("control_number", "d", "Control number", T),
                       ("employee_name", "e", "Employee name", T), ("employee_ssn", "a", "Employee SSN", T),
                       ("employee_address", "f", "Employee address", T),
                       ("box1_wages", "1", "Wages, tips, other comp.", M), ("box2_fed_withheld", "2", "Federal tax withheld", M),
                       ("box3_ss_wages", "3", "Social security wages", M), ("box4_ss_tax", "4", "Social security tax withheld", M),
                       ("box5_medicare_wages", "5", "Medicare wages and tips", M), ("box6_medicare_tax", "6", "Medicare tax withheld", M),
                       ("box12a_code", "12a", "Code", C), ("box12a_amount", "12a", "Amount", M),
                       ("box12b_code", "12b", "Code", C), ("box12b_amount", "12b", "Amount", M),
                       ("box13_retirement_plan", "13", "Retirement plan", B)]},
    "SSA-1042S": {"module": "Income", "screen": "SSA", "button": "SSA", "name": "Social Security benefits", "transfer": "filler",
                  "fields": [("beneficiary_name", "1", "Name", T), ("beneficiary_ssn", "2", "Beneficiary's SSN", T),
                             ("box3_benefits_paid", "3", "Benefits paid", M), ("box4_benefits_repaid", "4", "Benefits repaid", M),
                             ("box5_net_benefits", "5", "Net benefits", M), ("box6_rate_of_tax", "6", "Rate of tax", P),
                             ("box7_tax_withheld", "7", "Tax withheld", M), ("box8_tax_refunded", "8", "Tax refunded", M),
                             ("box9_net_tax_withheld", "9", "Net tax withheld", M), ("claim_number", "11", "Claim number", T)]},
    "1099-R": {"module": "Income", "screen": "1099", "button": "1099", "name": "Retirement income (1099-R)", "transfer": "filler",
               "fields": [("payer", "", "Payer name", T), ("payer_tin", "", "Payer TIN", T), ("account_number", "", "Account number", T),
                          ("gross_distribution", "1", "Gross distribution", M), ("taxable_amount", "2a", "Taxable amount", M),
                          ("fed_tax_withheld", "4", "Federal income tax withheld", M),
                          ("employee_contributions", "5", "Employee contributions", M),
                          ("dist_code", "7", "Distribution code", C), ("is_ira", "7", "IRA/SEP/SIMPLE", B)]},
    "1099-INT": {"module": "Income", "screen": "INT", "button": "INT", "name": "Interest income (1099-INT)", "transfer": "filler",
                 "fields": [("payer", "", "Payer name", T), ("payer_tin", "", "Payer TIN", T), ("account_number", "", "Account number", T),
                            ("interest_income", "1", "Interest income", M), ("early_withdrawal_penalty", "2", "Early withdrawal penalty", M),
                            ("us_savings_bonds_interest", "3", "Interest on U.S. bonds & Treasury obligations", M),
                            ("fed_tax_withheld", "4", "Federal income tax withheld", M), ("investment_expenses", "5", "Investment expenses", M),
                            ("tax_exempt_interest", "8", "Tax-exempt interest", M)]},
    "1099-DIV": {"module": "Income", "screen": "DIV", "button": "DIV", "name": "Dividend income (1099-DIV)", "transfer": "filler",
                 "fields": [("payer", "", "Payer name", T), ("payer_tin", "", "Payer TIN", T), ("account_number", "", "Account number", T),
                            ("ordinary_dividends", "1a", "Total ordinary dividends", M), ("qualified_dividends", "1b", "Qualified dividends", M),
                            ("capital_gain_dist", "2a", "Total capital gain distributions", M),
                            ("fed_tax_withheld", "4", "Federal income tax withheld", M), ("section_199a_dividends", "5", "Section 199A dividends", M),
                            ("foreign_tax_paid", "7", "Foreign tax paid", M), ("foreign_country", "8", "Foreign country", T)]},
    "1099-MISC": {"module": "Income", "screen": "99M", "button": "99M", "name": "Miscellaneous income (1099-MISC)", "transfer": "filler",
                  "fields": [("payer", "", "Payer name", T), ("payer_tin", "", "Payer TIN", T), ("account_number", "", "Account number", T),
                             ("box2_royalties", "2", "Royalties", M), ("box3_other_income", "3", "Other income", M),
                             ("box4_fed_tax_withheld", "4", "Federal income tax withheld", M),
                             ("box8_substitute_payments", "8", "Substitute payments", M)]},
    "1099-OID": {"module": "Income", "screen": "OID", "button": "OID", "name": "Original issue discount (1099-OID)", "transfer": "filler",
                 "fields": [("payer", "", "Payer name", T), ("payer_tin", "", "Payer TIN", T), ("account_number", "", "Account number", T),
                            ("original_issue_discount", "1", "Original issue discount", M), ("early_withdrawal_penalty", "3", "Early withdrawal penalty", M),
                            ("market_discount", "5", "Market discount", M), ("acquisition_premium", "6", "Acquisition premium", M),
                            ("oid_treasury_obligations", "8", "OID on U.S. Treasury obligations", M),
                            ("investment_expenses", "9", "Investment expenses", M), ("tax_exempt_oid", "11", "Tax-exempt OID", M)]},
    "1099-B": {"module": "Income", "screen": "8949", "button": "8949", "name": "Capital gains (1099-B / 8949)", "transfer": "filler",
               "drake_screen_for_filler": "D",
               "fields": [("broker", "", "Broker", T), ("account_number", "", "Account number", T),
                          ("short_term_proceeds", "A", "Short-term proceeds", M), ("short_term_cost_basis", "A", "Short-term cost basis", M),
                          ("short_term_wash_sale", "A", "Short-term wash sale loss disallowed", M), ("short_term_net_gain", "A", "Short-term gain/loss", M),
                          ("long_term_proceeds", "D", "Long-term proceeds", M), ("long_term_cost_basis", "D", "Long-term cost basis", M),
                          ("long_term_wash_sale", "D", "Long-term wash sale loss disallowed", M), ("long_term_net_gain", "D", "Long-term gain/loss", M),
                          ("total_proceeds", "", "Total proceeds", M), ("total_cost_basis", "", "Total cost basis", M),
                          ("total_net_gain", "", "Total gain/loss", M)]},
    "1098": {"module": "Adjustments", "screen": "A", "button": "A", "name": "Itemized deductions — mortgage interest (1098)", "transfer": "filler",
             "fields": [("lender", "", "Lender", T), ("lender_tin", "", "Lender TIN", T), ("account_number", "", "Account number", T),
                        ("mortgage_interest", "1", "Mortgage interest received", M), ("outstanding_principal", "2", "Outstanding principal", M),
                        ("origination_date", "3", "Origination date", D), ("number_of_properties", "9", "Number of properties", T),
                        ("property_taxes_escrow", "10", "Property taxes paid from escrow", M)]},
    "5498": {"module": "Other Forms", "screen": "5498", "button": "5498", "name": "IRA contribution information (5498)", "transfer": "filler",
             "drake_screen_for_filler": "ROTH",
             "fields": [("trustee", "", "Trustee", T), ("trustee_tin", "", "Trustee TIN", T), ("account_number", "", "Account number", T),
                        ("account_type", "7", "Account type", T), ("ira_contributions", "1", "IRA contributions", M),
                        ("rollover_contributions", "2", "Rollover contributions", M), ("roth_conversion_amount", "3", "Roth IRA conversion amount", M),
                        ("recharacterized_contributions", "4", "Recharacterized contributions", M), ("fmv_of_account", "5", "Fair market value of account", M)]},
    # derived screens (built from several forms)
    "TAXPAYER": {"module": "General", "screen": "1", "button": "1", "name": "Name and address", "transfer": "none",
                 "fields": [("name", "", "Taxpayer name", T), ("ssn", "", "SSN", T), ("street", "", "Street", T),
                            ("city", "", "City", T), ("state", "", "State", T), ("zip", "", "ZIP", T)]},
    "FOREIGN": {"module": "Foreign", "screen": "1116", "button": "1116", "name": "Foreign tax credit (from brokerage statements)", "transfer": "none",
                "fields": [("payer", "", "Source", T), ("foreign_tax_1099", "7", "Foreign tax paid (1099-DIV box 7)", M),
                           ("foreign_tax_summary", "", "Foreign tax per country summary", M),
                           ("foreign_income_summary", "", "Foreign source income (summary)", M), ("countries", "", "Countries", T)]},
}

ACRO = {"MISC": "1099-MISC"}


# ---------------------------------------------------------------------------
def _money(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").replace("$", "").replace("%", ""))
    except ValueError:
        return None


def _fmt(v):
    n = _money(v)
    return f"{n:,.2f}" if n is not None else ""


def _page_texts(path):
    r = pypdf.PdfReader(path)
    return [(p.extract_text() or "") for p in r.pages]


LOT_RE = re.compile(r"^(\d\d/\d\d/\d{4})\s+([\d,]+\.\d+)\s+([\d,]+\.\d\d)\s*([GN])?\s+(\d\d/\d\d/\d{4}|Various)\s+([\d,]+\.\d\d)\s+"
                    r"([\d,]+\.\d\d)\s*([DW])?\s+(-?[\d,]+\.\d\d)(?:\s+(.*))?$")
SECTION_RE = re.compile(r"(SHORT|LONG) TERM TRANSACTIONS for (covered|noncovered) tax lots Form 8949, Part (I{1,2}) with Box ([A-F]) checked")
DESC_RE = re.compile(r"^[A-Za-z0-9].*\(([A-Z][A-Z.]{0,7})\)\s*$")
TOTALS_RE = re.compile(r"^Totals\s*:\s*([\d,]+\.\d\d)\s+([\d,]+\.\d\d)\s+([\d,]+\.\d\d)\s+(-?[\d,]+\.\d\d)")


def parse_lots(texts, first_page, last_page):
    """Form 8949 detail (one row per sale) from a brokerage composite statement."""
    lots, totals, section, desc = [], [], None, ""
    for pno in range(first_page, last_page + 1):
        for line in texts[pno - 1].splitlines():
            line = line.strip()
            m = SECTION_RE.search(line)
            if m:
                section = {"term": "Short" if m.group(1) == "SHORT" else "Long", "covered": m.group(2) == "covered",
                           "part": m.group(3), "box": m.group(4)}
                continue
            if not section:
                continue
            t = TOTALS_RE.match(line)
            if t:
                totals.append({**section, "page": pno, "proceeds": _money(t.group(1)), "cost": _money(t.group(2)),
                               "adjustment": _money(t.group(3)), "gain": _money(t.group(4))})
                continue
            m = LOT_RE.match(line)
            if m:
                notes = (m.group(10) or "").strip()
                adj = _money(m.group(7))
                code = m.group(8) or ("W" if "wash" in notes.lower() else ("D" if adj else ""))
                lots.append({"description": desc, "date_sold": m.group(1), "quantity": m.group(2), "proceeds": m.group(3).replace(",", ""),
                             "date_acquired": m.group(5), "cost": m.group(6).replace(",", ""), "adjustment": f"{adj:.2f}",
                             "adj_code": code if adj else "", "gain": m.group(9).replace(",", ""), "notes": notes,
                             "term": section["term"], "box": section["box"], "page": pno})
                continue
            d = DESC_RE.match(line)
            if d and not line.startswith(("Page", "Account")):
                desc = line
    return lots, totals


def _find_amount(texts, pages, pattern):
    for p in pages:
        m = re.search(pattern, texts[p - 1])
        if m:
            return _money(m.group(1)), p
    return None, None


def _composite_ranges(texts):
    """Brokerage composite statements: start at 'Page 1 of N' and run until the next one (or the end)."""
    starts = [i + 1 for i, t in enumerate(texts) if re.search(r"Page\s+1\s+of\s+\d+", t)]
    return [(s, (starts[k + 1] - 1) if k + 1 < len(starts) else len(texts)) for k, s in enumerate(starts)]


def _make_fields(ftype, data, page):
    out = []
    for key, box, label, kind in FORM_REGISTRY[ftype]["fields"]:
        v = data.get(key)
        if isinstance(v, bool):
            disp, find = ("Checked" if v else "Not checked"), ""
        elif kind == M:
            disp = _fmt(v)
            find = disp if disp and _money(v) not in (0, None) else ""     # zeros are everywhere on a page; don't point at one
        else:
            disp = "" if v is None else str(v)
            find = disp if len(disp) >= 3 else ""
        out.append({"key": key, "box": box, "label": label, "type": kind, "value": v if v is not None else "",
                    "display": disp, "find": find, "page": page})
    return out


# ---------------------------------------------------------------------------
def analyze_packet(path):
    st = os.stat(path)
    ck = (os.path.abspath(path), st.st_size, st.st_mtime_ns)
    with _lock:
        if ck in _cache:
            return _cache[ck]
    texts = _page_texts(path)
    res = extract_all_modules_from_packet(path)
    composites = _composite_ranges(texts)
    forms, checks, relations = [], [], []

    def comp_for(page):
        for a, b in composites:
            if a <= page <= b:
                return a, b
        return None

    counters = {}
    for m in res.get("modules", []):
        ftype = m.get("type")
        if ftype not in FORM_REGISTRY:
            continue
        data = dict(m)
        page = int(m.get("page") or 1)
        rng = comp_for(page)
        pages = list(range(rng[0], rng[1] + 1)) if rng and ftype in ("1099-B", "1099-DIV", "1099-INT", "1099-MISC", "1099-OID") else [page]
        extra = {}

        if ftype == "1099-R":
            # read the IRA/SEP/SIMPLE tick mark directly (the older extractor misses it on some pages)
            ira = bool(re.search(r"IRA/\s*SEP/\s*SIMPLE\s*\n\s*[✓✔Xx]\s*\n", texts[page - 1]))
            if ira != bool(data.get("is_ira")):
                checks.append({"level": "info", "form": None, "text": f"1099-R p.{page}: IRA/SEP/SIMPLE box read as {'checked' if ira else 'not checked'} "
                               f"from the page (the older extractor said {'checked' if data.get('is_ira') else 'not checked'})."})
            data["is_ira"] = ira
        if ftype == "1099-INT" and rng:
            # the summary line is authoritative for box 5 (fees on the statement are not investment expenses)
            v, _ = _find_amount(texts, [page], r"5-\s*Investment expenses\s+([\d,]+\.\d\d)")
            if v is not None:
                if _money(data.get("investment_expenses")) != v:
                    checks.append({"level": "info", "form": None, "text": f"{data.get('payer')} 1099-INT box 5 corrected to {v:,.2f} "
                                   f"(the older extractor read {data.get('investment_expenses')} from the fees section)."})
                data["investment_expenses"] = f"{v:.2f}"
            tot, tp = _find_amount(texts, pages, r"([\d,]+\.\d\d)\s+Total Interest Income")
            if tot is not None:
                extra["detail_total"] = {"label": "Interest detail pages total", "value": tot, "page": tp}
        if ftype == "1099-DIV" and rng:
            od, op = _find_amount(texts, pages, r"([\d,]+\.\d\d)\s+Ordinary Dividends")
            qd, qp = _find_amount(texts, pages, r"([\d,]+\.\d\d)\s+Qualified Dividends")
            if od is not None:
                extra["detail_total"] = {"label": "Dividend detail pages total", "value": od, "page": op, "qualified": qd}
        if ftype == "1099-B" and rng:
            lots, totals = parse_lots(texts, rng[0], rng[1])
            extra["lots"] = lots
            extra["section_totals"] = totals

        counters[ftype] = counters.get(ftype, 0) + 1
        reg = FORM_REGISTRY[ftype]
        fid = f"{ftype}-{page}-{counters[ftype]}".replace(" ", "")
        payer = data.get("payer") or data.get("broker") or data.get("employer_name") or data.get("lender") or data.get("trustee") or ""
        forms.append({"id": fid, "type": ftype, "module": reg["module"], "screen": reg["screen"], "button": reg["button"],
                      "screen_name": reg["name"], "transfer": reg["transfer"], "payer": payer, "page": page, "pages": pages,
                      "zero_value": bool(data.get("is_zero_value")), "account": data.get("account_number", ""),
                      "fields": _make_fields(ftype, data, page), "raw": {k: v for k, v in data.items() if not isinstance(v, (list, dict))},
                      **extra})

    _derive_screens(forms, texts, composites)
    _reconcile(forms, checks)
    _relate(forms, relations, checks)

    # Drake screen record numbers (1 of N) in packet order
    seen = {}
    for f in forms:
        seen[f["screen"]] = seen.get(f["screen"], 0) + 1
        f["record"] = seen[f["screen"]]
    for f in forms:
        f["records"] = seen[f["screen"]]

    modules = []
    for name in MODULE_ORDER:
        fs = [f for f in forms if f["module"] == name]
        if not fs:
            continue
        screens = []
        for f in fs:
            s = next((x for x in screens if x["screen"] == f["screen"]), None)
            if not s:
                s = {"screen": f["screen"], "button": f["button"], "name": f["screen_name"], "forms": []}
                screens.append(s)
            s["forms"].append(f["id"])
        modules.append({"name": name, "screens": screens, "count": len(fs)})

    page_map = {}
    for f in forms:
        for p in f["pages"]:
            page_map.setdefault(p, []).append(f["id"])
    result = {"file": os.path.basename(path), "total_pages": len(texts), "forms": forms, "modules": modules,
              "absent_modules": [m for m in MODULE_ORDER if m not in [x["name"] for x in modules]],
              "checks": checks, "relationships": relations, "page_map": page_map,
              "composites": [{"first": a, "last": b} for a, b in composites]}
    with _lock:
        _cache.clear()
        _cache[ck] = result
    return result


def _derive_screens(forms, texts, composites):
    # General · Screen 1 — taxpayer identity, taken from the W-2 (falls back to any form that names the recipient)
    src = next((f for f in forms if f["type"] == "W-2"), None) or next((f for f in forms if f["raw"].get("recipient_name")), None)
    if src:
        r = src["raw"]
        name = r.get("employee_name") or r.get("recipient_name") or ""
        ssn = r.get("employee_ssn") or r.get("ssn") or r.get("beneficiary_ssn") or ""
        addr = r.get("employee_address") or r.get("recipient_address") or ""
        m = re.match(r"^(.*?),\s*([^,]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$", addr)
        street, city, state, zp = (m.groups() if m else (addr, "", "", ""))
        data = {"name": name, "ssn": ssn, "street": street, "city": city, "state": state, "zip": zp}
        forms.insert(0, {"id": "TAXPAYER-1", "type": "TAXPAYER", "module": "General", "screen": "1", "button": "1",
                         "screen_name": FORM_REGISTRY["TAXPAYER"]["name"], "transfer": "none", "payer": name, "page": src["page"],
                         "pages": [src["page"]], "zero_value": False, "account": "", "derived_from": [src["id"]],
                         "fields": _make_fields("TAXPAYER", data, src["page"]), "raw": data})
    # Foreign · 1116 — one record per brokerage statement that reports foreign tax
    for f in [x for x in forms if x["type"] == "1099-DIV" and (_money(x["raw"].get("foreign_tax_paid")) or 0) > 0]:
        pages = f["pages"]
        tax_sum, tp = _find_amount(texts, pages, r"Foreign Tax\s+([\d,]+\.\d\d)")
        countries = sorted(set(re.findall(r"^Total ([A-Z][A-Z ]+?)\s+[\d,]+\.\d\d", "\n".join(texts[p - 1] for p in pages), re.M)))
        inc, _ = _find_amount(texts, pages, r"Total Foreign Source Income\*?\s+([\d,]+\.\d\d)")
        data = {"payer": f["payer"], "foreign_tax_1099": f["raw"].get("foreign_tax_paid"),
                "foreign_tax_summary": f"{tax_sum:.2f}" if tax_sum is not None else "",
                "foreign_income_summary": f"{inc:.2f}" if inc else "", "countries": ", ".join(c.title() for c in countries)}
        forms.append({"id": f"FOREIGN-{f['page']}", "type": "FOREIGN", "module": "Foreign", "screen": "1116", "button": "1116",
                      "screen_name": FORM_REGISTRY["FOREIGN"]["name"], "transfer": "none", "payer": f["payer"], "page": tp or f["page"],
                      "pages": sorted(set([f["page"]] + ([tp] if tp else []))), "zero_value": False, "account": f["account"],
                      "derived_from": [f["id"]], "fields": _make_fields("FOREIGN", data, tp or f["page"]), "raw": data})


def _reconcile(forms, checks):
    for f in forms:
        r = f["raw"]
        if f["type"] == "1099-B" and f.get("lots") is not None:
            lots = f["lots"]
            for term, key in (("Short", "short_term"), ("Long", "long_term")):
                ls = [l for l in lots if l["term"] == term]
                p = sum(float(l["proceeds"]) for l in ls); c = sum(float(l["cost"]) for l in ls)
                exp_p, exp_c = _money(r.get(f"{key}_proceeds")) or 0, _money(r.get(f"{key}_cost_basis")) or 0
                ok = abs(p - exp_p) < 0.05 and abs(c - exp_c) < 0.05
                checks.append({"level": "ok" if ok else "warn", "form": f["id"],
                               "text": f"{f['payer']} {term.lower()}-term: {len(ls)} sale lots total proceeds {p:,.2f} / cost {c:,.2f} "
                                       f"{'match' if ok else 'do NOT match'} the summary ({exp_p:,.2f} / {exp_c:,.2f})."})
            ws = [l for l in lots if l["adj_code"] == "W"]
            if ws:
                checks.append({"level": "info", "form": f["id"], "text": f"{f['payer']}: {len(ws)} lot(s) with wash-sale loss disallowed "
                               f"(total {sum(float(l['adjustment']) for l in ws):,.2f}) — Form 8949 adjustment code W."})
        dt = f.get("detail_total")
        if dt:
            box = "ordinary_dividends" if f["type"] == "1099-DIV" else "interest_income"
            exp = _money(r.get(box)) or 0
            ok = abs(exp - dt["value"]) < 0.05
            checks.append({"level": "ok" if ok else "warn", "form": f["id"],
                           "text": f"{f['payer']} {f['type']}: {dt['label'].lower()} {dt['value']:,.2f} {'matches' if ok else 'does NOT match'} "
                                   f"the form ({exp:,.2f}) — page {dt['page']}."})
        if f["type"] == "FOREIGN":
            a, b = _money(r.get("foreign_tax_1099")), _money(r.get("foreign_tax_summary"))
            if a is not None and b is not None and abs(a - b) >= 0.05:
                checks.append({"level": "warn", "form": f["id"], "text": f"{f['payer']}: foreign tax on the 1099-DIV ({a:,.2f}) differs from the "
                               f"per-country summary ({b:,.2f}). Check which amount belongs on Form 1116."})


def _relate(forms, relations, checks):
    by_acct = {}
    for f in forms:
        a = (f.get("account") or "").strip()
        if a and a != "****":
            by_acct.setdefault(a, []).append(f)
    for acct, fs in by_acct.items():
        if len(fs) > 1:
            relations.append({"kind": "same account", "forms": [x["id"] for x in fs],
                              "text": f"Account {acct}: " + ", ".join(f"{x['type']} (p.{x['page']})" for x in fs)})
    # IRA distribution matching a Roth conversion
    for r in [f for f in forms if f["type"] == "1099-R" and f["raw"].get("is_ira")]:
        amt = _money(r["raw"].get("gross_distribution"))
        for c in [f for f in forms if f["type"] == "5498" and _money(f["raw"].get("roth_conversion_amount"))]:
            if amt and abs(amt - _money(c["raw"]["roth_conversion_amount"])) < 0.05:
                relations.append({"kind": "Roth conversion", "forms": [r["id"], c["id"]],
                                  "text": f"1099-R p.{r['page']} IRA distribution {amt:,.2f} (code {r['raw'].get('dist_code')}) equals the Roth conversion "
                                          f"on 5498 p.{c['page']} — report on Form 8606 Part II."})
    for f in [x for x in forms if x["type"] == "1099-R" and not x["raw"].get("is_ira")]:
        if any(g["type"] == "5498" and g.get("account") == f.get("account") for g in forms):
            checks.append({"level": "warn", "form": f["id"], "text": f"1099-R p.{f['page']} is from IRA account {f['account']} (a 5498 exists for it) but the "
                           f"IRA/SEP/SIMPLE box was not read as checked — verify."})
    for f in [x for x in forms if x["type"] == "1098" and _money(x["raw"].get("property_taxes_escrow"))]:
        relations.append({"kind": "Schedule A", "forms": [f["id"]],
                          "text": f"1098 p.{f['page']}: mortgage interest {_fmt(f['raw'].get('mortgage_interest'))} and property taxes paid from escrow "
                                  f"{_fmt(f['raw'].get('property_taxes_escrow'))} both go to Schedule A."})
    comp = {}
    for f in forms:
        if len(f["pages"]) > 1 and f["type"].startswith("1099"):
            comp.setdefault((f["pages"][0], f["pages"][-1]), []).append(f)
    for (a, b), fs in comp.items():
        relations.append({"kind": "composite statement", "forms": [x["id"] for x in fs],
                          "text": f"{fs[0]['payer']} composite statement, pages {a}–{b}: " + ", ".join(sorted(set(x['type'] for x in fs)))})
    for f in [x for x in forms if x["type"] == "SSA-1042S"]:
        checks.append({"level": "warn", "form": f["id"], "text": "Page %d is an SSA-1042S, which Social Security issues to nonresident aliens. The other forms "
                       "describe a U.S. resident filer, who normally receives an SSA-1099 — confirm the form type before entering it on Drake's SSA screen." % f["page"]})
    tins = {re.sub(r"\D", "", str(f["raw"].get(k, "")))[-4:] for f in forms for k in ("employee_ssn", "recipient_tin", "beneficiary_ssn",
            "borrower_tin", "participant_tin") if f["raw"].get(k)}
    tins.discard("")
    checks.append({"level": "ok" if len(tins) <= 1 else "warn", "form": None,
                   "text": "All forms are for the same taxpayer (TIN ending %s)." % next(iter(tins)) if len(tins) == 1
                   else f"Forms show different recipient TINs: {', '.join(sorted(tins))}."})


# ---------------------------------------------------------------------------
@packet_bp.route("/drake-modules")
def page():
    # The module screens now live in the guided review workflow (all forms + fields shown automatically).
    from flask import redirect
    return redirect("/review")


@packet_bp.route("/drake-modules/classic")
def page_classic():
    return render_template("drake_modules.html")


@packet_bp.route("/api/packet/analysis")
def api_analysis():
    path = w2_mapping.current_pdf_path()
    if not path:
        return jsonify({"success": False, "error": "Tax packet PDF not found. Upload one first."}), 404
    try:
        return jsonify({"success": True, "registry": {k: {"module": v["module"], "screen": v["screen"], "name": v["name"],
                                                           "fields": [{"key": a, "box": b, "label": c, "type": d} for a, b, c, d in v["fields"]]}
                                                       for k, v in FORM_REGISTRY.items()},
                        **analyze_packet(path)})
    except Exception as exc:
        return jsonify({"success": False, "error": f"Could not analyze the PDF: {exc}"}), 500


@packet_bp.route("/api/packet/transfer", methods=["POST"])
def api_transfer():
    """Enter ONLY the confirmed values of one form on its Drake screen (existing drake_packet_filler automation)."""
    payload = request.get_json(silent=True) or {}
    path = w2_mapping.current_pdf_path()
    analysis = analyze_packet(path)
    form = next((f for f in analysis["forms"] if f["id"] == payload.get("form_id")), None)
    if not form:
        return jsonify({"success": False, "error": "Unknown form."}), 400
    if form["transfer"] == "w2page":
        return jsonify({"success": False, "error": "Use the exact Drake W-2 screen (Open W-2 screen) to send W-2 values."}), 400
    if form["transfer"] != "filler":
        return jsonify({"success": False, "error": "This screen is for review only — Drake fills it from the other forms."}), 400
    values = payload.get("values") or {}
    keys = {f["key"] for f in form["fields"]}
    confirmed = {k: v for k, v in values.items() if k in keys}
    if not confirmed:
        return jsonify({"success": False, "error": "Nothing confirmed for this form."}), 400
    reg = FORM_REGISTRY[form["type"]]
    item = {"type": form["type"], "screen": reg.get("drake_screen_for_filler", reg["screen"]), "page": form["page"],
            "title": f"{form['type']} — {form['payer']}", "instance_index": form["record"], **confirmed}
    if form["type"] == "SSA-1042S":           # the filler reads these names
        item["net_benefits"] = confirmed.get("box5_net_benefits")
        item["tax_withheld"] = confirmed.get("box7_tax_withheld")
    if form["type"] == "1099-MISC":
        item["royalties"] = confirmed.get("box2_royalties"); item["other_income"] = confirmed.get("box3_other_income")
    try:
        import drake_packet_filler as filler
    except Exception as exc:
        return jsonify({"success": False, "error": f"Drake automation is only available on the Windows PC running Drake ({exc})."}), 503
    with w2_mapping._drake_lock:
        ok, logs, status = filler.populate_single_packet_module(item)
    return jsonify({"success": bool(ok), "status": status, "logs": logs, "sent": sorted(confirmed),
                    "message": f"Entered {len(confirmed)} confirmed value(s) on Drake screen {item['screen']} (record {form['record']}). "
                               "Review it in Drake and save." if ok else "Drake did not accept the entry — see the log."})


@packet_bp.route("/api/packet/8949-import", methods=["POST"])
def api_8949_import():
    """Write a Drake Form 8949 batch-import file from the sale lots the user confirmed (edits applied)."""
    payload = request.get_json(silent=True) or {}
    analysis = analyze_packet(w2_mapping.current_pdf_path())
    lots_in = payload.get("lots") or []          # [{form_id, description, quantity, date_acquired, date_sold, proceeds, cost, adj_code, adjustment}]
    if not lots_in:
        return jsonify({"success": False, "error": "No confirmed sale lots to import."}), 400
    known = {f["id"] for f in analysis["forms"] if f["type"] == "1099-B"}
    tp = next((f for f in analysis["forms"] if f["type"] == "TAXPAYER"), None)
    ssn = re.sub(r"\D", "", str((tp or {}).get("raw", {}).get("ssn", "")))
    if len(ssn) != 9:
        return jsonify({"success": False, "error": "Taxpayer SSN not found — needed to name the Drake import file."}), 400
    from drake_import_generator import Drake8949ImportGenerator, DRAKE_IMPORT_DIR
    target = DRAKE_IMPORT_DIR if os.name == "nt" else os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")
    gen = Drake8949ImportGenerator(ssn_or_client_id=ssn, import_mode=payload.get("mode", "Append"), target_dir=target)
    bad = 0
    for l in lots_in:
        if l.get("form_id") not in known:
            bad += 1
            continue
        try:
            adj = _money(l.get("adjustment"))
            gen.add_transaction(description=f"{l.get('quantity', '')} {l.get('description', '')}".strip()[:60],
                                date_acquired=l.get("date_acquired"), date_sold=l.get("date_sold"),
                                sales_price=_money(l.get("proceeds")) or 0.0, cost_basis=_money(l.get("cost")) or 0.0,
                                adjustment_code=(l.get("adj_code") or "") if adj else "", adjustment_amount=adj if adj else None)
        except Exception:
            bad += 1
    if not gen.transactions:
        return jsonify({"success": False, "error": "None of the lots could be converted."}), 400
    path = gen.write_import_file()
    return jsonify({"success": True, "path": path, "count": len(gen.transactions), "skipped": bad,
                    "preview": gen.generate_content().splitlines()[:12],
                    "message": f"Wrote {len(gen.transactions)} confirmed sale lot(s) to {path}. In Drake open the return, go to Screen 8949 and import (Alt+I)."})
