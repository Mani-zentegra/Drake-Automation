"""
W-2 PDF -> Drake Tax 2025 visual field mapping.

Serves the /w2-mapping page and its API:
  * finds the W-2 inside a tax-packet PDF and exposes each W-2 box as a mappable "PDF field"
  * describes the Drake W-2 screen fields (by UI Automation id) and can take a live
    snapshot of the real Drake W-2 screen with the on-screen position of every input
  * stores the user's confirmed mapping (Drake field <- PDF field / fixed value)
  * on Proceed, re-extracts the values from the PDF, applies the mapping and types each
    value into its Drake control, then reads the control back to confirm it took.

Windows-only modules (pywinauto, win32gui, ...) are imported lazily so the page and the
extraction/mapping endpoints also run on machines without Drake.
"""
import base64
import io
import json
import os
import re
import threading
import time

from flask import Blueprint, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from packet_extractor import extract_all_modules_from_packet

w2_bp = Blueprint("w2_mapping", __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
MAPPING_FILE = os.path.join(BASE_DIR, "w2_mappings.json")

DEFAULT_PDF_CANDIDATES = [
    os.path.join(BASE_DIR, "..", "..", "Weaver-Cummings_2025_Tax_Packet.pdf"),     # ...\Documents\Drake Automation\
    r"C:\Users\Zen\Downloads\Weaver-Cummings_2025_Tax_Packet.pdf",
    os.path.join(os.path.expanduser("~"), "Downloads", "Weaver-Cummings_2025_Tax_Packet.pdf"),
    os.path.join(BASE_DIR, "..", "Weaver-Cummings_2025_Tax_Packet.pdf"),
    os.path.join(UPLOAD_DIR, "Weaver-Cummings_2025_Tax_Packet.pdf"),
]

_state = {"pdf_path": None}
_drake_lock = threading.Lock()   # only one Drake automation at a time

# ---------------------------------------------------------------------------
# Drake W-2 screen fields (automation ids discovered on Drake 2025 Screen W2)
# ---------------------------------------------------------------------------
CLIENT_SSN = "__client_ssn"
CLIENT_NAME = "__client_name"

DRAKE_W2_FIELDS = [
    # Virtual targets: used to open / create the client's return before Screen W2
    {"id": CLIENT_SSN, "label": "Employee SSN (Drake taxpayer SSN)", "section": "Return / Client", "type": "ssn", "required": True, "control": "virtual",
     "hint": "Drake links a W-2 to the return opened by this SSN (Screen 1)."},
    {"id": CLIENT_NAME, "label": "Employee name (Drake taxpayer)", "section": "Return / Client", "type": "name", "required": False, "control": "virtual",
     "hint": "Used only when Drake has to create a new return for this SSN."},
    # Screen W2
    {"id": "Dropdown_1", "label": "TS (T = taxpayer, S = spouse)", "section": "Ownership", "type": "code", "required": True, "control": "combo"},
    {"id": "Textbox_4", "label": "Employer EIN", "box": "b", "section": "Employer", "type": "ein", "required": True, "control": "edit"},
    {"id": "Textbox_5", "label": "Employer name", "box": "c", "section": "Employer", "type": "text", "required": True, "control": "edit"},
    {"id": "Textbox_7", "label": "Employer street", "box": "c", "section": "Employer", "type": "text", "required": False, "control": "edit"},
    {"id": "Textbox_8", "label": "Employer city", "box": "c", "section": "Employer", "type": "text", "required": False, "control": "edit"},
    {"id": "Dropdown_9", "label": "Employer state", "box": "c", "section": "Employer", "type": "state", "required": False, "control": "combo"},
    {"id": "Textbox_10", "label": "Employer ZIP", "box": "c", "section": "Employer", "type": "zip", "required": False, "control": "edit"},
    {"id": "Textbox_23", "label": "Wages, tips, other comp.", "box": "1", "section": "Federal boxes", "type": "money", "required": True, "control": "edit"},
    {"id": "Textbox_24", "label": "Federal income tax withheld", "box": "2", "section": "Federal boxes", "type": "money", "required": True, "control": "edit"},
    {"id": "Textbox_25", "label": "Social security wages", "box": "3", "section": "Federal boxes", "type": "money", "required": False, "control": "edit"},
    {"id": "Textbox_26", "label": "Social security tax withheld", "box": "4", "section": "Federal boxes", "type": "money", "required": False, "control": "edit"},
    {"id": "Textbox_27", "label": "Medicare wages and tips", "box": "5", "section": "Federal boxes", "type": "money", "required": False, "control": "edit"},
    {"id": "Textbox_28", "label": "Medicare tax withheld", "box": "6", "section": "Federal boxes", "type": "money", "required": False, "control": "edit"},
    {"id": "Dropdown_34", "label": "Box 12a code", "box": "12a", "section": "Box 12 / 13", "type": "code", "required": False, "control": "combo"},
    {"id": "Textbox_35", "label": "Box 12a amount", "box": "12a", "section": "Box 12 / 13", "type": "money", "required": False, "control": "edit"},
    {"id": "Dropdown_37", "label": "Box 12b code", "box": "12b", "section": "Box 12 / 13", "type": "code", "required": False, "control": "combo"},
    {"id": "Textbox_38", "label": "Box 12b amount", "box": "12b", "section": "Box 12 / 13", "type": "money", "required": False, "control": "edit"},
    {"id": "CheckboxTextRight_47", "label": "Retirement plan", "box": "13", "section": "Box 12 / 13", "type": "bool", "required": False, "control": "checkbox"},
    {"id": "Dropdown_57", "label": "State", "box": "15", "section": "State", "type": "state", "required": False, "control": "combo"},
    {"id": "Textbox_59", "label": "State wages", "box": "16", "section": "State", "type": "money", "required": False, "control": "edit"},
    {"id": "Textbox_60", "label": "State income tax", "box": "17", "section": "State", "type": "money", "required": False, "control": "edit"},
]
DRAKE_FIELDS_BY_ID = {f["id"]: f for f in DRAKE_W2_FIELDS}

# Default mapping: Drake field id -> source ({"pdf": key} or {"const": value})
DEFAULT_MAPPING = {
    CLIENT_SSN: {"pdf": "employee_ssn"},
    CLIENT_NAME: {"pdf": "employee_name"},
    "Dropdown_1": {"const": "T"},
    "Textbox_4": {"pdf": "employer_ein"},
    "Textbox_5": {"pdf": "employer_name"},
    "Textbox_7": {"pdf": "employer_street"},
    "Textbox_8": {"pdf": "employer_city"},
    "Dropdown_9": {"pdf": "employer_state"},
    "Textbox_10": {"pdf": "employer_zip"},
    "Textbox_23": {"pdf": "box1_wages"},
    "Textbox_24": {"pdf": "box2_fed_withheld"},
    "Textbox_25": {"pdf": "box3_ss_wages"},
    "Textbox_26": {"pdf": "box4_ss_tax"},
    "Textbox_27": {"pdf": "box5_medicare_wages"},
    "Textbox_28": {"pdf": "box6_medicare_tax"},
    "Dropdown_34": {"pdf": "box12a_code"},
    "Textbox_35": {"pdf": "box12a_amount"},
    "Dropdown_37": {"pdf": "box12b_code"},
    "Textbox_38": {"pdf": "box12b_amount"},
    "CheckboxTextRight_47": {"pdf": "box13_retirement_plan"},
}

# ---------------------------------------------------------------------------
# PDF side
# ---------------------------------------------------------------------------
def _resolve_default_pdf():
    for p in DEFAULT_PDF_CANDIDATES:
        p = os.path.abspath(p)
        if os.path.isfile(p):
            return p
    return None


def current_pdf_path():
    p = _state.get("pdf_path")
    if p and os.path.isfile(p):
        return p
    p = _resolve_default_pdf()
    _state["pdf_path"] = p
    return p


def _money_display(v):
    try:
        return f"{float(str(v).replace(',', '')):,.2f}"
    except (TypeError, ValueError):
        return str(v or "")


_ADDR_RE = re.compile(r"^(?P<street>.+?),\s*(?P<city>[^,]+),\s*(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)$")


def _split_address(addr):
    m = _ADDR_RE.match((addr or "").strip())
    if not m:
        return {"street": addr or "", "city": "", "state": "", "zip": ""}
    return m.groupdict()


def _split_name(full):
    parts = (full or "").split()
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    first, last = parts[0], parts[-1]
    mi = parts[1][0] if len(parts) > 2 else ""
    return first, mi, last


def build_pdf_fields(w2):
    """Turn one extracted W-2 module into the list of mappable PDF fields.
    `find` is the text exactly as printed on the PDF, used by the viewer to draw the box."""
    page = w2.get("page", 1)
    er = _split_address(w2.get("employer_address"))
    ee = _split_address(w2.get("employee_address"))
    city_line_er = f"{er['city']}, {er['state']} {er['zip']}" if er["city"] else ""
    city_line_ee = f"{ee['city']}, {ee['state']} {ee['zip']}" if ee["city"] else ""

    def f(key, label, box, value, ftype="text", find=None, part=None):
        value = "" if value is None else value
        disp = _money_display(value) if ftype == "money" and value != "" else (value if not isinstance(value, bool) else ("Checked" if value else "Not checked"))
        return {"key": key, "label": label, "box": box, "type": ftype, "value": value,
                "display": disp, "find": find if find is not None else (disp if isinstance(disp, str) else ""),
                "part": part if part is not None else (disp if find is not None and isinstance(disp, str) else ""), "page": page}

    fields = [
        f("employee_ssn", "Employee's SSN", "a", w2.get("employee_ssn"), "ssn"),
        f("employer_ein", "Employer EIN", "b", w2.get("ein"), "ein"),
        f("employer_name", "Employer name", "c", w2.get("employer_name")),
        f("employer_street", "Employer street", "c", er["street"]),
        f("employer_city", "Employer city", "c", er["city"], find=city_line_er),
        f("employer_state", "Employer state", "c", er["state"], "state", find=city_line_er),
        f("employer_zip", "Employer ZIP", "c", er["zip"], "zip", find=city_line_er),
        f("control_number", "Control number", "d", w2.get("control_number")),
        f("employee_name", "Employee name", "e", w2.get("employee_name"), "name"),
        f("employee_street", "Employee street", "f", ee["street"]),
        f("employee_city", "Employee city", "f", ee["city"], find=city_line_ee),
        f("employee_state", "Employee state", "f", ee["state"], "state", find=city_line_ee),
        f("employee_zip", "Employee ZIP", "f", ee["zip"], "zip", find=city_line_ee),
        f("box1_wages", "Wages, tips, other compensation", "1", w2.get("box1_wages"), "money"),
        f("box2_fed_withheld", "Federal income tax withheld", "2", w2.get("box2_fed_withheld"), "money"),
        f("box3_ss_wages", "Social security wages", "3", w2.get("box3_ss_wages"), "money"),
        f("box4_ss_tax", "Social security tax withheld", "4", w2.get("box4_ss_tax"), "money"),
        f("box5_medicare_wages", "Medicare wages and tips", "5", w2.get("box5_medicare_wages"), "money"),
        f("box6_medicare_tax", "Medicare tax withheld", "6", w2.get("box6_medicare_tax"), "money"),
    ]
    for slot in ("a", "b"):
        code, amt = w2.get(f"box12{slot}_code"), w2.get(f"box12{slot}_amount")
        line = f"{code} {_money_display(amt)}" if code and amt else None
        fields.append(f(f"box12{slot}_code", f"Box 12{slot} code", f"12{slot}", code, "code", find=line))
        fields.append(f(f"box12{slot}_amount", f"Box 12{slot} amount", f"12{slot}", amt, "money", find=line))
    fields.append(f("box13_retirement_plan", "Retirement plan (checked)", "13",
                    bool(w2.get("box13_retirement_plan")), "bool", find="Retirement plan", part=""))
    # Empty values are still listed so the user sees what the PDF did NOT contain.
    return fields


_extract_cache = {}


def extract_w2s(pdf_path):
    """Find every W-2 in the packet. Cached per file version (path + size + mtime), so an edited
    or replaced PDF is always re-read, while repeated reviews of the same file stay fast."""
    st = os.stat(pdf_path)
    cache_key = (os.path.abspath(pdf_path), st.st_size, st.st_mtime_ns)
    if cache_key in _extract_cache:
        return _extract_cache[cache_key]
    res = extract_all_modules_from_packet(pdf_path)
    w2s = [m for m in res.get("modules", []) if str(m.get("type", "")).upper().replace(" ", "") == "W-2"]
    out = []
    for m in w2s:
        out.append({
            "id": m.get("id"),
            "page": m.get("page"),
            "title": m.get("title") or f"W-2 (page {m.get('page')})",
            "employer": m.get("employer_name", ""),
            "employee": m.get("employee_name", ""),
            "fields": build_pdf_fields(m),
        })
    result = {"total_pages": res.get("total_pages", 0), "w2s": out}
    _extract_cache.clear()
    _extract_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Value transforms (PDF value -> what Drake expects)
# ---------------------------------------------------------------------------
def transform_value(drake_type, value):
    if isinstance(value, bool):
        return value if drake_type == "bool" else ("X" if value else "")
    v = "" if value is None else str(value).strip()
    if drake_type == "bool":
        return v.lower() in ("1", "true", "yes", "x", "checked", "on")
    if drake_type == "money":
        neg = v.startswith("(") and v.endswith(")") or v.startswith("-")
        digits = re.sub(r"[^\d.]", "", v)
        if not digits:
            return ""
        return ("-" if neg else "") + f"{float(digits):.2f}"
    if drake_type in ("ein", "ssn"):
        return re.sub(r"\D", "", v)
    if drake_type == "zip":
        return re.sub(r"[^\d-]", "", v)
    if drake_type in ("state", "code"):
        return v.upper()
    return v


def resolve_values(fields, mapping):
    """mapping: drake_id -> {"pdf": key} | {"const": v}. Returns rows for the summary/populate."""
    by_key = {f["key"]: f for f in fields}
    rows = []
    for d in DRAKE_W2_FIELDS:
        src = mapping.get(d["id"])
        row = {"drake_id": d["id"], "drake_label": d["label"], "section": d["section"], "box": d.get("box", ""),
               "type": d["type"], "required": d["required"], "control": d["control"], "source": src,
               "source_label": "", "raw": "", "value": "", "status": "unmapped"}
        if src and "pdf" in src:
            pf = by_key.get(src["pdf"])
            if pf:
                row["source_label"] = f"PDF box {pf['box']} – {pf['label']}"
                row["raw"] = pf["value"]
                row["value"] = transform_value(d["type"], pf["value"])
        elif src and "const" in src:
            row["source_label"] = "Fixed value"
            row["raw"] = src["const"]
            row["value"] = transform_value(d["type"], src["const"])
        if src:
            empty = row["value"] in ("", None) and row["value"] is not False
            row["status"] = "empty" if empty else "ready"
        elif d["required"]:
            row["status"] = "missing"
        rows.append(row)
    # Extra live Drake controls the user mapped (ids not in the built-in schema)
    for did, src in mapping.items():
        if did in DRAKE_FIELDS_BY_ID or not src:
            continue
        pf = by_key.get(src.get("pdf")) if "pdf" in src else None
        raw = pf["value"] if pf else src.get("const", "")
        ftype = (pf or {}).get("type", "text")
        rows.append({"drake_id": did, "drake_label": src.get("label") or did, "section": "Other Drake fields", "box": "",
                     "type": ftype, "required": False, "control": src.get("control", "edit"), "source": src,
                     "source_label": (f"PDF box {pf['box']} – {pf['label']}" if pf else "Fixed value"),
                     "raw": raw, "value": transform_value(ftype, raw), "status": "ready" if raw not in ("", None) else "empty"})
    return rows


# ---------------------------------------------------------------------------
# Mapping persistence
# ---------------------------------------------------------------------------
def load_mapping():
    try:
        with open(MAPPING_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict) and data:
                return data
    except (OSError, ValueError):
        pass
    return dict(DEFAULT_MAPPING)


def save_mapping(mapping):
    clean = {}
    for did, src in (mapping or {}).items():
        if not isinstance(src, dict):
            continue
        if "pdf" in src and isinstance(src["pdf"], str):
            entry = {"pdf": src["pdf"]}
        elif "const" in src:
            entry = {"const": str(src["const"])}
        else:
            continue
        if did not in DRAKE_FIELDS_BY_ID:          # live-discovered control: keep its label/type
            entry["label"] = str(src.get("label", did))[:80]
            entry["control"] = src.get("control", "edit")
        clean[str(did)] = entry
    with open(MAPPING_FILE, "w", encoding="utf-8") as fh:
        json.dump(clean, fh, indent=2)
    return clean


# ---------------------------------------------------------------------------
# Drake side (Windows only)
# ---------------------------------------------------------------------------
class DrakeUnavailable(Exception):
    pass


def _drake_modules():
    try:
        import drake_w2_filler as filler  # noqa: WPS433 (Windows-only imports inside)
        import app_navigator
        from pywinauto import Desktop
        return filler, app_navigator, Desktop
    except Exception as exc:  # ImportError on non-Windows, or pywin32 problems
        raise DrakeUnavailable(f"Drake automation is only available on the Windows machine running Drake ({exc}).")


def _exit_to_menu(window, filler, Desktop, log):
    """Leave the current sub-screen for the Data Entry Menu without typing into any field."""
    import pyautogui
    for _ in range(3):
        for b in window.descendants(control_type="Button"):
            try:
                if b.element_info.automation_id == "btnExit" or "screen menu" in b.window_text().lower():
                    b.invoke()
                    break
            except Exception:
                continue
        else:
            pyautogui.press("esc")
        time.sleep(0.5)
        filler.dismiss_drake_popups()
        h, _ = filler.find_drake_window()
        if h:
            window = Desktop(backend="uia").window(handle=h)
            if filler.get_current_drake_state(window) == "MENU_SCREEN":
                log("[NAVIGATE] Back on the Data Entry Menu.")
                return window
    return None


def goto_w2_screen(client, log):
    """Bring Drake forward and make sure Screen W2 is open. Returns (hwnd, uia_window)."""
    filler, nav, Desktop = _drake_modules()
    nav.switch_to_drake(dismiss_popups=True)
    filler.dismiss_drake_popups()
    hwnd, title = filler.find_drake_window()
    if not hwnd:
        raise RuntimeError("Drake 2025 is not open. Please start Drake first.")
    log(f"[DRAKE] Connected to '{title}'")
    window = Desktop(backend="uia").window(handle=hwnd)

    if "data entry" not in title.lower():
        ssn = re.sub(r"\D", "", str((client or {}).get("ssn", "")))
        if len(ssn) != 9:
            raise RuntimeError("No return is open in Drake and no valid employee SSN is mapped, "
                               "so the tool cannot pick the client. Map 'Employee SSN' or open the return in Drake.")
        first, mi, last = _split_name((client or {}).get("name", ""))
        if not (first and last):
            raise RuntimeError("Employee name is needed to open/create the return. Map 'Employee name'.")
        log(f"[DRAKE] Opening return for SSN ***-**-{ssn[-4:]} ...")
        if not filler.open_or_create_client(ssn, first, last, mi):
            raise RuntimeError("Could not open or create the client return in Drake.")
        time.sleep(1.0)
        hwnd, title = filler.find_drake_window()
        window = Desktop(backend="uia").window(handle=hwnd)
    else:
        ssn = re.sub(r"\D", "", str((client or {}).get("ssn", "")))
        if ssn and ssn not in re.sub(r"\D", "", title):
            log("[WARN] A return is already open in Drake; confirm it belongs to this employee before saving.")

    state = filler.get_current_drake_state(window)
    if state == "W2_SCREEN":
        return hwnd, window
    if state != "MENU_SCREEN":
        log(f"[NAVIGATE] On {state}; returning to the Data Entry Menu...")
        window = _exit_to_menu(window, filler, Desktop, log)
        if window is None:
            raise RuntimeError("Could not return to the Data Entry Menu in Drake.")

    log("[NAVIGATE] Opening Screen W2 (W2|Wages)...")
    clicked = False
    for b in window.descendants(control_type="Button"):
        if "w2|wages" in b.window_text().strip().lower():
            try:
                b.invoke()
                clicked = True
                break
            except Exception:
                pass
    if not clicked:
        raise RuntimeError("Could not find the 'W2|Wages' button on the Data Entry Menu.")
    for _ in range(30):
        time.sleep(0.15)
        h, _ = filler.find_drake_window()
        if h:
            w = Desktop(backend="uia").window(handle=h)
            if filler.get_current_drake_state(w) == "W2_SCREEN":
                log("[NAVIGATE] Screen W2 is open.")
                return h, w
    raise RuntimeError("Screen W2 did not open in Drake.")


def _collect_controls(w2_win):
    """aid -> (kind, wrapper). For combos the inner Edit is stored as well."""
    controls = {}
    for kind, ctype in (("edit", "Edit"), ("combo", "ComboBox"), ("checkbox", "CheckBox")):
        for c in w2_win.descendants(control_type=ctype):
            try:
                aid = c.element_info.automation_id
            except Exception:
                continue
            if not aid or aid == "PART_EditableTextBox" or aid in controls:
                continue
            controls[aid] = (kind, c)
    return controls


def _nearest_label(rect, texts):
    cy = (rect.top + rect.bottom) / 2
    best, best_d = "", 10 ** 9
    for t, r in texts:
        ty = (r.top + r.bottom) / 2
        if abs(ty - cy) <= 12 and r.right <= rect.left + 6:      # same row, to the left
            d = rect.left - r.right
        elif 0 <= rect.top - r.bottom <= 26 and r.left < rect.right and r.right > rect.left:  # just above
            d = 400 + (rect.top - r.bottom)
        else:
            continue
        if d < best_d:
            best, best_d = t, d
    return best


def capture_drake_snapshot(open_screen=False, client=None):
    """Screenshot of the real Drake window + the position/label of each input control on Screen W2."""
    logs = []
    filler, nav, Desktop = _drake_modules()
    with _drake_lock:
        if open_screen:
            hwnd, win = goto_w2_screen(client, logs.append)
        else:
            hwnd, _ = filler.find_drake_window()
            if not hwnd:
                raise RuntimeError("Drake 2025 is not open.")
            win = Desktop(backend="uia").window(handle=hwnd)
            if filler.get_current_drake_state(win) != "W2_SCREEN":
                return {"w2_open": False, "logs": logs}
            nav.force_activate_window(hwnd)
        time.sleep(0.5)

        import win32gui
        from PIL import ImageGrab
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        img = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        texts = []
        for t in win.descendants(control_type="Text"):
            try:
                s = t.window_text().strip()
                if s:
                    texts.append((s.rstrip(":"), t.rectangle()))
            except Exception:
                pass
        controls = []
        for aid, (kind, c) in _collect_controls(win).items():
            try:
                r = c.rectangle()
                if r.width() <= 2 or r.height() <= 2 or r.right < left or r.left > right:
                    continue
                known = DRAKE_FIELDS_BY_ID.get(aid)
                controls.append({
                    "id": aid, "control": kind,
                    "x": r.left - left, "y": r.top - top, "w": r.width(), "h": r.height(),
                    "live_label": _nearest_label(r, texts),
                    "label": known["label"] if known else "",
                    "known": bool(known),
                })
            except Exception:
                continue
        try:
            nav.switch_to_browser(preferred_title="W-2 to Drake Mapping")
        except Exception:
            pass
    return {"w2_open": True, "image": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
            "width": img.width, "height": img.height, "controls": controls, "logs": logs}


def _read_back(kind, ctrl):
    try:
        if kind == "checkbox":
            return bool(ctrl.get_toggle_state())
        target = ctrl
        if kind == "combo":
            inner = ctrl.descendants(control_type="Edit")
            target = inner[0] if inner else ctrl
        try:
            return str(target.iface_value.CurrentValue)
        except Exception:
            return str(target.window_text())
    except Exception:
        return None


def _same(dtype, expected, actual):
    if actual is None:
        return False
    if dtype == "bool":
        return bool(expected) == bool(actual)
    if dtype == "money":
        try:
            a = float(re.sub(r"[^\d.\-]", "", str(actual)) or 0)
            return abs(a - float(expected)) < 0.005
        except ValueError:
            return False
    norm = lambda s: re.sub(r"[^A-Za-z0-9]", "", str(s)).upper()
    return norm(expected) == norm(actual)


def populate_drake(rows, overwrite=False):
    """Type every mapped value into its Drake control and read each one back."""
    logs, results = [], []
    log = lambda m: (print(m), logs.append(m))
    filler, nav, Desktop = _drake_modules()
    client = {"ssn": "", "name": ""}
    for r in rows:
        if r["drake_id"] == CLIENT_SSN:
            client["ssn"] = r["value"]
        elif r["drake_id"] == CLIENT_NAME:
            client["name"] = r["value"]

    with _drake_lock:
        try:
            hwnd, w2_win = goto_w2_screen(client, log)
        except Exception as exc:
            log(f"[ERROR] {exc}")
            return False, logs, results

        controls = _collect_controls(w2_win)
        log(f"[DISCOVERY] {len(controls)} input controls found on Screen W2.")

        # Safety: don't silently overwrite a W-2 that already has wages entered
        box1 = controls.get("Textbox_23")
        if box1 and not overwrite:
            existing = _read_back(box1[0], box1[1])
            if existing and re.sub(r"[^\d]", "", existing).strip("0"):
                log(f"[STOP] This W-2 screen already has Box 1 = {existing}. Open a blank W-2 (PgDn) or tick 'Overwrite' and retry.")
                try:
                    nav.switch_to_browser(preferred_title="W-2 to Drake Mapping")
                except Exception:
                    pass
                return False, logs, [{"drake_id": "Textbox_23", "status": "blocked", "message": f"Existing value {existing}"}]

        ok_all = True
        for r in rows:
            did = r["drake_id"]
            if did in (CLIENT_SSN, CLIENT_NAME):
                results.append({"drake_id": did, "status": "used", "message": "Used to open the client's return"})
                continue
            if not r.get("source"):
                continue
            value = r["value"]
            if value in ("", None):
                results.append({"drake_id": did, "status": "skipped", "message": "PDF has no value"})
                continue
            entry = controls.get(did)
            if not entry:
                ok_all = False
                results.append({"drake_id": did, "status": "failed", "message": "Control not found on Screen W2"})
                log(f"[FAIL] {r['drake_label']}: control {did} not found")
                continue
            kind, ctrl = entry
            try:
                if kind == "checkbox":
                    want = bool(value)
                    if bool(ctrl.get_toggle_state()) != want:
                        ctrl.toggle()
                else:
                    target = ctrl
                    if kind == "combo":
                        inner = ctrl.descendants(control_type="Edit")
                        target = inner[0] if inner else ctrl
                    if not filler.enter_clean_value(target, value):
                        raise RuntimeError("value was not accepted")
                time.sleep(0.05)
                actual = _read_back(kind, ctrl)
                if _same(r["type"], value, actual):
                    results.append({"drake_id": did, "status": "verified", "message": f"Drake shows {actual}"})
                    log(f"[OK] {r['drake_label']:<30} = {value}")
                else:
                    ok_all = False
                    results.append({"drake_id": did, "status": "mismatch", "message": f"Sent {value}, Drake shows {actual!r}"})
                    log(f"[CHECK] {r['drake_label']}: sent {value}, Drake shows {actual!r}")
            except Exception as exc:
                ok_all = False
                results.append({"drake_id": did, "status": "failed", "message": str(exc)})
                log(f"[FAIL] {r['drake_label']}: {exc}")

        log("[DONE] Screen W2 left open in Drake for your review. Save it in Drake when it looks right.")
        try:
            nav.switch_to_browser(preferred_title="W-2 to Drake Mapping")
        except Exception:
            pass
    return ok_all, logs, results


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@w2_bp.route("/w2-mapping")
def w2_mapping_page():
    return render_template("w2_mapping.html")


@w2_bp.route("/api/w2-mapping/source")
def api_source():
    path = current_pdf_path()
    if not path:
        return jsonify({"success": False, "error": "Tax packet PDF not found. Upload one to continue.",
                        "looked_in": DEFAULT_PDF_CANDIDATES}), 404
    try:
        data = extract_w2s(path)
    except Exception as exc:
        return jsonify({"success": False, "error": f"Could not read the PDF: {exc}"}), 500
    if not data["w2s"]:
        return jsonify({"success": False, "error": "No Form W-2 was found in this PDF.", "file": os.path.basename(path)}), 422
    return jsonify({"success": True, "file": os.path.basename(path), "path": path,
                    "total_pages": data["total_pages"], "w2s": data["w2s"]})


@w2_bp.route("/api/w2-mapping/pdf")
def api_pdf():
    path = current_pdf_path()
    if not path:
        return "PDF not found", 404
    return send_file(path, mimetype="application/pdf", as_attachment=False)


@w2_bp.route("/api/w2-mapping/upload", methods=["POST"])
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    name = secure_filename(f.filename)
    if not name.lower().endswith(".pdf"):
        return jsonify({"success": False, "error": "Please upload a PDF file"}), 400
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    dest = os.path.join(UPLOAD_DIR, name)
    f.save(dest)
    _state["pdf_path"] = dest
    return jsonify({"success": True, "file": name})


@w2_bp.route("/api/w2-mapping/drake-fields")
def api_drake_fields():
    return jsonify({"success": True, "fields": DRAKE_W2_FIELDS})


@w2_bp.route("/api/w2-mapping/drake-snapshot", methods=["POST"])
def api_drake_snapshot():
    payload = request.get_json(silent=True) or {}
    try:
        snap = capture_drake_snapshot(open_screen=bool(payload.get("open_screen")), client=payload.get("client"))
        return jsonify({"success": True, **snap})
    except DrakeUnavailable as exc:
        return jsonify({"success": False, "unavailable": True, "error": str(exc)})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)})


