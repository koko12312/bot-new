import requests
import textverified
import logging
import datetime
from textverified.data.dtypes import NumberType, ReservationType, ReservationCapability, RentalDuration
from config import *

class PVADealsClient:
    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def _get(self, endpoint):
        response = requests.get(f"{self.base_url}/{endpoint}", headers=self.headers)
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint, data=None):
        response = requests.post(f"{self.base_url}/{endpoint}", headers=self.headers, json=data)
        response.raise_for_status()
        return response.json()

    def get_balance(self):
        return self._get("balance")

    def get_services(self):
        return self._get("services/all")

    def purchase_ltr(self, service_id, country="US", duration=30):
        data = {
            "serviceId": service_id,
            "duration": duration,
            "autoRenewEnable": True
        }
        return self._post("purchase-ltr", data)

    def get_ltr_details(self, request_id):
        return self._get(f"request/{request_id}")

    def set_auto_renew(self, request_id, enabled: bool = None):
        # NOTE: This endpoint /renew-ltr/{id} acts as a TOGGLE in V3.
        # We call it without a body to flip the state.
        return self._post(f"renew-ltr/{request_id}")

    def flag_number(self, request_id):
        # Flagging/Reporting a number usually releases it and triggers a refund if no SMS was received
        return self._post(f"flag/{request_id}")

    def get_sms(self, request_id):
        return self._get(f"request/{request_id}")

pva_client = PVADealsClient(PVADEALS_API_KEY, PVADEALS_BASE_URL)


# --- TEXTVERIFIED HELPERS ---

def tv_headers():
    # Still used for any manual requests if needed, but library is preferred
    return {
        "Authorization": f"Bearer {TV_API_KEY}",
        "Content-Type": "application/json"
    }

def get_services():
    try:
        svc_list = textverified.services.list(
            number_type=NumberType.MOBILE, 
            reservation_type=ReservationType.VERIFICATION
        )
        # Convert objects to dicts to keep compatibility with rest of the bot
        return [{"id": s.service_name, "name": s.service_name} for s in svc_list]
    except Exception as e:
        logging.error(f"Error fetching services: {e}")
        return []

def purchase_number(service_name):
    try:
        # Creating a 30-day renewable rental as requested (long-term rent)
        sale = textverified.reservations.create(
            service_name=service_name,
            capability=ReservationCapability.SMS,
            duration=RentalDuration.THIRTY_DAY,
            is_renewable=True,
            number_type=NumberType.MOBILE,
            always_on=True,
            allow_back_order_reservations=False,
            billing_cycle_id_to_assign_to=None  # Explicitly force a new billing cycle
        )
        
        # A sale can contain multiple reservations, we take the first one
        if sale.reservations:
            res = sale.reservations[0]
            # Get full details of the newly created reservation
            details = textverified.reservations.details(res.id)
            
            # Get actual expiry from TextVerified billing cycle
            expiry = None
            if hasattr(details, 'billing_cycle_id') and details.billing_cycle_id:
                try:
                    cycle = textverified.billing_cycles.get(details.billing_cycle_id)
                    expiry = cycle.billing_cycle_ends_at.isoformat()
                except Exception as e:
                    logging.error(f"Error fetching billing cycle: {e}")
            
            # Fallback if billing cycle fetch fails
            if not expiry:
                expiry = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=30)).isoformat()
            
            return {
                "id": details.id,
                "number": details.number,
                "status": details.state.value,
                "expires_at": expiry
            }
        return None
    except Exception as e:
        logging.error(f"Error purchasing rental: {e}")
        return None

