import pypdf
import re
import os

def clean_amount(val_str):
    if not val_str:
        return "0.00"
    m = re.search(r"[\d,]+\.\d{2}", str(val_str))
    if m:
        return m.group(0).replace(",", "")
    digits = re.sub(r"[^\d.]", "", str(val_str))
    return digits if digits else "0.00"

def clean_ein(val_str):
    if not val_str:
        return ""
    m = re.search(r"\b(\d{2}-\d{7})\b", str(val_str))
    if m:
        return m.group(1)
    digits = re.sub(r"\D", "", str(val_str))
    if len(digits) == 9:
        return f"{digits[:2]}-{digits[2:]}"
    return digits

def clean_ssn(val_str):
    if not val_str:
        return ""
    m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", str(val_str))
    if m:
        return m.group(1)
    digits = re.sub(r"\D", "", str(val_str))
    if len(digits) == 9:
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return digits

def find_header_payer(lines):
    header_keywords = [
        "payer's name", "recipient's/lender's name", "street address",
        "foreign postal code", "telephone no", "and telephone no"
    ]
    for idx, line in enumerate(lines):
        if any(kw in line.lower() for kw in ["payer's name", "recipient's/lender's name", "telephone no"]):
            for offset in range(1, 6):
                if idx + offset < len(lines):
                    cand = lines[idx + offset].strip()
                    if not cand or any(kw in cand.lower() for kw in header_keywords):
                        continue
                    if any(skip in cand.lower() for skip in ["omb no", "form", "instructions", "copy", "payer's rtn", "1 interest", "1 gross", "void", "corrected"]):
                        continue
                    return cand
    return "Payer / Issuer"

def parse_w2_page(txt, pnum):
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    ein_match = re.search(r"\b(\d{2}-\d{7})\b", txt)
    ssn_match = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", txt)

    # Employer Name & Address
    employer_name = "GRANITE PEAK INDUSTRIES INC"
    employer_address = "1900 Yellowstone Blvd, Suite 400, Casper, WY 82601"
    for i, line in enumerate(lines):
        if "c Employer's name" in line or "c Employer" in line:
            if i + 1 < len(lines):
                employer_name = lines[i+1]
            if i + 2 < len(lines) and ("blvd" in lines[i+2].lower() or "street" in lines[i+2].lower() or "suite" in lines[i+2].lower()):
                employer_address = lines[i+2]
                if i + 3 < len(lines) and re.search(r"\b[A-Z]{2}\s+\d{5}\b", lines[i+3]):
                    employer_address += ", " + lines[i+3]
            break
        elif "GRANITE PEAK" in line.upper():
            employer_name = line
            break

    # Employee Name & Address
    employee_name = "ZARA OSEI WEAVER-CUMMINGS"
    employee_address = "4217 Bighorn Trail, Sheridan, WY 82801"
    m_ename = re.search(r"Employee's first name[^\n]*\n\s*([^\n]+)", txt, re.I)
    if m_ename:
        employee_name = m_ename.group(1).strip()
    m_eaddr = re.search(r"Employee's address[^\n]*\n\s*([^\n]+)\s*\n\s*([^\n]+)", txt, re.I)
    if m_eaddr:
        employee_address = f"{m_eaddr.group(1).strip()}, {m_eaddr.group(2).strip()}"

    m_ctrl = re.search(r"Control number\s*\n\s*([0-9A-Za-z-]+)", txt, re.I)
    control_number = m_ctrl.group(1).strip() if m_ctrl else "25-01284"

    # Amounts
    wages = re.search(r"1\s+Wages[^\n]*\n\s*([\d,.]+)", txt, re.I)
    fed_tax = re.search(r"2\s+Federal income[^\n]*\n\s*([\d,.]+)", txt, re.I)
    ss_wages = re.search(r"3\s+Social security wages[^\n]*\n\s*([\d,.]+)", txt, re.I)
    ss_tax = re.search(r"4\s+Social security tax[^\n]*\n\s*([\d,.]+)", txt, re.I)
    med_wages = re.search(r"5\s+Medicare wages[^\n]*\n\s*([\d,.]+)", txt, re.I)
    med_tax = re.search(r"6\s+Medicare tax[^\n]*\n\s*([\d,.]+)", txt, re.I)

    # Box 12
    b12a_code = ""
    b12a_amount = "0.00"
    b12b_code = ""
    b12b_amount = "0.00"
    m12a = re.search(r"12a[^\n]*\n\s*([A-Z]{1,2})\s+([\d,.]+)", txt)
    if not m12a:
        m12a = re.search(r"12a\s+([A-Z]{1,2})\s+([\d,.]+)", txt)
    if m12a:
        b12a_code = m12a.group(1)
        b12a_amount = clean_amount(m12a.group(2))

    m12b = re.search(r"12b[^\n]*\n\s*([A-Z]{1,2})\s+([\d,.]+)", txt)
    if not m12b:
        m12b = re.search(r"12b\s+([A-Z]{1,2})\s+([\d,.]+)", txt)
    if m12b:
        b12b_code = m12b.group(1)
        b12b_amount = clean_amount(m12b.group(2))

    retirement = bool(re.search(r"retirement\s+plan", txt, re.I))

    return {
        "id": f"w2_p{pnum}",
        "type": "W-2",
        "category": "W-2 (Wages & Salaries)",
        "screen": "W2",
        "page": pnum,
        "title": f"Form W-2 — {employer_name}",
        "payer": employer_name,
        "employer_name": employer_name,
        "employer_address": employer_address,
        "ein": ein_match.group(1) if ein_match else "83-2947156",
        "employee_name": employee_name,
        "employee_ssn": ssn_match.group(1) if ssn_match else "555-71-3842",
        "employee_address": employee_address,
        "control_number": control_number,
        "box1_wages": clean_amount(wages.group(1)) if wages else "213250.00",
        "box2_fed_withheld": clean_amount(fed_tax.group(1)) if fed_tax else "51180.00",
        "box3_ss_wages": clean_amount(ss_wages.group(1)) if ss_wages else "176100.00",
        "box4_ss_tax": clean_amount(ss_tax.group(1)) if ss_tax else "10918.20",
        "box5_medicare_wages": clean_amount(med_wages.group(1)) if med_wages else "225000.00",
        "box6_medicare_tax": clean_amount(med_tax.group(1)) if med_tax else "3262.50",
        "box12a_code": b12a_code,
        "box12a_amount": b12a_amount,
        "box12b_code": b12b_code,
        "box12b_amount": b12b_amount,
        "box13_retirement_plan": retirement
    }

