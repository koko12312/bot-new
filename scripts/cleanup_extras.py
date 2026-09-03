import sqlite3
import os

db_path = r'C:\Users\dsagh\OneDrive\Desktop\html\bot new\users.db'
conn = sqlite3.connect(db_path)

print("--- Removing Extra Test Numbers ---")

# Numbers to remove
to_delete = ['5403270339', '6292441064']

for num in to_delete:
    print(f"Hiding number +{num} from user view.")
    conn.execute("UPDATE numbers SET status = 'deleted' WHERE number = ?", (num,))

conn.commit()
print("Cleanup complete.")
conn.close()
