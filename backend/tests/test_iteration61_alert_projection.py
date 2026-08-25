"""Iteration 61 — maybe_alert_admin projection fix (Atlas maxTimeMS / read timeout).

Covers:
  * maybe_alert_admin: projected doc contains ONLY the alert fields (no image_url)
  * alert payload correctness (customer phone, store, amount, bill no, reason)
  * dedup semantics per (bill_id, status) still intact after projection
  * per-status independence (pending_review vs rejected)
  * guards: unknown status, missing bill
  * send_admin_bill_alert message content over WhatsApp + SMS
  * insert_bill_and_alert fires the alert
  * _bill_alert_scanner_loop-style projection feeding maybe_alert_admin
  * regression: GET /api/bills, GET /api/bills/{id}, POST /api/bills/{id}/reprocess,
    GET /api/bills/{id}/image
"""
import asyncio
import base64
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

sys.path.insert(0, "/app/backend")
import server  # noqa: E402

CREDS_PATH = Path("/app/memory/test_credentials.md")

try:
    _LOOP = asyncio.get_event_loop_policy().get_event_loop()
    if _LOOP.is_closed():
        raise RuntimeError
except RuntimeError:
    _LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _run(coro):
    return _LOOP.run_until_complete(coro)


def _admin_creds():
    content = CREDS_PATH.read_text(encoding="utf-8")
    block = content.split("## Admin Dashboard")[1]
    u = re.search(r"Username:\s*`([^`]+)`", block).group(1)
    p = re.search(r"Password:\s*`([^`]+)`", block).group(1)
    return u, p


@pytest.fixture(scope="module")
def admin_token():
    u, p = _admin_creds()
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"username": u, "password": p}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in {r.json()}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ------------------------------------------------------------------ seed data
BIG_IMAGE = "data:image/jpeg;base64," + base64.b64encode(b"X" * 900_000).decode()
_created = []


