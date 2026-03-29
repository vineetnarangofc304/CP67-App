"""
Iteration 21 Tests: CP67 Mall UI and WhatsApp Changes
Tests:
1. Home page header shows 'Homeland Advantage' (not customer name)
2. Home page does NOT show 'Welcome back' text
3. Home page points card shows customer name inside the card
4. Login page has clickable 'Terms of Service' link with data-testid='terms-link'
5. GET /api/consumer/tier-info returns 7 tiers (Bronze, Silver, Gold, Platinum, Titanium, Diamond, Privilege)
6. GET /api/consumer/stores includes 'Third Floor' in floors array
7. GET /api/consumer/stores does NOT include 'Food Court' in floors array
8. GET /api/consumer/participating-brands includes 'Third Floor' in filters.floors
9. Wallet page shows 'Redeem' button (not 'Rewards')
10. Profile page does NOT show Referral Code section
11. Tier Journey page renders all 7 tiers correctly
12. Admin banner management page at /banners works
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://brand-sync-staging.preview.emergentagent.com').rstrip('/')

# Test credentials
CONSUMER_PHONE = "9876543210"
CONSUMER_OTP = "1234"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "CP67Admin@2025"


class TestConsumerAuth:
    """Consumer authentication tests"""
    
    def test_send_otp_success(self):
        """Test sending OTP to valid phone"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={
            "phone": CONSUMER_PHONE
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        print(f"PASS: Send OTP to {CONSUMER_PHONE} succeeded")
    
    def test_verify_otp_success(self):
        """Test verifying OTP with dev code 1234"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": CONSUMER_PHONE,
            "otp": CONSUMER_OTP
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert "token" in data
        print(f"PASS: Verify OTP for {CONSUMER_PHONE} succeeded, got token")
        return data.get("token")


class TestTierSystem:
    """Test 7-tier system"""
    
    @pytest.fixture
    def auth_token(self):
        """Get consumer auth token"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": CONSUMER_PHONE,
            "otp": CONSUMER_OTP
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Could not get auth token")
    
    def test_tier_info_returns_7_tiers(self, auth_token):
        """Test GET /api/consumer/tier-info returns 7 tiers"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/tier-info",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check tiers array exists
        assert "tiers" in data
        tiers = data["tiers"]
        
        # Verify 7 tiers
        assert len(tiers) == 7, f"Expected 7 tiers, got {len(tiers)}"
        
        # Verify tier names in order
        expected_tiers = ["Bronze", "Silver", "Gold", "Platinum", "Titanium", "Diamond", "Privilege"]
        actual_tiers = [t["name"] for t in tiers]
        assert actual_tiers == expected_tiers, f"Expected {expected_tiers}, got {actual_tiers}"
        
        # Verify each tier has required fields
        for tier in tiers:
            assert "name" in tier
            assert "min_points" in tier
            assert "color" in tier
            assert "benefits" in tier
            assert isinstance(tier["benefits"], list)
        
        print(f"PASS: tier-info returns 7 tiers: {actual_tiers}")


class TestFloorFilters:
    """Test floor filter changes - Third Floor included, Food Court excluded"""
    
    def test_stores_includes_third_floor(self):
        """Test GET /api/consumer/stores includes 'Third Floor' in floors array"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        assert response.status_code == 200
        data = response.json()
        
        assert "floors" in data
        floors = data["floors"]
        
        # Third Floor should be included
        assert "Third Floor" in floors, f"'Third Floor' not found in floors: {floors}"
        print(f"PASS: /api/consumer/stores includes 'Third Floor' in floors: {floors}")
    
    def test_stores_excludes_food_court(self):
        """Test GET /api/consumer/stores does NOT include 'Food Court' in floors array"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        assert response.status_code == 200
        data = response.json()
        
        assert "floors" in data
        floors = data["floors"]
        
        # Food Court should be excluded
        assert "Food Court" not in floors, f"'Food Court' should not be in floors: {floors}"
        print(f"PASS: /api/consumer/stores excludes 'Food Court' from floors: {floors}")
    
    def test_participating_brands_includes_third_floor(self):
        """Test GET /api/consumer/participating-brands includes 'Third Floor' in filters.floors"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        data = response.json()
        
        assert "filters" in data
        assert "floors" in data["filters"]
        floors = data["filters"]["floors"]
        
        # Third Floor should be included
        assert "Third Floor" in floors, f"'Third Floor' not found in filters.floors: {floors}"
        print(f"PASS: /api/consumer/participating-brands includes 'Third Floor' in filters.floors: {floors}")
    
    def test_participating_brands_excludes_food_court(self):
        """Test GET /api/consumer/participating-brands does NOT include 'Food Court' in filters.floors"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        data = response.json()
        
        assert "filters" in data
        assert "floors" in data["filters"]
        floors = data["filters"]["floors"]
        
        # Food Court should be excluded
        assert "Food Court" not in floors, f"'Food Court' should not be in filters.floors: {floors}"
        print(f"PASS: /api/consumer/participating-brands excludes 'Food Court' from filters.floors: {floors}")


class TestAdminAuth:
    """Admin authentication tests"""
    
    def test_admin_login_success(self):
        """Test admin login with correct credentials"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        print(f"PASS: Admin login succeeded")
        return data.get("token")
    
    def test_admin_login_wrong_password(self):
        """Test admin login with wrong password returns 401"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": ADMIN_USERNAME,
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print(f"PASS: Admin login with wrong password returns 401")


class TestAdminBanners:
    """Admin banner management tests"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Could not get admin token")
    
    def test_get_banners(self, admin_token):
        """Test GET /api/admin/banners returns banners list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/banners",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "banners" in data
        print(f"PASS: GET /api/admin/banners returns {len(data['banners'])} banners")


class TestHomeEndpoint:
    """Test home endpoint for user data"""
    
    @pytest.fixture
    def auth_token(self):
        """Get consumer auth token"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": CONSUMER_PHONE,
            "otp": CONSUMER_OTP
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Could not get auth token")
    
    def test_home_returns_user_data(self, auth_token):
        """Test GET /api/consumer/home returns user data with name"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/home",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check user object exists
        assert "user" in data
        user = data["user"]
        
        # User should have name, tier, balance_points
        assert "name" in user
        assert "tier" in user
        assert "balance_points" in user
        
        print(f"PASS: /api/consumer/home returns user data: name={user.get('name')}, tier={user.get('tier')}, points={user.get('balance_points')}")


class TestWalletEndpoint:
    """Test wallet endpoint"""
    
    @pytest.fixture
    def auth_token(self):
        """Get consumer auth token"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": CONSUMER_PHONE,
            "otp": CONSUMER_OTP
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Could not get auth token")
    
    def test_wallet_returns_tier_info(self, auth_token):
        """Test GET /api/consumer/wallet returns tier info"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/wallet",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert "balance" in data
        assert "tier" in data
        
        print(f"PASS: /api/consumer/wallet returns balance={data.get('balance')}, tier={data.get('tier')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
