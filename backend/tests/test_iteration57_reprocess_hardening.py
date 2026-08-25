"""Iteration 57 — POST /api/bills/{bill_id}/reprocess hardening (never raw 500).

Covers:
  * server.py:3328 reprocess_bill — top-level try/except wrapper
  * fast queued path (<500ms), 404 unknown id, 400 wrong status
  * exception simulation: pymongo NetworkTimeout -> HTTPException(500) with
    JSON detail "Reprocess server error: ..." (never an empty raw 500)
  * background task actually executes (reprocessing_finished_at appears)
  * GET /api/bills with status + date-range filters returns 200 <1s
"""
import asyncio
import os
import re
import sys
import time
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

CREDS_PATH = Path("/app/memory/test_credentials.md")
REPROCESSABLE = ["pending_review", "rejected", "manual_review"]

# Reuse an already-installed loop if a sibling suite created one (motor's global
# client binds to the first loop it is used on — mixing loops raises
# "attached to a different loop").
try:
    _LOOP = asyncio.get_event_loop_policy().get_event_loop()
    if _LOOP.is_closed():
        raise RuntimeError
except RuntimeError:
    _LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _run(coro):
    """Run a coroutine on one shared loop (motor binds to the first loop used)."""
    return _LOOP.run_until_complete(coro)


def _admin_creds():
    content = CREDS_PATH.read_text(encoding="utf-8")
    block = content.split("## Admin Dashboard")[1]
    u = re.search(r"Username:\s*`([^`]+)`", block).group(1)
    p = re.search(r"Password:\s*`([^`]+)`", block).group(1)
    return u, p


@pytest.fixture(scope="session")
def admin_token():
    u, p = _admin_creds()
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"username": u, "password": p}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token")
    assert isinstance(tok, str) and tok
    return tok


