"""
Iteration 19: Floor Filter Synchronization Bug Fix Tests
Tests for floor filter functionality in Consumer Stores, Participating Brands, and Admin Brands pages.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://cp67-engage-preview.preview.emergentagent.com').rstrip('/')

# Expected floor distribution based on fix
EXPECTED_FLOOR_COUNTS = {
    "Ground Floor": 23,
    "First Floor": 28,
    "Second Floor": 27,
    "Food Court": 21,
    "Lower Ground": 2,
}
TOTAL_BRANDS = 101

class TestFloorFilterStores:
    """Test floor filter for Consumer Stores endpoint"""
    
    def test_stores_returns_all_brands_without_filter(self):
        """GET /api/consumer/stores without filter returns all 101 brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        assert response.status_code == 200
        data = response.json()
        assert "stores" in data
        assert len(data["stores"]) == TOTAL_BRANDS, f"Expected {TOTAL_BRANDS} brands, got {len(data['stores'])}"
        
    def test_stores_returns_correct_floors_list(self):
        """GET /api/consumer/stores returns correct floors list"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        assert response.status_code == 200
        data = response.json()
        assert "floors" in data
        expected_floors = sorted(EXPECTED_FLOOR_COUNTS.keys())
        actual_floors = sorted(data["floors"])
        assert actual_floors == expected_floors, f"Expected floors {expected_floors}, got {actual_floors}"
        
    def test_stores_ground_floor_filter(self):
        """GET /api/consumer/stores?floor=Ground Floor returns 23 brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores", params={"floor": "Ground Floor"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["stores"]) == EXPECTED_FLOOR_COUNTS["Ground Floor"]
        # Verify all returned brands have correct floor
        for store in data["stores"]:
            assert store.get("floor") == "Ground Floor", f"Brand {store['name']} has floor {store.get('floor')}"
            
    def test_stores_first_floor_filter(self):
        """GET /api/consumer/stores?floor=First Floor returns 28 brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores", params={"floor": "First Floor"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["stores"]) == EXPECTED_FLOOR_COUNTS["First Floor"]
        for store in data["stores"]:
            assert store.get("floor") == "First Floor"
            
    def test_stores_second_floor_filter(self):
        """GET /api/consumer/stores?floor=Second Floor returns 27 brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores", params={"floor": "Second Floor"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["stores"]) == EXPECTED_FLOOR_COUNTS["Second Floor"]
        for store in data["stores"]:
            assert store.get("floor") == "Second Floor"
            
    def test_stores_food_court_filter(self):
        """GET /api/consumer/stores?floor=Food Court returns 21 brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores", params={"floor": "Food Court"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["stores"]) == EXPECTED_FLOOR_COUNTS["Food Court"]
        for store in data["stores"]:
            assert store.get("floor") == "Food Court"
            
    def test_stores_lower_ground_filter(self):
        """GET /api/consumer/stores?floor=Lower Ground returns 2 brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores", params={"floor": "Lower Ground"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["stores"]) == EXPECTED_FLOOR_COUNTS["Lower Ground"]
        for store in data["stores"]:
            assert store.get("floor") == "Lower Ground"


