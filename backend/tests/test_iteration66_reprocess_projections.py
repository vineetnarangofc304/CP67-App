"""Iteration 66 — reprocess / edit-brand large-field projection fixes.

Covers (per review request):
  * POST /api/admin/bills/{id}/edit-brand (queued mode) — fast, returns
    {success:true, reprocessed:'queued'}; initial find_one projection is lean
    ({id,store_name,status}) and never pulls image_url.
  * POST /api/admin/bills/{id}/edit-brand?wait_for_result=true (sync path) —
    both find_ones pass max_time_ms; the 2nd reload excludes image_url +
    ocr_raw_data.
  * POST /api/bills/{id}/reprocess (queued) — fast; guard find_one projects
    only status/reprocessing_started_at/reprocessing_finished_at.
  * _do_reprocess_bill_bg / _do_reprocess_bill_sync / _reprocess_after_brand_edit
    — full doc read with max_time_ms=25000 (structural, via find_one spy).
  * _reprocess_single_bill objstore: branch — resolves bytes via
    storage.aresolve_objstore_url and base64-encodes them for Fundle.
  * Regression: iteration 61-65 test modules still collect.
"""
import asyncio
import base64
import os
import re
import subprocess
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
def auth_headers():
    u, p = _admin_creds()
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"username": u, "password": p}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in login response: {r.json()}"
    return {"Authorization": f"Bearer {tok}"}


# --------------------------------------------------------------- seed helpers
BIG_B64 = base64.b64encode(b"Y" * 500_000).decode()
BIG_DATA_URL = "data:image/jpeg;base64," + BIG_B64
OBJSTORE_URL = "objstore:cp67-mall/bills/TEST_ITER66_fake.jpg"

TEST_USER_ID = "TEST_ITER66_USER"
TEST_PHONE = "919876543210"
ADMIN_PAYLOAD = {"username": "admin", "name": "Admin", "role": "admin"}

_bills = []


