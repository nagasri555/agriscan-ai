import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('analysis.db')
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
    print("✅ 'role' column added to users table.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("⚠️ 'role' column already exists.")
    else:
        raise

# Optional: create an admin user if not exists
cursor.execute("SELECT * FROM users WHERE email = ?", ('admin@example.com',))
if not cursor.fetchone():
    cursor.execute('''
        INSERT INTO users (username, email, password_hash, role)
        VALUES (?, ?, ?, ?)
    ''', ('admin', 'admin@example.com', generate_password_hash('admin123'), 'admin'))
    print("✅ Admin user created.")
else:
    print("✅ Admin user already exists.")

conn.commit()
conn.close()
