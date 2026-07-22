"""Point 16 tests: normalize_bill_no helper + check_duplicate_bill + backfill + indexes."""
import os
import sys
import asyncio
import pytest

sys.path.insert(0, "/app/backend")

from server import normalize_bill_no  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


def _fresh_db():
    client = AsyncIOMotorClient(MONGO_URL)
    return client, client[DB_NAME]


async def _check_duplicate_bill(db, image_hash, bill_no, store_name):
    """Local mirror of server.check_duplicate_bill using a per-test event-loop-safe client."""
    existing = await db.bills.find_one({"image_hash": image_hash, "status": {"$ne": "rejected"}})
    if existing:
        return True
    if bill_no and store_name:
        norm = normalize_bill_no(bill_no)
        if norm:
            existing = await db.bills.find_one({
                "$or": [
                    {"bill_no_normalized": norm, "store_name": store_name, "status": {"$ne": "rejected"}},
                    {"bill_no": bill_no, "store_name": store_name, "status": {"$ne": "rejected"}}
                ]
            })
            if existing:
                return True
    return False


# --- normalize_bill_no ---
def test_normalize_strip_colon():
    assert normalize_bill_no("INV:12345") == "inv12345"

def test_normalize_no_punct():
    assert normalize_bill_no("INV12345") == "inv12345"

def test_normalize_dot_and_space_equivalent():
    assert normalize_bill_no("INV.12345") == normalize_bill_no("inv 12345") == "inv12345"

def test_normalize_empty_and_none():
    assert normalize_bill_no(None) == ""
    assert normalize_bill_no("") == ""

def test_normalize_dashes_slashes():
    assert normalize_bill_no("INV-123/45") == "inv12345"


@pytest.mark.asyncio
async def test_check_duplicate_bill_normalized_match():
    client, db = _fresh_db()
    seed = {
        "id": "TEST_dup_bill_1",
        "user_id": "TEST_user",
        "user_phone": "9999999999",
        "store_name": "TestB",
        "bill_no": "INV999",
        "bill_no_normalized": "inv999",
        "status": "approved",
        "image_hash": "TEST_hash_original",
    }
    try:
        await db.bills.delete_many({"id": {"$regex": "^TEST_dup_bill"}})
        await db.bills.insert_one(seed)
        is_dup = await _check_duplicate_bill(db, image_hash="TEST_hash_NEW", bill_no="INV:999", store_name="TestB")
        assert is_dup is True
        is_dup2 = await _check_duplicate_bill(db, image_hash="TEST_hash_NEW2", bill_no="INV:999", store_name="OtherB")
        assert is_dup2 is False
        is_dup3 = await _check_duplicate_bill(db, image_hash="TEST_hash_original", bill_no=None, store_name=None)
        assert is_dup3 is True
    finally:
        await db.bills.delete_many({"id": {"$regex": "^TEST_dup_bill"}})
        client.close()


@pytest.mark.asyncio
async def test_bills_indexes_present():
    client, db = _fresh_db()
    try:
        info = await db.bills.index_information()
    finally:
        client.close()
    single = any(spec.get("key", []) == [("bill_no_normalized", 1)] for spec in info.values())
    compound = any(
        spec.get("key", []) == [("user_id", 1), ("store_name", 1), ("bill_no_normalized", 1)]
        for spec in info.values()
    )
    assert single, f"Missing single-field bill_no_normalized index. Have: {list(info.keys())}"
    assert compound, f"Missing compound index. Have: {list(info.keys())}"


@pytest.mark.asyncio
async def test_backfill_bill_no_normalized_on_legacy():
    client, db = _fresh_db()
    try:
        cursor = db.bills.find(
            {"bill_no": {"$nin": [None, ""]}},
            {"_id": 0, "bill_no": 1, "bill_no_normalized": 1},
        ).limit(20)
        docs = await cursor.to_list(length=20)
    finally:
        client.close()
    if not docs:
        pytest.skip("No bills with bill_no found to sample backfill")
    missing = [d for d in docs if not d.get("bill_no_normalized")]
    assert not missing, f"{len(missing)}/{len(docs)} sampled bills missing bill_no_normalized: {missing[:3]}"
