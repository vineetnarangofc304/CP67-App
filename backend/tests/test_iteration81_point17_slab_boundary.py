"""Point 17: Rs 62 Subway bill wrongly returned Rs 80 (slabs top amount)
because `_amount_for_value_slab` silently fell back to slabs[-1].amount
when bill_value didn't fit any configured range. Fix returns 0 for
bill_value BELOW the lowest slab min, and only caps at top when above.
"""
from backend.routes.staff import _amount_for_value_slab


def test_below_floor_returns_zero_not_top_slab():
    slabs = [
        {"min_value": 100, "max_value": 500, "amount": 10},
        {"min_value": 501, "max_value": 1000, "amount": 30},
        {"min_value": 1001, "max_value": 5000, "amount": 80},
    ]
    assert _amount_for_value_slab(62, slabs) == 0
    assert _amount_for_value_slab(0, slabs) == 0
    assert _amount_for_value_slab(99.9, slabs) == 0


def test_in_range_returns_expected_amount():
    slabs = [
        {"min_value": 100, "max_value": 500, "amount": 10},
        {"min_value": 501, "max_value": 1000, "amount": 30},
        {"min_value": 1001, "max_value": 5000, "amount": 80},
    ]
    assert _amount_for_value_slab(100, slabs) == 10  # slab boundary
    assert _amount_for_value_slab(250, slabs) == 10
    assert _amount_for_value_slab(500, slabs) == 10  # upper boundary of slab 1
    assert _amount_for_value_slab(800, slabs) == 30
    assert _amount_for_value_slab(1500, slabs) == 80


def test_above_ceiling_caps_at_last_slab():
    slabs = [
        {"min_value": 100, "max_value": 500, "amount": 10},
        {"min_value": 501, "max_value": 1000, "amount": 30},
        {"min_value": 1001, "max_value": 5000, "amount": 80},
    ]
    assert _amount_for_value_slab(6000, slabs) == 80
    assert _amount_for_value_slab(99999, slabs) == 80


def test_slabs_starting_from_zero_still_credit_low_bills():
    slabs = [
        {"min_value": 0, "max_value": 100, "amount": 10},
        {"min_value": 101, "max_value": 500, "amount": 30},
    ]
    # Rs 62 with a 0-100 slab present should award 10, not fall through
    assert _amount_for_value_slab(62, slabs) == 10
    assert _amount_for_value_slab(0, slabs) == 10


def test_empty_slabs_returns_zero():
    assert _amount_for_value_slab(100, []) == 0
    assert _amount_for_value_slab(0, []) == 0
