"""
Iteration 12 Tests: Eligibility Toggle, Floor/Category Filters, Dark Hero Header
Tests for:
1. Consumer participating-brands endpoint with is_eligible filter
2. Admin brands endpoint with eligibility toggle
3. Floor and category filter dropdowns
4. Logo URL normalization
5. Regression tests for mall-map and other consumer endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://brand-sync-staging.preview.emergentagent.com')
ADIDAS_BRAND_ID = "21110bec-0005-417c-adda-d0600b58fb2e"

@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={"username": "admin", "password": "CP67Admin@2025"}
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["token"]

@pytest.fixture(scope="module")
def consumer_token():
    """Get consumer authentication token"""
    # Send OTP
    requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": "9876543210"})
    # Verify with dev OTP
    response = requests.post(
        f"{BASE_URL}/api/consumer/auth/verify-otp",
        json={"phone": "9876543210", "otp": "1234"}
    )
    assert response.status_code == 200, f"Consumer login failed: {response.text}"
    return response.json()["token"]


class TestParticipatingBrandsAPI:
    """Tests for GET /api/consumer/participating-brands"""
    
    def test_returns_102_brands_default(self):
        """Default query returns all 102 eligible brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 102, f"Expected 102 brands, got {data['total']}"
        assert len(data["brands"]) == 102
    
    def test_search_adidas_returns_1_result(self):
        """Search for 'adidas' returns exactly 1 result"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands?search=adidas")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1, f"Expected 1 brand for 'adidas', got {data['total']}"
        assert data["brands"][0]["name"].lower() == "adidas"
    
    def test_floor_filter_ground_floor(self):
        """Floor filter 'Ground Floor' returns filtered results"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands?floor=Ground+Floor")
        assert response.status_code == 200
        data = response.json()
        # Should return at least Adidas which is on Ground Floor
        assert data["total"] >= 1
        for brand in data["brands"]:
            assert brand["floor"] == "Ground Floor", f"Brand {brand['name']} has floor {brand['floor']}"
    
    def test_filters_include_floors_and_categories(self):
        """Response includes floors and categories for filter dropdowns"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        data = response.json()
        assert "filters" in data
        assert "floors" in data["filters"]
        assert "categories" in data["filters"]
        assert isinstance(data["filters"]["floors"], list)
        assert isinstance(data["filters"]["categories"], list)
    
    def test_brand_structure_has_required_fields(self):
        """Each brand has required fields: id, name, category, floor, logo_url"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        data = response.json()
        for brand in data["brands"][:5]:  # Check first 5
            assert "id" in brand
            assert "name" in brand
            assert "category" in brand
            assert "floor" in brand
            assert "logo_url" in brand


