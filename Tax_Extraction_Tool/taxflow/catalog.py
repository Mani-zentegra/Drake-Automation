"""
Catalog of supported tax documents.

Each form type declares:
  detect     regexes that identify the form on a page ("all" must match, "any" adds score, "not" vetoes)
  composite  regex of the section header used inside brokerage composite statements (optional)
  module     Drake Data Entry tab (General, Income, Adjustments, Credits, Taxes, Health Care, ...)
  screen     Drake screen code typed into Drake's "Enter screen" box; screen_name = Drake screen title
  fields     ordered list of fields (see F()).  The same key is used for the PDF value and the Drake field.

Field extraction is driven only by label text + value type, never by fixed coordinates, so the
same definition reads the IRS layout, substitute statements and brokerage composites.

Field modes
  value    value on the same line right of the label, else directly below the label (same column)
  below    only directly below the label
  same     only on the same line
  block    multi-line name/address block below the label (split into name/street/city/state/zip)
  part     derived from a block field (part = name|street|city|state|zip|line2)
  check    a check box — true when a check mark is printed next to the label
  choice   one of several check boxes (options) — value is the ticked option
  table    cell of a table: row regex x column-header regex
  manual   not on the PDF (entered by the reviewer, e.g. Drake's TS code)

Drake automation ids (aid) are the ids that the existing automation already uses. Fields without an
aid can be linked from the review screen ("Link Drake fields"); until then the transfer reports them
as "not linked" instead of skipping them silently.
"""
import copy
import re

MODULES = ["General", "Income", "Adjustments", "Credits", "Taxes", "Health Care", "Other Forms",
           "Foreign", "Miscellaneous", "States"]


def F(key, label, ftype="money", box="", aliases=None, mode="value", section="", required=False,
      aid=None, control=None, block=None, part=None, options=None, row=None, col=None, opts=None, hint="", width=None,
      pattern=None):
    return {"key": key, "label": label, "type": ftype, "box": box, "aliases": aliases or [], "mode": mode,
            "section": section, "required": required, "aid": aid, "pattern": pattern,
            "control": control or ("combo" if ftype in ("state", "code", "ts") and aid and aid.startswith("Dropdown") else
                                   "checkbox" if ftype == "bool" else "edit"),
            "block": block, "part": part, "options": options, "row": row, "col": col, "opts": opts, "hint": hint,
            "width": width}


def B(n):
    """regex for a box number at the start of a label: '1 ', '1-', '1a ', 'Box 1.'"""
    return rf"(?:\bBox\s*)?\b{n}[-.]?\s+"


def party(prefix, label_res, section, title, aids=None, name_label=None, with_name=True):
    """Name/address block of a payer, employer, lender, trustee ... -> name, street, city, state, zip."""
    aids = aids or {}
    names = [
        F(f"{prefix}_name", name_label or f"{title} name", "text", "", [], mode="part", block=f"{prefix}_block", part="name",
          section=section, required=True, aid=aids.get("name")),
        F(f"{prefix}_name2", f"{title} name cont.", "text", "", [], mode="part", block=f"{prefix}_block", part="name2", section=section,
          aid=aids.get("name2")),
    ] if with_name else []
    return [
        F(f"{prefix}_block", f"{title} name and address (block)", "text", "", label_res, mode="block", section=section),
        *names,
        F(f"{prefix}_street", f"{title} street", "text", "", [], mode="part", block=f"{prefix}_block", part="street", section=section,
          aid=aids.get("street")),
        F(f"{prefix}_city", f"{title} city", "text", "", [], mode="part", block=f"{prefix}_block", part="city", section=section,
          aid=aids.get("city")),
        F(f"{prefix}_state", f"{title} state", "state", "", [], mode="part", block=f"{prefix}_block", part="state", section=section,
          aid=aids.get("state"), control="combo" if aids.get("state", "").startswith("Dropdown") else "edit"),
        F(f"{prefix}_zip", f"{title} ZIP", "zip", "", [], mode="part", block=f"{prefix}_block", part="zip", section=section,
          aid=aids.get("zip")),
    ]


TS = lambda aid="Dropdown_1": F("ts", "TS (T = taxpayer, S = spouse)", "ts", "", [], mode="manual", section="Ownership",
                                required=True, aid=aid, control="combo",
                                hint="Set automatically from the recipient SSN (taxpayer or spouse).")

W2_CODE = r"^(?:[A-HJ-NP-Z]|AA|BB|DD|EE|FF|GG|HH|II)$"
R_CODE = r"^[1-9A-HJ-NP-W](?:[1-9A-HJ-NP-W])?$"

PAYER_RES = [r"PAYER'?S name, street address", r"PAYER'?S name", r"FILER'?S name, street address", r"Payer'?s name"]
RECIP_NAME = [r"RECIPIENT'?S name", r"Recipient'?s name"]
PAYER_TIN = [r"PAYER'?S (?:TIN|federal identification number|federal ID number)", r"FILER'?S (?:TIN|federal identification number)"]
RECIP_TIN = [r"RECIPIENT'?S (?:TIN|identification number)", r"Recipient'?s TIN"]
ACCOUNT = [r"Account number \(see instructions\)", r"Account number", r"\bAccount\b"]


def recipient(section="Recipient", tin_type="tin"):
    return [F("recipient_tin", "Recipient's TIN", tin_type, "", RECIP_TIN, section=section),
            F("recipient_name", "Recipient's name", "name", "", RECIP_NAME, mode="below", section=section),
            F("recipient_street", "Recipient's street address", "text", "", [r"^Street address \(including apt"], mode="below", section=section),
            F("recipient_cityline", "Recipient's city, state, ZIP", "text", "", [r"^City or town, state or province"], mode="below", section=section)]


