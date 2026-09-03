import sqlite3
import os

db_path = r'C:\Users\dsagh\OneDrive\Desktop\html\bot new\users.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

print("--- Checking All PVA Numbers ---")
rows = conn.execute("SELECT * FROM numbers WHERE provider='pva'").fetchall()
if rows:
    for r in rows:
        print(f"User: {r['user_id']} | Num: {r['number']} | ID: {r['verification_id']} | Status: {r['status']} | AutoRenew: {r['auto_renew']} | Expires: {r['expires_at']}")
else:
    print("No PVA numbers found in database.")

print("\n--- Checking for Recently 'Deleted' or 'Expired' Numbers (Last 24h) ---")
# Since we don't have a 'deleted_at' column, we check status
deleted_rows = conn.execute("SELECT * FROM numbers WHERE status IN ('deleted', 'expired', 'canceled', 'refunded')").fetchall()
if deleted_rows:
    for r in deleted_rows:
        print(f"User: {r['user_id']} | Num: {r['number']} | Status: {r['status']} | Provider: {r['provider']}")
else:
    print("No inactive numbers found.")

conn.close()
