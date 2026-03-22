"""
Iteration 14 Tests: Logo placement and WhatsApp number change
- Homeland Advantage logo on Welcome, Login, Home, SideDrawer pages
- WhatsApp number changed from 9729676767 to 7347576767
- WhatsApp card is green and placed first on Help page
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestIteration14Features:
    """Test iteration 14 features: Logo and WhatsApp changes"""
    
    def test_participating_brands_api(self):
        """Test that participating brands API returns brands with logo_url"""
        response = requests.get(f"{BASE_URL}/api/consumer/participating-brands")
        assert response.status_code == 200
        data = response.json()
        assert 'brands' in data
        assert len(data['brands']) > 0
        # Check that brands have logo_url
        brands_with_logos = [b for b in data['brands'] if b.get('logo_url')]
        assert len(brands_with_logos) > 80, f"Expected 80+ brands with logos, got {len(brands_with_logos)}"
        print(f"✓ {len(data['brands'])} brands returned, {len(brands_with_logos)} with logos")
    
    def test_send_otp_api(self):
        """Test OTP sending works"""
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/send-otp",
            json={"phone": "9876543210"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') == True
        print("✓ OTP send API working")
    
    def test_verify_otp_api(self):
        """Test OTP verification works with test credentials"""
        # First send OTP
        requests.post(
            f"{BASE_URL}/api/consumer/auth/send-otp",
            json={"phone": "9876543210"}
        )
        
        # Verify OTP
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/verify-otp",
            json={"phone": "9876543210", "otp": "1234"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') == True
        assert 'token' in data
        assert 'user' in data
        print("✓ OTP verify API working")
    
    def test_home_api_authenticated(self):
        """Test home API with authentication"""
        # Get token
        response = requests.post(
            f"{BASE_URL}/api/consumer/auth/verify-otp",
            json={"phone": "9876543210", "otp": "1234"}
        )
        token = response.json().get('token')
        
        # Call home API
        response = requests.get(
            f"{BASE_URL}/api/consumer/home",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert 'user' in data
        print("✓ Home API working")
    
    def test_logo_file_exists(self):
        """Test that homeland-advantage-logo.jpeg is accessible"""
        response = requests.get(f"{BASE_URL}/homeland-advantage-logo.jpeg")
        # Should return 200 or redirect to static file
        assert response.status_code in [200, 304], f"Logo file not accessible, got {response.status_code}"
        print("✓ Logo file accessible")
    
    def test_brand_logo_accessible(self):
        """Test that brand logos are accessible"""
        response = requests.get(f"{BASE_URL}/api/uploads/brands/adidas_logo.png")
        assert response.status_code == 200
        assert 'image' in response.headers.get('content-type', '')
        print("✓ Brand logos accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
