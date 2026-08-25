"""Iteration 58 — latency probe: multi-MB inline base64 bill image.

Seeds a ~4MB data: image bill (same shape as the production Haldiram's doc),
then measures (a) raw motor find_one latency with zstd compression enabled and
(b) end-to-end GET /api/bills/{id}/image latency, to confirm the read is well
inside the 20s socketTimeoutMS budget.
"""
import asyncio
import os
import re
import sys
import time
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env["REACT_APP_BACKEND_URL"]).rstrip("/")
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


@pytest.fixture(scope="module")
def client():
    content = CREDS_PATH.read_text(encoding="utf-8").split("## Admin Dashboard")[1]
    u = re.search(r"Username:\s*`([^`]+)`", content).group(1)
    p = re.search(r"Password:\s*`([^`]+)`", content).group(1)
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"username": u, "password": p}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def big_bill():
    import server

    bill_id = f"TEST_i58_big_{uuid.uuid4().hex[:8]}"
    payload = "data:image/jpeg;base64," + ("QUJDREVGR0g" * 400_000)  # ~4.4MB
    _run(server.db.bills.insert_one({
        "id": bill_id,
        "user_id": "TEST_i58_big_user",
        "user_phone": "919999900058",
        "brand": "Haldiram's",
        "amount": 91.36,
        "status": "pending_review",
        "image_url": payload,
        "image_hash": "TEST_i58_big_hash",
    }))
    yield bill_id, len(payload)
    _run(server.db.bills.delete_many({"id": bill_id}))


def test_raw_find_one_latency(big_bill):
    import server

    bill_id, size = big_bill
    times = []
    for _ in range(3):
        t0 = time.time()
        doc = _run(server.db.bills.find_one({"id": bill_id}, {"_id": 0, "image_url": 1, "image_hash": 1}))
        times.append(time.time() - t0)
        assert doc and len(doc["image_url"]) == size
    print(f"\nraw find_one on {size/1024/1024:.2f}MB doc (zstd on): "
          f"{[round(t*1000) for t in times]} ms")
    assert max(times) < 20.0, "read exceeded socketTimeoutMS budget"


def test_image_endpoint_latency_big_doc(client, big_bill):
    bill_id, size = big_bill
    times = []
    for _ in range(3):
        t0 = time.time()
        r = client.get(f"{BASE_URL}/api/bills/{bill_id}/image", timeout=60)
        times.append(time.time() - t0)
        assert r.status_code == 200, r.text[:200]
        assert r.json()["fetch_error"] is None
        assert len(r.json()["image_url"]) == size
    print(f"end-to-end /image on {size/1024/1024:.2f}MB doc: "
          f"{[round(t*1000) for t in times]} ms")
    assert max(times) < 20.0
