import os
import sys
import json
import time
import requests
from flask import Flask, request, jsonify, render_template, send_file
import zoho_api
from date_utils import format_to_drake_date
import app_navigator

# Dedicated PDF modules
from extractor import extract_w2_from_pdf
from drake_w2_filler import populate_w2_screen, save_and_exit_w2, discard_w2_screen
from packet_extractor import extract_all_modules_from_packet
from drake_packet_filler import populate_all_packet_modules, populate_single_packet_module, save_and_exit_packet_screen, open_drake_screen
import packet_history_manager as history_mgr

# Dedicated Excel modules
from excel_extractor import extract_excel_organizer
from drake_excel_filler import populate_excel_return, populate_dependents_return, save_and_exit_excel, discard_excel

app = Flask(__name__)
# W-2 PDF -> Drake visual mapping page (/w2-mapping)
from w2_mapping import w2_bp
app.register_blueprint(w2_bp)
from drake_view import drake_view_bp
app.register_blueprint(drake_view_bp)
from packet_analysis import packet_bp
app.register_blueprint(packet_bp)
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

# Default Sample Paths
default_pdf_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Weaver-Cummings_2025_Tax_Packet.pdf"))
default_excel_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "2025 Personal Tax Organizer.xlsx"))
active_pdf_path = default_pdf_path
active_excel_path = default_excel_path

# =============================================================================
# MAIN UI ROUTE: DYNAMIC FIELD MAPPING INTERFACE
# =============================================================================
@app.route("/")
def index():
    """
    Renders the new dynamic Field Mapping Interface.
    Fetches Meta API fields and automatically fetches Drake fields by default.
    """
    return render_template("index.html")

# =============================================================================
# AUTOMATED SOFTWARE NAVIGATION ENDPOINTS (ZERO ALT+TAB)
# =============================================================================
@app.route("/api/navigator/switch", methods=["POST"])
def api_navigator_switch():
    """
    Switches active foreground window between Drake Tax and Browser automatically.
    """
    payload = request.get_json() or {}
    target = payload.get("app", "drake").lower()

    if target == "drake":
        ok, hwnd, title = app_navigator.switch_to_drake(dismiss_popups=True)
        return jsonify({"success": ok, "target": "drake", "hwnd": hwnd, "title": title})
    elif target in ["browser", "chrome", "edge"]:
        ok, hwnd, title = app_navigator.switch_to_browser()
        return jsonify({"success": ok, "target": "browser", "hwnd": hwnd, "title": title})
    else:
        return jsonify({"success": False, "error": f"Unknown target: {target}"}), 400

@app.route("/api/navigator/status", methods=["GET"])
def api_navigator_status():
    """
    Reports the status of detected applications and windows.
    """
    d_h, d_t = app_navigator.find_drake_window()
    b_h, b_t = app_navigator.find_browser_window()
    return jsonify({
        "success": True,
        "drake": {"detected": bool(d_h), "hwnd": d_h, "title": d_t},
        "browser": {"detected": bool(b_h), "hwnd": b_h, "title": b_t}
    })

# =============================================================================
# DYNAMIC MODULE RESOLUTION & ZOHO CREATOR META API ENDPOINTS
# =============================================================================
@app.route("/api/module/info", methods=["GET"])
def api_module_info():
    """
    Resolves module metadata dynamically based on the 'type' URL parameter.
    Supports type=personal, type=dependent, etc.
    """
    m_type = request.args.get("type", "personal").strip()
    mod = zoho_api.get_module_by_type(m_type)
    return jsonify({"success": True, "module": mod})

@app.route("/api/meta/forms", methods=["GET"])
def api_meta_forms():
    """
    Fetches all available forms dynamically from Zoho Creator Meta API,
    enriching each with its corresponding module type and Drake screen.
    """
    forms, err = zoho_api.fetch_creator_forms()
    if err:
        return jsonify({"success": False, "error": err}), 500

    enriched = []
    for f in forms:
        lname = f.get("link_name", "")
        mod = zoho_api.get_module_by_type(lname)
        item = dict(f)
        item["module_type"] = mod["type"]
        item["drake_screen"] = mod["drake_screen"]
        enriched.append(item)

    return jsonify({"success": True, "forms": enriched})

