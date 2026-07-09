"""Iteration 27 - Backend regression for camera bridge fix.
Only tests backend endpoints (Android JS bridge is FE-only)."""
import os
import io
import time
import requests
import pytest

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')


@pytest.fixture(scope="module")
def consumer_token():
    r = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": "9876543210"})
    assert r.status_code == 200, r.text
    r = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp",
                      json={"phone": "9876543210", "otp": "1234"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"username": "admin", "password": "CP67Admin@2025"})
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("access_token") or j.get("token")


# --- Consumer bill upload regression ---
def test_bill_upload_endpoint(consumer_token):
    unique = str(time.time_ns()).encode()
    files = {'file': ('bill.jpg', io.BytesIO(b'\xff\xd8\xff\xe0' + unique + os.urandom(300)), 'image/jpeg')}
    r = requests.post(f"{BASE_URL}/api/consumer/bills/upload",
                      headers={"Authorization": f"Bearer {consumer_token}"},
                      files=files)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "bill_id" in data or "bill" in data or "message" in data


# --- Active campaigns regression ---
def test_active_campaigns_shape():
    r = requests.get(f"{BASE_URL}/api/consumer/campaigns/active")
    assert r.status_code == 200
    data = r.json()
    assert "campaigns" in data
    assert isinstance(data["campaigns"], list)


# --- Admin edit-brand endpoint shape (fake bill id -> expect 404) ---
def test_edit_brand_404_for_fake_bill(admin_token):
    r = requests.post(
        f"{BASE_URL}/api/admin/bills/nonexistent_bill_id_TEST_iter27/edit-brand",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"new_store_name": "TestBrandXYZ"}
    )
    # Fake id -> expect 404 (not 500) as per request
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
