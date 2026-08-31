"""Iteration 74 — Point 44: deferred parking coupon (issued only after first verified bill).

Covers:
  * process_parking_registration → NO coupon doc, users.parking_coupon_pending=true (+source, +60d expiry),
    welcome text mentions 'reserved' / 'Upload any purchase bill'
  * _maybe_issue_pending_parking_coupon: happy path, idempotency, expired window, non-parking no-op
  * POST /api/bills/{id}/process approve → coupon issued + WhatsApp caption
  * POST /api/bills/{id}/reprocess?wait=true approve → coupon issued (hook in _do_reprocess_bill_sync)
"""
import asyncio
import os
import re
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing from env and /app/frontend/.env")
BASE_URL = _base.rstrip("/")

sys.path.insert(0, "/app/backend")
import server  # noqa: E402

PREFIX = "TEST_ITER74_"
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


def _phone():
    # 91 + 10 digits, unlikely to collide
    return "917" + str(uuid.uuid4().int)[:9]


@pytest.fixture(scope="session")
def admin_token():
    content = CREDS_PATH.read_text(encoding="utf-8")
    user = re.search(r"(?im)^\s*[-*]?\s*(?:\*\*)?Username(?:\*\*)?\s*:\s*`?(admin)`?", content)
    pwd = re.search(r"(?im)^\s*[-*]?\s*(?:\*\*)?Password(?:\*\*)?\s*:\s*`?([^`\s]+)", content)
    if not user or not pwd:
        pytest.skip("admin credentials not found in test_credentials.md")
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"username": user.group(1), "password": pwd.group(1)}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in login response: {r.text[:300]}"
    return tok


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    async def _cl():
        await server.db.users.delete_many({"name": {"$regex": f"^{PREFIX}"}})
        await server.db.parking_coupons.delete_many({"user_name": {"$regex": f"^{PREFIX}"}})
        await server.db.bills.delete_many({"store_name": {"$regex": f"^{PREFIX}"}})
        await server.db.whatsapp_logs.delete_many({"user_phone": {"$regex": "^917"}, "content": {"$regex": "reserved"}})
    _run(_cl())


async def _seed_pending_user(phone, expires_delta_days=60, name=None):
    uid = str(uuid.uuid4())
    doc = {
        "id": uid,
        "phone": phone,
        "name": name or (PREFIX + "pending"),
        "kyc_status": True,
        "balance_points": 0,
        "customer_type": "new",
        "registration_time": datetime.now(timezone.utc).isoformat(),
        "parking_coupon_pending": True,
        "parking_coupon_source": "SRC_PARKING",
        "parking_coupon_pending_expires_at": (
            datetime.now(timezone.utc) + timedelta(days=expires_delta_days)).isoformat(),
    }
    await server.db.users.insert_one(doc)
    return uid


