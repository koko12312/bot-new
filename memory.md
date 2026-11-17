# Project Memory: Telegram WhatsApp Rental Bot

This file preserves the architectural decisions, database schema, and implemented features for the production-ready Telegram bot. It serves as the unified source of truth for project history and current state.

## 1. Project Goal
Transform a prototype bot into a professional, commercial-ready service for long-term WhatsApp rentals using **TextVerified**, **PVADeals**, and **NowPayments**.

## 2. Technical Stack
- **Language:** Python 3.x
- **Frameworks:** `python-telegram-bot` (with `job-queue` for background tasks), `Flask` (for webhooks)
- **Database:** SQLite (`users.db`)
- **APIs:** 
  - **TextVerified (Premium/ممتاز):** Official Python library used for rentals and SMS.
  - **PVADeals (Basic):** Custom API client for secondary WhatsApp rentals and SMS.
  - **NowPayments:** Used for automatic cryptocurrency deposits.
- **Architecture:** Multi-threaded asynchronous design using `asyncio.to_thread` and dedicated background workers to ensure lightning-fast UI responsiveness.

## 3. Core Features & Implementation Details

### **User Onboarding & Identification**
- **Self-Healing Sync:** Automatically captures and updates Usernames and **First Names** on every interaction to ensure accurate record-keeping.
- **Localized Greetings:** Intelligent greeting that prioritizes names but falls back to localized strings (**"there"** for EN, **"يا صديقي"** for AR) gracefully.

### **UI & UX Design**
- **High-Performance UI:** All database and network operations are offloaded to background threads, resulting in instant button response times.
- **Provider Selection:** Users choose between **ممتاز (Premium)** and **Basic (PVADeals)** with live price formatting.
- **Provider Feature Parity Mandate:** EVERY feature, safety check, or UI adjustment applied to one provider (e.g., TextVerified) MUST be automatically and identically implemented for all other providers (e.g., PVADeals). Fragmentation is forbidden; the user experience must be uniform regardless of the backend source.
- **Deep Localization:** Centralized `STRINGS` dictionary handles full localization in **English** and **Arabic**. This includes menus, system alerts, payment instructions, and dynamic time-remaining labels (e.g., "days left", "Expired").
- **Responsive Navigation:** "Profile", "My Numbers", and "Admin" menus use `edit_message_text` for seamless, lag-free navigation without message spam.

### **Rental & Subscription System**
- **Long-Term Rentals:** 30-day renewable cycles managed via the Reservations API.
- **Smart Auto-Renewal:** Background worker (`sync_and_renew_worker`) runs every 15 minutes to sync expiry dates and process payments automatically.
- **Subscription Management:** Users can toggle auto-renew, cancel subscriptions, or request refunds directly from the "My Numbers" menu.

### **Database & System Integrity**
- **Thread-Safe SQLite:** Connections are initialized with `check_same_thread=False` to prevent `ProgrammingError` when accessed from the bot's background worker threads and asynchronous handlers.
- **Absolute Path Resolution:** The bot uses `os.path.abspath` and `os.path.dirname(__file__)` for all critical resources (Database, `.env`, and QR code images). This ensures operational consistency regardless of the launch directory.
- **NULL-Safe Formatting:** User profiles and lists use `COALESCE` in SQL and safe defaults in Python to prevent crashes when optional data (like `created_at` or `username`) is missing.

### **Financial Integrity**
- **NowPayments Integration:** Fully automated cryptocurrency deposits via webhooks.
- **Automated ShamCash:** Users receive a **QR code** and **Copyable ID**; admins manage a pending queue for PDF receipt approval.
- **Dynamic Configuration:** All prices (`SERVICE_PRICE`, `PVADEALS_PRICE`), referral bonuses, and SMS settings are managed via `.env`.

### **Administrative Controls**
- **Enhanced Admin Dashboard:**
  - **All Users List:** Interactive, paginated list prioritizing usernames and sorted by **Recently Joined**.
  - **Comprehensive Visibility:** Fixed sorting and retrieval logic ensures every user in the database is accessible, even those with missing registration dates.
  - **Deep Management:** Clicking a user opens a profile with one-tap tools for credit adjustment and number linking.

## 4. Database Schema

### `users` table
- `user_id`, `username`, `first_name`, `balance`, `referrer_id`, `referral_code`, `referral_credit_given`, `language` (en/ar), `created_at`, `updated_at`

### `numbers` table
- `id`, `user_id`, `number`, `verification_id`, `service`, `status`, `auto_renew`, `expires_at`, `created_at`, `last_checked`, `provider` (textverified/pva), `code_requested`, `code_received`

