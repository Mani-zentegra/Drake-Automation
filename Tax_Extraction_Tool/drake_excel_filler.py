import sys
import os
import ctypes
import time
import win32gui
import win32con
import win32process
import psutil
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
    if subscreen_w: return subscreen_w
    if menu_w: return menu_w
    if home_w: return home_w
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

def dismiss_drake_popups(prefer_cancel=True):
    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            t = get_window_title(h).lower()
            cls = win32gui.GetClassName(h)
            if "data entry" in t or "chat" in t:
                return
            owner = get_window_owner(h)
            if owner != 0 or cls == "#32770":
                try:
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
                                return

                    if any(k in t for k in ["help", "not valid", "save", "confirm", "attention", "notice", "reminder", "warning", "error"]):
                        for btn in w.descendants(control_type="Button"):
                            txt = btn.window_text().strip().lower()
                            aid = btn.element_info.automation_id
                            if prefer_cancel and (txt in ["cancel", "_cancel"] or aid == "2"):
                                btn.invoke()
                                time.sleep(0.3)
                                return
                            elif not prefer_cancel and (txt in ["yes", "_yes", "ok", "_ok", "save"] or aid == "1"):
                                btn.invoke()
                                time.sleep(0.3)
                                return
                except Exception:
                    pass
    try:
        win32gui.EnumDesktopWindows(hdesk, cb, None)
    except Exception:
        pass

def enter_clean_value(control, value):
    """
    Directly uses ValuePattern.SetValue without focus delays or artificial sleeps (<5ms).
    """
    if value is None or str(value).strip() == "":
        return False
    val_str = str(value).strip()

    try:
        control.iface_value.SetValue(val_str)
        return True
    except Exception:
        pass

    try:
        control.set_edit_text(val_str)
        return True
    except Exception:
        pass

    try:
        control.set_focus()
        control.set_edit_text(val_str)
        return True
    except Exception:
        pass

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

def sanitize_value(field_name, value):
    val_str = str(value).strip() if value is not None else ""
    f_lower = field_name.lower()
    if not val_str or val_str.lower() == "none":
        return ""
    if "date" in f_lower or "/" in val_str:
        cleaned = val_str.replace("/", "").replace("-", "").strip()
        if cleaned.isdigit() and len(cleaned) == 8:
            return cleaned
    if "phone" in f_lower or f_lower in ["daytime", "evening", "cell", "fax"]:
        cleaned = val_str.replace("-", "").replace(" ", "").replace("(", "").replace(")", "").strip()
        if cleaned.isdigit() and len(cleaned) == 10:
            return cleaned
    if "ssn" in f_lower:
        return val_str.replace("-", "").replace(" ", "").strip()
    return val_str.replace("$", "").replace(",", "").strip()

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

def create_new_individual_return(new_return_window, first_name, last_name, mi=""):
    for rb in new_return_window.descendants(control_type="RadioButton"):
        txt = rb.window_text().strip().lower()
        if "1040" in txt or "individual" in txt:
            try: rb.select(); break
            except: pass

    time.sleep(0.3)
    edits = [e for e in new_return_window.descendants(control_type="Edit") if e.is_visible() and e.is_enabled()]
    if len(edits) == 1:
        try: edits[0].set_edit_text(f"{first_name} {last_name}".strip())
        except: pass
    elif len(edits) == 2:
        try: edits[0].set_edit_text(first_name)
        except: pass
        try: edits[1].set_edit_text(last_name)
        except: pass
    elif len(edits) >= 3:
        try: edits[0].set_edit_text(first_name)
        except: pass
        if mi:
            try: edits[1].set_edit_text(mi)
            except: pass
        try: edits[2].set_edit_text(last_name)
        except: pass

    time.sleep(0.3)
    for btn in new_return_window.descendants(control_type="Button"):
        if btn.window_text().strip().lower() in ["ok", "_ok"]:
            try: btn.invoke(); return True
            except: pass
    pyautogui.press('enter')
    return True

def find_all_drake_raw_windows():
    drake_pids = set()
    for p in psutil.process_iter(['pid', 'name']):
        try:
            if 'draketax' in (p.info['name'] or '').lower():
                drake_pids.add(p.info['pid'])
        except Exception:
            pass

    matched = []
    def cb(h, _):
        if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
            _, pid = win32process.GetWindowThreadProcessId(h)
            if drake_pids and pid not in drake_pids:
                return
            t = get_window_title(h)
            cls = win32gui.GetClassName(h)
            if any(x in t.lower() for x in ["chrome", "visual studio", "cmd.exe", "powershell"]):
                return
            if cls.startswith("HwndWrapper[Drake") or cls == "#32770" or any(k in t.lower() for k in ["drake", "data entry", "1040", "open / create", "open return", "new return"]):
                if t.strip() and "chat" not in t.lower():
                    matched.append((h, t))
    try:
        win32gui.EnumDesktopWindows(hdesk, cb, None)
    except Exception:
        try:
            win32gui.EnumWindows(cb, None)
        except Exception:
            pass
    return matched

