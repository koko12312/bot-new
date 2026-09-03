import sqlite3
import os

db_path = r'C:\Users\dsagh\OneDrive\Desktop\html\bot new\users.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

print("--- Running Database Repair for Active Numbers ---")

# 1. Correct the provider for all TextVerified numbers (mistakenly marked as pva because of non-digits check)
conn.execute("UPDATE numbers SET provider = 'textverified' WHERE verification_id LIKE 'lr_%'")
print("Updated provider to 'textverified' for all 'lr_%' verification IDs.")

# 2. List of verified active TextVerified numbers
active_ids = [
    'lr_01KQGD9DY1Z0ACR71101TXNHV2',
    'lr_01KR1PX1K0JR1Z4T1E5TTRA7XP',
    'lr_01JK3RKHM7B9TFDRFZKH618K5N',
    'lr_01JK3S0TZ06DB99ZV88RH02SDC',
    'lr_01K3S0B7SF2YJC1NKXQ8F5KTGD',
    'lr_01K3S0WPQBCWWJ5Y32TF60HHRK',
    'lr_01JK3PCTQZ4MX32VKZSWWBDRB2',
    'lr_01KHGPV3MD1TGSTMVMNG4F02XV'
]

# Set their status to 'renewableActive'
for v_id in active_ids:
    conn.execute("UPDATE numbers SET status = 'renewableActive' WHERE verification_id = ?", (v_id,))
    print(f"Restored verification_id: {v_id} to status 'renewableActive'.")

conn.commit()

# Verify the changes
print("\n--- Verifying Active Numbers in DB ---")
active_nums = conn.execute("SELECT * FROM numbers WHERE status IN ('active', 'renewableActive')").fetchall()
for num in active_nums:
    print(f"User: {num['user_id']} | Num: {num['number']} | ID: {num['verification_id']} | Status: {num['status']} | Provider: {num['provider']}")

conn.close()
print("Repair completed successfully.")
