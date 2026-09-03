import sqlite3
import os

db_path = r'C:\Users\dsagh\OneDrive\Desktop\html\bot new\users.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM numbers WHERE provider='pva'").fetchall()
if rows:
    for r in rows:
        print(f"Number: {r['number']} | ID: {r['verification_id']} | Status: {r['status']}")
else:
    print("No recorded PVA numbers found in the database.")
conn.close()
