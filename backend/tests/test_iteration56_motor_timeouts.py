"""Iteration 56 — Motor client explicit timeouts + never-raw-500 invariants.

Covers:
  * server.py:36 AsyncIOMotorClient timeout kwargs (introspected via client.options)
  * GET /api/bills/{id}/image  → clean 200 / 404, <500ms, never raw 500
  * POST /api/admin/bills/{id}/edit-brand → 200 / 404 / 400-422, never raw 500
  * exception simulation: pymongo NetworkTimeout inside get_bill_image
  * ensure_db_indexes() idempotency (re-run in-process)
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
def sample_bill_ids(client):
    r = client.get(f"{BASE_URL}/api/bills?limit=25", timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    bills = data if isinstance(data, list) else data.get("bills", [])
    ids = [b["id"] for b in bills if b.get("id")]
    if not ids:
        pytest.fail("No bills available in preview DB to test image endpoint")
    return ids


# ---------------- Motor client options ----------------
class TestMotorClientOptions:
    def test_client_options_have_explicit_timeouts(self):
        import server  # noqa
        opts = server.client.options
        assert opts.server_selection_timeout == 5.0
        assert opts.pool_options.connect_timeout == 5.0
        assert opts.pool_options.socket_timeout == 10.0
        assert opts.pool_options.wait_queue_timeout == 5.0
        assert opts.retry_reads is True
        assert opts.retry_writes is True

    def test_source_declares_timeouts(self):
        src = Path("/app/backend/server.py").read_text(encoding="utf-8")[:3000]
        for kw in ["serverSelectionTimeoutMS=5000", "connectTimeoutMS=5000",
                   "socketTimeoutMS=10000", "waitQueueTimeoutMS=5000",
                   "retryWrites=True", "retryReads=True"]:
            assert kw in src, f"missing {kw} in AsyncIOMotorClient init"


# ---------------- GET /api/bills/{id}/image ----------------
class TestBillImageEndpoint:
    def test_valid_bill_returns_clean_200_fast(self, client, sample_bill_ids):
        slow = []
        for bid in sample_bill_ids[:10]:
            t0 = time.time()
            r = client.get(f"{BASE_URL}/api/bills/{bid}/image", timeout=30)
            el = (time.time() - t0) * 1000
            assert r.status_code == 200, f"{bid} -> {r.status_code} {r.text[:200]}"
            assert r.headers.get("content-type", "").startswith("application/json")
            body = r.json()
            assert set(["image_url", "image_hash", "fetch_error"]).issubset(body.keys())
            if el > 500:
                slow.append((bid, round(el)))
        assert not slow, f"bills slower than 500ms: {slow}"

    def test_unknown_bill_returns_404_fast(self, client):
        t0 = time.time()
        r = client.get(f"{BASE_URL}/api/bills/does-not-exist-iter56/image", timeout=30)
        el = (time.time() - t0) * 1000
        assert r.status_code == 404, f"{r.status_code}: {r.text[:200]}"
        assert r.json().get("detail") == "Bill not found"
        assert el < 500, f"404 took {el:.0f}ms"

    def test_malformed_ids_never_raw_500(self, client):
        weird = ["", " ", "%20", "null", "undefined", "../../etc/passwd",
                 "a" * 300, "0" * 24, '{"$ne":null}', "id%00"]
        for w in weird:
            r = client.get(f"{BASE_URL}/api/bills/{w}/image", timeout=30)
            assert r.status_code != 500, f"id={w!r} -> RAW 500 body={r.text[:200]}"
            assert r.status_code in (200, 307, 400, 404, 405, 422), f"id={w!r} -> {r.status_code}"

    def test_unauthorized_is_401_403_not_500(self):
        r = requests.get(f"{BASE_URL}/api/bills/whatever/image", timeout=30)
        assert r.status_code in (401, 403), r.status_code


# ---------------- exception simulation ----------------
class _FakeBills:
    def __init__(self, exc):
        self._exc = exc

    async def find_one(self, *a, **k):
        raise self._exc

    async def update_one(self, *a, **k):
        raise self._exc


class _FakeDB:
    def __init__(self, exc):
        self.bills = _FakeBills(exc)

    def __getitem__(self, name):
        return self.bills


class TestExceptionSimulation:
    """Patch db so find_one raises pymongo NetworkTimeout — handler must still
    return a clean dict with fetch_error (FastAPI serialises as HTTP 200)."""

    @pytest.mark.parametrize("exc_name", ["NetworkTimeout", "ServerSelectionTimeoutError", "AutoReconnect"])
    def test_get_bill_image_converts_db_exception_to_fetch_error(self, exc_name):
        import server
        from pymongo import errors as pe
        exc = getattr(pe, exc_name)("simulated %s" % exc_name)
        with mock.patch.object(server, "db", _FakeDB(exc)):
            res = _run(server.get_bill_image("some-bill-id", payload={"username": "admin"}))
        assert isinstance(res, dict)
        assert res["image_url"] is None
        assert res["fetch_error"] and "Server error while loading image" in res["fetch_error"]

    def test_edit_brand_db_exception_becomes_json_500_not_empty(self):
        import server
        from fastapi import BackgroundTasks, HTTPException
        from pymongo import errors as pe
        req = server.EditBrandRequest(new_store_name="TEST_BRAND_I56", reprocess=False)
        with mock.patch.object(server, "db", _FakeDB(pe.NetworkTimeout("simulated"))):
            with pytest.raises(HTTPException) as ei:
                _run(server.edit_bill_brand("some-bill-id", req, BackgroundTasks(), payload={"username": "admin"}))
        assert ei.value.status_code == 500
        assert "Brand edit server error" in str(ei.value.detail)


# ---------------- POST /api/admin/bills/{id}/edit-brand ----------------
class TestEditBrandEndpoint:
    def test_reprocess_false_returns_200_fast(self, client, sample_bill_ids):
        bid = sample_bill_ids[0]
        orig = client.get(f"{BASE_URL}/api/bills/{bid}", timeout=30)
        assert orig.status_code == 200
        orig_name = orig.json().get("store_name") or orig.json().get("bill", {}).get("store_name")

        t0 = time.time()
        r = client.post(f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
                        json={"new_store_name": "TEST_I56_BRAND", "reprocess": False}, timeout=30)
        el = (time.time() - t0) * 1000
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        body = r.json()
        assert body["success"] is True and body["reprocessed"] is False
        assert body["store_name"] == "TEST_I56_BRAND"
        assert el < 500, f"took {el:.0f}ms"

        # verify persistence
        chk = client.get(f"{BASE_URL}/api/bills/{bid}", timeout=30)
        cname = chk.json().get("store_name") or chk.json().get("bill", {}).get("store_name")
        assert cname == "TEST_I56_BRAND"

        # restore original name
        if orig_name:
            rb = client.post(f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
                             json={"new_store_name": orig_name, "reprocess": False}, timeout=30)
            assert rb.status_code == 200

    def test_unknown_bill_returns_404(self, client):
        t0 = time.time()
        r = client.post(f"{BASE_URL}/api/admin/bills/nope-iter56/edit-brand",
                        json={"new_store_name": "X", "reprocess": False}, timeout=30)
        el = (time.time() - t0) * 1000
        assert r.status_code == 404, f"{r.status_code}: {r.text[:300]}"
        assert r.json().get("detail") == "Bill not found"
        assert el < 500, f"took {el:.0f}ms"

    def test_empty_and_missing_store_name(self, client, sample_bill_ids):
        bid = sample_bill_ids[0]
        r = client.post(f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
                        json={"new_store_name": "   ", "reprocess": False}, timeout=30)
        assert r.status_code in (400, 422), f"{r.status_code}: {r.text[:200]}"
        r2 = client.post(f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
                         json={"reprocess": False}, timeout=30)
        assert r2.status_code == 422, f"{r2.status_code}: {r2.text[:200]}"

    def test_reprocess_true_queues_in_background(self, client, sample_bill_ids):
        # pick a bill and keep its name so the background reprocess is a no-op-ish
        bid = sample_bill_ids[0]
        cur = client.get(f"{BASE_URL}/api/bills/{bid}", timeout=30).json()
        name = cur.get("store_name") or cur.get("bill", {}).get("store_name") or "TEST_I56_BRAND"
        t0 = time.time()
        r = client.post(f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
                        json={"new_store_name": name, "reprocess": True}, timeout=60)
        el = (time.time() - t0) * 1000
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        body = r.json()
        assert body.get("reprocessed") == "queued", body
        assert body.get("store_name") == name
        assert el < 500, f"queued response took {el:.0f}ms"

    def test_unauthorized_edit_brand(self):
        r = requests.post(f"{BASE_URL}/api/admin/bills/x/edit-brand",
                          json={"new_store_name": "Y"}, timeout=30)
        assert r.status_code in (401, 403), r.status_code


# ---------------- ensure_db_indexes idempotency ----------------
class TestIndexIdempotency:
    def test_ensure_db_indexes_runs_twice_without_error(self):
        import server
        _run(server.ensure_db_indexes())
        _run(server.ensure_db_indexes())

    def test_id_indexes_exist_on_key_collections(self):
        import server
        async def _check():
            missing = []
            for col in ["bills", "users", "brands", "stores", "campaigns", "coupons",
                        "staff", "staff_incentives", "parking_sessions", "parking_coupons",
                        "sync_jobs", "bulk_reprocess_jobs", "app_settings", "staff_attributions"]:
                idx = await server.client[os.environ.get("DB_NAME", "cp67_loyalty")][col].index_information()
                if not any(v.get("key") == [("id", 1)] for v in idx.values()):
                    missing.append(col)
            return missing

        missing = _run(_check())
        assert not missing, f"collections missing id_1 index: {missing}"

    def test_backend_health(self):
        r = requests.get(f"{BASE_URL}/api/", timeout=30)
        assert r.status_code in (200, 404)
