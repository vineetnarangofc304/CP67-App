"""Point 10: /admin/staff/catalog/brands-categories now returns staff_mapped_categories + staff_mapped_brands — the subsets that actually have retail staff mapped through brand → category.

We hit the live endpoint against the running backend so this doubles as an integration smoke.
"""
import os
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


def test_catalog_response_includes_staff_mapped_subsets():
    tok = _admin_token()
    r = requests.get(
        f"{BASE_URL}/api/admin/staff/catalog/brands-categories",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    assert "brands" in data and "categories" in data
    # New fields exist
    assert "staff_mapped_brands" in data
    assert "staff_mapped_categories" in data
    # Each staff-mapped brand must appear in the full brands list
    all_brands = {b["brand_name"].lower() for b in data["brands"]}
    for b in data["staff_mapped_brands"]:
        assert b.lower() in all_brands, f"staff_mapped brand '{b}' not in full brand list"
    # Each staff-mapped category must appear in the full categories list
    all_cats = {c.lower() for c in data["categories"]}
    for c in data["staff_mapped_categories"]:
        assert c.lower() in all_cats, f"staff_mapped category '{c}' not in full category list"
    # Subsets must be strictly ≤ superset
    assert len(data["staff_mapped_brands"]) <= len(data["brands"])
    assert len(data["staff_mapped_categories"]) <= len(data["categories"])