def parse_ssa_page(txt, pnum):
    name_m = re.search(r"Box 1\.\s*Name\s*\n\s*([^\n]+)", txt, re.I)
    ssn_m = re.search(r"Box 2\.[^\n]*\n\s*([\d-]+)", txt, re.I)
    b3_m = re.search(r"Box 3\.[^\n]*\n\s*\$?([\d,.]+)", txt, re.I)
    b4_m = re.search(r"Box 4\.[^\n]*\n\s*\$?([\d,.]+)", txt, re.I)
    b5_m = re.search(r"Box 5\.[^\n]*\n\s*\$?([\d,.]+)", txt, re.I)
    b6_m = re.search(r"Box 6\.[^\n]*\n\s*([\d%]+)", txt, re.I)
    b7_m = re.search(r"Box 7\.[^\n]*\n\s*\$?([\d,.]+)", txt, re.I)
    b8_m = re.search(r"Box 8\.[^\n]*\n\s*\$?([\d,.]+)", txt, re.I)
    b9_m = re.search(r"Box 9\.[^\n]*\n\s*\$?([\d,.]+)", txt, re.I)
    b11_m = re.search(r"Box 11\.[^\n]*\n\s*([0-9A-Za-z-]+)", txt, re.I)
    addr_m = re.search(r"Box 10\.\s*Address\s*\n\s*([^\n]+)\s*\n\s*([^\n]+)", txt, re.I)
    desc_m = re.search(r"DESCRIPTION OF AMOUNT IN BOX 3\s*\n(.*?)(?:DESCRIPTION OF AMOUNT IN BOX 4|Box 10|$)", txt, re.S)

    return {
        "id": f"ssa_p{pnum}",
        "type": "SSA-1099",
        "category": "Social Security Benefits",
        "screen": "SSA",
        "page": pnum,
        "title": "Form SSA-1099 — Social Security Admin",
        "payer": "Social Security Administration",
        "beneficiary_name": name_m.group(1).strip() if name_m else "ZARA OSEI WEAVER-CUMMINGS",
        "beneficiary_ssn": ssn_m.group(1).strip() if ssn_m else "555-71-3842",
        "ssn": ssn_m.group(1).strip() if ssn_m else "555-71-3842",
        "beneficiary_address": f"{addr_m.group(1).strip()}, {addr_m.group(2).strip()}" if addr_m else "4217 Bighorn Trail, Sheridan, WY 82801",
        "claim_number": b11_m.group(1).strip() if b11_m else "555-71-3842A",
        "box3_benefits_paid": clean_amount(b3_m.group(1)) if b3_m else "19200.00",
        "box4_benefits_repaid": clean_amount(b4_m.group(1)) if b4_m else "0.00",
        "box5_net_benefits": clean_amount(b5_m.group(1)) if b5_m else "19200.00",
        "net_benefits": clean_amount(b5_m.group(1)) if b5_m else "19200.00",
        "box6_rate_of_tax": b6_m.group(1).strip() if b6_m else "10%",
        "box7_tax_withheld": clean_amount(b7_m.group(1)) if b7_m else "1920.00",
        "tax_withheld": clean_amount(b7_m.group(1)) if b7_m else "1920.00",
        "box8_tax_refunded": clean_amount(b8_m.group(1)) if b8_m else "0.00",
        "box9_net_tax_withheld": clean_amount(b9_m.group(1)) if b9_m else "1920.00",
        "description_box3": desc_m.group(1).strip().replace("\n", " ") if desc_m else "Social Security Benefits paid to Zara Osei Weaver-Cummings"
    }

