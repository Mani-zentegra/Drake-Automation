"""
Review sessions.

One session = one uploaded PDF + its analysis + everything the reviewer did:

  state[doc_id] = {
      "values":   {field_key: {"value": v, "origin": "pdf"|"edited"|"mapped"|"fixed"|"blank", "src": pdf_field_id|None,
                               "confirmed": bool}},
      "reviewed": bool,          # reviewer marked the whole form as reviewed & confirmed
      "excluded": bool,          # not transferred (duplicates, informational forms, ...)
      "note": str
  }

Only values that are confirmed, on documents that are reviewed and not excluded, are ever sent to Drake.
Sessions are plain JSON files in uploads/sessions/ so a review can be resumed after a restart.
"""
import json
import os
import re
import threading
import time
import uuid

from . import catalog
from .extract import analyze_pdf, norm_label
from .validate import validate

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESS_DIR = os.path.join(BASE, "uploads", "sessions")
LEARNED_FILE = os.path.join(BASE, "taxflow_learned_mappings.json")
_lock = threading.RLock()
_jobs = {}            # sid -> {"stage", "pct", "error"}
_mem = {}


def _path(sid):
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", sid or ""):
        raise KeyError("bad session id")
    return os.path.join(SESS_DIR, f"{sid}.json")


def load(sid):
    with _lock:
        if sid in _mem:
            return _mem[sid]
        with open(_path(sid), "r", encoding="utf-8") as fh:
            s = json.load(fh)
        _mem[sid] = s
        return s


def save(s):
    s["updated"] = time.time()
    os.makedirs(SESS_DIR, exist_ok=True)
    with _lock:
        tmp = _path(s["id"]) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(s, fh)
        os.replace(tmp, _path(s["id"]))
        _mem[s["id"]] = s


def list_sessions():
    out = []
    if not os.path.isdir(SESS_DIR):
        return out
    for fn in os.listdir(SESS_DIR):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(SESS_DIR, fn), "r", encoding="utf-8") as fh:
                s = json.load(fh)
        except (OSError, ValueError):
            continue
        a = s.get("analysis") or {}
        st = s.get("state") or {}
        docs = a.get("documents") or []
        out.append({"id": s["id"], "file": s.get("file"), "created": s.get("created"), "updated": s.get("updated"),
                    "status": s.get("status"), "taxpayer": (a.get("taxpayer") or {}).get("name", ""), "year": a.get("tax_year", ""),
                    "documents": len(docs), "reviewed": sum(1 for d in docs if (st.get(d["id"]) or {}).get("reviewed")),
                    "transferred": bool((s.get("transfer") or {}).get("finished"))})
    return sorted(out, key=lambda x: -(x["updated"] or 0))


# ---------------------------------------------------------------------------
# learned mappings (reviewer mapped an unknown PDF label to a Drake field -> reused next time)
# ---------------------------------------------------------------------------
def load_learned():
    try:
        with open(LEARNED_FILE, "r", encoding="utf-8") as fh:
            d = json.load(fh)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def learn(form_type, pdf_label, field_key):
    if form_type not in catalog.FORMS or not pdf_label:
        return False
    keys = {f["key"] for f in catalog.FORMS[form_type]["fields"]}
    if field_key not in keys:
        return False
    with _lock:
        d = load_learned()
        d.setdefault(form_type, {})[norm_label(pdf_label)] = field_key
        with open(LEARNED_FILE, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=2)
    return True


# ---------------------------------------------------------------------------
# create / analyze
# ---------------------------------------------------------------------------
def initial_state(doc):
    vals = {}
    for f in doc["fields"]:
        has = f["value"] not in ("", None) and f["value"] is not False
        vals[f["key"]] = {"value": f["value"], "origin": ("pdf" if has else "blank") if f["mode"] != "manual" else ("fixed" if has else "blank"),
                          "src": ("f:" + f["key"]) if (has or f["status"] == "blank") and f["mode"] != "manual" else None,
                          "confirmed": False}
    return {"values": vals, "reviewed": False, "excluded": bool(doc.get("excluded_default")), "note": ""}


