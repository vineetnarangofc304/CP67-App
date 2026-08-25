"""Seed helper for iteration 53: creates registration + bill_upload incentives
so the Point 12 report endpoint & Reports tab UI have visible data."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    print("counts before:",
          await db.staff_incentives.count_documents({}),
          await db.retail_staff.count_documents({}))
    for c in ("registration", "bill_upload"):
        print(c, await db.staff_incentives.count_documents({"type": c}))

    staff = await db.retail_staff.find_one({"is_active": True}, {"_id": 0})
    if not staff:
        sid = f"TEST_staff_{uuid.uuid4().hex[:8]}"
        staff = {
            "id": sid, "staff_code": "HL-QA53", "name": "TEST_QA Staff",
            "phone": "9800000053", "brand_name": "Nike", "brand_category": "Footwear",
            "store_location": "GF-12", "is_active": True,
            "qr_token": uuid.uuid4().hex[:8].upper(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.retail_staff.insert_one(dict(staff))
    print("using staff", staff["id"], staff.get("brand_name"))

    now = datetime.now(timezone.utc).isoformat()
    reg_id = f"TEST_inc_{uuid.uuid4().hex[:8]}"
    await db.staff_incentives.insert_one({
        "id": reg_id, "staff_id": staff["id"], "staff_code": staff["staff_code"],
        "customer_phone": "9811100053", "type": "registration", "status": "redeemable",
        "amount": 10, "created_at": now, "approved_at": now,
    })

    bill_id = f"TEST_bill_{uuid.uuid4().hex[:8]}"
    await db.bills.insert_one({
        "id": bill_id, "user_phone": "9811100054", "amount": 3200,
        "store_name": staff.get("brand_name"), "bill_no": "QA53-001",
        "status": "auto_approved", "created_at": now,
    })
    up_id = f"TEST_inc_{uuid.uuid4().hex[:8]}"
    await db.staff_incentives.insert_one({
        "id": up_id, "staff_id": staff["id"], "staff_code": staff["staff_code"],
        "customer_phone": "9811100054", "type": "bill_upload", "status": "redeemable",
        "amount": 25, "bill_id": bill_id, "bill_value": 3200,
        "bill_brand": staff.get("brand_name"), "created_at": now, "approved_at": now,
    })
    print("seeded", reg_id, up_id, bill_id)


asyncio.run(main())
