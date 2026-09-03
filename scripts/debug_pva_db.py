import sqlite3
import os

db_path = r'C:\Users\dsagh\OneDrive\Desktop\html\bot new\users.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT * FROM numbers WHERE provider='pva' LIMIT 1").fetchone()
if row:
    print(f"ID: {row['id']}")
    print(f"Number: {row['number']}")
    print(f"Verification ID: {row['verification_id']}")
    print(f"Expires At: {row['expires_at']}")
else:
    print("No PVA numbers found.")
conn.close()
