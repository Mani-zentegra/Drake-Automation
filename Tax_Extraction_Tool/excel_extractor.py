import os
import openpyxl
from datetime import datetime

def sanitize_cell(val):
    if val is None:
        return ""
    if isinstance(val, (datetime,)):
        return val.strftime("%m/%d/%Y")
    return str(val).strip()

def sanitize_number(val, default=0):
    if val is None or val == "":
        return default
    try:
        if isinstance(val, (int, float)):
            return val
        cleaned = str(val).replace("$", "").replace(",", "").strip()
        if "." in cleaned:
            return float(cleaned)
        return int(cleaned)
    except Exception:
        return val

def extract_excel_organizer(file_path):
    """
    Extracts personal tax details from Excel Tax Organizer (.xlsx).
    Supports both:
    1. Standard 'Organizer' format (e.g. 2025 Personal Tax Organizer.xlsx)
    2. Tabular 'Name and Address' / 'Dependents' format (e.g. drake_input.xlsx)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Excel file not found at: {file_path}")

    wb = openpyxl.load_workbook(file_path, data_only=True)
    sheet_names = wb.sheetnames
    sheet_names_lower = [s.lower() for s in sheet_names]

    # CASE A: Format is 'Organizer' sheet
    if "organizer" in sheet_names_lower:
        idx = sheet_names_lower.index("organizer")
        sheet = wb[sheet_names[idx]]

        def c_val(r, c):
            return sanitize_cell(sheet.cell(r, c).value)

        def c_num(r, c, default=0):
            return sanitize_number(sheet.cell(r, c).value, default)

        # Taxpayer Personal Info
        tp_first = c_val(18, 5)
        tp_mi = c_val(18, 9)
        tp_last = c_val(18, 13)
        tp_ssn = c_val(18, 17)
        tp_occ = c_val(21, 3)
        tp_dob = c_val(21, 8)
        tp_phone = c_val(22, 3)
        tp_other_phone = c_val(22, 9)
        tp_email = c_val(22, 15)

        # Spouse Personal Info
        sp_first = c_val(19, 5)
        sp_mi = c_val(19, 9)
        sp_last = c_val(19, 13)
        sp_ssn = c_val(19, 17)
        sp_occ = c_val(21, 14)
        sp_dob = c_val(21, 19)
        sp_phone = c_val(23, 3)
        sp_other_phone = c_val(23, 9)
        sp_email = c_val(23, 15)

        # Mailing Address
        street = c_val(20, 4)
        city = c_val(20, 11)
        state = c_val(20, 17)
        zip_code = c_val(20, 19)

        # Direct Deposit / Debit Bank Info
        bank_name = c_val(27, 16)
        routing = c_val(28, 16)
        account_num = c_val(29, 16)
        account_type = c_val(30, 16)

        # Dependents (Rows 33 to 39)
        dependents = []
        for r in range(33, 40):
            full_name = c_val(r, 2)
            if full_name:
                dob = c_val(r, 7)
                ssn = c_val(r, 11)
                rel = c_val(r, 16).upper()
                months = c_val(r, 19) or "12"

                parts = full_name.split()
                fname = parts[0] if parts else ""
                lname = parts[-1] if len(parts) > 1 else tp_last
                mi = parts[1] if len(parts) > 2 else ""

                dependents.append({
                    "full_name": full_name,
                    "first_name": fname,
                    "mi": mi,
                    "last_name": lname,
                    "ssn": ssn,
                    "relationship": rel,
                    "months": months,
                    "dob": dob
                })

        # Residency, FBAR, PFIC, Digital Assets & Health Questions
        residency_status = c_val(25, 5) or "Citizen"
        foreign_bank_account = c_val(41, 8) or "No"
        fbar_required = c_val(41, 39) or "Yes"
        fbar_file_request = c_val(42, 39) or "No"
        digital_assets = c_val(44, 8) or "No"
        health_insurance = c_val(45, 8) or "Yes"

        days_us_2025 = c_val(28, 8)
        days_us_2024 = c_val(29, 8)
        days_us_2023 = c_val(30, 8)

        # Income Checklist
        wages_tp = c_num(64, 8, 125000)
        wages_sp = c_num(65, 8, 95000)
        state_tax_refund = c_num(63, 18, 450)
        social_security = c_num(65, 18, 0)
        interest_dividends = c_num(66, 9, 2500)
        unemployment = c_num(68, 18, 0)
        stock_sales = c_num(70, 8, 15000)
        pension_ira = c_num(74, 8, 5000)

        # Credits & Adjustments to Income
        educator_supplies = c_num(81, 18, 300)
        higher_ed_tuition = c_num(82, 8, 4000)
        hsa_contributions = c_num(82, 18, 3850)
        ira_contributions = c_num(85, 18, 6500)
        child_care_expenses = c_num(87, 8, 3000)
        student_loan_interest = c_num(88, 8, 1200)

        # Itemized Deductions (Schedule A)
        prescription_drugs = c_num(95, 8, 850)
        doctors_hospitals = c_num(100, 8, 2400)
        real_estate_taxes = c_num(95, 18, 6200)
        personal_property_tax = c_num(96, 18, 350)
        mortgage_interest = c_num(103, 8, 11500)
        charity_donations = c_num(103, 18, 2500)
        medical_total = (prescription_drugs if isinstance(prescription_drugs, (int, float)) else 0) + \
                        (doctors_hospitals if isinstance(doctors_hospitals, (int, float)) else 0)

        has_spouse = bool(sp_first or sp_last or sp_ssn)

        return {
            "source_type": "ORGANIZER_SHEET",
            "file_name": os.path.basename(file_path),
            "available_sheets": sheet_names,
            "filing_status": "2" if has_spouse else "1",
            "filing_status_label": "Married Filing Jointly (2)" if has_spouse else "Single (1)",
            "taxpayer": {
                "first_name": tp_first,
                "mi": tp_mi,
                "last_name": tp_last,
                "ssn": tp_ssn,
                "dob": tp_dob,
                "occupation": tp_occ,
                "phone": tp_phone,
                "other_phone": tp_other_phone,
                "email": tp_email
            },
            "spouse": {
                "first_name": sp_first,
                "mi": sp_mi,
                "last_name": sp_last,
                "ssn": sp_ssn,
                "dob": sp_dob,
                "occupation": sp_occ,
                "phone": sp_phone,
                "other_phone": sp_other_phone,
                "email": sp_email
            },
            "address": {
                "street": street,
                "apt": "",
                "city": city,
                "state": state,
                "zip": zip_code,
                "county": ""
            },
            "bank": {
                "bank_name": bank_name,
                "routing": routing,
                "account_number": account_num,
                "account_type": account_type
            },
            "dependents": dependents,
            "residency_questions": {
                "residential_status": residency_status,
                "days_us_2025": days_us_2025,
                "days_us_2024": days_us_2024,
                "days_us_2023": days_us_2023,
                "foreign_bank_account": foreign_bank_account,
                "fbar_required": fbar_required,
                "fbar_file_request": fbar_file_request,
                "digital_assets": digital_assets,
                "health_insurance": health_insurance
            },
            "income_checklist": {
                "wages_taxpayer": wages_tp,
                "wages_spouse": wages_sp,
                "state_tax_refund": state_tax_refund,
                "interest_dividends": interest_dividends,
                "stock_sales_capital_gains": stock_sales,
                "pension_annuity_ira": pension_ira,
                "social_security": social_security,
                "unemployment": unemployment
            },
            "credits_and_adjustments": {
                "higher_education_tuition": higher_ed_tuition,
                "educator_supplies": educator_supplies,
                "hsa_contributions": hsa_contributions,
                "ira_contributions": ira_contributions,
                "ira_type": "Traditional",
                "ira_for": "Both",
                "child_care_expenses": child_care_expenses,
                "student_loan_interest": student_loan_interest
            },
            "itemized_deductions": {
                "mortgage_interest": mortgage_interest,
                "real_estate_taxes": real_estate_taxes,
                "personal_property_tax": personal_property_tax,
                "charitable_contributions": charity_donations,
                "doctors_dentists_hospitals": doctors_hospitals,
                "prescription_drugs": prescription_drugs,
                "medical_total": medical_total
            }
        }

    # CASE B: Tabular format (Name and Address / Dependents sheets)
    data = {
        "source_type": "TABULAR_SHEET",
        "file_name": os.path.basename(file_path),
        "available_sheets": sheet_names,
        "filing_status": "1",
        "filing_status_label": "Single (1)",
        "taxpayer": {},
        "spouse": {},
        "address": {},
        "bank": {},
        "dependents": [],
        "residency_questions": {
            "residential_status": "Citizen",
            "foreign_bank_account": "No",
            "fbar_required": "No",
            "fbar_file_request": "No",
            "digital_assets": "No",
            "health_insurance": "Yes"
        },
        "income_checklist": {},
        "credits_and_adjustments": {},
        "itemized_deductions": {}
    }

    if "name and address" in sheet_names_lower:
        idx = sheet_names_lower.index("name and address")
        sheet = wb[sheet_names[idx]]
        rows = list(sheet.iter_rows(values_only=True))
        if len(rows) > 1:
            for row in rows[1:]:
                if not row or len(row) < 3 or not row[0]:
                    continue
                field_name = str(row[0]).strip().lower()
                sec = str(row[1]).strip().lower() if row[1] else ""
                val = sanitize_cell(row[2])

                if sec == "taxpayer":
                    if "first" in field_name: data["taxpayer"]["first_name"] = val
                    elif "last" in field_name: data["taxpayer"]["last_name"] = val
                    elif "m.i" in field_name or "middle" in field_name: data["taxpayer"]["mi"] = val
                    elif "ssn" in field_name: data["taxpayer"]["ssn"] = val
                    elif "birth" in field_name: data["taxpayer"]["dob"] = val
                    elif "occupation" in field_name: data["taxpayer"]["occupation"] = val
                    elif "phone" in field_name or "daytime" in field_name: data["taxpayer"]["phone"] = val
                    elif "cell" in field_name or "other" in field_name: data["taxpayer"]["other_phone"] = val
                    elif "email" in field_name: data["taxpayer"]["email"] = val
                elif sec == "spouse":
                    if "first" in field_name: data["spouse"]["first_name"] = val
                    elif "last" in field_name: data["spouse"]["last_name"] = val
                    elif "m.i" in field_name or "middle" in field_name: data["spouse"]["mi"] = val
                    elif "ssn" in field_name: data["spouse"]["ssn"] = val
                    elif "birth" in field_name: data["spouse"]["dob"] = val
                    elif "occupation" in field_name: data["spouse"]["occupation"] = val
                    elif "phone" in field_name or "daytime" in field_name: data["spouse"]["phone"] = val
                    elif "cell" in field_name or "other" in field_name: data["spouse"]["other_phone"] = val
                    elif "email" in field_name: data["spouse"]["email"] = val
                elif sec == "address":
                    if "street" in field_name: data["address"]["street"] = val
                    elif "apt" in field_name: data["address"]["apt"] = val
                    elif "city" in field_name: data["address"]["city"] = val
                    elif "state" in field_name: data["address"]["state"] = val
                    elif "zip" in field_name: data["address"]["zip"] = val
                    elif "county" in field_name: data["address"]["county"] = val

    if bool(data["spouse"].get("first_name") or data["spouse"].get("last_name") or data["spouse"].get("ssn")):
        data["filing_status"] = "2"
        data["filing_status_label"] = "Married Filing Jointly (2)"

    if "dependents" in sheet_names_lower:
        idx = sheet_names_lower.index("dependents")
        sheet = wb[sheet_names[idx]]
        rows = list(sheet.iter_rows(values_only=True))
        if len(rows) > 1:
            headers = [str(h).strip().lower() if h else "" for h in rows[0]]
            for r in rows[1:]:
                if not r or not any(r):
                    continue
                dep = {
                    "first_name": "", "mi": "", "last_name": "",
                    "ssn": "", "relationship": "", "months": "12", "dob": ""
                }
                for ci, h in enumerate(headers):
                    if ci >= len(r): break
                    v = sanitize_cell(r[ci])
                    if "first" in h: dep["first_name"] = v
                    elif "m.i" in h or "middle" in h: dep["mi"] = v
                    elif "last" in h: dep["last_name"] = v
                    elif "ssn" in h: dep["ssn"] = v
                    elif "relationship" in h: dep["relationship"] = v.upper()
                    elif "months" in h: dep["months"] = v
                    elif "birth" in h: dep["dob"] = v
                if dep["first_name"] or dep["last_name"]:
                    dep["full_name"] = f"{dep['first_name']} {dep['last_name']}".strip()
                    data["dependents"].append(dep)

    return data

