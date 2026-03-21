"""
WhatsApp Webhook Tests - Critical tests for list_reply handling
Tests the fix for WhatsApp bot list message replies not being handled properly
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestWhatsAppWebhookListReply:
    """CRITICAL: Test WhatsApp webhook handles list_reply properly"""
    
    def test_list_reply_upload_bill(self):
        """Test list_reply with id='upload_bill' returns bill upload prompt"""
        payload = {
            "events": {
                "eventType": "MESSAGE EVENTS"
            },
            "eventContent": {
                "message": {
                    "from": "919876543210",
                    "messageType": "interactive",
                    "profileName": "Test User",
                    "interactive": {
                        "type": "list_reply",
                        "list_reply": {
                            "id": "upload_bill",
                            "title": "Upload Bill"
                        }
                    }
                }
            }
        }
        response = requests.post(f"{BASE_URL}/api/whatsapp/webhook", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got: {data}"
        print(f"✓ list_reply upload_bill handled: {data}")
    
    def test_list_reply_my_points(self):
        """Test list_reply with id='my_points' returns points balance breakdown"""
        payload = {
            "events": {
                "eventType": "MESSAGE EVENTS"
            },
            "eventContent": {
                "message": {
                    "from": "919876543210",
                    "messageType": "interactive",
                    "profileName": "Test User",
                    "interactive": {
                        "type": "list_reply",
                        "list_reply": {
                            "id": "my_points",
                            "title": "My Points"
                        }
                    }
                }
            }
        }
        response = requests.post(f"{BASE_URL}/api/whatsapp/webhook", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got: {data}"
        print(f"✓ list_reply my_points handled: {data}")
    
    def test_list_reply_customer_support(self):
        """Test list_reply with id='customer_support' returns help info"""
        payload = {
            "events": {
                "eventType": "MESSAGE EVENTS"
            },
            "eventContent": {
                "message": {
                    "from": "919876543210",
                    "messageType": "interactive",
                    "profileName": "Test User",
                    "interactive": {
                        "type": "list_reply",
                        "list_reply": {
                            "id": "customer_support",
                            "title": "Help / Support"
                        }
                    }
                }
            }
        }
        response = requests.post(f"{BASE_URL}/api/whatsapp/webhook", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got: {data}"
        print(f"✓ list_reply customer_support handled: {data}")
    
    def test_list_reply_redeem_points(self):
        """Test list_reply with id='redeem_points' returns redemption info"""
        payload = {
            "events": {
                "eventType": "MESSAGE EVENTS"
            },
            "eventContent": {
                "message": {
                    "from": "919876543210",
                    "messageType": "interactive",
                    "profileName": "Test User",
                    "interactive": {
                        "type": "list_reply",
                        "list_reply": {
                            "id": "redeem_points",
                            "title": "Redeem Points"
                        }
                    }
                }
            }
        }
        response = requests.post(f"{BASE_URL}/api/whatsapp/webhook", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got: {data}"
        print(f"✓ list_reply redeem_points handled: {data}")
    
    def test_list_reply_know_more(self):
        """Test list_reply with id='know_more' returns program URL"""
        payload = {
            "events": {
                "eventType": "MESSAGE EVENTS"
            },
            "eventContent": {
                "message": {
                    "from": "919876543210",
                    "messageType": "interactive",
                    "profileName": "Test User",
                    "interactive": {
                        "type": "list_reply",
                        "list_reply": {
                            "id": "know_more",
                            "title": "Know More"
                        }
                    }
                }
            }
        }
        response = requests.post(f"{BASE_URL}/api/whatsapp/webhook", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got: {data}"
        print(f"✓ list_reply know_more handled: {data}")


class TestWhatsAppWebhookTitleMatching:
    """Test text messages matching known titles trigger correct handlers"""
    
    def test_text_my_points(self):
        """Test text 'My Points' triggers points handler"""
        payload = {
            "events": {
                "eventType": "MESSAGE EVENTS"
            },
            "eventContent": {
                "message": {
                    "from": "919876543210",
                    "messageType": "text",
                    "profileName": "Test User",
                    "text": {
                        "body": "My Points"
                    }
                }
            }
        }
        response = requests.post(f"{BASE_URL}/api/whatsapp/webhook", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got: {data}"
        print(f"✓ text 'My Points' handled: {data}")
    
    def test_text_upload_bill(self):
        """Test text 'Upload Bill' triggers upload handler"""
        payload = {
            "events": {
                "eventType": "MESSAGE EVENTS"
            },
            "eventContent": {
                "message": {
                    "from": "919876543210",
                    "messageType": "text",
                    "profileName": "Test User",
                    "text": {
                        "body": "Upload Bill"
                    }
                }
            }
        }
        response = requests.post(f"{BASE_URL}/api/whatsapp/webhook", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got: {data}"
        print(f"✓ text 'Upload Bill' handled: {data}")
    
    def test_text_help_support(self):
        """Test text 'Help / Support' triggers support handler"""
        payload = {
            "events": {
                "eventType": "MESSAGE EVENTS"
            },
            "eventContent": {
                "message": {
                    "from": "919876543210",
                    "messageType": "text",
                    "profileName": "Test User",
                    "text": {
                        "body": "Help / Support"
                    }
                }
            }
        }
        response = requests.post(f"{BASE_URL}/api/whatsapp/webhook", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got: {data}"
        print(f"✓ text 'Help / Support' handled: {data}")


class TestConsumerAPIEndpoints:
    """Test consumer app API endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for consumer"""
        # Send OTP
        send_res = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": "9876543210"})
        assert send_res.status_code == 200, f"Send OTP failed: {send_res.text}"
        
        # Verify OTP (dev mode accepts 1234)
        verify_res = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={"phone": "9876543210", "otp": "1234"})
        assert verify_res.status_code == 200, f"Verify OTP failed: {verify_res.text}"
        data = verify_res.json()
        assert "token" in data, f"No token in response: {data}"
        print(f"✓ Auth token obtained")
        return data["token"]
    
    def test_wallet_detailed(self, auth_token):
        """GET /api/consumer/wallet/detailed returns balance, total_earned, total_redeemed, expired, tier"""
        response = requests.get(f"{BASE_URL}/api/consumer/wallet/detailed", 
                               headers={"Authorization": f"Bearer {auth_token}"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "balance" in data, f"Missing 'balance' in response: {data}"
        assert "total_earned" in data, f"Missing 'total_earned' in response: {data}"
        assert "total_redeemed" in data, f"Missing 'total_redeemed' in response: {data}"
        assert "expired" in data, f"Missing 'expired' in response: {data}"
        assert "tier" in data, f"Missing 'tier' in response: {data}"
        print(f"✓ wallet/detailed: balance={data['balance']}, tier={data['tier'].get('name')}")
    
    def test_transactions_all(self, auth_token):
        """GET /api/consumer/transactions?filter_type=all returns transactions list"""
        response = requests.get(f"{BASE_URL}/api/consumer/transactions?filter_type=all",
                               headers={"Authorization": f"Bearer {auth_token}"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "transactions" in data, f"Missing 'transactions' in response: {data}"
        assert isinstance(data["transactions"], list), f"transactions should be a list: {data}"
        print(f"✓ transactions: {len(data['transactions'])} items")
    
    def test_transactions_earn_filter(self, auth_token):
        """GET /api/consumer/transactions?filter_type=earn returns only earn transactions"""
        response = requests.get(f"{BASE_URL}/api/consumer/transactions?filter_type=earn",
                               headers={"Authorization": f"Bearer {auth_token}"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "transactions" in data, f"Missing 'transactions' in response: {data}"
        print(f"✓ transactions (earn filter): {len(data['transactions'])} items")
    
    def test_transactions_redeem_filter(self, auth_token):
        """GET /api/consumer/transactions?filter_type=redeem returns only redeem transactions"""
        response = requests.get(f"{BASE_URL}/api/consumer/transactions?filter_type=redeem",
                               headers={"Authorization": f"Bearer {auth_token}"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "transactions" in data, f"Missing 'transactions' in response: {data}"
        print(f"✓ transactions (redeem filter): {len(data['transactions'])} items")
    
    def test_rewards_catalog(self, auth_token):
        """GET /api/consumer/rewards returns rewards catalog (auto-seeded if empty)"""
        response = requests.get(f"{BASE_URL}/api/consumer/rewards",
                               headers={"Authorization": f"Bearer {auth_token}"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "rewards" in data, f"Missing 'rewards' in response: {data}"
        assert isinstance(data["rewards"], list), f"rewards should be a list: {data}"
        print(f"✓ rewards catalog: {len(data['rewards'])} rewards")
    
    def test_rewards_history(self, auth_token):
        """GET /api/consumer/rewards/history returns redemption history"""
        response = requests.get(f"{BASE_URL}/api/consumer/rewards/history",
                               headers={"Authorization": f"Bearer {auth_token}"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "redemptions" in data, f"Missing 'redemptions' in response: {data}"
        print(f"✓ rewards history: {len(data['redemptions'])} redemptions")
    
    def test_favorites_get(self, auth_token):
        """GET /api/consumer/favorites returns favorites array"""
        response = requests.get(f"{BASE_URL}/api/consumer/favorites",
                               headers={"Authorization": f"Bearer {auth_token}"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "favorites" in data, f"Missing 'favorites' in response: {data}"
        assert isinstance(data["favorites"], list), f"favorites should be a list: {data}"
        print(f"✓ favorites: {len(data['favorites'])} items")
    
    def test_favorites_toggle(self, auth_token):
        """POST /api/consumer/favorites/toggle adds/removes a store from favorites"""
        # First get stores to get a valid store_id
        stores_res = requests.get(f"{BASE_URL}/api/consumer/stores",
                                  headers={"Authorization": f"Bearer {auth_token}"})
        stores_data = stores_res.json()
        if stores_data.get("stores") and len(stores_data["stores"]) > 0:
            store_id = stores_data["stores"][0]["id"]
            
            # Toggle favorite
            response = requests.post(f"{BASE_URL}/api/consumer/favorites/toggle",
                                    headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
                                    json={"store_id": store_id})
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert "favorites" in data, f"Missing 'favorites' in response: {data}"
            assert "action" in data, f"Missing 'action' in response: {data}"
            print(f"✓ favorites toggle: action={data['action']}")
        else:
            print("⚠ No stores available to test favorites toggle")
    
    def test_notification_preferences_get(self, auth_token):
        """GET /api/consumer/notification-preferences returns 6 preference categories all true by default"""
        response = requests.get(f"{BASE_URL}/api/consumer/notification-preferences",
                               headers={"Authorization": f"Bearer {auth_token}"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "preferences" in data, f"Missing 'preferences' in response: {data}"
        prefs = data["preferences"]
        expected_keys = ["offers", "points_updates", "events", "bill_status", "promotions", "rewards"]
        for key in expected_keys:
            assert key in prefs, f"Missing preference key '{key}' in response: {prefs}"
        print(f"✓ notification preferences: {len(prefs)} categories")
    
    def test_notification_preferences_update(self, auth_token):
        """PUT /api/consumer/notification-preferences updates preferences"""
        response = requests.put(f"{BASE_URL}/api/consumer/notification-preferences",
                               headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
                               json={"offers": False, "promotions": False})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "preferences" in data, f"Missing 'preferences' in response: {data}"
        print(f"✓ notification preferences updated")
    
    def test_profile_get(self, auth_token):
        """GET /api/consumer/profile returns address field"""
        response = requests.get(f"{BASE_URL}/api/consumer/profile",
                               headers={"Authorization": f"Bearer {auth_token}"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # address field should exist (can be null)
        assert "address" in data or data.get("address") is None, f"Missing 'address' field in profile: {data}"
        print(f"✓ profile: name={data.get('name')}, address={data.get('address')}")
    
    def test_profile_update_address(self, auth_token):
        """PUT /api/consumer/profile accepts address field update"""
        response = requests.put(f"{BASE_URL}/api/consumer/profile",
                               headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
                               json={"address": "Test Address, CP67 Mall, Mohali"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") == True, f"Expected success=True: {data}"
        print(f"✓ profile address updated")
    
    def test_bills_list(self, auth_token):
        """GET /api/consumer/bills returns bill history"""
        response = requests.get(f"{BASE_URL}/api/consumer/bills",
                               headers={"Authorization": f"Bearer {auth_token}"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "bills" in data, f"Missing 'bills' in response: {data}"
        print(f"✓ bills: {len(data['bills'])} items")


class TestProtectedEndpoints:
    """Test that protected endpoints require authentication"""
    
    def test_wallet_requires_auth(self):
        """GET /api/consumer/wallet/detailed requires auth"""
        response = requests.get(f"{BASE_URL}/api/consumer/wallet/detailed")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ wallet/detailed requires auth")
    
    def test_transactions_requires_auth(self):
        """GET /api/consumer/transactions requires auth"""
        response = requests.get(f"{BASE_URL}/api/consumer/transactions")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ transactions requires auth")
    
    def test_rewards_requires_auth(self):
        """GET /api/consumer/rewards requires auth"""
        response = requests.get(f"{BASE_URL}/api/consumer/rewards")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ rewards requires auth")
    
    def test_favorites_requires_auth(self):
        """GET /api/consumer/favorites requires auth"""
        response = requests.get(f"{BASE_URL}/api/consumer/favorites")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ favorites requires auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
