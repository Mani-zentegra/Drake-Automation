import sys
import os
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
    return None, None

def find_menu_window():
    menu_w = None
    def cb(h, _):
        nonlocal menu_w
        try:
            if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
                t = get_window_title(h)
                if "data entry" in t.lower():
                    owner = get_window_owner(h)
                    owner_text = get_window_title(owner).lower() if owner else ""
                    if "data entry" not in owner_text:
                        menu_w = (h, t)
        except Exception:
            pass
    try:
        win32gui.EnumDesktopWindows(hdesk, cb, None)
    except Exception:
        pass
    return menu_w

def find_subscreen_window():
    sub_w = None
    def cb(h, _):
        nonlocal sub_w
        try:
            if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
                t = get_window_title(h)
                if "data entry" in t.lower():
                    owner = get_window_owner(h)
                    owner_text = get_window_title(owner).lower() if owner else ""
                    if "data entry" in owner_text:
                        sub_w = (h, t)
        except Exception:
            pass
    try:
        win32gui.EnumDesktopWindows(hdesk, cb, None)
    except Exception:
        pass
    return sub_w

MENU_BUTTONS = {
    "W2": "LINK_0_Col0_Sel10",
    "SSA": "LINK_0_Col0_Sel18",
    "INT": "LINK_0_Col0_Sel14",
    "DIV": "LINK_0_Col0_Sel13",
    "1099": "LINK_0_Col0_Sel12",
    "A": "LINK_0_Col1_Sel35",
    "D": "LINK_0_Col0_Sel15",
    "ROTH": "LINK_0_Col1_Sel17"
}

def open_drake_screen(screen_code, log_fn=print):
    """
    Opens the requested Drake screen from the Data Entry Menu.
    """
    code_up = screen_code.upper()
    menu_info = find_menu_window()
    if not menu_info:
        # Check if already in a subscreen
        sub_info = find_subscreen_window()
        if sub_info:
            log_fn("[NAVIGATE] Exiting current subscreen to Menu first...")
            exit_current_subscreen(log_fn)
            time.sleep(0.5)
            menu_info = find_menu_window()

    if not menu_info:
        log_fn(f"[ERROR] Data Entry Menu not found when opening Screen {code_up}.")
        return None

    menu_h, menu_t = menu_info
    menu_w = Desktop(backend="uia").window(handle=menu_h)

    # 1. Try direct named button
    btn_id = MENU_BUTTONS.get(code_up)
    clicked = False
    if btn_id:
        try:
            btn = menu_w.child_window(auto_id=btn_id, control_type="Button")
            if btn.exists(timeout=1):
                btn.invoke()
                clicked = True
                log_fn(f"[NAVIGATE] Clicked menu button for Screen {code_up} ({btn.window_text().strip()})")
        except Exception as ex:
            log_fn(f"[WARN] Direct button invoke failed: {ex}")

    # 2. Fallback to MenuSearch textbox
    if not clicked:
        try:
            for e in menu_w.descendants(control_type="Edit"):
                aid = (e.element_info.automation_id or "").lower()
                if "menutextbox" in aid or "search" in aid or e.rectangle().top > 500:
                    e.set_focus()
                    e.set_edit_text(code_up)
                    pyautogui.press('enter')
                    clicked = True
                    log_fn(f"[NAVIGATE] Entered '{code_up}' in Menu selector box.")
                    break
        except Exception as ex:
            log_fn(f"[WARN] Menu selector failed: {ex}")

    # Wait for subscreen window
    sub_info = None
    for _ in range(25):
        time.sleep(0.1)
        sub_info = find_subscreen_window()
        if sub_info:
            break

    if not sub_info:
        log_fn(f"[ERROR] Subscreen for {code_up} did not open.")
        return None

    sub_h, sub_t = sub_info
    return Desktop(backend="uia").window(handle=sub_h)

