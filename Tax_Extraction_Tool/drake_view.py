"""
Real Drake Tax window inside / beside the W-2 mapping page.

Option A - "In-app live Drake":
    /api/drake-view/stream   MJPEG stream of the real Drake window (PrintWindow, so it keeps
                             updating even while the browser covers Drake). Drake dialogs that sit
                             on top of the window are composited in, so the user sees what Drake shows.
    /api/drake-view/layout   live position + label of every Drake input (UI Automation), used to
                             draw drop targets / arrows on top of the stream.
    /api/drake-view/input    click / double-click / right-click / wheel / keys / text from the page
                             are replayed on the real Drake window, then focus returns to the browser.

Option B - "Side-by-side windows":
    /api/drake-view/arrange  tiles the browser (left) and Drake (right) on the browser's monitor,
                             and restores the previous window positions on request.
    /api/drake-view/focus    puts the caret in a given Drake field (to locate it on screen).

Everything Windows-specific is imported lazily; on other machines the endpoints answer
{"success": false, "unavailable": true, ...} instead of crashing.
"""
import ctypes
import io
import threading
import time

from flask import Blueprint, Response, jsonify, request

import w2_mapping

drake_view_bp = Blueprint("drake_view", __name__)
DRAKE_VIEW_API_VERSION = 3


@drake_view_bp.record_once
def _announce(state):
    print("[drake-view] Live Drake view + side-by-side routes ready: /api/drake-view/{status,stream,layout,input,open-w2,arrange,focus}")

BROWSER_TITLE = "W-2 to Drake Mapping"      # must match <title> of templates/w2_mapping.html
STREAM_FPS = 8
JPEG_QUALITY = 72

_frame_lock = threading.Lock()
_input_lock = threading.Lock()
_layout_lock = threading.Lock()
_frame_cache = {"ts": 0.0, "jpg": None, "meta": None}
_layout_cache = {"ts": 0.0, "data": None}
_saved_placements = {}


class _Win:
    """Lazy holder for the Windows-only modules."""
    loaded = False

    @classmethod
    def load(cls):
        if cls.loaded:
            return cls
        try:
            import win32api
            import win32con
            import win32gui
            import win32process
            import win32ui
            from PIL import Image, ImageDraw, ImageGrab
            import drake_w2_filler as filler
            import app_navigator as nav
        except Exception as exc:
            raise w2_mapping.DrakeUnavailable(
                f"Live Drake view only works on the Windows PC where Drake is installed ({exc}).")
        cls.win32api, cls.win32con, cls.win32gui = win32api, win32con, win32gui
        cls.win32process, cls.win32ui = win32process, win32ui
        cls.Image, cls.ImageDraw, cls.ImageGrab = Image, ImageDraw, ImageGrab
        cls.filler, cls.nav = filler, nav
        cls.loaded = True
        return cls


def _com_init():
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Finding Drake's windows
# ---------------------------------------------------------------------------
def _pid_of(hwnd):
    W = _Win.load()
    try:
        return W.win32process.GetWindowThreadProcessId(hwnd)[1]
    except Exception:
        return None


def _owner(h):
    try:
        return ctypes.windll.user32.GetWindow(h, 4)          # GW_OWNER
    except Exception:
        return 0


def _owned_by(h, target, depth=8):
    o = _owner(h)
    while o and depth:
        if o == target:
            return True
        o, depth = _owner(o), depth - 1
    return False


def all_drake_windows():
    """Every visible top-level window of the Drake process, top of the z-order first."""
    W = _Win.load()
    hwnd, title = W.filler.find_drake_window()
    if not hwnd:
        return None, [], ""
    pid = _pid_of(hwnd)
    found = []

    def cb(h, _):
        try:
            if W.win32gui.IsWindowVisible(h) and _pid_of(h) == pid:
                l, t, r, b = W.win32gui.GetWindowRect(h)
                if r - l > 40 and b - t > 30:
                    found.append(h)
        except Exception:
            pass

    W.win32gui.EnumWindows(cb, None)          # EnumWindows walks top -> bottom z-order
    return hwnd, (found or [hwnd]), title


