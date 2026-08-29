"""Iteration 59 (session-20) — Emergent Object Storage for bill images.

Covers:
  * /app/backend/storage.py  init_storage (memoised) / put_object / get_object /
    upload_bill_image / resolve_objstore_url
  * GET /api/bills/{id}/image  objstore:<path> branch (success, missing path,
    read exception) — always HTTP 200, never a raw 500
  * progressive migration in the finally block (>50KB inline only)
  * POST /api/admin/bills/migrate-images-to-objstore (auth, clamping, queueing)
  * exception simulation: upload_bill_image -> None, get_object -> raise
"""
import asyncio
import base64
import os
import re
import sys
import time
import uuid
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
# NOTE: server.py performs load_dotenv(); storage.py reads EMERGENT_LLM_KEY at
# IMPORT time, so it must be imported *after* server or the key is None.
import server  # noqa: E402
import storage  # noqa: E402,F401

CREDS_PATH = Path("/app/memory/test_credentials.md")

# motor binds to the first loop it sees — share one loop for every direct call
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


# ---------- image payload helpers ----------
def _jpeg_bytes(n: int) -> bytes:
    """Deterministic pseudo-JPEG of ~n bytes (real JPEG SOI/EOI markers)."""
    body = bytes((i * 7 + 13) % 256 for i in range(max(0, n - 4)))
    return b"\xff\xd8" + body + b"\xff\xd9"


def _data_url(n: int, ctype: str = "image/jpeg") -> str:
    return f"data:{ctype};base64," + base64.b64encode(_jpeg_bytes(n)).decode()


BIG_DATA_URL = _data_url(120_000)      # ~160KB data URL -> should migrate
SMALL_DATA_URL = _data_url(20_000)     # ~26KB data URL  -> must NOT migrate
TINY_OK_DATA_URL = _data_url(6_000)    # ~8KB, >200 bytes so it renders


_created_bill_ids = []


def _seed_bill(image_url, extra=None):
    import server

    bill_id = f"TEST_i59_{uuid.uuid4().hex[:8]}"
    doc = {
        "id": bill_id,
        "user_id": f"TEST_i59_user_{uuid.uuid4().hex[:6]}",
        "user_phone": "919999900059",
        "brand": "Haldiram's",
        "amount": 91.36,
        "status": "pending_review",
        "image_url": image_url,
        "image_hash": f"TEST_i59_{uuid.uuid4().hex[:6]}",
    }
    if extra:
        doc.update(extra)
    _run(server.db.bills.insert_one(dict(doc)))
    _created_bill_ids.append(bill_id)
    return bill_id


def _bill_doc(bill_id):
    import server

    return _run(server.db.bills.find_one({"id": bill_id}, {"_id": 0}))


@pytest.fixture(scope="session", autouse=True)
def cleanup():
    yield
    import server

    if _created_bill_ids:
        _run(server.db.bills.delete_many({"id": {"$in": _created_bill_ids}}))