def create(pdf_path, original_name):
    sid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    s = {"id": sid, "file": original_name, "pdf_path": pdf_path, "created": time.time(), "updated": time.time(),
         "status": "analyzing", "analysis": None, "state": {}, "transfer": None}
    save(s)
    _jobs[sid] = {"stage": "Queued", "pct": 0, "error": None}

    def run():
        try:
            def prog(stage, pct):
                _jobs[sid] = {"stage": stage, "pct": pct, "error": None}
            a = analyze_pdf(pdf_path, learned=load_learned(), progress=prog)
            s2 = load(sid)
            s2["analysis"] = a
            s2["state"] = {d["id"]: initial_state(d) for d in a["documents"]}
            s2["status"] = "review"
            save(s2)
            _jobs[sid] = {"stage": "Done", "pct": 100, "error": None}
        except Exception as exc:          # report, never leave the reviewer waiting
            import traceback
            traceback.print_exc()
            s2 = load(sid)
            s2["status"] = "error"
            s2["error"] = str(exc)
            save(s2)
            _jobs[sid] = {"stage": "Failed", "pct": 100, "error": str(exc)}

    threading.Thread(target=run, daemon=True).start()
    return sid


def job(sid):
    j = _jobs.get(sid)
    if j:
        return j
    s = load(sid)
    return {"stage": "Done" if s.get("status") != "error" else "Failed", "pct": 100, "error": s.get("error")}


def reanalyze(sid):
    """Re-run extraction (e.g. after new learned mappings); keeps reviewer edits for documents that still exist."""
    s = load(sid)
    a = analyze_pdf(s["pdf_path"], learned=load_learned())
    old = s.get("state") or {}
    st = {}
    for d in a["documents"]:
        st[d["id"]] = old.get(d["id"]) or initial_state(d)
        for k, v in initial_state(d)["values"].items():
            st[d["id"]]["values"].setdefault(k, v)
    s["analysis"], s["state"] = a, st
    save(s)
    return s


# ---------------------------------------------------------------------------
# review operations
# ---------------------------------------------------------------------------
def doc_of(s, doc_id):
    for d in s["analysis"]["documents"]:
        if d["id"] == doc_id:
            return d
    raise KeyError(f"unknown document {doc_id}")


def values_of(s, doc_id):
    return {k: v["value"] for k, v in s["state"][doc_id]["values"].items()}


def issues_of(s, doc):
    return validate(doc["type"], doc["fields"], values_of(s, doc["id"]), s["analysis"].get("tax_year", ""))


def doc_status(s, doc):
    st = s["state"][doc["id"]]
    iss = issues_of(s, doc)
    sendable = [f for f in doc["fields"] if _has_value(st["values"].get(f["key"]), f)]
    conf = [f for f in sendable if st["values"][f["key"]].get("confirmed")]
    errors = [k for k, i in iss.items() if i["level"] in ("error", "missing")]
    return {"reviewed": st["reviewed"], "excluded": st["excluded"], "issues": iss, "errors": len(errors),
            "warnings": sum(1 for i in iss.values() if i["level"] == "warn"),
            "to_confirm": len(sendable), "confirmed": len(conf),
            "state": "excluded" if st["excluded"] else "reviewed" if st["reviewed"] else "errors" if errors else
                     "in_progress" if conf else "pending"}


def _has_value(v, f):
    if not v:
        return False
    if f["type"] == "bool":
        return v.get("value") is True or v.get("origin") == "edited"
    return v.get("value") not in ("", None)


def update_doc(sid, doc_id, payload):
    """payload: {"values": {key: {value?, origin?, src?, confirmed?}}, "reviewed"?: bool, "excluded"?: bool, "note"?: str}"""
    with _lock:
        s = load(sid)
        d = doc_of(s, doc_id)
        st = s["state"][doc_id]
        keys = {f["key"]: f for f in d["fields"]}
        for k, upd in (payload.get("values") or {}).items():
            if k not in keys or not isinstance(upd, dict):
                continue
            cur = st["values"].setdefault(k, {"value": "", "origin": "blank", "src": None, "confirmed": False})
            for a in ("value", "origin", "src", "confirmed"):
                if a in upd:
                    cur[a] = upd[a]
            if "value" in upd and "confirmed" not in upd:
                cur["confirmed"] = False            # a changed value must be confirmed again
            if "value" in upd or "confirmed" in upd:
                st["reviewed"] = False if not payload.get("reviewed") else st["reviewed"]
        if "excluded" in payload:
            st["excluded"] = bool(payload["excluded"])
        if "note" in payload:
            st["note"] = str(payload["note"])[:500]
        status = doc_status(s, d)
        if payload.get("reviewed") is True:
            if status["errors"]:
                save(s)
                return {"ok": False, "error": f"Fix {status['errors']} field(s) before marking this form reviewed.", "status": doc_status(s, d)}
            missing_conf = status["to_confirm"] - status["confirmed"]
            if missing_conf:
                save(s)
                return {"ok": False, "error": f"Confirm the remaining {missing_conf} value(s) (or clear them) before marking this form reviewed.",
                        "status": doc_status(s, d)}
            st["reviewed"] = True
        elif payload.get("reviewed") is False:
            st["reviewed"] = False
        save(s)
        return {"ok": True, "status": doc_status(s, d)}


