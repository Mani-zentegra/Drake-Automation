"""
Drake Tax transfer of confirmed values, and Drake field discovery ("Link Drake fields").

Safety rules
  * Only reviewed, included documents and their confirmed values are sent (session.transfer_plan).
  * A field is typed into Drake only through a known automation id — built into the catalog (ids the
    existing automation already uses) or linked by the reviewer with "Link Drake fields". Fields without an
    id are reported as "not linked"; nothing is ever skipped silently.
  * Every value is read back from Drake after it is entered (verified / mismatch / failed).
  * A record that already holds data is not overwritten unless the reviewer asked for it.

Windows-only modules are imported lazily; dry runs work everywhere.
"""
import json
import os
import re
import threading
import time

from . import catalog, session

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINKS_FILE = os.path.join(BASE, "taxflow_drake_links.json")
_run_lock = threading.Lock()


class DrakeUnavailable(Exception):
    pass


# ---------------------------------------------------------------------------
# links: Drake automation ids per screen + field key
# ---------------------------------------------------------------------------
def load_links():
    try:
        with open(LINKS_FILE, "r", encoding="utf-8") as fh:
            d = json.load(fh)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_links(screen, links):
    d = load_links()
    clean = {}
    for k, spec in (links or {}).items():
        if not isinstance(spec, dict):
            continue
        aid = str(spec.get("aid", ""))
        if not re.fullmatch(r"[A-Za-z]+_?\w*", aid) or len(aid) > 60:
            continue
        clean[str(k)[:60]] = {"aid": aid, "control": spec.get("control") if spec.get("control") in ("edit", "combo", "checkbox") else "edit",
                              "label": str(spec.get("label", ""))[:80]}
    d[str(screen)] = {**d.get(str(screen), {}), **clean}
    for k, spec in (links or {}).items():
        if spec is None:
            d[str(screen)].pop(k, None)
    with open(LINKS_FILE, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=2)
    return d[str(screen)]


def resolve(screen, field, links=None):
    links = links if links is not None else load_links()
    sp = (links.get(str(screen)) or {}).get(field["key"])
    if sp:
        return sp["aid"], sp.get("control") or field.get("control") or "edit", "linked"
    if field.get("aid"):
        return field["aid"], field.get("control") or "edit", "built-in"
    return None, None, None


def link_status(screen, fields):
    links = load_links()
    out = {}
    for f in fields:
        aid, ctl, how = resolve(screen, f, links)
        out[f["key"]] = {"aid": aid, "control": ctl, "how": how}
    return out


# ---------------------------------------------------------------------------
# Drake modules (Windows)
# ---------------------------------------------------------------------------
def _drake():
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pass
    try:
        import drake_packet_filler as pf
        import drake_w2_filler as wf
        import app_navigator as nav
        import w2_mapping
        from pywinauto import Desktop
    except Exception as exc:
        raise DrakeUnavailable(f"Drake automation only runs on the Windows PC where Drake Tax is installed ({exc}).")
    return pf, wf, nav, w2_mapping, Desktop


def _exit_prompt_open():
    """Drake's 'exit the program?' dialog — must be answered by a person, never by the automation."""
    try:
        import win32gui
    except Exception:
        return False
    found = []
    win32gui.EnumWindows(lambda h, _: found.append(h) if win32gui.IsWindowVisible(h)
                         and "close program" in win32gui.GetWindowText(h).lower() else None, None)
    return bool(found)


# ---------------------------------------------------------------------------
# Drake windows / dialogs (automation ids read from Drake Tax 2025)
# ---------------------------------------------------------------------------
def _drake_windows():
    import psutil
    import win32gui
    import win32process
    out = []

    def cb(h, _):
        try:
            if not win32gui.IsWindowVisible(h):
                return
            _, pid = win32process.GetWindowThreadProcessId(h)
            if "drake" in psutil.Process(pid).name().lower():
                t = win32gui.GetWindowText(h) or ""
                if "chat" not in t.lower():
                    out.append((h, t))
        except Exception:
            pass
    win32gui.EnumWindows(cb, None)
    return out


def _find(title_part):
    return next(((h, t) for h, t in _drake_windows() if title_part in t.lower()), (None, ""))


def _by_aid(win, aid, ctype=None):
    for c in win.descendants(control_type=ctype) if ctype else win.descendants():
        try:
            if c.element_info.automation_id == aid:
                return c
        except Exception:
            continue
    return None


def _message_boxes(Desktop):
    """Drake message boxes (CustomMessageBoxWindow) -> [(window, text, {button_text: button})]."""
    out = []
    for h, t in _drake_windows():
        if "data entry" in t.lower() or t.strip() in ("Drake 2025 Tax Software", ""):
            continue
        try:
            w = Desktop(backend="uia").window(handle=h)
            msg = _by_aid(w, "CustomMessageBoxWindow_TextBlockMessage", "Text")
            if msg is None:
                if "close program" not in t.lower():
                    continue                      # not a message box (Open/Create, New Return, ... are handled elsewhere)
                text = " ".join(x.window_text() for x in w.descendants(control_type="Text") if x.window_text())
            else:
                text = msg.window_text()
            btns = {b.window_text().strip().lower(): b for b in w.descendants(control_type="Button") if b.window_text().strip()}
            btns.pop("close", None) if len(btns) > 1 else None
            out.append((w, f"{t}: {text}".replace("\r", " ").replace("\n", " "), btns))
        except Exception:
            continue
    return out