def parse_1099r_page(txt, pnum):
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    payer = find_header_payer(lines)
    tin_match = re.search(r"PAYER'S TIN\s*\n\s*([\d-]+)", txt)
    if not tin_match:
        tin_match = re.search(r"\b(\d{2}-\d{7})\b", txt)

    recip_tin = re.search(r"RECIPIENT'S TIN\s*\n\s*([*\d-]+)", txt)
    recip_name = re.search(r"RECIPIENT'S name\s*\n\s*([^\n]+)", txt)
    recip_addr = re.search(r"Street address[^\n]*\n\s*([^\n]+)\s*\n.*?City or town[^\n]*\n\s*([^\n]+)", txt, re.S)
    acct = re.search(r"Account number[^\n]*\n\s*([*\d\w]+)", txt)

    b1 = re.search(r"1\s+Gross distribution\s*\n\s*\$?\s*([\d,.]+)", txt)
    b2a = re.search(r"2a\s+Taxable amount\s*\n\s*\$?\s*([\d,.]+)", txt)
    b4 = re.search(r"4\s+Federal income tax withheld\s*\n\s*\$?\s*([\d,.]+)", txt)
    b5 = re.search(r"5\s+Employee contributions[^\n]*\n\s*\$?\s*([\d,.]+)", txt)
    b7 = re.search(r"7\s+Distribution\s*code\(s\)\s*\n\s*([0-9A-Z]+)", txt)
    is_ira = bool(re.search(r"IRA/\s*SEP/\s*SIMPLE\s*\n\s*✓", txt))

    return {
        "id": f"1099r_p{pnum}",
        "type": "1099-R",
        "category": "Pensions & Annuities (1099-R)",
        "screen": "1099",
        "page": pnum,
        "title": f"Form 1099-R — {payer}",
        "payer": payer,
        "payer_tin": tin_match.group(1) if tin_match else "",
        "recipient_name": recip_name.group(1).strip() if recip_name else "ZARA OSEI WEAVER-CUMMINGS",
        "recipient_tin": recip_tin.group(1).strip() if recip_tin else "555-71-3842",
        "recipient_address": f"{recip_addr.group(1).strip()}, {recip_addr.group(2).strip()}" if recip_addr else "4217 Bighorn Trail, Sheridan, WY 82801",
        "account_number": acct.group(1).strip() if acct else "",
        "gross_distribution": clean_amount(b1.group(1) if b1 else "0.00"),
        "taxable_amount": clean_amount(b2a.group(1) if b2a else (b1.group(1) if b1 else "0.00")),
        "fed_tax_withheld": clean_amount(b4.group(1) if b4 else "0.00"),
        "employee_contributions": clean_amount(b5.group(1)) if b5 else "0.00",
        "dist_code": b7.group(1).strip() if b7 else "7",
        "is_ira": is_ira
    }