def retype(sid, doc_id, new_type):
    """Reviewer says what an unrecognised (or misrecognised) document is: give it that form's Drake screen and
    fields. Values found on the page stay available in the mapping view to drag onto the new fields."""
    from . import derive
    from .extract import display
    if new_type not in catalog.FORMS:
        return {"ok": False, "error": "Unknown form type."}
    with _lock:
        s = load(sid)
        d = doc_of(s, doc_id)
        f0 = catalog.FORMS[new_type]
        fields = []
        for f in catalog.clone_fields(new_type):
            if f["mode"] == "block":
                continue
            rec = {k: f[k] for k in ("key", "label", "type", "box", "section", "required", "aid", "control", "mode", "hint", "options", "ref", "pattern")}
            v = False if f["type"] == "bool" else ("T" if f["key"] == "ts" else "")
            rec.update({"raw": "", "value": v, "display": display(f["type"], v), "page": None, "bbox": None, "conf": 0.0,
                        "how": "defaulted to taxpayer — change to S for the spouse" if f["key"] == "ts" else "map manually",
                        "status": "extracted" if v else "not_found"})
            fields.append(rec)
        d.update(type=new_type, form_name=f0["name"], module=f0["module"], screen=f0["screen"], screen_name=f0["screen_name"],
                 informational=bool(f0.get("informational")), drake_verified=bool(f0.get("drake_verified")), fields=fields,
                 retyped=True, flags=[{"level": "info", "text": "Form type chosen by the reviewer — drag the values from the PDF onto the Drake fields."}])
        for p in d["pdf_fields"]:
            p["auto"] = None
        derive.number_and_group(s["analysis"])
        s["state"][doc_id] = initial_state(d)
        save(s)
        return {"ok": True, "id": doc_id, "module": d["module"]}


def summary(s):
    a = s["analysis"]
    out = {"documents": [], "modules": a["modules"], "ready": True, "blocking": []}
    for d in a["documents"]:
        stt = doc_status(s, d)
        out["documents"].append({"id": d["id"], "type": d["type"], "module": d["module"], "screen": d["screen"], "payer": d["payer"],
                                 "page": d["page"], "record": d["record"], "records": d["records"], **{k: v for k, v in stt.items() if k != "issues"}})
        if not stt["excluded"] and not stt["reviewed"]:
            out["ready"] = False
            out["blocking"].append(d["id"])
    return out


def transfer_plan(s):
    """Everything that would be sent to Drake: reviewed, included documents and their confirmed values only."""
    plan = []
    for d in s["analysis"]["documents"]:
        st = s["state"][d["id"]]
        if st["excluded"] or not st["reviewed"]:
            continue
        vals = []
        for f in d["fields"]:
            v = st["values"].get(f["key"]) or {}
            if not v.get("confirmed") or not _has_value(v, f):
                continue
            vals.append({"key": f["key"], "label": f["label"], "box": f["box"], "type": f["type"], "value": v["value"],
                         "aid": f.get("aid"), "control": f.get("control"), "ref": bool(f.get("ref"))})
        lots = None
        if d.get("lots") is not None and (st.get("lots_confirmed") or True):
            lots = d["lots"]
        plan.append({"doc_id": d["id"], "type": d["type"], "screen": d["screen"], "screen_name": d["screen_name"], "module": d["module"],
                     "record": d["record"], "records": d["records"], "payer": d["payer"], "page": d["page"],
                     "informational": d.get("informational"), "zero_value": d.get("zero_value"), "values": vals, "lots": lots})
    return plan
