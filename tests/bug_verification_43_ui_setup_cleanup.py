#!/usr/bin/env python3
"""Setup/verify/cleanup helper for Point 26 iteration 43 UI verification."""
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
CONTEXT_PATH = REPORT_DIR / "bug_verification_43_ui_context.json"
RESULT_PATH = REPORT_DIR / "bug_verification_43_ui_db_results.json"
CSV_PATH = Path("/tmp/coupon_ui_test43.csv")
load_dotenv(BACKEND_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"].strip('"')
DB_NAME = os.environ.get("DB_NAME", "test_database")
API_BASE = "http://localhost:8001/api"


def db():
    return MongoClient(MONGO_URL)[DB_NAME]


def cleanup(database, source=None, marker=None):
    filters = [{"source_code": {"$regex": "^SRC_UI_BV43_"}}, {"code": {"$regex": "^BV43UI_"}}, {"brand_name": {"$regex": "^BV43UI_"}}]
    if source:
        filters.append({"source_code": source})
    if marker:
        filters.append({"code": {"$regex": f"^BV43UI_{marker}"}})
        filters.append({"brand_name": {"$regex": f"^BV43UI_{marker}"}})
    return database.coupon_codes.delete_many({"$or": filters}).deleted_count


def login_token():
    r = requests.post(API_BASE + "/admin/login", json={"username": "admin", "password": "CP67Admin@2025"}, timeout=20)
    r.raise_for_status()
    return r.json()["token"]


def setup():
    database = db()
    deleted = cleanup(database)
    marker = str(int(time.time()))[-6:] + str(random.randint(100, 999))
    source = f"SRC_UI_BV43_{marker}"
    rows = [
        [f"BV43UI_{marker}_BrandValidA", f"BV43UI_{marker}_VALID_A", "111", "2026-12-31"],
        [f"BV43UI_{marker}_BrandCompact", f"BV43UI_{marker}_COMPACT_1", "222", "20281231"],
        [f"BV43UI_{marker}_BrandWeek", f"BV43UI_{marker}_WEEK_1", "333", "2028-W01-1"],
        [f"BV43UI_{marker}_BrandValidB", f"BV43UI_{marker}_VALID_B", "444", "2027-06-30"],
        [f"BV43UI_{marker}_BrandBad", f"BV43UI_{marker}_BAD_1", "555", "not-a-date"],
        [f"BV43UI_{marker}_BrandEmpty", f"BV43UI_{marker}_EMPTY_1", "666", ""],
    ]
    with CSV_PATH.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Brand Name", "Coupon Code", "Coupon Value", "Expiry Date"])
        writer.writerows(rows)
    ctx = {
        "marker": marker,
        "source": source,
        "csv_path": str(CSV_PATH),
        "valid_codes": [rows[0][1], rows[3][1]],
        "invalid_codes": [rows[1][1], rows[2][1], rows[4][1], rows[5][1]],
        "valid_brands": [rows[0][0], rows[3][0]],
        "invalid_brands": [rows[1][0], rows[2][0], rows[4][0], rows[5][0]],
        "setup_deleted_existing_ui_rows": deleted,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    CONTEXT_PATH.write_text(json.dumps(ctx, indent=2))
    print(json.dumps(ctx, indent=2))


def verify_cleanup():
    database = db()
    ctx = json.loads(CONTEXT_PATH.read_text())
    docs = list(database.coupon_codes.find({"source_code": ctx["source"]}, {"_id": 0}))
    persisted_codes = sorted(d["code"] for d in docs)
    valid_ok = persisted_codes == sorted(ctx["valid_codes"])
    invalid_absent = not any(code in persisted_codes for code in ctx["invalid_codes"])
    inventory_before_cleanup = requests.get(
        API_BASE + "/admin/coupons/inventory",
        params={"source_code": ctx["source"]},
        headers={"Authorization": "Bearer " + login_token()},
        timeout=20,
    ).json()
    deleted = cleanup(database, ctx["source"], ctx["marker"])
    remaining = database.coupon_codes.count_documents({"source_code": ctx["source"]})
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