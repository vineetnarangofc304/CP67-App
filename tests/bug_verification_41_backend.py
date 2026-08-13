import asyncio
import csv
import io
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone

import requests
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = "/app"
BACKEND_DIR = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND_DIR)


def load_env(path):
    out = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                out[k] = v
    return out

backend_env = load_env(os.path.join(BACKEND_DIR, ".env"))
frontend_env = load_env(os.path.join(ROOT, "frontend", ".env"))
MONGO_URL = backend_env.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = backend_env.get("DB_NAME", "test_database")
BASE_URL = os.environ.get("TEST_API_BASE", "http://localhost:8001/api")
ADMIN_USER = backend_env.get("ADMIN_USERNAME", "admin")
ADMIN_PASS = backend_env.get("ADMIN_PASSWORD", "CP67Admin@2025")

RUN = f"TEST41_{int(time.time())}_{uuid.uuid4().hex[:6]}"
SRC = "SRC_RWA"
SRC_OFFICE = "SRC_OFFICE"
PHONES = [f"91988841{str(i).zfill(5)}" for i in range(1, 8)]
TEST_PREFIX = "TEST41_"
results = {"run": RUN, "base_url": BASE_URL, "checks": []}


def check(name, passed, detail=None):
    rec = {"name": name, "passed": bool(passed), "detail": detail}
    results["checks"].append(rec)
    print(("PASS" if passed else "FAIL") + f" - {name}" + (f": {detail}" if detail else ""), flush=True)


