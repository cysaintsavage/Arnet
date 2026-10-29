"""Command line tools:  python -m app.cli migrate | create-admin EMAIL | promote EMAIL"""
import getpass
import sys

from .core import EMAIL_RE
from .db import db, migrate
from .security import hash_password


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "migrate":
        done = migrate()
        print("Applied:", ", ".join(done) if done else "nothing (already up to date)")
        return 0
    if cmd in ("create-admin", "promote") and len(argv) == 2:
        migrate()
        email = argv[1].strip().lower()
        if not EMAIL_RE.match(email):
            print("That is not a valid email address.")
            return 1
        with db() as conn:
            row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if cmd == "promote":
                if not row:
                    print("No user with that email. Register first, or use create-admin.")
                    return 1
                conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (row["id"],))
                print(f"{email} is now an administrator.")
                return 0
            if row:
                print("That email is already registered. Use: promote", email)
                return 1
            pw = getpass.getpass("Password (min 8 characters): ")
            if len(pw) < 8 or pw != getpass.getpass("Repeat password: "):
                print("Passwords did not match or are too short.")
                return 1
            conn.execute("INSERT INTO users(email, password_hash, name, role, plan) VALUES (?, ?, 'Chris', 'admin', 'pro')",
                         (email, hash_password(pw)))
            print(f"Administrator {email} created.")
            return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
