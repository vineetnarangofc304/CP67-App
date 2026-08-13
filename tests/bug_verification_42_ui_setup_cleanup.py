#!/usr/bin/env python3
"""Setup/verify/cleanup helper for Point 26 UI verification.

Usage:
  python tests/bug_verification_42_ui_setup_cleanup.py setup
  python tests/bug_verification_42_ui_setup_cleanup.py verify-cleanup
"""
import csv
import json
import os
import random
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient


ROOT = Path("/app")
BACKEND_DIR = ROOT / "backend"
REPORT_DIR = ROOT / "test_reports"
CONTEXT_PATH = REPORT_DIR / "bug_verification_42_ui_context.json"
RESULT_PATH = REPORT_DIR / "bug_verification_42_ui_db_results.json"
CSV_PATH = Path("/tmp/coupon_ui_test42.csv")
load_dotenv(BACKEND_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"].strip('"')
DB_NAME = os.environ.get("DB_NAME", "test_database")
API_BASE = "http://localhost:8001/api"


def db():
    return MongoClient(MONGO_URL)[DB_NAME]


def cleanup_ui_rows(database):
    return database.coupon_codes.delete_many({
        "source_code": "SRC_RWA",
        "$or": [
            {"code": {"$regex": "^BV42UI_"}},
            {"brand_name": {"$regex": "^BV42UI_"}},
        ],
    }).deleted_count


def login_token():
    r = requests.post(API_BASE + "/admin/login", json={"username": "admin", "password": "CP67Admin@2025"}, timeout=20)
    r.raise_for_status()
    return r.json()["token"]


def setup():
    database = db()
    deleted = cleanup_ui_rows(database)
    marker = str(int(time.time()))[-6:] + str(random.randint(100, 999))
    rows = [
        [f"BV42UI_{marker}_BrandA", f"BV42UI_{marker}_VALID_A", "101", "2027-12-31"],
        [f"BV42UI_{marker}_BrandBad", f"BV42UI_{marker}_BAD_DATE", "202", "not-a-date"],
        [f"BV42UI_{marker}_BrandMissing", f"BV42UI_{marker}_MISSING_EXP", "303", ""],
        [f"BV42UI_{marker}_BrandB", f"BV42UI_{marker}_VALID_B", "404", "2028-01-15"],
    ]
    with CSV_PATH.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Brand Name", "Coupon Code", "Coupon Value", "Expiry Date"])
        writer.writerows(rows)
    ctx = {
        "marker": marker,
        "csv_path": str(CSV_PATH),
        "valid_codes": [rows[0][1], rows[3][1]],
        "invalid_codes": [rows[1][1], rows[2][1]],
        "valid_brands": [rows[0][0], rows[3][0]],
        "invalid_brands": [rows[1][0], rows[2][0]],
        "setup_deleted_existing_ui_rows": deleted,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    CONTEXT_PATH.write_text(json.dumps(ctx, indent=2))
    print(json.dumps(ctx, indent=2))


def verify_cleanup():
    database = db()
    ctx = json.loads(CONTEXT_PATH.read_text())
    codes = ctx["valid_codes"] + ctx["invalid_codes"]
    docs = list(database.coupon_codes.find({"source_code": "SRC_RWA", "code": {"$in": codes}}, {"_id": 0}))
    persisted_codes = sorted(d["code"] for d in docs)
    valid_ok = sorted(ctx["valid_codes"]) == sorted([d["code"] for d in docs if d["code"] in ctx["valid_codes"]])
    invalid_absent = not any(d["code"] in ctx["invalid_codes"] for d in docs)
    inventory_before_cleanup = requests.get(
        API_BASE + "/admin/coupons/inventory",
        params={"source_code": "SRC_RWA"},
        headers={"Authorization": "Bearer " + login_token()},
        timeout=20,
    ).json()
    deleted = cleanup_ui_rows(database)
    remaining = database.coupon_codes.count_documents({"source_code": "SRC_RWA", "code": {"$in": codes}})
    result = {
        "context": ctx,
        "persisted_codes_before_cleanup": persisted_codes,
        "valid_rows_persisted": valid_ok,
        "invalid_rows_absent": invalid_absent,
        "inventory_before_cleanup": inventory_before_cleanup,
        "deleted_ui_rows": deleted,
        "remaining_after_cleanup": remaining,
        "passed": valid_ok and invalid_absent and remaining == 0,
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(result, indent=2, default=str))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"setup", "verify-cleanup"}:
        print(__doc__)
        raise SystemExit(2)
    if sys.argv[1] == "setup":
        setup()
    else:
        verify_cleanup()