def drake_windows():
    """The Drake window the user is working in, framed for the live view.
    Returns (frame_hwnd, [overlay windows above it, top first] + [frame_hwnd], title).

    frame  = Screen W2 / other sub-screen if open, else the Data Entry window, else the home window
             (the same priority the automation uses).
    overlay = only windows that belong to that work window (its message boxes / pick lists),
              never the home window or Drake's separate chat window."""
    W = _Win.load()
    frame, wins, title = all_drake_windows()
    if not frame:
        return None, [], ""
    idx = wins.index(frame) if frame in wins else len(wins)
    owner = _owner(frame)
    overlays = []
    for h in wins[:idx]:                        # windows above the frame
        try:
            t = (W.win32gui.GetWindowText(h) or "").lower()
            if "chat" in t:
                continue
            if _owned_by(h, frame) or (owner and _owned_by(h, owner) and "data entry" not in t
                                         and "tax software" not in t):
                overlays.append(h)
        except Exception:
            continue
    return frame, overlays + [frame], title


def _print_window(hwnd):
    """Image of one window even if it is covered by other windows."""
    W = _Win.load()
    g = W.win32gui
    l, t, r, b = g.GetWindowRect(hwnd)
    w, h = r - l, b - t
    if w <= 0 or h <= 0:
        return None
    hdc = g.GetWindowDC(hwnd)
    src = W.win32ui.CreateDCFromHandle(hdc)
    mem = src.CreateCompatibleDC()
    bmp = W.win32ui.CreateBitmap()
    try:
        bmp.CreateCompatibleBitmap(src, w, h)
        mem.SelectObject(bmp)
        ok = ctypes.windll.user32.PrintWindow(hwnd, mem.GetSafeHdc(), 2)   # 2 = PW_RENDERFULLCONTENT
        img = W.Image.frombuffer("RGB", (w, h), bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1) if ok else None
    finally:
        try:
            g.DeleteObject(bmp.GetHandle())
        except Exception:
            pass
        mem.DeleteDC()
        src.DeleteDC()
        g.ReleaseDC(hwnd, hdc)
    if img is None:   # fallback: plain screen grab (only correct when Drake is visible)
        img = W.ImageGrab.grab(bbox=(l, t, r, b), all_screens=True)
    return img


def _placeholder(text):
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    img = Image.new("RGB", (960, 540), (236, 240, 245))
    d = ImageDraw.Draw(img)
    d.text((40, 250), text, fill=(70, 80, 95))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def capture_frame():
    """Composite of Drake's main window and every Drake window above it (subscreens, dialogs)."""
    W = _Win.load()
    g = W.win32gui
    main, wins, title = drake_windows()
    if not main:
        return None, {"running": False}
    if g.IsIconic(main):
        g.ShowWindow(main, 4)            # SW_SHOWNOACTIVATE: un-minimise without stealing focus
        time.sleep(0.15)
    ml, mt, mr, mb = g.GetWindowRect(main)
    frame = _print_window(main)
    if frame is None:
        return None, {"running": True, "error": "Drake window has no size"}
    idx = wins.index(main) if main in wins else len(wins)
    for h in reversed(wins[:idx]):       # paint bottom-most first so the top window ends on top
        try:
            l, t, r, b = g.GetWindowRect(h)
            if r <= ml or l >= mr or b <= mt or t >= mb:
                continue
            img = _print_window(h)
            if img is not None:
                frame.paste(img, (l - ml, t - mt))
        except Exception:
            continue
    meta = {"running": True, "title": title, "x": ml, "y": mt, "w": mr - ml, "h": mb - mt,
            "main": main, "windows": len(wins)}
    return frame, meta


def get_frame():
    """Shared, throttled capture so several viewers don't multiply the work."""
    with _frame_lock:
        now = time.time()
        if _frame_cache["jpg"] is not None and now - _frame_cache["ts"] < 1.0 / STREAM_FPS:
            return _frame_cache["jpg"], _frame_cache["meta"]
        try:
            frame, meta = capture_frame()
        except w2_mapping.DrakeUnavailable:
            raise
        except Exception as exc:
            frame, meta = None, {"running": False, "error": str(exc)}
        if frame is None:
            jpg = _placeholder("Drake Tax 2025 is not running - start Drake and this view will appear here.")
        else:
            buf = io.BytesIO()
            frame.save(buf, "JPEG", quality=JPEG_QUALITY)
            jpg = buf.getvalue()
        _frame_cache.update(ts=now, jpg=jpg, meta=meta)
        return jpg, meta