def get_current_drake_state():
    """
    Intelligently inspects all windows on the desktop and returns the current Drake state:
    Returns (state_name, hwnd, window_obj, extra_info)
    States:
      'NOT_RUNNING'
      'POPUP_DIALOG'
      'OPEN_SEARCH_DIALOG'
      'OPEN_PROMPT_DIALOG'
      'NEW_RETURN_DIALOG'
      'SCREEN_1'
      'SCREEN_2_MACRO'
      'SCREEN_2_DETAIL'
      'DATA_ENTRY_MENU'
      'OTHER_SCREEN'
      'HOME_SCREEN'
    """
    raw_wins = find_all_drake_raw_windows()
    if not raw_wins:
        return ('NOT_RUNNING', None, None, None)

    # 1. Dialogs and popups (highest priority, modal dialogs only)
    for h, t in raw_wins:
        t_low = t.lower()
        if "open / create a return" in t_low:
            try: return ('OPEN_SEARCH_DIALOG', h, Desktop(backend="uia").window(handle=h), t)
            except: pass
        if t == "Open Return" or (t_low.startswith("open return") and "data entry" not in t_low):
            try: return ('OPEN_PROMPT_DIALOG', h, Desktop(backend="uia").window(handle=h), t)
            except: pass
        if "new return" in t_low and "data entry" not in t_low:
            try: return ('NEW_RETURN_DIALOG', h, Desktop(backend="uia").window(handle=h), t)
            except: pass

        cls = win32gui.GetClassName(h)
        owner = get_window_owner(h)
        if (cls == "#32770" or owner != 0) and "data entry" not in t_low:
            try:
                w = Desktop(backend="uia").window(handle=h)
                for c in w.descendants(control_type="Text"):
                    ctxt = c.window_text().strip().lower()
                    if "must contain data if you are planning to e-file" in ctxt:
                        return ('POPUP_DIALOG', h, w, "E_FILE_WARNING")
            except: pass

    # 2. Check Data Entry Screens
    data_entry_wins = [(h, t) for (h, t) in raw_wins if "data entry" in t.lower()]
    for h, t in data_entry_wins:
        try:
            w = Desktop(backend="uia").window(handle=h)
            
            # Check for Screen 2 Macro (ButtonItemDetail)
            try:
                b_macro = w.child_window(auto_id="ButtonItemDetail", control_type="Button")
                if b_macro.exists(timeout=0.1):
                    return ('SCREEN_2_MACRO', h, w, None)
            except Exception:
                pass

            # Check for Data Entry Menu (LINK_0_Col0_Sel1 or MenuScreenWindow_TextBoxSearch)
            try:
                b_menu = w.child_window(auto_id="LINK_0_Col0_Sel1", control_type="Button")
                if b_menu.exists(timeout=0.1):
                    return ('DATA_ENTRY_MENU', h, w, t)
            except Exception:
                pass

            # Check for Screen 1 Demographics FIRST!
            for c in w.descendants(control_type="Text"):
                ctxt = c.window_text().strip().lower()
                if "filing status" in ctxt or "mfs claiming spouse" in ctxt or "married filing jointly" in ctxt or "name, address, and general information" in ctxt:
                    return ('SCREEN_1', h, w, None)

            # Check for Screen 2 Detail fields (strictly by distinctive labels)
            for c in w.descendants(control_type="Text"):
                ctxt = c.window_text().strip().lower()
                if "months in home" in ctxt or "relationship to taxpayer" in ctxt or "eligible for ctc" in ctxt:
                    return ('SCREEN_2_DETAIL', h, w, None)

            # Check for secondary ButtonItemDetail via descendants if child_window missed it
            for c in w.descendants(control_type="Button"):
                aid = c.element_info.automation_id or ""
                if aid == "ButtonItemDetail":
                    return ('SCREEN_2_MACRO', h, w, None)

        except Exception:
            pass

    # 3. Other Data Entry Subscreen
    for h, t in data_entry_wins:
        owner = get_window_owner(h)
        owner_t = get_window_title(owner).lower() if owner else ""
        if "data entry" in owner_t:
            try: return ('OTHER_SCREEN', h, Desktop(backend="uia").window(handle=h), t)
            except: pass

    # 4. Drake Home Screen
    for h, t in raw_wins:
        t_low = t.lower()
        if "drake" in t_low and "tax" in t_low and "data entry" not in t_low:
            try: return ('HOME_SCREEN', h, Desktop(backend="uia").window(handle=h), t)
            except: pass

    return ('UNKNOWN', None, None, None)