def _seed_bill(status="pending_review", **over):
    bid = str(uuid.uuid4())
    doc = {
        "id": bid,
        "user_id": f"TEST_user_{bid[:8]}",
        "user_phone": "9876543210",
        "store_name": "TEST_Zara",
        "amount": 2499.0,
        "bill_no": "TEST-INV-0091",
        "status": status,
        "rejection_reason": "TEST duplicate bill number",
        "image_url": BIG_IMAGE,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update(over)
    _run(server.db.bills.insert_one(dict(doc)))
    _created.append(bid)
    return bid


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    if _created:
        _run(server.db.bills.delete_many({"id": {"$in": _created}}))


# ------------------------------------------------- maybe_alert_admin projection
class TestMaybeAlertAdminProjection:
    def test_projection_only_returns_alert_fields(self):
        bid = _seed_bill()
        seen = {}

        async def fake_alert(event, bill, reason=None):
            seen["event"] = event
            seen["bill"] = dict(bill)
            seen["reason"] = reason

        with mock.patch.object(server, "send_admin_bill_alert", side_effect=fake_alert):
            _run(server.maybe_alert_admin(bid, "pending_review"))

        assert seen, "send_admin_bill_alert was never called"
        b = seen["bill"]
        # heavy payload must NOT be transferred
        assert "image_url" not in b, "projection leaked image_url (root-cause field)"
        assert "_id" not in b
        assert set(b.keys()) <= {
            "id", "user_phone", "store_name", "amount", "bill_no",
            "rejection_reason", "admin_alerts_sent",
        }, f"unexpected projected fields: {b.keys()}"
        # all fields consumed by send_admin_bill_alert are present & correct
        assert b["id"] == bid
        assert b["user_phone"] == "9876543210"
        assert b["store_name"] == "TEST_Zara"
        assert b["amount"] == 2499.0
        assert b["bill_no"] == "TEST-INV-0091"
        assert b["rejection_reason"] == "TEST duplicate bill number"
        assert seen["event"] == "pending_review"

    def test_dedup_marker_persisted(self):
        bid = _seed_bill()
        with mock.patch.object(server, "send_admin_bill_alert", new=mock.AsyncMock()):
            _run(server.maybe_alert_admin(bid, "pending_review"))
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "admin_alerts_sent": 1}))
        assert isinstance(doc.get("admin_alerts_sent"), dict)
        assert doc["admin_alerts_sent"].get("pending_review"), "dedup marker not written"

    def test_second_call_same_status_is_deduped(self):
        bid = _seed_bill()
        m = mock.AsyncMock()
        with mock.patch.object(server, "send_admin_bill_alert", new=m):
            _run(server.maybe_alert_admin(bid, "pending_review"))
            _run(server.maybe_alert_admin(bid, "pending_review"))
            _run(server.maybe_alert_admin(bid, "pending_review"))
        assert m.await_count == 1, f"alert sent {m.await_count} times (dedup broken)"

    def test_different_status_alerts_independently(self):
        bid = _seed_bill()
        m = mock.AsyncMock()
        with mock.patch.object(server, "send_admin_bill_alert", new=m):
            _run(server.maybe_alert_admin(bid, "pending_review"))
            _run(server.maybe_alert_admin(bid, "rejected", "TEST bad photo"))
            _run(server.maybe_alert_admin(bid, "rejected", "TEST bad photo"))
        assert m.await_count == 2
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "admin_alerts_sent": 1}))
        assert set(doc["admin_alerts_sent"].keys()) == {"pending_review", "rejected"}

    def test_explicit_reason_overrides_stored_reason(self):
        bid = _seed_bill()
        seen = {}

        async def fake_alert(event, bill, reason=None):
            seen["reason"] = reason

        with mock.patch.object(server, "send_admin_bill_alert", side_effect=fake_alert):
            _run(server.maybe_alert_admin(bid, "rejected", "TEST explicit reason"))
        assert seen["reason"] == "TEST explicit reason"

    def test_unknown_status_and_missing_bill_are_noops(self):
        bid = _seed_bill()
        m = mock.AsyncMock()
        with mock.patch.object(server, "send_admin_bill_alert", new=m):
            _run(server.maybe_alert_admin(bid, "approved"))
            _run(server.maybe_alert_admin("", "rejected"))
            _run(server.maybe_alert_admin(str(uuid.uuid4()), "rejected"))
        assert m.await_count == 0

    def test_backfilled_bill_still_alerts_for_new_status(self):
        """Legacy backfill writes admin_alerts_sent={'backfill': ts} — must not
        block a genuine status alert."""
        bid = _seed_bill(admin_alerts_sent={"backfill": "2026-01-01T00:00:00Z"})
        m = mock.AsyncMock()
        with mock.patch.object(server, "send_admin_bill_alert", new=m):
            _run(server.maybe_alert_admin(bid, "pending_review"))
        assert m.await_count == 1


# --------------------------------------------------- send_admin_bill_alert body
class TestSendAdminBillAlert:
    def test_whatsapp_and_sms_payload(self):
        bid = _seed_bill()
        bill = _run(server.db.bills.find_one(
            {"id": bid},
            {"_id": 0, "id": 1, "user_phone": 1, "store_name": 1, "amount": 1,
             "bill_no": 1, "rejection_reason": 1, "admin_alerts_sent": 1},
        ))
        wa, sms = [], []

        async def fake_wa(to, msg):
            wa.append((to, msg))

        async def fake_sms(to, msg):
            sms.append((to, msg))

        with mock.patch.object(server, "send_whatsapp_text", side_effect=fake_wa), \
             mock.patch.object(server, "send_sms_text", side_effect=fake_sms):
            _run(server.send_admin_bill_alert("pending_review", bill))

        assert len(wa) == len(server.ADMIN_ALERT_PHONES) >= 1
        assert len(sms) == len(server.ADMIN_ALERT_PHONES)
        to, msg = wa[0]
        assert to.startswith("91") and len(to) == 12, f"phone not normalised: {to}"
        assert "PENDING REVIEW" in msg
        assert "9876543210" in msg
        assert "TEST_Zara" in msg
        assert "2499" in msg
        assert "TEST-INV-0091" in msg
        assert bid[:8] in msg
        assert "duplicate bill number" in msg
        s_msg = sms[0][1]
        assert "TEST_Zara" in s_msg and "TEST-INV-0091" in s_msg

    def test_missing_optional_fields_do_not_crash(self):
        wa = []

        async def fake_wa(to, msg):
            wa.append(msg)

        with mock.patch.object(server, "send_whatsapp_text", side_effect=fake_wa), \
             mock.patch.object(server, "send_sms_text", new=mock.AsyncMock()):
            _run(server.send_admin_bill_alert("rejected", {"id": "abcdef123456"}))
        assert wa and "REJECTED" in wa[0]
        assert "Amount: -" in wa[0]


