"""Iteration 62 — large-field projection fixes on the bills collection.

Covers (per review request):
  * POST /api/bills/{id}/process (approve): first find_one omits image_url +
    ocr_raw_data; approve branch re-fetches image_url via targeted projection;
    TagnPay earn-points still receives valid base64; status/points/WhatsApp OK.
  * POST /api/bills/{id}/process (reject): no image_url fetch at all; status
    rejected, Fundle log queued in background, WhatsApp rejection queued.
  * GET /api/bills/{id}: response has NO image_url and NO ocr_raw_data.
  * GET /api/bills/{id}/image: still serves data:, base64:, objstore:, http:
    shapes; max_time_ms=25000 applied.
  * _resolve_bill_image_base64: objstore:<path> branch returns base64.
  * Regression: maybe_alert_admin projection (iteration 61) still intact.
"""
import asyncio
import base64
import inspect
import os
import re
import sys
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
# ~500KB inline base64 image (mimics the legacy multi-MB payload shape)
BIG_B64 = base64.b64encode(b"Y" * 500_000).decode()
BIG_DATA_URL = "data:image/jpeg;base64," + BIG_B64

TEST_USER_ID = "TEST_ITER62_USER"
TEST_PHONE = "919876543210"

_bills = []


def _seed_user():
    _run(server.db.users.update_one(
        {"id": TEST_USER_ID},
        {"$set": {
            "id": TEST_USER_ID,
            "phone": TEST_PHONE,
            "name": "TEST_ITER62",
            "balance_points": 100,
            "total_earned_points": 100,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    ))


def _seed_bill(status="pending_review", image_url=BIG_DATA_URL, **over):
    bid = "TEST_ITER62_" + str(uuid.uuid4())[:8]
    doc = {
        "id": bid,
        "user_id": TEST_USER_ID,
        "user_phone": TEST_PHONE,
        "store_name": "TEST_Zara",
        "amount": 1500.0,
        "bill_no": f"TEST-62-{bid[-4:]}",
        "bill_date": "2026-07-01",
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


class _Req:
    """Stand-in for BillProcessRequest for direct in-process handler calls."""

    def __init__(self, action, **kw):
        self.bill_id = kw.get("bill_id", "")
        self.action = action
        self.rejection_reason = kw.get("rejection_reason")
        self.admin_notes = kw.get("admin_notes")
        self.points_override = kw.get("points_override")
        self.send_whatsapp = kw.get("send_whatsapp", True)


class _CollProxy:
    """Delegates to the real motor collection but records find_one call args.
    (motor's db.bills returns a fresh object each access, so we must proxy the
    db object itself rather than patch the collection attribute.)"""

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
    """Context helper: patches server.db so bills.find_one calls are recorded."""

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
                out.append(c["args"][1])
            else:
                out.append(c["kwargs"].get("projection") or {})
        return out


# =================================================== process_bill  (approve)
class TestProcessBillApprove:
    def test_approve_projection_and_tagnpay_image(self):
        bid = _seed_bill()
        earn_kwargs = {}

        async def fake_earn(**kw):
            earn_kwargs.update(kw)
            return {"success": True, "data": {"earned_points": 15, "total_points": 115}}

        from fastapi import BackgroundTasks
        bg = BackgroundTasks()
        with _FindOneSpy() as spy, \
             mock.patch.object(server.tagnpay_client, "earn_points", side_effect=fake_earn), \
             mock.patch.object(server.tagnpay_client, "get_customer_points",
                               new=mock.AsyncMock(return_value={"success": True, "data": {"balance_points": 115}})):
            res = _run(server.process_bill(
                bid, _Req("approve", bill_id=bid), bg,
                payload={"username": "admin", "name": "Admin", "role": "admin"},
            ))

        assert res.get("success") is True
        assert res.get("action") == "approve"
        assert spy.calls, "no bills.find_one calls recorded (spy not wired)"

        # --- primary find_one must exclude the heavy fields
        proj = spy.projections()[0]
        assert proj, "primary find_one has no projection (full doc transferred)"
        assert proj.get("image_url") == 0, f"image_url not excluded in primary find_one: {proj}"
        assert proj.get("ocr_raw_data") == 0, f"ocr_raw_data not excluded: {proj}"

        # --- targeted re-fetch of image_url only
        img_projs = [p for p in spy.projections() if p.get("image_url") == 1]
        assert img_projs, "approve path never re-fetched image_url with a targeted projection"
        assert set(k for k, v in img_projs[0].items() if v == 1) == {"image_url"}, \
            f"image re-fetch projection pulls extra fields: {img_projs[0]}"

        # --- TagnPay got valid base64 of the seeded image
        assert "bill_image_base64" in earn_kwargs
        b64 = earn_kwargs["bill_image_base64"]
        assert b64, "TagnPay earn_points received no image base64"
        assert base64.b64decode(b64) == b"Y" * 500_000
        assert earn_kwargs["bill_amount"] == 1500.0
        assert earn_kwargs["mobile_number"] == "9876543210"

    def test_approve_persists_status_points_and_queues_whatsapp(self):
        bid = _seed_bill()
        before = _run(server.db.users.find_one({"id": TEST_USER_ID}, {"_id": 0, "balance_points": 1}))
        from fastapi import BackgroundTasks
        bg = BackgroundTasks()
        with mock.patch.object(server.tagnpay_client, "earn_points",
                               new=mock.AsyncMock(return_value={"success": True, "data": {"earned_points": 20, "total_points": 200}})), \
             mock.patch.object(server.tagnpay_client, "get_customer_points",
                               new=mock.AsyncMock(return_value={"success": True, "data": {"balance_points": 200}})):
            res = _run(server.process_bill(
                bid, _Req("approve", bill_id=bid), bg,
                payload={"username": "admin", "name": "Admin", "role": "admin"},
            ))

        assert res["points_issued"] == 20
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "status": 1, "points_issued": 1, "processed_by": 1}))
        assert doc["status"] == "approved"
        assert doc["points_issued"] == 20
        assert doc["processed_by"] == "Admin"

        after = _run(server.db.users.find_one({"id": TEST_USER_ID}, {"_id": 0, "balance_points": 1}))
        assert after["balance_points"] == before["balance_points"] + 20

        # WhatsApp queued as background task + outbound log written
        names = [getattr(t.func, "__name__", str(t.func)) for t in bg.tasks]
        assert "send_whatsapp_buttons" in names, f"WhatsApp not queued: {names}"
        log = _run(server.db.whatsapp_logs.find_one({"user_id": TEST_USER_ID, "direction": "outbound"}))
        assert log and "Points Credited" in log["content"]

    def test_approve_via_http_end_to_end(self, auth_headers):
        """Real endpoint + real TagnPay with a 500KB inline image — must not 500."""
        import time
        bid = _seed_bill()
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/bills/{bid}/process",
            json={"bill_id": bid, "action": "approve", "send_whatsapp": False},
            headers=auth_headers, timeout=120,
        )
        elapsed = time.time() - t0
        assert r.status_code == 200, f"{r.status_code} in {elapsed:.1f}s: {r.text[:400]}"
        body = r.json()
        assert body["success"] is True and body["action"] == "approve"
        assert isinstance(body["points_issued"], (int, float)) and body["points_issued"] > 0
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "status": 1, "points_issued": 1}))
        assert doc["status"] == "approved"
        assert doc["points_issued"] == body["points_issued"]
        print(f"HTTP approve latency with 500KB image: {elapsed:.2f}s")

    def test_approve_objstore_image_resolves_to_base64(self):
        """_resolve_bill_image_base64 objstore:<path> branch feeds TagnPay."""
        bid = _seed_bill(image_url="objstore:cp67-mall/bills/TEST_ITER62.jpg")
        earn_kwargs = {}

        async def fake_earn(**kw):
            earn_kwargs.update(kw)
            return {"success": True, "data": {"earned_points": 5, "total_points": 5}}

        async def fake_objstore(url):
            assert url == "objstore:cp67-mall/bills/TEST_ITER62.jpg"
            return (b"OBJSTOREBYTES" * 100, "image/jpeg")

        from fastapi import BackgroundTasks
        with mock.patch("storage.aresolve_objstore_url", side_effect=fake_objstore), \
             mock.patch.object(server.tagnpay_client, "earn_points", side_effect=fake_earn), \
             mock.patch.object(server.tagnpay_client, "get_customer_points",
                               new=mock.AsyncMock(return_value={"success": True, "data": {"balance_points": 5}})):
            _run(server.process_bill(
                bid, _Req("approve", bill_id=bid, send_whatsapp=False), BackgroundTasks(),
                payload={"username": "admin", "role": "admin"},
            ))

        b64 = earn_kwargs.get("bill_image_base64")
        assert b64, "objstore bill sent no base64 to TagnPay"
        assert base64.b64decode(b64) == b"OBJSTOREBYTES" * 100

    def test_resolve_bill_image_base64_shapes(self):
        # data:
        assert _run(server._resolve_bill_image_base64({"image_url": BIG_DATA_URL})) == BIG_B64
        # base64:
        assert _run(server._resolve_bill_image_base64({"image_url": "base64:" + BIG_B64})) == BIG_B64
        # empty / missing
        assert _run(server._resolve_bill_image_base64({"image_url": ""})) is None
        assert _run(server._resolve_bill_image_base64({})) is None
        # objstore returning nothing → None (graceful skip)
        with mock.patch("storage.aresolve_objstore_url", new=mock.AsyncMock(return_value=None)):
            assert _run(server._resolve_bill_image_base64({"image_url": "objstore:x/y.jpg"})) is None


