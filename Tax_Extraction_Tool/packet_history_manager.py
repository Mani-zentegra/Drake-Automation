import os
import json
import time
import re
from datetime import datetime

HISTORY_DIR = os.path.join(os.path.dirname(__file__), "history")
INDEX_FILE = os.path.join(HISTORY_DIR, "packets_index.json")

def ensure_history_dir():
    os.makedirs(HISTORY_DIR, exist_ok=True)
    if not os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)

def get_history_list():
    ensure_history_dir()
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            items = json.load(f)
            # Filter out entries whose files no longer exist or are invalid
            valid_items = []
            for item in items:
                detail_path = os.path.join(HISTORY_DIR, f"{item['id']}.json")
                if os.path.exists(detail_path):
                    valid_items.append(item)
            return sorted(valid_items, key=lambda x: x.get("timestamp", 0), reverse=True)
    except Exception as e:
        print(f"[HISTORY] Error reading index: {e}")
        return []

def get_packet_by_id(packet_id):
    ensure_history_dir()
    detail_path = os.path.join(HISTORY_DIR, f"{packet_id}.json")
    if not os.path.exists(detail_path):
        return None
    try:
        with open(detail_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[HISTORY] Error reading packet {packet_id}: {e}")
        return None

def derive_client_label(packet_res, filename):
    modules = packet_res.get("modules", [])
    # Check if W-2 has employee name
    for m in modules:
        if m.get("type") == "W-2":
            emp_name = m.get("employee_name") or m.get("taxpayer_name")
            if emp_name and emp_name.strip():
                return emp_name.strip()
    # Check 1099-R or SSA
    for m in modules:
        for k in ["recipient_name", "beneficiary_name"]:
            val = m.get(k)
            if val and val.strip():
                return val.strip()
    # Fallback to sanitized filename
    base = os.path.splitext(os.path.basename(filename))[0]
    return base.replace("_", " ").replace("-", " ")

def save_packet_history(filename, file_path, packet_res):
    ensure_history_dir()
    # Create a stable ID or timestamped ID
    slug = re.sub(r"[^a-zA-Z0-9_]", "_", os.path.splitext(filename)[0]).lower()
    ts = int(time.time())
    packet_id = f"{slug}_{ts}"

    taxpayer_name = derive_client_label(packet_res, filename)
    created_at = datetime.now().strftime("%b %d, %Y - %I:%M %p")

    # Full packet payload
    full_data = {
        "id": packet_id,
        "filename": filename,
        "file_path": os.path.abspath(file_path),
        "created_at": created_at,
        "timestamp": ts,
        "taxpayer_name": taxpayer_name,
        "total_modules": packet_res.get("total_modules", len(packet_res.get("modules", []))),
        "total_pages": packet_res.get("total_pages", 1),
        "category_counts": packet_res.get("category_counts", {}),
        "modules": packet_res.get("modules", [])
    }

    # Save detailed JSON
    detail_path = os.path.join(HISTORY_DIR, f"{packet_id}.json")
    with open(detail_path, "w", encoding="utf-8") as f:
        json.dump(full_data, f, indent=2)

    # Update Index
    index_entry = {
        "id": packet_id,
        "filename": filename,
        "file_path": os.path.abspath(file_path),
        "created_at": created_at,
        "timestamp": ts,
        "taxpayer_name": taxpayer_name,
        "total_modules": full_data["total_modules"],
        "total_pages": full_data["total_pages"],
        "category_counts": full_data["category_counts"]
    }

    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception:
        items = []

    # If same filename exists, replace or keep as recent
    # Let's keep unique by filename or allow multiple versions
    items = [it for it in items if it.get("filename") != filename]
    items.insert(0, index_entry)

    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)

    return full_data

def delete_packet_history(packet_id):
    ensure_history_dir()
    detail_path = os.path.join(HISTORY_DIR, f"{packet_id}.json")
    if os.path.exists(detail_path):
        try:
            os.remove(detail_path)
        except Exception:
            pass

    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            items = json.load(f)
        items = [it for it in items if it.get("id") != packet_id]
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
        return True
    except Exception as e:
        print(f"[HISTORY] Error deleting: {e}")
        return False

def seed_sample_packet_if_needed():
    ensure_history_dir()
    items = get_history_list()
    # Check if sample packet is already in history
    sample_name = "Weaver-Cummings_2025_Tax_Packet.pdf"
    for it in items:
        if it.get("filename") == sample_name:
            return  # Already seeded

    # Seed it
    sample_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "uploads", sample_name))
    if not os.path.exists(sample_path):
        sample_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", sample_name))

    if os.path.exists(sample_path):
        try:
            from packet_extractor import extract_all_modules_from_packet
            print(f"[HISTORY] Pre-seeding default history with {sample_name}...")
            res = extract_all_modules_from_packet(sample_path)
            if res.get("total_modules", 0) > 0:
                save_packet_history(sample_name, sample_path, res)
                print(f"[HISTORY] Pre-seeded {res['total_modules']} modules for {sample_name} successfully.")
        except Exception as e:
            print(f"[HISTORY] Failed to seed sample packet: {e}")