def _seed_user():
    _run(server.db.users.update_one(
        {"id": TEST_USER_ID},
        {"$set": {
            "id": TEST_USER_ID,
            "phone": TEST_PHONE,
            "name": "TEST_ITER66",
            "balance_points": 100,
            "total_earned_points": 100,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    ))


def _seed_bill(status="pending_review", image_url=BIG_DATA_URL, **over):
    bid = "TEST_ITER66_" + str(uuid.uuid4())[:8]
    doc = {
        "id": bid,
        "user_id": TEST_USER_ID,
        "user_phone": TEST_PHONE,
        "store_name": "TEST_WrongBrand",
        "amount": 1500.0,
        "bill_no": f"TEST-66-{bid[-4:]}",
        "bill_date": datetime.now().strftime("%Y-%m-%d"),
        "status": status,
        "rejection_reason": "TEST system reason",
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
    _seed_user()
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


# =========================================================== edit-brand (queued)
class TestEditBrandQueued:
    def test_edit_brand_queued_http_is_fast_and_persists(self, auth_headers):
        bid = _seed_bill()
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
            json={"new_store_name": "TEST_Zara", "reprocess": True,
                  "auto_force_credit_on_fundle_reject": True},
            headers=auth_headers, timeout=60,
        )
        elapsed = time.time() - t0
        assert r.status_code == 200, f"{r.status_code} in {elapsed:.1f}s: {r.text[:400]}"
        body = r.json()
        assert body.get("success") is True, body
        assert body.get("reprocessed") == "queued", body
        assert body.get("store_name") == "TEST_Zara", body
        print(f"edit-brand queued latency (500KB inline image bill): {elapsed:.2f}s")
        assert elapsed < 5.0, f"edit-brand queued took {elapsed:.2f}s (expected sub-second)"

        doc = _run(server.db.bills.find_one(
            {"id": bid}, {"_id": 0, "store_name": 1, "reprocessing_started_at": 1, "admin_notes": 1}))
        assert doc["store_name"] == "TEST_Zara"
        assert doc.get("reprocessing_started_at"), "reprocessing_started_at not set"
        assert "TEST_WrongBrand" in doc.get("admin_notes", "")

    def test_edit_brand_initial_find_one_is_lean(self):
        """Initial guard read must NOT pull the full doc / image_url."""
        bid = _seed_bill()
        from fastapi import BackgroundTasks
        bg = BackgroundTasks()
        with _FindOneSpy() as spy:
            res = _run(server.edit_bill_brand(
                bid, server.EditBrandRequest(new_store_name="TEST_Zara"), bg, payload=ADMIN_PAYLOAD))

        assert res["success"] is True and res["reprocessed"] == "queued", res
        assert spy.calls, "no bills.find_one recorded (spy not wired)"
        proj = spy.projections()[0]
        assert proj, "initial find_one has NO projection (full doc transferred)"
        keys = {k for k, v in proj.items() if v == 1}
        assert keys == {"id", "store_name", "status"}, f"projection not lean: {proj}"
        assert proj.get("image_url") != 1
        # queued mode must not read the bill again on the request thread
        assert len(spy.calls) == 1, f"queued path made {len(spy.calls)} bills.find_one calls: {spy.projections()}"
        names = [getattr(t.func, "__name__", str(t.func)) for t in bg.tasks]
        assert "_reprocess_after_brand_edit" in names, f"bg reprocess not queued: {names}"

    def test_edit_brand_no_reprocess_flag(self):
        bid = _seed_bill()
        from fastapi import BackgroundTasks
        res = _run(server.edit_bill_brand(
            bid, server.EditBrandRequest(new_store_name="TEST_OnlyRename", reprocess=False),
            BackgroundTasks(), payload=ADMIN_PAYLOAD))
        assert res == {"success": True, "reprocessed": False, "store_name": "TEST_OnlyRename"}
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "store_name": 1}))
        assert doc["store_name"] == "TEST_OnlyRename"

    def test_edit_brand_validation_and_404(self, auth_headers):
        bid = _seed_bill()
        r = requests.post(f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
                          json={"new_store_name": "   ", "reprocess": False},
                          headers=auth_headers, timeout=60)
        assert r.status_code == 400, f"blank brand returned {r.status_code}: {r.text[:200]}"

        r = requests.post(f"{BASE_URL}/api/admin/bills/TEST_ITER66_NOPE/edit-brand",
                          json={"new_store_name": "TEST_Zara", "reprocess": False},
                          headers=auth_headers, timeout=60)
        assert r.status_code == 404, f"unknown bill returned {r.status_code}: {r.text[:200]}"

        r = requests.post(f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
                          json={"new_store_name": "TEST_Zara"}, timeout=60)
        assert r.status_code in (401, 403), f"unauthenticated edit-brand returned {r.status_code}"


# ============================================================ edit-brand (sync)
class TestEditBrandSyncPath:
    def test_sync_path_reads_use_max_time_ms_and_skip_heavy_fields(self):
        bid = _seed_bill()
        calls = []

        async def fake_reprocess(bill, **kw):
            calls.append((bill.get("id"), kw))
            if kw.get("force_credit"):
                return {"bill_id": bill.get("id"), "action": "approved",
                        "status": "approved", "points": 15, "error": None}
            return {"bill_id": bill.get("id"), "action": "kept_pending",
                    "status": "manual_review", "points": 0,
                    "error": "Brand not found in Fundle master"}

        from fastapi import BackgroundTasks
        with _FindOneSpy() as spy, \
             mock.patch.object(server, "_reprocess_single_bill", side_effect=fake_reprocess):
            res = _run(server.edit_bill_brand(
                bid, server.EditBrandRequest(new_store_name="TEST_Zara", wait_for_result=True),
                BackgroundTasks(), payload=ADMIN_PAYLOAD))

        projs, mts = spy.projections(), spy.max_times()
        assert len(spy.calls) == 3, f"expected 3 reads on sync path, got {len(spy.calls)}: {projs}"

        # 1) lean guard read
        assert {k for k, v in projs[0].items() if v == 1} == {"id", "store_name", "status"}
        # 2) full doc read WITH max_time_ms headroom
        assert mts[1] == 25000, f"sync full reload missing max_time_ms=25000: {spy.calls[1]}"
        # 3) fallback reload excludes heavy fields, with max_time_ms
        assert projs[2].get("image_url") == 0, f"3rd read did not exclude image_url: {projs[2]}"
        assert projs[2].get("ocr_raw_data") == 0, f"3rd read did not exclude ocr_raw_data: {projs[2]}"
        assert mts[2] == 15000, f"3rd read missing max_time_ms: {spy.calls[2]}"

        # force-credit fallback fired and result surfaced
        assert res["fallback"] == "force_credit", res
        assert res["success"] is True and res["points"] == 15, res
        assert len(calls) == 2 and calls[1][1].get("force_credit") is True, calls

    def test_sync_path_success_no_fallback(self):
        bid = _seed_bill()

        async def fake_reprocess(bill, **kw):
            return {"bill_id": bill.get("id"), "action": "approved",
                    "status": "approved", "points": 42, "error": None}

        from fastapi import BackgroundTasks
        with _FindOneSpy() as spy, \
             mock.patch.object(server, "_reprocess_single_bill", side_effect=fake_reprocess):
            res = _run(server.edit_bill_brand(
                bid, server.EditBrandRequest(new_store_name="TEST_Zara", wait_for_result=True),
                BackgroundTasks(), payload=ADMIN_PAYLOAD))
        assert res["success"] is True and res["points"] == 42 and res["reprocessed"] is True, res
        assert len(spy.calls) == 2, f"expected 2 reads, got {spy.projections()}"


