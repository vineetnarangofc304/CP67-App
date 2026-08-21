"""Iteration 51 — verification of Point 38 & 39 fixes against the PUBLIC preview URL.

Point 38: /api/admin/bills/<id>/edit-brand must never return "Incorrect padding"
          for bills whose image_url is a broken data: URL, a legacy base64: blob
          or a raw http(s) Karix URL.
Point 39: /api/bills/<id>/image must null out placeholder (<200 char) data: URLs
          and return a descriptive fetch_error, while still serving legitimate
          long data: URLs untouched.
Regression: /api/admin/alerts/test still returns whatsapp + sms per phone.
"""
import asyncio
import base64
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env["REACT_APP_BACKEND_URL"]).rstrip("/")

backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = backend_env["MONGO_URL"]
DB_NAME = backend_env["DB_NAME"]

# A real 1x1 JPEG, repeated padding to exceed the 200-char placeholder threshold
_REAL_JPEG = base64.b64encode(bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300"
    + "10" * 64
) + b"\x00" * 400).decode()
LONG_DATA_URL = "data:image/jpeg;base64," + _REAL_JPEG


def _db():
    return AsyncIOMotorClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"username": "admin", "password": "CP67Admin@2025"}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token")
    assert tok, f"no token in login response: {r.text[:300]}"
    return tok


@pytest.fixture(scope="module")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def seeded_bills():
    """Seed bills covering every image_url storage variant + cleanup."""
    ids = {
        "broken_data": f"TEST_i51_broken_{uuid.uuid4().hex[:6]}",
        "legacy_b64": f"TEST_i51_legacyb64_{uuid.uuid4().hex[:6]}",
        "http_url": f"TEST_i51_httpurl_{uuid.uuid4().hex[:6]}",
        "good_data": f"TEST_i51_gooddata_{uuid.uuid4().hex[:6]}",
    }
    docs = [
        {"id": ids["broken_data"], "image_url": "data:image/png;"},
        {"id": ids["legacy_b64"], "image_url": "base64:iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"},
        {"id": ids["http_url"], "image_url": "https://invalid-karix-host-does-not-exist.example.com/media/xyz.jpg"},
        {"id": ids["good_data"], "image_url": LONG_DATA_URL},
    ]

    async def _seed():
        db = _db()
        for d in docs:
            d.update({
                "user_id": "TEST_i51_user",
                "user_phone": "919876543210",
                "bill_no": f"TB-{uuid.uuid4().hex[:6]}",
                "bill_no_normalized": uuid.uuid4().hex[:8],
                "store_name": "Zara",
                "amount": "500.0",
                "status": "manual_review",
                "created_at": "2026-07-01T00:00:00+00:00",
            })
            await db.bills.insert_one(dict(d))

    async def _cleanup():
        db = _db()
        await db.bills.delete_many({"id": {"$in": list(ids.values())}})

    asyncio.get_event_loop().run_until_complete(_seed())
    yield ids
    asyncio.get_event_loop().run_until_complete(_cleanup())


# ── Point 38: edit-brand must not crash on undecodable images ───────────────

@pytest.mark.parametrize("variant", ["broken_data", "legacy_b64", "http_url", "good_data"])
def test_edit_brand_never_returns_incorrect_padding(client, seeded_bills, variant):
    bill_id = seeded_bills[variant]
    r = client.post(f"{BASE_URL}/api/admin/bills/{bill_id}/edit-brand",
                    json={"new_store_name": "Adidas", "wait_for_result": True}, timeout=120)
    assert r.status_code == 200, f"{variant}: HTTP {r.status_code} {r.text[:400]}"
    data = r.json()
    blob = str(data).lower()
    assert "incorrect padding" not in blob, f"{variant}: padding error leaking -> {data}"
    assert "invalid base64" not in blob, f"{variant}: base64 error leaking -> {data}"
    print(f"[{variant}] edit-brand -> {str(data)[:300]}")


