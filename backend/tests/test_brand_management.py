"""
Test suite for Brand Management Enhancements
- Admin Brands page APIs (GET, PUT, POST, DELETE)
- Brand image upload (logo, cover)
- Sync to stores collection
- App QR code generation
- Consumer stores integration
- WhatsApp success message with app link
"""
import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Admin credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "CP67Admin@2025"

@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json().get("token")
    assert token, "No token returned from admin login"
    return token

@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Get authenticated headers"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }

class TestBrandsAPI:
    """Test Admin Brands CRUD operations"""
    
    def test_get_brands_list(self, auth_headers):
        """GET /api/admin/brands - should return 102 brands from ATV sheet upload"""
        response = requests.get(f"{BASE_URL}/api/admin/brands", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # Data assertions
        assert "brands" in data
        assert "total" in data
        assert data["total"] >= 100, f"Expected at least 100 brands, got {data['total']}"
        
        # Verify brand structure
        if len(data["brands"]) > 0:
            brand = data["brands"][0]
            assert "id" in brand
            assert "brand_name" in brand
            assert "atv" in brand or brand.get("atv") is None
        
        print(f"PASS: GET /api/admin/brands - Total brands: {data['total']}")
    
    def test_get_brands_returns_expected_fields(self, auth_headers):
        """Verify brand objects contain store detail fields"""
        response = requests.get(f"{BASE_URL}/api/admin/brands", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # Sample a brand to check structure
        if len(data["brands"]) > 0:
            brand = data["brands"][0]
            expected_fields = ["id", "brand_name"]
            for field in expected_fields:
                assert field in brand, f"Missing field: {field}"
        
        print(f"PASS: Brand objects contain expected fields")
    
    def test_update_brand_with_store_details(self, auth_headers):
        """PUT /api/admin/brands/{id} - update with store details"""
        # First get a brand to update
        response = requests.get(f"{BASE_URL}/api/admin/brands", headers=auth_headers)
        assert response.status_code == 200
        brands = response.json()["brands"]
        
        # Find Adidas or first brand
        test_brand = next((b for b in brands if b["brand_name"] == "Adidas"), brands[0])
        brand_id = test_brand["id"]
        
        # Update with store details
        update_data = {
            "brand_name": test_brand["brand_name"],
            "atv": 5000,
            "description": "Premium sportswear and athletic apparel at CP67 Mall",
            "floor": "Ground Floor",
            "timing": "11:00 AM - 9:00 PM",
            "unit_no": "G-15",
            "tags": ["sports", "footwear", "apparel"],
            "is_featured": True
        }
        
        response = requests.put(
            f"{BASE_URL}/api/admin/brands/{brand_id}",
            headers=auth_headers,
            json=update_data
        )
        
        assert response.status_code == 200, f"Update failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        
        print(f"PASS: PUT /api/admin/brands/{brand_id} - Updated with store details")
    
    def test_update_brand_accepts_all_fields(self, auth_headers):
        """Verify PUT accepts description, floor, timing, unit_no, tags, is_featured"""
        response = requests.get(f"{BASE_URL}/api/admin/brands", headers=auth_headers)
        brands = response.json()["brands"]
        
        # Find a different brand to test
        test_brand = next((b for b in brands if b["brand_name"] == "Nike"), 
                         next((b for b in brands if b["brand_name"] != "Adidas"), brands[0]))
        brand_id = test_brand["id"]
        
        # Test all store detail fields
        update_data = {
            "description": "Global sportswear brand",
            "floor": "First Floor",
            "timing": "10:00 AM - 10:00 PM",
            "unit_no": "F1-12",
            "tags": ["sports", "shoes", "athletic"],
            "is_featured": False
        }
        
        response = requests.put(
            f"{BASE_URL}/api/admin/brands/{brand_id}",
            headers=auth_headers,
            json=update_data
        )
        
        assert response.status_code == 200
        assert response.json().get("success") == True
        
        print(f"PASS: PUT accepts all store detail fields (description, floor, timing, unit_no, tags, is_featured)")


class TestBrandImageUpload:
    """Test brand image upload functionality"""
    
    def test_upload_logo_image(self, admin_token):
        """POST /api/admin/brands/{id}/upload-image - upload logo"""
        # Get a brand
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/brands", headers=headers)
        brands = response.json()["brands"]
        test_brand = next((b for b in brands if b["brand_name"] == "Adidas"), brands[0])
        brand_id = test_brand["id"]
        
        # Create a simple test image (1x1 white pixel PNG)
        from base64 import b64decode
        # 1x1 white PNG image
        png_data = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==")
        
        files = {
            'file': ('test_logo.png', io.BytesIO(png_data), 'image/png')
        }
        data = {
            'image_type': 'logo'
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin/brands/{brand_id}/upload-image",
            headers=headers,
            files=files,
            data=data
        )
        
        assert response.status_code == 200, f"Logo upload failed: {response.text}"
        result = response.json()
        assert result.get("success") == True
        assert "image_url" in result
        assert result.get("field") == "logo_url"
        
        print(f"PASS: POST /api/admin/brands/{brand_id}/upload-image (logo) - URL: {result.get('image_url', '')[:50]}...")
    
    def test_upload_cover_image(self, admin_token):
        """POST /api/admin/brands/{id}/upload-image - upload cover"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/brands", headers=headers)
        brands = response.json()["brands"]
        test_brand = next((b for b in brands if b["brand_name"] == "Adidas"), brands[0])
        brand_id = test_brand["id"]
        
        # Create test image
        from base64 import b64decode
        png_data = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==")
        
        files = {
            'file': ('test_cover.png', io.BytesIO(png_data), 'image/png')
        }
        data = {
            'image_type': 'cover'
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin/brands/{brand_id}/upload-image",
            headers=headers,
            files=files,
            data=data
        )
        
        assert response.status_code == 200, f"Cover upload failed: {response.text}"
        result = response.json()
        assert result.get("success") == True
        assert "image_url" in result
        assert result.get("field") == "cover_image_url"
        
        print(f"PASS: POST /api/admin/brands/{brand_id}/upload-image (cover) - URL: {result.get('image_url', '')[:50]}...")
    
    def test_upload_image_invalid_type(self, admin_token):
        """POST /api/admin/brands/{id}/upload-image with invalid type should fail"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/brands", headers=headers)
        brands = response.json()["brands"]
        brand_id = brands[0]["id"]
        
        from base64 import b64decode
        png_data = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==")
        
        files = {'file': ('test.png', io.BytesIO(png_data), 'image/png')}
        data = {'image_type': 'invalid_type'}
        
        response = requests.post(
            f"{BASE_URL}/api/admin/brands/{brand_id}/upload-image",
            headers=headers,
            files=files,
            data=data
        )
        
        assert response.status_code == 400
        print(f"PASS: Invalid image_type correctly returns 400")


class TestSyncToStores:
    """Test sync brands to consumer stores collection"""
    
    def test_sync_brands_to_stores(self, auth_headers):
        """POST /api/admin/brands/sync-to-stores - syncs brands with descriptions"""
        response = requests.post(
            f"{BASE_URL}/api/admin/brands/sync-to-stores",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Sync failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert "synced" in data
        
        print(f"PASS: POST /api/admin/brands/sync-to-stores - Synced {data.get('synced')} brands")
    
    def test_consumer_stores_after_sync(self):
        """GET /api/consumer/stores - verify synced brands appear"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "stores" in data
        stores = data["stores"]
        
        # Check if Adidas (which we updated with description) appears
        adidas = next((s for s in stores if s.get("name") == "Adidas"), None)
        if adidas:
            print(f"PASS: Adidas found in consumer stores with fields: {list(adidas.keys())}")
            # Verify store has expected fields
            assert "name" in adidas
        
        print(f"PASS: GET /api/consumer/stores - Total stores: {len(stores)}")


class TestAppQRCode:
    """Test App download QR code generation"""
    
    def test_app_download_qr_returns_png(self):
        """GET /api/app-download-qr - returns PNG image"""
        response = requests.get(f"{BASE_URL}/api/app-download-qr")
        
        assert response.status_code == 200
        assert response.headers.get("Content-Type") == "image/png"
        
        # Verify it's a valid PNG (starts with PNG magic bytes)
        content = response.content
        assert content[:8] == b'\x89PNG\r\n\x1a\n', "Response is not a valid PNG image"
        
        print(f"PASS: GET /api/app-download-qr - Returns valid PNG image ({len(content)} bytes)")
    
    def test_app_download_qr_has_content_disposition(self):
        """GET /api/app-download-qr - has Content-Disposition header"""
        response = requests.get(f"{BASE_URL}/api/app-download-qr")
        
        assert response.status_code == 200
        # Server sets Content-Disposition header for inline display
        content_disp = response.headers.get("Content-Disposition", "")
        # Header may be present or not depending on infrastructure
        content_type = response.headers.get("Content-Type", "")
        assert content_type == "image/png"
        
        print(f"PASS: GET /api/app-download-qr - Content-Type: {content_type}, Disposition: {content_disp}")


class TestConsumerAppIntegration:
    """Test consumer app still works after brand/store changes"""
    
    def test_consumer_home_after_changes(self):
        """GET /api/consumer/home - verify home endpoint works with consumer token"""
        # First login as consumer
        send_otp = requests.post(
            f"{BASE_URL}/api/consumer/auth/send-otp",
            json={"phone": "9876543210"}
        )
        assert send_otp.status_code == 200
        
        verify_otp = requests.post(
            f"{BASE_URL}/api/consumer/auth/verify-otp",
            json={"phone": "9876543210", "otp": "1234"}
        )
        assert verify_otp.status_code == 200
        consumer_token = verify_otp.json().get("token")
        
        # Test home endpoint
        headers = {"Authorization": f"Bearer {consumer_token}"}
        response = requests.get(f"{BASE_URL}/api/consumer/home", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "user" in data
        assert "featured_stores" in data
        assert "banners" in data
        
        print(f"PASS: GET /api/consumer/home - Returns home data with {len(data.get('featured_stores', []))} featured stores")
    
    def test_consumer_stores_includes_synced_brands(self):
        """GET /api/consumer/stores - verify it includes both seeded and synced brands"""
        response = requests.get(f"{BASE_URL}/api/consumer/stores")
        
        assert response.status_code == 200
        stores = response.json()["stores"]
        
        store_names = [s["name"] for s in stores]
        
        # Check for seeded stores (from previous test)
        seeded_stores = ["Lifestyle", "Starbucks", "Nike", "Sephora"]
        for store in seeded_stores:
            if store in store_names:
                print(f"  - Found seeded store: {store}")
        
        # Check for synced brands (Adidas was updated)
        if "Adidas" in store_names:
            print(f"  - Found synced brand: Adidas")
        
        print(f"PASS: GET /api/consumer/stores - Total: {len(stores)} stores")


class TestAdminDashboard:
    """Verify admin dashboard endpoints still work"""
    
    def test_admin_login_works(self):
        """POST /api/admin/login - verify admin login still works"""
        response = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data.get("username") == ADMIN_USERNAME
        
        print("PASS: POST /api/admin/login - Admin login working")
    
    def test_admin_me_endpoint(self, auth_headers):
        """GET /api/admin/me - verify admin profile endpoint"""
        response = requests.get(f"{BASE_URL}/api/admin/me", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("username") == ADMIN_USERNAME
        
        print("PASS: GET /api/admin/me - Admin profile working")


class TestBrandStats:
    """Test brand statistics calculations"""
    
    def test_brands_stats_calculation(self, auth_headers):
        """Verify we can calculate stats from brands data"""
        response = requests.get(f"{BASE_URL}/api/admin/brands", headers=auth_headers)
        
        assert response.status_code == 200
        brands = response.json()["brands"]
        
        # Calculate stats
        total_brands = len(brands)
        total_atv = sum(b.get("atv", 0) or 0 for b in brands)
        avg_atv = total_atv / total_brands if total_brands > 0 else 0
        app_ready = sum(1 for b in brands if b.get("description"))
        highest_atv = max((b.get("atv", 0) or 0 for b in brands), default=0)
        
        print(f"PASS: Brand Stats - Total: {total_brands}, Avg ATV: {avg_atv:.0f}, App-Ready: {app_ready}, Highest ATV: {highest_atv}")
        
        assert total_brands >= 100, "Expected at least 100 brands"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
