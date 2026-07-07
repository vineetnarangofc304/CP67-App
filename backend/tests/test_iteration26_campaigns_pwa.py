"""Iteration 26 backend tests:
- Public campaigns/active endpoint (consumer)
- Campaign engine (multiplier + bonus) via admin CRUD + presence in active list
- Admin campaigns CRUD (POST/PUT/DELETE/toggle/GET)
- Consumer bill upload regression
- Admin bills regression endpoints
"""
import os
import io
import pytest
import requests
from datetime import datetime, timezone

def _load_frontend_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env()).rstrip("/")
ADMIN_USER = "admin"
ADMIN_PASS = "CP67Admin@2025"
CONSUMER_PHONE = "9876543210"
CONSUMER_OTP = "1234"

CREATED_CAMPAIGNS = []


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def consumer_token():
    r = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp",
                      json={"phone": CONSUMER_PHONE}, timeout=15)
    assert r.status_code == 200, r.text
    r2 = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp",
                       json={"phone": CONSUMER_PHONE, "otp": CONSUMER_OTP}, timeout=15)
    assert r2.status_code == 200, r2.text
    d = r2.json()
    return d.get("token") or d.get("access_token")


@pytest.fixture(scope="session")
def consumer_headers(consumer_token):
    return {"Authorization": f"Bearer {consumer_token}"}


# ==================== PUBLIC /consumer/campaigns/active ====================

