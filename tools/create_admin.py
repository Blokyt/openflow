"""Crée le premier compte administrateur (bootstrap production).

Usage : python tools/create_admin.py email@exemple.fr --name "Prénom" [--password ...]
Sans --password, le mot de passe est demandé de manière interactive.
"""
import argparse
import getpass
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.auth import MIN_PASSWORD_LENGTH, hash_password


def main() -> int:
    parser = argparse.ArgumentParser(description="Crée un compte administrateur OpenFlow")
    parser.add_argument("email")
    parser.add_argument("--name", default="")
    parser.add_argument("--password", default=None)
    parser.add_argument("--db", default="data/openflow.db")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Mot de passe : ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Mot de passe trop court ({MIN_PASSWORD_LENGTH} caractères minimum).", file=sys.stderr)
        return 1

    email = args.email.strip().lower()
    conn = sqlite3.connect(args.db)
    try:
        conn.execute(
            "INSERT INTO users (email, display_name, password_hash, is_admin, is_active, created_at) "
            "VALUES (?, ?, ?, 1, 1, ?)",
            (email, args.name or email, hash_password(password),
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        print(f"Un compte existe déjà pour {email}.", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(f"Administrateur {email} créé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