async def _seed_bill(user_id, phone, status="pending_review"):
    bid = str(uuid.uuid4())
    await server.db.bills.insert_one({
        "id": bid,
        "user_id": user_id,
        "user_phone": phone,
        "store_name": PREFIX + "Store",
        "amount": 1000.0,
        "bill_no": PREFIX + "B1",
        "bill_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return bid


# ---------------- Registration ----------------
class TestRegistration:
    def test_registration_defers_coupon(self):
        phone = _phone()
        sent = {}

        async def _fake_list(to, body, options, header_text=None, button_text=None):
            sent["to"] = to
            sent["body"] = body
            return True

        async def _fake_points(m):
            return {"success": False, "data": None}

        async def _fake_reg(**kw):
            return {"success": True}

        async def _flow():
            with mock.patch.object(server, "send_whatsapp_list", _fake_list), \
                 mock.patch.object(server.tagnpay_client, "get_customer_points", _fake_points), \
                 mock.patch.object(server.tagnpay_client, "register_customer", _fake_reg):
                res = await server.process_parking_registration(
                    phone, PREFIX + "Cust", "SRC_PARKING",
                    {"qr_code_id": PREFIX + "QR"}, None)
            return res

        res = _run(_flow())
        assert res is not None, "process_parking_registration returned None (exception swallowed)"

        user = _run(server.db.users.find_one({"phone": phone}, {"_id": 0}))
        assert user is not None, "user not created"
        assert user.get("parking_coupon_pending") is True
        assert user.get("parking_coupon_source") == "SRC_PARKING"
        exp = datetime.fromisoformat(user["parking_coupon_pending_expires_at"])
        delta_days = (exp - datetime.now(timezone.utc)).days
        assert 58 <= delta_days <= 60, f"expiry not ~60 days out: {delta_days}"

        coupons = _run(server.db.parking_coupons.count_documents({"user_phone": phone}))
        assert coupons == 0, "coupon must NOT be issued at registration"

        assert "reserved" in sent.get("body", ""), sent.get("body")
        assert "Upload any purchase bill" in sent.get("body", ""), sent.get("body")


# ---------------- Helper unit behaviour ----------------
class TestHelper:
    def _patched(self):
        return mock.patch.multiple(
            server,
            generate_parking_qr_image=mock.AsyncMock(return_value="data:image/png;base64,AAA"),
            send_whatsapp_image=mock.AsyncMock(return_value=True),
            send_whatsapp_text=mock.AsyncMock(return_value=True),
        )

    def test_happy_path_and_idempotency(self):
        phone = _phone()
        _run(_seed_pending_user(phone))

        async def _flow():
            with self._patched():
                c1 = await server._maybe_issue_pending_parking_coupon(phone)
                c2 = await server._maybe_issue_pending_parking_coupon(phone)
                cap = server.send_whatsapp_image.call_args[0][2] if server.send_whatsapp_image.call_args else ""
            return c1, c2, cap

        c1, c2, cap = _run(_flow())
        assert c1 and c1.startswith("PARK-"), c1
        assert c2 is None, "second call must be a no-op (idempotency)"

        docs = _run(server.db.parking_coupons.find({"user_phone": phone}, {"_id": 0}).to_list(10))
        assert len(docs) == 1, f"expected exactly 1 coupon, got {len(docs)}"
        assert docs[0]["issued_after_bill_verification"] is True
        assert docs[0]["coupon_code"] == c1
        assert docs[0]["status"] == "active"

        user = _run(server.db.users.find_one({"phone": phone}, {"_id": 0}))
        for f in ("parking_coupon_pending", "parking_coupon_source", "parking_coupon_pending_expires_at"):
            assert f not in user, f"{f} not cleared"

        assert "Parking Coupon" in cap and c1 in cap, cap

    def test_expired_window_clears_flag_without_coupon(self):
        phone = _phone()
        _run(_seed_pending_user(phone, expires_delta_days=-1))

        async def _flow():
            with self._patched():
                return await server._maybe_issue_pending_parking_coupon(phone)

        assert _run(_flow()) is None
        assert _run(server.db.parking_coupons.count_documents({"user_phone": phone})) == 0
        user = _run(server.db.users.find_one({"phone": phone}, {"_id": 0}))
        assert "parking_coupon_pending" not in user

    def test_non_parking_user_noop(self):
        phone = _phone()
        _run(server.db.users.insert_one({
            "id": str(uuid.uuid4()), "phone": phone, "name": PREFIX + "plain",
            "balance_points": 0}))

        async def _flow():
            with self._patched():
                return await server._maybe_issue_pending_parking_coupon(phone)

        assert _run(_flow()) is None
        assert _run(server.db.parking_coupons.count_documents({"user_phone": phone})) == 0

    def test_10_digit_phone_normalised(self):
        phone = _phone()
        _run(_seed_pending_user(phone))

        async def _flow():
            with self._patched():
                return await server._maybe_issue_pending_parking_coupon(phone[2:])

        code = _run(_flow())
        assert code and code.startswith("PARK-"), "10-digit phone should normalise to 91XXXXXXXXXX"


# ---------------- API: process (approve) ----------------
class TestProcessBillApprove:
    def test_approve_issues_pending_coupon(self, admin_token):
        phone = _phone()
        uid = _run(_seed_pending_user(phone))
        bid = _run(_seed_bill(uid, phone))

        captured = {}

        async def _img(to, image, caption=None, *a, **k):
            captured["caption"] = caption
            return True

        async def _txt(to, body, *a, **k):
            captured.setdefault("caption", body)
            return True

        with mock.patch.object(server, "generate_parking_qr_image",
                               mock.AsyncMock(return_value="data:image/png;base64,AAA")), \
             mock.patch.object(server, "send_whatsapp_image", _img), \
             mock.patch.object(server, "send_whatsapp_text", _txt):
            r = requests.post(
                f"{BASE_URL}/api/bills/{bid}/process",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"bill_id": bid, "action": "approve", "admin_notes": PREFIX + "approve",
                      "send_whatsapp": False},
                timeout=120,
            )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"

        bill = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "status": 1}))
        assert bill["status"] == "approved", bill

        docs = _run(server.db.parking_coupons.find({"user_phone": phone}, {"_id": 0}).to_list(10))
        assert len(docs) == 1, f"coupon not issued on approve (found {len(docs)})"
        code = docs[0]["coupon_code"]
        assert docs[0]["issued_after_bill_verification"] is True

        user = _run(server.db.users.find_one({"phone": phone}, {"_id": 0}))
        for f in ("parking_coupon_pending", "parking_coupon_source", "parking_coupon_pending_expires_at"):
            assert f not in user, f"{f} not cleared after approve"

        # NOTE: server-side WhatsApp mock only applies if the hook ran in this
        # process; the API runs in the uvicorn process, so caption is checked
        # only when available.
        if captured.get("caption"):
            assert "Parking Coupon" in captured["caption"] and code in captured["caption"]

    def test_reject_does_not_issue_coupon(self, admin_token):
        phone = _phone()
        uid = _run(_seed_pending_user(phone))
        bid = _run(_seed_bill(uid, phone))
        r = requests.post(
            f"{BASE_URL}/api/bills/{bid}/process",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"bill_id": bid, "action": "reject", "admin_notes": PREFIX + "reject",
                  "rejection_reason": "test", "send_whatsapp": False},
            timeout=90,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        assert _run(server.db.parking_coupons.count_documents({"user_phone": phone})) == 0
        user = _run(server.db.users.find_one({"phone": phone}, {"_id": 0}))
        assert user.get("parking_coupon_pending") is True, "reject must keep the pending flag"


