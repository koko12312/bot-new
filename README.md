# Telegram WhatsApp Rental Bot 📱💼

A professional, commercial-ready Telegram Bot service for long-term WhatsApp number rentals. Built with Python, this bot automates the process of purchasing and managing WhatsApp numbers through multiple SMS providers (TextVerified and PVADeals) and seamlessly handles cryptocurrency deposits via NowPayments.

## 🌟 Key Features

- **Automated WhatsApp Rentals:** Users can rent long-term (30-day) renewable WhatsApp numbers.
- **Dual SMS Providers:** Seamlessly integrates with **TextVerified** (Premium) and **PVADeals** (Basic) to offer tiered pricing and reliable fallback options.
- **Crypto & Manual Payments:** Fully automated cryptocurrency deposits using **NowPayments** Webhooks, alongside a manual **ShamCash** deposit flow with PDF receipt uploads for admin approval.
- **Bilingual UI (English & Arabic):** Deep localization out-of-the-box. Users are greeted in their preferred language, with dynamic time-remaining labels and localized buttons.
- **Auto-Renewal & Subscription Management:** Smart background workers run periodically to sync expiry dates, process auto-renewals, and allow users to toggle auto-renew or cancel active subscriptions.
- **High-Performance Architecture:** Employs multi-threaded async operations (`asyncio.to_thread`) to offload network requests and database writes, keeping the Telegram UI lightning-fast and lag-free.
- **Referral Program:** Built-in referral system to reward users when they invite friends who make their first deposit.
- **Admin Dashboard:** In-app tools for administrators to manage users, view all balances, process manual ShamCash receipts, and perform ad-hoc credit adjustments.

## 🛠️ Tech Stack

- **Language:** Python 3.x
- **Frameworks:** `python-telegram-bot` (v20+), `Flask` (for webhooks)
- **Database:** SQLite3 (`users.db`) with thread-safe connections.
- **APIs:** 
  - `TextVerified` (Official library for SMS/rentals)
  - `PVADeals` (Custom API Client for secondary SMS/rentals)
  - `NowPayments` (Cryptocurrency gateways & webhooks)

## 🚀 Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/whatsapp-rental-bot.git
cd whatsapp-rental-bot
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy the provided `.env.example` file and fill in your actual credentials.
```bash
cp .env.example .env
```
Make sure to fill out your `TELEGRAM_TOKEN`, API Keys (`TEXTVERIFIED_API_KEY`, `PVADEALS_API_KEY`, `NOWPAYMENTS_API_KEY`), and `ADMIN_ID`.

### 4. Run the Bot
```bash
python bot.py
```
*Note: The bot will automatically create the required SQLite tables (`users.db`) on the first run.*

## 🏗️ Architecture Highlights

- **Webhook & Polling:** The bot runs Telegram updates via polling, while a dedicated background `Flask` thread listens for incoming NowPayments IPN (Instant Payment Notification) webhooks.
- **Thread-Safe SQLite:** Configured with `check_same_thread=False` to safely handle concurrent reads/writes from background workers, the Flask server, and Telegram async handlers.
- **Null-Safe Formatting:** Designed to gracefully handle missing optional data (like missing usernames or incomplete profiles) using safe defaults in Python and `COALESCE` in SQL.

## 🛡️ License

MIT License. See `LICENSE` for details.