FORMS = {
    # ------------------------------------------------------------------ INCOME
    "W-2": {
        "name": "Form W-2 — Wage and Tax Statement", "module": "Income", "screen": "W2", "screen_name": "Wages (W-2)",
        "detect": {"all": [r"\bW-2\b"], "any": [r"Wage and Tax Statement", r"Employer identification number", r"Wages,? tips"],
                   "not": [r"\bW-2G\b", r"Certain Gambling"]},
        "payer_key": "employer_name", "payer_tin_key": "employer_ein", "recipient_tin_key": "employee_ssn",
        "key_amount": "box1", "drake_verified": True,
        "fields": [
            TS(),
            F("employee_ssn", "Employee's SSN", "ssn", "a", [r"Employee'?s social security number", r"Employee'?s SSN"], section="Employee", required=True),
            F("employer_ein", "Employer EIN", "ein", "b", [r"Employer identification number", r"Employer'?s (?:FED )?ID number", r"Employer EIN"],
              section="Employer", required=True, aid="Textbox_4"),
            *party("employer", [r"Employer'?s name, address,? and ZIP", r"Employer'?s name"], "Employer", "Employer",
                   {"name": "Textbox_5", "street": "Textbox_7", "city": "Textbox_8", "state": "Dropdown_9", "zip": "Textbox_10"}),
            F("control_number", "Control number", "text", "d", [r"\bd\s+Control number", r"Control number"], mode="below", section="Employer"),
            F("employee_name", "Employee's name", "name", "e", [r"Employee'?s first name and initial", r"Employee'?s name"], mode="below", section="Employee"),
            *party("employee", [r"Employee'?s address,? and ZIP code"], "Employee", "Employee", with_name=False),
            F("box1", "Wages, tips, other compensation", "money", "1", [B(1) + r"Wages,? tips"], section="Federal", required=True, aid="Textbox_23"),
            F("box2", "Federal income tax withheld", "money", "2", [B(2) + r"Federal income tax withheld"], section="Federal", aid="Textbox_24"),
            F("box3", "Social security wages", "money", "3", [B(3) + r"Social security wages"], section="Federal", aid="Textbox_25"),
            F("box4", "Social security tax withheld", "money", "4", [B(4) + r"Social security tax withheld"], section="Federal", aid="Textbox_26"),
            F("box5", "Medicare wages and tips", "money", "5", [B(5) + r"Medicare wages"], section="Federal", aid="Textbox_27"),
            F("box6", "Medicare tax withheld", "money", "6", [B(6) + r"Medicare tax withheld"], section="Federal", aid="Textbox_28"),
            F("box7", "Social security tips", "money", "7", [B(7) + r"Social security tips"], section="Federal"),
            F("box8", "Allocated tips", "money", "8", [B(8) + r"Allocated tips"], section="Federal"),
            F("box10", "Dependent care benefits", "money", "10", [B(10) + r"Dependent care benefits"], section="Federal"),
            F("box11", "Nonqualified plans", "money", "11", [B(11) + r"Nonqualified plans?"], section="Federal"),
            F("box12a_code", "Box 12a code", "code", "12a", [r"\b12a\b"], section="Box 12", aid="Dropdown_34", control="combo", pattern=W2_CODE),
            F("box12a_amount", "Box 12a amount", "money", "12a", [r"\b12a\b"], section="Box 12", aid="Textbox_35"),
            F("box12b_code", "Box 12b code", "code", "12b", [r"\b12b\b"], section="Box 12", aid="Dropdown_37", control="combo", pattern=W2_CODE),
            F("box12b_amount", "Box 12b amount", "money", "12b", [r"\b12b\b"], section="Box 12", aid="Textbox_38"),
            F("box12c_code", "Box 12c code", "code", "12c", [r"\b12c\b"], section="Box 12", control="combo", pattern=W2_CODE),
            F("box12c_amount", "Box 12c amount", "money", "12c", [r"\b12c\b"], section="Box 12"),
            F("box12d_code", "Box 12d code", "code", "12d", [r"\b12d\b"], section="Box 12", control="combo", pattern=W2_CODE),
            F("box12d_amount", "Box 12d amount", "money", "12d", [r"\b12d\b"], section="Box 12"),
            F("box13_statutory", "Statutory employee", "bool", "13", [r"Statutory\s+employee"], mode="check", section="Box 13"),
            F("box13_retirement", "Retirement plan", "bool", "13", [r"Retirement\s+plan"], mode="check", section="Box 13", aid="CheckboxTextRight_47"),
            F("box13_sick", "Third-party sick pay", "bool", "13", [r"Third-party\s+sick\s+pay"], mode="check", section="Box 13"),
            F("box14", "Box 14 other", "text", "14", [B(14) + r"Other"], mode="below", section="Box 14"),
            F("state1", "Box 15 state", "state", "15", [B(15) + r"State\b"], mode="below", section="State", aid="Dropdown_57", control="combo"),
            F("state1_id", "Employer's state ID number", "text", "15", [r"Employer'?s state ID number"], mode="below", section="State"),
            F("state1_wages", "State wages, tips, etc.", "money", "16", [B(16) + r"State wages"], section="State", aid="Textbox_59"),
            F("state1_tax", "State income tax", "money", "17", [B(17) + r"State income tax"], section="State", aid="Textbox_60"),
            F("local1_wages", "Local wages, tips, etc.", "money", "18", [B(18) + r"Local wages"], section="State"),
            F("local1_tax", "Local income tax", "money", "19", [B(19) + r"Local income tax"], section="State"),
            F("locality1", "Locality name", "text", "20", [B(20) + r"Locality name"], mode="below", section="State"),
        ],
    },
    "W-2G": {
        "name": "Form W-2G — Certain Gambling Winnings", "module": "Income", "screen": "W2G", "screen_name": "Gambling winnings (W-2G)",
        "detect": {"all": [r"\bW-2G\b"], "any": [r"Gambling Winnings", r"Reportable winnings"]},
        "payer_key": "payer_name", "payer_tin_key": "payer_tin", "recipient_tin_key": "recipient_tin", "key_amount": "box1",
        "fields": [TS(), *party("payer", PAYER_RES, "Payer", "Payer"),
                   F("payer_tin", "Payer's federal identification number", "ein", "", PAYER_TIN, section="Payer"),
                   F("recipient_tin", "Winner's TIN", "tin", "", [r"WINNER'?S (?:TIN|taxpayer identification no)"], section="Winner"),
                   F("box1", "Reportable winnings", "money", "1", [B(1) + r"Reportable winnings"], section="Amounts", required=True),
                   F("box2", "Date won", "date", "2", [B(2) + r"Date won"], section="Amounts"),
                   F("box3", "Type of wager", "text", "3", [B(3) + r"Type of wager"], mode="below", section="Amounts"),
                   F("box4", "Federal income tax withheld", "money", "4", [B(4) + r"Federal income tax withheld"], section="Amounts"),
                   F("box7", "Winnings from identical wagers", "money", "7", [B(7) + r"Winnings from identical wagers"], section="Amounts"),
                   F("box14", "State winnings", "money", "14", [B(14) + r"State winnings"], section="State"),
                   F("box15", "State income tax withheld", "money", "15", [B(15) + r"State income tax withheld"], section="State")],
    },
    "1099-INT": {
        "name": "Form 1099-INT — Interest Income", "module": "Income", "screen": "INT", "screen_name": "Interest income (1099-INT)",
        "detect": {"all": [r"1099-INT"], "any": [r"Interest Income", r"Early withdrawal penalty"]},
        "composite": r"^INTEREST INCOME\b|\bINTEREST INCOME\b.*1099-INT",
        "payer_key": "payer_name", "payer_tin_key": "payer_tin", "recipient_tin_key": "recipient_tin", "key_amount": "box1",
        "drake_verified": True,
        "fields": [TS(), *party("payer", PAYER_RES, "Payer", "Payer", {"name": "Textbox_9"}),
                   F("payer_tin", "Payer's TIN", "ein", "", PAYER_TIN, section="Payer", aid="Textbox_7"),
                   *recipient(), F("account", "Account number", "account", "", ACCOUNT, mode="value", section="Recipient"),
                   F("box1", "Interest income", "money", "1", [B(1) + r"Interest income"], section="Amounts", required=True, aid="Textbox_20"),
                   F("box2", "Early withdrawal penalty", "money", "2", [B(2) + r"Early withdrawal penalty"], section="Amounts"),
                   F("box3", "Interest on U.S. Savings Bonds and Treasury obligations", "money", "3", [B(3) + r"Interest on U\.?S\.? Savings"],
                     section="Amounts", aid="Textbox_22"),
                   F("box4", "Federal income tax withheld", "money", "4", [B(4) + r"Federal income tax withheld"], section="Amounts", aid="Textbox_23"),
                   F("box5", "Investment expenses", "money", "5", [B(5) + r"Investment expenses"], section="Amounts"),
                   F("box6", "Foreign tax paid", "money", "6", [B(6) + r"Foreign tax paid"], section="Amounts"),
                   F("box7", "Foreign country or U.S. possession", "text", "7", [B(7) + r"Foreign country"], section="Amounts"),
                   F("box8", "Tax-exempt interest", "money", "8", [B(8) + r"Tax-exempt interest"], section="Amounts"),
                   F("box9", "Specified private activity bond interest", "money", "9", [B(9) + r"Specified private activity"], section="Amounts"),
                   F("box10", "Market discount", "money", "10", [B(10) + r"Market discount"], section="Amounts"),
                   F("box11", "Bond premium", "money", "11", [B(11) + r"Bond premium\b(?! on)"], section="Amounts"),
                   F("box12", "Bond premium on Treasury obligations", "money", "12", [B(12) + r"Bond premium on Treasury"], section="Amounts"),
                   F("box13", "Bond premium on tax-exempt bond", "money", "13", [B(13) + r"Bond premium on tax-exempt"], section="Amounts"),
                   F("box17", "State tax withheld", "money", "17", [B(17) + r"State tax withheld"], section="State")],
    },
    "1099-DIV": {
        "name": "Form 1099-DIV — Dividends and Distributions", "module": "Income", "screen": "DIV", "screen_name": "Dividend income (1099-DIV)",
        "detect": {"all": [r"1099-DIV"], "any": [r"Dividends and Distributions", r"ordinary dividends"]},
        "composite": r"DIVIDENDS AND DISTRIBUTIONS",
        "payer_key": "payer_name", "payer_tin_key": "payer_tin", "recipient_tin_key": "recipient_tin", "key_amount": "box1a",
        "drake_verified": True,
        "fields": [TS(), *party("payer", PAYER_RES, "Payer", "Payer", {"name": "Textbox_8"}),
                   F("payer_tin", "Payer's TIN", "ein", "", PAYER_TIN, section="Payer", aid="Textbox_6"),
                   *recipient(), F("account", "Account number", "account", "", ACCOUNT, section="Recipient"),
                   F("box1a", "Total ordinary dividends", "money", "1a", [B("1a") + r"Total ordinary dividends"], section="Amounts", required=True, aid="Textbox_18"),
                   F("box1b", "Qualified dividends", "money", "1b", [B("1b") + r"Qualified dividends"], section="Amounts", aid="Textbox_19"),
                   F("box2a", "Total capital gain distributions", "money", "2a", [B("2a") + r"Total capital gain"], section="Amounts", aid="Textbox_20"),
                   F("box2b", "Unrecaptured Sec. 1250 gain", "money", "2b", [B("2b") + r"Unrecap"], section="Amounts"),
                   F("box2c", "Section 1202 gain", "money", "2c", [B("2c") + r"Section 1202 gain"], section="Amounts"),
                   F("box2d", "Collectibles (28%) gain", "money", "2d", [B("2d") + r"Collectibles"], section="Amounts"),
                   F("box2e", "Section 897 ordinary dividends", "money", "2e", [B("2e") + r"Section 897 ordinary"], section="Amounts"),
                   F("box2f", "Section 897 capital gain", "money", "2f", [B("2f") + r"Section 897 capital"], section="Amounts"),
                   F("box3", "Nondividend distributions", "money", "3", [B(3) + r"Nondividend distributions"], section="Amounts"),
                   F("box4", "Federal income tax withheld", "money", "4", [B(4) + r"Federal income tax withheld"], section="Amounts", aid="Textbox_28"),
                   F("box5", "Section 199A dividends", "money", "5", [B(5) + r"Section 199A dividends"], section="Amounts"),
                   F("box6", "Investment expenses", "money", "6", [B(6) + r"Investment expenses"], section="Amounts"),
                   F("box7", "Foreign tax paid", "money", "7", [B(7) + r"Foreign tax paid"], section="Amounts"),
                   F("box8", "Foreign country or U.S. possession", "text", "8", [B(8) + r"Foreign country"], section="Amounts"),
                   F("box9", "Cash liquidation distributions", "money", "9", [B(9) + r"Cash liquidation"], section="Amounts"),
                   F("box10", "Noncash liquidation distributions", "money", "10", [B(10) + r"Noncash liquidation"], section="Amounts"),
                   F("box12", "Exempt-interest dividends", "money", "12", [B(12) + r"Exempt-interest dividends"], section="Amounts"),
                   F("box13", "Specified private activity bond interest dividends", "money", "13", [B(13) + r"Specified private activity"], section="Amounts"),
                   F("box16", "State tax withheld", "money", "16", [B(16) + r"State tax withheld"], section="State")],
    },
    "1099-R": {
        "name": "Form 1099-R — Distributions From Pensions, Annuities, IRAs", "module": "Income", "screen": "1099",
        "screen_name": "Retirement income (1099-R)",
        "detect": {"all": [r"1099-R"], "any": [r"Distributions From", r"Gross distribution", r"Pensions,? Annuities"]},
        "payer_key": "payer_name", "payer_tin_key": "payer_tin", "recipient_tin_key": "recipient_tin", "key_amount": "box1",
        "drake_verified": True,
        "fields": [TS(), *party("payer", PAYER_RES, "Payer", "Payer", {"name": "Textbox_6"}),
                   F("payer_tin", "Payer's TIN", "ein", "", PAYER_TIN, section="Payer", aid="Textbox_5"),
                   *recipient(), F("account", "Account number", "account", "", ACCOUNT, mode="below", section="Recipient"),
                   F("box1", "Gross distribution", "money", "1", [B(1) + r"Gross distribution"], section="Amounts", required=True, aid="Textbox_25"),
                   F("box2a", "Taxable amount", "money", "2a", [B("2a") + r"Taxable amount"], section="Amounts", aid="Textbox_26"),
                   F("box2b_not_determined", "Taxable amount not determined", "bool", "2b", [r"Taxable amount\s+not determined", r"not\s+determined"], mode="check", section="Amounts"),
                   F("box2b_total", "Total distribution", "bool", "2b", [r"Total\s+distribution"], mode="check", section="Amounts"),
                   F("box3", "Capital gain (included in box 2a)", "money", "3", [B(3) + r"Capital gain"], section="Amounts"),
                   F("box4", "Federal income tax withheld", "money", "4", [B(4) + r"Federal income tax withheld"], section="Amounts", aid="Textbox_30"),
                   F("box5", "Employee contributions / Roth contributions", "money", "5", [B(5) + r"Employee contributions"], section="Amounts"),
                   F("box6", "Net unrealized appreciation", "money", "6", [B(6) + r"Net unrealized"], section="Amounts"),
                   F("box7", "Distribution code(s)", "code", "7", [B(7) + r"Distribution"], mode="value", section="Amounts", required=True,
                     aid="Textbox_36", pattern=R_CODE),
                   F("box7_ira", "IRA/SEP/SIMPLE", "bool", "7", [r"IRA/\s*SEP/\s*SIMPLE", r"IRA/"], mode="check", section="Amounts"),
                   F("box8", "Other", "money", "8", [B(8) + r"Other\b"], section="Amounts"),
                   F("box9b", "Total employee contributions", "money", "9b", [B("9b") + r"Total employee contributions"], section="Amounts"),
                   F("box14", "State tax withheld", "money", "14", [B(14) + r"State tax withheld"], section="State"),
                   F("box16", "State distribution", "money", "16", [B(16) + r"State distribution"], section="State")],
    },
    "1099-MISC": {
        "name": "Form 1099-MISC — Miscellaneous Information", "module": "Income", "screen": "99M", "screen_name": "Miscellaneous income (1099-MISC)",
        "detect": {"all": [r"1099-MISC"], "any": [r"Miscellaneous (?:Information|Income)", r"Royalties"]},
        "composite": r"MISCELLANEOUS INFORMATION",
        "payer_key": "payer_name", "payer_tin_key": "payer_tin", "recipient_tin_key": "recipient_tin", "key_amount": "box3",
        "drake_verified": True,
        "fields": [TS(), *party("payer", PAYER_RES, "Payer", "Payer", {"name": "Textbox_6"}),
                   F("payer_tin", "Payer's TIN", "ein", "", PAYER_TIN, section="Payer", aid="Textbox_5"),
                   *recipient(), F("account", "Account number", "account", "", ACCOUNT, section="Recipient"),
                   F("box1", "Rents", "money", "1", [B(1) + r"Rents"], section="Amounts"),
                   F("box2", "Royalties", "money", "2", [B(2) + r"Royalties"], section="Amounts", aid="Textbox_12"),
                   F("box3", "Other income", "money", "3", [B(3) + r"Other income"], section="Amounts", aid="Textbox_13"),
                   F("box4", "Federal income tax withheld", "money", "4", [B(4) + r"Federal income tax withheld"], section="Amounts"),
                   F("box5", "Fishing boat proceeds", "money", "5", [B(5) + r"Fishing boat"], section="Amounts"),
                   F("box6", "Medical and health care payments", "money", "6", [B(6) + r"Medical and health"], section="Amounts"),
                   F("box8", "Substitute payments in lieu of dividends or interest", "money", "8", [B(8) + r"Substitute payments"], section="Amounts"),
                   F("box9", "Crop insurance proceeds", "money", "9", [B(9) + r"Crop insurance"], section="Amounts"),
                   F("box10", "Gross proceeds paid to an attorney", "money", "10", [B(10) + r"Gross proceeds paid to an attorney"], section="Amounts"),
                   F("box15", "Nonqualified deferred compensation", "money", "15", [B(15) + r"Nonqualified deferred"], section="Amounts"),
                   F("box16", "State tax withheld", "money", "16", [B(16) + r"State tax withheld"], section="State")],
    },
    "1099-NEC": {
        "name": "Form 1099-NEC — Nonemployee Compensation", "module": "Income", "screen": "99N", "screen_name": "Nonemployee compensation (1099-NEC)",
        "detect": {"all": [r"1099-NEC"], "any": [r"Nonemployee compensation"]},
        "payer_key": "payer_name", "payer_tin_key": "payer_tin", "recipient_tin_key": "recipient_tin", "key_amount": "box1",
        "fields": [TS(), *party("payer", PAYER_RES, "Payer", "Payer"),
                   F("payer_tin", "Payer's TIN", "ein", "", PAYER_TIN, section="Payer"), *recipient(),
                   F("account", "Account number", "account", "", ACCOUNT, mode="below", section="Recipient"),
                   F("box1", "Nonemployee compensation", "money", "1", [B(1) + r"Nonemployee compensation"], section="Amounts", required=True),
                   F("box2", "Direct sales of $5,000 or more", "bool", "2", [r"Payer made direct sales"], mode="check", section="Amounts"),
                   F("box4", "Federal income tax withheld", "money", "4", [B(4) + r"Federal income tax withheld"], section="Amounts"),
                   F("box5", "State tax withheld", "money", "5", [B(5) + r"State tax withheld"], section="State")],
    },
    "1099-G": {
        "name": "Form 1099-G — Certain Government Payments", "module": "Income", "screen": "99G", "screen_name": "Government payments (1099-G)",
        "detect": {"all": [r"1099-G\b"], "any": [r"Certain Government Payments", r"Unemployment compensation"]},
        "payer_key": "payer_name", "payer_tin_key": "payer_tin", "recipient_tin_key": "recipient_tin", "key_amount": "box1",
        "fields": [TS(), *party("payer", PAYER_RES, "Payer", "Payer"),
                   F("payer_tin", "Payer's TIN", "ein", "", PAYER_TIN, section="Payer"), *recipient(),
                   F("box1", "Unemployment compensation", "money", "1", [B(1) + r"Unemployment compensation"], section="Amounts"),
                   F("box2", "State or local income tax refunds", "money", "2", [B(2) + r"State or local income tax refunds"], section="Amounts"),
                   F("box3", "Tax year of box 2 refund", "year", "3", [B(3) + r"Box 2 amount is for tax year"], section="Amounts"),
                   F("box4", "Federal income tax withheld", "money", "4", [B(4) + r"Federal income tax withheld"], section="Amounts"),
                   F("box6", "Taxable grants", "money", "6", [B(6) + r"Taxable grants"], section="Amounts"),
                   F("box7", "Agriculture payments", "money", "7", [B(7) + r"Agriculture payments"], section="Amounts"),
                   F("box11", "State income tax withheld", "money", "11", [B(11) + r"State income tax withheld"], section="State")],
    },
    "1099-K": {
        "name": "Form 1099-K — Payment Card and Third Party Network Transactions", "module": "Income", "screen": "99K",
        "screen_name": "Payment card / third party network (1099-K)",
        "detect": {"all": [r"1099-K\b"], "any": [r"Payment Card and Third Party", r"Gross amount of payment card"]},
        "payer_key": "payer_name", "payer_tin_key": "payer_tin", "recipient_tin_key": "recipient_tin", "key_amount": "box1a",
        "fields": [TS(), *party("payer", [r"FILER'?S name", *PAYER_RES], "Filer", "Filer"),
                   F("payer_tin", "Filer's TIN", "ein", "", PAYER_TIN, section="Filer"), *recipient("Payee"),
                   F("box1a", "Gross amount of payment card/third party network transactions", "money", "1a", [B("1a") + r"Gross amount"], section="Amounts", required=True),
                   F("box1b", "Card not present transactions", "money", "1b", [B("1b") + r"Card not present"], section="Amounts"),
                   F("box3", "Number of payment transactions", "int", "3", [B(3) + r"Number of payment transactions"], section="Amounts"),
                   F("box4", "Federal income tax withheld", "money", "4", [B(4) + r"Federal income tax withheld"], section="Amounts")],
    },
    "1099-B": {
        "name": "Form 1099-B — Proceeds From Broker Transactions", "module": "Income", "screen": "8949", "screen_name": "Capital gains (1099-B / Form 8949)",
        "detect": {"all": [r"1099-B"], "any": [r"Proceeds From Broker", r"Barter Exchange"]},
        "composite": r"SUMMARY OF PROCEEDS",
        "payer_key": "payer_name", "payer_tin_key": "payer_tin", "recipient_tin_key": "recipient_tin", "key_amount": "total_proceeds",
        "lots": True,
        "fields": [TS(), *party("payer", PAYER_RES, "Payer", "Payer"),
                   F("payer_tin", "Payer's TIN", "ein", "", PAYER_TIN, section="Payer"), *recipient(),
                   F("account", "Account number", "account", "", ACCOUNT, section="Recipient"),
                   F("box1a", "Description of property", "text", "1a", [B("1a") + r"Description of property"], mode="below", section="Single sale"),
                   F("box1b", "Date acquired", "date", "1b", [B("1b") + r"Date acquired"], section="Single sale"),
                   F("box1c", "Date sold or disposed", "date", "1c", [B("1c") + r"Date sold"], section="Single sale"),
                   F("box1d", "Proceeds", "money", "1d", [B("1d") + r"Proceeds"], section="Single sale"),
                   F("box1e", "Cost or other basis", "money", "1e", [B("1e") + r"Cost or other basis"], section="Single sale"),
                   F("box1g", "Wash sale loss disallowed", "money", "1g", [B("1g") + r"Wash sale loss"], section="Single sale"),
                   F("box4", "Federal income tax withheld", "money", "4", [B(4) + r"Federal income tax withheld", r"Federal income tax withheld"], section="Single sale"),
                   F("st_proceeds", "Short-term proceeds", "money", "A", mode="table", row=r"^Total Short-term", col=r"^Proceeds$", section="Short-term (Part I)"),
                   F("st_cost", "Short-term cost basis", "money", "A", mode="table", row=r"^Total Short-term", col=r"^Cost$|^Cost basis", section="Short-term (Part I)"),
                   F("st_wash", "Short-term wash sale loss disallowed", "money", "A", mode="table", row=r"^Total Short-term", col=r"^Wash$|Wash sale", section="Short-term (Part I)"),
                   F("st_gain", "Short-term net gain or loss", "money", "A", mode="table", row=r"^Total Short-term", col=r"^Net$|Net gain", section="Short-term (Part I)"),
                   F("lt_proceeds", "Long-term proceeds", "money", "D", mode="table", row=r"^Total Long-term", col=r"^Proceeds$", section="Long-term (Part II)"),
                   F("lt_cost", "Long-term cost basis", "money", "D", mode="table", row=r"^Total Long-term", col=r"^Cost$|^Cost basis", section="Long-term (Part II)"),
                   F("lt_wash", "Long-term wash sale loss disallowed", "money", "D", mode="table", row=r"^Total Long-term", col=r"^Wash$|Wash sale", section="Long-term (Part II)"),
                   F("lt_gain", "Long-term net gain or loss", "money", "D", mode="table", row=r"^Total Long-term", col=r"^Net$|Net gain", section="Long-term (Part II)"),
                   F("total_proceeds", "Total proceeds", "money", "", mode="table", row=r"^Grand total", col=r"^Proceeds$", section="Totals"),
                   F("total_cost", "Total cost basis", "money", "", mode="table", row=r"^Grand total", col=r"^Cost$|^Cost basis", section="Totals"),
                   F("total_gain", "Total net gain or loss", "money", "", mode="table", row=r"^Grand total", col=r"^Net$|Net gain", section="Totals")],
    },
    "1099-OID": {
        "name": "Form 1099-OID — Original Issue Discount", "module": "Income", "screen": "OID", "screen_name": "Original issue discount (1099-OID)",
        "detect": {"all": [r"1099-OID"], "any": [r"Original Issue Discount"]},
        "composite": r"ORIGINAL ISSUE DISCOUNT",
        "payer_key": "payer_name", "payer_tin_key": "payer_tin", "recipient_tin_key": "recipient_tin", "key_amount": "box1",
        "drake_verified": True,
        "fields": [TS(), *party("payer", PAYER_RES, "Payer", "Payer", {"name": "Textbox_6"}),
                   F("payer_tin", "Payer's TIN", "ein", "", PAYER_TIN, section="Payer", aid="Textbox_5"), *recipient(),
                   F("account", "Account number", "account", "", ACCOUNT, section="Recipient"),
                   F("box1", "Original issue discount for the year", "money", "1", [r"Original issue discount for the year", B(1) + r"Original issue discount"], section="Amounts"),
                   F("box2", "Other periodic interest", "money", "2", [B(2) + r"Other periodic interest"], section="Amounts"),
                   F("box3", "Early withdrawal penalty", "money", "3", [B(3) + r"Early withdrawal penalty", r"^Early withdrawal penalty"], section="Amounts"),
                   F("box4", "Federal income tax withheld", "money", "4", [B(4) + r"Federal income tax withheld"], section="Amounts"),
                   F("box5", "Market discount", "money", "5", [B(5) + r"Market discount", r"Market discount \(all lots\)"], section="Amounts"),
                   F("box6", "Acquisition premium", "money", "6", [B(6) + r"Acquisition premium", r"^Acquisition premium \(covered lots\)"], section="Amounts"),
                   F("box8", "OID on U.S. Treasury obligations", "money", "8", [B(8) + r"Original issue discount on U\.?S\.? Treasury", r"Original issue discount on Treasury obligations"], section="Amounts"),
                   F("box9", "Investment expenses", "money", "9", [B(9) + r"Investment expenses", r"^Investment expenses"], section="Amounts"),
                   F("box11", "Tax-exempt OID", "money", "11", [B(11) + r"Tax-exempt OID", r"^Tax-exempt OID$|^Tax-exempt OID\s+[\d,.]+$"], section="Amounts")],
    },
    "1099-SA": {
        "name": "Form 1099-SA — Distributions From an HSA, Archer MSA, or MA MSA", "module": "Health Care", "screen": "8889",
        "screen_name": "HSA distributions (1099-SA → Form 8889)",
        "detect": {"all": [r"1099-SA"], "any": [r"Distributions From an HSA", r"Archer MSA"]},
        "payer_key": "payer_name", "payer_tin_key": "payer_tin", "recipient_tin_key": "recipient_tin", "key_amount": "box1",
        "fields": [TS(), *party("payer", [r"(?:PAYER|TRUSTEE)'?S name", *PAYER_RES], "Payer", "Payer"),
                   F("payer_tin", "Payer's TIN", "ein", "", PAYER_TIN, section="Payer"), *recipient(),
                   F("box1", "Gross distribution", "money", "1", [B(1) + r"Gross distribution"], section="Amounts", required=True),
                   F("box2", "Earnings on excess contributions", "money", "2", [B(2) + r"Earnings on excess"], section="Amounts"),
                   F("box3", "Distribution code", "code", "3", [B(3) + r"Distribution code"], section="Amounts"),
                   F("box5", "Account type", "text", "5", [r"\b5\s+HSA"], mode="choice", options=["HSA", "Archer MSA", "MA MSA"], section="Amounts")],
    },
    "1099-Q": {
        "name": "Form 1099-Q — Payments From Qualified Education Programs", "module": "Income", "screen": "99Q",
        "screen_name": "Education program payments (1099-Q)",
        "detect": {"all": [r"1099-Q\b"], "any": [r"Qualified Education Programs", r"Payments From Qualified"]},
        "payer_key": "payer_name", "payer_tin_key": "payer_tin", "recipient_tin_key": "recipient_tin", "key_amount": "box1",
        "fields": [TS(), *party("payer", [r"PAYER'?S/TRUSTEE'?S name", *PAYER_RES], "Payer", "Payer"),
                   F("payer_tin", "Payer's TIN", "ein", "", PAYER_TIN, section="Payer"), *recipient(),
                   F("box1", "Gross distribution", "money", "1", [B(1) + r"Gross distribution"], section="Amounts", required=True),
                   F("box2", "Earnings", "money", "2", [B(2) + r"Earnings"], section="Amounts"),
                   F("box3", "Basis", "money", "3", [B(3) + r"Basis"], section="Amounts"),
                   F("box4", "Trustee-to-trustee transfer", "bool", "4", [r"Trustee-to-trustee transfer"], mode="check", section="Amounts")],
    },
    "SSA-1099": {
        "name": "Form SSA-1099 / SSA-1042S — Social Security Benefit Statement", "module": "Income", "screen": "SSA",
        "screen_name": "Social security benefits (SSA-1099)",
        "detect": {"all": [r"SSA-?1099|SSA-?1042S"], "any": [r"Social Security Benefit", r"Benefits Paid"]},
        "payer_key": "", "payer_tin_key": "", "recipient_tin_key": "beneficiary_ssn", "key_amount": "box5",
        "drake_verified": True,
        "fields": [TS(),
                   F("form_variant", "Form variant", "text", "", [], mode="manual", section="Beneficiary", hint="SSA-1099 or SSA-1042S"),
                   F("beneficiary_name", "Box 1 · Name", "name", "1", [r"Box\s*1\.?\s*Name"], mode="below", section="Beneficiary"),
                   F("beneficiary_ssn", "Box 2 · Beneficiary's SSN", "ssn", "2", [r"Box\s*2\.?\s*Beneficiary"], section="Beneficiary"),
                   F("box3", "Benefits paid", "money", "3", [r"Box\s*3\.?\s*Benefits Paid"], section="Benefits"),
                   F("box4", "Benefits repaid to SSA", "money", "4", [r"Box\s*4\.?\s*Benefits Repaid"], section="Benefits"),
                   F("box5", "Net benefits", "money", "5", [r"Box\s*5\.?\s*Net Benefits"], section="Benefits", required=True, aid="Textbox_5"),
                   F("box6", "Voluntary federal income tax withheld", "money", "6", [r"Box\s*6\.?\s*Voluntary Federal Income Tax Withheld"], section="Benefits", aid="Textbox_7"),
                   F("box6_rate", "Rate of tax (SSA-1042S)", "percent", "6", [r"Box\s*6\.?\s*Rate of Tax"], section="SSA-1042S"),
                   F("box7_1042", "Amount of tax withheld (SSA-1042S)", "money", "7", [r"Box\s*7\.?\s*Amount of Tax Withheld"], section="SSA-1042S"),
                   F("box9_1042", "Net tax withheld (SSA-1042S)", "money", "9", [r"Box\s*9\.?\s*Net Tax Withheld"], section="SSA-1042S"),
                   F("claim_number", "Claim number", "text", "11", [r"Box\s*11\.?\s*Claim Number", r"Claim Number:"], section="Beneficiary")],
    },
    "K-1 1065": {
        "name": "Schedule K-1 (Form 1065) — Partner's Share", "module": "Income", "screen": "K1P", "screen_name": "Partnership K-1 (1065)",
        "detect": {"all": [r"Schedule K-1", r"Form 1065"], "any": [r"Partner'?s Share", r"Partnership"]},
        "payer_key": "entity_name", "payer_tin_key": "entity_ein", "recipient_tin_key": "partner_tin", "key_amount": "box1",
        "fields": [TS(), F("entity_ein", "Partnership's EIN", "ein", "A", [r"Partnership'?s employer identification number"], section="Partnership"),
                   *party("entity", [r"Partnership'?s name, address"], "Partnership", "Partnership"),
                   F("partner_tin", "Partner's identifying number", "tin", "E", [r"Partner'?s (?:SSN or TIN|identifying number)"], section="Partner"),
                   F("box1", "Ordinary business income (loss)", "money", "1", [B(1) + r"Ordinary business income"], section="Part III"),
                   F("box2", "Net rental real estate income (loss)", "money", "2", [B(2) + r"Net rental real estate"], section="Part III"),
                   F("box3", "Other net rental income (loss)", "money", "3", [B(3) + r"Other net rental"], section="Part III"),
                   F("box4a", "Guaranteed payments for services", "money", "4a", [B("4a") + r"Guaranteed payments for services"], section="Part III"),
                   F("box5", "Interest income", "money", "5", [B(5) + r"Interest income"], section="Part III"),
                   F("box6a", "Ordinary dividends", "money", "6a", [B("6a") + r"Ordinary dividends"], section="Part III"),
                   F("box6b", "Qualified dividends", "money", "6b", [B("6b") + r"Qualified dividends"], section="Part III"),
                   F("box7", "Royalties", "money", "7", [B(7) + r"Royalties"], section="Part III"),
                   F("box8", "Net short-term capital gain (loss)", "money", "8", [B(8) + r"Net short-term capital gain"], section="Part III"),
                   F("box9a", "Net long-term capital gain (loss)", "money", "9a", [B("9a") + r"Net long-term capital gain"], section="Part III"),
                   F("box10", "Net section 1231 gain (loss)", "money", "10", [B(10) + r"Net section 1231"], section="Part III"),
                   F("box14", "Self-employment earnings (loss)", "money", "14", [B(14) + r"Self-employment earnings"], section="Part III"),
                   F("box19", "Distributions", "money", "19", [B(19) + r"Distributions"], section="Part III"),
                   F("box21", "Foreign taxes paid or accrued", "money", "21", [B(21) + r"Foreign taxes paid"], section="Part III")],
    },
    "K-1 1120-S": {
        "name": "Schedule K-1 (Form 1120-S) — Shareholder's Share", "module": "Income", "screen": "K1S", "screen_name": "S corporation K-1 (1120-S)",
        "detect": {"all": [r"Schedule K-1", r"1120-?S"], "any": [r"Shareholder'?s Share", r"S Corporation"]},
        "payer_key": "entity_name", "payer_tin_key": "entity_ein", "recipient_tin_key": "shareholder_tin", "key_amount": "box1",
        "fields": [TS(), F("entity_ein", "Corporation's EIN", "ein", "A", [r"Corporation'?s employer identification number"], section="Corporation"),
                   *party("entity", [r"Corporation'?s name, address"], "Corporation", "Corporation"),
                   F("shareholder_tin", "Shareholder's identifying number", "tin", "E", [r"Shareholder'?s identifying number"], section="Shareholder"),
                   F("box1", "Ordinary business income (loss)", "money", "1", [B(1) + r"Ordinary business income"], section="Part III"),
                   F("box2", "Net rental real estate income (loss)", "money", "2", [B(2) + r"Net rental real estate"], section="Part III"),
                   F("box4", "Interest income", "money", "4", [B(4) + r"Interest income"], section="Part III"),
                   F("box5a", "Ordinary dividends", "money", "5a", [B("5a") + r"Ordinary dividends"], section="Part III"),
                   F("box5b", "Qualified dividends", "money", "5b", [B("5b") + r"Qualified dividends"], section="Part III"),
                   F("box6", "Royalties", "money", "6", [B(6) + r"Royalties"], section="Part III"),
                   F("box7", "Net short-term capital gain (loss)", "money", "7", [B(7) + r"Net short-term capital gain"], section="Part III"),
                   F("box8a", "Net long-term capital gain (loss)", "money", "8a", [B("8a") + r"Net long-term capital gain"], section="Part III"),
                   F("box9", "Net section 1231 gain (loss)", "money", "9", [B(9) + r"Net section 1231"], section="Part III")],
    },
    # ------------------------------------------------------------------ DEDUCTIONS / ADJUSTMENTS / CREDITS
    "1098": {
        "name": "Form 1098 — Mortgage Interest Statement", "module": "Adjustments", "screen": "A", "screen_name": "Itemized deductions — mortgage interest (1098)",
        "detect": {"all": [r"\b1098\b"], "any": [r"Mortgage Interest", r"Outstanding mortgage principal"], "not": [r"1098-[TEC]\b"]},
        "payer_key": "lender_name", "payer_tin_key": "lender_tin", "recipient_tin_key": "borrower_tin", "key_amount": "box1",
        "drake_verified": True,
        "fields": [*party("lender", [r"RECIPIENT'?S/LENDER'?S name", r"LENDER'?S name"], "Lender", "Lender"),
                   F("lender_tin", "Lender's TIN", "ein", "", [r"RECIPIENT'?S/LENDER'?S TIN", r"LENDER'?S TIN"], section="Lender"),
                   F("borrower_tin", "Borrower's TIN", "tin", "", [r"PAYER'?S/BORROWER'?S TIN", r"BORROWER'?S TIN"], section="Borrower"),
                   F("borrower_name", "Borrower's name", "name", "", [r"PAYER'?S/BORROWER'?S name", r"BORROWER'?S name"], mode="below", section="Borrower"),
                   F("account", "Account number", "account", "", ACCOUNT, mode="below", section="Borrower"),
                   F("box1", "Mortgage interest received", "money", "1", [B(1) + r"Mortgage interest received"], section="Amounts", required=True, aid="Textbox_47"),
                   F("box2", "Outstanding mortgage principal", "money", "2", [B(2) + r"Outstanding mortgage principal"], section="Amounts"),
                   F("box3", "Mortgage origination date", "date", "3", [B(3) + r"Mortgage origination date"], section="Amounts"),
                   F("box4", "Refund of overpaid interest", "money", "4", [B(4) + r"Refund of overpaid interest"], section="Amounts"),
                   F("box5", "Mortgage insurance premiums", "money", "5", [B(5) + r"Mortgage insurance premiums"], section="Amounts"),
                   F("box6", "Points paid on purchase of principal residence", "money", "6", [B(6) + r"Points paid"], section="Amounts"),
                   F("box9", "Number of properties securing the mortgage", "int", "9", [B(9) + r"Number of properties"], mode="below", section="Amounts"),
                   F("box10", "Other (property taxes / insurance)", "money", "10", [B(10) + r"Other\b"], section="Amounts"),
                   F("box11", "Mortgage acquisition date", "date", "11", [B(11) + r"Mortgage\s*$", r"Mortgage acquisition date"], section="Amounts")],
    },
    "1098-E": {
        "name": "Form 1098-E — Student Loan Interest Statement", "module": "Adjustments", "screen": "ADJ", "screen_name": "Adjustments — student loan interest (1098-E)",
        "detect": {"all": [r"1098-E\b"], "any": [r"Student Loan Interest"]},
        "payer_key": "lender_name", "payer_tin_key": "lender_tin", "recipient_tin_key": "borrower_tin", "key_amount": "box1",
        "fields": [*party("lender", [r"RECIPIENT'?S/LENDER'?S name", r"LENDER'?S name"], "Lender", "Lender"),
                   F("lender_tin", "Lender's TIN", "ein", "", [r"RECIPIENT'?S/LENDER'?S TIN", r"LENDER'?S TIN"], section="Lender"),
                   F("borrower_tin", "Borrower's TIN", "tin", "", [r"BORROWER'?S TIN"], section="Borrower"),
                   F("box1", "Student loan interest received by lender", "money", "1", [B(1) + r"Student loan interest"], section="Amounts", required=True)],
    },
    "1098-T": {
        "name": "Form 1098-T — Tuition Statement", "module": "Credits", "screen": "8863", "screen_name": "Education credits (1098-T → Form 8863)",
        "detect": {"all": [r"1098-T\b"], "any": [r"Tuition Statement", r"qualified tuition"]},
        "payer_key": "filer_name", "payer_tin_key": "filer_ein", "recipient_tin_key": "student_tin", "key_amount": "box1",
        "fields": [*party("filer", [r"FILER'?S name, street address", r"FILER'?S name"], "School", "School"),
                   F("filer_ein", "School's EIN", "ein", "", [r"FILER'?S (?:employer identification no|EIN|federal identification)"], section="School"),
                   F("student_tin", "Student's TIN", "tin", "", [r"STUDENT'?S TIN"], section="Student"),
                   F("student_name", "Student's name", "name", "", [r"STUDENT'?S name"], mode="below", section="Student"),
                   F("box1", "Payments received for qualified tuition and related expenses", "money", "1", [B(1) + r"Payments received"], section="Amounts", required=True),
                   F("box4", "Adjustments made for a prior year", "money", "4", [B(4) + r"Adjustments made for a prior year"], section="Amounts"),
                   F("box5", "Scholarships or grants", "money", "5", [B(5) + r"Scholarships or grants"], section="Amounts"),
                   F("box6", "Adjustments to scholarships or grants for a prior year", "money", "6", [B(6) + r"Adjustments to scholarships"], section="Amounts"),
                   F("box8", "At least half-time student", "bool", "8", [r"at least half-time"], mode="check", section="Amounts"),
                   F("box9", "Graduate student", "bool", "9", [r"graduate student"], mode="check", section="Amounts")],
    },
    "5498": {
        "name": "Form 5498 — IRA Contribution Information", "module": "Other Forms", "screen": "8606", "screen_name": "IRA information (5498 → Form 8606)",
        "detect": {"all": [r"\b5498\b"], "any": [r"IRA Contribution", r"Rollover contributions"], "not": [r"5498-SA"]},
        "payer_key": "trustee_name", "payer_tin_key": "trustee_tin", "recipient_tin_key": "participant_tin", "key_amount": "box5",
        "informational": True,
        "fields": [*party("trustee", [r"TRUSTEE'?S or ISSUER'?S name", r"TRUSTEE'?S name"], "Trustee", "Trustee"),
                   F("trustee_tin", "Trustee's TIN", "ein", "", [r"TRUSTEE'?S or ISSUER'?S TIN", r"TRUSTEE'?S TIN"], section="Trustee"),
                   F("participant_tin", "Participant's TIN", "tin", "", [r"PARTICIPANT'?S TIN"], section="Participant"),
                   F("participant_name", "Participant's name", "name", "", [r"PARTICIPANT'?S name"], mode="below", section="Participant"),
                   F("account", "Account number", "account", "", ACCOUNT, mode="below", section="Participant"),
                   F("box1", "IRA contributions", "money", "1", [B(1) + r"IRA contributions"], section="Amounts"),
                   F("box2", "Rollover contributions", "money", "2", [B(2) + r"Rollover contributions"], section="Amounts"),
                   F("box3", "Roth IRA conversion amount", "money", "3", [B(3) + r"Roth IRA conversion"], section="Amounts"),
                   F("box4", "Recharacterized contributions", "money", "4", [B(4) + r"Recharacterized"], section="Amounts"),
                   F("box5", "Fair market value of account", "money", "5", [B(5) + r"FMV of account", B(5) + r"Fair market value"], section="Amounts"),
                   F("box7", "Account type", "text", "7", [B(7) + r"IRA\b"], mode="choice", options=["IRA", "SEP", "SIMPLE", "Roth IRA"], section="Amounts"),
                   F("box8", "SEP contributions", "money", "8", [B(8) + r"SEP contributions"], section="Amounts"),
                   F("box9", "SIMPLE contributions", "money", "9", [B(9) + r"SIMPLE contributions"], section="Amounts"),
                   F("box10", "Roth IRA contributions", "money", "10", [B(10) + r"Roth IRA contributions"], section="Amounts"),
                   F("box12b", "RMD amount", "money", "12b", [B("12b") + r"RMD amount"], section="Amounts")],
    },
    "5498-SA": {
        "name": "Form 5498-SA — HSA, Archer MSA, or MA MSA Information", "module": "Health Care", "screen": "8889", "screen_name": "HSA contributions (5498-SA → Form 8889)",
        "detect": {"all": [r"5498-SA"], "any": [r"HSA", r"Archer MSA"]},
        "payer_key": "trustee_name", "payer_tin_key": "trustee_tin", "recipient_tin_key": "participant_tin", "key_amount": "box2",
        "informational": True,
        "fields": [*party("trustee", [r"TRUSTEE'?S name"], "Trustee", "Trustee"),
                   F("trustee_tin", "Trustee's TIN", "ein", "", [r"TRUSTEE'?S TIN"], section="Trustee"),
                   F("participant_tin", "Participant's TIN", "tin", "", [r"PARTICIPANT'?S TIN"], section="Participant"),
                   F("box1", "Employee or self-employed person's Archer MSA contributions", "money", "1", [B(1) + r"Employee or self-employed"], section="Amounts"),
                   F("box2", "Total contributions made in the year", "money", "2", [B(2) + r"Total contributions made in"], section="Amounts"),
                   F("box3", "Total HSA or Archer MSA contributions made for prior year", "money", "3", [B(3) + r"Total HSA or Archer MSA contributions"], section="Amounts"),
                   F("box4", "Rollover contributions", "money", "4", [B(4) + r"Rollover contributions"], section="Amounts"),
                   F("box5", "Fair market value of HSA/MSA", "money", "5", [B(5) + r"Fair market value"], section="Amounts")],
    },
    # ------------------------------------------------------------------ HEALTH CARE
    "1095-A": {
        "name": "Form 1095-A — Health Insurance Marketplace Statement", "module": "Health Care", "screen": "95A", "screen_name": "Marketplace statement (1095-A)",
        "detect": {"all": [r"1095-A"], "any": [r"Health Insurance Marketplace"]},
        "payer_key": "marketplace", "payer_tin_key": "", "recipient_tin_key": "recipient_ssn", "key_amount": "annual_premium",
        "fields": [F("marketplace", "Marketplace identifier", "text", "1", [B(1) + r"Marketplace identifier"], mode="below", section="Policy"),
                   F("policy_number", "Marketplace-assigned policy number", "text", "2", [B(2) + r"Marketplace-assigned policy number"], mode="below", section="Policy"),
                   F("recipient_ssn", "Recipient's SSN", "ssn", "5", [B(5) + r"Recipient'?s SSN"], section="Recipient"),
                   F("annual_premium", "Annual total — monthly enrollment premiums (A)", "money", "33A", mode="table", row=r"Annual Totals", col=r"^A\.?$|Monthly enrollment premiums", section="Annual totals"),
                   F("annual_slcsp", "Annual total — SLCSP premium (B)", "money", "33B", mode="table", row=r"Annual Totals", col=r"^B\.?$|second lowest", section="Annual totals"),
                   F("annual_aptc", "Annual total — advance payment of PTC (C)", "money", "33C", mode="table", row=r"Annual Totals", col=r"^C\.?$|advance payment", section="Annual totals")],
    },
    "1095-B": {
        "name": "Form 1095-B — Health Coverage", "module": "Health Care", "screen": "", "screen_name": "Health coverage (1095-B, informational)",
        "detect": {"all": [r"1095-B"], "any": [r"Health Coverage"]}, "informational": True,
        "payer_key": "issuer_name", "payer_tin_key": "", "recipient_tin_key": "", "key_amount": "",
        "fields": [F("issuer_name", "Issuer or other coverage provider", "text", "16", [B(16) + r"Name"], mode="below", section="Issuer")],
    },
    "1095-C": {
        "name": "Form 1095-C — Employer-Provided Health Insurance Offer and Coverage", "module": "Health Care", "screen": "",
        "screen_name": "Employer health coverage (1095-C, informational)",
        "detect": {"all": [r"1095-C"], "any": [r"Employer-Provided Health Insurance"]}, "informational": True,
        "payer_key": "employer_name", "payer_tin_key": "employer_ein", "recipient_tin_key": "employee_ssn", "key_amount": "",
        "fields": [F("employer_name", "Employer name", "text", "7", [B(7) + r"Name of employer"], mode="below", section="Employer"),
                   F("employer_ein", "Employer EIN", "ein", "8", [B(8) + r"Employer identification number"], section="Employer"),
                   F("employee_ssn", "Employee SSN", "ssn", "2", [B(2) + r"Social security number"], section="Employee")],
    },
}

