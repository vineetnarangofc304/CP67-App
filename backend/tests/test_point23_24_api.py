"""Points 23/24 API regression: staff balance deduction via redemption requests (public URL) +
registration unlock brand rules (function-level). Throwaway P2324TEST records, phones 70000230xx."""
import os, sys, uuid, asyncio
from datetime import datetime, timezone
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
load_dotenv(os.path.join(HERE, ".env"))
load_dotenv(os.path.join(os.path.dirname(HERE), "frontend", ".env"))
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
TAG = "P2324TEST"
STAFF_PHONE = "7000023010"
MGR_PHONE = "7000023011"
CUST_PHONE = "7000023012"
BRAND = "P2324TEST Brand"

mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
CTX = {}


def _now():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture(scope="module", autouse=True)
def setup_module_data():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"username": "admin", "password": "CP67Admin@2025"})
    assert r.status_code == 200
    CTX["admin"] = {"Authorization": f"Bearer {r.json()['token']}"}
    r = requests.post(f"{BASE_URL}/api/admin/staff", headers=CTX["admin"],
                      json={"name": f"{TAG} Staff", "phone": STAFF_PHONE, "brand_name": BRAND})
    assert r.status_code == 200, r.text
    CTX["sid"] = r.json()["staff"]["id"]
    r = requests.post(f"{BASE_URL}/api/staff/auth/verify-otp", json={"phone": STAFF_PHONE, "otp": "1234"})
    assert r.status_code == 200, r.text
    CTX["staff"] = {"Authorization": f"Bearer {r.json()['token']}"}
    for amt, st in ((50, "redeemable"), (60, "redeemable"), (30, "pending")):
        mdb.staff_incentives.insert_one({"id": f"{TAG}-{uuid.uuid4()}", "staff_id": CTX["sid"], "type": "bill_upload",
                                         "status": st, "amount": amt, "created_at": _now(), "tag": TAG})
    yield
    sid = CTX["sid"]
    mdb.staff_incentives.delete_many({"staff_id": sid})
    mdb.staff_redemptions.delete_many({"staff_id": sid})
    mdb.staff_attribution_misses.delete_many({"staff_id": sid})
    mdb.retail_staff.delete_one({"id": sid})
    if CTX.get("mid"):
        mdb.retailer_managers.delete_one({"id": CTX["mid"]})


def _dash():
    r = requests.get(f"{BASE_URL}/api/staff/dashboard", headers=CTX["staff"])
    assert r.status_code == 200
    return r.json()["summary"]


def _redeem(amount):
    return requests.post(f"{BASE_URL}/api/staff/redeem", headers=CTX["staff"], json={"amount": amount})


def _last_redemption_id():
    r = requests.get(f"{BASE_URL}/api/staff/redemptions", headers=CTX["staff"])
    assert r.status_code == 200
    return r.json()["redemptions"][0]["id"]


def _patch(rid, status):
    return requests.patch(f"{BASE_URL}/api/admin/staff/redemptions/{rid}", headers=CTX["admin"], json={"status": status})


