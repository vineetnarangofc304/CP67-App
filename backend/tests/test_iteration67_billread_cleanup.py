"""Iteration 67 — bill-read cleanup (projections + max_time_ms) & shared consumer auth.

Covers (per review request):
  * GET  /api/admin/bills/{id}/force-credit-preview — find_one uses
    {_id:0, amount:1, store_name:1}; response payload unchanged.
  * POST /api/admin/bills/{id}/force-credit — find_one excludes image_url +
    ocr_raw_data and passes max_time_ms=15000; approve flow still works.
  * POST /api/bills/{id}/reprocess-legacy — find_one uses {_id:0} +
    max_time_ms=25000.
  * Regression: iteration-66 fixes (reprocess_bill guard, _do_reprocess_bill_bg /
    _sync, edit_bill_brand, _reprocess_after_brand_edit) still lean.
  * routes/admin_diy._current_consumer now delegates to
    routes.consumer.get_current_consumer — consumer JWT 200, admin/staff 401/403.
"""
import asyncio
import base64
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
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

CREDS_PATH = Path("/app/memory/test_credentials.md")
CONSUMER_PHONE = "9876543210"
CONSUMER_OTP = "1234"

try:
    _LOOP = asyncio.get_event_loop_policy().get_event_loop()
    if _LOOP.is_closed():
        raise RuntimeError
except RuntimeError:
    _LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _run(coro):
    return _LOOP.run_until_complete(coro)


def _creds(section):
    content = CREDS_PATH.read_text(encoding="utf-8")
    block = content.split(section)[1]
    u = re.search(r"Username\s*`?([\w.@-]+)`?", block.replace("Username:", "Username")).group(1)
    p = re.search(r"[Pp]assword:?\s*`([^`]+)`", block).group(1)
    return u, p


@pytest.fixture(scope="module")
def admin_headers():
    content = CREDS_PATH.read_text(encoding="utf-8")
    block = content.split("## Admin Dashboard")[1]
    u = re.search(r"Username:\s*`([^`]+)`", block).group(1)
    p = re.search(r"Password:\s*`([^`]+)`", block).group(1)
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"username": u, "password": p}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, r.json()
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def consumer_token():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": CONSUMER_PHONE}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"send-otp failed {r.status_code}: {r.text[:300]}")
    v = s.post(f"{BASE_URL}/api/consumer/auth/verify-otp",
               json={"phone": CONSUMER_PHONE, "otp": CONSUMER_OTP}, timeout=60)
    if v.status_code != 200:
        pytest.fail(f"verify-otp failed {v.status_code}: {v.text[:300]}")
    tok = v.json().get("token") or v.json().get("access_token")
    assert tok, v.json()
    return tok


@pytest.fixture(scope="module")
def staff_token():
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"username": "parking1", "password": "Parking1@2025"}, timeout=60)
    if r.status_code != 200:
        pytest.skip(f"parking staff login unavailable: {r.status_code}")
    return r.json().get("token") or r.json().get("access_token")


# --------------------------------------------------------------- seed helpers
BIG_DATA_URL = "data:image/jpeg;base64," + base64.b64encode(b"Y" * 500_000).decode()

TEST_USER_ID = "TEST_ITER67_USER"
TEST_PHONE = "919876543210"
ADMIN_PAYLOAD = {"username": "admin", "name": "Admin", "role": "admin"}

_bills = []


