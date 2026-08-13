#!/usr/bin/env python3
"""Focused backend/E2E verification for Point 26 iteration 43.

Verifies the exact strict Expiry Date regression (compact ISO and ISO week dates
must be rejected), plus coupon issuance/inventory and WhatsApp welcome-message
regressions. This is a test artifact only; it does not modify product code.
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
REPORT = ROOT / "test_reports" / "bug_verification_43_backend_results.json"
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

API_BASE = "http://localhost:8001/api"
MONGO_URL = os.environ["MONGO_URL"].strip('"')
DB_NAME = os.environ.get("DB_NAME", "test_database")


def make_csv(rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Brand Name", "Coupon Code", "Coupon Value", "Expiry Date"])
    writer.writerows(rows)
    return buf.getvalue()


def login_token():
    r = requests.post(
        f"{API_BASE}/admin/login",
        json={"username": "admin", "password": "CP67Admin@2025"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["token"]


async def cleanup(db, marker, source, wa_phone=None, wa_code=None):
    coupon_filter = {
        "$or": [
            {"source_code": source},
            {"source_code": {"$regex": f"^SRC_STRICT_TEST_BV43_{marker}"}},
            {"source_code": {"$regex": f"^SRC_RETEST_43_{marker}"}},
            {"code": {"$regex": f"^BV43_{marker}"}},
            {"brand_name": {"$regex": f"^BV43_{marker}"}},
        ]
    }
    if wa_code:
        coupon_filter["$or"].append({"code": wa_code})
    await db.coupon_codes.delete_many(coupon_filter)
    if wa_phone:
        await db.users.delete_many({"phone": wa_phone})
        await db.whatsapp_logs.delete_many({"user_phone": wa_phone})
        await db.whatsapp_dedup.delete_many({"key": {"$regex": f"^{wa_phone}:"}})


async def main():
    marker = str(int(time.time()))[-6:] + str(random.randint(100, 999))
    source = f"SRC_STRICT_TEST_BV43_{marker}"
    wa_phone = f"918811{random.randint(100000, 999999)}"
    wa_code = f"BV43_{marker}_WA_CODE"
    wa_brand = f"BV43_{marker}_WABrand"

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    evidence = {
        "marker": marker,
        "source": source,
        "skill_lookup": "No relevant testing skill found.",
        "checks": [],
        "failures": [],
    }

    def check(name, condition, details=None):
        passed = bool(condition)
        evidence["checks"].append({"name": name, "passed": passed, "details": details})
        if not passed:
            evidence["failures"].append({"name": name, "details": details})

    try:
        await cleanup(db, marker, source, wa_phone, wa_code)
        token = login_token()
        headers = {"Authorization": f"Bearer {token}"}

        valid_a = f"BV43_{marker}_VALID_A"
        compact = f"BV43_{marker}_COMPACT_1"
        week = f"BV43_{marker}_WEEK_1"
        valid_b = f"BV43_{marker}_VALID_B"
        bad = f"BV43_{marker}_BAD_1"
        empty = f"BV43_{marker}_EMPTY_1"
        csv_body = make_csv([
            [f"BV43_{marker}_BrandValidA", valid_a, "101", "2026-12-31"],
            [f"BV43_{marker}_BrandCompact", compact, "202", "20281231"],
            [f"BV43_{marker}_BrandWeek", week, "303", "2028-W01-1"],
            [f"BV43_{marker}_BrandValidB", valid_b, "404", "2027-06-30"],
            [f"BV43_{marker}_BrandBad", bad, "505", "not-a-date"],
            [f"BV43_{marker}_BrandEmpty", empty, "606", ""],
        ])

        upload = requests.post(
            f"{API_BASE}/admin/coupons/bulk-upload",
            headers=headers,
            data={"source_code": source, "dry_run": "false"},
            files={"file": ("strict_expiry_bv43.csv", csv_body, "text/csv")},
            timeout=30,
        )
        upload_data = upload.json() if upload.headers.get("content-type", "").startswith("application/json") else {"raw": upload.text}
        evidence["strict_bulk_upload_response"] = upload_data
        summary = upload_data.get("summary", {})
        invalid_codes = sorted([x.get("code") for x in upload_data.get("invalid_preview", []) if x.get("code")])
        expected_invalid = sorted([compact, week, bad, empty])
        check("strict 6-row bulk upload returns HTTP 200", upload.status_code == 200, {"status": upload.status_code, "body": upload_data})
        check("strict upload summary imported=2 invalid=4", summary.get("imported") == 2 and summary.get("invalid") == 4, summary)
        check("invalid_preview includes compact ISO, week date, garbage, and empty-expiry codes", invalid_codes == expected_invalid, invalid_codes)

        list_r = requests.get(f"{API_BASE}/admin/coupons/list", headers=headers, params={"source_code": source}, timeout=20)
        list_data = list_r.json()
        listed_codes = sorted([c["code"] for c in list_data.get("coupons", [])])
        mongo_codes = sorted([c["code"] async for c in db.coupon_codes.find({"source_code": source}, {"_id": 0, "code": 1})])
        check("list endpoint persisted only 2 valid strict-date rows", listed_codes == sorted([valid_a, valid_b]), listed_codes)
        check("MongoDB has no compact/week/garbage/empty invalid rows", mongo_codes == sorted([valid_a, valid_b]), mongo_codes)

        # Regression 1: production helper atomically issues N coupons; N+1 returns None.
        from routes.coupons import bind_db, issue_coupon_for_registration
        bind_db(db)
        issued = []
        for idx in range(3):
            issued.append(await issue_coupon_for_registration(f"918843{marker[-6:]}{idx}", source))
        issued_codes = [c.get("code") for c in issued if c]
        check(
            "atomic issuance returns two distinct coupons then None",
            len(issued_codes) == 2 and len(set(issued_codes)) == 2 and issued[2] is None and all(c.get("status") == "issued" for c in issued if c),
            {"issued_codes": issued_codes, "third_result": issued[2]},
        )

        inv_r = requests.get(f"{API_BASE}/admin/coupons/inventory", headers=headers, params={"source_code": source}, timeout=20)
        issued_r = requests.get(f"{API_BASE}/admin/coupons/issued", headers=headers, params={"source_code": source}, timeout=20)
        inv_data = inv_r.json()
        issued_data = issued_r.json()
        check("inventory endpoint reports available=0 issued=2 after issuance", inv_data.get("totals", {}).get("available", 0) == 0 and inv_data.get("totals", {}).get("issued") == 2, inv_data)
        check("issued endpoint returns exactly the two issued coupon codes", issued_data.get("total") == 2 and sorted([c["code"] for c in issued_data.get("issued", [])]) == sorted(issued_codes), issued_data)

        # Regression 3: real WhatsApp webhook path for a new SRC_RWA user.
        await db.users.delete_many({"phone": wa_phone})
        await db.whatsapp_logs.delete_many({"user_phone": wa_phone})
        await db.whatsapp_dedup.delete_many({"key": {"$regex": f"^{wa_phone}:"}})
        wa_csv = make_csv([[wa_brand, wa_code, "777", "2028-12-31"]])
        wa_upload = requests.post(
            f"{API_BASE}/admin/coupons/bulk-upload",
            headers=headers,
            data={"source_code": "SRC_RWA", "dry_run": "false"},
            files={"file": ("rwa_coupon_bv43.csv", wa_csv, "text/csv")},
            timeout=30,
        )
        wa_upload_data = wa_upload.json() if wa_upload.headers.get("content-type", "").startswith("application/json") else {"raw": wa_upload.text}
        check("seeded one SRC_RWA coupon for WhatsApp webhook", wa_upload.status_code == 200 and wa_upload_data.get("summary", {}).get("imported") == 1, wa_upload_data)
        # Make this test coupon the oldest available SRC_RWA coupon so the FIFO issuer selects it without deleting any real inventory.
        await db.coupon_codes.update_one({"code": wa_code}, {"$set": {"created_at": "2000-01-01T00:00:00+00:00"}})

        webhook_payload = {
            "events": {"eventType": "USER EVENTS"},
            "eventContent": {
                "message": {
                    "from": wa_phone,
                    "messageType": "text",
                    "profileName": f"BV43 User {marker}",
                    "text": {"body": "Hi! Register me for CP67 Loyalty — RWA | SRC_RWA"},
                }
            },
        }
        wh = requests.post(f"{API_BASE}/whatsapp/webhook", json=webhook_payload, timeout=30)
        evidence["webhook_response"] = {"status": wh.status_code, "body": wh.json() if wh.headers.get("content-type", "").startswith("application/json") else wh.text}
        check("WhatsApp webhook accepts new SRC_RWA registration", wh.status_code == 200, evidence["webhook_response"])

        outbound_log = None
        issued_coupon_doc = None
        deadline = time.time() + 100
        while time.time() < deadline:
            outbound_log = await db.whatsapp_logs.find_one({
                "user_phone": wa_phone,
                "direction": "outbound",
                "content": {"$regex": "Welcome Coupon Unlocked"},
            }, {"_id": 0})
            issued_coupon_doc = await db.coupon_codes.find_one({"code": wa_code}, {"_id": 0})
            if outbound_log and issued_coupon_doc and issued_coupon_doc.get("status") == "issued":
                break
            await asyncio.sleep(2)
        content = (outbound_log or {}).get("content", "")
        check(
            "WhatsApp welcome_msg log appends coupon brand/code/value",
            bool(outbound_log) and "Welcome Coupon Unlocked" in content and wa_brand in content and wa_code in content and "₹777" in content,
            outbound_log,
        )
        check(
            "WhatsApp webhook issued the seeded SRC_RWA coupon to the new phone",
            issued_coupon_doc is not None and issued_coupon_doc.get("status") == "issued" and issued_coupon_doc.get("issued_to_phone") == wa_phone,
            issued_coupon_doc,
        )

    finally:
        await cleanup(db, marker, source, wa_phone, wa_code)
        remaining_coupons = await db.coupon_codes.count_documents({"$or": [
            {"source_code": source},
            {"code": {"$regex": f"^BV43_{marker}"}},
            {"code": wa_code},
        ]})
        remaining_logs = await db.whatsapp_logs.count_documents({"user_phone": wa_phone})
        remaining_user = await db.users.count_documents({"phone": wa_phone})
        evidence["cleanup"] = {"remaining_coupons": remaining_coupons, "remaining_whatsapp_logs": remaining_logs, "remaining_users": remaining_user}
        evidence["passed"] = not evidence["failures"] and remaining_coupons == 0 and remaining_logs == 0 and remaining_user == 0
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(evidence, indent=2, default=str))
        client.close()
        print(json.dumps(evidence, indent=2, default=str))
        if not evidence["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())