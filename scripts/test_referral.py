import os
import sqlite3
import unittest
from dotenv import load_dotenv

# Load env variables
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

# Set dummy env vars if not present to prevent import errors in bot.py
os.environ.setdefault("TELEGRAM_TOKEN", "dummy_token")
os.environ.setdefault("TV_API_KEY", "dummy_tv")
os.environ.setdefault("NP_API_KEY", "dummy_np")
os.environ.setdefault("NP_IPN_SECRET", "dummy_secret")

import bot

class TestReferralSystem(unittest.TestCase):
    def setUp(self):
        # Override the database file to use a temporary database file for testing
        self.original_db = bot.DB_FILE
        self.test_db_file = os.path.join(os.path.dirname(__file__), 'test_users.db')
        bot.DB_FILE = self.test_db_file
        
        # Initialize the database schema
        bot.init_db()

    def tearDown(self):
        # Clean up the test database file
        bot.DB_FILE = self.original_db
        if os.path.exists(self.test_db_file):
            try:
                os.remove(self.test_db_file)
            except Exception as e:
                print(f"Error removing test db: {e}")

    def test_referral_reward_crypto(self):
        # 1. Create a referrer user
        referrer_id = 111111
        bot.create_user(referrer_id, username="referrer_user", first_name="Referrer")
        
        # Get referrer details to check referral code
        referrer = bot.get_user(referrer_id)
        ref_code = referrer['referral_code']
        self.assertEqual(ref_code, "ref111111")

        # 2. Create a referred user
        referred_id = 222222
        bot.create_user(referred_id, username="referred_user", first_name="Referred", referrer_code=ref_code)
        
        # Verify referred user has referrer_id set correctly
        referred = bot.get_user(referred_id)
        self.assertEqual(referred['referrer_id'], referrer_id)

        # 3. Create a pending crypto deposit
        conn = bot.get_db_connection()
        conn.execute(
            "INSERT INTO deposits (user_id, order_id, invoice_id, amount, price_currency, pay_currency, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (referred_id, "order_123", "invoice_123", 10.0, "usd", "BTC", "waiting")
        )
        conn.commit()
        
        # Get the deposit
        deposit = conn.execute("SELECT * FROM deposits WHERE order_id = 'order_123'").fetchone()
        deposit_id = deposit['id']
        conn.close()

        # 4. Mark deposit completed
        conn = bot.get_db_connection()
        conn.execute("UPDATE deposits SET status = 'completed' WHERE id = ?", (deposit_id,))
        conn.commit()
        conn.close()

        # Mock send_telegram_message_sync to prevent real HTTP calls during test
        original_send_msg = bot.send_telegram_message_sync
        sent_messages = []
        bot.send_telegram_message_sync = lambda chat_id, text: sent_messages.append((chat_id, text))

        try:
            # Trigger referral reward checking
            bot.check_and_reward_referrer(referred_id, 'crypto', deposit_id)

            # Check referrer balance
            updated_referrer = bot.get_user(referrer_id)
            self.assertEqual(updated_referrer['balance'], bot.REFERRAL_BONUS)
            self.assertEqual(updated_referrer['referral_credit_given'], bot.REFERRAL_BONUS)

            # Check deposit status marked as rewarded
            conn = bot.get_db_connection()
            updated_deposit = conn.execute("SELECT * FROM deposits WHERE id = ?", (deposit_id,)).fetchone()
            self.assertEqual(updated_deposit['referral_rewarded'], 1)
            conn.close()

            # Check notification was sent
            self.assertEqual(len(sent_messages), 1)
            self.assertEqual(sent_messages[0][0], referrer_id)
            self.assertIn("Referral Reward", sent_messages[0][1])

            # 5. Check Idempotency: try to reward again, balance should remain unchanged
            bot.check_and_reward_referrer(referred_id, 'crypto', deposit_id)
            updated_referrer_2 = bot.get_user(referrer_id)
            self.assertEqual(updated_referrer_2['balance'], bot.REFERRAL_BONUS)
        
        finally:
            bot.send_telegram_message_sync = original_send_msg

    def test_referral_reward_manual(self):
        # 1. Create a referrer user
        referrer_id = 333333
        bot.create_user(referrer_id, username="ref_m", first_name="ReferrerManual")
        referrer = bot.get_user(referrer_id)
        ref_code = referrer['referral_code']

        # 2. Create a referred user
        referred_id = 444444
        bot.create_user(referred_id, username="ref_d", first_name="ReferredManual", referrer_code=ref_code)

        # 3. Create a pending manual deposit
        conn = bot.get_db_connection()
        conn.execute(
            "INSERT INTO manual_deposits (user_id, amount, status) VALUES (?, ?, ?)",
            (referred_id, 25.0, "pending")
        )
        conn.commit()
        manual_dep = conn.execute("SELECT * FROM manual_deposits WHERE user_id = ?", (referred_id,)).fetchone()
        dep_id = manual_dep['id']
        conn.close()

        # Mock send_telegram_message_sync
        original_send_msg = bot.send_telegram_message_sync
        sent_messages = []
        bot.send_telegram_message_sync = lambda chat_id, text: sent_messages.append((chat_id, text))

        try:
            # 4. Approve manual deposit
            conn = bot.get_db_connection()
            conn.execute("UPDATE manual_deposits SET status = 'approved' WHERE id = ?", (dep_id,))
            conn.commit()
            conn.close()

            # Trigger referral reward checking
            bot.check_and_reward_referrer(referred_id, 'manual', dep_id)

            # Check referrer balance
            updated_referrer = bot.get_user(referrer_id)
            self.assertEqual(updated_referrer['balance'], bot.REFERRAL_BONUS)

            # Check manual deposit marked as rewarded
            conn = bot.get_db_connection()
            updated_dep = conn.execute("SELECT * FROM manual_deposits WHERE id = ?", (dep_id,)).fetchone()
            self.assertEqual(updated_dep['referral_rewarded'], 1)
            conn.close()

            # Check notification
            self.assertEqual(len(sent_messages), 1)
            self.assertEqual(sent_messages[0][0], referrer_id)
        
        finally:
            bot.send_telegram_message_sync = original_send_msg

if __name__ == '__main__':
    unittest.main()
