#!/usr/bin/env python3
"""Seed/cleanup isolated records for the focused UI verification."""
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import requests
from pymongo import MongoClient

APP = Path("/app")
SEED_FILE = APP / "test_reports" / "bug_verify_points_2_3_4_5_ui_seed.json"


def read_env(path: Path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.strip().startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


frontend_env = read_env(APP / "frontend" / ".env")
backend_env = read_env(APP / "backend" / ".env")
BASE = frontend_env.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = BASE + "/api"
MONGO_URL = backend_env.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = backend_env.get("DB_NAME", "test_database")


def cleanup():
    if not SEED_FILE.exists():
        print("No UI seed file found; nothing to cleanup")
        return 0
    seed = json.loads(SEED_FILE.read_text())
    db = MongoClient(MONGO_URL)[DB_NAME]
    if seed.get("staff_id"):
        db.retail_staff.delete_one({"id": seed["staff_id"]})
    if seed.get("manager_id"):
        db.retailer_managers.delete_one({"id": seed["manager_id"]})
    if seed.get("incentive_ids"):
        db.staff_incentives.delete_many({"id": {"$in": seed["incentive_ids"]}})
    if seed.get("redemption_ids"):
        db.staff_redemptions.delete_many({"id": {"$in": seed["redemption_ids"]}})
    db.staff_otps.delete_many({"phone": {"$in": [seed.get("staff_phone"), seed.get("manager_phone")]}})
    print(f"Cleaned UI seed: {seed}")
    return 0


def seed():
    run = str(int(time.time()))[-6:]
    brand = f"QA-UI-Retailer-{run}"
    category = f"QA-UI-Category-{run}"
    staff_phone = "9020" + run
    manager_phone = "9021" + run

    r = requests.post(f"{API}/admin/login", json={"username": "admin", "password": "CP67Admin@2025"}, timeout=25)
    r.raise_for_status()
    token = r.json()["token"]
    ah = {"Authorization": f"Bearer {token}"}

    staff_payload = {
        "name": f"QA UI Staff {run}",
        "phone": staff_phone,
        "brand_name": brand,
        "brand_category": category,
        "store_location": "bug_verify_points_2_3_4_5_ui",
    }
    r = requests.post(f"{API}/admin/staff", headers=ah, json=staff_payload, timeout=25)
    r.raise_for_status()
    staff = r.json()["staff"]

    mgr_payload = {"name": f"QA UI Manager {run}", "phone": manager_phone, "brands": [brand]}
    r = requests.post(f"{API}/admin/staff/retailer-managers", headers=ah, json=mgr_payload, timeout=25)
    r.raise_for_status()
    manager = r.json()["manager"]

    db = MongoClient(MONGO_URL)[DB_NAME]
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    incentive_docs = [
        {"id": str(uuid.uuid4()), "staff_id": staff["id"], "type": "registration", "status": "redeemable", "amount": 10, "created_at": now, "source": "ui_seed", "customer_phone": "9555555555"},
        {"id": str(uuid.uuid4()), "staff_id": staff["id"], "type": "bill_upload", "status": "redeemed", "amount": 20, "created_at": now, "source": "ui_seed", "bill_image": "hidden"},
    ]
    db.staff_incentives.insert_many(incentive_docs)
    red_doc = {"id": str(uuid.uuid4()), "staff_id": staff["id"], "reference": f"QA-UI-RED-{run}", "amount": 20, "status": "settled", "requested_at": now, "source": "ui_seed"}
    db.staff_redemptions.insert_one(red_doc)

    seed_data = {
        "base": BASE,
        "api": API,
        "brand": brand,
        "category": category,
        "staff_name": staff["name"],
        "staff_id": staff["id"],
        "staff_phone": staff_phone,
        "manager_id": manager["id"],
        "manager_name": manager["name"],
        "manager_phone": manager_phone,
        "incentive_ids": [x["id"] for x in incentive_docs],
        "redemption_ids": [red_doc["id"]],
    }
    SEED_FILE.write_text(json.dumps(seed_data, indent=2))
    print(json.dumps(seed_data, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(cleanup() if "--cleanup" in sys.argv else seed())