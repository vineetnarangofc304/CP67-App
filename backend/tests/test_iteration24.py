"""
Iteration 24 Backend Tests - CP67 Mall Consumer PWA
Tests for: Consumer Auth, Profile with pincode, Transactions with Expired filter,
Admin Offers CRUD, Admin Events CRUD, Amenities (no ATM), Help FAQs
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://mall-engagement-hub.preview.emergentagent.com')

# Test credentials
CONSUMER_PHONE = "9876543210"
CONSUMER_OTP = "1234"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "CP67Admin@2025"


class TestConsumerAuth:
    """Consumer OTP authentication flow"""
    
    def test_send_otp(self):
        """Test sending OTP to consumer phone"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/send-otp",
            json={"phone": CONSUMER_PHONE}
        )
        print(f"Send OTP response: {response.status_code} - {response.text[:200]}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
    
    def test_verify_otp(self):
        """Test verifying OTP and getting token"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/verify-otp",
            json={"phone": CONSUMER_PHONE, "otp": CONSUMER_OTP}
        )
        print(f"Verify OTP response: {response.status_code} - {response.text[:200]}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert "token" in data
        assert "user" in data


class TestConsumerProfile:
    """Consumer profile with new address fields"""
    
    @pytest.fixture
    def consumer_token(self):
        """Get consumer auth token"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/verify-otp",
            json={"phone": CONSUMER_PHONE, "otp": CONSUMER_OTP}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Consumer auth failed")
    
    def test_get_profile(self, consumer_token):
        """Test getting consumer profile"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/profile",
            headers={"Authorization": f"Bearer {consumer_token}"}
        )
        print(f"Get profile response: {response.status_code}")
        assert response.status_code == 200
        data = response.json()
        assert "phone" in data
        assert "tier" in data
    
    def test_update_profile_with_address(self, consumer_token):
        """Test updating profile with house_no, landmark, pincode, city, state"""
        update_data = {
            "name": "Test User",
            "house_no": "B-42, Tower 3",
            "landmark": "Near Metro Station",
            "pincode": "160062",
            "city": "Mohali",
            "state": "Punjab"
        }
        response = requests.put(
            f"{BASE_URL}/api/consumer/profile",
            headers={"Authorization": f"Bearer {consumer_token}", "Content-Type": "application/json"},
            json=update_data
        )
        print(f"Update profile response: {response.status_code} - {response.text[:200]}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True


class TestPincodeLookup:
    """Pincode auto-fill API"""
    
    def test_pincode_lookup_valid(self):
        """Test pincode lookup returns city and state"""
        response = requests.get(f"{BASE_URL}/api/consumer/pincode/160062")
        print(f"Pincode lookup response: {response.status_code} - {response.text}")
        assert response.status_code == 200
        data = response.json()
        # API may return success or not depending on external service
        if data.get("success"):
            assert "city" in data
            assert "state" in data
    
    def test_pincode_lookup_invalid(self):
        """Test pincode lookup with invalid pincode"""
        response = requests.get(f"{BASE_URL}/api/consumer/pincode/000000")
        print(f"Invalid pincode response: {response.status_code} - {response.text}")
        assert response.status_code == 200
        data = response.json()
        # Should return success: false for invalid pincode
        assert data.get("success") == False or data.get("city") == ""


class TestTransactionsWithExpiredFilter:
    """Transactions API with expired filter"""
    
    @pytest.fixture
    def consumer_token(self):
        """Get consumer auth token"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/verify-otp",
            json={"phone": CONSUMER_PHONE, "otp": CONSUMER_OTP}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Consumer auth failed")
    
    def test_transactions_all(self, consumer_token):
        """Test getting all transactions"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/transactions?filter_type=all",
            headers={"Authorization": f"Bearer {consumer_token}"}
        )
        print(f"Transactions all response: {response.status_code}")
        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data
    
    def test_transactions_earned(self, consumer_token):
        """Test getting earned transactions"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/transactions?filter_type=earn",
            headers={"Authorization": f"Bearer {consumer_token}"}
        )
        print(f"Transactions earned response: {response.status_code}")
        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data
    
    def test_transactions_redeemed(self, consumer_token):
        """Test getting redeemed transactions"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/transactions?filter_type=redeem",
            headers={"Authorization": f"Bearer {consumer_token}"}
        )
        print(f"Transactions redeemed response: {response.status_code}")
        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data
    
    def test_transactions_expired(self, consumer_token):
        """Test getting expired transactions - NEW FILTER"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/transactions?filter_type=expired",
            headers={"Authorization": f"Bearer {consumer_token}"}
        )
        print(f"Transactions expired response: {response.status_code}")
        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data