def normalize_phone(n):
    if not n:
        return ''
    digits = ''.join(c for c in str(n) if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits

def get_sms_tv(reservation_id, min_timestamp=None):
    try:
        details = textverified.reservations.details(reservation_id)
        target_num = normalize_phone(details.number)
        messages = textverified.sms.list()
        count = 0
        for msg in messages:
            msg_num = normalize_phone(getattr(msg, 'to_value', ''))
            if msg_num == target_num:
                msg_created = getattr(msg, 'created_at', None)
                if min_timestamp and msg_created:
                    if min_timestamp.tzinfo is None:
                        min_timestamp = min_timestamp.replace(tzinfo=datetime.timezone.utc)
                    if msg_created.tzinfo is None:
                        msg_created = msg_created.replace(tzinfo=datetime.timezone.utc)
                    if msg_created < (min_timestamp - datetime.timedelta(seconds=5)):
                        count += 1
                        if count >= 30:
                            break
                        continue

                return {
                    "code": msg.parsed_code,
                    "sms": msg.sms_content,
                    "status": details.state.value
                }
            count += 1
            if count >= 30:
                break
        return {"code": None, "sms": None, "status": details.state.value}
    except Exception as e:
        logging.error(f"Error getting TV SMS: {e}")
        return None

def get_sms_pva(request_id):
    try:
        res = pva_client.get_sms(request_id)
        data = res.get('data', {}) if isinstance(res, dict) else {}
        code = res.get('code') or data.get('code') or data.get('smsCode')
        sms_text = (
            res.get('message') or res.get('sms') or 
            data.get('sms') or data.get('message') or data.get('smsContent')
        )
        return {
            "code": code,
            "sms": sms_text,
            "status": "active"
        }
    except Exception as e:
        logging.error(f"Error getting PVA SMS: {e}")
        return None

async def poll_sms_code(verification_id: str, provider: str = 'tv', query=None, number_str: str = '', lang: str = 'en', min_timestamp=None):
    sms_data = None
    total_seconds = SMS_POLL_ATTEMPTS * SMS_POLL_DELAY
    last_text = ""
    
    if min_timestamp is None:
        min_timestamp = datetime.datetime.now(datetime.timezone.utc)

    for attempt in range(SMS_POLL_ATTEMPTS):
        time_remaining = max(0, total_seconds - (attempt * SMS_POLL_DELAY))
        
        if query:
            if lang == 'ar':
                status_text = (
                    f"⏳ *جاري البحث عن كود التحقق للرقم `+{number_str}`...*\n\n"
                    f"⏱ الوقت المتبقي: `{time_remaining}` ثانية"
                )
            else:
                status_text = (
                    f"⏳ *Checking for SMS code for `+{number_str}`...*\n\n"
                    f"⏱ Time remaining: `{time_remaining}`s"
                )
            if status_text != last_text:
                try:
                    await query.edit_message_text(status_text, parse_mode='Markdown')
                    last_text = status_text
                except Exception:
                    pass
        
        if provider in ['tv', 'textverified']:
            sms_data = await asyncio.to_thread(get_sms_tv, verification_id, min_timestamp)
        else:
            sms_data = await asyncio.to_thread(get_sms_pva, verification_id)
            
        if isinstance(sms_data, dict) and sms_data.get('code'):
            await asyncio.to_thread(mark_code_received_by_verification_id, verification_id)
            return sms_data
        
        if attempt < SMS_POLL_ATTEMPTS - 1:
            await asyncio.sleep(SMS_POLL_DELAY)
            
    return sms_data

def has_username(user):
    return user and user['username']

def build_referral_link(user):
    lang = user['language'] or 'en'
    s = STRINGS[lang]
    if BOT_USERNAME:
        return f"https://t.me/{BOT_USERNAME}?start={user['referral_code']}"
    return s['label_your_ref_code'].format(code=user['referral_code'])

# --- NOWPAYMENTS HELPERS ---

def create_invoice(amount: float, user_id: int):
    order_id = f"ORDER_{user_id}_{int(datetime.datetime.now(datetime.UTC).timestamp())}"
    
    payload = {
        "price_amount": amount,
        "price_currency": "usd",
        "order_id": order_id,
        "order_description": f"Deposit for user {user_id}",
        "ipn_callback_url": IPN_CALLBACK_URL,
        "success_url": SUCCESS_URL,
        "cancel_url": CANCEL_URL
    }
    
    headers = {
        "x-api-key": NP_API_KEY,
        "Content-Type": "application/json"
    }
    
    response = requests.post(f"{NP_BASE_URL}/invoice", headers=headers, json=payload)
    
    if response.status_code == 200 or response.status_code == 201:
        data = response.json()
        add_deposit_record(user_id, order_id, data.get('id'), amount, 'usd', '')
        return data
    else:
        logging.error(f"Invoice creation failed: {response.status_code} - {response.text}")
        return None

