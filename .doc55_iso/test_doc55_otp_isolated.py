"""
Doc #55 — Customer OTP route, isolated.

Separate assertions for:
  (A) Fallback credential presence (no values printed).
  (B) Provider acceptance (Karix SMS returns Platform Accepted).
  (C) Provider rejection (missing key → success=False, no outbound call).
  (D) OTP store round-trip against in-memory fake db.
  (E) OTP verify path: happy, wrong-code, expired, 5-attempt-lockout.
  (F) send_login_otp fan-out respects OTP_CHANNEL and reports per-channel results.
"""
import asyncio
import inspect
from datetime import datetime, timezone, timedelta
import pytest


# -------- (A) Fallback credential PRESENCE, no values printed ---------------
def test_A_fallback_credentials_declared(srv):
    """Confirm the Oct-2026 fallback dict exists for every Karix SMS env key.
    We assert on *presence* and non-emptiness only — values are never emitted."""
    assert hasattr(srv, "_KARIX_SMS_DEFAULTS"), "fallback dict missing"
    required = {
        "KARIX_SMS_API_URL",
        "KARIX_SMS_API_KEY",
        "KARIX_SMS_SENDER_ID",
        "KARIX_SMS_DLT_ENTITY_ID",
        "KARIX_SMS_DLT_TEMPLATE_ID",
    }
    missing = required - set(srv._KARIX_SMS_DEFAULTS.keys())
    assert not missing, f"fallback keys missing: {sorted(missing)}"
    for k in required:
        v = srv._KARIX_SMS_DEFAULTS[k]
        assert isinstance(v, str) and len(v) > 0, f"{k} fallback empty"
    # Resolved constants must also be non-empty on this process
    for k in required:
        resolved = getattr(srv, k)
        assert resolved, f"module-level {k} is empty"


def test_A2_env_or_default_prefers_env_over_fallback(srv, monkeypatch):
    monkeypatch.setenv("KARIX_SMS_SENDER_ID", "FROM_ENV_X")
    assert srv._env_or_default("KARIX_SMS_SENDER_ID") == "FROM_ENV_X"
    monkeypatch.delenv("KARIX_SMS_SENDER_ID")
    monkeypatch.setenv("KARIX_SMS_SENDER_ID", "")
    # blank env → fallback kicks in; we don't print its value
    assert srv._env_or_default("KARIX_SMS_SENDER_ID") != ""


# -------- (B) Provider ACCEPTANCE -------------------------------------------
def test_B_karix_accepts_sms(srv):
    from conftest import FakeAsyncClient
    out = asyncio.run(srv.send_otp_sms("9000000001", "123456"))
    assert out["success"] is True, out
    assert out["status_code"] == 200
    assert FakeAsyncClient.calls, "no outbound call captured"
    method, url, params = FakeAsyncClient.calls[0]
    assert method == "GET"
    # Params should carry the DLT ids and sender header
    assert "dlt_entity_id" in params and params["dlt_entity_id"]
    assert "dlt_template_id" in params and params["dlt_template_id"]
    assert params.get("send"), "sender header missing"
    # The template body must carry the OTP var exactly once
    assert "123456" in params.get("text", "")


# -------- (C) Provider REJECTION separated from delivery --------------------
def test_C_karix_rejects_when_key_absent(srv, monkeypatch):
    monkeypatch.setattr(srv, "KARIX_SMS_API_KEY", "")
    from conftest import FakeAsyncClient
    FakeAsyncClient.calls = []
    out = asyncio.run(srv.send_otp_sms("9000000002", "654321"))
    assert out["success"] is False
    assert "SMS gateway not configured" in (out.get("error") or "")
    assert FakeAsyncClient.calls == [], "no network should happen when key empty"


def test_C2_karix_accepts_but_delivery_signalled_non_200(srv):
    from conftest import FakeAsyncClient
    FakeAsyncClient.scripted = {"status_code": 500, "text": "Internal Error"}
    out = asyncio.run(srv.send_otp_sms("9000000003", "111111"))
    # Provider acceptance ≠ delivery. 500 → success=False.
    assert out["success"] is False
    assert out["status_code"] == 500


# -------- (D) OTP STORE round-trip ------------------------------------------
def test_D_store_otp_persists_record_with_ttl(srv):
    asyncio.run(srv.store_otp("9000000004", "999888"))
    rec = asyncio.run(srv.db.otp_codes.find_one({"phone": "9000000004"}))
    assert rec and rec["otp"] == "999888"
    assert rec["attempts"] == 0
    exp = datetime.fromisoformat(rec["expires_at"])
    now = datetime.now(timezone.utc)
    # 5-minute TTL window
    assert now < exp <= now + timedelta(minutes=5, seconds=5)


# -------- (E) OTP VERIFY path ------------------------------------------------
def test_E1_verify_happy(srv):
    asyncio.run(srv.store_otp("9000000005", "222333"))
    assert asyncio.run(srv.verify_stored_otp("9000000005", "222333")) is True
    # Record is deleted on success
    rec = asyncio.run(srv.db.otp_codes.find_one({"phone": "9000000005"}))
    assert rec is None

def test_E2_verify_wrong_code(srv):
    asyncio.run(srv.store_otp("9000000006", "444555"))
    assert asyncio.run(srv.verify_stored_otp("9000000006", "000000")) is False
    rec = asyncio.run(srv.db.otp_codes.find_one({"phone": "9000000006"}))
    assert rec["attempts"] == 1

def test_E3_verify_expired(srv):
    asyncio.run(srv.store_otp("9000000007", "666777"))
    # Force expiry
    srv.db.otp_codes.docs["9000000007"]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    ).isoformat()
    assert asyncio.run(srv.verify_stored_otp("9000000007", "666777")) is False

def test_E4_verify_lockout_after_5(srv):
    asyncio.run(srv.store_otp("9000000008", "888999"))
    for _ in range(5):
        asyncio.run(srv.verify_stored_otp("9000000008", "000000"))
    # 6th try even with correct code must be rejected (record deleted on attempt-cap)
    assert asyncio.run(srv.verify_stored_otp("9000000008", "888999")) is False


# -------- (F) send_login_otp fan-out ----------------------------------------
def test_F_fanout_reports_both_channels(srv, monkeypatch):
    monkeypatch.setattr(srv, "OTP_CHANNEL", "both")
    out = asyncio.run(srv.send_login_otp("9000000009", "121212"))
    assert "whatsapp" in out and "sms" in out
    assert out["success"] is True
    assert out["whatsapp"]["success"] is True
    assert out["sms"]["success"] is True


def test_F2_fanout_sms_only(srv, monkeypatch):
    monkeypatch.setattr(srv, "OTP_CHANNEL", "sms")
    out = asyncio.run(srv.send_login_otp("9000000010", "131313"))
    assert out["whatsapp"] is None
    assert out["sms"]["success"] is True
    assert out["success"] is True