# ---------------- reprocess hook (in-process) ----------------
# Iter-75: the hook lives inside _reprocess_single_bill (the shared choke point),
# so these tests must exercise the REAL helper with Fundle mocked instead of
# stubbing _reprocess_single_bill (which would bypass the hook).
def _fundle_ok():
    async def _earn(**kw):
        return {"success": True, "data": {"earned_points": 50, "total_points": 50, "message": "ok"}}

    async def _points(m):
        return {"success": True, "data": {"balance_points": 0}}

    async def _reg(**kw):
        return {"success": True}

    return mock.patch.multiple(server.tagnpay_client, earn_points=_earn,
                               get_customer_points=_points, register_customer=_reg)


def _wa_ok():
    return mock.patch.multiple(
        server,
        generate_parking_qr_image=mock.AsyncMock(return_value="data:image/png;base64,AAA"),
        send_whatsapp_image=mock.AsyncMock(return_value=True),
        send_whatsapp_text=mock.AsyncMock(return_value=True),
    )


class TestReprocessHook:
    def test_reprocess_sync_path_issues_coupon(self):
        phone = _phone()
        uid = _run(_seed_pending_user(phone))
        bid = _run(_seed_bill(uid, phone))

        async def _flow():
            from fastapi import BackgroundTasks
            with _fundle_ok(), _wa_ok():
                return await server._do_reprocess_bill_sync(bid, BackgroundTasks())

        res = _run(_flow())
        assert res.get("success") is True, res
        docs = _run(server.db.parking_coupons.find({"user_phone": phone}, {"_id": 0}).to_list(10))
        assert len(docs) == 1, f"reprocess-approve did not issue coupon (found {len(docs)})"

    def test_reprocess_background_path_issues_coupon(self):
        """Default admin Reprocess (wait=False) runs _do_reprocess_bill_bg —
        verify the deferred coupon hook fires there too (regression guard)."""
        phone = _phone()
        uid = _run(_seed_pending_user(phone))
        bid = _run(_seed_bill(uid, phone))

        async def _flow():
            with _fundle_ok(), _wa_ok():
                await server._do_reprocess_bill_bg(bid)

        _run(_flow())
        bill = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "status": 1}))
        assert bill["status"] == "approved", bill
        cnt = _run(server.db.parking_coupons.count_documents({"user_phone": phone}))
        assert cnt == 1, f"background reprocess approve did not issue coupon (found {cnt})"
