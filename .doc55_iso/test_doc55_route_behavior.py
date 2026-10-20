"""
Doc #55 Fix 1 + Fix 2 — assert the new POST /api/consumer/auth/send-otp contract.

Isolated: uses FastAPI TestClient against the consumer_router, with send_login_otp
and store_otp monkey-patched. No DB connection, no provider traffic.
"""
import asyncio
import importlib
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client_and_srv(srv, monkeypatch):
    # Import the router module fresh and wire its init with the fake db.
    consumer = importlib.import_module("routes.consumer")

    # Replace the TagnPay client with a no-op so background sync doesn't dial out.
    class _FakeTag:
        async def send_login_otp(self, p): return {"success": True}
        async def register_customer(self, *_a, **_kw): return {"success": True}

    consumer.init_consumer_routes(
        db=srv.db,
        tagnpay_client=_FakeTag(),
        jwt_secret="test-secret",
        jwt_algorithm="HS256",
        emergent_key="",
        backend_url="",
    )

    # blocked_phones fake
    class _Blocked:
        async def find_one(self, *_a, **_kw): return None
    srv.db.blocked_phones = _Blocked()

    app = FastAPI()
    app.include_router(consumer.consumer_router)
    return TestClient(app), srv


def test_send_otp_success_returns_truthful_delivery(client_and_srv, monkeypatch):
    client, srv = client_and_srv
    # Patch send_login_otp to simulate SMS acceptance only.
    async def _fake_fanout(p10, otp):
        return {"whatsapp": {"success": False}, "sms": {"success": True, "status_code": 200}, "success": True}
    monkeypatch.setattr(srv, "send_login_otp", _fake_fanout)
    r = client.post("/api/consumer/auth/send-otp", json={"phone": "9000000020"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["success"] is True
    assert data["delivery"] == {"whatsapp": "rejected", "sms": "accepted"}


def test_send_otp_all_channels_fail_returns_503(client_and_srv, monkeypatch):
    client, srv = client_and_srv
    async def _fake_fanout(p10, otp):
        return {"whatsapp": {"success": False, "error": "x"},
                "sms": {"success": False, "error": "SMS gateway not configured"},
                "success": False}
    monkeypatch.setattr(srv, "send_login_otp", _fake_fanout)
    r = client.post("/api/consumer/auth/send-otp", json={"phone": "9000000021"})
    assert r.status_code == 503, r.text
    body = r.json()
    assert "detail" in body
    assert "try again" in body["detail"].lower()


def test_reviewer_bypass_still_short_circuits(client_and_srv, monkeypatch):
    """App Store reviewer phone must keep working without touching any gateway."""
    client, srv = client_and_srv
    called = {"fanout": 0}
    async def _fake_fanout(*_a, **_kw):
        called["fanout"] += 1
        return {"whatsapp": None, "sms": None, "success": False}
    monkeypatch.setattr(srv, "send_login_otp", _fake_fanout)
    r = client.post("/api/consumer/auth/send-otp", json={"phone": "9999999999"})
    assert r.status_code == 200
    assert called["fanout"] == 0, "reviewer bypass must not hit the gateway"


def test_send_login_otp_stamps_delivery_on_otp_record(srv, monkeypatch):
    """Fix 2 — the per-channel acceptance is annotated on the OTP doc."""
    # Force both channels through our FakeAsyncClient so no real HTTP leaves.
    monkeypatch.setattr(srv, "OTP_CHANNEL", "both")
    asyncio.run(srv.store_otp("9000000022", "121212"))
    asyncio.run(srv.send_login_otp("9000000022", "121212"))
    rec = asyncio.run(srv.db.otp_codes.find_one({"phone": "9000000022"}))
    assert rec and "delivery_last" in rec
    dl = rec["delivery_last"]
    assert set(dl.keys()) >= {"whatsapp", "sms", "channel_policy", "at"}
    assert dl["channel_policy"] == "both"
    # FakeAsyncClient default is Platform Accepted → both channels marked accepted.
    assert dl["sms"] in {"accepted", "rejected", "skipped"}
    assert dl["whatsapp"] in {"accepted", "rejected", "skipped"}
    # Success path → delivery_failed must be False.
    assert rec["delivery_failed"] is False


def test_send_login_otp_marks_delivery_failed_when_all_reject(srv, monkeypatch):
    from conftest import FakeAsyncClient
    FakeAsyncClient.scripted = {"status_code": 500, "text": "nope"}
    # Also force an empty SMS key path by making send_otp_sms refuse early.
    async def _fail_wa(*_a, **_kw): return {"success": False, "error": "wa down"}
    async def _fail_sms(*_a, **_kw): return {"success": False, "error": "sms down"}
    monkeypatch.setattr(srv, "send_otp_whatsapp", _fail_wa)
    monkeypatch.setattr(srv, "send_otp_sms", _fail_sms)
    monkeypatch.setattr(srv, "OTP_CHANNEL", "both")
    asyncio.run(srv.store_otp("9000000023", "131313"))
    asyncio.run(srv.send_login_otp("9000000023", "131313"))
    rec = asyncio.run(srv.db.otp_codes.find_one({"phone": "9000000023"}))
    assert rec["delivery_failed"] is True
    assert rec["delivery_last"]["whatsapp"] == "rejected"
    assert rec["delivery_last"]["sms"] == "rejected"
