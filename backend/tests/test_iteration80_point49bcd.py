"""
Iteration 80 — Backend regression + Point 49 (b/c/d) features:
  - 49-b: /api/bills/{id}/image/stream returns raw bytes (auth-gated).
  - 49-c: brand mirror flag on /api/bills and /api/bills/pending-review;
          /api/admin/bills/brand-audit endpoint.
  - 49-a: _reprocess_single_bill brand-variants retry (original -> Title -> UPPER).
  - 49-d: POST /api/admin/bills/{id}/push-to-fundle (happy + guards).
  - Regression: admin/consumer endpoints still 200; /bills/{id}/image (JSON) still works.

Mocking pattern: patch server.tagnpay_client.earn_points with AsyncMock so we
never hit real Fundle. In-process calls use asyncio.run once per test to share
motor's event loop.
"""
import os
import sys
import uuid
import asyncio
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Read from frontend/.env for pytest runs where env var isn't propagated
    try:
        with open("/app/frontend/.env") as _f:
            for _line in _f:
                if _line.strip().startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = _line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except Exception:
        pass
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
BASE_URL = BASE_URL.rstrip("/")

SUPER_ADMIN = {"username": "admin", "password": "CP67Admin@2025"}
APP_MGR = {"username": "appmgr", "password": "AppMgr@2025"}
BILL_OP = {"username": "billop", "password": "BillOp@2025"}
CONSUMER_PHONE = "9876543210"
CONSUMER_OTP = "1234"

sys.path.insert(0, "/app/backend")


def _reset_motor_client():
    """motor's AsyncIOMotorClient is bound to the event loop it was created on.
    Since each test calls asyncio.run (fresh loop), we must rebuild `server.db`
    to attach it to the current loop before doing any motor I/O."""
    import importlib
    from motor.motor_asyncio import AsyncIOMotorClient
    server = importlib.import_module("server")
    mongo_url = os.environ.get("MONGO_URL") or _read_backend_env("MONGO_URL")
    db_name = os.environ.get("DB_NAME") or _read_backend_env("DB_NAME")
    client = AsyncIOMotorClient(mongo_url)
    server.db = client[db_name]
    return server


def _read_backend_env(key):
    try:
        with open("/app/backend/.env") as f:
            for line in f:
                if line.strip().startswith(f"{key}="):
                    return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        return None
    return None


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def super_admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login", json=SUPER_ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_hdr(super_admin_token):
    return {"Authorization": f"Bearer {super_admin_token}"}


@pytest.fixture(scope="session")
def consumer_token():
    r = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp",
                      json={"phone": CONSUMER_PHONE, "otp": CONSUMER_OTP}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]["id"]


@pytest.fixture(scope="session")
def seeded_audit_brand(admin_hdr):
    brand_name = "TEST_BrandAuditX"
    # cleanup prior if any
    r = requests.get(f"{BASE_URL}/api/admin/brands", headers=admin_hdr, timeout=30)
    if r.status_code == 200:
        for b in r.json().get("brands", []):
            if (b.get("brand_name") or "").lower() == brand_name.lower():
                if b.get("id"):
                    requests.delete(f"{BASE_URL}/api/admin/brands/{b['id']}", headers=admin_hdr, timeout=30)
    r = requests.post(f"{BASE_URL}/api/admin/brands", headers=admin_hdr,
                      json={"brand_name": brand_name, "atv": 500, "category": "Dining"}, timeout=30)
    assert r.status_code == 200, f"seed brand failed: {r.status_code} {r.text}"
    yield brand_name
    r = requests.get(f"{BASE_URL}/api/admin/brands", headers=admin_hdr, timeout=30)
    if r.status_code == 200:
        for b in r.json().get("brands", []):
            if (b.get("brand_name") or "").lower() == brand_name.lower():
                if b.get("id"):
                    requests.delete(f"{BASE_URL}/api/admin/brands/{b['id']}", headers=admin_hdr, timeout=30)


# ============================================================
# 49-b: STREAMING ENDPOINT
# ============================================================

def test_stream_image_requires_auth():
    r = requests.get(f"{BASE_URL}/api/bills/TEST-OBJSTORE-01/image/stream", timeout=30)
    assert r.status_code in (401, 403), f"expected 401/403 unauth, got {r.status_code}: {r.text[:200]}"


def test_stream_image_with_admin_returns_bytes(admin_hdr):
    r = requests.get(f"{BASE_URL}/api/bills/TEST-OBJSTORE-01/image/stream",
                     headers=admin_hdr, timeout=30)
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
    ctype = r.headers.get("content-type", "")
    assert ctype.startswith("image/"), f"unexpected content-type {ctype}"
    assert len(r.content) > 0, "empty body"


