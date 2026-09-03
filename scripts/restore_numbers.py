import sqlite3
import os

db_path = r'C:\Users\dsagh\OneDrive\Desktop\html\bot new\users.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

print("--- Restoring Misidentified PVA Numbers ---")

# Numbers that were mistakenly marked as 'deleted' because they were treated as TextVerified
# but actually have a PVA-like ID (usually hex strings or different format than TV integers)
# Or simply any recently deleted number where the user says it should be there.

# First, find them
misidentified = conn.execute("SELECT * FROM numbers WHERE status = 'deleted' AND provider IN ('tv', 'textverified')").fetchall()

for num in misidentified:
    # TextVerified IDs are typically large integers or simple strings. 
    # If the ID doesn't look like a standard TV ID, or if we just want to be safe,
    # we restore it and set provider to 'pva' if it's the one the user just added.
    
    # Based on our recent test, the PVA ID looked like '6a31dd263dbe211cce1502ed' (Hex string)
    v_id = str(num['verification_id'])
    
    if len(v_id) > 15 or not v_id.isdigit(): 
        print(f"Restoring number +{num['number']} (ID: {v_id}) as PVA.")
        conn.execute("UPDATE numbers SET status = 'active', provider = 'pva' WHERE id = ?", (num['id'],))
    else:
        # If it's your specific number 9145018157 from the logs
        if num['number'] == '9145018157':
            print(f"Restoring specific number +{num['number']} as PVA.")
            conn.execute("UPDATE numbers SET status = 'active', provider = 'pva' WHERE id = ?", (num['id'],))

conn.commit()
print("Restoration complete.")
conn.close()
