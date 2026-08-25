"""
Iteration 20 Tests: CP67 Mall Multiple Feature Changes
- Blocked phone numbers (brand staff contacts)
- Banner updates (Vipul Goyal, Vivek Samtani events)
- Floor filter exclusions (Food Court, Third Floor)
- Admin banner management
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://mall-engagement-hub.preview.emergentagent.com')

# Test credentials
BLOCKED_PHONE = "8146141325"
NORMAL_PHONE = "9876543210"
TEST_OTP = "1234"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "CP67Admin@2025"


class TestBlockedPhones:
    """Test blocked phone number functionality for brand staff"""
    
    def test_blocked_phone_send_otp_returns_403(self):
        """Blocked phone should return 403 with 'not eligible' message"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/send-otp",
            json={"phone": BLOCKED_PHONE}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        data = response.json()
        assert "not eligible" in data.get("detail", "").lower(), f"Expected 'not eligible' in message, got: {data}"
    
    def test_blocked_phone_verify_otp_returns_403(self):
        """Blocked phone should return 403 on verify-otp as well"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/verify-otp",
            json={"phone": BLOCKED_PHONE, "otp": TEST_OTP}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        data = response.json()
        assert "not eligible" in data.get("detail", "").lower(), f"Expected 'not eligible' in message, got: {data}"
    
    def test_normal_phone_send_otp_succeeds(self):
        """Normal phone should succeed with send-otp"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/send-otp",
            json={"phone": NORMAL_PHONE}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") == True, f"Expected success=True, got: {data}"
    
    def test_normal_phone_verify_otp_succeeds(self):
        """Normal phone should succeed with verify-otp (dev mode OTP 1234)"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/verify-otp",
            json={"phone": NORMAL_PHONE, "otp": TEST_OTP}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") == True, f"Expected success=True, got: {data}"
        assert "token" in data, "Expected token in response"


class TestFloorFilterExclusions:
    """Test that Food Court and Third Floor are excluded from floor dropdowns"""
    
    def test_stores_excludes_food_court_and_third_floor(self):
        """GET /api/consumer/stores should NOT include Food Court or Third Floor in floors"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        assert response.status_code == 200
        data = response.json()
        floors = data.get("floors", [])
        
        assert "Food Court" not in floors, f"Food Court should be excluded, got floors: {floors}"
        assert "Third Floor" not in floors, f"Third Floor should be excluded, got floors: {floors}"
        
        # Should have these floors
        expected_floors = ["Ground Floor", "First Floor", "Second Floor", "Lower Ground"]
        for floor in expected_floors:
            assert floor in floors, f"Expected {floor} in floors, got: {floors}"
    
    def test_participating_brands_excludes_food_court_and_third_floor(self):
        """GET /api/consumer/participating-brands should NOT include Food Court or Third Floor"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        data = response.json()
        floors = data.get("filters", {}).get("floors", [])
        
        assert "Food Court" not in floors, f"Food Court should be excluded, got floors: {floors}"
        assert "Third Floor" not in floors, f"Third Floor should be excluded, got floors: {floors}"
        
        # Should have these floors
        expected_floors = ["Ground Floor", "First Floor", "Second Floor", "Lower Ground"]
        for floor in expected_floors:
            assert floor in floors, f"Expected {floor} in floors, got: {floors}"


class TestBanners:
    """Test banner functionality"""
    
    @pytest.fixture
    def consumer_token(self):
        """Get consumer auth token"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/verify-otp",
            json={"phone": NORMAL_PHONE, "otp": TEST_OTP}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Could not get consumer token")
    
    @pytest.fixture
    def admin_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Could not get admin token")
    
    def test_consumer_home_returns_2_banners(self, consumer_token):
        """GET /api/consumer/home should return 2 banners (Vipul Goyal, Vivek Samtani)"""
        response = requests.get(
            f"{BASE_URL}/api/consumer/home",
            headers={"Authorization": f"Bearer {consumer_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        banners = data.get("banners", [])
        
        assert len(banners) == 2, f"Expected 2 banners, got {len(banners)}"
        
        # Check banner titles
        titles = [b.get("title", "").lower() for b in banners]
        assert any("vipul" in t for t in titles), f"Expected Vipul Goyal banner, got titles: {titles}"
        assert any("vivek" in t for t in titles), f"Expected Vivek Samtani banner, got titles: {titles}"
        
        # Check image URLs are valid
        for banner in banners:
            image_url = banner.get("image_url", "")
            assert image_url, f"Banner {banner.get('title')} has no image_url"
            assert image_url.startswith("http"), f"Invalid image_url: {image_url}"
    
    def test_admin_banners_list(self, admin_token):
        """GET /api/admin/banners should return banners list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/banners",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "banners" in data, "Expected 'banners' key in response"
        banners = data.get("banners", [])
        assert len(banners) >= 2, f"Expected at least 2 banners, got {len(banners)}"
    
    def test_admin_create_banner(self, admin_token):
        """POST /api/admin/banners should create a new banner"""
        test_banner = {
            "title": "Test Banner",
            "subtitle": "Test Subtitle",
            "image_url": "https://example.com/test.jpg",
            "position": 99,
            "is_active": False  # Inactive so it doesn't show in consumer app
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/banners",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json=test_banner
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") == True, f"Expected success=True, got: {data}"
        assert "banner" in data, "Expected 'banner' in response"
        
        # Clean up - delete the test banner
        banner_id = data["banner"].get("id")
        if banner_id:
            requests.delete(
                f"{BASE_URL}/api/admin/banners/{banner_id}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )


class TestAdminLogin:
    """Test admin authentication"""
    
    def test_admin_login_success(self):
        """Admin login with correct credentials should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data, "Expected token in response"
        assert data.get("username") == ADMIN_USERNAME
    
    def test_admin_login_invalid_credentials(self):
        """Admin login with wrong credentials should fail"""
        response = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"username": "wrong", "password": "wrong"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestBannerImages:
    """Test that banner images are accessible"""
    
    def test_vipul_goyal_banner_image_accessible(self):
        """Vipul Goyal banner image should be accessible"""
        response = requests.head(f"{BASE_URL}/banner-vipul-goyal.jpeg")
        assert response.status_code == 200, f"Vipul Goyal banner image not accessible: {response.status_code}"
    
    def test_vivek_samtani_banner_image_accessible(self):
        """Vivek Samtani banner image should be accessible"""
        response = requests.head(f"{BASE_URL}/banner-vivek-samtani.jpg")
        assert response.status_code == 200, f"Vivek Samtani banner image not accessible: {response.status_code}"
    
    def test_ha_logo_white_accessible(self):
        """HA logo with white background should be accessible"""
        response = requests.head(f"{BASE_URL}/ha-logo-white.png")
        assert response.status_code == 200, f"HA logo white not accessible: {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
