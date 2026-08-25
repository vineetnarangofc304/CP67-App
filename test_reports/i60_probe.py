"""iter-60 probes: (a) baseline vs loaded /api/health latency, (b) why bulk queued != 0."""
import asyncio
import base64
import os
import re
import statistics
import sys
import time
import concurrent.futures as cf
from pathlib import Path

import requests
from dotenv import dotenv_values

sys.path.insert(0, "/app/backend")
BASE_URL = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
import server  # noqa

content = Path("/app/memory/test_credentials.md").read_text()
blk = content.split("## Admin Dashboard")[1]
U = re.search(r"Username:\s*`([^`]+)`", blk).group(1)
P = re.search(r"Password:\s*`([^`]+)`", blk).group(1)
TOK = requests.post(f"{BASE_URL}/api/admin/login", json={"username": U, "password": P}, timeout=30).json()["token"]
H = {"Authorization": f"Bearer {TOK}"}


def run(c):
    return loop.run_until_complete(c)


def health():
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/health", timeout=60)
    return r.status_code, (time.time() - t0) * 1000


print("=== A. baseline /api/health (idle) ===")
base = [health()[1] for _ in range(8)]
print(f"idle health: min={min(base):.0f} med={statistics.median(base):.0f} max={max(base):.0f}")

print("=== B. /api/health while 6 concurrent 300KB objstore reads ===")
docs = run(server.db.bills.find({"image_url": {"$regex": "^objstore:"}}, {"_id": 0, "id": 1}).limit(1).to_list(1))
bill_id = docs[0]["id"]


def read_image():
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/bills/{bill_id}/image", headers=H, timeout=60)
    return r.status_code, (time.time() - t0) * 1000, len(r.content)


with cf.ThreadPoolExecutor(max_workers=12) as ex:
    imgs = [ex.submit(read_image) for _ in range(6)]
    time.sleep(0.05)
    hs = [ex.submit(health) for _ in range(6)]
    ir = [f.result() for f in imgs]
    hr = [f.result() for f in hs]
print("img:", [(s, round(t), sz) for s, t, sz in ir])
print("health under load:", [(s, round(t)) for s, t in hr])

print("=== C. bulk endpoint state ===")
q = {"image_url": {"$regex": "^(data:image/|base64:)"}, "$expr": {"$gt": [{"$strLenCP": "$image_url"}, 50000]}}
n = run(server.db.bills.count_documents(q))
print("matching docs (fat inline):", n)
sample = run(server.db.bills.find(q, {"_id": 0, "id": 1, "image_url": 1, "image_migrated_at": 1}).limit(10).to_list(10))
for d in sample:
    u = d["image_url"]
    b64 = u.split(",", 1)[1] if u.startswith("data:") else u[7:]
    try:
        dec = len(base64.b64decode(b64))
        err = None
    except Exception as e:
        dec, err = -1, str(e)[:60]
    print(f"  {d['id']}  urllen={len(u)} decoded={dec} err={err} migrated_at={d.get('image_migrated_at')}")

for i in range(4):
    r = requests.post(f"{BASE_URL}/api/admin/bills/migrate-images-to-objstore?limit=500", headers=H, timeout=60)
    print(f"call {i+1}: {r.status_code} {r.json()}")
    if r.json().get("queued") == 0:
        break
    time.sleep(20)
print("final matching docs:", run(server.db.bills.count_documents(q)))
left = run(server.db.bills.find(q, {"_id": 0, "id": 1, "image_url": 1}).limit(5).to_list(5))
for d in left:
    u = d["image_url"]
    b64 = u.split(",", 1)[1] if u.startswith("data:") else u[7:]
    try:
        dec = len(base64.b64decode(b64))
    except Exception as e:
        dec = f"ERR {e}"
    print("  STUCK:", d["id"], "urllen", len(u), "decoded", dec)
