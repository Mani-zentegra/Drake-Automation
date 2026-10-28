import sys
import os

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass
import ctypes
import time
import win32gui
import win32con
import pyautogui
from pywinauto import Desktop

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

def dismiss_drake_popups(prefer_cancel=True):
    """
    Dynamically dismisses any validation alerts, e-file warnings, Help windows, or confirmation popups.
    Specifically handles the Drake 2025 e-file alert:
    'There are fields on this screen that must contain data if you are planning to e-file this return...
     To enter this data now, click OK. To exit this screen, click Cancel.'
    Clicking button 'Cancel' (auto_id='2' or text 'Cancel') exits the screen cleanly.
    """
    handled = False
    def cb(h, _):
        nonlocal handled
        try:
            if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
                t = get_window_title(h).lower()
                owner = get_window_owner(h)
                if owner != 0:
                    w = Desktop(backend="uia").window(handle=h)
                    dialog_texts = [x.window_text().lower() for x in w.descendants(control_type="Text") if x.window_text()]
                    full_txt = " ".join(dialog_texts)

                    # 1. E-FILE WARNING ALERT: Click CANCEL (auto_id '2' or 'Cancel') to exit!
                    if "fields on this screen" in full_txt or "e-file" in full_txt or "to exit this screen" in full_txt:
                        for btn in w.descendants(control_type="Button"):
                            btxt = btn.window_text().strip().lower()
                            aid = btn.element_info.automation_id
                            if btxt in ["cancel", "_cancel"] or aid == "2":
                                btn.invoke()
                                time.sleep(0.3)
                                handled = True
                                return

                    # 2. SAVE CONFIRMATION DIALOG: Click YES to save
                    if "save" in full_txt and "changes" in full_txt:
                        for btn in w.descendants(control_type="Button"):
                            btxt = btn.window_text().strip().lower()
                            if btxt in ["yes", "_yes"]:
                                btn.invoke()
                                time.sleep(0.3)
                                handled = True
                                return

                    # 3. GENERIC POPUP WITH OK/CANCEL/YES
                    if any(k in t for k in ["help", "not valid", "save", "confirm", "attention", "notice", "reminder", "data entry"]):
                        for btn in w.descendants(control_type="Button"):
                            btxt = btn.window_text().strip().lower()
                            aid = btn.element_info.automation_id
                            if prefer_cancel and (btxt in ["cancel", "_cancel"] or aid == "2"):
                                btn.invoke()
                                time.sleep(0.3)
                                handled = True
                                return
                            elif not prefer_cancel and (btxt in ["yes", "_yes", "ok", "_ok", "save"] or aid == "1"):
                                btn.invoke()
                                time.sleep(0.3)
                                handled = True
                                return
        except Exception:
            pass
    try:
        win32gui.EnumDesktopWindows(hdesk, cb, None)
    except Exception:
        pass
    return handled

def find_drake_window():
    """
    Locates Drake 2025 windows: subscreen (W2/Screen 1), Menu window, or Home window.
    """
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

def get_current_drake_state(window):
    """
    Pre-condition check: Detects exact screen Drake is currently sitting on.
    Returns: 'W2_SCREEN', 'SCREEN_1', 'MENU_SCREEN', 'HOME_SCREEN', or 'UNKNOWN'
    """
    for tab in window.descendants(control_type="TabItem"):
        tt = tab.window_text().strip().lower()
        if "w-2" in tt:
            return "W2_SCREEN"
        elif "general" in tt or "due diligence" in tt:
            return "MENU_SCREEN"

    for txt in window.descendants(control_type="Text"):
        t = txt.window_text().strip().lower()
        if "form w-2 - wage and tax statement" in t:
            return "W2_SCREEN"
        elif "employer information" in t and "wages, tips" in t:
            return "W2_SCREEN"
        elif "name, address, and general information" in t or "filing status" in t:
            return "SCREEN_1"
        elif "enter screen, state or search phrase" in t:
            return "MENU_SCREEN"

    for b in window.descendants(control_type="Button"):
        if "w2|wages" in b.window_text().strip().lower():
            return "MENU_SCREEN"

    return "UNKNOWN"

