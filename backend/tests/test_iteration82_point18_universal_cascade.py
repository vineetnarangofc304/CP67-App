"""Point 18 (Sep 2026): Subway ₹353 (Food Court) awarded ₹0 because the
category slabs didn't cover ₹353 and the code stopped at the category tier
instead of falling back to __ALL__. Fixed: cascade category → __ALL__ before
returning 0 or the ceiling-cap.
"""
import asyncio
from unittest.mock import patch, AsyncMock

from backend.routes.staff import (
    _amount_for_value_slab,
    _amount_for_value_slab_match,
    _resolve_bill_upload_amount,
)


def test_match_helper_returns_none_on_miss():
    slabs = [{"min_value": 500, "max_value": 1000, "amount": 20}]
    assert _amount_for_value_slab_match(353, slabs) is None
    assert _amount_for_value_slab_match(1500, slabs) is None
    assert _amount_for_value_slab_match(700, slabs) == 20


def test_match_helper_empty_slabs():
    assert _amount_for_value_slab_match(100, []) is None
    assert _amount_for_value_slab_match(100, None) is None


def test_amount_wrapper_preserves_point17_semantics():
    slabs = [{"min_value": 100, "max_value": 500, "amount": 10},
             {"min_value": 501, "max_value": 1000, "amount": 30}]
    assert _amount_for_value_slab(62, slabs) == 0
    assert _amount_for_value_slab(250, slabs) == 10
    assert _amount_for_value_slab(2000, slabs) == 30


def _resolve(cfg, staff, bill_value, category):
    with patch("backend.routes.staff._brand_category", new=AsyncMock(return_value=category)):
        return asyncio.run(_resolve_bill_upload_amount(cfg, staff, bill_value, upload_count=0))


def test_point18_cascade_category_miss_falls_back_to_universal():
    cfg = {
        "bill_upload_value_slabs_by_category": {
            "Food Court": [{"min_value": 500, "max_value": 1000, "amount": 20}],
            "__ALL__":    [{"min_value": 1,   "max_value": 500,  "amount": 10}],
        }
    }
    assert _resolve(cfg, {"brand_name": "Subway"}, 353, "Food Court") == 10


def test_point18_cascade_both_miss_returns_deepest_floor_zero():
    cfg = {
        "bill_upload_value_slabs_by_category": {
            "Food Court": [{"min_value": 500, "max_value": 1000, "amount": 20}],
            "__ALL__":    [{"min_value": 500, "max_value": 1000, "amount": 10}],
        }
    }
    assert _resolve(cfg, {"brand_name": "Subway"}, 353, "Food Court") == 0


def test_point18_category_hit_still_wins():
    cfg = {
        "bill_upload_value_slabs_by_category": {
            "Food Court": [{"min_value": 1, "max_value": 500, "amount": 20}],
            "__ALL__":    [{"min_value": 1, "max_value": 500, "amount": 10}],
        }
    }
    assert _resolve(cfg, {"brand_name": "Subway"}, 353, "Food Court") == 20


def test_point18_only_universal_still_works():
    cfg = {
        "bill_upload_value_slabs_by_category": {
            "__ALL__": [{"min_value": 1, "max_value": 500, "amount": 10}],
        }
    }
    assert _resolve(cfg, {"brand_name": "Subway"}, 353, "Food Court") == 10


def test_point18_category_above_ceiling_falls_to_universal():
    """Category has [1-500]; bill is ₹1500 → above category ceiling. Universal has
    [1-2000→50]. Expected: fall to universal → ₹50, not cap at category top."""
    cfg = {
        "bill_upload_value_slabs_by_category": {
            "Food Court": [{"min_value": 1, "max_value": 500, "amount": 20}],
            "__ALL__":    [{"min_value": 1, "max_value": 2000, "amount": 50}],
        }
    }
    assert _resolve(cfg, {"brand_name": "Subway"}, 1500, "Food Court") == 50

