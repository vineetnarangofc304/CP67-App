"""Iteration 65 — verify the one-line auth-claim fix in routes/admin_diy.py:69.

_current_consumer now accepts payload['role'] == 'consumer' OR payload['type'] == 'consumer'.
Consumer tokens minted by routes/consumer.py carry {'type': 'consumer'} only.

Covers:
- GET  /api/consumer/popups/active  with a real consumer JWT  -> 200 (was 403)
- POST /api/consumer/popups/dismiss with a real consumer JWT  -> 200 (was 403)
- Dismissal persistence (once-frequency popup disappears after dismiss)
- No privilege escalation: admin JWT rejected on consumer popup routes,
  consumer JWT rejected on all admin DIY routes, garbage/absent tokens rejected.
"""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

ADMIN = {"username": "admin", "password": "CP67Admin@2025"}
CONSUMER_PHONE = "9876543210"
CONSUMER_OTP = "1234"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(client):
    r = client.post(f"{BASE_URL}/api/admin/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("token") or r.json().get("access_token")
    assert token
    return token


@pytest.fixture(scope="module")
def consumer_token(client):
    r = client.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": CONSUMER_PHONE}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"send-otp failed {r.status_code}: {r.text[:300]}")
    v = client.post(
        f"{BASE_URL}/api/consumer/auth/verify-otp",
        json={"phone": CONSUMER_PHONE, "otp": CONSUMER_OTP},
        timeout=30,
    )
    if v.status_code != 200:
        pytest.fail(f"verify-otp failed {v.status_code}: {v.text[:300]}")
    token = v.json().get("token") or v.json().get("access_token")
    assert token
    return token


@pytest.fixture(scope="module")
def created_popup_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(client, admin_token, created_popup_ids):
    yield
    for pid in created_popup_ids:
        client.delete(
            f"{BASE_URL}/api/admin/diy/popups/{pid}",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )


# ---------- fix verification ----------
def test_popups_active_with_consumer_token_returns_200(client, consumer_token):
    r = client.get(
        f"{BASE_URL}/api/consumer/popups/active",
        headers={"Authorization": f"Bearer {consumer_token}"},
        timeout=30,
    )
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"
    body = r.json()
    assert "popup" in body
    assert "_id" not in str(body)


def test_popups_dismiss_with_consumer_token_returns_200(client, consumer_token):
    r = client.post(
        f"{BASE_URL}/api/consumer/popups/dismiss",
        json={"popup_id": f"TEST_nonexistent_{uuid.uuid4()}"},
        headers={"Authorization": f"Bearer {consumer_token}"},
        timeout=30,
    )
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"
    assert r.json().get("success") is True


def test_active_then_dismiss_then_hidden(client, admin_token, consumer_token, created_popup_ids):
    """End-to-end: admin creates a high-priority popup, consumer sees it, dismisses it, no longer sees it."""
    create = client.post(
        f"{BASE_URL}/api/admin/diy/popups",
        json={
            "title": "TEST_iter65_popup",
            "body": "iteration 65 auth fix check",
            "show_frequency": "once",
            "priority": 9999,
            "active": True,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    assert create.status_code == 200, create.text[:300]
    popup = create.json()["popup"]
    pid = popup["id"]
    created_popup_ids.append(pid)

    ch = {"Authorization": f"Bearer {consumer_token}"}
    active = client.get(f"{BASE_URL}/api/consumer/popups/active", headers=ch, timeout=30)
    assert active.status_code == 200, active.text[:300]
    got = active.json().get("popup")
    assert got is not None, "newly created highest-priority popup not returned"
    assert got["id"] == pid, f"expected {pid}, got {got.get('id')} (title={got.get('title')})"

    d = client.post(
        f"{BASE_URL}/api/consumer/popups/dismiss", json={"popup_id": pid}, headers=ch, timeout=30
    )
    assert d.status_code == 200, d.text[:300]

    after = client.get(f"{BASE_URL}/api/consumer/popups/active", headers=ch, timeout=30)
    assert after.status_code == 200
    after_popup = after.json().get("popup")
    assert after_popup is None or after_popup["id"] != pid, "dismissed once-popup still returned"


# ---------- no privilege escalation ----------
@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/api/admin/diy/popups", None),
        ("POST", "/api/admin/diy/popups", {"title": "TEST_x", "body": "b"}),
        ("GET", "/api/admin/diy/push/history", None),
        ("POST", "/api/admin/diy/push/broadcast", {"title": "TEST_x", "body": "b", "dry_run": True}),
        ("GET", "/api/admin/diy/referral-config", None),
        ("PUT", "/api/admin/diy/referral-config", {"referrer_points": 1}),
        ("PATCH", "/api/admin/diy/popups/does-not-exist", {"title": "TEST_x"}),
        ("DELETE", "/api/admin/diy/popups/does-not-exist", None),
    ],
)
def test_consumer_token_cannot_access_admin_diy(client, consumer_token, method, path, payload):
    r = client.request(
        method,
        f"{BASE_URL}{path}",
        json=payload,
        headers={"Authorization": f"Bearer {consumer_token}"},
        timeout=30,
    )
    assert r.status_code in (401, 403), f"{method} {path} allowed consumer token: {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/api/consumer/popups/active", None),
        ("POST", "/api/consumer/popups/dismiss", {"popup_id": "x"}),
    ],
)
def test_admin_token_rejected_on_consumer_popups(client, admin_token, method, path, payload):
    r = client.request(
        method,
        f"{BASE_URL}{path}",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    # Backend rejects admin tokens on consumer routes with 401 "Invalid token type"
    # (403 also acceptable) — both are a hard reject.
    assert r.status_code in (401, 403), f"{method} {path} accepted admin token: {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/api/consumer/popups/active", None),
        ("POST", "/api/consumer/popups/dismiss", {"popup_id": "x"}),
    ],
)
def test_no_token_and_garbage_token_rejected(client, method, path, payload):
    r = client.request(method, f"{BASE_URL}{path}", json=payload, timeout=30)
    assert r.status_code in (401, 403), f"{method} {path} unauth: {r.status_code}"

    r2 = client.request(
        method,
        f"{BASE_URL}{path}",
        json=payload,
        headers={"Authorization": "Bearer not.a.real.jwt"},
        timeout=30,
    )
    assert r2.status_code == 401, f"{method} {path} garbage token: {r2.status_code} {r2.text[:200]}"
