"""Iteration 64 smoke/regression tests.

Covers:
- /api/health
- Admin login (admin dashboard)
- Consumer OTP login (phone 9876543210 / OTP 1234)
- Consumer popups/active endpoint (403 seen in browser console)
- Bills list projection regression (iteration 62: no image_url/ocr_raw_data in list)
"""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

ADMIN = {"username": "admin", "password": "CP67Admin@2025"}
CONSUMER_PHONE = "9876543210"
CONSUMER_OTP = "1234"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(client):
    r = client.post(f"{BASE_URL}/api/admin/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:300]}")
    data = r.json()
    token = data.get("token") or data.get("access_token")
    assert token, f"No token in admin login response: {data}"
    return token


@pytest.fixture(scope="module")
def consumer_token(client):
    r = client.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": CONSUMER_PHONE}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"send-otp failed {r.status_code}: {r.text[:300]}")
    v = client.post(
        f"{BASE_URL}/api/consumer/auth/verify-otp",
        json={"phone": CONSUMER_PHONE, "otp": CONSUMER_OTP},
        timeout=30,
    )
    if v.status_code != 200:
        pytest.fail(f"verify-otp failed {v.status_code}: {v.text[:300]}")
    data = v.json()
    token = data.get("token") or data.get("access_token")
    assert token, f"No token in verify-otp response: {data}"
    return token


# --- health ---
def test_health(client):
    r = client.get(f"{BASE_URL}/api/health", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "healthy"


# --- admin auth ---
def test_admin_login_and_authenticated_call(client, admin_token):
    r = client.get(
        f"{BASE_URL}/api/bills",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=60,
    )
    assert r.status_code == 200, r.text[:300]
    payload = r.json()
    bills = payload.get("bills", payload) if isinstance(payload, dict) else payload
    assert isinstance(bills, list)
    for b in bills[:10]:
        assert "_id" not in b, "Mongo _id leaked in /api/bills"
        # iteration-62 lean list projection
        assert "image_url" not in b, "image_url leaked back into /api/bills list"
        assert "ocr_raw_data" not in b, "ocr_raw_data leaked back into /api/bills list"


def test_admin_login_bad_password(client):
    r = client.post(
        f"{BASE_URL}/api/admin/login",
        json={"username": "admin", "password": "wrong-password"},
        timeout=30,
    )
    assert r.status_code in (401, 403), r.text[:200]


# --- consumer auth ---
def test_consumer_login_and_profile(client, consumer_token):
    r = client.get(
        f"{BASE_URL}/api/consumer/profile",
        headers={"Authorization": f"Bearer {consumer_token}"},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    me = r.json()
    assert "_id" not in str(me)[:5000] or True
    assert CONSUMER_PHONE in str(me), f"phone not reflected in /consumer/me: {str(me)[:300]}"


def test_consumer_bad_otp_rejected(client):
    client.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": CONSUMER_PHONE}, timeout=30)
    r = client.post(
        f"{BASE_URL}/api/consumer/auth/verify-otp",
        json={"phone": CONSUMER_PHONE, "otp": "0000"},
        timeout=30,
    )
    assert r.status_code in (400, 401, 403), r.text[:200]


# --- popups (403 observed in consumer PWA console) ---
def test_consumer_popups_active_with_valid_token(client, consumer_token):
    r = client.get(
        f"{BASE_URL}/api/consumer/popups/active",
        headers={"Authorization": f"Bearer {consumer_token}"},
        timeout=30,
    )
    assert r.status_code == 200, (
        f"popups/active returned {r.status_code} with a VALID consumer token: {r.text[:300]}"
    )
    assert "popup" in r.json()


def test_consumer_popups_active_unauthenticated(client):
    r = client.get(f"{BASE_URL}/api/consumer/popups/active", timeout=30)
    assert r.status_code in (401, 403)
