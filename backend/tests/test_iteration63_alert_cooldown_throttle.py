"""Iteration 63 — scanner-loop snowball hardening.

Covers (per review request):
  1. maybe_alert_admin registers a 5-min cooldown in _ALERT_FAILURE_COOLDOWN on
     any exception; next call with the SAME (bill_id, status) returns early
     without touching find_one.
  2. Cooldown is cleared on a successful send.
  3. find_one inside maybe_alert_admin is called with max_time_ms=5000.
  4. _bill_alert_scanner_loop uses .limit(10) per status and awaits
     asyncio.sleep(0.5) between successive maybe_alert_admin calls.
  5. Happy path: fresh (bill_id, status) still alerts + writes
     admin_alerts_sent.<status>.
  6. Light regression on iteration 61/62 fixes.
"""
import asyncio
import base64
import inspect
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
BIG_B64 = base64.b64encode(b"Y" * 200_000).decode()
BIG_DATA_URL = "data:image/jpeg;base64," + BIG_B64

TEST_USER_ID = "TEST_ITER63_USER"
TEST_PHONE = "919876543210"

_bills = []


def _seed_user():
    _run(server.db.users.update_one(
        {"id": TEST_USER_ID},
        {"$set": {
            "id": TEST_USER_ID,
            "phone": TEST_PHONE,
            "name": "TEST_ITER63",
            "balance_points": 100,
            "total_earned_points": 100,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    ))


def _seed_bill(status="pending_review", image_url=BIG_DATA_URL, **over):
    bid = "TEST_ITER63_" + str(uuid.uuid4())[:8]
    doc = {
        "id": bid,
        "user_id": TEST_USER_ID,
        "user_phone": TEST_PHONE,
        "store_name": "TEST_Zara63",
        "amount": 1500.0,
        "bill_no": f"TEST-63-{bid[-4:]}",
        "bill_date": "2026-07-01",
        "status": status,
        "rejection_reason": "TEST system reason 63",
        "image_url": image_url,
        "ocr_raw_data": {"extraction_notes": "TEST ocr notes", "blob": "Z" * 20_000},
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
    _run(server.db.bills.delete_many({"id": {"$regex": "^TEST_ITER63_"}}))
    _run(server.db.users.delete_many({"id": TEST_USER_ID}))
    _run(server.db.whatsapp_logs.delete_many({"user_id": TEST_USER_ID}))


@pytest.fixture(autouse=True)
def clear_cooldown():
    server._ALERT_FAILURE_COOLDOWN.clear()
    yield
    server._ALERT_FAILURE_COOLDOWN.clear()


# ------------------------------------------------------------- spy machinery
class _CollProxy:
    """Delegates to the real motor collection, recording find_one args and
    optionally raising instead of hitting the DB."""

    def __init__(self, coll, calls, raise_exc=None):
        self._coll = coll
        self._calls = calls
        self._raise = raise_exc

    async def find_one(self, *args, **kwargs):
        self._calls.append({"args": args, "kwargs": kwargs})
        if self._raise is not None:
            raise self._raise
        return await self._coll.find_one(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._coll, item)


class _DbProxy:
    def __init__(self, db, calls, raise_exc=None):
        self._db = db
        self._calls = calls
        self._raise = raise_exc

    @property
    def bills(self):
        return _CollProxy(self._db.bills, self._calls, self._raise)

    def __getattr__(self, item):
        return getattr(self._db, item)


class _FindOneSpy:
    def __init__(self, raise_exc=None):
        self.calls = []
        self._raise = raise_exc
        self._patch = None

    def __enter__(self):
        self._patch = mock.patch.object(
            server, "db", new=_DbProxy(server.db, self.calls, self._raise))
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        return False


class _NoopAlert:
    """Patches send_admin_bill_alert; records bills passed."""

    def __init__(self):
        self.bills = []

    def __enter__(self):
        async def fake(event, bill, reason=None):
            self.bills.append({"event": event, "bill": dict(bill), "reason": reason})
        self._p = mock.patch.object(server, "send_admin_bill_alert", side_effect=fake)
        self._p.start()
        return self

    def __exit__(self, *exc):
        self._p.stop()
        return False


# ============================================== 1/2/3. cooldown + max_time_ms
class TestAlertFailureCooldown:
    def test_failure_registers_cooldown_and_next_call_skips_find_one(self):
        from pymongo.errors import ExecutionTimeout
        bid = _seed_bill(status="manual_review")
        key = (bid, "manual_review")

        # --- first call: find_one raises -> cooldown registered
        t0 = time.time()
        with _FindOneSpy(raise_exc=ExecutionTimeout("operation exceeded time limit")) as spy:
            _run(server.maybe_alert_admin(bid, "manual_review", "TEST reason"))
            assert len(spy.calls) == 1, f"expected 1 find_one, got {len(spy.calls)}"

        assert key in server._ALERT_FAILURE_COOLDOWN, \
            f"cooldown not registered on failure: {server._ALERT_FAILURE_COOLDOWN}"
        until = server._ALERT_FAILURE_COOLDOWN[key]
        # 5 minutes (300s) window, allow small clock slack
        assert 295 <= (until - t0) <= 305, f"cooldown window not ~300s: {until - t0:.1f}s"

        # --- second call for SAME (bill, status): must not hit the DB at all
        with _FindOneSpy() as spy2, _NoopAlert() as alerts:
            _run(server.maybe_alert_admin(bid, "manual_review", "TEST reason"))
        assert spy2.calls == [], f"cooldown did not short-circuit find_one: {spy2.calls}"
        assert alerts.bills == [], "alert fired despite active cooldown"

    def test_cooldown_is_per_status_not_per_bill(self):
        from pymongo.errors import ExecutionTimeout
        bid = _seed_bill(status="manual_review")
        with _FindOneSpy(raise_exc=ExecutionTimeout("boom")):
            _run(server.maybe_alert_admin(bid, "manual_review"))
        assert (bid, "manual_review") in server._ALERT_FAILURE_COOLDOWN

        # a different status on the same bill must still be attempted
        with _FindOneSpy() as spy, _NoopAlert() as alerts:
            _run(server.maybe_alert_admin(bid, "rejected", "TEST other status"))
        assert len(spy.calls) >= 1, "different status was wrongly suppressed"
        assert alerts.bills, "different status did not fire an alert"

    def test_expired_cooldown_allows_retry(self):
        bid = _seed_bill(status="pending_review")
        server._ALERT_FAILURE_COOLDOWN[(bid, "pending_review")] = time.time() - 1
        with _FindOneSpy() as spy, _NoopAlert() as alerts:
            _run(server.maybe_alert_admin(bid, "pending_review"))
        assert spy.calls, "expired cooldown still blocked the call"
        assert alerts.bills, "expired cooldown blocked the alert"

    def test_success_clears_cooldown_entry(self):
        bid = _seed_bill(status="rejected")
        key = (bid, "rejected")
        # simulate a stale-but-active cooldown then let a success run:
        # (set it expired so the guard passes, success must still pop it)
        server._ALERT_FAILURE_COOLDOWN[key] = time.time() - 1
        with _NoopAlert() as alerts:
            _run(server.maybe_alert_admin(bid, "rejected", "TEST reason"))
        assert alerts.bills, "happy path did not alert"
        assert key not in server._ALERT_FAILURE_COOLDOWN, \
            "success path did not clear the cooldown entry"

    def test_find_one_uses_max_time_ms_5000(self):
        bid = _seed_bill(status="manual_review")
        with _FindOneSpy() as spy, _NoopAlert():
            _run(server.maybe_alert_admin(bid, "manual_review"))
        assert spy.calls, "no find_one recorded"
        first = spy.calls[0]
        assert first["kwargs"].get("max_time_ms") == 5000, \
            f"max_time_ms=5000 missing on maybe_alert_admin find_one: {first['kwargs']}"
        # projection (iteration 61) still intact
        proj = first["args"][1] if len(first["args"]) > 1 else first["kwargs"].get("projection")
        assert proj and proj.get("_id") == 0
        assert "image_url" not in proj and "ocr_raw_data" not in proj

    def test_prune_helper_drops_only_expired(self):
        now = time.time()
        server._ALERT_FAILURE_COOLDOWN[("A", "rejected")] = now - 5
        server._ALERT_FAILURE_COOLDOWN[("B", "rejected")] = now + 300
        server._prune_alert_failure_cooldown(now)
        assert ("A", "rejected") not in server._ALERT_FAILURE_COOLDOWN
        assert ("B", "rejected") in server._ALERT_FAILURE_COOLDOWN


# ================================================ 5. happy-path regression
class TestHappyPath:
    def test_fresh_bill_alerts_and_persists_marker(self):
        bid = _seed_bill(status="manual_review")
        with _NoopAlert() as alerts:
            _run(server.maybe_alert_admin(bid, "manual_review", "TEST reason 63"))
        assert len(alerts.bills) == 1, f"expected exactly one alert: {alerts.bills}"
        b = alerts.bills[0]["bill"]
        assert b["id"] == bid and b["amount"] == 1500.0 and b["user_phone"] == TEST_PHONE
        assert "image_url" not in b and "ocr_raw_data" not in b and "_id" not in b
        assert alerts.bills[0]["reason"] == "TEST reason 63"

        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "admin_alerts_sent": 1}))
        assert doc["admin_alerts_sent"].get("manual_review"), \
            f"admin_alerts_sent.manual_review not written: {doc}"

        # dedup still holds
        with _NoopAlert() as alerts2:
            _run(server.maybe_alert_admin(bid, "manual_review", "TEST reason 63"))
        assert alerts2.bills == [], "dedup broken — alert fired twice"

    def test_unknown_status_is_ignored(self):
        bid = _seed_bill(status="approved")
        with _FindOneSpy() as spy, _NoopAlert() as alerts:
            _run(server.maybe_alert_admin(bid, "approved"))
        assert spy.calls == [] and alerts.bills == []


