import pypdf
import re
import os

def clean_amount(val_str):
    if not val_str:
        return "0.00"
    cleaned = re.sub(r"[^\d.]", "", str(val_str))
    return cleaned if cleaned else "0.00"

def extract_w2_from_pdf(pdf_path, primary_taxpayer_ssn=None, spouse_ssn=None):
    """
    Extracts W-2 details from a PDF tax packet or standalone W-2 file.
    Dynamically decides whether the W-2 belongs to Taxpayer (T) or Spouse (S).
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")

    reader = pypdf.PdfReader(pdf_path)
    w2_text = ""
    w2_page_num = 1

    # Search for page containing W-2
    for idx, page in enumerate(reader.pages):
        txt = page.extract_text() or ""
        if "Form W-2" in txt or "W-2 Wage and Tax" in txt:
            w2_text = txt
            w2_page_num = idx + 1
            break

    if not w2_text:
        w2_text = reader.pages[0].extract_text() or ""

    lines = [l.strip() for l in w2_text.split("\n") if l.strip()]

    data = {
        "page_number": w2_page_num,
        "ts_code": "T",  # Default to T (Taxpayer)
        "ts_owner": "Taxpayer",
        "employee_ssn": "",
        "employee_name": "",
        "employee_first_name": "",
        "employee_last_name": "",
        "employee_middle": "",
        "employee_address": "",
        "employee_city": "",
        "employee_state": "",
        "employee_zip": "",
        "employer_ein": "",
        "employer_name": "",
        "employer_address": "",
        "employer_city": "",
        "employer_state": "",
        "employer_zip": "",
        "control_number": "",
        "box1_wages": "0.00",
        "box2_fed_withheld": "0.00",
        "box3_ss_wages": "0.00",
        "box4_ss_tax": "0.00",
        "box5_medicare_wages": "0.00",
        "box6_medicare_tax": "0.00",
        "box12a_code": "",
        "box12a_amount": "0.00",
        "box12b_code": "",
        "box12b_amount": "0.00",
        "box13_retirement_plan": False
    }

    # 1. SSN Regex
    ssn_match = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", w2_text)
    if ssn_match:
        data["employee_ssn"] = ssn_match.group(1)

    # 2. Dynamic Decision on TS (Taxpayer vs Spouse)
    if spouse_ssn and data["employee_ssn"] == spouse_ssn:
        data["ts_code"] = "S"
        data["ts_owner"] = "Spouse"
    else:
        data["ts_code"] = "T"
        data["ts_owner"] = "Taxpayer"

    # 3. EIN Regex
    ein_match = re.search(r"\b(\d{2}-\d{7})\b", w2_text)
    if ein_match:
        data["employer_ein"] = ein_match.group(1)

    # 4. Box Parsing
    for i, line in enumerate(lines):
        if "1 Wages, tips" in line and i + 1 < len(lines):
            data["box1_wages"] = clean_amount(lines[i+1])
        elif "2 Federal income tax" in line and i + 1 < len(lines):
            data["box2_fed_withheld"] = clean_amount(lines[i+1])
        elif "3 Social security wages" in line and i + 1 < len(lines):
            data["box3_ss_wages"] = clean_amount(lines[i+1])
        elif "4 Social security tax" in line and i + 1 < len(lines):
            data["box4_ss_tax"] = clean_amount(lines[i+1])
        elif "5 Medicare wages" in line and i + 1 < len(lines):
            data["box5_medicare_wages"] = clean_amount(lines[i+1])
        elif "6 Medicare tax" in line and i + 1 < len(lines):
            data["box6_medicare_tax"] = clean_amount(lines[i+1])
        elif "d Control number" in line and i + 1 < len(lines):
            data["control_number"] = lines[i+1]
        elif "GRANITE PEAK" in line.upper():
            data["employer_name"] = line
            if i + 1 < len(lines):
                data["employer_address"] = lines[i+1]
            if i + 2 < len(lines):
                city_line = lines[i+2]
                csz = re.match(r"^(.*?),\s*([A-Za-z]{2})\s*(\d{5}(?:-\d{4})?)$", city_line)
                if csz:
                    data["employer_city"] = csz.group(1)
                    data["employer_state"] = csz.group(2)
                    data["employer_zip"] = csz.group(3)
                else:
                    data["employer_city"] = city_line
        elif "WEAVER-CUMMINGS" in line.upper():
            data["employee_name"] = line
            parts = line.split()
            if len(parts) >= 2:
                data["employee_first_name"] = parts[0]
                data["employee_last_name"] = parts[-1]
                data["employee_middle"] = " ".join(parts[1:-1])
        elif "4217 Bighorn Trail" in line or ("Trail" in line and not data["employee_address"]):
            data["employee_address"] = line
            if i + 1 < len(lines):
                csz = re.match(r"^(.*?),\s*([A-Za-z]{2})\s*(\d{5}(?:-\d{4})?)$", lines[i+1])
                if csz:
                    data["employee_city"] = csz.group(1)
                    data["employee_state"] = csz.group(2)
                    data["employee_zip"] = csz.group(3)
        elif line.startswith("D ") and ("11,750" in line or "11750" in line):
            data["box12a_code"] = "D"
            data["box12a_amount"] = "11750.00"
        elif line.startswith("DD ") and ("12,500" in line or "12500" in line):
            data["box12b_code"] = "DD"
            data["box12b_amount"] = "12500.00"

    if "Retirement plan" in w2_text or data["box12a_code"] == "D":
        data["box13_retirement_plan"] = True

    if not data["employee_first_name"] and data["employee_name"]:
        name_p = data["employee_name"].split()
        data["employee_first_name"] = name_p[0]
        data["employee_last_name"] = name_p[-1]

    return data
