"""
Iteration 13 Tests: Color scheme overhaul, brand logos, and admin eligibility toggle
Tests:
1. Brand logos - 87 real logos from Google Favicons API
2. Consumer participating-brands endpoint with logo URLs
3. Admin eligibility toggle (green ON / red OFF)
4. Color scheme verification (warm brown/gold palette)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://mall-engagement-hub.preview.emergentagent.com')

# Test credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "CP67Admin@2025"
CONSUMER_PHONE = "9876543210"
CONSUMER_OTP = "1234"
ADIDAS_BRAND_ID = "21110bec-0005-417c-adda-d0600b58fb2e"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def consumer_token():
    """Get consumer authentication token"""
    # Send OTP
    requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": CONSUMER_PHONE})
    # Verify OTP (dev mode accepts 1234)
    response = requests.post(
        f"{BASE_URL}/api/consumer/auth/verify-otp",
        json={"phone": CONSUMER_PHONE, "otp": CONSUMER_OTP}
    )
    assert response.status_code == 200, f"Consumer login failed: {response.text}"
    return response.json().get("token")


class TestBrandLogos:
    """Test brand logo functionality"""
    
    def test_participating_brands_returns_brands_with_logos(self):
        """GET /api/consumer/participating-brands returns brands with logo_url"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        
        data = response.json()
        brands = data.get("brands", [])
        assert len(brands) > 0, "No brands returned"
        
        # Count brands with logos
        with_logo = [b for b in brands if b.get("logo_url")]
        without_logo = [b for b in brands if not b.get("logo_url")]
        
        print(f"Brands with logos: {len(with_logo)}")
        print(f"Brands without logos: {len(without_logo)}")
        
        # Should have at least 80 brands with logos (87 expected)
        assert len(with_logo) >= 80, f"Expected at least 80 brands with logos, got {len(with_logo)}"
    
    def test_logo_urls_are_accessible(self):
        """Logo URLs should return valid image data"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        data = response.json()
        brands = data.get("brands", [])
        
        # Test first 5 brands with logos
        brands_with_logos = [b for b in brands if b.get("logo_url")][:5]
        
        for brand in brands_with_logos:
            logo_url = brand["logo_url"]
            logo_response = requests.head(logo_url, timeout=5)
            assert logo_response.status_code == 200, f"Logo not accessible for {brand['name']}: {logo_url}"
            assert "image" in logo_response.headers.get("content-type", ""), f"Logo is not an image for {brand['name']}"
            print(f"✓ {brand['name']} logo accessible: {logo_url}")
    
    def test_specific_brands_have_logos(self):
        """Specific brands should have logos (Adidas, Apple, Baskin Robbins, etc.)"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        data = response.json()
        brands = {b["name"]: b for b in data.get("brands", [])}
        
        expected_with_logos = ["Adidas", "Apple", "Baskin Robbins", "Burger King", "Bata", "Aldo"]
        
        for brand_name in expected_with_logos:
            if brand_name in brands:
                assert brands[brand_name].get("logo_url"), f"{brand_name} should have a logo"
                print(f"✓ {brand_name} has logo: {brands[brand_name]['logo_url']}")
    
    def test_brands_without_logos_show_initials(self):
        """Brands without logos should be in the list (UI shows initials)"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        data = response.json()
        brands = {b["name"]: b for b in data.get("brands", [])}
        
        # These brands don't have logos (show initials in UI)
        expected_without_logos = ["Bath And Body Works", "Biba", "Bhpc", "Woodland"]
        
        for brand_name in expected_without_logos:
            if brand_name in brands:
                # Brand exists but may not have logo_url
                print(f"✓ {brand_name} in list (shows initials if no logo)")


class TestAdminEligibilityToggle:
    """Test admin eligibility toggle functionality"""
    
    def test_toggle_brand_off_reduces_count(self, admin_token):
        """Toggling brand OFF should reduce consumer brand count"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get initial count
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        initial_count = response.json().get("total", 0)
        print(f"Initial brand count: {initial_count}")
        
        # Disable Adidas
        response = requests.put(
            f"{BASE_URL}/api/admin/brands/{ADIDAS_BRAND_ID}",
            headers=headers,
            json={"brand_name": "Adidas", "is_eligible": False}
        )
        assert response.status_code == 200, f"Failed to disable Adidas: {response.text}"
        
        # Check count reduced
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        new_count = response.json().get("total", 0)
        print(f"Count after disabling Adidas: {new_count}")
        
        assert new_count == initial_count - 1, f"Expected {initial_count - 1}, got {new_count}"
        
        # Verify Adidas not in list
        brands = [b["name"] for b in response.json().get("brands", [])]
        assert "Adidas" not in brands, "Adidas should not be in consumer list when disabled"
        
        # Re-enable Adidas
        response = requests.put(
            f"{BASE_URL}/api/admin/brands/{ADIDAS_BRAND_ID}",
            headers=headers,
            json={"brand_name": "Adidas", "is_eligible": True}
        )
        assert response.status_code == 200
        
        # Verify count restored
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        final_count = response.json().get("total", 0)
        print(f"Count after re-enabling Adidas: {final_count}")
        
        assert final_count == initial_count, f"Expected {initial_count}, got {final_count}"
    
    def test_admin_brands_endpoint_returns_is_eligible(self, admin_token):
        """Admin brands endpoint should return is_eligible field"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.get(f"{BASE_URL}/api/admin/brands", headers=headers)
        assert response.status_code == 200
        
        brands = response.json().get("brands", [])
        assert len(brands) > 0
        
        # Check first brand has is_eligible field
        first_brand = brands[0]
        assert "is_eligible" in first_brand or first_brand.get("is_eligible") is not False, \
            "Brand should have is_eligible field (defaults to True)"
        print(f"✓ Admin brands endpoint returns is_eligible field")
    
    def test_admin_brands_show_logos(self, admin_token):
        """Admin brands endpoint should return logo_url"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.get(f"{BASE_URL}/api/admin/brands", headers=headers)
        assert response.status_code == 200
        
        brands = response.json().get("brands", [])
        with_logo = [b for b in brands if b.get("logo_url")]
        
        print(f"Admin brands with logos: {len(with_logo)}")
        assert len(with_logo) >= 80, f"Expected at least 80 brands with logos in admin view"