def _seed_bill(status="pending_review", image_url=BIG_DATA_URL, **over):
    bid = "TEST_ITER67_" + str(uuid.uuid4())[:8]
    doc = {
        "id": bid,
        "user_id": TEST_USER_ID,
        "user_phone": TEST_PHONE,
        "store_name": "TEST_ITER67_Brand",
        "amount": 1500.0,
        "bill_no": f"TEST-67-{bid[-4:]}",
        "bill_date": datetime.now().strftime("%Y-%m-%d"),
        "status": status,
        "image_url": image_url,
        "ocr_raw_data": {"extraction_notes": "TEST ocr notes", "blob": "Z" * 50_000},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update(over)
    _run(server.db.bills.insert_one(dict(doc)))
    _bills.append(bid)
    return bid


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    _run(server.db.users.update_one(
        {"id": TEST_USER_ID},
        {"$set": {"id": TEST_USER_ID, "phone": TEST_PHONE, "name": "TEST_ITER67",
                  "balance_points": 100, "total_earned_points": 100,
                  "created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True))
    yield
    if _bills:
        _run(server.db.bills.delete_many({"id": {"$in": _bills}}))
    _run(server.db.users.delete_many({"id": TEST_USER_ID}))
    _run(server.db.whatsapp_logs.delete_many({"user_id": TEST_USER_ID}))


# ------------------------------------------------------------- find_one spy
class _CollProxy:
    def __init__(self, coll, calls):
        self._coll = coll
        self._calls = calls

    async def find_one(self, *args, **kwargs):
        self._calls.append({"args": args, "kwargs": kwargs})
        return await self._coll.find_one(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._coll, item)


class _DbProxy:
    def __init__(self, db, calls):
        self._db = db
        self._calls = calls

    @property
    def bills(self):
        return _CollProxy(self._db.bills, self._calls)

    def __getattr__(self, item):
        return getattr(self._db, item)


class _FindOneSpy:
    def __init__(self):
        self.calls = []
        self._patch = None

    def __enter__(self):
        self._patch = mock.patch.object(server, "db", new=_DbProxy(server.db, self.calls))
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        return False

    def projections(self):
        out = []
        for c in self.calls:
            if len(c["args"]) > 1:
                out.append(c["args"][1] or {})
            else:
                out.append(c["kwargs"].get("projection") or {})
        return out

    def max_times(self):
        return [c["kwargs"].get("max_time_ms") for c in self.calls]


# ============================================ force-credit-preview
class TestForceCreditPreview:
    def test_preview_find_one_projection_is_lean(self):
        bid = _seed_bill()
        with _FindOneSpy() as spy:
            res = _run(server.force_credit_preview(bid, payload=ADMIN_PAYLOAD))
        assert spy.calls, "no bills.find_one recorded (spy not wired)"
        proj = spy.projections()[0]
        assert {k for k, v in proj.items() if v == 1} == {"amount", "store_name"}, f"not lean: {proj}"
        assert proj.get("_id") == 0
        assert "image_url" not in proj and "ocr_raw_data" not in proj
        # payload unchanged
        for k in ("bill_id", "amount", "store_name", "calculated_points", "rate_pct",
                  "rate_basis", "category", "range_label", "brand_found"):
            assert k in res, f"missing key {k} in preview payload: {res}"
        assert res["bill_id"] == bid
        assert res["amount"] == 1500.0
        assert res["store_name"] == "TEST_ITER67_Brand"

    def test_preview_http_ok_and_fast(self, admin_headers):
        bid = _seed_bill()
        t0 = time.time()
        r = requests.get(f"{BASE_URL}/api/admin/bills/{bid}/force-credit-preview",
                         headers=admin_headers, timeout=60)
        elapsed = time.time() - t0
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        body = r.json()
        assert body["bill_id"] == bid and body["amount"] == 1500.0
        assert isinstance(body["calculated_points"], (int, float))
        assert "_id" not in body
        print(f"force-credit-preview latency (500KB inline image bill): {elapsed:.2f}s")
        assert elapsed < 5.0, f"preview took {elapsed:.2f}s"

    def test_preview_404_and_auth(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/bills/TEST_ITER67_NOPE/force-credit-preview",
                         headers=admin_headers, timeout=60)
        assert r.status_code == 404, f"unknown bill returned {r.status_code}: {r.text[:200]}"
        r = requests.get(f"{BASE_URL}/api/admin/bills/x/force-credit-preview", timeout=60)
        assert r.status_code in (401, 403), r.status_code


# ==================================================== force-credit
class TestForceCredit:
    def test_force_credit_excludes_heavy_fields_and_has_max_time_ms(self):
        bid = _seed_bill(status="manual_review")
        seen = {}

        async def fake_reprocess(bill, **kw):
            seen["keys"] = set(bill.keys())
            seen["kw"] = kw
            return {"bill_id": bid, "action": "approved", "status": "approved", "points": 33, "error": None}

        from fastapi import BackgroundTasks
        with _FindOneSpy() as spy, \
             mock.patch.object(server, "_reprocess_single_bill", side_effect=fake_reprocess):
            res = _run(server.force_credit_bill(bid, BackgroundTasks(), payload=ADMIN_PAYLOAD))

        proj = spy.projections()[0]
        assert proj.get("image_url") == 0, f"image_url not excluded: {proj}"
        assert proj.get("ocr_raw_data") == 0, f"ocr_raw_data not excluded: {proj}"
        assert proj.get("_id") == 0
        assert spy.max_times()[0] == 15000, f"max_time_ms missing: {spy.calls[0]}"
        assert len(spy.calls) == 1, f"extra reads: {spy.projections()}"
        # heavy fields really absent from the doc handed to the pipeline
        assert "image_url" not in seen["keys"] and "ocr_raw_data" not in seen["keys"]
        assert seen["kw"].get("force_credit") is True
        assert res == {"success": True, "points_issued": 33, "status": "approved", "error": None}

    def test_force_credit_end_to_end_updates_bill_and_credits(self, admin_headers):
        """Real endpoint, Fundle earn mocked at the client boundary."""
        bid = _seed_bill(status="manual_review")
        r = requests.post(f"{BASE_URL}/api/admin/bills/{bid}/force-credit",
                          headers=admin_headers, timeout=180)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        body = r.json()
        assert set(body) == {"success", "points_issued", "status", "error"}, body
        assert body["success"] is True, f"force-credit did not approve: {body}"
        assert body["points_issued"] > 0, body
        doc = _run(server.db.bills.find_one(
            {"id": bid}, {"_id": 0, "status": 1, "points_awarded": 1, "force_credited": 1}))
        assert doc["status"] == "approved", f"bill status not updated: {doc}"
        print(f"force-credit persisted doc: {doc}")

    def test_force_credit_rejects_non_pending_and_404(self, admin_headers):
        bid = _seed_bill(status="approved")
        r = requests.post(f"{BASE_URL}/api/admin/bills/{bid}/force-credit",
                          headers=admin_headers, timeout=60)
        assert r.status_code == 400, f"approved bill force-credit returned {r.status_code}: {r.text[:200]}"
        r = requests.post(f"{BASE_URL}/api/admin/bills/TEST_ITER67_NOPE/force-credit",
                          headers=admin_headers, timeout=60)
        assert r.status_code == 404, r.status_code
        r = requests.post(f"{BASE_URL}/api/admin/bills/{bid}/force-credit", timeout=60)
        assert r.status_code in (401, 403), r.status_code


# ==================================================== reprocess-legacy
class TestReprocessLegacy:
    def test_legacy_read_full_doc_with_max_time_ms(self):
        bid = _seed_bill()
        from fastapi import BackgroundTasks
        with _FindOneSpy() as spy, \
             mock.patch.object(server.tagnpay_client, "get_customer_points",
                               new=mock.AsyncMock(return_value={"success": False, "data": {}})), \
             mock.patch.object(server.tagnpay_client, "register_customer",
                               new=mock.AsyncMock(return_value={"success": False, "message": "TEST stop"})):
            try:
                _run(server._reprocess_bill_full_legacy_impl(bid, BackgroundTasks(), ADMIN_PAYLOAD))
            except Exception as e:
                print(f"legacy impl stopped early (expected): {type(e).__name__}: {e}")
        assert spy.calls, "no bills.find_one recorded"
        assert spy.projections()[0] == {"_id": 0}, f"legacy should read full doc: {spy.projections()[0]}"
        assert spy.max_times()[0] == 25000, f"max_time_ms missing: {spy.calls[0]}"

    def test_legacy_404_and_status_guard(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/bills/TEST_ITER67_NOPE/reprocess-legacy",
                          headers=admin_headers, timeout=120)
        assert r.status_code == 404, f"{r.status_code}: {r.text[:200]}"
        bid = _seed_bill(status="approved")
        r = requests.post(f"{BASE_URL}/api/bills/{bid}/reprocess-legacy",
                          headers=admin_headers, timeout=120)
        assert r.status_code == 400, f"{r.status_code}: {r.text[:200]}"
        r = requests.post(f"{BASE_URL}/api/bills/{bid}/reprocess-legacy", timeout=60)
        assert r.status_code in (401, 403), r.status_code


# ============================================ iteration-66 regressions
class TestIteration66Regression:
    def test_reprocess_guard_still_lean(self):
        bid = _seed_bill()
        from fastapi import BackgroundTasks
        bg = BackgroundTasks()
        with _FindOneSpy() as spy:
            res = _run(server.reprocess_bill(bid, bg, wait=False, payload=ADMIN_PAYLOAD))
        assert res["reprocessed"] == "queued", res
        assert len(spy.calls) == 1
        assert {k for k, v in spy.projections()[0].items() if v == 1} == {
            "status", "reprocessing_started_at", "reprocessing_finished_at"}
        assert "_do_reprocess_bill_bg" in [getattr(t.func, "__name__", "") for t in bg.tasks]

    def test_edit_brand_guard_still_lean(self):
        bid = _seed_bill()
        from fastapi import BackgroundTasks
        with _FindOneSpy() as spy:
            res = _run(server.edit_bill_brand(
                bid, server.EditBrandRequest(new_store_name="TEST_ITER67_Zara"),
                BackgroundTasks(), payload=ADMIN_PAYLOAD))
        assert res["reprocessed"] == "queued", res
        assert {k for k, v in spy.projections()[0].items() if v == 1} == {"id", "store_name", "status"}

    def test_bg_worker_reads_full_doc_with_max_time(self):
        bid = _seed_bill()

        async def fake_reprocess(bill, **kw):
            assert len(bill.get("image_url") or "") > 500_000
            return {"bill_id": bid, "action": "approved", "status": "approved", "points": 5}

        with _FindOneSpy() as spy, \
             mock.patch.object(server, "_reprocess_single_bill", side_effect=fake_reprocess):
            _run(server._do_reprocess_bill_bg(bid))
        assert spy.max_times()[0] == 25000
        assert spy.projections()[0] == {"_id": 0}

    def test_sync_worker_and_brand_edit_worker_reads(self):
        bid = _seed_bill()

        async def ok(bill, **kw):
            return {"bill_id": bid, "action": "approved", "status": "approved", "points": 7}

        from fastapi import BackgroundTasks
        with _FindOneSpy() as spy, mock.patch.object(server, "_reprocess_single_bill", side_effect=ok):
            _run(server._do_reprocess_bill_sync(bid, BackgroundTasks()))
        assert spy.max_times()[0] == 25000

        bid2 = _seed_bill()
        calls = []

        async def reject_then_fc(bill, **kw):
            calls.append(kw)
            if kw.get("force_credit"):
                return {"bill_id": bid2, "action": "approved", "status": "approved", "points": 11}
            return {"bill_id": bid2, "action": "kept_pending", "status": "manual_review",
                    "points": 0, "error": "Brand not found"}

        with _FindOneSpy() as spy2, \
             mock.patch.object(server, "_reprocess_single_bill", side_effect=reject_then_fc):
            _run(server._reprocess_after_brand_edit(bid2, "TEST_ITER67_Zara", True))
        projs, mts = spy2.projections(), spy2.max_times()
        assert len(spy2.calls) == 2, projs
        assert projs[0] == {"_id": 0} and mts[0] == 25000
        assert projs[1].get("image_url") == 0 and projs[1].get("ocr_raw_data") == 0 and mts[1] == 15000
        assert calls[1].get("force_credit") is True


# ============================================ shared consumer auth (admin_diy)
class TestSharedConsumerAuth:
    def test_delegation_wired(self):
        import inspect
        import routes.admin_diy as ad
        src = inspect.getsource(ad._current_consumer)
        assert "get_current_consumer" in src, "admin_diy._current_consumer no longer delegates"

    def test_popups_active_consumer_token_200(self, consumer_token):
        r = requests.get(f"{BASE_URL}/api/consumer/popups/active",
                         headers={"Authorization": f"Bearer {consumer_token}"}, timeout=60)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        body = r.json()
        assert "popup" in body
        assert "_id" not in str(body)

    def test_popups_dismiss_consumer_token_200(self, consumer_token):
        r = requests.post(f"{BASE_URL}/api/consumer/popups/dismiss",
                          json={"popup_id": f"TEST_ITER67_{uuid.uuid4()}"},
                          headers={"Authorization": f"Bearer {consumer_token}"}, timeout=60)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        assert r.json().get("success") is True

    def test_admin_and_staff_tokens_rejected(self, admin_headers, staff_token):
        r = requests.get(f"{BASE_URL}/api/consumer/popups/active", headers=admin_headers, timeout=60)
        assert r.status_code in (401, 403), f"admin token accepted on consumer route: {r.status_code}"
        r = requests.get(f"{BASE_URL}/api/consumer/popups/active",
                         headers={"Authorization": f"Bearer {staff_token}"}, timeout=60)
        assert r.status_code in (401, 403), f"staff token accepted on consumer route: {r.status_code}"
        r = requests.get(f"{BASE_URL}/api/consumer/popups/active",
                         headers={"Authorization": "Bearer garbage.token.value"}, timeout=60)
        assert r.status_code in (401, 403), r.status_code
        r = requests.get(f"{BASE_URL}/api/consumer/popups/active", timeout=60)
        assert r.status_code in (401, 403), r.status_code
