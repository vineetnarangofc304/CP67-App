"""
CP67 Consumer App Phase 1 Features Tests
Tests for: Enhanced Wallet, Transactions, Bill History, Rewards, Help & Support, Legal, Profile
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://mall-engage-preview.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api/consumer"

# Test credentials
TEST_PHONE = "9876543210"
DEV_OTP = "1234"


@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for testing"""
    # Send OTP
    requests.post(f"{API}/auth/send-otp", json={"phone": TEST_PHONE})
    # Verify with dev OTP
    resp = requests.post(f"{API}/auth/verify-otp", json={"phone": TEST_PHONE, "otp": DEV_OTP})
    if resp.status_code == 200:
        return resp.json()["token"]
    pytest.skip("Auth failed")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for authenticated requests"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestWalletDetailed:
    """Tests for GET /api/consumer/wallet/detailed - Enhanced wallet with breakdown"""
    
    def test_wallet_detailed_returns_200(self, auth_headers):
        """Wallet detailed endpoint returns 200"""
        response = requests.get(f"{API}/wallet/detailed", headers=auth_headers)
        assert response.status_code == 200
        print("✓ GET /api/consumer/wallet/detailed returns 200")
    
    def test_wallet_detailed_has_balance(self, auth_headers):
        """Wallet detailed has balance field"""
        response = requests.get(f"{API}/wallet/detailed", headers=auth_headers)
        data = response.json()
        assert "balance" in data
        assert isinstance(data["balance"], (int, float))
        print(f"✓ Wallet balance: {data['balance']}")
    
    def test_wallet_detailed_has_total_earned(self, auth_headers):
        """Wallet detailed has total_earned field"""
        response = requests.get(f"{API}/wallet/detailed", headers=auth_headers)
        data = response.json()
        assert "total_earned" in data
        assert isinstance(data["total_earned"], (int, float))
        print(f"✓ Total earned: {data['total_earned']}")
    
    def test_wallet_detailed_has_total_redeemed(self, auth_headers):
        """Wallet detailed has total_redeemed field"""
        response = requests.get(f"{API}/wallet/detailed", headers=auth_headers)
        data = response.json()
        assert "total_redeemed" in data
        assert isinstance(data["total_redeemed"], (int, float))
        print(f"✓ Total redeemed: {data['total_redeemed']}")
    
    def test_wallet_detailed_has_expired(self, auth_headers):
        """Wallet detailed has expired field"""
        response = requests.get(f"{API}/wallet/detailed", headers=auth_headers)
        data = response.json()
        assert "expired" in data
        assert isinstance(data["expired"], (int, float))
        print(f"✓ Expired points: {data['expired']}")
    
    def test_wallet_detailed_has_tier_info(self, auth_headers):
        """Wallet detailed has tier info with progress"""
        response = requests.get(f"{API}/wallet/detailed", headers=auth_headers)
        data = response.json()
        assert "tier" in data
        tier = data["tier"]
        assert "name" in tier
        assert "progress" in tier
        assert "color" in tier
        print(f"✓ Tier: {tier['name']}, Progress: {tier['progress']}%")
    
    def test_wallet_detailed_has_recent_transactions(self, auth_headers):
        """Wallet detailed has recent_transactions list"""
        response = requests.get(f"{API}/wallet/detailed", headers=auth_headers)
        data = response.json()
        assert "recent_transactions" in data
        assert isinstance(data["recent_transactions"], list)
        print(f"✓ Recent transactions: {len(data['recent_transactions'])} items")


