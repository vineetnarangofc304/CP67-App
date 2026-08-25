"""iter-60 probe 2: isolate residual /api/health latency source.
Compare health latency under (a) 6x objstore reads (async storage path)
vs (b) 6x INLINE fat bill reads (no objstore call, same JSON payload size)
vs (c) 6x tiny /api/bills list calls (no big payload)."""
import asyncio
import base64
import re
import sys
import time
import uuid
import concurrent.futures as cf
from pathlib import Path

import requests
from dotenv import dotenv_values

sys.path.insert(0, "/app/backend")
BASE_URL = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
import server  # noqa
import storage  # noqa

blk = Path("/app/memory/test_credentials.md").read_text().split("## Admin Dashboard")[1]
U = re.search(r"Username:\s*`([^`]+)`", blk).group(1)
P = re.search(r"Password:\s*`([^`]+)`", blk).group(1)
TOK = requests.post(f"{BASE_URL}/api/admin/login", json={"username": U, "password": P}, timeout=30).json()["token"]
H = {"Authorization": f"Bearer {TOK}"}


def run(c):
    return loop.run_until_complete(c)


def jpeg(n):
    return b"\xff\xd8" + bytes((i * 7 + 13) % 256 for i in range(n - 4)) + b"\xff\xd9"


created = []


def seed(url):
    bid = f"TEST_i60_{uuid.uuid4().hex[:8]}"
    run(server.db.bills.insert_one({
        "id": bid, "user_id": "TEST_i60_u", "user_phone": "919999900060",
        "brand": "Haldiram's", "amount": 10.0, "status": "pending_review",
        "image_url": url, "image_hash": bid,
    }))
    created.append(bid)
    return bid


payload = jpeg(300_000)
obj_url = storage.upload_bill_image(f"TEST_i60_obj_{uuid.uuid4().hex[:6]}", payload, "image/jpeg")
obj_bill = seed(obj_url)
# inline bill of the same served size, but small enough NOT to trigger migration? no -
# it WILL trigger progressive migration; use a marker so we only read once and re-seed.
inline_url = "data:image/jpeg;base64," + base64.b64encode(payload).decode()


def health():
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/health", timeout=60)
    return r.status_code, (time.time() - t0) * 1000


def hit(url):
    t0 = time.time()
    r = requests.get(url, headers=H, timeout=90)
    return r.status_code, (time.time() - t0) * 1000, len(r.content)


def scenario(name, urls):
    with cf.ThreadPoolExecutor(max_workers=14) as ex:
        futs = [ex.submit(hit, u) for u in urls]
        time.sleep(0.05)
        hf = [ex.submit(health) for _ in range(6)]
        rr = [f.result() for f in futs]
        hr = [f.result() for f in hf]
    print(f"{name}: worst_req={max(t for _, t, _ in rr):.0f}ms size={rr[0][2]} "
          f"health=[{', '.join(f'{t:.0f}' for _, t in hr)}] worst_health={max(t for _, t in hr):.0f}ms")


print("idle health:", [round(health()[1]) for _ in range(5)])

scenario("A objstore x6 (300KB)", [f"{BASE_URL}/api/bills/{obj_bill}/image"] * 6)

inline_bills = [seed(inline_url) for _ in range(6)]
scenario("B inline x6 (300KB, no objstore call)", [f"{BASE_URL}/api/bills/{b}/image" for b in inline_bills])

scenario("C /api/health x6 only", [f"{BASE_URL}/api/health"] * 6)

# single objstore read latency, no concurrency
print("D single objstore read:", [round(hit(f"{BASE_URL}/api/bills/{obj_bill}/image")[1]) for _ in range(3)])

run(server.db.bills.delete_many({"id": {"$in": created}}))
print("cleaned", len(created))
