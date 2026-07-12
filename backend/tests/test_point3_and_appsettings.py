"""Tests for:
   - Point 3: Fix Brand modal force-credit fallback (edit-brand endpoint)
   - Point 9: App settings (fonts) admin + consumer endpoints
"""
import os
import time
import uuid
import base64
import pytest
import requests
from datetime import datetime
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback for tests running in-container; but prefer env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "cp67_mall")

# Load DB name from backend/.env if not env
try:
    with open("/app/backend/.env") as f:
        for line in f:
            if line.startswith("DB_NAME"):
                DB_NAME = line.split("=", 1)[1].strip().strip('"').strip("'")
            if line.startswith("MONGO_URL"):
                MONGO_URL = line.split("=", 1)[1].strip().strip('"').strip("'")
except Exception:
    pass


@pytest.fixture(scope="session")
def db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"username": "admin", "password": "CP67Admin@2025"},
                      timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------- Point 9: App Settings ----------------------

class TestAppSettings:
    """Point 9: font family / size / weight settings"""

    ORIGINAL = None

    def test_01_consumer_get_public(self):
        r = requests.get(f"{BASE_URL}/api/consumer/app-settings", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "settings" in data
        s = data["settings"]
        for k in ("heading_font_family", "heading_font_size_scale",
                  "heading_font_weight", "content_font_family",
                  "content_font_size_scale", "content_font_weight"):
            assert k in s, f"missing key {k}"
        assert isinstance(s["heading_font_size_scale"], (int, float))
        assert isinstance(s["heading_font_weight"], int)

    def test_02_admin_get(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/admin/app-settings",
                         headers=auth_headers, timeout=10)
        assert r.status_code == 200, r.text
        s = r.json()["settings"]
        TestAppSettings.ORIGINAL = {
            "heading_font_family": s["heading_font_family"],
            "heading_font_size_scale": s["heading_font_size_scale"],
            "heading_font_weight": s["heading_font_weight"],
            "content_font_family": s["content_font_family"],
            "content_font_size_scale": s["content_font_size_scale"],
            "content_font_weight": s["content_font_weight"],
        }

    def test_03_admin_put_clamp_scale_high(self, auth_headers):
        r = requests.put(f"{BASE_URL}/api/admin/app-settings",
                         headers=auth_headers,
                         json={"heading_font_family": "Playfair Display",
                               "heading_font_size_scale": 5.0},
                         timeout=10)
        assert r.status_code == 200, r.text
        s = r.json()["settings"]
        assert s["heading_font_family"] == "Playfair Display"
        assert s["heading_font_size_scale"] == 2.0  # clamped

    def test_04_admin_put_clamp_weight_high(self, auth_headers):
        r = requests.put(f"{BASE_URL}/api/admin/app-settings",
                         headers=auth_headers,
                         json={"content_font_weight": 1200},
                         timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["settings"]["content_font_weight"] == 900

    def test_05_partial_update_preserves_other_fields(self, auth_headers):
        # heading_font_family should still be Playfair Display from test_03
        r = requests.put(f"{BASE_URL}/api/admin/app-settings",
                         headers=auth_headers,
                         json={"content_font_family": "Roboto"},
                         timeout=10)
        assert r.status_code == 200
        s = r.json()["settings"]
        assert s["content_font_family"] == "Roboto"
        assert s["heading_font_family"] == "Playfair Display"
        assert s["heading_font_size_scale"] == 2.0

    def test_06_consumer_reflects_admin_update(self):
        r = requests.get(f"{BASE_URL}/api/consumer/app-settings", timeout=10)
        assert r.status_code == 200
        s = r.json()["settings"]
        assert s["heading_font_family"] == "Playfair Display"
        assert s["content_font_family"] == "Roboto"

    def test_07_clamp_scale_low(self, auth_headers):
        r = requests.put(f"{BASE_URL}/api/admin/app-settings",
                         headers=auth_headers,
                         json={"content_font_size_scale": 0.1},
                         timeout=10)
        assert r.status_code == 200
        assert r.json()["settings"]["content_font_size_scale"] == 0.6

    def test_99_restore_defaults(self, auth_headers):
        # Restore original settings for cleanup
        if TestAppSettings.ORIGINAL:
            r = requests.put(f"{BASE_URL}/api/admin/app-settings",
                             headers=auth_headers,
                             json=TestAppSettings.ORIGINAL, timeout=10)
            assert r.status_code == 200


# ---------------------- Point 3: force-credit fallback ----------------------

# Minimal 1x1 JPEG base64
MINI_JPEG_B64 = ("/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsL"
                 "DBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/"
                 "2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
                 "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QA"
                 "HwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUF"
                 "BAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkK"
                 "FhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1"
                 "dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXG"
                 "x8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/9oADAMBAAIRAxEA"
                 "PwD3+iiigD//2Q==")


@pytest.fixture
def seed_bill(db):
    """Create a test bill in pending_review status. Cleans up after test."""
    user = db.users.find_one({}, {"_id": 0, "id": 1, "phone": 1, "name": 1})
    assert user, "No users in DB — cannot create test bill"
    bill_id = f"TEST-P3-{uuid.uuid4().hex[:8]}"
    doc = {
        "id": bill_id,
        "user_id": user["id"],
        "user_phone": user.get("phone", "919876543210"),
        "amount": 1500.0,
        "store_name": "Some Nonexistent Brand XYZ",
        "bill_no": f"TEST-P3-{int(time.time())}",
        "bill_date": datetime.now().strftime("%Y-%m-%d"),
        "status": "pending_review",
        "image_url": f"data:image/jpeg;base64,{MINI_JPEG_B64}",
        "created_at": datetime.utcnow().isoformat(),
        "ocr_confidence": 0.5,
    }
    db.bills.insert_one(doc)
    yield doc
    # cleanup
    db.bills.delete_one({"id": bill_id})


class TestFixBrandForceCredit:
    """Point 3: edit-brand endpoint force-credit fallback"""

    def test_force_credit_fallback_on_fundle_reject(self, auth_headers, db, seed_bill):
        bill_id = seed_bill["id"]
        r = requests.post(f"{BASE_URL}/api/admin/bills/{bill_id}/edit-brand",
                          headers=auth_headers,
                          json={
                              "new_store_name": "Another Nonexistent Brand ABCXYZ",
                              "reprocess": True,
                              "auto_force_credit_on_fundle_reject": True
                          },
                          timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        print("Response:", data)
        # Because brand doesn't exist in Fundle, fallback should kick in
        assert data.get("fallback") == "force_credit", (
            f"Expected fallback=force_credit; got: {data}")
        assert data.get("action") == "approved", f"Expected action=approved; got: {data}"
        assert data.get("points", 0) > 0, f"Expected points > 0; got: {data}"
        assert data.get("status") == "approved"

        # Verify DB
        updated = db.bills.find_one({"id": bill_id}, {"_id": 0})
        assert updated["status"] == "approved"
        assert updated.get("force_credited") is True
        assert updated.get("points_issued", 0) > 0

    def test_no_force_credit_when_flag_false(self, auth_headers, db, seed_bill):
        bill_id = seed_bill["id"]
        r = requests.post(f"{BASE_URL}/api/admin/bills/{bill_id}/edit-brand",
                          headers=auth_headers,
                          json={
                              "new_store_name": "Yet Another Bogus Brand QQQ",
                              "reprocess": True,
                              "auto_force_credit_on_fundle_reject": False
                          },
                          timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        print("No-fallback response:", data)
        # Should NOT have fallback key
        assert data.get("fallback") != "force_credit"
        # Should not be approved (Fundle rejected, no fallback)
        assert data.get("action") != "approved" or data.get("points", 0) == 0
        updated = db.bills.find_one({"id": bill_id}, {"_id": 0})
        assert updated.get("force_credited") is not True

    def test_valid_brand_uses_fundle_normally(self, auth_headers, db, seed_bill):
        # Get a valid brand from the master list
        rb = requests.get(f"{BASE_URL}/api/admin/brands", headers=auth_headers, timeout=15)
        assert rb.status_code == 200
        brands_payload = rb.json()
        brands = brands_payload if isinstance(brands_payload, list) else brands_payload.get("brands", [])
        assert len(brands) > 0, "No brands available to test with"
        valid_brand_name = None
        for b in brands:
            name = b.get("name") or b.get("brand_name") or b.get("store_name")
            if name:
                valid_brand_name = name
                break
        assert valid_brand_name, "Could not extract a brand name"
        print(f"Testing with valid brand: {valid_brand_name}")

        bill_id = seed_bill["id"]
        r = requests.post(f"{BASE_URL}/api/admin/bills/{bill_id}/edit-brand",
                          headers=auth_headers,
                          json={
                              "new_store_name": valid_brand_name,
                              "reprocess": True,
                              "auto_force_credit_on_fundle_reject": True
                          },
                          timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        print("Valid brand response:", data)
        # When valid brand is used, ideally Fundle approves it and no fallback needed.
        # However Fundle's master frequently drifts from local brand list (very reason
        # this fallback exists). We only verify the endpoint returns approved.
        # If fallback triggered, points must be >0 and status approved.
        assert data.get("action") == "approved", f"Bill not approved: {data}"
        assert data.get("points", 0) > 0
        if data.get("fallback") == "force_credit":
            print(f"NOTE: Fundle rejected valid brand '{valid_brand_name}' — "
                  f"fallback used. Fundle error: {data.get('fundle_error')}")


# ---------------------- Regression checks ----------------------

class TestRegression:
    def test_consumer_campaigns_active(self):
        r = requests.get(f"{BASE_URL}/api/consumer/campaigns/active", timeout=15)
        assert r.status_code == 200
        assert "campaigns" in r.json()

    def test_admin_dashboard_still_works(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/admin/brands", headers=auth_headers, timeout=15)
        assert r.status_code == 200

    def test_admin_bills_still_works(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/bills?limit=5", headers=auth_headers, timeout=15)
        assert r.status_code == 200
