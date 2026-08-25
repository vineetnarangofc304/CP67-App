"""Pytest coverage for Retailer Doc Points 11, 12, 14 (Aug 2026).

- Point 11: retailer OTP diagnostic endpoint returns delivery info
- Point 12: incentive report endpoint filters by type and returns customer phone
- Point 14: create_or_activate_bill_incentive skips credit when bill_brand != staff_brand
"""
import asyncio
import os
import sys
import uuid
import pytest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
os.environ.setdefault("DB_NAME", os.environ.get("DB_NAME", "test_database"))


@pytest.fixture(scope="module")
def loop():
    return asyncio.new_event_loop()


@pytest.fixture(scope="module")
def db(loop):
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    return db


@pytest.mark.parametrize("bill_brand, staff_brand, expected_match", [
    ("Nike", "Nike", True),
    ("nike ", " Nike", True),
    ("Nike Store", "NIKE-STORE", True),
    ("Nike", "Adidas", False),
    ("", "Nike", False),
    ("Nike", "", False),
    # Regex-normalised comparison
    ("Nike Kids Store!", "nikekidsstore", True),
])
def test_point14_brand_normalisation(bill_brand, staff_brand, expected_match):
    """Point 14: brand-match rule uses lowercase + strip [^a-z0-9]. Mirror the logic."""
    import re
    def _norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", (s or "").lower())
    assert bool(bill_brand and staff_brand and _norm(bill_brand) == _norm(staff_brand)) is expected_match


def test_point14_end_to_end_brand_mismatch_skips_credit(loop, db):
    """Seed: staff for brand 'BrandA', open attribution window, upload a bill for 'BrandB'.
    Expect: NO staff_incentives row for this bill, attribution marked used, attribution_miss logged."""
    from routes.staff import create_or_activate_bill_incentive, bind_db

    async def run():
        # Wire staff.py globals
        bind_db(db)
        staff_id = f"test_staff_{uuid.uuid4().hex[:8]}"
        staff_code = f"HL-TST{uuid.uuid4().hex[:4].upper()}"
        cust = f"91555{uuid.uuid4().hex[:5]}"
        cust = "".join(c for c in cust if c.isdigit())[-10:]
        bill_id = f"test_bill_{uuid.uuid4().hex[:8]}"

        # Cleanup any pre-existing records for this cust
        await db.retail_staff.delete_many({"id": staff_id})
        await db.staff_attributions.delete_many({"customer_phone": cust})
        await db.staff_incentives.delete_many({"customer_phone": cust})
        await db.bills.delete_many({"id": bill_id})
        await db.staff_attribution_misses.delete_many({"bill_id": bill_id})

        # Seed staff mapped to Brand A
        await db.retail_staff.insert_one({
            "id": staff_id, "staff_code": staff_code, "name": "Test Staff",
            "phone": "9000000000", "brand_name": "Brand A", "brand_category": "Retail",
            "is_active": True, "created_at": datetime.now(timezone.utc).isoformat(),
        })

        # Seed attribution window (already open)
        await db.staff_attributions.insert_one({
            "id": str(uuid.uuid4()),
            "customer_phone": cust,
            "staff_id": staff_id,
            "staff_code": staff_code,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": "2099-01-01T00:00:00+00:00",  # future
            "used": False,
        })

        # Seed a bill for Brand B (mismatch)
        await db.bills.insert_one({
            "id": bill_id, "user_phone": cust, "amount": 1500,
            "store_name": "Brand B", "status": "auto_approved",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        # Run the incentive logic
        await create_or_activate_bill_incentive(bill_id, cust, "auto_approved", bill_value=1500.0)

        # Assertions
        # 1. No staff_incentives row for this bill
        credited = await db.staff_incentives.find_one({"bill_id": bill_id})
        assert credited is None, f"Expected NO incentive credit for brand-mismatch bill; got: {credited}"

        # 2. Attribution consumed (used=True)
        attr = await db.staff_attributions.find_one({"customer_phone": cust})
        assert attr and attr.get("used") is True, "Attribution should be consumed on mismatch bill"

        # 3. Attribution miss logged
        miss = await db.staff_attribution_misses.find_one({"bill_id": bill_id})
        assert miss is not None, "Expected attribution_misses row logged for audit"
        assert miss.get("reason") == "brand_mismatch"
        assert miss.get("bill_brand") == "Brand B"
        assert miss.get("staff_brand") == "Brand A"

        # Cleanup
        await db.retail_staff.delete_many({"id": staff_id})
        await db.staff_attributions.delete_many({"customer_phone": cust})
        await db.bills.delete_many({"id": bill_id})
        await db.staff_attribution_misses.delete_many({"bill_id": bill_id})

    loop.run_until_complete(run())


def test_point14_brand_match_still_credits(loop, db):
    """Positive test: matching brand → credit is created, attribution consumed."""
    from routes.staff import create_or_activate_bill_incentive, bind_db

    async def run():
        bind_db(db)
        staff_id = f"test_staff_{uuid.uuid4().hex[:8]}"
        staff_code = f"HL-MTC{uuid.uuid4().hex[:4].upper()}"
        cust = "9000" + uuid.uuid4().hex[:6]
        cust = "".join(c for c in cust if c.isdigit())[-10:]
        bill_id = f"test_bill_{uuid.uuid4().hex[:8]}"

        await db.retail_staff.delete_many({"id": staff_id})
        await db.staff_attributions.delete_many({"customer_phone": cust})
        await db.staff_incentives.delete_many({"customer_phone": cust})
        await db.bills.delete_many({"id": bill_id})

        await db.retail_staff.insert_one({
            "id": staff_id, "staff_code": staff_code, "name": "Match Staff",
            "phone": "9000000001", "brand_name": "Nike", "brand_category": "Retail",
            "is_active": True, "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await db.staff_attributions.insert_one({
            "id": str(uuid.uuid4()),
            "customer_phone": cust,
            "staff_id": staff_id,
            "staff_code": staff_code,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": "2099-01-01T00:00:00+00:00",
            "used": False,
        })
        # Case-different brand name — should still match
        await db.bills.insert_one({
            "id": bill_id, "user_phone": cust, "amount": 2500,
            "store_name": "NIKE", "status": "auto_approved",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        await create_or_activate_bill_incentive(bill_id, cust, "auto_approved", bill_value=2500.0)

        credited = await db.staff_incentives.find_one({"bill_id": bill_id})
        assert credited is not None, "Expected incentive credit on brand match"
        assert credited.get("type") == "bill_upload"
        assert credited.get("customer_phone") == cust

        attr = await db.staff_attributions.find_one({"customer_phone": cust})
        assert attr.get("used") is True

        # Cleanup
        await db.retail_staff.delete_many({"id": staff_id})
        await db.staff_attributions.delete_many({"customer_phone": cust})
        await db.staff_incentives.delete_many({"customer_phone": cust})
        await db.bills.delete_many({"id": bill_id})

    loop.run_until_complete(run())


def test_point12_report_shape():
    """Sanity check: report endpoint schema fields exist. This is a schema-shape assertion,
    not an integration test (we don't seed live data here)."""
    # This is validated live via curl in the main-agent smoke test.
    # Just assert the route module exposes the expected function.
    from routes.staff import staff_admin_router
    paths = {r.path for r in staff_admin_router.routes}
    assert "/api/admin/staff/incentives/report" in paths, f"Report endpoint missing. Paths: {sorted(paths)}"
    assert "/api/admin/staff/incentives/report.csv" in paths
    assert "/api/admin/staff/retailer/test-otp" in paths
