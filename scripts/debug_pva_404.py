import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

API_KEY = os.getenv("PVADEALS_API_KEY")
BASE_URL = os.getenv("PVADEALS_BASE_URL", "https://prod-v3.pvadeals.com/v3/api")
TARGET_ID = "6a31dd263dbe211cce1502ed"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

endpoints = [
    f"ltr/rentals/{TARGET_ID}",
    f"ltr-rentals/{TARGET_ID}",
    f"ltr/rental/{TARGET_ID}",
    f"purchase/{TARGET_ID}",
    f"purchases/{TARGET_ID}",
    f"order/{TARGET_ID}",
    f"ltr/details/{TARGET_ID}"
]

def find_details_endpoint():
    print(f"Investigating 404 for ID: {TARGET_ID}")
    for ep in endpoints:
        url = f"{BASE_URL}/{ep}"
        try:
            response = requests.get(url, headers=headers)
            print(f"GET {url} -> {response.status_code}")
            if response.status_code == 200:
                print(f"  FOUND! Response: {response.text[:200]}")
        except Exception as e:
            print(f"Error testing {url}: {e}")

if __name__ == "__main__":
    find_details_endpoint()
