"""Report-only probe: concurrent /api/staff/redeem on throwaway P2324TEST UI staff (double-spend check)."""
import json, os, concurrent.futures as cf
import requests
from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
st = json.load(open("/tmp/p2324_ui.json"))
h = {"Authorization": f"Bearer {st['staff_token']}"}
with cf.ThreadPoolExecutor(8) as ex:
    codes = list(ex.map(lambda _: requests.post(f"{BASE}/api/staff/redeem", headers=h, json={"amount": 100}).status_code, range(8)))
print("codes", codes)
print("summary", requests.get(f"{BASE}/api/staff/dashboard", headers=h).json()["summary"])