def popup_check(log, Desktop=None):
    """After typing a value: acknowledge Drake notices that only offer OK; leave every real question to the user."""
    try:
        if Desktop is None:
            from pywinauto import Desktop
        notes = []
        for w, text, btns in _message_boxes(Desktop):
            low = text.lower()
            if "exit" in low and ("drake" in low or "close program" in low):
                raise RuntimeError("Drake is asking whether to exit the program — answer it in Drake (No), then retry.")
            if set(btns) <= {"ok", "_ok"} and btns:
                list(btns.values())[0].invoke()
                time.sleep(0.3)
                log(f"[DRAKE NOTICE] {text}")
                notes.append(text)
            elif "e-file" in low or "to exit this screen" in low or "fields on this screen" in low:
                continue                                  # handled when the screen is exited
            else:
                raise RuntimeError(f"Drake is asking a question the automation will not answer: {text}")
        return " | ".join(notes)
    except RuntimeError:
        raise
    except Exception:
        return ""


def open_return(ssn, first, mi, last, log, pf, nav, Desktop):
    """Open the return for this SSN, or create it (Individual 1040) when Drake says it does not exist."""
    menu = pf.find_menu_window()
    if menu:
        digits = re.sub(r"\D", "", menu[1])
        if ssn in digits:
            log(f"[DRAKE] The return is already open: {menu[1]}")
            return
        raise RuntimeError(f"Drake has a different return open ('{menu[1]}'). Close it in Drake, then start the transfer again.")
    main_h, _ = _find("drake 2025 tax software")
    if not main_h:
        raise RuntimeError("Drake Tax 2025 is not running. Start Drake and try again.")
    nav.force_activate_window(main_h)
    dlg_h, _ = _find("open / create a return")
    if not dlg_h:
        main = Desktop(backend="uia").window(handle=main_h)
        t = _by_aid(main, "MainWindow_TextBlockToolbarOpenCreate", "Text")
        if t is None:
            raise RuntimeError("Could not find Drake's Open/Create button.")
        clicked = False
        try:
            p = t.parent()
            if p.element_info.control_type == "Button":
                p.invoke()
                clicked = True
        except Exception:
            pass
        if not clicked:
            t.click_input()
        for _ in range(30):
            time.sleep(0.25)
            dlg_h, _ = _find("open / create a return")
            if dlg_h:
                break
    if not dlg_h:
        raise RuntimeError("Drake's 'Open / Create a Return' window did not appear.")
    dlg = Desktop(backend="uia").window(handle=dlg_h)
    box = _by_aid(dlg, "ClearableWatermarkTextbox_TextBoxInput", "Edit")
    okb = _by_aid(dlg, "FileOpenCreateWindow_ButtonOK", "Button")
    if box is None or okb is None:
        raise RuntimeError("The Open / Create window does not look as expected — open the return in Drake manually.")
    box.iface_value.SetValue(ssn)
    time.sleep(0.3)
    log(f"[DRAKE] Opening the return for SSN ***-**-{ssn[-4:]}…")
    okb.invoke()
    created = False
    for _ in range(80):
        time.sleep(0.25)
        menu = pf.find_menu_window()
        if menu and ssn in re.sub(r"\D", "", menu[1]):
            log(f"[DRAKE] {'Created and opened' if created else 'Opened'} the return: {menu[1]}")
            time.sleep(1.0)
            return
        nr_h, _ = _find("new return")
        if nr_h:
            nr = Desktop(backend="uia").window(handle=nr_h)
            rb = _by_aid(nr, "CreateReturnWindow_RadioButtonIndividual", "RadioButton")
            if rb is None:
                raise RuntimeError("Drake's New Return window does not look as expected — create the return manually.")
            try:
                rb.select()
            except Exception:
                rb.click_input()
            for aid, v in (("CreateReturnWindow_TextBoxFirstName", first), ("CreateReturnWindow_TextBoxMiddleInitial", (mi or "")[:1]),
                           ("CreateReturnWindow_TextBoxLastName", last)):
                e = _by_aid(nr, aid, "Edit")
                if e is not None and v:
                    e.iface_value.SetValue(str(v))
            log(f"[DRAKE] Creating a new Individual (1040) return for {first} {last}…")
            _by_aid(nr, "UCButtonsControl_ButtonOk", "Button").invoke()
            created = True
            continue
        for w, text, btns in _message_boxes(Desktop):
            low = text.lower()
            if "does not exist" in low and "create" in low and "yes" in btns:
                log(f"[DRAKE] {ssn[:0]}SSN ***-**-{ssn[-4:]} has no return yet — answering Yes to create it.")
                btns["yes"].invoke()
                break
            raise RuntimeError(f"Drake showed a message the automation will not answer: {text}")
    raise RuntimeError("Drake did not open the return within 20 seconds.")