@w2_bp.route("/api/w2-mapping/mappings", methods=["GET", "POST"])
def api_mappings():
    if request.method == "GET":
        if request.args.get("defaults"):
            return jsonify({"success": True, "mapping": DEFAULT_MAPPING})
        return jsonify({"success": True, "mapping": load_mapping()})
    payload = request.get_json(silent=True) or {}
    return jsonify({"success": True, "mapping": save_mapping(payload.get("mapping"))})


def _fields_for(w2_id):
    path = current_pdf_path()
    if not path:
        raise RuntimeError("Tax packet PDF not found.")
    data = extract_w2s(path)            # always re-read the PDF so Drake gets what the PDF says
    for w in data["w2s"]:
        if w["id"] == w2_id:
            return w["fields"]
    raise RuntimeError(f"W-2 '{w2_id}' is no longer in the PDF.")


@w2_bp.route("/api/w2-mapping/preview", methods=["POST"])
def api_preview():
    payload = request.get_json(silent=True) or {}
    try:
        rows = resolve_values(_fields_for(payload.get("w2_id")), payload.get("mapping") or {})
        return jsonify({"success": True, "rows": rows})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@w2_bp.route("/api/w2-mapping/proceed", methods=["POST"])
def api_proceed():
    payload = request.get_json(silent=True) or {}
    mapping = payload.get("mapping") or {}
    try:
        rows = resolve_values(_fields_for(payload.get("w2_id")), mapping)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    missing = [r["drake_label"] for r in rows if r["status"] == "missing"]
    if missing:
        return jsonify({"success": False, "error": "Required Drake fields are not mapped: " + ", ".join(missing), "rows": rows}), 400
    save_mapping(mapping)
    try:
        ok, logs, results = populate_drake(rows, overwrite=bool(payload.get("overwrite")))
    except DrakeUnavailable as exc:
        return jsonify({"success": False, "error": str(exc), "rows": rows}), 503
    return jsonify({"success": ok, "rows": rows, "results": results, "logs": logs,
                    "message": "All mapped values were entered and verified in Drake." if ok
                    else "Finished with some fields needing attention — see the results."})