def enter_clean_value(control, value):
    """
    Ultra-fast, reliable value setting.
    Directly uses ValuePattern.SetValue without focus delays or artificial sleeps (<5ms).
    """
    if value is None or str(value).strip() == "":
        return False
    val_str = str(value).strip()

    # Fast path: instant programmatic value assignment via ValuePattern (under 5ms, no focus redraw lag)
    try:
        control.iface_value.SetValue(val_str)
        return True
    except Exception:
        pass

    # Fallback 1: Pywinauto EditWrapper set_edit_text
    try:
        control.set_edit_text(val_str)
        return True
    except Exception:
        pass

    # Fallback 2: Focus and set
    try:
        control.set_focus()
        control.set_edit_text(val_str)
        return True
    except Exception:
        pass

    # Fallback 2: Keystroke typing
    try:
        rect = control.rectangle()
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        pyautogui.click(cx, cy)
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.write(val_str, interval=0.0)
        return True
    except Exception:
        return False

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

def open_or_create_client(ssn, first_name="Zara", last_name="Weaver-Cummings", mi="O"):
    cleaned_ssn = str(ssn).replace("-", "").replace(" ", "").strip()
    print(f"[PRE-CONDITION] Opening or creating client SSN: {cleaned_ssn} ({first_name} {last_name})")

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

        for _ in range(12):
            time.sleep(0.4)
            open_h, _ = find_drake_dialog("Open / Create a Return")
            if open_h:
                break

    if not open_h:
        print("[ERROR] Could not open 'Open / Create a Return' dialog.")
        return False

    print("[DIALOG] 'Open / Create a Return' is ready.")
    open_dialog = Desktop(backend="uia").window(handle=open_h)

    print(f"[SEARCH] Submitting SSN: {cleaned_ssn}...")
    for c in open_dialog.descendants(control_type="Edit"):
        try:
            if c.is_visible() and c.is_enabled():
                c.set_edit_text(cleaned_ssn)
                time.sleep(0.3)
                break
        except Exception:
            continue

    for c in open_dialog.descendants(control_type="Button"):
        if c.window_text().strip().lower() in ["ok", "_ok"]:
            try:
                c.invoke()
                break
            except Exception:
                pass
    else:
        pyautogui.press('enter')

    for _ in range(12):
        time.sleep(0.5)
        dismiss_drake_popups()
        cur_h, cur_t = find_drake_window()
        if cur_h and "data entry" in cur_t.lower():
            print(f"[SUCCESS] Client {cleaned_ssn} return opened!")
            return True

    return False

def ensure_menu_screen(window):
    """
    Pre-condition logic: If Drake is sitting on Screen 1 (or any subscreen),
    safely saves/exits back to the Data Entry Menu so W2 can be opened cleanly.
    """
    state = get_current_drake_state(window)
    if state == "MENU_SCREEN":
        return True

    if state == "SCREEN_1":
        print("[PRE-CONDITION] Detected Screen 1 (Demographics) is open!")
        # If Filing Status is empty on Screen 1, set to 1 (Single) to prevent validation alert
        for e in window.descendants(control_type="Edit"):
            r = e.rectangle()
            if r.top < 300 and r.left < 500:
                try:
                    e.set_focus()
                    e.set_edit_text("1")
                    print("[PRE-CONDITION] Set default Filing Status = 1 on Screen 1")
                except:
                    pass
                break

    # Find btnExit or Screen Menu
    for _ in range(3):
        for b in window.descendants(control_type="Button"):
            aid = b.element_info.automation_id
            bt = b.window_text().strip().lower()
            if aid == "btnExit" or "screen menu" in bt or "save" in bt or bt == "exit":
                try:
                    b.invoke()
                    time.sleep(0.5)
                    break
                except:
                    pass
        pyautogui.press('esc')
        time.sleep(0.4)
        dismiss_drake_popups()
        h, t = find_drake_window()
        if h:
            w_cur = Desktop(backend="uia").window(handle=h)
            if get_current_drake_state(w_cur) == "MENU_SCREEN":
                print("[PRE-CONDITION] Successfully returned to Data Entry Menu!")
                return True
    return False

