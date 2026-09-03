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
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))

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
    SHAMCASH_QR_PATH = os.path.join(os.path.dirname(__file__), '../' + SHAMCASH_QR_PATH)

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


DB_FILE = os.path.join(os.path.dirname(__file__), '../users.db')
