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
    "ltr/purchase",
    "ltr/rentals",
    "ltr/rent",
    "rentals/purchase",
    "rentals/create",
    "ltr/rentals/create"
]

def test_endpoints():
    print(f"Testing endpoints on {BASE_URL}")
    for ep in endpoints:
        url = f"{BASE_URL}/{ep}"
        try:
            # We use an invalid service ID to avoid accidental purchase but check for 404 vs 400/401/etc.
            # If it's a 404, the endpoint doesn't exist.
            # If it's a 400 or 401 or 422, the endpoint MIGHT exist.
            response = requests.post(url, headers=headers, json={"serviceId": "123"})
            print(f"POST {url} -> {response.status_code}")
            if response.status_code != 404:
                print(f"  POTENTIAL MATCH: {ep} (Response: {response.text[:100]})")
        except Exception as e:
            print(f"Error testing {url}: {e}")

if __name__ == "__main__":
    test_endpoints()