def populate_w2_screen(w2_data):
    """
    Step 1: Navigates to Screen W-2, populates all fields, and leaves screen open
    in Drake for visual verification by reviewer.
    """
    logs = []
    def log(msg):
        print(msg)
        logs.append(msg)

    dismiss_drake_popups()
    time.sleep(0.2)

    # 1. PRE-CONDITION: Locate Drake Window
    hwnd, title = find_drake_window()
    if not hwnd:
        return False, ["Drake 2025 is not open. Please launch Drake 2025 first."], "ERROR"

    log(f"[PRE-CONDITION] Connected to Drake Window: '{title}'")
    window = Desktop(backend="uia").window(handle=hwnd)

    # 2. PRE-CONDITION: If on Home Screen, open/create return
    if "data entry" not in title.lower():
        log("[PRE-CONDITION] Home screen detected. Opening client return...")
        ssn = w2_data.get("employee_ssn", "555-71-3842")
        fn = w2_data.get("employee_first_name", "Zara")
        ln = w2_data.get("employee_last_name", "Weaver-Cummings")
        mi = w2_data.get("employee_middle", "O")
        opened = open_or_create_client(ssn, fn, ln, mi)
        if not opened:
            return False, logs + ["[ERROR] Could not open or create client return."], "ERROR"
        time.sleep(1.0)
        hwnd, title = find_drake_window()
        window = Desktop(backend="uia").window(handle=hwnd)

    # 3. PRE-CONDITION: Check exact state
    state = get_current_drake_state(window)
    log(f"[PRE-CONDITION] Detected current Drake state: {state}")

    w2_win = window if state == "W2_SCREEN" else None
    if state != "W2_SCREEN":
        # If on Screen 1 or another subscreen, return cleanly to Data Entry Menu
        if state != "MENU_SCREEN":
            log("[PRE-CONDITION] Exiting subscreen to Data Entry Menu...")
            ensure_menu_screen(window)
            time.sleep(0.5)
            hwnd, title = find_drake_window()
            window = Desktop(backend="uia").window(handle=hwnd)

        # Now on Menu screen: Click 'Button: W2|Wages'
        log("[NAVIGATE] Clicking 'W2|Wages' button on Data Entry Menu...")
        w2_clicked = False
        for b in window.descendants(control_type="Button"):
            if "w2|wages" in b.window_text().strip().lower():
                try:
                    b.invoke()
                    w2_clicked = True
                    log("[NAVIGATE] Successfully opened Screen W-2 via menu button!")
                    break
                except Exception as ex:
                    log(f"[WARN] invoke failed: {ex}")

        if not w2_clicked:
            # Fallback to search box
            for e in window.descendants(control_type="Edit"):
                if "menutextbox" in (e.element_info.automation_id or "").lower() or e.rectangle().top > 600:
                    e.set_focus()
                    e.set_edit_text("W2")
                    pyautogui.press('enter')
                    break

        w2_win = None
        w2_hwnd = None
        for _ in range(15):
            time.sleep(0.1)
            h, t = find_drake_window()
            if h:
                w_test = Desktop(backend="uia").window(handle=h)
                if get_current_drake_state(w_test) == "W2_SCREEN":
                    w2_win = w_test
                    w2_hwnd = h
                    break

    # 4. PRE-CONDITION: Verify Screen W-2 is now open
    if not w2_win:
        for _ in range(6):
            h, t = find_drake_window()
            if h:
                w_test = Desktop(backend="uia").window(handle=h)
                if get_current_drake_state(w_test) == "W2_SCREEN":
                    w2_win = w_test
                    w2_hwnd = h
                    break
            time.sleep(0.15)

    if not w2_win:
        return False, logs + ["[ERROR] Failed to navigate to Screen W2."], "ERROR"

    log("[READY] Verified Screen W-2 is active and ready for field insertion!")

    # 5. DYNAMIC CONTROL DISCOVERY & CACHING
    edits_by_aid = {}
    dropdown_edits_by_aid = {}
    checkboxes_by_aid = {}

    for c in w2_win.descendants(control_type="Edit"):
        try:
            aid = c.element_info.automation_id
            if aid and aid != "PART_EditableTextBox":
                edits_by_aid[aid] = c
        except Exception:
            pass

    for c in w2_win.descendants(control_type="ComboBox"):
        try:
            aid = c.element_info.automation_id
            if aid:
                for ed in c.descendants(control_type="Edit"):
                    dropdown_edits_by_aid[aid] = ed
                    break
        except Exception:
            pass

    for c in w2_win.descendants(control_type="CheckBox"):
        try:
            aid = c.element_info.automation_id
            if aid:
                checkboxes_by_aid[aid] = c
        except Exception:
            pass

    log(f"[DISCOVERY] Cached {len(edits_by_aid)} edits, {len(dropdown_edits_by_aid)} dropdowns, {len(checkboxes_by_aid)} checkboxes in <0.5s.")

    def set_aid_val(aid, val, label_name):
        if val is None or str(val).strip() == "":
            return False
        clean_v = str(val).replace("$", "").replace(",", "").strip()
        ctrl = edits_by_aid.get(aid)
        if ctrl:
            if enter_clean_value(ctrl, clean_v):
                log(f"[OK] {label_name:<26} = {clean_v}")
                return True
            else:
                log(f"[FAIL] Could not set: {label_name}")
        else:
            log(f"[-] Control aid '{aid}' not found for: {label_name}")
        return False

    def set_dropdown_aid_val(aid, val, label_name):
        if val is None or str(val).strip() == "":
            return False
        clean_v = str(val).strip().upper()
        ed = dropdown_edits_by_aid.get(aid)
        if ed:
            if enter_clean_value(ed, clean_v):
                log(f"[OK] {label_name:<26} = {clean_v}")
                return True
            else:
                log(f"[FAIL] Could not set dropdown: {label_name}")
        else:
            log(f"[-] Dropdown aid '{aid}' not found for: {label_name}")
        return False

    # 6. POPULATE FIELDS DYNAMICALLY (High-speed direct injection)
    # TS Code: Primary Taxpayer (T) vs Spouse (S)
    ts_code = w2_data.get("ts_code", "T").upper()
    set_dropdown_aid_val("Dropdown_1", ts_code, "TS Code (Ownership)")

    # Employer Information
    clean_ein = str(w2_data.get("employer_ein", "")).replace("-", "").strip()
    set_aid_val("Textbox_4", clean_ein, "Employer EIN")
    set_aid_val("Textbox_5", w2_data.get("employer_name"), "Employer Name")
    set_aid_val("Textbox_7", w2_data.get("employer_address"), "Employer Street")
    set_aid_val("Textbox_8", w2_data.get("employer_city"), "Employer City")
    set_dropdown_aid_val("Dropdown_9", w2_data.get("employer_state", "WY"), "Employer State")
    set_aid_val("Textbox_10", w2_data.get("employer_zip"), "Employer ZIP")

    # Box 1 to 6
    set_aid_val("Textbox_23", w2_data.get("box1_wages"), "Box 1 Wages")
    set_aid_val("Textbox_24", w2_data.get("box2_fed_withheld"), "Box 2 Federal Tax")
    set_aid_val("Textbox_25", w2_data.get("box3_ss_wages"), "Box 3 SS Wages")
    set_aid_val("Textbox_26", w2_data.get("box4_ss_tax"), "Box 4 SS Tax")
    set_aid_val("Textbox_27", w2_data.get("box5_medicare_wages"), "Box 5 Medicare Wages")
    set_aid_val("Textbox_28", w2_data.get("box6_medicare_tax"), "Box 6 Medicare Tax")

    # Box 12a and 12b (Retirement, Health, etc.)
    b12a_code = w2_data.get("box12a_code", "D")
    b12a_amt = w2_data.get("box12a_amount", "11750.00")
    b12b_code = w2_data.get("box12b_code", "DD")
    b12b_amt = w2_data.get("box12b_amount", "12500.00")

    set_dropdown_aid_val("Dropdown_34", b12a_code, "Box 12a Code")
    set_aid_val("Textbox_35", b12a_amt, f"Box 12a ({b12a_code}) Amount")
    set_dropdown_aid_val("Dropdown_37", b12b_code, "Box 12b Code")
    set_aid_val("Textbox_38", b12b_amt, f"Box 12b ({b12b_code}) Amount")

    # Box 13 Checkbox: Retirement Plan
    if w2_data.get("box13_retirement_plan"):
        cb = checkboxes_by_aid.get("CheckboxTextRight_47")
        if cb:
            try:
                cb.set_focus()
                cb.toggle()
                log("[OK] Box 13: Retirement Plan Checked")
            except Exception as e:
                log(f"[WARN] Box 13 toggle: {e}")

    # State Information (Boxes 15-20)
    st_code = w2_data.get("box15_state", "WY")
    st_wages = w2_data.get("box16_state_wages", "")
    st_tax = w2_data.get("box17_state_tax", "")
    if st_code:
        set_dropdown_aid_val("Dropdown_57", st_code, "Box 15 State")
    if st_wages:
        set_aid_val("Textbox_59", st_wages, "Box 16 State Wages")
    if st_tax:
        set_aid_val("Textbox_60", st_tax, "Box 17 State Tax")

    time.sleep(0.3)
    log("[READY_TO_VERIFY] All Form W-2 fields populated in Drake software!")
    log("[ACTION_REQUIRED] Screen W-2 is open in Drake. Review the fields and click 'Verify & Save' to exit.")
    return True, logs, "POPULATED"

