"""CP67 Points 36 & 37 — Admin diagnostics:

Point 36: /api/admin/alerts/test and /api/admin/whatsapp/send-test must return per-phone Karix diagnostic (status_code, mid, response) so admin can see why a message might not have delivered even though the send call "succeeded".

Point 37: /api/admin/users/sources must return every distinct first_touch_source in the users collection PLUS a curated shortlist so the Users source dropdown reflects reality.
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


# ─── Point 37 ─────────────────────────────────────────────────────────────


def test_sources_endpoint_returns_all_sources_with_counts():
    tok = _admin_token()
    r = requests.get(
        f"{BASE_URL}/api/admin/users/sources",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    assert "sources" in data and isinstance(data["sources"], list)
    # Every entry must have code + label + count
    for s in data["sources"]:
        assert set(s.keys()) >= {"code", "label", "count"}
        assert isinstance(s["count"], int)
    codes = {s["code"] for s in data["sources"]}
    # Curated defaults must be present even if 0
    for expected in ("SRC_APP", "SRC_RWA", "SRC_OFFICE", "SRC_WHATSAPP", "SRC_MARKETING"):
        assert expected in codes, f"{expected} missing from /admin/users/sources"
    # Response must be sorted highest-count first
    counts = [s["count"] for s in data["sources"]]
    assert counts == sorted(counts, reverse=True), "sources not sorted by count desc"


def test_sources_endpoint_requires_auth():
    r = requests.get(f"{BASE_URL}/api/admin/users/sources", timeout=10)
    assert r.status_code in (401, 403)


# ─── Point 36 ─────────────────────────────────────────────────────────────


def test_alerts_test_returns_per_phone_diagnostic():
    tok = _admin_token()
    r = requests.post(
        f"{BASE_URL}/api/admin/alerts/test",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    assert "results" in data and "accepted" in data and "total" in data
    assert data["total"] == len(data.get("phones", []))
    # Point 36 (updated): hint now explains the dual-channel WhatsApp + SMS behaviour
    assert "hint" in data
    assert "24-hour" in data["hint"] or "24 hours" in data["hint"]
    assert "SMS" in data["hint"]
    # Every result carries per-channel diagnostic fields (whatsapp + sms)
    for res in data["results"]:
        assert set(res.keys()) >= {"success", "phone_input", "phone_sent_to", "whatsapp", "sms"}
        wa = res.get("whatsapp") or {}
        sms = res.get("sms") or {}
        if wa.get("success"):
            # Karix should have echoed a mid + 200 status on WhatsApp
            assert wa.get("status_code") == 200
            assert wa.get("mid")
        if sms.get("success"):
            assert sms.get("status_code") == 200
        assert res.get("success") == bool(wa.get("success") or sms.get("success"))


def test_whatsapp_send_test_requires_phone():
    tok = _admin_token()
    r = requests.post(
        f"{BASE_URL}/api/admin/whatsapp/send-test",
        headers={"Authorization": f"Bearer {tok}"},
        json={},
        timeout=15,
    )
    assert r.status_code == 400
    body = r.json()
    assert "phone required" in (body.get("detail") or "").lower()


def test_whatsapp_send_test_sends_and_returns_diag():
    tok = _admin_token()
    r = requests.post(
        f"{BASE_URL}/api/admin/whatsapp/send-test",
        headers={"Authorization": f"Bearer {tok}"},
        json={"phone": "9999999999", "message": "unit-test ping"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    assert set(data.keys()) >= {"success", "phone_input", "phone_sent_to", "hint"}
    assert data["phone_sent_to"] == "919999999999"
    assert "24-hour" in data["hint"]