# ================================= 4. scanner loop: limit(10) + sleep(0.5)
class _FakeCursor:
    def __init__(self, docs, rec):
        self._docs = docs
        self._rec = rec

    def limit(self, n):
        self._rec["limits"].append(n)
        self._docs = self._docs[:n]
        return self

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


class _FakeBills:
    def __init__(self, docs_by_status, rec):
        self._docs = docs_by_status
        self._rec = rec

    def find(self, flt, proj=None):
        self._rec["finds"].append({"filter": flt, "projection": proj})
        return _FakeCursor(list(self._docs.get(flt.get("status"), [])), self._rec)


class _FakeDb:
    def __init__(self, bills):
        self.bills = bills


class _StopLoop(Exception):
    pass


class TestScannerLoop:
    def test_source_uses_limit_10_and_sleep_half_second(self):
        src = inspect.getsource(server._bill_alert_scanner_loop)
        assert ".limit(10)" in src, "scanner still uses a larger per-status limit"
        assert ".limit(50)" not in src, "scanner still contains .limit(50)"
        assert "asyncio.sleep(0.5)" in src, "no 0.5s throttle between per-bill alerts"
        assert "asyncio.sleep(60)" in src, "60s cycle interval changed unexpectedly"

    def test_runtime_limit_and_throttle(self):
        """Run one full cycle against a fake collection; assert limit(10) per
        status and one 0.5s sleep per bill."""
        rec = {"finds": [], "limits": []}
        docs = {
            "manual_review": [{"id": f"MR{i}", "rejection_reason": None} for i in range(25)],
            "pending_review": [{"id": f"PR{i}", "rejection_reason": None} for i in range(3)],
            "rejected": [{"id": f"RJ{i}", "rejection_reason": "r"} for i in range(12)],
        }
        alerted = []
        sleeps = []
        real_sleep = asyncio.sleep

        async def fake_sleep(delay, *a, **kw):
            sleeps.append(delay)
            if delay >= 60:          # end of a full cycle -> stop the loop
                raise _StopLoop()
            return await real_sleep(0)

        async def fake_alert(bid, status, reason=None):
            alerted.append((bid, status))

        async def drive():
            with mock.patch.object(server, "db", new=_FakeDb(_FakeBills(docs, rec))), \
                 mock.patch.object(server, "maybe_alert_admin", side_effect=fake_alert), \
                 mock.patch.object(asyncio, "sleep", side_effect=fake_sleep):
                try:
                    await server._bill_alert_scanner_loop()
                except _StopLoop:
                    pass

        _run(drive())

        assert rec["limits"] == [10, 10, 10], f"per-status limits: {rec['limits']}"
        # projections should stay lean
        for f in rec["finds"]:
            assert f["projection"] == {"_id": 0, "id": 1, "rejection_reason": 1}, f
        # 10 + 3 + 10 = 23 bills processed in the cycle
        assert len(alerted) == 23, f"expected 23 alerts in one cycle, got {len(alerted)}"
        throttles = [s for s in sleeps if s == 0.5]
        assert len(throttles) == 23, f"expected 23 x 0.5s throttles, got {len(throttles)}"
        assert sleeps[-1] == 60, f"cycle did not end with a 60s sleep: {sleeps[-3:]}"
        # max concurrent DB reads per cycle is now bounded at 30
        assert sum(rec["limits"]) == 30

    def test_loop_survives_alert_exception(self):
        rec = {"finds": [], "limits": []}
        docs = {"manual_review": [{"id": "MR0"}, {"id": "MR1"}],
                "pending_review": [], "rejected": []}
        seen = []
        real_sleep = asyncio.sleep

        async def fake_sleep(delay, *a, **kw):
            if delay >= 60:
                raise _StopLoop()
            return await real_sleep(0)

        async def boom(bid, status, reason=None):
            seen.append(bid)
            raise RuntimeError("TEST alert blow-up")

        async def drive():
            with mock.patch.object(server, "db", new=_FakeDb(_FakeBills(docs, rec))), \
                 mock.patch.object(server, "maybe_alert_admin", side_effect=boom), \
                 mock.patch.object(asyncio, "sleep", side_effect=fake_sleep):
                try:
                    await server._bill_alert_scanner_loop()
                except _StopLoop:
                    pass

        _run(drive())
        assert seen == ["MR0", "MR1"], f"loop aborted on first failure: {seen}"