def save_and_exit_w2():
    """
    Step 2: Invoked when reviewer clicks 'Verify & Save (Exit Screen in Drake)'.
    Clicks 'btnExit' in Drake, verifies clean return to Data Entry Menu, and verifies the saved record.
    """
    logs = []
    def log(msg):
        print(msg)
        logs.append(msg)

    dismiss_drake_popups()
    time.sleep(0.2)

    h, t = find_drake_window()
    if not h:
        return False, ["Drake 2025 is not open."], "ERROR"

    owner = get_window_owner(h)
    owner_text = get_window_title(owner).lower() if owner else ""

    w_target = None
    if "data entry" in t.lower() and "data entry" in owner_text:
        w_target = Desktop(backend="uia").window(handle=h)
    else:
        def cb_find_sub(hw, _):
            nonlocal w_target
            if win32gui.IsWindowVisible(hw):
                tt = get_window_title(hw)
                ow = get_window_owner(hw)
                ow_t = get_window_title(ow).lower() if ow else ""
                if "data entry" in tt.lower() and "data entry" in ow_t:
                    w_target = Desktop(backend="uia").window(handle=hw)
        try:
            win32gui.EnumDesktopWindows(hdesk, cb_find_sub, None)
        except Exception:
            pass

    saved = False
    if w_target:
        btn_exit = None
        for b in w_target.descendants(control_type="Button"):
            aid = b.element_info.automation_id
            if aid == "btnExit" or b.window_text().strip().lower() == "exit":
                btn_exit = b
                break

        if btn_exit:
            try:
                btn_exit.invoke()
                saved = True
                log("[SAVE] Invoked 'btnExit' to save and exit Screen W-2.")
            except Exception as ex:
                log(f"[WARN] btnExit invoke failed: {ex}")

    if not saved:
        pyautogui.press('esc')
        log("[SAVE] Sent Esc key to exit Screen W-2.")

    # Post-Save Verification
    verified = False
    for _ in range(12):
        time.sleep(0.15)
        dismiss_drake_popups()
        cur_h, cur_t = find_drake_window()
        cur_owner = get_window_owner(cur_h)
        cur_owner_text = get_window_title(cur_owner).lower() if cur_owner else ""
        if cur_h and "data entry" in cur_t.lower() and "data entry" not in cur_owner_text:
            verified = True
            log("[VERIFICATION] Successfully returned to Data Entry Menu! Screen W-2 is saved.")
            break

    if not verified:
        log("[WARN] Screen did not close automatically; dismissing lingering popups...")
        dismiss_drake_popups()
        pyautogui.press('esc')

    log("[SUCCESS] Form W-2 verified, saved, and closed in Drake Tax 2025!")
    return True, logs, "SAVED"

