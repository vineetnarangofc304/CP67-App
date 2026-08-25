#!/usr/bin/env python3
"""Focused bug verification for CP67 feedback points 11, 16, 17 on preview.
Creates ephemeral Mongo seed data and cleans it up.
"""
import base64
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://staff-points-engine.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
ADMIN_USER = "admin"
ADMIN_PASS = "CP67Admin@2025"
CONSUMER_PHONE = "9876543210"
CONSUMER_OTP = "1234"
RUN_ID = f"BUGVERIFY_{int(time.time())}_{uuid.uuid4().hex[:8]}"

# Tiny valid JPEG (1x1-ish), plus test salts after EOI for unique hashes.
TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707"
    "070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c"
    "1c2837292c30313434341f27393d38323c2e333432ffc0000b080001000101011100"
    "ffc4001f0000010501010101010100000000000000000102030405060708090a0bff"
    "c400b5100002010303020403050504040000017d01020300041105122131410613516107"
    "227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a"
    "3435363738393a434445464748494a535455565758595a636465666768696a737475"
    "767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4"
    "b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9ea"
    "f1f2f3f4f5f6f7f8f9faffda0008010100003f00fbd0ffd9"
)

results = []
cleanup_ids = []
cleanup_hashes = []
client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
db = client[DB_NAME]


def record(name, ok, detail="", data=None):
    row = {"name": name, "ok": bool(ok), "detail": detail}
    if data is not None:
        row["data"] = data
    results.append(row)
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {detail}")


def unique_jpeg(label):
    return TINY_JPEG + f"\n{RUN_ID}:{label}:{time.time_ns()}".encode()


def login_admin():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=20)
    assert r.status_code == 200, f"admin login failed {r.status_code}: {r.text[:300]}"
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"admin token missing: {r.text[:300]}"
    return token


def login_consumer():
    r1 = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": CONSUMER_PHONE}, timeout=20)
    assert r1.status_code == 200, f"send-otp failed {r1.status_code}: {r1.text[:300]}"
    r2 = requests.post(
        f"{BASE_URL}/api/consumer/auth/verify-otp",
        json={"phone": CONSUMER_PHONE, "otp": CONSUMER_OTP}, timeout=20,
    )
    assert r2.status_code == 200, f"verify-otp failed {r2.status_code}: {r2.text[:300]}"
    body = r2.json()
    token = body.get("token") or body.get("access_token")
    user = body.get("user") or {}
    assert token, f"consumer token missing: {body}"
    user_id = user.get("id") or user.get("sub")
    if not user_id:
        # Fallback to DB lookup for seeded test user.
        user_doc = db.users.find_one({"phone": {"$in": [CONSUMER_PHONE, "91" + CONSUMER_PHONE]}}, {"_id": 0, "id": 1, "phone": 1})
        assert user_doc and user_doc.get("id"), f"cannot resolve user id for {CONSUMER_PHONE}"
        user_id = user_doc["id"]
        user = user_doc
    return token, user_id, user


def normalize_bill_no(bill_no):
    import re
    return re.sub(r"[^A-Za-z0-9]+", "", str(bill_no)).lower() if bill_no else ""


def local_duplicate_check(image_hash, bill_no, store_name):
    existing = db.bills.find_one({"image_hash": image_hash, "status": {"$ne": "rejected"}}, {"_id": 0, "id": 1})
    if existing:
        return True
    if bill_no and store_name:
        norm = normalize_bill_no(bill_no)
        if norm:
            existing = db.bills.find_one({
                "$or": [
                    {"bill_no_normalized": norm, "store_name": store_name, "status": {"$ne": "rejected"}},
                    {"bill_no": bill_no, "store_name": store_name, "status": {"$ne": "rejected"}},
                ]
            }, {"_id": 0, "id": 1, "bill_no": 1, "bill_no_normalized": 1})
            return bool(existing)
    return False


def cleanup():
    ids = list(set(cleanup_ids))
    hashes = list(set(cleanup_hashes))
    q = {"$or": []}
    if ids:
        q["$or"].append({"id": {"$in": ids}})
    if hashes:
        q["$or"].append({"image_hash": {"$in": hashes}})
    q["$or"].append({"test_run_id": RUN_ID})
    q["$or"].append({"id": {"$regex": f"^{RUN_ID}"}})
    try:
        deleted = db.bills.delete_many(q).deleted_count
        print(f"Cleanup deleted {deleted} test bill(s).")
    except Exception as e:
        print(f"Cleanup error: {e}")


