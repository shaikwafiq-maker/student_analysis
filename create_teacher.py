"""Create (or reset) a teacher account.

Run this once from the project folder:
    python create_teacher.py            (password typing is hidden)
    python create_teacher.py --visible  (password is shown while you type)
"""
import getpass
import sys

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

from db import get_connection  # noqa: E402


def ask_password(prompt):
    if "--visible" in sys.argv:
        return input(prompt + " (visible): ")
    return getpass.getpass(prompt + " (typing is hidden): ")


def main():
    username = input("Teacher username (3-50 characters, no spaces): ").strip()
    if not 3 <= len(username) <= 50 or " " in username:
        print("Username must be 3-50 characters with no spaces.")
        return

    password = ask_password("Password (at least 8 characters)")
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return
    if password.lower() == username.lower():
        print("Password must be different from the username.")
        return
    if ask_password("Repeat password") != password:
        print("The two passwords do not match.")
        return

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash)",
            (username, generate_password_hash(password)),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    print(f"Teacher account '{username}' is ready. You can now log in.")


if __name__ == "__main__":
    main()
