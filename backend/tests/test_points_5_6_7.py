"""Backend tests for Points 5, 6, 7 (iteration 38).

Coverage:
- GET /api/admin/staff/catalog/brands-categories
- GET /api/admin/staff/catalog/brand-category-mapping/template.csv
- POST /api/admin/staff/catalog/brand-category-mapping (dry_run + live)
- PUT /api/admin/staff/config/current with "__ALL__" category key round-trip
- Invalid/expired admin JWT returns 401 with detail='Invalid token'
"""
import io
import os
import uuid
import pytest
import requests
from pathlib import Path


def _load_backend_url() -> str:
    env_val = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if env_val:
        return env_val.rstrip("/")
    fe_env = Path("/app/frontend/.env")
    if fe_env.exists():
        for line in fe_env.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    return ""


BASE_URL = _load_backend_url()
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
ADMIN_USER = "admin"
ADMIN_PASS = "CP67Admin@2025"

TEST_TAG = f"TEST_{uuid.uuid4().hex[:8].upper()}"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"No token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ------------ Point 7 tests ------------

def test_catalog_brands_categories(auth_headers):
    r = requests.get(f"{BASE_URL}/api/admin/staff/catalog/brands-categories",
                     headers=auth_headers, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "brands" in body and isinstance(body["brands"], list)
    assert "categories" in body and isinstance(body["categories"], list)
    # Should include real data from the brands collection (typically seeded)
    assert len(body["brands"]) > 0, "Expected at least one brand in catalog"
    for b in body["brands"]:
        assert "brand_name" in b
        assert "category" in b
    # Categories must be sorted (case-insensitive)
    lower = [c.lower() for c in body["categories"]]
    assert lower == sorted(lower), "Categories not sorted case-insensitive"


def test_mapping_template_csv(auth_headers):
    r = requests.get(f"{BASE_URL}/api/admin/staff/catalog/brand-category-mapping/template.csv",
                     headers=auth_headers, timeout=30)
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers.get("content-type", "")
    first_line = r.text.splitlines()[0]
    assert first_line.strip() == "Brand Name,Brand Category", f"Unexpected header: {first_line}"


def test_mapping_upload_dry_run_then_live(auth_headers):
    # Prepare CSV with 1 update (Zara) + 1 new brand (TEST_)
    new_brand = f"{TEST_TAG}_BrandX"
    csv_body = f"Brand Name,Brand Category\nZara,Fashion\n{new_brand},TestCategory\n".encode()
    files = {"file": ("mapping.csv", io.BytesIO(csv_body), "text/csv")}

    # DRY RUN
    r = requests.post(f"{BASE_URL}/api/admin/staff/catalog/brand-category-mapping",
                      headers=auth_headers, files=files, data={"dry_run": "true"}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["dry_run"] is True
    assert body["summary"]["created"] >= 1  # our new TEST brand should be a "create"
    # Should not have persisted new brand yet
    r2 = requests.get(f"{BASE_URL}/api/admin/staff/catalog/brands-categories",
                      headers=auth_headers, timeout=30)
    names = {b["brand_name"] for b in r2.json()["brands"]}
    assert new_brand not in names, "Dry-run should not have written new brand"

    # LIVE upload
    files = {"file": ("mapping.csv", io.BytesIO(csv_body), "text/csv")}
    r = requests.post(f"{BASE_URL}/api/admin/staff/catalog/brand-category-mapping",
                      headers=auth_headers, files=files, data={"dry_run": "false"}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["dry_run"] is False

    # Confirm new brand appears now
    r3 = requests.get(f"{BASE_URL}/api/admin/staff/catalog/brands-categories",
                      headers=auth_headers, timeout=30)
    brands = r3.json()["brands"]
    match = [b for b in brands if b["brand_name"] == new_brand]
    assert match, f"New brand {new_brand} not present after live upload"
    assert match[0]["category"] == "TestCategory"


def test_mapping_upload_missing_columns(auth_headers):
    bad = b"Foo,Bar\nZara,Fashion\n"
    files = {"file": ("bad.csv", io.BytesIO(bad), "text/csv")}
    r = requests.post(f"{BASE_URL}/api/admin/staff/catalog/brand-category-mapping",
                      headers=auth_headers, files=files, data={"dry_run": "true"}, timeout=30)
    assert r.status_code == 400
    assert "Brand Name" in r.text


# ------------ __ALL__ slab round-trip ------------

def test_all_scope_category_slabs_round_trip(auth_headers):
    # Fetch current config first
    r = requests.get(f"{BASE_URL}/api/admin/staff/config/current",
                     headers=auth_headers, timeout=30)
    assert r.status_code == 200
    cur = r.json()["config"]
    orig_cat = cur.get("category_slabs") or {}

    # Merge in __ALL__ override
    new_cat = dict(orig_cat)
    new_cat["__ALL__"] = {
        "registration_slabs": [{"min": 0, "max": 10, "amount": 5}],
        "bill_upload_slabs": [{"min": 0, "max": 10, "amount": 7}],
    }
    r = requests.put(f"{BASE_URL}/api/admin/staff/config/current",
                     headers=auth_headers, json={"category_slabs": new_cat}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    cat_after = body["config"].get("category_slabs") or {}
    assert "__ALL__" in cat_after, f"__ALL__ key missing after PUT: {list(cat_after.keys())}"
    assert cat_after["__ALL__"]["registration_slabs"][0]["amount"] == 5
    assert cat_after["__ALL__"]["bill_upload_slabs"][0]["amount"] == 7

    # Second GET to verify persistence
    r = requests.get(f"{BASE_URL}/api/admin/staff/config/current",
                     headers=auth_headers, timeout=30)
    assert r.status_code == 200
    persisted = r.json()["config"].get("category_slabs") or {}
    assert "__ALL__" in persisted

    # Cleanup: restore original
    requests.put(f"{BASE_URL}/api/admin/staff/config/current",
                 headers=auth_headers, json={"category_slabs": orig_cat}, timeout=30)


# ------------ Point 6: 401 semantics ------------

@pytest.mark.parametrize("endpoint", [
    "/api/admin/staff/catalog/brands-categories",
    "/api/admin/staff/catalog/brand-category-mapping/template.csv",
    "/api/admin/staff/config/current",
])
def test_invalid_token_returns_401(endpoint):
    r = requests.get(f"{BASE_URL}{endpoint}",
                     headers={"Authorization": "Bearer garbage.jwt.here"}, timeout=30)
    assert r.status_code == 401, f"Expected 401, got {r.status_code} for {endpoint}"
    try:
        body = r.json()
        # detail should be 'Invalid token'
        assert body.get("detail") == "Invalid token", f"Unexpected detail: {body}"
    except ValueError:
        pytest.fail(f"Response not JSON for {endpoint}: {r.text[:200]}")


# ------------ Cleanup ------------

def test_cleanup_created_test_brands(auth_headers):
    """Remove any TEST_ prefixed brand rows inserted by earlier tests via mongo helper.

    Since we don't have a delete-brand endpoint here, we call the pre-existing admin
    brand delete API if it exists; otherwise skip cleanup (best-effort)."""
    # Try common admin brand endpoints
    r = requests.get(f"{BASE_URL}/api/admin/staff/catalog/brands-categories",
                     headers=auth_headers, timeout=30)
    if r.status_code != 200:
        pytest.skip("Cannot list brands for cleanup")
    to_delete = [b for b in r.json()["brands"] if b["brand_name"].startswith(TEST_TAG)]
    if not to_delete:
        return
    # Attempt cleanup via /api/admin/brands/{id} if such endpoint exists — best effort
    for b in to_delete:
        # Look up brand id via full brand list endpoint
        rr = requests.get(f"{BASE_URL}/api/admin/brands", headers=auth_headers, timeout=30)
        if rr.status_code == 200:
            for full in rr.json() if isinstance(rr.json(), list) else rr.json().get("brands", []):
                if full.get("brand_name") == b["brand_name"]:
                    bid = full.get("id")
                    if bid:
                        requests.delete(f"{BASE_URL}/api/admin/brands/{bid}",
                                        headers=auth_headers, timeout=30)