# =================================================== process_bill  (reject)
class TestProcessBillReject:
    def test_reject_never_fetches_image_and_persists(self):
        bid = _seed_bill()
        from fastapi import BackgroundTasks
        bg = BackgroundTasks()
        with _FindOneSpy() as spy, \
             mock.patch.object(server.tagnpay_client, "log_rejected_bill", new=mock.AsyncMock(return_value={"success": True})):
            res = _run(server.process_bill(
                bid, _Req("reject", bill_id=bid, rejection_reason="TEST blurry image"), bg,
                payload={"username": "admin", "name": "Admin", "role": "admin"},
            ))

        assert res["success"] is True and res["action"] == "reject"
        assert spy.calls, "no bills.find_one calls recorded (spy not wired)"
        # no call anywhere requested image_url
        for proj in spy.projections():
            assert proj.get("image_url") != 1, f"reject path fetched image_url: {proj}"

        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "status": 1, "admin_rejection_reason": 1, "system_rejection_reason": 1}))
        assert doc["status"] == "rejected"
        assert doc["admin_rejection_reason"] == "TEST blurry image"
        assert doc["system_rejection_reason"] == "TEST system reason"

        names = [getattr(t.func, "__name__", str(t.func)) for t in bg.tasks]
        assert "_log_reject_bg" in names, f"Fundle rejection log not queued: {names}"
        assert "maybe_alert_admin" in names, f"admin alert not queued on reject: {names}"
        assert "send_whatsapp_buttons" in names, f"WhatsApp rejection not queued: {names}"

    def test_reject_via_http_end_to_end(self, auth_headers):
        bid = _seed_bill()
        r = requests.post(
            f"{BASE_URL}/api/bills/{bid}/process",
            json={"bill_id": bid, "action": "reject", "rejection_reason": "TEST http reject", "send_whatsapp": False},
            headers=auth_headers, timeout=120,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        body = r.json()
        assert body["success"] is True and body["action"] == "reject"
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "status": 1, "admin_rejection_reason": 1}))
        assert doc["status"] == "rejected"
        assert doc["admin_rejection_reason"] == "TEST http reject"

    def test_process_unknown_bill_404(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/bills/TEST_ITER62_NOPE/process",
            json={"bill_id": "TEST_ITER62_NOPE", "action": "reject", "send_whatsapp": False},
            headers=auth_headers, timeout=60,
        )
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"

    def test_process_requires_auth(self):
        r = requests.post(
            f"{BASE_URL}/api/bills/TEST_ITER62_NOPE/process",
            json={"bill_id": "TEST_ITER62_NOPE", "action": "reject"}, timeout=60,
        )
        assert r.status_code in (401, 403), f"unauthenticated process returned {r.status_code}"


