"""
Iteration 79 — Backend regression + Point 49 (Fix Brand category resolution).

Tests:
- Point 49: earn_points looks up brand category from db.brands (case-insensitive)
            and posts the resolved category (e.g. "Dining") in the TagnPay payload.
- Point 49 fallback: brand not in db.brands -> category defaults to "Shopping".
- Point 45 RBAC regression: appmgr -> role app_manager, billop -> role bill_operator.
- Regression: /admin/login, /admin/me, /admin/users (super_admin),
  /api/consumer/{home,wallet,profile,tier-info,bills} all return 200.

Point 49 method-level tests hit the tagnpay_client.earn_points code path directly
with httpx.AsyncClient patched to capture the outgoing payload — no real TagnPay
traffic. db writes go against the same MongoDB the backend service uses.
"""
import os
import sys
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
BASE_URL = BASE_URL.rstrip("/")

SUPER_ADMIN = {"username": "admin", "password": "CP67Admin@2025"}
APP_MGR = {"username": "appmgr", "password": "AppMgr@2025"}
BILL_OP = {"username": "billop", "password": "BillOp@2025"}
CONSUMER_PHONE = "9876543210"
CONSUMER_OTP = "1234"

sys.path.insert(0, "/app/backend")


# ---------- fixtures ----------

@pytest.fixture(scope="session")
def super_admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login", json=SUPER_ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def consumer_token():
    r = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp",
                      json={"phone": CONSUMER_PHONE, "otp": CONSUMER_OTP}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def seeded_dining_brand(super_admin_token):
    """Insert (idempotent) TEST_SagarRatnaTest brand w/ category=Dining."""
    hdr = {"Authorization": f"Bearer {super_admin_token}"}
    brand_name = "TEST_SagarRatnaTest"
    # cleanup any prior
    r = requests.get(f"{BASE_URL}/api/admin/brands", headers=hdr, timeout=30)
    if r.status_code == 200:
        for b in r.json().get("brands", []):
            if b.get("brand_name", "").lower() == brand_name.lower():
                bid = b.get("id")
                if bid:
                    requests.delete(f"{BASE_URL}/api/admin/brands/{bid}", headers=hdr, timeout=30)
    # create fresh
    r = requests.post(f"{BASE_URL}/api/admin/brands", headers=hdr,
                      json={"brand_name": brand_name, "atv": 500, "category": "Dining"},
                      timeout=30)
    assert r.status_code == 200, f"create brand failed: {r.status_code} {r.text}"
    yield brand_name
    # teardown
    r = requests.get(f"{BASE_URL}/api/admin/brands", headers=hdr, timeout=30)
    if r.status_code == 200:
        for b in r.json().get("brands", []):
            if b.get("brand_name", "").lower() == brand_name.lower():
                bid = b.get("id")
                if bid:
                    requests.delete(f"{BASE_URL}/api/admin/brands/{bid}", headers=hdr, timeout=30)


# ---------- Point 49: category lookup ----------

def _run_earn_points_capture(brand_name):
    """
    Directly invoke tagnpay_client.earn_points with httpx.AsyncClient patched,
    returning the captured `data` payload sent to /api/earn-points/.
    """
    import importlib
    server = importlib.import_module("server")

    captured = {}

    class FakeResp:
        status_code = 200
        def json(self):
            return {"success": True, "points": 10}

    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, data=None, files=None, **kw):
            captured["url"] = url
            captured["data"] = data
            captured["headers"] = headers
            return FakeResp()

    async def go():
        # short-circuit get_token to skip real TagnPay auth
        with patch.object(server.tagnpay_client, "get_token", new=AsyncMock(return_value="fake-token")):
            with patch.object(server.httpx, "AsyncClient", FakeClient):
                return await server.tagnpay_client.earn_points(
                    mobile_number="9478933434",
                    bill_amount=250.0,
                    bill_number="TEST-BN-001",
                    bill_date="2026-01-15",
                    store_name=brand_name,
                    bill_image_base64=None,
                )

    result = asyncio.run(go())
    return result, captured


