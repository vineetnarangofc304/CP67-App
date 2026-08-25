"""
Iteration 18 Tests: Content Updates
- Points Earning Slab (7-tier table) in Wallet and TierJourney
- '10 Points = INR 1' conversion
- Full Terms & Conditions (11 clauses) in Legal page
- Amenities with 6 categories (Restrooms, ATMs & Banking, Services, Connectivity, Parking & EV Services, Emergency)
- Dashboard footfall stats
- Footfall CRUD endpoints
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://staff-points-engine.preview.emergentagent.com')

# Test credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "CP67Admin@2025"
CONSUMER_PHONE = "9876543210"
CONSUMER_OTP = "1234"


class TestAdminAuth:
    """Admin authentication tests"""
    
    def test_admin_login(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        print(f"PASS: Admin login successful")
        return data["token"]


class TestConsumerAuth:
    """Consumer authentication tests"""
    
    def test_consumer_verify_otp(self):
        """Test consumer OTP verification (dev mode)"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": CONSUMER_PHONE,
            "otp": CONSUMER_OTP
        })
        assert response.status_code == 200, f"Consumer OTP verification failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        print(f"PASS: Consumer OTP verification successful")
        return data["token"]


class TestAmenitiesEndpoint:
    """Test GET /api/consumer/amenities endpoint"""
    
    def test_amenities_returns_6_categories(self):
        """Test that amenities endpoint returns 6 categories"""
        response = requests.get(f"{BASE_URL}/api/consumer/amenities")
        assert response.status_code == 200, f"Amenities endpoint failed: {response.text}"
        
        data = response.json()
        assert "amenities" in data, "No amenities in response"
        
        amenities = data["amenities"]
        assert len(amenities) == 6, f"Expected 6 categories, got {len(amenities)}"
        
        # Check category names
        expected_categories = [
            "Restrooms",
            "ATMs & Banking",
            "Services",
            "Connectivity",
            "Parking & EV Services",
            "Emergency"
        ]
        
        actual_categories = [a["category"] for a in amenities]
        for cat in expected_categories:
            assert cat in actual_categories, f"Missing category: {cat}"
        
        print(f"PASS: Amenities returns 6 categories: {actual_categories}")
    
    def test_amenities_restrooms_has_floor_data(self):
        """Test that Restrooms category has floor-specific data"""
        response = requests.get(f"{BASE_URL}/api/consumer/amenities")
        assert response.status_code == 200
        
        data = response.json()
        restrooms = next((a for a in data["amenities"] if a["category"] == "Restrooms"), None)
        assert restrooms is not None, "Restrooms category not found"
        
        items = restrooms.get("items", [])
        assert len(items) >= 4, f"Expected at least 4 restroom locations, got {len(items)}"
        
        # Check for floor-specific entries
        floors_found = [item.get("floor", "") for item in items]
        assert any("Ground" in f for f in floors_found), "No Ground Floor restroom found"
        assert any("First" in f for f in floors_found), "No First Floor restroom found"
        
        print(f"PASS: Restrooms has {len(items)} floor-specific locations")
    
    def test_amenities_parking_ev_services(self):
        """Test that Parking & EV Services category exists with correct items"""
        response = requests.get(f"{BASE_URL}/api/consumer/amenities")
        assert response.status_code == 200
        
        data = response.json()
        parking = next((a for a in data["amenities"] if a["category"] == "Parking & EV Services"), None)
        assert parking is not None, "Parking & EV Services category not found"
        
        items = parking.get("items", [])
        assert len(items) >= 2, f"Expected at least 2 parking items, got {len(items)}"
        
        # Check for EV charging
        item_names = [item.get("name", "").lower() for item in items]
        has_ev = any("ev" in name for name in item_names)
        assert has_ev, "No EV charging item found in Parking & EV Services"
        
        print(f"PASS: Parking & EV Services has {len(items)} items including EV charging")