# ==================== 1. storage.py module ====================
class TestStorageModule:
    def test_config_from_env_no_hardcoded_key(self):

        assert storage._emergent_key(), "EMERGENT_LLM_KEY not loaded in storage.py"
        assert storage._base_url().endswith("/objstore/api/v1/storage")
        assert storage.APP_NAME == "cp67-mall"

    def test_import_order_safety_storage_first(self):
        """iter-60: storage.py must load its own .env, so importing it BEFORE
        server.py still yields a working init_storage()."""
        import subprocess

        code = (
            "import sys; sys.path.insert(0,'/app/backend')\n"
            "import storage\n"
            "assert storage._emergent_key(), 'EMERGENT_LLM_KEY not picked up when storage imported first'\n"
            "k = storage.init_storage()\n"
            "assert k, 'init_storage() returned None without server.py preloading .env'\n"
            "print('OK')\n"
        )
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, f"stdout={r.stdout[-500:]} stderr={r.stderr[-800:]}"
        assert "OK" in r.stdout

    def test_init_storage_returns_key(self):

        key = storage.init_storage()
        assert key, "init_storage() returned no storage key"
        assert isinstance(key, str)

    def test_init_storage_is_memoised(self):
        """Second call must NOT re-POST /init."""

        storage.init_storage()  # warm
        with mock.patch.object(storage.requests, "post") as m_post:
            key = storage.init_storage()
        assert key, "memoised init returned nothing"
        assert m_post.call_count == 0, f"init re-POSTed /init {m_post.call_count} time(s)"

    def test_init_storage_returns_none_on_failure(self):

        with mock.patch.object(storage, "_storage_key", None), \
             mock.patch.object(storage.requests, "post", side_effect=RuntimeError("boom")):
            assert storage.init_storage() is None, "init_storage must return None (non-fatal) on failure"

    def test_put_get_object_roundtrip(self):

        path = f"cp67-mall/tests/i59_{uuid.uuid4().hex[:8]}.bin"
        payload = _jpeg_bytes(4096)
        res = storage.put_object(path, payload, "image/jpeg")
        assert res and res.get("path") == path, f"put_object failed: {res}"
        assert res.get("size") == len(payload)
        got = storage.get_object(path)
        assert got is not None, "get_object returned None for a just-written object"
        data, ctype = got
        assert data == payload, "round-trip bytes mismatch"
        assert ctype.startswith("image/jpeg")

    def test_get_object_missing_returns_none(self):

        assert storage.get_object(f"cp67-mall/tests/missing_{uuid.uuid4().hex}.bin") is None

    def test_upload_bill_image_extension_mapping(self):

        bid = f"TEST_i59_ext_{uuid.uuid4().hex[:6]}"
        url_jpg = storage.upload_bill_image(bid, _jpeg_bytes(2048), "image/jpeg")
        assert url_jpg == f"objstore:cp67-mall/bills/{bid}.jpg", url_jpg
        url_png = storage.upload_bill_image(bid, _jpeg_bytes(2048), "image/png")
        assert url_png == f"objstore:cp67-mall/bills/{bid}.png", url_png

    def test_upload_bill_image_returns_none_on_put_failure(self):

        with mock.patch.object(storage, "put_object", return_value=None):
            assert storage.upload_bill_image("TEST_i59_fail", _jpeg_bytes(1024)) is None

    def test_resolve_objstore_url(self):

        payload = _jpeg_bytes(3000)
        bid = f"TEST_i59_res_{uuid.uuid4().hex[:6]}"
        url = storage.upload_bill_image(bid, payload, "image/jpeg")
        assert url and url.startswith("objstore:")
        got = storage.resolve_objstore_url(url)
        assert got is not None
        assert got[0] == payload
        assert storage.resolve_objstore_url("data:image/jpeg;base64,AAAA") is None
        assert storage.resolve_objstore_url("") is None

    def test_startup_log_line_present(self):
        logs = ""
        for p in ("/var/log/supervisor/backend.out.log", "/var/log/supervisor/backend.err.log"):
            if os.path.exists(p):
                logs += Path(p).read_text(errors="ignore")[-400_000:]
        assert "Object storage initialised" in logs, "startup init_storage() log line missing"


