import ctypes
import win32gui
from pywinauto import Desktop

user32 = ctypes.windll.user32
hwinsta = user32.OpenWindowStationW('winsta0', False, 0xF037F)
if hwinsta: user32.SetProcessWindowStation(hwinsta)
hdesk = user32.OpenDesktopW('default', 0, False, 0x01FF)
if hdesk: user32.SetThreadDesktop(hdesk)

w = Desktop(backend="uia").window(handle=3543344)
for b in w.descendants(control_type="Button"):
    txt = b.window_text().strip()
    aid = b.element_info.automation_id or ""
    if txt.startswith("1|") or txt.startswith("2|") or txt.startswith("W2"):
        print(f"Text: {txt!r} | AutoID: {aid!r}")