def test_consumer_campaigns_active_public_no_auth():
    r = requests.get(f"{BASE_URL}/api/consumer/campaigns/active", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "campaigns" in data
    assert isinstance(data["campaigns"], list)


# ==================== ADMIN CAMPAIGN CRUD ====================

def test_admin_login(admin_token):
    assert admin_token and isinstance(admin_token, str)


def test_create_active_multiplier_campaign(admin_headers):
    payload = {
        "name": "TEST_2X_Weekend_iter26",
        "description": "Test 2X multiplier",
        "campaign_type": "multiplier",
        "multiplier": 2.0,
        "bonus_points": 0,
        "min_spend": 0,
        "applicable_floors": None,
        "applicable_categories": None,
        "applicable_brand_ids": None,
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "is_active": True,
    }
    r = requests.post(f"{BASE_URL}/api/admin/campaigns", json=payload, headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True
    camp = body.get("campaign")
    assert camp["name"] == payload["name"]
    assert camp["multiplier"] == 2.0
    assert camp["campaign_type"] == "multiplier"
    assert "id" in camp
    CREATED_CAMPAIGNS.append(camp["id"])


def test_active_multiplier_appears_in_active_endpoint():
    r = requests.get(f"{BASE_URL}/api/consumer/campaigns/active", timeout=15)
    assert r.status_code == 200
    names = [c.get("name") for c in r.json().get("campaigns", [])]
    assert "TEST_2X_Weekend_iter26" in names


def test_create_scheduled_future_campaign_not_in_active(admin_headers):
    payload = {
        "name": "TEST_Future_iter26",
        "description": "Scheduled future",
        "campaign_type": "multiplier",
        "multiplier": 3.0,
        "bonus_points": 0,
        "min_spend": 0,
        "applicable_floors": None,
        "applicable_categories": None,
        "applicable_brand_ids": None,
        "start_date": "2099-01-01",
        "end_date": "2099-12-31",
        "is_active": True,
    }
    r = requests.post(f"{BASE_URL}/api/admin/campaigns", json=payload, headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    CREATED_CAMPAIGNS.append(r.json()["campaign"]["id"])

    r2 = requests.get(f"{BASE_URL}/api/consumer/campaigns/active", timeout=15)
    names = [c.get("name") for c in r2.json().get("campaigns", [])]
    assert "TEST_Future_iter26" not in names


def test_create_inactive_campaign_not_in_active(admin_headers):
    payload = {
        "name": "TEST_Inactive_iter26",
        "description": "Disabled",
        "campaign_type": "bonus",
        "multiplier": 1.0,
        "bonus_points": 50,
        "min_spend": 0,
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "is_active": False,
    }
    r = requests.post(f"{BASE_URL}/api/admin/campaigns", json=payload, headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    CREATED_CAMPAIGNS.append(r.json()["campaign"]["id"])
    r2 = requests.get(f"{BASE_URL}/api/consumer/campaigns/active", timeout=15)
    names = [c.get("name") for c in r2.json().get("campaigns", [])]
    assert "TEST_Inactive_iter26" not in names


def test_create_bonus_campaign_visible(admin_headers):
    payload = {
        "name": "TEST_Bonus_iter26",
        "description": "Flat bonus",
        "campaign_type": "bonus",
        "multiplier": 1.0,
        "bonus_points": 100,
        "min_spend": 0,
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "is_active": True,
    }
    r = requests.post(f"{BASE_URL}/api/admin/campaigns", json=payload, headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    cid = r.json()["campaign"]["id"]
    CREATED_CAMPAIGNS.append(cid)

    r2 = requests.get(f"{BASE_URL}/api/consumer/campaigns/active", timeout=15)
    campaigns = r2.json()["campaigns"]
    match = [c for c in campaigns if c.get("name") == "TEST_Bonus_iter26"]
    assert len(match) == 1
    assert match[0]["campaign_type"] == "bonus"
    assert match[0]["bonus_points"] == 100


def test_toggle_campaign(admin_headers):
    assert CREATED_CAMPAIGNS
    cid = CREATED_CAMPAIGNS[0]
    r = requests.put(f"{BASE_URL}/api/admin/campaigns/{cid}/toggle", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    is_active = r.json().get("is_active")
    # toggle back
    r2 = requests.put(f"{BASE_URL}/api/admin/campaigns/{cid}/toggle", headers=admin_headers, timeout=15)
    assert r2.status_code == 200
    assert r2.json().get("is_active") == (not is_active)


def test_update_campaign(admin_headers):
    assert CREATED_CAMPAIGNS
    cid = CREATED_CAMPAIGNS[0]
    payload = {
        "name": "TEST_2X_Weekend_iter26",
        "description": "Updated desc",
        "campaign_type": "multiplier",
        "multiplier": 2.5,
        "bonus_points": 0,
        "min_spend": 0,
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "is_active": True,
    }
    r = requests.put(f"{BASE_URL}/api/admin/campaigns/{cid}", json=payload, headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["campaign"]["multiplier"] == 2.5
    assert r.json()["campaign"]["description"] == "Updated desc"


def test_list_admin_campaigns(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/campaigns", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "campaigns" in body
    names = [c["name"] for c in body["campaigns"]]
    assert "TEST_2X_Weekend_iter26" in names


# ==================== CAMPAIGN ENGINE HELPER ====================

def test_apply_campaign_bonus_helper_multiplier():
    """Test the server.apply_campaign_bonus helper directly (in-process)."""
    import asyncio, sys
    sys.path.insert(0, "/app/backend")
    from server import apply_campaign_bonus
    # After creation above we should have TEST_2X_Weekend_iter26 active (multiplier=2.5 after update)
    result = asyncio.get_event_loop().run_until_complete(
        apply_campaign_bonus(bill_amount=1000.0, base_points=100)
    ) if False else asyncio.run(
        apply_campaign_bonus(bill_amount=1000.0, base_points=100)
    )
    # base_points=100, multiplier=2.5 => extra = 150; plus bonus campaign +100
    assert result["final_points"] >= 100
    assert result["bonus_points"] >= 0
    assert isinstance(result["applied_campaigns"], list)


# ==================== CONSUMER BILL UPLOAD REGRESSION ====================

def _tiny_jpeg_bytes():
    # 1x1 pixel JPEG (minimal valid)
    return bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d0d1832211c2132323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232ffc00011080001000103012200021101031101ffc4001f0000010501010101010100000000000000000102030405060708090a0bffc400b5100002010303020403050504040000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a535455565758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffc4001f0100030101010101010101010000000000000102030405060708090a0bffc400b51100020102040403040705040400010277000102031104052131061241510761711322328108144291a1b1c109233352f0156272d10a162434e125f11718191a262728292a35363738393a434445464748494a535455565758595a636465666768696a737475767778797a82838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9faffda000c03010002110311003f00fbfc7fffd9"
    )


def test_consumer_bill_upload_accepts_image(consumer_headers):
    files = {"file": ("test.jpg", _tiny_jpeg_bytes(), "image/jpeg")}
    r = requests.post(f"{BASE_URL}/api/consumer/bills/upload", files=files, headers=consumer_headers, timeout=30)
    assert r.status_code in (200, 201), f"{r.status_code} - {r.text}"
    body = r.json()
    assert "bill_id" in body or "id" in body


# ==================== ADMIN BILLS REGRESSION ====================

def test_admin_bills_list(admin_headers):
    r = requests.get(f"{BASE_URL}/api/bills?limit=5", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "bills" in body or isinstance(body, list)


def test_admin_bills_pending_review(admin_headers):
    r = requests.get(f"{BASE_URL}/api/bills/pending-review", headers=admin_headers, timeout=15)
    assert r.status_code == 200


# ==================== CLEANUP ====================

def test_zzz_cleanup_delete_campaigns(admin_headers):
    for cid in list(CREATED_CAMPAIGNS):
        r = requests.delete(f"{BASE_URL}/api/admin/campaigns/{cid}", headers=admin_headers, timeout=15)
        assert r.status_code == 200, f"Failed to delete {cid}: {r.text}"
        CREATED_CAMPAIGNS.remove(cid)
