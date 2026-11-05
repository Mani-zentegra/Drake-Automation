"""
Validation of reviewed values: formats Drake accepts + consistency checks within each form.

validate(doc_type, fields, values, year) -> {field_key: {"level": "error"|"missing"|"warn", "msg": str}}
"""
import re
from datetime import datetime

from .pdftext import US_STATES

SS_WAGE_BASE = {"2022": 147000, "2023": 160200, "2024": 168600, "2025": 176100, "2026": 184500}
W2_CODES = set("A B C D E F G H J K L M N P Q R S T V W Y Z AA BB DD EE FF GG HH II".split())
RETIREMENT_CODES = {"D", "E", "F", "G", "H", "S", "AA", "BB", "EE"}


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def blank(v):
    return v is None or v == "" or v is False


def format_error(ftype, v, pattern=None):
    if isinstance(v, bool) or blank(v):
        return ""
    s = str(v).strip()
    if ftype == "money":
        return "" if re.fullmatch(r"-?\d+(\.\d{1,2})?", s) else "Enter an amount like 1234.56"
    if ftype in ("ssn", "ein", "tin"):
        if re.fullmatch(r"\d{9}", s):
            return ""
        if re.search(r"[*X]", s, re.I):
            return "Masked on the PDF — enter the full 9-digit number"
        return f"{'SSN' if ftype == 'ssn' else 'EIN' if ftype == 'ein' else 'TIN'} must be 9 digits"
    if ftype == "zip":
        return "" if re.fullmatch(r"\d{5}(-?\d{4})?", s) else "ZIP must be 5 or 9 digits"
    if ftype == "state":
        return "" if s.upper() in US_STATES else "Use a 2-letter state code"
    if ftype == "date":
        try:
            datetime.strptime(s, "%m/%d/%Y")
            return ""
        except ValueError:
            return "Use MM/DD/YYYY"
    if ftype == "year":
        return "" if re.fullmatch(r"(19|20)\d\d", s) else "Enter a 4-digit year"
    if ftype == "int":
        return "" if re.fullmatch(r"\d+", s) else "Enter a whole number"
    if ftype == "ts":
        return "" if s in ("T", "S", "J") else "Use T (taxpayer), S (spouse) or J (joint)"
    if ftype == "percent":
        return "" if re.fullmatch(r"-?\d+(\.\d+)?%?", s) else "Enter a percentage like 10%"
    if ftype == "code" and pattern and not re.match(pattern, s):
        return "Not a valid code for this box"
    return ""


def validate(doc_type, fields, values, year=""):
    iss = {}
    by = {f["key"]: f for f in fields}
    for f in fields:
        v = values.get(f["key"])
        e = format_error(f["type"], v, f.get("pattern"))
        if e.startswith("Masked") and not (f.get("required") or f.get("aid")):
            e = ""            # a masked recipient TIN is normal on 1099s and is not sent to Drake
        if e:
            iss[f["key"]] = {"level": "error", "msg": e}
        elif f.get("required") and blank(v) and f["type"] != "bool":
            iss[f["key"]] = {"level": "missing", "msg": "Required by Drake — not found on the PDF"}

    def warn(k, msg):
        if k in by and k not in iss:
            iss[k] = {"level": "warn", "msg": msg}

    n = lambda k: num(values.get(k)) if not blank(values.get(k)) else None

    if doc_type == "W-2":
        b1, b2, b3, b4, b5, b6 = (n("box%d" % i) for i in range(1, 7))
        if b1 is not None and b2 is not None and b2 > b1:
            warn("box2", "Federal tax withheld is more than wages (box 1)")
        base = SS_WAGE_BASE.get(str(year))
        if base and b3 is not None and b3 > base + 0.005:
            warn("box3", f"Above the {year} social security wage base (${base:,})")
        if b3 is not None and b4 is not None and abs(b3 * 0.062 - b4) > 1:
            warn("box4", f"Expected about {b3 * 0.062:,.2f} (6.2% of box 3)")
        if b5 is not None and b3 is not None and b5 + 0.005 < b3:
            warn("box5", "Medicare wages are normally at least social security wages (box 3)")
        if b5 is not None and b6 is not None:
            lo = b5 * 0.0145
            hi = lo + max(0.0, b5 - 200000) * 0.009
            if b6 < lo - 1 or b6 > hi + 1:
                warn("box6", f"Expected about {lo:,.2f}" + (f"–{hi:,.2f}" if hi > lo else "") + " (1.45% of box 5"
                     + (", + 0.9% over $200,000)" if hi > lo else ")"))
        codes = set()
        for r in "abcd":
            c, a = values.get(f"box12{r}_code"), values.get(f"box12{r}_amount")
            if not blank(c):
                codes.add(str(c).upper())
            if not blank(c) and blank(a):
                warn(f"box12{r}_amount", "Code entered without an amount")
            if blank(c) and not blank(a) and num(a):
                warn(f"box12{r}_code", "Amount entered without a code")
        if codes & RETIREMENT_CODES and values.get("box13_retirement") is not True:
            warn("box13_retirement", f"Box 12 code {', '.join(sorted(codes & RETIREMENT_CODES))} is a retirement deferral, but box 13 "
                                     "'Retirement plan' is not ticked on the PDF — confirm with the client/employer")
        if blank(values.get("state1")) and (n("state1_wages") or n("state1_tax")):
            warn("state1", "State wages or tax entered without a state")
    elif doc_type == "1099-DIV":
        a, b = n("box1a"), n("box1b")
        if a is not None and b is not None and b > a + 0.005:
            warn("box1b", "Qualified dividends are more than total ordinary dividends (1a)")
        if a is not None and n("box5") and n("box5") > a + 0.005:
            warn("box5", "Section 199A dividends are more than total ordinary dividends (1a)")
        if n("box2a") is not None:
            for k in ("box2b", "box2c", "box2d", "box2f"):
                if n(k) and n(k) > n("box2a") + 0.005:
                    warn(k, "More than total capital gain distributions (2a)")
    elif doc_type == "1099-R":
        g, t = n("box1"), n("box2a")
        if g is not None and t is not None and t > g + 0.005:
            warn("box2a", "Taxable amount is more than the gross distribution (box 1)")
        if g is not None and n("box4") and n("box4") > g:
            warn("box4", "Withholding is more than the gross distribution")
    elif doc_type == "1099-INT":
        b1, b3 = n("box1"), n("box3")
        if b1 and b3 and abs(b1 - b3) < 0.005:
            warn("box1", "Box 1 equals box 3 — box 1 should exclude U.S. bond/Treasury interest. Possible double count.")
    elif doc_type == "SSA-1099":
        b3, b4, b5 = n("box3"), n("box4"), n("box5")
        if b3 is not None and b5 is not None and abs((b3 - (b4 or 0)) - b5) > 0.005:
            warn("box5", f"Net benefits should be box 3 minus box 4 ({(b3 - (b4 or 0)):,.2f})")
    elif doc_type == "TAXPAYER":
        if not blank(values.get("sp_ssn")) and values.get("sp_ssn") == values.get("tp_ssn"):
            warn("sp_ssn", "Spouse SSN is the same as the taxpayer SSN")
    return iss