# ---------------------------------------------------------------------------
# Live layout of Drake inputs (for drop targets / arrows on top of the stream)
# ---------------------------------------------------------------------------
def build_layout():
    W = _Win.load()
    _com_init()
    from pywinauto import Desktop
    main, wins, title = drake_windows()
    if not main:
        return {"running": False}
    ml, mt, mr, mb = W.win32gui.GetWindowRect(main)
    hwnd = main
    state = "UNKNOWN"
    controls = []
    try:
        win = Desktop(backend="uia").window(handle=hwnd)
        state = W.filler.get_current_drake_state(win)
        if state == "W2_SCREEN":
            texts = []
            for t in win.descendants(control_type="Text"):
                try:
                    s = t.window_text().strip()
                    if s:
                        texts.append((s.rstrip(":"), t.rectangle()))
                except Exception:
                    pass
            for aid, (kind, c) in w2_mapping._collect_controls(win).items():
                try:
                    r = c.rectangle()
                    if r.width() <= 2 or r.height() <= 2:
                        continue
                    known = w2_mapping.DRAKE_FIELDS_BY_ID.get(aid)
                    value = w2_mapping._read_back(kind, c)       # what Drake currently shows in the field
                    controls.append({"id": aid, "control": kind,
                                     "x": r.left - ml, "y": r.top - mt, "w": r.width(), "h": r.height(),
                                     "live_label": w2_mapping._nearest_label(r, texts),
                                     "label": known["label"] if known else "", "known": bool(known),
                                     "value": value})
                except Exception:
                    continue
    except Exception as exc:
        return {"running": True, "title": title, "state": "UNKNOWN", "error": str(exc),
                "frame": {"w": mr - ml, "h": mb - mt}, "controls": []}
    dialogs = [W.win32gui.GetWindowText(h) or "Drake message" for h in wins if h != main]
    return {"running": True, "title": title, "state": state, "frame": {"w": mr - ml, "h": mb - mt},
            "controls": controls, "dialogs": dialogs}


# ---------------------------------------------------------------------------
# Input passthrough (page -> real Drake)
# ---------------------------------------------------------------------------
_KEYMAP = {"Enter": "enter", "Tab": "tab", "Backspace": "backspace", "Delete": "delete", "Escape": "esc",
           "ArrowUp": "up", "ArrowDown": "down", "ArrowLeft": "left", "ArrowRight": "right",
           "Home": "home", "End": "end", "PageUp": "pageup", "PageDown": "pagedown", "Insert": "insert",
           " ": "space"}
_KEYMAP.update({f"F{i}": f"f{i}" for i in range(1, 13)})


def _activate_at(sx, sy, main):
    """Bring forward the Drake window that is under (sx, sy) in Drake's own stacking order."""
    W = _Win.load()
    g = W.win32gui
    _, wins, _ = drake_windows()
    target = main
    for h in wins:                         # top-most first
        l, t, r, b = g.GetWindowRect(h)
        if l <= sx < r and t <= sy < b:
            target = h
            break
    W.nav.force_activate_window(target, delay_after=0.12)
    return target


def replay_input(events, return_focus=True):
    import pyautogui
    W = _Win.load()
    g = W.win32gui
    main, _, _ = drake_windows()
    if not main:
        raise RuntimeError("Drake is not running.")
    ml, mt, mr, mb = g.GetWindowRect(main)
    with _input_lock:
        activated = False
        for ev in events:
            kind = ev.get("type")
            if kind in ("click", "dblclick", "rightclick", "scroll"):
                sx, sy = ml + int(ev.get("x", 0)), mt + int(ev.get("y", 0))
                if not (ml <= sx < mr and mt <= sy < mb):
                    continue
                if not activated:
                    _activate_at(sx, sy, main)
                    activated = True
                if kind == "click":
                    pyautogui.click(sx, sy)
                elif kind == "dblclick":
                    pyautogui.doubleClick(sx, sy)
                elif kind == "rightclick":
                    pyautogui.rightClick(sx, sy)
                else:
                    pyautogui.scroll(int(ev.get("delta", 0)), x=sx, y=sy)
            elif kind in ("key", "text"):
                if not activated:
                    W.nav.force_activate_window(main, delay_after=0.12)
                    activated = True
                if kind == "text":
                    pyautogui.write(str(ev.get("text", "")), interval=0)
                else:
                    key = _KEYMAP.get(ev.get("key"), str(ev.get("key", "")).lower())
                    mods = [m for m in ev.get("mods", []) if m in ("ctrl", "shift", "alt")]
                    if mods:
                        pyautogui.hotkey(*mods, key)
                    else:
                        pyautogui.press(key)
        if activated and return_focus:
            time.sleep(0.08)
            W.nav.switch_to_browser(preferred_title=BROWSER_TITLE)
    with _frame_lock:
        _frame_cache["ts"] = 0          # next frame is fresh
    with _layout_lock:
        _layout_cache["ts"] = 0