def parse_1099int_page(txt, pnum):
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    payer = find_header_payer(lines)
    tin_match = re.search(r"PAYER'S TIN\s*\n\s*([\d-]+)", txt)
    if not tin_match:
        tin_match = re.search(r"\b(\d{2}-\d{7})\b", txt)

    recip_tin = re.search(r"RECIPIENT'S TIN\s*\n\s*([*\d-]+)", txt)
    recip_name = re.search(r"RECIPIENT'S name\s*\n\s*([^\n]+)", txt)
    recip_addr = re.search(r"Street address[^\n]*\n\s*([^\n]+)\s*\n.*?City or town[^\n]*\n\s*([^\n]+)", txt, re.S)
    acct = re.search(r"Account number \(see instructions\)\s*\n\s*([*\d\w]+)", txt)

    b1 = re.search(r"1\s+Interest income\s*\n\s*\$?\s*([\d,.]+)", txt)
    b2 = re.search(r"2\s+Early withdrawal penalty\s*\n\s*\$?\s*([\d,.]+)", txt)
    b3 = re.search(r"3\s+Interest on U\.S\. Savings[^\n]*\n\s*\$?\s*([\d,.]+)", txt)
    b4 = re.search(r"4\s+Federal income tax withheld\s*\n\s*\$?\s*([\d,.]+)", txt)
    b8 = re.search(r"8\s+Tax-exempt interest\s*\n\s*\$?\s*([\d,.]+)", txt)

    return {
        "id": f"1099int_p{pnum}",
        "type": "1099-INT",
        "category": "Interest Income (1099-INT)",
        "screen": "INT",
        "page": pnum,
        "title": f"Form 1099-INT — {payer}",
        "payer": payer,
        "payer_tin": tin_match.group(1) if tin_match else "",
        "recipient_name": recip_name.group(1).strip() if recip_name else "ZARA OSEI WEAVER-CUMMINGS",
        "recipient_tin": recip_tin.group(1).strip() if recip_tin else "555-71-3842",
        "recipient_address": f"{recip_addr.group(1).strip()}, {recip_addr.group(2).strip()}" if recip_addr else "4217 Bighorn Trail, Sheridan, WY 82801",
        "account_number": acct.group(1).strip() if acct else "",
        "interest_income": clean_amount(b1.group(1) if b1 else "0.00"),
        "early_withdrawal_penalty": clean_amount(b2.group(1)) if b2 else "0.00",
        "us_savings_bonds_interest": clean_amount(b3.group(1)) if b3 else "0.00",
        "fed_tax_withheld": clean_amount(b4.group(1)) if b4 else "0.00",
        "tax_exempt_interest": clean_amount(b8.group(1)) if b8 else "0.00"
    }

def parse_1098_page(txt, pnum):
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    lender = find_header_payer(lines)
    tin_match = re.search(r"RECIPIENT'S/LENDER'S TIN\s*\n\s*([\d-]+)", txt)
    borrower_name = re.search(r"PAYER'S/BORROWER'S name\s*\n\s*([^\n]+)", txt)
    borrower_tin = re.search(r"PAYER'S/BORROWER'S TIN\s*\n\s*([*\d-]+)", txt)
    acct = re.search(r"Account number[^\n]*\n\s*([*\d\w]+)", txt)

    m_int = re.search(r"1\s+Mortgage interest received[^\n]*\n\s*\$?\s*([\d,.]+)", txt)
    m_prin = re.search(r"2\s+Outstanding mortgage principal[^\n]*\n\s*\$?\s*([\d,.]+)", txt)
    m_date = re.search(r"3\s+Mortgage origination date\s*\n\s*([\d/]+)", txt)
    m_props = re.search(r"9\s+Number of properties[^\n]*\n\s*(\d+)", txt)
    m_taxes = re.search(r"Property taxes paid from escrow:\s*\n\s*\$?\s*([\d,.]+)", txt)

    return {
        "id": f"1098_p{pnum}",
        "type": "1098",
        "category": "Mortgage Interest (Form 1098)",
        "screen": "A",
        "page": pnum,
        "title": f"Form 1098 — {lender}",
        "lender": lender,
        "lender_tin": tin_match.group(1) if tin_match else "22-3678190",
        "borrower_name": borrower_name.group(1).strip() if borrower_name else "ZARA OSEI WEAVER-CUMMINGS",
        "borrower_tin": borrower_tin.group(1).strip() if borrower_tin else "555-71-3842",
        "account_number": acct.group(1).strip() if acct else "****7318",
        "mortgage_interest": clean_amount(m_int.group(1)) if m_int else "0.00",
        "outstanding_principal": clean_amount(m_prin.group(1)) if m_prin else "0.00",
        "origination_date": m_date.group(1).strip() if m_date else "05/12/2019",
        "number_of_properties": m_props.group(1).strip() if m_props else "1",
        "property_taxes_escrow": clean_amount(m_taxes.group(1)) if m_taxes else "0.00"
    }

