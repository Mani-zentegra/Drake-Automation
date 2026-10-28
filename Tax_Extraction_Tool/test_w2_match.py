import ctypes
import win32gui
import time
from pywinauto import Desktop

user32 = ctypes.windll.user32
hdesk = user32.OpenDesktopW('default', 0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

# Locate active Drake screen
w2_hwnd = None
def cb(h, _):
    global w2_hwnd
    if win32gui.IsWindowVisible(h):
        t = win32gui.GetWindowText(h)
        if "data entry" in t.lower():
            # Check owner
            w = Desktop(backend="uia").window(handle=h)
            for tab in w.descendants(control_type="TabItem"):
                if "w-2" in tab.window_text().lower():
                    w2_hwnd = h
                    return
win32gui.EnumDesktopWindows(hdesk, cb, None)

print(f"Target W-2 Screen HWND: {w2_hwnd}")
if not w2_hwnd:
    print("Could not find W-2 screen.")
    exit()

w = Desktop(backend="uia").window(handle=w2_hwnd)
texts = [(c.window_text().strip(), c.rectangle()) for c in w.descendants(control_type="Text") if c.window_text().strip()]
edits = [(c, c.rectangle()) for c in w.descendants(control_type="Edit") if c.is_visible()]

print(f"Found {len(texts)} texts, {len(edits)} visible edits.")

def find_input(keywords):
    for txt, r in texts:
        ltxt = txt.lower()
        if any(k in ltxt for k in keywords):
            cy = (r.top + r.bottom) / 2
            # Find edit on same line
            matches = []
            for e, er in edits:
                ey = (er.top + er.bottom) / 2
                if abs(ey - cy) <= 16:
                    matches.append((e, er))
            if matches:
                # Prefer edit to right of label text
                right = [m for m in matches if m[1].left >= r.left]
                if right:
                    right.sort(key=lambda x: x[1].left)
                    return right[0][0]
                matches.sort(key=lambda x: abs(x[1].left - r.right))
                return matches[0][0]
    return None

test_data = [
    (["ts"], "T", "TS Code"),
    (["ein"], "832947156", "Employer EIN"),
    (["employer information"], "GRANITE PEAK INDUSTRIES INC", "Employer Name"),
    (["street"], "1900 Yellowstone Blvd, Suite 400", "Street"),
    (["city"], "Casper", "City"),
    (["state"], "WY", "State"),
    (["zip"], "82601", "ZIP"),
    (["wages, tips"], "213250.00", "Box 1 Wages"),
    (["federal tax w/h"], "51180.00", "Box 2 Federal Withheld"),
    (["soc. sec. wages"], "176100.00", "Box 3 SS Wages"),
    (["soc. sec. w/h"], "10918.20", "Box 4 SS Tax"),
    (["medicare wages"], "225000.00", "Box 5 Medicare Wages"),
    (["medicare tax w/h"], "3262.50", "Box 6 Medicare Tax")
]

for kw, val, label in test_data:
    edit = find_input(kw)
    if edit:
        try:
            edit.set_focus()
            time.sleep(0.04)
            edit.set_edit_text(val)
            print(f"[OK] {label:<25} = {val}")
        except Exception as ex:
            print(f"[ERROR] {label}: {ex}")
    else:
        print(f"[FAIL] Control not found for: {label} ({kw})")
