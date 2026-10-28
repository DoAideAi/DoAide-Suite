"""Create an initial pilot owner locally; never reset an existing identity.

Production registration stays closed until verified SMTP is configured. Run
interactively inside the API container. Passwords are read with getpass and
never accepted as command-line arguments or printed.
"""
import argparse
from datetime import datetime, timezone
import getpass
import os
from pathlib import Path
import sys
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.db import initialize, database, password_hash
from backend.migrations import ensure_workspace


def bootstrap(path, email, password):
    email = email.strip().lower()
    if not 5 <= len(email) <= 254 or '@' not in email or email.startswith('@') or email.endswith('@') or any(c.isspace() for c in email):
        raise ValueError('Enter a valid email address')
    if not 12 <= len(password) <= 256:
        raise ValueError('Use a password between 12 and 256 characters')
    initialize(path)
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone():
            raise ValueError('Account already exists; use the normal password-recovery flow')
        owner = {'id': str(uuid4()), 'email': email, 'created_at': datetime.now(timezone.utc).isoformat()}
        db.execute('INSERT INTO users VALUES (?,?,?,?)', (owner['id'], email, password_hash(password), owner['created_at']))
        ensure_workspace(db, owner)
    return owner['id']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default=os.environ.get('DOAIDE_DB_PATH'))
    parser.add_argument('--email', required=True)
    args = parser.parse_args()
    if not args.database:parser.error('Set DOAIDE_DB_PATH or supply --database')
    if not sys.stdin.isatty():parser.error('Use an interactive terminal for hidden password entry')
    password = getpass.getpass('Initial owner password: ')
    if password != getpass.getpass('Confirm password: '):parser.error('Passwords did not match')
    print('Created owner workspace: ' + bootstrap(args.database, args.email, password))