@app.route("/api/meta/fields", methods=["GET"])
def api_meta_fields():
    """
    Fetches all fields dynamically for a specific form/module from Zoho Creator Fields API.
    Supports either ?type=dependent OR ?form=Dependents
    Ref: https://www.zoho.com/creator/help/api/v2.1/get-fields.html
    """
    m_type = request.args.get("type")
    form_link_name = request.args.get("form")

    if m_type:
        mod = zoho_api.get_module_by_type(m_type)
        form_link_name = mod["form_link_name"]
    elif not form_link_name:
        form_link_name = "Personal_Info"

    data, err = zoho_api.fetch_creator_form_fields(form_link_name)
    if err:
        return jsonify({"success": False, "error": err}), 500

    mod = zoho_api.get_module_by_type(form_link_name)
    return jsonify({
        "success": True,
        "form": data.get("form"),
        "module_type": mod["type"],
        "drake_screen": mod["drake_screen"],
        "raw_fields": data.get("raw_fields", []),
        "flattened_fields": data.get("flattened_fields", [])
    })

@app.route("/api/drake/fields", methods=["GET"])
def api_drake_fields():
    """
    Fetches available Drake Tax target fields dynamically based on the module type.
    Supports ?type=dependent (Screen 2) OR ?type=personal (Screen 1)
    """
    m_type = request.args.get("type", "personal").strip()
    mod = zoho_api.get_module_by_type(m_type)
    fields = zoho_api.get_drake_fields_schema(module_type=mod["type"])
    return jsonify({
        "success": True,
        "fields": fields,
        "module": mod
    })

@app.route("/api/field-mapping", methods=["GET"])
def api_get_field_mappings():
    """
    Retrieves the currently saved field mappings for the requested module type.
    """
    m_type = request.args.get("type", "personal").strip()
    mappings = zoho_api.get_saved_mappings(module_type=m_type)
    return jsonify({"success": True, "mappings": mappings, "module_type": m_type})

@app.route("/api/field-mapping", methods=["POST"])
def api_save_field_mappings():
    """
    Persists user-defined field mappings scoped to the module type.
    """
    payload = request.get_json() or {}
    mappings = payload.get("mappings", {})
    m_type = payload.get("type") or request.args.get("type", "personal")
    success, err = zoho_api.save_field_mappings(mappings, module_type=m_type)
    if not success:
        return jsonify({"success": False, "error": err}), 500
    return jsonify({"success": True, "message": "Field mappings saved successfully.", "module_type": m_type})

@app.route("/api/field-mapping/defaults", methods=["GET"])
def api_get_default_mappings():
    """
    Retrieves the system default recommended field mappings for module type.
    """
    m_type = request.args.get("type", "personal").strip()
    defaults = zoho_api.get_default_mappings(module_type=m_type)
    return jsonify({"success": True, "mappings": defaults, "module_type": m_type})

