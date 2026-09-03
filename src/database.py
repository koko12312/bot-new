import sqlite3
import datetime
import logging
import requests
import textverified
from config import *
from providers import pva_client

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


