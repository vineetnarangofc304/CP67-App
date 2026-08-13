#!/usr/bin/env python3
"""Focused backend verification for Point 26 iteration 42.

Validates strict Expiry Date handling in coupon CSV bulk upload and focused
regressions for atomic issuance, inventory/issued endpoints, and WhatsApp
new-registration coupon message logging.
"""
import asyncio
import csv
import io
import json
import os
import random
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


ROOT = Path("/app")
BACKEND_DIR = ROOT / "backend"
REPORT = ROOT / "test_reports" / "bug_verification_42_backend_results.json"
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

API_BASE = os.environ.get("BACKEND_PUBLIC_URL", "http://localhost:8001").rstrip("/") + "/api"
INTERNAL_API_BASE = "http://localhost:8001/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "test_database")


def make_csv(rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Brand Name", "Coupon Code", "Coupon Value", "Expiry Date"])
    writer.writerows(rows)
    return buf.getvalue()


def login():
    r = requests.post(
        f"{INTERNAL_API_BASE}/admin/login",
        json={"username": "admin", "password": "CP67Admin@2025"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["token"]


async def cleanup(db, marker, phones):
    await db.coupon_codes.delete_many({
        "$or": [
            {"source_code": {"$regex": f"^SRC_RETEST_42_{marker}"}},
            {"code": {"$regex": f"^BV42_{marker}"}},
            {"brand_name": {"$regex": f"^BV42_{marker}"}},
        ]
    })
    if phones:
        await db.users.delete_many({"phone": {"$in": phones}})
        await db.whatsapp_logs.delete_many({"user_phone": {"$in": phones}})
        await db.whatsapp_dedup.delete_many({"key": {"$regex": "^(" + "|".join(phones) + "):"}})


async def main():
    marker = str(int(time.time()))[-6:] + str(random.randint(100, 999))
    source = f"SRC_RETEST_42_{marker}"
    wa_source = f"SRC_RETEST_42_{marker}_WA"
    phones = [f"91894242{random.randint(1000, 9999)}", f"91894243{random.randint(1000, 9999)}"]
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    evidence = {
        "marker": marker,
        "source": source,
        "wa_source": wa_source,
        "checks": [],
        "failures": [],
    }

    def check(name, condition, details=None):
        evidence["checks"].append({"name": name, "passed": bool(condition), "details": details})
        if not condition:
            evidence["failures"].append({"name": name, "details": details})

    try:
        await cleanup(db, marker, phones)
        token = login()
        headers = {"Authorization": f"Bearer {token}"}

        valid_a = f"BV42_{marker}_VALID_A"
        bad_date = f"BV42_{marker}_BAD_DATE"
        missing_exp = f"BV42_{marker}_MISSING_EXP"
        valid_b = f"BV42_{marker}_VALID_B"
        csv_body = make_csv([
            [f"BV42_{marker}_BrandA", valid_a, "111", "2027-12-31"],
            [f"BV42_{marker}_BrandBad", bad_date, "222", "not-a-date"],
            [f"BV42_{marker}_BrandMissing", missing_exp, "333", ""],
            [f"BV42_{marker}_BrandB", valid_b, "444", "2028-01-15"],
        ])

        upload = requests.post(
            f"{INTERNAL_API_BASE}/admin/coupons/bulk-upload",
            headers=headers,
            data={"source_code": source, "dry_run": "false"},
            files={"file": ("coupon_expiry_retest.csv", csv_body, "text/csv")},
            timeout=30,
        )
        evidence["bulk_upload_status"] = upload.status_code
        evidence["bulk_upload_response"] = upload.json() if upload.headers.get("content-type", "").startswith("application/json") else upload.text
        check("bulk upload returned 200", upload.status_code == 200, evidence["bulk_upload_response"])
        data = upload.json()
        summary = data.get("summary", {})
        reasons = [x.get("reason") for x in data.get("invalid_preview", [])]
        check("summary imported=2 invalid=2", summary.get("imported") == 2 and summary.get("invalid") == 2, summary)
        check(
            "invalid_preview has exact expiry reasons",
            "invalid expiry date (need YYYY-MM-DD)" in reasons and "missing expiry date" in reasons,
            data.get("invalid_preview"),
        )

        list_r = requests.get(f"{INTERNAL_API_BASE}/admin/coupons/list", headers=headers, params={"source_code": source}, timeout=20)
        list_data = list_r.json()
        codes = sorted([c["code"] for c in list_data.get("coupons", [])])
        check("only valid rows persisted via API list", codes == sorted([valid_a, valid_b]), codes)
        mongo_codes = sorted([c["code"] async for c in db.coupon_codes.find({"source_code": source}, {"_id": 0, "code": 1})])
        check("invalid rows not present in MongoDB", bad_date not in mongo_codes and missing_exp not in mongo_codes and len(mongo_codes) == 2, mongo_codes)

        # Atomic issuance regression: directly call the production helper N+1 times.
        from routes.coupons import bind_db, issue_coupon_for_registration
        bind_db(db)
        issued = []
        for idx in range(3):
            issued.append(await issue_coupon_for_registration(f"91894299{marker[-4:]}{idx}", source))
        issued_codes = [c.get("code") for c in issued if c]
        check(
            "atomic N+1 issuance returns 2 distinct issued coupons then None",
            len(issued_codes) == 2 and len(set(issued_codes)) == 2 and issued[2] is None and all(c.get("status") == "issued" for c in issued if c),
            {"issued": issued},
        )

        inv_r = requests.get(f"{INTERNAL_API_BASE}/admin/coupons/inventory", headers=headers, params={"source_code": source}, timeout=20)
        issued_r = requests.get(f"{INTERNAL_API_BASE}/admin/coupons/issued", headers=headers, params={"source_code": source}, timeout=20)
        inv_data = inv_r.json()
        issued_data = issued_r.json()
        check(
            "inventory endpoint shape/counts after issuance",
            isinstance(inv_data.get("inventory"), list) and isinstance(inv_data.get("totals"), dict) and inv_data["totals"].get("issued") == 2 and inv_data["totals"].get("available", 0) == 0,
            inv_data,
        )
        check(
            "issued endpoint shape/counts after issuance",
            isinstance(issued_data.get("issued"), list) and issued_data.get("total") == 2 and sorted([c["code"] for c in issued_data["issued"]]) == sorted(issued_codes),
            issued_data,
        )

        # WhatsApp new-user regression with a fresh custom source and one coupon.
        wa_code = f"BV42_{marker}_WA_CODE"
        wa_csv = make_csv([[f"BV42_{marker}_WABrand", wa_code, "555", "2028-12-31"]])
        wa_upload = requests.post(
            f"{INTERNAL_API_BASE}/admin/coupons/bulk-upload",
            headers=headers,
            data={"source_code": wa_source, "dry_run": "false"},
            files={"file": ("coupon_wa.csv", wa_csv, "text/csv")},
            timeout=30,
        )
        check("WhatsApp seed coupon uploaded", wa_upload.status_code == 200 and wa_upload.json().get("summary", {}).get("imported") == 1, wa_upload.json())
        phone = phones[0]
        webhook_payload = {
            "events": {"eventType": "USER EVENTS"},
            "eventContent": {
                "message": {
                    "from": phone,
                    "messageType": "text",
                    "profileName": f"BV42 User {marker}",
                    "text": {"body": f"Hi! Register me for CP67 Loyalty | {wa_source}"},
                }
            },
        }
        wh = requests.post(f"{INTERNAL_API_BASE}/whatsapp/webhook", json=webhook_payload, timeout=20)
        evidence["webhook_response"] = {"status": wh.status_code, "body": wh.json() if wh.headers.get("content-type", "").startswith("application/json") else wh.text}
        check("webhook accepted new-user registration", wh.status_code == 200, evidence["webhook_response"])

        outbound_log = None
        issued_coupon_doc = None
        deadline = time.time() + 90
        while time.time() < deadline:
            outbound_log = await db.whatsapp_logs.find_one({
                "user_phone": phone,
                "direction": "outbound",
                "content": {"$regex": "Welcome Coupon Unlocked"},
            }, {"_id": 0})
            issued_coupon_doc = await db.coupon_codes.find_one({"source_code": wa_source, "code": wa_code}, {"_id": 0})
            if outbound_log and issued_coupon_doc and issued_coupon_doc.get("status") == "issued":
                break
            await asyncio.sleep(2)
        content = (outbound_log or {}).get("content", "")
        check(
            "WhatsApp welcome log contains coupon brand/code/value",
            bool(outbound_log) and "Welcome Coupon Unlocked" in content and wa_code in content and f"BV42_{marker}_WABrand" in content and "₹555" in content,
            outbound_log,
        )
        check(
            "WhatsApp registration atomically issued seeded coupon",
            issued_coupon_doc is not None and issued_coupon_doc.get("status") == "issued" and issued_coupon_doc.get("issued_to_phone") == phone,
            issued_coupon_doc,
        )

    finally:
        await cleanup(db, marker, phones)
        remaining = await db.coupon_codes.count_documents({"$or": [
            {"source_code": {"$regex": f"^SRC_RETEST_42_{marker}"}},
            {"code": {"$regex": f"^BV42_{marker}"}},
        ]})
        remaining_logs = await db.whatsapp_logs.count_documents({"user_phone": {"$in": phones}})
        evidence["cleanup"] = {"remaining_coupons": remaining, "remaining_whatsapp_logs": remaining_logs}
        evidence["passed"] = not evidence["failures"] and remaining == 0 and remaining_logs == 0
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(evidence, indent=2, default=str))
        client.close()
        print(json.dumps(evidence, indent=2, default=str))
        if not evidence["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())