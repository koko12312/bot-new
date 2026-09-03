import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

API_KEY = os.getenv("PVADEALS_API_KEY")
BASE_URL = os.getenv("PVADEALS_BASE_URL", "https://prod-v3.pvadeals.com/v3/api")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def test_purchase_ltr_endpoint():
    url = f"{BASE_URL}/purchase-ltr"
    payload = {
        "serviceId": "697139f4fe5460ddc2f271c2", # WhatsApp ID
        "duration": 30
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        print(f"POST {url} -> {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_purchase_ltr_endpoint()
