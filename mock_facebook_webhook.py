import requests
import json
import time

# --- CONFIG ---
BASE_URL = "http://127.0.0.1:8000"
VERIFY_TOKEN = "crm-secret-verify-token-123"

# Colors
GREEN = "\033[92m"
BLUE = "\033[94m"
RESET = "\033[0m"
RED = "\033[2M"

def test_verification_handshake():
    print(f"\n{BLUE}[TEST 1] Testing Facebook Verification Handshake (GET)...{RESET}")
    
    # Facebook sends these params to check if your server is real
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": VERIFY_TOKEN,
        "hub.challenge": "11223344"
    }
    
    resp = requests.get(f"{BASE_URL}/api/v1/webhooks/facebook/", params=params)
    
    if resp.status_code == 200 and resp.text == "11223344":
        print(f"{GREEN}[PASS] Handshake successful! Challenge echoed correctly.{RESET}")
    else:
        print(f"[FAIL] Handshake failed. Status: {resp.status_code}, Body: {resp.text}")

def test_lead_ingestion():
    print(f"\n{BLUE}[TEST 2] Testing Lead Ingestion (POST)...{RESET}")
    
    # This is a Mock Payload simulating a Lead Ad submission
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "12345",
                "time": int(time.time()),
                "changes": [
                    {
                        "field": "leadgen",
                        "value": {
                            "form_id": "FORM_999",
                            "ad_id": "AD_888",
                            "lead_data": {
                                "full_name": "Facebook Mock User",
                                "phone_number": "+201066778899",
                                "email": "fb.mock@example.com",
                                "campaign_name": "Summer Villa Promo"
                            }
                        }
                    }
                ]
            }
        ]
    }
    
    resp = requests.post(f"{BASE_URL}/api/v1/webhooks/facebook/", json=payload)
    
    if resp.status_code == 200:
        print(f"{GREEN}[PASS] Webhook accepted! Status: {resp.json().get('status')}{RESET}")
        print("-> Go check your database (or Lead List API) for 'Facebook Mock User'.")
    else:
        print(f"[FAIL] Webhook rejected. Status: {resp.status_code}, Body: {resp.text}")

if __name__ == "__main__":
    try:
        test_verification_handshake()
        test_lead_ingestion()
    except requests.exceptions.ConnectionError:
        print(f"{RED}[FAIL] Could not connect to localhost:8000{RESET}")