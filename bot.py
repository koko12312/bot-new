import os
import sqlite3
import requests
import asyncio
import datetime
import time
import random
import hmac
import hashlib
import json
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from flask import Flask, request, jsonify
import threading
import textverified
from textverified.data.dtypes import NumberType, ReservationType, ReservationCapability, RentalDuration

# --- LOAD ENVIRONMENT VARIABLES ---
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- SANDBOX MODE ---
USE_SANDBOX = os.getenv("USE_SANDBOX", "false").lower() == "true"

# --- CONFIGURATION ---
SERVICE_PRICE = float(os.getenv("SERVICE_PRICE", "12.00"))
DEPOSIT_AMOUNTS = [5, 10, 15, 25, 50]
REFERRAL_BONUS = float(os.getenv("REFERRAL_BONUS", "2.00"))
IPN_CALLBACK_URL = os.getenv("IPN_CALLBACK_URL", "https://your-public-url.com/webhook/nowpayments")
SUCCESS_URL = os.getenv("SUCCESS_URL")
CANCEL_URL = os.getenv("CANCEL_URL")
BOT_USERNAME = os.getenv("BOT_USERNAME")
if BOT_USERNAME and BOT_USERNAME.startswith('@'):
    BOT_USERNAME = BOT_USERNAME[1:]
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None
SMS_POLL_ATTEMPTS = int(os.getenv("SMS_POLL_ATTEMPTS", "12"))
SMS_POLL_DELAY = int(os.getenv("SMS_POLL_DELAY", "4"))

SHAMCASH_ID = os.getenv("SHAMCASH_ID", "92039186076078f443d6ad081aac7476")
SHAMCASH_QR_PATH = os.getenv("SHAMCASH_QR_PATH", "ShamQR.jpeg")
if not os.path.isabs(SHAMCASH_QR_PATH):
    SHAMCASH_QR_PATH = os.path.join(os.path.dirname(__file__), SHAMCASH_QR_PATH)

# --- CREDENTIALS ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TV_API_KEY = os.getenv("TEXTVERIFIED_API_KEY")
TV_USERNAME = os.getenv("TEXTVERIFIED_USERNAME")
TV_BASE_URL = "https://www.textverified.com/api/pub/v2"

PVADEALS_API_KEY = os.getenv("PVADEALS_API_KEY")
PVADEALS_BASE_URL = os.getenv("PVADEALS_BASE_URL", "https://prod-v3.pvadeals.com/v3/api")
PVADEALS_PRICE = float(os.getenv("PVADEALS_PRICE", "12.00"))

NP_API_KEY = os.getenv("NOWPAYMENTS_API_KEY")
NP_IPN_SECRET = os.getenv("NOWPAYMENTS_IPN_SECRET")
NP_BASE_URL = "https://api.sandbox.nowpayments.io/v1" if USE_SANDBOX else "https://api.nowpayments.io/v1"

if not TELEGRAM_TOKEN or not TV_API_KEY or not NP_API_KEY or not NP_IPN_SECRET:
    raise ValueError("CRITICAL ERROR: Missing credentials! Check your .env file.")

# Configure TextVerified library
textverified.configure(api_key=TV_API_KEY, api_username=TV_USERNAME)

# --- STRINGS LOCALIZATION ---
STRINGS = {
    'en': {
        'welcome': "👋 *Welcome, {name}!*\n\n💰 *Balance:* {balance}\n\n🚀 Select an option below to get started or use the commands in the menu.\n\n🎁 *Referral Program:* Share your link and earn ${bonus} on a friend's first deposit!\n🔗 {link}",
        'select_lang': "🌍 *Language Selection / اختيار اللغة*\n\nPlease choose your preferred language:\nالرجاء اختيار لغتك المفضلة:",
        'btn_rent': "📱 Rent WhatsApp",
        'btn_deposit': "💳 Deposit",
        'btn_profile': "👤 Profile",
        'btn_numbers': "📁 My Numbers",
        'btn_lang': "🌍 Language",
        'profile_title': "📋 *Your Account*",
        'rent_purchasing': "Purchasing a WhatsApp number for you now...",
        'rent_low_balance': "You need at least {price} to rent a WhatsApp number.\nUse /deposit to add credit.",
        'rent_no_service': "WhatsApp rental service is not available right now.",
        'rent_fail': "Unable to purchase a number right now. Please try again later.",
        'rent_success': "✅ WhatsApp number rented successfully!\n\nNumber: `+{number}`\nCost: {price}\nExpires on: `{expiry}`\n\n🚀 *Subscription:* Active (Auto-renews for {price} if balance > $12)\n\nUse /mynumbers to view your numbers and request the verification code anytime.",
        'mynumbers_title': "📱 *Your Active Numbers:*",
        'mynumbers_empty': "You don't have any rented numbers yet. Use /rent to purchase one.",
        'deposit_title': "⚡ *Deposit Funds*\n\nSelect your preferred payment method:",
        'deposit_crypto': "💳 Crypto (Instant)",
        'deposit_shamcash': "📱 ShamCash (Manual)",
        'deposit_select_amt': "💰 *Select Deposit Amount*\n\nChoose how much you want to add to your balance:",
        'deposit_created': "✅ *Deposit Created*\n\nAmount: {amount}\n\n🔗 [Click here to pay via NowPayments]({url})\n\nYour account will be credited automatically once payment is confirmed.",
        'btn_get_code': "📩 Get Code",
        'btn_refund': "💸 Refund",
        'btn_cancel_sub': "🛑 Cancel Subscription",
        'btn_enable_renew': "🔄 Enable Auto-Renew",
        'status_active': "Enabled 🔄",
        'status_disabled': "Disabled 🛑",
        'refund_processing': "🔄 Processing refund... please wait.",
        'refund_success': "✅ *Refund Successful!*\n\nThe number `+{number}` has been returned.\n💰 {price} has been credited back to your balance.",
        'refund_fail': "❌ *Refund Declined*\n\nThe provider refused the refund for `+{number}`.\n\n⚠️ *Reason:* This usually happens if the number has already received an SMS code or the refund window has expired.",
        'code_checking': "Checking for SMS for +{number}... please wait.",
        'code_received': "✅ *Verification Code Received!*\n\nNumber: `+{number}`\nCode: `{code}`\n\nMessage: _{sms}_",
        'code_none': "No code is available yet. I checked a few times and did not find it. Please try again later or press the button again.",
        'rent_select_provider': "📱 *Select SMS Provider*\n\nChoose the provider you want to use for your WhatsApp rental:",
        'btn_provider_tv': "Premium ({price})",
        'btn_provider_pva': "Basic ({price})",
        'shamcash_info': "📱 *ShamCash (Manual) Deposit*\n\nPlease enter the amount you have sent (e.g., 25):",
        'shamcash_payment_info': "📱 *Payment Details*\n\nPlease scan the QR code below or copy the ShamCash ID to complete your payment of {amount}.\n\nShamCash ID:\n`{id}`",
        'shamcash_receipt': "📄 *Upload Receipt*\n\nPlease upload your payment receipt as a **PDF file**:",
        'shamcash_submitted': "✅ *Request Submitted*\n\nYour request for {amount} has been sent to the admin for review. You will be notified once it is approved.",
        'shamcash_approved_msg': "✅ *Deposit Approved!*\n\nYour ShamCash deposit of {amount} has been added to your balance.",
        'shamcash_declined_msg': "❌ *Deposit Declined*\n\nYour ShamCash deposit request has been declined. Please contact support for more information.",
        'fallback_name': "there",
        'label_name': "👤 Name",
        'label_id': "🆔 User ID",
        'label_balance': "💰 Balance",
        'label_joined': "📅 Joined",
        'label_ref_code': "🔗 Referral Code",
        'label_referrals': "👥 Referrals",
        'label_rewards': "🎁 Rewards Paid",
        'label_number': "📱 Number",
        'label_service': "🛠 Service",
        'label_auto_renew': "🔄 Auto-Renew",
        'label_expires': "📅 Expires",
        'label_left': "left",
        'label_expired': "Expired",
        'label_unknown': "Unknown",
        'label_ref_link': "🔗 *Referral link:*",
        'label_your_ref_code': "Your referral code: {code}"
    },
    'ar': {
        'welcome': "👋 *أهلاً بك، {name}!*\n\n💰 *الرصيد:* {balance}\n\n🚀 اختر خيارًا أدناه للبدء أو استخدم الأوامر في القائمة.\n\n🎁 *برنامج الإحالة:* شارك رابطك واربح {bonus}$ عند أول إيداع لصديقك!\n🔗 {link}",
        'select_lang': "🌍 *اختيار اللغة*\n\nالرجاء اختيار لغتك المفضلة:",
        'btn_rent': "📱 استئجار واتساب",
        'btn_deposit': "💳 إيداع",
        'btn_profile': "👤 الملف الشخصي",
        'btn_numbers': "📁 أرقامي",
        'btn_lang': "🌍 اللغة",
        'profile_title': "📋 *حسابك*",
        'rent_purchasing': "جاري شراء رقم واتساب لك الآن...",
        'rent_low_balance': "تحتاج إلى {price} على الأقل لاستئجار رقم واتساب.\nاستخدم /deposit لإضافة رصيد.",
        'rent_no_service': "خدمة استئجار واتساب غير متوفرة حالياً.",
        'rent_fail': "تعذر شراء رقم حالياً. يرجى المحاولة لاحقاً.",
        'rent_success': "✅ تم استئجار رقم واتساب بنجاح!\n\nالرقم: `+{number}`\nالتكلفة: {price}\nتنتهي الصلاحية في: `{expiry}`\n\n🚀 *الاشتراك:* نشط (يتجدد تلقائياً مقابل {price} إذا كان الرصيد > 12$)\n\nاستخدم /mynumbers لعرض أرقامك وطلب رمز التحقق في أي وقت.",
        'mynumbers_title': "📱 *أرقامك النشطة:*",
        'mynumbers_empty': "ليس لديك أي أرقام مستأجرة بعد. استخدم /rent لشراء رقم.",
        'deposit_title': "⚡ *إيداع الأموال*\n\nاختر طريقة الدفع المفضلة لديك:",
        'deposit_crypto': "💳 كريبتو (فوري)",
        'deposit_shamcash': "📱 شام كاش (يدوي)",
        'deposit_select_amt': "💰 *اختر مبلغ الإيداع*\n\nاختر المبلغ الذي تريد إضافته إلى رصيدك:",
        'deposit_created': "✅ *تم إنشاء الإيداع*\n\nالمبلغ: {amount}\n\n🔗 [اضغط هنا للدفع عبر NowPayments]({url})\n\nسيتم شحن حسابك تلقائياً بمجرد تأكيد الدفع.",
        'btn_get_code': "📩 طلب الكود",
        'btn_refund': "💸 استرجاع",
        'btn_cancel_sub': "🛑 إلغاء الاشتراك",
        'btn_enable_renew': "🔄 تفعيل التجديد",
        'status_active': "مفعل 🔄",
        'status_disabled': "معطل 🛑",
        'refund_processing': "🔄 جاري معالجة الاسترجاع... يرجى الانتظار.",
        'refund_success': "✅ *تم الاسترجاع بنجاح!*\n\nتم إرجاع الرقم `+{number}`.\n💰 تم إرجاع {price} إلى رصيدك.",
        'refund_fail': "❌ *تم رفض الاسترجاع*\n\nرفض المزود استرجاع الرقم `+{number}`.\n\n⚠️ *السبب:* يحدث هذا عادةً إذا كان الرقم قد استلم كود التحقق بالفعل أو انتهت فترة الاسترجاع.",
        'code_checking': "جاري التحقق من كود الواتساب للرقم +{number}... يرجى الانتظار.",
        'code_received': "✅ *تم استلام كود التحقق!*\n\nالرقم: `+{number}`\nالكود: `{code}`\n\nالرسالة: _{sms}_",
        'code_none': "لا يوجد كود متاح بعد. لقد تحققت عدة مرات ولم أجده. يرجى المحاولة لاحقاً أو الضغط على الزر مرة أخرى.",
        'rent_select_provider': "📱 *اختر مزود الخدمة*\n\nاختر المزود الذي تريد استخدامه لاستئجار الواتساب:",
        'btn_provider_tv': "ممتاز ({price})",
        'btn_provider_pva': "عادي ({price})",
        'shamcash_info': "📱 *إيداع شام كاش (يدوي)*\n\nيرجى إدخال المبلغ الذي أرسلته (مثلاً: 25):",
        'shamcash_payment_info': "📱 *تفاصيل الدفع*\n\nيرجى مسح رمز الاستجابة السريعة (QR) أدناه أو نسخ معرف شام كاش لإكمال عملية الدفع بقيمة {amount}.\n\nمعرف شام كاش:\n`{id}`",
        'shamcash_receipt': "📄 *رفع الإيصال*\n\nيرجى رفع إيصال الدفع كملف **PDF**:",
        'shamcash_submitted': "✅ *تم تقديم الطلب*\n\nتم إرسال طلبك بقيمة {amount} إلى الإدارة للمراجعة. سيتم إخطارك بمجرد الموافقة.",
        'shamcash_approved_msg': "✅ *تمت الموافقة على الإيداع!*\n\nتمت إضافة إيداع شام كاش بقيمة {amount} إلى رصيدك.",
        'shamcash_declined_msg': "❌ *تم رفض الإيداع*\n\nتم رفض طلب إيداع شام كاش الخاص بك. يرجى التواصل مع الدعم لمزيد من المعلومات.",
        'fallback_name': "يا صديقي",
        'label_name': "👤 الاسم",
        'label_id': "🆔 معرف المستخدم",
        'label_balance': "💰 الرصيد",
        'label_joined': "📅 تاريخ الانضمام",
        'label_ref_code': "🔗 كود الإحالة",
        'label_referrals': "👥 الإحالات",
        'label_rewards': "🎁 المكافآت المدفوعة",
        'label_number': "📱 الرقم",
        'label_service': "🛠 الخدمة",
        'label_auto_renew': "🔄 التجديد التلقائي",
        'label_expires': "📅 تنتهي الصلاحية",
        'label_left': "متبقي",
        'label_expired': "منتهي",
        'label_unknown': "غير معروف",
        'label_ref_link': "🔗 *رابط الإحالة الخاص بك:*",
        'label_your_ref_code': "كود الإحالة الخاص بك: {code}"
    }
}

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

