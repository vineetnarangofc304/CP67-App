"""
Iteration 15 Tests - Critical Fixes Verification
1. Brand logos use Google CDN URLs (not local /api/uploads/)
2. Banner order randomization on home page
3. Upload Bill button renamed with Camera icon
4. Floor/Category filters working
5. WhatsApp Support card on Help page
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://cp67-engage-preview.preview.emergentagent.com')


class TestBrandLogoCDN:
    """Test that all brand logos use Google CDN URLs, not local file paths"""
    
    def test_all_brands_have_cdn_logos(self):
        """Verify ALL brands have Google CDN logo URLs, zero /api/uploads/ URLs"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        
        data = response.json()
        brands = data.get('brands', [])
        assert len(brands) > 0, "No brands returned"
        
        cdn_count = 0
        local_count = 0
        broken_brands = []
        
        for brand in brands:
            logo_url = brand.get('logo_url', '')
            if 'google.com/s2/favicons' in logo_url:
                cdn_count += 1
            elif '/api/uploads/' in logo_url:
                local_count += 1
                broken_brands.append(f"{brand['name']}: {logo_url}")
        
        # All brands should have CDN URLs
        assert local_count == 0, f"Found {local_count} broken local URLs: {broken_brands[:5]}"
        assert cdn_count == len(brands), f"Only {cdn_count}/{len(brands)} brands have CDN URLs"
        print(f"✓ All {cdn_count} brands have Google CDN logo URLs")
    
    def test_brand_search_returns_cdn_logo(self):
        """Verify search results also have CDN logos"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands?search=adidas")
        assert response.status_code == 200
        
        data = response.json()
        brands = data.get('brands', [])
        assert len(brands) >= 1, "Adidas not found"
        
        adidas = brands[0]
        assert 'google.com/s2/favicons' in adidas.get('logo_url', ''), \
            f"Adidas logo not from CDN: {adidas.get('logo_url')}"
        assert 'adidas.com' in adidas.get('logo_url', ''), "Adidas domain not in logo URL"
        print(f"✓ Adidas logo URL: {adidas.get('logo_url')}")


class TestBrandFilters:
    """Test floor and category filters on participating brands"""
    
    def test_filters_returned_in_response(self):
        """Verify filters are returned in API response"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        
        data = response.json()
        filters = data.get('filters', {})
        
        assert 'floors' in filters, "Floors filter missing"
        assert 'categories' in filters, "Categories filter missing"
        assert isinstance(filters['floors'], list), "Floors should be a list"
        assert isinstance(filters['categories'], list), "Categories should be a list"
        print(f"✓ Floors: {filters['floors']}")
        print(f"✓ Categories: {filters['categories']}")
    
    def test_floor_filter_works(self):
        """Verify floor filter returns correct results"""
        # First get available floors
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        data = response.json()
        floors = data.get('filters', {}).get('floors', [])
        
        if floors:
            floor = floors[0]
            response = requests.get(f"{BASE_URL}/api/consumer/participating-brands?floor={floor}")
            assert response.status_code == 200
            
            filtered_data = response.json()
            brands = filtered_data.get('brands', [])
            
            # All returned brands should have the selected floor
            for brand in brands:
                assert brand.get('floor') == floor, f"Brand {brand['name']} has floor {brand.get('floor')}, expected {floor}"
            print(f"✓ Floor filter '{floor}' returned {len(brands)} brands")
        else:
            pytest.skip("No floors available for filtering")
    
    def test_category_filter_works(self):
        """Verify category filter returns correct results"""
        # First get available categories
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        data = response.json()
        categories = data.get('filters', {}).get('categories', [])
        
        if categories:
            category = categories[0]
            response = requests.get(f"{BASE_URL}/api/consumer/participating-brands?category={category}")
            assert response.status_code == 200
            
            filtered_data = response.json()
            brands = filtered_data.get('brands', [])
            
            # All returned brands should have the selected category
            for brand in brands:
                assert brand.get('category') == category, f"Brand {brand['name']} has category {brand.get('category')}, expected {category}"
            print(f"✓ Category filter '{category}' returned {len(brands)} brands")
        else:
            pytest.skip("No categories available for filtering")


class TestBannerRandomization:
    """Test that banners are returned in random order"""
    
    def get_auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": "9876543210",
            "otp": "1234"
        })
        if response.status_code == 200:
            return response.json().get('token')
        return None
    
    def test_banner_order_changes(self):
        """Verify banner order changes between calls (randomization)"""
        token = self.get_auth_token()
        assert token, "Failed to get auth token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Make multiple calls and collect banner orders
        orders = []
        for i in range(5):
            response = requests.get(f"{BASE_URL}/api/consumer/home", headers=headers)
            assert response.status_code == 200
            
            data = response.json()
            banners = data.get('banners', [])
            order = [b.get('title') for b in banners]
            orders.append(tuple(order))
        
        # Check that we got at least 2 different orders (randomization working)
        unique_orders = set(orders)
        assert len(unique_orders) >= 2, f"Banner order never changed in 5 calls. Orders: {orders}"
        print(f"✓ Banner randomization working: {len(unique_orders)} unique orders in 5 calls")


class TestOTPLogin:
    """Regression test for OTP login flow"""
    
    def test_send_otp(self):
        """Test sending OTP"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={
            "phone": "9876543210"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data.get('success') == True
        print("✓ OTP sent successfully")
    
    def test_verify_otp_dev_mode(self):
        """Test verifying OTP with dev mode code 1234"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": "9876543210",
            "otp": "1234"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data.get('success') == True
        assert 'token' in data
        assert 'user' in data
        print(f"✓ OTP verified, user: {data['user'].get('name', 'N/A')}")
    
    def test_invalid_otp_rejected(self):
        """Test that invalid OTP is rejected"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": "9876543210",
            "otp": "9999"
        })
        assert response.status_code == 400
        print("✓ Invalid OTP correctly rejected")


class TestAdminBrands:
    """Test admin brands API"""
    
    def get_admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": "admin",
            "password": "CP67Admin@2025"
        })
        if response.status_code == 200:
            return response.json().get('token')
        return None
    
    def test_admin_brands_list(self):
        """Test admin can list all brands"""
        token = self.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/admin/brands", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        brands = data.get('brands', [])
        assert len(brands) > 0, "No brands returned"
        
        # Check brand structure
        brand = brands[0]
        assert 'brand_name' in brand or 'name' in brand
        assert 'logo_url' in brand
        print(f"✓ Admin brands API returned {len(brands)} brands")


class TestStaticAssets:
    """Test static assets are accessible"""
    
    def test_homeland_advantage_logo(self):
        """Test Homeland Advantage logo is accessible"""
        response = requests.head(f"{BASE_URL}/homeland-advantage-logo.jpeg")
        assert response.status_code == 200, f"Logo not accessible: {response.status_code}"
        print("✓ Homeland Advantage logo accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