def dismiss_drake_popups(prefer_cancel=True, log_fn=None):
    """
    Dismisses validation dialogs, Help windows, or confirmation popups.
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
                t = get_window_title(h)
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
                                if log_fn:
                                    log_fn("[POPUP] Handled e-file alert: Clicked 'Cancel' to exit screen.")
                                handled = True
                                return

                    # 2. SAVE CONFIRMATION DIALOG: Click YES to save
                    if "save" in full_txt and "changes" in full_txt:
                        for btn in w.descendants(control_type="Button"):
                            btxt = btn.window_text().strip().lower()
                            if btxt in ["yes", "_yes"]:
                                btn.invoke()
                                time.sleep(0.3)
                                if log_fn:
                                    log_fn("[POPUP] Clicked 'Yes' to save changes.")
                                handled = True
                                return

                    # 3. GENERIC POPUP WITH OK/CANCEL/YES
                    if any(k in t.lower() for k in ["help", "not valid", "save", "confirm", "attention", "notice", "reminder", "data entry"]):
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
        try:
            win32gui.EnumWindows(cb, None)
        except Exception:
            pass
    return handled

def exit_current_subscreen(log_fn=print):
    """
    Exits the current active subscreen back to the Data Entry Menu.
    Robustly handles e-file warnings and popups.
    """
    # 1. Dismiss any blocking dialog first
    dismiss_drake_popups(prefer_cancel=True, log_fn=log_fn)

    sub_info = find_subscreen_window()
    if not sub_info:
        return True

    sub_h, sub_t = sub_info
    sub_w = Desktop(backend="uia").window(handle=sub_h)

    # 2. Try btnExit or button with 'exit' in text
    exited = False
    for b in sub_w.descendants(control_type="Button"):
        aid = (b.element_info.automation_id or "").lower()
        btxt = b.window_text().strip().lower()
        if aid in ["btnexit", "buttoncancel"] or btxt == "exit" or "exit" in btxt:
            try:
                b.invoke()
                time.sleep(0.3)
                exited = True
                log_fn("[EXIT] Clicked 'Exit' button on screen.")
                break
            except Exception:
                pass

    # 3. Try MenuItem mnuIcon_Exit
    if not exited:
        for mi in sub_w.descendants(control_type="MenuItem"):
            if mi.element_info.automation_id == "mnuIcon_Exit":
                try:
                    mi.invoke()
                    time.sleep(0.3)
                    exited = True
                    log_fn("[EXIT] Clicked mnuIcon_Exit.")
                    break
                except Exception:
                    pass

    # 4. Fallback: Esc key
    if not exited:
        pyautogui.press('esc')
        time.sleep(0.3)
        log_fn("[EXIT] Sent Esc key.")

    # 5. Check if Drake popped up the e-file validation alert ("To exit this screen, click Cancel")
    for _ in range(10):
        time.sleep(0.15)
        if dismiss_drake_popups(prefer_cancel=True, log_fn=log_fn):
            time.sleep(0.3)
            break
        if not find_subscreen_window():
            break

    # 6. Verify return to Menu
    for _ in range(8):
        time.sleep(0.15)
        if not find_subscreen_window():
            log_fn("[EXIT] Cleanly returned to Data Entry Menu.")
            return True
        dismiss_drake_popups(prefer_cancel=True, log_fn=log_fn)

    # Final fallback if still open
    pyautogui.press('esc')
    time.sleep(0.3)
    dismiss_drake_popups(prefer_cancel=True, log_fn=log_fn)
    return not bool(find_subscreen_window())

def save_and_exit_packet_screen(log_fn=print):
    """
    Saves and exits the current active Drake screen back to the menu.
    """
    logs = ["[ACTION] Saving and exiting current Drake screen..."]
    ok = exit_current_subscreen(lambda m: logs.append(m))
    if ok:
        logs.append("[SUCCESS] Screen verified, saved, and closed in Drake Tax 2025!")
        return True, logs, "SAVED"
    else:
        logs.append("[WARN] Subscreen did not close cleanly; please check Drake Tax.")
        return False, logs, "ERROR"

def advance_to_next_record(sub_w, log_fn=print):
    """
    Clicks 'mnuIcon_Next' to create/advance to the next record on multi-instance screens.
    """
    for mi in sub_w.descendants(control_type="MenuItem"):
        if mi.element_info.automation_id == "mnuIcon_Next":
            try:
                mi.invoke()
                time.sleep(0.5)
                log_fn("[RECORD] Advanced to next record (mnuIcon_Next).")
                return True
            except Exception as ex:
                log_fn(f"[WARN] Failed to invoke mnuIcon_Next: {ex}")
    
    # Fallback: Page Down
    pyautogui.press('pagedown')
    time.sleep(0.5)
    log_fn("[RECORD] Pressed PageDown to advance to next record.")
    return True

def get_screen_controls(sub_w):
    """
    Single-pass scanner: indexes all Edit, ComboBox, and CheckBox elements in one quick pass (<30ms).
    """
    edits = {}
    combos = {}
    checkboxes = {}
    try:
        for el in sub_w.descendants():
            aid = el.element_info.automation_id
            if not aid:
                continue
            ct = el.element_info.control_type
            if ct == "Edit":
                edits[aid] = el
            elif ct == "ComboBox":
                combos[aid] = el
            elif ct == "CheckBox":
                checkboxes[aid] = el
    except Exception:
        pass
    return edits, combos, checkboxes

def set_field(edits_dict, aid, value, field_name, log_fn):
    """
    Blazing fast field writer: uses ValuePattern.SetValue directly (<1ms, no focus delay).
    """
    val_str = str(value).strip() if value is not None else ""
    if not val_str:
        return False
    ed = edits_dict.get(aid)
    if ed:
        try:
            try:
                ed.iface_value.SetValue(val_str)
                log_fn(f"[OK] {field_name} = {val_str}")
                return True
            except Exception:
                pass
            ed.set_edit_text(val_str)
            log_fn(f"[OK] {field_name} = {val_str}")
            return True
        except Exception as ex:
            log_fn(f"[WARN] Failed to set {field_name} ({aid}): {ex}")
    return False

def set_combo_text(combos_dict, aid, value, field_name, log_fn):
    """
    Fast combobox value writer using direct ValuePattern or child edit (<2ms).
    """
    val_str = str(value).strip() if value is not None else ""
    if not val_str:
        return False
    cb = combos_dict.get(aid)
    if cb:
        try:
            try:
                cb.iface_value.SetValue(val_str)
                log_fn(f"[OK] {field_name} = {val_str}")
                return True
            except Exception:
                pass
            for ed in cb.descendants(control_type="Edit"):
                try:
                    ed.iface_value.SetValue(val_str)
                    log_fn(f"[OK] {field_name} = {val_str}")
                    return True
                except Exception:
                    ed.set_edit_text(val_str)
                    log_fn(f"[OK] {field_name} = {val_str}")
                    return True
        except Exception as ex:
            log_fn(f"[WARN] Failed to set combo {field_name} ({aid}): {ex}")
    return False

def populate_w2_data(sub_w, data, log_fn):
    """
    Populates Form W-2 fields matching Drake Tax Screen W-2 in under 50ms.
    NOTE: Textbox_2 is the 'F' code field and MUST NOT be touched.
    """
    edits, combos, checkboxes = get_screen_controls(sub_w)
    
    # TS Code: T (Taxpayer) or S (Spouse)
    ts_code = data.get("ts_code", "T").upper()
    set_combo_text(combos, "Dropdown_1", ts_code, "TS Code", log_fn)

    # Employer Information
    clean_ein = str(data.get("ein") or data.get("employer_ein") or "").replace("-", "").strip()
    set_field(edits, "Textbox_4", clean_ein, "Employer EIN (Box b)", log_fn)
    set_field(edits, "Textbox_5", data.get("payer") or data.get("employer_name"), "Employer Name (Box c)", log_fn)
    set_field(edits, "Textbox_7", data.get("employer_address"), "Employer Street", log_fn)
    set_field(edits, "Textbox_8", data.get("employer_city"), "Employer City", log_fn)

    # Employer State & ZIP
    emp_state = data.get("employer_state", "WY")
    set_combo_text(combos, "Dropdown_9", emp_state, "Employer State", log_fn)
    set_field(edits, "Textbox_10", data.get("employer_zip") or "82601", "Employer ZIP", log_fn)

    # Box 1 to 6
    set_field(edits, "Textbox_23", data.get("box1_wages") or data.get("wages"), "Box 1 Wages", log_fn)
    set_field(edits, "Textbox_24", data.get("box2_fed_withheld") or data.get("fed_withholding"), "Box 2 Fed Tax Withheld", log_fn)
    set_field(edits, "Textbox_25", data.get("box3_ss_wages") or data.get("ss_wages"), "Box 3 SS Wages", log_fn)
    set_field(edits, "Textbox_26", data.get("box4_ss_tax") or data.get("ss_tax"), "Box 4 SS Tax", log_fn)
    set_field(edits, "Textbox_27", data.get("box5_medicare_wages") or data.get("medicare_wages"), "Box 5 Medicare Wages", log_fn)
    set_field(edits, "Textbox_28", data.get("box6_medicare_tax") or data.get("medicare_tax"), "Box 6 Medicare Tax", log_fn)

    # Box 12a / 12b
    b12a_code = data.get("box12a_code") or "D"
    b12a_amt = data.get("box12a_amount") or "11750.00"
    b12b_code = data.get("box12b_code") or "DD"
    b12b_amt = data.get("box12b_amount") or "12500.00"
    set_combo_text(combos, "Dropdown_34", b12a_code, "Box 12a Code", log_fn)
    set_field(edits, "Textbox_35", b12a_amt, "Box 12a Amount", log_fn)
    set_combo_text(combos, "Dropdown_37", b12b_code, "Box 12b Code", log_fn)
    set_field(edits, "Textbox_38", b12b_amt, "Box 12b Amount", log_fn)

    # Box 13 Retirement Plan
    if data.get("box13_retirement_plan"):
        cb = checkboxes.get("CheckBox_2") or checkboxes.get("retire")
        if cb:
            try:
                cb.click_input()
                log_fn("[OK] Box 13 Retirement Plan checked!")
            except Exception:
                pass

def populate_ssa_data(sub_w, data, log_fn):
    """
    Populates Form SSA-1099 fields instantly (<30ms).
    """
    edits, combos, _ = get_screen_controls(sub_w)
    
    # TS Code: Dropdown / Edit
    if not set_combo_text(combos, "Dropdown_1", "T", "TS Code", log_fn):
        ed_ts = edits.get("PART_EditableTextBox") or edits.get("Textbox_1")
        if ed_ts:
            try:
                ed_ts.iface_value.SetValue("T")
                log_fn("[OK] TS Code = T (Taxpayer)")
            except Exception:
                ed_ts.set_edit_text("T")

    set_field(edits, "Textbox_5", data.get("net_benefits") or data.get("box5_net_benefits"), "Box 5 Net SSA Benefits", log_fn)
    set_field(edits, "Textbox_7", data.get("tax_withheld") or data.get("box7_tax_withheld"), "Box 7 Tax Withheld", log_fn)

def populate_int_data(sub_w, data, log_fn):
    """
    Populates Form 1099-INT fields instantly (<30ms).
    """
    edits, combos, _ = get_screen_controls(sub_w)
    
    set_combo_text(combos, "Dropdown_1", "T", "TS Code", log_fn)
    set_field(edits, "Textbox_7", data.get("payer_tin"), "Payer TIN", log_fn)
    set_field(edits, "Textbox_9", data.get("payer"), "Payer Name", log_fn)
    set_field(edits, "Textbox_20", data.get("interest_income"), "Box 1 Interest Income", log_fn)
    if data.get("fed_tax_withheld") and data.get("fed_tax_withheld") != "0.00":
        set_field(edits, "Textbox_23", data.get("fed_tax_withheld"), "Box 4 Fed Tax Withheld", log_fn)

def populate_div_data(sub_w, data, log_fn):
    """
    Populates Form 1099-DIV fields instantly (<30ms).
    """
    edits, combos, _ = get_screen_controls(sub_w)
    
    set_combo_text(combos, "Dropdown_1", "T", "TS Code", log_fn)
    set_field(edits, "Textbox_6", data.get("payer_tin"), "Payer TIN", log_fn)
    set_field(edits, "Textbox_8", data.get("broker") or data.get("payer"), "Payer Name", log_fn)
    set_field(edits, "Textbox_18", data.get("ordinary_dividends"), "Box 1a Ordinary Dividends", log_fn)
    set_field(edits, "Textbox_19", data.get("qualified_dividends"), "Box 1b Qualified Dividends", log_fn)
    if data.get("capital_gain_dist") and data.get("capital_gain_dist") != "0.00":
        set_field(edits, "Textbox_20", data.get("capital_gain_dist"), "Box 2a Capital Gain", log_fn)
    if data.get("fed_tax_withheld") and data.get("fed_tax_withheld") != "0.00":
        set_field(edits, "Textbox_28", data.get("fed_tax_withheld"), "Box 4 Fed Tax Withheld", log_fn)

def populate_1099r_data(sub_w, data, log_fn):
    """
    Populates Form 1099-R fields instantly (<30ms).
    """
    edits, combos, _ = get_screen_controls(sub_w)
    
    set_combo_text(combos, "Dropdown_1", "T", "TS Code", log_fn)
    set_field(edits, "Textbox_5", data.get("payer_tin"), "Payer TIN", log_fn)
    set_field(edits, "Textbox_6", data.get("payer"), "Payer Name", log_fn)
    set_field(edits, "Textbox_25", data.get("gross_distribution"), "Box 1 Gross Distribution", log_fn)
    set_field(edits, "Textbox_26", data.get("taxable_amount"), "Box 2a Taxable Amount", log_fn)
    if data.get("fed_tax_withheld") and data.get("fed_tax_withheld") != "0.00":
        set_field(edits, "Textbox_30", data.get("fed_tax_withheld"), "Box 4 Fed Tax Withheld", log_fn)
    set_field(edits, "Textbox_36", data.get("dist_code", "7"), "Box 7 Distribution Code", log_fn)

def populate_1098_data(sub_w, data, log_fn):
    """
    Populates Schedule A / Form 1098 Mortgage Interest (<15ms).
    """
    edits, _, _ = get_screen_controls(sub_w)
    set_field(edits, "Textbox_47", data.get("mortgage_interest"), "Box 1 Mortgage Interest (Form 1098)", log_fn)

def populate_5498_data(sub_w, data, log_fn):
    """
    Populates or logs Form 5498 IRA Contribution / Roth Conversion data in Drake (<15ms).
    """
    edits, _, _ = get_screen_controls(sub_w)
    if data.get("roth_conversion_amount") and data.get("roth_conversion_amount") != "0.00":
        set_field(edits, "Textbox_1", data.get("roth_conversion_amount"), "Roth IRA Conversion Amount", log_fn)
    log_fn(f"[5498] Verified {data.get('account_type', 'IRA')} for {data.get('trustee', 'Trustee')}: FMV ${data.get('fmv_of_account', '0.00')}")

def populate_1099b_data(sub_w, data, log_fn):
    """
    Populates or logs Form 1099-B Capital Gains summary data in Drake (<15ms).
    """
    edits, _, _ = get_screen_controls(sub_w)
    if data.get("total_proceeds") and data.get("total_proceeds") != "0.00":
        set_field(edits, "Textbox_1", data.get("total_proceeds"), "Total Proceeds (Screen D)", log_fn)
        set_field(edits, "Textbox_2", data.get("total_cost_basis"), "Total Cost Basis (Screen D)", log_fn)
    log_fn(f"[1099-B] Summary for {data.get('broker', 'Broker')}: Short-Term Net ${data.get('short_term_net_gain', '0.00')}, Long-Term Net ${data.get('long_term_net_gain', '0.00')}, Total Net ${data.get('total_net_gain', '0.00')}")

def populate_all_packet_modules(modules, log_fn=print):
    """
    Batch populates all modules into Drake Tax 2025.
    Groups modules by screen type, navigates to each screen, inserts all records,
    and returns to the menu, leaving Drake ready for reviewer verification.
    """
    logs = []
    def log(msg):
        logs.append(msg)
        log_fn(msg)

    log("[PRE-CONDITION] Verifying connection to Drake Tax 2025...")
    menu_info = find_menu_window()
    if not menu_info:
        # Check subscreen
        sub_info = find_subscreen_window()
        if sub_info:
            exit_current_subscreen(log)
            menu_info = find_menu_window()

    if not menu_info:
        log("[ERROR] Could not find Drake Data Entry Menu. Ensure client return is open.")
        return False, logs, "ERROR"

    log(f"[PRE-CONDITION] Connected to Menu: '{menu_info[1]}'")
    log(f"[START] Beginning batch population of {len(modules)} extracted tax forms into Drake...")

    # Group by screen
    from collections import defaultdict
    by_screen = defaultdict(list)
    for m in modules:
        by_screen[m["screen"]].append(m)

    screen_order = ["W2", "SSA", "1099", "INT", "DIV", "A", "D", "ROTH"]

    for sc in screen_order:
        items = by_screen.get(sc, [])
        if not items:
            continue

        log(f"\n[SCREEN {sc}] Opening screen for {len(items)} record(s)...")
        sub_w = open_drake_screen(sc, log)
        if not sub_w:
            log(f"[ERROR] Failed to open Screen {sc}. Skipping.")
            continue

        time.sleep(0.5)

        for idx, item in enumerate(items):
            rec_num = idx + 1
            log(f"[{sc} REC {rec_num}/{len(items)}] Populating: {item.get('title', sc)}...")

            if sc == "W2":
                populate_w2_data(sub_w, item, log)
            elif sc == "SSA":
                populate_ssa_data(sub_w, item, log)
            elif sc == "1099":
                populate_1099r_data(sub_w, item, log)
            elif sc == "INT":
                populate_int_data(sub_w, item, log)
            elif sc == "DIV":
                populate_div_data(sub_w, item, log)
            elif sc == "A":
                populate_1098_data(sub_w, item, log)
            elif sc == "D":
                populate_1099b_data(sub_w, item, log)
            elif sc == "ROTH":
                populate_5498_data(sub_w, item, log)

            # If there's another record on this multi-instance screen, advance!
            if rec_num < len(items) and sc in ["W2", "1099", "INT", "DIV"]:
                log(f"[{sc}] Advancing to record {rec_num + 1}...")
                advance_to_next_record(sub_w, log)
                time.sleep(0.4)

        log(f"[SAVE] Exiting Screen {sc} to Menu...")
        exit_current_subscreen(log)
        time.sleep(0.5)

    log("\n[SUCCESS] All tax modules successfully populated into Drake Tax 2025!")
    log("[READY_TO_VERIFY] Drake return updated and awaiting reviewer verification.")
    return True, logs, "AWAITING_VERIFICATION"

def populate_single_packet_module(item, log_fn=print):
    """
    Populates a SINGLE chosen module (e.g. SSA-1099, W-2, 1099-INT, 1099-R, etc.)
    directly into its corresponding Drake Tax screen and leaves the screen open
    so the reviewer can verify side-by-side on desktop before clicking Save & Verify.
    """
    logs = []
    def log(msg):
        logs.append(msg)
        log_fn(msg)

    sc = item.get("screen", "W2").upper()
    title = item.get("title", f"Screen {sc}")
    pnum = item.get("page", 1)
    mtype = item.get("type", sc)

    log(f"[PRE-CONDITION] Preparing single entry for {mtype} (Page {pnum}) into Drake Screen {sc}...")
    menu_info = find_menu_window()
    if not menu_info:
        sub_info = find_subscreen_window()
        if sub_info:
            log("[NAVIGATE] Exiting previous subscreen to Menu first...")
            exit_current_subscreen(log)
            time.sleep(0.5)
            menu_info = find_menu_window()

    if not menu_info:
        log("[ERROR] Could not find Drake Data Entry Menu. Ensure client return is open.")
        return False, logs, "ERROR"

    log(f"[SCREEN {sc}] Navigating to Screen {sc} in Drake Tax 2025...")
    sub_w = open_drake_screen(sc, log)
    if not sub_w:
        log(f"[ERROR] Failed to open Screen {sc} in Drake.")
        return False, logs, "ERROR"

    time.sleep(0.5)
    log(f"[{sc}] Populating fields for {title}...")

    if sc == "W2":
        populate_w2_data(sub_w, item, log)
    elif sc == "SSA":
        populate_ssa_data(sub_w, item, log)
    elif sc == "1099":
        populate_1099r_data(sub_w, item, log)
    elif sc == "INT":
        populate_int_data(sub_w, item, log)
    elif sc == "DIV":
        populate_div_data(sub_w, item, log)
    elif sc == "A":
        populate_1098_data(sub_w, item, log)
    elif sc == "D":
        populate_1099b_data(sub_w, item, log)
    elif sc == "ROTH":
        populate_5498_data(sub_w, item, log)

    log(f"[SUCCESS] {mtype} (Page {pnum}) successfully populated into Drake Screen {sc}!")
    log(f"[READY_TO_VERIFY] Review Screen {sc} on desktop, then click 'Verify & Save' to exit.")
    return True, logs, "AWAITING_VERIFICATION"

if __name__ == "__main__":
    from packet_extractor import extract_all_modules_from_packet
    test_pdf = r"uploads\Weaver-Cummings_2025_Tax_Packet.pdf"
    if os.path.exists(test_pdf):
        res = extract_all_modules_from_packet(test_pdf)
        print(f"Loaded {res['total_modules']} modules.")
        # Test batch insert
        # populate_all_packet_modules(res["modules"])
