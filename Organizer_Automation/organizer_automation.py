import sys
import os
import ctypes
import time
import win32gui
import win32con
import pyautogui
from pywinauto import Desktop

# Import the dedicated organizer adapter and parser
from organizer_adapter import adapt_organizer_for_drake

pyautogui.FAILSAFE = False

try:
    user32 = ctypes.windll.user32
    hwinsta = user32.OpenWindowStationW('winsta0', False, 0xF037F)
    if hwinsta:
        user32.SetProcessWindowStation(hwinsta)
    hdesk = user32.OpenDesktopW('default', 0, False, 0x01FF)
    if hdesk:
        user32.SetThreadDesktop(hdesk)
except Exception:
    pass

def get_window_owner(h):
    try:
        if h and win32gui.IsWindow(h):
            return win32gui.GetWindow(h, win32con.GW_OWNER)
    except Exception:
        pass
    return 0

def get_window_title(h):
    try:
        if h and win32gui.IsWindow(h):
            return win32gui.GetWindowText(h)
    except Exception:
        pass
    return ""

def find_drake_window():
    menu_w = None
    subscreen_w = None
    home_w = None
    def cb(h, _):
        nonlocal menu_w, subscreen_w, home_w
        try:
            if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
                t = get_window_title(h)
                if "data entry" in t.lower():
                    owner = get_window_owner(h)
                    owner_text = get_window_title(owner).lower() if owner else ""
                    if "data entry" in owner_text:
                        subscreen_w = (h, t)
                    else:
                        menu_w = (h, t)
                elif "drake 2025 tax software" in t.lower() or "drake 2025" in t.lower():
                    home_w = (h, t)
        except Exception:
            pass
    try:
        win32gui.EnumDesktopWindows(hdesk, cb, None)
    except Exception:
        try:
            win32gui.EnumWindows(cb, None)
        except Exception:
            pass
    if subscreen_w:
        return subscreen_w
    if menu_w:
        return menu_w
    if home_w:
        return home_w
    return (None, "")

def find_drake_dialog(keyword):
    matched = []
    def enum_cb(h, _):
        if win32gui.IsWindowVisible(h):
            t = get_window_title(h)
            if keyword.lower() in t.lower():
                matched.append((h, t))
    try:
        win32gui.EnumDesktopWindows(hdesk, enum_cb, None)
    except Exception:
        try:
            win32gui.EnumWindows(enum_cb, None)
        except Exception:
            pass
    return matched[0] if matched else (None, "")

def dismiss_drake_popups():
    for _ in range(3):
        h, _ = find_drake_dialog("Data Entry")
        if not h:
            h, _ = find_drake_dialog("Save")
        if not h:
            h, _ = find_drake_dialog("Confirm")
        if h:
            owner = get_window_owner(h)
            if owner != 0:
                try:
                    w = Desktop(backend="uia").window(handle=h)
                    handled = False
                    for btn in w.descendants(control_type="Button"):
                        txt = btn.window_text().strip().lower()
                        if txt in ["yes", "_yes", "ok", "_ok", "save"]:
                            btn.invoke()
                            time.sleep(0.5)
                            handled = True
                            break
                    if not handled:
                        for btn in w.descendants(control_type="Button"):
                            txt = btn.window_text().strip().lower()
                            if txt in ["cancel", "no", "_cancel", "_no"]:
                                btn.invoke()
                                time.sleep(0.5)
                                break
                except Exception:
                    pass
        break

def connect_window(hwnd):
    try:
        return Desktop(backend="uia").window(handle=hwnd)
    except Exception as e:
        print(f"[ERROR] Could not connect to window {hwnd}: {e}")
        return None

def click_open_create(window):
    for control in window.descendants(control_type="Button"):
        try:
            text = control.window_text().strip().lower()
            cid = (control.element_info.automation_id or "").lower()
            if "open" in text or "create" in text or "open" in cid or "fileopen" in cid:
                control.invoke()
                return True
        except Exception:
            continue
    for control in window.descendants(control_type="Text"):
        try:
            text = control.window_text().strip().lower()
            if "open/create" in text or "open / create" in text:
                r = control.rectangle()
                pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
                return True
        except Exception:
            continue
    pyautogui.hotkey('ctrl', 'o')
    return True