def test_stream_image_404_on_unknown_id(admin_hdr):
    r = requests.get(f"{BASE_URL}/api/bills/DOES-NOT-EXIST-XYZ/image/stream",
                     headers=admin_hdr, timeout=30)
    assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"


def test_legacy_json_image_endpoint_still_works(admin_hdr):
    """Backward-compat: /api/bills/{id}/image JSON endpoint."""
    r = requests.get(f"{BASE_URL}/api/bills/TEST-OBJSTORE-01/image",
                     headers=admin_hdr, timeout=30)
    assert r.status_code == 200, f"legacy JSON image broke: {r.status_code} {r.text[:200]}"
    # Should return JSON containing image_url or bytes reference
    try:
        j = r.json()
        assert ("image_url" in j) or ("image" in j) or ("data" in j), f"unexpected shape: {list(j)[:5]}"
    except ValueError:
        # some routes return bytes directly — still OK
        assert len(r.content) > 0


# ============================================================
# 49-c: brand_in_mirror flag + brand-audit endpoint
# ============================================================

def test_bills_list_has_brand_in_mirror_flag(admin_hdr):
    r = requests.get(f"{BASE_URL}/api/bills?limit=5", headers=admin_hdr, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    bills = j.get("bills", [])
    if not bills:
        pytest.skip("no bills to test brand_in_mirror flag")
    for b in bills:
        assert "brand_in_mirror" in b, f"missing brand_in_mirror on bill {b.get('id')}"
        assert isinstance(b["brand_in_mirror"], bool), \
            f"brand_in_mirror not bool: {type(b['brand_in_mirror'])}"


def test_pending_review_list_has_brand_in_mirror_flag(admin_hdr):
    r = requests.get(f"{BASE_URL}/api/bills/pending-review", headers=admin_hdr, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    bills = j if isinstance(j, list) else (j.get("bills") or j.get("items") or [])
    for b in bills[:5]:
        assert "brand_in_mirror" in b, f"missing brand_in_mirror: keys={list(b)[:10]}"


def test_brand_audit_endpoint_shape(admin_hdr, seeded_audit_brand):
    r = requests.get(f"{BASE_URL}/api/admin/bills/brand-audit?limit=10",
                     headers=admin_hdr, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("total_scanned", "total_missing", "bills"):
        assert k in j, f"missing {k} in brand-audit response: {list(j)}"
    assert isinstance(j["bills"], list)
    # Every returned bill's store_name should NOT be in the mirror.
    # Seeded brand IS in mirror -> should NOT appear here.
    seeded = seeded_audit_brand.lower().replace("_", "")
    import re as _re
    def norm(s): return _re.sub(r"[^a-z0-9]+", "", (s or "").lower())
    seeded_key = norm(seeded_audit_brand)
    for b in j["bills"]:
        assert norm(b.get("store_name", "")) != seeded_key, \
            f"seeded brand should NOT appear in brand-audit missing list: {b}"


def test_brand_in_mirror_true_when_store_matches_seeded(admin_hdr, seeded_audit_brand):
    """Insert a temp bill with store_name = seeded brand, verify brand_in_mirror=true."""
    import importlib
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    server = _reset_motor_client()

    tmp_id = f"TEST-MIRROR-{uuid.uuid4().hex[:8]}"

    async def go():
        # Clear the cache so newly-seeded brand is included
        server._BRAND_MIRROR_CACHE["expires_at"] = 0.0
        server._BRAND_MIRROR_CACHE["names"] = set()
        await server.db.bills.insert_one({
            "id": tmp_id, "user_id": "testuser", "user_phone": "9999999999",
            "store_name": seeded_audit_brand, "amount": 100.0, "status": "approved",
            "points_issued": 5, "created_at": datetime.now(timezone.utc).isoformat(),
        })
        mirror = await server._brand_names_norm()
        in_mirror = server._brand_in_mirror(seeded_audit_brand, mirror)
        not_in = server._brand_in_mirror("XX_NONEXISTENT_ZZZ_" + uuid.uuid4().hex[:6], mirror)
        # cleanup
        await server.db.bills.delete_one({"id": tmp_id})
        return in_mirror, not_in

    in_mirror, not_in = asyncio.run(go())
    assert in_mirror is True, "seeded brand should be in mirror"
    assert not_in is False, "unknown brand should NOT be in mirror"


# ============================================================
# 49-a: brand variants retry in _reprocess_single_bill
# ============================================================

def test_reprocess_brand_variants_retry_upper_accepted(admin_hdr, consumer_token):
    """Patch earn_points to reject original, reject Title, accept UPPER.
    Verify: earn_points called with UPPER variant AND bill.store_name persisted as UPPER."""
    import importlib
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    server = _reset_motor_client()
    token, user_id = consumer_token

    tmp_id = f"TEST-VAR-{uuid.uuid4().hex[:8]}"
    original_name = "sagar ratna"
    today_str = datetime.now().strftime("%Y-%m-%d")
    calls = []

    async def fake_earn(*, mobile_number, bill_amount, bill_number, bill_date,
                        store_name, bill_image_base64=None, **kw):
        calls.append(store_name)
        if store_name == store_name.upper() and store_name != store_name.title():
            return {"success": True, "data": {"earned_points": 42, "message": "ok"}}
        # Return a brand-mismatch error to trigger next variant
        return {"success": False, "error": "brand not found", "data": {"message": "brand mismatch"}}

    # Point registration flow uses get_customer_points then register_customer.
    async def fake_get_pts(mobile_number):
        return {"success": True, "data": {"points": 0}}

    async def go():
        await server.db.bills.insert_one({
            "id": tmp_id, "user_id": user_id, "user_phone": CONSUMER_PHONE,
            "store_name": original_name, "amount": 250.0, "status": "manual_review",
            "bill_no": "BN-VAR-01", "bill_date": today_str,
            "image_url": "", "created_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            bill = await server.db.bills.find_one({"id": tmp_id})
            from fastapi import BackgroundTasks
            bg = BackgroundTasks()
            with patch.object(server.tagnpay_client, "earn_points", new=AsyncMock(side_effect=fake_earn)):
                with patch.object(server.tagnpay_client, "get_customer_points",
                                  new=AsyncMock(side_effect=fake_get_pts)):
                    res = await server._reprocess_single_bill(
                        bill, re_ocr=False, send_whatsapp_flag=False,
                        background_tasks=bg,
                    )
            updated = await server.db.bills.find_one({"id": tmp_id})
            return res, updated
        finally:
            await server.db.bills.delete_one({"id": tmp_id})
            # revert user balance changes made by reprocess
            await server.db.users.update_one(
                {"id": user_id}, {"$inc": {"balance_points": 0}}  # noop placeholder
            )

    res, updated = asyncio.run(go())
    print("reprocess result:", res)
    print("calls:", calls)
    print("store_name after:", updated.get("store_name") if updated else None)
    # Assert earn_points was called at least twice (original -> ... -> UPPER)
    assert any(c == original_name.upper() for c in calls), f"UPPER variant never tried, calls={calls}"
    # First call should be the original name
    assert calls[0] == original_name, f"first call should be original, got {calls}"
    # store_name should have been updated to UPPER
    assert (updated or {}).get("store_name") == original_name.upper(), \
        f"store_name not persisted to UPPER variant: {updated.get('store_name') if updated else None}"


# ============================================================
# 49-d: push-to-fundle
# ============================================================

def _login_get_admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login", json=SUPER_ADMIN, timeout=30)
    return r.json()["token"]


def test_push_to_fundle_happy_path(consumer_token):
    """force_credited bill w/ points_issued=50 → Fundle returns 120 → delta +70 to user.
    Invoked in-process (patch.object on the running backend process would not
    apply to a separate HTTP call, so we drive push_bill_to_fundle directly)."""
    import importlib
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    server = _reset_motor_client()
    _, user_id = consumer_token

    tmp_id = f"TEST-PUSH-{uuid.uuid4().hex[:8]}"

    async def go():
        u = await server.db.users.find_one({"id": user_id}, {"_id": 0, "balance_points": 1, "total_earned_points": 1})
        bp0 = int((u or {}).get("balance_points") or 0)
        tp0 = int((u or {}).get("total_earned_points") or 0)
        await server.db.bills.insert_one({
            "id": tmp_id, "user_id": user_id, "user_phone": CONSUMER_PHONE,
            "store_name": "TestPushStore", "amount": 500.0, "status": "approved",
            "bill_no": "BN-PUSH-01", "bill_date": "2026-01-15",
            "image_url": "", "force_credited": True, "points_issued": 50,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            fake_earn = AsyncMock(return_value={"success": True, "data": {"earned_points": 120, "message": "ok"}})
            with patch.object(server.tagnpay_client, "earn_points", new=fake_earn):
                resp = await server.push_bill_to_fundle(tmp_id, payload={"username": "admin"})
            b = await server.db.bills.find_one({"id": tmp_id}, {"_id": 0})
            u2 = await server.db.users.find_one({"id": user_id},
                {"_id": 0, "balance_points": 1, "total_earned_points": 1})
            return bp0, tp0, resp, b, u2, fake_earn.await_args
        finally:
            # revert balance +70 and drop bill
            await server.db.users.update_one({"id": user_id},
                {"$inc": {"balance_points": -70, "total_earned_points": -70}})
            await server.db.bills.delete_one({"id": tmp_id})

    bp0, tp0, resp, b, u2, earn_call = asyncio.run(go())
    print("resp:", resp)
    print("earn call kwargs:", earn_call.kwargs if earn_call else None)
    assert resp.success is True, resp
    assert resp.fundle_points == 120, resp
    assert resp.delta_points == 70, resp
    assert b.get("force_credited") is False, b
    assert b.get("fundle_pushed_at"), b
    assert b.get("points_issued") == 120, b
    assert int(u2.get("balance_points") or 0) == bp0 + 70, \
        f"balance expected {bp0+70}, got {u2.get('balance_points')}"
    assert int(u2.get("total_earned_points") or 0) == tp0 + 70


def test_push_to_fundle_failure_zero_points(consumer_token):
    """Patch earn_points to return 0 → response.success=false, bill unchanged."""
    import importlib
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    server = _reset_motor_client()
    _, user_id = consumer_token

    tmp_id = f"TEST-PUSHF-{uuid.uuid4().hex[:8]}"

    async def go():
        await server.db.bills.insert_one({
            "id": tmp_id, "user_id": user_id, "user_phone": CONSUMER_PHONE,
            "store_name": "ZStore", "amount": 200.0, "status": "approved",
            "bill_no": "BN-PUSHF-01", "bill_date": "2026-01-15",
            "image_url": "", "force_credited": True, "points_issued": 20,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            fake_earn = AsyncMock(return_value={"success": False, "error": "rejected",
                                                "data": {"earned_points": 0, "message": "no match"}})
            with patch.object(server.tagnpay_client, "earn_points", new=fake_earn):
                resp = await server.push_bill_to_fundle(tmp_id, payload={"username": "admin"})
            b = await server.db.bills.find_one({"id": tmp_id}, {"_id": 0})
            return resp, b
        finally:
            await server.db.bills.delete_one({"id": tmp_id})

    resp, b = asyncio.run(go())
    assert resp.success is False, resp
    assert resp.fundle_points == 0, resp
    # bill unchanged
    assert b.get("force_credited") is True, b
    assert not b.get("fundle_pushed_at"), b
    assert b.get("points_issued") == 20, b


def test_push_to_fundle_guards(admin_hdr, consumer_token):
    """Guards: non-force-credited -> 400; already pushed -> 400; unknown id -> 404."""
    import importlib
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    server = _reset_motor_client()
    _, user_id = consumer_token

    tmp_non_fc = f"TEST-PUSHG-NFC-{uuid.uuid4().hex[:6]}"
    tmp_pushed = f"TEST-PUSHG-PSH-{uuid.uuid4().hex[:6]}"

    async def setup():
        await server.db.bills.insert_one({
            "id": tmp_non_fc, "user_id": user_id, "user_phone": CONSUMER_PHONE,
            "store_name": "S", "amount": 100.0, "status": "approved",
            "force_credited": False, "points_issued": 10,
        })
        await server.db.bills.insert_one({
            "id": tmp_pushed, "user_id": user_id, "user_phone": CONSUMER_PHONE,
            "store_name": "S", "amount": 100.0, "status": "approved",
            "force_credited": True, "points_issued": 10,
            "fundle_pushed_at": datetime.now(timezone.utc).isoformat(),
        })

    async def cleanup():
        srv2 = _reset_motor_client()
        await srv2.db.bills.delete_many({"id": {"$in": [tmp_non_fc, tmp_pushed]}})

    asyncio.run(setup())
    try:
        # (a) non-force-credited
        r = requests.post(f"{BASE_URL}/api/admin/bills/{tmp_non_fc}/push-to-fundle",
                          headers=admin_hdr, timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"

        # (b) already pushed
        r = requests.post(f"{BASE_URL}/api/admin/bills/{tmp_pushed}/push-to-fundle",
                          headers=admin_hdr, timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"

        # (c) unknown id
        r = requests.post(f"{BASE_URL}/api/admin/bills/UNKNOWN-{uuid.uuid4().hex[:6]}/push-to-fundle",
                          headers=admin_hdr, timeout=30)
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"
    finally:
        asyncio.run(cleanup())


# ============================================================
# Regression
# ============================================================

def test_regression_admin_endpoints(admin_hdr):
    for path in ("/api/admin/me", "/api/admin/users", "/api/bills"):
        r = requests.get(f"{BASE_URL}{path}", headers=admin_hdr, timeout=30)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"


def test_regression_consumer_endpoints(consumer_token):
    token, _ = consumer_token
    hdr = {"Authorization": f"Bearer {token}"}
    for e in ("home", "wallet", "profile", "tier-info"):
        r = requests.get(f"{BASE_URL}/api/consumer/{e}", headers=hdr, timeout=30)
        assert r.status_code == 200, f"/consumer/{e} -> {r.status_code}: {r.text[:200]}"