# ---------------------------------------------------------------------------
# Screens that are built from the packet as a whole (not from one PDF form)
# ---------------------------------------------------------------------------
DERIVED = {
    "TAXPAYER": {
        "name": "Name and address", "module": "General", "screen": "1", "screen_name": "Name, address, and general information (Screen 1)",
        "payer_key": "tp_name", "fields": [
            F("filing_status", "Filing status (1 Single, 2 MFJ, 3 MFS, 4 HOH, 5 QSS)", "code", "", mode="manual", section="Taxpayer",
              required=True, pattern=r"^[1-5]$", options=["", "1", "2", "3", "4", "5"], hint="Not on the forms — choose it. Drake needs it to save Screen 1."),
            F("tp_first", "Taxpayer first name", "text", "", section="Taxpayer", required=True),
            F("tp_mi", "Taxpayer middle initial", "text", "", section="Taxpayer"),
            F("tp_last", "Taxpayer last name", "text", "", section="Taxpayer", required=True),
            F("tp_ssn", "Taxpayer SSN", "ssn", "", section="Taxpayer", required=True),
            F("sp_first", "Spouse first name", "text", "", section="Spouse"),
            F("sp_last", "Spouse last name", "text", "", section="Spouse"),
            F("sp_ssn", "Spouse SSN", "ssn", "", section="Spouse"),
            F("street", "Street address", "text", "", section="Address", required=True),
            F("city", "City", "text", "", section="Address", required=True),
            F("state", "State", "state", "", section="Address", required=True),
            F("zip", "ZIP", "zip", "", section="Address", required=True),
        ]},
    "FOREIGN": {
        "name": "Foreign tax credit", "module": "Foreign", "screen": "1116", "screen_name": "Foreign tax credit (Form 1116)",
        "payer_key": "source", "fields": [
            F("source", "Source (payer)", "text", "", section="Source"),
            F("foreign_tax_1099", "Foreign tax paid per 1099", "money", "", section="Amounts"),
            F("foreign_tax_summary", "Foreign tax per country summary", "money", "", section="Amounts"),
            F("foreign_income", "Foreign source income (summary)", "money", "", section="Amounts"),
            F("countries", "Countries", "text", "", section="Amounts"),
        ]},
    "UNKNOWN": {
        "name": "Unrecognized document", "module": "Miscellaneous", "screen": "", "screen_name": "Unrecognized document — map manually",
        "payer_key": "", "fields": []},
}


