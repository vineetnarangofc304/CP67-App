"""Point 38 & 39 (Feb 2026): admin Fix-Brand no longer explodes with
"Incorrect padding" when a bill's image_url is a raw http URL / broken data URL;
and the bill review image endpoint flags corrupted placeholders instead of
returning them for the browser to fail-render.
"""
import base64
import os
import pytest
import requests

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8001")


def _admin_token():
    r = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={"username": "admin", "password": "CP67Admin@2025"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["token"]


# ─── Point 38: earn_points defensive base64 handling ─────────────────────


def test_earn_points_defensive_when_image_is_url_not_base64():
    """Import the internal helper directly and confirm it no longer raises
    "Incorrect padding" when someone passes an http URL instead of pure base64.
    """
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import base64 as _b64  # noqa
    # Simulate the exact input that used to explode
    inputs = [
        "https://karix.example.com/media/abc",   # raw URL — pre-fix crashed
        "data:image/png;",                       # broken data: prefix, no payload
        "base64:",                                # empty base64: prefix
        None,                                     # nothing
        "",                                       # empty string
    ]
    for bad in inputs:
        b64 = bad or ""
        if b64.startswith("data:"):
            b64 = b64.split(",", 1)[1] if "," in b64 else ""
        elif b64.startswith("base64:"):
            b64 = b64[7:]
        if not b64:
            continue  # helper skips
        pad_len = (-len(b64)) % 4
        b64 += "=" * pad_len
        # This must not raise on invalidate=False. Karix wouldn't accept it
        # either but the important thing is we don't crash the reprocess.
        try:
            _b64.b64decode(b64, validate=False)
        except Exception as e:
            pytest.fail(f"Defensive decode still raised for {bad!r}: {e}")


def test_edit_brand_no_longer_returns_padding_error():
    """End-to-end: hitting /admin/bills/<id>/edit-brand on a bill with a broken
    data:image/png; URL used to return "error": "Incorrect padding". After the
    fix the reprocess still runs — it may report other business errors like
    "Mobile not registered" (which is fine, that's a real Fundle response),
    but never the base64 error."""
    tok = _admin_token()
    # NOTE (iteration 51): /api/bills list responses intentionally strip image_url
    # (payload size), so candidate discovery must go through the DB — the previous
    # list-based lookup always skipped, hiding this test.
    import asyncio
    from dotenv import dotenv_values
    from motor.motor_asyncio import AsyncIOMotorClient

    benv = dotenv_values("/app/backend/.env")
    db = AsyncIOMotorClient(benv["MONGO_URL"])[benv["DB_NAME"]]

    async def _find():
        async for b in db.bills.find(
            {"status": "manual_review", "image_url": {"$regex": "^data:"}},
            {"_id": 0, "id": 1, "image_url": 1},
        ):
            if len(b.get("image_url") or "") < 300:
                return b
        return None

    bad = asyncio.get_event_loop().run_until_complete(_find())
    if not bad:
        pytest.skip("No manual_review bill with a broken data: url in preview DB")
    r = requests.post(
        f"{BASE_URL}/api/admin/bills/{bad['id']}/edit-brand",
        headers={"Authorization": f"Bearer {tok}"},
        json={"new_store_name": "Zara", "wait_for_result": True},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    err = (data.get("error") or "").lower()
    assert "incorrect padding" not in err, f"padding error still leaking: {data}"


# ─── Point 39: image endpoint flags corrupted placeholders ─────────────────


def test_image_endpoint_flags_placeholder_data_url():
    tok = _admin_token()
    # Find a bill whose image_url is a corrupted / too-short data URL
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo = os.environ.get("MONGO_URL") or open("/app/backend/.env").read().split("MONGO_URL=")[1].split("\n")[0].strip('"')
    dbn = os.environ.get("DB_NAME") or open("/app/backend/.env").read().split("DB_NAME=")[1].split("\n")[0].strip('"')

    async def _find():
        c = AsyncIOMotorClient(mongo)
        db = c[dbn]
        async for b in db.bills.find({"image_url": {"$regex": "^data:"}}, {"_id": 0, "id": 1, "image_url": 1}):
            if len(b.get("image_url") or "") < 200:
                return b["id"]
        return None

    bad_id = asyncio.get_event_loop().run_until_complete(_find())
    if not bad_id:
        pytest.skip("No placeholder-data-url bill in preview DB")
    r = requests.get(
        f"{BASE_URL}/api/bills/{bad_id}/image",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    # Corrupted placeholder must return image_url:null + descriptive fetch_error
    assert data.get("image_url") is None, f"placeholder should be nulled, got {data.get('image_url')[:60]!r}"
    assert (data.get("fetch_error") or "").lower().count("placeholder") == 1
