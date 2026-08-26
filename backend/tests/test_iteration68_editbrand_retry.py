"""Iteration 68 — POST /api/admin/bills/{bill_id}/edit-brand defensive hardening.

Covers (per review request):
  * Happy path (queued): 200 + {success, reprocessed:"queued"} in <1s, lean
    find_one projection {id, store_name, status} + max_time_ms=8000,
    update_one invoked exactly once.
  * Simulated transient find_one failures (NetworkTimeout / AutoReconnect /
    ServerSelectionTimeoutError / ExecutionTimeout): retry once -> 200;
    persistent -> HTTP 503 with the friendly retry message (NOT 500).
  * Simulated update_one hang (asyncio.sleep(30)) -> asyncio.wait_for fires,
    retried once, then 503 (NOT 500).
  * Regression: 404 unknown bill, 400 blank brand, 401/403 unauthenticated,
    reprocess=false rename-only path, iteration-66/67 projections.
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
TEST_USER_ID = "TEST_ITER68_USER"
TEST_PHONE = "919876543210"
ADMIN_PAYLOAD = {"username": "admin", "name": "Admin", "role": "admin"}

_bills = []


def _seed_bill(status="pending_review", **over):
    bid = "TEST_ITER68_" + str(uuid.uuid4())[:8]
    doc = {
        "id": bid,
        "user_id": TEST_USER_ID,
        "user_phone": TEST_PHONE,
        "store_name": "TEST_WrongBrand",
        "amount": 1500.0,
        "bill_no": f"TEST-68-{bid[-4:]}",
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
        {"$set": {"id": TEST_USER_ID, "phone": TEST_PHONE, "name": "TEST_ITER68",
                  "balance_points": 100, "total_earned_points": 100,
                  "created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    ))
    yield
    if _bills:
        _run(server.db.bills.delete_many({"id": {"$in": _bills}}))
    _run(server.db.bills.delete_many({"id": {"$regex": "^TEST_ITER68_"}}))
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
        self._rec["find_one"].append({"args": args, "kwargs": kwargs})
        if self._find_faults:
            fault = self._find_faults.pop(0)
            if fault is not None:
                raise fault
        return await self._coll.find_one(*args, **kwargs)

    async def update_one(self, *args, **kwargs):
        self._rec["update_one"].append({"args": args, "kwargs": kwargs})
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


def _call(bid, **kw):
    req = server.EditBrandRequest(new_store_name=kw.pop("new_store_name", "TEST_Zara"), **kw)
    return _run(server.edit_bill_brand(bid, req, BackgroundTasks(), payload=ADMIN_PAYLOAD))


FRIENDLY = "MongoDB is under load — the brand edit didn't go through. Please retry in ~10s."


# ================================================================= happy path
class TestEditBrandHappyPath:
    def test_queued_http_fast_and_persists(self, auth_headers):
        bid = _seed_bill()
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
            json={"new_store_name": "TEST_Zara", "reprocess": True,
                  "auto_force_credit_on_fundle_reject": True},
            headers=auth_headers, timeout=60)
        elapsed = time.time() - t0
        assert r.status_code == 200, f"{r.status_code} in {elapsed:.2f}s: {r.text[:400]}"
        body = r.json()
        assert body.get("success") is True and body.get("reprocessed") == "queued", body
        assert body.get("store_name") == "TEST_Zara", body
        print(f"edit-brand queued HTTP latency: {elapsed:.2f}s")
        assert elapsed < 5.0, f"took {elapsed:.2f}s"
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "store_name": 1,
                                                          "reprocessing_started_at": 1,
                                                          "admin_notes": 1}))
        assert doc["store_name"] == "TEST_Zara"
        assert doc.get("reprocessing_started_at")
        assert "TEST_WrongBrand" in (doc.get("admin_notes") or "")

    def test_lean_projection_maxtime_and_single_update(self):
        bid = _seed_bill()
        with _Spy() as spy:
            res = _call(bid, reprocess=True, auto_force_credit_on_fundle_reject=True)
        assert res["success"] is True and res["reprocessed"] == "queued", res
        assert len(spy.rec["find_one"]) == 1, spy.find_projections()
        proj = spy.find_projections()[0]
        assert {k for k, v in proj.items() if v == 1} == {"id", "store_name", "status"}, proj
        assert proj.get("_id") == 0 and proj.get("image_url") != 1
        assert spy.find_max_times() == [8000], spy.find_max_times()
        assert len(spy.rec["update_one"]) == 1, f"update_one called {len(spy.rec['update_one'])}x"

    def test_rename_only_no_reprocess(self):
        bid = _seed_bill()
        res = _call(bid, new_store_name="TEST_OnlyRename", reprocess=False)
        assert res == {"success": True, "reprocessed": False, "store_name": "TEST_OnlyRename"}
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "store_name": 1}))
        assert doc["store_name"] == "TEST_OnlyRename"


# ============================================ simulated transient find_one errs
class TestFindOneTransient:
    @pytest.mark.parametrize("exc", [
        NetworkTimeout("customer-apps-shard-00-01:27017: The read operation timed out"),
        AutoReconnect("connection pool paused"),
        ServerSelectionTimeoutError("No replica set members match"),
        ExecutionTimeout("operation exceeded time limit"),
    ])
    def test_first_call_fails_then_succeeds(self, exc):
        bid = _seed_bill()
        with _Spy(find_faults=[exc, None]) as spy:
            res = _call(bid, new_store_name="TEST_RetryOk")
        assert res["success"] is True and res["reprocessed"] == "queued", res
        assert len(spy.rec["find_one"]) == 2, "no retry happened on find_one"
        assert len(spy.rec["update_one"]) == 1
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "store_name": 1}))
        assert doc["store_name"] == "TEST_RetryOk"

    @pytest.mark.parametrize("exc,label", [
        (NetworkTimeout("customer-apps-shard-00-01:27017: The read operation timed out"), "NetworkTimeout"),
        (AutoReconnect("connection pool paused"), "AutoReconnect"),
        (ServerSelectionTimeoutError("No replica set members match"), "ServerSelectionTimeoutError"),
        (ExecutionTimeout("operation exceeded time limit"), "ExecutionTimeout"),
    ])
    def test_persistent_failure_maps_to_503(self, exc, label):
        bid = _seed_bill()
        with _Spy(find_faults=[exc, exc]) as spy:
            with pytest.raises(HTTPException) as ei:
                _call(bid, new_store_name="TEST_Never")
        assert len(spy.rec["find_one"]) == 2, "expected exactly 2 find_one attempts"
        assert len(spy.rec["update_one"]) == 0, "update_one must not run after read failure"
        assert ei.value.status_code == 503, (
            f"{label}: expected 503, got {ei.value.status_code} detail={ei.value.detail}")
        assert ei.value.detail == FRIENDLY, ei.value.detail
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "store_name": 1}))
        assert doc["store_name"] == "TEST_WrongBrand", "bill must be unchanged on failure"


# ======================================================= simulated update hang
class TestUpdateOneHardening:
    def test_hang_then_success_retries(self):
        bid = _seed_bill()
        t0 = time.time()
        with _Spy(update_faults=["hang", None]) as spy:
            res = _call(bid, new_store_name="TEST_UpdRetry")
        elapsed = time.time() - t0
        assert res["success"] is True, res
        assert len(spy.rec["update_one"]) == 2, "update_one was not retried after wait_for timeout"
        # iter-69: per-attempt wait_for lowered 10.0s -> 6.0s
        assert 5.5 < elapsed < 11, f"wait_for did not fire near 6s (took {elapsed:.1f}s)"
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "store_name": 1}))
        assert doc["store_name"] == "TEST_UpdRetry"

    def test_double_hang_maps_to_503(self):
        bid = _seed_bill()
        t0 = time.time()
        with _Spy(update_faults=["hang", "hang"]) as spy:
            with pytest.raises(HTTPException) as ei:
                _call(bid, new_store_name="TEST_UpdFail")
        elapsed = time.time() - t0
        assert len(spy.rec["update_one"]) == 2
        assert ei.value.status_code == 503, f"got {ei.value.status_code}: {ei.value.detail}"
        assert ei.value.detail == FRIENDLY, ei.value.detail
        # iter-69: 2 x 6.0s wait_for + 0.3s backoff => ~12.5s (was ~20.6s)
        assert 11.5 < elapsed < 17, f"unexpected total elapsed {elapsed:.1f}s (expected ~12.5s)"
        print(f"worst-case update_one hang+hang latency: {elapsed:.2f}s")

    @pytest.mark.parametrize("exc,label", [
        (NetworkTimeout("connection closed: The write operation timed out"), "NetworkTimeout"),
        (AutoReconnect("primary stepped down"), "AutoReconnect"),
        (ExecutionTimeout("operation exceeded time limit"), "ExecutionTimeout"),
    ])
    def test_update_transient_exception_persistent_503(self, exc, label):
        bid = _seed_bill()
        with _Spy(update_faults=[exc, exc]) as spy:
            with pytest.raises(HTTPException) as ei:
                _call(bid, new_store_name="TEST_UpdExc")
        assert len(spy.rec["update_one"]) == 2, "no retry on transient write error"
        assert ei.value.status_code == 503, (
            f"{label}: expected 503, got {ei.value.status_code} detail={ei.value.detail}")
        assert ei.value.detail == FRIENDLY, ei.value.detail

    def test_non_transient_error_still_500(self):
        bid = _seed_bill()
        with _Spy(update_faults=[ValueError("boom-not-transient")]):
            with pytest.raises(HTTPException) as ei:
                _call(bid, new_store_name="TEST_Boom")
        assert ei.value.status_code == 500, ei.value.status_code
        assert "Brand edit server error" in str(ei.value.detail)


# ===================================================================== regression
class TestRegression:
    def test_404_unknown_bill(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/admin/bills/TEST_ITER68_NOPE/edit-brand",
                          json={"new_store_name": "TEST_Zara", "reprocess": False},
                          headers=auth_headers, timeout=60)
        assert r.status_code == 404, f"{r.status_code}: {r.text[:200]}"

    def test_400_blank_brand(self, auth_headers):
        bid = _seed_bill()
        r = requests.post(f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
                          json={"new_store_name": "   ", "reprocess": False},
                          headers=auth_headers, timeout=60)
        assert r.status_code == 400, f"{r.status_code}: {r.text[:200]}"

    def test_unauthenticated_rejected(self):
        bid = _seed_bill()
        r = requests.post(f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
                          json={"new_store_name": "TEST_Zara"}, timeout=60)
        assert r.status_code in (401, 403), r.status_code

    def test_iter66_67_projections_still_lean(self):
        """reprocess guard + force-credit + legacy reads keep lean projections."""
        bid = _seed_bill(status="manual_review")
        with _Spy() as spy:
            try:
                _run(server.reprocess_bill(bid, BackgroundTasks(), payload=ADMIN_PAYLOAD))
            except HTTPException as e:
                assert e.status_code in (400, 409), e.status_code
        guard = spy.find_projections()[0]
        assert guard.get("image_url") != 1 and guard, guard
        print("reprocess guard projection:", guard)

    def test_prev_iteration_suites_pass(self):
        import subprocess
        files = [
            "/app/backend/tests/test_iteration66_reprocess_projections.py",
            "/app/backend/tests/test_iteration67_billread_cleanup.py",
        ]
        p = subprocess.run(["python", "-m", "pytest", "-p", "no:cacheprovider", "-q", *files],
                           capture_output=True, text=True, cwd="/app/backend", timeout=1500)
        tail = (p.stdout or "")[-2500:]
        print(tail)
        assert p.returncode == 0, tail