class TestFloorFilterParticipatingBrands:
    """Test floor filter for Consumer Participating Brands (Redeem) endpoint"""
    
    def test_participating_brands_returns_all_without_filter(self):
        """GET /api/consumer/participating-brands without filter returns all eligible brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        data = response.json()
        assert "brands" in data
        assert "total" in data
        assert data["total"] == TOTAL_BRANDS, f"Expected {TOTAL_BRANDS} brands, got {data['total']}"
        
    def test_participating_brands_returns_correct_floors_in_filters(self):
        """GET /api/consumer/participating-brands returns correct floors in filters"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        data = response.json()
        assert "filters" in data
        assert "floors" in data["filters"]
        expected_floors = ["Lower Ground", "Ground Floor", "First Floor", "Second Floor", "Food Court"]
        actual_floors = data["filters"]["floors"]
        # Check all expected floors are present
        for floor in expected_floors:
            assert floor in actual_floors, f"Floor '{floor}' missing from filters"
            
    def test_participating_brands_ground_floor_filter(self):
        """GET /api/consumer/participating-brands?floor=Ground Floor returns 23 brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands", params={"floor": "Ground Floor"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == EXPECTED_FLOOR_COUNTS["Ground Floor"]
        for brand in data["brands"]:
            assert brand.get("floor") == "Ground Floor"
            
    def test_participating_brands_first_floor_filter(self):
        """GET /api/consumer/participating-brands?floor=First Floor returns 28 brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands", params={"floor": "First Floor"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == EXPECTED_FLOOR_COUNTS["First Floor"]
        
    def test_participating_brands_second_floor_filter(self):
        """GET /api/consumer/participating-brands?floor=Second Floor returns 27 brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands", params={"floor": "Second Floor"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == EXPECTED_FLOOR_COUNTS["Second Floor"]
        
    def test_participating_brands_food_court_filter(self):
        """GET /api/consumer/participating-brands?floor=Food Court returns 21 brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands", params={"floor": "Food Court"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == EXPECTED_FLOOR_COUNTS["Food Court"]
        
    def test_participating_brands_lower_ground_filter(self):
        """GET /api/consumer/participating-brands?floor=Lower Ground returns 2 brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands", params={"floor": "Lower Ground"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == EXPECTED_FLOOR_COUNTS["Lower Ground"]


class TestAdminBrandsFloor:
    """Test Admin Brands endpoint floor data"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": "admin",
            "password": "CP67Admin@2025"
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Admin authentication failed")
        
    def test_admin_brands_returns_all_brands(self, admin_token):
        """GET /api/admin/brands returns all 101 brands"""
        response = requests.get(f"{BASE_URL}/api/admin/brands", 
                               headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 200
        data = response.json()
        assert "brands" in data
        assert len(data["brands"]) == TOTAL_BRANDS
        
    def test_admin_brands_all_have_floor(self, admin_token):
        """All 101 brands have a non-empty floor value"""
        response = requests.get(f"{BASE_URL}/api/admin/brands", 
                               headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 200
        data = response.json()
        brands_without_floor = [b["brand_name"] for b in data["brands"] if not b.get("floor")]
        assert len(brands_without_floor) == 0, f"Brands without floor: {brands_without_floor}"
        
    def test_admin_brands_floor_distribution(self, admin_token):
        """Verify floor distribution matches expected counts"""
        response = requests.get(f"{BASE_URL}/api/admin/brands", 
                               headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 200
        data = response.json()
        
        # Count brands per floor
        floor_counts = {}
        for brand in data["brands"]:
            floor = brand.get("floor", "")
            floor_counts[floor] = floor_counts.get(floor, 0) + 1
            
        # Verify counts match expected
        for floor, expected_count in EXPECTED_FLOOR_COUNTS.items():
            actual_count = floor_counts.get(floor, 0)
            assert actual_count == expected_count, f"Floor '{floor}': expected {expected_count}, got {actual_count}"
            
    def test_admin_brands_no_duplicates(self, admin_token):
        """Verify no duplicate brand names exist"""
        response = requests.get(f"{BASE_URL}/api/admin/brands", 
                               headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 200
        data = response.json()
        
        brand_names = [b["brand_name"] for b in data["brands"]]
        duplicates = [name for name in brand_names if brand_names.count(name) > 1]
        unique_duplicates = list(set(duplicates))
        assert len(unique_duplicates) == 0, f"Duplicate brands found: {unique_duplicates}"


class TestFloorFilterTotalCount:
    """Test that floor filter counts add up correctly"""
    
    def test_stores_floor_counts_sum_to_total(self):
        """Sum of all floor-filtered stores equals total stores"""
        total_from_filters = 0
        for floor in EXPECTED_FLOOR_COUNTS.keys():
            response = requests.get(f"{BASE_URL}/api/consumer/stores", params={"floor": floor})
            assert response.status_code == 200
            total_from_filters += len(response.json()["stores"])
        assert total_from_filters == TOTAL_BRANDS, f"Sum of floor counts ({total_from_filters}) != total ({TOTAL_BRANDS})"
        
    def test_participating_brands_floor_counts_sum_to_total(self):
        """Sum of all floor-filtered participating brands equals total"""
        total_from_filters = 0
        for floor in EXPECTED_FLOOR_COUNTS.keys():
            response = requests.get(f"{BASE_URL}/api/consumer/participating-brands", params={"floor": floor})
            assert response.status_code == 200
            total_from_filters += response.json()["total"]
        assert total_from_filters == TOTAL_BRANDS, f"Sum of floor counts ({total_from_filters}) != total ({TOTAL_BRANDS})"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
