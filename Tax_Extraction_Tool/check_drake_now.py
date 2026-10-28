import ctypes
import win32gui
import win32con

user32 = ctypes.windll.user32
hwinsta = user32.OpenWindowStationW('winsta0', False, 0xF037F)
if hwinsta: user32.SetProcessWindowStation(hwinsta)
hdesk = user32.OpenDesktopW('default', 0, False, 0x01FF)
if hdesk: user32.SetThreadDesktop(hdesk)

def cb(h, _):
    if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
        t = win32gui.GetWindowText(h)
        owner = win32gui.GetWindow(h, win32con.GW_OWNER)
        cls = win32gui.GetClassName(h)
        if any(k in t.lower() for k in ["drake", "data entry", "dependents", "error"]):
            rect = win32gui.GetWindowRect(h)
            print(f"HWND: {h} | Owner: {owner} | Title: {t!r} | Rect: {rect}")

win32gui.EnumDesktopWindows(hdesk, cb, None)