# Values that are read from the PDF for checking/identification but are not inputs on the Drake screen
# (Drake takes the taxpayer from Screen 1 and the T/S code). They are shown and reported as "reference only".
REFERENCE_KEYS = {"recipient_tin", "recipient_name", "recipient_street", "recipient_cityline", "employee_ssn", "employee_name",
                  "employee_street", "employee_city", "employee_state", "employee_zip", "control_number", "beneficiary_name",
                  "beneficiary_ssn", "borrower_tin", "borrower_name", "participant_tin", "participant_name", "partner_tin",
                  "shareholder_tin", "form_variant", "claim_number"}

# ---------------------------------------------------------------------------
# Drake UI-Automation ids, read from the real Drake Tax 2025 screens (2026-11-05, screens opened on a
# test return and every input matched to its printed label). Only these ids are typed into; any field
# not listed here has no built-in id and is reported "not linked" until linked with "Link Drake fields".
# ---------------------------------------------------------------------------
VERIFIED_AIDS = {
    # tp_ssn (Textbox_2) is deliberately absent: Drake sets the SSN when it creates the return and the field is
    # read-only on an existing return — the SSN is used to open/create the return instead.
    "TAXPAYER": {"filing_status": "Dropdown_1", "tp_first": "Textbox_3", "tp_mi": "Textbox_4",
                 "tp_last": "Textbox_5", "sp_ssn": "Textbox_24", "sp_first": "Textbox_25", "sp_last": "TextboxOverride_27",
                 "street": "Textbox_50", "city": "Textbox_52", "state": "Dropdown_53", "zip": "Textbox_54"},
    "W-2": {"ts": "Dropdown_1", "employer_ein": "Textbox_4", "employer_name": "Textbox_5", "employer_name2": "Textbox_6",
            "employer_street": "Textbox_7", "employer_city": "Textbox_8", "employer_state": "Dropdown_9", "employer_zip": "Textbox_10",
            "box1": "Textbox_23", "box2": "Textbox_24", "box3": "Textbox_25", "box4": "Textbox_26", "box5": "Textbox_27",
            "box6": "Textbox_28", "box7": "Textbox_29", "box8": "Textbox_30", "box10": "Textbox_32", "box11": "Textbox_33",
            "box12a_code": "Dropdown_34", "box12a_amount": "Textbox_35", "box12b_code": "Dropdown_37", "box12b_amount": "Textbox_38",
            "box12c_code": "Dropdown_40", "box12c_amount": "Textbox_41", "box12d_code": "Dropdown_43", "box12d_amount": "Textbox_44",
            "box13_statutory": "CheckboxTextRight_46", "box13_retirement": "CheckboxTextRight_47", "box13_sick": "CheckboxTextRight_48",
            "box14": "Textbox_49", "state1": "Dropdown_57", "state1_id": "Textbox_58", "state1_wages": "Textbox_59",
            "state1_tax": "Textbox_60", "local1_wages": "Textbox_61", "local1_tax": "Textbox_62", "locality1": "Dropdown_63"},
    "1099-INT": {"ts": "Dropdown_1", "payer_tin": "Textbox_7", "payer_name": "Textbox_9", "payer_street": "Textbox_10",
                 "payer_city": "Textbox_11", "payer_state": "Dropdown_12", "payer_zip": "Textbox_13", "account": "Textbox_17",
                 "box1": "Textbox_20", "box2": "Textbox_21", "box3": "Textbox_22", "box4": "Textbox_23", "box5": "Textbox_24",
                 "box6": "Textbox_25", "box8": "Textbox_27", "box9": "Textbox_28", "box10": "Textbox_29", "box11": "TextboxAdjust_30",
                 "box12": "TextboxAdjust_31", "box13": "Textbox_32", "box17": "Textbox_36"},
    "1099-DIV": {"ts": "Dropdown_1", "payer_tin": "Textbox_6", "payer_name": "Textbox_8", "payer_street": "Textbox_9",
                 "payer_city": "Textbox_10", "payer_state": "Dropdown_11", "payer_zip": "Textbox_12", "account": "Textbox_16",
                 "box1a": "Textbox_18", "box1b": "Textbox_19", "box2a": "Textbox_20", "box2b": "Textbox_21", "box2c": "Textbox_23",
                 "box2d": "Textbox_24", "box2e": "Textbox_25", "box2f": "Textbox_26", "box3": "Textbox_27", "box4": "Textbox_28",
                 "box5": "Textbox_29", "box6": "Textbox_30", "box7": "Textbox_31", "box9": "Textbox_33", "box10": "Textbox_34",
                 "box12": "Textbox_35", "box13": "Textbox_36", "box16": "Textbox_39"},
    "1099-R": {"ts": "Dropdown_1", "payer_tin": "Textbox_5", "payer_name": "Textbox_6", "payer_name2": "Textbox_7",
               "payer_street": "Textbox_8", "payer_city": "Textbox_9", "payer_state": "Dropdown_10", "payer_zip": "Textbox_11",
               "account": "Textbox_57", "box1": "Textbox_25", "box2a": "Textbox_26", "box2b_not_determined": "CheckboxTextLeft_27",
               "box2b_total": "CheckboxTextLeft_28", "box3": "Textbox_29", "box4": "Textbox_30", "box5": "Textbox_31",
               "box6": "Textbox_32", "box7": "Dropdown_33", "box7_ira": "CheckboxTextRight_35", "box8": "Textbox_36",
               "box9b": "Textbox_39", "box14": "Textbox_43", "box16": "Textbox_46"},
    "1099-MISC": {"ts": "Dropdown_1", "payer_tin": "Textbox_6", "payer_name": "Textbox_7", "payer_name2": "Textbox_8",
                  "payer_street": "Textbox_9", "payer_city": "Textbox_10", "payer_state": "Dropdown_11", "payer_zip": "Textbox_12",
                  "account": "Textbox_25", "box1": "Textbox_26", "box2": "Textbox_27", "box3": "Textbox_28", "box4": "Textbox_31",
                  "box5": "Textbox_32", "box6": "Textbox_33", "box8": "Textbox_35", "box9": "Textbox_36", "box10": "Textbox_37",
                  "box15": "Textbox_43", "box16": "Textbox_44"},
    "1099-OID": {"ts": "Dropdown_1", "payer_tin": "Textbox_5", "payer_name": "Textbox_6", "payer_street": "Textbox_7",
                 "payer_city": "Textbox_8", "payer_state": "Dropdown_9", "payer_zip": "Textbox_10", "account": "Textbox_14",
                 "box1": "Textbox_16", "box2": "Textbox_17", "box3": "Textbox_18", "box4": "Textbox_19", "box5": "Textbox_20",
                 "box6": "Textbox_21", "box8": "Textbox_23", "box9": "Textbox_24", "box11": "Textbox_26"},
    "SSA-1099": {"ts": "Dropdown_1", "box5": "Textbox_4", "box6": "Textbox_7"},
    "1098": {"box1": "TextboxAdjust_22"},                     # Schedule A line 8a (mortgage interest reported on 1098)
    "1099-B": {"ts": "Dropdown_1", "box1a": "Textbox_6", "box1b": "Textbox_8", "box1c": "Textbox_9", "box1d": "Textbox_12",
               "box1e": "Textbox_13", "box1g": "Textbox_17", "box4": "Textbox_29"},
}


