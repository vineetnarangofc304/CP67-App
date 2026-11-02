# Points 56-59: Fundle-based tier sync, consumer tier endpoints consistency, static assets
import os
import sys
import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
REVIEWER_PHONE = "9999999999"
REVIEWER_OTP = "123456"


# ---------- Unit tests for fundle_tier ----------
@pytest.fixture(scope="module")
def ft():
    from routes.consumer import fundle_tier
    return fundle_tier


EXAMPLE = {"balance_points": 52146.04, "next_tier_target_amount": 150001,
           "next_tier_pending_amt": 51186.52, "next_tier_name": "Titanium",
           "total_customer_spend": 98814.48}


class TestFundleTierUnit:
    def test_example_point56(self, ft):
        r = ft({"success": True, "data": EXAMPLE}, "Titanium")
        assert r["name"] == "Platinum"
        assert r["to_next_amount"] == 51187
        assert r["next"] == "Titanium" and r["next_tier"] == "Titanium"
        assert r["next_at"] == 150001
        assert r["synced"] is True
        assert r["current_spend"] == 98814.48
        # (98814.48-75001)/(150001-75001) = 31.7%
        assert r["progress"] == 31

    def test_zero_spend_bronze(self, ft):
        r = ft({"success": True, "data": {"total_customer_spend": 0, "next_tier_name": "Silver",
                                           "next_tier_target_amount": 10001, "next_tier_pending_amt": 10001}})
        assert r["name"] == "Bronze" and r["next"] == "Silver" and r["to_next_amount"] == 10001
        assert r["progress"] == 0

    def test_top_tier(self, ft):
        r = ft({"success": True, "data": {"total_customer_spend": 600000, "next_tier_name": None}})
        assert r["name"] == "Privilege" and r["next"] is None
        assert r["to_next_amount"] is None and r["progress"] == 100

    def test_spend_fallback_when_no_next_name(self, ft):
        r = ft({"success": True, "data": {"total_customer_spend": 30000}})
        assert r["name"] == "Gold" and r["next"] == "Platinum"
        assert r["to_next_amount"] == 45001

    def test_fundle_failure_falls_back_to_stored(self, ft):
        r = ft({"success": False, "error": "x"}, "Gold")
        assert r["name"] == "Gold" and r["synced"] is False
        assert r["to_next_amount"] is None
        r2 = ft({"success": False}, None)
        assert r2["name"] == "Bronze" and r2["synced"] is False

    def test_unknown_stored_tier(self, ft):
        r = ft({"success": True, "data": None}, "Weird")
        assert r["name"] == "Bronze" and r["synced"] is False


# ---------- API tests with reviewer account ----------
@pytest.fixture(scope="module")
def token():
    s = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": REVIEWER_PHONE}, timeout=30)
    assert s.status_code == 200, s.text
    r = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp",
                      json={"phone": REVIEWER_PHONE, "otp": REVIEWER_OTP}, timeout=60)
    if r.status_code != 200:
        pytest.skip(f"reviewer login failed {r.status_code} {r.text}")
    d = r.json()
    return d.get("token") or d.get("access_token")


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def tier_info(H):
    r = requests.get(f"{BASE_URL}/api/consumer/tier-info", headers=H, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


class TestTierEndpoints:
    def test_tier_info_shape(self, tier_info):
        ct = tier_info["current_tier"]
        for k in ["name", "color", "min", "next", "next_tier", "next_at", "current_spend",
                  "to_next_amount", "progress", "basis", "synced"]:
            assert k in ct, k
        assert ct["basis"] == "spend"
        assert tier_info["total_spend"] == ct["current_spend"]
        assert tier_info["next_tier"] == ct["next_tier"]
        assert tier_info["to_next_amount"] == ct["to_next_amount"]
        names = [t["name"] for t in tier_info["tiers"]]
        assert names == ["Bronze", "Silver", "Gold", "Platinum", "Titanium", "Diamond", "Privilege"]
        ms = [t["min_spend"] for t in tier_info["tiers"]]
        assert ms == [0, 10001, 25001, 75001, 150001, 300001, 500001]
        print("tier-info current_tier:", ct)

    def test_consistency_across_endpoints(self, H, tier_info):
        name = tier_info["current_tier"]["name"]
        home = requests.get(f"{BASE_URL}/api/consumer/home", headers=H, timeout=60)
        assert home.status_code == 200
        assert home.json()["user"]["tier"] == name
        prof = requests.get(f"{BASE_URL}/api/consumer/profile", headers=H, timeout=60)
        assert prof.status_code == 200
        assert prof.json()["tier"] == name
        w = requests.get(f"{BASE_URL}/api/consumer/wallet", headers=H, timeout=60)
        assert w.status_code == 200
        wt = w.json()["tier"]
        assert (wt["name"] if isinstance(wt, dict) else wt) == name
        wd = requests.get(f"{BASE_URL}/api/consumer/wallet/detailed", headers=H, timeout=60)
        assert wd.status_code == 200
        wdt = wd.json()["tier"]
        assert (wdt["name"] if isinstance(wdt, dict) else wdt) == name

    def test_tier_info_unauth(self):
        r = requests.get(f"{BASE_URL}/api/consumer/tier-info", timeout=30)
        assert r.status_code in (401, 403)


class TestStaticAssets:
    def test_logo_loads(self):
        r = requests.get(f"{BASE_URL}/ha-logo-full.png", timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/")