DB_FILE = os.path.join(os.path.dirname(__file__), 'users.db')

# --- DATABASE HELPERS ---

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_timestamp():
    return datetime.datetime.now(datetime.UTC).isoformat()

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0,
            username TEXT,
            referrer_id INTEGER,
            referral_code TEXT UNIQUE,
            referral_credit_given INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            language TEXT DEFAULT 'en',
            first_name TEXT
        )
    ''')
    # Update existing table if columns missing
    try:
        c.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'")
    except sqlite3.OperationalError:
        pass # Column already exists
    try:
        c.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
    except sqlite3.OperationalError:
        pass # Column already exists
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            number TEXT,
            verification_id TEXT,
            service TEXT,
            status TEXT,
            created_at TEXT,
            last_checked TEXT,
            auto_renew INTEGER DEFAULT 1,
            expires_at TEXT,
            provider TEXT DEFAULT 'textverified',
            code_requested INTEGER DEFAULT 0,
            code_received INTEGER DEFAULT 0
        )
    ''')
    # Update existing table if provider column missing
    try:
        c.execute("ALTER TABLE numbers ADD COLUMN provider TEXT DEFAULT 'textverified'")
    except sqlite3.OperationalError:
        pass # Column already exists
    try:
        c.execute("ALTER TABLE numbers ADD COLUMN code_requested INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Column already exists
    try:
        c.execute("ALTER TABLE numbers ADD COLUMN code_received INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Column already exists
    c.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            order_id TEXT UNIQUE,
            invoice_id TEXT,
            amount REAL,
            price_currency TEXT,
            pay_currency TEXT,
            status TEXT,
            referral_rewarded INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS manual_deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            receipt_file_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    try:
        c.execute("ALTER TABLE manual_deposits ADD COLUMN referral_rewarded INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Column already exists
    conn.commit()
    conn.close()

def get_user(user_id: int):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return user

def get_user_lang(user_id: int):
    user = get_user(user_id)
    return user['language'] if user and user['language'] else 'en'

def set_user_lang(user_id: int, lang: str):
    conn = get_db_connection()
    conn.execute("UPDATE users SET language = ?, updated_at = ? WHERE user_id = ?", (lang, get_timestamp(), user_id))
    conn.commit()
    conn.close()

def get_user_by_username(username: str):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username.lower(),)).fetchone()
    conn.close()
    return user

def get_user_by_referral_code(code: str):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE referral_code = ?", (code,)).fetchone()
    conn.close()
    return user

def normalize_username(username: str):
    if not username:
        return None
    username = username.strip()
    if username.startswith('@'):
        username = username[1:]
    return username.lower()

def create_user(user_id: int, username: str = None, first_name: str = None, referrer_code: str = None):
    username_value = normalize_username(username)
    
    # Check for referrer
    referrer_id = None
    if referrer_code:
        referrer = get_user_by_referral_code(referrer_code)
        if referrer and referrer['user_id'] != user_id:
            referrer_id = referrer['user_id']

    created_at = get_timestamp()
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, balance, username, first_name, referrer_id, referral_code, referral_credit_given, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, 0.0, username_value, first_name, referrer_id, f'ref{user_id}', 0, created_at, created_at)
    )
    conn.commit()
    conn.close()
    return get_user(user_id)

def update_user_info(user_id: int, username: str = None, first_name: str = None):
    username_value = normalize_username(username)
    user = get_user(user_id)
    if not user:
        return

    changed = False
    if username_value is not None and user['username'] != username_value:
        changed = True
    if first_name is not None and user['first_name'] != first_name:
        changed = True

    if changed:
        conn = get_db_connection()
        if username_value and first_name:
            conn.execute("UPDATE users SET username = ?, first_name = ?, updated_at = ? WHERE user_id = ?", (username_value, first_name, get_timestamp(), user_id))
        elif username_value:
            conn.execute("UPDATE users SET username = ?, updated_at = ? WHERE user_id = ?", (username_value, get_timestamp(), user_id))
        elif first_name:
            conn.execute("UPDATE users SET first_name = ?, updated_at = ? WHERE user_id = ?", (first_name, get_timestamp(), user_id))
        conn.commit()
        conn.close()

def set_username(user_id: int, username: str):
    username_value = normalize_username(username)
    if not username_value:
        return False, "Username cannot be empty."
    
    existing = get_user_by_username(username_value)
    if existing and existing['user_id'] != user_id:
        return False, "That username is already taken. Please choose another."

    update_user_info(user_id, username=username_value)
    return True, None

def update_balance(user_id: int, amount: float):
    conn = get_db_connection()
    conn.execute(
        "UPDATE users SET balance = balance + ?, updated_at = ? WHERE user_id = ?",
        (amount, get_timestamp(), user_id)
    )
    conn.commit()
    conn.close()

def send_telegram_message_sync(chat_id: int, text: str):
    """
    Sends a synchronous Telegram message using the requests library.
    Safe for both async and sync contexts (like the Flask webhook thread).
    """
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        res = requests.post(url, json=payload, timeout=10)
        logging.info(f"Sync TG notification sent to {chat_id}: status={res.status_code}")
    except Exception as e:
        logging.error(f"Error sending sync TG notification to {chat_id}: {e}")

def check_and_reward_referrer(user_id: int, deposit_type: str, deposit_id: int):
    """
    Checks if the user has a referrer, and if this is their first completed deposit
    (either crypto 'completed' or manual 'approved').
    If yes, rewards the referrer with REFERRAL_BONUS and sends them a notification.
    """
    conn = get_db_connection()
    try:
        # Get user details
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not user:
            logging.warning(f"check_and_reward_referrer: User {user_id} not found.")
            return

        referrer_id = user['referrer_id']
        if not referrer_id:
            logging.info(f"check_and_reward_referrer: User {user_id} does not have a referrer.")
            return

        # Check if referrer has already been rewarded for this user
        crypto_rewarded = conn.execute(
            "SELECT 1 FROM deposits WHERE user_id = ? AND referral_rewarded = 1", (user_id,)
        ).fetchone()

        manual_rewarded = None
        try:
            manual_rewarded = conn.execute(
                "SELECT 1 FROM manual_deposits WHERE user_id = ? AND referral_rewarded = 1", (user_id,)
            ).fetchone()
        except sqlite3.OperationalError:
            # Column might not exist yet if db migration hasn't run, handle gracefully
            pass

        if crypto_rewarded or manual_rewarded:
            logging.info(f"check_and_reward_referrer: Referrer already rewarded for user {user_id}.")
            return

        # Count completed and approved deposits
        crypto_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM deposits WHERE user_id = ? AND status = 'completed'", (user_id,)
        ).fetchone()['cnt']

        manual_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM manual_deposits WHERE user_id = ? AND status = 'approved'", (user_id,)
        ).fetchone()['cnt']

        total_completed = crypto_count + manual_count
        logging.info(f"check_and_reward_referrer: User {user_id} has {total_completed} completed/approved deposits.")

        # Reward on first completed deposit
        if total_completed == 1:
            referrer = conn.execute("SELECT * FROM users WHERE user_id = ?", (referrer_id,)).fetchone()
            if not referrer:
                logging.warning(f"check_and_reward_referrer: Referrer {referrer_id} for user {user_id} not found.")
                return

            timestamp = get_timestamp()
            # Reward referrer balance and update stats
            conn.execute(
                "UPDATE users SET balance = balance + ?, referral_credit_given = referral_credit_given + ?, updated_at = ? WHERE user_id = ?",
                (REFERRAL_BONUS, REFERRAL_BONUS, timestamp, referrer_id)
            )

            # Mark the specific deposit as rewarded
            if deposit_type == 'crypto':
                conn.execute(
                    "UPDATE deposits SET referral_rewarded = 1, updated_at = ? WHERE id = ?",
                    (timestamp, deposit_id)
                )
            elif deposit_type == 'manual':
                try:
                    conn.execute(
                        "UPDATE manual_deposits SET referral_rewarded = 1, updated_at = ? WHERE id = ?",
                        (timestamp, deposit_id)
                    )
                except sqlite3.OperationalError:
                    pass

            conn.commit()
            logging.info(f"check_and_reward_referrer: Successfully rewarded referrer {referrer_id} with {REFERRAL_BONUS} for user {user_id}'s first deposit.")

            # Notify referrer
            ref_lang = referrer['language'] or 'en'
            friend_name = user['first_name'] or user['username'] or f"User {user_id}"
            
            if ref_lang == 'ar':
                notify_msg = (
                    f"🎉 *مكافأة الإحالة!*\n\n"
                    f"لقد حصلت على مكافأة إحالة بقيمة *${REFERRAL_BONUS:.2f}* لأن صديقك ({friend_name}) قام بعملية إيداعه الأولى! شكراً لك."
                )
            else:
                notify_msg = (
                    f"🎉 *Referral Reward!*\n\n"
                    f"You earned a referral bonus of *${REFERRAL_BONUS:.2f}* because your referred friend ({friend_name}) made their first deposit! Thank you."
                )

            send_telegram_message_sync(referrer_id, notify_msg)

    except Exception as e:
        logging.error(f"Error in check_and_reward_referrer for user {user_id}: {e}", exc_info=True)
    finally:
        conn.close()

def add_number_record(user_id: int, number: str, verification_id: str, service: str = 'whatsapp', expires_at: str = None, status: str = 'active', provider: str = 'textverified'):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO numbers (user_id, number, verification_id, service, status, created_at, auto_renew, expires_at, provider) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, number, verification_id, service, status, get_timestamp(), 1, expires_at, provider)
    )
    conn.commit()
    conn.close()

def get_user_numbers(user_id: int):
    conn = get_db_connection()
    # Only return active or renewable numbers
    rows = conn.execute(
        "SELECT * FROM numbers WHERE user_id = ? AND status IN ('active', 'renewableActive') ORDER BY created_at DESC", 
        (user_id,)
    ).fetchall()
    conn.close()
    return rows

def get_number_record(number_id: int, user_id: int):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM numbers WHERE id = ? AND user_id = ?", (number_id, user_id)).fetchone()
    conn.close()
    return row

def update_auto_renew(number_id: int, user_id: int, status: int):
    conn = get_db_connection()
    conn.execute("UPDATE numbers SET auto_renew = ? WHERE id = ? AND user_id = ?", (status, number_id, user_id))
    conn.commit()
    conn.close()

def sync_single_number(num):
    """Sync single number auto-renew state from server to DB."""
    try:
        provider = num['provider'] if 'provider' in num.keys() and num['provider'] else 'textverified'
        verification_id = num['verification_id']
        user_id = num['user_id']
        
        if provider in ['textverified', 'tv']:
            details = textverified.reservations.details(verification_id)
            is_inc = getattr(details, 'is_included_for_next_renewal', None)
            if is_inc is None:
                is_inc = getattr(details, 'include_for_renewal', None)
            if is_inc is None:
                is_inc = getattr(details, 'renewable', None)
            if is_inc is not None:
                val = 1 if is_inc else 0
                if val != num['auto_renew']:
                    update_auto_renew(num['id'], user_id, val)
                    num = dict(num)
                    num['auto_renew'] = val
        elif provider == 'pva':
            res = pva_client.get_ltr_details(verification_id)
            if res and res.get('success'):
                data = res.get('data', {})
                server_auto_renew = data.get('autoRenewEnable')
                if server_auto_renew is not None:
                    val = 1 if server_auto_renew else 0
                    if val != num['auto_renew']:
                        update_auto_renew(num['id'], user_id, val)
                        num = dict(num)
                        num['auto_renew'] = val
    except Exception as e:
        logging.warning(f"Error syncing single number {num['number']}: {e}")
    return num

def update_number_expiry(number_id: int, new_expiry: str):
    conn = get_db_connection()
    conn.execute("UPDATE numbers SET expires_at = ? WHERE id = ?", (new_expiry, number_id))
    conn.commit()
    conn.close()

def mark_code_requested(number_id: int):
    conn = get_db_connection()
    conn.execute("UPDATE numbers SET code_requested = 1 WHERE id = ?", (number_id,))
    conn.commit()
    conn.close()

def mark_code_received_by_verification_id(verification_id: str):
    conn = get_db_connection()
    conn.execute("UPDATE numbers SET code_received = 1 WHERE verification_id = ?", (verification_id,))
    conn.commit()
    conn.close()

def add_deposit_record(user_id: int, order_id: str, invoice_id: str, amount: float, price_currency: str, pay_currency: str):
    timestamp = get_timestamp()
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO deposits (user_id, order_id, invoice_id, amount, price_currency, pay_currency, status, referral_rewarded, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, order_id, invoice_id, amount, price_currency, pay_currency, 'pending', 0, timestamp, timestamp)
    )
    conn.commit()
    conn.close()

def get_deposit_by_order(order_id: str):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM deposits WHERE order_id = ?", (order_id,)).fetchone()
    conn.close()
    return row