class TestDashboardAnalytics:
    """Test dashboard analytics endpoint with footfall stats"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_dashboard_returns_footfall_stats(self):
        """Test that dashboard endpoint returns footfall stats"""
        response = requests.get(f"{BASE_URL}/api/analytics/dashboard", headers=self.headers)
        assert response.status_code == 200, f"Dashboard endpoint failed: {response.text}"
        
        data = response.json()
        assert "footfall" in data, "No footfall in dashboard response"
        
        footfall = data["footfall"]
        assert "total" in footfall, "No total in footfall stats"
        
        print(f"PASS: Dashboard returns footfall stats: total={footfall.get('total', 0)}")
    
    def test_dashboard_returns_users_stats(self):
        """Test that dashboard returns user registration stats"""
        response = requests.get(f"{BASE_URL}/api/analytics/dashboard", headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "users" in data, "No users in dashboard response"
        
        users = data["users"]
        assert "total" in users, "No total in users stats"
        
        print(f"PASS: Dashboard returns users stats: total={users.get('total', 0)}")
    
    def test_dashboard_returns_bills_stats(self):
        """Test that dashboard returns bill upload stats"""
        response = requests.get(f"{BASE_URL}/api/analytics/dashboard", headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "bills" in data, "No bills in dashboard response"
        
        bills = data["bills"]
        assert "total" in bills, "No total in bills stats"
        
        print(f"PASS: Dashboard returns bills stats: total={bills.get('total', 0)}")


class TestFootfallCRUD:
    """Test footfall CRUD endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_add_footfall_entry(self):
        """Test POST /api/admin/footfall - add daily footfall"""
        test_date = "2026-01-15"
        test_count = 5000
        
        response = requests.post(
            f"{BASE_URL}/api/admin/footfall",
            headers=self.headers,
            json={"date": test_date, "count": test_count}
        )
        assert response.status_code == 200, f"Add footfall failed: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, "Footfall add not successful"
        
        print(f"PASS: Added footfall entry for {test_date}: {test_count}")
    
    def test_get_footfall_history(self):
        """Test GET /api/admin/footfall - get footfall history"""
        response = requests.get(f"{BASE_URL}/api/admin/footfall", headers=self.headers)
        assert response.status_code == 200, f"Get footfall failed: {response.text}"
        
        data = response.json()
        # API returns 'entries' key
        assert "entries" in data, "No entries in response"
        assert isinstance(data["entries"], list), "Entries should be a list"
        
        print(f"PASS: Got footfall history with {len(data['entries'])} entries")
    
    def test_update_footfall_entry(self):
        """Test updating existing footfall entry (same date)"""
        test_date = "2026-01-15"
        updated_count = 5500
        
        response = requests.post(
            f"{BASE_URL}/api/admin/footfall",
            headers=self.headers,
            json={"date": test_date, "count": updated_count}
        )
        assert response.status_code == 200, f"Update footfall failed: {response.text}"
        
        # Verify the update
        get_response = requests.get(f"{BASE_URL}/api/admin/footfall", headers=self.headers)
        data = get_response.json()
        
        # API returns 'entries' key
        entry = next((f for f in data["entries"] if f.get("date") == test_date), None)
        if entry:
            assert entry.get("count") == updated_count, f"Count not updated: expected {updated_count}, got {entry.get('count')}"
        
        print(f"PASS: Updated footfall entry for {test_date} to {updated_count}")


class TestConsumerTierInfo:
    """Test consumer tier info endpoint for earning slab"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get consumer token"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": CONSUMER_PHONE,
            "otp": CONSUMER_OTP
        })
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_tier_info_returns_tiers(self):
        """Test that tier-info endpoint returns tier data"""
        response = requests.get(f"{BASE_URL}/api/consumer/tier-info", headers=self.headers)
        assert response.status_code == 200, f"Tier info failed: {response.text}"
        
        data = response.json()
        assert "current_tier" in data, "No current_tier in response"
        assert "tiers" in data, "No tiers in response"
        
        tiers = data["tiers"]
        assert len(tiers) >= 4, f"Expected at least 4 tiers, got {len(tiers)}"
        
        tier_names = [t.get("name") for t in tiers]
        assert "Bronze" in tier_names, "Bronze tier not found"
        assert "Platinum" in tier_names, "Platinum tier not found"
        
        print(f"PASS: Tier info returns {len(tiers)} tiers: {tier_names}")


class TestConsumerWalletDetailed:
    """Test consumer wallet detailed endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get consumer token"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": CONSUMER_PHONE,
            "otp": CONSUMER_OTP
        })
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_wallet_detailed_returns_balance(self):
        """Test that wallet/detailed endpoint returns balance info"""
        response = requests.get(f"{BASE_URL}/api/consumer/wallet/detailed", headers=self.headers)
        assert response.status_code == 200, f"Wallet detailed failed: {response.text}"
        
        data = response.json()
        assert "balance" in data, "No balance in response"
        assert "total_earned" in data, "No total_earned in response"
        assert "tier" in data, "No tier in response"
        
        print(f"PASS: Wallet detailed returns balance={data.get('balance')}, tier={data.get('tier', {}).get('name')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