# ------------------------------------------------------- callers of the helper
class TestCallers:
    def test_insert_bill_and_alert_fires_alert(self):
        bid = str(uuid.uuid4())
        _created.append(bid)
        doc = {
            "id": bid, "user_id": "TEST_u", "user_phone": "9876543210",
            "store_name": "TEST_HM", "amount": 100.0, "bill_no": "TEST-1",
            "status": "pending_review", "image_url": BIG_IMAGE,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        m = mock.AsyncMock()

        async def go():
            with mock.patch.object(server, "send_admin_bill_alert", new=m):
                rid = await server.insert_bill_and_alert(doc)
                await asyncio.sleep(1.5)
                return rid

        rid = _run(go())
        assert rid == bid
        assert m.await_count == 1, "insert_bill_and_alert did not fire the alert"
        saved = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "admin_alerts_sent": 1}))
        assert saved["admin_alerts_sent"].get("pending_review")

    def test_scanner_style_projection_flow(self):
        """Mirror _bill_alert_scanner_loop: find(projection id+reason) -> alert."""
        bid = _seed_bill(status="rejected")
        m = mock.AsyncMock()

        async def go():
            cursor = server.db.bills.find(
                {"id": bid, "status": "rejected", "admin_alerts_sent.rejected": {"$exists": False}},
                {"_id": 0, "id": 1, "rejection_reason": 1},
            ).limit(50)
            n = 0
            with mock.patch.object(server, "send_admin_bill_alert", new=m):
                async for b in cursor:
                    assert "image_url" not in b
                    await server.maybe_alert_admin(b["id"], "rejected", b.get("rejection_reason"))
                    n += 1
            return n

        assert _run(go()) == 1
        assert m.await_count == 1


# --------------------------------------------------------------- API regression
class TestBillEndpointsRegression:
    def test_bills_list(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/bills?limit=5", headers=auth_headers, timeout=120)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert isinstance(data.get("bills"), list)
        assert isinstance(data.get("total"), int)
        for b in data["bills"]:
            assert "_id" not in b
            assert "image_url" not in b, "list response still carries base64 image_url"

    def test_bills_list_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/bills?limit=1", timeout=60)
        assert r.status_code in (401, 403), r.status_code

    def test_bill_details(self, auth_headers):
        bid = _seed_bill(status="pending_review")
        r = requests.get(f"{BASE_URL}/api/bills/{bid}", headers=auth_headers, timeout=120)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["bill"]["id"] == bid
        assert body["bill"]["store_name"] == "TEST_Zara"
        assert "_id" not in body["bill"]

    def test_bill_details_404(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/bills/{uuid.uuid4()}", headers=auth_headers, timeout=60)
        assert r.status_code == 404

    def test_bill_image(self, auth_headers):
        bid = _seed_bill()
        r = requests.get(f"{BASE_URL}/api/bills/{bid}/image", headers=auth_headers, timeout=120)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert "image_url" in j or "image" in j or j.get("error"), j

    def test_reprocess_rejects_wrong_status(self, auth_headers):
        bid = _seed_bill(status="approved")
        r = requests.post(f"{BASE_URL}/api/bills/{bid}/reprocess", headers=auth_headers, timeout=120)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"

    def test_reprocess_404(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/bills/{uuid.uuid4()}/reprocess",
                          headers=auth_headers, timeout=120)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_reprocess_queues_pending_bill(self, auth_headers):
        bid = _seed_bill(status="pending_review", store_name="TEST_UnknownBrandXYZ")
        r = requests.post(f"{BASE_URL}/api/bills/{bid}/reprocess", headers=auth_headers, timeout=120)
        assert r.status_code in (200, 202, 409), f"{r.status_code} {r.text[:300]}"
        if r.status_code in (200, 202):
            assert isinstance(r.json(), dict)
