import sqlite3
import psycopg2
import psycopg2.extras
import os

POSTGRES_URL = "postgresql://data_6an7_user:nIv8IjLw3FqsBr9DQngOKM0HqbbLxiBp@dpg-dbchbtss728c7395ja40-a.oregon-postgres.render.com/data_6an7"
SQLITE_DB = os.path.join(os.path.dirname(__file__), "users.db")

def migrate():
    print(f"Connecting to SQLite: {SQLITE_DB}")
    s_conn = sqlite3.connect(SQLITE_DB)
    s_conn.row_factory = sqlite3.Row
    s_cur = s_conn.cursor()

    print(f"Connecting to PostgreSQL...")
    p_conn = psycopg2.connect(POSTGRES_URL, sslmode="require")
    p_cur = p_conn.cursor()

    # 1. Create Tables in PostgreSQL
    print("Creating tables in PostgreSQL...")
    p_cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            balance DOUBLE PRECISION DEFAULT 0.0,
            username TEXT,
            referrer_id BIGINT,
            referral_code TEXT UNIQUE,
            referral_credit_given INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            language TEXT DEFAULT 'en',
            first_name TEXT
        );
    ''')

    p_cur.execute('''
        CREATE TABLE IF NOT EXISTS numbers (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
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
            code_received INTEGER DEFAULT 0,
            last_sms_id TEXT
        );
    ''')

    p_cur.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            order_id TEXT UNIQUE,
            invoice_id TEXT,
            amount DOUBLE PRECISION,
            price_currency TEXT,
            pay_currency TEXT,
            status TEXT,
            referral_rewarded INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        );
    ''')

    p_cur.execute('''
        CREATE TABLE IF NOT EXISTS manual_deposits (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount DOUBLE PRECISION,
            receipt_file_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            updated_at TEXT,
            receipt_file_type TEXT DEFAULT 'document',
            referral_rewarded INTEGER DEFAULT 0
        );
    ''')
    p_conn.commit()

    # 2. Migrate Users
    users = s_cur.execute("SELECT * FROM users").fetchall()
    print(f"Migrating {len(users)} users...")
    for u in users:
        p_cur.execute('''
            INSERT INTO users (user_id, balance, username, referrer_id, referral_code, referral_credit_given, created_at, updated_at, language, first_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                balance = EXCLUDED.balance,
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                language = EXCLUDED.language,
                updated_at = EXCLUDED.updated_at;
        ''', (
            u['user_id'], u['balance'], u['username'], u['referrer_id'],
            u['referral_code'], u['referral_credit_given'], u['created_at'],
            u['updated_at'], u['language'], u['first_name']
        ))
    p_conn.commit()

    # 3. Migrate Numbers
    numbers = s_cur.execute("SELECT * FROM numbers").fetchall()
    print(f"Migrating {len(numbers)} numbers...")
    for n in numbers:
        p_cur.execute('''
            INSERT INTO numbers (id, user_id, number, verification_id, service, status, created_at, last_checked, auto_renew, expires_at, provider, code_requested, code_received, last_sms_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                last_checked = EXCLUDED.last_checked,
                auto_renew = EXCLUDED.auto_renew,
                expires_at = EXCLUDED.expires_at,
                code_requested = EXCLUDED.code_requested,
                code_received = EXCLUDED.code_received,
                last_sms_id = EXCLUDED.last_sms_id;
        ''', (
            n['id'], n['user_id'], n['number'], n['verification_id'], n['service'],
            n['status'], n['created_at'], n['last_checked'], n['auto_renew'],
            n['expires_at'], n['provider'], n['code_requested'], n['code_received'],
            n['last_sms_id']
        ))
    p_cur.execute("SELECT setval('numbers_id_seq', (SELECT COALESCE(MAX(id), 1) FROM numbers));")
    p_conn.commit()

    # 4. Migrate Deposits
    deposits = s_cur.execute("SELECT * FROM deposits").fetchall()
    print(f"Migrating {len(deposits)} deposits...")
    for d in deposits:
        p_cur.execute('''
            INSERT INTO deposits (id, user_id, order_id, invoice_id, amount, price_currency, pay_currency, status, referral_rewarded, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING;
        ''', (
            d['id'], d['user_id'], d['order_id'], d['invoice_id'], d['amount'],
            d['price_currency'], d['pay_currency'], d['status'], d['referral_rewarded'],
            d['created_at'], d['updated_at']
        ))
    p_cur.execute("SELECT setval('deposits_id_seq', (SELECT COALESCE(MAX(id), 1) FROM deposits));")
    p_conn.commit()

    # 5. Migrate Manual Deposits
    manual_deposits = s_cur.execute("SELECT * FROM manual_deposits").fetchall()
    print(f"Migrating {len(manual_deposits)} manual deposits...")
    for m in manual_deposits:
        file_type = m['receipt_file_type'] if 'receipt_file_type' in m.keys() else 'document'
        p_cur.execute('''
            INSERT INTO manual_deposits (id, user_id, amount, receipt_file_id, status, created_at, updated_at, receipt_file_type, referral_rewarded)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING;
        ''', (
            m['id'], m['user_id'], m['amount'], m['receipt_file_id'], m['status'],
            m['created_at'], m['updated_at'], file_type, m['referral_rewarded']
        ))
    p_cur.execute("SELECT setval('manual_deposits_id_seq', (SELECT COALESCE(MAX(id), 1) FROM manual_deposits));")
    p_conn.commit()

    # Verify counts
    p_cur.execute("SELECT count(*) FROM users;")
    p_users = p_cur.fetchone()[0]
    p_cur.execute("SELECT count(*) FROM numbers;")
    p_numbers = p_cur.fetchone()[0]
    print(f"✅ Migration complete! Verified in PostgreSQL: {p_users} users, {p_numbers} numbers.")

    s_conn.close()
    p_conn.close()

if __name__ == "__main__":
    migrate()
