"""
/review — guided Drake review workflow (Upload → Analyze → module screens → Summary → Transfer) and its API.
"""
import os
import time

from flask import Blueprint, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from . import catalog, session, transfer

review_bp = Blueprint("taxflow_review", __name__)
UPLOAD_DIR = os.path.join(session.BASE, "uploads")


def _err(msg, code=400, **kw):
    return jsonify({"success": False, "error": msg, **kw}), code


def _sess(sid):
    try:
        return session.load(sid)
    except (KeyError, OSError, ValueError):
        return None


@review_bp.route("/review")
def review_page():
    return render_template("review.html")


@review_bp.route("/api/review/catalog")
def api_catalog():
    return jsonify({"success": True, "modules": catalog.MODULES, "forms": catalog.public_catalog()})


@review_bp.route("/api/review/sessions")
def api_sessions():
    return jsonify({"success": True, "sessions": session.list_sessions()})


@review_bp.route("/api/review/upload", methods=["POST"])
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return _err("No file was uploaded.")
    name = secure_filename(f.filename) or "packet.pdf"
    if not name.lower().endswith(".pdf"):
        return _err("Please upload a PDF file.")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    dest = os.path.join(UPLOAD_DIR, f"{time.strftime('%Y%m%d-%H%M%S')}-{name}")
    f.save(dest)
    with open(dest, "rb") as fh:
        if fh.read(5) != b"%PDF-":
            os.remove(dest)
            return _err("That file is not a valid PDF.")
    sid = session.create(dest, f.filename)
    return jsonify({"success": True, "id": sid})


@review_bp.route("/api/review/use-current", methods=["POST"])
def api_use_current():
    """Start a review of the packet already loaded in the W-2 mapping page (handy for testing)."""
    try:
        import w2_mapping
        path = w2_mapping.current_pdf_path()
    except Exception:
        path = None
    if not path:
        return _err("No tax packet PDF is loaded yet — upload one.", 404)
    return jsonify({"success": True, "id": session.create(path, os.path.basename(path))})


@review_bp.route("/api/review/<sid>/job")
def api_job(sid):
    if not _sess(sid):
        return _err("Unknown review session.", 404)
    return jsonify({"success": True, **session.job(sid)})


@review_bp.route("/api/review/<sid>")
def api_session(sid):
    s = _sess(sid)
    if not s:
        return _err("Unknown review session.", 404)
    if s.get("status") == "analyzing":
        return jsonify({"success": True, "status": "analyzing", "job": session.job(sid)})
    if s.get("status") == "error":
        return _err(f"The PDF could not be analyzed: {s.get('error')}", 500)
    a = s["analysis"]
    statuses = {d["id"]: session.doc_status(s, d) for d in a["documents"]}
    links = {}
    for d in a["documents"]:
        links.setdefault(d["screen"], {}).update(transfer.link_status(d["screen"], d["fields"]))
    return jsonify({"success": True, "id": sid, "file": s["file"], "status": s["status"], "analysis": a, "state": s["state"],
                    "statuses": statuses, "links": links, "transfer": s.get("transfer")})


@review_bp.route("/api/review/<sid>/pdf")
def api_pdf(sid):
    s = _sess(sid)
    if not s or not os.path.isfile(s.get("pdf_path", "")):
        return "PDF not found", 404
    return send_file(s["pdf_path"], mimetype="application/pdf")


@review_bp.route("/api/review/<sid>/doc/<doc_id>", methods=["POST"])
def api_doc(sid, doc_id):
    if not _sess(sid):
        return _err("Unknown review session.", 404)
    try:
        res = session.update_doc(sid, doc_id, request.get_json(silent=True) or {})
    except KeyError as exc:
        return _err(str(exc), 404)
    return jsonify({"success": res["ok"], **res})


@review_bp.route("/api/review/<sid>/doc/<doc_id>/retype", methods=["POST"])
def api_retype(sid, doc_id):
    if not _sess(sid):
        return _err("Unknown review session.", 404)
    try:
        res = session.retype(sid, doc_id, (request.get_json(silent=True) or {}).get("type"))
    except KeyError as exc:
        return _err(str(exc), 404)
    return jsonify({"success": res["ok"], **res})


@review_bp.route("/api/review/<sid>/learn", methods=["POST"])
def api_learn(sid):
    p = request.get_json(silent=True) or {}
    ok = session.learn(p.get("form_type"), p.get("pdf_label"), p.get("field_key"))
    return jsonify({"success": ok})


@review_bp.route("/api/review/<sid>/reanalyze", methods=["POST"])
def api_reanalyze(sid):
    if not _sess(sid):
        return _err("Unknown review session.", 404)
    session.reanalyze(sid)
    return jsonify({"success": True})


@review_bp.route("/api/review/<sid>/summary")
def api_summary(sid):
    s = _sess(sid)
    if not s or not s.get("analysis"):
        return _err("Unknown review session.", 404)
    return jsonify({"success": True, **session.summary(s), "plan": session.transfer_plan(s)})


@review_bp.route("/api/review/<sid>/transfer", methods=["GET", "POST"])
def api_transfer(sid):
    if not _sess(sid):
        return _err("Unknown review session.", 404)
    if request.method == "GET":
        return jsonify({"success": True, **transfer.state(sid)})
    p = request.get_json(silent=True) or {}
    res = transfer.start(sid, overwrite=bool(p.get("overwrite")), dry_run=bool(p.get("dry_run")), doc_ids=p.get("doc_ids"))
    return jsonify({"success": res["ok"], **res}), (200 if res["ok"] else 409)


@review_bp.route("/api/review/links/<screen>", methods=["GET", "POST"])
def api_links(screen):
    if request.method == "GET":
        return jsonify({"success": True, "links": transfer.load_links().get(screen, {})})
    p = request.get_json(silent=True) or {}
    return jsonify({"success": True, "links": transfer.save_links(screen, p.get("links") or {})})


@review_bp.route("/api/review/discover", methods=["POST"])
def api_discover():
    p = request.get_json(silent=True) or {}
    screen = str(p.get("screen") or "")
    try:
        res = transfer.discover(screen, open_screen=bool(p.get("open_screen", True)))
    except transfer.DrakeUnavailable as exc:
        return jsonify({"success": False, "unavailable": True, "error": str(exc)})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)})
    return jsonify({"success": True, "controls": res["controls"], "logs": res["logs"],
                    "suggestions": transfer.suggest(screen, res["controls"])})
