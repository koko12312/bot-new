import os
import textverified
from dotenv import load_dotenv

load_dotenv(r'C:\Users\dsagh\OneDrive\Desktop\html\bot new\.env')
api_key = os.getenv('TEXTVERIFIED_API_KEY')
api_username = os.getenv('TEXTVERIFIED_USERNAME')

from textverified.data.dtypes import NumberType, ReservationType

print(f"Testing with Username: {api_username}")

textverified.configure(api_key=api_key, api_username=api_username)

try:
    # Try to list services
    svc_list = textverified.services.list(number_type=NumberType.MOBILE, reservation_type=ReservationType.VERIFICATION)
    print(f"Success! {len(svc_list)} services found.")
    if svc_list:
        print(f"Attributes of first service: {vars(svc_list[0])}")
        for s in svc_list:
            if 'whatsapp' in str(vars(s)).lower():
                print(f"WhatsApp found: {vars(s)}")
                break
except Exception as e:
    print(f"Error: {e}")