SCREEN_TITLES = {"1": "Name, Address", "W2": "Form W-2", "INT": "1099-INT", "DIV": "1099-DIV", "1099": "Form 1099-R",
                 "99M": "1099-MISC", "OID": "1099-OID", "SSA": "SSA-1099", "A": "Schedule A", "8949": "Form 8949",
                 "99G": "1099-G", "99N": "1099-NEC", "W2G": "W-2G", "1116": "Form 1116"}


def _pick_record(record, create, log, Desktop):
    """Drake's 'Existing Forms List' (shown when a screen already has records): select record N, or the
    'New Record' row. Returns 'existing' | 'new' | None (no list shown) | raises when the record is missing."""
    lst_h = None
    for _ in range(12):
        lst_h, _t = _find("existing forms list")
        if lst_h:
            break
        time.sleep(0.15)
    if not lst_h:
        return None
    lw = Desktop(backend="uia").window(handle=lst_h)
    rows = lw.descendants(control_type="DataItem")
    target, kind = None, None
    for row in rows:
        cells = [c.window_text().strip() for c in row.descendants(control_type="Text") if c.window_text().strip()]
        first = cells[0] if cells else ""
        if first == str(record):
            target, kind = row, "existing"
            break
        if first.lower() == "new" and create:
            target, kind = row, "new"
    if target is None:
        _by_aid(lw, "MultiInstanceSelectionWindow_ButtonCancel", "Button").invoke()
        raise RuntimeError(f"Drake has no record {record} on this screen.")
    try:
        target.select()
    except Exception:
        target.click_input()
    time.sleep(0.3)
    log(f"[RECORD] Drake forms list: opening {'record ' + str(record) if kind == 'existing' else 'a new record'}.")
    _by_aid(lw, "MultiInstanceSelectionWindow_ButtonOpen", "Button").invoke()
    return kind


def _visible_screens(Desktop):
    """On-screen Drake sub-screens (owned by the Data Entry window). Drake parks hidden copies at y≈10000."""
    import win32gui
    out = []
    for h, t in _drake_windows():
        if "data entry" not in t.lower():
            continue
        o = win32gui.GetWindow(h, 4)
        if not o or "data entry" not in (win32gui.GetWindowText(o) or "").lower():
            continue
        if win32gui.GetWindowRect(h)[1] > 5000:
            continue
        out.append(h)
    return out


def _grid_window(Desktop):
    for h in _visible_screens(Desktop):
        w = Desktop(backend="uia").window(handle=h)
        if _by_aid(w, "ButtonItemDetail", "Button") is not None:
            return w
    return None


def _grid_pick(grid, record, create, log, Desktop):
    """Drake grid mode (INT, DIV, ... once a record exists): select row N (or the blank new row) and open Item Detail."""
    inst = _by_aid(grid, "txtInstance", "Text")
    m = re.search(r"of\s+(\d+)", inst.window_text() if inst else "")
    total = int(m.group(1)) if m else 0
    existing = max(0, total - 1)                          # the last grid row is the blank "new" row
    rows = grid.descendants(control_type="DataItem")
    if record <= existing:
        idx, kind = record - 1, "existing"
    elif create:
        idx, kind = len(rows) - 1, "new"
    else:
        _by_aid(grid, "ButtonCancel", "Button").invoke()
        raise RuntimeError(f"Drake has no record {record} on this screen ({existing} record(s)).")
    row = rows[idx]
    try:
        row.select()
    except Exception:
        row.click_input()
    time.sleep(0.3)
    now = _by_aid(grid, "txtInstance", "Text")
    if now and f"Row: {idx + 1} of" not in now.window_text():
        _by_aid(grid, "ButtonCancel", "Button").invoke()
        raise RuntimeError(f"Could not select row {idx + 1} in Drake's grid ({now.window_text()}).")
    log(f"[RECORD] Drake grid: opening {'record ' + str(record) if kind == 'existing' else 'a new record'} in Item Detail.")
    _by_aid(grid, "ButtonItemDetail", "Button").invoke()
    return kind


def _enter(target, val):
    """Type one value into one Drake field: the cursor must be in that exact field (never blind typing), then
    Tab out so Drake commits it (Drake saves a field when it loses focus)."""
    from pywinauto import keyboard
    try:
        if target.iface_value.CurrentIsReadOnly:
            raise RuntimeError("Drake shows this field as read-only — nothing typed")
    except AttributeError:
        pass
    target.set_focus()
    time.sleep(0.08)
    if not target.has_keyboard_focus():
        raise RuntimeError("Could not put the cursor in this Drake field — nothing typed")
    target.iface_value.SetValue(str(val))
    keyboard.send_keys("{TAB}")
    time.sleep(0.12)


def open_record(code, record, log, pf, Desktop, create=True):
    """Open record N of a Drake screen (or a new record when it does not exist yet). Returns (window, 'existing'|'new')."""
    return open_screen(code, log, pf, Desktop, record=record, create=create)