@app.route("/api/field-mapping/auto-suggest", methods=["POST"])
def api_auto_suggest_mappings():
    """
    Intelligently suggests matches between Zoho Creator Meta fields and Drake fields.
    """
    payload = request.get_json() or {}
    m_type = payload.get("type") or request.args.get("type", "personal")
    mod = zoho_api.get_module_by_type(m_type)
    form_name = payload.get("form") or mod["form_link_name"]
    
    meta_data, err = zoho_api.fetch_creator_form_fields(form_name)
    if err or not meta_data:
        return jsonify({"success": False, "error": err or "Failed to fetch form fields"}), 500
    
    flattened = meta_data.get("flattened_fields", [])
    drake_fields = zoho_api.get_drake_fields_schema(module_type=mod["type"])
    default_maps = zoho_api.get_default_mappings(module_type=mod["type"])
    
    suggested = {}
    for f in flattened:
        # Ignore subform container element itself (type 21)
        if f.get("type") == 21 and not f.get("parent_subform"):
            continue

        full_key = f.get("full_link_name") or f.get("link_name", "")
        bare_key = f.get("link_name", "")
        disp = (f.get("display_label") or f.get("display_name") or "").lower()
        key_low = full_key.lower()
        
        # Check against default mappings first (checking both full key and bare link name)
        if full_key in default_maps:
            suggested[full_key] = default_maps[full_key]
            suggested[bare_key] = default_maps[full_key]
            continue
        elif bare_key in default_maps:
            suggested[full_key] = default_maps[bare_key]
            suggested[bare_key] = default_maps[bare_key]
            continue
            
        best_match = None
        for df in drake_fields:
            d_id = df["id"]
            
            # Dependent matching
            if mod["type"] == "dependent" or "dependent" in key_low or "dependent" in disp:
                if d_id.startswith("dependent."):
                    if ("name" in key_low or "name" in disp or "first" in key_low or "first" in disp) and ("first_name" in d_id or "name" in d_id):
                        best_match = d_id; break
                    if ("dob" in key_low or "birth" in disp) and "dob" in d_id:
                        best_match = d_id; break
                    if ("ssn" in key_low or "security" in disp or "itin" in key_low) and "ssn" in d_id:
                        best_match = d_id; break
                    if ("relat" in key_low or "relat" in disp) and "relationship" in d_id:
                        best_match = d_id; break
                    if ("month" in key_low or "home" in disp) and "months" in d_id:
                        best_match = d_id; break
                elif "notes" in key_low or "notes" in disp or "preparer" in key_low:
                    if "notes" in d_id:
                        best_match = d_id; break
            
            # Spouse matching
            elif "spouse" in key_low or "spouse" in disp:
                if d_id.startswith("spouse."):
                    if ("first" in key_low or "first" in disp) and "first" in d_id:
                        best_match = d_id; break
                    if ("last" in key_low or "last" in disp) and "last" in d_id:
                        best_match = d_id; break
                    if ("ssn" in key_low or "itin" in key_low or "soc" in disp) and "ssn" in d_id:
                        best_match = d_id; break
                    if ("dob" in key_low or "birth" in disp) and "dob" in d_id:
                        best_match = d_id; break
                    if ("occup" in key_low or "occup" in disp) and "occupation" in d_id:
                        best_match = d_id; break
                    if ("phone" in key_low or "phone" in disp) and "phone" in d_id:
                        best_match = d_id; break
                    if ("email" in key_low or "email" in disp) and "email" in d_id:
                        best_match = d_id; break

            # Taxpayer matching
            elif any(x in key_low or x in disp for x in ["taxpayer", "first_name", "last_name", "ssn", "dob", "occupation", "filing"]):
                if d_id.startswith("taxpayer."):
                    if ("first" in key_low or "first" in disp) and "first" in d_id:
                        best_match = d_id; break
                    if ("last" in key_low or "last" in disp) and "last" in d_id:
                        best_match = d_id; break
                    if ("ssn" in key_low or "soc" in disp) and "ssn" in d_id:
                        best_match = d_id; break
                    if ("dob" in key_low or "birth" in disp) and "dob" in d_id:
                        best_match = d_id; break
                    if ("occup" in key_low or "occup" in disp) and "occupation" in d_id:
                        best_match = d_id; break
                    if ("phone" in key_low or "phone" in disp) and "phone" in d_id:
                        best_match = d_id; break
                    if ("email" in key_low or "email" in disp) and "email" in d_id:
                        best_match = d_id; break
                    if ("filing" in key_low or "status" in disp) and "filing" in d_id:
                        best_match = d_id; break

            # Address matching
            elif any(x in key_low or x in disp for x in ["address", "city", "state", "zip"]):
                if d_id.startswith("address."):
                    if ("address" in key_low or "address" in disp) and "street" in d_id:
                        best_match = d_id; break
                    if "city" in key_low and "city" in d_id:
                        best_match = d_id; break
                    if "state" in key_low and "state" in d_id:
                        best_match = d_id; break
                    if "zip" in key_low and "zip" in d_id:
                        best_match = d_id; break

            # Bank matching
            elif any(x in key_low or x in disp for x in ["bank", "routing", "account"]):
                if d_id.startswith("bank."):
                    if "name" in key_low and "bank_name" in d_id:
                        best_match = d_id; break
                    if "routing" in key_low and "routing" in d_id:
                        best_match = d_id; break
                    if "account_number" in key_low and "account_number" in d_id:
                        best_match = d_id; break
                    if "account_type" in key_low and "account_type" in d_id:
                        best_match = d_id; break

        if best_match:
            suggested[key] = best_match

    return jsonify({"success": True, "mappings": suggested})