# ================================================== POST /api/bills/{id}/reprocess
class TestReprocessBill:
    def test_reprocess_queued_http_is_fast(self, auth_headers):
        bid = _seed_bill()
        t0 = time.time()
        r = requests.post(f"{BASE_URL}/api/bills/{bid}/reprocess", headers=auth_headers, timeout=60)
        elapsed = time.time() - t0
        assert r.status_code == 200, f"{r.status_code} in {elapsed:.1f}s: {r.text[:400]}"
        body = r.json()
        assert body.get("success") is True and body.get("reprocessed") == "queued", body
        assert body.get("bill_id") == bid, body
        print(f"reprocess queued latency (500KB inline image bill): {elapsed:.2f}s")
        assert elapsed < 5.0, f"reprocess queued took {elapsed:.2f}s (expected sub-second)"
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "reprocessing_started_at": 1, "reprocessing_by": 1}))
        assert doc.get("reprocessing_started_at"), "reprocessing_started_at not stamped"
        assert doc.get("reprocessing_by") == "admin"

    def test_reprocess_guard_projection_is_lean(self):
        bid = _seed_bill()
        from fastapi import BackgroundTasks
        bg = BackgroundTasks()
        with _FindOneSpy() as spy:
            res = _run(server.reprocess_bill(bid, bg, wait=False, payload=ADMIN_PAYLOAD))
        assert res["reprocessed"] == "queued", res
        assert len(spy.calls) == 1, f"queued reprocess made {len(spy.calls)} reads: {spy.projections()}"
        proj = spy.projections()[0]
        keys = {k for k, v in proj.items() if v == 1}
        assert keys == {"status", "reprocessing_started_at", "reprocessing_finished_at"}, f"guard projection: {proj}"
        assert proj.get("image_url") != 1
        names = [getattr(t.func, "__name__", str(t.func)) for t in bg.tasks]
        assert "_do_reprocess_bill_bg" in names, f"bg worker not queued: {names}"

    def test_reprocess_double_click_returns_409(self, auth_headers):
        bid = _seed_bill(reprocessing_started_at=datetime.now(timezone.utc).isoformat())
        r = requests.post(f"{BASE_URL}/api/bills/{bid}/reprocess", headers=auth_headers, timeout=60)
        assert r.status_code == 409, f"in-flight reprocess returned {r.status_code}: {r.text[:200]}"

    def test_reprocess_stale_guard_allows_retry(self):
        old = "2020-01-01T00:00:00+00:00"
        bid = _seed_bill(reprocessing_started_at=old)
        from fastapi import BackgroundTasks
        res = _run(server.reprocess_bill(bid, BackgroundTasks(), wait=False, payload=ADMIN_PAYLOAD))
        assert res["reprocessed"] == "queued", res

    def test_reprocess_wrong_status_400_and_404_and_auth(self, auth_headers):
        bid = _seed_bill(status="approved")
        r = requests.post(f"{BASE_URL}/api/bills/{bid}/reprocess", headers=auth_headers, timeout=60)
        assert r.status_code == 400, f"approved bill reprocess returned {r.status_code}: {r.text[:200]}"

        r = requests.post(f"{BASE_URL}/api/bills/TEST_ITER66_NOPE/reprocess", headers=auth_headers, timeout=60)
        assert r.status_code == 404, f"unknown bill returned {r.status_code}: {r.text[:200]}"

        r = requests.post(f"{BASE_URL}/api/bills/{bid}/reprocess", timeout=60)
        assert r.status_code in (401, 403), f"unauthenticated reprocess returned {r.status_code}"


