"""Iteration 75 — Point 44 deferred parking coupon: ALL approval paths.

Verifies the coupon hook now fires from the shared choke points:
  * _reprocess_single_bill  (admin queued reprocess wait=false, bulk, edit-brand)
  * _reprocess_single_bill force-credit-on-Fundle-reject fallback
  * _reprocess_single_bill explicit force_credit=True branch  (gap check)
  * process_bill_image      (WhatsApp auto_approved + force-credit fallback)
  * routes/consumer.process_bill_ocr (consumer-app upload, status='approved')
Plus negative paths (pending_review → no coupon) and concurrency idempotency.
"""
import asyncio
import base64
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
from routes import consumer as consumer_mod  # noqa: E402

PREFIX = "TEST_ITER75_"

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
    return "917" + str(uuid.uuid4().int)[:9]


CREDS_PATH = Path("/app/memory/test_credentials.md")


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
        users = await server.db.users.find(
            {"name": {"$regex": f"^{PREFIX}"}}, {"_id": 0, "phone": 1}).to_list(500)
        phones = [u["phone"] for u in users if u.get("phone")]
        await server.db.users.delete_many({"name": {"$regex": f"^{PREFIX}"}})
        await server.db.bills.delete_many({"store_name": {"$regex": f"^{PREFIX}"}})
        if phones:
            await server.db.bills.delete_many({"user_phone": {"$in": phones}})
            await server.db.parking_coupons.delete_many({"user_phone": {"$in": phones}})
        await server.db.parking_coupons.delete_many({"user_name": {"$regex": f"^{PREFIX}"}})
    _run(_cl())