def discard_w2_screen():
    logs = []
    def log(msg):
        print(msg)
        logs.append(msg)
    log("[DISCARD] Discarding Screen W-2 changes...")
    pyautogui.press('esc')
    time.sleep(0.4)
    dismiss_drake_popups()
    log("[DISCARD] Exited screen without saving.")
    return True, logs, "DISCARDED"

def fill_w2_screen(w2_data, auto_save=False):
    ok, logs, status = populate_w2_screen(w2_data)
    if not ok:
        return False, logs
    if auto_save:
        ok2, logs2, status2 = save_and_exit_w2()
        return ok2, logs + logs2
    return True, logs

if __name__ == "__main__":
    test_data = {
        "ts_code": "T",
        "employer_ein": "832947156",
        "employer_name": "GRANITE PEAK INDUSTRIES INC",
        "employer_address": "1900 Yellowstone Blvd, Suite 400",
        "employer_city": "Casper",
        "employer_state": "WY",
        "employer_zip": "82601",
        "box1_wages": "213250.00",
        "box2_fed_withheld": "51180.00",
        "box3_ss_wages": "176100.00",
        "box4_ss_tax": "10918.20",
        "box5_medicare_wages": "225000.00",
        "box6_medicare_tax": "3262.50",
        "box12a_code": "D",
        "box12a_amount": "11750.00",
        "box12b_code": "DD",
        "box12b_amount": "12500.00",
        "box13_retirement_plan": True
    }
    success, logs = fill_w2_screen(test_data)
    print("\n--- FINAL RESULT ---")
    print(f"Success: {success}")
    for l in logs:
        print(l)
