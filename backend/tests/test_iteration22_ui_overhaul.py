"""
Iteration 22: CP67 Mall UI/UX Overhaul Tests
Tests for animated welcome splash, home page, tier journey, wallet, stores, and profile pages
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestConsumerAuth:
    """Consumer authentication tests"""
    
    def test_send_otp_valid_phone(self):
        """Test OTP sending for valid phone"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={
            "phone": "9876543210"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert "message" in data
        print(f"✓ OTP sent successfully: {data.get('message')}")
    
    def test_send_otp_blocked_phone(self):
        """Test OTP sending for blocked phone returns 403"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={
            "phone": "8146141325"
        })
        assert response.status_code == 403
        data = response.json()
        assert "detail" in data
        print(f"✓ Blocked phone correctly rejected: {data.get('detail')}")
    
    def test_verify_otp_success(self):
        """Test OTP verification with correct OTP"""
        # First send OTP
        requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={
            "phone": "9876543210"
        })
        
        # Verify with dev OTP
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": "9876543210",
            "otp": "1234"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert "token" in data
        assert "user" in data
        print(f"✓ OTP verified, user: {data['user'].get('name')}")
        return data.get("token")


class TestStoresAPI:
    """Stores API tests including Third Floor"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for authenticated requests"""
        requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": "9876543210"})
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": "9876543210", "otp": "1234"
        })
        return response.json().get("token")
    
    def test_stores_returns_third_floor(self, auth_token):
        """Test that stores API returns Third Floor in floors array"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "floors" in data
        assert "Third Floor" in data["floors"]
        print(f"✓ Third Floor found in floors: {data['floors']}")
    
    def test_stores_excludes_food_court(self, auth_token):
        """Test that stores API excludes Food Court from floors"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "Food Court" not in data.get("floors", [])
        print("✓ Food Court correctly excluded from floors")


class TestTierInfo:
    """Tier info API tests for 7-tier system"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for authenticated requests"""
        requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": "9876543210"})
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": "9876543210", "otp": "1234"
        })
        return response.json().get("token")
    
    def test_tier_info_returns_7_tiers(self, auth_token):
        """Test that tier-info returns all 7 tiers"""
        response = requests.get(f"{BASE_URL}/api/consumer/tier-info", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "tiers" in data
        assert len(data["tiers"]) == 7
        
        expected_tiers = ["Bronze", "Silver", "Gold", "Platinum", "Titanium", "Diamond", "Privilege"]
        actual_tiers = [t["name"] for t in data["tiers"]]
        assert actual_tiers == expected_tiers
        print(f"✓ All 7 tiers found: {actual_tiers}")
    
    def test_tier_info_has_current_tier(self, auth_token):
        """Test that tier-info returns current tier info"""
        response = requests.get(f"{BASE_URL}/api/consumer/tier-info", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "current_tier" in data
        assert "name" in data["current_tier"]
        print(f"✓ Current tier: {data['current_tier']['name']}")


class TestWalletAPI:
    """Wallet API tests"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for authenticated requests"""
        requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": "9876543210"})
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": "9876543210", "otp": "1234"
        })
        return response.json().get("token")
    
    def test_wallet_detailed_returns_data(self, auth_token):
        """Test wallet/detailed endpoint returns balance and tier"""
        response = requests.get(f"{BASE_URL}/api/consumer/wallet/detailed", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "balance" in data
        assert "tier" in data
        print(f"✓ Wallet balance: {data.get('balance')}, tier: {data.get('tier', {}).get('name')}")


class TestHomeAPI:
    """Home API tests"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for authenticated requests"""
        requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": "9876543210"})
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": "9876543210", "otp": "1234"
        })
        return response.json().get("token")
    
    def test_home_returns_user_data(self, auth_token):
        """Test home endpoint returns user data"""
        response = requests.get(f"{BASE_URL}/api/consumer/home", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert "name" in data["user"]
        assert "tier" in data["user"]
        assert "balance_points" in data["user"]
        print(f"✓ Home user: {data['user'].get('name')}, tier: {data['user'].get('tier')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