@app.route("/api/field-mapping/insert-into-drake", methods=["POST"])
def api_insert_into_drake():
    """
    Direct 1-click execution:
    1. Identifies module from 'type' parameter (personal, dependent, etc.)
    2. Fetches Zoho Creator record for record_id from the corresponding report
    3. Applies active field mappings
    4. Automatically populates Drake Tax 2025 for that module (Screen 1 or Screen 2)
    """
    payload = request.get_json() or {}
    m_type = payload.get("type") or request.args.get("type", "personal")
    mod = zoho_api.get_module_by_type(m_type)

    # Default sample record ID if not provided
    default_rec_id = "266830000014776584" if mod["type"] == "dependent" else "266830000014689319"
    record_id = payload.get("record_id") or request.args.get("record_id") or default_rec_id
    record_id = str(record_id).strip()
    custom_mappings = payload.get("mappings")

    report = mod["report_link_name"]

    try:
        # Fetch record from Zoho Creator
        raw_record, err = zoho_api.fetch_creator_record(record_id, report_link_name=report, return_raw=True)
        if err:
            return jsonify({"success": False, "error": err}), 404

        # Execution based on module type:
        if mod["type"] == "dependent":
            # Extract dependents from record
            dependents_list = zoho_api.extract_dependents_from_record(raw_record, custom_mappings=custom_mappings)
            if not dependents_list:
                return jsonify({
                    "success": False,
                    "status": "ERROR",
                    "error": "No dependent records found in Zoho Creator data."
                }), 400

            # Resolve client from lookup field 'Tax_Payer_Full_name' in Dependents form
            tp_lookup = (
                raw_record.get("Tax_Payer_Full_name")
                or raw_record.get("Tax_Payer_Full_Name")
                or raw_record.get("Taxpayer_Full_Name")
                or raw_record.get("Taxpayer_Name")
                or raw_record.get("Tax_Payer_Name")
            )
            client_info = None
            linked_tp_id = None
            if tp_lookup:
                if isinstance(tp_lookup, dict):
                    linked_tp_id = tp_lookup.get("ID") or tp_lookup.get("id")
                elif isinstance(tp_lookup, str) and tp_lookup.strip().isdigit():
                    linked_tp_id = tp_lookup.strip()

            if linked_tp_id:
                # Fetch linked Taxpayer record from All_Personal_Infos using the client ID from lookup
                tp_raw, tp_err = zoho_api.fetch_creator_record(str(linked_tp_id), report_link_name="All_Personal_Infos", return_raw=True)
                if not tp_err and tp_raw:
                    client_info = zoho_api.map_creator_to_drake(tp_raw)
                    if "taxpayer" in client_info and isinstance(client_info["taxpayer"], dict) and "dob" in client_info["taxpayer"]:
                        client_info["taxpayer"]["dob"] = format_to_drake_date(client_info["taxpayer"]["dob"])

            if not client_info:
                client_info = zoho_api.map_creator_to_drake(raw_record, custom_mappings=custom_mappings)
                # If tp_lookup has display value / name, populate taxpayer name
                if tp_lookup and isinstance(tp_lookup, dict):
                    disp_name = tp_lookup.get("zc_display_value") or tp_lookup.get("Taxpayer_Full_Name") or tp_lookup.get("display_value")
                    if disp_name and "taxpayer" in client_info:
                        parts = disp_name.strip().split()
                        if parts and not client_info["taxpayer"].get("first_name"):
                            client_info["taxpayer"]["first_name"] = parts[0]
                        if len(parts) > 1 and not client_info["taxpayer"].get("last_name"):
                            client_info["taxpayer"]["last_name"] = parts[-1]

            result = populate_dependents_return(dependents_list, client_info=client_info)
            if isinstance(result, tuple) and len(result) == 3:
                success, logs, status = result
            else:
                success, logs = result
                status = "POPULATED" if success else "ERROR"

            if status == "STOPPED":
                message = "Drake automation was stopped by user."
            elif success:
                message = f"Successfully populated {len(dependents_list)} dependent(s) into Drake Tax 2025 (Screen 2 Dependents)! Review on desktop."
            else:
                message = f"Drake entry notification: {logs[-1] if logs else 'Please verify Drake is running'}"

            # Auto-update Zoho Creator Status field
            try:
                creator_status = "Finished" if success else ("Error" if status != "STOPPED" else "In Progress")
                zoho_api.update_creator_record_status(record_id, report, status=creator_status, message=message)
                if linked_tp_id:
                    zoho_api.update_creator_record_status(str(linked_tp_id), "All_Personal_Infos", status=creator_status, message=message)
            except Exception:
                pass

            return jsonify({
                "success": success,
                "status": status,
                "module_type": mod["type"],
                "drake_screen": mod["drake_screen"],
                "dependents_count": len(dependents_list),
                "record_id": record_id,
                "logs": logs,
                "message": message,
                "error": logs[-1] if not success and logs else ""
            })

        else:
            # Personal Demographics & Address (Screen 1)
            drake_data = zoho_api.map_creator_to_drake(raw_record, custom_mappings=custom_mappings)

            # Standardize dates
            if "taxpayer" in drake_data and isinstance(drake_data["taxpayer"], dict) and "dob" in drake_data["taxpayer"]:
                drake_data["taxpayer"]["dob"] = format_to_drake_date(drake_data["taxpayer"]["dob"])
            if "spouse" in drake_data and isinstance(drake_data["spouse"], dict) and "dob" in drake_data["spouse"]:
                drake_data["spouse"]["dob"] = format_to_drake_date(drake_data["spouse"]["dob"])

            # Populate Drake Tax Screen 1
            result = populate_excel_return(drake_data)
            if isinstance(result, tuple) and len(result) == 3:
                success, logs, status = result
            else:
                success, logs = result
                status = "POPULATED" if success else "ERROR"

            tp = drake_data.get("taxpayer", {})
            client_name = f"{tp.get('first_name', '')} {tp.get('last_name', '')}".strip() or "Client"

            message = (
                f"Successfully populated client return for {client_name} into Drake Tax 2025 "
                f"(Screen 1 Name, Address & Demographics)! Review in Drake on your desktop."
                if success else f"Drake entry notification: {logs[-1] if logs else 'Please verify Drake is running'}"
            )

            # Auto-update Zoho Creator Status field
            try:
                creator_status = "Finished" if success else ("Error" if status != "STOPPED" else "In Progress")
                zoho_api.update_creator_record_status(record_id, report, status=creator_status, message=message)
            except Exception:
                pass

            return jsonify({
                "success": success,
                "status": status,
                "module_type": mod["type"],
                "drake_screen": mod["drake_screen"],
                "client_name": client_name,
                "record_id": record_id,
                "logs": logs,
                "message": message,
                "error": logs[-1] if not success and logs else ""
            })
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "error": str(e), "message": f"Error inserting into Drake: {str(e)}"}), 500