# ================================================= GET /api/bills/{bill_id}
class TestGetBillDetails:
    def test_details_excludes_large_fields(self, auth_headers):
        bid = _seed_bill()
        r = requests.get(f"{BASE_URL}/api/bills/{bid}", headers=auth_headers, timeout=60)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        body = r.json()
        bill = body["bill"]
        assert "image_url" not in bill, "GET /bills/{id} leaked image_url"
        assert "ocr_raw_data" not in bill, "GET /bills/{id} leaked ocr_raw_data"
        assert "_id" not in bill
        # required fields still present
        assert bill["id"] == bid
        assert bill["amount"] == 1500.0
        assert bill["store_name"] == "TEST_Zara"
        assert bill["status"] == "pending_review"
        assert body["user"] and body["user"]["id"] == TEST_USER_ID
        assert "_id" not in body["user"]
        # payload must be small now
        assert len(r.content) < 20_000, f"response still {len(r.content)} bytes"

    def test_details_404(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/bills/TEST_ITER62_NOPE", headers=auth_headers, timeout=60)
        assert r.status_code == 404


# =========================================== GET /api/bills/{bill_id}/image
class TestGetBillImage:
    def test_max_time_ms_applied(self):
        src = inspect.getsource(server.get_bill_image)
        assert "max_time_ms=25000" in src, "max_time_ms=25000 missing on get_bill_image find_one"

    def test_inline_data_url(self, auth_headers):
        bid = _seed_bill()
        r = requests.get(f"{BASE_URL}/api/bills/{bid}/image", headers=auth_headers, timeout=90)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        body = r.json()
        assert body.get("fetch_error") in (None, ""), f"fetch_error: {body.get('fetch_error')}"
        assert body["image_url"].startswith("data:image/jpeg;base64,")
        assert body["image_url"].split(",", 1)[1] == BIG_B64

    def test_base64_prefix_shape(self, auth_headers):
        bid = _seed_bill(image_url="base64:" + BIG_B64)
        r = requests.get(f"{BASE_URL}/api/bills/{bid}/image", headers=auth_headers, timeout=90)
        assert r.status_code == 200
        body = r.json()
        assert not body.get("fetch_error")
        assert body["image_url"] == "data:image/jpeg;base64," + BIG_B64

    def test_missing_image_returns_friendly_error(self, auth_headers):
        bid = _seed_bill(image_url="")
        r = requests.get(f"{BASE_URL}/api/bills/{bid}/image", headers=auth_headers, timeout=60)
        assert r.status_code == 200
        body = r.json()
        assert body["image_url"] is None
        assert body["fetch_error"] == "No image on record for this bill."

    def test_unreachable_http_url_no_500(self, auth_headers):
        bid = _seed_bill(image_url="http://127.0.0.1:9/nope.jpg")
        r = requests.get(f"{BASE_URL}/api/bills/{bid}/image", headers=auth_headers, timeout=90)
        assert r.status_code == 200, f"http shape returned {r.status_code}: {r.text[:300]}"
        body = r.json()
        assert body["image_url"] is None
        assert body["fetch_error"], "expected a fetch_error diagnostic"

    def test_objstore_shape_in_process(self):
        """objstore path exercised in-process (no live object-storage dependency)."""
        bid = _seed_bill(image_url="objstore:cp67-mall/bills/TEST_ITER62_IMG.jpg")
        from fastapi import BackgroundTasks
        with mock.patch("storage.aresolve_objstore_url",
                        new=mock.AsyncMock(return_value=(b"PNGBYTES" * 200, "image/png"))):
            out = _run(server.get_bill_image(bid, BackgroundTasks(), payload={"username": "admin"}))
        assert out["fetch_error"] is None, out
        assert out["image_url"].startswith("data:image/png;base64,")
        assert base64.b64decode(out["image_url"].split(",", 1)[1]) == b"PNGBYTES" * 200

    def test_image_404_unknown_bill(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/bills/TEST_ITER62_NOPE/image", headers=auth_headers, timeout=60)
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"


# ============================== regression: maybe_alert_admin (iteration 61)
class TestMaybeAlertAdminRegression:
    def test_alert_projection_and_dedup(self):
        bid = _seed_bill()
        seen = {}

        async def fake_alert(event, bill, reason=None):
            seen["event"] = event
            seen["bill"] = dict(bill)
            seen["reason"] = reason

        with mock.patch.object(server, "send_admin_bill_alert", side_effect=fake_alert):
            _run(server.maybe_alert_admin(bid, "rejected", "TEST reason"))
        assert seen, "send_admin_bill_alert never called"
        b = seen["bill"]
        assert "image_url" not in b and "ocr_raw_data" not in b and "_id" not in b
        assert b["id"] == bid and b["amount"] == 1500.0 and b["user_phone"] == TEST_PHONE
        assert seen["reason"] == "TEST reason"

        # dedup: second call for same status must not re-alert
        calls = []
        with mock.patch.object(server, "send_admin_bill_alert",
                               side_effect=lambda *a, **k: calls.append(a) or asyncio.sleep(0)):
            _run(server.maybe_alert_admin(bid, "rejected", "TEST reason"))
        assert not calls, "dedup broken — alert fired twice for same (bill, status)"


# ============ adjacent endpoints that still fetch the FULL bill doc (risk) ====
class TestRemainingFullDocFetches:
    """Read-only probes on endpoints that still pull image_url inline. They work
    locally; flagged for the same Atlas maxTimeMS risk as iteration 62's fixes."""

    def test_force_credit_preview_works_but_fetches_full_doc(self, auth_headers):
        bid = _seed_bill()
        r = requests.get(f"{BASE_URL}/api/admin/bills/{bid}/force-credit-preview",
                         headers=auth_headers, timeout=90)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        body = r.json()
        assert body["bill_id"] == bid and body["amount"] == 1500.0
        # response itself is small (good) — the risk is the server-side transfer
        assert len(r.content) < 5_000

    def test_force_credit_preview_projection_is_full_doc(self):
        src = inspect.getsource(server.force_credit_preview)
        assert 'find_one({"id": bill_id}, {"_id": 0})' in src, \
            "force_credit_preview projection changed — update this guard"
