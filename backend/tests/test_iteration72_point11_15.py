"""Iteration 72 — CP67 Points 11 & 15.

Point 11 (retailer OTP observability):
  * GET  /api/admin/staff/retailer/diagnose-otp?phone=...  (admin only, read-only)
  * POST /api/staff/retailer/auth/send-otp  — neutral response + WARN log for
    non-whitelisted phones; real delivery dict for whitelisted+active managers.

Point 15 (admin incentive report resilience):
  * GET /api/admin/staff/incentives/report — max_time_ms bounded cursor,
    transient DB errors mapped to HTTP 503 (not 500), happy-path regression
    for incentive_type filters + bill enrichment.
"""
import asyncio
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
from fastapi import HTTPException

frontend_env = dotenv_values("/app/frontend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing from env and /app/frontend/.env")
BASE_URL = _base.rstrip("/")

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from routes import staff as staff_mod  # noqa: E402

CREDS_PATH = Path("/app/memory/test_credentials.md")
BACKEND_LOGS = ["/var/log/supervisor/backend.err.log", "/var/log/supervisor/backend.out.log"]

PREFIX = "TEST_ITER72_"
WL_PHONE = "9998812345"      # seeded whitelisted+active retailer manager
INACTIVE_PHONE = "9998812346"  # seeded but is_active=False
RANDOM_PHONE = "9111100022"   # never whitelisted

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


# ---------------- seed ----------------
STAFF_ID = PREFIX + str(uuid.uuid4())[:8]
BILL_ID = PREFIX + "bill_" + str(uuid.uuid4())[:8]
INC_REG_ID = PREFIX + "reg_" + str(uuid.uuid4())[:8]
INC_BILL_ID = PREFIX + "bil_" + str(uuid.uuid4())[:8]


@pytest.fixture(scope="module", autouse=True)
def seed():
    now = datetime.now(timezone.utc).isoformat()
    _run(server.db.retailer_managers.insert_many([
        {"id": PREFIX + "mgr1", "name": PREFIX + "Manager One", "phone": WL_PHONE,
         "brands": [PREFIX + "Brand"], "is_active": True, "created_at": now},
        {"id": PREFIX + "mgr2", "name": PREFIX + "Manager Two", "phone": INACTIVE_PHONE,
         "brands": [PREFIX + "Brand"], "is_active": False, "created_at": now},
    ]))
    _run(server.db.retail_staff.insert_one({
        "id": STAFF_ID, "name": PREFIX + "Staff", "phone": "9998812399",
        "staff_code": "TI72-0001", "brand_name": PREFIX + "Brand",
        "brand_category": "Fashion", "store_location": "L1-99", "is_active": True,
        "created_at": now,
    }))
    _run(server.db.bills.insert_one({
        "id": BILL_ID, "amount": 4321.0, "store_name": PREFIX + "Store",
        "status": "approved", "bill_no": "TI72BILL001", "created_at": now,
    }))
    _run(server.db.staff_incentives.insert_many([
        {"id": INC_REG_ID, "type": "registration", "status": "redeemable", "amount": 10.0,
         "customer_phone": "9000000072", "staff_id": STAFF_ID, "staff_code": "TI72-0001",
         "created_at": now},
        {"id": INC_BILL_ID, "type": "bill_upload", "status": "pending_verification", "amount": 25.0,
         "customer_phone": "9000000072", "staff_id": STAFF_ID, "staff_code": "TI72-0001",
         "bill_id": BILL_ID, "bill_value": 4321.0, "created_at": now},
    ]))
    yield
    _run(server.db.retailer_managers.delete_many({"id": {"$regex": f"^{PREFIX}"}}))
    _run(server.db.retail_staff.delete_many({"id": {"$regex": f"^{PREFIX}"}}))
    _run(server.db.bills.delete_many({"id": {"$regex": f"^{PREFIX}"}}))
    _run(server.db.staff_incentives.delete_many({"id": {"$regex": f"^{PREFIX}"}}))


class _DBProxy:
    """Motor's db.<collection> returns a NEW Collection object on every attribute
    access, so patching an instance attribute has no effect inside the endpoint.
    This proxy swaps whole collections for fault injection instead."""

    def __init__(self, real, overrides):
        self._real = real
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._real, name)


class _ColProxy:
    def __init__(self, real, overrides):
        self._real = real
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._real, name)


def _tail_logs(nbytes=200000):
    out = ""
    for p in BACKEND_LOGS:
        try:
            with open(p, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - nbytes))
                out += f.read().decode("utf-8", "replace")
        except FileNotFoundError:
            pass
    return out


