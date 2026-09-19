"""Point 19 + 20 (Sep 2026): brand aliases + no-attribution audit trail.

Point 19: Domino's staff QR scan → Domino's bill uploaded → no incentive.
Point 20: give admin scope to handle brand-name mismatches (aliases).

Solution: match brand names via aliases stored on the brand doc, and
always log an attribution_miss row (even when no attribution window
exists) so admins can diagnose why an incentive wasn't credited.
"""
import asyncio
from unittest.mock import patch, AsyncMock

from backend.routes.staff import _brand_alias_set, _brands_match


def test_brands_match_exact_normalised():
    async def run():
        # "Domino's" and "dominos" normalise to same key even without alias lookup
        with patch("backend.routes.staff._db") as mock_db:
            mock_db.brands.find_one = AsyncMock(return_value=None)
            assert await _brands_match("Domino's", "Dominos") is True
            assert await _brands_match("SUBWAY", "subway") is True
            assert await _brands_match("Apple  Store", "apple store") is True
    asyncio.run(run())


def test_brands_match_via_aliases():
    async def run():
        with patch("backend.routes.staff._db") as mock_db:
            # brand 'Dominos' has aliases including 'Dominos Pizza'
            mock_db.brands.find_one = AsyncMock(return_value={
                "brand_name": "Dominos",
                "aliases": ["Dominos Pizza", "Jubilant Foodworks"],
            })
            assert await _brands_match("Dominos", "Dominos Pizza") is True
            assert await _brands_match("Dominos Pizza", "Dominos") is True
            assert await _brands_match("Jubilant  Foodworks!", "Dominos") is True
    asyncio.run(run())


def test_brands_no_match_when_neither_alias_matches():
    async def run():
        with patch("backend.routes.staff._db") as mock_db:
            async def _lookup(q, *a, **k):
                # Regex-based lookup: return doc only if the anchored name matches
                pat = q.get("brand_name", {}).get("$regex", "")
                if "Dominos" in pat:
                    return {"brand_name": "Dominos", "aliases": ["Dominos Pizza"]}
                return None
            mock_db.brands.find_one = AsyncMock(side_effect=_lookup)
            assert await _brands_match("Dominos", "Pizza Hut") is False
    asyncio.run(run())


def test_brands_empty_inputs_return_false():
    async def run():
        assert await _brands_match("", "Dominos") is False
        assert await _brands_match("Dominos", "") is False
        assert await _brands_match("", "") is False
    asyncio.run(run())


def test_alias_set_includes_own_name_and_aliases():
    async def run():
        with patch("backend.routes.staff._db") as mock_db:
            mock_db.brands.find_one = AsyncMock(return_value={
                "brand_name": "Subway",
                "aliases": ["SUBWAY India", "Subway Sandwiches"],
            })
            s = await _brand_alias_set("Subway")
            assert "subway" in s
            assert "subwayindia" in s
            assert "subwaysandwiches" in s
    asyncio.run(run())


def test_alias_set_survives_missing_brand():
    async def run():
        with patch("backend.routes.staff._db") as mock_db:
            mock_db.brands.find_one = AsyncMock(return_value=None)
            s = await _brand_alias_set("UnknownBrand")
            # Only the raw input's normalised form is present
            assert s == {"unknownbrand"}
    asyncio.run(run())