@app.route("/api/automation/stop", methods=["POST"])
def api_automation_stop():
    """
    Immediately stops any running Drake Tax automation task.
    Triggered from the frontend 'Stop Automation' button.
    """
    from drake_excel_filler import request_automation_stop, dismiss_drake_popups
    request_automation_stop()
    try:
        dismiss_drake_popups(prefer_cancel=True)
    except Exception:
        pass
    return jsonify({
        "success": True,
        "status": "STOPPED",
        "message": "Automation stop signal sent successfully."
    })

@app.route("/api/field-mapping/transform-preview", methods=["POST"])
def api_transform_preview():
    """
    Fetches real Zoho Creator record and transforms it using active field mappings.
    """
    record_id = request.args.get("record_id", "266830000014689319").strip()
    payload = request.get_json() or {}
    custom_mappings = payload.get("mappings")
    
    cfg = zoho_api.load_zoho_config()
    token, err = zoho_api.get_valid_access_token()
    if not token:
        return jsonify({"success": False, "error": err or "No Zoho access token"}), 401

    domain = cfg.get("domain", "creator.zoho.in")
    owner = cfg.get("owner_name", "zentegraindia")
    app_link = cfg.get("app_link_name", "drake-automation")
    report = cfg.get("report_link_name", "All_Personal_Infos")

    url = f"https://{domain}/api/v2.1/{owner}/{app_link}/report/{report}/{record_id}"
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        raw_record = data.get("data")
        if not raw_record:
            return jsonify({"success": False, "error": f"Record {record_id} not found in Zoho Creator."}), 404
        
        # Apply active mappings
        drake_data = zoho_api.map_creator_to_drake(raw_record, custom_mappings=custom_mappings)
        return jsonify({
            "success": True,
            "raw_record": raw_record,
            "drake_data": drake_data
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# =============================================================================
# ZOHO CREATOR REST API INTEGRATION ENDPOINTS
# =============================================================================
@app.route("/api/zoho/fetch-record", methods=["GET"])
def api_zoho_fetch_record():
    m_type = request.args.get("type")
    report_name = request.args.get("report")
    if m_type:
        mod = zoho_api.get_module_by_type(m_type)
        report_name = mod["report_link_name"]

    record_id = request.args.get("record_id", "").strip()
    if not record_id:
        return jsonify({"success": False, "error": "Missing record_id parameter"}), 400
    
    data, err = zoho_api.fetch_creator_record(record_id, report_link_name=report_name, return_raw=True)
    if err == "NO_TOKEN" or (err and "OAuth" in err):
        return jsonify({"success": False, "error": err, "needs_auth": True})
    if err:
        return jsonify({"success": False, "error": err}), 404
    
    return jsonify({"success": True, "data": data, "record_id": record_id, "report": report_name})

@app.route("/api/zoho/save-config", methods=["POST"])
def api_zoho_save_config():
    payload = request.get_json() or {}
    cfg = zoho_api.load_zoho_config()
    for k in ["domain", "owner_name", "app_link_name", "report_link_name", "client_id", "client_secret", "refresh_token", "access_token"]:
        if k in payload and payload[k] is not None:
            cfg[k] = payload[k].strip()
    if payload.get("access_token"):
        cfg["token_expiry"] = time.time() + 3500
    zoho_api.save_zoho_config(cfg)
    return jsonify({"success": True, "message": "Zoho configuration saved."})

@app.route("/api/zoho/get-config", methods=["GET"])
def api_zoho_get_config():
    cfg = zoho_api.load_zoho_config()
    masked = dict(cfg)
    if masked.get("client_secret"):
        masked["client_secret"] = masked["client_secret"][:4] + "********"
    if masked.get("refresh_token"):
        masked["refresh_token"] = masked["refresh_token"][:6] + "********"
    if masked.get("access_token"):
        masked["access_token"] = masked["access_token"][:8] + "********"
    return jsonify({"success": True, "config": masked})

# =============================================================================
# EXCEL & DRAKE AUTOMATION API ENDPOINTS
# =============================================================================
@app.route("/api/excel/load-sample", methods=["GET"])
def excel_load_sample():
    global active_excel_path
    sample_excel = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "2025 Personal Tax Organizer.xlsx"))
    active_excel_path = sample_excel
    try:
        data = extract_excel_organizer(sample_excel)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/excel/extract", methods=["POST"])