def main():
    # Verify DB reachable before seeding.
    client.admin.command("ping")
    admin_token = login_admin()
    consumer_token, user_id, user = login_consumer()
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    consumer_headers_json = {"Authorization": f"Bearer {consumer_token}", "Content-Type": "application/json"}
    consumer_headers = {"Authorization": f"Bearer {consumer_token}"}
    print(f"Using user_id={user_id}, run_id={RUN_ID}, base={BASE_URL}")

    try:
        # POINT 11: JSON base64 endpoint accepts data URL and returns required shape.
        img = unique_jpeg("point11_base64")
        cleanup_hashes.append(hashlib.md5(img).hexdigest())
        data_url = "data:image/jpeg;base64," + base64.b64encode(img).decode()
        r = requests.post(f"{BASE_URL}/api/consumer/bills/upload-base64", headers=consumer_headers_json,
                          json={"image_base64": data_url}, timeout=40)
        ok = r.status_code == 200 and r.json().get("success") is True and r.json().get("bill_id") and r.json().get("status") == "processing"
        if r.status_code == 200 and r.json().get("bill_id"):
            cleanup_ids.append(r.json()["bill_id"])
        record("POINT 11 base64 data-url API upload", ok, f"status={r.status_code}, body={r.text[:250]}")

        # REGRESSION: multipart upload still works.
        img2 = unique_jpeg("multipart")
        cleanup_hashes.append(hashlib.md5(img2).hexdigest())
        r = requests.post(f"{BASE_URL}/api/consumer/bills/upload", headers=consumer_headers,
                          files={"file": ("test.jpg", img2, "image/jpeg")}, timeout=40)
        ok = r.status_code == 200 and r.json().get("success") is True and r.json().get("bill_id")
        if r.status_code == 200 and r.json().get("bill_id"):
            cleanup_ids.append(r.json()["bill_id"])
        record("REGRESSION multipart bill upload", ok, f"status={r.status_code}, body={r.text[:250]}")

        # POINT 16: backfill and same invoice normalization duplicate detection.
        legacy_id = f"{RUN_ID}_legacy_backfill"
        db.bills.delete_many({"id": legacy_id})
        db.bills.insert_one({
            "id": legacy_id, "user_id": user_id, "user_phone": user.get("phone") or CONSUMER_PHONE,
            "store_name": "DedupTestStore", "bill_no": "LEG:123", "status": "approved",
            "image_hash": f"{RUN_ID}_legacy_hash", "test_run_id": RUN_ID,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        cleanup_ids.append(legacy_id)
        # Invoke actual app backfill helper in a subprocess to avoid event-loop/client issues.
        import subprocess
        env = os.environ.copy()
        env["MONGO_URL"] = MONGO_URL
        env["DB_NAME"] = DB_NAME
        subprocess.run([
            sys.executable, "-c",
            "import sys, asyncio; sys.path.insert(0, '/app/backend'); "
            "import server; asyncio.run(server._backfill_bill_no_normalized())"
        ], check=True, timeout=30, env=env)
        legacy = db.bills.find_one({"id": legacy_id}, {"_id": 0, "bill_no_normalized": 1})
        record("POINT 16 backfill legacy bill_no_normalized", legacy and legacy.get("bill_no_normalized") == "leg123",
               f"legacy normalized={legacy}")

        seed_id = f"{RUN_ID}_dedup_approved"
        db.bills.delete_many({"id": seed_id})
        db.bills.insert_one({
            "id": seed_id, "user_id": user_id, "user_phone": user.get("phone") or CONSUMER_PHONE,
            "store_name": "DedupTestStore", "bill_no": "INV12345", "bill_no_normalized": "inv12345",
            "bill_date": "2026-07-22", "amount": 500.0, "status": "approved", "points_issued": 5,
            "image_hash": f"{RUN_ID}_orig_hash", "test_run_id": RUN_ID,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        cleanup_ids.append(seed_id)
        # Use the app's exported server.check_duplicate_bill against seeded DB.
        script = (
            "import sys, asyncio, json; sys.path.insert(0, '/app/backend'); import server; "
            "print(asyncio.run(server.check_duplicate_bill('NEW_IMAGE_HASH_BUGVERIFY', 'INV:12345', 'DedupTestStore')))"
        )
        proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30, env=env)
        server_dup_true = proc.returncode == 0 and proc.stdout.strip().splitlines()[-1] == "True"
        local_dup_true = local_duplicate_check("NEW_IMAGE_HASH_BUGVERIFY", "INV:12345", "DedupTestStore") is True
        local_other_false = local_duplicate_check("NEW_IMAGE_HASH_BUGVERIFY2", "INV:12345", "OtherStore") is False
        record("POINT 16 normalized duplicate check INV12345 vs INV:12345", server_dup_true and local_dup_true and local_other_false,
               f"server_stdout={proc.stdout.strip()}, stderr={proc.stderr.strip()[:200]}, local_dup={local_dup_true}, other_store={local_other_false}")

        # POINT 17: seed pending bill, edit brand queues reprocess and auto-force-credits after fallback.
        before_user = db.users.find_one({"id": user_id}, {"_id": 0, "balance_points": 1, "total_earned_points": 1}) or {}
        bill17_id = f"{RUN_ID}_point17"
        img17 = unique_jpeg("point17")
        image_url = "data:image/jpeg;base64," + base64.b64encode(img17).decode()
        db.bills.delete_many({"id": bill17_id})
        db.bills.insert_one({
            "id": bill17_id, "user_id": user_id, "user_phone": user.get("phone") or CONSUMER_PHONE,
            "store_name": "UnknownBrandXYZ", "bill_no": f"TEST17-{int(time.time())}", "bill_no_normalized": normalize_bill_no(f"TEST17-{int(time.time())}"),
            "bill_date": "2026-07-22", "amount": 1500.0, "status": "pending_review", "points_issued": 0,
            "rejection_reason": "Brand not found", "image_url": image_url, "image_hash": hashlib.md5(img17).hexdigest(),
            "ocr_confidence": 0.95, "source": "bug_verify", "test_run_id": RUN_ID,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        cleanup_ids.append(bill17_id)
        start = time.time()
        r = requests.post(f"{BASE_URL}/api/admin/bills/{bill17_id}/edit-brand", headers=admin_headers,
                          json={"new_store_name": "AlsoUnknownBrand", "reprocess": True,
                                "auto_force_credit_on_fundle_reject": True}, timeout=10)
        elapsed = time.time() - start
        queued_ok = r.status_code == 200 and r.json().get("reprocessed") == "queued" and elapsed < 3
        record("POINT 17 edit-brand returns fast queued", queued_ok, f"elapsed={elapsed:.2f}s status={r.status_code}, body={r.text[:300]}")

        final_bill = None
        observed = []
        deadline = time.time() + 25
        while time.time() < deadline:
            gr = requests.get(f"{BASE_URL}/api/bills/{bill17_id}", headers=admin_headers, timeout=15)
            if gr.status_code == 200:
                final_bill = gr.json().get("bill") or gr.json()
                observed.append({
                    "t": round(time.time() - start, 1),
                    "status": final_bill.get("status"),
                    "points_issued": final_bill.get("points_issued"),
                    "force_credited": final_bill.get("force_credited"),
                    "rejection_reason": final_bill.get("rejection_reason"),
                })
                if final_bill.get("status") == "approved" and int(final_bill.get("points_issued") or 0) > 0 and final_bill.get("force_credited") is True and final_bill.get("rejection_reason") is None:
                    break
            time.sleep(2)
        point17_ok = bool(final_bill and final_bill.get("status") == "approved" and int(final_bill.get("points_issued") or 0) > 0 and final_bill.get("force_credited") is True and final_bill.get("rejection_reason") is None)
        record("POINT 17 background force-credit outcome", point17_ok, f"observed={observed[-6:]}")
        # Roll back points if force-credit incremented test user's balance before deleting bill.
        if point17_ok:
            pts = int(final_bill.get("points_issued") or 0)
            if pts:
                db.users.update_one({"id": user_id}, {"$inc": {"balance_points": -pts, "total_earned_points": -pts}})
                record("Cleanup point17 user point rollback", True, f"rolled back {pts} points; before={before_user}")

        # REGRESSION: specified endpoints still work.
        reg_checks = []
        for name, method, url, headers in [
            ("consumer app-settings", "GET", f"{BASE_URL}/api/consumer/app-settings", None),
            ("consumer campaigns active", "GET", f"{BASE_URL}/api/consumer/campaigns/active", None),
            ("admin app-settings", "GET", f"{BASE_URL}/api/admin/app-settings", admin_headers),
            ("qr-links", "GET", f"{BASE_URL}/api/qr-links", admin_headers),
        ]:
            rr = requests.request(method, url, headers=headers, timeout=20)
            ok2 = rr.status_code == 200
            detail = rr.text[:400]
            if name == "qr-links" and ok2:
                data = rr.json()
                text = json.dumps(data)
                ok2 = "SRC_RWA" in text and "SRC_OFFICE" in text
                detail = f"contains_SRC_RWA={ 'SRC_RWA' in text }, contains_SRC_OFFICE={ 'SRC_OFFICE' in text }, body_prefix={text[:250]}"
            reg_checks.append(ok2)
            record(f"REGRESSION {name}", ok2, f"status={rr.status_code}, {detail}")

    finally:
        cleanup()
        client.close()

    passed = sum(1 for r in results if r["ok"])
    failed = [r for r in results if not r["ok"]]
    print(json.dumps({"run_id": RUN_ID, "base_url": BASE_URL, "passed": passed, "total": len(results), "failed": failed}, indent=2))
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
