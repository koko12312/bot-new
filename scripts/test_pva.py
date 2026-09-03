import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

PVADEALS_API_KEY = os.getenv("PVADEALS_API_KEY")
PVADEALS_BASE_URL = os.getenv("PVADEALS_BASE_URL", "https://prod-v3.pvadeals.com/v3/api")

class PVADealsClient:
    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def _get(self, endpoint):
        url = f"{self.base_url}/{endpoint}"
        print(f"DEBUG: GET {url}")
        response = requests.get(url, headers=self.headers)
        if response.status_code != 200:
            print(f"ERROR: {response.status_code} - {response.text}")
        response.raise_for_status()
        return response.json()

    def get_balance(self):
        return self._get("balance")

    def get_services(self):
        return self._get("services/all")

def main():
    if not PVADEALS_API_KEY:
        print("CRITICAL ERROR: PVADEALS_API_KEY not found in .env")
        return

    print(f"--- Testing PVADeals Integration ---")
    print(f"Base URL: {PVADEALS_BASE_URL}")
    
    client = PVADealsClient(PVADEALS_API_KEY, PVADEALS_BASE_URL)

    try:
        print("\n1. Checking Balance...")
        balance_data = client.get_balance()
        print(f"Success! Current Balance: {balance_data.get('balance')} {balance_data.get('currency', 'USD')}")
    except Exception as e:
        print(f"Failed to check balance: {e}")

    try:
        print("\n2. Fetching Services...")
        res = client.get_services()
        print(f"DEBUG: Raw services response: {res}")
        
        # Structure is {'success': True, 'data': {'services': [...]}, 'message': '...'}
        if isinstance(res, dict) and res.get('success'):
            services = res.get('data', {}).get('services', [])
            print(f"Success! Found {len(services)} services.")
            whatsapp_svc = next((svc for svc in services if 'whatsapp' in svc.get('name', '').lower()), None)
            if whatsapp_svc:
                print(f"Found WhatsApp Service: {whatsapp_svc}")
            else:
                print("WhatsApp service not found in the list.")
        else:
            print(f"Unexpected services format or success=False: {res}")
            
    except Exception as e:
        print(f"Failed to fetch services: {e}")
        import traceback
        traceback.print_exc()

    print("\n--- Test Complete ---")
    print("Note: There is no dedicated sandbox for PVADeals.")
    print("Testing purchase endpoints will consume REAL balance.")

if __name__ == "__main__":
    main()
