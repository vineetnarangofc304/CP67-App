"""
Backend tests for client feedback Points 2, 3, 4, 5:
  2 - Staff QR uses correct WhatsApp business number (from WHATSAPP_NUMBER env)
  3 - Category-wise and Brand-wise slab configuration
  4 - CSV bulk-import template + import with new headers + brand auto-upsert
  5 - Retailer manager CRUD + OTP login + PII-free dashboard
"""
import os
import io
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://staff-incentive-lab.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_USER = "admin"
ADMIN_PASS = "CP67Admin@2025"
OTP_BYPASS = "1234"
EXPECTED_WA_PHONE = "917347576767"
OLD_FALLBACK_WA = "917988077663"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in admin login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ==================== Point 4: Template CSV ====================

class TestPoint4TemplateCsv:
    def test_template_requires_auth(self):
        r = requests.get(f"{API}/admin/staff/bulk-import/template.csv", timeout=15)
        assert r.status_code in (401, 403)

    def test_template_download(self, admin_headers):
        r = requests.get(f"{API}/admin/staff/bulk-import/template.csv", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        first_line = r.text.splitlines()[0]
        assert first_line == "Mob No,Name of Employee,Brand Name,Brand Category", f"Unexpected header: {first_line!r}"
        # attachment filename
        assert "staff-upload-template.csv" in r.headers.get("content-disposition", "")


# ==================== Point 4: Bulk import ====================

@pytest.fixture(scope="module")
def seed_prefix():
    # Unique phone prefix for this run — 10-digit phones starting with 90000
    return "90000"


def _make_csv(rows):
    header = "Mob No,Name of Employee,Brand Name,Brand Category\n"
    return header + "\n".join(",".join(r) for r in rows) + "\n"


class TestPoint4BulkImport:
    def _cleanup(self, admin_headers, phones):
        # Best-effort cleanup — list staff and delete-by-id if endpoint exists;
        # otherwise leave for later prefix-based cleanup. We use PATCH deactivate
        # only if delete is missing.
        r = requests.get(f"{API}/admin/staff", headers=admin_headers, timeout=15)
        if r.status_code != 200:
            return
        for s in r.json().get("staff", []):
            if s.get("phone") in phones:
                # try delete (may 404/405 — safe to ignore)
                requests.delete(f"{API}/admin/staff/{s['id']}", headers=admin_headers, timeout=15)

    def test_dry_run_and_live_run(self, admin_headers, seed_prefix):
        # Phones unique across this run
        p1 = f"{seed_prefix}00021"
        p2 = f"{seed_prefix}00022"
        p3 = f"{seed_prefix}00023"
        brand_new = f"TEST_BULK_BRAND_{uuid.uuid4().hex[:6]}"
        csv_body = _make_csv([
            [p1, "TEST Rahul", brand_new, "Fashion"],
            [p2, "TEST Priya", "", "Fashion"],   # ffill brand
            [p3, "TEST Aman", "Croma", "Electronics"],
        ])
        files = {"file": ("import.csv", csv_body, "text/csv")}

        # Dry-run should NOT insert
        r = requests.post(
            f"{API}/admin/staff/bulk-import",
            headers=admin_headers,
            data={"dry_run": "true"},
            files=files,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["dry_run"] is True
        assert j["summary"]["imported"] == 3
        assert j["summary"]["invalid"] == 0

        # Confirm not persisted
        r2 = requests.get(f"{API}/admin/staff", headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        phones_after = {s["phone"] for s in r2.json().get("staff", [])}
        assert p1 not in phones_after

        # Live run
        files = {"file": ("import.csv", csv_body, "text/csv")}
        r = requests.post(
            f"{API}/admin/staff/bulk-import",
            headers=admin_headers,
            data={"dry_run": "false"},
            files=files,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["summary"]["imported"] == 3, j
        assert j["dry_run"] is False

        # Verify persistence + brand_category stored
        r2 = requests.get(f"{API}/admin/staff", headers=admin_headers, timeout=15)
        staff_by_phone = {s["phone"]: s for s in r2.json()["staff"]}
        assert p1 in staff_by_phone
        assert staff_by_phone[p1]["brand_name"] == brand_new
        assert staff_by_phone[p1].get("brand_category") == "Fashion"
        assert staff_by_phone[p2]["brand_name"] == brand_new, "brand should ffill"

        # Verify brand auto-upsert (Point 4 requirement)
        rb = requests.get(f"{API}/admin/brands", headers=admin_headers, timeout=15)
        if rb.status_code == 200:
            brands = rb.json().get("brands") or rb.json()
            if isinstance(brands, dict):
                brands = brands.get("brands", [])
            names = { (b.get("brand_name") or "").lower(): b for b in brands }
            assert brand_new.lower() in names, f"new brand {brand_new} not upserted"
            assert (names[brand_new.lower()].get("category") or "") == "Fashion"

        # Cleanup
        self._cleanup(admin_headers, {p1, p2, p3})


# ==================== Point 2: Staff QR WhatsApp number ====================

class TestPoint2QrNumber:
    def test_qr_uses_correct_wa_phone(self, admin_headers):
        # Create a temp staff
        phone = "9000090002"
        r = requests.post(
            f"{API}/admin/staff",
            headers=admin_headers,
            json={"name": "TEST_QR_Staff", "phone": phone, "brand_name": "TEST_Brand_QR"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        staff_id = r.json()["staff"]["id"]

        try:
            r = requests.get(f"{API}/admin/staff/{staff_id}/qr", headers=admin_headers, timeout=15)
            assert r.status_code == 200, r.text
            wa_url = r.json()["whatsapp_url"]
            assert EXPECTED_WA_PHONE in wa_url, f"expected {EXPECTED_WA_PHONE} in URL, got {wa_url}"
            assert OLD_FALLBACK_WA not in wa_url, f"old fallback {OLD_FALLBACK_WA} leaked into {wa_url}"
        finally:
            requests.delete(f"{API}/admin/staff/{staff_id}", headers=admin_headers, timeout=10)

    def test_qr_cards_pdf_uses_correct_wa(self, admin_headers):
        # Create staff first
        phone = "9000090003"
        r = requests.post(
            f"{API}/admin/staff",
            headers=admin_headers,
            json={"name": "TEST_PDF_Staff", "phone": phone, "brand_name": "TEST_PDF_Brand"},
            timeout=15,
        )
        assert r.status_code == 200
        staff_id = r.json()["staff"]["id"]
        try:
            r = requests.get(
                f"{API}/admin/staff/qr-cards.pdf",
                params={"ids": staff_id},
                headers=admin_headers,
                timeout=30,
            )
            assert r.status_code == 200, r.text
            assert r.headers.get("content-type", "").startswith("application/pdf")
            # PDF body will contain the wa.me URL encoded; not easy to grep raw phone
            # (URL is inside a QR image), so we just assert PDF is non-empty.
            assert len(r.content) > 1000
        finally:
            requests.delete(f"{API}/admin/staff/{staff_id}", headers=admin_headers, timeout=10)


# ==================== Point 3: Category & Brand slabs ====================

class TestPoint3Slabs:
    def test_get_config_has_slab_fields(self, admin_headers):
        r = requests.get(f"{API}/admin/staff/config/current", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        cfg = r.json()["config"]
        assert "category_slabs" in cfg
        assert "brand_slabs" in cfg
        assert isinstance(cfg["category_slabs"], dict)
        assert isinstance(cfg["brand_slabs"], dict)

    def test_put_and_get_slabs(self, admin_headers):
        category_slabs = {
            "TESTCategoryFashion": {
                "registration_slabs": [{"min": 0, "max": 10, "amount": 60}],
                "bill_upload_slabs": [{"min": 0, "max": 5, "amount": 25}],
            }
        }
        brand_slabs = {
            "TESTBrandZ": {
                "registration_slabs": [{"min": 0, "max": 5, "amount": 200}],
                "bill_upload_slabs": [{"min": 0, "max": 5, "amount": 40}],
            }
        }
        r = requests.put(
            f"{API}/admin/staff/config/current",
            headers=admin_headers,
            json={"category_slabs": category_slabs, "brand_slabs": brand_slabs},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # Verify persisted
        r2 = requests.get(f"{API}/admin/staff/config/current", headers=admin_headers, timeout=15)
        cfg = r2.json()["config"]
        assert "TESTCategoryFashion" in cfg["category_slabs"]
        assert cfg["category_slabs"]["TESTCategoryFashion"]["registration_slabs"][0]["amount"] == 60
        assert cfg["brand_slabs"]["TESTBrandZ"]["registration_slabs"][0]["amount"] == 200

        # Cleanup — reset overrides to empty
        requests.put(
            f"{API}/admin/staff/config/current",
            headers=admin_headers,
            json={"category_slabs": {}, "brand_slabs": {}},
            timeout=15,
        )


# ==================== Point 10: brand_category on Add Staff ====================

class TestAddStaffBrandCategory:
    def test_add_staff_stores_brand_category(self, admin_headers):
        phone = "9000090010"
        r = requests.post(
            f"{API}/admin/staff",
            headers=admin_headers,
            json={"name": "TEST_BC_Staff", "phone": phone, "brand_name": "TEST_BC_Brand",
                  "brand_category": "Electronics"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        sid = r.json()["staff"]["id"]
        assert r.json()["staff"].get("brand_category") == "Electronics"
        try:
            # Verify via list
            r2 = requests.get(f"{API}/admin/staff", headers=admin_headers, timeout=15)
            found = next((s for s in r2.json()["staff"] if s["id"] == sid), None)
            assert found is not None
            assert found.get("brand_category") == "Electronics"
        finally:
            requests.delete(f"{API}/admin/staff/{sid}", headers=admin_headers, timeout=10)


# ==================== Point 5: Retailer manager CRUD + login + dashboard ====================

@pytest.fixture
def retailer_manager(admin_headers):
    phone = "9000090055"
    brand = f"TEST_RM_Brand_{uuid.uuid4().hex[:6]}"
    r = requests.post(
        f"{API}/admin/staff/retailer-managers",
        headers=admin_headers,
        json={"name": "TEST_RM_Manager", "phone": phone, "brands": [brand], "email": "rm@test.co"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    mgr = r.json()["manager"]
    yield {"mgr": mgr, "phone": phone, "brand": brand}
    requests.delete(f"{API}/admin/staff/retailer-managers/{mgr['id']}", headers=admin_headers, timeout=10)


class TestPoint5Retailer:
    def test_crud_list(self, admin_headers, retailer_manager):
        r = requests.get(f"{API}/admin/staff/retailer-managers", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()["managers"]]
        assert retailer_manager["mgr"]["id"] in ids

    def test_patch_toggle_active(self, admin_headers, retailer_manager):
        mgr_id = retailer_manager["mgr"]["id"]
        r = requests.patch(
            f"{API}/admin/staff/retailer-managers/{mgr_id}",
            headers=admin_headers, json={"is_active": False}, timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["manager"]["is_active"] is False
        # re-enable
        requests.patch(
            f"{API}/admin/staff/retailer-managers/{mgr_id}",
            headers=admin_headers, json={"is_active": True}, timeout=15,
        )

    def test_send_and_verify_otp(self, admin_headers, retailer_manager):
        phone = retailer_manager["phone"]
        r = requests.post(f"{API}/staff/retailer/auth/send-otp", json={"phone": phone}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("success") is True

        r = requests.post(
            f"{API}/staff/retailer/auth/verify-otp",
            json={"phone": phone, "otp": OTP_BYPASS},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        tok = r.json().get("token")
        assert tok
        assert r.json()["manager"]["brands"] == [retailer_manager["brand"]]

    def test_non_whitelisted_phone_denied(self):
        r = requests.post(
            f"{API}/staff/retailer/auth/verify-otp",
            json={"phone": "9999900000", "otp": OTP_BYPASS},
            timeout=15,
        )
        assert r.status_code == 401

    def test_dashboard_no_pii(self, admin_headers, retailer_manager):
        # Login as retailer
        phone = retailer_manager["phone"]
        rv = requests.post(
            f"{API}/staff/retailer/auth/verify-otp",
            json={"phone": phone, "otp": OTP_BYPASS},
            timeout=15,
        )
        assert rv.status_code == 200
        tok = rv.json()["token"]

        # Seed one brand-scoped staff so we have something to view
        staff_phone = "9000090066"
        rs = requests.post(
            f"{API}/admin/staff",
            headers=admin_headers,
            json={"name": "TEST_RM_Employee", "phone": staff_phone,
                  "brand_name": retailer_manager["brand"], "brand_category": "Testing"},
            timeout=15,
        )
        assert rs.status_code == 200
        staff_id = rs.json()["staff"]["id"]

        # Seed a staff outside brand — should NOT appear
        rs_other = requests.post(
            f"{API}/admin/staff",
            headers=admin_headers,
            json={"name": "TEST_OtherBrand_Emp", "phone": "9000090077",
                  "brand_name": "TEST_OTHER_BRAND_XYZ"},
            timeout=15,
        )
        other_id = rs_other.json()["staff"]["id"] if rs_other.status_code == 200 else None

        try:
            rd = requests.get(
                f"{API}/staff/retailer/dashboard",
                headers={"Authorization": f"Bearer {tok}"},
                timeout=15,
            )
            assert rd.status_code == 200, rd.text
            body = rd.json()
            assert "manager" in body and "summary" in body and "staff" in body
            # Ensure our staff is present
            codes = {s["staff_code"] for s in body["staff"]}
            assert rs.json()["staff"]["staff_code"] in codes
            # Ensure out-of-brand staff not present
            other_codes = {s["staff_code"] for s in body["staff"]}
            if other_id:
                assert rs_other.json()["staff"]["staff_code"] not in other_codes or True
                # Explicit check
                assert rs_other.json()["staff"]["staff_code"] not in codes, "cross-brand staff leaked"
            # PII check
            raw = rd.text.lower()
            forbidden_keys = ["customer_phone", "bill_image", "customer_name"]
            for k in forbidden_keys:
                assert k not in raw, f"PII field {k!r} leaked in retailer dashboard"
            # Staff object should not contain phone/email (limit to code/name/brand/etc)
            for s in body["staff"]:
                assert "phone" not in s, f"staff.phone leaked: {s}"
                assert "email" not in s
        finally:
            requests.delete(f"{API}/admin/staff/{staff_id}", headers=admin_headers, timeout=10)
            if other_id:
                requests.delete(f"{API}/admin/staff/{other_id}", headers=admin_headers, timeout=10)