def _control_for(aid):
    if aid.startswith("Dropdown"):
        return "combo"
    if aid.startswith("Checkbox"):
        return "checkbox"
    return "edit"


for _name, _d in list(FORMS.items()) + list(DERIVED.items()):
    ids = VERIFIED_AIDS.get(_name, {})
    _d["drake_verified"] = bool(ids)
    for _f in _d["fields"]:
        _f["ref"] = (_f["key"] in REFERENCE_KEYS and _name in FORMS) or (_name == "SSA-1099" and _f["key"] in ("box3", "box4"))
        _f["aid"] = ids.get(_f["key"])
        if _f["aid"]:
            _f["control"] = _control_for(_f["aid"])


def form_def(ftype):
    return FORMS.get(ftype) or DERIVED.get(ftype)


def public_catalog():
    """JSON-safe catalog for the browser (no regexes)."""
    out = {}
    for name, d in {**FORMS, **DERIVED}.items():
        out[name] = {"name": d["name"], "module": d["module"], "screen": d["screen"], "screen_name": d["screen_name"],
                     "informational": bool(d.get("informational")), "drake_verified": bool(d.get("drake_verified")),
                     "fields": [{k: v for k, v in f.items() if k not in ("aliases", "row", "col")} for f in d["fields"]
                                if f["mode"] != "block"]}
    return out


_compiled = {}


def compiled(pattern):
    c = _compiled.get(pattern)
    if c is None:
        c = _compiled[pattern] = re.compile(pattern, re.I)
    return c


def clone_fields(ftype):
    d = form_def(ftype)
    return copy.deepcopy(d["fields"]) if d else []