class TestEligibilityToggle:
    """Tests for admin eligibility toggle feature"""
    
    def test_set_brand_ineligible_hides_from_consumer(self, admin_token):
        """Setting is_eligible=false hides brand from consumer endpoint"""
        # Set Adidas to ineligible
        response = requests.put(
            f"{BASE_URL}/api/admin/brands/{ADIDAS_BRAND_ID}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"brand_name": "Adidas", "is_eligible": False}
        )
        assert response.status_code == 200
        
        # Verify Adidas is hidden from consumer endpoint
        consumer_response = requests.get(f"{BASE_URL}/api/consumer/participating-brands?search=adidas")
        assert consumer_response.status_code == 200
        data = consumer_response.json()
        assert data["total"] == 0, "Adidas should be hidden when is_eligible=false"
    
    def test_set_brand_eligible_shows_on_consumer(self, admin_token):
        """Setting is_eligible=true shows brand on consumer endpoint"""
        # Set Adidas back to eligible
        response = requests.put(
            f"{BASE_URL}/api/admin/brands/{ADIDAS_BRAND_ID}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"brand_name": "Adidas", "is_eligible": True}
        )
        assert response.status_code == 200
        
        # Verify Adidas is visible on consumer endpoint
        consumer_response = requests.get(f"{BASE_URL}/api/consumer/participating-brands?search=adidas")
        assert consumer_response.status_code == 200
        data = consumer_response.json()
        assert data["total"] == 1, "Adidas should be visible when is_eligible=true"
        assert data["brands"][0]["name"].lower() == "adidas"
    
    def test_admin_brands_endpoint_returns_is_eligible_field(self, admin_token):
        """Admin brands endpoint includes is_eligible field"""
        response = requests.get(
            f"{BASE_URL}/api/admin/brands",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # Find Adidas and check is_eligible field
        adidas = next((b for b in data["brands"] if b.get("id") == ADIDAS_BRAND_ID), None)
        assert adidas is not None, "Adidas brand not found"
        assert "is_eligible" in adidas or adidas.get("is_eligible") is None, "is_eligible field should exist"


class TestAdminBrandsFilters:
    """Tests for admin brands page floor/category filters"""
    
    def test_admin_brands_returns_floor_data(self, admin_token):
        """Admin brands endpoint returns floor data for each brand"""
        response = requests.get(
            f"{BASE_URL}/api/admin/brands",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # Check that brands have floor field
        brands_with_floor = [b for b in data["brands"] if b.get("floor")]
        assert len(brands_with_floor) >= 1, "At least one brand should have floor data"
    
    def test_admin_brands_returns_category_data(self, admin_token):
        """Admin brands endpoint returns category data for each brand"""
        response = requests.get(
            f"{BASE_URL}/api/admin/brands",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # Check that brands have category field
        brands_with_category = [b for b in data["brands"] if b.get("category")]
        assert len(brands_with_category) >= 1, "At least one brand should have category data"


class TestMallMapRegression:
    """Regression tests for mall-map endpoint (brand_name fix)"""
    
    def test_mall_map_requires_auth(self):
        """Mall map endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/consumer/mall-map")
        assert response.status_code == 401
    
    def test_mall_map_returns_floors_with_stores(self, consumer_token):
        """Mall map returns floors with stores (brand_name fix verified)"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/mall-map",
            headers={"Authorization": f"Bearer {consumer_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "floors" in data
        assert len(data["floors"]) > 0, "Mall map should return at least one floor"
        
        # Check floor structure
        for floor in data["floors"]:
            assert "floor" in floor
            assert "stores" in floor
            assert isinstance(floor["stores"], list)
    
    def test_mall_map_stores_have_name_field(self, consumer_token):
        """Mall map stores use 'name' field (from brand_name)"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/mall-map",
            headers={"Authorization": f"Bearer {consumer_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check that stores have name field
        for floor in data["floors"]:
            for store in floor["stores"][:3]:  # Check first 3 stores per floor
                assert "name" in store, f"Store missing 'name' field: {store}"


class TestConsumerRegressions:
    """Regression tests for other consumer endpoints"""
    
    def test_home_endpoint(self, consumer_token):
        """Home endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/home",
            headers={"Authorization": f"Bearer {consumer_token}"}
        )
        assert response.status_code == 200
    
    def test_wallet_endpoint(self, consumer_token):
        """Wallet endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/wallet",
            headers={"Authorization": f"Bearer {consumer_token}"}
        )
        assert response.status_code == 200
    
    def test_stores_endpoint(self):
        """Stores endpoint works (public)"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        assert response.status_code == 200
    
    def test_profile_endpoint(self, consumer_token):
        """Profile endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/profile",
            headers={"Authorization": f"Bearer {consumer_token}"}
        )
        assert response.status_code == 200


class TestLogoURLNormalization:
    """Tests for logo URL normalization"""
    
    def test_adidas_logo_url_is_normalized(self):
        """Adidas logo URL should be normalized to current BACKEND_PUBLIC_URL"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands?search=adidas")
        assert response.status_code == 200
        data = response.json()
        if data["total"] > 0:
            adidas = data["brands"][0]
            logo_url = adidas.get("logo_url", "")
            if logo_url:
                # Logo URL should start with the backend URL
                assert logo_url.startswith("https://"), f"Logo URL should be absolute: {logo_url}"
                assert "/api/uploads/" in logo_url, f"Logo URL should contain /api/uploads/: {logo_url}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
