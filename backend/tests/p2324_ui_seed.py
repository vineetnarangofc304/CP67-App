"""Seed/cleanup throwaway P2324TEST staff + manager for UI test. Usage: python p2324_ui_seed.py seed|cleanup"""
import os, sys, json, uuid
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv
from pymongo import MongoClient
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(HERE, ".env")); load_dotenv(os.path.join(os.path.dirname(HERE), "frontend", ".env"))
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
STATE = "/tmp/p2324_ui.json"

if sys.argv[1] == "seed":
    adm = requests.post(f"{BASE}/api/admin/login", json={"username": "admin", "password": "CP67Admin@2025"}).json()["token"]
    h = {"Authorization": f"Bearer {adm}"}
    s = requests.post(f"{BASE}/api/admin/staff", headers=h, json={"name": "P2324TEST UI Staff", "phone": "7000023020", "brand_name": "P2324TEST UIBrand"}).json()["staff"]
    for amt in (50, 60):
        db.staff_incentives.insert_one({"id": f"P2324TEST-{uuid.uuid4()}", "staff_id": s["id"], "type": "bill_upload", "status": "redeemable", "amount": amt, "created_at": datetime.now(timezone.utc).isoformat(), "tag": "P2324TEST"})
    m = requests.post(f"{BASE}/api/admin/staff/retailer-managers", headers=h, json={"name": "P2324TEST UI Mgr", "phone": "7000023021", "brands": ["P2324TEST UIBrand"]}).json()["manager"]
    st = requests.post(f"{BASE}/api/staff/auth/verify-otp", json={"phone": "7000023020", "otp": "1234"}).json()
    rt = requests.post(f"{BASE}/api/staff/retailer/auth/verify-otp", json={"phone": "7000023021", "otp": "1234"}).json()
    out = {"sid": s["id"], "mid": m["id"], "admin": adm, "staff_token": st["token"], "staff": st["staff"], "ret_token": rt["token"], "mgr": rt["manager"]}
    json.dump(out, open(STATE, "w")); print(json.dumps(out))
else:
    st = json.load(open(STATE))
    for c in ("staff_incentives", "staff_redemptions", "staff_attribution_misses"):
        print(c, db[c].delete_many({"staff_id": st["sid"]}).deleted_count)
    print("staff", db.retail_staff.delete_one({"id": st["sid"]}).deleted_count)
    print("mgr", db.retailer_managers.delete_one({"id": st["mid"]}).deleted_count)
