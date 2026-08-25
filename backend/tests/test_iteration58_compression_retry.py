"""Iteration 58 (session-19) — Motor zstd compression + higher pool + one-shot
retry inside GET /api/bills/{id}/image.

Covers:
  * server.py:~32 AsyncIOMotorClient kwargs: compressors='zstd,zlib',
    socketTimeoutMS=20000, maxPoolSize=100, minPoolSize=10,
    serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, waitQueueTimeoutMS=5000
  * zstandard importable + pinned in requirements.txt
  * GET /api/bills/{id}/image  → 200 JSON <500ms, never raw 500
  * transparent one-shot retry: first find_one raises NetworkTimeout, second
    succeeds → 200 with the REAL image_url (proves retry loop retries)
  * both attempts fail → 200 with fetch_error "Server error while loading image: ..."
  * unknown id → 404 "Bill not found" and NOT retried
  * POST /api/admin/bills/{id}/edit-brand and POST /api/bills/{id}/reprocess <500ms
"""
import asyncio
import os
import re
import sys
import time
import uuid
from pathlib import Path
from unittest import mock

from starlette.background import BackgroundTasks

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


# A ~1KB valid data URL so the >200-byte guard passes
BIG_DATA_URL = "data:image/jpeg;base64," + ("A" * 1200)


@pytest.fixture(scope="session")
def seeded_bill():
    """Insert a TEST_ bill carrying an inline data: image; drop it afterwards."""
    import server

    bill_id = f"TEST_i58_{uuid.uuid4().hex[:8]}"
    doc = {
        "id": bill_id,
        "user_id": f"TEST_i58_user_{uuid.uuid4().hex[:6]}",
        "user_phone": "919999900058",
        "brand": "Haldiram's",
        "amount": 91.36,
        "status": "pending_review",
        "image_url": BIG_DATA_URL,
        "image_hash": "TEST_i58_hash",
    }
    _run(server.db.bills.insert_one(dict(doc)))
    yield bill_id
    _run(server.db.bills.delete_many({"id": bill_id}))


# ---------------- 1. Motor client options ----------------
class TestMotorClientOptions:
    def test_timeouts_and_pool(self):
        import server

        opts = server.client.options
        po = opts.pool_options
        assert po.socket_timeout == 20.0, f"socketTimeoutMS != 20000 (got {po.socket_timeout})"
        assert po.connect_timeout == 5.0, po.connect_timeout
        assert po.wait_queue_timeout == 5.0, po.wait_queue_timeout
        assert po.max_pool_size == 100, po.max_pool_size
        assert po.min_pool_size == 10, po.min_pool_size
        assert opts.server_selection_timeout == 5.0, opts.server_selection_timeout
        assert opts.retry_reads is True
        assert opts.retry_writes is True

    def test_compressors_negotiated(self):
        import server

        cs = server.client.options.pool_options._compression_settings
        compressors = list(cs.compressors)
        assert "zstd" in compressors, f"zstd not enabled: {compressors}"
        assert "zlib" in compressors, f"zlib not enabled: {compressors}"
        assert compressors.index("zstd") < compressors.index("zlib")

    def test_zstandard_available_and_pinned(self):
        import zstandard  # noqa: F401

        req = Path("/app/backend/requirements.txt").read_text()
        assert re.search(r"(?im)^zstandard==", req), "zstandard not pinned in requirements.txt"

    def test_client_actually_reads_with_compression(self):
        import server

        n = _run(server.db.bills.count_documents({}))
        assert isinstance(n, int) and n >= 0


# ---------------- 2. /image endpoint over HTTP ----------------
class TestImageEndpointHTTP:
    def test_image_200_fast(self, client, seeded_bill):
        t0 = time.time()
        r = client.get(f"{BASE_URL}/api/bills/{seeded_bill}/image", timeout=30)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["image_url"] == BIG_DATA_URL
        assert body["image_hash"] == "TEST_i58_hash"
        assert body["fetch_error"] is None
        assert elapsed < 0.5, f"/image took {elapsed:.3f}s (>500ms budget)"

    def test_image_repeat_latency_budget(self, client, seeded_bill):
        """5 sequential reads — confirm every read is far under the 20s socket budget."""
        times = []
        for _ in range(5):
            t0 = time.time()
            r = client.get(f"{BASE_URL}/api/bills/{seeded_bill}/image", timeout=30)
            times.append(time.time() - t0)
            assert r.status_code == 200
        worst = max(times)
        print(f"\n/image latencies: {[round(t*1000) for t in times]} ms (worst {worst*1000:.0f}ms)")
        assert worst < 1.0, f"worst /image latency {worst:.3f}s"

    def test_image_unknown_id_404(self, client):
        r = client.get(f"{BASE_URL}/api/bills/TEST_i58_no_such_bill/image", timeout=30)
        assert r.status_code == 404, r.text[:300]
        assert r.json().get("detail") == "Bill not found"

    def test_image_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/bills/anything/image", timeout=30)
        assert r.status_code in (401, 403), r.status_code