# Point 23: balance lifecycle (ordered)
class TestBalanceFlow:
    def test_01_initial(self):
        s = _dash()
        assert s["redeemable"] == 110 and s["redeemed"] == 0 and s["in_process"] == 0 and s["on_hold"] == 30

    def test_02_over_and_zero_rejected(self):
        assert _redeem(110.01).status_code == 400
        assert _redeem(0).status_code == 400
        assert _redeem(-5).status_code == 400
        assert _dash()["redeemable"] == 110

    def test_03_request_deducts_then_settle(self):
        r = _redeem(10)
        assert r.status_code == 200 and r.json()["amount"] == 10
        s = _dash()
        assert s["redeemable"] == 100 and s["in_process"] == 10
        rid = _last_redemption_id()
        assert _patch(rid, "settled").status_code == 200
        s = _dash()
        assert s["redeemable"] == 100 and s["redeemed"] == 10 and s["in_process"] == 0

    def test_04_reject_restores(self):
        assert _redeem(25).status_code == 200
        assert _dash()["redeemable"] == 75
        rid = _last_redemption_id()
        assert _patch(rid, "rejected").status_code == 200
        s = _dash()
        assert s["redeemable"] == 100 and s["redeemed"] == 10

    def test_05_approved_still_deducted_and_exact_full(self):
        assert _redeem(100.01).status_code == 400
        assert _redeem(100).status_code == 200
        rid = _last_redemption_id()
        assert _patch(rid, "approved").status_code == 200
        s = _dash()
        assert s["redeemable"] == 0 and s["in_process"] == 100 and s["redeemed"] == 10
        assert _redeem(1).status_code == 400

    def test_06_metrics_overview(self):
        r = requests.get(f"{BASE_URL}/api/admin/staff/metrics/overview", headers=CTX["admin"])
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d["available_balance"], (int, float)) and isinstance(d["settled_amount"], (int, float))
        assert d["settled_amount"] >= 10

    def test_07_retailer_manager_dashboard(self):
        r = requests.post(f"{BASE_URL}/api/admin/staff/retailer-managers", headers=CTX["admin"],
                          json={"name": f"{TAG} Mgr", "phone": MGR_PHONE, "brands": [BRAND]})
        assert r.status_code == 200, r.text
        CTX["mid"] = r.json()["manager"]["id"]
        r = requests.post(f"{BASE_URL}/api/staff/retailer/auth/verify-otp", json={"phone": MGR_PHONE, "otp": "1234"})
        assert r.status_code == 200, r.text
        h = {"Authorization": f"Bearer {r.json()['token']}"}
        r = requests.get(f"{BASE_URL}/api/staff/retailer/dashboard", headers=h)
        assert r.status_code == 200
        d = r.json()
        row = [x for x in d["staff"] if x["name"] == f"{TAG} Staff"][0]
        assert row["redeemable"] == 0 and row["redeemed"] == 10 and row["pending"] == 30
        assert d["summary"]["redeemable"] == 0 and d["summary"]["redeemed"] == 10

    def test_08_unknown_status_patch(self):
        """Report-only: unvalidated status strings drop out of hold statuses and silently restore balance."""
        rid = _last_redemption_id()
        r = _patch(rid, "bogus")
        CTX["bogus_status"] = r.status_code
        if r.status_code == 200:
            bal = _dash()["redeemable"]
            _patch(rid, "approved")
            pytest.fail(f"PATCH accepted status='bogus' (200); balance became {bal}")


# Point 24: registration unlock rules (function-level, no messaging)
def test_registration_unlock_rules():
    from motor.motor_asyncio import AsyncIOMotorClient
    import routes.staff as staff_mod

    async def t():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        staff_mod._db = db
        sid = f"{TAG}-{uuid.uuid4()}"
        reg = f"{TAG}-reg-{uuid.uuid4()}"
        bills = []
        try:
            await db.retail_staff.insert_one({"id": sid, "staff_code": f"{TAG}-S2", "brand_name": "P2324TEST Mart", "tag": TAG})
            await db.staff_incentives.insert_one({"id": reg, "staff_id": sid, "staff_code": f"{TAG}-S2", "customer_phone": CUST_PHONE,
                                                  "type": "registration", "status": "pending", "amount": 20, "created_at": _now(), "tag": TAG})

            async def bill(store, status):
                bid = f"{TAG}-bill-{uuid.uuid4()}"
                bills.append(bid)
                await db.bills.insert_one({"id": bid, "user_phone": CUST_PHONE, "store_name": store, "amount": 100,
                                           "status": status, "created_at": _now(), "tag": TAG})
                await staff_mod.create_or_activate_bill_incentive(bid, CUST_PHONE, status)
                return (await db.staff_incentives.find_one({"id": reg}))["status"]

            assert await bill("P2324TEST Other", "auto_approved") == "pending"
            assert await bill("P2324TEST Mart", "pending_review") == "pending"
            assert await bill("P2324TEST Mart", "rejected") == "pending"
            assert await bill("", "approved") == "pending"
            assert await bill("p2324test-MART", "auto_approved") == "redeemable"
        finally:
            await db.staff_incentives.delete_many({"$or": [{"staff_id": sid}, {"bill_id": {"$in": bills}}]})
            await db.staff_attribution_misses.delete_many({"$or": [{"staff_id": sid}, {"bill_id": {"$in": bills}}]})
            await db.bills.delete_many({"id": {"$in": bills}})
            await db.retail_staff.delete_one({"id": sid})
    asyncio.run(t())
