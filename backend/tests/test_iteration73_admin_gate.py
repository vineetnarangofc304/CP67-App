"""Iteration 73 — verification of iter-72 findings fixes in /app/backend/routes/staff.py

Covers:
  * _verify_admin allowlist (privilege-escalation fix): retailer_manager / consumer /
    retail_staff / missing-role tokens must get 403 on every /api/admin/staff/* endpoint,
    while admin / super_admin / mall_admin tokens succeed.
  * admin_incentive_report `limit` bounds: Query(1000, ge=1, le=5000).
  * transient-error classification via isinstance() against pymongo error classes
    (AutoReconnect whose message has no 'timed out'/'time limit' substring → 503).
"""
import asyncio
import os
import re
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

import jwt
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
PREFIX = "TEST_ITER73_"
JWT_SECRET = staff_mod.JWT_SECRET

ADMIN_PATHS = [
    "/api/admin/staff/retailer/diagnose-otp?phone=9876543210",
    "/api/admin/staff/incentives/report?limit=5",
    "/api/admin/staff/retailer-managers",
]

try:
    _LOOP = asyncio.get_event_loop_policy().get_event_loop()
    if _LOOP.is_closed():
        raise RuntimeError
except RuntimeError:
    _LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _run(coro):
    return _LOOP.run_until_complete(coro)


def _mint(claims):
    body = {"exp": datetime.now(timezone.utc) + timedelta(hours=1), "sub": PREFIX + "sub"}
    body.update(claims)
    return jwt.encode(body, JWT_SECRET, algorithm="HS256")


def _admin_creds():
    content = CREDS_PATH.read_text(encoding="utf-8")
    block = content.split("## Admin Dashboard")[1]
    u = re.search(r"Username:\s*`([^`]+)`", block).group(1)
    p = re.search(r"Password:\s*`([^`]+)`", block).group(1)
    return u, p


@pytest.fixture(scope="module")
def admin_headers():
    u, p = _admin_creds()
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"username": u, "password": p}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, r.json()
    return {"Authorization": f"Bearer {tok}"}