def csv_bytes(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Brand Name", "Coupon Code", "Coupon Value", "Expiry Date"])
    for row in rows:
        w.writerow(row)
    return buf.getvalue().encode("utf-8")


mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


def cleanup():
    code_q = {"$or": [
        {"code": {"$regex": f"^{TEST_PREFIX}"}},
        {"brand_name": {"$regex": f"^{TEST_PREFIX}"}},
        {"issued_to_phone": {"$in": PHONES}},
    ]}
    deleted_coupons = db.coupon_codes.delete_many(code_q).deleted_count
    deleted_users = db.users.delete_many({"phone": {"$in": PHONES}}).deleted_count
    deleted_logs = db.whatsapp_logs.delete_many({"user_phone": {"$in": PHONES}}).deleted_count
    deleted_dedup = db.whatsapp_dedup.delete_many({"key": {"$regex": "|".join(PHONES)}}).deleted_count
    db.fundle_customers.delete_many({"phone_10": {"$in": [p[2:] for p in PHONES]}})
    db.blocked_phones.delete_many({"phone": {"$in": [p[2:] for p in PHONES]}})
    return {"coupons": deleted_coupons, "users": deleted_users, "logs": deleted_logs, "dedup": deleted_dedup}

cleanup_before = cleanup()
results["cleanup_before"] = cleanup_before

try:
    r = requests.post(f"{BASE_URL}/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=20)
    token = r.json().get("token") if r.headers.get("content-type", "").startswith("application/json") else None
    check("admin login", r.status_code == 200 and bool(token), {"status": r.status_code, "body": r.text[:200]})
    headers = {"Authorization": f"Bearer {token}"}

    # Template endpoint
    r = requests.get(f"{BASE_URL}/admin/coupons/template.csv", headers=headers, timeout=20)
    first_line = r.text.splitlines()[0] if r.text else ""
    check("template.csv returns exact required header", r.status_code == 200 and first_line == "Brand Name,Coupon Code,Coupon Value,Expiry Date", {"status": r.status_code, "first_line": first_line, "content_disposition": r.headers.get("content-disposition")})

    before_count = db.coupon_codes.count_documents({"code": {"$regex": f"^{TEST_PREFIX}"}})
    dry_rows = [
        [f"{TEST_PREFIX}DryBrand", f"{TEST_PREFIX}{RUN}_DRY1", "111", "2026-12-31"],
        [f"{TEST_PREFIX}DryBrand", f"{TEST_PREFIX}{RUN}_DRY2", "222", "2026-12-31"],
    ]
    r = requests.post(
        f"{BASE_URL}/admin/coupons/bulk-upload",
        headers=headers,
        data={"source_code": SRC, "dry_run": "true"},
        files={"file": ("dry.csv", csv_bytes(dry_rows), "text/csv")},
        timeout=20,
    )
    after_count = db.coupon_codes.count_documents({"code": {"$regex": f"^{TEST_PREFIX}"}})
    dry_json = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    check("dry-run reports imports but does not persist", r.status_code == 200 and dry_json.get("dry_run") is True and dry_json.get("summary", {}).get("imported") == 2 and before_count == after_count, {"status": r.status_code, "summary": dry_json.get("summary"), "before": before_count, "after": after_count})

    # Live upload with duplicate and invalid rows: duplicate code within same source, missing brand, invalid value, invalid expiry.
    code_a = f"{TEST_PREFIX}{RUN}_A"
    code_b = f"{TEST_PREFIX}{RUN}_B"
    code_c = f"{TEST_PREFIX}{RUN}_BAD_EXPIRY"
    live_rows = [
        [f"{TEST_PREFIX}BrandA", code_a, "100", "2026-12-31"],
        [f"{TEST_PREFIX}BrandA", code_b, "200", "2026-12-31"],
        [f"{TEST_PREFIX}BrandA", code_a, "100", "2026-12-31"],  # duplicate same source
        ["", f"{TEST_PREFIX}{RUN}_MISS_BRAND", "100", "2026-12-31"],
        [f"{TEST_PREFIX}BrandB", f"{TEST_PREFIX}{RUN}_BAD_VALUE", "notnum", "2026-12-31"],
        [f"{TEST_PREFIX}BrandC", code_c, "300", "not-a-date"],
    ]
    r = requests.post(
        f"{BASE_URL}/admin/coupons/bulk-upload",
        headers=headers,
        data={"source_code": SRC, "dry_run": "false"},
        files={"file": ("live.csv", csv_bytes(live_rows), "text/csv")},
        timeout=20,
    )
    live_json = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    persisted = list(db.coupon_codes.find({"code": {"$in": [code_a, code_b, code_c]}}, {"_id": 0, "code": 1, "status": 1, "source_code": 1, "expiry": 1}))
    expected_strict = r.status_code == 200 and live_json.get("summary", {}).get("imported") == 2 and live_json.get("summary", {}).get("skipped_duplicates") == 1 and live_json.get("summary", {}).get("invalid") == 3 and len(persisted) == 2
    expected_current = r.status_code == 200 and live_json.get("summary", {}).get("imported") in (2, 3) and live_json.get("summary", {}).get("skipped_duplicates") == 1 and live_json.get("summary", {}).get("invalid") in (2, 3)
    check("live upload imports available coupons, skips duplicate, counts invalid rows including bad expiry", expected_strict, {"status": r.status_code, "summary": live_json.get("summary"), "persisted": persisted, "note": "Bad expiry should be invalid; if imported, expiry validation is missing."})
    check("live upload basic persistence/status works", expected_current and all(p.get("status") == "available" for p in persisted), {"status": r.status_code, "summary": live_json.get("summary"), "persisted": persisted})

    # Duplicate same code in another source should be allowed (contract says same source duplicates skipped)
    office_code = code_a
    r = requests.post(
        f"{BASE_URL}/admin/coupons/bulk-upload",
        headers=headers,
        data={"source_code": SRC_OFFICE, "dry_run": "false"},
        files={"file": ("office.csv", csv_bytes([[f"{TEST_PREFIX}OfficeBrand", office_code, "123", "2026-12-31"]]), "text/csv")},
        timeout=20,
    )
    office_json = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    office_doc = db.coupon_codes.find_one({"source_code": SRC_OFFICE, "code": office_code}, {"_id": 0})
    check("same coupon code allowed for different source", r.status_code == 200 and office_json.get("summary", {}).get("imported") == 1 and bool(office_doc), {"status": r.status_code, "summary": office_json.get("summary"), "office_doc_exists": bool(office_doc)})

    # Inventory endpoint before issuance
    r = requests.get(f"{BASE_URL}/admin/coupons/inventory", headers=headers, params={"source_code": SRC}, timeout=20)
    inv = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    brand_rows = [row for row in inv.get("inventory", []) if str(row.get("brand_name", "")).startswith(TEST_PREFIX)]
    totals = inv.get("totals", {})
    check("inventory endpoint returns per-brand/status rows and top-level totals", r.status_code == 200 and isinstance(inv.get("inventory"), list) and {"available", "issued", "expired", "void"}.issubset(totals.keys()) and any(row.get("status") == "available" for row in brand_rows), {"status": r.status_code, "brand_rows": brand_rows, "totals": totals})

    # Atomic helper issuance with N+1 calls; seed exactly 3 fresh helper coupons so result is deterministic.
    helper_docs = []
    for i in range(3):
        helper_docs.append({
            "id": str(uuid.uuid4()),
            "source_code": SRC,
            "brand_name": f"{TEST_PREFIX}HelperBrand",
            "code": f"{TEST_PREFIX}{RUN}_HELPER_{i}",
            "value": 50 + i,
            "expiry": "2026-12-31",
            "status": "available",
            "issued_to_phone": None,
            "issued_at": None,
            "created_at": datetime.now(timezone.utc).isoformat() + f"_{i}",
        })
    # Make all other TEST41 SRC_RWA coupons unavailable to isolate this N+1 check.
    db.coupon_codes.update_many({"source_code": SRC, "code": {"$regex": f"^{TEST_PREFIX}"}, "status": "available"}, {"$set": {"status": "void"}})
    db.coupon_codes.insert_many(helper_docs)

    async def helper_test():
        from routes.coupons import bind_db, issue_coupon_for_registration
        motor_client = AsyncIOMotorClient(MONGO_URL)
        adb = motor_client[DB_NAME]
        bind_db(adb)
        out = []
        for i in range(4):
            out.append(await issue_coupon_for_registration(PHONES[i], SRC))
        motor_client.close()
        return out

    issued = asyncio.run(helper_test())
    issued_non_null = [c for c in issued if c]
    distinct_codes = {c.get("code") for c in issued_non_null}
    db_after_helper = list(db.coupon_codes.find({"code": {"$regex": f"^{TEST_PREFIX}{RUN}_HELPER_"}}, {"_id": 0, "code": 1, "status": 1, "issued_to_phone": 1, "issued_at": 1}).sort("code", 1))
    check("atomic helper issues N distinct coupons then returns None on N+1", len(issued_non_null) == 3 and issued[-1] is None and len(distinct_codes) == 3 and all(d.get("status") == "issued" for d in db_after_helper), {"returned": [{k: c.get(k) for k in ("code", "status", "issued_to_phone")} if c else None for c in issued], "db": db_after_helper})

    # Issued endpoint after helper
    r = requests.get(f"{BASE_URL}/admin/coupons/issued", headers=headers, params={"source_code": SRC}, timeout=20)
    issued_json = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    issued_rows = [c for c in issued_json.get("issued", []) if str(c.get("code", "")).startswith(TEST_PREFIX)]
    check("issued endpoint returns issued coupons with issued_to_phone and issued_at", r.status_code == 200 and len(issued_rows) >= 3 and all(c.get("issued_to_phone") and c.get("issued_at") for c in issued_rows), {"status": r.status_code, "issued_rows": [{"code": c.get("code"), "phone": c.get("issued_to_phone"), "issued_at": c.get("issued_at")} for c in issued_rows[:10]]})

    # Webhook registration hook: seed two fresh coupons, simulate two unique RWA registrations, assert logs contain distinct coupon content.
    db.coupon_codes.update_many({"source_code": SRC, "code": {"$regex": f"^{TEST_PREFIX}"}, "status": "available"}, {"$set": {"status": "void"}})
    webhook_codes = [f"{TEST_PREFIX}{RUN}_WEBHOOK_1", f"{TEST_PREFIX}{RUN}_WEBHOOK_2"]
    db.coupon_codes.insert_many([
        {"id": str(uuid.uuid4()), "source_code": SRC, "brand_name": f"{TEST_PREFIX}WebhookBrand", "code": webhook_codes[0], "value": 777, "expiry": "2026-12-31", "status": "available", "issued_to_phone": None, "issued_at": None, "created_at": datetime.now(timezone.utc).isoformat() + "_w1"},
        {"id": str(uuid.uuid4()), "source_code": SRC, "brand_name": f"{TEST_PREFIX}WebhookBrand", "code": webhook_codes[1], "value": 888, "expiry": "2026-12-31", "status": "available", "issued_to_phone": None, "issued_at": None, "created_at": datetime.now(timezone.utc).isoformat() + "_w2"},
    ])

    def post_webhook(phone, name, msg_suffix=""):
        payload = {
            "events": {"eventType": "USER MESSAGE"},
            "eventContent": {
                "message": {
                    "from": phone,
                    "messageType": "text",
                    "profileName": name,
                    "text": {"body": f"Hi! Register me for CP67 Loyalty — RWA {msg_suffix} | SRC_RWA"},
                }
            },
        }
        return requests.post(f"{BASE_URL}/whatsapp/webhook", json=payload, timeout=60)

    webhook_responses = []
    for idx, phone in enumerate(PHONES[4:6], start=1):
        webhook_responses.append(post_webhook(phone, f"{TEST_PREFIX} User {idx}", msg_suffix=str(idx)))

    deadline = time.time() + 75
    webhook_docs = []
    outbound_logs = []
    while time.time() < deadline:
        webhook_docs = list(db.coupon_codes.find({"code": {"$in": webhook_codes}}, {"_id": 0, "code": 1, "status": 1, "issued_to_phone": 1, "issued_at": 1, "brand_name": 1, "value": 1}).sort("code", 1))
        outbound_logs = list(db.whatsapp_logs.find({"user_phone": {"$in": PHONES[4:6]}, "direction": "outbound", "content": {"$regex": "Welcome Coupon Unlocked"}}, {"_id": 0, "user_phone": 1, "content": 1}).sort("user_phone", 1))
        if len([d for d in webhook_docs if d.get("status") == "issued"]) == 2 and len(outbound_logs) >= 2:
            break
        time.sleep(2)
    log_contents = "\n---\n".join(l.get("content", "") for l in outbound_logs)
    webhook_ok = (
        all(resp.status_code == 200 for resp in webhook_responses)
        and len([d for d in webhook_docs if d.get("status") == "issued"]) == 2
        and len({d.get("issued_to_phone") for d in webhook_docs}) == 2
        and len(outbound_logs) >= 2
        and "Welcome Coupon Unlocked" in log_contents
        and f"{TEST_PREFIX}WebhookBrand" in log_contents
        and all(code in log_contents for code in webhook_codes)
        and "₹777" in log_contents and "₹888" in log_contents
    )
    check("WhatsApp webhook new RWA registrations pop distinct coupons and welcome logs include coupon details", webhook_ok, {"responses": [{"status": x.status_code, "body": x.text[:120]} for x in webhook_responses], "docs": webhook_docs, "logs_found": len(outbound_logs), "log_excerpt": log_contents[:1000]})

    # Existing user should not receive another registration coupon on repeat scan.
    pre_available = db.coupon_codes.count_documents({"source_code": SRC, "code": {"$regex": f"^{TEST_PREFIX}{RUN}_WEBHOOK_"}, "status": "available"})
    repeat_resp = post_webhook(PHONES[4], f"{TEST_PREFIX} User Repeat", msg_suffix="repeat")
    time.sleep(5)
    post_available = db.coupon_codes.count_documents({"source_code": SRC, "code": {"$regex": f"^{TEST_PREFIX}{RUN}_WEBHOOK_"}, "status": "available"})
    repeat_coupon_logs = list(db.whatsapp_logs.find({"user_phone": PHONES[4], "direction": "outbound", "content": {"$regex": "Welcome Coupon Unlocked"}}, {"_id": 0, "content": 1}))
    # Since first registration already had one coupon log, repeat should not add an additional coupon-unlocked log for same phone.
    check("repeat scan by existing user does not issue an extra registration coupon", repeat_resp.status_code == 200 and pre_available == post_available and len(repeat_coupon_logs) == 1, {"repeat_status": repeat_resp.status_code, "available_before": pre_available, "available_after": post_available, "coupon_logs_for_phone": len(repeat_coupon_logs)})

    # Regression sanity endpoints
    r_staff = requests.get(f"{BASE_URL}/admin/staff/bulk-import/template.csv", headers=headers, timeout=20)
    r_me = requests.get(f"{BASE_URL}/admin/me", headers=headers, timeout=20)
    check("regression sanity: admin me and staff bulk-import template still work", r_me.status_code == 200 and r_staff.status_code == 200 and "Staff Code" in r_staff.text, {"me_status": r_me.status_code, "staff_template_status": r_staff.status_code, "staff_first_line": r_staff.text.splitlines()[0] if r_staff.text else ""})

finally:
    cleanup_after = cleanup()
    results["cleanup_after"] = cleanup_after
    results["passed"] = sum(1 for c in results["checks"] if c["passed"])
    results["failed"] = sum(1 for c in results["checks"] if not c["passed"])
    report_path = os.path.join(ROOT, "test_reports", "bug_verification_41_backend_results.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Wrote backend test detail report: {report_path}")
    print(json.dumps({"passed": results["passed"], "failed": results["failed"], "cleanup_after": cleanup_after}, indent=2))
    if results["failed"]:
        sys.exit(1)
