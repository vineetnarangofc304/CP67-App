"""Iteration 55 — verify the `id` indexes added in ensure_db_indexes() exist and
that the previously-timing-out endpoints are now fast (<500 ms):
  • GET  /api/bills/{bill_id}/image        (valid + unknown id)
  • POST /api/admin/bills/{bill_id}/edit-brand?reprocess=false
Also asserts ensure_db_indexes() is idempotent (safe re-run).
"""
import asyncio
import base64
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or backend_env.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or backend_env.get("DB_NAME")

ID_INDEX_COLLECTIONS = [
    "bills", "users", "brands", "stores",
    "campaigns", "coupons", "staff", "staff_incentives",
]
LATENCY_BUDGET_MS = 500


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def creds():
    p = Path("/app/memory/test_credentials.md")
    if not p.exists():
        pytest.skip("missing test_credentials.md")
    m = re.search(r"## Admin Dashboard\s*\n- Username: `([^`]+)`\s*\n- Password: `([^`]+)`", p.read_text())
    if not m:
        pytest.skip("admin creds not found")
    return {"username": m.group(1), "password": m.group(2)}


@pytest.fixture(scope="session")
def client(creds):
    r = requests.post(f"{BASE_URL}/api/admin/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, "no token in admin login response"
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def mongo():
    cl = MongoClient(MONGO_URL)
    yield cl[DB_NAME]
    cl.close()


@pytest.fixture(scope="session")
def seeded_bill(mongo):
    """A bill with an inline base64 image so the image endpoint can serve it."""
    bid = f"TEST-I55-{uuid.uuid4().hex[:8]}"
    doc = {
        "id": bid,
        "user_id": f"TEST-I55-user-{uuid.uuid4().hex[:6]}",
        "user_phone": "9990001155",
        "store_name": "TEST_I55 Store",
        "brand_name": "TEST_I55 Brand",
        "bill_number": "I55-001",
        "bill_no_normalized": "I55001",
        "amount": 1234.0,
        "status": "approved",
        "image_url": f"data:image/png;base64,{base64.b64encode(os.urandom(400)).decode()}",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    mongo.bills.insert_one(doc)
    yield bid
    mongo.bills.delete_many({"id": {"$regex": "^TEST-I55-"}})


def timed(fn):
    t0 = time.perf_counter()
    resp = fn()
    return resp, (time.perf_counter() - t0) * 1000


# ---------------- index existence ----------------
@pytest.mark.parametrize("collection", ID_INDEX_COLLECTIONS)
def test_id_index_exists(mongo, collection):
    info = mongo[collection].index_information()
    assert "id_1" in info, f"{collection} missing id_1 index; have {sorted(info)}"
    assert info["id_1"]["key"] == [("id", 1)]


def test_bills_id_lookup_uses_index(mongo, seeded_bill):
    plan = mongo.command("explain", {
        "find": "bills",
        "filter": {"id": seeded_bill},
    }, verbosity="queryPlanner")
    winning = plan["queryPlanner"]["winningPlan"]
    stages = str(winning)
    assert "IXSCAN" in stages, f"bills.id lookup not using an index: {stages[:500]}"
    assert "COLLSCAN" not in stages, f"bills.id lookup still doing a collection scan: {stages[:500]}"


# ---------------- endpoint latency / behaviour ----------------
def test_bill_image_valid_fast(client, seeded_bill):
    resp, ms = timed(lambda: client.get(f"{BASE_URL}/api/bills/{seeded_bill}/image", timeout=30))
    assert resp.status_code == 200, f"{resp.status_code}: {resp.text[:300]}"
    body = resp.json()
    assert body.get("image_url"), f"no image_url returned: {str(body)[:300]}"
    assert not body.get("fetch_error"), f"unexpected fetch_error: {body.get('fetch_error')}"
    assert ms < LATENCY_BUDGET_MS, f"took {ms:.0f}ms (budget {LATENCY_BUDGET_MS}ms)"


def test_bill_image_unknown_id_404_fast(client):
    unknown = f"TEST-I55-missing-{uuid.uuid4().hex}"
    resp, ms = timed(lambda: client.get(f"{BASE_URL}/api/bills/{unknown}/image", timeout=30))
    assert resp.status_code == 404, f"{resp.status_code}: {resp.text[:300]}"
    assert "detail" in resp.json()
    assert ms < LATENCY_BUDGET_MS, f"took {ms:.0f}ms (budget {LATENCY_BUDGET_MS}ms)"


def test_edit_brand_no_reprocess_fast(client, seeded_bill, mongo):
    resp, ms = timed(lambda: client.post(
        f"{BASE_URL}/api/admin/bills/{seeded_bill}/edit-brand",
        json={"new_store_name": "TEST_I55 Store Updated", "reprocess": False},
        timeout=30,
    ))
    assert resp.status_code == 200, f"{resp.status_code}: {resp.text[:300]}"
    body = resp.json()
    assert body["success"] is True
    assert body["reprocessed"] is False
    assert body["store_name"] == "TEST_I55 Store Updated"
    assert ms < LATENCY_BUDGET_MS, f"took {ms:.0f}ms (budget {LATENCY_BUDGET_MS}ms)"
    # persistence check
    doc = mongo.bills.find_one({"id": seeded_bill})
    assert doc["store_name"] == "TEST_I55 Store Updated"


def test_repeated_image_calls_stay_fast(client, seeded_bill):
    times = []
    for _ in range(5):
        resp, ms = timed(lambda: client.get(f"{BASE_URL}/api/bills/{seeded_bill}/image", timeout=30))
        assert resp.status_code == 200
        times.append(ms)
    avg = sum(times) / len(times)
    assert max(times) < LATENCY_BUDGET_MS, f"slowest call {max(times):.0f}ms, times={[round(t) for t in times]}"
    print(f"avg image latency {avg:.0f}ms, max {max(times):.0f}ms")


# ---------------- idempotency ----------------
def test_ensure_db_indexes_idempotent(mongo):
    import sys
    sys.path.insert(0, "/app/backend")
    before = {c: set(mongo[c].index_information()) for c in ID_INDEX_COLLECTIONS}
    from server import ensure_db_indexes
    asyncio.run(ensure_db_indexes())
    after = {c: set(mongo[c].index_information()) for c in ID_INDEX_COLLECTIONS}
    for c in ID_INDEX_COLLECTIONS:
        assert "id_1" in after[c]
        assert before[c] <= after[c], f"{c} lost indexes: {before[c] - after[c]}"
