"""
Iteration 17 Tests: Campaign Engine & Tier Journey Features
Tests for:
- Admin Campaign CRUD (GET, POST, PUT, DELETE, toggle)
- Consumer campaigns endpoint
- Consumer tier-info endpoint
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://staff-incentive-lab.preview.emergentagent.com')

# Test credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "CP67Admin@2025"
CONSUMER_PHONE = "9876543210"
CONSUMER_OTP = "1234"


class TestAdminAuth:
    """Admin authentication tests"""
    
    def test_admin_login(self):
        """Test admin login and get token"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert data["username"] == ADMIN_USERNAME
        print(f"✓ Admin login successful, token received")
        return data["token"]


class TestAdminCampaigns:
    """Admin Campaign CRUD tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token before each test"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_campaigns_list(self):
        """GET /api/admin/campaigns - returns list of campaigns"""
        response = requests.get(f"{BASE_URL}/api/admin/campaigns", headers=self.headers)
        assert response.status_code == 200, f"Failed to get campaigns: {response.text}"
        data = response.json()
        assert "campaigns" in data, "No campaigns key in response"
        assert "total" in data, "No total key in response"
        print(f"✓ GET /api/admin/campaigns - {data['total']} campaigns found")
        return data["campaigns"]
    
    def test_create_campaign_multiplier(self):
        """POST /api/admin/campaigns - create multiplier campaign"""
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        payload = {
            "name": "TEST_Weekend Double Points",
            "description": "Earn 2X points this weekend",
            "campaign_type": "multiplier",
            "multiplier": 2.0,
            "bonus_points": 0,
            "min_spend": 0,
            "applicable_floors": ["Ground Floor", "First Floor"],
            "applicable_categories": ["Fashion", "Electronics"],
            "applicable_brand_ids": None,
            "start_date": start_date,
            "end_date": end_date,
            "is_active": True
        }
        
        response = requests.post(f"{BASE_URL}/api/admin/campaigns", 
                                headers={**self.headers, "Content-Type": "application/json"},
                                json=payload)
        assert response.status_code == 200, f"Failed to create campaign: {response.text}"
        data = response.json()
        assert data.get("success") == True, "Campaign creation not successful"
        assert "campaign" in data, "No campaign in response"
        campaign = data["campaign"]
        assert campaign["name"] == payload["name"]
        assert campaign["campaign_type"] == "multiplier"
        assert campaign["multiplier"] == 2.0
        assert campaign["applicable_floors"] == ["Ground Floor", "First Floor"]
        print(f"✓ POST /api/admin/campaigns - Created multiplier campaign: {campaign['id']}")
        return campaign["id"]
    
    def test_create_campaign_bonus(self):
        """POST /api/admin/campaigns - create bonus points campaign"""
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        
        payload = {
            "name": "TEST_Food Court Festival Bonus",
            "description": "Get 100 bonus points on Food Court purchases",
            "campaign_type": "bonus",
            "multiplier": 1.0,
            "bonus_points": 100,
            "min_spend": 0,
            "applicable_floors": ["Food Court"],
            "applicable_categories": None,
            "applicable_brand_ids": None,
            "start_date": start_date,
            "end_date": end_date,
            "is_active": True
        }
        
        response = requests.post(f"{BASE_URL}/api/admin/campaigns", 
                                headers={**self.headers, "Content-Type": "application/json"},
                                json=payload)
        assert response.status_code == 200, f"Failed to create bonus campaign: {response.text}"
        data = response.json()
        assert data.get("success") == True
        campaign = data["campaign"]
        assert campaign["campaign_type"] == "bonus"
        assert campaign["bonus_points"] == 100
        print(f"✓ POST /api/admin/campaigns - Created bonus campaign: {campaign['id']}")
        return campaign["id"]
    
    def test_create_campaign_spend_threshold(self):
        """POST /api/admin/campaigns - create spend threshold campaign"""
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        payload = {
            "name": "TEST_Spend Rs.5000 Get 500 Bonus",
            "description": "Spend Rs.5000 or more and get 500 bonus points",
            "campaign_type": "spend_threshold",
            "multiplier": 1.0,
            "bonus_points": 500,
            "min_spend": 5000,
            "applicable_floors": None,
            "applicable_categories": None,
            "applicable_brand_ids": None,
            "start_date": start_date,
            "end_date": end_date,
            "is_active": True
        }
        
        response = requests.post(f"{BASE_URL}/api/admin/campaigns", 
                                headers={**self.headers, "Content-Type": "application/json"},
                                json=payload)
        assert response.status_code == 200, f"Failed to create spend_threshold campaign: {response.text}"
        data = response.json()
        assert data.get("success") == True
        campaign = data["campaign"]
        assert campaign["campaign_type"] == "spend_threshold"
        assert campaign["min_spend"] == 5000
        assert campaign["bonus_points"] == 500
        print(f"✓ POST /api/admin/campaigns - Created spend_threshold campaign: {campaign['id']}")
        return campaign["id"]
    
    def test_create_campaign_first_visit(self):
        """POST /api/admin/campaigns - create first visit campaign"""
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
        
        payload = {
            "name": "TEST_First Visit Welcome Bonus",
            "description": "Get 200 bonus points on your first visit",
            "campaign_type": "first_visit",
            "multiplier": 1.0,
            "bonus_points": 200,
            "min_spend": 0,
            "applicable_floors": None,
            "applicable_categories": None,
            "applicable_brand_ids": None,
            "start_date": start_date,
            "end_date": end_date,
            "is_active": True
        }
        
        response = requests.post(f"{BASE_URL}/api/admin/campaigns", 
                                headers={**self.headers, "Content-Type": "application/json"},
                                json=payload)
        assert response.status_code == 200, f"Failed to create first_visit campaign: {response.text}"
        data = response.json()
        assert data.get("success") == True
        campaign = data["campaign"]
        assert campaign["campaign_type"] == "first_visit"
        assert campaign["bonus_points"] == 200
        print(f"✓ POST /api/admin/campaigns - Created first_visit campaign: {campaign['id']}")
        return campaign["id"]
    
    def test_update_campaign(self):
        """PUT /api/admin/campaigns/{id} - update campaign"""
        # First create a campaign
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        create_payload = {
            "name": "TEST_Update Test Campaign",
            "description": "Original description",
            "campaign_type": "multiplier",
            "multiplier": 2.0,
            "bonus_points": 0,
            "min_spend": 0,
            "applicable_floors": None,
            "applicable_categories": None,
            "applicable_brand_ids": None,
            "start_date": start_date,
            "end_date": end_date,
            "is_active": True
        }
        
        create_response = requests.post(f"{BASE_URL}/api/admin/campaigns", 
                                       headers={**self.headers, "Content-Type": "application/json"},
                                       json=create_payload)
        campaign_id = create_response.json()["campaign"]["id"]
        
        # Now update it
        update_payload = {
            "name": "TEST_Updated Campaign Name",
            "description": "Updated description",
            "campaign_type": "multiplier",
            "multiplier": 3.0,
            "bonus_points": 0,
            "min_spend": 0,
            "applicable_floors": ["Second Floor"],
            "applicable_categories": ["Beauty"],
            "applicable_brand_ids": None,
            "start_date": start_date,
            "end_date": end_date,
            "is_active": True
        }
        
        response = requests.put(f"{BASE_URL}/api/admin/campaigns/{campaign_id}", 
                               headers={**self.headers, "Content-Type": "application/json"},
                               json=update_payload)
        assert response.status_code == 200, f"Failed to update campaign: {response.text}"
        data = response.json()
        assert data.get("success") == True
        campaign = data["campaign"]
        assert campaign["name"] == "TEST_Updated Campaign Name"
        assert campaign["multiplier"] == 3.0
        assert campaign["applicable_floors"] == ["Second Floor"]
        print(f"✓ PUT /api/admin/campaigns/{campaign_id} - Campaign updated successfully")
        return campaign_id
    
    def test_toggle_campaign(self):
        """PUT /api/admin/campaigns/{id}/toggle - toggle active status"""
        # First create a campaign
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        create_payload = {
            "name": "TEST_Toggle Test Campaign",
            "description": "Test toggle",
            "campaign_type": "multiplier",
            "multiplier": 2.0,
            "bonus_points": 0,
            "min_spend": 0,
            "applicable_floors": None,
            "applicable_categories": None,
            "applicable_brand_ids": None,
            "start_date": start_date,
            "end_date": end_date,
            "is_active": True
        }
        
        create_response = requests.post(f"{BASE_URL}/api/admin/campaigns", 
                                       headers={**self.headers, "Content-Type": "application/json"},
                                       json=create_payload)
        campaign_id = create_response.json()["campaign"]["id"]
        
        # Toggle to inactive
        response = requests.put(f"{BASE_URL}/api/admin/campaigns/{campaign_id}/toggle", 
                               headers=self.headers)
        assert response.status_code == 200, f"Failed to toggle campaign: {response.text}"
        data = response.json()
        assert data.get("is_active") == False, "Campaign should be inactive after toggle"
        print(f"✓ PUT /api/admin/campaigns/{campaign_id}/toggle - Toggled to inactive")
        
        # Toggle back to active
        response = requests.put(f"{BASE_URL}/api/admin/campaigns/{campaign_id}/toggle", 
                               headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("is_active") == True, "Campaign should be active after second toggle"
        print(f"✓ PUT /api/admin/campaigns/{campaign_id}/toggle - Toggled back to active")
        return campaign_id
    
    def test_delete_campaign(self):
        """DELETE /api/admin/campaigns/{id} - delete campaign"""
        # First create a campaign
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        create_payload = {
            "name": "TEST_Delete Test Campaign",
            "description": "To be deleted",
            "campaign_type": "bonus",
            "multiplier": 1.0,
            "bonus_points": 50,
            "min_spend": 0,
            "applicable_floors": None,
            "applicable_categories": None,
            "applicable_brand_ids": None,
            "start_date": start_date,
            "end_date": end_date,
            "is_active": True
        }
        
        create_response = requests.post(f"{BASE_URL}/api/admin/campaigns", 
                                       headers={**self.headers, "Content-Type": "application/json"},
                                       json=create_payload)
        campaign_id = create_response.json()["campaign"]["id"]
        
        # Delete it
        response = requests.delete(f"{BASE_URL}/api/admin/campaigns/{campaign_id}", 
                                  headers=self.headers)
        assert response.status_code == 200, f"Failed to delete campaign: {response.text}"
        data = response.json()
        assert data.get("success") == True
        print(f"✓ DELETE /api/admin/campaigns/{campaign_id} - Campaign deleted")
        
        # Verify it's gone
        list_response = requests.get(f"{BASE_URL}/api/admin/campaigns", headers=self.headers)
        campaigns = list_response.json()["campaigns"]
        campaign_ids = [c["id"] for c in campaigns]
        assert campaign_id not in campaign_ids, "Deleted campaign still in list"
        print(f"✓ Verified campaign {campaign_id} no longer in list")
    
    def test_get_active_campaigns(self):
        """GET /api/admin/campaigns/active - returns currently active campaigns"""
        response = requests.get(f"{BASE_URL}/api/admin/campaigns/active")
        assert response.status_code == 200, f"Failed to get active campaigns: {response.text}"
        data = response.json()
        assert "campaigns" in data, "No campaigns key in response"
        print(f"✓ GET /api/admin/campaigns/active - {len(data['campaigns'])} active campaigns")


class TestConsumerAuth:
    """Consumer authentication tests"""
    
    def test_consumer_verify_otp(self):
        """POST /api/consumer/auth/verify-otp - verify OTP and get token"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": CONSUMER_PHONE,
            "otp": CONSUMER_OTP
        })
        assert response.status_code == 200, f"Consumer OTP verification failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert "token" in data, "No token in response"
        print(f"✓ Consumer OTP verified, token received")
        return data["token"]