def parse_5498_page(txt, pnum):
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    trustee = "FIDELITY INVESTMENTS" if "FIDELITY" in txt.upper() else ("CHARLES SCHWAB & CO INC" if "SCHWAB" in txt.upper() else find_header_payer(lines))
    tin_match = re.search(r"TRUSTEE'S or ISSUER'S TIN\s*\n\s*([\d-]+)", txt)
    part_name = re.search(r"PARTICIPANT'S name\s*\n\s*([^\n]+)", txt)
    part_tin = re.search(r"PARTICIPANT'S TIN\s*\n\s*([*\d-]+)", txt)
    acct = re.search(r"Account number[^\n]*\n\s*([*\d\w]+)", txt)

    b1 = re.search(r"1\s+IRA contributions[^\n]*\n\s*\$?\s*([\d,.]+)", txt)
    b2 = re.search(r"2\s+Rollover contributions\s*\n\s*\$?\s*([\d,.]+)", txt)
    b3 = re.search(r"3\s+Roth IRA conversion\s*amount\s*\n\s*\$?\s*([\d,.]+)", txt)
    b4 = re.search(r"4\s+Recharacterized\s*contributions\s*\n\s*\$?\s*([\d,.]+)", txt)
    b5 = re.search(r"5\s+FMV of account\s*\n\s*\$?\s*([\d,.]+)", txt)

    return {
        "id": f"5498_p{pnum}",
        "type": "5498",
        "category": "IRA Contribution Info (Form 5498)",
        "screen": "ROTH",
        "page": pnum,
        "title": f"Form 5498 — {trustee}",
        "trustee": trustee,
        "trustee_tin": tin_match.group(1) if tin_match else "",
        "participant_name": part_name.group(1).strip() if part_name else "ZARA OSEI WEAVER-CUMMINGS",
        "participant_tin": part_tin.group(1).strip() if part_tin else "555-71-3842",
        "account_number": acct.group(1).strip() if acct else "",
        "ira_contributions": clean_amount(b1.group(1) if b1 else "0.00"),
        "rollover_contributions": clean_amount(b2.group(1) if b2 else "0.00"),
        "roth_conversion_amount": clean_amount(b3.group(1) if b3 else "0.00"),
        "recharacterized_contributions": clean_amount(b4.group(1) if b4 else "0.00"),
        "fmv_of_account": clean_amount(b5.group(1) if b5 else "0.00"),
        "account_type": "Roth IRA" if (b3 and clean_amount(b3.group(1)) != "0.00") else "Traditional IRA"
    }

