"""Backend tests for Points 29-35 (iteration 48)."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://staff-points-engine.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"username": "admin", "password": "CP67Admin@2025"}, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("token") or j.get("access_token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def consumer_headers():
    requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": "9876543210"}, timeout=30)
    r = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={"phone": "9876543210", "otp": "1234"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# Point 31 - App download QR + scan tracking
class TestAppDownloadQR:
    def test_qr_image_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/app-download-qr", timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/")

    def test_scan_redirects_to_play_store_and_increments(self, admin_headers):
        s0 = requests.get(f"{BASE_URL}/api/admin/app-download-qr/stats", headers=admin_headers, timeout=30)
        assert s0.status_code == 200
        before = s0.json()
        before_total = before.get("total_scans", 0)

        r = requests.get(f"{BASE_URL}/api/app-download-qr/scan", allow_redirects=False, timeout=30)
        assert r.status_code in (301, 302, 303, 307, 308), f"got {r.status_code}"
        loc = r.headers.get("Location", "")
        assert "play.google.com" in loc, f"redirect location was: {loc}"

        s1 = requests.get(f"{BASE_URL}/api/admin/app-download-qr/stats", headers=admin_headers, timeout=30)
        assert s1.status_code == 200
        after = s1.json()
        assert after["total_scans"] >= before_total + 1
        assert after.get("today_scans", 0) >= 1


# Point 32 & 33 - Hidden + Featured brand toggles
class TestBrandVisibilityAndFeatured:
    def _get_adidas(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/brands?limit=500", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        payload = r.json()
        brands = payload if isinstance(payload, list) else payload.get("brands", [])
        for b in brands:
            if b.get("brand_name", b.get("name", "")).lower() == "adidas":
                return b
        pytest.skip("Adidas brand not present in preview DB")

    def test_featured_and_hidden_toggle(self, admin_headers, consumer_headers):
        adidas = self._get_adidas(admin_headers)
        bid = adidas.get("id") or adidas.get("_id")
        assert bid
        original_featured = adidas.get("is_featured", False)
        original_hidden = adidas.get("hidden_from_app", False)

        try:
            # Ensure featured=True hidden=False
            up = requests.put(f"{BASE_URL}/api/admin/brands/{bid}",
                              json={"is_featured": True, "hidden_from_app": False},
                              headers=admin_headers, timeout=30)
            assert up.status_code == 200, up.text

            home = requests.get(f"{BASE_URL}/api/consumer/home", headers=consumer_headers, timeout=30).json()
            fs = home.get("featured_stores", [])
            names = [(s.get("name") or s.get("brand_name") or "").lower() for s in fs]
            assert "adidas" in names, f"Adidas not in featured_stores when featured+visible: {names}"

            # Now hide it
            up2 = requests.put(f"{BASE_URL}/api/admin/brands/{bid}",
                               json={"is_featured": True, "hidden_from_app": True},
                               headers=admin_headers, timeout=30)
            assert up2.status_code == 200, up2.text

            home2 = requests.get(f"{BASE_URL}/api/consumer/home", headers=consumer_headers, timeout=30).json()
            names2 = [(s.get("name") or s.get("brand_name") or "").lower() for s in home2.get("featured_stores", [])]
            assert "adidas" not in names2, f"Adidas still in featured_stores when hidden: {names2}"

            stores = requests.get(f"{BASE_URL}/api/consumer/stores", headers=consumer_headers, timeout=30).json()
            store_list = stores if isinstance(stores, list) else stores.get("stores", [])
            store_names = [(s.get("name") or s.get("brand_name") or "").lower() for s in store_list]
            assert "adidas" not in store_names, "Adidas still in /consumer/stores when hidden"
        finally:
            # Always restore
            requests.put(f"{BASE_URL}/api/admin/brands/{bid}",
                         json={"is_featured": original_featured, "hidden_from_app": original_hidden},
                         headers=admin_headers, timeout=30)


# Point 34 - Hot deal offers
class TestHotDealOffer:
    def test_create_hot_deal_and_verify_consumer_api(self, admin_headers, consumer_headers):
        payload = {
            "title": "TEST_HotDeal_29_35",
            "description": "Automated test hot deal",
            "discount_type": "percentage",
            "discount_value": 10,
            "is_hot_deal": True,
            "is_active": True,
        }
        c = requests.post(f"{BASE_URL}/api/admin/offers", json=payload, headers=admin_headers, timeout=30)
        assert c.status_code in (200, 201), c.text
        offer = c.json()
        if isinstance(offer, dict) and "offer" in offer and isinstance(offer["offer"], dict):
            offer = offer["offer"]
        oid = offer.get("id") or offer.get("_id")
        assert offer.get("is_hot_deal") is True

        try:
            co = requests.get(f"{BASE_URL}/api/consumer/offers", headers=consumer_headers, timeout=30).json()
            offers = co if isinstance(co, list) else co.get("offers", [])
            found = next((o for o in offers if (o.get("id") or o.get("_id")) == oid), None)
            assert found is not None, "Created offer not in /api/consumer/offers"
            assert found.get("is_hot_deal") is True
        finally:
            if oid:
                requests.delete(f"{BASE_URL}/api/admin/offers/{oid}", headers=admin_headers, timeout=30)


# Point 35 - staff mapping fields in list response
class TestStaffMapping:
    def test_staff_list_includes_mapping_fields(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/staff", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "unmapped_count" in data, f"missing unmapped_count in payload: keys={list(data.keys()) if isinstance(data, dict) else type(data)}"
        staff_list = data.get("staff") or data.get("items") or []
        if staff_list:
            assert "is_brand_mapped" in staff_list[0], f"first staff row missing is_brand_mapped: keys={list(staff_list[0].keys())}"

    def test_master_brands_catalog(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/staff/catalog/brands-categories", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "brands" in data or isinstance(data, list)