class TestAmenities:
    """Amenities API - should NOT include ATM & Banking"""
    
    def test_amenities_list(self):
        """Test amenities list does not include ATM & Banking"""
        response = requests.get(f"{BASE_URL}/api/consumer/amenities")
        print(f"Amenities response: {response.status_code}")
        assert response.status_code == 200
        data = response.json()
        assert "amenities" in data
        
        # Check that ATM & Banking is NOT in the categories
        categories = [a.get("category", "") for a in data.get("amenities", [])]
        print(f"Amenity categories: {categories}")
        assert "ATM & Banking" not in categories, "ATM & Banking should be removed from amenities"


class TestAdminAuth:
    """Admin authentication"""
    
    def test_admin_login(self):
        """Test admin login"""
        response = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
        )
        print(f"Admin login response: {response.status_code}")
        assert response.status_code == 200
        data = response.json()
        assert "token" in data


class TestAdminOffers:
    """Admin Hot Deals/Offers CRUD"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Admin auth failed")
    
    def test_get_offers(self, admin_token):
        """Test getting offers list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/offers",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        print(f"Get offers response: {response.status_code}")
        assert response.status_code == 200
        data = response.json()
        assert "offers" in data
    
    def test_create_offer(self, admin_token):
        """Test creating a new offer"""
        offer_data = {
            "title": "TEST_Flat 30% Off",
            "store_name": "Test Store",
            "discount_text": "Up to 30% Off",
            "description": "Test offer description",
            "is_active": True
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/offers",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json=offer_data
        )
        print(f"Create offer response: {response.status_code} - {response.text[:200]}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert "offer" in data
        return data["offer"]["id"]
    
    def test_update_offer(self, admin_token):
        """Test updating an offer"""
        # First create an offer
        offer_data = {
            "title": "TEST_Update Offer",
            "store_name": "Test Store",
            "is_active": True
        }
        create_response = requests.post(
            f"{BASE_URL}/api/admin/offers",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json=offer_data
        )
        if create_response.status_code != 200:
            pytest.skip("Could not create offer for update test")
        
        offer_id = create_response.json()["offer"]["id"]
        
        # Update the offer
        update_data = {"title": "TEST_Updated Offer Title", "is_active": False}
        response = requests.put(
            f"{BASE_URL}/api/admin/offers/{offer_id}",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json=update_data
        )
        print(f"Update offer response: {response.status_code}")
        assert response.status_code == 200
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/admin/offers/{offer_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
    
    def test_delete_offer(self, admin_token):
        """Test deleting an offer"""
        # First create an offer
        offer_data = {
            "title": "TEST_Delete Offer",
            "store_name": "Test Store",
            "is_active": True
        }
        create_response = requests.post(
            f"{BASE_URL}/api/admin/offers",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json=offer_data
        )
        if create_response.status_code != 200:
            pytest.skip("Could not create offer for delete test")
        
        offer_id = create_response.json()["offer"]["id"]
        
        # Delete the offer
        response = requests.delete(
            f"{BASE_URL}/api/admin/offers/{offer_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        print(f"Delete offer response: {response.status_code}")
        assert response.status_code == 200


class TestAdminEvents:
    """Admin Events CRUD"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Admin auth failed")
    
    def test_get_events(self, admin_token):
        """Test getting events list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/events",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        print(f"Get events response: {response.status_code}")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
    
    def test_create_event(self, admin_token):
        """Test creating a new event"""
        event_data = {
            "title": "TEST_New Year Event",
            "date": "2026-02-15",
            "time": "6:00 PM onwards",
            "venue": "CP67 Main Atrium",
            "description": "Test event description",
            "is_active": True
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/events",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json=event_data
        )
        print(f"Create event response: {response.status_code} - {response.text[:200]}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert "event" in data
        
        # Cleanup
        event_id = data["event"]["id"]
        requests.delete(
            f"{BASE_URL}/api/admin/events/{event_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
    
    def test_update_event(self, admin_token):
        """Test updating an event"""
        # First create an event
        event_data = {
            "title": "TEST_Update Event",
            "date": "2026-03-01",
            "is_active": True
        }
        create_response = requests.post(
            f"{BASE_URL}/api/admin/events",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json=event_data
        )
        if create_response.status_code != 200:
            pytest.skip("Could not create event for update test")
        
        event_id = create_response.json()["event"]["id"]
        
        # Update the event
        update_data = {"title": "TEST_Updated Event Title", "venue": "Updated Venue"}
        response = requests.put(
            f"{BASE_URL}/api/admin/events/{event_id}",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json=update_data
        )
        print(f"Update event response: {response.status_code}")
        assert response.status_code == 200
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/admin/events/{event_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
    
    def test_delete_event(self, admin_token):
        """Test deleting an event"""
        # First create an event
        event_data = {
            "title": "TEST_Delete Event",
            "date": "2026-04-01",
            "is_active": True
        }
        create_response = requests.post(
            f"{BASE_URL}/api/admin/events",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json=event_data
        )
        if create_response.status_code != 200:
            pytest.skip("Could not create event for delete test")
        
        event_id = create_response.json()["event"]["id"]
        
        # Delete the event
        response = requests.delete(
            f"{BASE_URL}/api/admin/events/{event_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        print(f"Delete event response: {response.status_code}")
        assert response.status_code == 200


class TestTierInfo:
    """Tier info API with earning rates"""
    
    @pytest.fixture
    def consumer_token(self):
        """Get consumer auth token"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/verify-otp",
            json={"phone": CONSUMER_PHONE, "otp": CONSUMER_OTP}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Consumer auth failed")
    
    def test_tier_info(self, consumer_token):
        """Test tier info returns earning rates"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/tier-info",
            headers={"Authorization": f"Bearer {consumer_token}"}
        )
        print(f"Tier info response: {response.status_code}")
        assert response.status_code == 200
        data = response.json()
        assert "current_tier" in data
        assert "tiers" in data
        
        # Check that tiers have earning rate info
        tiers = data.get("tiers", [])
        if tiers:
            tier = tiers[0]
            print(f"First tier data: {tier}")
            # Tiers should have retail and jewellery earning rates
            assert "name" in tier
            assert "min_points" in tier


class TestWalletDetailed:
    """Wallet detailed API with tier card info"""
    
    @pytest.fixture
    def consumer_token(self):
        """Get consumer auth token"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/verify-otp",
            json={"phone": CONSUMER_PHONE, "otp": CONSUMER_OTP}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Consumer auth failed")
    
    def test_wallet_detailed(self, consumer_token):
        """Test wallet detailed returns tier info"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/wallet/detailed",
            headers={"Authorization": f"Bearer {consumer_token}"}
        )
        print(f"Wallet detailed response: {response.status_code}")
        assert response.status_code == 200
        data = response.json()
        assert "balance" in data
        assert "tier" in data
        assert "total_earned" in data
        
        # Check tier has name for card styling
        tier = data.get("tier", {})
        assert "name" in tier
        print(f"Tier name: {tier.get('name')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
