"""Point 22: upload-bound attribution re-evaluation. Throwaway Preview records only (prefix P22TEST)."""
import os, sys, uuid, asyncio
from datetime import datetime, timezone, timedelta
import pytest
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from motor.motor_asyncio import AsyncIOMotorClient
import routes.staff as staff_mod

TAG = "P22TEST"
PHONE = "7000022001"


def _iso(dt):
    return dt.isoformat()


async def _setup():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    staff_mod._db = db
    return db


async def _cleanup(db):
    for c in ("retail_staff", "staff_attributions", "staff_incentives", "staff_attribution_misses", "bills"):
        await db[c].delete_many({"$or": [{"tag": TAG}, {"customer_phone": PHONE}, {"user_phone": PHONE}]})


async def _staff(db, brand="Dominos"):
    sid = f"{TAG}-{uuid.uuid4()}"
    await db.retail_staff.insert_one({"id": sid, "staff_code": f"{TAG}-S", "name": "P22", "brand_name": brand,
                                      "is_active": True, "qr_token": f"{TAG}{uuid.uuid4().hex[:6]}", "tag": TAG})
    return sid


async def _scan(db, sid, at):
    aid = str(uuid.uuid4())
    await db.staff_attributions.insert_one({"id": aid, "customer_phone": PHONE, "staff_id": sid, "staff_code": f"{TAG}-S",
                                            "created_at": _iso(at), "expires_at": _iso(at + timedelta(minutes=15)),
                                            "used": False, "tag": TAG})
    return aid


async def _bill(db, store, at, amount=500):
    bid = f"{TAG}-{uuid.uuid4()}"
    await db.bills.insert_one({"id": bid, "user_phone": PHONE, "store_name": store, "amount": amount,
                               "status": "manual_review", "created_at": _iso(at), "tag": TAG})
    return bid


def run(coro):
    return asyncio.run(coro)


def test_brand_correction_after_upload_credits_upload_attribution():
    async def t():
        db = await _setup(); await _cleanup(db)
        try:
            now = datetime.now(timezone.utc)
            sid = await _staff(db)
            aid = await _scan(db, sid, now - timedelta(minutes=2))
            bid = await _bill(db, "Jubilant FoodWorks Ltd", now)
            await staff_mod.create_or_activate_bill_incentive(bid, PHONE, "manual_review")
            assert await db.staff_incentives.count_documents({"bill_id": bid}) == 0
            att = await db.staff_attributions.find_one({"id": aid})
            assert att["used"] is True and att["used_by_bill_id"] == bid
            assert await db.staff_attribution_misses.count_documents({"bill_id": bid, "reason": "brand_mismatch"}) == 1
            # admin corrects brand, then approves
            await db.bills.update_one({"id": bid}, {"$set": {"store_name": "Dominos", "status": "approved"}})
            await staff_mod.create_or_activate_bill_incentive(bid, PHONE, "approved")
            await staff_mod.sync_incentive_on_bill_status_change(bid, "approved")
            rows = await db.staff_incentives.find({"bill_id": bid}).to_list(10)
            assert len(rows) == 1 and rows[0]["staff_id"] == sid and rows[0]["status"] == "redeemable"
            # repeat approval → still exactly one award
            await staff_mod.create_or_activate_bill_incentive(bid, PHONE, "approved")
            assert await db.staff_incentives.count_documents({"bill_id": bid}) == 1
            # reject → cancelled
            await staff_mod.create_or_activate_bill_incentive(bid, PHONE, "rejected")
            await staff_mod.sync_incentive_on_bill_status_change(bid, "rejected")
            r = await db.staff_incentives.find_one({"bill_id": bid})
            assert r["status"] == "cancelled"
        finally:
            await _cleanup(db)
    run(t())


def test_later_qr_scan_not_used_for_earlier_bill():
    async def t():
        db = await _setup(); await _cleanup(db)
        try:
            now = datetime.now(timezone.utc)
            sid_later = await _staff(db)
            bid = await _bill(db, "Dominos", now - timedelta(minutes=5))
            later = await _scan(db, sid_later, now - timedelta(minutes=1))
            await staff_mod.create_or_activate_bill_incentive(bid, PHONE, "approved")
            assert await db.staff_incentives.count_documents({"bill_id": bid}) == 0
            att = await db.staff_attributions.find_one({"id": later})
            assert att["used"] is False and "used_by_bill_id" not in att
        finally:
            await _cleanup(db)
    run(t())


def test_same_brand_upload_credits_once_and_latest_scan_wins():
    async def t():
        db = await _setup(); await _cleanup(db)
        try:
            now = datetime.now(timezone.utc)
            s1 = await _staff(db); s2 = await _staff(db)
            await _scan(db, s1, now - timedelta(minutes=6))
            await _scan(db, s2, now - timedelta(minutes=2))
            bid = await _bill(db, "Dominos", now)
            await staff_mod.create_or_activate_bill_incentive(bid, PHONE, "auto_approved")
            rows = await db.staff_incentives.find({"bill_id": bid}).to_list(10)
            assert len(rows) == 1 and rows[0]["staff_id"] == s2 and rows[0]["status"] == "redeemable"
            # second bill in window without new scan: no credit
            bid2 = await _bill(db, "Dominos", now + timedelta(seconds=30))
            await staff_mod.create_or_activate_bill_incentive(bid2, PHONE, "auto_approved")
            assert await db.staff_incentives.count_documents({"bill_id": bid2}) == 0
        finally:
            await _cleanup(db)
    run(t())


def test_mismatch_stays_uncredited_without_correction():
    async def t():
        db = await _setup(); await _cleanup(db)
        try:
            now = datetime.now(timezone.utc)
            sid = await _staff(db)
            await _scan(db, sid, now - timedelta(minutes=1))
            bid = await _bill(db, "Nike", now)
            await staff_mod.create_or_activate_bill_incentive(bid, PHONE, "approved")
            await staff_mod.create_or_activate_bill_incentive(bid, PHONE, "approved")
            assert await db.staff_incentives.count_documents({"bill_id": bid}) == 0
            assert await db.staff_attribution_misses.count_documents({"bill_id": bid, "reason": "brand_mismatch"}) == 1
        finally:
            await _cleanup(db)
    run(t())
