import sqlite3
import os

db_path = r'C:\Users\dsagh\OneDrive\Desktop\html\bot new\users.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

tables = ['users', 'numbers', 'deposits', 'transactions', 'manual_deposits']
for table in tables:
    cursor.execute(f"PRAGMA table_info({table})")
    columns = cursor.fetchall()
    print(f"Table: {table}")
    for col in columns:
        print(f"  {col}")
conn.close()