# =========================================================== background workers
class TestBackgroundWorkers:
    def test_do_reprocess_bill_bg_uses_max_time_ms_and_stamps_finish(self):
        bid = _seed_bill()
        seen = {}

        async def fake_reprocess(bill, **kw):
            seen["image_len"] = len(bill.get("image_url") or "")
            seen["kw"] = kw
            return {"bill_id": bid, "action": "approved", "status": "approved", "points": 5}

        with _FindOneSpy() as spy, \
             mock.patch.object(server, "_reprocess_single_bill", side_effect=fake_reprocess):
            _run(server._do_reprocess_bill_bg(bid))

        assert len(spy.calls) == 1, spy.projections()
        assert spy.max_times()[0] == 25000, f"bg worker read missing max_time_ms=25000: {spy.calls[0]}"
        assert spy.projections()[0] == {"_id": 0}, f"bg worker should read the full doc: {spy.projections()[0]}"
        assert seen["image_len"] > 500_000, "bg worker did not pass the image to the pipeline"
        assert seen["kw"].get("force_credit_on_fundle_reject") is True
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "reprocessing_finished_at": 1}))
        assert doc.get("reprocessing_finished_at"), "reprocessing_finished_at not stamped"

    def test_do_reprocess_bill_bg_records_error_and_finishes(self):
        bid = _seed_bill()

        async def boom(bill, **kw):
            raise RuntimeError("TEST boom")

        with mock.patch.object(server, "_reprocess_single_bill", side_effect=boom):
            _run(server._do_reprocess_bill_bg(bid))
        doc = _run(server.db.bills.find_one(
            {"id": bid}, {"_id": 0, "reprocessing_error": 1, "reprocessing_finished_at": 1}))
        assert "TEST boom" in (doc.get("reprocessing_error") or "")
        assert doc.get("reprocessing_finished_at"), "finished_at not stamped on failure"

    def test_do_reprocess_bill_sync_uses_max_time_ms(self):
        bid = _seed_bill()

        async def fake_reprocess(bill, **kw):
            return {"bill_id": bid, "action": "approved", "status": "approved", "points": 7}

        from fastapi import BackgroundTasks
        with _FindOneSpy() as spy, \
             mock.patch.object(server, "_reprocess_single_bill", side_effect=fake_reprocess):
            res = _run(server._do_reprocess_bill_sync(bid, BackgroundTasks()))
        assert res == {"success": True, "points_earned": 7, "message": "Bill reprocessed successfully"}
        assert spy.max_times()[0] == 25000, f"sync worker read missing max_time_ms: {spy.calls[0]}"

    def test_reprocess_after_brand_edit_worker_reads(self):
        bid = _seed_bill()
        calls = []

        async def fake_reprocess(bill, **kw):
            calls.append(kw)
            if kw.get("force_credit"):
                return {"bill_id": bid, "action": "approved", "status": "approved", "points": 11}
            return {"bill_id": bid, "action": "kept_pending", "status": "manual_review",
                    "points": 0, "error": "Brand not found"}

        with _FindOneSpy() as spy, \
             mock.patch.object(server, "_reprocess_single_bill", side_effect=fake_reprocess):
            _run(server._reprocess_after_brand_edit(bid, "TEST_Zara", True))

        mts, projs = spy.max_times(), spy.projections()
        assert len(spy.calls) == 2, f"expected 2 reads, got {projs}"
        assert mts[0] == 25000, f"1st read missing max_time_ms=25000: {spy.calls[0]}"
        assert projs[0] == {"_id": 0}, projs[0]
        assert projs[1].get("image_url") == 0 and projs[1].get("ocr_raw_data") == 0, projs[1]
        assert mts[1] == 15000, f"2nd read missing max_time_ms: {spy.calls[1]}"
        assert len(calls) == 2 and calls[1].get("force_credit") is True, calls

    def test_reprocess_after_brand_edit_skips_force_credit_on_missing_image(self):
        bid = _seed_bill()
        calls = []

        async def fake_reprocess(bill, **kw):
            calls.append(kw)
            return {"bill_id": bid, "action": "no_image", "status": "manual_review",
                    "points": 0, "error": "Fundle: bill_file — no file was submitted"}

        with mock.patch.object(server, "_reprocess_single_bill", side_effect=fake_reprocess):
            _run(server._reprocess_after_brand_edit(bid, "TEST_Zara", True))
        assert len(calls) == 1, f"force-credit fallback should be suppressed for missing image: {calls}"