# ---------------------------------------------------------------------------
# Drake-style W-2 form: validate the reviewed values and send them to Drake
# ---------------------------------------------------------------------------
US_STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
                "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY AS GU MP PR VI".split())
BOX12_CODES = set("A B C D E F G H J K L M N P Q R S T V W Y Z AA BB DD EE FF GG HH II".split())


def validate_value(ftype, value, required=False):
    """Return an error message for a value that Drake would reject, else ''."""
    if isinstance(value, bool):
        return ""
    v = "" if value is None else str(value).strip()
    if not v:
        return "Required" if required else ""
    if ftype == "money":
        return "" if re.fullmatch(r"-?\d+(\.\d{1,2})?", v) else "Enter an amount like 1234.56"
    if ftype in ("ssn", "ein"):
        return "" if re.fullmatch(r"\d{9}", v) else f"{ftype.upper()} must be 9 digits"
    if ftype == "zip":
        return "" if re.fullmatch(r"\d{5}(-?\d{4})?", v) else "ZIP must be 5 or 9 digits"
    if ftype == "state":
        return "" if v in US_STATES else "Use a 2-letter state code"
    if ftype == "code":
        return "" if v in BOX12_CODES or v in ("T", "S") else "Not a valid code"
    return ""


@w2_bp.route("/api/w2-mapping/send", methods=["POST"])
def api_send():
    """Body: {"values": {drake_id: value}, "overwrite": bool}. Values come from the reviewed form."""
    payload = request.get_json(silent=True) or {}
    values = payload.get("values") or {}
    rows, errors = [], []
    for d in DRAKE_W2_FIELDS:
        if d["id"] not in values:
            continue
        val = transform_value(d["type"], values[d["id"]])
        err = validate_value(d["type"], val, d["required"])
        if err:
            errors.append(f"{d['label']}: {err}")
        rows.append({"drake_id": d["id"], "drake_label": d["label"], "section": d["section"], "box": d.get("box", ""),
                     "type": d["type"], "required": d["required"], "control": d["control"],
                     "source": {"form": True}, "value": val, "status": "ready" if val not in ("", None) else "empty"})
    # Fields linked to Drake with "Link Drake fields" (ids discovered on the real Screen W2)
    extra = payload.get("extra") or {}
    for aid, spec in (extra.items() if isinstance(extra, dict) else []):
        if aid in DRAKE_FIELDS_BY_ID or not isinstance(spec, dict) or not re.fullmatch(r"[A-Za-z]+_\d+", str(aid)):
            continue
        ftype = FORM_TYPE_TO_DRAKE.get(spec.get("type"), "text")
        control = spec.get("control") if spec.get("control") in ("edit", "combo", "checkbox") else "edit"
        val = transform_value(ftype, spec.get("value"))
        err = validate_value(ftype, val)
        label = str(spec.get("label") or aid)[:80]
        if err:
            errors.append(f"{label}: {err}")
        rows.append({"drake_id": aid, "drake_label": label, "section": "Linked field", "box": "", "type": ftype,
                     "required": False, "control": control, "source": {"form": True}, "value": val,
                     "status": "ready" if val not in ("", None) else "empty"})
    for d in DRAKE_W2_FIELDS:
        if d["required"] and d["id"] not in values:
            errors.append(f"{d['label']}: Required")
    if errors:
        return jsonify({"success": False, "error": "Fix these fields first: " + "; ".join(errors), "errors": errors}), 400
    try:
        ok, logs, results = populate_drake(rows, overwrite=bool(payload.get("overwrite")))
    except DrakeUnavailable as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    return jsonify({"success": ok, "results": results, "logs": logs,
                    "message": "All values were entered in Drake and confirmed." if ok
                    else "Finished — some fields need attention (see the marks on the form)."})


