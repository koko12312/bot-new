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

endpoints = [
    "purchase/history",
    "purchase/ltr",
    "purchase/ltr/history",
    "ltr/rentals/active"
]

def test_get_endpoints():
    print(f"Testing GET endpoints on {BASE_URL}")
    for ep in endpoints:
        url = f"{BASE_URL}/{ep}"
        try:
            response = requests.get(url, headers=headers)
            print(f"GET {url} -> {response.status_code}")
            if response.status_code == 200:
                print(f"  MATCH: {ep} (Response: {response.text[:200]})")
        except Exception as e:
            print(f"Error testing {url}: {e}")

if __name__ == "__main__":
    test_get_endpoints()