def test_point49_category_resolved_from_db(seeded_dining_brand):
    brand = seeded_dining_brand  # "TEST_SagarRatnaTest" w/ category=Dining
    # Run both invocations in the SAME event loop (motor client is loop-bound
    # via the module-level `db` handle, so asyncio.run twice breaks the DB
    # cursor with "Event loop is closed"). This is a test-harness quirk only.
    import importlib
    server = importlib.import_module("server")

    captured_runs = []

    class FakeResp:
        status_code = 200
        def json(self): return {"success": True, "points": 10}

    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, data=None, files=None, **kw):
            captured_runs.append({"url": url, "data": data})
            return FakeResp()

    async def go_both():
        with patch.object(server.tagnpay_client, "get_token",
                          new=AsyncMock(return_value="fake-token")):
            with patch.object(server.httpx, "AsyncClient", FakeClient):
                r1 = await server.tagnpay_client.earn_points(
                    mobile_number="9478933434", bill_amount=250.0,
                    bill_number="TEST-BN-001", bill_date="2026-01-15",
                    store_name=brand, bill_image_base64=None)
                r2 = await server.tagnpay_client.earn_points(
                    mobile_number="9478933434", bill_amount=250.0,
                    bill_number="TEST-BN-002", bill_date="2026-01-15",
                    store_name=brand.lower(), bill_image_base64=None)
                return r1, r2

    r1, r2 = asyncio.run(go_both())
    assert r1.get("success") and r2.get("success"), f"earn_points failed: {r1} {r2}"
    assert captured_runs[0]["data"]["brand"] == brand
    assert captured_runs[0]["data"]["category"] == "Dining", \
        f"Expected category=Dining from db.brands lookup, got {captured_runs[0]['data']}"
    assert captured_runs[1]["data"]["category"] == "Dining", \
        f"case-insensitive lookup broken: {captured_runs[1]['data']}"


def test_point49_fallback_shopping_when_brand_missing():
    brand = "TEST_NoSuchBrand_ZZZ_9999"
    result, cap = _run_earn_points_capture(brand)
    assert result.get("success"), f"earn_points failed: {result}"
    assert cap["data"]["brand"] == brand
    assert cap["data"]["category"] == "Shopping", \
        f"Expected fallback Shopping, got {cap['data'].get('category')}"


def test_point49_signature_unchanged():
    """earn_points signature must still accept the same positional/keyword params
    used by _reprocess_single_bill and WhatsApp/consumer bill flows."""
    import importlib, inspect
    server = importlib.import_module("server")
    sig = inspect.signature(server.tagnpay_client.earn_points)
    params = list(sig.parameters.keys())
    # method signature (self implicit on bound method — not in params)
    expected = ["mobile_number", "bill_amount", "bill_number", "bill_date",
                "store_name", "bill_image_base64"]
    for p in expected:
        assert p in params, f"earn_points signature broke; missing param {p}. Got: {params}"


# ---------- Point 45 RBAC regression ----------

def test_point45_app_manager_role():
    r = requests.post(f"{BASE_URL}/api/admin/login", json=APP_MGR, timeout=30)
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    me = requests.get(f"{BASE_URL}/api/admin/me",
                      headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert me.status_code == 200
    assert me.json().get("role") == "app_manager", me.json()


def test_point45_bill_operator_role():
    r = requests.post(f"{BASE_URL}/api/admin/login", json=BILL_OP, timeout=30)
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    me = requests.get(f"{BASE_URL}/api/admin/me",
                      headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert me.status_code == 200
    assert me.json().get("role") == "bill_operator", me.json()


# ---------- Regression ----------

def test_regression_admin_users(super_admin_token):
    r = requests.get(f"{BASE_URL}/api/admin/users",
                     headers={"Authorization": f"Bearer {super_admin_token}"}, timeout=30)
    assert r.status_code == 200, r.text


def test_regression_consumer_endpoints(consumer_token):
    hdr = {"Authorization": f"Bearer {consumer_token}"}
    for e in ("home", "wallet", "profile", "tier-info", "bills"):
        r = requests.get(f"{BASE_URL}/api/consumer/{e}", headers=hdr, timeout=30)
        assert r.status_code == 200, f"/consumer/{e} -> {r.status_code}: {r.text[:200]}"


def test_regression_bills_admin(super_admin_token):
    r = requests.get(f"{BASE_URL}/api/bills",
                     headers={"Authorization": f"Bearer {super_admin_token}"}, timeout=30)
    assert r.status_code == 200, r.text