async def _seed_pending_user(phone, name_suffix="u"):
    uid = str(uuid.uuid4())
    await server.db.users.insert_one({
        "id": uid,
        "phone": phone,
        "name": PREFIX + name_suffix,
        "kyc_status": True,
        "balance_points": 0,
        "customer_type": "new",
        "registration_time": datetime.now(timezone.utc).isoformat(),
        "parking_coupon_pending": True,
        "parking_coupon_source": "SRC_PARKING",
        "parking_coupon_pending_expires_at": (
            datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
    })
    return uid


async def _seed_bill(user_id, phone, status="pending_review"):
    bid = str(uuid.uuid4())
    await server.db.bills.insert_one({
        "id": bid,
        "user_id": user_id,
        "user_phone": phone,
        "store_name": PREFIX + "Store",
        "amount": 2000.0,
        "bill_no": PREFIX + uuid.uuid4().hex[:8].upper(),
        "bill_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return bid


def _coupon_count(phone):
    return _run(server.db.parking_coupons.count_documents({"user_phone": phone}))


def _user(phone):
    return _run(server.db.users.find_one({"phone": phone}, {"_id": 0}))


def _wa_patches():
    """Silence outbound WhatsApp + QR generation."""
    return mock.patch.multiple(
        server,
        generate_parking_qr_image=mock.AsyncMock(return_value="data:image/png;base64,AAA"),
        send_whatsapp_image=mock.AsyncMock(return_value=True),
        send_whatsapp_text=mock.AsyncMock(return_value=True),
        send_whatsapp_buttons=mock.AsyncMock(return_value=True),
        send_whatsapp_list=mock.AsyncMock(return_value=True),
    )


def _fundle_patches(earn_result):
    async def _earn(**kw):
        return earn_result

    async def _points(m):
        return {"success": True, "data": {"balance_points": 0}}

    async def _reg(**kw):
        return {"success": True}

    return mock.patch.multiple(
        server.tagnpay_client,
        earn_points=_earn,
        get_customer_points=_points,
        register_customer=_reg,
    )


_EARN_OK = {"success": True, "data": {"earned_points": 50, "total_points": 50, "message": "ok"}}
_EARN_BRAND_REJECT = {"success": False, "error": "Brand not found in master"}
_EARN_OTHER_FAIL = {"success": False, "error": "Fundle gateway timeout"}


# ---------------- _reprocess_single_bill (choke point) ----------------
class TestReprocessChokePoint:
    def test_reprocess_single_bill_approve_issues_coupon(self):
        phone = _phone()
        uid = _run(_seed_pending_user(phone, "rsb"))
        bid = _run(_seed_bill(uid, phone))

        async def _flow():
            bill = await server.db.bills.find_one({"id": bid}, {"_id": 0})
            from fastapi import BackgroundTasks
            with _wa_patches(), _fundle_patches(_EARN_OK):
                return await server._reprocess_single_bill(
                    bill, re_ocr=False, send_whatsapp_flag=False,
                    background_tasks=BackgroundTasks())

        res = _run(_flow())
        assert res.get("action") == "approved", res
        assert _coupon_count(phone) == 1, f"choke point did not issue coupon: {res}"
        u = _user(phone)
        for f in ("parking_coupon_pending", "parking_coupon_source",
                  "parking_coupon_pending_expires_at"):
            assert f not in u, f"{f} not cleared"

    def test_queued_reprocess_bg_issues_coupon(self):
        """Default admin Reprocess (wait=false) → _do_reprocess_bill_bg."""
        phone = _phone()
        uid = _run(_seed_pending_user(phone, "bg"))
        bid = _run(_seed_bill(uid, phone))

        async def _flow():
            with _wa_patches(), _fundle_patches(_EARN_OK):
                await server._do_reprocess_bill_bg(bid)

        _run(_flow())
        bill = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "status": 1}))
        assert bill["status"] == "approved", bill
        assert _coupon_count(phone) == 1, "background reprocess approve did not issue coupon"

    def test_reprocess_force_credit_fallback_issues_coupon(self):
        phone = _phone()
        uid = _run(_seed_pending_user(phone, "fcfb"))
        bid = _run(_seed_bill(uid, phone))

        async def _flow():
            with _wa_patches(), _fundle_patches(_EARN_BRAND_REJECT):
                await server._do_reprocess_bill_bg(bid)

        _run(_flow())
        bill = _run(server.db.bills.find_one({"id": bid}, {"_id": 0}))
        assert bill["status"] == "approved", f"force-credit fallback did not approve: {bill.get('rejection_reason')}"
        assert bill.get("force_credited") is True
        assert _coupon_count(phone) == 1, "force-credit fallback did not issue coupon"

    def test_reprocess_explicit_force_credit_issues_coupon(self):
        """Admin 'Force credit' (force_credit=True) skips Fundle entirely."""
        phone = _phone()
        uid = _run(_seed_pending_user(phone, "fcex"))
        bid = _run(_seed_bill(uid, phone))

        async def _flow():
            bill = await server.db.bills.find_one({"id": bid}, {"_id": 0})
            from fastapi import BackgroundTasks
            with _wa_patches(), _fundle_patches(_EARN_OK):
                return await server._reprocess_single_bill(
                    bill, re_ocr=False, send_whatsapp_flag=False,
                    background_tasks=BackgroundTasks(), force_credit=True)

        res = _run(_flow())
        assert res.get("action") == "approved", res
        assert _coupon_count(phone) == 1, (
            "explicit force_credit=True branch approves the bill but does NOT "
            "issue the deferred parking coupon (hook missing in that branch)")

    def test_reprocess_kept_pending_no_coupon(self):
        phone = _phone()
        uid = _run(_seed_pending_user(phone, "pend"))
        bid = _run(_seed_bill(uid, phone))

        async def _flow():
            bill = await server.db.bills.find_one({"id": bid}, {"_id": 0})
            from fastapi import BackgroundTasks
            with _wa_patches(), _fundle_patches(_EARN_OTHER_FAIL):
                return await server._reprocess_single_bill(
                    bill, re_ocr=False, send_whatsapp_flag=False,
                    background_tasks=BackgroundTasks())

        res = _run(_flow())
        assert res.get("action") != "approved", res
        assert _coupon_count(phone) == 0
        assert _user(phone).get("parking_coupon_pending") is True