def test_edit_brand_on_real_preview_bill_TEST_1c0d66220b(client):
    """The exact bill reported by the client (image_url='data:image/png;base64,AAA')."""
    r = client.post(f"{BASE_URL}/api/admin/bills/TEST-1c0d66220b/edit-brand",
                    json={"new_store_name": "Adidas", "wait_for_result": True}, timeout=120)
    if r.status_code == 404:
        pytest.skip("TEST-1c0d66220b no longer present in preview DB")
    assert r.status_code == 200, f"HTTP {r.status_code} {r.text[:400]}"
    data = r.json()
    assert "incorrect padding" not in str(data).lower(), f"padding error leaking -> {data}"
    print(f"[TEST-1c0d66220b] edit-brand -> {str(data)[:400]}")


def test_edit_brand_persists_new_brand(client, seeded_bills):
    bill_id = seeded_bills["broken_data"]
    client.post(f"{BASE_URL}/api/admin/bills/{bill_id}/edit-brand",
                json={"new_store_name": "Puma", "wait_for_result": True}, timeout=120)

    async def _get():
        return await _db().bills.find_one({"id": bill_id}, {"_id": 0})

    doc = asyncio.get_event_loop().run_until_complete(_get())
    assert doc is not None
    assert doc.get("store_name") == "Puma", f"brand not persisted: {doc.get('store_name')}"


# ── Point 39: /bills/<id>/image placeholder detection ───────────────────────

def test_image_endpoint_nulls_short_placeholder_data_url(client, seeded_bills):
    r = client.get(f"{BASE_URL}/api/bills/{seeded_bills['broken_data']}/image", timeout=30)
    assert r.status_code == 200, f"HTTP {r.status_code} {r.text[:300]}"
    data = r.json()
    assert data.get("image_url") is None, f"placeholder not nulled: {str(data.get('image_url'))[:80]}"
    assert "placeholder" in (data.get("fetch_error") or "").lower(), f"missing fetch_error: {data}"


def test_image_endpoint_serves_legitimate_long_data_url(client, seeded_bills):
    r = client.get(f"{BASE_URL}/api/bills/{seeded_bills['good_data']}/image", timeout=30)
    assert r.status_code == 200, f"HTTP {r.status_code} {r.text[:300]}"
    data = r.json()
    assert data.get("image_url"), f"legit image was dropped: {data}"
    assert data["image_url"].startswith("data:image/jpeg;base64,"), data["image_url"][:60]
    assert not data.get("fetch_error"), f"false placeholder flag: {data.get('fetch_error')}"


def test_image_endpoint_real_preview_placeholder_bill(client):
    r = client.get(f"{BASE_URL}/api/bills/TEST-1c0d66220b/image", timeout=30)
    if r.status_code == 404:
        pytest.skip("TEST-1c0d66220b not present")
    assert r.status_code == 200, f"HTTP {r.status_code} {r.text[:300]}"
    data = r.json()
    assert data.get("image_url") is None, "placeholder should be nulled"
    assert "placeholder" in (data.get("fetch_error") or "").lower(), data


def test_image_endpoint_unknown_bill_returns_404(client):
    r = client.get(f"{BASE_URL}/api/bills/TEST_i51_does_not_exist/image", timeout=30)
    assert r.status_code == 404, f"expected 404, got {r.status_code} {r.text[:200]}"


def test_image_endpoint_requires_auth():
    r = requests.get(f"{BASE_URL}/api/bills/TEST-1c0d66220b/image", timeout=30)
    assert r.status_code in (401, 403), f"unauthenticated access allowed: {r.status_code}"


# ── Regression: Point 36 alerts test still returns whatsapp + sms ───────────

def test_alerts_test_returns_whatsapp_and_sms(client):
    r = client.post(f"{BASE_URL}/api/admin/alerts/test", json={}, timeout=90)
    assert r.status_code == 200, f"HTTP {r.status_code} {r.text[:300]}"
    data = r.json()
    results = data.get("results") or data.get("details") or []
    assert results, f"no per-phone results: {str(data)[:400]}"
    for entry in results:
        blob = str(entry).lower()
        assert "whatsapp" in blob, f"missing whatsapp channel: {entry}"
        assert "sms" in blob, f"missing sms channel: {entry}"
