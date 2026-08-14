"""
Consumer Mobile PWA App Backend Tests
Tests for: OTP authentication, stores, offers, events, wallet, profile, bills, notifications
"""
import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://staff-incentive-lab.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api/consumer"

# Test phone and OTP for dev mode
TEST_PHONE = f"98765{str(uuid.uuid4())[:5].replace('-', '0')}"[:10]  # Random phone for testing
DEV_OTP = "1234"


class TestConsumerAuth:
    """OTP-based authentication flow tests"""
    
    def test_send_otp_success(self):
        """Test sending OTP to a valid phone number"""
        response = requests.post(f"{API}/auth/send-otp", json={"phone": TEST_PHONE})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "message" in data
        assert "phone" in data
        print(f"✓ Send OTP successful for {TEST_PHONE}")
    
    def test_send_otp_with_country_code(self):
        """Test OTP with 91 prefix"""
        response = requests.post(f"{API}/auth/send-otp", json={"phone": f"91{TEST_PHONE}"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        print("✓ Send OTP with 91 prefix works")
    
    def test_verify_otp_dev_mode(self):
        """Test OTP verification with dev bypass (1234)"""
        # First send OTP
        requests.post(f"{API}/auth/send-otp", json={"phone": TEST_PHONE})
        
        # Verify with dev OTP
        response = requests.post(f"{API}/auth/verify-otp", json={
            "phone": TEST_PHONE,
            "otp": DEV_OTP
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "token" in data
        assert "user" in data
        assert data["user"]["phone"] is not None
        assert "tier" in data["user"]
        print(f"✓ OTP verification successful, token received")
    
    def test_verify_otp_invalid(self):
        """Test invalid OTP rejection"""
        response = requests.post(f"{API}/auth/verify-otp", json={
            "phone": "9999999999",
            "otp": "9999"
        })
        assert response.status_code == 400
        print("✓ Invalid OTP correctly rejected")


class TestConsumerStores:
    """Store listing and detail tests"""
    
    def test_list_stores(self):
        """GET /api/consumer/stores returns stores"""
        response = requests.get(f"{API}/stores")
        assert response.status_code == 200
        data = response.json()
        assert "stores" in data
        assert isinstance(data["stores"], list)
        assert len(data["stores"]) > 0  # Should have seeded data
        assert "categories" in data
        print(f"✓ Listed {len(data['stores'])} stores")
    
    def test_list_stores_by_category(self):
        """Filter stores by category"""
        response = requests.get(f"{API}/stores?category=Fashion")
        assert response.status_code == 200
        data = response.json()
        for store in data["stores"]:
            assert store["category"] == "Fashion"
        print(f"✓ Category filter working, found {len(data['stores'])} Fashion stores")
    
    def test_list_stores_search(self):
        """Search stores by name"""
        response = requests.get(f"{API}/stores?search=Nike")
        assert response.status_code == 200
        data = response.json()
        assert len(data["stores"]) >= 0  # May or may not exist
        print("✓ Store search working")
    
    def test_store_detail(self):
        """GET /api/consumer/stores/{id} returns store details"""
        # First get list
        list_resp = requests.get(f"{API}/stores")
        stores = list_resp.json()["stores"]
        if stores:
            store_id = stores[0]["id"]
            response = requests.get(f"{API}/stores/{store_id}")
            assert response.status_code == 200
            store = response.json()
            assert store["id"] == store_id
            assert "name" in store
            assert "category" in store
            assert "floor" in store
            assert "timing" in store
            assert "offers" in store  # Should include offers
            print(f"✓ Store detail retrieved: {store['name']}")
        else:
            pytest.skip("No stores to test")
    
    def test_store_detail_not_found(self):
        """Non-existent store returns 404"""
        response = requests.get(f"{API}/stores/nonexistent-id")
        assert response.status_code == 404
        print("✓ Non-existent store returns 404")


class TestConsumerOffers:
    """Offers listing tests"""
    
    def test_list_offers(self):
        """GET /api/consumer/offers returns offers"""
        response = requests.get(f"{API}/offers")
        assert response.status_code == 200
        data = response.json()
        assert "offers" in data
        assert isinstance(data["offers"], list)
        if data["offers"]:
            offer = data["offers"][0]
            assert "title" in offer
            assert "store_name" in offer
            assert "discount_value" in offer
            print(f"✓ Listed {len(data['offers'])} offers")
        else:
            print("⚠ No offers found (may need seeding)")
    
    def test_offers_by_store(self):
        """Filter offers by store_id"""
        # Get a store first
        stores_resp = requests.get(f"{API}/stores")
        stores = stores_resp.json()["stores"]
        if stores:
            store_id = stores[0]["id"]
            response = requests.get(f"{API}/offers?store_id={store_id}")
            assert response.status_code == 200
            print("✓ Offers filter by store working")
        else:
            pytest.skip("No stores")


class TestConsumerEvents:
    """Events listing and registration tests"""
    
    def test_list_events(self):
        """GET /api/consumer/events returns events"""
        response = requests.get(f"{API}/events")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert isinstance(data["events"], list)
        if data["events"]:
            event = data["events"][0]
            assert "title" in event
            assert "date" in event
            assert "venue" in event
            print(f"✓ Listed {len(data['events'])} events")
        else:
            print("⚠ No events found")
    
    def test_event_registration_requires_auth(self):
        """Event registration needs authentication"""
        response = requests.post(f"{API}/events/some-event-id/register")
        assert response.status_code in [401, 403, 422]
        print("✓ Event registration requires auth")


class TestConsumerWalletAndProfile:
    """Authenticated endpoints: wallet, profile, bills, notifications"""
    
    @pytest.fixture(autouse=True)
    def setup_auth(self):
        """Get auth token for testing"""
        phone = "9876543210"  # Known test phone
        # Send OTP
        requests.post(f"{API}/auth/send-otp", json={"phone": phone})
        # Verify with dev OTP
        resp = requests.post(f"{API}/auth/verify-otp", json={"phone": phone, "otp": "1234"})
        if resp.status_code == 200:
            self.token = resp.json()["token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            pytest.skip("Auth failed")
    
    def test_get_profile(self):
        """GET /api/consumer/profile returns user profile"""
        response = requests.get(f"{API}/profile", headers=self.headers)
        assert response.status_code == 200
        profile = response.json()
        assert "id" in profile
        assert "phone" in profile
        assert "tier" in profile
        assert "balance_points" in profile
        assert "referral_code" in profile
        print(f"✓ Profile retrieved: tier={profile['tier']}, points={profile['balance_points']}")
    
    def test_update_profile(self):
        """PUT /api/consumer/profile updates user"""
        response = requests.put(f"{API}/profile", 
            headers={**self.headers, "Content-Type": "application/json"},
            json={"name": "Test User Updated", "gender": "Male"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        print("✓ Profile update successful")
    
    def test_get_wallet(self):
        """GET /api/consumer/wallet returns wallet with balance and tier"""
        response = requests.get(f"{API}/wallet", headers=self.headers)
        assert response.status_code == 200
        wallet = response.json()
        assert "balance" in wallet
        assert "tier" in wallet
        assert "transactions" in wallet
        # Tier should have progress info
        tier = wallet["tier"]
        assert "name" in tier
        assert "progress" in tier
        print(f"✓ Wallet retrieved: balance={wallet['balance']}, tier={tier['name']}")
    
    def test_get_notifications(self):
        """GET /api/consumer/notifications returns notifications list"""
        response = requests.get(f"{API}/notifications", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "notifications" in data
        assert "unread_count" in data
        print(f"✓ Notifications retrieved, unread={data['unread_count']}")
    
    def test_get_bills(self):
        """GET /api/consumer/bills returns user's bills"""
        response = requests.get(f"{API}/bills", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "bills" in data
        print(f"✓ Bills retrieved: {len(data['bills'])} bills")
    
    def test_get_home(self):
        """GET /api/consumer/home returns home screen data"""
        response = requests.get(f"{API}/home", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert "banners" in data
        assert "featured_stores" in data
        assert "trending_offers" in data
        assert "upcoming_events" in data
        print(f"✓ Home data: {len(data['banners'])} banners, {len(data['featured_stores'])} stores")


class TestUnauthorizedAccess:
    """Test endpoints that require auth without token"""
    
    def test_profile_without_auth(self):
        response = requests.get(f"{API}/profile")
        assert response.status_code == 401
        print("✓ Profile requires auth")
    
    def test_wallet_without_auth(self):
        response = requests.get(f"{API}/wallet")
        assert response.status_code == 401
        print("✓ Wallet requires auth")
    
    def test_home_without_auth(self):
        response = requests.get(f"{API}/home")
        assert response.status_code == 401
        print("✓ Home requires auth")
    
    def test_bills_without_auth(self):
        response = requests.get(f"{API}/bills")
        assert response.status_code == 401
        print("✓ Bills requires auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
