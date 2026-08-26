"""Iteration 70 — edit-brand: ALL writes moved off the request thread.

Covers (per review request):
  * POST /api/admin/bills/{id}/edit-brand with reprocess=true + wait_for_result=false
    (the Fix Brand popup default) -> 200 {success:true, reprocessed:"queued"} fast,
    with ZERO update_one on the request thread and exactly ONE bg task queued.
  * `_apply_brand_edit_and_reprocess_bg` happy path -> single update_one, store_name /
    admin_notes / brand_edited_* / reprocessing_started_at persisted, reprocess invoked.
  * bg worker under Atlas hiccup (NetworkTimeout x2 then OK) -> 3 update_one calls,
    backoff ~1s + ~2s, final write persists, reprocess still runs.
  * bg worker with persistent write failure (NetworkTimeout x3) -> reprocess STILL invoked.
  * Rename-only path (reprocess=false) -> inline write with 1-shot retry; both fail -> 503.
  * Regression: 404 unknown bill, 400 blank name, 401/403 unauthenticated.
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
from fastapi import BackgroundTasks, HTTPException
from pymongo.errors import (AutoReconnect, ExecutionTimeout, NetworkTimeout,
                            ServerSelectionTimeoutError)

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
BIG_DATA_URL = "data:image/jpeg;base64," + base64.b64encode(b"Y" * 500_000).decode()
TEST_USER_ID = "TEST_ITER70_USER"
TEST_PHONE = "919876543210"
ADMIN_PAYLOAD = {"username": "admin", "name": "Admin", "role": "admin"}

_bills = []


def _seed_bill(status="pending_review", **over):
    bid = "TEST_ITER70_" + str(uuid.uuid4())[:8]
    doc = {
        "id": bid,
        "user_id": TEST_USER_ID,
        "user_phone": TEST_PHONE,
        "store_name": "TEST_WrongBrand",
        "amount": 1500.0,
        "bill_no": f"TEST-70-{bid[-4:]}",
        "bill_date": datetime.now().strftime("%Y-%m-%d"),
        "status": status,
        "image_url": BIG_DATA_URL,
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
        {"$set": {"id": TEST_USER_ID, "phone": TEST_PHONE, "name": "TEST_ITER70",
                  "balance_points": 100, "total_earned_points": 100,
                  "created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    ))
    yield
    _run(server.db.bills.delete_many({"id": {"$regex": "^TEST_ITER70_"}}))
    _run(server.db.users.delete_many({"id": TEST_USER_ID}))
    _run(server.db.whatsapp_logs.delete_many({"user_id": TEST_USER_ID}))


# --------------------------------------------------------- spy / fault proxies
class _CollProxy:
    """Records find_one/update_one calls and can inject faults per attempt."""

    def __init__(self, coll, rec, find_faults=None, update_faults=None):
        self._coll = coll
        self._rec = rec
        self._find_faults = list(find_faults or [])
        self._update_faults = list(update_faults or [])

    async def find_one(self, *args, **kwargs):
        self._rec["find_one"].append({"args": args, "kwargs": kwargs, "t": time.time()})
        if self._find_faults:
            fault = self._find_faults.pop(0)
            if fault is not None:
                raise fault
        return await self._coll.find_one(*args, **kwargs)

    async def update_one(self, *args, **kwargs):
        self._rec["update_one"].append({"args": args, "kwargs": kwargs, "t": time.time()})
        if self._update_faults:
            fault = self._update_faults.pop(0)
            if fault == "hang":
                await asyncio.sleep(30)
            elif fault is not None:
                raise fault
        return await self._coll.update_one(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._coll, item)


class _DbProxy:
    def __init__(self, db, rec, find_faults=None, update_faults=None):
        self._db = db
        self._rec = rec
        self._ff = find_faults
        self._uf = update_faults
        self._bills = None

    @property
    def bills(self):
        if self._bills is None:
            self._bills = _CollProxy(self._db.bills, self._rec, self._ff, self._uf)
        return self._bills

    def __getattr__(self, item):
        return getattr(self._db, item)


class _Spy:
    def __init__(self, find_faults=None, update_faults=None):
        self.rec = {"find_one": [], "update_one": []}
        self._proxy = _DbProxy(server.db, self.rec, find_faults, update_faults)
        self._patch = None

    def __enter__(self):
        self._patch = mock.patch.object(server, "db", new=self._proxy)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        return False

    def find_projections(self):
        out = []
        for c in self.rec["find_one"]:
            out.append((c["args"][1] if len(c["args"]) > 1 else c["kwargs"].get("projection")) or {})
        return out

    def find_max_times(self):
        return [c["kwargs"].get("max_time_ms") for c in self.rec["find_one"]]

    def update_gaps(self):
        ts = [c["t"] for c in self.rec["update_one"]]
        return [round(b - a, 2) for a, b in zip(ts, ts[1:])]


def _call(bid, bg=None, **kw):
    """Invoke the handler in-process; returns (result, BackgroundTasks)."""
    bg = bg or BackgroundTasks()
    req = server.EditBrandRequest(new_store_name=kw.pop("new_store_name", "TEST_Zara"), **kw)
    return _run(server.edit_bill_brand(bid, req, bg, payload=ADMIN_PAYLOAD)), bg


FRIENDLY = "MongoDB is under load — the brand edit didn't go through. Please retry in ~10s."


# ============================== 1. request thread does NO write, returns fast
class TestRequestThreadNoWrite:
    def test_http_queued_returns_fast(self, auth_headers):
        bid = _seed_bill()
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
            json={"new_store_name": "TEST_Zara", "reprocess": True,
                  "wait_for_result": False, "auto_force_credit_on_fundle_reject": True},
            headers=auth_headers, timeout=60)
        elapsed = time.time() - t0
        assert r.status_code == 200, f"{r.status_code} in {elapsed:.2f}s: {r.text[:400]}"
        body = r.json()
        assert body.get("success") is True and body.get("reprocessed") == "queued", body
        assert body.get("store_name") == "TEST_Zara", body
        print(f"iter70 queued HTTP latency (incl. network/ingress): {elapsed:.2f}s")
        assert elapsed < 5.0, f"took {elapsed:.2f}s"

    def test_no_update_one_on_request_thread_and_one_bg_task(self):
        bid = _seed_bill()
        with _Spy() as spy:
            res, bg = _call(bid, reprocess=True, wait_for_result=False)
        assert res["success"] is True and res["reprocessed"] == "queued", res
        assert len(spy.rec["update_one"]) == 0, (
            f"request thread performed {len(spy.rec['update_one'])} update_one call(s) — must be 0")
        assert len(spy.rec["find_one"]) == 1, spy.find_projections()
        proj = spy.find_projections()[0]
        assert {k for k, v in proj.items() if v == 1} == {"id", "store_name", "status"}, proj
        assert proj.get("_id") == 0
        assert spy.find_max_times() == [8000], spy.find_max_times()
        assert len(bg.tasks) == 1, f"expected 1 bg task, got {len(bg.tasks)}"
        assert bg.tasks[0].func is server._apply_brand_edit_and_reprocess_bg
        assert bg.tasks[0].args[0] == bid
        assert bg.tasks[0].args[2] == "TEST_Zara"
        # request thread must NOT have mutated the doc
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "store_name": 1}))
        assert doc["store_name"] == "TEST_WrongBrand", "write leaked onto the request thread"

    def test_request_thread_latency_when_writes_are_slow(self):
        """Even with a pathologically slow update_one, HTTP path is unaffected."""
        bid = _seed_bill()
        t0 = time.time()
        with _Spy(update_faults=["hang", "hang", "hang"]) as spy:
            res, bg = _call(bid, reprocess=True, wait_for_result=False)
        elapsed = time.time() - t0
        assert res["reprocessed"] == "queued", res
        assert len(spy.rec["update_one"]) == 0
        assert elapsed < 1.0, f"request thread took {elapsed:.2f}s (should be <200ms of DB work)"
        print(f"handler in-process latency with slow writes: {elapsed*1000:.0f}ms")


# ================================================ 2. bg worker — happy path
class TestBgWorkerHappyPath:
    def test_write_then_reprocess(self):
        bid = _seed_bill()
        calls = []

        async def _fake_reprocess(b, n, fc):
            calls.append((b, n, fc))

        with _Spy() as spy:
            with mock.patch.object(server, "_reprocess_after_brand_edit", _fake_reprocess):
                _run(asyncio.ensure_future(server._apply_brand_edit_and_reprocess_bg(
                    bid, "TEST_WrongBrand", "TEST_Zara", "admin", True)))
        assert len(spy.rec["update_one"]) == 1, f"{len(spy.rec['update_one'])} update_one calls"
        assert calls == [(bid, "TEST_Zara", True)], calls
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0}))
        assert doc["store_name"] == "TEST_Zara"
        assert doc.get("reprocessing_started_at")
        assert doc.get("brand_edited_by") == "admin"
        assert doc.get("brand_edited_at")
        assert "TEST_WrongBrand" in (doc.get("admin_notes") or ""), doc.get("admin_notes")
        assert "TEST_Zara" in (doc.get("admin_notes") or ""), doc.get("admin_notes")

    def test_end_to_end_http_then_bg_persists(self, auth_headers):
        """HTTP call queues the FastAPI bg task; poll for the persisted rename."""
        bid = _seed_bill()
        r = requests.post(
            f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
            json={"new_store_name": "TEST_E2EBrand", "reprocess": True,
                  "wait_for_result": False},
            headers=auth_headers, timeout=60)
        assert r.status_code == 200, r.text[:300]
        got = None
        for _ in range(30):
            doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "store_name": 1,
                                                              "admin_notes": 1,
                                                              "reprocessing_started_at": 1}))
            if doc and doc.get("store_name") == "TEST_E2EBrand":
                got = doc
                break
            time.sleep(1)
        assert got, "bg worker never persisted store_name within 30s"
        assert got.get("reprocessing_started_at")
        assert "TEST_WrongBrand" in (got.get("admin_notes") or "")
        print("bg worker persisted rename e2e:", got.get("admin_notes"))


# ============================================ 3. bg worker — Atlas hiccup
class TestBgWorkerRetry:
    def test_two_timeouts_then_success_with_backoff(self):
        bid = _seed_bill()
        calls = []

        async def _fake_reprocess(b, n, fc):
            calls.append(b)

        exc = NetworkTimeout("connection closed: The write operation timed out")
        t0 = time.time()
        with _Spy(update_faults=[exc, exc, None]) as spy:
            with mock.patch.object(server, "_reprocess_after_brand_edit", _fake_reprocess):
                _run(server._apply_brand_edit_and_reprocess_bg(
                    bid, "TEST_WrongBrand", "TEST_Retry3", "admin", True))
        elapsed = time.time() - t0
        assert len(spy.rec["update_one"]) == 3, f"{len(spy.rec['update_one'])} attempts"
        gaps = spy.update_gaps()
        assert 0.8 <= gaps[0] <= 1.6, f"first backoff {gaps} (expected ~1s)"
        assert 1.8 <= gaps[1] <= 2.6, f"second backoff {gaps} (expected ~2s)"
        assert 2.8 < elapsed < 6.0, f"total {elapsed:.2f}s"
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "store_name": 1}))
        assert doc["store_name"] == "TEST_Retry3", "3rd attempt did not persist"
        assert calls == [bid], "reprocess not invoked after retried write"
        print(f"bg retry backoff gaps={gaps} total={elapsed:.2f}s")

    @pytest.mark.parametrize("exc", [
        AutoReconnect("primary stepped down"),
        ServerSelectionTimeoutError("No replica set members match"),
        ExecutionTimeout("operation exceeded time limit"),
    ])
    def test_other_transient_classes_retried(self, exc):
        bid = _seed_bill()
        with _Spy(update_faults=[exc, None]) as spy:
            with mock.patch.object(server, "_reprocess_after_brand_edit",
                                   mock.AsyncMock()):
                _run(server._apply_brand_edit_and_reprocess_bg(
                    bid, "TEST_WrongBrand", "TEST_Transient", "admin", True))
        assert len(spy.rec["update_one"]) == 2, len(spy.rec["update_one"])
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "store_name": 1}))
        assert doc["store_name"] == "TEST_Transient"


# ================================ 4. bg worker — persistent write failure
class TestBgWorkerPersistentFailure:
    def test_three_failures_still_reprocesses(self):
        bid = _seed_bill()
        calls = []

        async def _fake_reprocess(b, n, fc):
            calls.append((b, n, fc))

        exc = NetworkTimeout("connection closed: The write operation timed out")
        with _Spy(update_faults=[exc, exc, exc]) as spy:
            with mock.patch.object(server, "_reprocess_after_brand_edit", _fake_reprocess):
                _run(server._apply_brand_edit_and_reprocess_bg(
                    bid, "TEST_WrongBrand", "TEST_AllFail", "admin", False))
        assert len(spy.rec["update_one"]) == 3, len(spy.rec["update_one"])
        assert calls == [(bid, "TEST_AllFail", False)], (
            "reprocess must still run so the pipeline can re-write store_name")
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "store_name": 1}))
        assert doc["store_name"] == "TEST_WrongBrand"

    def test_bg_worker_never_raises(self):
        """Non-transient write error + failing reprocess must be swallowed."""
        bid = _seed_bill()

        async def _boom(b, n, fc):
            raise RuntimeError("reprocess exploded")

        with _Spy(update_faults=[ValueError("not-transient")]) as spy:
            with mock.patch.object(server, "_reprocess_after_brand_edit", _boom):
                _run(server._apply_brand_edit_and_reprocess_bg(
                    bid, "TEST_WrongBrand", "TEST_NonTransient", "admin", True))
        assert len(spy.rec["update_one"]) == 1, "non-transient error must not be retried"


# ============================================== 5. rename-only inline path
class TestRenameOnlyPath:
    def test_rename_only_inline_write(self):
        bid = _seed_bill()
        with _Spy() as spy:
            res, bg = _call(bid, new_store_name="TEST_OnlyRename", reprocess=False)
        assert res == {"success": True, "reprocessed": False, "store_name": "TEST_OnlyRename"}
        assert len(spy.rec["update_one"]) == 1
        assert len(bg.tasks) == 0
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "store_name": 1}))
        assert doc["store_name"] == "TEST_OnlyRename"

    def test_rename_only_retry_then_success(self):
        bid = _seed_bill()
        exc = NetworkTimeout("connection closed: The write operation timed out")
        with _Spy(update_faults=[exc, None]) as spy:
            res, _ = _call(bid, new_store_name="TEST_RenameRetry", reprocess=False)
        assert res["success"] is True
        assert len(spy.rec["update_one"]) == 2
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "store_name": 1}))
        assert doc["store_name"] == "TEST_RenameRetry"

    def test_rename_only_double_failure_503(self):
        bid = _seed_bill()
        exc = NetworkTimeout("connection closed: The write operation timed out")
        with _Spy(update_faults=[exc, exc]) as spy:
            with pytest.raises(HTTPException) as ei:
                _call(bid, new_store_name="TEST_RenameFail", reprocess=False)
        assert len(spy.rec["update_one"]) == 2
        assert ei.value.status_code == 503, ei.value.status_code
        assert ei.value.detail == FRIENDLY, ei.value.detail

    def test_rename_only_hang_maps_to_503(self):
        bid = _seed_bill()
        t0 = time.time()
        with _Spy(update_faults=["hang", "hang"]) as spy:
            with pytest.raises(HTTPException) as ei:
                _call(bid, new_store_name="TEST_RenameHang", reprocess=False)
        elapsed = time.time() - t0
        assert len(spy.rec["update_one"]) == 2
        assert ei.value.status_code == 503, ei.value.status_code
        assert 11.5 < elapsed < 17, f"unexpected elapsed {elapsed:.1f}s (expected ~12.3s)"


# ===================================================== 6. regressions
class TestRegression:
    def test_404_unknown_bill(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/admin/bills/TEST_ITER70_NOPE/edit-brand",
                          json={"new_store_name": "TEST_Zara", "reprocess": True},
                          headers=auth_headers, timeout=60)
        assert r.status_code == 404, f"{r.status_code}: {r.text[:200]}"

    def test_400_blank_brand(self, auth_headers):
        bid = _seed_bill()
        r = requests.post(f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
                          json={"new_store_name": "   ", "reprocess": True},
                          headers=auth_headers, timeout=60)
        assert r.status_code == 400, f"{r.status_code}: {r.text[:200]}"
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "store_name": 1}))
        assert doc["store_name"] == "TEST_WrongBrand"

    def test_unauthenticated_rejected(self):
        bid = _seed_bill()
        r = requests.post(f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
                          json={"new_store_name": "TEST_Zara"}, timeout=60)
        assert r.status_code in (401, 403), r.status_code

    def test_find_one_transient_retry_then_503(self):
        bid = _seed_bill()
        exc = NetworkTimeout("shard-00-01:27017: The read operation timed out")
        with _Spy(find_faults=[exc, None]) as spy:
            res, bg = _call(bid, new_store_name="TEST_ReadRetry", reprocess=True)
        assert res["reprocessed"] == "queued" and len(spy.rec["find_one"]) == 2
        assert len(bg.tasks) == 1
        with _Spy(find_faults=[exc, exc]) as spy2:
            with pytest.raises(HTTPException) as ei:
                _call(bid, new_store_name="TEST_ReadFail", reprocess=True)
        assert len(spy2.rec["find_one"]) == 2
        assert ei.value.status_code == 503 and ei.value.detail == FRIENDLY
