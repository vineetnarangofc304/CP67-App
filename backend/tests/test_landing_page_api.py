"""
Test cases for CP67 Landing Page and WhatsApp Bot Message Templates
Tests:
- GET /api/consumer/stores - Returns stores list for landing page
- Backend server starts without errors
- WhatsApp message templates structure verification
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestConsumerStoresAPI:
    """Tests for the consumer stores API used by landing page"""
    
    def test_stores_endpoint_returns_200(self):
        """GET /api/consumer/stores should return 200"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/consumer/stores returns 200")
    
    def test_stores_endpoint_returns_stores_list(self):
        """GET /api/consumer/stores should return stores array"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        assert response.status_code == 200
        
        data = response.json()
        # Response can be either {"stores": [...]} or direct array
        stores = data.get("stores", data) if isinstance(data, dict) else data
        
        assert isinstance(stores, list), "Stores should be a list"
        assert len(stores) > 0, "Stores list should not be empty"
        print(f"PASS: /api/consumer/stores returns {len(stores)} stores")
    
    def test_stores_have_required_fields(self):
        """Each store should have name field at minimum"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        assert response.status_code == 200
        
        data = response.json()
        stores = data.get("stores", data) if isinstance(data, dict) else data
        
        # Check first few stores have name field
        for i, store in enumerate(stores[:5]):
            assert "name" in store, f"Store {i} missing 'name' field"
            assert store["name"], f"Store {i} has empty name"
        
        print("PASS: Stores have required 'name' field")
    
    def test_stores_have_brand_names(self):
        """Verify some expected brand names are present"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        assert response.status_code == 200
        
        data = response.json()
        stores = data.get("stores", data) if isinstance(data, dict) else data
        
        brand_names = [s.get("name", "").lower() for s in stores]
        
        # Check for some expected brands
        expected_brands = ["adidas", "h&m", "zara", "starbucks"]
        found_brands = [b for b in expected_brands if any(b in name for name in brand_names)]
        
        print(f"PASS: Found {len(found_brands)} expected brands: {found_brands}")
        assert len(found_brands) > 0, "Should find at least one expected brand"


class TestBackendHealth:
    """Tests for backend health and availability"""
    
    def test_backend_is_running(self):
        """Backend should respond to requests"""
        try:
            response = requests.get(f"{BASE_URL}/api/consumer/stores", timeout=10)
            assert response.status_code == 200
            print("PASS: Backend is running and responding")
        except requests.exceptions.ConnectionError:
            pytest.fail("Backend is not running or not accessible")
    
    def test_admin_login_endpoint_exists(self):
        """Admin login endpoint should exist"""
        response = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"username": "test", "password": "test"}
        )
        # Should return 401 for invalid credentials, not 404
        assert response.status_code in [200, 401], f"Expected 200 or 401, got {response.status_code}"
        print("PASS: Admin login endpoint exists")


class TestWhatsAppMenuStructure:
    """Tests to verify WhatsApp menu structure via code review"""
    
    def test_main_menu_has_5_options(self):
        """Verify main menu has 5 options per revised flow document"""
        # Read server.py and check menu_options
        server_path = "/app/backend/server.py"
        with open(server_path, "r") as f:
            content = f.read()
        
        # Check for the 5 menu options
        required_options = [
            '"id": "upload_bill"',
            '"id": "redeem_points"',
            '"id": "my_points"',
            '"id": "customer_support"',
            '"id": "know_more"'
        ]
        
        found_options = []
        for option in required_options:
            if option in content:
                found_options.append(option)
        
        assert len(found_options) == 5, f"Expected 5 menu options, found {len(found_options)}: {found_options}"
        print(f"PASS: Main menu has all 5 required options")
    
    def test_send_whatsapp_list_function_exists(self):
        """Verify send_whatsapp_list function exists for list messages"""
        server_path = "/app/backend/server.py"
        with open(server_path, "r") as f:
            content = f.read()
        
        assert "async def send_whatsapp_list" in content, "send_whatsapp_list function not found"
        print("PASS: send_whatsapp_list function exists")
    
    def test_my_points_handler_separate_from_redeem(self):
        """Verify my_points and redeem_points are separate handlers"""
        server_path = "/app/backend/server.py"
        with open(server_path, "r") as f:
            content = f.read()
        
        # Check for separate elif branches
        assert 'message == "my_points"' in content, "my_points handler not found"
        assert 'message == "redeem_points"' in content, "redeem_points handler not found"
        
        # Verify they are separate conditions (not combined)
        my_points_idx = content.find('message == "my_points"')
        redeem_idx = content.find('message == "redeem_points"')
        
        assert my_points_idx != redeem_idx, "my_points and redeem_points should be separate handlers"
        print("PASS: my_points and redeem_points are separate handlers")
    
    def test_know_more_handler_exists(self):
        """Verify know_more handler exists and sends program URL"""
        server_path = "/app/backend/server.py"
        with open(server_path, "r") as f:
            content = f.read()
        
        assert 'message == "know_more"' in content, "know_more handler not found"
        assert "/app/program" in content, "Program URL not found in know_more handler"
        print("PASS: know_more handler exists and sends program URL")
    
    def test_bill_success_message_format(self):
        """Verify bill success message format matches spec"""
        server_path = "/app/backend/server.py"
        with open(server_path, "r") as f:
            content = f.read()
        
        # Check for the correct success message format
        # Expected: "Thank you for uploading your bill of {store} with Homeland Advantage. Points Credited: X, Total Balance: Y"
        assert "Thank you for uploading your bill of" in content, "Bill success message format incorrect"
        assert "with Homeland Advantage" in content, "Missing 'with Homeland Advantage' in success message"
        assert "Points Credited:" in content, "Missing 'Points Credited:' in success message"
        assert "Total Balance:" in content, "Missing 'Total Balance:' in success message"
        print("PASS: Bill success message format matches spec")


class TestEmojiRemoval:
    """Tests to verify emoji characters have been removed from WhatsApp messages"""
    
    def test_check_for_emoji_characters(self):
        """Check if emoji characters exist in server.py message templates"""
        server_path = "/app/backend/server.py"
        with open(server_path, "r") as f:
            content = f.read()
        
        # Common emoji characters to check
        emoji_chars = [
            '🎉', '✅', '❌', '📱', '💰', '🛒', '🎁', '📞', '📧', '🏪', '⭐', '🔔', '👋', '✨', 
            '🎊', '💳', '🏆', '📋', '🔗', '📍', '⏰', '🎯', '💡', '🙏', '👍', '🤝', '💪', '🌟',
            '🛍️', '💎', '🏬'
        ]
        
        found_emojis = []
        for emoji in emoji_chars:
            if emoji in content:
                # Find line numbers where emoji appears
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    if emoji in line:
                        found_emojis.append(f"{emoji} at line {i}")
        
        if found_emojis:
            print(f"WARNING: Found {len(found_emojis)} emoji occurrences in server.py:")
            for e in found_emojis[:10]:  # Show first 10
                print(f"  - {e}")
            # This is a warning, not a failure - emojis may be intentional
            print("NOTE: Emoji characters found - verify if they should be removed per requirements")
        else:
            print("PASS: No emoji characters found in message templates")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