def open_screen(code, log, pf, Desktop, record=1, create=True):
    """Open a Drake screen from the Data Entry menu and make sure it is the right one before anything is typed."""
    if pf.find_subscreen_window():
        pf.exit_current_subscreen(log)
        time.sleep(0.5)
    menu = pf.find_menu_window()
    if not menu:
        raise RuntimeError("Drake's Data Entry menu is not open.")
    mw = Desktop(backend="uia").window(handle=menu[0])
    btn = next((b for b in mw.descendants(control_type="Button")
                if b.window_text().split("|")[0].strip().upper() == code.upper() and "|" in b.window_text()), None)
    if btn is not None:
        btn.invoke()
    else:
        box = _by_aid(mw, "MenuScreenWindow_TextBoxSearch", "Edit")
        if box is None:
            return pf.open_drake_screen(code, log)
        import pyautogui
        box.set_focus()
        box.set_edit_text(code)
        time.sleep(0.2)
        pyautogui.press("enter")
    picked = _pick_record(record, create, log, Desktop)
    win = None
    for _ in range(40):
        time.sleep(0.15)
        if _visible_screens(Desktop):
            break
    grid = _grid_window(Desktop)
    if grid is not None:
        if picked is not None:
            raise RuntimeError("Drake showed both a forms list and a grid — open the screen manually.")
        picked = _grid_pick(grid, record, create, log, Desktop)
        for _ in range(40):
            time.sleep(0.15)
            if _visible_screens(Desktop) and _grid_window(Desktop) is None:
                break
    elif picked is None and record > 1 and not create:
        # no forms list and no grid -> the screen has no records yet, so record N>1 cannot exist
        pf.exit_current_subscreen(log)
        raise RuntimeError(f"Drake has no record {record} on screen {code}.")
    hs = [h for h in _visible_screens(Desktop)]
    if not hs:
        raise RuntimeError(f"Drake screen {code} did not open.")
    win = Desktop(backend="uia").window(handle=hs[-1])
    want = SCREEN_TITLES.get(code.upper())
    if want:
        time.sleep(0.3)
        texts = " ".join(t.window_text() for t in win.descendants(control_type="Text"))
        if want.lower() not in texts.lower():
            pf.exit_current_subscreen(log)
            raise RuntimeError(f"Drake opened a different screen than {code} (expected '{want}') — nothing was typed.")
    log(f"[NAVIGATE] Screen {code} is open" + (f" ({picked} record {record})" if picked == "existing" else
                                                " (new record)" if picked == "new" else "") + ".")
    return win


def verify_saved(groups, tr, log, pf, w2m, Desktop):
    """Second read-back: reopen every screen after it was saved and check each entered value is still there."""
    log("\n[VERIFY] Re-opening every screen to check the saved values…")
    for g in groups:
        sent = g.get("sent")
        if not sent:
            continue
        for p, items in sent:
            try:
                win = open_record(g["screen"], p["drake_record"], log, pf, Desktop, create=False)
            except Exception as exc:
                log(f"[VERIFY] Screen {g['screen']} record {p['drake_record']} could not be reopened: {exc}")
                for it in items:
                    r = next((x for x in tr["results"] if x["doc_id"] == p["doc_id"] and x["key"] == it["key"]), None)
                    if r and r["status"] == "verified":
                        r["status"] = "not_saved"
                        r["message"] = f"Could not reopen record {p['drake_record']} to confirm it was saved: {exc}"
                continue
            time.sleep(0.4)
            edits, combos, checks = _controls(win)
            for it in items:
                r = next((x for x in tr["results"] if x["doc_id"] == p["doc_id"] and x["key"] == it["key"]), None)
                if not r or r["status"] != "verified":
                    continue
                kind, ctrl = _kind_ctrl(it["aid"], it["control"], edits, combos, checks)
                actual = w2m._read_back(kind, ctrl) if ctrl is not None else None
                val = _drake_text(it["type"], it["value"])
                if ctrl is not None and _same(it["type"], val, actual, w2m):
                    r["message"] += " · still there after saving ✓"
                    r["saved"] = True
                elif (ctrl is not None and it["type"] in ("text", "name") and actual and len(actual) >= 20
                      and str(val).upper().startswith(str(actual).upper())):
                    r["message"] = f"Saved — Drake keeps the first {len(actual)} characters of this field: {actual!r}"
                    r["saved"] = True
                else:
                    r["status"] = "not_saved"
                    r["message"] = f"Entered, but after saving and reopening Drake shows {actual!r}"
                    log(f"[VERIFY] {p['type']} {it['label']}: expected {val}, Drake now shows {actual!r}")
            pf.exit_current_subscreen(log)
            time.sleep(0.4)
    ok = sum(1 for r in tr["results"] if r.get("saved"))
    log(f"[VERIFY] {ok} value(s) confirmed in Drake after saving.")