def enter_ssn_and_submit(dialog, ssn):
    for c in dialog.descendants(control_type="Edit"):
        try:
            if c.is_visible() and c.is_enabled():
                c.set_edit_text(str(ssn).strip())
                time.sleep(0.5)
                break
        except Exception:
            continue

    for c in dialog.descendants(control_type="Button"):
        if c.window_text().strip().lower() in ["ok", "_ok"]:
            try:
                c.invoke()
                return True
            except Exception:
                pass
    pyautogui.press('enter')
    return True

def create_new_individual_return(new_return_window, first_name, last_name, mi=""):
    for rb in new_return_window.descendants(control_type="RadioButton"):
        txt = rb.window_text().strip().lower()
        if "1040" in txt or "individual" in txt:
            try:
                rb.select()
            except Exception:
                pass
            break
    time.sleep(0.3)

    edits = [e for e in new_return_window.descendants(control_type="Edit") if e.is_visible() and e.is_enabled()]
    fn_edit, mi_edit, ln_edit = None, None, None

    for t in new_return_window.descendants(control_type="Text"):
        lbl_txt = t.window_text().strip().rstrip(':').lower()
        if lbl_txt in ["first name", "mi", "last name", "middle initial"]:
            lcx = (t.rectangle().left + t.rectangle().right) / 2
            for e in edits:
                ecx = (e.rectangle().left + e.rectangle().right) / 2
                if abs(ecx - lcx) < 70 and e.rectangle().top >= t.rectangle().bottom - 10:
                    if "first" in lbl_txt:
                        fn_edit = e
                    elif "mi" in lbl_txt or "middle" in lbl_txt:
                        mi_edit = e
                    elif "last" in lbl_txt:
                        ln_edit = e

    if not fn_edit and len(edits) >= 1:
        fn_edit = edits[0]
    if not mi_edit and len(edits) >= 2:
        mi_edit = edits[1]
    if not ln_edit and len(edits) >= 3:
        ln_edit = edits[2]

    if fn_edit and first_name:
        try:
            fn_edit.set_edit_text(first_name)
        except Exception:
            pass

    if mi and mi_edit:
        try:
            mi_edit.set_edit_text(mi)
        except Exception:
            pass

    if ln_edit and last_name:
        try:
            ln_edit.set_edit_text(last_name)
        except Exception:
            pass

    time.sleep(0.3)
    for btn in new_return_window.descendants(control_type="Button"):
        if btn.window_text().strip().lower() in ["ok", "_ok"]:
            try:
                btn.invoke()
                return True
            except Exception:
                pass
    pyautogui.press('enter')
    return True

def open_or_create_client(ssn, first_name="", last_name="", mi=""):
    cleaned_ssn = str(ssn).replace("-", "").replace(" ", "").strip()
    if len(cleaned_ssn) != 9 or not cleaned_ssn.isdigit():
        print(f"[ERROR] SSN must be exactly 9 digits, got '{ssn}'")
        return False

    print("=" * 65)
    print("       DRAKE 2025: OPEN OR CREATE CLIENT RETURN       ")
    print("=" * 65)
    print(f"[TARGET] Client SSN: {cleaned_ssn} ({first_name} {last_name})")

    open_h, _ = find_drake_dialog("Open / Create a Return")
    if not open_h:
        main_h, main_t = find_drake_window()
        if not main_h or "data entry" in main_t.lower():
            main_h, main_t = find_drake_dialog("Drake 2025 Tax Software")
        if not main_h:
            print("[ERROR] Drake 2025 Tax Software is not running.")
            return False

        print(f"[CONNECT] Drake Main Window: '{main_t}'")
        main_win = Desktop(backend="uia").window(handle=main_h)
        print("[ACTION] Clicking 'Open/Create' button...")
        click_open_create(main_win)

        for _ in range(10):
            time.sleep(0.5)
            open_h, _ = find_drake_dialog("Open / Create a Return")
            if open_h:
                break

    if not open_h:
        print("[ERROR] Could not open 'Open / Create a Return' dialog.")
        return False

    print("[DIALOG] 'Open / Create a Return' is ready.")
    open_dialog = Desktop(backend="uia").window(handle=open_h)

    print(f"[SEARCH] Submitting SSN: {cleaned_ssn}...")
    enter_ssn_and_submit(open_dialog, cleaned_ssn)

    for _ in range(12):
        time.sleep(0.5)
        prompt_h, _ = find_drake_dialog("Open Return")
        if prompt_h:
            print(f"[NOT FOUND] Client {cleaned_ssn} does not exist yet. Creating new return...")
            prompt_win = Desktop(backend="uia").window(handle=prompt_h)
            yes_clicked = False
            for btn in prompt_win.descendants(control_type="Button"):
                if btn.window_text().strip().lower() in ["yes", "_yes"]:
                    try:
                        btn.invoke()
                        yes_clicked = True
                        break
                    except Exception:
                        pass
            if not yes_clicked:
                pyautogui.press('y')
            time.sleep(1.0)

            new_ret_h, _ = find_drake_dialog("New Return")
            for _ in range(6):
                if new_ret_h:
                    break
                time.sleep(0.5)
                new_ret_h, _ = find_drake_dialog("New Return")

            if not new_ret_h:
                print("[ERROR] 'New Return' dialog did not appear.")
                return False

            print(f"[CREATE] Creating Individual (1040) return: {first_name} {mi} {last_name}...")
            new_ret_win = Desktop(backend="uia").window(handle=new_ret_h)
            create_new_individual_return(new_ret_win, first_name, last_name, mi)
            break

        entry_h, entry_t = find_drake_window()
        if entry_h and "data entry" in entry_t.lower():
            print(f"[SUCCESS] Client {cleaned_ssn} exists! Opened return: '{entry_t}'")
            return True

    for _ in range(10):
        time.sleep(0.6)
        entry_h, entry_t = find_drake_window()
        if entry_h and "data entry" in entry_t.lower():
            print(f"[SUCCESS] Return created and opened: '{entry_t}'")
            return True

    return True