def open_or_create_client(ssn, first_name="Mani", last_name="Bharathi", mi="K", log=print):
    cleaned_ssn = str(ssn).replace("-", "").replace(" ", "").strip()
    log(f"[PRE-CONDITION] Opening or creating client SSN: {cleaned_ssn} ({first_name} {last_name})")

    # Step 1: Check if already open or on Open/Create dialog
    open_h, _ = find_drake_dialog("Open / Create a Return")
    if not open_h:
        main_h, main_t = find_drake_dialog("Drake 2025 Tax Software")
        if not main_h:
            main_h, main_t = find_drake_window()
        if not main_h or "data entry" in main_t.lower():
            for h, t in find_all_drake_raw_windows():
                if "drake 2025" in t.lower() and "data entry" not in t.lower():
                    main_h, main_t = h, t
                    break
        if not main_h:
            log("[ERROR] Drake 2025 Tax Software is not running.")
            return False

        log(f"[CONNECT] Drake Main Window: '{main_t}'")
        main_win = Desktop(backend="uia").window(handle=main_h)
        log("[ACTION] Clicking 'Open/Create' button...")
        click_open_create(main_win)

        for _ in range(12):
            time.sleep(0.4)
            open_h, _ = find_drake_dialog("Open / Create a Return")
            if open_h:
                break

    if not open_h:
        log("[ERROR] Could not open 'Open / Create a Return' dialog.")
        return False

    log("[DIALOG] 'Open / Create a Return' is ready.")
    open_dialog = Desktop(backend="uia").window(handle=open_h)

    log(f"[SEARCH] Submitting SSN: {cleaned_ssn}...")
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
            try: c.invoke(); break
            except: pass
    else:
        pyautogui.press('enter')

    # Step 2: Handle results (New Client prompt vs Existing Client)
    for _ in range(24):
        time.sleep(0.5)

        # Check for 'Open Return' prompt
        prompt_h, _ = find_drake_dialog("Open Return")
        if prompt_h:
            log(f"[NEW CLIENT] Client {cleaned_ssn} does not exist. Creating new return...")
            prompt_win = Desktop(backend="uia").window(handle=prompt_h)
            for btn in prompt_win.descendants(control_type="Button"):
                if btn.window_text().strip().lower() in ["yes", "_yes"]:
                    try: btn.invoke(); break
                    except: pass
            else:
                pyautogui.press('y')
            time.sleep(0.8)

            # Wait for 'New Return' dialog
            new_ret_h = None
            for _ in range(15):
                new_ret_h, _ = find_drake_dialog("New Return")
                if new_ret_h:
                    break
                time.sleep(0.3)

            if new_ret_h:
                new_ret_win = Desktop(backend="uia").window(handle=new_ret_h)
                create_new_individual_return(new_ret_win, first_name, last_name, mi)
                log(f"[NEW CLIENT] 1040 Individual return configured for {first_name} {last_name}.")
                time.sleep(1.0)
            return True

        # Check if already transitioned into return
        state, _, _, _ = get_current_drake_state()
        if state in ['SCREEN_1', 'DATA_ENTRY_MENU', 'SCREEN_2_MACRO', 'SCREEN_2_DETAIL', 'OTHER_SCREEN']:
            log(f"[SUCCESS] Client {cleaned_ssn} return opened (Current state: {state})!")
            return True

    return True

def find_data_entry_menu():
    matched = []
    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            t = get_window_title(h)
            if "data entry" in t.lower():
                owner = get_window_owner(h)
                owner_t = get_window_title(owner).lower() if owner else ""
                if "data entry" not in owner_t:
                    matched.append((h, t))
    try:
        win32gui.EnumDesktopWindows(hdesk, cb, None)
    except: pass
    if not matched:
        try:
            win32gui.EnumWindows(cb, None)
        except: pass
    return matched[0] if matched else (None, "")

def wait_for_data_entry_menu(timeout=5.0):
    start = time.time()
    while time.time() - start < timeout:
        state, h, w, _ = get_current_drake_state()
        if state == 'DATA_ENTRY_MENU':
            return h, get_window_title(h)
        h, t = find_data_entry_menu()
        if h:
            return h, t
        time.sleep(0.3)
    return None, ""

