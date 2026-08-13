#!/usr/bin/env python3
"""Additional strict-format edge check for Point 26 Expiry Date validation.

The product copy/error reason requires YYYY-MM-DD. Python date.fromisoformat()
also accepts compact ISO dates and ISO week dates, so this test verifies those
non-YYYY-MM-DD strings are rejected instead of persisted.
"""
import csv
import io
import json
import os
import random
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path("/app")
REPORT = ROOT / "test_reports" / "bug_verification_42_expiry_edge_results.json"
load_dotenv(ROOT / "backend" / ".env")
API_BASE = "http://localhost:8001/api"
MONGO_URL = os.environ["MONGO_URL"].strip('"')
DB_NAME = os.environ.get("DB_NAME", "test_database")


def main():
    marker = str(int(time.time()))[-6:] + str(random.randint(100, 999))
    source = f"SRC_RETEST_42_EDGE_{marker}"
    rows = [
        ["Brand Name", "Coupon Code", "Coupon Value", "Expiry Date"],
        ["BV42EDGEBrandCompact", f"BV42EDGE_{marker}_COMPACT", "100", "20281231"],
        ["BV42EDGEBrandWeek", f"BV42EDGE_{marker}_WEEK", "100", "2028-W01-1"],
    ]
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    db = MongoClient(MONGO_URL)[DB_NAME]
    token = requests.post(API_BASE + "/admin/login", json={"username": "admin", "password": "CP67Admin@2025"}, timeout=20).json()["token"]
    headers = {"Authorization": "Bearer " + token}
    try:
        r = requests.post(
            API_BASE + "/admin/coupons/bulk-upload",
            headers=headers,
            data={"source_code": source, "dry_run": "false"},
            files={"file": ("expiry_edge.csv", buf.getvalue(), "text/csv")},
            timeout=30,
        )
        data = r.json()
        persisted = list(db.coupon_codes.find({"source_code": source}, {"_id": 0, "code": 1, "expiry": 1}))
        passed = (
            r.status_code == 200
            and data.get("summary", {}).get("imported") == 0
            and data.get("summary", {}).get("invalid") == 2
            and len(persisted) == 0
        )
        result = {
            "source": source,
            "expected": "Non-YYYY-MM-DD expiry strings 20281231 and 2028-W01-1 should be invalid and not persisted.",
            "status_code": r.status_code,
            "response": data,
            "persisted_before_cleanup": persisted,
            "passed": passed,
        }
    finally:
        deleted = db.coupon_codes.delete_many({"source_code": source}).deleted_count
    result["cleanup_deleted"] = deleted
    REPORT.write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(result, indent=2, default=str))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()