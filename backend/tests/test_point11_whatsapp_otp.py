"""Point 11: OTP now goes via WhatsApp by default (configurable via OTP_CHANNEL env).

- Consumer /consumer/auth/send-otp uses the new dispatcher `send_login_otp`.
- New admin endpoint /admin/otp/send-test fires a real OTP through the configured channel and returns per-channel Karix diagnostics.
"""
import os
import requests

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8001")


def _admin_token():
    r = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={"username": "admin", "password": "CP67Admin@2025"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["token"]


def test_consumer_send_otp_still_ok():
    """The public send-otp endpoint must remain a 200 → success:true, regardless of channel."""
    r = requests.post(
        f"{BASE_URL}/api/consumer/auth/send-otp",
        json={"phone": "9876543299"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    assert data.get("success") is True
    assert data.get("phone") == "919876543299"


def test_admin_otp_send_test_returns_whatsapp_diag():
    """/admin/otp/send-test must return per-channel diagnostics with WhatsApp attempt evidence."""
    tok = _admin_token()
    r = requests.post(
        f"{BASE_URL}/api/admin/otp/send-test",
        headers={"Authorization": f"Bearer {tok}"},
        json={"phone": "9876543298"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    assert set(data.keys()) >= {"phone", "otp_channel", "success", "whatsapp", "sms", "hint"}
    assert data["phone"] == "9876543298"
    # Default channel is WhatsApp
    assert data["otp_channel"] in ("whatsapp", "both")
    # WhatsApp attempt must be present with Karix response
    assert data["whatsapp"] is not None
    assert "status_code" in data["whatsapp"] or "error" in data["whatsapp"]
    if data["whatsapp"].get("success"):
        assert data["whatsapp"].get("status_code") == 200
        assert data["whatsapp"].get("mid")


def test_admin_otp_send_test_requires_phone():
    tok = _admin_token()
    r = requests.post(
        f"{BASE_URL}/api/admin/otp/send-test",
        headers={"Authorization": f"Bearer {tok}"},
        json={},
        timeout=15,
    )
    assert r.status_code == 400


def test_admin_otp_send_test_requires_auth():
    r = requests.post(
        f"{BASE_URL}/api/admin/otp/send-test",
        json={"phone": "9876543210"},
        timeout=15,
    )
    assert r.status_code in (401, 403)