def _controls(win):
    edits, combos, checks = {}, {}, {}
    for ctype, store in (("Edit", edits), ("ComboBox", combos), ("CheckBox", checks)):
        try:
            for c in win.descendants(control_type=ctype):
                aid = c.element_info.automation_id
                if aid and aid != "PART_EditableTextBox" and aid not in store:
                    store[aid] = c
        except Exception:
            pass
    return edits, combos, checks


def _kind_ctrl(aid, control, edits, combos, checks):
    if aid in checks:
        return "checkbox", checks[aid]
    if aid in combos:
        return "combo", combos[aid]
    if aid in edits:
        return "edit", edits[aid]
    return None, None


def _drake_text(ftype, value):
    if isinstance(value, bool):
        return value
    s = str(value).strip()
    if ftype in ("ssn", "ein", "tin"):
        return re.sub(r"\D", "", s)
    if ftype == "money":
        return s.replace(",", "").replace("$", "")
    return s


def _same(ftype, expected, actual, w2m):
    t = {"money": "money", "bool": "bool"}.get(ftype, "text")
    if t == "money":
        try:
            exp = float(expected)
        except (TypeError, ValueError):
            t = "text"
        else:
            # Drake stores whole dollars on saved screens (10918.20 is kept as 10918): accept its rounding
            act = str(actual or "").replace(",", "").replace("$", "").strip()
            if re.fullmatch(r"-?\d+", act) and abs(int(act) - exp) <= 0.5:
                return True
    return w2m._same(t, expected, actual)


# ---------------------------------------------------------------------------
# transfer
# ---------------------------------------------------------------------------
def state(sid):
    s = session.load(sid)
    return s.get("transfer") or {"running": False, "finished": False, "log": [], "results": [], "docs": []}


def start(sid, overwrite=False, dry_run=False, doc_ids=None):
    s = session.load(sid)
    summ = session.summary(s)
    if not summ["ready"] and not dry_run:
        return {"ok": False, "error": f"{len(summ['blocking'])} form(s) are not reviewed yet. Review (or exclude) every form first."}
    if not _run_lock.acquire(blocking=False):
        return {"ok": False, "error": "A transfer is already running."}
    plan = session.transfer_plan(s)
    if doc_ids:
        plan = [p for p in plan if p["doc_id"] in set(doc_ids)]
    tr = {"running": True, "finished": False, "dry_run": bool(dry_run), "overwrite": bool(overwrite), "started": time.time(),
          "log": [], "results": [], "docs": [], "progress": 0, "total": len(plan)}
    s["transfer"] = tr
    session.save(s)

    def run():
        try:
            if dry_run:
                _run(sid, plan, tr, overwrite, dry_run)
            else:
                _, _, _, w2m, _ = _drake()
                with w2m._drake_lock:          # never drive Drake together with the W-2 page or the live view input
                    _run(sid, plan, tr, overwrite, dry_run)
        except DrakeUnavailable as exc:
            tr["log"].append(f"[ERROR] {exc}")
            tr["error"] = str(exc)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            tr["log"].append(f"[ERROR] {exc}")
            tr["error"] = str(exc)
        finally:
            tr["running"] = False
            tr["finished"] = True
            tr["ended"] = time.time()
            s2 = session.load(sid)
            s2["transfer"] = tr
            session.save(s2)
            _run_lock.release()

    threading.Thread(target=run, daemon=True).start()
    return {"ok": True}


def _result(tr, doc, key, label, value, status, msg, aid=None):
    tr["results"].append({"doc_id": doc["doc_id"], "type": doc["type"], "screen": doc["screen"], "key": key, "label": label,
                          "value": value if not isinstance(value, bool) else ("Checked" if value else "Not checked"),
                          "status": status, "message": msg, "aid": aid})