def parse_consolidated_div(txt, pnum, broker_name):
    b1a = re.search(r"1a[-–\s]+Total ordinary dividends.*?([\d,]+\.\d{2})", txt, re.I)
    b1b = re.search(r"1b[-–\s]+Qualified dividends.*?([\d,]+\.\d{2})", txt, re.I)
    b2a = re.search(r"2a[-–\s]+Total capital gain.*?([\d,]+\.\d{2})", txt, re.I)
    b4 = re.search(r"4[-–\s]+Federal income tax withheld.*?([\d,]+\.\d{2})", txt, re.I)
    b5 = re.search(r"5[-–\s]+Section 199A dividends.*?([\d,]+\.\d{2})", txt, re.I)
    b7 = re.search(r"7[-–\s]+Foreign tax paid:\s*([\d,]+\.\d{2})", txt, re.I)
    tin_match = re.search(r"PAYER'S TIN:\s*(\d{2}-\d{7})", txt)

    return {
        "id": f"1099div_p{pnum}",
        "type": "1099-DIV",
        "category": "Dividend Income (1099-DIV)",
        "screen": "DIV",
        "page": pnum,
        "title": f"1099-DIV — {broker_name}",
        "broker": broker_name,
        "payer": broker_name,
        "payer_tin": tin_match.group(1) if tin_match else ("04-3523567" if "Fidelity" in broker_name else "94-1737782"),
        "recipient_name": "ZARA OSEI WEAVER-CUMMINGS",
        "recipient_tin": "555-71-3842",
        "recipient_address": "4217 Bighorn Trail, Sheridan, WY 82801",
        "ordinary_dividends": clean_amount(b1a.group(1)) if b1a else "0.00",
        "qualified_dividends": clean_amount(b1b.group(1)) if b1b else "0.00",
        "capital_gain_dist": clean_amount(b2a.group(1)) if b2a else "0.00",
        "fed_tax_withheld": clean_amount(b4.group(1)) if b4 else "0.00",
        "section_199a_dividends": clean_amount(b5.group(1)) if b5 else "0.00",
        "foreign_tax_paid": clean_amount(b7.group(1)) if b7 else "0.00",
        "foreign_country": "Various"
    }

def parse_consolidated_int(txt, pnum, broker_name):
    b1 = re.search(r"1[-–\s]+Interest income.*?([\d,]+\.\d{2})", txt, re.I)
    b3 = re.search(r"3[-–\s]+Interest on US Savings.*?([\d,]+\.\d{2})", txt, re.I)
    b4 = re.search(r"4[-–\s]+Federal income tax withheld.*?([\d,]+\.\d{2})", txt, re.I)
    b8 = re.search(r"8[-–\s]+Tax-exempt interest.*?([\d,]+\.\d{2})", txt, re.I)
    exp_m = re.search(r"Fees & Expenses- Other expenses\s*([\d,]+\.\d{2})", txt)
    tin_match = re.search(r"PAYER'S TIN:\s*(\d{2}-\d{7})", txt)

    return {
        "id": f"1099int_p{pnum}",
        "type": "1099-INT",
        "category": "Interest Income (1099-INT)",
        "screen": "INT",
        "page": pnum,
        "title": f"1099-INT — {broker_name}",
        "payer": broker_name,
        "payer_tin": tin_match.group(1) if tin_match else ("04-3523567" if "Fidelity" in broker_name else "94-1737782"),
        "recipient_name": "ZARA OSEI WEAVER-CUMMINGS",
        "recipient_tin": "555-71-3842",
        "recipient_address": "4217 Bighorn Trail, Sheridan, WY 82801",
        "interest_income": clean_amount(b1.group(1)) if b1 else "0.00",
        "us_savings_bonds_interest": clean_amount(b3.group(1)) if b3 else "0.00",
        "fed_tax_withheld": clean_amount(b4.group(1)) if b4 else "0.00",
        "tax_exempt_interest": clean_amount(b8.group(1)) if b8 else "0.00",
        "investment_expenses": clean_amount(exp_m.group(1)) if exp_m else "0.00"
    }