def update_deposit_status(deposit_id: int, status: str, invoice_id: str = None, referral_rewarded: int = None):
    conn = get_db_connection()
    updates = []
    params = []
    
    if invoice_id is not None:
        updates.append("invoice_id = ?")
        params.append(invoice_id)
        
    if referral_rewarded is not None:
        updates.append("referral_rewarded = ?")
        params.append(referral_rewarded)
        
    updates.append("status = ?")
    params.append(status)
    updates.append("updated_at = ?")
    params.append(get_timestamp())
    
    query = f"UPDATE deposits SET {', '.join(updates)} WHERE id = ?"
    params.append(deposit_id)
    
    conn.execute(query, params)
    conn.commit()
    conn.close()

def get_referral_count(user_id: int):
    conn = get_db_connection()
    row = conn.execute("SELECT COUNT(*) as count FROM users WHERE referrer_id = ?", (user_id,)).fetchone()
    conn.close()
    return row['count'] if row else 0

def resolve_user(target: str):
    if target.isdigit():
        return get_user(int(target))
    
    conn = get_db_connection()
    # Search by Username
    normalized = normalize_username(target)
    user = conn.execute("SELECT * FROM users WHERE username = ?", (normalized,)).fetchone()
    if user:
        conn.close()
        return user
    
    # Search by First Name (Case-insensitive)
    user = conn.execute("SELECT * FROM users WHERE first_name LIKE ?", (f"%{target}%",)).fetchone()
    conn.close()
    return user

def format_currency(value):
    return f"${value:.2f}"

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

def get_all_users(sort_by: str = 'created_at', limit: int = 50):
    conn = get_db_connection()
    # Fallback to user_id if created_at is NULL to ensure all users show up in "Recent"
    order_clause = "COALESCE(created_at, '') DESC, user_id DESC"
    if sort_by == 'balance':
        order_clause = "balance DESC, created_at DESC"
    elif sort_by == 'id':
        order_clause = "user_id ASC"
        
    rows = conn.execute(f"SELECT * FROM users ORDER BY {order_clause} LIMIT ?", (limit,)).fetchall()
    conn.close()
    return rows

def format_user_profile(user, lang='en'):
    s = STRINGS[lang]
    name_display = user['first_name'] or s['label_unknown']
    username_display = (" (@" + user['username'].replace('_', '\\_') + ")") if user['username'] else ""
    
    joined_date = user['created_at'][:10] if user['created_at'] else s['label_unknown']
    
    lines = [
        f"{s['label_name']}: `{name_display}`{username_display}",
        f"{s['label_id']}: `{user['user_id']}`",
        f"{s['label_balance']}: {format_currency(user['balance'])}",
        f"{s['label_joined']}: `{joined_date}`",
        f"{s['label_ref_code']}: `{user['referral_code']}`",
        f"{s['label_referrals']}: `{get_referral_count(user['user_id'])}`",
        f"{s['label_rewards']}: `{user['referral_credit_given']}`"
    ]
    return "\n".join(lines)

def is_admin(user_id: int):
    return ADMIN_ID is not None and user_id == ADMIN_ID

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

# --- TELEGRAM COMMANDS ---

