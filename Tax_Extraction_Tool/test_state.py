import sys
import ctypes
import win32gui
from drake_excel_filler import get_current_drake_state

state, hwnd, win, extra = get_current_drake_state()
print("CURRENT STATE:", state)
print("HWND:", hwnd)
print("TITLE:", win.window_text() if win else "None")