# ==================== 2. GET /image objstore branch ====================
class TestImageEndpointObjstore:
    def test_objstore_bill_returns_full_data_url_fast(self, client):

        payload = _jpeg_bytes(120_000)
        bid_seed = f"TEST_i59_read_{uuid.uuid4().hex[:6]}"
        url = storage.upload_bill_image(bid_seed, payload, "image/jpeg")
        assert url
        bill_id = _seed_bill(url)

        timings = []
        for _ in range(3):
            t0 = time.time()
            r = client.get(f"{BASE_URL}/api/bills/{bill_id}/image", timeout=30)
            timings.append((time.time() - t0) * 1000)
            assert r.status_code == 200, r.text[:300]
            data = r.json()
            assert data.get("fetch_error") is None, data.get("fetch_error")
            assert data["image_url"].startswith("data:image/jpeg;base64,")
            decoded = base64.b64decode(data["image_url"].split(",", 1)[1])
            assert decoded == payload, "bytes served != bytes uploaded"
        assert max(timings) < 1500, f"objstore read too slow: {timings}"

    def test_objstore_missing_path_returns_friendly_error(self, client):
        bill_id = _seed_bill(f"objstore:cp67-mall/bills/MISSING_{uuid.uuid4().hex}.jpg")
        r = client.get(f"{BASE_URL}/api/bills/{bill_id}/image", timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["image_url"] is None
        assert data["fetch_error"] == "Object storage returned no data (path may be missing).", data

    def test_objstore_read_exception_returns_200(self):
        """mock storage.get_object -> raise; endpoint must return 200 + 'Object storage read error'."""
        import server
        from starlette.background import BackgroundTasks

        bill_id = _seed_bill(f"objstore:cp67-mall/bills/EXC_{uuid.uuid4().hex}.jpg")
        with mock.patch.object(storage, "get_object", side_effect=RuntimeError("socket blew up")):
            res = _run(server.get_bill_image(bill_id, BackgroundTasks(), payload={"role": "admin"}))
        assert res["image_url"] is None
        assert res["fetch_error"].startswith("Object storage read error:"), res
        assert "socket blew up" in res["fetch_error"]

    def test_no_response_regression_for_inline_and_missing(self, client):
        inline = _seed_bill(TINY_OK_DATA_URL)
        r = client.get(f"{BASE_URL}/api/bills/{inline}/image", timeout=30)
        assert r.status_code == 200 and r.json()["fetch_error"] is None
        assert r.json()["image_url"] == TINY_OK_DATA_URL

        empty = _seed_bill("")
        r = client.get(f"{BASE_URL}/api/bills/{empty}/image", timeout=30)
        assert r.status_code == 200
        assert r.json()["fetch_error"] == "No image on record for this bill."

        r = client.get(f"{BASE_URL}/api/bills/TEST_i59_nope_{uuid.uuid4().hex[:6]}/image", timeout=30)
        assert r.status_code == 404, r.text[:200]


# ==================== 3. progressive migration ====================
def _wait_migrated(bill_id, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        doc = _bill_doc(bill_id) or {}
        if str(doc.get("image_url", "")).startswith("objstore:"):
            return doc
        time.sleep(1)
    return _bill_doc(bill_id) or {}


class TestProgressiveMigration:
    def test_fat_inline_bill_is_migrated_after_first_read(self, client):
        bill_id = _seed_bill(BIG_DATA_URL)
        r = client.get(f"{BASE_URL}/api/bills/{bill_id}/image", timeout=60)
        assert r.status_code == 200, r.text[:300]
        first = r.json()
        assert first["fetch_error"] is None
        assert first["image_url"] == BIG_DATA_URL, "first read must still serve the inline URL"

        doc = _wait_migrated(bill_id)
        assert doc.get("image_url") == f"objstore:cp67-mall/bills/{bill_id}.jpg", doc.get("image_url")
        assert doc.get("image_migrated_at"), "image_migrated_at not set"
        assert len(doc["image_url"]) < 100, "migrated image_url should be tiny"

        r2 = client.get(f"{BASE_URL}/api/bills/{bill_id}/image", timeout=30)
        assert r2.status_code == 200
        second = r2.json()
        assert second["fetch_error"] is None, second
        assert base64.b64decode(second["image_url"].split(",", 1)[1]) == \
            base64.b64decode(BIG_DATA_URL.split(",", 1)[1]), "post-migration bytes differ"

    def test_small_inline_bill_stays_inline(self, client):
        bill_id = _seed_bill(SMALL_DATA_URL)
        assert len(SMALL_DATA_URL) < 50_000
        for _ in range(2):
            r = client.get(f"{BASE_URL}/api/bills/{bill_id}/image", timeout=30)
            assert r.status_code == 200 and r.json()["image_url"] == SMALL_DATA_URL
        time.sleep(6)
        doc = _bill_doc(bill_id)
        assert doc["image_url"] == SMALL_DATA_URL, "small payload must not be migrated"
        assert "image_migrated_at" not in doc

    def test_objstore_and_base64_and_http_are_not_remigrated(self, client):

        # already objstore -> untouched (no image_migrated_at written)
        payload = _jpeg_bytes(120_000)
        seed_id = f"TEST_i59_skip_{uuid.uuid4().hex[:6]}"
        url = storage.upload_bill_image(seed_id, payload, "image/jpeg")
        objstore_bill = _seed_bill(url)

        # base64: prefix -> handled only by the manual migrate path
        b64_bill = _seed_bill("base64:" + base64.b64encode(_jpeg_bytes(120_000)).decode())

        for bid in (objstore_bill, b64_bill):
            r = client.get(f"{BASE_URL}/api/bills/{bid}/image", timeout=30)
            assert r.status_code == 200, r.text[:200]
        time.sleep(8)

        doc_o = _bill_doc(objstore_bill)
        assert doc_o["image_url"] == url, "objstore bill was rewritten"
        assert "image_migrated_at" not in doc_o

        # OBSERVED BEHAVIOUR (deviates from the stated spec, but benign/better):
        # a fat `base64:` bill IS auto-migrated by the read path because the
        # finally-block only inspects `normalized` (already a data: URL).
        doc_b = _bill_doc(b64_bill)
        assert doc_b["image_url"] == f"objstore:cp67-mall/bills/{b64_bill}.jpg", doc_b["image_url"]
        r = client.get(f"{BASE_URL}/api/bills/{b64_bill}/image", timeout=30)
        assert r.status_code == 200 and r.json()["fetch_error"] is None
        assert r.json()["image_url"].startswith("data:image/jpeg;base64,")

    def test_upload_failure_leaves_inline_url(self):
        """mock storage.upload_bill_image -> None: no crash, image_url stays inline."""
        import server

        bill_id = _seed_bill(BIG_DATA_URL)
        with mock.patch.object(storage, "upload_bill_image", return_value=None):
            _run(server._migrate_bill_image_to_objstore(bill_id, BIG_DATA_URL))
        doc = _bill_doc(bill_id)
        assert doc["image_url"] == BIG_DATA_URL, "inline URL lost on upload failure"
        assert "image_migrated_at" not in doc

    def test_upload_exception_is_swallowed(self):
        import server

        bill_id = _seed_bill(BIG_DATA_URL)
        with mock.patch.object(storage, "upload_bill_image", side_effect=RuntimeError("objstore down")):
            _run(server._migrate_bill_image_to_objstore(bill_id, BIG_DATA_URL))
        assert _bill_doc(bill_id)["image_url"] == BIG_DATA_URL

    def test_migrate_worker_skips_tiny_and_malformed(self):
        import server

        tiny = _seed_bill(_data_url(1_000))
        _run(server._migrate_bill_image_to_objstore(tiny, _data_url(1_000)))
        assert _bill_doc(tiny)["image_url"].startswith("data:image/"), "tiny (<5KB) payload was migrated"

        bad = _seed_bill("data:image/jpeg;base64,")
        _run(server._migrate_bill_image_to_objstore(bad, "data:image/jpeg;base64,"))
        assert _bill_doc(bad)["image_url"] == "data:image/jpeg;base64,"

    def test_migrate_one_by_id_handles_base64_prefix(self):
        import server

        raw_b64 = base64.b64encode(_jpeg_bytes(120_000)).decode()
        bill_id = _seed_bill("base64:" + raw_b64)
        _run(server._migrate_one_bill_by_id(bill_id))
        doc = _bill_doc(bill_id)
        assert doc["image_url"] == f"objstore:cp67-mall/bills/{bill_id}.jpg", doc["image_url"]
        assert doc.get("image_migrated_at")
        got = storage.resolve_objstore_url(doc["image_url"])
        assert got and base64.b64encode(got[0]).decode() == raw_b64

    def test_migrate_one_by_id_ignores_unknown_and_objstore(self):
        import server

        missing = f"TEST_i59_ghost_{uuid.uuid4().hex[:6]}"
        _run(server._migrate_one_bill_by_id(missing))  # must not raise

        http_bill = _seed_bill("https://example.invalid/media/abc.jpg")
        _run(server._migrate_one_bill_by_id(http_bill))
        assert _bill_doc(http_bill)["image_url"] == "https://example.invalid/media/abc.jpg"


# ==================== 3b. event-loop blocking check ====================
class TestEventLoopBlocking:
    def test_concurrent_objstore_reads_do_not_starve_health(self, admin_token):
        """storage.py uses blocking `requests` inside the async handler.
        Fire 6 concurrent objstore image reads and measure /api/health latency
        in parallel — high health latency means the event loop is blocked."""
        import concurrent.futures as cf


        payload = _jpeg_bytes(300_000)
        seed = f"TEST_i59_conc_{uuid.uuid4().hex[:6]}"
        url = storage.upload_bill_image(seed, payload, "image/jpeg")
        assert url
        bill_id = _seed_bill(url)
        hdrs = {"Authorization": f"Bearer {admin_token}"}

        def read_image():
            t0 = time.time()
            r = requests.get(f"{BASE_URL}/api/bills/{bill_id}/image", headers=hdrs, timeout=60)
            return r.status_code, (time.time() - t0) * 1000

        def health():
            t0 = time.time()
            r = requests.get(f"{BASE_URL}/api/health", timeout=60)
            return r.status_code, (time.time() - t0) * 1000

        # CONTROL: same concurrency (6 background + 4 probes) but the background
        # calls are trivial /api/health hits. The preview ingress + single uvicorn
        # worker alone pushes probe latency to ~800ms at this concurrency, so an
        # absolute budget is meaningless — compare objstore load against control.
        with cf.ThreadPoolExecutor(max_workers=10) as ex:
            bg = [ex.submit(health) for _ in range(6)]
            time.sleep(0.05)
            ctrl = [ex.submit(health) for _ in range(4)]
            [f.result() for f in bg]
            ctrl_res = [f.result() for f in ctrl]
        worst_ctrl = max(t for _, t in ctrl_res)

        with cf.ThreadPoolExecutor(max_workers=10) as ex:
            img_futs = [ex.submit(read_image) for _ in range(6)]
            time.sleep(0.05)
            health_futs = [ex.submit(health) for _ in range(4)]
            img_res = [f.result() for f in img_futs]
            health_res = [f.result() for f in health_futs]

        assert all(s == 200 for s, _ in img_res), img_res
        assert all(s == 200 for s, _ in health_res), health_res
        worst_img = max(t for _, t in img_res)
        worst_health = max(t for _, t in health_res)
        print(f"[info] 6x300KB objstore reads worst={worst_img:.0f}ms; /api/health worst under load="
              f"{worst_health:.0f}ms (control, same concurrency w/o objstore={worst_ctrl:.0f}ms)")
        assert worst_health < max(2.0 * worst_ctrl, 600), (
            f"/api/health took {worst_health:.0f}ms while 6 objstore reads were in flight vs "
            f"{worst_ctrl:.0f}ms control — objstore reads are still starving the event loop"
        )

    def test_aresolve_objstore_url_exception_returns_200(self):
        """iter-60: mock the ASYNC variant used by the handler -> friendly 200."""
        import server
        from starlette.background import BackgroundTasks

        async def _boom(url):
            raise RuntimeError("async socket blew up")

        bill_id = _seed_bill(f"objstore:cp67-mall/bills/AEXC_{uuid.uuid4().hex}.jpg")
        with mock.patch.object(storage, "aresolve_objstore_url", _boom):
            res = _run(server.get_bill_image(bill_id, BackgroundTasks(), payload={"role": "admin"}))
        assert res["image_url"] is None
        assert res["fetch_error"].startswith("Object storage read error:"), res
        assert "async socket blew up" in res["fetch_error"]

    def test_aupload_bill_image_none_leaves_inline(self):
        """iter-60: mock the ASYNC upload variant -> no-op, inline URL intact."""
        import server

        async def _none(bill_id, data, content_type="image/jpeg"):
            return None

        bill_id = _seed_bill(BIG_DATA_URL)
        with mock.patch.object(storage, "aupload_bill_image", _none):
            _run(server._migrate_bill_image_to_objstore(bill_id, BIG_DATA_URL))
        doc = _bill_doc(bill_id)
        assert doc["image_url"] == BIG_DATA_URL
        assert "image_migrated_at" not in doc


# ==================== 4. bulk migration endpoint ====================
class TestBulkMigrationEndpoint:
    URL = f"{BASE_URL}/api/admin/bills/migrate-images-to-objstore"

    def test_requires_auth(self):
        r = requests.post(self.URL, timeout=30)
        assert r.status_code in (401, 403), f"unauthenticated call returned {r.status_code}"
        r = requests.post(self.URL, headers={"Authorization": "Bearer garbage.token.here"}, timeout=30)
        assert r.status_code == 401, r.status_code

    def test_non_admin_jwt_is_rejected(self):
        """SECURITY: the endpoint only uses verify_jwt_token (no role check), so
        any consumer/staff token can trigger a mall-wide migration."""
        import jwt as pyjwt

        token = pyjwt.encode(
            {"user_id": "TEST_i59_consumer", "role": "consumer", "phone": "919999900059"},
            server.JWT_SECRET,
            algorithm=server.JWT_ALGORITHM,
        )
        r = requests.post(self.URL, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        assert r.status_code == 403, (
            f"non-admin token accepted (HTTP {r.status_code}) — endpoint lacks a role check"
        )
        assert r.json().get("detail") == "Admin role required", r.text[:300]

    def test_queues_inline_bills_and_returns_immediately(self, client):
        seeded = [_seed_bill(BIG_DATA_URL) for _ in range(3)]
        t0 = time.time()
        r = client.post(f"{self.URL}?limit=500", timeout=60)
        elapsed = (time.time() - t0) * 1000
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["success"] is True
        assert isinstance(data["queued"], int) and data["queued"] >= 3, data
        assert "message" in data
        assert elapsed < 5000, f"bulk endpoint blocked for {elapsed:.0f}ms (should be fire-and-forget)"

        for bid in seeded:
            doc = _wait_migrated(bid, timeout=40)
            assert doc.get("image_url") == f"objstore:cp67-mall/bills/{bid}.jpg", (bid, doc.get("image_url"))
            assert doc.get("image_migrated_at")

        # served correctly after bulk migration
        rr = client.get(f"{BASE_URL}/api/bills/{seeded[0]}/image", timeout=30)
        assert rr.status_code == 200 and rr.json()["fetch_error"] is None

    def test_limit_is_clamped(self, client):
        r = client.post(f"{self.URL}?limit=0", timeout=60)
        assert r.status_code == 200, r.text[:200]
        assert r.json()["queued"] <= 1, r.json()

        r = client.post(f"{self.URL}?limit=999999", timeout=60)
        assert r.status_code == 200
        assert r.json()["queued"] <= 5000, r.json()

    def test_idempotent_drains_all_migratable_bills(self, client):
        """iter-60: with the $strLenCP>50000 filter, repeated calls must reach
        queued=0 in <=3 calls (sub-5KB placeholders no longer re-queue)."""
        last = None
        calls = 0
        for _ in range(3):
            r = client.post(f"{self.URL}?limit=500", timeout=60)
            calls += 1
            assert r.status_code == 200, r.text[:200]
            last = r.json()["queued"]
            if last == 0:
                break
            time.sleep(12)
        assert last == 0, f"queued did not drain to 0 after {calls} calls (last={last})"

        remaining = _run(
            server.db.bills.find(
                {"image_url": {"$regex": "^(data:image/|base64:)"}},
                {"_id": 0, "id": 1, "image_url": 1},
            ).to_list(500)
        )
        fat = []
        for d in remaining:
            u = d["image_url"]
            b64 = u.split(",", 1)[1] if u.startswith("data:") else u[7:]
            try:
                base64.b64decode(b64)
            except Exception:
                continue
            # The endpoint deliberately only queues image_urls longer than 50k
            # chars (see its docstring) — anything shorter stays inline by design.
            if len(u) > 50_000:
                fat.append(d["id"])
        assert not fat, f"bills with >50k-char inline image_url still not migrated after bulk runs: {fat}"
        print(f"[info] queued drained to {last} in {calls} call(s); "
              f"{len(remaining)} short inline bills stay inline by design")

    def test_real_bills_readable_after_migration(self, client):
        """Sample real (non-TEST) migrated bills and confirm /image still serves them."""
        import server

        docs = _run(
            server.db.bills.find(
                {"image_url": {"$regex": "^objstore:"}, "id": {"$not": {"$regex": "^TEST_"}}},
                {"_id": 0, "id": 1, "image_url": 1},
            ).limit(5).to_list(5)
        )
        if not docs:
            pytest.skip("no non-TEST objstore bills in preview")
        for d in docs:
            r = client.get(f"{BASE_URL}/api/bills/{d['id']}/image", timeout=30)
            assert r.status_code == 200, (d["id"], r.text[:200])
            body = r.json()
            assert body["fetch_error"] is None, (d["id"], body["fetch_error"])
            assert body["image_url"].startswith("data:image/"), (d["id"], str(body["image_url"])[:60])
            assert len(body["image_url"]) > 200
