import time
import os
import win32gui
import win32con
import openpyxl
from pywinauto import Desktop

# Toolbar buttons and system items to ignore
IGNORED_LABELS = {
    "minimize", "maximize", "close", "screen menu", "calculate", "view/print", 
    "refresh", "delete", "clear flags", "previous", "next", "calculator", 
    "py fields", "py data", "text size", "help", "exit", "record 1 of 1", 
    "press f1 or right-click for help", "(screen help)", "split", "documents", 
    "tax planner", "import", "csm", "email", "payments"
}

from Automation import find_drake_window, connect_window

def extract_all_form_fields(window):
    """Extracts all tax fields organized cleanly by Section (GroupBox)."""
    ignored_sections = {"screen menu", "mfs claiming spouse exemption", "foreign account and digital asset questions"}
    ignored_labels = {"=", "taxpayer", "spouse", "mailing address", "return options", "miscellaneous codes", "2210 options"}

    groups = window.descendants(control_type="Group")
    sections = {}

    for g in groups:
        sec_name = g.window_text().strip()
        if not sec_name or sec_name.lower() in ignored_sections:
            continue

        edits = g.descendants(control_type="Edit")
        labels = []
        for c in g.descendants(control_type="Text"):
            txt = c.window_text().strip().rstrip('.').rstrip(':')
            if txt and txt.lower() not in ignored_labels and not txt.startswith("Age:"):
                try:
                    labels.append((txt, c.rectangle()))
                except Exception:
                    pass

        sec_fields = []
        for edit in edits:
            try:
                aid = edit.element_info.automation_id or ""
                val = edit.window_text().strip()
                erect = edit.rectangle()
                ecy = (erect.top + erect.bottom) / 2

                best_lbl = None
                min_dist = 9999
                for lbl_txt, lrect in labels:
                    lcy = (lrect.top + lrect.bottom) / 2
                    v_dist = abs(ecy - lcy)
                    if v_dist <= 14 and lrect.left <= erect.left:
                        dist = v_dist * 2 + (erect.left - lrect.right)
                        if dist < min_dist:
                            min_dist = dist
                            best_lbl = lbl_txt

                field_name = best_lbl if best_lbl else aid
                sec_fields.append((field_name, sec_name, val, aid))
            except Exception:
                continue

        if sec_fields:
            sections[sec_name] = sec_fields

    return sections

def export_fields_to_excel(sections, excel_path):
    """Creates a clean Excel file with all discovered fields split by section."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ScreenFields"

    ws.append(["Field Name", "Section", "Value", "Automation ID"])

    total = 0
    for sec_name, fields in sections.items():
        for field_name, section, val, aid in fields:
            ws.append([field_name, section, val, aid])
            total += 1

    ws.column_dimensions['A'].width = 32
    ws.column_dimensions['B'].width = 22
    ws.column_dimensions['C'].width = 25
    ws.column_dimensions['D'].width = 22

    wb.save(excel_path)
    print(f"\n[EXCEL CREATED] Wrote {total} fields across {len(sections)} sections to:")
    print(f"  -> {excel_path}")

def main():
    print("=" * 65)
    print("   DRAKE FIELD DISCOVERY & STRUCTURED SECTION PARSER")
    print("=" * 65)

    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwinsta = user32.OpenWindowStationW('winsta0', False, 0xF037F)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)
        hdesk = user32.OpenDesktopW('default', 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass

    hwnd, title = find_drake_window()
    if not hwnd:
        print("[ERROR] Drake window not found! Please open Drake.")
        return

    print(f"[CONNECTED] Window: '{title}'")
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.3)

    window = connect_window(hwnd)
    if not window:
        return

    sections = extract_all_form_fields(window)

    print("\n" + "=" * 65)
    print("DISCOVERED TAX FIELDS GROUPED BY SECTION:")
    print("=" * 65)
    for sec_name, fields in sections.items():
        print(f"\n[{sec_name.upper()}] ({len(fields)} fields)")
        print("-" * 65)
        for i, (field_name, section, val, aid) in enumerate(fields, 1):
            val_display = f"'{val}'" if val else "<empty>"
            print(f"  {i:2d}. {field_name:<28} | ID: {aid:<20} | Current: {val_display}")

    excel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drake_fields.xlsx")
    export_fields_to_excel(sections, excel_path)

if __name__ == "__main__":
    main()
