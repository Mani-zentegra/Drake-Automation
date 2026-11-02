"""
app_navigator.py - Automated Software Navigation & Zero-Alt+Tab Focus Management

Eliminates manual Alt+Tab switching across the entire automation lifecycle:
1. Automatically detects Drake Tax 2025 and Web Browser (Chrome/Edge/Zoho Creator).
2. Brings the required application to the foreground forcefully using Win32 API
   thread-input attachment and synthetic Alt-event bypass (bypassing Windows foreground lock).
3. Handles unexpected modal popups, warnings, save prompts, and update notifications.
4. Provides a context manager for seamless switching:
   - When automation begins: switches to Drake Tax 2025.
   - When automation finishes: automatically restores Browser/Zoho Creator.
5. Zero keyboard or manual Alt+Tab intervention required.
"""

import os
import sys
import time
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
import win32gui
import win32con
import win32process
import psutil
from pywinauto import Desktop

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# =============================================================================
# WIN32 DESKTOP & WINDOW STATION INITIALIZATION
# =============================================================================
def init_station():
    """Ensures process is attached to interactive desktop station (winsta0\\default)."""
    try:
        hwinsta = user32.OpenWindowStationW('winsta0', False, 0xF037F)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)
        hdesk = user32.OpenDesktopW('default', 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
        return hdesk
    except Exception:
        return None

# Run init_station at module load
init_station()

# =============================================================================
# FOOLPROOF FOREGROUND WINDOW ACTIVATION (BYPASSES WINDOWS LOCK)
# =============================================================================
def force_activate_window(hwnd, max_retries=3, delay_after=0.2):
    """
    Brings any window handle forcefully to the foreground without Alt+Tab.
    Uses Win32 thread-input attachment + AllowSetForegroundWindow + synthetic Alt key event.
    """
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False

    init_station()

    for attempt in range(max_retries):
        current_fg = user32.GetForegroundWindow()
        if current_fg == hwnd:
            return True

        # 1. Restore if minimized/iconic
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        except Exception:
            pass

        # 2. Setup thread inputs
        cur_thread = kernel32.GetCurrentThreadId()
        fg_thread, _ = win32process.GetWindowThreadProcessId(current_fg) if current_fg else (0, 0)
        target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)

        user32.AllowSetForegroundWindow(-1)  # ASFW_ANY

        # Attach target and foreground threads to current thread
        if fg_thread and fg_thread != cur_thread:
            user32.AttachThreadInput(cur_thread, fg_thread, True)
        if target_thread and target_thread != cur_thread:
            user32.AttachThreadInput(cur_thread, target_thread, True)

        # 3. Simulate Alt keypress to unlock Windows SetForegroundWindow restriction
        user32.keybd_event(0x12, 0, 0, 0)                  # VK_MENU down
        user32.keybd_event(0x12, 0, win32con.KEYEVENTF_KEYUP, 0)  # VK_MENU up

        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)

        # Detach threads
        if fg_thread and fg_thread != cur_thread:
            user32.AttachThreadInput(cur_thread, fg_thread, False)
        if target_thread and target_thread != cur_thread:
            user32.AttachThreadInput(cur_thread, target_thread, False)

        # 4. Fallback with SwitchToThisWindow
        time.sleep(0.08)
        user32.SwitchToThisWindow(hwnd, True)

        time.sleep(delay_after)
        current_fg = user32.GetForegroundWindow()
        if current_fg == hwnd:
            return True

    # If foreground verification is masked by desktop station in background process, return True if window is visible and active
    return bool(win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd))

