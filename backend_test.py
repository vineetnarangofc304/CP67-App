#!/usr/bin/env python3

import requests
import sys
import json
import base64
import io
from datetime import datetime
from pathlib import Path

class CP67LoyaltyAPITester:
    def __init__(self, base_url="https://fundle-loyalty-cp67.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.test_results = []

    def log_result(self, test_name, success, details="", error_msg=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {test_name} - PASSED")
        else:
            print(f"❌ {test_name} - FAILED: {error_msg}")
            self.failed_tests.append({
                "test": test_name,
                "error": error_msg,
                "details": details
            })
        
        self.test_results.append({
            "test_name": test_name,
            "success": success,
            "details": details,
            "error": error_msg,
            "timestamp": datetime.now().isoformat()
        })

    def run_test(self, name, method, endpoint, expected_status, data=None, files=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {}
        
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        if not files:
            headers['Content-Type'] = 'application/json'

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                if files:
                    response = requests.post(url, headers={k: v for k, v in headers.items() if k != 'Content-Type'}, 
                                           data=data, files=files, timeout=30)
                else:
                    response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)

            success = response.status_code == expected_status
            response_data = {}
            
            try:
                response_data = response.json() if response.text else {}
            except:
                response_data = {"raw_response": response.text}

            self.log_result(
                name, 
                success, 
                f"Status: {response.status_code}, Response: {str(response_data)[:200]}",
                f"Expected {expected_status}, got {response.status_code}. Response: {str(response_data)[:200]}" if not success else ""
            )

            return success, response_data

        except Exception as e:
            self.log_result(name, False, "", f"Exception: {str(e)}")
            return False, {}

    def test_health_check(self):
        """Test basic health endpoints"""
        print("\n🔍 Testing Health Endpoints...")
        self.run_test("Health Check", "GET", "", 200)
        self.run_test("API Health", "GET", "health", 200)

    def test_admin_login(self):
        """Test admin authentication"""
        print("\n🔍 Testing Admin Authentication...")
        
        # Test with correct credentials
        success, response = self.run_test(
            "Admin Login - Valid Credentials",
            "POST",
            "admin/login",
            200,
            data={"username": "admin", "password": "CP67Admin@2025"}
        )
        
        if success and 'token' in response:
            self.token = response['token']
            print(f"✅ Token obtained: {self.token[:20]}...")
        
        # Test with invalid credentials
        self.run_test(
            "Admin Login - Invalid Credentials",
            "POST",
            "admin/login",
            401,
            data={"username": "admin", "password": "wrong_password"}
        )
        
        # Test admin profile
        if self.token:
            self.run_test("Get Admin Profile", "GET", "admin/me", 200)

    def test_qr_codes(self):
        """Test QR code endpoints"""
        print("\n🔍 Testing QR Code Management...")
        
        # Get all QR codes
        success, qr_codes = self.run_test("Get QR Codes", "GET", "qr-codes", 200)
        
        if success and qr_codes:
            print(f"📊 Found {len(qr_codes)} QR codes")
            
            # Test QR code generation for first QR
            if len(qr_codes) > 0:
                qr_id = qr_codes[0].get('qr_code_id')
                if qr_id:
                    self.run_test(
                        f"Generate QR Image - {qr_id}",
                        "GET",
                        f"qr-codes/{qr_id}/generate",
                        200
                    )

    def test_whatsapp_simulation(self):
        """Test WhatsApp simulation endpoints"""
        print("\n🔍 Testing WhatsApp Simulation...")
        
        test_phone = "9876543210"
        
        # Test QR scan simulation (new user)
        success, response = self.run_test(
            "WhatsApp Simulate - QR Scan",
            "POST",
            "whatsapp/simulate",
            200,
            data={
                "phone": test_phone,
                "message": "Hi! I want to join CP67 Loyalty Program | SRC_BRANDS",
                "message_type": "text"
            }
        )
        
        if success:
            print(f"📱 WhatsApp response: {response.get('response', '')[:100]}...")
        
        # Test registration flow
        self.run_test(
            "WhatsApp Simulate - Registration",
            "POST",
            "whatsapp/simulate",
            200,
            data={
                "phone": test_phone,
                "message": "John Doe | ABCDE1234F",
                "message_type": "text"
            }
        )
        
        # Test points check
        self.run_test(
            "WhatsApp Simulate - Points Check",
            "POST",
            "whatsapp/simulate",
            200,
            data={
                "phone": test_phone,
                "message": "2",
                "message_type": "text"
            }
        )

    def create_test_bill_image(self):
        """Create a simple test bill image"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            # Create a simple bill image
            img = Image.new('RGB', (400, 600), color='white')
            draw = ImageDraw.Draw(img)
            
            # Add some text to make it look like a bill
            draw.text((50, 50), "CP67 MALL", fill='black')
            draw.text((50, 100), "RECEIPT", fill='black')
            draw.text((50, 150), "Bill No: INV001", fill='black')
            draw.text((50, 200), "Date: 2025-01-24", fill='black')
            draw.text((50, 250), "Amount: Rs. 1500.00", fill='black')
            draw.text((50, 300), "Tax: Rs. 150.00", fill='black')
            draw.text((50, 350), "Total: Rs. 1650.00", fill='black')
            
            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            return buffer.getvalue()
            
        except ImportError:
            # Fallback: create a minimal PNG
            # This is a 1x1 white PNG in base64
            return base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==')

    def test_bill_upload(self):
        """Test bill upload simulation"""
        print("\n🔍 Testing Bill Upload...")
        
        test_phone = "9876543210"
        
        # Create test image
        image_data = self.create_test_bill_image()
        
        # Test bill upload
        files = {'file': ('test_bill.png', image_data, 'image/png')}
        data = {'phone': test_phone}
        
        success, response = self.run_test(
            "WhatsApp Bill Upload",
            "POST",
            "whatsapp/simulate-bill-upload",
            200,
            data=data,
            files=files
        )
        
        if success:
            print(f"📄 Bill upload status: {response.get('status', 'unknown')}")

    def test_users_management(self):
        """Test user management endpoints"""
        print("\n🔍 Testing User Management...")
        
        # Get all users
        success, users_data = self.run_test("Get Users", "GET", "users", 200)
        
        if success and users_data.get('users'):
            print(f"👥 Found {len(users_data['users'])} users")
            
            # Test get user by phone
            test_phone = "919876543210"  # With country code
            self.run_test(
                "Get User by Phone",
                "GET",
                f"users/phone/{test_phone}",
                200
            )
            
            # Test user details if we have users
            if users_data['users']:
                user_id = users_data['users'][0].get('id')
                if user_id:
                    self.run_test(
                        "Get User Details",
                        "GET",
                        f"users/{user_id}",
                        200
                    )

    def test_bills_management(self):
        """Test bill management endpoints"""
        print("\n🔍 Testing Bill Management...")
        
        # Get all bills
        success, bills_data = self.run_test("Get Bills", "GET", "bills", 200)
        
        if success:
            print(f"📄 Found {bills_data.get('total', 0)} bills")
        
        # Get pending bills
        self.run_test("Get Pending Bills", "GET", "bills/pending-review", 200)
        
        # Test bill processing (if we have bills)
        if success and bills_data.get('bills'):
            for bill in bills_data['bills']:
                if bill.get('status') == 'manual_review':
                    bill_id = bill.get('id')
                    if bill_id:
                        # Test approve bill
                        self.run_test(
                            "Process Bill - Approve",
                            "POST",
                            f"bills/{bill_id}/process",
                            200,
                            data={"bill_id": bill_id, "action": "approve"}
                        )
                        break

    def test_analytics(self):
        """Test analytics endpoints"""
        print("\n🔍 Testing Analytics...")
        
        self.run_test("Dashboard Analytics", "GET", "analytics/dashboard", 200)
        self.run_test("QR Performance", "GET", "analytics/qr-performance", 200)
        self.run_test("User Funnel", "GET", "analytics/user-funnel", 200)
        self.run_test("Daily Stats", "GET", "analytics/daily-stats?days=7", 200)

    def test_whatsapp_logs(self):
        """Test WhatsApp logs endpoint"""
        print("\n🔍 Testing WhatsApp Logs...")
        
        self.run_test("Get WhatsApp Logs", "GET", "whatsapp/logs", 200)

    def run_all_tests(self):
        """Run all test suites"""
        print("🚀 Starting CP67 Loyalty System API Tests")
        print(f"🌐 Testing against: {self.base_url}")
        print("=" * 60)
        
        try:
            # Test in logical order
            self.test_health_check()
            self.test_admin_login()
            
            if not self.token:
                print("❌ Cannot proceed without authentication token")
                return False
            
            self.test_qr_codes()
            self.test_whatsapp_simulation()
            self.test_bill_upload()
            self.test_users_management()
            self.test_bills_management()
            self.test_analytics()
            self.test_whatsapp_logs()
            
        except Exception as e:
            print(f"❌ Test suite failed with exception: {e}")
            return False
        
        return True

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {len(self.failed_tests)}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "0%")
        
        if self.failed_tests:
            print("\n❌ FAILED TESTS:")
            for i, test in enumerate(self.failed_tests, 1):
                print(f"{i}. {test['test']}: {test['error']}")
        
        return len(self.failed_tests) == 0

def main():
    """Main test runner"""
    tester = CP67LoyaltyAPITester()
    
    success = tester.run_all_tests()
    all_passed = tester.print_summary()
    
    # Save detailed results
    results_file = "/app/backend_test_results.json"
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_tests": tester.tests_run,
            "passed_tests": tester.tests_passed,
            "failed_tests": len(tester.failed_tests),
            "success_rate": (tester.tests_passed/tester.tests_run*100) if tester.tests_run > 0 else 0,
            "failed_test_details": tester.failed_tests,
            "all_test_results": tester.test_results
        }, f, indent=2)
    
    print(f"\n📄 Detailed results saved to: {results_file}")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())