# ---------------------------------------------------------------------------
# Option B: side-by-side windows
# ---------------------------------------------------------------------------
def _frame_margins(hwnd):
    """Win10/11 windows have invisible resize borders; return how far the visible frame is inset."""
    W = _Win.load()
    try:
        import ctypes.wintypes as wt
        rect = wt.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(wt.HWND(hwnd), 9, ctypes.byref(rect), ctypes.sizeof(rect))
        l, t, r, b = W.win32gui.GetWindowRect(hwnd)
        return rect.left - l, rect.top - t, r - rect.right, b - rect.bottom
    except Exception:
        return 0, 0, 0, 0


def _place(hwnd, x, y, w, h):
    W = _Win.load()
    W.win32gui.ShowWindow(hwnd, W.win32con.SW_RESTORE)
    ml, mt, mr, mb = _frame_margins(hwnd)
    W.win32gui.MoveWindow(hwnd, x - ml, y - mt, w + ml + mr, h + mt + mb, True)


def arrange_side_by_side(split=0.5):
    W = _Win.load()
    g = W.win32gui
    bh, btitle = W.nav.find_browser_window(preferred_title=BROWSER_TITLE)
    if not bh:
        raise RuntimeError("Could not find the browser window showing the mapping page.")
    main, wins, title = all_drake_windows()
    if not main:
        raise RuntimeError("Drake Tax 2025 is not running. Start Drake, then click 'Arrange windows' again.")
    mon = W.win32api.MonitorFromWindow(bh, 2)                   # MONITOR_DEFAULTTONEAREST
    wl, wt_, wr, wb = W.win32api.GetMonitorInfo(mon)["Work"]
    width, height = wr - wl, wb - wt_
    left_w = int(width * split)
    big = [h for h in wins if (g.GetWindowRect(h)[2] - g.GetWindowRect(h)[0]) >= 500]
    for h in [bh] + big:
        if h not in _saved_placements:
            try:
                _saved_placements[h] = g.GetWindowPlacement(h)
            except Exception:
                pass
    _place(bh, wl, wt_, left_w, height)
    for h in reversed(big):                                     # keep Drake's own stacking order
        _place(h, wl + left_w, wt_, width - left_w, height)
    W.nav.force_activate_window(main, delay_after=0.1)
    W.nav.force_activate_window(bh, delay_after=0.05)
    return {"browser": btitle, "drake": title, "drake_windows": len(big),
            "monitor": {"x": wl, "y": wt_, "w": width, "h": height}}


def restore_windows():
    W = _Win.load()
    restored = 0
    for h, placement in list(_saved_placements.items()):
        try:
            if W.win32gui.IsWindow(h):
                W.win32gui.SetWindowPlacement(h, placement)
                restored += 1
        except Exception:
            pass
    _saved_placements.clear()
    bh, _ = W.nav.find_browser_window(preferred_title=BROWSER_TITLE)
    if bh and not restored:
        W.win32gui.ShowWindow(bh, W.win32con.SW_MAXIMIZE)
    return {"restored": restored}


