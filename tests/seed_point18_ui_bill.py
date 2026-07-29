#!/usr/bin/env python3
"""Seed one pending_review bill for the Point 18 admin Bills UI reprocess test."""
import asyncio
import base64
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path("/app")
load_dotenv(ROOT / "backend" / ".env")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "test_database")
OUT = Path("/app/test_reports/point18_ui_seed.json")
TINY_PNG = "data:image/png;base64," + base64.b64encode(
    base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=")
).decode()


def iso_now():
    return datetime.now(timezone.utc).isoformat()


async def main():
    run_id = "p18ui_" + uuid.uuid4().hex[:8]
    user_id = "user_" + run_id
    bill_id = "bill_" + run_id
    phone = "91" + str(7100000000 + int(uuid.uuid4().int % 89999999))[-10:]
    bill_no = "P18UI-" + uuid.uuid4().hex[:8]
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db.users.insert_one({
        "id": user_id,
        "phone": phone,
        "name": "QA Point18 UI",
        "loyalty_id": "QA" + uuid.uuid4().hex[:8],
        "customer_type": "new",
        "balance_points": 0,
        "total_earned_points": 0,
        "created_at": iso_now(),
        "registration_time": iso_now(),
        "kyc_status": False,
        "fundle_registered": False,
    })
    await db.bills.insert_one({
        "id": bill_id,
        "user_id": user_id,
        "user_phone": phone,
        "store_name": "QA UI Unknown Brand P18",
        "bill_no": bill_no,
        "bill_no_normalized": "".join(ch.lower() for ch in bill_no if ch.isalnum()),
        "bill_date": datetime.now().strftime("%Y-%m-%d"),
        "amount": 1234.0,
        "tax": 0,
        "status": "pending_review",
        "points_issued": 0,
        "image_url": TINY_PNG,
        "image_hash": "hash_" + uuid.uuid4().hex,
        "ocr_confidence": 0.85,
        "ocr_raw_data": {"store_name": "QA UI Unknown Brand P18", "bill_no": bill_no, "amount": 1234, "is_valid_bill": True},
        "rejection_reason": "QA UI seeded unknown brand for Point 18 reprocess",
        "created_at": iso_now(),
    })
    data = {"run_id": run_id, "bill_id": bill_id, "user_id": user_id, "phone": phone}
    OUT.write_text(json.dumps(data, indent=2))
    print(json.dumps(data, indent=2))
    client.close()


if __name__ == "__main__":
    asyncio.run(main())