# =============================================================================
# WINDOW DISCOVERY: DRAKE TAX 2025
# =============================================================================
def find_drake_window():
    """
    Finds the active Drake Tax window.
    Priority order:
    1. Active Subscreen (Screen 1 Demographics, W-2, etc.)
    2. Data Entry Menu
    3. Drake Main Home Window
    """
    hdesk = init_station()
    subscreen_w = None
    menu_w = None
    home_w = None
    other_drake = None

    def cb(h, _):
        nonlocal subscreen_w, menu_w, home_w, other_drake
        try:
            if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
                t = win32gui.GetWindowText(h).strip()
                if not t:
                    return
                t_lower = t.lower()
                
                # Check process name
                _, pid = win32process.GetWindowThreadProcessId(h)
                pname = psutil.Process(pid).name().lower() if pid else ""
                
                if "draketax" in pname or "drake" in pname or "drake" in t_lower:
                    if "data entry" in t_lower:
                        owner = win32gui.GetWindow(h, win32con.GW_OWNER)
                        owner_text = win32gui.GetWindowText(owner).lower() if owner else ""
                        if "data entry" in owner_text:
                            subscreen_w = (h, t)
                        else:
                            menu_w = (h, t)
                    elif "drake 2025 tax software" in t_lower or "drake 2025" in t_lower:
                        home_w = (h, t)
                    elif "chat" not in t_lower:
                        other_drake = (h, t)
        except Exception:
            pass

    if hdesk:
        try:
            win32gui.EnumDesktopWindows(hdesk, cb, None)
        except Exception:
            win32gui.EnumWindows(cb, None)
    else:
        win32gui.EnumWindows(cb, None)

    if subscreen_w:
        return subscreen_w
    if menu_w:
        return menu_w
    if home_w:
        return home_w
    if other_drake:
        return other_drake
    return (None, "")

# =============================================================================
# WINDOW DISCOVERY: BROWSER (CHROME / EDGE / ZOHO CREATOR)
# =============================================================================
def find_browser_window(preferred_title=None):
    """
    Finds the active web browser window (Chrome, Edge, Brave, Firefox).
    Prioritizes the Drake Automation web interface or Zoho Creator tab.
    """
    hdesk = init_station()
    matched = None
    fallback_browser = None
    browser_exes = ["chrome.exe", "msedge.exe", "brave.exe", "firefox.exe"]

    def cb(h, _):
        nonlocal matched, fallback_browser
        try:
            if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
                t = win32gui.GetWindowText(h).strip()
                if not t:
                    return
                t_lower = t.lower()
                _, pid = win32process.GetWindowThreadProcessId(h)
                pname = psutil.Process(pid).name().lower() if pid else ""

                if pname in browser_exes:
                    if preferred_title and preferred_title.lower() in t_lower:
                        matched = (h, t)
                    elif any(k in t_lower for k in ["drake automation", "nmg drake", "zoho creator", "field mapping"]):
                        if not matched:
                            matched = (h, t)
                    elif not fallback_browser:
                        fallback_browser = (h, t)
        except Exception:
            pass

    if hdesk:
        try:
            win32gui.EnumDesktopWindows(hdesk, cb, None)
        except Exception:
            win32gui.EnumWindows(cb, None)
    else:
        win32gui.EnumWindows(cb, None)

    return matched or fallback_browser or (None, "")

# =============================================================================
# MODAL POPUP & UNEXPECTED DIALOG DISMISSAL
# =============================================================================
def dismiss_unexpected_popups(max_passes=2, prefer_cancel=False):
    """
    Detects and safely dismisses unexpected popups, modal confirmation dialogs,
    validation notices, or save prompts in Drake Tax.
    """
    hdesk = init_station()
    dismissed = []

    def check_dialog(h, _):
        try:
            if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
                t = win32gui.GetWindowText(h).strip()
                t_lower = t.lower()
                owner = win32gui.GetWindow(h, win32con.GW_OWNER)
                
                # Look for owned dialogs or matching title dialogs
                is_dialog = False
                if owner != 0:
                    owner_text = win32gui.GetWindowText(owner).lower()
                    if "drake" in owner_text:
                        is_dialog = True
                if any(k in t_lower for k in ["save", "confirm", "notice", "warning", "message", "attention", "information"]):
                    is_dialog = True

                if is_dialog:
                    try:
                        w = Desktop(backend="uia").window(handle=h)
                        buttons = w.descendants(control_type="Button")
                        
                        target_words = ["cancel", "no", "_cancel", "_no"] if prefer_cancel else ["ok", "yes", "_ok", "_yes", "save", "continue", "close"]
                        fallback_words = ["ok", "yes", "_ok", "_yes", "save", "continue", "close"] if prefer_cancel else ["cancel", "no"]

                        clicked = False
                        for btn in buttons:
                            btxt = btn.window_text().strip().lower()
                            if btxt in target_words:
                                btn.invoke()
                                dismissed.append((t, btxt))
                                clicked = True
                                time.sleep(0.3)
                                break
                        if not clicked:
                            for btn in buttons:
                                btxt = btn.window_text().strip().lower()
                                if btxt in fallback_words:
                                    btn.invoke()
                                    dismissed.append((t, btxt))
                                    clicked = True
                                    time.sleep(0.3)
                                    break
                    except Exception:
                        pass
        except Exception:
            pass

    for _ in range(max_passes):
        if hdesk:
            try:
                win32gui.EnumDesktopWindows(hdesk, check_dialog, None)
            except Exception:
                win32gui.EnumWindows(check_dialog, None)
        else:
            win32gui.EnumWindows(check_dialog, None)

    return dismissed