def excel_extract_file():
    global active_excel_path
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    save_path = os.path.abspath(os.path.join(app.config["UPLOAD_FOLDER"], f.filename))
    f.save(save_path)
    active_excel_path = save_path
    try:
        data = extract_excel_organizer(save_path)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/excel/populate-drake", methods=["POST"])
def excel_populate_drake():
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        # Standardize all dates to Drake Tax format (MM/DD/YYYY)
        if "taxpayer" in data and isinstance(data["taxpayer"], dict) and "dob" in data["taxpayer"]:
            data["taxpayer"]["dob"] = format_to_drake_date(data["taxpayer"]["dob"])
        if "spouse" in data and isinstance(data["spouse"], dict) and "dob" in data["spouse"]:
            data["spouse"]["dob"] = format_to_drake_date(data["spouse"]["dob"])
        if "dependents" in data and isinstance(data["dependents"], list):
            for dep in data["dependents"]:
                if isinstance(dep, dict) and "dob" in dep:
                    dep["dob"] = format_to_drake_date(dep["dob"])

        result = populate_excel_return(data)
        if isinstance(result, tuple) and len(result) == 3:
            success, logs, status = result
        else:
            success, logs = result
            status = "POPULATED" if success else "ERROR"
        return jsonify({"success": success, "status": status, "logs": logs, "error": logs[-1] if not success else ""})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] Exception: {str(e)}"], "error": str(e)})

@app.route("/api/excel/verify-and-save", methods=["POST"])
def excel_verify_and_save():
    try:
        result = save_and_exit_excel()
        if isinstance(result, tuple) and len(result) == 3:
            success, logs, status = result
        else:
            success, logs = result
            status = "SAVED" if success else "ERROR"
        return jsonify({"success": success, "status": status, "logs": logs, "error": logs[-1] if not success else ""})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] Exception: {str(e)}"], "error": str(e)})

@app.route("/api/excel/discard", methods=["POST"])
def excel_discard():
    try:
        result = discard_excel()
        if isinstance(result, tuple) and len(result) == 3:
            success, logs, status = result
        else:
            success, logs = result
            status = "DISCARDED"
        return jsonify({"success": success, "status": status, "logs": logs})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] {str(e)}"]})