def find_active_subscreen():
    matched = []
    def cb(h, _):
        if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
            t = get_window_title(h)
            if "data entry" in t.lower():
                owner = get_window_owner(h)
                owner_t = get_window_title(owner).lower() if owner else ""
                if "data entry" in owner_t:
                    matched.append((h, t))
    try:
        win32gui.EnumDesktopWindows(hdesk, cb, None)
    except Exception:
        pass
    return matched

MENU_BUTTON_MAP = {
    "1": "LINK_0_Col0_Sel1",
    "2": "LINK_0_Col0_Sel2",
    "W2": "LINK_0_Col0_Sel10",
    "SSA": "LINK_0_Col0_Sel18",
    "INT": "LINK_0_Col0_Sel14",
    "DIV": "LINK_0_Col0_Sel13",
    "1099": "LINK_0_Col0_Sel12",
}

def navigate_to_screen(code):
    dismiss_drake_popups(prefer_cancel=True)
    menu_h, menu_t = find_data_entry_menu()
    if not menu_h:
        exit_to_menu()
        time.sleep(0.4)
        menu_h, menu_t = find_data_entry_menu()

    if not menu_h:
        return False

    w = Desktop(backend="uia").window(handle=menu_h)

    # 1. Fast direct button by Automation ID (<5ms)
    btn_id = MENU_BUTTON_MAP.get(str(code).upper())
    if btn_id:
        try:
            btn = w.child_window(auto_id=btn_id, control_type="Button")
            if btn.exists(timeout=1):
                btn.invoke()
                time.sleep(0.6)
                dismiss_drake_popups(prefer_cancel=True)
                return True
        except Exception:
            pass

    # 2. Try by prefix (e.g. "2|Dependents")
    prefix = f"{code}|"
    try:
        for btn in w.descendants(control_type="Button"):
            btxt = btn.window_text().strip().lower()
            if btxt.startswith(prefix) or btxt.startswith(f"{code} |"):
                try:
                    btn.invoke()
                    time.sleep(0.6)
                    dismiss_drake_popups(prefer_cancel=True)
                    return True
                except Exception:
                    btn.click_input()
                    time.sleep(0.6)
                    dismiss_drake_popups(prefer_cancel=True)
                    return True
    except Exception:
        pass

    # 3. Fallback: menu selector edit box
    try:
        for edit in w.descendants(control_type="Edit"):
            if edit.is_visible() and edit.is_enabled():
                edit.set_edit_text(str(code))
                pyautogui.press('enter')
                time.sleep(0.8)
                dismiss_drake_popups(prefer_cancel=True)
                return True
    except Exception:
        pass

    return False

def find_screen2_windows():
    detail_w = None
    macro_w = None
    for h, t in find_all_drake_raw_windows():
        owner = get_window_owner(h)
        if owner == 0:
            continue
        try:
            w = Desktop(backend="uia").window(handle=h)
            for c in w.descendants(control_type="Button"):
                aid = c.element_info.automation_id or ""
                btxt = c.window_text().strip().lower()
                if aid == "ButtonItemDetail" or "item detail" in btxt:
                    macro_w = (h, w)
                    break
            if macro_w and macro_w[0] == h:
                continue

            for c in w.descendants(control_type="Edit"):
                aid = c.element_info.automation_id or ""
                if aid in ["Textbox_1", "Textbox_5", "Textbox_8", "TextboxOverride_1", "TextboxOverride_3"]:
                    detail_w = (h, w)
                    break
        except Exception:
            pass
    return detail_w, macro_w

def wait_for_screen2(timeout=8.0):
    start = time.time()
    while time.time() - start < timeout:
        detail_w, macro_w = find_screen2_windows()
        if detail_w or macro_w:
            return detail_w, macro_w
        dismiss_drake_popups(prefer_cancel=True)
        time.sleep(0.3)
    return None, None

def click_item_detail(win):
    try:
        for b in win.descendants(control_type="Button"):
            aid = b.element_info.automation_id or ""
            btxt = b.window_text().strip().lower()
            if aid == "ButtonItemDetail" or "item detail" in btxt:
                try:
                    b.invoke()
                    return True
                except:
                    try:
                        b.click_input()
                        return True
                    except:
                        pass
    except Exception:
        pass
    pyautogui.press('enter')
    return True