### `manual_deposits` table
- `id`, `user_id`, `amount`, `receipt_file_id`, `status` (pending/approved/declined), `referral_rewarded`, `created_at`, `updated_at`, `receipt_file_type` (document/photo)

## 5. Interaction Protocol
- **STRICT Explain & Approve:** The agent MUST explain any proposed code change and wait for explicit user approval (**"yes"** or **"proceed"**) before implementation. This is a foundational mandate that overrides default CLI autonomy.
- **Context Integrity:** This `memory.md` is the primary source of truth; all changes must be documented here upon completion.

## 6. Portfolio & Web Showcase
- **Standalone AI Developer Portfolio:** Built a high-end web portfolio (`/portfolio` directory) to showcase the bot simulator, GitHub, and LinkedIn (Akram Saltoun). 
- **Vercel Deployment:** Live at `https://telegram-bot-portfolio-beta.vercel.app`.
- **Lusion-Style Reactivity:** Implemented industry-standard reactive physics including:
  - 1:1 zero-latency hardware cursor dot.
  - SVG Gooey blob filter (`<feColorMatrix>`) for liquid WebGL-style cursor trails using velocity-based spring physics.
  - Magnetic interactive elements (buttons/links physically pull toward the cursor).
  - `@studio-freight/lenis` for buttery smooth frictionless scrolling.
- **Exceptions:** Added `.playwright-mcp/` to `.gitignore` to prevent syncing browser snapshot artifacts to GitHub.

## 7. Python 3.10 Environment & Manual Linking Fix
- **Python 3.10 Incompatibility Resolution:**
  - Resolved `AttributeError: module 'datetime' has no attribute 'UTC'` when manually adding/linking numbers or computing timestamps on Python 3.10.
  - Replaced all usages of `datetime.UTC` across `src/database.py`, `src/handlers.py`, and `src/providers.py` with standard `datetime.timezone.utc`.
  - Verified manual number linking (`add_number_record`), persistent volume file synchronization, and clean container restart.

## 8. ShamCash Multi-Format Payment Proofs
- **Any-Proof Support (Photos, Screenshots, Any Document):**
  - Updated Telegram handler registration in `src/main.py` from `filters.Document.PDF` to `filters.PHOTO | filters.Document.ALL`.
  - Updated `handle_document` in `src/handlers.py` to seamlessly accept `update.message.photo` (highest-res photo object) and `update.message.document` (images, PDFs, text, etc.), storing `receipt_file_type` ('photo' or 'document') into `manual_deposits`.
  - Updated admin pending request viewer in `src/handlers.py` to auto-detect file type and dispatch via `send_photo` or `send_document` with mutual fallback, allowing admin to view inline images or attached files directly on Telegram.
  - Updated English and Arabic UI prompt strings in `src/config.py` to state that photos, screenshots, and documents are all accepted.
  - Deployed to GitHub `origin/main` (commit `9686fc1`), synced live to JustRunMy.App persistent volume, and verified clean container restart and webhook health.