# ===================================== 6. light regression (iteration 61/62)
class TestIteration62Regression:
    def test_get_bill_details_excludes_large_fields(self, auth_headers):
        bid = _seed_bill()
        r = requests.get(f"{BASE_URL}/api/bills/{bid}", headers=auth_headers, timeout=60)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        bill = r.json()["bill"]
        assert "image_url" not in bill and "ocr_raw_data" not in bill and "_id" not in bill
        assert bill["id"] == bid and bill["amount"] == 1500.0
        assert len(r.content) < 20_000, f"response still {len(r.content)} bytes"

    def test_get_bill_image_inline(self, auth_headers):
        bid = _seed_bill()
        r = requests.get(f"{BASE_URL}/api/bills/{bid}/image", headers=auth_headers, timeout=90)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        body = r.json()
        assert not body.get("fetch_error"), body.get("fetch_error")
        assert body["image_url"].split(",", 1)[1] == BIG_B64

    def test_resolve_bill_image_objstore_branch(self):
        with mock.patch("storage.aresolve_objstore_url",
                        new=mock.AsyncMock(return_value=(b"OBJ63" * 100, "image/jpeg"))):
            out = _run(server._resolve_bill_image_base64({"image_url": "objstore:x/y63.jpg"}))
        assert out and base64.b64decode(out) == b"OBJ63" * 100

    def test_process_approve_http(self, auth_headers):
        bid = _seed_bill()
        r = requests.post(f"{BASE_URL}/api/bills/{bid}/process",
                          json={"bill_id": bid, "action": "approve", "send_whatsapp": False},
                          headers=auth_headers, timeout=120)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        body = r.json()
        assert body["success"] is True and body["action"] == "approve"
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "status": 1}))
        assert doc["status"] == "approved"

    def test_process_reject_http(self, auth_headers):
        bid = _seed_bill()
        r = requests.post(f"{BASE_URL}/api/bills/{bid}/process",
                          json={"bill_id": bid, "action": "reject",
                                "rejection_reason": "TEST iter63 reject", "send_whatsapp": False},
                          headers=auth_headers, timeout=120)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        doc = _run(server.db.bills.find_one({"id": bid}, {"_id": 0, "status": 1, "admin_rejection_reason": 1}))
        assert doc["status"] == "rejected"
        assert doc["admin_rejection_reason"] == "TEST iter63 reject"

    def test_health_endpoint_responsive(self):
        t0 = time.time()
        r = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        print(f"health latency {time.time() - t0:.2f}s")