# ---------------------------------------------------------------------------
# Link the remaining Screen W2 fields: read every control Drake shows, so the page can match
# them to its fields by position and remember their automation ids.
# ---------------------------------------------------------------------------
FIELD_IDS_FILE = os.path.join(BASE_DIR, "drake_field_ids.json")
FORM_TYPE_TO_DRAKE = {"money": "money", "ssn": "ssn", "ein": "ein", "zip": "zip", "state": "state", "code12": "code",
                      "ts": "code", "bool": "bool", "text": "text", "name": "text", "year": "text", "opt": "text"}


@w2_bp.route("/api/w2-mapping/field-ids", methods=["GET", "POST"])
def api_field_ids():
    if request.method == "GET":
        try:
            with open(FIELD_IDS_FILE, "r", encoding="utf-8") as fh:
                return jsonify({"success": True, "ids": json.load(fh)})
        except (OSError, ValueError):
            return jsonify({"success": True, "ids": {}})
    payload = request.get_json(silent=True) or {}
    clean = {}
    for key, spec in (payload.get("ids") or {}).items():
        if not isinstance(spec, dict):
            continue
        aid = str(spec.get("aid", ""))
        if not re.fullmatch(r"[A-Za-z]+_\d+", aid):
            continue
        clean[str(key)[:40]] = {"aid": aid,
                                "control": spec.get("control") if spec.get("control") in ("edit", "combo", "checkbox") else "edit",
                                "label": str(spec.get("label", ""))[:80]}
    with open(FIELD_IDS_FILE, "w", encoding="utf-8") as fh:
        json.dump(clean, fh, indent=2)
    return jsonify({"success": True, "ids": clean})


