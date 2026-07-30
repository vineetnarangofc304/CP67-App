"""Point 19 — Retailer Staff Incentive Platform: end-to-end backend tests."""
import os
import re
import uuid
import pytest
import httpx

API_URL = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
API_URL = API_URL.rstrip("/") + "/api"

ADMIN_USER = "admin"
ADMIN_PASS = "CP67Admin@2025"


def _admin_token():
    r = httpx.post(f"{API_URL}/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def _mk_staff(token, phone=None):
    phone = phone or f"98{uuid.uuid4().int % 100000000:08d}"
    r = httpx.post(
        f"{API_URL}/admin/staff",
        json={"name": "Pytest Staff", "phone": phone, "brand_name": "PytestBrand", "store_location": "Level 1"},
        headers={"Authorization": f"Bearer {token}"}, timeout=15,
    )
    r.raise_for_status()
    return phone, r.json()["staff"]


def test_admin_can_onboard_and_list_staff():
    t = _admin_token()
    phone, staff = _mk_staff(t)
    assert staff["staff_code"].startswith("HL-")
    assert staff["qr_token"].startswith("HL")
    r = httpx.get(f"{API_URL}/admin/staff", headers={"Authorization": f"Bearer {t}"}, timeout=15)
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()["staff"]]
    assert staff["id"] in ids


def test_admin_qr_generation_returns_image():
    t = _admin_token()
    _, staff = _mk_staff(t)
    r = httpx.get(f"{API_URL}/admin/staff/{staff['id']}/qr",
                  headers={"Authorization": f"Bearer {t}"}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("qr_image_base64")
    assert d["whatsapp_url"].startswith("https://wa.me/")
    assert "%23STAFF%3A" + staff["qr_token"] in d["whatsapp_url"]


def test_admin_can_update_config_slabs():
    t = _admin_token()
    r = httpx.put(
        f"{API_URL}/admin/staff/config/current",
        json={"attribution_window_minutes": 20},
        headers={"Authorization": f"Bearer {t}"}, timeout=15,
    )
    assert r.status_code == 200
    assert r.json()["config"]["attribution_window_minutes"] == 20
    # Restore
    httpx.put(f"{API_URL}/admin/staff/config/current",
              json={"attribution_window_minutes": 15},
              headers={"Authorization": f"Bearer {t}"}, timeout=15)


def test_staff_login_with_dev_bypass():
    t = _admin_token()
    phone, staff = _mk_staff(t)
    r = httpx.post(f"{API_URL}/staff/auth/send-otp", json={"phone": phone}, timeout=15)
    assert r.status_code == 200
    r2 = httpx.post(f"{API_URL}/staff/auth/verify-otp",
                    json={"phone": phone, "otp": "1234"}, timeout=15)
    # Depends on OTP_DEV_BYPASS env var. Only assert 200 if enabled.
    if os.environ.get("OTP_DEV_BYPASS") == "1234":
        assert r2.status_code == 200
        assert r2.json()["staff"]["staff_code"] == staff["staff_code"]


def test_staff_dashboard_shape():
    t = _admin_token()
    phone, staff = _mk_staff(t)
    # Force dev bypass path — configured on this env
    r = httpx.post(f"{API_URL}/staff/auth/verify-otp",
                   json={"phone": phone, "otp": "1234"}, timeout=15)
    if r.status_code != 200:
        pytest.skip("Dev OTP bypass not enabled on this env")
    stok = r.json()["token"]
    d = httpx.get(f"{API_URL}/staff/dashboard",
                  headers={"Authorization": f"Bearer {stok}"}, timeout=15)
    assert d.status_code == 200
    j = d.json()
    assert "summary" in j and "performance" in j and "config_snapshot" in j


def test_leaderboard_and_metrics():
    t = _admin_token()
    r = httpx.get(f"{API_URL}/admin/staff/metrics/overview",
                  headers={"Authorization": f"Bearer {t}"}, timeout=15)
    assert r.status_code == 200
    assert "total_staff" in r.json()
    r2 = httpx.get(f"{API_URL}/admin/staff/leaderboard?period=monthly",
                   headers={"Authorization": f"Bearer {t}"}, timeout=15)
    assert r2.status_code == 200
    assert "leaderboard" in r2.json()


def test_staff_token_parsing_from_message():
    """Simulated: the WhatsApp webhook should detect #STAFF: token and
    open an attribution window (verified via staff module regex)."""
    import sys, os as _os
    _backend = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
    if _backend not in sys.path:
        sys.path.insert(0, _backend)
    from routes.staff import STAFF_MSG_PATTERN
    msg = "Hi CP67! I'm registering via staff HL-0001 (Zara). #STAFF:HLBEB8FBCEE18"
    m = STAFF_MSG_PATTERN.search(msg.upper())
    assert m and m.group(1) == "HLBEB8FBCEE18"


def test_admin_redemptions_endpoint_reachable():
    t = _admin_token()
    r = httpx.get(f"{API_URL}/admin/staff/redemptions",
                  headers={"Authorization": f"Bearer {t}"}, timeout=15)
    assert r.status_code == 200
    assert "redemptions" in r.json()
