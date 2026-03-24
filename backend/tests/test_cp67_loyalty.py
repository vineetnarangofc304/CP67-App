"""
CP67 Mall WhatsApp Loyalty System - Backend API Tests
Tests: Admin auth, Dashboard, QR Codes, Users, Bills, WhatsApp webhook, OCR, Analytics
"""
import pytest
import requests
import os
import json
import base64
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://brand-sync-staging.preview.emergentagent.com')

# Test credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "CP67Admin@2025"


class TestAdminAuth:
    """Admin authentication tests"""
    
    def test_admin_login_success(self):
        """Test admin login with correct credentials"""
        response = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data, "Response should contain token"
        assert "username" in data, "Response should contain username"
        assert data["username"] == ADMIN_USERNAME
        
    def test_admin_login_invalid_credentials(self):
        """Test admin login with wrong credentials"""
        response = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"username": "wrong", "password": "wrong"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
    def test_admin_me_endpoint(self, auth_token):
        """Test /admin/me endpoint with valid token"""
        response = requests.get(
            f"{BASE_URL}/api/admin/me",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "username" in data
        assert "role" in data
        
    def test_admin_me_without_token(self):
        """Test /admin/me endpoint without token"""
        response = requests.get(f"{BASE_URL}/api/admin/me")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


class TestDashboard:
    """Dashboard metrics tests"""
    
    def test_dashboard_analytics(self, auth_token):
        """Test dashboard analytics endpoint returns all metrics"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/dashboard",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify all required metrics are present
        assert "users" in data, "Dashboard should have users metrics"
        assert "bills" in data, "Dashboard should have bills metrics"
        assert "qr" in data, "Dashboard should have QR metrics"
        assert "points" in data, "Dashboard should have points metrics"
        
        # Verify users metrics structure
        assert "total" in data["users"], "Users should have total count"
        
        # Verify bills metrics structure
        assert "total" in data["bills"], "Bills should have total count"
        
        # Verify QR metrics structure
        assert "total_scans" in data["qr"], "QR should have total_scans"
        
        # Verify points metrics structure
        assert "total_issued" in data["points"], "Points should have total_issued"
        
    def test_daily_stats(self, auth_token):
        """Test daily stats endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/daily-stats?days=7",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Daily stats should return a list"
        
    def test_user_funnel(self, auth_token):
        """Test user funnel analytics"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/user-funnel",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "funnel" in data, "Response should contain funnel data"


class TestQRCodes:
    """QR Code management tests"""
    
    def test_get_qr_codes(self, auth_token):
        """Test getting all QR codes - should return 5 QR codes"""
        response = requests.get(
            f"{BASE_URL}/api/qr-codes",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert isinstance(data, list), "QR codes should be a list"
        assert len(data) >= 5, f"Expected at least 5 QR codes, got {len(data)}"
        
        # Verify each QR code has required fields
        for qr in data:
            assert "qr_code_id" in qr, "QR should have qr_code_id"
            assert "location" in qr, "QR should have location"
            assert "source_code" in qr, "QR should have source_code"
            assert "whatsapp_link" in qr, "QR should have whatsapp_link"
            assert "scans" in qr, "QR should have scans count"
            assert "registrations" in qr, "QR should have registrations count"
            assert "bill_uploads" in qr, "QR should have bill_uploads count"
            
    def test_qr_code_source_attribution(self, auth_token):
        """Test QR codes have proper source codes"""
        response = requests.get(
            f"{BASE_URL}/api/qr-codes",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        expected_sources = ["SRC_BRANDS", "SRC_FOODCOURT", "SRC_PARKING", "SRC_DIGITAL", "SRC_SOCIAL"]
        actual_sources = [qr["source_code"] for qr in data]
        
        for source in expected_sources:
            assert source in actual_sources, f"Missing source code: {source}"
            
    def test_generate_qr_image(self, auth_token):
        """Test QR code image generation"""
        response = requests.get(
            f"{BASE_URL}/api/qr-codes/QR0124001/generate",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "qr_code_id" in data
        assert "image_base64" in data
        assert "whatsapp_link" in data
        assert data["image_base64"].startswith("data:image/png;base64,")


class TestUsers:
    """User management tests"""
    
    def test_get_users(self, auth_token):
        """Test getting users list"""
        response = requests.get(
            f"{BASE_URL}/api/users",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "users" in data, "Response should have users list"
        assert "total" in data, "Response should have total count"
        assert "skip" in data, "Response should have skip"
        assert "limit" in data, "Response should have limit"
        
    def test_users_search(self, auth_token):
        """Test user search functionality"""
        response = requests.get(
            f"{BASE_URL}/api/users?search=test",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "users" in data
        
    def test_users_filter_by_source(self, auth_token):
        """Test filtering users by source"""
        response = requests.get(
            f"{BASE_URL}/api/users?source=SRC_BRANDS",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "users" in data


class TestBills:
    """Bill management tests"""
    
    def test_get_bills(self, auth_token):
        """Test getting all bills"""
        response = requests.get(
            f"{BASE_URL}/api/bills",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "bills" in data, "Response should have bills list"
        assert "total" in data, "Response should have total count"
        
    def test_get_pending_bills(self, auth_token):
        """Test getting pending review bills"""
        response = requests.get(
            f"{BASE_URL}/api/bills/pending-review",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Pending bills should be a list"
        
    def test_bills_filter_by_status(self, auth_token):
        """Test filtering bills by status"""
        statuses = ["auto_approved", "manual_review", "approved", "rejected", "duplicate"]
        for status in statuses:
            response = requests.get(
                f"{BASE_URL}/api/bills?status={status}",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code == 200, f"Expected 200 for status {status}, got {response.status_code}"


class TestWhatsAppWebhook:
    """WhatsApp webhook tests"""
    
    def test_webhook_get_verification(self):
        """Test webhook GET verification endpoint"""
        response = requests.get(f"{BASE_URL}/api/whatsapp/webhook")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"
        
    def test_webhook_post_delivery_event(self):
        """Test webhook handles delivery events"""
        payload = {
            "events": {"eventType": "DELIVERY EVENTS"},
            "eventContent": {}
        }
        response = requests.post(
            f"{BASE_URL}/api/whatsapp/webhook",
            json=payload
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["status"] == "ok"
        
    def test_webhook_post_text_message(self):
        """Test webhook handles text messages"""
        payload = {
            "events": {"eventType": "MESSAGE"},
            "eventContent": {
                "message": {
                    "from": "919876543210",
                    "messageType": "text",
                    "profileName": "Test User",
                    "text": {"body": "Hi! I want to join CP67 Loyalty Program | SRC_BRANDS"}
                }
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/whatsapp/webhook",
            json=payload
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["status"] == "ok"


class TestWhatsAppSimulation:
    """WhatsApp simulation tests (admin authenticated)"""
    
    def test_simulate_message(self, auth_token):
        """Test WhatsApp message simulation"""
        test_phone = f"91987654{datetime.now().strftime('%H%M')}"
        response = requests.post(
            f"{BASE_URL}/api/whatsapp/simulate",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "phone": test_phone,
                "message": "Hi! I want to join CP67 Loyalty Program | SRC_BRANDS",
                "message_type": "text"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "success" in data
        assert "response" in data


class TestBillProcessing:
    """Bill processing tests - approve/reject actions"""
    
    def test_bill_process_endpoint_exists(self, auth_token):
        """Test bill process endpoint is accessible"""
        # First get a bill ID if any exist
        bills_response = requests.get(
            f"{BASE_URL}/api/bills?status=manual_review",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert bills_response.status_code == 200
        bills_data = bills_response.json()
        
        if bills_data["bills"]:
            bill_id = bills_data["bills"][0]["id"]
            # Test the process endpoint with a non-existent bill to verify endpoint works
            response = requests.post(
                f"{BASE_URL}/api/bills/nonexistent-bill-id/process",
                headers={"Authorization": f"Bearer {auth_token}"},
                json={
                    "bill_id": "nonexistent-bill-id",
                    "action": "approve",
                    "send_whatsapp": False
                }
            )
            # Should return 404 for non-existent bill
            assert response.status_code == 404, f"Expected 404 for non-existent bill, got {response.status_code}"
        else:
            # No pending bills, just verify endpoint structure
            response = requests.post(
                f"{BASE_URL}/api/bills/test-bill-id/process",
                headers={"Authorization": f"Bearer {auth_token}"},
                json={
                    "bill_id": "test-bill-id",
                    "action": "approve",
                    "send_whatsapp": False
                }
            )
            assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestAnalytics:
    """Analytics dashboard tests"""
    
    def test_qr_analytics(self, auth_token):
        """Test QR analytics endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/qr-performance",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
    def test_whatsapp_logs(self, auth_token):
        """Test WhatsApp logs endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/whatsapp/logs",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"


class TestParkingValidation:
    """Parking validation flow tests"""
    
    def test_parking_entry_creates_session(self):
        """Test POST /api/parking/entry creates parking session with QR"""
        test_phone = f"91999888{datetime.now().strftime('%H%M')}"
        response = requests.post(
            f"{BASE_URL}/api/parking/entry",
            params={"phone": test_phone, "name": "TEST_ParkingUser"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert data.get("success") == True, "Response should indicate success"
        assert "session_id" in data, "Response should contain session_id"
        assert "session_code" in data, "Response should contain session_code"
        assert "entry_time" in data, "Response should contain entry_time"
        assert "qr_image" in data, "Response should contain qr_image"
        
        # Verify session code format (PKG-HHMMSS-XXXXXX)
        session_code = data["session_code"]
        assert session_code.startswith("PKG-"), f"Session code should start with PKG-, got {session_code}"
        
        # Verify QR image is base64 PNG
        qr_image = data["qr_image"]
        assert qr_image.startswith("data:image/png;base64,"), "QR image should be base64 PNG"
        
        # Store session code for validation test
        TestParkingValidation.test_session_code = session_code
        
    def test_parking_validate_success(self):
        """Test POST /api/parking/validate/{session_code} validates active session"""
        # First create a new session to validate
        test_phone = f"91888777{datetime.now().strftime('%H%M')}"
        entry_response = requests.post(
            f"{BASE_URL}/api/parking/entry",
            params={"phone": test_phone, "name": "TEST_ValidateUser"}
        )
        assert entry_response.status_code == 200
        session_code = entry_response.json()["session_code"]
        
        # Now validate the session
        response = requests.post(
            f"{BASE_URL}/api/parking/validate/{session_code}",
            json={"scanned_by": "test_counter_staff"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify validation response
        assert data.get("valid") == True, "Validation should be successful"
        assert data.get("message") == "Parking validated successfully!", "Should have success message"
        assert data.get("session_code") == session_code, "Should return same session code"
        assert "mobile_number" in data, "Should return mobile number"
        assert "entry_time" in data, "Should return entry time"
        assert "exit_time" in data, "Should return exit time"
        assert "entry_time_display" in data, "Should return formatted entry time"
        assert "exit_time_display" in data, "Should return formatted exit time"
        assert "duration_minutes" in data, "Should return duration in minutes"
        assert "duration_display" in data, "Should return formatted duration"
        
    def test_parking_validate_invalid_code(self):
        """Test validation fails for non-existent code"""
        response = requests.post(
            f"{BASE_URL}/api/parking/validate/INVALID-CODE-12345",
            json={"scanned_by": "test_staff"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data.get("valid") == False, "Validation should fail"
        assert data.get("error") == "Invalid parking code", "Should return invalid code error"
        assert "message" in data, "Should have error message"
        
    def test_parking_validate_already_used(self):
        """Test validation fails for already completed session"""
        # Create and validate a session first
        test_phone = f"91777666{datetime.now().strftime('%H%M')}"
        entry_response = requests.post(
            f"{BASE_URL}/api/parking/entry",
            params={"phone": test_phone, "name": "TEST_AlreadyUsed"}
        )
        session_code = entry_response.json()["session_code"]
        
        # First validation should succeed
        first_validate = requests.post(
            f"{BASE_URL}/api/parking/validate/{session_code}",
            json={"scanned_by": "staff1"}
        )
        assert first_validate.json().get("valid") == True
        
        # Second validation should fail
        second_validate = requests.post(
            f"{BASE_URL}/api/parking/validate/{session_code}",
            json={"scanned_by": "staff2"}
        )
        assert second_validate.status_code == 200
        data = second_validate.json()
        
        assert data.get("valid") == False, "Second validation should fail"
        assert data.get("error") == "Already used", "Should return already used error"
        assert "exit_time" in data, "Should return original exit time"
        
    def test_parking_sessions_report(self, auth_token):
        """Test GET /api/parking/sessions returns sessions with stats"""
        response = requests.get(
            f"{BASE_URL}/api/parking/sessions",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "sessions" in data, "Response should contain sessions list"
        assert "total" in data, "Response should contain total count"
        assert "skip" in data, "Response should contain skip"
        assert "limit" in data, "Response should contain limit"
        assert "stats" in data, "Response should contain stats"
        
        # Verify stats structure
        stats = data["stats"]
        assert "active" in stats, "Stats should have active count"
        assert "completed_today" in stats, "Stats should have completed_today count"
        assert "avg_duration_minutes" in stats, "Stats should have avg_duration_minutes"
        
        # Verify sessions have required fields
        if data["sessions"]:
            session = data["sessions"][0]
            assert "id" in session, "Session should have id"
            assert "session_code" in session, "Session should have session_code"
            assert "user_phone" in session, "Session should have user_phone"
            assert "entry_time" in session, "Session should have entry_time"
            assert "status" in session, "Session should have status"
            
    def test_parking_sessions_filter_by_status(self, auth_token):
        """Test filtering parking sessions by status"""
        for status in ["active", "completed", "expired"]:
            response = requests.get(
                f"{BASE_URL}/api/parking/sessions?status={status}",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code == 200, f"Expected 200 for status {status}, got {response.status_code}"
            data = response.json()
            
            # Verify all returned sessions have the requested status
            for session in data.get("sessions", []):
                assert session.get("status") == status, f"Session should have status {status}"
                
    def test_parking_sessions_requires_auth(self):
        """Test parking sessions endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/parking/sessions")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


# ======================== FIXTURES ========================

@pytest.fixture(scope="session")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("token")
    pytest.fail(f"Failed to get auth token: {response.status_code} - {response.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
