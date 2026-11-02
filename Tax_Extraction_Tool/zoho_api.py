import os
import json
import time
import requests
from dotenv import load_dotenv
from date_utils import format_to_drake_date

# Load .env or env from current directory or root directory
for _name in [".env", "env"]:
    load_dotenv(os.path.join(os.path.dirname(__file__), _name))
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", _name))

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "zoho_config.json")
MAPPING_FILE_PATH = os.path.join(os.path.dirname(__file__), "field_mappings.json")

DEFAULT_CONFIG = {
    "domain": "creator.zoho.in",
    "accounts_domain": "accounts.zoho.in",
    "owner_name": "zentegraindia",
    "app_link_name": "drake-automation",
    "report_link_name": "All_Personal_Infos",
    "dependents_report_link_name": "All_Dependents",
    "client_id": "",
    "client_secret": "",
    "refresh_token": "",
    "access_token": "",
    "token_expiry": 0
}

def load_zoho_config():
    # Reload .env or env with override=True on every call to pick up any changes immediately
    for _name in [".env", "env"]:
        load_dotenv(os.path.join(os.path.dirname(__file__), _name), override=True)
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", _name), override=True)

    merged = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged.update(data)
        except Exception:
            pass

    # Environment variable overrides from .env
    env_mappings = {
        "client_id": "ZOHO_CLIENT_ID",
        "client_secret": "ZOHO_CLIENT_SECRET",
        "refresh_token": "ZOHO_REFRESH_TOKEN",
        "access_token": "ZOHO_ACCESS_TOKEN",
        "domain": "ZOHO_DOMAIN",
        "accounts_domain": "ZOHO_ACCOUNTS_DOMAIN",
        "owner_name": "ZOHO_OWNER_NAME",
        "app_link_name": "ZOHO_APP_NAME",
        "report_link_name": "ZOHO_REPORT_NAME"
    }
    for cfg_key, env_var in env_mappings.items():
        val = os.getenv(env_var)
        if val and val.strip():
            merged[cfg_key] = val.strip()

    return merged

def save_zoho_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        print(f"[ZOHO API] Error saving config: {e}")
        return False

def get_valid_access_token():
    cfg = load_zoho_config()
    now = time.time()
    
    # 1. Check if existing access token is still fresh (valid for at least 60 more seconds)
    if cfg.get("access_token") and cfg.get("token_expiry", 0) > now + 60:
        return cfg["access_token"], None
    
    # 2. Try refreshing using refresh_token if available
    refresh_token = cfg.get("refresh_token")
    client_id = cfg.get("client_id")
    client_secret = cfg.get("client_secret")
    accounts_domain = cfg.get("accounts_domain", "accounts.zoho.in")

    if refresh_token and client_id and client_secret:
        token_url = f"https://{accounts_domain}/oauth/v2/token"
        params = {
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token"
        }
        try:
            resp = requests.post(token_url, data=params, timeout=15)
            data = resp.json()
            if "access_token" in data:
                cfg["access_token"] = data["access_token"]
                expires_in = data.get("expires_in", 3600)
                cfg["token_expiry"] = now + expires_in
                save_zoho_config(cfg)
                return cfg["access_token"], None
            else:
                err = data.get("error", "Failed to refresh token")
                return None, f"OAuth Refresh Error: {err}"
        except Exception as e:
            return None, f"OAuth Network Error: {str(e)}"
    
    # 3. If direct access_token is set manually without expiry, return it
    if cfg.get("access_token"):
        return cfg["access_token"], None
        
    return None, "NO_TOKEN"

def fetch_creator_record(record_id, report_link_name=None, return_raw=False):
    """
    Fetches record from Zoho Creator REST API v2.1:
    GET https://creator.zoho.in/api/v2.1/{owner}/{app}/report/{report}/{id}
    """
    cfg = load_zoho_config()
    token, err = get_valid_access_token()
    if not token:
        return None, err or "No valid access token available."

    domain = cfg.get("domain", "creator.zoho.in")
    owner = cfg.get("owner_name", "zentegraindia")
    app = cfg.get("app_link_name", "drake-automation")
    report = report_link_name or cfg.get("report_link_name", "All_Personal_Infos")

    url = f"https://{domain}/api/v2.1/{owner}/{app}/report/{report}/{record_id}"
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=20)
        
        # If 401 Unauthorized, token might be expired
        if resp.status_code == 401:
            cfg["token_expiry"] = 0
            save_zoho_config(cfg)
            # Retry refresh once
            token, retry_err = get_valid_access_token()
            if token:
                headers["Authorization"] = f"Zoho-oauthtoken {token}"
                resp = requests.get(url, headers=headers, timeout=20)

        data = resp.json()
        if resp.status_code != 200 or data.get("code") not in (3000, 0, None):
            msg = data.get("message") or data.get("error") or str(data)
            return None, f"Zoho Creator API Error ({resp.status_code}): {msg}"
        
        raw_record = data.get("data")
        if not raw_record:
            return None, f"No record data found for ID: {record_id} in {report}"

        if return_raw:
            return raw_record, None

        # Map Zoho Creator fields to Drake Automation schema
        formatted_data = map_creator_to_drake(raw_record)
        return formatted_data, None

    except Exception as e:
        return None, f"Request to Zoho Creator failed: {str(e)}"

