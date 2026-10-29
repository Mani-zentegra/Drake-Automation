import os
import json
import time
import requests
from dotenv import load_dotenv
from date_utils import format_to_drake_date

# Load .env from current directory or root directory
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "zoho_config.json")

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
    # Reload .env with override=True on every call to pick up any changes immediately
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

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

def fetch_creator_record(record_id):
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
    report = cfg.get("report_link_name", "All_Personal_Infos")

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
            return None, f"No record data found for ID: {record_id}"

        # Map Zoho Creator fields to Drake Automation schema
        formatted_data = map_creator_to_drake(raw_record)
        return formatted_data, None

    except Exception as e:
        return None, f"Request to Zoho Creator failed: {str(e)}"

def map_creator_to_drake(raw):
    """
    Transforms Zoho Creator API record into Drake Demographics / Review dictionary.
    """
    # Helper to retrieve field with case/alias fallbacks
    def get_val(*keys, default=""):
        for k in keys:
            if k in raw and raw[k] is not None:
                v = raw[k]
                if isinstance(v, dict) and "display_value" in v:
                    return str(v["display_value"]).strip()
                if isinstance(v, (str, int, float)):
                    return str(v).strip()
        return default

    # Filing Status mapping to Drake numeric code: 1=Single, 2=MFJ, 3=MFS, 4=HOH, 5=QSS
    fs_raw = get_val("Filing_Status", "FilingStatus", default="Single").lower()
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
        "first_name": get_val("Taxpayer_First_Name", "First_Name", "Taxpayer_Name"),
        "mi": get_val("Taxpayer_Middle_Name", "Middle_Name", "Middle_Initial", "Taxpayer_MI"),
        "last_name": get_val("Taxpayer_Last_Name", "Last_Name"),
        "ssn": get_val("Taxpayer_SSN", "Soc_Sec", "SSN"),
        "dob": format_to_drake_date(get_val("Taxpayer_DOB", "DOB", "Date_of_Birth")),
        "occupation": get_val("Taxpayer_Occupation", "Occupation"),
        "phone": get_val("Taxpayer_Main_Phone", "Main_Phone", "Phone"),
        "other_phone": get_val("Taxpayer_Other_Phone", "Other_Phone"),
        "email": get_val("Taxpayer_Email", "Email_Address", "Email")
    }

    spouse = {
        "first_name": get_val("Spouse_First_Name", "Spouse_First"),
        "mi": get_val("Spouse_Middle_Name", "Spouse_MI"),
        "last_name": get_val("Spouse_Last_Name", "Spouse_Last"),
        "ssn": get_val("Spouse_SSN", "Spouse_Soc_ITIN", "Spouse_SSN_ITIN"),
        "dob": format_to_drake_date(get_val("Spouse_DOB", "Spouse_Date_of_Birth")),
        "occupation": get_val("Spouse_Occupation"),
        "phone": get_val("Spouse_Main_Phone", "Spouse_Main", "Spouse_Phone"),
        "other_phone": get_val("Spouse_Other_Phone", "Spouse_Other"),
        "email": get_val("Spouse_Email", "Spouse_Email_Address")
    }

    address = {
        "street": get_val("Mailing_Address", "Address", "Street_Address"),
        "city": get_val("City"),
        "state": get_val("State", "State_Field"),
        "zip": get_val("Zip", "Postal_Code", "Zip_Code")
    }

    bank = {
        "bank_name": get_val("Bank_Name"),
        "account_type": get_val("Account_Type", default=""),
        "routing": get_val("Routing_Number", "Routing"),
        "account_number": get_val("Account_Number", "Account_Num")
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
        "residential_status": get_val("Your_residential_Status", "Residential_Status", default=""),
        "days_2025": get_val("Days_Present_in_US_2025", default=""),
        "days_2024": get_val("Days_Present_in_US_2024", default=""),
        "days_2023": get_val("Days_Present_in_US_2023", default="")
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
