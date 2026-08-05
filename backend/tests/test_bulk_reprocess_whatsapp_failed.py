"""Regression tests for Bulk Reprocess WhatsApp-failed bills fix.

Covers:
1. Bills with rejection_reason starting with 'WhatsApp bill processing failed'
   are auto-forced to re-OCR (no more silent 'skipped').
2. Bills with no downloadable image -> action='no_image' (not 'skipped').
3. amount>0 + no bill_no => synthetic bill_no 'WA-...' generated + goes to Fundle.
4. Job status summary contains 'no_image' bucket.
5. user_id drift falls back to user_phone (10-digit and 91XXX).
6. data:image URL with re_ocr=False still triggers re-OCR when rejection_reason
   matches WhatsApp-failed pattern.
"""
import os
import time
import uuid
import base64
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
# Backend .env
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"

ADMIN_USER = "admin"
ADMIN_PASS = "CP67Admin@2025"

# Minimal valid JPEG (1x1 grey) - OCR will fail on this, produces "manual_review"
BROKEN_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAr/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwB/AAf/2Q=="
)


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def test_user(mongo):
    """Create a test consumer user, and make sure the drift-fallback test can find
    them by phone even when user_id doesn't match."""
    phone = "919876543210"
    user = mongo.users.find_one({"phone": {"$in": [phone, phone[2:]]}})
    if not user:
        user = {
            "id": f"TEST-USER-{uuid.uuid4()}",
            "phone": phone,
            "name": "TEST Bulk Reprocess User",
            "balance_points": 0,
            "total_earned_points": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        mongo.users.insert_one(user)
    return user


@pytest.fixture
def stub_bills(mongo, test_user):
    """Inserts 5 stub bills covering all edge cases; yields list of bill IDs; cleans up after."""
    now = datetime.now(timezone.utc).isoformat()
    today_date = datetime.now().strftime("%Y-%m-%d")
    phone = test_user["phone"]

    bills = [
        # 1. WhatsApp-failed, no image_url at all -> expect action='no_image'
        {
            "id": f"TEST-BR-{uuid.uuid4()}",
            "user_id": test_user["id"],
            "user_phone": phone,
            "status": "manual_review",
            "rejection_reason": "WhatsApp bill processing failed: no media",
            "image_url": "",
            "amount": 0,
            "bill_no": "",
            "store_name": "TEST Store A",
            "created_at": now,
            "bill_date": today_date,
        },
        # 2. WhatsApp-failed, HTTP url that will 404 -> expect action='no_image' w/ error
        {
            "id": f"TEST-BR-{uuid.uuid4()}",
            "user_id": test_user["id"],
            "user_phone": phone,
            "status": "manual_review",
            "rejection_reason": "WhatsApp bill processing failed: media download error",
            "image_url": "https://httpstat.us/404",
            "amount": 0,
            "bill_no": "",
            "store_name": "TEST Store B",
            "created_at": now,
            "bill_date": today_date,
        },
        # 3. WhatsApp-failed, data:image with broken 1px JPEG -> OCR fails -> manual_review
        {
            "id": f"TEST-BR-{uuid.uuid4()}",
            "user_id": test_user["id"],
            "user_phone": phone,
            "status": "manual_review",
            "rejection_reason": "WhatsApp bill processing failed: OCR none",
            "image_url": f"data:image/jpeg;base64,{BROKEN_JPEG_B64}",
            "amount": 0,
            "bill_no": "",
            "store_name": "TEST Store C",
            "created_at": now,
            "bill_date": today_date,
        },
        # 4. amount>0 & no bill_no -> synthetic WA-... generated & sent to Fundle
        #    Fundle mock will return 0 pts -> action='kept_pending' (NOT skipped)
        {
            "id": f"TEST-BR-{uuid.uuid4()}",
            "user_id": test_user["id"],
            "user_phone": phone,
            "status": "manual_review",
            "rejection_reason": "WhatsApp bill processing failed: partial OCR",
            "image_url": f"data:image/jpeg;base64,{BROKEN_JPEG_B64}",
            "amount": 1500,
            "bill_no": "",
            "store_name": "TEST Store D",
            "created_at": now,
            "bill_date": today_date,
        },
        # 5. user_id drift: bad user_id but valid user_phone -> phone-fallback should work
        {
            "id": f"TEST-BR-{uuid.uuid4()}",
            "user_id": "NON-EXISTENT-USER-DRIFT",
            "user_phone": phone[2:],  # 10-digit format to test both lookups
            "status": "manual_review",
            "rejection_reason": "WhatsApp bill processing failed: legacy",
            "image_url": "",
            "amount": 0,
            "bill_no": "",
            "store_name": "TEST Store E",
            "created_at": now,
            "bill_date": today_date,
        },
    ]
    mongo.bills.insert_many(bills)
    ids = [b["id"] for b in bills]
    yield ids
    # Cleanup
    mongo.bills.delete_many({"id": {"$in": ids}})


def _wait_for_job(headers, job_id, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        r = requests.get(f"{BASE_URL}/api/admin/bills/bulk-reprocess/{job_id}/status",
                         headers=headers, timeout=15)
        assert r.status_code == 200, f"status poll failed: {r.status_code} {r.text}"
        j = r.json()
        if j.get("status") == "completed":
            return j
        time.sleep(2)
    pytest.fail(f"Job {job_id} did not finish within {timeout}s")


def test_dry_run_returns_candidates(headers, stub_bills):
    """Dry run should list our stubs without mutating anything."""
    r = requests.post(
        f"{BASE_URL}/api/admin/bills/bulk-reprocess",
        headers=headers,
        json={"statuses": ["manual_review", "pending_review"], "dry_run": True, "limit": 500},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    got_ids = {b["id"] for b in body["bills"]}
    # All our stubs must appear (subset check — DB may have other bills)
    missing = set(stub_bills) - got_ids
    assert not missing, f"stubs missing from dry-run: {missing}"


def test_bulk_reprocess_whatsapp_failed_flow(headers, stub_bills, mongo):
    """End-to-end: run bulk reprocess, poll status, verify each stub's outcome."""
    # Start job — only target our stub bill IDs by using created_at boundary is tricky,
    # so we just run against manual_review and filter results by our IDs.
    r = requests.post(
        f"{BASE_URL}/api/admin/bills/bulk-reprocess",
        headers=headers,
        json={
            "statuses": ["manual_review"],
            "dry_run": False,
            "re_ocr": False,   # deliberately False — auto-force logic should still kick in
            "send_whatsapp": False,
            "limit": 500,
        },
        timeout=30,
    )
    assert r.status_code == 200, r.text
    job = r.json()
    job_id = job["job_id"]

    final = _wait_for_job(headers, job_id, timeout=180)

    # (4) summary contains 'no_image' bucket
    assert "no_image" in final["summary"], f"summary missing no_image: {final['summary']}"

    # Build map of results by bill_id (results capped to last 200; our 5 should fit)
    res_by_id = {r["bill_id"]: r for r in final.get("results", []) if r.get("bill_id") in stub_bills}
    assert len(res_by_id) == len(stub_bills), \
        f"missing results for some stubs: got {list(res_by_id.keys())}, expected {stub_bills}"

    b1, b2, b3, b4, b5 = stub_bills

    # (1) empty image_url -> no_image
    assert res_by_id[b1]["action"] == "no_image", res_by_id[b1]
    # (2) 404 URL -> no_image with error mentioning HTTP or download
    assert res_by_id[b2]["action"] == "no_image", res_by_id[b2]
    err2 = (res_by_id[b2].get("error") or "").lower()
    assert ("http" in err2 or "download" in err2 or "not available" in err2), \
        f"expected download-error hint, got: {res_by_id[b2].get('error')}"
    # (3) broken image, OCR fails -> manual_review (NOT skipped, NOT no_image because image existed)
    assert res_by_id[b3]["action"] == "manual_review", res_by_id[b3]
    # (4) amount>0 + no bill_no -> synthetic bill_no + goes to Fundle -> kept_pending (mock returns 0)
    assert res_by_id[b4]["action"] in ("kept_pending", "approved"), res_by_id[b4]
    assert res_by_id[b4]["action"] != "skipped"
    b4_doc = mongo.bills.find_one({"id": b4}, {"_id": 0})
    assert b4_doc.get("synthetic_bill_no") is True, f"synthetic_bill_no flag missing: {b4_doc}"
    assert (b4_doc.get("bill_no") or "").startswith("WA-"), f"bill_no not WA-*: {b4_doc.get('bill_no')}"
    # (5) user_id drift -> phone fallback -> not 'skipped'
    assert res_by_id[b5]["action"] != "skipped", \
        f"phone-fallback failed: {res_by_id[b5]}"

    # No stub should be silently 'skipped' (the core bug we're fixing)
    skipped_stubs = [bid for bid, r in res_by_id.items() if r["action"] == "skipped"]
    assert not skipped_stubs, f"Found bills silently skipped (regression!): {skipped_stubs}"

    # DB state: bill (1) rejection_reason should mention 'image not available'
    b1_doc = mongo.bills.find_one({"id": b1}, {"_id": 0})
    assert "image not available" in (b1_doc.get("rejection_reason") or "").lower(), \
        f"unexpected reason for b1: {b1_doc.get('rejection_reason')}"

    # DB state: bill (2) reason should include download error hint (HTTP 4xx / err text)
    b2_doc = mongo.bills.find_one({"id": b2}, {"_id": 0})
    r2 = (b2_doc.get("rejection_reason") or "").lower()
    assert "image not available" in r2, f"unexpected reason for b2: {r2}"
