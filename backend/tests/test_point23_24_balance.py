"""Points 23/24: staff balance deducts redemption requests; registration unlock uses brand aliases. Throwaway P2324TEST records."""
import os, sys, uuid, asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from motor.motor_asyncio import AsyncIOMotorClient
import routes.staff as staff_mod

TAG = "P2324TEST"
PHONE = "7000023001"


async def _db():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    staff_mod._db = db
    return db


async def _cleanup(db):
    for c in ("retail_staff", "staff_incentives", "staff_redemptions", "staff_attribution_misses", "bills", "brands"):
        await db[c].delete_many({"$or": [{"tag": TAG}, {"customer_phone": PHONE}, {"user_phone": PHONE}]})


def _now():
    return datetime.now(timezone.utc).isoformat()


def test_balance_deducts_requested_and_settled_restores_rejected():
    async def t():
        db = await _db(); await _cleanup(db)
        try:
            sid = f"{TAG}-{uuid.uuid4()}"
            await db.retail_staff.insert_one({"id": sid, "staff_code": f"{TAG}-S", "brand_name": "X", "tag": TAG})
            for amt in (50, 60):
                await db.staff_incentives.insert_one({"id": str(uuid.uuid4()), "staff_id": sid, "type": "bill_upload", "status": "redeemable", "amount": amt, "created_at": _now(), "tag": TAG})
            for amt, st in ((10, "settled"), (15, "rejected"), (5, "requested")):
                await db.staff_redemptions.insert_one({"id": str(uuid.uuid4()), "staff_id": sid, "amount": amt, "status": st, "requested_at": _now(), "tag": TAG})
            b = (await staff_mod.staff_balances([sid]))[sid]
            assert b["available"] == 95 and b["settled"] == 10 and b["in_process"] == 5
            d = await staff_mod.staff_dashboard(staff={"id": sid})
            assert d["summary"]["redeemable"] == 95 and d["summary"]["redeemed"] == 10
        finally:
            await _cleanup(db)
    asyncio.run(t())


def test_registration_unlocks_on_alias_brand_bill_only():
    async def t():
        db = await _db(); await _cleanup(db)
        try:
            sid = f"{TAG}-{uuid.uuid4()}"
            await db.brands.insert_one({"id": f"{TAG}-b", "brand_name": "P2324TEST Pizza", "aliases": ["P2324TEST Foodworks"], "tag": TAG})
            await db.retail_staff.insert_one({"id": sid, "staff_code": f"{TAG}-S", "brand_name": "P2324TEST Pizza", "tag": TAG})
            await db.staff_incentives.insert_one({"id": f"{TAG}-r", "staff_id": sid, "staff_code": f"{TAG}-S", "customer_phone": PHONE, "type": "registration", "status": "pending", "amount": 20, "created_at": _now(), "tag": TAG})
            other = f"{TAG}-{uuid.uuid4()}"
            await db.bills.insert_one({"id": other, "user_phone": PHONE, "store_name": "Nike", "amount": 100, "status": "approved", "created_at": _now(), "tag": TAG})
            await staff_mod.create_or_activate_bill_incentive(other, PHONE, "approved")
            assert (await db.staff_incentives.find_one({"id": f"{TAG}-r"}))["status"] == "pending"
            alias = f"{TAG}-{uuid.uuid4()}"
            await db.bills.insert_one({"id": alias, "user_phone": PHONE, "store_name": "P2324TEST Foodworks", "amount": 100, "status": "manual_review", "created_at": _now(), "tag": TAG})
            await staff_mod.create_or_activate_bill_incentive(alias, PHONE, "manual_review")
            assert (await db.staff_incentives.find_one({"id": f"{TAG}-r"}))["status"] == "pending"
            await staff_mod.create_or_activate_bill_incentive(alias, PHONE, "approved")
            assert (await db.staff_incentives.find_one({"id": f"{TAG}-r"}))["status"] == "redeemable"
        finally:
            await _cleanup(db)
    asyncio.run(t())
