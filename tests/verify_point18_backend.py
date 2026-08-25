#!/usr/bin/env python3
"""
Focused verification for Point 18 bill reprocess queue behavior.
Creates isolated test bills/users, exercises fast queued reprocess, legacy wait=true,
edit-brand queued regression, and bulk reprocess dry-run/start/status.
"""
import asyncio
import base64
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

PREVIEW_URL = os.environ.get("PREVIEW_URL", "https://staff-points-engine.preview.emergentagent.com")
API = PREVIEW_URL.rstrip("/") + "/api"
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "CP67Admin@2025")

ROOT = Path("/app")
load_dotenv(ROOT / "backend" / ".env")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "test_database")

# Tiny 1x1 PNG data URL to keep DB payload small; enough for the Fundle upload code path.
TINY_PNG = "data:image/png;base64," + base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
).decode()


def iso_now():
    return datetime.now(timezone.utc).isoformat()


async def main():
    run_id = "p18qa_" + uuid.uuid4().hex[:8]
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    created_bill_ids = []
    created_user_ids = []
    results = {"run_id": run_id, "api": API, "checks": []}

    async def add_check(name, ok, details):
        results["checks"].append({"name": name, "ok": bool(ok), "details": details})
        print(("PASS" if ok else "FAIL") + f" {name}: {details}")

    async def seed_bill(status="pending_review", store_name="QA Unknown Brand", phone_suffix=None):
        user_id = "user_" + run_id + "_" + uuid.uuid4().hex[:5]
        bill_id = "bill_" + run_id + "_" + uuid.uuid4().hex[:5]
        phone_suffix = phone_suffix or str(7000000000 + int(uuid.uuid4().int % 99999999)).zfill(10)[-10:]
        phone = "91" + phone_suffix
        bill_no = "P18-" + uuid.uuid4().hex[:8]
        user = {
            "id": user_id,
            "phone": phone,
            "name": "QA Point18",
            "loyalty_id": "QA" + uuid.uuid4().hex[:8],
            "customer_type": "new",
            "balance_points": 0,
            "total_earned_points": 0,
            "created_at": iso_now(),
            "registration_time": iso_now(),
            "kyc_status": False,
            "fundle_registered": False,
        }
        bill = {
            "id": bill_id,
            "user_id": user_id,
            "user_phone": phone,
            "store_name": store_name,
            "bill_no": bill_no,
            "bill_no_normalized": "".join(ch.lower() for ch in bill_no if ch.isalnum()),
            "bill_date": datetime.now().strftime("%Y-%m-%d"),
            "amount": 1234.0,
            "tax": 0,
            "status": status,
            "points_issued": 0,
            "image_url": TINY_PNG,
            "image_hash": "hash_" + uuid.uuid4().hex,
            "ocr_confidence": 0.85,
            "ocr_raw_data": {"store_name": store_name, "bill_no": bill_no, "amount": 1234, "is_valid_bill": True},
            "rejection_reason": "QA seeded unknown brand for Point 18 reprocess",
            "created_at": iso_now(),
        }
        await db.users.insert_one(user)
        await db.bills.insert_one(bill)
        created_user_ids.append(user_id)
        created_bill_ids.append(bill_id)
        return bill_id, user_id

    try:
        async with httpx.AsyncClient(timeout=90.0) as hx:
            login = await hx.post(f"{API}/admin/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
            await add_check("admin_login", login.status_code == 200 and login.json().get("token"), {"status": login.status_code, "body": login.text[:300]})
            token = login.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            # 1) Main Point 18: default reprocess must return queued in <3s and mark DB start fields.
            bill_id, user_id = await seed_bill(status="pending_review", store_name="QA Unknown Brand P18")
            t0 = time.perf_counter()
            resp = await hx.post(f"{API}/bills/{bill_id}/reprocess", headers=headers)
            elapsed = time.perf_counter() - t0
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"raw": resp.text}
            started_doc = await db.bills.find_one({"id": bill_id}, {"_id": 0})
            await add_check(
                "single_reprocess_fast_queued_response",
                resp.status_code == 200 and elapsed < 3 and body.get("success") is True and body.get("reprocessed") == "queued" and body.get("bill_id") == bill_id,
                {"status": resp.status_code, "elapsed_sec": round(elapsed, 3), "body": body},
            )
            await add_check(
                "single_reprocess_started_fields_persisted",
                bool(started_doc.get("reprocessing_started_at")) and started_doc.get("reprocessing_by") == "admin",
                {"reprocessing_started_at": started_doc.get("reprocessing_started_at"), "reprocessing_by": started_doc.get("reprocessing_by")},
            )

            # Poll DB and GET /bills up to 25s for approved force-credit fallback.
            approved_doc = None
            list_seen = None
            doc = None
            poll_start = time.perf_counter()
            while time.perf_counter() - poll_start < 25:
                doc = await db.bills.find_one({"id": bill_id}, {"_id": 0})
                list_resp = await hx.get(f"{API}/bills?status=approved&limit=100", headers=headers)
                if list_resp.status_code == 200:
                    list_seen = next((b for b in list_resp.json().get("bills", []) if b.get("id") == bill_id), None)
                if doc and doc.get("status") == "approved" and (doc.get("points_issued") or 0) > 0 and doc.get("reprocessing_finished_at"):
                    approved_doc = doc
                    break
                await asyncio.sleep(2)
            await add_check(
                "single_reprocess_approved_within_25s",
                approved_doc is not None,
                {
                    "final_status": (approved_doc or doc or {}).get("status"),
                    "points_issued": (approved_doc or doc or {}).get("points_issued"),
                    "force_credited": (approved_doc or doc or {}).get("force_credited"),
                    "reprocessing_finished_at": (approved_doc or doc or {}).get("reprocessing_finished_at"),
                    "seen_in_get_bills_approved": bool(list_seen),
                    "elapsed_poll_sec": round(time.perf_counter() - poll_start, 1),
                    "rejection_reason": (approved_doc or doc or {}).get("rejection_reason"),
                },
            )

            # 2) Legacy sync path wait=true: should run synchronously and return success/points_earned.
            sync_bill_id, _ = await seed_bill(status="pending_review", store_name="QA Unknown Brand P18 Sync")
            t0 = time.perf_counter()
            sync_resp = await hx.post(f"{API}/bills/{sync_bill_id}/reprocess?wait=true", headers=headers)
            sync_elapsed = time.perf_counter() - t0
            sync_body = sync_resp.json() if sync_resp.headers.get("content-type", "").startswith("application/json") else {"raw": sync_resp.text}
            sync_doc = await db.bills.find_one({"id": sync_bill_id}, {"_id": 0})
            await add_check(
                "legacy_wait_true_sync_success",
                sync_resp.status_code == 200 and sync_body.get("success") is True and sync_body.get("points_earned", 0) > 0 and sync_doc.get("status") == "approved",
                {"status": sync_resp.status_code, "elapsed_sec": round(sync_elapsed, 3), "body": sync_body, "db_status": sync_doc.get("status"), "db_points": sync_doc.get("points_issued"), "force_credited": sync_doc.get("force_credited")},
            )

            # 3) Regression: edit-brand queued should also return fast and eventually approve.
            edit_bill_id, _ = await seed_bill(status="pending_review", store_name="QA Bad Brand Before Edit")
            t0 = time.perf_counter()
            edit_resp = await hx.post(
                f"{API}/admin/bills/{edit_bill_id}/edit-brand",
                headers={**headers, "Content-Type": "application/json"},
                json={"new_store_name": "QA Edited Unknown Brand", "reprocess": True, "auto_force_credit_on_fundle_reject": True},
            )
            edit_elapsed = time.perf_counter() - t0
            edit_body = edit_resp.json() if edit_resp.headers.get("content-type", "").startswith("application/json") else {"raw": edit_resp.text}
            await add_check(
                "edit_brand_queued_fast_response",
                edit_resp.status_code == 200 and edit_elapsed < 3 and edit_body.get("success") is True and edit_body.get("reprocessed") == "queued",
                {"status": edit_resp.status_code, "elapsed_sec": round(edit_elapsed, 3), "body": edit_body},
            )
            edit_doc = None
            edit_start = time.perf_counter()
            while time.perf_counter() - edit_start < 25:
                edit_doc = await db.bills.find_one({"id": edit_bill_id}, {"_id": 0})
                if edit_doc and edit_doc.get("status") == "approved" and (edit_doc.get("points_issued") or 0) > 0:
                    break
                await asyncio.sleep(2)
            await add_check(
                "edit_brand_background_eventual_approval",
                edit_doc and edit_doc.get("status") == "approved" and (edit_doc.get("points_issued") or 0) > 0,
                {"status": (edit_doc or {}).get("status"), "points": (edit_doc or {}).get("points_issued"), "force_credited": (edit_doc or {}).get("force_credited"), "store_name": (edit_doc or {}).get("store_name")},
            )

            # 4) Bulk regression: dry-run should include candidate; run should create job and status endpoint should respond.
            bulk_bill_id, _ = await seed_bill(status="manual_review", store_name="QA Bulk Unknown Brand")
            today = datetime.now().strftime("%Y-%m-%d")
            bulk_payload = {"from_date": today, "to_date": today, "statuses": ["manual_review"], "re_ocr": False, "send_whatsapp": False, "force_credit": False, "force_credit_on_fundle_reject": True, "dry_run": True, "limit": 500}
            bulk_dry = await hx.post(f"{API}/admin/bills/bulk-reprocess", headers={**headers, "Content-Type": "application/json"}, json=bulk_payload)
            bulk_dry_body = bulk_dry.json() if bulk_dry.headers.get("content-type", "").startswith("application/json") else {"raw": bulk_dry.text}
            dry_has_candidate = any(b.get("id") == bulk_bill_id for b in bulk_dry_body.get("bills", []))
            await add_check(
                "bulk_reprocess_dry_run_candidate",
                bulk_dry.status_code == 200 and dry_has_candidate,
                {"status": bulk_dry.status_code, "candidates": bulk_dry_body.get("candidates"), "has_seed_candidate": dry_has_candidate},
            )
            bulk_payload["dry_run"] = False
            t0 = time.perf_counter()
            bulk_start = await hx.post(f"{API}/admin/bills/bulk-reprocess", headers={**headers, "Content-Type": "application/json"}, json=bulk_payload)
            bulk_start_elapsed = time.perf_counter() - t0
            bulk_start_body = bulk_start.json() if bulk_start.headers.get("content-type", "").startswith("application/json") else {"raw": bulk_start.text}
            job_id = bulk_start_body.get("job_id")
            await add_check(
                "bulk_reprocess_starts_background_job",
                bulk_start.status_code == 200 and bool(job_id) and bulk_start_elapsed < 3,
                {"status": bulk_start.status_code, "elapsed_sec": round(bulk_start_elapsed, 3), "body": bulk_start_body},
            )
            if job_id:
                status_resp = None
                status_body = {}
                bulk_doc = None
                bulk_poll_start = time.perf_counter()
                while time.perf_counter() - bulk_poll_start < 25:
                    status_resp = await hx.get(f"{API}/admin/bills/bulk-reprocess/{job_id}/status", headers=headers)
                    status_body = status_resp.json() if status_resp.headers.get("content-type", "").startswith("application/json") else {"raw": status_resp.text}
                    bulk_doc = await db.bills.find_one({"id": bulk_bill_id}, {"_id": 0})
                    if status_body.get("status") == "completed" and bulk_doc and bulk_doc.get("status") == "approved":
                        break
                    await asyncio.sleep(2)
                await add_check(
                    "bulk_reprocess_status_endpoint_and_completion",
                    status_resp.status_code == 200
                    and (status_body.get("job_id") == job_id or status_body.get("id") == job_id)
                    and status_body.get("status") == "completed"
                    and bulk_doc
                    and bulk_doc.get("status") == "approved"
                    and (bulk_doc.get("points_issued") or 0) > 0,
                    {"status": status_resp.status_code, "body": status_body, "db_status": (bulk_doc or {}).get("status"), "db_points": (bulk_doc or {}).get("points_issued"), "force_credited": (bulk_doc or {}).get("force_credited")},
                )

        ok = all(c["ok"] for c in results["checks"])
        results["overall_ok"] = ok
    finally:
        # Keep enough evidence fields in report, but remove test-created users/bills to avoid polluting preview.
        cleanup = {"bills_deleted": 0, "users_deleted": 0}
        if created_bill_ids:
            r = await db.bills.delete_many({"id": {"$in": created_bill_ids}})
            cleanup["bills_deleted"] = r.deleted_count
        if created_user_ids:
            r = await db.users.delete_many({"id": {"$in": created_user_ids}})
            cleanup["users_deleted"] = r.deleted_count
        results["cleanup"] = cleanup
        client.close()
        out = Path("/app/test_reports/point18_backend_verification.json")
        out.write_text(json.dumps(results, indent=2))
        print("WROTE", out)
        print(json.dumps(results, indent=2))
    return 0 if results.get("overall_ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))