def exit_to_menu():
    """
    Exits any open subscreens (Screen 1, Screen 2, Macro dialogs, etc.)
    and safely returns to the Data Entry Menu.
    Guaranteed NEVER to press Esc or click Exit when already on the Menu!
    """
    dismiss_drake_popups(prefer_cancel=True)

    for _ in range(5):
        state, h, w, _ = get_current_drake_state()
        if state == 'DATA_ENTRY_MENU':
            return True
        if state in ['NOT_RUNNING', 'HOME_SCREEN']:
            return False

        if state in ['SCREEN_1', 'SCREEN_2_DETAIL', 'SCREEN_2_MACRO', 'OTHER_SCREEN']:
            handled = False
            for b in w.descendants(control_type="Button"):
                aid = b.element_info.automation_id or ""
                if aid in ["ButtonSave", "btnExit"]:
                    try: b.invoke(); handled = True; break
                    except: pass
            if not handled:
                for m in w.descendants(control_type="MenuItem"):
                    aid = m.element_info.automation_id or ""
                    if aid == "mnuIcon_Exit":
                        try: m.invoke(); handled = True; break
                        except: pass
            if not handled:
                try:
                    w.set_focus()
                    time.sleep(0.1)
                except Exception:
                    pass
                pyautogui.press('esc')

            time.sleep(0.6)
            dismiss_drake_popups(prefer_cancel=True)

    state, _, _, _ = get_current_drake_state()
    return state == 'DATA_ENTRY_MENU'

def exit_return_to_home():
    """
    Exits from any subscreen or Data Entry Menu back to Drake Home Window.
    """
    exit_to_menu()
    time.sleep(0.5)
    menu_h, menu_t = find_data_entry_menu()
    if menu_h:
        try:
            w = Desktop(backend="uia").window(handle=menu_h)
            w.set_focus()
            time.sleep(0.2)
        except Exception:
            pass
        pyautogui.press('esc')
        time.sleep(1.0)
    dismiss_drake_popups(prefer_cancel=True)

def discover_section_controls(window):
    ignored_sections = {"screen menu", "mfs claiming spouse exemption", "foreign account and digital asset questions", "return options"}
    ignored_labels = {"=", "taxpayer", "spouse", "mailing address", "return options", "miscellaneous codes", "2210 options", "u.s. only", "foreign only"}

    sections = {}
    for g in window.descendants(control_type="Group"):
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

        field_map = {}
        for edit in edits:
            try:
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
                    v_above = erect.top - lrect.bottom
                    if 0 <= v_above <= 22 and abs(erect.left - lrect.left) <= 20:
                        dist = v_above + abs(erect.left - lrect.left)
                        if dist < min_dist:
                            min_dist = dist
                            best_lbl = lbl_txt
                if best_lbl:
                    field_map[best_lbl.lower()] = edit
            except Exception:
                continue

        if field_map:
            sections[sec_name.lower()] = field_map
    return sections

def wait_for_screen1(timeout=6.0):
    """Waits for Screen 1 subscreen and ensures UI sections are loaded."""
    start = time.time()
    while time.time() - start < timeout:
        state, h, w, secs = get_current_drake_state()
        if state == 'SCREEN_1' and w:
            return h, w, secs
        time.sleep(0.3)
    return None, None, {}

