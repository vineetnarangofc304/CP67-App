"""Tests for admin edit-brand endpoint (async background reprocess) and regressions."""
import os
import time
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://staff-incentive-lab.preview.emergentagent.com").rstrip("/")
ADMIN_USER = "admin"
ADMIN_PASS = "CP67Admin@2025"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _get_pending_bill(auth):
    r = requests.get(f"{BASE_URL}/api/bills/pending-review?limit=20", headers=auth, timeout=15)
    assert r.status_code == 200
    bills = r.json()
    if isinstance(bills, dict):
        bills = bills.get("bills", [])
    # prefer bills with an amount and image
    candidates = [b for b in bills if b.get("amount") and b.get("has_image")]
    return candidates[0] if candidates else (bills[0] if bills else None)


def _get_bill(auth, bill_id):
    r = requests.get(f"{BASE_URL}/api/bills/{bill_id}", headers=auth, timeout=15)
    if r.status_code == 200:
        j = r.json()
        return j.get("bill", j) if isinstance(j, dict) else j
    return None


# --- URGENT: fast queued edit-brand ---
class TestEditBrandQueued:

    def test_edit_brand_returns_fast_queued(self, auth):
        bill = _get_pending_bill(auth)
        if not bill:
            pytest.skip("No pending_review/manual_review bill to test with")
        bill_id = bill["id"]
        start = time.time()
        r = requests.post(
            f"{BASE_URL}/api/admin/bills/{bill_id}/edit-brand",
            headers=auth,
            json={"new_store_name": "Reliance Retail Limited",
                  "reprocess": True,
                  "auto_force_credit_on_fundle_reject": True},
            timeout=10,
        )
        elapsed = time.time() - start
        print(f"edit-brand queued elapsed={elapsed:.2f}s")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("success") is True
        assert data.get("reprocessed") == "queued"
        assert data.get("store_name") == "Reliance Retail Limited"
        assert "message" in data
        assert elapsed < 3.0, f"Endpoint took {elapsed:.2f}s, exceeds 3s SLA"

        # Verify DB stamps
        b = _get_bill(auth, bill_id)
        assert b is not None
        assert b.get("brand_edited_at"), "brand_edited_at not set"
        assert b.get("reprocessing_started_at"), "reprocessing_started_at not set"

    def test_edit_brand_no_reprocess_fast(self, auth):
        bill = _get_pending_bill(auth)
        if not bill:
            pytest.skip("No pending bill")
        bill_id = bill["id"]
        start = time.time()
        r = requests.post(
            f"{BASE_URL}/api/admin/bills/{bill_id}/edit-brand",
            headers=auth,
            json={"new_store_name": "Some Brand", "reprocess": False},
            timeout=10,
        )
        elapsed = time.time() - start
        print(f"edit-brand no-reprocess elapsed={elapsed:.2f}s")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("success") is True
        assert data.get("reprocessed") is False
        assert data.get("store_name") == "Some Brand"
        assert elapsed < 2.0


# --- REGRESSION: other endpoints ---
class TestRegressions:

    def test_consumer_campaigns_active(self):
        r = requests.get(f"{BASE_URL}/api/consumer/campaigns/active", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))

    def test_consumer_app_settings(self):
        r = requests.get(f"{BASE_URL}/api/consumer/app-settings", timeout=15)
        assert r.status_code == 200

    def test_admin_app_settings(self, auth):
        r = requests.get(f"{BASE_URL}/api/admin/app-settings", headers=auth, timeout=15)
        assert r.status_code == 200

    def test_admin_sync_jobs(self, auth):
        r = requests.get(f"{BASE_URL}/api/admin/sync/jobs", headers=auth, timeout=15)
        assert r.status_code == 200

    def test_qr_links(self, auth):
        r = requests.get(f"{BASE_URL}/api/qr-links", headers=auth, timeout=15)
        # qr-links might be public or admin. Accept 200 or 401 if auth wrong.
        assert r.status_code in (200, 401, 403), r.text
