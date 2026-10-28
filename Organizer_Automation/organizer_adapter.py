import os
from organizer_parser import parse_organizer

def adapt_organizer_for_drake(organizer_file_path):
    """
    Reads the 2025 Personal Tax Organizer.xlsx and produces the exact section dictionaries
    ready for Drake Tax 2025 screens.
    """
    raw = parse_organizer(organizer_file_path)

    # 1. Screen 1: Name and Address entries
    name_address_entries = []
    
    # Taxpayer details
    tp = raw.get("taxpayer", {})
    if tp.get("first_name"):
        name_address_entries.append(("First name", "Taxpayer", tp["first_name"]))
    if tp.get("middle_name"):
        name_address_entries.append(("M.I", "Taxpayer", tp["middle_name"]))
    if tp.get("last_name"):
        name_address_entries.append(("Last name", "Taxpayer", tp["last_name"]))
    if tp.get("dob"):
        name_address_entries.append(("Date of birth", "Taxpayer", tp["dob"]))
    if tp.get("occupation"):
        name_address_entries.append(("Occupation", "Taxpayer", tp["occupation"]))
    if tp.get("main_phone"):
        name_address_entries.append(("Daytime", "Taxpayer", tp["main_phone"]))
    if tp.get("other_phone"):
        name_address_entries.append(("Cell", "Taxpayer", tp["other_phone"]))
    if tp.get("email"):
        name_address_entries.append(("Email or text msg", "Taxpayer", tp["email"]))

    # Spouse details
    sp = raw.get("spouse", {})
    if sp.get("first_name"):
        name_address_entries.append(("First name", "Spouse", sp["first_name"]))
    if sp.get("middle_name"):
        name_address_entries.append(("M.I", "Spouse", sp["middle_name"]))
    if sp.get("last_name"):
        name_address_entries.append(("Last name", "Spouse", sp["last_name"]))
    if sp.get("ssn"):
        name_address_entries.append(("SSN", "Spouse", sp["ssn"]))
    if sp.get("dob"):
        name_address_entries.append(("Date of birth", "Spouse", sp["dob"]))
    if sp.get("occupation"):
        name_address_entries.append(("Occupation", "Spouse", sp["occupation"]))
    if sp.get("main_phone"):
        name_address_entries.append(("Daytime", "Spouse", sp["main_phone"]))
    if sp.get("other_phone"):
        name_address_entries.append(("Cell", "Spouse", sp["other_phone"]))
    if sp.get("email"):
        name_address_entries.append(("Email or text msg", "Spouse", sp["email"]))

    # Address
    addr = raw.get("address", {})
    if addr.get("street"):
        name_address_entries.append(("Street", "Address", addr["street"]))
    if addr.get("city"):
        name_address_entries.append(("City", "Address", addr["city"]))
    if addr.get("state"):
        name_address_entries.append(("State", "Address", addr["state"]))
        name_address_entries.append(("Resident state", "Address", addr["state"]))
    if addr.get("zip"):
        name_address_entries.append(("ZIP", "Address", addr["zip"]))

    # 2. Screen 2: Dependents
    dep_headers = ["First Name", "M.I.", "Last Name", "Suffix", "SSN", "Relationship"]
    dep_rows = []
    for d in raw.get("dependents", []):
        dep_rows.append([
            d.get("first_name", ""),
            "",
            d.get("last_name", ""),
            "",
            d.get("ssn", ""),
            d.get("relationship", "").upper()
        ])

    # 3. Screen 3: Income entries
    inc = raw.get("income", {})
    income_entries = []
    if inc.get("pension_ira"):
        income_entries.append(("Pension distributions received (if no 1099 was received)", "Taxpayer", inc["pension_ira"]))
    if inc.get("state_tax_refund"):
        income_entries.append(("State taxes", "Taxpayer", inc["state_tax_refund"]))
    if inc.get("social_security") and inc["social_security"] != "0":
        income_entries.append(("Net Social Security benefits received for 2025", "Taxpayer", inc["social_security"]))
    if inc.get("unemployment") and inc["unemployment"] != "0":
        income_entries.append(("Unemployment compensation (full amount from Form 1099-G, box 1)", "Taxpayer", inc["unemployment"]))

    # 4. Screen 4: Adjustments entries
    adj = raw.get("adjustments", {})
    adjustments_entries = []
    if adj.get("educator_supplies"):
        adjustments_entries.append(("Educator expenses", "Taxpayer", adj["educator_supplies"]))

    # Client summary for logging and verification
    client_info = {
        "ssn": tp.get("ssn", ""),
        "first_name": tp.get("first_name", ""),
        "last_name": tp.get("last_name", ""),
        "middle_name": tp.get("middle_name", ""),
        "has_spouse": bool(sp.get("first_name"))
    }

    return {
        "client_info": client_info,
        "name_and_address": name_address_entries,
        "dependents": {
            "headers": dep_headers,
            "rows": dep_rows
        },
        "income": income_entries,
        "adjustments": adjustments_entries,
        "banking": raw.get("banking", {}),
        "raw_parsed": raw
    }

if __name__ == "__main__":
    import pprint
    sample_path = os.path.join(os.path.dirname(__file__), "..", "2025 Personal Tax Organizer.xlsx")
    res = adapt_organizer_for_drake(sample_path)
    print("=== CLIENT INFO ===")
    pprint.pprint(res["client_info"])
    print("\n=== NAME & ADDRESS ENTRIES ===")
    pprint.pprint(res["name_and_address"])
    print("\n=== DEPENDENTS ROWS ===")
    pprint.pprint(res["dependents"])
    print("\n=== INCOME ENTRIES ===")
    pprint.pprint(res["income"])
    print("\n=== ADJUSTMENTS ENTRIES ===")
    pprint.pprint(res["adjustments"])