class TestConsumerCampaigns:
    """Consumer campaigns endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get consumer token before each test"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": CONSUMER_PHONE,
            "otp": CONSUMER_OTP
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_consumer_campaigns(self):
        """GET /api/consumer/campaigns - returns active campaigns for consumer"""
        response = requests.get(f"{BASE_URL}/api/consumer/campaigns", headers=self.headers)
        assert response.status_code == 200, f"Failed to get consumer campaigns: {response.text}"
        data = response.json()
        assert "campaigns" in data, "No campaigns key in response"
        
        # Verify campaign structure (should not include internal fields)
        for campaign in data["campaigns"]:
            assert "name" in campaign
            assert "campaign_type" in campaign
            assert "applicable_brand_ids" not in campaign, "Internal field exposed to consumer"
            assert "created_by" not in campaign, "Internal field exposed to consumer"
        
        print(f"✓ GET /api/consumer/campaigns - {len(data['campaigns'])} active campaigns for consumer")


class TestConsumerTierInfo:
    """Consumer tier-info endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get consumer token before each test"""
        response = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={
            "phone": CONSUMER_PHONE,
            "otp": CONSUMER_OTP
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_tier_info(self):
        """GET /api/consumer/tier-info - returns tier data with current tier, all tiers, benefits"""
        response = requests.get(f"{BASE_URL}/api/consumer/tier-info", headers=self.headers)
        assert response.status_code == 200, f"Failed to get tier info: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "current_tier" in data, "No current_tier in response"
        assert "total_earned" in data, "No total_earned in response"
        assert "tiers" in data, "No tiers in response"
        
        # Verify current_tier structure
        current_tier = data["current_tier"]
        assert "name" in current_tier, "No name in current_tier"
        assert current_tier["name"] in ["Bronze", "Silver", "Gold", "Platinum"], f"Invalid tier name: {current_tier['name']}"
        
        # Verify tiers array
        tiers = data["tiers"]
        assert len(tiers) == 4, f"Expected 4 tiers, got {len(tiers)}"
        
        tier_names = [t["name"] for t in tiers]
        assert tier_names == ["Bronze", "Silver", "Gold", "Platinum"], f"Unexpected tier order: {tier_names}"
        
        # Verify tier structure
        for tier in tiers:
            assert "name" in tier
            assert "min_points" in tier
            assert "color" in tier
            assert "benefits" in tier
            assert isinstance(tier["benefits"], list)
            assert len(tier["benefits"]) > 0, f"No benefits for tier {tier['name']}"
        
        # Verify tier thresholds
        assert tiers[0]["min_points"] == 0, "Bronze should start at 0 points"
        assert tiers[1]["min_points"] == 2500, "Silver should start at 2500 points"
        assert tiers[2]["min_points"] == 10000, "Gold should start at 10000 points"
        assert tiers[3]["min_points"] == 25000, "Platinum should start at 25000 points"
        
        print(f"✓ GET /api/consumer/tier-info - Current tier: {current_tier['name']}, Total earned: {data['total_earned']}")
        print(f"  Tiers: {tier_names}")
        print(f"  Benefits per tier: Bronze({len(tiers[0]['benefits'])}), Silver({len(tiers[1]['benefits'])}), Gold({len(tiers[2]['benefits'])}), Platinum({len(tiers[3]['benefits'])})")


class TestCleanup:
    """Cleanup test campaigns created during testing"""
    
    def test_cleanup_test_campaigns(self):
        """Delete all TEST_ prefixed campaigns"""
        # Get admin token
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD
        })
        token = response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get all campaigns
        list_response = requests.get(f"{BASE_URL}/api/admin/campaigns", headers=headers)
        campaigns = list_response.json()["campaigns"]
        
        # Delete TEST_ prefixed campaigns
        deleted = 0
        for campaign in campaigns:
            if campaign["name"].startswith("TEST_"):
                delete_response = requests.delete(f"{BASE_URL}/api/admin/campaigns/{campaign['id']}", 
                                                 headers=headers)
                if delete_response.status_code == 200:
                    deleted += 1
        
        print(f"✓ Cleanup: Deleted {deleted} test campaigns")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