# ==================== POINT 11: diagnose-otp ====================
class TestPoint11Diagnose:
    URL = f"{BASE_URL}/api/admin/staff/retailer/diagnose-otp"

    def test_requires_auth(self):
        r = requests.get(self.URL, params={"phone": RANDOM_PHONE}, timeout=60)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text[:200]}"

    def test_whitelisted_active(self, auth_headers):
        r = requests.get(self.URL, params={"phone": WL_PHONE}, headers=auth_headers, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("phone", "is_whitelisted", "is_active", "manager_name",
                  "otp_send_bound", "otp_channel", "explanation"):
            assert k in d, f"missing key {k} in {d}"
        assert d["phone"] == WL_PHONE
        assert d["is_whitelisted"] is True
        assert d["is_active"] is True
        assert d["manager_name"] == PREFIX + "Manager One"
        assert d["otp_send_bound"] is True, "OTP dispatcher not bound (bind_staff_db missing?)"
        assert isinstance(d["otp_channel"], str) and d["otp_channel"]
        assert "user will receive OTP" in d["explanation"], d["explanation"]

    def test_random_phone_warns(self, auth_headers):
        r = requests.get(self.URL, params={"phone": RANDOM_PHONE}, headers=auth_headers, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["is_whitelisted"] is False
        assert d["is_active"] is False
        assert d["manager_name"] is None
        assert "silently" in d["explanation"].lower(), d["explanation"]

    def test_inactive_manager(self, auth_headers):
        r = requests.get(self.URL, params={"phone": INACTIVE_PHONE}, headers=auth_headers, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["is_whitelisted"] is True
        assert d["is_active"] is False, f"inactive manager reported active: {d}"
        assert "user will receive OTP" not in d["explanation"], d["explanation"]

    def test_phone_normalisation(self, auth_headers):
        r = requests.get(self.URL, params={"phone": f"+91{WL_PHONE}"}, headers=auth_headers, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["phone"] == WL_PHONE, d
        assert d["is_whitelisted"] is True


# ==================== POINT 11: send-otp ====================
class TestPoint11SendOTP:
    URL = f"{BASE_URL}/api/staff/retailer/auth/send-otp"

    def test_non_whitelisted_neutral_and_warn_log(self):
        r = requests.post(self.URL, json={"phone": RANDOM_PHONE}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("success") is True
        assert d.get("message") == "OTP sent if number is registered", d
        assert "delivery" not in d, "leaks delivery info for non-whitelisted phone"
        time.sleep(1)
        logs = _tail_logs()
        assert "Retailer OTP requested by non-whitelisted / inactive phone" in logs, \
            "WARN log line for non-whitelisted retailer OTP not found in backend logs"
        assert RANDOM_PHONE in logs

    def test_whitelisted_returns_delivery(self):
        r = requests.post(self.URL, json={"phone": WL_PHONE}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("success") is True
        assert d.get("message") == "OTP sent", d
        assert isinstance(d.get("delivery"), dict), d
        assert set(["whatsapp", "sms", "success"]).issubset(set(d["delivery"].keys())), d["delivery"]

    def test_inactive_manager_neutral(self):
        r = requests.post(self.URL, json={"phone": INACTIVE_PHONE}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("message") == "OTP sent if number is registered"

    def test_send_otp_binding_missing_logs_error(self):
        """If _send_sms_otp is unbound the endpoint must log loudly (Point 11)."""
        payload = staff_mod.StaffOTPRequest(phone=WL_PHONE)
        with mock.patch.object(staff_mod, "_send_sms_otp", None), \
             mock.patch.object(staff_mod.logger, "error") as m_err:
            res = _run(staff_mod.retailer_send_otp(payload))
        assert res["success"] is True
        msgs = " ".join(str(c.args[0]) for c in m_err.call_args_list)
        assert "_send_sms_otp binding is None" in msgs, msgs


# ==================== POINT 15: incentive report ====================
class TestPoint15Report:
    URL = f"{BASE_URL}/api/admin/staff/incentives/report"

    def test_report_ok_and_fast(self, auth_headers):
        t0 = time.time()
        r = requests.get(self.URL, params={"limit": 100}, headers=auth_headers, timeout=60)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "rows" in d and "summary" in d
        s = d["summary"]
        for k in ("total", "registration_count", "bill_upload_count", "total_amount", "redeemable_amount"):
            assert k in s, s
        assert s["total"] == len(d["rows"])
        assert len(d["rows"]) <= 100
        assert all("_id" not in row for row in d["rows"]), "_id leaked in report rows"
        print(f"report limit=100 elapsed={elapsed:.2f}s")
        assert elapsed < 2.0, f"report took {elapsed:.2f}s (>2s) for small load"

    def test_report_requires_auth(self):
        r = requests.get(self.URL, timeout=60)
        assert r.status_code in (401, 403), r.status_code

    def test_filter_registration(self, auth_headers):
        r = requests.get(self.URL, params={"incentive_type": "registration", "staff_id": STAFF_ID},
                         headers=auth_headers, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["summary"]["bill_upload_count"] == 0
        ids = [x["id"] for x in d["rows"]]
        assert INC_REG_ID in ids, ids
        assert INC_BILL_ID not in ids
        row = next(x for x in d["rows"] if x["id"] == INC_REG_ID)
        assert row["type"] == "registration"
        assert row["staff_name"] == PREFIX + "Staff"
        assert row["staff_code"] == "TI72-0001"
        assert row["staff_brand"] == PREFIX + "Brand"
        assert row["staff_store"] == "L1-99"
        assert row["customer_phone"] == "9000000072"

    def test_filter_bill_upload_with_enrichment(self, auth_headers):
        r = requests.get(self.URL, params={"incentive_type": "bill_upload", "staff_id": STAFF_ID},
                         headers=auth_headers, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["summary"]["registration_count"] == 0
        row = next((x for x in d["rows"] if x["id"] == INC_BILL_ID), None)
        assert row is not None, d["rows"]
        assert row["bill_id"] == BILL_ID
        assert row["bill_amount"] == 4321.0
        assert row["bill_store"] == PREFIX + "Store"
        assert row["bill_status"] == "approved"
        assert row["bill_no"] == "TI72BILL001"

    def test_brand_filter(self, auth_headers):
        r = requests.get(self.URL, params={"brand": PREFIX + "Brand"}, headers=auth_headers, timeout=60)
        assert r.status_code == 200, r.text[:300]
        ids = [x["id"] for x in r.json()["rows"]]
        assert INC_REG_ID in ids and INC_BILL_ID in ids, ids

    def test_max_time_ms_applied_on_primary_cursor(self):
        """Point 15: primary find cursor must be bounded with max_time_ms(15000)."""
        calls = {}
        real_col = staff_mod._db.staff_incentives

        class Cur:
            def __init__(self, inner):
                self.inner = inner

            def sort(self, *a, **k):
                self.inner = self.inner.sort(*a, **k)
                return self

            def limit(self, *a, **k):
                self.inner = self.inner.limit(*a, **k)
                return self

            def max_time_ms(self, ms):
                calls["ms"] = ms
                return self

            def __aiter__(self):
                return self.inner.__aiter__()

        fake_col = _ColProxy(real_col, {"find": lambda *a, **k: Cur(real_col.find(*a, **k))})
        proxy = _DBProxy(staff_mod._db, {"staff_incentives": fake_col})
        with mock.patch.object(staff_mod, "_db", proxy):
            res = _run(staff_mod.admin_incentive_report(staff_id=STAFF_ID, limit=10, auth={"role": "admin"}))
        assert calls.get("ms") == 15000, f"max_time_ms not applied: {calls}"
        assert res["summary"]["total"] == 2, res["summary"]

    @staticmethod
    def _boom_db(message):
        class BoomCur:
            def sort(self, *a, **k):
                return self

            def limit(self, *a, **k):
                return self

            def max_time_ms(self, *a, **k):
                return self

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise Exception(message)

        fake_col = _ColProxy(staff_mod._db.staff_incentives, {"find": lambda *a, **k: BoomCur()})
        return _DBProxy(staff_mod._db, {"staff_incentives": fake_col})

    def test_transient_db_error_maps_to_503(self):
        with mock.patch.object(staff_mod, "_db", self._boom_db("operation exceeded time limit")):
            with pytest.raises(HTTPException) as ei:
                _run(staff_mod.admin_incentive_report(limit=10, auth={"role": "admin"}))
        assert ei.value.status_code == 503, f"expected 503, got {ei.value.status_code}: {ei.value.detail}"
        detail = str(ei.value.detail).lower()
        assert "retry" in detail and ("narrow" in detail or "filter" in detail), ei.value.detail

    def test_timed_out_error_maps_to_503(self):
        with mock.patch.object(staff_mod, "_db", self._boom_db("cursor timed out on server")):
            with pytest.raises(HTTPException) as ei:
                _run(staff_mod.admin_incentive_report(limit=10, auth={"role": "admin"}))
        assert ei.value.status_code == 503, ei.value.status_code

    def test_non_transient_error_maps_to_500(self):
        with mock.patch.object(staff_mod, "_db", self._boom_db("some unrelated failure")):
            with pytest.raises(HTTPException) as ei:
                _run(staff_mod.admin_incentive_report(limit=10, auth={"role": "admin"}))
        assert ei.value.status_code == 500, ei.value.status_code

    def test_per_row_lookup_failure_does_not_500(self):
        """A bad retail_staff lookup must degrade gracefully, not 500."""
        async def boom(*a, **k):
            raise Exception("staff lookup exploded")

        fake_staff = _ColProxy(staff_mod._db.retail_staff, {"find_one": boom})
        proxy = _DBProxy(staff_mod._db, {"retail_staff": fake_staff})
        with mock.patch.object(staff_mod, "_db", proxy):
            res = _run(staff_mod.admin_incentive_report(staff_id=STAFF_ID, limit=10, auth={"role": "admin"}))
        assert res["summary"]["total"] == 2
        assert all(r["staff_name"] is None for r in res["rows"]), res["rows"]

    def test_enrichment_lookups_bounded(self):
        """Point 15: per-row retail_staff/bills lookups must pass max_time_ms=5000."""
        seen = {"staff": None, "bills": None}
        real_staff_col = staff_mod._db.retail_staff
        real_bills_col = staff_mod._db.bills

        async def staff_find_one(*a, **k):
            seen["staff"] = k.get("max_time_ms")
            k.pop("max_time_ms", None)
            return await real_staff_col.find_one(*a, **k)

        async def bills_find_one(*a, **k):
            seen["bills"] = k.get("max_time_ms")
            k.pop("max_time_ms", None)
            return await real_bills_col.find_one(*a, **k)

        proxy = _DBProxy(staff_mod._db, {
            "retail_staff": _ColProxy(real_staff_col, {"find_one": staff_find_one}),
            "bills": _ColProxy(real_bills_col, {"find_one": bills_find_one}),
        })
        with mock.patch.object(staff_mod, "_db", proxy):
            _run(staff_mod.admin_incentive_report(staff_id=STAFF_ID, limit=10, auth={"role": "admin"}))
        assert seen["staff"] == 5000, seen
        assert seen["bills"] == 5000, seen

    def test_report_csv_still_works(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/admin/staff/incentives/report.csv",
                         params={"staff_id": STAFF_ID}, headers=auth_headers, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert "TI72-0001" in r.text, r.text[:500]


# ==================== POINT 15: synthetic large dataset ====================
class TestPoint15LargeLoad:
    URL = f"{BASE_URL}/api/admin/staff/incentives/report"
    N = 1200

    @pytest.fixture(scope="class", autouse=True)
    def bulk(self):
        now = datetime.now(timezone.utc).isoformat()
        docs = [{
            "id": f"{PREFIX}bulk_{i}", "type": "registration" if i % 2 else "bill_upload",
            "status": "redeemable", "amount": 10.0, "customer_phone": "9000000073",
            "staff_id": STAFF_ID, "bill_id": BILL_ID if i % 2 == 0 else None,
            "bill_value": 100.0, "created_at": now,
        } for i in range(self.N)]
        _run(server.db.staff_incentives.insert_many(docs))
        yield
        _run(server.db.staff_incentives.delete_many({"id": {"$regex": f"^{PREFIX}bulk_"}}))

    def test_large_dataset_report(self, auth_headers):
        t0 = time.time()
        r = requests.get(self.URL, params={"limit": 2000, "staff_id": STAFF_ID},
                         headers=auth_headers, timeout=90)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        print(f"large report rows={len(d['rows'])} elapsed={elapsed:.2f}s")
        assert len(d["rows"]) == self.N + 2, len(d["rows"])
        assert d["summary"]["total"] == self.N + 2
        assert elapsed < 15.0, f"large report took {elapsed:.2f}s"


# ==================== SECURITY: admin gate scope ====================
class TestAdminGateScope:
    """Found in iter 72 (fixed in iter 73): _verify_admin used to only reject
    role == 'retail_staff', so a 30-day retailer_manager token passed every
    /api/admin/staff/* endpoint (diagnose-otp, incentives report,
    retailer-managers CRUD). Now an allowlist of admin roles is enforced, so the
    retailer token must get 403 — assertion is live (xfail removed)."""

    def test_retailer_token_cannot_reach_admin_endpoints(self):
        phone = "9998819999"
        _run(server.db.retailer_managers.insert_one({
            "id": PREFIX + "priv", "name": PREFIX + "Priv", "phone": phone,
            "brands": ["X"], "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }))
        try:
            requests.post(f"{BASE_URL}/api/staff/retailer/auth/send-otp", json={"phone": phone}, timeout=90)
            r = requests.post(f"{BASE_URL}/api/staff/retailer/auth/verify-otp",
                              json={"phone": phone, "otp": "1234"}, timeout=60)
            assert r.status_code == 200, r.text[:200]
            tok = r.json()["token"]
            h = {"Authorization": f"Bearer {tok}"}
            for path in ("/api/admin/staff/retailer/diagnose-otp?phone=9876543210",
                         "/api/admin/staff/incentives/report?limit=5",
                         "/api/admin/staff/retailer-managers"):
                rr = requests.get(BASE_URL + path, headers=h, timeout=60)
                assert rr.status_code == 403, f"{path} allowed retailer token: {rr.status_code}"
        finally:
            _run(server.db.retailer_managers.delete_many({"id": PREFIX + "priv"}))
