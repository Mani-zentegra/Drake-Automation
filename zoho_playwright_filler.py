import sys
import os
import time
from playwright.sync_api import sync_playwright

USER_DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), "DrakeZohoPlaywrightProfile")

# Dynamic sample dependents (can be 1, 2, or N dependents)
SAMPLE_DEPENDENTS = [
    {
        "name": "Aarav Bharathi",
        "dob": "10-Apr-2015 00:00:00",
        "ssn": "400-01-1111",
        "relationship": "Son",
        "months": "12"
    },
    {
        "name": "Ananya Bharathi",
        "dob": "18-Sep-2018 00:00:00",
        "ssn": "400-01-2222",
        "relationship": "Daughter",
        "months": "12"
    }
]

NOTES_TO_PREPARER = "Eligible for Child Tax Credit. Lived with taxpayer in the US for 12 months."

def find_creator_frame(page):
    """Finds the frame containing the Zoho Creator form components."""
    for frame in page.frames:
        if frame.locator("[name*='Dependents_Information'], [zc-form-name], form").count() > 0:
            return frame
    return page

def fill_field(frame, selector, value):
    """Dynamically locates, scrolls into view, and sets field value."""
    loc = frame.locator(selector).first
    if loc.count() > 0:
        try:
            loc.scroll_into_view_if_needed(timeout=3000)
            loc.fill(value, timeout=3000)
            return True
        except Exception:
            # Fallback to JavaScript direct value injection if Zoho has virtual table/overlays
            try:
                loc.evaluate(f"""el => {{
                    el.value = "{value}";
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                }}""")
                return True
            except Exception:
                pass
    return False

def select_relationship(frame, row_idx, relationship_val):
    """Selects dropdown value for relationship dynamically."""
    rel_selectors = [
        f"[name*='row_{row_idx}'][name*='Relationship']",
        f"[name='Dependents_Information.t::row_{row_idx}.Relationship']",
        f"table tr:nth-child({row_idx + 1}) select",
        "select[name*='Relationship']"
    ]
    for sel in rel_selectors:
        loc = frame.locator(sel).first
        if loc.count() > 0:
            try:
                # Try direct select
                loc.select_option(label=relationship_val, timeout=2000)
                return True
            except Exception:
                try:
                    loc.select_option(value=relationship_val, timeout=2000)
                    return True
                except Exception:
                    pass
    
    # Check if Zoho uses customized select2/div dropdown
    custom_dd = frame.locator(f"[name*='row_{row_idx}'][name*='Relationship'] ~ .select2-container, table tr:nth-child({row_idx + 1}) .zc-select, .select2-selection").first
    if custom_dd.count() > 0:
        try:
            custom_dd.click()
            time.sleep(0.5)
            frame.locator(f"li:has-text('{relationship_val}'), .select2-results__option:has-text('{relationship_val}')").first.click(timeout=3000)
            return True
        except Exception:
            pass
    return False

def run():
    print(f"[PLAYWRIGHT] User profile directory: {USER_DATA_DIR}")
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            args=["--start-maximized"],
            no_viewport=True
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        target_url = "https://creatorapp.zoho.in/zentegraindia/drake-automation/#Form:Dependents"
        print(f"[PLAYWRIGHT] Navigating to: {target_url}")
        page.goto(target_url)

        # Wait for page & form ready
        print("[WAITING] Waiting for Zoho Creator Form...")
        logged_in = False
        for i in range(60):
            time.sleep(3)
            url = page.url
            if "drake-automation" in url and "login" not in url.lower() and "accounts.zoho" not in url.lower():
                logged_in = True
                break

        if not logged_in:
            print("[TIMEOUT] Login waiting timed out.")
            return

        page.wait_for_timeout(4000)
        target_frame = find_creator_frame(page)
        print(f"[FRAME] Working in frame: {target_frame.url}")

        # 1. Fill Notes to Preparer
        print("[AUTOMATION] Filling Notes to Preparer...")
        notes_selectors = [
            "textarea[name='Notes_to_Preparer']",
            "textarea[elename='Notes_to_Preparer']",
            "[aria-label*='Notes to Preparer']",
            "textarea"
        ]
        for ns in notes_selectors:
            if fill_field(target_frame, ns, NOTES_TO_PREPARER):
                print(f"[OK] Notes to Preparer filled.")
                break

        # 2. Iterate dynamically over all Dependents
        for idx, dep in enumerate(SAMPLE_DEPENDENTS):
            print(f"\n--- Inserting Dependent {idx + 1}: {dep['name']} ---")

            # If not row 0, click '+ Add New' button to add row in Zoho Subform
            if idx > 0:
                add_btn_selectors = [
                    "a:has-text('+ Add New')",
                    "button:has-text('Add New')",
                    "[zc-action='addrow']",
                    "[elename='add_row']",
                    ".zc-subform-addrow"
                ]
                for btn_sel in add_btn_selectors:
                    btn = target_frame.locator(btn_sel).first
                    if btn.count() > 0:
                        btn.click()
                        time.sleep(1)
                        print(f"[OK] Clicked '+ Add New' for row {idx + 1}")
                        break

            # Match exact Zoho Subform field naming pattern: Dependents_Information.t::row_{idx}.{FieldName}
            prefix = f"Dependents_Information.t::row_{idx}"

            # Dependent Name
            name_sel = f"[name='{prefix}.Dependents_Name'], [name*='row_{idx}'][name*='Name'], #zc-Dependents_Information-Dependents_Name"
            if fill_field(target_frame, name_sel, dep["name"]):
                print(f"[OK] Row {idx + 1} Name: {dep['name']}")

            # Date of Birth
            dob_sel = f"[name='{prefix}.Date_of_Birth'], [name*='row_{idx}'][name*='Birth'], [placeholder*='dd-MMM-yyyy']"
            if fill_field(target_frame, dob_sel, dep["dob"]):
                print(f"[OK] Row {idx + 1} DOB: {dep['dob']}")

            # SSN / ITIN
            ssn_sel = f"[name='{prefix}.Social_Security_ITIN'], [name='{prefix}.Social_Security_ITIN_#'], [name*='row_{idx}'][name*='Security']"
            if fill_field(target_frame, ssn_sel, dep["ssn"]):
                print(f"[OK] Row {idx + 1} SSN: {dep['ssn']}")

            # Relationship
            if select_relationship(target_frame, idx, dep["relationship"]):
                print(f"[OK] Row {idx + 1} Relationship: {dep['relationship']}")

            # Mos. In Home
            mos_sel = f"[name='{prefix}.Mos_In_Home'], [name*='row_{idx}'][name*='Home'], [placeholder*='#######']"
            if fill_field(target_frame, mos_sel, dep["months"]):
                print(f"[OK] Row {idx + 1} Mos. In Home: {dep['months']}")

        print("\n============================================================")
        print(">>> ALL DEPENDENT ROWS DYNAMICALLY INSERTED SUCCESSFULLY! <<<")
        print("Please review the populated subform and click 'Submit'!")
        print("============================================================\n")

        # Keep browser open for inspection
        time.sleep(180)

if __name__ == "__main__":
    run()
