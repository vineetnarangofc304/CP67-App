#!/usr/bin/env python3
"""Final cleanup verification for Point 26 iteration 43 test artifacts."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


ROOT = Path("/app")
REPORT = ROOT / "test_reports" / "bug_verification_43_cleanup_results.json"
load_dotenv(ROOT / "backend" / ".env")
db = MongoClient(os.environ["MONGO_URL"].strip('"'))[os.environ.get("DB_NAME", "test_database")]

phones = set()
backend_result = ROOT / "test_reports" / "bug_verification_43_backend_results.json"
if backend_result.exists():
    try:
        def walk(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in {"user_phone", "issued_to_phone", "phone"} and isinstance(value, str) and value.startswith("91"):
                        phones.add(value)
                    walk(value)
            elif isinstance(obj, list):
                for value in obj:
                    walk(value)
        walk(json.loads(backend_result.read_text()))
    except Exception:
        pass

coupon_filter = {"$or": [
    {"source_code": {"$regex": "^SRC_STRICT_TEST"}},
    {"source_code": {"$regex": "^SRC_RETEST"}},
    {"source_code": {"$regex": "^SRC_UI_BV43_"}},
    {"code": {"$regex": "^BV43"}},
    {"brand_name": {"$regex": "^BV43"}},
]}
log_terms = [{"content": {"$regex": "BV43"}}]
user_terms = [{"name": {"$regex": "BV43"}}]
if phones:
    log_terms.append({"user_phone": {"$in": sorted(phones)}})
    user_terms.append({"phone": {"$in": sorted(phones)}})
log_filter = {"$or": log_terms}
user_filter = {"$or": user_terms}

deleted_coupons = db.coupon_codes.delete_many(coupon_filter).deleted_count
deleted_logs = db.whatsapp_logs.delete_many(log_filter).deleted_count
deleted_users = db.users.delete_many(user_filter).deleted_count
remaining = {
    "coupons": db.coupon_codes.count_documents(coupon_filter),
    "whatsapp_logs": db.whatsapp_logs.count_documents(log_filter),
    "users": db.users.count_documents(user_filter),
}
result = {
    "phones_from_backend_result": sorted(phones),
    "deleted_coupons": deleted_coupons,
    "deleted_whatsapp_logs": deleted_logs,
    "deleted_users": deleted_users,
    "remaining": remaining,
    "passed": all(v == 0 for v in remaining.values()),
}
REPORT.write_text(json.dumps(result, indent=2, default=str))
print(json.dumps(result, indent=2, default=str))
if not result["passed"]:
    raise SystemExit(1)