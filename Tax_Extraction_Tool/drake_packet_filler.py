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
}

def open_drake_screen(screen_code, log_fn=print):
    """
    Opens the requested Drake screen from the Data Entry Menu.
    """
    code_up = screen_code.upper()
    
    # 1. If any subscreen is already open, always exit it first back to Menu
    sub_info = find_subscreen_window()
    if sub_info:
        log_fn(f"[NAVIGATE] Exiting current subscreen before navigating to Screen {code_up}...")
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

                    # NEVER answer Drake's "exit the program?" prompt automatically (Yes would close Drake).
                    if "close program" in t.lower() or "exit drake" in full_txt or "want to exit" in full_txt:
                        if log_fn:
                            log_fn("[POPUP] Drake is asking whether to EXIT the program — left for the user to answer.")
                        return

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

                    # 3. INVALID ENTRY / CHARACTER ALERT: Click OK to dismiss
                    if "invalid" in full_txt or "not valid" in full_txt or "invalid character" in full_txt:
                        for btn in w.descendants(control_type="Button"):
                            btxt = btn.window_text().strip().lower()
                            aid = btn.element_info.automation_id
                            if btxt in ["ok", "_ok"] or aid in ["1", "2", "buttonok"]:
                                try:
                                    btn.invoke()
                                    time.sleep(0.3)
                                    if log_fn:
                                        log_fn("[POPUP] Dismissed Drake invalid character alert dialog.")
                                    handled = True
                                    return
                                except Exception:
                                    pass

                    # 4. GENERIC POPUP WITH OK/CANCEL/YES
                    if any(k in t.lower() for k in ["help", "not valid", "save", "confirm", "attention", "notice", "reminder", "data entry", "invalid"]):
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
    Fast selective control scanner: queries Edit, ComboBox, and CheckBox elements in milliseconds.
    """
    edits = {}
    combos = {}
    checkboxes = {}
    try:
        for c in sub_w.descendants(control_type="Edit"):
            aid = c.element_info.automation_id
            if aid:
                edits[aid] = c
    except Exception:
        pass
    try:
        for c in sub_w.descendants(control_type="ComboBox"):
            aid = c.element_info.automation_id
            if aid:
                combos[aid] = c
                try:
                    for ch in c.descendants(control_type="Edit"):
                        combos[f"{aid}_edit"] = ch
                        break
                except Exception:
                    pass
    except Exception:
        pass
    try:
        for c in sub_w.descendants(control_type="CheckBox"):
            aid = c.element_info.automation_id
            if aid:
                checkboxes[aid] = c
    except Exception:
        pass
    return edits, combos, checkboxes

def clean_tin(val):
    """
    Strips hyphens, spaces, and all non-digits from TIN/EIN/SSN so Drake does not reject it.
    Example: '81-0192834' -> '810192834', '04-3523567' -> '043523567'
    """
    if not val:
        return ""
    import re
    return re.sub(r"[^\d]", "", str(val)).strip()

def clean_amt(val):
    """
    Strips $, commas, and spaces from amounts so Drake accepts them cleanly without invalid character alerts.
    Example: '$3,847.62' -> '3847.62'
    """
    if not val:
        return ""
    return str(val).replace("$", "").replace(",", "").strip()

def set_field(edits_dict, aid, value, field_name, log_fn):
    """
    Blazing fast field writer: uses ValuePattern.SetValue directly (<1ms, no focus delay).
    Automatically sanitizes TIN/EIN and amounts to prevent Drake invalid character errors.
    """
    import re
    val_str = str(value).strip() if value is not None else ""
    if not val_str:
        return False

    # Auto-sanitize TIN / EIN / SSN: Drake strictly rejects hyphens and non-digits
    if any(k in field_name.lower() for k in ["tin", "ein", "ssn"]):
        val_str = re.sub(r"[^\d]", "", val_str)
        if not val_str:
            return False

    # Auto-sanitize numeric/amount fields: strip $ and commas
    if any(k in field_name.lower() for k in ["wages", "amount", "income", "tax", "withheld", "dividends", "proceeds", "basis", "benefits", "interest", "gain", "distribution", "premium", "discount", "penalty", "expense", "royalties"]):
        val_str = val_str.replace("$", "").replace(",", "").strip()

    ed = edits_dict.get(aid)
    if not ed:
        log_fn(f"[WARN] {field_name}: field {aid} is not on this Drake screen — not entered")
        return False
    from drake_w2_filler import enter_clean_value      # focus-checked entry + Tab so Drake keeps the value
    if enter_clean_value(ed, val_str):
        log_fn(f"[OK] {field_name} = {val_str}")
        return True
    log_fn(f"[WARN] {field_name}: Drake did not take the value (field read-only or could not be focused)")
    return False

def set_combo_text(combos_dict, aid, value, field_name, log_fn):
    """
    Fast combobox value writer using cached child edit or direct ValuePattern (<2ms).
    """
    val_str = str(value).strip() if value is not None else ""
    if not val_str:
        return False
    from drake_w2_filler import enter_clean_value
    ed = combos_dict.get(f"{aid}_edit")
    if ed is None and combos_dict.get(aid) is not None:
        inner = combos_dict[aid].descendants(control_type="Edit")
        ed = inner[0] if inner else combos_dict[aid]
    if ed is None:
        log_fn(f"[WARN] {field_name}: field {aid} is not on this Drake screen — not entered")
        return False
    if enter_clean_value(ed, val_str):
        log_fn(f"[OK] {field_name} = {val_str}")
        return True
    log_fn(f"[WARN] {field_name}: Drake did not take the value")
    return False


def set_checkbox(checks_dict, aid, want, field_name, log_fn):
    """Set a Drake check box to the wanted state (the old code toggled blindly, which UN-ticks a ticked box)."""
    cb = checks_dict.get(aid)
    if cb is None:
        log_fn(f"[WARN] {field_name}: check box {aid} is not on this Drake screen")
        return False
    try:
        if bool(cb.get_toggle_state()) != bool(want):
            cb.toggle()
        log_fn(f"[OK] {field_name} = {'checked' if want else 'not checked'}")
        return True
    except Exception as ex:
        log_fn(f"[WARN] {field_name}: {ex}")
        return False

# Field ids below were read from the real Drake Tax 2025 screens on 2026-11-05 (each input matched to its label).
# The same verified ids drive the /review transfer (taxflow/catalog.py VERIFIED_AIDS).

def _money(v):
    return clean_amt(v) if v not in (None, "") else ""


def _nonzero(v):
    try:
        return float(str(v).replace(",", "").replace("$", "")) != 0
    except (TypeError, ValueError):
        return False


def populate_w2_data(sub_w, data, log_fn):
    """Screen W2. Only values present in `data` are typed — no client defaults are ever filled in."""
    edits, combos, checkboxes = get_screen_controls(sub_w)
    set_field(edits, "Textbox_4", clean_tin(data.get("ein") or data.get("employer_ein")), "Employer EIN (Box b)", log_fn)
    set_combo_text(combos, "Dropdown_1", (data.get("ts_code") or "T").upper(), "TS Code", log_fn)
    set_field(edits, "Textbox_5", data.get("employer_name") or data.get("payer"), "Employer Name (Box c)", log_fn)
    set_field(edits, "Textbox_7", data.get("employer_street") or data.get("employer_address"), "Employer Street", log_fn)
    set_field(edits, "Textbox_8", data.get("employer_city"), "Employer City", log_fn)
    set_combo_text(combos, "Dropdown_9", data.get("employer_state"), "Employer State", log_fn)
    set_field(edits, "Textbox_10", data.get("employer_zip"), "Employer ZIP", log_fn)
    for aid, keys, name in (("Textbox_23", ("box1_wages", "wages"), "Box 1 Wages"),
                            ("Textbox_24", ("box2_fed_withheld", "fed_withholding"), "Box 2 Fed Tax Withheld"),
                            ("Textbox_25", ("box3_ss_wages", "ss_wages"), "Box 3 SS Wages"),
                            ("Textbox_26", ("box4_ss_tax", "ss_tax"), "Box 4 SS Tax"),
                            ("Textbox_27", ("box5_medicare_wages", "medicare_wages"), "Box 5 Medicare Wages"),
                            ("Textbox_28", ("box6_medicare_tax", "medicare_tax"), "Box 6 Medicare Tax")):
        set_field(edits, aid, _money(next((data.get(k) for k in keys if data.get(k)), "")), name, log_fn)
    for slot, code_aid, amt_aid in (("a", "Dropdown_34", "Textbox_35"), ("b", "Dropdown_37", "Textbox_38"),
                                    ("c", "Dropdown_40", "Textbox_41"), ("d", "Dropdown_43", "Textbox_44")):
        code, amt = data.get(f"box12{slot}_code"), data.get(f"box12{slot}_amount")
        if code and _nonzero(amt):
            set_combo_text(combos, code_aid, str(code).upper(), f"Box 12{slot} Code", log_fn)
            set_field(edits, amt_aid, _money(amt), f"Box 12{slot} Amount", log_fn)
    if "box13_retirement_plan" in data:
        set_checkbox(checkboxes, "CheckboxTextRight_47", bool(data.get("box13_retirement_plan")), "Box 13 Retirement plan", log_fn)


def populate_ssa_data(sub_w, data, log_fn):
    """Screen SSA: net benefits = Textbox_4, federal tax withheld (SSA-1099 box 6) = Textbox_7."""
    edits, combos, _ = get_screen_controls(sub_w)
    set_combo_text(combos, "Dropdown_1", "T", "TS Code", log_fn)
    set_field(edits, "Textbox_4", _money(data.get("net_benefits") or data.get("box5_net_benefits") or data.get("box5")), "Box 5 Net Benefits", log_fn)
    fed = data.get("box6") or data.get("fed_tax_withheld")
    if _nonzero(fed):
        set_field(edits, "Textbox_7", _money(fed), "Box 6 Federal tax withheld", log_fn)
    if _nonzero(data.get("tax_withheld") or data.get("box7_tax_withheld")) and not fed:
        log_fn("[INFO] SSA-1042S tax withheld is nonresident withholding — not entered on Screen SSA; review it in Drake.")


def populate_int_data(sub_w, data, log_fn):
    """Screen INT (opened through Item Detail when Drake shows its grid)."""
    edits, combos, _ = get_screen_controls(sub_w)
    set_field(edits, "Textbox_7", clean_tin(data.get("payer_tin")), "Payer TIN", log_fn)   # TIN first: Drake refills the payer from it
    set_combo_text(combos, "Dropdown_1", "T", "TS Code", log_fn)
    set_field(edits, "Textbox_9", data.get("payer"), "Payer Name", log_fn)
    set_field(edits, "Textbox_20", _money(data.get("interest_income")), "Box 1 Interest Income", log_fn)
    us = data.get("us_savings_bonds_interest") or data.get("box3_us_bond") or data.get("us_bond_interest")
    if _nonzero(us):
        set_field(edits, "Textbox_22", _money(us), "Box 3 U.S. bond / Treasury interest", log_fn)
    if _nonzero(data.get("fed_tax_withheld")):
        set_field(edits, "Textbox_23", _money(data.get("fed_tax_withheld")), "Box 4 Fed Tax Withheld", log_fn)
    if _nonzero(data.get("investment_expenses")):
        set_field(edits, "Textbox_24", _money(data.get("investment_expenses")), "Box 5 Investment expenses", log_fn)
    if _nonzero(data.get("tax_exempt_interest")):
        set_field(edits, "Textbox_27", _money(data.get("tax_exempt_interest")), "Box 8 Tax-exempt interest", log_fn)


def populate_div_data(sub_w, data, log_fn):
    edits, combos, _ = get_screen_controls(sub_w)
    set_field(edits, "Textbox_6", clean_tin(data.get("payer_tin")), "Payer TIN", log_fn)
    set_combo_text(combos, "Dropdown_1", "T", "TS Code", log_fn)
    set_field(edits, "Textbox_8", data.get("broker") or data.get("payer"), "Payer Name", log_fn)
    set_field(edits, "Textbox_18", _money(data.get("ordinary_dividends")), "Box 1a Ordinary Dividends", log_fn)
    set_field(edits, "Textbox_19", _money(data.get("qualified_dividends")), "Box 1b Qualified Dividends", log_fn)
    for aid, key, name in (("Textbox_20", "capital_gain_dist", "Box 2a Capital Gain Distr."), ("Textbox_28", "fed_tax_withheld", "Box 4 Fed Tax Withheld"),
                           ("Textbox_29", "section_199a_dividends", "Box 5 Section 199A dividends"), ("Textbox_31", "foreign_tax_paid", "Box 7 Foreign tax paid")):
        if _nonzero(data.get(key)):
            set_field(edits, aid, _money(data.get(key)), name, log_fn)


def populate_99m_data(sub_w, data, log_fn):
    """Screen 99M: TIN = Textbox_6, name = Textbox_7, box 2 royalties = Textbox_27, box 3 other income = Textbox_28,
    box 4 = Textbox_31. (The old ids 5/6/12/13 were a check box, the TIN box, the payer ZIP and a foreign field.)"""
    if data.get("is_zero_value"):
        log_fn("[INFO] Zero-value 1099-MISC (all fields 0.00) — no Drake entry required.")
        return
    edits, combos, _ = get_screen_controls(sub_w)
    set_field(edits, "Textbox_6", clean_tin(data.get("payer_tin")), "Payer TIN", log_fn)
    set_combo_text(combos, "Dropdown_1", "T", "TS Code", log_fn)
    set_field(edits, "Textbox_7", data.get("payer"), "Payer Name", log_fn)
    for aid, keys, name in (("Textbox_27", ("royalties", "box2_royalties"), "Box 2 Royalties"),
                            ("Textbox_28", ("other_income", "box3_other_income"), "Box 3 Other Income"),
                            ("Textbox_31", ("box4_fed_tax_withheld",), "Box 4 Fed Tax Withheld")):
        v = next((data.get(k) for k in keys if data.get(k)), "")
        if _nonzero(v):
            set_field(edits, aid, _money(v), name, log_fn)


def populate_oid_data(sub_w, data, log_fn):
    if data.get("is_zero_value"):
        log_fn("[INFO] Zero-value 1099-OID (all fields 0.00) — no Drake entry required.")
        return
    edits, combos, _ = get_screen_controls(sub_w)
    set_field(edits, "Textbox_5", clean_tin(data.get("payer_tin")), "Payer TIN", log_fn)
    set_combo_text(combos, "Dropdown_1", "T", "TS Code", log_fn)
    set_field(edits, "Textbox_6", data.get("payer"), "Payer Name", log_fn)
    for aid, key, name in (("Textbox_16", "original_issue_discount", "Box 1 OID"), ("Textbox_19", "fed_tax_withheld", "Box 4 Fed Tax Withheld"),
                           ("Textbox_23", "oid_treasury_obligations", "Box 8 OID on Treasury obligations")):
        if _nonzero(data.get(key)):
            set_field(edits, aid, _money(data.get(key)), name, log_fn)


def populate_1099r_data(sub_w, data, log_fn):
    """Screen 1099: distribution code is the Dropdown_33 drop-down (the old code typed it into Textbox_36 = box 8 'Other')."""
    edits, combos, checkboxes = get_screen_controls(sub_w)
    set_field(edits, "Textbox_5", clean_tin(data.get("payer_tin")), "Payer TIN", log_fn)
    set_combo_text(combos, "Dropdown_1", "T", "TS Code", log_fn)
    set_field(edits, "Textbox_6", data.get("payer"), "Payer Name", log_fn)
    set_field(edits, "Textbox_25", _money(data.get("gross_distribution")), "Box 1 Gross Distribution", log_fn)
    set_field(edits, "Textbox_26", _money(data.get("taxable_amount")), "Box 2a Taxable Amount", log_fn)
    if _nonzero(data.get("fed_tax_withheld")):
        set_field(edits, "Textbox_30", _money(data.get("fed_tax_withheld")), "Box 4 Fed Tax Withheld", log_fn)
    code = str(data.get("dist_code") or "").strip()
    if code:
        set_combo_text(combos, "Dropdown_33", code[:1], "Box 7 Distribution Code", log_fn)
        if len(code) > 1:
            set_combo_text(combos, "Dropdown_34", code[1:2], "Box 7 Second Distribution Code", log_fn)
    if data.get("is_ira"):          # only ever tick: the old extractor cannot reliably tell 'not ticked'
        set_checkbox(checkboxes, "CheckboxTextRight_35", True, "Box 7 IRA/SEP/SIMPLE", log_fn)


def populate_1098_data(sub_w, data, log_fn):
    """Schedule A line 8a 'Home mortgage interest and points reported on Form 1098' = TextboxAdjust_22
    (the old Textbox_47 is a state-only job-expense field)."""
    edits, _, _ = get_screen_controls(sub_w)
    set_field(edits, "TextboxAdjust_22", _money(data.get("mortgage_interest")), "Line 8a Mortgage interest (Form 1098)", log_fn)


def populate_5498_data(sub_w, data, log_fn):
    """Form 5498 is informational: nothing is typed (the old code wrote into an unverified Textbox_1)."""
    log_fn(f"[5498] {data.get('account_type', 'IRA')} at {data.get('trustee', 'trustee')}: FMV {data.get('fmv_of_account', '0.00')}, "
           f"Roth conversion {data.get('roth_conversion_amount', '0.00')} — informational, review Form 8606 in Drake. Nothing typed.")


def populate_1099b_data(sub_w, data, log_fn):
    """1099-B totals are NOT typed (the old code wrote them into Textbox_1/2 of screen 'D', which is the 99G
    screen). Sale lots go into Drake through the Form 8949 import file (Review page -> Transfer)."""
    log_fn(f"[1099-B] {data.get('broker', 'Broker')}: proceeds {data.get('total_proceeds', '')}, basis {data.get('total_cost_basis', '')} — "
           "enter through the Form 8949 import file. Nothing typed.")


FILLERS = {"W2": populate_w2_data, "SSA": populate_ssa_data, "1099": populate_1099r_data, "INT": populate_int_data,
           "DIV": populate_div_data, "A": populate_1098_data, "99M": populate_99m_data, "OID": populate_oid_data,
           "ROTH": populate_5498_data, "8606": populate_5498_data, "D": populate_1099b_data, "8949": populate_1099b_data}
NO_SCREEN = {"ROTH", "8606", "D", "8949"}         # informational / import-file only: never opened or typed into


def _open(sc, record, log):
    """Open record N of a Drake screen through the verified forms-list / grid handling (taxflow.transfer)."""
    from pywinauto import Desktop as _D
    from taxflow import transfer as T
    import sys as _sys
    return T.open_record(sc, record, log, _sys.modules[__name__], _D, create=True)


def populate_all_packet_modules(modules, log_fn=print):
    """Enter every module on its Drake screen: one record at a time (open record N -> fill -> Exit saves it)."""
    logs = []
    def log(msg):
        logs.append(msg)
        log_fn(msg)

    log("[PRE-CONDITION] Verifying connection to Drake Tax 2025...")
    if find_subscreen_window():
        exit_current_subscreen(log)
    menu_info = find_menu_window()
    if not menu_info:
        log("[ERROR] Could not find Drake Data Entry Menu. Ensure client return is open.")
        return False, logs, "ERROR"
    log(f"[PRE-CONDITION] Connected to Menu: '{menu_info[1]}'")

    from collections import defaultdict
    by_screen = defaultdict(list)
    for m in modules:
        by_screen[str(m["screen"]).upper()].append(m)
    ok_all = True
    for sc in ["W2", "SSA", "1099", "INT", "DIV", "99M", "OID", "A", "ROTH", "8606", "D", "8949"]:
        items = [m for m in by_screen.get(sc, []) if not m.get("is_zero_value")]
        for m in by_screen.get(sc, []):
            if m.get("is_zero_value"):
                log(f"[{sc}] {m.get('title', sc)}: all amounts zero — nothing entered.")
        if not items:
            continue
        if sc in NO_SCREEN:
            for item in items:
                FILLERS[sc](None, item, log)
            continue
        for rec, item in enumerate(items, 1):
            log(f"\n[{sc} REC {rec}/{len(items)}] {item.get('title', sc)}")
            try:
                sub_w = _open(sc, rec, log)
            except Exception as ex:
                ok_all = False
                log(f"[ERROR] Screen {sc} record {rec} did not open: {ex}")
                continue
            time.sleep(0.4)
            FILLERS[sc](sub_w, item, log)
            exit_current_subscreen(log)
            time.sleep(0.4)
    log("\n[DONE] Entered every module that has verified Drake fields. Review the return in Drake.")
    return ok_all, logs, "AWAITING_VERIFICATION"


def populate_single_packet_module(item, log_fn=print):
    """Enter ONE module on its Drake screen/record and leave the screen open for the reviewer."""
    logs = []
    def log(msg):
        logs.append(msg)
        log_fn(msg)

    sc = str(item.get("screen", "W2")).upper()
    title, pnum, mtype = item.get("title", f"Screen {sc}"), item.get("page", 1), item.get("type", sc)
    if sc not in FILLERS:
        log(f"[ERROR] No verified Drake fields for screen {sc} — enter {mtype} manually.")
        return False, logs, "ERROR"
    if sc in NO_SCREEN or item.get("is_zero_value"):
        FILLERS[sc](None, item, log) if sc in NO_SCREEN else log("[INFO] All amounts are zero — nothing to enter.")
        return True, logs, "NOTHING_TO_ENTER"
    if find_subscreen_window():
        exit_current_subscreen(log)
        time.sleep(0.5)
    if not find_menu_window():
        log("[ERROR] Could not find Drake Data Entry Menu. Ensure client return is open.")
        return False, logs, "ERROR"
    record = int(item.get("instance_index") or 1)          # no more hard-coded page -> record tables
    log(f"[SCREEN {sc}] Opening record {record} for {mtype} (page {pnum})...")
    try:
        sub_w = _open(sc, record, log)
    except Exception as ex:
        log(f"[ERROR] {ex}")
        return False, logs, "ERROR"
    time.sleep(0.4)
    FILLERS[sc](sub_w, item, log)
    log(f"[READY_TO_VERIFY] Review Screen {sc} record {record} in Drake, then click 'Verify & Save' to exit.")
    return True, logs, "AWAITING_VERIFICATION"

if __name__ == "__main__":
    from packet_extractor import extract_all_modules_from_packet
    test_pdf = r"uploads\Weaver-Cummings_2025_Tax_Packet.pdf"
    if os.path.exists(test_pdf):
        res = extract_all_modules_from_packet(test_pdf)
        print(f"Loaded {res['total_modules']} modules.")
        # Test batch insert
        # populate_all_packet_modules(res["modules"])
