"""
Test suite for Participating Brands feature (Iteration 11)
Tests:
- GET /api/consumer/participating-brands endpoint
- Search, floor, and category filters
- Fixed mall-map endpoint (now uses brand_name field)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
API_URL = f"{BASE_URL}/api/consumer"

# Test credentials
TEST_PHONE = "9876543210"
TEST_OTP = "1234"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for protected endpoints"""
    response = requests.post(f"{API_URL}/auth/verify-otp", json={
        "phone": TEST_PHONE,
        "otp": TEST_OTP
    })
    assert response.status_code == 200, f"Auth failed: {response.text}"
    data = response.json()
    assert "token" in data, "No token in response"
    return data["token"]


class TestParticipatingBrandsEndpoint:
    """Tests for GET /api/consumer/participating-brands"""
    
    def test_participating_brands_returns_102_brands(self):
        """Verify endpoint returns all 102 brands"""
        response = requests.get(f"{API_URL}/participating-brands")
        assert response.status_code == 200
        data = response.json()
        
        assert "brands" in data
        assert "total" in data
        assert data["total"] == 102, f"Expected 102 brands, got {data['total']}"
        assert len(data["brands"]) == 102
        
    def test_participating_brands_has_filters(self):
        """Verify endpoint returns filter options"""
        response = requests.get(f"{API_URL}/participating-brands")
        assert response.status_code == 200
        data = response.json()
        
        assert "filters" in data
        assert "floors" in data["filters"]
        assert "categories" in data["filters"]
        # Should have at least Ground Floor and First Floor
        assert len(data["filters"]["floors"]) >= 2
        
    def test_participating_brands_brand_structure(self):
        """Verify brand objects have required fields"""
        response = requests.get(f"{API_URL}/participating-brands")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["brands"]) > 0
        brand = data["brands"][0]
        
        # Required fields
        assert "id" in brand
        assert "name" in brand
        assert "category" in brand
        assert "floor" in brand
        assert "logo_url" in brand
        
    def test_search_filter_bata(self):
        """Verify search filter returns Bata brand"""
        response = requests.get(f"{API_URL}/participating-brands?search=bata")
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 1, f"Expected 1 result for 'bata', got {data['total']}"
        assert len(data["brands"]) == 1
        assert data["brands"][0]["name"].lower() == "bata"
        
    def test_search_filter_case_insensitive(self):
        """Verify search is case insensitive"""
        response = requests.get(f"{API_URL}/participating-brands?search=BATA")
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 1
        assert data["brands"][0]["name"].lower() == "bata"
        
    def test_floor_filter_ground_floor(self):
        """Verify floor filter works for Ground Floor"""
        response = requests.get(f"{API_URL}/participating-brands?floor=Ground%20Floor")
        assert response.status_code == 200
        data = response.json()
        
        # Should return brands on Ground Floor
        assert data["total"] >= 1
        for brand in data["brands"]:
            assert brand["floor"] == "Ground Floor"
            
    def test_floor_filter_first_floor(self):
        """Verify floor filter works for First Floor"""
        response = requests.get(f"{API_URL}/participating-brands?floor=First%20Floor")
        assert response.status_code == 200
        data = response.json()
        
        # Should return brands on First Floor
        assert data["total"] >= 1
        for brand in data["brands"]:
            assert brand["floor"] == "First Floor"
            
    def test_search_no_results(self):
        """Verify search with no matches returns empty"""
        response = requests.get(f"{API_URL}/participating-brands?search=xyznonexistent")
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 0
        assert len(data["brands"]) == 0
        
    def test_brands_sorted_alphabetically(self):
        """Verify brands are sorted alphabetically by name"""
        response = requests.get(f"{API_URL}/participating-brands")
        assert response.status_code == 200
        data = response.json()
        
        names = [b["name"] for b in data["brands"]]
        assert names == sorted(names), "Brands should be sorted alphabetically"


class TestMallMapEndpointFixed:
    """Tests for fixed GET /api/consumer/mall-map endpoint"""
    
    def test_mall_map_requires_auth(self):
        """Verify mall-map requires authentication"""
        response = requests.get(f"{API_URL}/mall-map")
        assert response.status_code in [401, 403]
        
    def test_mall_map_returns_floors(self, auth_token):
        """Verify mall-map returns floors with stores (was 0 before fix)"""
        response = requests.get(
            f"{API_URL}/mall-map",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "floors" in data
        # After fix, should return 3 floors (Ground Floor, First Floor, Other)
        assert len(data["floors"]) >= 3, f"Expected at least 3 floors, got {len(data['floors'])}"
        
    def test_mall_map_floor_structure(self, auth_token):
        """Verify floor objects have correct structure"""
        response = requests.get(
            f"{API_URL}/mall-map",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        for floor in data["floors"]:
            assert "floor" in floor
            assert "stores" in floor
            assert isinstance(floor["stores"], list)
            
    def test_mall_map_stores_have_brand_name(self, auth_token):
        """Verify stores use brand_name field (the fix)"""
        response = requests.get(
            f"{API_URL}/mall-map",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Find a floor with stores
        for floor in data["floors"]:
            if floor["stores"]:
                store = floor["stores"][0]
                assert "name" in store, "Store should have 'name' field"
                assert store["name"], "Store name should not be empty"
                break


class TestRegressionExistingEndpoints:
    """Regression tests for existing endpoints"""
    
    def test_stores_endpoint_works(self):
        """Verify /stores endpoint still works"""
        response = requests.get(f"{API_URL}/stores")
        assert response.status_code == 200
        data = response.json()
        assert "stores" in data
        
    def test_offers_endpoint_works(self):
        """Verify /offers endpoint still works"""
        response = requests.get(f"{API_URL}/offers")
        assert response.status_code == 200
        data = response.json()
        assert "offers" in data
        
    def test_events_endpoint_works(self):
        """Verify /events endpoint still works"""
        response = requests.get(f"{API_URL}/events")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        
    def test_amenities_endpoint_works(self):
        """Verify /amenities endpoint still works"""
        response = requests.get(f"{API_URL}/amenities")
        assert response.status_code == 200
        data = response.json()
        assert "amenities" in data
        
    def test_profile_endpoint_works(self, auth_token):
        """Verify /profile endpoint still works"""
        response = requests.get(
            f"{API_URL}/profile",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "phone" in data
        
    def test_wallet_endpoint_works(self, auth_token):
        """Verify /wallet endpoint still works"""
        response = requests.get(
            f"{API_URL}/wallet",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "balance" in data
        
    def test_rewards_endpoint_works(self, auth_token):
        """Verify /rewards endpoint still works"""
        response = requests.get(
            f"{API_URL}/rewards",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "rewards" in data
        
    def test_referral_endpoint_works(self, auth_token):
        """Verify /referral endpoint still works"""
        response = requests.get(
            f"{API_URL}/referral",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "referral_code" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
