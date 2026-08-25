"""API-level tests for Points 8 & 9 config persistence via preview URL."""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://staff-points-engine.preview.emergentagent.com").rstrip("/")
ADMIN_USER = "admin"
ADMIN_PASS = "CP67Admin@2025"


def _login():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _headers(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def test_point8_registration_by_category_persistence():
    tok = _login()
    payload = {"registration_by_category": {"__ALL__": 60, "Fashion": 88}}
    r = requests.put(f"{BASE_URL}/api/admin/staff/config/current", json=payload, headers=_headers(tok), timeout=30)
    assert r.status_code == 200, r.text
    g = requests.get(f"{BASE_URL}/api/admin/staff/config/current", headers=_headers(tok), timeout=30)
    assert g.status_code == 200
    data = g.json().get("config") or g.json()
    saved = data.get("registration_by_category") or {}
    assert saved.get("__ALL__") == 60, f"expected __ALL__=60, got {saved}"
    assert saved.get("Fashion") == 88, f"expected Fashion=88, got {saved}"


def test_point9_bill_upload_value_slabs_persistence():
    tok = _login()
    payload = {
        "bill_upload_value_slabs_by_category": {
            "__ALL__": [
                {"min_value": 0, "max_value": 1000, "amount": 22},
                {"min_value": 1001, "max_value": 999999, "amount": 55},
            ]
        }
    }
    r = requests.put(f"{BASE_URL}/api/admin/staff/config/current", json=payload, headers=_headers(tok), timeout=30)
    assert r.status_code == 200, r.text
    g = requests.get(f"{BASE_URL}/api/admin/staff/config/current", headers=_headers(tok), timeout=30)
    assert g.status_code == 200
    saved = ((g.json().get("config") or g.json()).get("bill_upload_value_slabs_by_category") or {}).get("__ALL__") or []
    assert len(saved) == 2, f"expected 2 slabs, got {saved}"
    assert saved[0]["min_value"] == 0 and saved[0]["max_value"] == 1000 and saved[0]["amount"] == 22
    assert saved[1]["min_value"] == 1001 and saved[1]["amount"] == 55


def test_cleanup_reset_maps():
    tok = _login()
    r = requests.put(
        f"{BASE_URL}/api/admin/staff/config/current",
        json={"registration_by_category": {}, "bill_upload_value_slabs_by_category": {}},
        headers=_headers(tok),
        timeout=30,
    )
    assert r.status_code == 200
    g = requests.get(f"{BASE_URL}/api/admin/staff/config/current", headers=_headers(tok), timeout=30).json()
    cfg = g.get("config") or g
    assert (cfg.get("registration_by_category") or {}) == {}
    assert (cfg.get("bill_upload_value_slabs_by_category") or {}) == {}