@w2_bp.route("/api/w2-mapping/discover-ids", methods=["POST"])
def api_discover_ids():
    """List every input on the open Drake Screen W2: automation id, type, on-screen position and label."""
    try:
        filler, nav, Desktop = _drake_modules()
    except DrakeUnavailable as exc:
        return jsonify({"success": False, "unavailable": True, "error": str(exc)})
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pass
    with _drake_lock:
        hwnd, title = filler.find_drake_window()
        if not hwnd:
            return jsonify({"success": False, "error": "Drake Tax 2025 is not running."})
        win = Desktop(backend="uia").window(handle=hwnd)
        if filler.get_current_drake_state(win) != "W2_SCREEN":
            return jsonify({"success": False, "error": "Open Screen W2 in Drake (on the W-2 tab), then click Link Drake fields again."})
        texts = []
        for t in win.descendants(control_type="Text"):
            try:
                s = t.window_text().strip()
                if s:
                    texts.append((s.rstrip(":"), t.rectangle()))
            except Exception:
                pass
        controls = []
        for aid, (kind, c) in _collect_controls(win).items():
            try:
                if not c.is_visible():
                    continue
                r = c.rectangle()
                if r.width() <= 2 or r.height() <= 2:
                    continue
                controls.append({"aid": aid, "control": kind, "x": r.left, "y": r.top, "w": r.width(), "h": r.height(),
                                 "label": _nearest_label(r, texts), "enabled": bool(c.is_enabled())})
            except Exception:
                continue
    return jsonify({"success": True, "title": title, "controls": controls})