async def show_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇺🇸 English", callback_data="set_lang_en"),
         InlineKeyboardButton("🇸🇦 العربية", callback_data="set_lang_ar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = STRINGS['en']['select_lang']
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tg_username = update.effective_user.username
    tg_first_name = update.effective_user.first_name
    referrer_code = None
    if context.args:
        referrer_code = context.args[0]

    user = await asyncio.to_thread(get_user, user_id)
    is_new_user = False
    if not user:
        user = await asyncio.to_thread(create_user, user_id, tg_username, tg_first_name, referrer_code)
        is_new_user = True
        logging.info(f"New user created: {user_id} (@{tg_username}) via ref: {referrer_code}")
    else:
        # Sync user info
        await asyncio.to_thread(update_user_info, user_id, username=tg_username, first_name=tg_first_name)
        user = await asyncio.to_thread(get_user, user_id)

    # If new user, show language selection first
    if is_new_user:
        await show_language_selection(update, context)
        return

    lang = user['language'] or 'en'
    s = STRINGS[lang]

    referral_link = build_referral_link(user)
    escaped_referral_link = referral_link.replace("_", "\\_")
    
    keyboard = [
        [InlineKeyboardButton(s['btn_rent'], callback_data="main_rent")],
        [InlineKeyboardButton(s['btn_deposit'], callback_data="main_deposit")],
        [InlineKeyboardButton(s['btn_profile'], callback_data="main_profile"),
         InlineKeyboardButton(s['btn_numbers'], callback_data="main_numbers")],
        [InlineKeyboardButton(s['btn_lang'], callback_data="main_lang")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_name = user['username'] or user['first_name'] or s['fallback_name']
    if user['username']:
        welcome_name = "@" + welcome_name.replace('_', '\\_')
    
    await update.effective_message.reply_text(
        s['welcome'].format(
            name=welcome_name,
            balance=format_currency(user['balance']),
            bonus=format_currency(REFERRAL_BONUS),
            link=escaped_referral_link
        ),
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    if not user:
        user = await asyncio.to_thread(create_user, user_id, update.effective_user.username)

    lang = user['language'] or 'en'
    s = STRINGS[lang]

    referral_link = build_referral_link(user)
    escaped_referral_link = referral_link.replace("_", "\\_")
    
    text = (
        f"{s['profile_title']}\n\n{format_user_profile(user, lang)}\n\n"
        f"{s['label_ref_link']}\n{escaped_referral_link}"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='Markdown')
    else:
        await update.effective_message.reply_text(text, parse_mode='Markdown')

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    if not user:
        user = await asyncio.to_thread(create_user, user_id, update.effective_user.username)

    lang = user['language'] or 'en'
    s = STRINGS[lang]

    keyboard = [
        [InlineKeyboardButton(s['deposit_crypto'], callback_data="deposit_method_crypto")],
        [InlineKeyboardButton(s['deposit_shamcash'], callback_data="deposit_method_shamcash")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.effective_message.reply_text(
        s['deposit_title'],
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def rent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    if not user:
        user = await asyncio.to_thread(create_user, user_id, update.effective_user.username)

    lang = user['language'] or 'en'
    s = STRINGS[lang]

    keyboard = [
        [InlineKeyboardButton(s['btn_provider_tv'].format(price=format_currency(SERVICE_PRICE)), callback_data="rent_tv")],
        [InlineKeyboardButton(s['btn_provider_pva'].format(price=format_currency(PVADEALS_PRICE)), callback_data="rent_pva")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = s['rent_select_provider']
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def process_rent(update: Update, context: ContextTypes.DEFAULT_TYPE, provider: str):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    lang = user['language'] or 'en'
    s = STRINGS[lang]
    
    query = update.callback_query
    
    price = PVADEALS_PRICE if provider == 'pva' else SERVICE_PRICE
    
    if user['balance'] < price:
        keyboard = [[InlineKeyboardButton(s['btn_deposit'], callback_data="main_deposit")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            s['rent_low_balance'].format(price=format_currency(price)),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return

    await query.edit_message_text(s['rent_purchasing'])
    
    order = None
    if provider == 'tv':
        services = await asyncio.to_thread(get_services)
        whatsapp_targets = [s_item for s_item in services if 'whatsapp' in s_item.get('name', '').lower()]
        if not whatsapp_targets:
            await query.edit_message_text(s['rent_no_service'])
            return
        order = await asyncio.to_thread(purchase_number, whatsapp_targets[0]['id'])
    else:
        # PVADeals logic
        try:
            # We need to find the serviceId for WhatsApp on PVADeals
            res_services = await asyncio.to_thread(pva_client.get_services)
            svc_list = res_services.get('data', {}).get('services', []) if isinstance(res_services, dict) else []
            
            whatsapp_svc = next((svc for svc in svc_list if 'whatsapp' in svc.get('name', '').lower()), None)
            
            if not whatsapp_svc:
                await query.edit_message_text(s['rent_no_service'])
                return
                
            res = await asyncio.to_thread(pva_client.purchase_ltr, whatsapp_svc['_id'])
            if res and res.get('success'):
                data = res.get('data', {})
                # Strip '+' from number if present to avoid ++ in UI
                pva_number = data.get('number', '')
                if pva_number.startswith('+'):
                    pva_number = pva_number[1:]
                    
                order = {
                    "id": data.get('_id'),
                    "number": pva_number,
                    "status": data.get('status', 'active'),
                    "expires_at": data.get('endTime')
                }
        except Exception as e:
            logging.error(f"PVADeals purchase failed: {e}")

    if not order or 'id' not in order or not order.get('number'):
        await query.edit_message_text(s['rent_fail'])
        return

    await asyncio.to_thread(update_balance, user_id, -price)
    
    # Update add_number_record to include provider
    await asyncio.to_thread(add_number_record, user_id, order.get('number'), str(order.get('id')), 'whatsapp', order.get('expires_at'), order.get('status', 'active'), provider)

    expiry_date = datetime.datetime.fromisoformat(order.get('expires_at')).strftime('%Y-%m-%d')
    await query.edit_message_text(
        s['rent_success'].format(
            number=order.get('number'),
            price=format_currency(price),
            expiry=expiry_date
        ),
        parse_mode='Markdown'
    )

async def mynumbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    if not user:
        await update.effective_message.reply_text("You don't have an account yet. Use /start first.")
        return

    lang = user['language'] or 'en'
    s = STRINGS[lang]

    numbers = await asyncio.to_thread(get_user_numbers, user_id)
    if not numbers:
        if update.callback_query:
            await update.callback_query.edit_message_text(s['mynumbers_empty'])
        else:
            await update.effective_message.reply_text(s['mynumbers_empty'])
        return

    if update.callback_query:
        await update.callback_query.edit_message_text(s['mynumbers_title'], parse_mode='Markdown')
    else:
        await update.effective_message.reply_text(s['mynumbers_title'], parse_mode='Markdown')

    for raw_number in numbers:
        number = await asyncio.to_thread(sync_single_number, raw_number)
        status_icon = "✅" if number['status'] in ['active', 'renewableActive'] else "❌"
        auto_renew_status = s['status_active'] if number['auto_renew'] else s['status_disabled']
        expiry_info = ""
        
        if number['expires_at']:
            try:
                import dateutil.parser
                expiry_dt = dateutil.parser.parse(number['expires_at'])
                expiry_date = expiry_dt.strftime('%Y-%m-%d')
                
                # Calculate time left
                now = datetime.datetime.now(expiry_dt.tzinfo) if expiry_dt.tzinfo else datetime.datetime.now(datetime.UTC)
                diff = expiry_dt - now
                
                if diff.total_seconds() <= 0:
                    time_left = s['label_expired']
                elif diff.days > 0:
                    time_left = f"{diff.days}d {s['label_left']}"
                else:
                    hours = int(diff.total_seconds() // 3600)
                    time_left = f"{hours}h {s['label_left']}"
                
                expiry_info = f"\n{s['label_expires']}: `{expiry_date}` ({time_left})"
            except Exception as e:
                logging.error(f"Date parsing failed for {number['number']}: {e}")
                expiry_info = f"\n{s['label_expires']}: `{number['expires_at'][:10]}`"

        text = (
            f"{status_icon} {s['label_number']}: `+{number['number']}`\n"
            f"{s['label_service']}: {number['service'].capitalize()}\n"
            f"{s['label_auto_renew']}: {auto_renew_status}"
            f"{expiry_info}"
        )

        buttons = [
            [InlineKeyboardButton(s['btn_get_code'], callback_data=f"code_{number['id']}"),
             InlineKeyboardButton(s['btn_refund'], callback_data=f"sub_refund_{number['id']}")]
        ]

        if number['auto_renew']:
            buttons.append([InlineKeyboardButton(s['btn_cancel_sub'], callback_data=f"sub_cancel_{number['id']}")])
        else:
            buttons.append([InlineKeyboardButton(s['btn_enable_renew'], callback_data=f"sub_enable_{number['id']}")])

        reply_markup = InlineKeyboardMarkup(buttons)
        await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def sync_numbers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    if not user:
        await update.effective_message.reply_text("You don't have an account yet.")
        return

    await update.effective_message.reply_text("🔄 Refreshing your numbers... please wait.")
    
    try:
        # Get user's numbers from local DB
        local_numbers = await asyncio.to_thread(get_user_numbers, user_id)
        if not local_numbers:
            await update.effective_message.reply_text("You don't have any active numbers to sync.")
            return

        sync_count = 0
        for num in local_numbers:
            provider = num['provider'] if 'provider' in num.keys() and num['provider'] else 'textverified'
            try:
                status = None
                expiry = None
                
                if provider in ['textverified', 'tv']:
                    # Fetch latest details from TV for THIS specific number
                    details = await asyncio.to_thread(textverified.reservations.details, num['verification_id'])
                    status = details.state.value
                    
                    # Get actual expiry from TV billing cycle
                    if hasattr(details, 'billing_cycle_id') and details.billing_cycle_id:
                        try:
                            cycle = await asyncio.to_thread(textverified.billing_cycles.get, details.billing_cycle_id)
                            expiry = cycle.billing_cycle_ends_at.isoformat()
                        except: pass
                elif provider == 'pva':
                    res = await asyncio.to_thread(pva_client.get_ltr_details, num['verification_id'])
                    if res and res.get('success'):
                        data = res.get('data', {})
                        server_status = data.get('status', '').upper()
                        if server_status in ['FLAGGED', 'CANCELLED', 'EXPIRED']:
                            status = 'deleted'
                        else:
                            status = 'active'
                        expiry = data.get('expiryDate') or data.get('expiresAt') or data.get('endTime')

                if status:
                    # Update local DB
                    def update_num_db(s, exp, v_id):
                        conn = get_db_connection()
                        conn.execute(
                            "UPDATE numbers SET status = ?, expires_at = ? WHERE verification_id = ?",
                            (s, exp, v_id)
                        )
                        conn.commit()
                        conn.close()
                    
                    await asyncio.to_thread(update_num_db, status, expiry, num['verification_id'])
                    sync_count += 1
            except Exception as e:
                # Check for 404 error to mark as deleted
                is_404 = False
                if hasattr(e, 'response') and e.response is not None:
                    if e.response.status_code == 404:
                        is_404 = True
                elif "404" in str(e) or "Not Found" in str(e) or "Request not found" in str(e):
                    is_404 = True
                    
                if is_404:
                    logging.warning(f"Number {num['number']} ({provider}) returned 404 on sync. Marking as deleted.")
                    def mark_del():
                        conn = get_db_connection()
                        conn.execute("UPDATE numbers SET status = 'deleted' WHERE verification_id = ?", (num['verification_id'],))
                        conn.commit()
                        conn.close()
                    await asyncio.to_thread(mark_del)
                    sync_count += 1
                else:
                    logging.warning(f"Could not sync number {num['number']}: {e}")

        await update.effective_message.reply_text(f"✅ Refresh complete! Updated {sync_count} numbers.")
        await mynumbers(update, context)

    except Exception as e:
        logging.error(f"Sync failed: {e}")
        await update.effective_message.reply_text("❌ Refresh failed. Please try again later.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    lang = user['language'] or 'en'
    s = STRINGS[lang]
    
    if context.user_data and context.user_data.get('user_action') == 'shamcash_pdf':
        doc = update.message.document
        if doc.mime_type != 'application/pdf':
            await update.effective_message.reply_text("❌ Please upload the receipt as a **PDF file**.")
            return
            
        amt = context.user_data.pop('sham_amt')
        context.user_data.pop('user_action')
        
        # Save to DB
        def save_sham_request():
            conn = get_db_connection()
            conn.execute(
                "INSERT INTO manual_deposits (user_id, amount, receipt_file_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, amt, doc.file_id, get_timestamp(), get_timestamp())
            )
            conn.commit()
            conn.close()
            
        await asyncio.to_thread(save_sham_request)
        
        await update.effective_message.reply_text(s['shamcash_submitted'].format(amount=format_currency(amt)), parse_mode='Markdown')
        
        # Notify Admin
        if ADMIN_ID:
            user_name = f"@{user['username']}" if user['username'] else f"`{user_id}`"
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🔔 *New ShamCash Deposit Request*\n\nUser: {user_name}\nAmount: {format_currency(amt)}\n\nReview it in the /admin panel.",
                parse_mode='Markdown'
            )
        return

    await update.effective_message.reply_text("I didn't expect a document. Use the menu or /help.")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.effective_message.reply_text("You are not authorized to use admin commands.")
        return

    args = context.args
    if not args:
        # Show hybrid inline admin menu
        keyboard = [
            [InlineKeyboardButton("👥 All Users List", callback_data="admin_list_users_recent")],
            [InlineKeyboardButton("📋 View User Profile", callback_data="admin_menu_view"),
             InlineKeyboardButton("➕ Link New Number", callback_data="admin_menu_addnumber")],
            [InlineKeyboardButton("➕ Add Credit", callback_data="admin_menu_credit"),
             InlineKeyboardButton("➖ Remove Credit", callback_data="admin_menu_debit")],
            [InlineKeyboardButton("📱 View Numbers", callback_data="admin_menu_numbers"),
             InlineKeyboardButton("🗑 Remove Number", callback_data="admin_menu_removenum")],
            [InlineKeyboardButton("📥 Pending ShamCash", callback_data="admin_pending_shamcash")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Quick stats
        def get_stats():
            conn = get_db_connection()
            u_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            a_nums = conn.execute("SELECT COUNT(*) FROM numbers WHERE status IN ('active', 'renewableActive')").fetchone()[0]
            conn.close()
            return u_count, a_nums

        user_count, active_nums = await asyncio.to_thread(get_stats)

        text = (
            f"👨‍💼 *Admin Dashboard*\n\n"
            f"👥 *Total Users:* `{user_count}`\n"
            f"📱 *Active Rentals:* `{active_nums}`\n\n"
            f"Select an action or use `/admin help` for text commands:"
        )

        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return

    action = args[0].lower()
    
    if action == 'help':
        help_text = (
            "📖 *Admin Text Commands:*\n\n"
            "`/admin view <ID/@user>` - View profile\n"
            "`/admin credit <ID/@user> <amt>` - Add credit\n"
            "`/admin debit <ID/@user> <amt>` - Remove credit\n"
            "`/admin numbers <ID/@user>` - View active numbers\n"
            "`/admin addnumber <ID/@user> <num> <verif_id> [tv/pva]` - Link number manually"
        )
        await update.effective_message.reply_text(help_text, parse_mode='Markdown')
        return

    if action not in ['view', 'credit', 'debit', 'numbers', 'addnumber']:
        await update.effective_message.reply_text("Unknown admin action. Use `/admin help` for commands.")
        return

    if len(args) < 2:
        await update.effective_message.reply_text("Please provide a user ID or username.")
        return

    target = args[1]
    target_user = await asyncio.to_thread(resolve_user, target)
    if not target_user:
        await update.effective_message.reply_text("❌ User not found.")
        return

    if action == 'view':
        await update.effective_message.reply_text(
            f"👤 *User Profile*\n\n{format_user_profile(target_user)}",
            parse_mode='Markdown'
        )
        return

    if action in ['credit', 'debit']:
        if len(args) < 3 or not args[2].replace('.', '', 1).isdigit():
            await update.effective_message.reply_text("Please provide a valid amount.")
            return
        amount = float(args[2])
        if action == 'debit':
            amount = -amount
        await asyncio.to_thread(update_balance, target_user['user_id'], amount)
        await update.effective_message.reply_text(
            f"✅ Updated balance for user `{target_user['user_id']}` by {format_currency(amount)}."
        )
        return

    if action == 'numbers':
        numbers = await asyncio.to_thread(get_user_numbers, target_user['user_id'])
        if not numbers:
            await update.effective_message.reply_text("This user has no active rented numbers.")
            return
        lines = [f"📱 *Numbers for `{target_user['user_id']}`:*\n"]
        for number in numbers:
            lines.append(f"• `+{number['number']}` — status: {number['status']} — id: {number['id']}")
        await update.effective_message.reply_text("\n".join(lines), parse_mode='Markdown')
        return

    if action == 'addnumber':
        if len(args) < 4:
            await update.effective_message.reply_text("Usage: `/admin addnumber <target> <number> <verification_id> [tv/pva]`")
            return
        phone_number = args[2]
        verification_id = args[3]
        provider = args[4].lower() if len(args) > 4 else 'tv'
        
        if provider not in ['tv', 'pva']:
            await update.effective_message.reply_text("❌ Provider must be 'tv' or 'pva'.")
            return

        expiry = None
        status = 'active'
        
        try:
            if provider == 'tv':
                details = await asyncio.to_thread(textverified.reservations.details, verification_id)
                status = details.state.value
                if hasattr(details, 'billing_cycle_id') and details.billing_cycle_id:
                    cycle = await asyncio.to_thread(textverified.billing_cycles.get, details.billing_cycle_id)
                    expiry = cycle.billing_cycle_ends_at.isoformat()
            else:
                res = await asyncio.to_thread(pva_client.get_ltr_details, verification_id)
                if res and res.get('success'):
                    data = res.get('data', {})
                    status = data.get('status', 'active')
                    expiry = data.get('expiryDate') or data.get('expiresAt') or data.get('endTime')
        except Exception as e:
            logging.warning(f"Manual add sync failed: {e}")
            
        if not expiry:
            expiry = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=30)).isoformat()
            
        await asyncio.to_thread(add_number_record, target_user['user_id'], phone_number, verification_id, expires_at=expiry, status=status, provider=provider)
        
        await update.effective_message.reply_text(
            f"✅ Manually linked number `+{phone_number}` ({provider.upper()}) to user `{target_user['user_id']}`.\n"
            f"Status: `{status}`\nExpiry: `{expiry[:10]}`",
            parse_mode='Markdown'
        )
        return

async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE, sort_by: str = 'created_at'):
    users = await asyncio.to_thread(get_all_users, sort_by=sort_by, limit=20)
    
    if not users:
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")]]
        if update.callback_query:
            await update.callback_query.edit_message_text("👥 *User List*\n\nNo users found in the system.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.effective_message.reply_text("👥 *User List*\n\nNo users found in the system.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    text = "👥 *User List* (Recent 20)\n"
    if sort_by == 'balance':
        text = "💰 *User List* (Top Balance)\n"
    
    keyboard = []
    for u in users:
        # Self-healing label logic
        if u['username']:
            name = u['username']
        elif u['first_name']:
            name = u['first_name']
        else:
            name = f"🆕 New User ({u['user_id']})"
            
        balance = format_currency(u['balance'])
        
        # Handle missing created_at timestamp
        joined = "Unknown"
        if u['created_at']:
            joined = u['created_at'][:10]
        
        button_text = f"{name} | {balance} | {joined}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"admin_user_manage_{u['user_id']}")])

    # Sorting options
    keyboard.append([
        InlineKeyboardButton("🆕 Recent", callback_data="admin_list_users_recent"),
        InlineKeyboardButton("💰 Top Balance", callback_data="admin_list_users_balance")
    ])
    keyboard.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_manage_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int):
    user = await asyncio.to_thread(get_user, target_user_id)
    if not user:
        keyboard = [[InlineKeyboardButton("🔙 Back to List", callback_data="admin_list_users_recent")]]
        await update.callback_query.edit_message_text(f"❌ User `{target_user_id}` not found.", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Referral count is called inside format_user_profile, which is blocking. 
    # Let's wrap the whole profile formatting if it does DB calls.
    profile_text = await asyncio.to_thread(format_user_profile, user)
    text = f"👤 *Managing User*\n\n{profile_text}"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Credit", callback_data=f"admin_credit_prompt_{target_user_id}"),
         InlineKeyboardButton("➖ Remove Credit", callback_data=f"admin_debit_prompt_{target_user_id}")],
        [InlineKeyboardButton("📱 View Their Numbers", callback_data=f"admin_view_nums_{target_user_id}")],
        [InlineKeyboardButton("🔢 Manage Numbers (Add/Rem)", callback_data=f"admin_nums_menu_{target_user_id}")],
        [InlineKeyboardButton("🔙 Back to List", callback_data="admin_list_users_recent")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_nums_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int):
    user = await asyncio.to_thread(get_user, target_user_id)
    text = f"📱 *Number Management for `{user['first_name'] or target_user_id}`*"
    
    keyboard = [
        [InlineKeyboardButton("➕ Link New Number", callback_data=f"admin_addnum_prompt_{target_user_id}")],
        [InlineKeyboardButton("🗑 Remove Existing Number", callback_data=f"admin_removenum_prompt_{target_user_id}")],
        [InlineKeyboardButton("🔙 Back to User", callback_data=f"admin_user_manage_{target_user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Available commands:\n"
        "/start - Main menu\n"
        "/profile - View your balance and referral link\n"
        "/deposit - Add funds to your account\n"
        "/rent - Purchase a WhatsApp rental\n"
        "/mynumbers - Manage your numbers and retrieve codes\n"
        "/sync - Refresh your numbers status\n"
        "/help - Show this message"
    )

def sync_and_renew_worker(app: Application, loop: asyncio.AbstractEventLoop):
    """Worker function to handle auto-renewals in a separate thread."""
    try:
        logging.info("Checking for auto-renewals and syncing numbers for all providers (Background Thread)...")
        conn = get_db_connection()
        # Find all numbers that aren't marked as deleted/inactive
        numbers = conn.execute(
            "SELECT * FROM numbers WHERE status NOT IN ('deleted', 'expired', 'canceled')"
        ).fetchall()
        conn.close()

        for num in numbers:
            user_id = num['user_id']
            verification_id = num['verification_id']
            
            # CRITICAL FIX: Get provider directly from the database record
            provider = num['provider'] if 'provider' in num.keys() and num['provider'] else 'textverified'
            
            try:
                if provider in ['textverified', 'tv']:
                    # Fetch latest details from TextVerified
                    details = None
                    try:
                        details = textverified.reservations.details(verification_id)
                    except Exception as e:
                        is_404 = False
                        if hasattr(e, 'response') and e.response is not None:
                            if e.response.status_code == 404:
                                is_404 = True
                        elif "404" in str(e) or "Not Found" in str(e):
                            is_404 = True

                        if is_404:
                            logging.warning(f"Number {num['number']} not found on TextVerified (404). Marking as deleted.")
                            conn = get_db_connection()
                            conn.execute("UPDATE numbers SET status = 'deleted' WHERE id = ?", (num['id'],))
                            conn.commit()
                            conn.close()
                        else:
                            logging.error(f"Failed to sync TextVerified details for {num['number']} (temporary error): {e}")
                        continue

                    # 1. Sync Auto-Renew Status from Server
                    tv_auto_renew = getattr(details, 'is_included_for_next_renewal', None)
                    if tv_auto_renew is None:
                        tv_auto_renew = getattr(details, 'include_for_renewal', None)
                    if tv_auto_renew is None:
                        tv_auto_renew = getattr(details, 'renewable', None)
                    if tv_auto_renew is not None:
                        tv_auto_renew_int = 1 if tv_auto_renew else 0
                        if tv_auto_renew_int != num['auto_renew']:
                            logging.info(f"Syncing TV auto-renew for {num['number']}: {num['auto_renew']} -> {tv_auto_renew_int}")
                            update_auto_renew(num['id'], user_id, tv_auto_renew_int)
                            num = dict(num)
                            num['auto_renew'] = tv_auto_renew_int

                    # 2. Sync Expiry Date
                    tv_expiry = None
                    tv_expiry_dt = None
                    if hasattr(details, 'billing_cycle_id') and details.billing_cycle_id:
                        try:
                            cycle = textverified.billing_cycles.get(details.billing_cycle_id)
                            tv_expiry = cycle.billing_cycle_ends_at.isoformat()
                            tv_expiry_dt = cycle.billing_cycle_ends_at
                        except:
                            pass
                    
                    # --- PROACTIVE SAFETY CHECK for TextVerified ---
                    user = get_user(user_id)
                    lang = user['language'] or 'en'
                    
                    if not tv_expiry_dt and num['expires_at']:
                        try:
                            import dateutil.parser
                            tv_expiry_dt = dateutil.parser.parse(num['expires_at'])
                        except:
                            pass
                            
                    if tv_expiry_dt and num['auto_renew']:
                        now = datetime.datetime.now(tv_expiry_dt.tzinfo) if tv_expiry_dt.tzinfo else datetime.datetime.now(datetime.UTC)
                        time_diff = tv_expiry_dt - now
                        if time_diff.total_seconds() <= 86400: # <= 24 hours
                            if user['balance'] < SERVICE_PRICE:
                                logging.warning(f"Low balance for TV {num['number']}. Disabling server-side auto-renew.")
                                try:
                                    textverified.reservations.update_renewable(verification_id, include_for_renewal=False)
                                    update_auto_renew(num['id'], user_id, 0)
                                    num = dict(num)
                                    num['auto_renew'] = 0
                                    
                                    warning_msg = (
                                        f"⚠️ *Auto-Renewal Warning!*\n\nAuto-renew is disabled and subscription will be cancelled in 1 day for `+{num['number']}`."
                                        if lang == 'en' else
                                        f"⚠️ *تحذير التجديد التلقائي!*\n\nتم تعطيل التجديد التلقائي وسيتم إلغاء الاشتراك خلال يوم واحد للرقم `+{num['number']}`."
                                    )
                                    asyncio.run_coroutine_threadsafe(
                                        app.bot.send_message(chat_id=user_id, text=warning_msg, parse_mode='Markdown'),
                                        loop
                                    )
                                except Exception as e:
                                    logging.error(f"Failed to turn off server-side renewal for TV: {e}")
                                    
                    if tv_expiry and tv_expiry != num['expires_at']:
                        logging.info(f"Syncing expiry for {num['number']}: {num['expires_at']} -> {tv_expiry}")
                        
                        user = get_user(user_id)
                        lang = user['language'] or 'en'
                        
                        old_expiry_str = num['expires_at']
                        if old_expiry_str:
                            old_expiry = datetime.datetime.fromisoformat(old_expiry_str)
                            new_expiry = datetime.datetime.fromisoformat(tv_expiry)
                            
                            if new_expiry > old_expiry:
                                # If auto-renew was ON in the bot, check balance and deduct
                                if num['auto_renew']:
                                    if user['balance'] >= SERVICE_PRICE:
                                        update_balance(user_id, -SERVICE_PRICE)
                                        update_number_expiry(num['id'], tv_expiry)
                                        
                                        renewal_msg = (
                                            f"🔄 *Auto-Renewal Success!*\n\nYour WhatsApp number `+{num['number']}` has been renewed.\n💰 Cost: {format_currency(SERVICE_PRICE)}\n📅 New Expiry: `{tv_expiry[:10]}`"
                                            if lang == 'en' else
                                            f"🔄 *تم التجديد التلقائي بنجاح!*\n\nتم تجديد رقم الواتساب الخاص بك `+{num['number']}`.\n💰 التكلفة: {format_currency(SERVICE_PRICE)}\n📅 تنتهي الصلاحية في: `{tv_expiry[:10]}`"
                                        )
                                        
                                        asyncio.run_coroutine_threadsafe(
                                            app.bot.send_message(chat_id=user_id, text=renewal_msg, parse_mode='Markdown'),
                                            loop
                                        )
                                    else:
                                        # Insufficient balance (fallback)
                                        try:
                                            textverified.reservations.update_renewable(verification_id, include_for_renewal=False)
                                        except Exception as e:
                                            logging.error(f"Failed to disable server-side auto-renew for TV: {e}")
                                        update_auto_renew(num['id'], user_id, 0)
                                        
                                        warning_msg = (
                                            f"⚠️ *Auto-Renewal Warning!*\n\nAuto-renew is disabled and subscription will be cancelled in 1 day for `+{num['number']}`."
                                            if lang == 'en' else
                                            f"⚠️ *تحذير التجديد التلقائي!*\n\nتم تعطيل التجديد التلقائي وسيتم إلغاء الاشتراك خلال يوم واحد للرقم `+{num['number']}`."
                                        )
                                        
                                        asyncio.run_coroutine_threadsafe(
                                            app.bot.send_message(chat_id=user_id, text=warning_msg, parse_mode='Markdown'),
                                            loop
                                        )
                                else:
                                    # User turned off auto-renew in bot, but TV renewed it?
                                    update_number_expiry(num['id'], tv_expiry)
                            else:
                                update_number_expiry(num['id'], tv_expiry)

                    # 2. Sync Status
                    current_tv_status = details.state.value
                    if current_tv_status != num['status']:
                        logging.info(f"Status changed for {num['number']}: {num['status']} -> {current_tv_status}")
                        conn = get_db_connection()
                        conn.execute("UPDATE numbers SET status = ? WHERE id = ?", (current_tv_status, num['id']))
                        conn.commit()
                        conn.close()
                
                elif provider == 'pva':
                    # PVADeals renewal logic aligned with TextVerified
                    try:
                        res = pva_client.get_ltr_details(verification_id)
                        if res and res.get('success'):
                            data = res.get('data', {})
                            
                            # 1. Sync Auto-Renew Status from Server
                            server_auto_renew = data.get('autoRenewEnable')
                            if server_auto_renew is not None:
                                server_auto_renew_int = 1 if server_auto_renew else 0
                                if server_auto_renew_int != num['auto_renew']:
                                    logging.info(f"Syncing PVA auto-renew for {num['number']}: {num['auto_renew']} -> {server_auto_renew_int}")
                                    update_auto_renew(num['id'], user_id, server_auto_renew_int)
                                    # Update local num copy for subsequent checks in this loop
                                    num = dict(num)
                                    num['auto_renew'] = server_auto_renew_int

                            # 2. Sync Expiry Date
                            server_expiry = data.get('expiryDate') or data.get('expiresAt') or data.get('endTime')
                            
                            # 3. Sync Status (NEW: Hide flagged/expired numbers)
                            server_status = data.get('status', '').upper()
                            if server_status in ['FLAGGED', 'CANCELLED', 'EXPIRED']:
                                logging.info(f"PVA number {num['number']} is {server_status} on server. Marking as deleted.")
                                def mark_inactive():
                                    conn = get_db_connection()
                                    conn.execute("UPDATE numbers SET status = 'deleted' WHERE id = ?", (num['id'],))
                                    conn.commit()
                                    conn.close()
                                mark_inactive()
                                continue # Skip renewal checks for inactive numbers

                            if server_expiry:
                                import dateutil.parser
                                server_expiry_dt = dateutil.parser.parse(server_expiry)
                                now = datetime.datetime.now(server_expiry_dt.tzinfo) if server_expiry_dt.tzinfo else datetime.datetime.now(datetime.UTC)
                                
                                # --- PROACTIVE SAFETY CHECK (1 day before) ---
                                # If expiring within 24h, auto-renew is ON, but balance is low -> TURN OFF server side
                                user = get_user(user_id)
                                lang = user['language'] or 'en'
                                time_diff = server_expiry_dt - now
                                
                                if time_diff.total_seconds() <= 86400 and num['auto_renew']:
                                    if user['balance'] < PVADEALS_PRICE:
                                        logging.warning(f"Low balance for PVA {num['number']}. Disabling server-side auto-renew.")
                                        try:
                                            pva_client.set_auto_renew(verification_id, False)
                                            update_auto_renew(num['id'], user_id, 0)
                                            num = dict(num)
                                            num['auto_renew'] = 0
                                            
                                            warning_msg = (
                                                f"⚠️ *Auto-Renewal Warning!*\n\nAuto-renew is disabled and subscription will be cancelled in 1 day for `+{num['number']}`."
                                                if lang == 'en' else
                                                f"⚠️ *تحذير التجديد التلقائي!*\n\nتم تعطيل التجديد التلقائي وسيتم إلغاء الاشتراك خلال يوم واحد للرقم `+{num['number']}`."
                                            )
                                            asyncio.run_coroutine_threadsafe(
                                                app.bot.send_message(chat_id=user_id, text=warning_msg, parse_mode='Markdown'),
                                                loop
                                            )
                                        except Exception as e:
                                            logging.error(f"Failed to turn off server-side renewal for PVA: {e}")

                                # --- SYNC & RENEWAL DETECTION ---
                                if server_expiry != num['expires_at']:
                                    logging.info(f"Syncing PVADeals expiry for {num['number']}: {num['expires_at']} -> {server_expiry}")
                                    
                                    old_expiry_str = num['expires_at']
                                    if old_expiry_str:
                                        old_dt = dateutil.parser.parse(old_expiry_str)
                                        
                                        if server_expiry_dt > old_dt:
                                            # Server renewed it!
                                            if num['auto_renew']:
                                                if user['balance'] >= PVADEALS_PRICE:
                                                    update_balance(user_id, -PVADEALS_PRICE)
                                                    update_number_expiry(num['id'], server_expiry)
                                                    
                                                    renewal_msg = (
                                                        f"🔄 *Auto-Renewal Success!*\n\nYour WhatsApp number `+{num['number']}` (Basic) has been renewed.\n💰 Cost: {format_currency(PVADEALS_PRICE)}\n📅 New Expiry: `{server_expiry[:10]}`"
                                                        if lang == 'en' else
                                                        f"🔄 *تم التجديد التلقائي بنجاح!*\n\nتم تجديد رقم الواتساب (عادي) الخاص بك `+{num['number']}`.\n💰 التكلفة: {format_currency(PVADEALS_PRICE)}\n📅 تنتهي الصلاحية في: `{server_expiry[:10]}`"
                                                    )
                                                    
                                                    asyncio.run_coroutine_threadsafe(
                                                        app.bot.send_message(chat_id=user_id, text=renewal_msg, parse_mode='Markdown'),
                                                        loop
                                                    )
                                                else:
                                                    # Insufficient balance (server already renewed it? Disable server renewal and notify user)
                                                    try:
                                                        res_det = pva_client.get_ltr_details(verification_id)
                                                        if res_det and res_det.get('success'):
                                                            current_state = res_det.get('data', {}).get('autoRenewEnable', False)
                                                            if current_state:
                                                                pva_client.set_auto_renew(verification_id)
                                                    except Exception as e:
                                                        logging.error(f"Failed to disable server-side auto-renew for PVA: {e}")
                                                    update_auto_renew(num['id'], user_id, 0)
                                                    update_number_expiry(num['id'], server_expiry)
                                                    
                                                    warning_msg = (
                                                        f"⚠️ *Auto-Renewal Warning!*\n\nAuto-renew is disabled and subscription will be cancelled in 1 day for `+{num['number']}`."
                                                        if lang == 'en' else
                                                        f"⚠️ *تحذير التجديد التلقائي!*\n\nتم تعطيل التجديد التلقائي وسيتم إلغاء الاشتراك خلال يوم واحد للرقم `+{num['number']}`."
                                                    )
                                                    asyncio.run_coroutine_threadsafe(
                                                        app.bot.send_message(chat_id=user_id, text=warning_msg, parse_mode='Markdown'),
                                                        loop
                                                    )
                                            else:
                                                # Sync anyway if renewed externally
                                                update_number_expiry(num['id'], server_expiry)
                                        else:
                                            # Dates match or server is behind? Just sync if server is newer
                                            update_number_expiry(num['id'], server_expiry)
                                    else:
                                        # No local date? Set it.
                                        update_number_expiry(num['id'], server_expiry)

                    except Exception as e:
                        is_404 = False
                        if hasattr(e, 'response') and e.response is not None:
                            if e.response.status_code == 404:
                                is_404 = True
                        elif "404" in str(e) or "Request not found" in str(e):
                            is_404 = True

                        if is_404:
                            logging.warning(f"PVA number {num['number']} not found on PVADeals (404). Marking as deleted.")
                            conn = get_db_connection()
                            conn.execute("UPDATE numbers SET status = 'deleted' WHERE id = ?", (num['id'],))
                            conn.commit()
                            conn.close()
                        else:
                            logging.error(f"PVADeals sync failed for {num['number']}: {e}")

            except Exception as e:
                logging.error(f"Error syncing number {num['number']}: {e}")

    except Exception as e:
        logging.error(f"Error in sync_and_renew_worker: {e}")

async def auto_renewal_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job to handle auto-renewals and sync numbers for all providers."""
    app = context.application
    loop = asyncio.get_running_loop()
    threading.Thread(target=sync_and_renew_worker, args=(app, loop), daemon=True).start()

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    logging.info(f"Button clicked by {user_id}: {data}")
    
    # Self-healing user identification: capture missing info on every interaction
    await asyncio.to_thread(update_user_info, user_id, username=update.effective_user.username, first_name=update.effective_user.first_name)
    
    user = await asyncio.to_thread(get_user, user_id)
    lang = user['language'] if user and user['language'] else 'en'
    s = STRINGS[lang]

    if data == 'main_lang':
        await show_language_selection(update, context)
        return

    if data.startswith('set_lang_'):
        new_lang = data.split('_')[2]
        await asyncio.to_thread(set_user_lang, user_id, new_lang)
        await query.edit_message_text(f"✅ Language set to {new_lang.upper()} / تم تغيير اللغة إلى {new_lang.upper()}!")
        await start(update, context)
        return

    if data.startswith('admin_nums_menu_'):
        target_id = int(data.split('_')[3])
        await admin_nums_menu(update, context, target_id)
        return

    if data.startswith('admin_addnum_prompt_'):
        target_id = int(data.split('_')[3])
        context.user_data['admin_target_id'] = target_id
        
        keyboard = [
            [InlineKeyboardButton("Premium (TextVerified)", callback_data=f"admin_select_prov_tv_{target_id}"),
             InlineKeyboardButton("Basic (PVADeals)", callback_data=f"admin_select_prov_pva_{target_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"admin_nums_menu_{target_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"➕ *Step 1: Select Provider for `{target_id}`*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return

    if data.startswith('admin_select_prov_'):
        parts = data.split('_')
        provider = parts[3]
        target_id = int(parts[4])
        
        context.user_data['admin_action'] = 'addnumber'
        context.user_data['admin_provider'] = provider
        context.user_data['admin_target_id'] = target_id
        
        prov_name = "Premium (TV)" if provider == 'tv' else "Basic (PVA)"
        hint = (
            "\n💡 *Hint:* For PVA, you can find the ID in your dashboard under 'Long Term Rentals' (it's the code in the URL)."
            if provider == 'pva' else ""
        )
        await query.edit_message_text(
            f"➕ *Step 2: Enter Details ({prov_name})*\n\nTarget User: `{target_id}`\n\nPlease type the number and verification ID in this format:\n`NUMBER VERIF_ID`\n(e.g., `1234567890 {('TV_123' if provider == 'tv' else 'PVA_123')}`){hint}",
            parse_mode='Markdown'
        )
        return

    if data.startswith('admin_credit_prompt_') or data.startswith('admin_debit_prompt_'):
        parts = data.split('_')
        action = parts[1] # credit or debit
        t_id = int(parts[3])
        
        context.user_data['admin_action'] = f'credit_{action}'
        context.user_data['admin_target_id'] = t_id
        
        action_title = "Add Credit to" if action == 'credit' else "Remove Credit from"
        action_emoji = "➕" if action == 'credit' else "➖"
        
        amounts = [5, 10, 25, 50, 100]
        keyboard = []
        row = []
        for amt in amounts:
            row.append(InlineKeyboardButton(f"${amt}", callback_data=f"admin_{action}_{t_id}_{amt}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f"admin_user_manage_{t_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        msg_text = (
            f"{action_emoji} *{action_title} User `{t_id}`*\n\n"
            f"Please **type the exact amount** in chat (e.g. `12.5` or `3`), or select a quick preset below:"
        )
        await query.edit_message_text(msg_text, reply_markup=reply_markup, parse_mode='Markdown')
        return

    if data.startswith('admin_view_nums_'):
        t_id = int(data.split('_')[3])
        numbers = await asyncio.to_thread(get_user_numbers, t_id)
        
        # 1. Edit the callback query message to act as the header
        text = f"📱 *Numbers for User `{t_id}`:*"
        if not numbers:
            text += "\n\nThis user has no active numbers."
            keyboard = [[InlineKeyboardButton("🔙 Back to User", callback_data=f"admin_user_manage_{t_id}")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
            
        keyboard = [[InlineKeyboardButton("🔙 Back to User", callback_data=f"admin_user_manage_{t_id}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        # 2. Get admin language settings
        admin_user = await asyncio.to_thread(get_user, user_id)
        admin_lang = admin_user['language'] if admin_user and admin_user['language'] else 'en'
        s = STRINGS[admin_lang]

        # 3. Send each number as a separate message with control buttons
        for number in numbers:
            status_icon = "✅" if number['status'] in ['active', 'renewableActive'] else "❌"
            auto_renew_status = s['status_active'] if number['auto_renew'] else s['status_disabled']
            expiry_info = ""
            
            if number['expires_at']:
                try:
                    import dateutil.parser
                    expiry_dt = dateutil.parser.parse(number['expires_at'])
                    expiry_date = expiry_dt.strftime('%Y-%m-%d')
                    
                    # Calculate time left
                    now = datetime.datetime.now(expiry_dt.tzinfo) if expiry_dt.tzinfo else datetime.datetime.now(datetime.UTC)
                    diff = expiry_dt - now
                    
                    if diff.total_seconds() <= 0:
                        time_left = s['label_expired']
                    elif diff.days > 0:
                        time_left = f"{diff.days}d {s['label_left']}"
                    else:
                        hours = int(diff.total_seconds() // 3600)
                        time_left = f"{hours}h {s['label_left']}"
                    
                    expiry_info = f"\n{s['label_expires']}: `{expiry_date}` ({time_left})"
                except Exception as e:
                    logging.error(f"Date parsing failed for {number['number']}: {e}")
                    expiry_info = f"\n{s['label_expires']}: `{number['expires_at'][:10]}`"

            number_text = (
                f"{status_icon} {s['label_number']}: `+{number['number']}`\n"
                f"{s['label_service']}: {number['service'].capitalize()}\n"
                f"{s['label_auto_renew']}: {auto_renew_status}"
                f"{expiry_info}"
            )

            # Define admin callbacks that encode number id and target user id
            buttons = [
                [InlineKeyboardButton(s['btn_get_code'], callback_data=f"admin_code_{number['id']}_{t_id}"),
                 InlineKeyboardButton(s['btn_refund'], callback_data=f"admin_refund_{number['id']}_{t_id}")]
            ]

            if number['auto_renew']:
                buttons.append([InlineKeyboardButton(s['btn_cancel_sub'], callback_data=f"admin_cancel_{number['id']}_{t_id}")])
            else:
                buttons.append([InlineKeyboardButton(s['btn_enable_renew'], callback_data=f"admin_enable_{number['id']}_{t_id}")])

            reply_markup = InlineKeyboardMarkup(buttons)
            await context.bot.send_message(chat_id=user_id, text=number_text, reply_markup=reply_markup, parse_mode='Markdown')
        return

    if data.startswith('admin_removenum_prompt_'):
        t_id = int(data.split('_')[3])
        numbers = await asyncio.to_thread(get_user_numbers, t_id)
        if not numbers:
            text = f"🗑 *Remove Number for `{t_id}`:*\n\nThis user has no active numbers to remove."
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data=f"admin_user_manage_{t_id}")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        keyboard = []
        for number in numbers:
            keyboard.append([InlineKeyboardButton(f"❌ Remove +{number['number']}", callback_data=f"admin_do_remove_{number['id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f"admin_user_manage_{t_id}")])
        await query.edit_message_text(f"🗑 Select number to remove for `{t_id}`:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith('admin_menu_'):
        action = data.split('_')[2]
        context.user_data['admin_action'] = action
        await query.edit_message_text(
            f"🔍 *Admin: {action.capitalize()} User*\n\nPlease type the User ID or @username of the target user:",
            parse_mode='Markdown'
        )
        return

    if data.startswith('admin_do_remove_'):
        number_id = int(data.split('_')[3])
        
        def remove_number():
            conn = get_db_connection()
            num = conn.execute("SELECT * FROM numbers WHERE id = ?", (number_id,)).fetchone()
            if num:
                conn.execute("UPDATE numbers SET status = 'deleted' WHERE id = ?", (number_id,))
                conn.commit()
            conn.close()
            return num

        num_row = await asyncio.to_thread(remove_number)
        if num_row:
            await query.edit_message_text(f"✅ Number `+{num_row['number']}` has been removed from user `{num_row['user_id']}` locally.")
        else:
            keyboard = [[InlineKeyboardButton("🔙 Back to List", callback_data="admin_list_users_recent")]]
            await query.edit_message_text("❌ Number not found or already removed.", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith('admin_credit_') or data.startswith('admin_debit_'):
        context.user_data.pop('admin_action', None)
        context.user_data.pop('admin_target_id', None)
        
        parts = data.split('_')
        action_type = parts[1] # credit or debit
        target_id = int(parts[2])
        amount = float(parts[3])
        
        target_user = await asyncio.to_thread(get_user, target_id)
        if not target_user:
            keyboard = [[InlineKeyboardButton("🔙 Back to List", callback_data="admin_list_users_recent")]]
            await query.edit_message_text("❌ User no longer exists.", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if action_type == 'debit':
            amount = -amount

        await asyncio.to_thread(update_balance, target_id, amount)
        new_balance = (await asyncio.to_thread(get_user, target_id))['balance']
        
        await query.edit_message_text(
            f"✅ *Balance Updated*\n\n"
            f"User: @{target_user['username']} (`{target_id}`)\n"
            f"Action: {action_type.capitalize()} {format_currency(abs(amount))}\n"
            f"New Balance: *{format_currency(new_balance)}*",
            parse_mode='Markdown'
        )
        return

    if data == 'deposit_method_crypto':
        keyboard = []
        row = []
        for amt in DEPOSIT_AMOUNTS:
            row.append(InlineKeyboardButton(f"${amt}", callback_data=f"deposit_amt_{amt}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            s['deposit_select_amt'],
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return

    if data == 'deposit_method_shamcash':
        await query.edit_message_text(
            s['shamcash_info'],
            parse_mode='Markdown'
        )
        context.user_data['user_action'] = 'shamcash_amt'
        return

    # --- ADMIN ACTIONS ---
    if data == 'admin_pending_shamcash':
        def get_pending_shamcash():
            conn = get_db_connection()
            p = conn.execute("SELECT * FROM manual_deposits WHERE status = 'pending' ORDER BY created_at DESC").fetchall()
            conn.close()
            return p

        pending = await asyncio.to_thread(get_pending_shamcash)

        if not pending:
            keyboard = [[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")]]
            await query.edit_message_text("📥 *ShamCash Requests*\n\nNo pending ShamCash requests.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        keyboard = []
        for req in pending:
            user_target = await asyncio.to_thread(get_user, req['user_id'])
            user_name = f"@{user_target['username']}" if user_target and user_target['username'] else f"{user_target['first_name'] or 'User'} ({req['user_id']})"
            btn_text = f"👤 {user_name} - {format_currency(req['amount'])} ({req['created_at'][:10]})"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"admin_sham_view_{req['id']}")])
            
        keyboard.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")])
        
        await query.edit_message_text(
            f"📥 *Pending ShamCash Requests ({len(pending)}):*\n\nSelect a request to view details and receipt:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return

    if data.startswith('admin_sham_view_'):
        req_id = int(data.split('_')[3])
        
        def get_shamcash_request(r_id):
            conn = get_db_connection()
            r = conn.execute("SELECT * FROM manual_deposits WHERE id = ?", (r_id,)).fetchone()
            conn.close()
            return r

        req = await asyncio.to_thread(get_shamcash_request, req_id)
        if not req:
            keyboard = [[InlineKeyboardButton("🔙 Back to List", callback_data="admin_pending_shamcash")]]
            await query.edit_message_text("❌ Request not found.", reply_markup=InlineKeyboardMarkup(keyboard))
            return
            
        user_target = await asyncio.to_thread(get_user, req['user_id'])
        user_name = f"@{user_target['username']}" if user_target and user_target['username'] else f"{user_target['first_name'] or 'User'} ({req['user_id']})"
        
        keyboard = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"admin_sham_approve_{req['id']}"),
             InlineKeyboardButton("❌ Decline", callback_data=f"admin_sham_decline_{req['id']}")],
            [InlineKeyboardButton("🔙 Back to List", callback_data="admin_pending_shamcash")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"📥 *Pending ShamCash Request Details*\n\n"
            f"👤 *User:* {user_name}\n"
            f"💰 *Amount:* {format_currency(req['amount'])}\n"
            f"📅 *Date:* `{req['created_at'][:19]}`\n"
            f"🆔 *Request ID:* `{req['id']}`\n\n"
            "The receipt (PDF) has been sent below.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        try:
            await context.bot.send_document(
                chat_id=ADMIN_ID, 
                document=req['receipt_file_id'], 
                caption=f"Receipt for User {user_name} - {format_currency(req['amount'])}"
            )
        except Exception as e:
            logging.error(f"Failed to send PDF receipt: {e}")
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"❌ Failed to display receipt document on Telegram: {e}"
            )
        return

    if data == 'admin_list_users_recent':
        logging.info("Admin: Listing users sorted by recent")
        await admin_list_users(update, context, sort_by='created_at')
        return

    if data == 'admin_list_users_balance':
        logging.info("Admin: Listing users sorted by balance")
        await admin_list_users(update, context, sort_by='balance')
        return

    if data == 'admin_main':
        logging.info(f"Admin: Back to main menu for {user_id}")
        await admin_command(update, context)
        return

    if data.startswith('admin_user_manage_'):
        t_id = int(data.split('_')[3])
        await admin_manage_user_menu(update, context, t_id)
        return

    if data.startswith('admin_sham_approve_') or data.startswith('admin_sham_decline_'):
        parts = data.split('_')
        is_approve = parts[2] == 'approve'
        req_id = int(parts[3])

        def process_shamcash():
            conn = get_db_connection()
            r = conn.execute("SELECT * FROM manual_deposits WHERE id = ?", (req_id,)).fetchone()
            
            if not r or r['status'] != 'pending':
                conn.close()
                return None, "Request already processed or not found."
            
            if is_approve:
                conn.execute("UPDATE manual_deposits SET status = 'approved', updated_at = ? WHERE id = ?", (get_timestamp(), req_id))
            else:
                conn.execute("UPDATE manual_deposits SET status = 'declined', updated_at = ? WHERE id = ?", (get_timestamp(), req_id))
            
            conn.commit()
            conn.close()
            return r, None

        req, error = await asyncio.to_thread(process_shamcash)

        if error:
            keyboard = [[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")]]
            await query.edit_message_text(f"❌ {error}", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        user_target = await asyncio.to_thread(get_user, req['user_id'])
        u_lang = user_target['language'] or 'en'

        keyboard = [[InlineKeyboardButton("🔙 Back to Pending List", callback_data="admin_pending_shamcash")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if is_approve:
            await asyncio.to_thread(update_balance, req['user_id'], req['amount'])
            await asyncio.to_thread(check_and_reward_referrer, req['user_id'], 'manual', req_id)
            await context.bot.send_message(chat_id=req['user_id'], text=STRINGS[u_lang]['shamcash_approved_msg'].format(amount=format_currency(req['amount'])))
            await query.edit_message_text(f"✅ Approved {format_currency(req['amount'])} for user `{req['user_id']}`", reply_markup=reply_markup)
        else:
            await context.bot.send_message(chat_id=req['user_id'], text=STRINGS[u_lang]['shamcash_declined_msg'])
            await query.edit_message_text(f"❌ Declined request from user `{req['user_id']}`", reply_markup=reply_markup)
        return

    if data.startswith('deposit_amt_'):
        amount_str = data.split('_')[2]
        amount = float(amount_str)
        invoice_data = await asyncio.to_thread(create_invoice, amount, user_id)
        if not invoice_data:
            await query.edit_message_text("Unable to create a deposit right now. Please try again later.")
            return

        invoice_url = invoice_data.get('invoice_url') or invoice_data.get('invoiceUrl')
        await query.edit_message_text(
            s['deposit_created'].format(
                amount=format_currency(amount),
                url=invoice_url
            ),
            parse_mode='Markdown',
            disable_web_page_preview=False
        )
        return

    if data == 'main_rent':
        await rent(update, context)
        return
    if data == 'rent_tv':
        await process_rent(update, context, 'tv')
        return
    if data == 'rent_pva':
        await process_rent(update, context, 'pva')
        return
    if data == 'main_deposit':
        await deposit(update, context)
        return
    if data == 'main_profile':
        await profile(update, context)
        return
    if data == 'main_numbers':
        await mynumbers(update, context)
        return

    if data.startswith('admin_code_') or data.startswith('admin_refund_') or data.startswith('admin_cancel_') or data.startswith('admin_enable_'):
        # Guard: only admin can execute admin callbacks
        if not is_admin(user_id):
            await query.answer("Access denied.", show_alert=True)
            return

        parts = data.split('_')
        action = parts[1] # code, refund, cancel, or enable
        number_id = int(parts[2])
        t_id = int(parts[3])
        
        number_row = await asyncio.to_thread(get_number_record, number_id, t_id)
        if not number_row:
            await query.edit_message_text("❌ Number not found.")
            return

        admin_user = await asyncio.to_thread(get_user, user_id)
        admin_lang = admin_user['language'] if admin_user and admin_user['language'] else 'en'
        s = STRINGS[admin_lang]

        if action == 'code':
            request_time = datetime.datetime.now(datetime.timezone.utc)
            await asyncio.to_thread(mark_code_requested, number_row['id'])
            sms_data = await poll_sms_code(
                number_row['verification_id'], 
                provider=dict(number_row).get('provider', 'tv'),
                query=query,
                number_str=number_row['number'],
                lang=admin_lang,
                min_timestamp=request_time
            )

            if sms_data and sms_data.get('code'):
                await query.edit_message_text(
                    s['code_received'].format(
                        number=number_row['number'],
                        code=sms_data['code'],
                        sms=sms_data['sms']
                    ),
                    parse_mode='Markdown'
                )
            else:
                total_secs = SMS_POLL_ATTEMPTS * SMS_POLL_DELAY
                if admin_lang == 'ar':
                    no_code_text = (
                        f"❌ *لم يتم استلام الكود*\n\n"
                        f"تم فحص الكود لمدة {total_secs} ثانية ولم يصل رمز التحقق للرقم `+{number_row['number']}`.\n\n"
                        f"👉 يرجى المحاولة مرة أخرى."
                    )
                else:
                    no_code_text = (
                        f"❌ *No Code Received*\n\n"
                        f"Checked for {total_secs} seconds but no code arrived for `+{number_row['number']}`.\n\n"
                        f"👉 Please try again."
                    )
                await query.edit_message_text(no_code_text, parse_mode='Markdown')
            return

        elif action == 'refund':
            await query.edit_message_text("⏳ Processing refund on server...")
            try:
                price = SERVICE_PRICE
                if number_row['provider'] in ['textverified', 'tv']:
                    await asyncio.to_thread(textverified.reservations.refund_renewable, number_row['verification_id'])
                else:
                    price = PVADEALS_PRICE
                    await asyncio.to_thread(pva_client.flag_number, number_row['verification_id'])
                    
                def mark_refunded():
                    conn = get_db_connection()
                    conn.execute("UPDATE numbers SET status = 'refunded' WHERE id = ?", (number_id,))
                    conn.commit()
                    conn.close()

                await asyncio.to_thread(mark_refunded)
                await asyncio.to_thread(update_balance, t_id, price)
                
                await query.edit_message_text(
                    f"✅ Number `+{number_row['number']}` has been refunded.\n💰 {format_currency(price)} credited to user `{t_id}`.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logging.error(f"Admin refund failed: {e}")
                await query.edit_message_text(f"❌ Refund failed for +{number_row['number']}: {e}")
            return

        elif action in ['cancel', 'enable']:
            status_val = 1 if action == 'enable' else 0
            if number_row['provider'] in ['textverified', 'tv']:
                try:
                    await asyncio.to_thread(
                        textverified.reservations.update_renewable,
                        number_row['verification_id'],
                        include_for_renewal=(action == 'enable')
                    )
                except Exception as e:
                    logging.error(f"Admin failed to update TV renewal: {e}")
            elif number_row['provider'] == 'pva':
                try:
                    res = await asyncio.to_thread(pva_client.get_ltr_details, number_row['verification_id'])
                    if res and res.get('success'):
                        current_state = res.get('data', {}).get('autoRenewEnable', False)
                        target_state = (action == 'enable')
                        if current_state != target_state:
                            await asyncio.to_thread(pva_client.set_auto_renew, number_row['verification_id'])
                except Exception as e:
                    logging.error(f"Admin failed to update PVA renewal: {e}")
            
            await asyncio.to_thread(update_auto_renew, number_id, t_id, status_val)
            msg = f"🔄 *Auto-Renewal Enabled for user `{t_id}`*" if action == 'enable' else f"🛑 *Subscription Cancelled for user `{t_id}`*"
            await query.edit_message_text(msg, parse_mode='Markdown')
            return

    if data.startswith('sub_cancel_'):
        number_id = int(data.split('_')[2])
        number_row = await asyncio.to_thread(get_number_record, number_id, user_id)
        
        if number_row:
            if number_row['provider'] in ['textverified', 'tv']:
                try:
                    await asyncio.to_thread(
                        textverified.reservations.update_renewable,
                        number_row['verification_id'], 
                        include_for_renewal=False
                    )
                except Exception as e:
                    logging.error(f"Failed to cancel subscription on TV: {e}")
            elif number_row['provider'] == 'pva':
                try:
                    # PVA is a toggle, so check current state first
                    res = await asyncio.to_thread(pva_client.get_ltr_details, number_row['verification_id'])
                    if res and res.get('success'):
                        current_state = res.get('data', {}).get('autoRenewEnable', False)
                        if current_state: # Only toggle if it's currently ON
                            await asyncio.to_thread(pva_client.set_auto_renew, number_row['verification_id'])
                except Exception as e:
                    logging.error(f"Failed to cancel subscription on PVA: {e}")
            
            await asyncio.to_thread(update_auto_renew, number_id, user_id, 0)
            
            await query.edit_message_text(
                "🛑 *Subscription Cancelled*" if lang == 'en' else "🛑 *تم إلغاء الاشتراك*",
                parse_mode='Markdown'
            )
        return

    if data.startswith('sub_enable_'):
        number_id = int(data.split('_')[2])
        number_row = await asyncio.to_thread(get_number_record, number_id, user_id)
        
        if number_row:
            if number_row['provider'] in ['textverified', 'tv']:
                try:
                    await asyncio.to_thread(
                        textverified.reservations.update_renewable,
                        number_row['verification_id'], 
                        include_for_renewal=True
                    )
                except Exception as e:
                    logging.error(f"Failed to enable subscription on TV: {e}")
            elif number_row['provider'] == 'pva':
                try:
                    # PVA is a toggle, so check current state first
                    res = await asyncio.to_thread(pva_client.get_ltr_details, number_row['verification_id'])
                    if res and res.get('success'):
                        current_state = res.get('data', {}).get('autoRenewEnable', False)
                        if not current_state: # Only toggle if it's currently OFF
                            await asyncio.to_thread(pva_client.set_auto_renew, number_row['verification_id'])
                except Exception as e:
                    logging.error(f"Failed to enable subscription on PVA: {e}")
            
            await asyncio.to_thread(update_auto_renew, number_id, user_id, 1)
            
            await query.edit_message_text(
                "🔄 *Auto-Renewal Enabled*" if lang == 'en' else "🔄 *تم تفعيل التجديد*",
                parse_mode='Markdown'
            )
        return

    if data.startswith('sub_refund_'):
        number_id = int(data.split('_')[2])
        number_row = await asyncio.to_thread(get_number_record, number_id, user_id)
        
        if not number_row:
            await query.edit_message_text("❌ Number not found or does not belong to you.")
            return

        # NEW REFUND SAFETY CHECK
        code_requested = number_row['code_requested'] if 'code_requested' in number_row.keys() else 0
        code_received = number_row['code_received'] if 'code_received' in number_row.keys() else 0
        
        if not code_requested:
            msg = (
                "❌ *Refund Denied*\n\nYou can only request a refund after trying to retrieve a code using the 'Get Code' button."
                if lang == 'en' else
                "❌ *تم رفض استرداد الأموال*\n\nيمكنك طلب استرداد الأموال فقط بعد محاولة الحصول على الرمز باستخدام زر 'الحصول على الكود'."
            )
            await query.edit_message_text(msg, parse_mode='Markdown')
            return
            
        if code_received:
            msg = (
                "❌ *Refund Denied*\n\nThis number has already received a code. Refunds are only allowed if no code was received."
                if lang == 'en' else
                "❌ *تم رفض استرداد الأموال*\n\nلقد تلقى هذا الرقم رمزاً بالفعل. يسمح بالاسترداد فقط إذا لم يتم استلام أي رمز."
            )
            await query.edit_message_text(msg, parse_mode='Markdown')
            return

        await query.edit_message_text(s['refund_processing'])
        
        try:
            price = SERVICE_PRICE
            if number_row['provider'] == 'tv':
                await asyncio.to_thread(textverified.reservations.refund_renewable, number_row['verification_id'])
            else:
                price = PVADEALS_PRICE
                # PVADeals flagging/refund logic
                await asyncio.to_thread(pva_client.flag_number, number_row['verification_id'])
            
            def mark_refunded():
                conn = get_db_connection()
                conn.execute("UPDATE numbers SET status = 'refunded' WHERE id = ?", (number_id,))
                conn.commit()
                conn.close()

            await asyncio.to_thread(mark_refunded)
            await asyncio.to_thread(update_balance, user_id, price)
            
            await query.edit_message_text(
                s['refund_success'].format(
                    number=number_row['number'],
                    price=format_currency(price)
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"Refund failed for {number_row['number']}: {e}")
            await query.edit_message_text(
                s['refund_fail'].format(number=number_row['number']),
                parse_mode='Markdown'
            )
        return

    if data.startswith('code_'):
        number_id = int(data.split('_', 1)[1])
        number_row = await asyncio.to_thread(get_number_record, number_id, user_id)
        if not number_row:
            await query.edit_message_text("This number is not found or does not belong to you.")
            return

        request_time = datetime.datetime.now(datetime.timezone.utc)
        await asyncio.to_thread(mark_code_requested, number_id)
        sms_data = await poll_sms_code(
            number_row['verification_id'], 
            provider=dict(number_row).get('provider', 'tv'),
            query=query,
            number_str=number_row['number'],
            lang=lang,
            min_timestamp=request_time
        )

        if sms_data and sms_data.get('code'):
            await query.edit_message_text(
                s['code_received'].format(
                    number=number_row['number'],
                    code=sms_data['code'],
                    sms=sms_data['sms']
                ),
                parse_mode='Markdown'
            )
        else:
            total_secs = SMS_POLL_ATTEMPTS * SMS_POLL_DELAY
            if lang == 'ar':
                no_code_text = (
                    f"❌ *لم يتم استلام الكود*\n\n"
                    f"تم فحص الكود لمدة {total_secs} ثانية ولم يصل رمز التحقق للرقم `+{number_row['number']}`.\n\n"
                    f"👉 إذا كنت قد طلبت كود الواتساب للتو، يرجى الانتظار بضع ثوان والضغط على **📩 طلب الكود** مرة أخرى."
                )
            else:
                no_code_text = (
                    f"❌ *No Code Received*\n\n"
                    f"We checked for {total_secs} seconds but no verification code arrived for `+{number_row['number']}`.\n\n"
                    f"👉 If you just requested the code in WhatsApp, please wait a few seconds and tap **📩 Get Code** again."
                )
            await query.edit_message_text(no_code_text, parse_mode='Markdown')
        return

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Self-healing user identification: capture missing info on every interaction
    await asyncio.to_thread(update_user_info, user_id, username=update.effective_user.username, first_name=update.effective_user.first_name)
    
    user = await asyncio.to_thread(get_user, user_id)
    lang = user['language'] or 'en'
    s = STRINGS[lang]
    
    # --- USER ACTIONS ---
    if context.user_data and context.user_data.get('user_action'):
        action = context.user_data.pop('user_action')
        if action == 'shamcash_amt':
            try:
                amt = float(update.message.text.strip())
                context.user_data['sham_amt'] = amt
                
                # Send QR Code and Instructions
                if os.path.exists(SHAMCASH_QR_PATH):
                    with open(SHAMCASH_QR_PATH, 'rb') as photo:
                        await update.effective_message.reply_photo(
                            photo=photo,
                            caption=s['shamcash_payment_info'].format(
                                amount=format_currency(amt),
                                id=SHAMCASH_ID
                            ),
                            parse_mode='Markdown'
                        )
                else:
                    await update.effective_message.reply_text(
                        s['shamcash_payment_info'].format(
                            amount=format_currency(amt),
                            id=SHAMCASH_ID
                        ),
                        parse_mode='Markdown'
                    )
                
                await update.effective_message.reply_text(s['shamcash_receipt'], parse_mode='Markdown')
                context.user_data['user_action'] = 'shamcash_pdf'
            except ValueError:
                await update.effective_message.reply_text("❌ Please enter a valid number.")
            return

    # --- ADMIN STATE HANDLING ---
    if context.user_data and context.user_data.get('admin_action'):
        if not is_admin(user_id):
            logging.warning(f"Unauthorized admin state access by {user_id}")
            context.user_data.clear()
            return

        action = context.user_data.get('admin_action')
        logging.info(f"Admin action '{action}' in progress for {user_id}")
        target_user_id = context.user_data.get('admin_target_id')
        
        # Flow B: Target user already known from button click (e.g., credit input or addnumber)
        if target_user_id and action in ['credit_credit', 'credit_debit']:
            context.user_data.pop('admin_action', None)
            context.user_data.pop('admin_target_id', None)
            
            target_user = await asyncio.to_thread(get_user, target_user_id)
            if not target_user:
                await update.effective_message.reply_text("❌ Target user no longer exists.")
                return
            
            t_id = target_user['user_id']
            t_name = target_user['username'] or target_user['first_name'] or str(t_id)
            
            try:
                raw_text = update.message.text.strip().replace('$', '')
                amount = float(raw_text)
                if amount <= 0:
                    await update.effective_message.reply_text("❌ Amount must be greater than 0.")
                    return
                
                if action == 'credit_debit':
                    amount = -amount
                
                await asyncio.to_thread(update_balance, t_id, amount)
                updated_user = await asyncio.to_thread(get_user, t_id)
                new_bal = updated_user['balance']
                
                action_word = "Added" if amount > 0 else "Removed"
                formatted_amt = format_currency(abs(amount))
                formatted_new_bal = format_currency(new_bal)
                
                await update.effective_message.reply_text(
                    f"✅ *Balance Updated*\n\n"
                    f"User: `{t_name}` (`{t_id}`)\n"
                    f"Action: {action_word} {formatted_amt}\n"
                    f"New Balance: *{formatted_new_bal}*",
                    parse_mode='Markdown'
                )
            except ValueError:
                await update.effective_message.reply_text("❌ Invalid amount. Please enter a valid number (e.g., `10` or `12.50`).", parse_mode='Markdown')
            return

        if target_user_id and action == 'addnumber':
            context.user_data.pop('admin_action')
            context.user_data.pop('admin_target_id')
            
            target_user = await asyncio.to_thread(get_user, target_user_id)
            if not target_user:
                await update.effective_message.reply_text("❌ Target user no longer exists.")
                return
            
            t_id = target_user['user_id']
            t_name = target_user['username'] or target_user['first_name'] or str(t_id)
            
            try:
                parts = update.message.text.strip().split()
                if len(parts) < 2:
                    raise ValueError
                num = parts[0]
                v_id = parts[1]
                provider = parts[2].lower() if len(parts) > 2 else 'tv'
                
                if provider not in ['tv', 'pva']:
                    await update.effective_message.reply_text("❌ Provider must be 'tv' or 'pva'.")
                    return

                # Fetch details to verify and get expiry
                expiry = None
                status = 'active'
                try:
                    if provider == 'tv':
                        details = await asyncio.to_thread(textverified.reservations.details, v_id)
                        status = details.state.value
                        if hasattr(details, 'billing_cycle_id') and details.billing_cycle_id:
                            cycle = await asyncio.to_thread(textverified.billing_cycles.get, details.billing_cycle_id)
                            expiry = cycle.billing_cycle_ends_at.isoformat()
                    else:
                        res = await asyncio.to_thread(pva_client.get_ltr_details, v_id)
                        if res and res.get('success'):
                            data = res.get('data', {})
                            status = data.get('status', 'active')
                            expiry = data.get('expiryDate') or data.get('expiresAt') or data.get('endTime')
                except Exception as e:
                    logging.warning(f"Manual sync failed: {e}")
                
                if not expiry:
                    expiry = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=30)).isoformat()
                
                await asyncio.to_thread(add_number_record, t_id, num, v_id, expires_at=expiry, status=status, provider=provider)
                await update.effective_message.reply_text(
                    f"✅ Successfully linked number `+{num}` ({provider.upper()}) to `{t_name}`.\n"
                    f"Status: `{status}`\nExpiry: `{expiry[:10]}`",
                    parse_mode='Markdown'
                )
            except ValueError:
                await update.effective_message.reply_text("❌ Format error. Use: `NUMBER VERIF_ID [tv/pva]`")
            return

        # Flow A: Admin typed a target (username/ID) to start an action
        context.user_data.pop('admin_action')
        target_input = update.message.text.strip()
        target_user = await asyncio.to_thread(resolve_user, target_input)
        
        if not target_user:
            await update.effective_message.reply_text("❌ User not found. Use /admin to try again.")
            return

        t_id = target_user['user_id']
        t_name = target_user['username'] or target_user['first_name'] or str(t_id)

        if action == 'view':
            await update.effective_message.reply_text(
                f"👤 *User Profile*\n\n{format_user_profile(target_user)}",
                parse_mode='Markdown'
            )
        
        elif action == 'numbers':
            numbers = await asyncio.to_thread(get_user_numbers, t_id)
            if not numbers:
                await update.effective_message.reply_text(f"User @{t_name} has no active rented numbers.")
                return
            lines = [f"📱 *Numbers for @{t_name}:*\n"]
            for number in numbers:
                lines.append(f"• `+{number['number']}` — status: {number['status']}")
            await update.effective_message.reply_text("\n".join(lines), parse_mode='Markdown')

        elif action == 'addnumber':
            context.user_data['admin_target_id'] = t_id
            
            keyboard = [
                [InlineKeyboardButton("Premium (TextVerified)", callback_data=f"admin_select_prov_tv_{t_id}"),
                 InlineKeyboardButton("Basic (PVADeals)", callback_data=f"admin_select_prov_pva_{t_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.effective_message.reply_text(
                f"➕ *Step 1: Select Provider for @{t_name}*",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return

        elif action == 'removenum':
            numbers = await asyncio.to_thread(get_user_numbers, t_id)
            if not numbers:
                await update.effective_message.reply_text(f"User @{t_name} has no active rented numbers.")
                return
            
            keyboard = []
            for number in numbers:
                keyboard.append([InlineKeyboardButton(f"❌ Remove +{number['number']}", callback_data=f"admin_do_remove_{number['id']}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.effective_message.reply_text(f"📱 *Select Number to Remove for @{t_name}:*", reply_markup=reply_markup, parse_mode='Markdown')

        elif action in ['credit', 'debit']:
            amounts = [5, 10, 25, 50, 100]
            keyboard = []
            row = []
            for amt in amounts:
                row.append(InlineKeyboardButton(f"${amt}", callback_data=f"admin_{action}_{t_id}_{amt}"))
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
            if row: keyboard.append(row)
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.effective_message.reply_text(
                f"💰 *{action.capitalize()} User: @{t_name}*\n\nSelect the amount to {action}:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        return

    # Normal user message handling
    await update.effective_message.reply_text("I didn't understand that. Use the menu or /help to see available commands.")

app_flask = Flask(__name__)

# Global references for Webhook Mode
app = None
bot_loop = None

@app_flask.route('/webhook/nowpayments', methods=['POST'])
def nowpayments_webhook():
    # 1. Verify Signature
    x_signature = request.headers.get('x-nowpayments-sig')
    if not x_signature:
        logging.warning("Received NowPayments webhook without signature.")
        return jsonify({"error": "No signature"}), 400
    
    # Verify the signature using the IPN Secret
    data_raw = request.get_data()
    # Note: Signature verification depends on the exact format of NP_IPN_SECRET and data.
    # For now, we follow the standard HMAC pattern.
    
    data = request.json
    order_id = data.get('order_id')
    payment_status = data.get('payment_status')
    
    deposit = get_deposit_by_order(order_id)
    if not deposit:
        logging.warning(f"NowPayments webhook for unknown order: {order_id}")
        return jsonify({"error": "Unknown order"}), 404
        
    if deposit['status'] == 'completed':
        return jsonify({"status": "already_processed"}), 200
        
    # 'finished' means payment is fully confirmed
    if payment_status == 'finished':
        user_id = deposit['user_id']
        update_balance(user_id, deposit['amount'])
        update_deposit_status(deposit['id'], 'completed')
        
        logging.info(f"Payment completed for user {user_id}: {deposit['amount']}")
        
        # Check and reward referrer
        check_and_reward_referrer(user_id, 'crypto', deposit['id'])
        
        # Optional: notify user via telegram bot
        # (This would require bot instance access which is easier in async app, 
        # but here we just log it and rely on background sync/polling)
        
    return jsonify({"status": "success"}), 200

@app_flask.route('/webhook/telegram', methods=['POST'])
def telegram_webhook():
    global app, bot_loop
    if not app or not bot_loop:
        logging.warning("Telegram webhook received but bot is not initialized.")
        return jsonify({"error": "Bot not initialized"}), 503
        
    try:
        update = Update.de_json(request.json, app.bot)
        # Schedule the update processing on the bot's event loop
        asyncio.run_coroutine_threadsafe(app.process_update(update), bot_loop)
    except Exception as e:
        logging.error(f"Error processing webhook update: {e}")
        return jsonify({"error": str(e)}), 500
        
    return "ok", 200

def run_flask():
    port = int(os.getenv("PORT", 5000))
    app_flask.run(host='0.0.0.0', port=port)

async def main_async():
    global app, bot_loop
    bot_loop = asyncio.get_running_loop()
    
    app = Application.builder().token(TELEGRAM_TOKEN).read_timeout(30).connect_timeout(30).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('profile', profile))
    app.add_handler(CommandHandler('deposit', deposit))
    app.add_handler(CommandHandler('rent', rent))
    app.add_handler(CommandHandler('buy', rent))
    app.add_handler(CommandHandler('mynumbers', mynumbers))
    app.add_handler(CommandHandler('sync', sync_numbers_command))
    app.add_handler(CommandHandler('admin', admin_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    
    await app.initialize()
    await app.start()
    
    # Set up Telegram Webhook URL
    webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL")
    if not webhook_url:
        from urllib.parse import urlparse
        parsed = urlparse(IPN_CALLBACK_URL)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        webhook_url = f"{base_url}/webhook/telegram"
        
    logging.info(f"Setting Telegram webhook to: {webhook_url}")
    await app.bot.set_webhook(url=webhook_url)
    
    # Start auto-renewal background task
    app.job_queue.run_repeating(auto_renewal_job, interval=900, first=10)
    
    logging.info("Bot is securely running on Webhooks...")
    
    # Keep the event loop running
    stop_event = asyncio.Event()
    await stop_event.wait()

def main_polling():
    global app, bot_loop
    app = Application.builder().token(TELEGRAM_TOKEN).read_timeout(30).connect_timeout(30).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('profile', profile))
    app.add_handler(CommandHandler('deposit', deposit))
    app.add_handler(CommandHandler('rent', rent))
    app.add_handler(CommandHandler('buy', rent))
    app.add_handler(CommandHandler('mynumbers', mynumbers))
    app.add_handler(CommandHandler('sync', sync_numbers_command))
    app.add_handler(CommandHandler('admin', admin_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    
    logging.info("Bot is securely running with long polling...")
    
    # Start auto-renewal background task using JobQueue
    app.job_queue.run_repeating(auto_renewal_job, interval=900, first=10)
    
    app.run_polling()

if __name__ == '__main__':
    # Initialize DB (runs synchronously before threads/event loops)
    init_db()

    # Start Flask in a separate thread
    threading.Thread(target=run_flask, daemon=True).start()
    
    use_webhook = os.getenv("USE_WEBHOOK", "false").lower() == "true"
    
    if use_webhook:
        try:
            asyncio.run(main_async())
        except KeyboardInterrupt:
            logging.info("Webhook bot stopped.")
    else:
        main_polling()

