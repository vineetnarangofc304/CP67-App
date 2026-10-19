"""
Doc #55 — isolated OTP route test harness.

Isolation guarantees (gate):
1. MONGO_URL is clamped to 127.0.0.1:1 with 5ms serverSelectionTimeout *before* server
   is ever imported. Motor is lazy (no connect at construction), confirmed empirically.
2. httpx.AsyncClient is replaced with a FakeAsyncClient *before* any OTP helper runs,
   so no Karix/WhatsApp HTTP traffic can escape even if a test forgets to patch.
3. The `db.otp_codes` collection is replaced with an in-memory fake. All DB reads/writes
   are captured; a real Motor op would raise AttributeError on the fake, failing loudly.
4. send_whatsapp_text_diag is stubbed so the WhatsApp branch never dials out.
5. No real credentials, phones, provider calls, SMS, builds, or shared runtime are
   touched. The test runs out-of-tree under /tmp/doc55_iso and imports from /app/backend.
"""
import os
import sys
import types
import asyncio
import pytest
from datetime import datetime, timezone, timedelta

# --- Gate 1 — kill real Mongo URL BEFORE importing server ------------------
os.environ["MONGO_URL"] = "mongodb://127.0.0.1:1/doc55_iso?serverSelectionTimeoutMS=5"
os.environ["DB_NAME"] = "doc55_iso"

sys.path.insert(0, "/app/backend")


# --- Gate 2 — fake httpx.AsyncClient ----------------------------------------
class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text

class FakeAsyncClient:
    """Captures outbound Karix calls. Default behaviour: Platform Accepted (success).
    Tests mutate `.scripted` to replay provider rejection / timeout scenarios."""
    scripted = {"status_code": 200,
                "text": "Request accepted for Request ID=1 & Statuscode=200 & Info=Platform Accepted"}
    calls = []  # list of (method, url, params)

    def __init__(self, *_, **__):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def get(self, url, params=None, **_):
        FakeAsyncClient.calls.append(("GET", url, params or {}))
        return FakeResponse(FakeAsyncClient.scripted["status_code"],
                            FakeAsyncClient.scripted["text"])
    async def post(self, url, json=None, headers=None, **_):
        FakeAsyncClient.calls.append(("POST", url, json or {}))
        return FakeResponse(FakeAsyncClient.scripted["status_code"],
                            FakeAsyncClient.scripted["text"])


@pytest.fixture(autouse=True)
def _reset_fake_httpx():
    FakeAsyncClient.calls = []
    FakeAsyncClient.scripted = {
        "status_code": 200,
        "text": "Request accepted for Request ID=1 & Statuscode=200 & Info=Platform Accepted",
    }
    yield


# --- Gate 3 — fake in-memory db.otp_codes -----------------------------------
class FakeOtpCodes:
    def __init__(self):
        self.docs = {}
    async def update_one(self, flt, upd, upsert=False):
        phone = flt.get("phone")
        existing = self.docs.get(phone)
        if "$set" in upd:
            new = dict(existing or {})
            new.update(upd["$set"])
            self.docs[phone] = new
        if "$inc" in upd and existing:
            for k, v in upd["$inc"].items():
                existing[k] = existing.get(k, 0) + v
        if not existing and upsert and "$set" in upd:
            pass  # already set above
        class R: matched_count = 1 if existing else 0; modified_count = 1
        return R()
    async def find_one(self, flt, *_a, **_kw):
        return self.docs.get(flt.get("phone"))
    async def delete_one(self, flt):
        self.docs.pop(flt.get("phone"), None)
        class R: deleted_count = 1
        return R()


# --- Import server AFTER isolation primitives are in place ------------------
import httpx as _httpx
_httpx.AsyncClient = FakeAsyncClient   # covers any 'import httpx' in server

import server  # noqa: E402
server.httpx.AsyncClient = FakeAsyncClient  # belt-and-braces

# Replace the otp_codes collection on the real db reference
server.db.otp_codes = FakeOtpCodes()

# Replace WhatsApp diag with a success stub — scoped per-test via monkeypatch
_original_wa = getattr(server, "send_whatsapp_text_diag", None)
async def _fake_wa(_phone, _message):
    return {"success": True, "status_code": 200, "mid": "FAKE_MID"}
server.send_whatsapp_text_diag = _fake_wa


@pytest.fixture
def srv():
    """Return the imported server module with the fakes already wired."""
    # fresh otp store per test
    server.db.otp_codes = FakeOtpCodes()
    return server