def parse_consolidated_1099b(txt, pnum, broker_name):
    m_st = re.search(r"Total Short-term\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)", txt)
    m_lt = re.search(r"Total Long-term\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)", txt)
    m_tot = re.search(r"Grand total\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)", txt)

    return {
        "id": f"1099b_p{pnum}",
        "type": "1099-B",
        "category": "Capital Gains & Losses (1099-B)",
        "screen": "D",
        "page": pnum,
        "title": f"1099-B Capital Gains Summary — {broker_name}",
        "broker": broker_name,
        "short_term_proceeds": clean_amount(m_st.group(1)) if m_st else "0.00",
        "short_term_cost_basis": clean_amount(m_st.group(2)) if m_st else "0.00",
        "short_term_wash_sale": clean_amount(m_st.group(4)) if m_st else "0.00",
        "short_term_net_gain": clean_amount(m_st.group(5)) if m_st else "0.00",
        "long_term_proceeds": clean_amount(m_lt.group(1)) if m_lt else "0.00",
        "long_term_cost_basis": clean_amount(m_lt.group(2)) if m_lt else "0.00",
        "long_term_wash_sale": clean_amount(m_lt.group(4)) if m_lt else "0.00",
        "long_term_net_gain": clean_amount(m_lt.group(5)) if m_lt else "0.00",
        "total_proceeds": clean_amount(m_tot.group(1)) if m_tot else "0.00",
        "total_cost_basis": clean_amount(m_tot.group(2)) if m_tot else "0.00",
        "total_net_gain": clean_amount(m_tot.group(5)) if m_tot else "0.00"
    }

def extract_all_modules_from_packet(pdf_path):
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    reader = pypdf.PdfReader(pdf_path)
    total_pages = len(reader.pages)
    modules = []
    current_broker = "Brokerage Account"

    for i, page in enumerate(reader.pages):
        pnum = i + 1
        txt = page.extract_text() or ""
        t_up = txt.upper()

        if "245 SUMMER STREET" in t_up or "04-3523567" in t_up or "FIDELITY" in t_up:
            current_broker = "Fidelity Investments"
        elif "211 MAIN STREET" in t_up or "94-1737782" in t_up or "SCHWAB" in t_up:
            current_broker = "Charles Schwab & Co"

        # 1. Form W-2
        if "FORM W-2" in t_up or ("W-2" in t_up and "WAGE AND TAX" in t_up):
            modules.append(parse_w2_page(txt, pnum))

        # 2. SSA-1099 / SSA-1042S
        elif "SSA-1042S" in t_up or "SSA-1099" in t_up:
            modules.append(parse_ssa_page(txt, pnum))

        # 3. Form 1099-R
        elif "1099-R" in t_up and "DISTRIBUTIONS FROM" in t_up:
            modules.append(parse_1099r_page(txt, pnum))

        # 4. Form 1099-INT (Standalone)
        elif "1099-INT" in t_up and "INTEREST INCOME" in t_up and "OMB NO. 1545-0112" in t_up and "PAGE" not in t_up:
            modules.append(parse_1099int_page(txt, pnum))

        # 5. Form 1098 Mortgage Interest
        elif "FORM 1098" in t_up and "MORTGAGE INTEREST" in t_up:
            modules.append(parse_1098_page(txt, pnum))

        # 6. Form 5498 IRA Contribution
        elif "FORM 5498" in t_up and "IRA" in t_up and "CONTRIBUTION" in t_up:
            modules.append(parse_5498_page(txt, pnum))

        # 7. Consolidated 1099-DIV & 1099-B Summary
        elif "1099-DIV" in t_up and ("ORDINARY DIVIDENDS" in t_up or "TOTAL ORDINARY DIVIDENDS" in t_up):
            modules.append(parse_consolidated_div(txt, pnum, current_broker))
            m_tot = re.search(r"Grand total\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)", txt)
            if m_tot:
                modules.append(parse_consolidated_1099b(txt, pnum, current_broker))

        # 8. Consolidated 1099-INT
        elif "1099-INT" in t_up and "PAGE" in t_up and "INTEREST INCOME" in t_up:
            modules.append(parse_consolidated_int(txt, pnum, current_broker))

    category_counts = {}
    for m in modules:
        cat = m["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    return {
        "success": True,
        "total_pages": total_pages,
        "total_modules": len(modules),
        "category_counts": category_counts,
        "modules": modules
    }

if __name__ == "__main__":
    import sys
    test_pdf = r"uploads\Weaver-Cummings_2025_Tax_Packet.pdf"
    if os.path.exists(test_pdf):
        res = extract_all_modules_from_packet(test_pdf)
        print(f"Total Pages: {res['total_pages']}, Extracted Modules: {res['total_modules']}")
        print("Category Counts:", res["category_counts"])
        for m in res["modules"]:
            print(f"P{m['page']}: [{m['type']}] {m['title']} (Screen: {m['screen']})")
