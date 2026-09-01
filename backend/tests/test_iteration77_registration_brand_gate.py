"""Iteration 77 — Point 14b: registration-incentive activation is now BRAND-GATED.

Bug: `create_or_activate_bill_incentive` activated ANY pending registration
incentive for the customer the moment ANY bill was approved. So a customer
registered at Retailer A but uploading a Retailer B bill still credited A.

Scenarios covered (direct call to create_or_activate_bill_incentive):
  1. Reported bug: reg@BrandA pending + scan staff_B + BrandB bill approved
  2. Registration path still works (BrandA bill approved → reg redeemable)
  3. Multi-brand customer: only matching-brand registration activates
  4. No attribution at all → bill_doc fetched lazily, brand-match still applied
  5. pending_review does not activate; a later approved call does
  R. Regression: Point 14 bill_upload brand-match + attribution consumption
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
from dotenv import dotenv_values

sys.path.insert(0, "/app/backend")

_benv = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or _benv.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or _benv.get("DB_NAME")
if not MONGO_URL or not DB_NAME:
    raise RuntimeError("MONGO_URL / DB_NAME missing from env and /app/backend/.env")

PREFIX = "TEST_ITER77_"

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
def db():
    from motor.motor_asyncio import AsyncIOMotorClient
    from routes.staff import bind_db
    client = AsyncIOMotorClient(MONGO_URL, io_loop=_LOOP)
    database = client[DB_NAME]
    bind_db(database)
    return database


@pytest.fixture(scope="module", autouse=True)
def cleanup(db):
    yield
    async def _clean():
        for coll in ("retail_staff", "staff_attributions", "staff_incentives",
                     "bills", "staff_attribution_misses"):
            await db[coll].delete_many({"_iter77": True})
    _run(_clean())


def _phone():
    return "9" + uuid.uuid4().int.__str__()[:9]


async def _seed_staff(db, brand, name="Staff"):
    sid = f"{PREFIX}staff_{uuid.uuid4().hex[:8]}"
    code = f"HL-77{uuid.uuid4().hex[:4].upper()}"
    await db.retail_staff.insert_one({
        "id": sid, "staff_code": code, "name": f"{PREFIX}{name}",
        "phone": _phone(), "brand_name": brand, "brand_category": "Retail",
        "is_active": True, "created_at": datetime.now(timezone.utc).isoformat(),
        "_iter77": True,
    })
    return sid, code


async def _seed_attribution(db, cust, sid, code):
    await db.staff_attributions.insert_one({
        "id": str(uuid.uuid4()), "customer_phone": cust,
        "staff_id": sid, "staff_code": code,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": "2099-01-01T00:00:00+00:00", "used": False,
        "_iter77": True,
    })


async def _seed_pending_registration(db, cust, sid, code, amount=50):
    rid = str(uuid.uuid4())
    await db.staff_incentives.insert_one({
        "id": rid, "staff_id": sid, "staff_code": code, "customer_phone": cust,
        "type": "registration", "status": "pending", "amount": amount,
        "expires_at": "2099-01-01T00:00:00+00:00",
        "created_at": datetime.now(timezone.utc).isoformat(), "_iter77": True,
    })
    return rid


async def _seed_bill(db, cust, store_name, amount=1500, status="approved"):
    bid = f"{PREFIX}bill_{uuid.uuid4().hex[:8]}"
    await db.bills.insert_one({
        "id": bid, "user_phone": cust, "amount": amount,
        "store_name": store_name, "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(), "_iter77": True,
    })
    return bid


# ---------------- Scenario 1: the reported bug ----------------
def test_s1_other_brand_bill_does_not_activate_registration(db):
    from routes.staff import create_or_activate_bill_incentive

    async def run():
        cust = _phone()
        sid_a, code_a = await _seed_staff(db, "Brand Alpha", "A")
        sid_b, code_b = await _seed_staff(db, "Brand Beta", "B")
        reg_id = await _seed_pending_registration(db, cust, sid_a, code_a)
        await _seed_attribution(db, cust, sid_b, code_b)
        bill_id = await _seed_bill(db, cust, "Brand Beta")

        await create_or_activate_bill_incentive(bill_id, cust, "approved", 1500.0)

        # (a) staff_B credited with a redeemable bill_upload incentive
        credit = await db.staff_incentives.find_one(
            {"bill_id": bill_id, "type": "bill_upload"}, {"_id": 0})
        assert credit is not None, "staff_B should receive a bill_upload incentive"
        assert credit["staff_id"] == sid_b
        assert credit["status"] == "redeemable"

        # (b) staff_A registration incentive stays pending
        reg = await db.staff_incentives.find_one({"id": reg_id}, {"_id": 0})
        assert reg["status"] == "pending", f"BUG: reg activated wrongly -> {reg['status']}"
        assert reg.get("approved_at") in (None, ""), "reg should not have approved_at"

        # (c) audit miss row for staff_A
        miss = await db.staff_attribution_misses.find_one(
            {"bill_id": bill_id, "staff_id": sid_a,
             "reason": "registration_activation_brand_mismatch"}, {"_id": 0})
        assert miss is not None, "Expected registration_activation_brand_mismatch miss row"
        assert miss["bill_brand"] == "Brand Beta"
        assert miss["staff_brand"] == "Brand Alpha"
        assert miss["customer_phone"] == cust

    _run(run())


# ---------------- Scenario 2: happy path still works ----------------
def test_s2_same_brand_bill_activates_registration(db):
    from routes.staff import create_or_activate_bill_incentive

    async def run():
        cust = _phone()
        sid_a, code_a = await _seed_staff(db, "Brand Alpha", "A")
        reg_id = await _seed_pending_registration(db, cust, sid_a, code_a)
        await _seed_attribution(db, cust, sid_a, code_a)
        bill_id = await _seed_bill(db, cust, "brand alpha")

        await create_or_activate_bill_incentive(bill_id, cust, "approved", 2000.0)

        reg = await db.staff_incentives.find_one({"id": reg_id}, {"_id": 0})
        assert reg["status"] == "redeemable", "Matching-brand bill must activate registration"
        assert reg.get("approved_at")

        credit = await db.staff_incentives.find_one(
            {"bill_id": bill_id, "type": "bill_upload"}, {"_id": 0})
        assert credit is not None and credit["staff_id"] == sid_a
        assert credit["status"] == "redeemable"

        miss = await db.staff_attribution_misses.find_one({"bill_id": bill_id})
        assert miss is None, f"No miss rows expected on happy path: {miss}"

    _run(run())


# ---------------- Scenario 3: multi-brand customer ----------------
def test_s3_multi_brand_only_matching_registration_activates(db):
    from routes.staff import create_or_activate_bill_incentive

    async def run():
        cust = _phone()
        sid_a, code_a = await _seed_staff(db, "Brand Alpha", "A")
        sid_c, code_c = await _seed_staff(db, "Brand Charlie", "C")
        reg_a = await _seed_pending_registration(db, cust, sid_a, code_a)
        reg_c = await _seed_pending_registration(db, cust, sid_c, code_c)
        bill_id = await _seed_bill(db, cust, "Brand Alpha")

        await create_or_activate_bill_incentive(bill_id, cust, "approved", 900.0)

        assert (await db.staff_incentives.find_one({"id": reg_a}))["status"] == "redeemable"
        assert (await db.staff_incentives.find_one({"id": reg_c}))["status"] == "pending"

        misses = await db.staff_attribution_misses.find(
            {"bill_id": bill_id}, {"_id": 0}).to_list(10)
        assert len(misses) == 1, f"Expected exactly 1 miss row, got {misses}"
        assert misses[0]["staff_id"] == sid_c
        assert misses[0]["reason"] == "registration_activation_brand_mismatch"

    _run(run())


# ---------------- Scenario 4: no attribution → lazy bill_doc fetch ----------------
def test_s4_no_attribution_lazy_bill_doc_mismatch(db):
    from routes.staff import create_or_activate_bill_incentive

    async def run():
        cust = _phone()
        sid_a, code_a = await _seed_staff(db, "Brand Alpha", "A")
        reg_id = await _seed_pending_registration(db, cust, sid_a, code_a)
        bill_id = await _seed_bill(db, cust, "Brand Delta")

        # No attribution at all → step 1 skipped entirely
        await create_or_activate_bill_incentive(bill_id, cust, "approved", 1200.0)

        assert (await db.staff_incentives.find_one({"id": reg_id}))["status"] == "pending"
        miss = await db.staff_attribution_misses.find_one(
            {"bill_id": bill_id, "reason": "registration_activation_brand_mismatch"})
        assert miss is not None, "lazy bill_doc fetch should still produce a miss row"
        assert miss["bill_brand"] == "Brand Delta"
        # no bill_upload incentive since no attribution
        assert await db.staff_incentives.find_one({"bill_id": bill_id, "type": "bill_upload"}) is None

    _run(run())


def test_s4b_no_attribution_lazy_bill_doc_match(db):
    from routes.staff import create_or_activate_bill_incentive

    async def run():
        cust = _phone()
        sid_a, code_a = await _seed_staff(db, "Brand Echo", "A")
        reg_id = await _seed_pending_registration(db, cust, sid_a, code_a)
        bill_id = await _seed_bill(db, cust, "Brand Echo")

        await create_or_activate_bill_incentive(bill_id, cust, "approved", 1200.0)

        assert (await db.staff_incentives.find_one({"id": reg_id}))["status"] == "redeemable"
        assert await db.staff_attribution_misses.find_one({"bill_id": bill_id}) is None

    _run(run())


def test_s4c_missing_bill_doc_does_not_crash(db):
    """Bill row absent (edge) → no brand → nothing activates, miss row logged."""
    from routes.staff import create_or_activate_bill_incentive

    async def run():
        cust = _phone()
        sid_a, code_a = await _seed_staff(db, "Brand Foxtrot", "A")
        reg_id = await _seed_pending_registration(db, cust, sid_a, code_a)
        ghost_bill = f"{PREFIX}ghost_{uuid.uuid4().hex[:6]}"

        await create_or_activate_bill_incentive(ghost_bill, cust, "approved", 0.0)

        assert (await db.staff_incentives.find_one({"id": reg_id}))["status"] == "pending"
        miss = await db.staff_attribution_misses.find_one({"bill_id": ghost_bill})
        assert miss is not None
        await db.staff_attribution_misses.delete_many({"bill_id": ghost_bill})

    _run(run())


# ---------------- Scenario 5: interim status then approval ----------------
def test_s5_pending_review_then_approved(db):
    from routes.staff import create_or_activate_bill_incentive

    async def run():
        cust = _phone()
        sid_a, code_a = await _seed_staff(db, "Brand Golf", "A")
        reg_id = await _seed_pending_registration(db, cust, sid_a, code_a)
        await _seed_attribution(db, cust, sid_a, code_a)
        bill_id = await _seed_bill(db, cust, "Brand Golf", status="pending_review")

        # interim status → nothing activates
        await create_or_activate_bill_incentive(bill_id, cust, "pending_review", 800.0)
        assert (await db.staff_incentives.find_one({"id": reg_id}))["status"] == "pending"
        credit = await db.staff_incentives.find_one(
            {"bill_id": bill_id, "type": "bill_upload"}, {"_id": 0})
        assert credit is not None and credit["status"] == "pending_verification"
        assert await db.staff_attribution_misses.find_one({"bill_id": bill_id}) is None

        # now approved
        await db.bills.update_one({"id": bill_id}, {"$set": {"status": "approved"}})
        await create_or_activate_bill_incentive(bill_id, cust, "approved", 800.0)
        assert (await db.staff_incentives.find_one({"id": reg_id}))["status"] == "redeemable"
        # no duplicate bill_upload credit
        n = await db.staff_incentives.count_documents({"bill_id": bill_id, "type": "bill_upload"})
        assert n == 1, f"Duplicate bill_upload credits: {n}"

    _run(run())


def test_s5b_rejected_bill_never_activates(db):
    from routes.staff import create_or_activate_bill_incentive

    async def run():
        cust = _phone()
        sid_a, code_a = await _seed_staff(db, "Brand Hotel", "A")
        reg_id = await _seed_pending_registration(db, cust, sid_a, code_a)
        bill_id = await _seed_bill(db, cust, "Brand Hotel", status="rejected")

        await create_or_activate_bill_incentive(bill_id, cust, "rejected", 500.0)
        assert (await db.staff_incentives.find_one({"id": reg_id}))["status"] == "pending"
        assert await db.staff_attribution_misses.find_one({"bill_id": bill_id}) is None

    _run(run())


# ---------------- Regression: Point 14 bill_upload brand match ----------------
def test_regression_point14_bill_upload_mismatch_consumes_attribution(db):
    from routes.staff import create_or_activate_bill_incentive

    async def run():
        cust = _phone()
        sid_a, code_a = await _seed_staff(db, "Brand India", "A")
        await _seed_attribution(db, cust, sid_a, code_a)
        bill_id = await _seed_bill(db, cust, "Brand Juliet")

        await create_or_activate_bill_incentive(bill_id, cust, "approved", 1000.0)

        assert await db.staff_incentives.find_one({"bill_id": bill_id}) is None, \
            "No bill_upload credit expected on brand mismatch"
        attr = await db.staff_attributions.find_one({"customer_phone": cust}, {"_id": 0})
        assert attr and attr["used"] is True, "Attribution must be consumed even on mismatch"
        miss = await db.staff_attribution_misses.find_one(
            {"bill_id": bill_id, "reason": "brand_mismatch"})
        assert miss is not None, "Point 14 brand_mismatch miss row still expected"

    _run(run())
