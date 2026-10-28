import ctypes
import win32gui
import time
import pyautogui
pyautogui.FAILSAFE = False
from pywinauto import Desktop

user32 = ctypes.windll.user32
hdesk = user32.OpenDesktopW('default', 0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

def get_w2_window():
    res = []
    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            t = win32gui.GetWindowText(h)
            if "data entry" in t.lower():
                res.append(h)
    win32gui.EnumDesktopWindows(hdesk, cb, None)
    for h in res:
        try:
            w = Desktop(backend="uia").window(handle=h)
            for tab in w.descendants(control_type="TabItem"):
                if "w-2" in tab.window_text().lower():
                    return w, h
        except:
            pass
    return None, None

w, hwnd = get_w2_window()
if not w:
    print("[ERROR] W-2 screen not found.")
    exit(1)

print(f"[FOUND] Screen W2 on window HWND: {hwnd}")

cached_edits = []
label_map = {}

for control in w.descendants():
    try:
        ctype = control.element_info.control_type
        if ctype == "Edit":
            cached_edits.append((control, control.rectangle()))
        name = control.window_text().strip().rstrip(':').rstrip('.')
        if name and (ctype in ["Text", "HeaderItem"] or "label" in (control.element_info.automation_id or "").lower()):
            label_map[name.lower()] = (name, control.rectangle())
    except:
        pass

print(f"[SCAN] Found {len(label_map)} labels, {len(cached_edits)} edits.")

def find_edit(keyword):
    # Find label matching keyword
    target = None
    for k, v in label_map.items():
        if keyword.lower() in k or k in keyword.lower():
            target = v
            break
    if not target:
        return None
    
    lbl_text, lbl_rect = target
    lbl_cy = (lbl_rect.top + lbl_rect.bottom) / 2
    
    candidates = []
    for ctrl, r in cached_edits:
        # Must be on the same horizontal row (within 14px) and to the right
        cy = (r.top + r.bottom) / 2
        v_dist = abs(cy - lbl_cy)
        if v_dist <= 14 and r.left >= lbl_rect.right - 10:
            candidates.append((v_dist, r.left - lbl_rect.right, ctrl))
            
    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][2]
    return None

w2_data = [
    ("ts", "T"),
    ("ein", "832947156"),
    ("name", "GRANITE PEAK INDUSTRIES INC"),
    ("street", "1900 Yellowstone Blvd, Suite 400"),
    ("city", "Casper"),
    ("state", "WY"),
    ("zip", "82601"),
    ("wages, tips", "213250.00"),
    ("federal tax w/h", "51180.00"),
    ("soc. sec. wages", "176100.00"),
    ("soc. sec. w/h", "10918.20"),
    ("medicare wages", "225000.00"),
    ("medicare tax w/h", "3262.50")
]

for field, val in w2_data:
    edit = find_edit(field)
    if edit:
        try:
            edit.set_focus()
            time.sleep(0.04)
            edit.set_edit_text(val)
            print(f"[OK] {field:<20} = {val}")
        except Exception as e:
            print(f"[ERROR] {field}: {e}")
    else:
        print(f"[NOT FOUND] {field}")

# Checkbox
for cb in w.descendants(control_type="CheckBox"):
    if "retirement" in cb.window_text().lower():
        try:
            cb.toggle()
            print("[OK] Checked Retirement Plan")
        except:
            pass
        break

time.sleep(0.5)
# Save Screen
saved = False
for b in w.descendants(control_type="Button"):
    if b.window_text().strip().lower() == "save":
        b.invoke()
        saved = True
        print("[SAVE] Clicked Save button!")
        break

if not saved:
    pyautogui.hotkey('alt', 's')
    print("[SAVE] Sent Alt+S!")
