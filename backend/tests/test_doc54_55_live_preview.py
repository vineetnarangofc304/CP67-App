# Session 94 live-Preview verification: Doc #54 (Volunteer QRs) + Doc #55 (consumer OTP truthful send)
# SAFETY: only phones 9999999999 (reviewer bypass) and 7000700071 (synthetic) are used; 7000700071 send-otp is hit ONCE.
import os
import base64
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
REVIEWER = "9999999999"
SYNTH = "7000700071"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"username": "admin", "password": "CP67Admin@2025"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"admin login failed {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---- Doc #54: Volunteer QR codes ----
class TestVolunteerQR:
    @pytest.mark.parametrize("qid,src", [("QR0124012", "SRC_VOLUNTEER_1"), ("QR0124013", "SRC_VOLUNTEER_2")])
    def test_qr_list_contains_volunteer(self, admin_headers, qid, src):
        r = requests.get(f"{BASE_URL}/api/qr-codes", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        rec = next((q for q in r.json() if q.get("qr_code_id") == qid), None)
        assert rec is not None, f"{qid} missing"
        assert rec["source_code"] == src
        assert src in rec["whatsapp_link"]
        print(qid, rec.get("location"), rec["whatsapp_link"])

    @pytest.mark.parametrize("qid,src", [("QR0124012", "SRC_VOLUNTEER_1"), ("QR0124013", "SRC_VOLUNTEER_2")])
    def test_qr_generate(self, qid, src):
        r = requests.get(f"{BASE_URL}/api/qr-codes/{qid}/generate", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["qr_code_id"] == qid
        assert src in d["whatsapp_link"]
        assert d["image_base64"].startswith("data:image/png;base64,")
        raw = base64.b64decode(d["image_base64"].split(",", 1)[1])
        assert raw[:8] == b"\x89PNG\r\n\x1a\n" and len(raw) > 200

    def test_sources_endpoint(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/users/sources", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        srcs = {s["code"]: s for s in r.json()["sources"]}
        for code, label in [("SRC_VOLUNTEER_1", "Volunteer 1"), ("SRC_VOLUNTEER_2", "Volunteer 2")]:
            assert code in srcs
            assert srcs[code]["label"] == label
            assert isinstance(srcs[code]["count"], int)
        print({k: srcs[k] for k in ("SRC_VOLUNTEER_1", "SRC_VOLUNTEER_2")})

    def test_users_filter_volunteer1(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/users", params={"source": "SRC_VOLUNTEER_1", "limit": 200},
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        users = d["users"] if isinstance(d, dict) else d
        assert isinstance(users, list)
        assert all(u.get("first_touch_source") == "SRC_VOLUNTEER_1" for u in users)
        match = [u for u in users if str(u.get("phone", "")).endswith(SYNTH)]
        assert match, "7000700071 not found under SRC_VOLUNTEER_1"


# ---- Doc #55: consumer OTP ----
class TestConsumerOTP:
    def test_reviewer_send_otp_short_circuit(self):
        r = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": REVIEWER}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["success"] is True
        assert "delivery" not in d

    def test_reviewer_verify_ok(self):
        r = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={"phone": REVIEWER, "otp": "123456"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["success"] is True
        assert isinstance(d.get("token"), str) and d["token"].count(".") == 2

    def test_reviewer_verify_wrong(self):
        r = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={"phone": REVIEWER, "otp": "999999"}, timeout=30)
        assert r.status_code == 400
        assert "Invalid OTP" in r.json().get("detail", "")

    def test_synth_send_once_then_dev_bypass(self):
        # SINGLE send - no retry
        r = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": SYNTH}, timeout=60)
        print("send-otp 7000700071:", r.status_code, r.text)
        if r.status_code == 503:
            assert "detail" in r.json()
        else:
            assert r.status_code == 200
            d = r.json()
            assert d["success"] is True
            assert d["phone"] == "91" + SYNTH
            assert isinstance(d["delivery"]["whatsapp"], str)
            assert isinstance(d["delivery"]["sms"], str)
        v = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={"phone": SYNTH, "otp": "1234"}, timeout=30)
        print("verify 1234:", v.status_code, v.text[:200])
        assert v.status_code == 200
        assert v.json()["success"] is True


# ---- Regression: app-download QR stats (platform_counts) ----
def test_app_download_qr_stats(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/app-download-qr/stats", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    assert isinstance(r.json().get("platform_counts"), dict)


def test_admin_qr_codes_stats_path_as_named_in_request(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/qr-codes/stats", headers=admin_headers, timeout=30)
    print("/api/admin/qr-codes/stats ->", r.status_code, r.text[:200])
    assert r.status_code != 500


# ---- Regression: blocked phone -> 403 (returns before any OTP store/send) ----
def test_blocked_phone_403():
    blocked = "5807941844"  # first entry in Preview blocked_phones
    r = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": blocked}, timeout=30)
    assert r.status_code == 403
    assert "not eligible" in r.json().get("detail", "")