# ==================== PRIVESC: allowlist rejects non-admin roles ====================
class TestAdminAllowlistRejects:
    RETAILER_PHONE = "9998873001"

    @pytest.fixture(scope="class", autouse=True)
    def seed(self):
        _run(server.db.retailer_managers.insert_one({
            "id": PREFIX + "mgr", "name": PREFIX + "Mgr", "phone": self.RETAILER_PHONE,
            "brands": [PREFIX + "Brand"], "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }))
        yield
        _run(server.db.retailer_managers.delete_many({"id": {"$regex": f"^{PREFIX}"}}))

    def test_real_retailer_manager_token_rejected(self):
        """Mint a real retailer_manager JWT through the OTP flow and assert 403."""
        requests.post(f"{BASE_URL}/api/staff/retailer/auth/send-otp",
                      json={"phone": self.RETAILER_PHONE}, timeout=120)
        r = requests.post(f"{BASE_URL}/api/staff/retailer/auth/verify-otp",
                          json={"phone": self.RETAILER_PHONE, "otp": "1234"}, timeout=60)
        assert r.status_code == 200, f"dev-bypass OTP login failed: {r.status_code} {r.text[:200]}"
        tok = r.json()["token"]
        claims = jwt.decode(tok, JWT_SECRET, algorithms=["HS256"])
        assert claims.get("role") == "retailer_manager", claims
        h = {"Authorization": f"Bearer {tok}"}
        for path in ADMIN_PATHS:
            rr = requests.get(BASE_URL + path, headers=h, timeout=60)
            assert rr.status_code == 403, f"{path} allowed retailer token: {rr.status_code} {rr.text[:200]}"
            assert "admin only" in rr.text.lower(), rr.text[:200]

    @pytest.mark.parametrize("claims,label", [
        ({"role": "retailer_manager", "phone": "9998873001"}, "retailer_manager"),
        ({"role": "consumer"}, "consumer"),
        ({"role": "retail_staff"}, "retail_staff"),
        ({"role": ""}, "empty-role"),
        ({}, "no-role"),
        ({"role": "Admin"}, "case-mismatch-Admin"),
        ({"role": "admin_viewer"}, "prefix-lookalike"),
    ])
    def test_non_admin_roles_rejected(self, claims, label):
        h = {"Authorization": f"Bearer {_mint(claims)}"}
        for path in ADMIN_PATHS:
            rr = requests.get(BASE_URL + path, headers=h, timeout=60)
            assert rr.status_code == 403, f"[{label}] {path} -> {rr.status_code}: {rr.text[:200]}"

    def test_invalid_signature_rejected(self):
        bad = jwt.encode({"role": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                         "wrong-secret", algorithm="HS256")
        rr = requests.get(BASE_URL + ADMIN_PATHS[0], headers={"Authorization": f"Bearer {bad}"}, timeout=60)
        assert rr.status_code == 401, rr.status_code

    def test_expired_admin_token_rejected(self):
        exp = jwt.encode({"role": "admin", "exp": datetime.now(timezone.utc) - timedelta(minutes=5)},
                         JWT_SECRET, algorithm="HS256")
        rr = requests.get(BASE_URL + ADMIN_PATHS[0], headers={"Authorization": f"Bearer {exp}"}, timeout=60)
        assert rr.status_code == 401, rr.status_code

    def test_no_token_rejected(self):
        for path in ADMIN_PATHS:
            rr = requests.get(BASE_URL + path, timeout=60)
            assert rr.status_code in (401, 403), f"{path} -> {rr.status_code}"


# ==================== PRIVESC: allowlist accepts admin roles ====================
class TestAdminAllowlistAccepts:
    def test_real_admin_login_token_ok(self, admin_headers):
        for path in ADMIN_PATHS:
            rr = requests.get(BASE_URL + path, headers=admin_headers, timeout=60)
            assert rr.status_code == 200, f"{path} -> {rr.status_code}: {rr.text[:200]}"

    @pytest.mark.parametrize("role", ["admin", "super_admin", "mall_admin"])
    def test_allowlisted_roles_ok(self, role):
        h = {"Authorization": f"Bearer {_mint({'role': role})}"}
        for path in ADMIN_PATHS:
            rr = requests.get(BASE_URL + path, headers=h, timeout=60)
            assert rr.status_code == 200, f"[{role}] {path} -> {rr.status_code}: {rr.text[:200]}"

    def test_type_claim_only_admin_accepted(self):
        """_verify_admin falls back to the 'type' claim; documents current semantics."""
        h = {"Authorization": f"Bearer {_mint({'type': 'admin'})}"}
        rr = requests.get(BASE_URL + ADMIN_PATHS[0], headers=h, timeout=60)
        assert rr.status_code == 200, f"type-claim admin -> {rr.status_code}: {rr.text[:200]}"

    def test_role_wins_over_type(self):
        """role='consumer' + type='admin' must still be rejected (role read first)."""
        h = {"Authorization": f"Bearer {_mint({'role': 'consumer', 'type': 'admin'})}"}
        rr = requests.get(BASE_URL + ADMIN_PATHS[0], headers=h, timeout=60)
        assert rr.status_code == 403, rr.status_code


# ==================== diagnose-otp projection ====================
class TestDiagnoseProjection:
    def test_no_id_or_email_leak(self, admin_headers):
        phone = "9998873002"
        _run(server.db.retailer_managers.insert_one({
            "id": PREFIX + "proj", "name": PREFIX + "Proj", "phone": phone,
            "email": "leak@example.com", "brands": ["B"], "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }))
        try:
            r = requests.get(f"{BASE_URL}/api/admin/staff/retailer/diagnose-otp",
                             params={"phone": phone}, headers=admin_headers, timeout=60)
            assert r.status_code == 200, r.text[:300]
            d = r.json()
            assert d["is_whitelisted"] is True and d["is_active"] is True, d
            assert "_id" not in str(d), d
            assert "leak@example.com" not in str(d), d
        finally:
            _run(server.db.retailer_managers.delete_many({"id": PREFIX + "proj"}))


# ==================== limit bounds ====================
class TestReportLimitBounds:
    URL = f"{BASE_URL}/api/admin/staff/incentives/report"

    @pytest.mark.parametrize("limit,expected", [
        (10000, 422), (5001, 422), (0, 422), (-1, 422), (5000, 200), (1, 200),
    ])
    def test_limit_bounds(self, admin_headers, limit, expected):
        r = requests.get(self.URL, params={"limit": limit}, headers=admin_headers, timeout=90)
        assert r.status_code == expected, f"limit={limit} -> {r.status_code}: {r.text[:200]}"

    def test_default_limit_ok(self, admin_headers):
        r = requests.get(self.URL, headers=admin_headers, timeout=90)
        assert r.status_code == 200, r.text[:200]
        assert len(r.json()["rows"]) <= 1000


# ==================== 503 classification via isinstance ====================
class _ColProxy:
    def __init__(self, real, overrides):
        self._real = real
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._real, name)


class _DBProxy(_ColProxy):
    pass


def _boom_db(exc):
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
            raise exc

    fake_col = _ColProxy(staff_mod._db.staff_incentives, {"find": lambda *a, **k: BoomCur()})
    return _DBProxy(staff_mod._db, {"staff_incentives": fake_col})


class TestTransientClassification:
    @pytest.mark.parametrize("exc_name,message", [
        ("AutoReconnect", "connection pool paused"),
        ("NetworkTimeout", "socket hiccup"),
        ("ServerSelectionTimeoutError", "no primary available"),
        ("ExecutionTimeout", "operation aborted"),
    ])
    def test_pymongo_transient_maps_to_503(self, exc_name, message):
        import pymongo.errors as pe
        exc = getattr(pe, exc_name)(message)
        assert "timed out" not in str(exc).lower() and "time limit" not in str(exc).lower(), \
            "message must not match the substring fallback for this test to be meaningful"
        with mock.patch.object(staff_mod, "_db", _boom_db(exc)):
            with pytest.raises(HTTPException) as ei:
                _run(staff_mod.admin_incentive_report(limit=10, auth={"role": "admin"}))
        assert ei.value.status_code == 503, f"{exc_name} -> {ei.value.status_code}: {ei.value.detail}"

    def test_asyncio_timeout_maps_to_503(self):
        with mock.patch.object(staff_mod, "_db", _boom_db(asyncio.TimeoutError())):
            with pytest.raises(HTTPException) as ei:
                _run(staff_mod.admin_incentive_report(limit=10, auth={"role": "admin"}))
        assert ei.value.status_code == 503, ei.value.status_code

    def test_substring_fallback_still_503(self):
        with mock.patch.object(staff_mod, "_db", _boom_db(Exception("operation exceeded time limit"))):
            with pytest.raises(HTTPException) as ei:
                _run(staff_mod.admin_incentive_report(limit=10, auth={"role": "admin"}))
        assert ei.value.status_code == 503, ei.value.status_code

    def test_generic_error_still_500(self):
        with mock.patch.object(staff_mod, "_db", _boom_db(Exception("totally unrelated blowup"))):
            with pytest.raises(HTTPException) as ei:
                _run(staff_mod.admin_incentive_report(limit=10, auth={"role": "admin"}))
        assert ei.value.status_code == 500, ei.value.status_code

    def test_max_time_ms_unavailable_logs_warning(self):
        """Iter-73: cursor without max_time_ms must log a warning, not swallow silently."""
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

            @property
            def max_time_ms(self):
                raise AttributeError("no max_time_ms")

            def __aiter__(self):
                return self.inner.__aiter__()

        fake_col = _ColProxy(real_col, {"find": lambda *a, **k: Cur(real_col.find(*a, **k))})
        proxy = _DBProxy(staff_mod._db, {"staff_incentives": fake_col})
        with mock.patch.object(staff_mod, "_db", proxy), \
             mock.patch.object(staff_mod.logger, "warning") as m_warn:
            res = _run(staff_mod.admin_incentive_report(limit=5, auth={"role": "admin"}))
        assert "rows" in res
        msgs = " ".join(str(c.args[0]) for c in m_warn.call_args_list)
        assert "max_time_ms unavailable" in msgs, msgs


# ==================== light cross-router smoke (iter 70/71) ====================
class TestCrossRouterSmoke:
    def test_brands_list_ok(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/brands", headers=admin_headers, timeout=60)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"

    def test_staff_list_ok(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/staff", headers=admin_headers, timeout=60)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"

    def test_staff_list_rejects_retailer_role(self):
        h = {"Authorization": f"Bearer {_mint({'role': 'retailer_manager'})}"}
        r = requests.get(f"{BASE_URL}/api/admin/staff", headers=h, timeout=60)
        assert r.status_code == 403, f"{r.status_code}: {r.text[:200]}"

    def test_leaderboard_and_metrics_gated(self):
        h = {"Authorization": f"Bearer {_mint({'role': 'retailer_manager'})}"}
        for p in ("/api/admin/staff/leaderboard", "/api/admin/staff/metrics/overview",
                  "/api/admin/staff/redemptions", "/api/admin/staff/config/current"):
            r = requests.get(BASE_URL + p, headers=h, timeout=60)
            assert r.status_code == 403, f"{p} -> {r.status_code}: {r.text[:150]}"
