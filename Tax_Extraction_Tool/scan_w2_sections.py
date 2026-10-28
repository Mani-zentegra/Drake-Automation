import ctypes
import win32gui
from pywinauto import Desktop

user32 = ctypes.windll.user32
hdesk = user32.OpenDesktopW('default', 0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

def get_w():
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
                    return w
        except:
            pass
    return None

w = get_w()
if not w:
    print("W-2 screen not open")
    exit()

print("Connected to W-2 Screen:", w.window_text())

# Group sections on W-2
for g in w.descendants(control_type="Group"):
    sec_name = g.window_text().strip()
    print(f"\n=== GROUP: '{sec_name}' ===")
    for c in g.descendants(control_type="Text"):
        t = c.window_text().strip().rstrip(':').rstrip('.')
        if t and len(t) < 45 and not t.startswith('='):
            print(f"  Label: {t}")
    edits = g.descendants(control_type="Edit")
    print(f"  Total Edits in Group: {len(edits)}")

# Also top fields outside groups (like TS, F, etc.)
print("\n=== TOP / UNGROUPED FIELDS ===")
for c in w.descendants(control_type="Text"):
    r = c.rectangle()
    if r.top < 280:
        t = c.window_text().strip().rstrip(':')
        if t:
            print(f"  Top Text: {t} at {r}")