def _run(sid, plan, tr, overwrite, dry_run):
    log = lambda m: (tr["log"].append(m), print(m))
    links = load_links()
    s = session.load(sid)
    tp = next((p for p in plan if p["type"] == "TAXPAYER"), None)
    tpv = {v["key"]: v["value"] for v in (tp or {}).get("values", [])}
    ssn = re.sub(r"\D", "", str(tpv.get("tp_ssn", "")))

    # group by Drake screen in plan order; record numbers count only the documents being sent
    groups = []
    for p in plan:
        g = next((x for x in groups if x["screen"] == p["screen"]), None)
        if not g:
            g = {"screen": p["screen"], "entries": []}
            groups.append(g)
        g["entries"].append(p)
    for g in groups:
        for i, p in enumerate(g["entries"], 1):
            p["drake_record"] = i

    pf = wf = nav = w2m = Desktop = None
    if not dry_run:
        pf, wf, nav, w2m, Desktop = _drake()
        log("[DRAKE] Connecting to Drake Tax…")
        if _exit_prompt_open():
            raise RuntimeError("Drake is showing 'Are you sure you want to exit Drake Tax Software?'. Click No in Drake, then start the transfer again.")
        try:
            nav.switch_to_drake(dismiss_popups=False)    # restore + bring Drake forward (it may be minimised)
        except Exception as exc:
            log(f"[WARN] Could not bring Drake to the front: {exc}")
        time.sleep(0.6)
        if len(ssn) != 9:
            raise RuntimeError("Screen 1 has no confirmed 9-digit taxpayer SSN — Drake needs it to open or create the return.")
        open_return(ssn, tpv.get("tp_first", ""), tpv.get("tp_mi", ""), tpv.get("tp_last", ""), log, pf, nav, Desktop)
        if pf.find_subscreen_window():
            pf.exit_current_subscreen(log)
    else:
        log("[DRY RUN] Nothing is typed into Drake. This shows exactly what would be entered and which fields still need linking.")

    lot_docs = []
    for g in groups:
        sc = g["screen"]
        entries = g["entries"]
        # decide per entry what can be sent
        work = []
        for p in list(entries):
            if p.get("zero_value"):
                tr["docs"].append({"doc_id": p["doc_id"], "status": "nothing", "message": "All amounts are 0.00 — nothing to enter in Drake."})
                tr["progress"] += 1
                continue
            fdefs = {f["key"]: f for f in (catalog.form_def(p["type"]) or {}).get("fields", [])}
            items, unlinked = [], []
            for v in p["values"]:
                f = fdefs.get(v["key"], v)
                if p["type"] == "TAXPAYER" and v["key"] == "tp_ssn":
                    _result(tr, p, v["key"], v["label"], v["value"], "reference",
                            "Used to open (or create) the Drake return — Drake fills the SSN itself.")
                    continue
                if f.get("ref"):
                    _result(tr, p, v["key"], v["label"], v["value"], "reference",
                            "Reference only — checked on the PDF, not an input on this Drake screen.")
                    continue
                aid, ctl, how = resolve(sc, f, links)
                (items if aid else unlinked).append({**v, "aid": aid, "control": ctl, "how": how})
            # Drake looks a payer up by TIN/EIN and refills name + address when that field is left, so the TIN must be
            # entered first — otherwise the address typed before it is wiped.
            items.sort(key=lambda it: 0 if it["type"] in ("ein", "tin", "ssn") or it["key"].endswith(("_tin", "_ein")) else 1)
            if items and all(it["key"] == "ts" for it in items):
                # only the T/S code is linked: entering it alone would create an empty Drake record
                for it in items:
                    _result(tr, p, it["key"], it["label"], it["value"], "not_linked",
                            f"Not entered — none of this form's amounts have a Drake field on screen {sc}, so no record was created.")
                items = []
            work.append((p, items, unlinked))
        for p, items, unlinked in work:
            for u in unlinked:
                _result(tr, p, u["key"], u["label"], u["value"], "not_linked",
                        f"No Drake field id for this value on screen {sc or '—'}. Use 'Link Drake fields' on this screen, or enter it in Drake.")

        if not sc:
            for p, items, unlinked in work:
                tr["docs"].append({"doc_id": p["doc_id"], "status": "manual", "message": "No Drake screen for this document — enter it manually."})
            continue

        for p, items, unlinked in work:
            if p.get("lots"):
                lot_docs.append(p)

        sendable = [(p, items) for p, items, _ in work if items]
        for p, items, unlinked in work:
            if not items:
                tr["docs"].append({"doc_id": p["doc_id"], "status": "not_linked" if unlinked else "nothing",
                                   "message": f"{len(unlinked)} confirmed value(s) have no linked Drake field on screen {sc}." if unlinked
                                   else "No confirmed values to enter."})
        # Drake record numbers count only the forms that are actually entered on this screen
        for i, (p, _) in enumerate(sendable, 1):
            p["drake_record"] = i
        if not sendable:
            continue

        if dry_run:
            for p, items in sendable:
                log(f"[{sc} record {p['drake_record']}] {p['type']} — {p['payer']}")
                for it in items:
                    _result(tr, p, it["key"], it["label"], it["value"], "would_enter", f"{it['aid']} ({it['how']})", it["aid"])
                tr["docs"].append({"doc_id": p["doc_id"], "status": "dry_run", "message": f"{len(items)} value(s) would be entered on screen {sc}, record {p['drake_record']}."})
                tr["progress"] += 1
            continue

        log(f"\n[SCREEN {sc}] {len(sendable)} record(s) to enter…")
        g["sent"] = []
        for p, items in sendable:
            n = p["drake_record"]
            try:
                win = open_record(sc, n, log, pf, Desktop, create=True)
            except Exception as exc:
                log(f"[FAIL] Screen {sc} record {n}: {exc}")
                for it in items:
                    _result(tr, p, it["key"], it["label"], it["value"], "failed", f"Screen {sc} record {n} did not open: {exc}", it["aid"])
                tr["docs"].append({"doc_id": p["doc_id"], "status": "failed", "message": f"Drake screen {sc} record {n} did not open."})
                continue
            time.sleep(0.4)
            edits, combos, checks = _controls(win)
            log(f"[{sc} record {n}] {p['type']} — {p['payer']}  ({len(edits) + len(combos) + len(checks)} inputs on screen)")
            # overwrite guard: does this record already hold an amount?
            if not overwrite:
                existing = None
                for it in items:
                    if it["type"] != "money":
                        continue
                    kind, ctrl = _kind_ctrl(it["aid"], it["control"], edits, combos, checks)
                    cur = w2m._read_back(kind, ctrl) if ctrl is not None else None
                    if cur and re.sub(r"[^\d]", "", cur).strip("0"):
                        existing = (it, cur)
                        break
                if existing:
                    msg = f"Drake record {n} already has {existing[0]['label']} = {existing[1]}. Tick 'Overwrite' to replace it."
                    log(f"[STOP] {msg}")
                    for it in items:
                        _result(tr, p, it["key"], it["label"], it["value"], "blocked", msg, it["aid"])
                    tr["docs"].append({"doc_id": p["doc_id"], "status": "blocked", "message": msg})
                    pf.exit_current_subscreen(log)
                    time.sleep(0.4)
                    continue
            g["sent"].append((p, items))
            ok_n = 0
            for it in items:
                kind, ctrl = _kind_ctrl(it["aid"], it["control"], edits, combos, checks)
                val = _drake_text(it["type"], it["value"])
                if ctrl is None:
                    _result(tr, p, it["key"], it["label"], it["value"], "failed", f"Field {it['aid']} is not on Drake screen {sc}", it["aid"])
                    log(f"[FAIL] {it['label']}: {it['aid']} not on the screen")
                    continue
                try:
                    if kind == "checkbox":
                        want = bool(it["value"])
                        if bool(ctrl.get_toggle_state()) != want:
                            ctrl.toggle()
                    else:
                        target = ctrl
                        if kind == "combo":
                            inner = ctrl.descendants(control_type="Edit")
                            target = inner[0] if inner else ctrl
                        _enter(target, val)
                    time.sleep(0.04)
                    actual = w2m._read_back(kind, ctrl)
                    if _same(it["type"], val, actual, w2m):
                        ok_n += 1
                        _result(tr, p, it["key"], it["label"], it["value"], "verified", f"Drake shows {actual}", it["aid"])
                        log(f"[OK] {it['label']:<34} = {val}")
                    else:
                        _result(tr, p, it["key"], it["label"], it["value"], "mismatch", f"Sent {val}, Drake shows {actual!r}", it["aid"])
                        log(f"[CHECK] {it['label']}: sent {val}, Drake shows {actual!r}")
                except Exception as exc:
                    _result(tr, p, it["key"], it["label"], it["value"], "failed", str(exc), it["aid"])
                    log(f"[FAIL] {it['label']}: {exc}")
                note = popup_check(log)
                if note:
                    tr["results"][-1]["message"] += f" · Drake said: {note}"
            tr["docs"].append({"doc_id": p["doc_id"], "status": "entered" if ok_n == len(items) else "partial",
                               "message": f"{ok_n} of {len(items)} value(s) entered and verified on screen {sc}, record {n}."})
            tr["progress"] += 1
            log(f"[SCREEN {sc}] Saving record {n}…")
            pf.exit_current_subscreen(log)
            time.sleep(0.4)

    # 1099-B: every confirmed sale lot goes into ONE Drake Form 8949 import file
    _write_8949_all(lot_docs, ssn, tr, log, dry_run)

    if not dry_run:
        verify_saved(groups, tr, log, pf, w2m, Desktop)

    done = sum(1 for r in tr["results"] if r["status"] in ("verified", "would_enter"))
    need = sum(1 for r in tr["results"] if r["status"] not in ("verified", "would_enter", "reference"))
    log(f"\n[DONE] {done} value(s) {'would be entered' if dry_run else 'entered and verified'}; {need} need attention (see the report).")
    if not dry_run:
        try:
            nav.switch_to_browser(preferred_title="Drake Review")
        except Exception:
            pass