def exit_to_menu():
    for _ in range(4):
        h, _ = find_drake_window()
        if not h:
            break
        try:
            win32gui.ShowWindow(h, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(h)
        except Exception:
            pass
        time.sleep(0.2)

        try:
            w = Desktop(backend="uia").window(handle=h)
            for b in w.descendants(control_type="Button"):
                if b.window_text().strip().lower() == "save":
                    try:
                        b.invoke()
                        time.sleep(0.6)
                        break
                    except Exception:
                        pass
        except Exception:
            pass

        pyautogui.press('esc')
        time.sleep(0.4)
        dismiss_drake_popups()
        cur_h, cur_t = find_drake_window()
        owner = get_window_owner(cur_h)
        owner_text = get_window_title(owner).lower() if owner else ""
        if "data entry" in cur_t.lower() and "data entry" not in owner_text:
            return True
        time.sleep(0.3)
    return False

def navigate_to_screen(hwnd, code):
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.2)

    try:
        w = Desktop(backend="uia").window(handle=hwnd)
        for edit in w.descendants(control_type="Edit"):
            try:
                rect = edit.rectangle()
                if rect.left < 500 and rect.top < 350:
                    edit.set_focus()
                    edit.set_edit_text(code)
                    pyautogui.press('enter')
                    time.sleep(0.6)
                    return True
            except Exception:
                pass
    except Exception:
        pass

    pyautogui.write(code, interval=0.05)
    time.sleep(0.2)
    pyautogui.press('enter')
    time.sleep(0.6)
    return True

def get_column_header_x(window):
    taxpayer_x, spouse_x = None, None
    for control in window.descendants():
        try:
            if control.element_info.control_type in ["Text", "HeaderItem"]:
                name = control.window_text().strip().lower()
                rect = control.rectangle()
                if name == "taxpayer":
                    taxpayer_x = (rect.left + rect.right) / 2
                elif name == "spouse":
                    spouse_x = (rect.left + rect.right) / 2
        except Exception:
            pass
    return taxpayer_x, spouse_x

def find_edit_for_field(cached_edits, label_rect, col_type, col_headers):
    lbl_center_y = (label_rect.top + label_rect.bottom) / 2
    candidates = []
    for edit, rect in cached_edits:
        edit_center_y = (rect.top + rect.bottom) / 2
        if abs(edit_center_y - lbl_center_y) <= 18:
            candidates.append((edit, rect))

    if not candidates:
        return None

    if col_type:
        taxpayer_x, spouse_x = col_headers
        target_x = taxpayer_x if col_type.lower() == "taxpayer" else spouse_x
        if target_x is not None:
            best_edit, min_dist = None, 9999
            for edit, rect in candidates:
                edit_center_x = (rect.left + rect.right) / 2
                dist = abs(edit_center_x - target_x)
                if dist < min_dist:
                    min_dist = dist
                    best_edit = edit
            if min_dist < 100:
                return best_edit

    right_candidates = [(e, r) for e, r in candidates if r.left >= label_rect.left]
    if right_candidates:
        right_candidates.sort(key=lambda item: item[1].left)
        return right_candidates[0][0]

    return candidates[0][0]

