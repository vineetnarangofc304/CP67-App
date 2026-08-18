"""Tests for CP67 Points 8 & 9:

Point 8: Registration incentive resolver — flat ₹ amount per brand category, with __ALL__ as universal fallback and legacy count-based slabs as final backstop.

Point 9: Bill-upload incentive resolver — ₹ reward picked from bill-VALUE slabs (min_value / max_value), per category with __ALL__ universal fallback and legacy count-based slabs as final backstop.
"""
import asyncio
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.staff import (  # noqa: E402
    _resolve_registration_amount,
    _resolve_bill_upload_amount,
    _amount_for_value_slab,
)


LEGACY_REG_SLABS = [
    {"min": 0, "max": 10, "amount": 50},
    {"min": 11, "max": 999999, "amount": 100},
]
LEGACY_UPL_SLABS = [
    {"min": 0, "max": 20, "amount": 20},
    {"min": 21, "max": 999999, "amount": 40},
]


class _FakeCollection:
    """Minimal async stub so the resolvers can look up brand → category without touching Mongo."""

    def __init__(self, mapping):
        # mapping: {brand_name_lower: category}
        self._mapping = mapping

    async def find_one(self, query, projection=None):
        # very small subset: matches "brand_name" case-insensitive regex
        target = None
        bn = query.get("brand_name")
        if isinstance(bn, dict) and "$regex" in bn:
            pattern = bn["$regex"]
            # strip anchors ^…$ and re.escape output
            key = pattern.strip("^$").lower().replace("\\", "")
            target = key
        elif isinstance(bn, str):
            target = bn.lower()
        if target and target in self._mapping:
            return {"category": self._mapping[target]}
        return None


class _FakeDB:
    def __init__(self, brands_mapping):
        self.brands = _FakeCollection(brands_mapping)


@pytest.fixture(autouse=True)
def patch_db(monkeypatch):
    # Point 35 brand catalog: Adidas → Fashion, Starbucks → Food, Unknown → not present
    fake = _FakeDB({"adidas": "Fashion", "starbucks": "Food"})
    import routes.staff as staff_mod

    monkeypatch.setattr(staff_mod, "_db", fake)
    yield


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── Point 8: registration_by_category ─────────────────────────────────────


def test_registration_category_specific_wins():
    """If the staff's brand maps to a category with a configured flat amount, use that."""
    cfg = {
        "registration_by_category": {"Fashion": 75, "__ALL__": 50},
        "registration_slabs": LEGACY_REG_SLABS,
    }
    staff = {"brand_name": "Adidas"}
    amt = _run(_resolve_registration_amount(cfg, staff, 0))
    assert amt == 75


def test_registration_all_fallback():
    """If category has no override but __ALL__ is set, use __ALL__."""
    cfg = {
        "registration_by_category": {"__ALL__": 50},
        "registration_slabs": LEGACY_REG_SLABS,
    }
    # Adidas → Fashion, but no Fashion key; falls back to __ALL__
    staff = {"brand_name": "Adidas"}
    amt = _run(_resolve_registration_amount(cfg, staff, 0))
    assert amt == 50


def test_registration_falls_back_to_legacy_slabs_when_map_empty():
    """When registration_by_category is empty, keep legacy count-based slabs (backward-compat)."""
    cfg = {
        "registration_by_category": {},
        "registration_slabs": LEGACY_REG_SLABS,
        "brand_slabs": {},
        "category_slabs": {},
    }
    staff = {"brand_name": "Adidas"}
    # count_so_far=5 → first slab bucket amount=50
    amt = _run(_resolve_registration_amount(cfg, staff, 5))
    assert amt == 50
    # count_so_far=15 → second slab bucket amount=100
    amt = _run(_resolve_registration_amount(cfg, staff, 15))
    assert amt == 100


def test_registration_unknown_brand_uses_all():
    cfg = {"registration_by_category": {"__ALL__": 42}}
    staff = {"brand_name": "SomeUnknownShop"}  # not in brand catalog
    amt = _run(_resolve_registration_amount(cfg, staff, 0))
    assert amt == 42


# ─── Point 9: bill_upload_value_slabs_by_category ─────────────────────────


def test_value_slab_helper_picks_correct_bucket():
    slabs = [
        {"min_value": 0, "max_value": 1000, "amount": 20},
        {"min_value": 1001, "max_value": 5000, "amount": 50},
        {"min_value": 5001, "max_value": 999999, "amount": 100},
    ]
    assert _amount_for_value_slab(500, slabs) == 20
    assert _amount_for_value_slab(1000, slabs) == 20   # inclusive upper bound
    assert _amount_for_value_slab(1001, slabs) == 50   # inclusive lower bound
    assert _amount_for_value_slab(4999, slabs) == 50
    assert _amount_for_value_slab(9999, slabs) == 100
    assert _amount_for_value_slab(0, slabs) == 20


def test_bill_upload_category_specific_wins():
    """Fashion bucket used for Adidas; ₹1500 bill → the 1001–5000 bucket."""
    cfg = {
        "bill_upload_value_slabs_by_category": {
            "Fashion": [
                {"min_value": 0, "max_value": 1000, "amount": 30},
                {"min_value": 1001, "max_value": 999999, "amount": 100},
            ],
            "__ALL__": [
                {"min_value": 0, "max_value": 999999, "amount": 20},
            ],
        },
        "bill_upload_slabs": LEGACY_UPL_SLABS,
    }
    staff = {"brand_name": "Adidas"}
    amt = _run(_resolve_bill_upload_amount(cfg, staff, 1500, 0))
    assert amt == 100
    amt_low = _run(_resolve_bill_upload_amount(cfg, staff, 500, 0))
    assert amt_low == 30


def test_bill_upload_all_universal_fallback():
    """No Fashion bucket → falls to __ALL__."""
    cfg = {
        "bill_upload_value_slabs_by_category": {
            "__ALL__": [
                {"min_value": 0, "max_value": 1000, "amount": 25},
                {"min_value": 1001, "max_value": 999999, "amount": 75},
            ]
        },
        "bill_upload_slabs": LEGACY_UPL_SLABS,
    }
    staff = {"brand_name": "Adidas"}  # Fashion category, but only __ALL__ configured
    amt = _run(_resolve_bill_upload_amount(cfg, staff, 800, 0))
    assert amt == 25
    amt_hi = _run(_resolve_bill_upload_amount(cfg, staff, 2000, 0))
    assert amt_hi == 75


def test_bill_upload_falls_back_to_legacy_when_empty():
    """No value-slabs configured → legacy count-based slabs."""
    cfg = {
        "bill_upload_value_slabs_by_category": {},
        "bill_upload_slabs": LEGACY_UPL_SLABS,
        "brand_slabs": {},
        "category_slabs": {},
    }
    staff = {"brand_name": "Adidas"}
    # count_so_far=10 -> first bucket (0..20) amount 20
    amt = _run(_resolve_bill_upload_amount(cfg, staff, 999, 10))
    assert amt == 20
    # count_so_far=30 -> second bucket (21..∞) amount 40
    amt = _run(_resolve_bill_upload_amount(cfg, staff, 999, 30))
    assert amt == 40
