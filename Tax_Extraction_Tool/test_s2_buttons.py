import ctypes
from pywinauto import Desktop

user32 = ctypes.windll.user32
hwinsta = user32.OpenWindowStationW('winsta0', False, 0xF037F)
if hwinsta: user32.SetProcessWindowStation(hwinsta)
hdesk = user32.OpenDesktopW('default', 0, False, 0x01FF)
if hdesk: user32.SetThreadDesktop(hdesk)

w = Desktop(backend="uia").window(handle=1641348)
for b in w.descendants(control_type="Button"):
    print(f"Text: {b.window_text()!r} | AutoID: {b.element_info.automation_id!r} | Class: {b.element_info.class_name!r}")