# ---------------- WhatsApp path (process_bill_image) ----------------
def _ocr_ok(amount=2000.0):
    return {"success": True, "data": {
        "store_name": PREFIX + "Store",
        "bill_no": PREFIX + uuid.uuid4().hex[:8].upper(),
        "bill_date": datetime.now().strftime("%Y-%m-%d"),
        "amount": amount,
        "confidence_score": 0.95,
        "is_valid_bill": True,
        "tampering_detected": False,
        "image_quality": "good",
        "contains_cp67": True,
        "raw_text": "CP67 MALL TEST BILL",
        "items": [],
    }}


class TestWhatsAppPath:
    def _image(self):
        return "base64:" + base64.b64encode(
            f"iter75-{uuid.uuid4()}".encode()).decode()

    def _flow(self, phone, uid, earn_result, settings=None):
        async def _inner():
            from fastapi import BackgroundTasks
            user = await server.db.users.find_one({"id": uid}, {"_id": 0})
            ocr = _ocr_ok()

            async def _analyze(_b64):
                return ocr

            async def _settings():
                return settings if settings is not None else {}

            patches = [
                _wa_patches(),
                _fundle_patches(earn_result),
                mock.patch.object(server, "analyze_bill_image", _analyze),
                mock.patch.object(server, "_get_app_settings", _settings),
            ]
            for p in patches:
                p.__enter__()
            try:
                await server.process_bill_image(phone, user, self._image(), BackgroundTasks())
            finally:
                for p in reversed(patches):
                    p.__exit__(None, None, None)
        return _run(_inner())

    def test_whatsapp_auto_approved_issues_coupon(self):
        phone = _phone()
        uid = _run(_seed_pending_user(phone, "wa"))
        self._flow(phone, uid, _EARN_OK)

        bill = _run(server.db.bills.find_one({"user_phone": phone}, {"_id": 0}))
        assert bill is not None, "no bill inserted by process_bill_image"
        assert bill["status"] == "auto_approved", bill
        docs = _run(server.db.parking_coupons.find({"user_phone": phone}, {"_id": 0}).to_list(10))
        assert len(docs) == 1, f"WhatsApp auto-approve did not issue coupon (found {len(docs)})"
        assert docs[0]["coupon_code"].startswith("PARK-")
        assert docs[0]["issued_after_bill_verification"] is True
        u = _user(phone)
        assert "parking_coupon_pending" not in u

    def test_whatsapp_force_credit_fallback_issues_coupon(self):
        phone = _phone()
        uid = _run(_seed_pending_user(phone, "wafc"))
        self._flow(phone, uid, _EARN_BRAND_REJECT,
                   settings={"auto_force_credit_on_fundle_reject": True})

        bill = _run(server.db.bills.find_one({"user_phone": phone}, {"_id": 0}))
        assert bill is not None and bill["status"] == "auto_approved", bill
        assert _coupon_count(phone) == 1, "WhatsApp force-credit fallback did not issue coupon"

    def test_whatsapp_pending_review_no_coupon(self):
        phone = _phone()
        uid = _run(_seed_pending_user(phone, "wapend"))
        self._flow(phone, uid, _EARN_BRAND_REJECT,
                   settings={"auto_force_credit_on_fundle_reject": False})

        bill = _run(server.db.bills.find_one({"user_phone": phone}, {"_id": 0}))
        assert bill is not None and bill["status"] == "pending_review", bill
        assert _coupon_count(phone) == 0, "coupon must NOT be issued for pending_review"
        assert _user(phone).get("parking_coupon_pending") is True