def _write_8949_all(lot_docs, ssn, tr, log, dry_run):
    """One Drake 8949 import file per return (Drake names it by SSN, so separate files would overwrite each other)."""
    lot_docs = [p for p in lot_docs if p.get("lots")]
    if not lot_docs:
        return
    if len(lot_docs) == 1:
        return _write_8949(lot_docs[0], ssn, tr, log, dry_run)
    merged = {**lot_docs[0], "lots": [l for p in lot_docs for l in p["lots"]]}
    _write_8949(merged, ssn, tr, log, dry_run)
    msg = tr["docs"][-1]
    for p in lot_docs[1:]:
        tr["docs"].append({**msg, "doc_id": p["doc_id"],
                           "message": msg["message"] + f" (one file for all {len(lot_docs)} brokerage statements)"})


def _write_8949(p, ssn, tr, log, dry_run):
    lots = p.get("lots") or []
    if not lots:
        return
    if dry_run:
        tr["docs"].append({"doc_id": p["doc_id"], "status": "dry_run", "message": f"{len(lots)} sale lots would be written to a Drake 8949 import file."})
        return
    if len(ssn) != 9:
        tr["docs"].append({"doc_id": p["doc_id"], "status": "failed", "message": "No confirmed taxpayer SSN — needed to name the Drake 8949 import file."})
        return
    try:
        from drake_import_generator import Drake8949ImportGenerator, DRAKE_IMPORT_DIR
        target = DRAKE_IMPORT_DIR if os.name == "nt" else os.path.join(BASE, "exports")
        gen = Drake8949ImportGenerator(ssn_or_client_id=ssn, import_mode="Append", target_dir=target)
        bad = 0
        for l in lots:
            try:
                adj = float(l.get("adjustment") or 0)
                gen.add_transaction(description=f"{l.get('quantity', '')} {l.get('description', '')}".strip()[:60],
                                    date_acquired=l.get("date_acquired"), date_sold=l.get("date_sold"),
                                    sales_price=float(l.get("proceeds") or 0), cost_basis=float(l.get("cost") or 0),
                                    adjustment_code=(l.get("adj_code") or "") if adj else "", adjustment_amount=adj if adj else None)
            except Exception:
                bad += 1
        path = gen.write_import_file()
        msg = f"Wrote {len(gen.transactions)} sale lots to {path}" + (f" ({bad} could not be converted)" if bad else "") + \
              ". In Drake open Screen 8949 and use Import."
        log(f"[8949] {msg}")
        tr["docs"].append({"doc_id": p["doc_id"], "status": "import_file", "message": msg})
    except Exception as exc:
        tr["docs"].append({"doc_id": p["doc_id"], "status": "failed", "message": f"Could not write the 8949 import file: {exc}"})