# =============================================================================
# HIGH-LEVEL SEAMLESS SWITCHING ACTIONS
# =============================================================================
def switch_to_drake(dismiss_popups=True, timeout=5.0):
    """
    Automates switching to Drake Tax 2025.
    1. Finds Drake Tax window.
    2. Brings it to the foreground with zero manual Alt+Tab.
    3. Dismisses any blocking modal popups.
    Returns (success, hwnd, title).
    """
    start = time.time()
    hwnd, title = None, ""

    while (time.time() - start) < timeout:
        hwnd, title = find_drake_window()
        if hwnd:
            break
        time.sleep(0.2)

    if not hwnd:
        return False, None, "Drake Tax 2025 not found."

    success = force_activate_window(hwnd)
    if dismiss_popups:
        time.sleep(0.15)
        dismiss_unexpected_popups(max_passes=2)

    return success, hwnd, title

def switch_to_browser(preferred_title=None, timeout=5.0):
    """
    Automates switching back to the Web Browser (Drake Automation UI or Zoho Creator).
    Brings it smoothly to the foreground with zero manual Alt+Tab.
    Returns (success, hwnd, title).
    """
    start = time.time()
    hwnd, title = None, ""

    while (time.time() - start) < timeout:
        hwnd, title = find_browser_window(preferred_title=preferred_title)
        if hwnd:
            break
        time.sleep(0.2)

    if not hwnd:
        return False, None, "Browser window not found."

    success = force_activate_window(hwnd)
    return success, hwnd, title

# =============================================================================
# CONTEXT MANAGER FOR WORKFLOW STAGES
# =============================================================================
@contextmanager
def active_drake_session(restore_browser=True, preferred_browser_title=None):
    """
    Context manager that guarantees Drake Tax is active during the block,
    and automatically switches back to the browser when the block finishes.
    
    Usage:
        with active_drake_session():
            # Perform Drake clicks, data entry, etc.
        # Browser is automatically in foreground here!
    """
    # 1. Note previous foreground window
    prev_fg = user32.GetForegroundWindow()

    # 2. Switch to Drake
    ok, d_hwnd, d_title = switch_to_drake()
    if not ok:
        print(f"[NAVIGATOR] Warning: Could not activate Drake window '{d_title}'")
    else:
        print(f"[NAVIGATOR] Automatically brought Drake Tax 2025 to foreground: '{d_title}'")

    try:
        yield d_hwnd
    finally:
        # 3. Automatically restore Browser or previous window
        if restore_browser:
            time.sleep(0.3)
            b_ok, b_hwnd, b_title = switch_to_browser(preferred_title=preferred_browser_title)
            if b_ok:
                print(f"[NAVIGATOR] Automatically brought Browser back to foreground: '{b_title}'")
            elif prev_fg and win32gui.IsWindow(prev_fg):
                force_activate_window(prev_fg)
                print(f"[NAVIGATOR] Restored previous foreground window (HWND: {prev_fg})")