# ---------------- Consumer-app upload path ----------------
class TestConsumerAppPath:
    def _flow(self, uid, phone, earn_result):
        async def _inner():
            bid = await _seed_bill(uid, phone, status="processing")
            ocr = _ocr_ok()

            async def _analyze(_b64):
                return ocr

            async def _earn(**kw):
                return earn_result

            async def _notify(*a, **k):
                return True

            b64 = base64.b64encode(f"c75-{uuid.uuid4()}".encode()).decode()
            with _wa_patches(), \
                 mock.patch.object(server, "analyze_bill_image", _analyze), \
                 mock.patch.object(consumer_mod._tagnpay_client, "earn_points", _earn), \
                 mock.patch.object(consumer_mod, "send_app_notification", _notify):
                await consumer_mod.process_bill_ocr(bid, b64, uid, phone)
            return bid
        return _run(_inner())

    def test_consumer_app_approved_issues_coupon(self):
        assert consumer_mod._db is not None, "consumer routes not initialised"
        phone = _phone()
        uid = _run(_seed_pending_user(phone, "capp"))
        bid = self._flow(uid, phone, {"success": True, "data": {"points_earned": 40}})

        bill = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "status": 1}))
        assert bill["status"] == "approved", bill
        assert _coupon_count(phone) == 1, "consumer-app approved upload did not issue coupon"
        assert "parking_coupon_pending" not in _user(phone)

    def test_consumer_app_pending_review_no_coupon(self):
        phone = _phone()
        uid = _run(_seed_pending_user(phone, "cappend"))
        bid = self._flow(uid, phone, {"success": False, "error": "fundle down"})

        bill = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "status": 1}))
        assert bill["status"] == "pending_review", bill
        assert _coupon_count(phone) == 0
        assert _user(phone).get("parking_coupon_pending") is True


# ---------------- Idempotency under concurrency ----------------
class TestConcurrency:
    def test_concurrent_calls_issue_single_coupon(self):
        phone = _phone()
        _run(_seed_pending_user(phone, "conc"))

        async def _flow():
            with _wa_patches():
                return await asyncio.gather(
                    *[server._maybe_issue_pending_parking_coupon(phone) for _ in range(6)])

        results = _run(_flow())
        issued = [r for r in results if r]
        assert len(issued) == 1, f"expected exactly 1 issuance, got {issued}"
        assert _coupon_count(phone) == 1


# ---------------- Live API: queued reprocess against the running server ----------------
class TestLiveQueuedReprocess:
    def test_live_queued_reprocess_issues_coupon(self, admin_token):
        """End-to-end through uvicorn: POST /api/bills/{id}/reprocess (wait=false).
        Fundle is real here; force_credit_on_fundle_reject=True is passed by the
        endpoint so the bill should still land 'approved'."""
        import time
        phone = _phone()
        uid = _run(_seed_pending_user(phone, "live"))
        bid = _run(_seed_bill(uid, phone))

        r = requests.post(f"{BASE_URL}/api/bills/{bid}/reprocess",
                          headers={"Authorization": f"Bearer {admin_token}"}, timeout=60)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"

        status = None
        for _ in range(30):
            time.sleep(2)
            bill = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "status": 1,
                                                              "reprocessing_finished_at": 1}))
            status = bill.get("status")
            if bill.get("reprocessing_finished_at"):
                break
        if status != "approved":
            pytest.skip(f"live reprocess did not approve (status={status}); "
                        "Fundle-dependent, coupon hook not exercised")
        assert _coupon_count(phone) == 1, "live queued reprocess approved but issued no coupon"


# ---------------- Static: duplicate hook / dead code removed ----------------
class TestSourceHygiene:
    def test_no_duplicate_hook_in_reprocess_wrapper(self):
        import inspect
        src = inspect.getsource(server._do_reprocess_bill_sync)
        assert "_maybe_issue_pending_parking_coupon" not in src, (
            "duplicate hook still present in _do_reprocess_bill_sync — would risk "
            "double-processing; the choke point already covers it")

    def test_helper_has_no_unreachable_except(self):
        import inspect
        src = inspect.getsource(server._maybe_issue_pending_parking_coupon)
        assert src.count("return coupon_code") == 1
        tail = src.split("return coupon_code", 1)[1]
        # only the outer handler may follow
        assert tail.count("except Exception") == 1, (
            "unreachable/duplicate except block still present after return coupon_code")
