import sqlite3
import os

DB_FILE = 'bot new/users.db'

def check():
    if not os.path.exists(DB_FILE):
        print(f"Error: {DB_FILE} not found.")
        return
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"Total users in 'users' table: {user_count}")
    
    if user_count > 0:
        print("\nLast 5 users:")
        users = conn.execute("SELECT user_id, username, first_name, created_at FROM users ORDER BY created_at DESC LIMIT 5").fetchall()
        for u in users:
            print(f"ID: {u['user_id']} | Username: {u['username']} | Name: {u['first_name']} | Joined: {u['created_at']}")
            
    num_count = conn.execute("SELECT COUNT(*) FROM numbers").fetchone()[0]
    print(f"\nTotal records in 'numbers' table: {num_count}")
    
    conn.close()

if __name__ == '__main__':
    check()
