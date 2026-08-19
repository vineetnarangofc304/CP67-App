"""Point 36 (SMS everywhere) — dual-channel alerts + OTP.

Covers:
- POST /api/admin/alerts/test  -> per-phone whatsapp + sms diagnostics
- POST /api/admin/otp/send-test -> otp_channel 'both', both channel objects
- POST /api/consumer/auth/send-otp -> still 200
Live Karix calls: kept to a minimum (module-scoped fixtures reuse responses).
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

ADMIN_USER = "admin"
ADMIN_PASS = "CP67Admin@2025"
TEST_PHONE = "9876543210"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        pytest.fail(f"no token in login response: {r.text[:300]}")
    return tok


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ---------- /admin/alerts/test (original bug) ----------
@pytest.fixture(scope="module")
def alerts_test_response(auth_headers):
    r = requests.post(f"{BASE_URL}/api/admin/alerts/test", headers=auth_headers, json={}, timeout=90)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    return r.json()


class TestAdminAlertsTestDualChannel:
    def test_top_level_shape(self, alerts_test_response):
        d = alerts_test_response
        for k in ("success", "accepted", "total", "phones", "results", "hint"):
            assert k in d, f"missing key {k} in {d}"
        assert isinstance(d["results"], list) and len(d["results"]) >= 1
        assert d["total"] == len(d["results"])

    def test_hint_mentions_both_or_sms(self, alerts_test_response):
        hint = alerts_test_response["hint"].upper()
        assert "BOTH" in hint or "SMS" in hint, f"hint not updated: {hint}"

    def test_per_phone_channels(self, alerts_test_response):
        r0 = alerts_test_response["results"][0]
        print("alerts/test result[0]:", r0)
        assert "whatsapp" in r0 and isinstance(r0["whatsapp"], dict)
        assert "sms" in r0 and isinstance(r0["sms"], dict)
        for ch in ("whatsapp", "sms"):
            assert "success" in r0[ch], f"{ch} missing success"
            assert "status_code" in r0[ch], f"{ch} missing status_code: {r0[ch]}"
        assert r0["success"] == bool(r0["whatsapp"].get("success") or r0["sms"].get("success"))

    def test_at_least_one_channel_accepted(self, alerts_test_response):
        r0 = alerts_test_response["results"][0]
        assert r0["success"] is True, f"neither channel accepted: {r0}"
        assert alerts_test_response["success"] is True

    def test_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/admin/alerts/test", json={}, timeout=30)
        assert r.status_code in (401, 403), r.status_code


# ---------- /admin/otp/send-test ----------
@pytest.fixture(scope="module")
def otp_test_response(auth_headers):
    r = requests.post(f"{BASE_URL}/api/admin/otp/send-test", headers=auth_headers,
                      json={"phone": TEST_PHONE}, timeout=90)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    return r.json()


class TestAdminOtpSendTestDualChannel:
    def test_channel_is_both(self, otp_test_response):
        print("otp/send-test:", otp_test_response)
        assert otp_test_response["otp_channel"] == "both", otp_test_response.get("otp_channel")
        assert otp_test_response["phone"] == TEST_PHONE

    def test_both_channel_objects_present(self, otp_test_response):
        for ch in ("whatsapp", "sms"):
            assert otp_test_response.get(ch) is not None, f"{ch} is null"
            assert isinstance(otp_test_response[ch], dict)
            assert "success" in otp_test_response[ch]

    def test_root_success_when_any_channel_ok(self, otp_test_response):
        any_ok = bool(otp_test_response["whatsapp"].get("success") or otp_test_response["sms"].get("success"))
        assert otp_test_response["success"] == any_ok
        assert otp_test_response["success"] is True, otp_test_response

    def test_invalid_phone_rejected(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/admin/otp/send-test", headers=auth_headers,
                          json={"phone": "12345"}, timeout=30)
        assert r.status_code == 400, f"{r.status_code}: {r.text[:200]}"


# ---------- consumer OTP regression ----------
class TestConsumerSendOtp:
    def test_send_otp_ok(self):
        r = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp",
                          json={"phone": "9876543288"}, timeout=60)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        d = r.json()
        assert d.get("success") is True
        assert str(d.get("phone", "")).startswith("919"), d