def focus_field(aid):
    W = _Win.load()
    _com_init()
    from pywinauto import Desktop
    hwnd, _ = W.filler.find_drake_window()
    if not hwnd:
        raise RuntimeError("Drake is not running.")
    win = Desktop(backend="uia").window(handle=hwnd)
    if W.filler.get_current_drake_state(win) != "W2_SCREEN":
        raise RuntimeError("Open Screen W2 in Drake first.")
    entry = w2_mapping._collect_controls(win).get(aid)
    if not entry:
        raise RuntimeError(f"Field {aid} is not on the open Drake screen.")
    W.nav.force_activate_window(hwnd, delay_after=0.05)
    kind, ctrl = entry
    target = ctrl
    if kind == "combo":
        inner = ctrl.descendants(control_type="Edit")
        target = inner[0] if inner else ctrl
    target.set_focus()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def _fail(exc):
    if isinstance(exc, w2_mapping.DrakeUnavailable):
        return jsonify({"success": False, "unavailable": True, "error": str(exc)})
    return jsonify({"success": False, "error": str(exc)})


@drake_view_bp.route("/api/drake-view/stream")
def api_stream():
    try:
        _Win.load()
    except w2_mapping.DrakeUnavailable as exc:
        return jsonify({"success": False, "unavailable": True, "error": str(exc)}), 503

    def gen():
        while True:
            try:
                jpg, _ = get_frame()
            except Exception:
                jpg = _placeholder("Live view error - retrying...")
            if jpg:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                       + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
            time.sleep(1.0 / STREAM_FPS)

    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame",
                    headers={"Cache-Control": "no-store"})


@drake_view_bp.route("/api/drake-view/layout")
def api_layout():
    try:
        _Win.load()
        with _layout_lock:
            now = time.time()
            busy = w2_mapping._drake_lock.locked()
            if _layout_cache["data"] is not None and (busy or now - _layout_cache["ts"] < 1.0):
                return jsonify({"success": True, "busy": busy, **_layout_cache["data"]})
            data = build_layout()
            _layout_cache.update(ts=now, data=data)
        return jsonify({"success": True, "busy": busy, **data})
    except Exception as exc:
        return _fail(exc)


@drake_view_bp.route("/api/drake-view/input", methods=["POST"])
def api_input():
    payload = request.get_json(silent=True) or {}
    events = payload.get("events") or []
    if not isinstance(events, list) or not events:
        return jsonify({"success": False, "error": "No input events"}), 400
    if w2_mapping._drake_lock.locked():
        return jsonify({"success": False, "error": "Drake is busy being filled - wait for it to finish."}), 409
    try:
        replay_input(events[:200], return_focus=payload.get("return_focus", True))
        return jsonify({"success": True})
    except Exception as exc:
        return _fail(exc)


@drake_view_bp.route("/api/drake-view/open-w2", methods=["POST"])
def api_open_w2():
    payload = request.get_json(silent=True) or {}
    logs = []
    try:
        _Win.load()
        with w2_mapping._drake_lock:
            w2_mapping.goto_w2_screen(payload.get("client") or {}, logs.append)
        if payload.get("return_focus", True):
            _Win.nav.switch_to_browser(preferred_title=BROWSER_TITLE)
        with _layout_lock:
            _layout_cache["ts"] = 0
        return jsonify({"success": True, "logs": logs})
    except Exception as exc:
        resp = _fail(exc).get_json()
        resp["logs"] = logs
        return jsonify(resp)


@drake_view_bp.route("/api/drake-view/arrange", methods=["POST"])
def api_arrange():
    payload = request.get_json(silent=True) or {}
    try:
        if payload.get("mode") == "restore":
            return jsonify({"success": True, **restore_windows()})
        split = min(max(float(payload.get("split", 0.5)), 0.3), 0.7)
        return jsonify({"success": True, **arrange_side_by_side(split)})
    except Exception as exc:
        return _fail(exc)


@drake_view_bp.route("/api/drake-view/focus", methods=["POST"])
def api_focus():
    payload = request.get_json(silent=True) or {}
    try:
        focus_field(str(payload.get("id", "")))
        return jsonify({"success": True})
    except Exception as exc:
        return _fail(exc)


@drake_view_bp.route("/api/drake-view/status")
def api_status():
    try:
        _Win.load()
        main, wins, title = all_drake_windows()
        return jsonify({"success": True, "version": DRAKE_VIEW_API_VERSION, "running": bool(main), "title": title,
                        "windows": len(wins), "side_by_side": bool(_saved_placements)})
    except Exception as exc:
        return _fail(exc)
