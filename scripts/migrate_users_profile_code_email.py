"""One-time migration: add profile_code and email to users table.
Run if you already have a users table: uv run python -m scripts.migrate_users_profile_code_email
Uses raw SQL for backfill so it works even if the User model has not been updated yet."""
import secrets
import string
from sqlalchemy import text

from app.database import engine


def _generate_profile_code():
    """Return an 8-char uppercase alphanumeric code."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def main():
    with engine.connect() as conn:
        for col_sql, col_name in (
            ("ADD COLUMN IF NOT EXISTS profile_code VARCHAR(12)", "profile_code"),
            ("ADD COLUMN IF NOT EXISTS email VARCHAR(255)", "email"),
        ):
            try:
                conn.execute(text(f"ALTER TABLE users {col_sql}"))
                conn.commit()
                print(f"Added column: {col_name}")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"Column {col_name} already exists, skipping.")
                else:
                    raise

        # Backfill profile_code for existing users (raw SQL – no User model needed)
        rows = conn.execute(text("SELECT id FROM users WHERE profile_code IS NULL")).fetchall()
        if not rows:
            print("No users need profile_code backfill.")
        else:
            used = {r[0] for r in conn.execute(text("SELECT profile_code FROM users WHERE profile_code IS NOT NULL")).fetchall()}
            for (user_id,) in rows:
                for _ in range(20):
                    code = _generate_profile_code()
                    if code not in used:
                        used.add(code)
                        conn.execute(text("UPDATE users SET profile_code = :code WHERE id = :id"), {"code": code, "id": user_id})
                        conn.commit()
                        break
                else:
                    raise RuntimeError("Could not generate unique profile_code")
            print(f"Backfilled profile_code for {len(rows)} user(s).")

    print("Migration done.")


if __name__ == "__main__":
    main()