"""
Iteration 16 - Stores/Explore Page Tests
Tests for the fix: Explore section now shows brands from MongoDB instead of hardcoded data
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://explore-loyalty.preview.emergentagent.com')

class TestStoresEndpoint:
    """Tests for GET /api/consumer/stores endpoint - pulls brands from MongoDB"""
    
    def test_stores_returns_brands_from_db(self):
        """Verify stores endpoint returns brands with proper fields"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        assert response.status_code == 200
        
        data = response.json()
        assert "stores" in data
        assert "categories" in data
        assert "floors" in data
        
        # Should have 102 brands from DB
        stores = data["stores"]
        assert len(stores) > 50, f"Expected 100+ brands, got {len(stores)}"
        
        # Verify store structure
        first_store = stores[0]
        assert "id" in first_store
        assert "name" in first_store
        assert "category" in first_store
        assert "floor" in first_store
        assert "logo_url" in first_store
        
        print(f"SUCCESS: {len(stores)} brands returned from DB")
    
    def test_stores_floor_filter_food_court(self):
        """Verify floor filter returns ~21 Food Court brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores?floor=Food%20Court")
        assert response.status_code == 200
        
        data = response.json()
        stores = data["stores"]
        
        # Should have ~21 Food Court brands
        assert len(stores) >= 15, f"Expected 15+ Food Court brands, got {len(stores)}"
        assert len(stores) <= 25, f"Expected <=25 Food Court brands, got {len(stores)}"
        
        # All should be Food Court
        for store in stores:
            assert store["floor"] == "Food Court", f"Store {store['name']} has floor {store['floor']}"
        
        print(f"SUCCESS: {len(stores)} Food Court brands returned")
    
    def test_stores_floor_filter_ground_floor(self):
        """Verify floor filter returns Ground Floor brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores?floor=Ground%20Floor")
        assert response.status_code == 200
        
        data = response.json()
        stores = data["stores"]
        
        assert len(stores) > 10, f"Expected 10+ Ground Floor brands, got {len(stores)}"
        
        for store in stores:
            assert store["floor"] == "Ground Floor"
        
        print(f"SUCCESS: {len(stores)} Ground Floor brands returned")
    
    def test_stores_category_filter_fashion(self):
        """Verify category filter returns Fashion brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores?category=Fashion")
        assert response.status_code == 200
        
        data = response.json()
        stores = data["stores"]
        
        assert len(stores) > 20, f"Expected 20+ Fashion brands, got {len(stores)}"
        
        for store in stores:
            assert store["category"] == "Fashion"
        
        print(f"SUCCESS: {len(stores)} Fashion brands returned")
    
    def test_stores_search_starbucks(self):
        """Verify search returns Starbucks"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores?search=star")
        assert response.status_code == 200
        
        data = response.json()
        stores = data["stores"]
        
        assert len(stores) >= 1, "Expected at least 1 result for 'star'"
        
        # Find Starbucks
        starbucks = next((s for s in stores if "Starbucks" in s["name"]), None)
        assert starbucks is not None, "Starbucks not found in search results"
        assert starbucks["category"] == "Cafe"
        assert starbucks["floor"] == "Ground Floor"
        
        print(f"SUCCESS: Starbucks found - {starbucks['name']}, {starbucks['category']}, {starbucks['floor']}")
    
    def test_stores_combined_filters(self):
        """Verify combined floor + category filter works"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores?floor=Ground%20Floor&category=Fashion")
        assert response.status_code == 200
        
        data = response.json()
        stores = data["stores"]
        
        assert len(stores) > 5, f"Expected 5+ Ground Floor Fashion brands, got {len(stores)}"
        
        for store in stores:
            assert store["floor"] == "Ground Floor"
            assert store["category"] == "Fashion"
        
        print(f"SUCCESS: {len(stores)} Ground Floor Fashion brands returned")
    
    def test_stores_returns_categories_and_floors(self):
        """Verify API returns filter options"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        assert response.status_code == 200
        
        data = response.json()
        
        # Check categories
        categories = data["categories"]
        assert len(categories) > 5, f"Expected 5+ categories, got {len(categories)}"
        assert "Fashion" in categories
        assert "Food & Beverage" in categories
        
        # Check floors
        floors = data["floors"]
        assert len(floors) >= 4, f"Expected 4+ floors, got {len(floors)}"
        assert "Ground Floor" in floors
        assert "Food Court" in floors
        
        print(f"SUCCESS: {len(categories)} categories, {len(floors)} floors returned")
    
    def test_stores_logo_urls_are_cdn(self):
        """Verify brand logos use Google CDN URLs"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        assert response.status_code == 200
        
        data = response.json()
        stores = data["stores"]
        
        cdn_count = 0
        for store in stores:
            logo = store.get("logo_url", "")
            if logo and "google.com/s2/favicons" in logo:
                cdn_count += 1
        
        # Most brands should have CDN logos
        assert cdn_count > 80, f"Expected 80+ CDN logos, got {cdn_count}"
        
        print(f"SUCCESS: {cdn_count}/{len(stores)} brands have Google CDN logos")


class TestParticipatingBrandsEndpoint:
    """Tests for GET /api/consumer/participating-brands endpoint"""
    
    def test_participating_brands_returns_all(self):
        """Verify participating-brands returns all eligible brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        
        data = response.json()
        assert "brands" in data
        assert "total" in data
        assert "filters" in data
        
        assert data["total"] >= 100, f"Expected 100+ brands, got {data['total']}"
        
        print(f"SUCCESS: {data['total']} participating brands returned")
    
    def test_participating_brands_filters(self):
        """Verify filter options are returned"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        
        data = response.json()
        filters = data["filters"]
        
        assert "floors" in filters
        assert "categories" in filters
        assert len(filters["floors"]) >= 4
        assert len(filters["categories"]) >= 5
        
        print(f"SUCCESS: Filters returned - {len(filters['floors'])} floors, {len(filters['categories'])} categories")


class TestHomeEndpoint:
    """Tests for GET /api/consumer/home endpoint"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/verify-otp",
            json={"phone": "9876543210", "otp": "1234"}
        )
        if response.status_code == 200:
            return response.json()["token"]
        pytest.skip("Auth failed")
    
    def test_home_returns_featured_stores(self, auth_token):
        """Verify home endpoint returns featured stores from DB"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/home",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "featured_stores" in data
        assert "banners" in data
        assert "user" in data
        
        print(f"SUCCESS: Home returned {len(data['featured_stores'])} featured stores, {len(data['banners'])} banners")


class TestAuthFlow:
    """Tests for authentication flow"""
    
    def test_verify_otp_dev_mode(self):
        """Verify OTP 1234 works in dev mode"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/verify-otp",
            json={"phone": "9876543210", "otp": "1234"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == True
        assert "token" in data
        assert "user" in data
        
        print(f"SUCCESS: Login successful for user {data['user']['name']}")
    
    def test_verify_otp_invalid_rejected(self):
        """Verify invalid OTP is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/verify-otp",
            json={"phone": "9876543210", "otp": "9999"}
        )
        assert response.status_code == 400
        
        print("SUCCESS: Invalid OTP correctly rejected")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
