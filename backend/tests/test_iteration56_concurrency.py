"""Iteration 56 addendum — concurrency / production-bill smoke."""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")).rstrip("/")


@pytest.fixture(scope="module")
def client():
    c = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8").split("## Admin Dashboard")[1]
    u = re.search(r"Username:\s*`([^`]+)`", c).group(1)
    p = re.search(r"Password:\s*`([^`]+)`", c).group(1)
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"username": u, "password": p}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


def test_concurrent_image_requests_never_500(client):
    """25 parallel image fetches — exercises the motor pool waitQueueTimeout."""
    r = client.get(f"{BASE_URL}/api/bills?limit=25", timeout=30)
    data = r.json()
    bills = data if isinstance(data, list) else data.get("bills", [])
    ids = [b["id"] for b in bills if b.get("id")][:25]
    assert ids, "no bills to test"

    def _get(bid):
        t0 = time.time()
        rr = client.get(f"{BASE_URL}/api/bills/{bid}/image", timeout=60)
        return bid, rr.status_code, round((time.time() - t0) * 1000), rr.text[:120]

    with ThreadPoolExecutor(max_workers=25) as ex:
        results = list(ex.map(_get, ids))

    bad = [r for r in results if r[1] != 200]
    assert not bad, f"non-200 under concurrency: {bad}"
    worst = max(r[2] for r in results)
    print(f"concurrent image fetch: n={len(results)} worst={worst}ms")
    assert worst < 5000, f"worst latency under concurrency {worst}ms"


def test_market_ninetynine_bill_if_present(client):
    """Try to locate the production-reported bill (MARKET NINETY NINE, 667,
    918559087340) in preview and assert its image endpoint is clean."""
    r = client.get(f"{BASE_URL}/api/bills?limit=500", timeout=60)
    assert r.status_code == 200
    data = r.json()
    bills = data if isinstance(data, list) else data.get("bills", [])
    hits = [b for b in bills
            if "NINETY" in str(b.get("store_name", "")).upper()
            or str(b.get("user_phone", "")).endswith("8559087340")]
    if not hits:
        pytest.skip("target production bill not present in preview DB")
    for b in hits[:5]:
        rr = client.get(f"{BASE_URL}/api/bills/{b['id']}/image", timeout=60)
        assert rr.status_code == 200, f"{b['id']} -> {rr.status_code} {rr.text[:200]}"
        body = rr.json()
        print(f"{b.get('store_name')} amt={b.get('amount')} fetch_error={body.get('fetch_error')} "
              f"has_image={bool(body.get('image_url'))}")