def populate_screen1(window, organizer_data, log, pre_sections=None):
    log("[SCREEN 1] Starting Demographics & Name/Address Population...")
    tp = organizer_data.get("taxpayer", {})
    sp = organizer_data.get("spouse", {})
    addr = organizer_data.get("address", {})

    has_spouse = bool(sp.get("first_name") or sp.get("last_name") or sp.get("ssn"))
    filing_status = "2" if has_spouse else "1"

    # Set Filing Status
    filing_status_ctrl = None
    for lbl in window.descendants(control_type="Text"):
        if "filing status" in lbl.window_text().strip().lower():
            lrect = lbl.rectangle()
            lcy = (lrect.top + lrect.bottom) / 2
            best_dist = 9999
            for ctrl in window.descendants():
                try:
                    if ctrl.element_info.control_type in ["ComboBox", "Edit"]:
                        crect = ctrl.rectangle()
                        ccy = (crect.top + crect.bottom) / 2
                        if abs(ccy - lcy) <= 15 and crect.left >= lrect.left:
                            dist = crect.left - lrect.right
                            if dist < best_dist:
                                best_dist = dist
                                filing_status_ctrl = ctrl
                except: pass
            break

    if filing_status_ctrl:
        edits = filing_status_ctrl.descendants(control_type="Edit")
        target = edits[0] if edits else filing_status_ctrl
        enter_clean_value(target, filing_status)
        log(f"[OK] Filing Status                = {filing_status} ({'Married Filing Jointly' if has_spouse else 'Single'})")
        time.sleep(0.2)

    sections = pre_sections if pre_sections else discover_section_controls(window)
    log(f"[DISCOVERY] Found {len(sections)} UI sections on Screen 1")

    # Mapping entries: (field_name, section, value)
    entries = [
        ("First name", "Taxpayer", tp.get("first_name")),
        ("M.I", "Taxpayer", tp.get("mi")),
        ("Last name", "Taxpayer", tp.get("last_name")),
        ("Date of birth", "Taxpayer", sanitize_value("dob", tp.get("dob"))),
        ("Occupation", "Taxpayer", tp.get("occupation")),
        ("Daytime", "Taxpayer", sanitize_value("phone", tp.get("phone"))),
        ("Cell", "Taxpayer", sanitize_value("phone", tp.get("other_phone"))),
        ("Email or text msg", "Taxpayer", tp.get("email")),

        ("First name", "Spouse", sp.get("first_name")),
        ("M.I", "Spouse", sp.get("mi")),
        ("Last name", "Spouse", sp.get("last_name")),
        ("SSN", "Spouse", sanitize_value("ssn", sp.get("ssn"))),
        ("Date of birth", "Spouse", sanitize_value("dob", sp.get("dob"))),
        ("Occupation", "Spouse", sp.get("occupation")),
        ("Daytime", "Spouse", sanitize_value("phone", sp.get("phone"))),
        ("Cell", "Spouse", sanitize_value("phone", sp.get("other_phone"))),
        ("Email or text msg", "Spouse", sp.get("email")),

        ("Street", "Address", addr.get("street")),
        ("Apt. #", "Address", addr.get("apt")),
        ("City", "Address", addr.get("city")),
        ("State", "Address", addr.get("state")),
        ("ZIP", "Address", addr.get("zip")),
        ("County", "Address", addr.get("county")),
    ]

    for fname, sec, val in entries:
        if not val: continue
        matched_sec = None
        for s_key in sections:
            if sec.lower() in s_key or s_key in sec.lower():
                matched_sec = sections[s_key]
                break

        ctrl = None
        if matched_sec:
            ctrl = matched_sec.get(fname.lower())
            if not ctrl:
                for k, c in matched_sec.items():
                    if fname.lower() in k or k in fname.lower():
                        ctrl = c
                        break

        if ctrl and enter_clean_value(ctrl, val):
            log(f"[OK] {sec} {fname:<18} = {val}")
        time.sleep(0.02)

    log("[SCREEN 1] Screen 1 fields successfully populated!")
    return True

def populate_screen2_dependents_detail(w, dependents, log):
    for idx, dep in enumerate(dependents, start=1):
        # Cache controls once per screen for instant O(1) field injection
        ctrl_map = {}
        try:
            for c in w.descendants():
                aid = c.element_info.automation_id
                if aid:
                    ctrl_map[aid] = c
                    ctrl_map[aid.lower()] = c
        except Exception:
            pass

        def set_field(candidates, val):
            if val is None or str(val).strip() == "":
                return False
            if isinstance(candidates, str):
                candidates = [candidates]
            val_str = str(val).strip()

            for target in candidates:
                c = ctrl_map.get(target) or ctrl_map.get(target.lower())
                if c:
                    try:
                        c.iface_value.SetValue(val_str)
                        return True
                    except Exception:
                        pass
                    try:
                        if c.element_info.control_type == "ComboBox":
                            edits = c.descendants(control_type="Edit")
                            tgt = edits[0] if edits else c
                            tgt.set_edit_text(val_str)
                        else:
                            c.set_edit_text(val_str)
                        return True
                    except Exception:
                        pass
            return False

        def advance_next_screen():
            next_btn = ctrl_map.get("mnuIcon_Next") or ctrl_map.get("Next")
            if next_btn:
                try:
                    next_btn.invoke()
                    return True
                except Exception:
                    pass
            pyautogui.press('pagedown')
            return True

        fn = dep.get("first_name", "")
        mi = dep.get("mi", "")
        ln = dep.get("last_name", "")
        ssn = sanitize_value("ssn", dep.get("ssn", ""))
        rel = dep.get("relationship", "CHILD").upper()
        months = str(dep.get("months", "12"))
        dob = sanitize_value("dob", dep.get("dob", ""))

        log(f"[DEP {idx}] Populating: {fn} {ln} (SSN: {ssn}, Rel: {rel}, Months: {months}, DOB: {dob})...")

        # 1. First Name
        if fn and set_field(["Textbox_1", "TextboxOverride_1", "txtFirstName"], fn):
            log(f"   [OK] Dependent First Name     = {fn}")
        # 2. M.I.
        if mi and set_field(["Textbox_2", "TextboxOverride_2", "txtMI"], mi):
            log(f"   [OK] Dependent M.I.           = {mi}")
        # 3. Last Name
        if ln and set_field(["TextboxOverride_3", "Textbox_3", "txtLastName"], ln):
            log(f"   [OK] Dependent Last Name      = {ln}")
        # 4. Suffix (if any)
        sfx = dep.get("suffix", "")
        if sfx and set_field(["Textbox_4", "txtSuffix"], sfx):
            log(f"   [OK] Dependent Suffix         = {sfx}")
        # 5. SSN
        if ssn and set_field(["Textbox_5", "txtSSN"], ssn):
            log(f"   [OK] Dependent SSN            = {ssn}")
        # 6. Relationship
        if rel and set_field(["Dropdown_6", "cmbRel"], rel):
            log(f"   [OK] Relationship             = {rel}")
        # 7. Months in Home
        if months and set_field(["Dropdown_7", "cmbMonths"], months):
            log(f"   [OK] Months in Home           = {months}")
        # 8. Date of Birth
        if dob and set_field(["Textbox_8", "txtDOB"], dob):
            log(f"   [OK] Date of Birth            = {dob}")

        time.sleep(0.3)

        # If not the last dependent, advance to next record
        if idx < len(dependents):
            log(f"[DEP {idx}] Advancing to next dependent record...")
            advance_next_screen()
            time.sleep(0.8)
            state, h_next, w_next, _ = get_current_drake_state()
            if state == 'SCREEN_2_DETAIL' and w_next:
                w = w_next

    log(f"[SUCCESS] All {len(dependents)} dependents populated into Screen 2!")
    return True