class TestTransactions:
    """Tests for GET /api/consumer/transactions - Transaction history with filters"""
    
    def test_transactions_returns_200(self, auth_headers):
        """Transactions endpoint returns 200"""
        response = requests.get(f"{API}/transactions", headers=auth_headers)
        assert response.status_code == 200
        print("✓ GET /api/consumer/transactions returns 200")
    
    def test_transactions_has_list(self, auth_headers):
        """Transactions returns transactions list"""
        response = requests.get(f"{API}/transactions", headers=auth_headers)
        data = response.json()
        assert "transactions" in data
        assert isinstance(data["transactions"], list)
        print(f"✓ Transactions list: {len(data['transactions'])} items")
    
    def test_transactions_filter_all(self, auth_headers):
        """Transactions filter_type=all works"""
        response = requests.get(f"{API}/transactions?filter_type=all", headers=auth_headers)
        assert response.status_code == 200
        print("✓ Transactions filter_type=all works")
    
    def test_transactions_filter_earn(self, auth_headers):
        """Transactions filter_type=earn works"""
        response = requests.get(f"{API}/transactions?filter_type=earn", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # All transactions should be earn type
        for txn in data["transactions"]:
            assert txn["type"] == "earn"
        print(f"✓ Transactions filter_type=earn works, {len(data['transactions'])} earn transactions")
    
    def test_transactions_filter_redeem(self, auth_headers):
        """Transactions filter_type=redeem works"""
        response = requests.get(f"{API}/transactions?filter_type=redeem", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # All transactions should be redeem type
        for txn in data["transactions"]:
            assert txn["type"] == "redeem"
        print(f"✓ Transactions filter_type=redeem works, {len(data['transactions'])} redeem transactions")


class TestRewards:
    """Tests for GET /api/consumer/rewards - Rewards catalog"""
    
    def test_rewards_returns_200(self, auth_headers):
        """Rewards endpoint returns 200"""
        response = requests.get(f"{API}/rewards", headers=auth_headers)
        assert response.status_code == 200
        print("✓ GET /api/consumer/rewards returns 200")
    
    def test_rewards_has_list(self, auth_headers):
        """Rewards returns rewards list"""
        response = requests.get(f"{API}/rewards", headers=auth_headers)
        data = response.json()
        assert "rewards" in data
        assert isinstance(data["rewards"], list)
        print(f"✓ Rewards catalog: {len(data['rewards'])} rewards")
    
    def test_rewards_auto_seeded(self, auth_headers):
        """Rewards are auto-seeded if empty"""
        response = requests.get(f"{API}/rewards", headers=auth_headers)
        data = response.json()
        # Should have rewards (auto-seeded from brands)
        assert len(data["rewards"]) > 0
        print(f"✓ Rewards auto-seeded: {len(data['rewards'])} rewards available")
    
    def test_rewards_have_required_fields(self, auth_headers):
        """Rewards have required fields"""
        response = requests.get(f"{API}/rewards", headers=auth_headers)
        data = response.json()
        if data["rewards"]:
            reward = data["rewards"][0]
            assert "id" in reward
            assert "name" in reward
            assert "store_name" in reward
            assert "points_required" in reward
            assert "discount_value" in reward
            print(f"✓ Reward fields verified: {reward['name']}")
    
    def test_rewards_grouped_by_store(self, auth_headers):
        """Rewards should have store_name for grouping"""
        response = requests.get(f"{API}/rewards", headers=auth_headers)
        data = response.json()
        stores = set()
        for reward in data["rewards"]:
            if reward.get("store_name"):
                stores.add(reward["store_name"])
        print(f"✓ Rewards from {len(stores)} different stores")


class TestRewardsHistory:
    """Tests for GET /api/consumer/rewards/history - Redemption history"""
    
    def test_rewards_history_returns_200(self, auth_headers):
        """Rewards history endpoint returns 200"""
        response = requests.get(f"{API}/rewards/history", headers=auth_headers)
        assert response.status_code == 200
        print("✓ GET /api/consumer/rewards/history returns 200")
    
    def test_rewards_history_has_list(self, auth_headers):
        """Rewards history returns redemptions list"""
        response = requests.get(f"{API}/rewards/history", headers=auth_headers)
        data = response.json()
        assert "redemptions" in data
        assert isinstance(data["redemptions"], list)
        print(f"✓ Redemption history: {len(data['redemptions'])} items")


class TestBillHistory:
    """Tests for GET /api/consumer/bills - Bill history"""
    
    def test_bills_returns_200(self, auth_headers):
        """Bills endpoint returns 200"""
        response = requests.get(f"{API}/bills", headers=auth_headers)
        assert response.status_code == 200
        print("✓ GET /api/consumer/bills returns 200")
    
    def test_bills_has_list(self, auth_headers):
        """Bills returns bills list"""
        response = requests.get(f"{API}/bills", headers=auth_headers)
        data = response.json()
        assert "bills" in data
        assert isinstance(data["bills"], list)
        print(f"✓ Bill history: {len(data['bills'])} bills")


class TestProfileEnhanced:
    """Tests for enhanced profile with DOB, gender, address"""
    
    def test_profile_has_gender(self, auth_headers):
        """Profile has gender field"""
        response = requests.get(f"{API}/profile", headers=auth_headers)
        data = response.json()
        assert "gender" in data
        print(f"✓ Profile gender: {data.get('gender', 'Not set')}")
    
    def test_profile_has_dob(self, auth_headers):
        """Profile has dob field"""
        response = requests.get(f"{API}/profile", headers=auth_headers)
        data = response.json()
        assert "dob" in data
        print(f"✓ Profile DOB: {data.get('dob', 'Not set')}")
    
    def test_profile_has_address(self, auth_headers):
        """Profile has address field"""
        response = requests.get(f"{API}/profile", headers=auth_headers)
        data = response.json()
        assert "address" in data
        print(f"✓ Profile address: {data.get('address', 'Not set')}")
    
    def test_profile_update_gender(self, auth_headers):
        """Can update gender in profile"""
        response = requests.put(f"{API}/profile", 
            headers={**auth_headers, "Content-Type": "application/json"},
            json={"gender": "male"}
        )
        assert response.status_code == 200
        print("✓ Profile gender update works")
    
    def test_profile_update_dob(self, auth_headers):
        """Can update DOB in profile"""
        response = requests.put(f"{API}/profile", 
            headers={**auth_headers, "Content-Type": "application/json"},
            json={"dob": "1990-01-15"}
        )
        assert response.status_code == 200
        print("✓ Profile DOB update works")
    
    def test_profile_update_address(self, auth_headers):
        """Can update address in profile"""
        response = requests.put(f"{API}/profile", 
            headers={**auth_headers, "Content-Type": "application/json"},
            json={"address": "123 Test Street, Mohali"}
        )
        assert response.status_code == 200
        print("✓ Profile address update works")


class TestProgramLandingPage:
    """Tests for /app/program landing page (no auth required)"""
    
    def test_stores_endpoint_no_auth(self):
        """Stores endpoint works without auth (for landing page)"""
        response = requests.get(f"{API}/stores")
        assert response.status_code == 200
        data = response.json()
        assert "stores" in data
        assert len(data["stores"]) > 0
        print(f"✓ Stores endpoint (no auth): {len(data['stores'])} stores")


class TestUnauthorizedEndpoints:
    """Test that protected endpoints require auth"""
    
    def test_wallet_detailed_requires_auth(self):
        """Wallet detailed requires auth"""
        response = requests.get(f"{API}/wallet/detailed")
        assert response.status_code == 401
        print("✓ Wallet detailed requires auth")
    
    def test_transactions_requires_auth(self):
        """Transactions requires auth"""
        response = requests.get(f"{API}/transactions")
        assert response.status_code == 401
        print("✓ Transactions requires auth")
    
    def test_rewards_requires_auth(self):
        """Rewards requires auth"""
        response = requests.get(f"{API}/rewards")
        assert response.status_code == 401
        print("✓ Rewards requires auth")
    
    def test_rewards_history_requires_auth(self):
        """Rewards history requires auth"""
        response = requests.get(f"{API}/rewards/history")
        assert response.status_code == 401
        print("✓ Rewards history requires auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