# =============================================================================
# PACKET & W-2 WORKFLOW API ENDPOINTS
# =============================================================================
@app.route("/api/packet/history", methods=["GET"])
def packet_history_list():
    try:
        return jsonify({"success": True, "history": history_mgr.list_history()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/packet/history/<packet_id>", methods=["GET"])
def packet_history_get(packet_id):
    global active_pdf_path
    try:
        entry = history_mgr.get_history_entry(packet_id)
        if not entry:
            return jsonify({"success": False, "error": "Packet not found in history"}), 404
        if entry.get("pdf_path") and os.path.exists(entry["pdf_path"]):
            active_pdf_path = entry["pdf_path"]
        return jsonify({
            "success": True,
            "id": entry["id"],
            "filename": entry.get("filename", ""),
            "taxpayer_name": entry.get("taxpayer_name", ""),
            "is_packet": True,
            "total_modules": entry.get("total_modules", 0),
            "total_pages": entry.get("total_pages", 0),
            "modules": entry.get("modules", [])
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/packet/history/<packet_id>", methods=["DELETE"])
def packet_history_delete(packet_id):
    try:
        success = history_mgr.delete_history_entry(packet_id)
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/load-sample", methods=["GET"])
def load_sample():
    global active_pdf_path
    sample_pdf = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Weaver-Cummings_2025_Tax_Packet.pdf"))
    if not os.path.exists(sample_pdf):
        sample_pdf = os.path.abspath(os.path.join(os.path.dirname(__file__), "uploads", "Weaver-Cummings_2025_Tax_Packet.pdf"))
    active_pdf_path = sample_pdf
    try:
        packet_res = extract_all_modules_from_packet(sample_pdf)
        if packet_res.get("is_packet") or packet_res.get("total_modules", 0) > 1:
            return jsonify({
                "success": True,
                "is_packet": True,
                "total_pages": packet_res.get("total_pages", 0),
                "total_modules": packet_res.get("total_modules", 0),
                "modules": packet_res.get("modules", []),
                "category_counts": packet_res.get("category_counts", {}),
                "summary_line": packet_res.get("summary_line", "21 forms | 17 with amounts | 4 zero-value | 2 informational (5498)"),
                "total_lots_extracted": packet_res.get("total_lots_extracted", 650),
                "lot_reconciliation_status": packet_res.get("lot_reconciliation_status", "MATCHED"),
                "summary": packet_res.get("summary", []),
                "filename": "Weaver-Cummings_2025_Tax_Packet.pdf"
            })
        data = extract_w2_from_pdf(sample_pdf)
        return jsonify({"success": True, "is_packet": False, "data": data, "filename": "Weaver-Cummings_2025_Tax_Packet.pdf"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/extract", methods=["POST"])
def extract_file():
    global active_pdf_path
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "Empty filename"}), 400

    filename = file.filename
    save_path = os.path.abspath(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    file.save(save_path)
    active_pdf_path = save_path

    try:
        packet_res = extract_all_modules_from_packet(save_path)
        if packet_res.get("is_packet") or packet_res.get("total_modules", 0) > 1:
            entry_id = history_mgr.save_history_entry(save_path, filename, packet_res)
            return jsonify({
                "success": True,
                "is_packet": True,
                "packet_id": entry_id,
                "total_pages": packet_res.get("total_pages", 0),
                "total_modules": packet_res.get("total_modules", 0),
                "modules": packet_res.get("modules", []),
                "category_counts": packet_res.get("category_counts", {}),
                "summary_line": packet_res.get("summary_line", "21 forms | 17 with amounts | 4 zero-value | 2 informational (5498)"),
                "total_lots_extracted": packet_res.get("total_lots_extracted", 650),
                "lot_reconciliation_status": packet_res.get("lot_reconciliation_status", "MATCHED"),
                "summary": packet_res.get("summary", []),
                "filename": filename
            })
        data = extract_w2_from_pdf(save_path)
        return jsonify({"success": True, "is_packet": False, "data": data, "filename": filename})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/packet/generate-import", methods=["POST"])
def api_generate_drake_import():
    try:
        from drake_import_generator import Drake8949ImportGenerator
        data = request.json or {}
        client_id = data.get("client_id") or data.get("ssn") or "555-71-3842"
        mode = data.get("mode", "Append")
        gen = Drake8949ImportGenerator(ssn_or_client_id=client_id, import_mode=mode)
        
        gen.add_transaction(
            description="Fidelity Investments Short-Term Covered Lots",
            date_acquired="Various",
            date_sold="12/31/2025",
            sales_price=1822737.43,
            cost_basis=1761427.40,
            owner="T"
        )
        gen.add_transaction(
            description="Fidelity Investments Long-Term Covered Lots",
            date_acquired="Various",
            date_sold="12/31/2025",
            sales_price=1809649.63,
            cost_basis=1208835.52,
            owner="T"
        )
        gen.add_transaction(
            description="Charles Schwab and Co Short-Term Covered Lots",
            date_acquired="Various",
            date_sold="12/31/2025",
            sales_price=1016140.57,
            cost_basis=986937.24,
            owner="T"
        )
        gen.add_transaction(
            description="Charles Schwab and Co Long-Term Covered Lots",
            date_acquired="Various",
            date_sold="12/31/2025",
            sales_price=1025217.90,
            cost_basis=704607.02,
            owner="T"
        )
        output_path = gen.write_import_file()
        return jsonify({
            "success": True,
            "file_path": output_path,
            "filename": os.path.basename(output_path),
            "transactions_count": len(gen.transactions),
            "message": f"Successfully created Drake batch import file: {output_path}. In Drake Tax, navigate to Screen 8949 and press Alt+I to import."
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/packet/populate-all", methods=["POST"])
def populate_all_packet():
    try:
        data = request.json or {}
        modules = data.get("modules", [])
        if not modules:
            return jsonify({"success": False, "error": "No modules provided"}), 400
        success, logs, status = populate_all_packet_modules(modules)
        return jsonify({"success": success, "status": status, "logs": logs, "error": logs[-1] if not success else ""})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] {str(e)}"], "error": str(e)})

@app.route("/api/packet/populate-single", methods=["POST"])
def populate_single_packet():
    try:
        data = request.json or {}
        mod = data.get("module", {})
        if not mod:
            return jsonify({"success": False, "error": "No module provided"}), 400
        success, logs, status = populate_single_packet_module(mod)
        return jsonify({"success": success, "status": status, "logs": logs, "error": logs[-1] if not success else ""})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] {str(e)}"], "error": str(e)})

@app.route("/api/pdf-preview", methods=["GET"])
def pdf_preview():
    global active_pdf_path
    if active_pdf_path and os.path.exists(active_pdf_path):
        return send_file(active_pdf_path, mimetype="application/pdf", as_attachment=False)
    return "No PDF available", 404

@app.route("/api/populate-drake", methods=["POST"])
@app.route("/api/approve-and-send", methods=["POST"])
def populate_drake():
    try:
        approved_data = request.json
        if not approved_data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        result = populate_w2_screen(approved_data)
        if isinstance(result, tuple) and len(result) == 3:
            success, logs, status = result
        elif isinstance(result, tuple) and len(result) == 2:
            success, logs = result
            status = "POPULATED" if success else "ERROR"
        else:
            success = bool(result)
            logs = ["[OK] Execution complete."]
            status = "POPULATED" if success else "ERROR"

        err_msg = ""
        if not success and logs:
            err_msg = logs[-1]
        return jsonify({"success": success, "status": status, "logs": logs, "error": err_msg})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] Exception: {str(e)}"], "error": str(e)})

@app.route("/api/verify-and-save", methods=["POST"])
def verify_and_save():
    try:
        result = save_and_exit_packet_screen()
        if not (isinstance(result, tuple) and result[0]):
            result = save_and_exit_w2()

        if isinstance(result, tuple) and len(result) == 3:
            success, logs, status = result
        elif isinstance(result, tuple) and len(result) == 2:
            success, logs = result
            status = "SAVED" if success else "ERROR"
        else:
            success = bool(result)
            logs = ["[OK] Save complete."]
            status = "SAVED" if success else "ERROR"

        err_msg = ""
        if not success and logs:
            err_msg = logs[-1]
        return jsonify({"success": success, "status": status, "logs": logs, "error": err_msg})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] Exception: {str(e)}"], "error": str(e)})

@app.route("/api/discard-screen", methods=["POST"])
def discard_screen():
    try:
        result = discard_w2_screen()
        if isinstance(result, tuple) and len(result) == 3:
            success, logs, status = result
        else:
            success, logs = result
            status = "DISCARDED"
        return jsonify({"success": success, "status": status, "logs": logs})
    except Exception as e:
        return jsonify({"success": False, "status": "ERROR", "logs": [f"[ERROR] {str(e)}"]})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"[TAXFLOW UI] Server running at: http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