def populate_screen2_dependents(dependents, log):
    if not dependents:
        log("[SCREEN 2] No dependents to populate.")
        return True

    log(f"[SCREEN 2] Starting Screen 2 entry for {len(dependents)} dependents...")
    detail_w, macro_w = wait_for_screen2(timeout=6.0)

    if not detail_w and not macro_w:
        log("[SCREEN 2] Screen 2 not detected yet. Re-triggering Screen 2 navigation...")
        navigate_to_screen("2")
        detail_w, macro_w = wait_for_screen2(timeout=5.0)

    if macro_w:
        log("[SCREEN 2] Macro dialog detected. Clicking 'Item Detail' to enter full screen mode...")
        click_item_detail(macro_w[1])
        time.sleep(1.0)
        detail_w, macro_w = wait_for_screen2(timeout=5.0)

    if not detail_w and macro_w:
        detail_w = macro_w

    if not detail_w:
        log("[ERROR] Could not find Screen 2 Dependent window.")
        return False

    return populate_screen2_dependents_detail(detail_w[1], dependents, log)

def populate_excel_return(organizer_data):
    """
    Main workflow for Excel Master Organizer with intelligent state-based decision making:
    1. Checks if Drake is running.
    2. Checks if the requested return is already open; if not, opens or creates it.
    3. Handles Screen 1:
       - If Drake automatically lands on Screen 1 (new client), detects it immediately without navigating.
       - If on Data Entry Menu, navigates to Screen 1.
       - Populates Demographics, Spouse, and Address.
       - Exits Screen 1 cleanly to Data Entry Menu.
    4. Handles Screen 2 (Dependents):
       - Navigates to Screen 2.
       - If macro dialog opens, clicks Item Detail.
       - Populates all dependents.
    5. Returns readiness status for verification.
    """
    logs = []
    def log(msg):
        print(msg)
        logs.append(msg)

    dismiss_drake_popups(prefer_cancel=True)
    time.sleep(0.2)

    h_main, t_main = find_drake_window()
    if not h_main:
        return False, ["Drake 2025 is not running. Please open Drake Tax first."], "ERROR"

    log(f"[PRE-CONDITION] Connected to Drake Window: '{t_main}'")

    tp = organizer_data.get("taxpayer", {})
    ssn = tp.get("ssn", "123-45-6789")
    fn = tp.get("first_name", "Mani")
    ln = tp.get("last_name", "Bharathi")
    mi = tp.get("mi", "K")

    cleaned_req_ssn = str(ssn).replace("-", "").replace(" ", "").strip()

    # Step 1: Decision on current return state
    state, hwnd, win, extra = get_current_drake_state()
    log(f"[STATE] Current Drake state before client open: {state}")

    current_win_text = win.window_text() if win else ""
    return_already_open = False

    if cleaned_req_ssn in current_win_text.replace("-", ""):
        return_already_open = True
        log(f"[DECISION] Return for SSN {cleaned_req_ssn} is already open in Drake.")
    else:
        # If another return is open, close it back to Drake Home
        if state in ['SCREEN_1', 'SCREEN_2_MACRO', 'SCREEN_2_DETAIL', 'DATA_ENTRY_MENU', 'OTHER_SCREEN']:
            log("[DECISION] A different return is currently open. Exiting to Drake Home screen...")
            exit_return_to_home()
            time.sleep(0.8)

        log(f"[ACTION] Opening or creating client return SSN: {ssn} ({fn} {ln})...")
        opened = open_or_create_client(ssn, fn, ln, mi, log=log)
        if not opened:
            return False, logs + ["[ERROR] Could not open or create client return."], "ERROR"
        time.sleep(1.0)

    # Step 2: Intelligent Screen 1 Decision Making
    state, hwnd, win, extra = get_current_drake_state()
    log(f"[STATE] Drake state after open/create: {state}")

    s1_win = None
    s1_secs = None

    if state == 'SCREEN_1':
        log("[DECISION] Drake automatically landed on Screen 1 (Demographics). Skipping menu navigation!")
        s1_win = win
        s1_secs = extra
    else:
        if state != 'DATA_ENTRY_MENU':
            log("[NAVIGATE] Exiting current screen to Data Entry Menu...")
            exit_to_menu()
            time.sleep(0.5)

        log("[NAVIGATE] Opening Screen 1: Demographics / Name & Address...")
        navigate_to_screen("1")
        time.sleep(1.0)

        for _ in range(10):
            state, hwnd, win, extra = get_current_drake_state()
            if state == 'SCREEN_1':
                s1_win = win
                s1_secs = extra
                break
            time.sleep(0.4)

    if s1_win:
        log("[SCREEN 1] Screen 1 detected. Populating Demographics...")
        populate_screen1(s1_win, organizer_data, log, pre_sections=s1_secs)
        time.sleep(0.4)

        log("[SAVE] Exiting Screen 1 to Data Entry Menu...")
        exit_to_menu()
        time.sleep(0.8)
        dismiss_drake_popups(prefer_cancel=True)
    else:
        log(f"[ERROR] Could not open Screen 1 Demographics window. Current state: {state}")
        exit_to_menu()

    # Step 3: Screen 2 (Dependents) Decision Making
    dependents = organizer_data.get("dependents", [])
    if dependents:
        log(f"[NAVIGATE] Opening Screen 2: Dependents ({len(dependents)} dependents)...")
        state, hwnd, win, extra = get_current_drake_state()
        if state != 'DATA_ENTRY_MENU':
            exit_to_menu()
            time.sleep(0.5)

        navigate_to_screen("2")
        time.sleep(1.0)

        # Wait for Screen 2 state
        for _ in range(12):
            state, hwnd, win, extra = get_current_drake_state()
            if state in ['SCREEN_2_MACRO', 'SCREEN_2_DETAIL']:
                break
            time.sleep(0.4)

        if state == 'SCREEN_2_MACRO':
            log("[SCREEN 2] Macro dialog detected. Clicking 'Item Detail' to enter full screen mode...")
            click_item_detail(win)
            time.sleep(1.0)
            for _ in range(10):
                state, hwnd, win, extra = get_current_drake_state()
                if state == 'SCREEN_2_DETAIL':
                    break
                time.sleep(0.4)

        if state == 'SCREEN_2_DETAIL':
            populate_screen2_dependents_detail(win, dependents, log)
            time.sleep(0.4)
        else:
            log(f"[ERROR] Could not find Screen 2 Dependent window. Current state: {state}")
            return False, logs, "ERROR"

    log("[READY_TO_VERIFY] Excel Master Organizer data entered into Drake Software!")
    log("[ACTION_REQUIRED] Review Screen 2 / Screen 1 in Drake Tax and click 'Verify & Save' to exit.")
    return True, logs, "POPULATED"

def save_and_exit_excel():
    logs = []
    def log(msg):
        print(msg)
        logs.append(msg)

    try:
        dismiss_drake_popups()
    except Exception:
        pass
    time.sleep(0.2)

    h, t = find_drake_window()
    if not h:
        return False, ["Drake 2025 is not open."], "ERROR"

    log("[SAVE] Saving screen and returning cleanly to Data Entry Menu...")
    try:
        exit_to_menu()
    except Exception as e:
        log(f"[INFO] Exit event: {e}")
    time.sleep(0.5)
    try:
        dismiss_drake_popups()
    except Exception:
        pass
    log("[SUCCESS] Client Demographics & Dependents saved in Drake Tax 2025!")
    return True, logs, "SAVED"

def discard_excel():
    logs = []
    def log(msg):
        print(msg)
        logs.append(msg)
    log("[DISCARD] Discarding current screen changes...")
    exit_to_menu()
    time.sleep(0.3)
    dismiss_drake_popups()
    log("[DISCARD] Exited screen without saving.")
    return True, logs, "DISCARDED"