# ---------------- 3. Retry semantics (in-process) ----------------
class _FakeBills:
    """find_one raises NetworkTimeout for the first `fail_times` calls."""

    def __init__(self, fail_times, result=None):
        self.fail_times = fail_times
        self.result = result
        self.calls = 0

    async def find_one(self, *a, **k):
        from pymongo.errors import NetworkTimeout

        self.calls += 1
        if self.calls <= self.fail_times:
            raise NetworkTimeout(
                "customer-apps-shard-00-01.jxp3ul.mongodb.net:27017: The read operation timed out"
            )
        return self.result

    async def update_one(self, *a, **k):
        return None


class _FakeDB:
    def __init__(self, bills):
        self.bills = bills


class TestRetryLoop:
    def test_first_call_times_out_second_succeeds_returns_real_image(self):
        import server

        fake = _FakeBills(
            fail_times=1,
            result={"image_url": BIG_DATA_URL, "image_hash": "TEST_i58_hash"},
        )
        t0 = time.time()
        with mock.patch.object(server, "db", _FakeDB(fake)):
            out = _run(server.get_bill_image("TEST_i58_retry", BackgroundTasks(), payload={"role": "admin"}))
        elapsed = time.time() - t0
        assert fake.calls == 2, f"retry did not happen (find_one calls={fake.calls})"
        assert out["image_url"] == BIG_DATA_URL, out
        assert out["fetch_error"] is None, out
        assert out["image_hash"] == "TEST_i58_hash"
        assert 0.25 < elapsed < 2.0, f"expected ~300ms backoff, got {elapsed:.3f}s"

    def test_both_attempts_fail_returns_200_with_fetch_error(self):
        import server

        fake = _FakeBills(fail_times=5)
        with mock.patch.object(server, "db", _FakeDB(fake)):
            out = _run(server.get_bill_image("TEST_i58_retry_fail", BackgroundTasks(), payload={"role": "admin"}))
        assert fake.calls == 2, f"expected exactly 2 attempts, got {fake.calls}"
        assert out["image_url"] is None
        assert out["fetch_error"].startswith("Server error while loading image: "), out
        assert "read operation timed out" in out["fetch_error"]

    def test_not_found_is_not_retried(self):
        import server
        from fastapi import HTTPException

        fake = _FakeBills(fail_times=0, result=None)
        with mock.patch.object(server, "db", _FakeDB(fake)):
            with pytest.raises(HTTPException) as ei:
                _run(server.get_bill_image("TEST_i58_missing", BackgroundTasks(), payload={"role": "admin"}))
        assert ei.value.status_code == 404
        assert ei.value.detail == "Bill not found"
        assert fake.calls == 1, f"404 should not be retried (calls={fake.calls})"


# ---------------- 4. No regression on sibling admin endpoints ----------------
class TestNoRegression:
    def test_edit_brand_fast(self, client, seeded_bill):
        t0 = time.time()
        r = client.post(
            f"{BASE_URL}/api/admin/bills/{seeded_bill}/edit-brand",
            json={"new_store_name": "Haldiram's"},
            timeout=30,
        )
        elapsed = time.time() - t0
        assert r.status_code in (200, 400, 422), r.text[:300]
        assert elapsed < 0.5, f"edit-brand took {elapsed:.3f}s"

    def test_edit_brand_unknown_id_404(self, client):
        r = client.post(
            f"{BASE_URL}/api/admin/bills/TEST_i58_nope/edit-brand",
            json={"new_store_name": "Zara"},
            timeout=30,
        )
        assert r.status_code == 404, r.text[:300]

    def test_reprocess_fast(self, client, seeded_bill):
        t0 = time.time()
        r = client.post(f"{BASE_URL}/api/bills/{seeded_bill}/reprocess", timeout=30)
        elapsed = time.time() - t0
        assert r.status_code in (200, 400, 409), r.text[:300]
        assert elapsed < 0.5, f"reprocess took {elapsed:.3f}s"

    def test_bills_list_fast(self, client):
        t0 = time.time()
        r = client.get(f"{BASE_URL}/api/bills?limit=50", timeout=30)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text[:300]
        assert elapsed < 2.0, f"bills list took {elapsed:.3f}s"