@pytest.fixture(scope="session")
def client(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def all_bills(client):
    r = client.get(f"{BASE_URL}/api/bills?limit=200", timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    bills = data if isinstance(data, list) else data.get("bills", [])
    if not bills:
        pytest.fail("No bills in preview DB")
    return bills


@pytest.fixture(scope="session")
def reprocessable_bill(all_bills):
    for b in all_bills:
        if b.get("status") in REPROCESSABLE and b.get("id"):
            return b
    pytest.skip("No pending_review/rejected/manual_review bill available in preview DB")


@pytest.fixture(scope="session")
def non_reprocessable_bill(all_bills):
    for b in all_bills:
        if b.get("status") not in REPROCESSABLE and b.get("id"):
            return b
    pytest.skip("No non-reprocessable bill (e.g. auto_approved) available in preview DB")


# ---------------- happy path: queued in <500ms ----------------
class TestReprocessFastPath:
    def test_queued_response_is_fast_and_correct(self, client, reprocessable_bill):
        bill_id = reprocessable_bill["id"]
        t0 = time.time()
        r = client.post(f"{BASE_URL}/api/bills/{bill_id}/reprocess", json={"username": "admin"}, timeout=20)
        elapsed = (time.time() - t0) * 1000
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        body = r.json()
        assert body.get("success") is True
        assert body.get("reprocessed") == "queued"
        assert body.get("bill_id") == bill_id
        assert isinstance(body.get("message"), str) and body["message"]
        print(f"[reprocess queued] {bill_id} in {elapsed:.0f}ms")
        assert elapsed < 500, f"reprocess took {elapsed:.0f}ms (>500ms budget)"

    def test_reprocessing_started_at_persisted(self, client, reprocessable_bill):
        """The endpoint stamps reprocessing_started_at before returning."""
        bill_id = reprocessable_bill["id"]
        r = client.post(f"{BASE_URL}/api/bills/{bill_id}/reprocess", json={"username": "admin"}, timeout=20)
        assert r.status_code == 200
        import server
        doc = _run(server.db.bills.find_one({"id": bill_id}, {"_id": 0}))
        assert doc is not None
        assert doc.get("reprocessing_started_at"), "reprocessing_started_at not stamped"
        assert doc.get("reprocessing_by") == "admin"

    def test_repeated_calls_stay_fast(self, client, reprocessable_bill):
        bill_id = reprocessable_bill["id"]
        worst = 0
        for _ in range(5):
            t0 = time.time()
            r = client.post(f"{BASE_URL}/api/bills/{bill_id}/reprocess", json={"username": "admin"}, timeout=20)
            el = (time.time() - t0) * 1000
            worst = max(worst, el)
            assert r.status_code in (200, 400), f"{r.status_code}: {r.text[:300]}"
        print(f"[reprocess 5x] worst={worst:.0f}ms")
        assert worst < 1000, f"worst reprocess latency {worst:.0f}ms"


# ---------------- error paths ----------------
class TestReprocessErrorPaths:
    def test_unknown_bill_404_json_fast(self, client):
        t0 = time.time()
        r = client.post(f"{BASE_URL}/api/bills/TEST_no_such_bill_i57/reprocess", json={}, timeout=20)
        elapsed = (time.time() - t0) * 1000
        assert r.status_code == 404, f"{r.status_code}: {r.text[:300]}"
        assert r.json().get("detail") == "Bill not found"
        print(f"[reprocess 404] {elapsed:.0f}ms")
        assert elapsed < 500, f"404 took {elapsed:.0f}ms"

    def test_wrong_status_returns_400_json(self, client, non_reprocessable_bill):
        bill_id = non_reprocessable_bill["id"]
        r = client.post(f"{BASE_URL}/api/bills/{bill_id}/reprocess", json={}, timeout=20)
        assert r.status_code == 400, f"{r.status_code}: {r.text[:300]}"
        detail = r.json().get("detail")
        assert isinstance(detail, str) and "reprocessed" in detail.lower()

    def test_unauthorized_is_401_403(self):
        r = requests.post(f"{BASE_URL}/api/bills/anything/reprocess", json={}, timeout=20)
        assert r.status_code in (401, 403), f"{r.status_code}: {r.text[:200]}"

    @pytest.mark.parametrize("bad_id", [
        "../../etc/passwd", "%00", "a" * 300, '{"$ne":null}', "id with spaces",
        "<script>alert(1)</script>", "null", "0", "%2e%2e%2f",
    ])
    def test_malformed_ids_never_raw_500(self, client, bad_id):
        r = client.post(f"{BASE_URL}/api/bills/{bad_id}/reprocess", json={}, timeout=20)
        assert r.status_code != 500, f"raw 500 for {bad_id!r}: {r.text[:300]}"
        assert r.status_code in (400, 404, 422), f"unexpected {r.status_code} for {bad_id!r}"


# ---------------- exception simulation: never raw 500 ----------------
class _FakeBills:
    def __init__(self, exc, fail_on=("find_one", "update_one")):
        self._exc = exc
        self._fail_on = fail_on
        self.doc = {"id": "x", "status": "pending_review"}

    async def find_one(self, *a, **k):
        if "find_one" in self._fail_on:
            raise self._exc
        return dict(self.doc)

    async def update_one(self, *a, **k):
        if "update_one" in self._fail_on:
            raise self._exc
        return mock.Mock(modified_count=1)


class _FakeDB:
    def __init__(self, exc, fail_on=("find_one", "update_one")):
        self.bills = _FakeBills(exc, fail_on)

    def __getitem__(self, name):
        return self.bills


class TestReprocessExceptionSimulation:
    @pytest.mark.parametrize("exc_name", ["NetworkTimeout", "ServerSelectionTimeoutError", "AutoReconnect",
                                          "ExecutionTimeout"])
    def test_find_one_exception_becomes_json_500(self, exc_name):
        import server
        from fastapi import BackgroundTasks, HTTPException
        from pymongo import errors as pe
        exc = getattr(pe, exc_name)(f"simulated {exc_name}")
        with mock.patch.object(server, "db", _FakeDB(exc)):
            with pytest.raises(HTTPException) as ei:
                _run(server.reprocess_bill("some-bill-id", BackgroundTasks(),
                                           payload={"username": "admin"}))
        assert ei.value.status_code == 500
        assert "Reprocess server error" in str(ei.value.detail)
        assert exc_name.replace("Error", "") in str(ei.value.detail) or "simulated" in str(ei.value.detail)

    def test_update_one_exception_becomes_json_500(self):
        """find_one succeeds, update_one fails — still a JSON 500, not raw."""
        import server
        from fastapi import BackgroundTasks, HTTPException
        from pymongo import errors as pe
        db = _FakeDB(pe.NetworkTimeout("simulated update"), fail_on=("update_one",))
        with mock.patch.object(server, "db", db):
            with pytest.raises(HTTPException) as ei:
                _run(server.reprocess_bill("some-bill-id", BackgroundTasks(),
                                           payload={"username": "admin"}))
        assert ei.value.status_code == 500
        assert "Reprocess server error" in str(ei.value.detail)

    def test_httpexception_404_not_swallowed_into_500(self):
        """HTTPException re-raise branch: missing bill must stay 404."""
        import server
        from fastapi import BackgroundTasks, HTTPException

        class _NoneBills:
            async def find_one(self, *a, **k):
                return None

        class _NoneDB:
            bills = _NoneBills()

        with mock.patch.object(server, "db", _NoneDB()):
            with pytest.raises(HTTPException) as ei:
                _run(server.reprocess_bill("nope", BackgroundTasks(), payload={"username": "admin"}))
        assert ei.value.status_code == 404
        assert ei.value.detail == "Bill not found"

    def test_generic_exception_becomes_json_500(self):
        import server
        from fastapi import BackgroundTasks, HTTPException
        with mock.patch.object(server, "db", _FakeDB(RuntimeError("boom generic"))):
            with pytest.raises(HTTPException) as ei:
                _run(server.reprocess_bill("some-bill-id", BackgroundTasks(),
                                           payload={"username": "admin"}))
        assert ei.value.status_code == 500
        assert "Reprocess server error" in str(ei.value.detail)
        assert "boom generic" in str(ei.value.detail)

    def test_source_has_toplevel_try_except(self):
        src = Path("/app/backend/server.py").read_text(encoding="utf-8")
        seg = src.split('@api_router.post("/bills/{bill_id}/reprocess")')[1].split("async def _do_reprocess_bill_bg")[0]
        assert "except HTTPException:" in seg
        assert "Reprocess server error" in seg
        assert "logger.exception" in seg


# ---------------- background task actually runs ----------------
class TestBackgroundTaskExecution:
    def test_background_reprocess_completes(self, client, reprocessable_bill):
        import server
        bill_id = reprocessable_bill["id"]
        # clear previous marker
        _run(server.db.bills.update_one({"id": bill_id},
                                        {"$unset": {"reprocessing_finished_at": "", "reprocessing_error": ""}}))
        r = client.post(f"{BASE_URL}/api/bills/{bill_id}/reprocess", json={"username": "admin"}, timeout=20)
        assert r.status_code == 200, r.text[:300]
        finished = None
        status_after = None
        deadline = time.time() + 45
        while time.time() < deadline:
            doc = _run(server.db.bills.find_one({"id": bill_id}, {"_id": 0}))
            if doc and doc.get("reprocessing_finished_at"):
                finished = doc["reprocessing_finished_at"]
                status_after = doc.get("status")
                break
            time.sleep(2)
        print(f"[bg reprocess] finished_at={finished} status={status_after} "
              f"err={(doc or {}).get('reprocessing_error')}")
        assert finished, "Background reprocess never stamped reprocessing_finished_at within 45s"


# ---------------- GET /api/bills filters ----------------
class TestBillsListFilters:
    @pytest.mark.parametrize("qs", [
        "status=pending_review",
        "status=auto_approved",
        "start_date=2026-01-01&end_date=2026-12-31",
        "status=pending_review&start_date=2026-01-01&end_date=2026-12-31",
        "status=rejected&start_date=2025-01-01&end_date=2026-12-31&limit=100",
    ])
    def test_filters_fast_and_200(self, client, qs):
        t0 = time.time()
        r = client.get(f"{BASE_URL}/api/bills?{qs}", timeout=20)
        elapsed = (time.time() - t0) * 1000
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        data = r.json()
        bills = data if isinstance(data, list) else data.get("bills", [])
        assert isinstance(bills, list)
        for b in bills:
            assert "_id" not in b, "MongoDB _id leaked in /api/bills response"
        if "status=" in qs and bills:
            want = qs.split("status=")[1].split("&")[0]
            assert all(b.get("status") == want for b in bills), "status filter not applied"
        print(f"[GET /api/bills?{qs}] {len(bills)} bills in {elapsed:.0f}ms")
        assert elapsed < 1000, f"{qs} took {elapsed:.0f}ms (>1s)"


class TestHealth:
    def test_backend_reachable(self):
        r = requests.get(f"{BASE_URL}/api/bills", timeout=20)
        assert r.status_code in (401, 403), f"unexpected {r.status_code}"