# ---------------------------------------------------------------------------
# discovery: read the open Drake screen and suggest links
# ---------------------------------------------------------------------------
def _tokens(s):
    return set(re.findall(r"[a-z0-9]+", str(s or "").lower())) - {"the", "of", "or", "and", "a", "to", "in", "on", "for"}


def discover(screen, open_screen=True):
    pf, wf, nav, w2m, Desktop = _drake()
    logs = []
    if not w2m._drake_lock.acquire(timeout=1):
        raise RuntimeError("Drake is busy (a transfer or the W-2 page is entering values). Try again when it has finished.")
    try:
        if open_screen and screen:
            hwnd, title = wf.find_drake_window()
            if not hwnd or "data entry" not in (title or "").lower():
                raise RuntimeError("Open the client's return in Drake first (Data Entry), then link the fields.")
            win = pf.open_drake_screen(screen, logs.append)
            if not win:
                raise RuntimeError(f"Drake screen {screen} did not open.")
        else:
            h = pf.find_subscreen_window()
            if not h:
                raise RuntimeError("No Drake screen is open.")
            win = Desktop(backend="uia").window(handle=h[0])
        time.sleep(0.4)
        texts = []
        for t in win.descendants(control_type="Text"):
            try:
                s = t.window_text().strip()
                if s:
                    texts.append((s.rstrip(":"), t.rectangle()))
            except Exception:
                pass
        controls = []
        for aid, (kind, c) in w2m._collect_controls(win).items():
            try:
                if not c.is_visible():
                    continue
                r = c.rectangle()
                if r.width() <= 2 or r.height() <= 2:
                    continue
                controls.append({"aid": aid, "control": kind, "x": r.left, "y": r.top, "w": r.width(), "h": r.height(),
                                 "label": w2m._nearest_label(r, texts), "enabled": bool(c.is_enabled())})
            except Exception:
                continue
        try:
            nav.switch_to_browser(preferred_title="Drake Review")
        except Exception:
            pass
    finally:
        w2m._drake_lock.release()
    return {"controls": controls, "logs": logs}


def suggest(screen, controls):
    """Pair catalog fields of this screen with Drake controls by label words (+ box number)."""
    fields = {}
    for d in list(catalog.FORMS.values()) + list(catalog.DERIVED.values()):
        if d["screen"] == screen:
            for f in d["fields"]:
                if f["mode"] != "block":
                    fields.setdefault(f["key"], f)
    kind_ok = lambda f, c: (c["control"] == "checkbox") == (f["type"] == "bool")
    pairs = []
    for f in fields.values():
        ft = _tokens(f["label"]) | ({f["box"].lower()} if f["box"] else set())
        for c in controls:
            if not kind_ok(f, c) or not c.get("label"):
                continue
            ct = _tokens(c["label"])
            if not ct:
                continue
            score = len(ft & ct) / max(1, len(ft | ct))
            if f["box"] and re.search(rf"(?:^|\b){re.escape(f['box'])}\b", c["label"], re.I):
                score += 0.25
            if score >= 0.34:
                pairs.append((score, f["key"], c))
    pairs.sort(key=lambda x: -x[0])
    used_f, used_c, out = set(), set(), []
    for score, k, c in pairs:
        if k in used_f or c["aid"] in used_c:
            continue
        used_f.add(k)
        used_c.add(c["aid"])
        out.append({"key": k, "label": fields[k]["label"], "aid": c["aid"], "control": c["control"], "drake_label": c["label"],
                    "score": round(score, 2)})
    return out
