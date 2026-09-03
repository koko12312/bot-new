import sqlite3
import os

def check(db_path):
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found.")
        return
    
    conn = sqlite3.connect(db_path)
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"Total users in '{db_path}': {user_count}")
    conn.close()

if __name__ == '__main__':
    check('users.db')
    check('bot new/users.db')
