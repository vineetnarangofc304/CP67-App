"""
Test suite for CP67 Mall App - New Features (Iteration 10)
Tests: Mall Map, Amenities, Referrals APIs + Enhanced Offers/Events
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://cp67-engage-preview.preview.emergentagent.com')

class TestConsumerAuth:
    """Consumer OTP authentication tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get consumer auth token via OTP flow"""
        # Send OTP
        res = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": "9876543210"})
        assert res.status_code == 200
        
        # Verify OTP (dev mode: 1234)
        res = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={"phone": "9876543210", "otp": "1234"})
        assert res.status_code == 200
        data = res.json()
        assert "token" in data
        return data["token"]
    
    def test_otp_login_flow(self, auth_token):
        """Test OTP login returns valid token"""
        assert auth_token is not None
        assert len(auth_token) > 50  # JWT tokens are long


class TestMallMapAPI:
    """Mall Map endpoint tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        res = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={"phone": "9876543210", "otp": "1234"})
        return res.json()["token"]
    
    def test_mall_map_returns_floors_array(self, auth_token):
        """GET /api/consumer/mall-map returns floors array"""
        res = requests.get(f"{BASE_URL}/api/consumer/mall-map", headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        data = res.json()
        assert "floors" in data
        assert isinstance(data["floors"], list)
    
    def test_mall_map_requires_auth(self):
        """Mall map endpoint requires authentication"""
        res = requests.get(f"{BASE_URL}/api/consumer/mall-map")
        assert res.status_code == 401


class TestAmenitiesAPI:
    """Amenities endpoint tests"""
    
    def test_amenities_returns_6_categories(self):
        """GET /api/consumer/amenities returns 6 amenity categories"""
        res = requests.get(f"{BASE_URL}/api/consumer/amenities")
        assert res.status_code == 200
        data = res.json()
        assert "amenities" in data
        assert len(data["amenities"]) == 6
        
        # Verify category names
        categories = [a["category"] for a in data["amenities"]]
        expected = ["Restrooms", "ATMs & Banking", "Services", "Connectivity", "Parking & Transport", "Emergency"]
        assert categories == expected
    
    def test_amenities_items_have_required_fields(self):
        """Each amenity item has name, location, floor"""
        res = requests.get(f"{BASE_URL}/api/consumer/amenities")
        data = res.json()
        for category in data["amenities"]:
            assert "items" in category
            for item in category["items"]:
                assert "name" in item
                assert "location" in item
                assert "floor" in item


class TestReferralAPI:
    """Referral system endpoint tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        res = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={"phone": "9876543210", "otp": "1234"})
        return res.json()["token"]
    
    def test_referral_returns_code_and_stats(self, auth_token):
        """GET /api/consumer/referral returns referral_code, total_referrals, share_text"""
        res = requests.get(f"{BASE_URL}/api/consumer/referral", headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        data = res.json()
        
        # Verify required fields
        assert "referral_code" in data
        assert "total_referrals" in data
        assert "share_text" in data
        assert "referral_link" in data
        assert "points_per_referral" in data
        assert "bonus_points_earned" in data
        
        # Verify data types
        assert isinstance(data["referral_code"], str)
        assert isinstance(data["total_referrals"], int)
        assert data["points_per_referral"] == 50
    
    def test_referral_requires_auth(self):
        """Referral endpoint requires authentication"""
        res = requests.get(f"{BASE_URL}/api/consumer/referral")
        assert res.status_code == 401
    
    def test_apply_invalid_referral_code_returns_404(self, auth_token):
        """POST /api/consumer/referral/apply with invalid code returns 404"""
        res = requests.post(
            f"{BASE_URL}/api/consumer/referral/apply?code=INVALIDCODE123",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert res.status_code == 404
        data = res.json()
        assert "Invalid referral code" in data.get("detail", "")


class TestOffersAPI:
    """Offers endpoint tests (enhanced with hot deals)"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        res = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={"phone": "9876543210", "otp": "1234"})
        return res.json()["token"]
    
    def test_offers_returns_list(self, auth_token):
        """GET /api/consumer/offers returns offers array"""
        res = requests.get(f"{BASE_URL}/api/consumer/offers", headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        data = res.json()
        assert "offers" in data
        assert isinstance(data["offers"], list)


class TestEventsAPI:
    """Events endpoint tests (enhanced with featured)"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        res = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={"phone": "9876543210", "otp": "1234"})
        return res.json()["token"]
    
    def test_events_returns_list(self, auth_token):
        """GET /api/consumer/events returns events array"""
        res = requests.get(f"{BASE_URL}/api/consumer/events", headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        data = res.json()
        assert "events" in data
        assert isinstance(data["events"], list)


class TestExistingEndpoints:
    """Verify existing endpoints still work"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        res = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={"phone": "9876543210", "otp": "1234"})
        return res.json()["token"]
    
    def test_profile_endpoint(self, auth_token):
        """GET /api/consumer/profile returns user data"""
        res = requests.get(f"{BASE_URL}/api/consumer/profile", headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        data = res.json()
        assert "name" in data
        assert "phone" in data
    
    def test_wallet_endpoint(self, auth_token):
        """GET /api/consumer/wallet/detailed returns wallet data"""
        res = requests.get(f"{BASE_URL}/api/consumer/wallet/detailed", headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        data = res.json()
        assert "balance" in data
    
    def test_stores_endpoint(self, auth_token):
        """GET /api/consumer/stores returns stores list"""
        res = requests.get(f"{BASE_URL}/api/consumer/stores", headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        data = res.json()
        assert "stores" in data
    
    def test_transactions_endpoint(self, auth_token):
        """GET /api/consumer/transactions returns transactions"""
        res = requests.get(f"{BASE_URL}/api/consumer/transactions", headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        data = res.json()
        assert "transactions" in data
    
    def test_rewards_endpoint(self, auth_token):
        """GET /api/consumer/rewards returns rewards catalog"""
        res = requests.get(f"{BASE_URL}/api/consumer/rewards", headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        data = res.json()
        assert "rewards" in data