def update_creator_record_status(record_id, report_link_name, status="Finished", message=""):
    """
    Updates Drake_Status and Drake_Message on the Zoho Creator record via REST API v2.1.
    """
    cfg = load_zoho_config()
    token, err = get_valid_access_token()
    if not token:
        return False, err or "No valid access token available."

    domain = cfg.get("domain", "creator.zoho.in")
    owner = cfg.get("owner_name", "zentegraindia")
    app = cfg.get("app_link_name", "drake-automation")
    report = report_link_name or cfg.get("report_link_name", "All_Personal_Infos")

    url = f"https://{domain}/api/v2.1/{owner}/{app}/report/{report}/{record_id}"
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "data": {
            "Drake_Status": status,
            "Drake_Message": str(message)[:250] if message else ""
        }
    }

    try:
        resp = requests.patch(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 401:
            cfg["token_expiry"] = 0
            save_zoho_config(cfg)
            token, _ = get_valid_access_token()
            if token:
                headers["Authorization"] = f"Zoho-oauthtoken {token}"
                resp = requests.patch(url, json=payload, headers=headers, timeout=15)

        data = resp.json()
        if resp.status_code == 200 and data.get("code") in (3000, 0, None):
            return True, None
        return False, data.get("message") or str(data)
    except Exception as e:
        return False, str(e)

def fetch_creator_forms():
    """
    Fetches all available forms in the Zoho Creator application using the Meta API:
    GET https://creator.zoho.in/api/v2.1/{owner}/{app}/forms
    """
    cfg = load_zoho_config()
    token, err = get_valid_access_token()
    if not token:
        return None, err or "No valid access token available."

    domain = cfg.get("domain", "creator.zoho.in")
    owner = cfg.get("owner_name", "zentegraindia")
    app = cfg.get("app_link_name", "drake-automation")

    url = f"https://{domain}/api/v2.1/{owner}/{app}/forms"
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 401:
            cfg["token_expiry"] = 0
            save_zoho_config(cfg)
            token, _ = get_valid_access_token()
            if token:
                headers["Authorization"] = f"Zoho-oauthtoken {token}"
                resp = requests.get(url, headers=headers, timeout=15)

        data = resp.json()
        if resp.status_code != 200 or data.get("code") not in (3000, 0, None):
            msg = data.get("message") or data.get("error") or str(data)
            return None, f"Zoho Meta API Error ({resp.status_code}): {msg}"

        forms = data.get("forms", [])
        return forms, None
    except Exception as e:
        return None, f"Failed to fetch forms: {str(e)}"

def fetch_creator_form_fields(form_link_name):
    """
    Fetches all fields for a specific form using Zoho Creator Meta/Fields API:
    GET https://creator.zoho.in/api/v2.1/{owner}/{app}/form/{form_link_name}/fields
    """
    cfg = load_zoho_config()
    token, err = get_valid_access_token()
    if not token:
        return None, err or "No valid access token available."

    domain = cfg.get("domain", "creator.zoho.in")
    owner = cfg.get("owner_name", "zentegraindia")
    app = cfg.get("app_link_name", "drake-automation")

    url = f"https://{domain}/api/v2.1/{owner}/{app}/form/{form_link_name}/fields"
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 401:
            cfg["token_expiry"] = 0
            save_zoho_config(cfg)
            token, _ = get_valid_access_token()
            if token:
                headers["Authorization"] = f"Zoho-oauthtoken {token}"
                resp = requests.get(url, headers=headers, timeout=15)

        data = resp.json()
        if resp.status_code != 200 or data.get("code") not in (3000, 0, None):
            msg = data.get("message") or data.get("error") or str(data)
            return None, f"Zoho Fields API Error ({resp.status_code}): {msg}"

        fields = data.get("fields") or data.get("data") or []
        
        # Flatten and enrich subforms for easy mapping
        flattened_fields = []
        for f in fields:
            f_copy = dict(f)
            f_copy["form_link_name"] = form_link_name
            flattened_fields.append(f_copy)
            
            # If type 21 (SubForm), also include each subform field with combined link_name
            if f.get("type") == 21 and isinstance(f.get("fields"), list):
                for subf in f["fields"]:
                    sub_copy = dict(subf)
                    sub_copy["parent_subform"] = f.get("link_name")
                    sub_copy["parent_display_name"] = f.get("display_name")
                    sub_copy["form_link_name"] = form_link_name
                    sub_copy["full_link_name"] = f"{f.get('link_name')}.{subf.get('link_name')}"
                    sub_copy["display_label"] = f"{f.get('display_name')} → {subf.get('display_name')}"
                    flattened_fields.append(sub_copy)

        return {
            "form": form_link_name,
            "raw_fields": fields,
            "flattened_fields": flattened_fields
        }, None
    except Exception as e:
        return None, f"Failed to fetch fields for {form_link_name}: {str(e)}"

# =============================================================================
# DYNAMIC MODULE REGISTRY (Supports type=personal, type=dependent, etc.)
# =============================================================================
MODULE_DEFINITIONS = {
    "personal": {
        "type": "personal",
        "aliases": ["personal", "personal_info", "personal-info", "demographics"],
        "display_name": "Personal Information",
        "form_link_name": "Personal_Info",
        "report_link_name": "All_Personal_Infos",
        "drake_screen": "Screen 1 (Demographics & Address)",
        "screen_code": "1"
    },
    "dependent": {
        "type": "dependent",
        "aliases": ["dependent", "dependents", "dep", "screen2"],
        "display_name": "Dependents",
        "form_link_name": "Dependents",
        "report_link_name": "All_Dependents",
        "drake_screen": "Screen 2 (Dependents)",
        "screen_code": "2"
    },
    "additional_information": {
        "type": "additional_information",
        "aliases": ["additional_information", "additional", "additional-information"],
        "display_name": "Additional Information",
        "form_link_name": "Additional_Information",
        "report_link_name": "All_Additional_Information",
        "drake_screen": "Screen 1 (Residency & Presence)",
        "screen_code": "1"
    },
    "checklist": {
        "type": "checklist",
        "aliases": ["checklist", "checklist1", "upload", "all_checklist"],
        "display_name": "Checklist & Documents",
        "form_link_name": "Checklist",
        "report_link_name": "All_Checklist",
        "drake_screen": "Screen Checklist (W-2 & 1099-INT)",
        "screen_code": "W2"
    },
    "estimated_tax": {
        "type": "estimated_tax",
        "aliases": ["estimated_tax", "estimated-tax", "tax", "taxes"],
        "display_name": "Estimated Tax",
        "form_link_name": "Estimated_Tax",
        "report_link_name": "All_Taxes",
        "drake_screen": "Screen ES (Estimated Taxes)",
        "screen_code": "ES"
    }
}

def get_module_by_type(module_type_or_name):
    """
    Dynamically identifies the module based on type URL parameter, form name, or report name.
    """
    if not module_type_or_name:
        return MODULE_DEFINITIONS["personal"]
    val = str(module_type_or_name).strip().lower().replace("-", "_")
    for key, mod in MODULE_DEFINITIONS.items():
        if val == key or val in mod.get("aliases", []):
            return mod
        if val == mod["form_link_name"].lower() or val == mod["report_link_name"].lower():
            return mod
    return MODULE_DEFINITIONS["personal"]

# Drake Target Fields Schemas
DRAKE_PERSONAL_FIELDS = [
    # Taxpayer
    {"id": "taxpayer.filing_status", "label": "Filing Status", "section": "Primary Taxpayer", "screen": "Screen 1", "type": "dropdown", "description": "1=Single, 2=MFJ, 3=MFS, 4=HOH, 5=QSS", "required": True},
    {"id": "taxpayer.first_name", "label": "First Name", "section": "Primary Taxpayer", "screen": "Screen 1", "type": "text", "description": "Taxpayer Legal First Name", "required": True},
    {"id": "taxpayer.mi", "label": "M.I.", "section": "Primary Taxpayer", "screen": "Screen 1", "type": "text", "description": "Middle Initial", "required": False},
    {"id": "taxpayer.last_name", "label": "Last Name", "section": "Primary Taxpayer", "screen": "Screen 1", "type": "text", "description": "Taxpayer Legal Last Name", "required": True},
    {"id": "taxpayer.ssn", "label": "SSN / ITIN", "section": "Primary Taxpayer", "screen": "Screen 1", "type": "ssn", "description": "9-digit SSN or ITIN", "required": True},
    {"id": "taxpayer.dob", "label": "Date of Birth (DOB)", "section": "Primary Taxpayer", "screen": "Screen 1", "type": "date", "description": "MM-DD-YYYY", "required": True},
    {"id": "taxpayer.occupation", "label": "Occupation", "section": "Primary Taxpayer", "screen": "Screen 1", "type": "text", "description": "Primary job or occupation", "required": False},
    {"id": "taxpayer.phone", "label": "Daytime / Main Phone", "section": "Primary Taxpayer", "screen": "Screen 1", "type": "phone", "description": "Primary contact number", "required": False},
    {"id": "taxpayer.other_phone", "label": "Cell / Other Phone", "section": "Primary Taxpayer", "screen": "Screen 1", "type": "phone", "description": "Mobile or secondary phone", "required": False},
    {"id": "taxpayer.email", "label": "Email Address", "section": "Primary Taxpayer", "screen": "Screen 1", "type": "email", "description": "Client email for e-filing/contact", "required": False},

    # Spouse
    {"id": "spouse.first_name", "label": "Spouse First Name", "section": "Spouse Demographics", "screen": "Screen 1", "type": "text", "description": "Spouse Legal First Name", "required": False},
    {"id": "spouse.mi", "label": "Spouse M.I.", "section": "Spouse Demographics", "screen": "Screen 1", "type": "text", "description": "Spouse Middle Initial", "required": False},
    {"id": "spouse.last_name", "label": "Spouse Last Name", "section": "Spouse Demographics", "screen": "Screen 1", "type": "text", "description": "Spouse Legal Last Name", "required": False},
    {"id": "spouse.ssn", "label": "Spouse SSN / ITIN", "section": "Spouse Demographics", "screen": "Screen 1", "type": "ssn", "description": "Spouse 9-digit SSN or ITIN", "required": False},
    {"id": "spouse.dob", "label": "Spouse Date of Birth", "section": "Spouse Demographics", "screen": "Screen 1", "type": "date", "description": "Spouse DOB (MM-DD-YYYY)", "required": False},
    {"id": "spouse.occupation", "label": "Spouse Occupation", "section": "Spouse Demographics", "screen": "Screen 1", "type": "text", "description": "Spouse occupation", "required": False},
    {"id": "spouse.phone", "label": "Spouse Main Phone", "section": "Spouse Demographics", "screen": "Screen 1", "type": "phone", "description": "Spouse primary phone", "required": False},
    {"id": "spouse.other_phone", "label": "Spouse Cell Phone", "section": "Spouse Demographics", "screen": "Screen 1", "type": "phone", "description": "Spouse cell phone", "required": False},
    {"id": "spouse.email", "label": "Spouse Email Address", "section": "Spouse Demographics", "screen": "Screen 1", "type": "email", "description": "Spouse email", "required": False},

    # Address
    {"id": "address.street", "label": "Street Address", "section": "Mailing Address", "screen": "Screen 1", "type": "text", "description": "Street line 1", "required": True},
    {"id": "address.apt", "label": "Apt / Suite Number", "section": "Mailing Address", "screen": "Screen 1", "type": "text", "description": "Apartment, Unit, or Suite", "required": False},
    {"id": "address.city", "label": "City", "section": "Mailing Address", "screen": "Screen 1", "type": "text", "description": "City name", "required": True},
    {"id": "address.state", "label": "State Code", "section": "Mailing Address", "screen": "Screen 1", "type": "text", "description": "2-letter US State abbreviation", "required": True},
    {"id": "address.zip", "label": "ZIP Code", "section": "Mailing Address", "screen": "Screen 1", "type": "text", "description": "5 or 9-digit postal code", "required": True},
    {"id": "address.county", "label": "County", "section": "Mailing Address", "screen": "Screen 1", "type": "text", "description": "County of residence", "required": False},

    # Banking
    {"id": "bank.bank_name", "label": "Bank Name", "section": "Direct Deposit & Banking", "screen": "Screen DD", "type": "text", "description": "Name of banking institution", "required": False},
    {"id": "bank.account_type", "label": "Account Type", "section": "Direct Deposit & Banking", "screen": "Screen DD", "type": "dropdown", "description": "Checking or Savings", "required": False},
    {"id": "bank.routing", "label": "Routing Number", "section": "Direct Deposit & Banking", "screen": "Screen DD", "type": "text", "description": "9-digit ABA routing transit number", "required": False},
    {"id": "bank.account_number", "label": "Account Number", "section": "Direct Deposit & Banking", "screen": "Screen DD", "type": "text", "description": "Deposit account number", "required": False},

    # Residency
    {"id": "residency.residential_status", "label": "Residential Status", "section": "Residential Status & Presence", "screen": "Screen 1", "type": "text", "description": "US Citizen, Resident Alien, Non-Resident", "required": False},
    {"id": "residency.days_2025", "label": "Days in US (2025)", "section": "Residential Status & Presence", "screen": "Screen 1", "type": "number", "description": "Physical presence days in 2025", "required": False},
    {"id": "residency.days_2024", "label": "Days in US (2024)", "section": "Residential Status & Presence", "screen": "Screen 1", "type": "number", "description": "Physical presence days in 2024", "required": False},
    {"id": "residency.days_2023", "label": "Days in US (2023)", "section": "Residential Status & Presence", "screen": "Screen 1", "type": "number", "description": "Physical presence days in 2023", "required": False}
]

DRAKE_DEPENDENT_FIELDS = [
    {"id": "dependent.first_name", "label": "First Name / Dependent Name", "section": "Dependent Identity", "screen": "Screen 2", "type": "text", "description": "Dependent Legal First Name or Full Name", "required": True},
    {"id": "dependent.mi", "label": "M.I.", "section": "Dependent Identity", "screen": "Screen 2", "type": "text", "description": "Dependent Middle Initial", "required": False},
    {"id": "dependent.last_name", "label": "Last Name", "section": "Dependent Identity", "screen": "Screen 2", "type": "text", "description": "Dependent Legal Last Name (Auto-split if Full Name)", "required": False},
    {"id": "dependent.ssn", "label": "SSN / ITIN", "section": "Dependent Identity", "screen": "Screen 2", "type": "ssn", "description": "9-digit SSN or ITIN", "required": True},
    {"id": "dependent.dob", "label": "Date of Birth (DOB)", "section": "Dependent Demographics", "screen": "Screen 2", "type": "date", "description": "MM-DD-YYYY", "required": True},
    {"id": "dependent.relationship", "label": "Relationship", "section": "Dependent Demographics", "screen": "Screen 2", "type": "dropdown", "description": "Son, Daughter, Child, Parent, Other", "required": True},
    {"id": "dependent.months_in_home", "label": "Months in Home", "section": "Dependent Residency", "screen": "Screen 2", "type": "number", "description": "Months lived in home (1-12)", "required": True},
    {"id": "notes_to_preparer", "label": "Notes to Preparer", "section": "Preparer Notes", "screen": "Screen 2", "type": "text", "description": "Filer notes or instructions", "required": False}
]

def get_drake_fields_schema(module_type="personal"):
    """
    Returns the comprehensive Drake Tax 2025 target fields schema for the requested module.
    """
    mod = get_module_by_type(module_type)
    if mod["type"] == "dependent":
        return list(DRAKE_DEPENDENT_FIELDS)
    return list(DRAKE_PERSONAL_FIELDS)

DEFAULT_FIELD_MAPPINGS = {
    "Filing_Status": "taxpayer.filing_status",
    "Taxpayer_First_Name": "taxpayer.first_name",
    "Taxpayer_Middle_Name": "taxpayer.mi",
    "Taxpayer_Last_Name": "taxpayer.last_name",
    "Taxpayer_SSN": "taxpayer.ssn",
    "Taxpayer_DOB": "taxpayer.dob",
    "Taxpayer_Occupation": "taxpayer.occupation",
    "Taxpayer_Main_Phone": "taxpayer.phone",
    "Taxpayer_Other_Phone": "taxpayer.other_phone",
    "Taxpayer_Email": "taxpayer.email",
    "Spouse_First_Name": "spouse.first_name",
    "Spouse_Middle_Name": "spouse.mi",
    "Spouse_Last_Name": "spouse.last_name",
    "Spouse_SSN_ITIN": "spouse.ssn",
    "Spouse_DOB": "spouse.dob",
    "Spouse_Occupation": "spouse.occupation",
    "Spouse_Main_Phone": "spouse.phone",
    "Spouse_Other_Phone": "spouse.other_phone",
    "Spouse_Email": "spouse.email",
    "Mailing_Address": "address.street",
    "City": "address.city",
    "State_Field": "address.state",
    "Zip": "address.zip",
    "Bank_Name": "bank.bank_name",
    "Account_Type": "bank.account_type",
    "Routing_Number": "bank.routing",
    "Account_Number": "bank.account_number",
    "Residential_Status": "residency.residential_status",
    "Days_Present_in_US_2025": "residency.days_2025",
    "Days_Present_in_US_2024": "residency.days_2024",
    "Days_Present_in_US_2023": "residency.days_2023"
}

DEFAULT_DEPENDENT_MAPPINGS = {
    # Prefixed full link names (as returned by Zoho subform meta)
    "Dependents_Information.Dependents_Name": "dependent.first_name",
    "Dependents_Information.Social_Security_ITIN": "dependent.ssn",
    "Dependents_Information.Date_of_Birth": "dependent.dob",
    "Dependents_Information.Relationship": "dependent.relationship",
    "Dependents_Information.Mos_In_Home": "dependent.months_in_home",
    # Bare link names for direct field mapping
    "Dependents_Name": "dependent.first_name",
    "Social_Security_ITIN": "dependent.ssn",
    "Date_of_Birth": "dependent.dob",
    "Relationship": "dependent.relationship",
    "Mos_In_Home": "dependent.months_in_home",
    "Notes_to_Preparer": "notes_to_preparer"
}

def get_default_mappings(module_type="personal"):
    mod = get_module_by_type(module_type)
    if mod["type"] == "dependent":
        return dict(DEFAULT_DEPENDENT_MAPPINGS)
    return dict(DEFAULT_FIELD_MAPPINGS)

def get_saved_mappings(module_type="personal"):
    """
    Returns saved field mappings for the given module type, or default mappings if not customized.
    """
    mod = get_module_by_type(module_type)
    mtype = mod["type"]
    if os.path.exists(MAPPING_FILE_PATH):
        try:
            with open(MAPPING_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    if mtype in data and isinstance(data[mtype], dict):
                        return data[mtype]
                    if mtype == "personal":
                        # Check if legacy flat dictionary
                        if any(k.startswith("Taxpayer") or k == "Filing_Status" for k in data.keys()):
                            return data
        except Exception as e:
            print(f"[ZOHO MAPPINGS] Error loading mappings: {e}")
    return get_default_mappings(mtype)

def save_field_mappings(mappings, module_type="personal"):
    """
    Persists field mappings dictionary scoped to module_type.
    """
    mod = get_module_by_type(module_type)
    mtype = mod["type"]
    all_data = {}
    if os.path.exists(MAPPING_FILE_PATH):
        try:
            with open(MAPPING_FILE_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    all_data = loaded
        except Exception:
            pass

    all_data[mtype] = mappings
    # If personal, also preserve root keys for backwards compatibility
    if mtype == "personal":
        for k, v in mappings.items():
            all_data[k] = v

    try:
        with open(MAPPING_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(all_data, f, indent=2)
        return True, None
    except Exception as e:
        return False, f"Failed to save mappings: {str(e)}"

def extract_dependents_from_record(raw_record, custom_mappings=None):
    """
    Extracts a list of normalized dependent objects from a Zoho Creator record.
    Supports both subform array (Dependents_Information) and single-record formats,
    dynamically resolving fields via active or default mappings.
    """
    mappings = custom_mappings if custom_mappings is not None else get_saved_mappings("dependent")
    
    # Inverted lookup: drake_id -> [zoho_keys]
    drake_to_zoho = {}
    if isinstance(mappings, dict):
        for zk, did in mappings.items():
            base_zk = zk.split(".")[-1]
            drake_to_zoho.setdefault(did, []).extend([zk, base_zk])

    def get_dep_field(dep_dict, drake_id, *fallbacks):
        candidate_keys = drake_to_zoho.get(drake_id, []) + list(fallbacks)
        for k in candidate_keys:
            if k in dep_dict and dep_dict[k] not in (None, ""):
                v = dep_dict[k]
                if isinstance(v, dict):
                    return str(v.get("display_value") or v.get("value") or "").strip()
                return str(v).strip()
            # case insensitive fallback
            for rk in dep_dict:
                if rk.lower() == k.lower() and dep_dict[rk] not in (None, ""):
                    v = dep_dict[rk]
                    if isinstance(v, dict):
                        return str(v.get("display_value") or v.get("value") or "").strip()
                    return str(v).strip()
        return ""

    dependents = []
    deps_raw = raw_record.get("Dependents_Information") or raw_record.get("Dependents") or []
    if not deps_raw and any(k in raw_record for k in ["Dependents_Name", "Name", "Date_of_Birth"]):
        deps_raw = [raw_record]

    if isinstance(deps_raw, list):
        for dep in deps_raw:
            if isinstance(dep, dict):
                full_name = get_dep_field(dep, "dependent.first_name", "dependent.name", "Dependents_Name", "Name")
                parts = full_name.split() if full_name else []
                fn = parts[0] if parts else ""
                mi = parts[1][0] if len(parts) > 2 else ""
                ln = " ".join(parts[1:]) if len(parts) > 1 else ""
                dob_val = get_dep_field(dep, "dependent.dob", "Date_of_Birth", "DOB")

                rel = get_dep_field(dep, "dependent.relationship", "Relationship") or "Son"
                months = get_dep_field(dep, "dependent.months_in_home", "Mos_In_Home", "Months_In_Home") or "12"
                ssn = get_dep_field(dep, "dependent.ssn", "Social_Security_ITIN", "SSN")

                dependents.append({
                    "first_name": fn,
                    "mi": mi,
                    "last_name": ln,
                    "full_name": full_name,
                    "ssn": ssn,
                    "dob": format_to_drake_date(dob_val),
                    "relationship": rel.upper(),
                    "months": months
                })
    return dependents

def map_creator_to_drake(raw, custom_mappings=None):
    """
    Transforms Zoho Creator API record into Drake Demographics / Review dictionary
    using user-configured mappings with sensible fallbacks.
    """
    mappings = custom_mappings if custom_mappings is not None else get_saved_mappings()

    # Inverted lookup: drake_id -> zoho_key(s)
    drake_to_zoho = {}
    for z_key, d_id in mappings.items():
        if d_id not in drake_to_zoho:
            drake_to_zoho[d_id] = []
        drake_to_zoho[d_id].append(z_key)

    # Helper to retrieve field with case/alias fallbacks and Zoho object parsing
    def get_val_for_drake_id(drake_id, *fallback_keys, default=""):
        mapped_keys = drake_to_zoho.get(drake_id, [])
        all_candidate_keys = mapped_keys + list(fallback_keys)
        return get_val(*all_candidate_keys, default=default)

    def get_val(*keys, default=""):
        for k in keys:
            matched_key = None
            if k in raw:
                matched_key = k
            else:
                for rk in raw:
                    if rk.lower() == k.lower():
                        matched_key = rk
                        break

            if matched_key and raw[matched_key] is not None:
                v = raw[matched_key]
                if isinstance(v, dict):
                    for sub in ["phone_number", "display_value", "value", "international_number", "number"]:
                        if sub in v and v[sub]:
                            return str(v[sub]).strip()
                    vals = [str(x).strip() for x in v.values() if isinstance(x, (str, int, float)) and str(x).strip()]
                    if vals:
                        return " ".join(vals)
                if isinstance(v, (str, int, float)):
                    return str(v).strip()
        return default

    # Filing Status
    fs_raw = get_val_for_drake_id("taxpayer.filing_status", "Filing_Status", "FilingStatus", default="Single").lower()
    filing_status = "1"
    if "joint" in fs_raw or "mfj" in fs_raw or "married filing jointly" in fs_raw:
        filing_status = "2"
    elif "separat" in fs_raw or "mfs" in fs_raw:
        filing_status = "3"
    elif "head" in fs_raw or "hoh" in fs_raw:
        filing_status = "4"
    elif "surviv" in fs_raw or "widow" in fs_raw or "qss" in fs_raw:
        filing_status = "5"

    taxpayer = {
        "first_name": get_val_for_drake_id("taxpayer.first_name", "Taxpayer_First_Name", "First_Name", "Taxpayer_Name"),
        "mi": get_val_for_drake_id("taxpayer.mi", "Taxpayer_Middle_Name", "Middle_Name", "Middle_Initial", "Taxpayer_MI"),
        "last_name": get_val_for_drake_id("taxpayer.last_name", "Taxpayer_Last_Name", "Last_Name"),
        "ssn": get_val_for_drake_id("taxpayer.ssn", "Taxpayer_SSN", "Soc_Sec", "SSN"),
        "dob": format_to_drake_date(get_val_for_drake_id("taxpayer.dob", "Taxpayer_DOB", "DOB", "Date_of_Birth")),
        "occupation": get_val_for_drake_id("taxpayer.occupation", "Taxpayer_Occupation", "Occupation"),
        "phone": get_val_for_drake_id("taxpayer.phone", "Taxpayer_Main_Phone", "Main_Phone", "Taxpayer_Phone", "Phone", "Daytime_Phone"),
        "other_phone": get_val_for_drake_id("taxpayer.other_phone", "Taxpayer_Other_Phone", "Other_Phone", "Taxpayer_Cell_Phone", "Cell_Phone", "Other_Cell_Phone"),
        "email": get_val_for_drake_id("taxpayer.email", "Taxpayer_Email", "Email_Address", "Email")
    }

    spouse = {
        "first_name": get_val_for_drake_id("spouse.first_name", "Spouse_First_Name", "Spouse_First"),
        "mi": get_val_for_drake_id("spouse.mi", "Spouse_Middle_Name", "Spouse_MI"),
        "last_name": get_val_for_drake_id("spouse.last_name", "Spouse_Last_Name", "Spouse_Last"),
        "ssn": get_val_for_drake_id("spouse.ssn", "Spouse_SSN", "Spouse_Soc_ITIN", "Spouse_SSN_ITIN"),
        "dob": format_to_drake_date(get_val_for_drake_id("spouse.dob", "Spouse_DOB", "Spouse_Date_of_Birth")),
        "occupation": get_val_for_drake_id("spouse.occupation", "Spouse_Occupation"),
        "phone": get_val_for_drake_id("spouse.phone", "Spouse_Main_Phone", "Spouse_Main", "Spouse_Phone", "Spouse_Daytime_Phone"),
        "other_phone": get_val_for_drake_id("spouse.other_phone", "Spouse_Other_Phone", "Spouse_Other", "Spouse_Cell_Phone", "Spouse_Other_Cell_Phone"),
        "email": get_val_for_drake_id("spouse.email", "Spouse_Email", "Spouse_Email_Address")
    }

    address = {
        "street": get_val_for_drake_id("address.street", "Mailing_Address", "Address", "Street_Address"),
        "apt": get_val_for_drake_id("address.apt", "Apt", "Suite", default=""),
        "city": get_val_for_drake_id("address.city", "City"),
        "state": get_val_for_drake_id("address.state", "State", "State_Field"),
        "zip": get_val_for_drake_id("address.zip", "Zip", "Postal_Code", "Zip_Code"),
        "county": get_val_for_drake_id("address.county", "County", default="")
    }

    bank = {
        "bank_name": get_val_for_drake_id("bank.bank_name", "Bank_Name"),
        "account_type": get_val_for_drake_id("bank.account_type", "Account_Type", default=""),
        "routing": get_val_for_drake_id("bank.routing", "Routing_Number", "Routing"),
        "account_number": get_val_for_drake_id("bank.account_number", "Account_Number", "Account_Num")
    }

    # Extract dependents if present as subform or list
    dependents = []
    deps_raw = raw.get("Dependents_Information") or raw.get("Dependents") or []
    if isinstance(deps_raw, list):
        for dep in deps_raw:
            if isinstance(dep, dict):
                full_name = dep.get("Dependents_Name") or dep.get("Name") or ""
                parts = full_name.split() if full_name else []
                fn = parts[0] if parts else ""
                ln = " ".join(parts[1:]) if len(parts) > 1 else ""
                dob_val = str(dep.get("Date_of_Birth") or dep.get("DOB") or "")
                dependents.append({
                    "first_name": fn,
                    "last_name": ln,
                    "relationship": str(dep.get("Relationship") or "").upper(),
                    "ssn": str(dep.get("Social_Security_ITIN") or dep.get("SSN") or ""),
                    "dob": format_to_drake_date(dob_val),
                    "months": str(dep.get("Mos_In_Home") or dep.get("Months") or "")
                })

    residency = {
        "residential_status": get_val_for_drake_id("residency.residential_status", "Your_residential_Status", "Residential_Status", default=""),
        "days_2025": get_val_for_drake_id("residency.days_2025", "Days_Present_in_US_2025", default=""),
        "days_2024": get_val_for_drake_id("residency.days_2024", "Days_Present_in_US_2024", default=""),
        "days_2023": get_val_for_drake_id("residency.days_2023", "Days_Present_in_US_2023", default="")
    }

    return {
        "filing_status": filing_status,
        "taxpayer": taxpayer,
        "spouse": spouse,
        "address": address,
        "bank": bank,
        "dependents": dependents,
        "residency_questions": residency,
        "income_checklist": {},
        "raw_creator_record": raw
    }