def discover_section_controls(window):
    sections = {}
    current_section = "general"
    sections[current_section] = {}

    all_controls = []
    for control in window.descendants():
        try:
            rect = control.rectangle()
            all_controls.append((control, rect))
        except Exception:
            pass

    all_controls.sort(key=lambda c: (c[1].top, c[1].left))

    for control, rect in all_controls:
        try:
            ctrl_type = control.element_info.control_type
            txt = control.window_text().strip()
            if ctrl_type == "Group" and txt:
                current_section = txt.lower()
                if current_section not in sections:
                    sections[current_section] = {}
            elif ctrl_type in ["Text", "HeaderItem"] and txt:
                lower_txt = txt.rstrip(':').rstrip('.').strip().lower()
                lbl_cy = (rect.top + rect.bottom) / 2
                best_edit = None
                best_dist = 9999
                for other, orect in all_controls:
                    if other.element_info.control_type in ["Edit", "ComboBox"]:
                        ocy = (orect.top + orect.bottom) / 2
                        if abs(ocy - lbl_cy) <= 15 and orect.left >= rect.left:
                            dist = orect.left - rect.right
                            if dist < best_dist:
                                best_dist = dist
                                best_edit = other
                if best_edit and best_dist < 300:
                    sections[current_section][lower_txt] = best_edit
        except Exception:
            pass
    return sections

def focus_grid_start(window):
    for c in window.descendants():
        try:
            if c.element_info.control_type in ["DataGrid", "Table"]:
                c.set_focus()
                pyautogui.click((c.rectangle().left + 50), (c.rectangle().top + 50))
                time.sleep(0.3)
                return True
        except Exception:
            pass
    pyautogui.click(300, 300)
    time.sleep(0.3)
    return False

