"""Seed / cleanup a UI regression bill with a legitimate long data: image URL."""
import asyncio
import base64
import sys

from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

env = dotenv_values("/app/backend/.env")
db = AsyncIOMotorClient(env["MONGO_URL"])[env["DB_NAME"]]

BILL_ID = "TEST_i51_uigood"
# Real 8x8 red PNG (well over 200 chars once encoded with padding block)
PNG = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000080000000808020000004b6d29dc"
        "0000001a49444154789c63fccfc0f01f8419984a30fe0700a30d0b0b00fbdd05fd"
        "0f0f0f0f0000000049454e44ae426082"
    ) + b"\x00" * 300
).decode()
LONG_DATA_URL = "data:image/png;base64," + PNG


async def seed():
    await db.bills.delete_many({"id": BILL_ID})
    await db.bills.insert_one({
        "id": BILL_ID,
        "user_id": "TEST_i51_user",
        "user_phone": "919876543210",
        "bill_no": "TB-UIGOOD1",
        "bill_no_normalized": "tbuigood1",
        "store_name": "Zara",
        "amount": "777.0",
        "status": "manual_review",
        "created_at": "2026-07-02T00:00:00+00:00",
        "image_url": LONG_DATA_URL,
    })
    print("seeded", BILL_ID, "image len", len(LONG_DATA_URL))


async def cleanup():
    r = await db.bills.delete_many({"id": {"$regex": "^TEST_i51_"}})
    print("deleted", r.deleted_count)


asyncio.run(cleanup() if len(sys.argv) > 1 and sys.argv[1] == "cleanup" else seed())