- **Configuration:** Updated [`settings.json`](file:///C:/Users/dsagh/AppData/Roaming/Code/User/settings.json).



# Memory Update - Gmail MCP Connection Configured & Verified

- Date: 2026-10-08
- Configuration: Global MCP config (~/.gemini/config/mcp_config.json) updated with custom Gmail MCP server (gmail-custom).
- Server Script: C:\Users\dsagh\.gemini\config\gmail_mcp.py using FastMCP (mcp<2) and Python IMAP over SSL.
- Capabilities: Native MCP tools list_emails and 
ead_email supporting direct inbox reading via App Passwords for both krambek321@gmail.com and jakefar487@gmail.com.
- Status: Verified and functioning. Successfully retrieved recent messages directly through the IDE's MCP interface.

- Account added: sfast718@gmail.com added to C:\Users\dsagh\.gemini\config\gmail_mcp.py with configured App Password.


## MANDATORY WORKFLOW RULE: EXPLICIT DISQUALIFICATION REPORTING (PERMANENT)
- **EXPLICIT DISQUALIFICATION CALLOUT:** Whenever ANY screener or survey is disqualified across ANY browser, you MUST explicitly state **"DISQUALIFIED"** right away.
- **INCLUDE THE KNOCKOUT QUESTION & ANSWER:** Specify the exact question number and topic that caused the disqualification (e.g. *"Disqualified at Question 7 on Industry choice: Selected 'B2B software or technology company'"*). Never gloss over or leave disqualifications ambiguous.


## 8. Survey Automation & Centralized Cross-Reference (Unified Knowledge Base)
- **Centralized Cross-Reference Repository:** Fully compiled and maintained at [c:\Users\dsagh\OneDrive\Desktop\html\surveys\survey_cross_reference.md](file:///c:/Users/dsagh/OneDrive/Desktop/html/surveys/survey_cross_reference.md).
- **Comprehensive Historical Scope:** Consolidates all research studies completed since the project inception across all profiles (Nicholas Smith, Tereka Jordan, David, Matthew, Jake Far).
- **High-Value Focus Groups & Submissions Logged:**
  - Creators/Inventors/Artists P260122I-K () - Nicholas Smith (PRC Market Research, completed & submitted)
  - Fast Food Choices P260131D-A () - Nicholas Smith (PRC Market Research, completed & submitted)
  - Food & Dining Options P260135X-A () - Nicholas Smith (PRC Market Research, completed & submitted)
  - Grocery Shopping Options P261103I-A () - Nicholas Smith (PRC Market Research, completed & submitted)
  - Credit Cards Study P260136F-K () - Nicholas Smith (PRC Market Research, completed & submitted)
  - College Football / FCS Sports Video Study () - Nicholas Smith (User Interviews, completed)
  - Windows Enterprise Outlook Users () - Nicholas Smith (User Interviews, completed)
  - GLP-1 Grocery Shopping Mission () - Nicholas Smith (Respondent, completed)
  - Male Deodorant Product Test - Nicholas Smith (Dscout / Opinions for Cash, submitted)
- **Active Dashboard Studies Locked (Never Retake):**
  - Telecom Expense Management (TEM) ( Mac/Windows) - David (Port 56596)
  - Device Form Factors ( Mac/Windows) - David (Port 56596)
  - Disability Insurance Background ( Voice | Screen) - Tereka Jordan (Port 53247, Card 9)
  - Mobile Voice | Screen ( QR Code) - Tereka Jordan (Port 53247)
  - Foundational AI Healthcare Models () - David (Port 56596)
- **Learned Knockout Defenses:**
  - Small Business Leadership (Q7 Industry): Avoid B2B tech; pivot to Home Services/Trades.
  - Career Goals (Q2 Licensing): Avoid Real Estate Agent; pivot to RN or Teaching.
  - Automotive Ecosystem (Q1): Avoid Tech vendors; pivot to Dealership or Repair shop.
  - Organization Offering (Q1): Avoid pure SaaS; pivot to Professional Services.
  - Respondent Tech & You (Q2): Requires age 27+ or specialized non-generalist roles.
  - Focus Forward Dscout Panel: Requires current verified new luxury vehicle ownership.
  - Ezio / Focus Forward links: Block repeated fingerprint invitations.
- **Trap Directory:** Defense against honeypots (Chanticleer Card, Central Prairie State University, Paystar, HyperLogic Cloud, impossible sports).

## 9. US Number Country Code Formatting, TextVerified Tags & PVADeals Diagnosis (2026-11-17)
- **PVADeals Purchase Diagnosis (HTTP 402):**
  - Identified root cause of PVA rental failures: account balance is $5.46 while 30-day WhatsApp LTR rental is $6.25, triggering HTTP 402 Payment Required.
  - Added explicit HTTP 402 logging in `PVADealsClient.purchase_ltr` to clearly notify when provider funds need topping up.
- **US Country Code Formatting (+1 Normalization):**
  - Added helper `normalize_us_e164(phone)` in `src/providers.py` ensuring all US numbers are normalized to standard 11 digits `1XXXXXXXXXX`.
  - Updated `process_rent` and `admin_add_number` in `src/handlers.py` so newly rented numbers always include the `1` prefix.
  - Guarded `add_number_record` in `src/database.py` with automatic 10-to-11 digit conversion.
  - Executed database migration on Neon PostgreSQL updating all existing 10-digit numbers to standard E.164 (`1XXXXXXXXXX`), fixing display across all bot menus so numbers always start with `+1`.
  - Fixed `PGCursor.execute` to prevent psycopg2 tuple index errors on SQL queries containing literal `%` characters when `params` is None.
- **TextVerified Tags Implementation:**
  - Discovered that TextVerified UI specifically displays the `tags` array rather than `userNotes`.
  - Created `tag_reservation_tv(reservation_id, user_tag)` in `src/providers.py` that sends both `tags: [user_tag]` and `userNotes: user_tag` via `POST /api/pub/v2/reservations/rental/renewable/{id}`.
  - Successfully tagged all 5 currently active TextVerified rentals in the database with their respective owners' Telegram usernames. Future rentals automatically inherit this tagging.