def enter_clean_value(control, value):
    val_str = str(value).strip() if value is not None else ""
    if not val_str:
        return False
    try:
        control.set_focus()
        time.sleep(0.04)
        if hasattr(control, 'set_edit_text'):
            control.set_edit_text(val_str)
            return True
    except Exception:
        pass
    try:
        rect = control.rectangle()
        pyautogui.click((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
        time.sleep(0.02)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.01)
        pyautogui.write(val_str, interval=0.01)
        return True
    except Exception:
        return False

def sanitize_value(field_name, value):
    if value is None:
        return ""
    val_str = str(value).strip()
    f_lower = field_name.lower()
    if any(k in f_lower for k in ["phone", "cell", "daytime", "evening", "fax"]):
        cleaned = "".join([c for c in val_str if c.isdigit()])
        if cleaned.isdigit() and len(cleaned) == 10:
            return cleaned
    if "ssn" in f_lower:
        return val_str.replace("-", "").replace(" ", "").strip()
    return val_str.replace("$", "").replace(",", "").strip()

# Populate Screen 1 using adapted entries
def fill_name_and_address(window, name_address_entries, has_spouse=False):
    if not name_address_entries:
        print("[ERROR] No data entries for Name and Address.")
        return

    if has_spouse:
        filing_status_ctrl = None
        for lbl in window.descendants(control_type="Text"):
            txt = lbl.window_text().strip().lower()
            if "filing status" in txt:
                lrect = lbl.rectangle()
                lcy = (lrect.top + lrect.bottom) / 2
                best_dist = 9999
                for ctrl in window.descendants():
                    try:
                        ctype = ctrl.element_info.control_type
                        if ctype in ["ComboBox", "Edit"]:
                            crect = ctrl.rectangle()
                            ccy = (crect.top + crect.bottom) / 2
                            if abs(ccy - lcy) <= 15 and crect.left >= lrect.left:
                                dist = crect.left - lrect.right
                                if dist < best_dist:
                                    best_dist = dist
                                    filing_status_ctrl = ctrl
                    except Exception:
                        pass
                break

        if filing_status_ctrl:
            edits = filing_status_ctrl.descendants(control_type="Edit")
            target = edits[0] if edits else filing_status_ctrl
            enter_clean_value(target, "2")
            print("[STATUS] Set Filing Status = 2 (Married Filing Jointly)")
            time.sleep(0.3)

    sections = discover_section_controls(window)
    print(f"[READY] Discovered {len(sections)} UI sections on Screen 1: {list(sections.keys())}")
    print("-" * 65)

    success, total = 0, 0
    for field_name, section, raw_val in name_address_entries:
        total += 1
        clean_val = sanitize_value(field_name, raw_val)

        matched_sec = None
        for s_key in sections:
            if section.lower() in s_key or s_key in section.lower():
                matched_sec = sections[s_key]
                break

        ctrl = None
        if matched_sec:
            ctrl = matched_sec.get(field_name.lower())
            if not ctrl:
                for k, c in matched_sec.items():
                    if field_name.lower() in k or k in field_name.lower():
                        ctrl = c
                        break

        if not ctrl:
            print(f"[-] Control not found: '{field_name}' [{section}]")
            continue

        if enter_clean_value(ctrl, clean_val):
            display = f"{field_name} [{section}]" if section else field_name
            print(f"[OK] {display:<45} = {clean_val}")
            success += 1
        else:
            print(f"[FAIL] Could not set: '{field_name}' [{section}]")
        time.sleep(0.04)

    print("-" * 65)
    print(f"[RESULT] Successfully populated {success} of {total} fields on Screen 1!")

# Populate Screen 2 Dependents
def fill_dependents(window, dependents_data):
    headers = dependents_data.get("headers", [])
    data_rows = dependents_data.get("rows", [])
    if not data_rows:
        print("[INFO] No dependents to enter.")
        return

    focus_grid_start(window)
    time.sleep(0.2)
    print(f"[GRID] Entering {len(data_rows)} dependents...")
    print("-" * 65)

    for row_idx, row in enumerate(data_rows, start=1):
        print(f"Entering Dependent {row_idx}: {row[0]} {row[2]} (SSN: {row[4]})...")
        for col_idx, cell_value in enumerate(row):
            header_name = headers[col_idx] if col_idx < len(headers) else ""
            clean_val = sanitize_value(header_name, cell_value)
            if clean_val:
                pyautogui.hotkey('ctrl', 'a')
                time.sleep(0.01)
                pyautogui.write(clean_val, interval=0.01)
                time.sleep(0.02)
            pyautogui.press('tab')
            time.sleep(0.03)
        time.sleep(0.08)

    print("-" * 65)
    print(f"[RESULT] Successfully populated {len(data_rows)} dependents in grid!")

    time.sleep(0.3)
    saved = False
    for b in window.descendants(control_type="Button"):
        if b.window_text().strip().lower() == "save":
            try:
                b.invoke()
                print("[SAVE] Clicked 'Save' button for Dependents grid!")
                saved = True
                break
            except Exception:
                pass

    if not saved:
        pyautogui.hotkey('alt', 's')
        time.sleep(0.2)

    time.sleep(0.8)

# Populate column forms (Screen 3 Income or Screen 4 Adjustments)
def fill_column_form(window, data_entries, section_name):
    if not data_entries:
        print(f"[INFO] No entries to fill for {section_name}.")
        return

    taxpayer_x, spouse_x = None, None
    label_map = {}
    cached_edits = []
    for control in window.descendants():
        try:
            ctrl_type = control.element_info.control_type
            if ctrl_type == "Edit":
                cached_edits.append((control, control.rectangle()))
            name = control.window_text().strip().rstrip(':').rstrip('.')
            if name and (ctrl_type in ["Text", "HeaderItem"] or "label" in (control.element_info.automation_id or "").lower()):
                rect = control.rectangle()
                lower_name = name.lower()
                label_map[lower_name] = (name, rect)
                if lower_name == "taxpayer" and taxpayer_x is None:
                    taxpayer_x = (rect.left + rect.right) / 2
                elif lower_name == "spouse" and spouse_x is None:
                    spouse_x = (rect.left + rect.right) / 2
        except Exception:
            pass

    col_headers = (taxpayer_x, spouse_x)
    print(f"[SCAN] Discovered {len(label_map)} labels and {len(cached_edits)} edits on {section_name} screen.")
    print("-" * 65)

    success, total = 0, 0
    for field_name, col_type, raw_val in data_entries:
        total += 1
        clean_val = sanitize_value(field_name, raw_val)
        matched = label_map.get(field_name.lower())
        if not matched:
            for k, v in label_map.items():
                if field_name.lower() in k or k in field_name.lower():
                    matched = v
                    break

        if not matched:
            print(f"[-] Label not found: '{field_name}'")
            continue

        lbl_text, lbl_rect = matched
        edit_ctrl = find_edit_for_field(cached_edits, lbl_rect, col_type, col_headers)
        if not edit_ctrl:
            print(f"[-] Input box not found for: '{lbl_text}' [{col_type}]")
            continue

        if enter_clean_value(edit_ctrl, clean_val):
            display = f"{lbl_text} [{col_type}]" if col_type else lbl_text
            print(f"[OK] {display:<50} = {clean_val}")
            success += 1
        else:
            print(f"[FAIL] Could not set: '{lbl_text}'")
        time.sleep(0.04)

    print("-" * 65)
    print(f"[RESULT] Successfully populated {success} of {total} fields for {section_name}!")

def run_organizer(excel_file_path=None):
    if not excel_file_path:
        default_p = os.path.join(os.path.dirname(__file__), "..", "2025 Personal Tax Organizer.xlsx")
        excel_file_path = default_p

    print("=" * 65)
    print("   DRAKE TAX 2025: DYNAMIC TAX ORGANIZER AUTOMATION ")
    print("=" * 65)
    print(f"[FILE] Loading: {os.path.abspath(excel_file_path)}")

    # 1. Parse and Adapt Excel Data
    drake_data = adapt_organizer_for_drake(excel_file_path)
    client_info = drake_data["client_info"]
    print(f"[PARSED] Taxpayer: {client_info['first_name']} {client_info['last_name']} | SSN: {client_info['ssn']}")
    print(f"[PARSED] Has Spouse: {client_info['has_spouse']} | Dependents: {len(drake_data['dependents']['rows'])}")

    # 2. Connect to Drake Tax 2025
    hwnd, title = find_drake_window()
    if not hwnd:
        print("[ERROR] Drake 2025 window is not running. Please open Drake 2025 first.")
        return

    print(f"[CONNECTED] Window: '{title}'")

    if "data entry" not in title.lower():
        print("[HOME SCREEN] Drake Home Screen detected. Opening or creating client return...")
        created = open_or_create_client(
            ssn=client_info["ssn"],
            first_name=client_info["first_name"],
            last_name=client_info["last_name"],
            mi=client_info["middle_name"]
        )
        if not created:
            print("[ERROR] Failed to open/create client return.")
            return

    print("\n" + "=" * 65)
    print("   STARTING AUTOMATIC TAX ORGANIZER FILLING PIPELINE")
    print("=" * 65)

    pipeline = [
        ("1", "Name and Address", lambda w: fill_name_and_address(w, drake_data["name_and_address"], client_info["has_spouse"])),
        ("2", "Dependents", lambda w: fill_dependents(w, drake_data["dependents"])),
        ("3", "Income", lambda w: fill_column_form(w, drake_data["income"], "Income")),
        ("4", "Adjustments", lambda w: fill_column_form(w, drake_data["adjustments"], "Adjustments"))
    ]

    for step_num, (code, name, fill_func) in enumerate(pipeline, start=1):
        print(f"\n>>> [{step_num}/{len(pipeline)}] Processing Screen {code}: '{name}'...")
        hwnd, _ = find_drake_window()
        navigate_to_screen(hwnd, code)

        screen_hwnd = None
        for _ in range(8):
            h, t = find_drake_window()
            owner = get_window_owner(h)
            owner_text = get_window_title(owner).lower() if owner else ""
            if h and "data entry" in owner_text:
                screen_hwnd = h
                break
            time.sleep(0.3)

        if not screen_hwnd:
            screen_hwnd, _ = find_drake_window()

        if not screen_hwnd:
            print(f"[ERROR] Could not navigate to Screen {code}.")
            continue

        try:
            win32gui.ShowWindow(screen_hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(screen_hwnd)
        except Exception:
            pass
        time.sleep(0.2)

        window = connect_window(screen_hwnd)
        if not window:
            print(f"[ERROR] Could not connect to Screen {code} window.")
            continue

        fill_func(window)
        time.sleep(0.3)

        print(f"[SAVING] Screen {code} finished. Saving and returning to Data Entry Menu...")
        exit_to_menu()
        time.sleep(0.5)

    print("\n" + "=" * 65)
    print("   TAX ORGANIZER AUTOMATION SUCCESSFULLY COMPLETED! ")
    print("=" * 65)

if __name__ == "__main__":
    file_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run_organizer(file_arg)