# ================================== _reprocess_single_bill objstore: branch
class TestObjstoreBranch:
    def test_objstore_bytes_sent_to_fundle(self):
        bid = _seed_bill(image_url=OBJSTORE_URL)
        earn_kwargs = {}
        resolved = []

        async def fake_objstore(url):
            resolved.append(url)
            return (b"OBJSTOREBYTES" * 100, "image/jpeg")

        async def fake_earn(**kw):
            earn_kwargs.update(kw)
            return {"success": True, "data": {"earned_points": 25, "total_points": 125}}

        from fastapi import BackgroundTasks
        with mock.patch("storage.aresolve_objstore_url", side_effect=fake_objstore), \
             mock.patch.object(server.tagnpay_client, "get_customer_points",
                               new=mock.AsyncMock(return_value={"success": True, "data": {"balance_points": 100}})), \
             mock.patch.object(server.tagnpay_client, "earn_points", side_effect=fake_earn):
            bill = _run(server.db.bills.find_one({"id": bid}, {"_id": 0}))
            res = _run(server._reprocess_single_bill(
                bill, re_ocr=False, send_whatsapp_flag=False, background_tasks=BackgroundTasks()))

        assert resolved == [OBJSTORE_URL], f"aresolve_objstore_url not invoked: {resolved}"
        b64 = earn_kwargs.get("bill_image_base64")
        assert b64, "objstore bill sent NO image base64 to Fundle"
        assert base64.b64decode(b64) == b"OBJSTOREBYTES" * 100
        assert res["action"] == "approved" and res["points"] == 25, res

    def test_objstore_failure_reports_no_image(self):
        bid = _seed_bill(image_url=OBJSTORE_URL, amount=0, bill_no="")
        from fastapi import BackgroundTasks
        with mock.patch("storage.aresolve_objstore_url", new=mock.AsyncMock(return_value=None)), \
             mock.patch.object(server.tagnpay_client, "get_customer_points",
                               new=mock.AsyncMock(return_value={"success": True, "data": {"balance_points": 100}})):
            bill = _run(server.db.bills.find_one({"id": bid}, {"_id": 0}))
            res = _run(server._reprocess_single_bill(
                bill, re_ocr=False, send_whatsapp_flag=False, background_tasks=BackgroundTasks()))
        assert res["action"] == "no_image", res
        assert "Object storage returned no data" in (res.get("error") or ""), res


# ================================================================ regression
class TestPreviousIterationsStillCollect:
    def test_iter61_to_65_collect(self):
        files = [
            "/app/backend/tests/test_iteration61_alert_projection.py",
            "/app/backend/tests/test_iteration62_bill_projections.py",
            "/app/backend/tests/test_iteration63_alert_cooldown_throttle.py",
            "/app/backend/tests/test_iteration64_smoke.py",
            "/app/backend/tests/test_iteration65_consumer_popups_auth.py",
        ]
        for f in files:
            assert Path(f).exists(), f"missing previous test file: {f}"
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--collect-only", "-q", *files],
            capture_output=True, text=True, cwd="/app/backend", timeout=240,
        )
        assert proc.returncode == 0, f"collection failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-1000:]}"
        print(proc.stdout.strip().splitlines()[-1])