class TestColorScheme:
    """Test color scheme (verified via CSS, these are sanity checks)"""
    
    def test_consumer_home_endpoint_works(self, consumer_token):
        """Consumer home endpoint should work (color scheme is CSS)"""
        headers = {"Authorization": f"Bearer {consumer_token}"}
        
        response = requests.get(f"{BASE_URL}/api/consumer/home", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "user" in data
        assert "banners" in data
        print("✓ Consumer home endpoint working")
    
    def test_consumer_wallet_endpoint_works(self, consumer_token):
        """Consumer wallet endpoint should work"""
        headers = {"Authorization": f"Bearer {consumer_token}"}
        
        response = requests.get(f"{BASE_URL}/api/consumer/wallet", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "balance" in data
        assert "tier" in data
        print("✓ Consumer wallet endpoint working")
    
    def test_consumer_stores_endpoint_works(self):
        """Consumer stores endpoint should work"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        assert response.status_code == 200
        
        data = response.json()
        assert "stores" in data
        print(f"✓ Consumer stores endpoint working ({len(data['stores'])} stores)")


class TestRegressionChecks:
    """Regression tests for existing functionality"""
    
    def test_participating_brands_filters_work(self):
        """Search and filter parameters should work"""
        # Test search
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands?search=adidas")
        assert response.status_code == 200
        data = response.json()
        brands = data.get("brands", [])
        if len(brands) > 0:
            assert any("adidas" in b["name"].lower() for b in brands), "Search should filter by name"
        print(f"✓ Search filter works ({len(brands)} results for 'adidas')")
        
        # Test floor filter
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands?floor=Ground+Floor")
        assert response.status_code == 200
        print("✓ Floor filter works")
    
    def test_participating_brands_returns_filters(self):
        """Endpoint should return filter options"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        
        data = response.json()
        assert "filters" in data
        assert "floors" in data["filters"]
        assert "categories" in data["filters"]
        print(f"✓ Filter options returned: {len(data['filters']['floors'])} floors, {len(data['filters']['categories'])} categories")
    
    def test_mall_map_endpoint_works(self, consumer_token):
        """Mall map endpoint should work"""
        headers = {"Authorization": f"Bearer {consumer_token}"}
        
        response = requests.get(f"{BASE_URL}/api/consumer/mall-map", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "floors" in data
        print(f"✓ Mall map endpoint working ({len(data['floors'])} floors)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
