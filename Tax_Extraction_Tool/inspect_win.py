import ctypes
import win32gui

user32 = ctypes.windll.user32
hwinsta = user32.OpenWindowStationW('winsta0', False, 0xF037F)
if hwinsta:
    user32.SetProcessWindowStation(hwinsta)
hdesk = user32.OpenDesktopW('default', 0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

def cb(h, _):
    if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
        txt = win32gui.GetWindowText(h).strip()
        cls = win32gui.GetClassName(h).strip()
        if txt:
            print(f"HWND: {h} | Class: {cls} | Title: {txt}")

win32gui.EnumDesktopWindows(hdesk, cb, None)
