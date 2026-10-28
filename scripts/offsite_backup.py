"""Pull a consistent snapshot over SSH, encrypt and restore-check it off-site.

Run this on a separate backup host. The encryption key never goes to the app
server. SSH uses known_hosts and an existing restricted key; no password prompt.
No backup is overwritten or expired automatically.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
if __package__:
    from .encrypted_backup import cipher, encrypt_backup, decrypt_backup, private_write
else:
    from encrypted_backup import cipher, encrypt_backup, decrypt_backup, private_write

MAX_SNAPSHOT = 512 * 1024 * 1024
REMOTE_SNAPSHOT = '''import os, pathlib, sys, tempfile
from scripts.backup import backup
with tempfile.TemporaryDirectory(prefix="doaide-offsite-") as directory:
    path = pathlib.Path(directory) / "snapshot.db"
    backup(os.environ["DOAIDE_DB_PATH"], path)
    if path.stat().st_size > 512 * 1024 * 1024:
        raise SystemExit("Use a streaming backup system above 512 MiB")
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            sys.stdout.buffer.write(chunk)
'''


def pull_backup(host, directory, project, key_file, output):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.@-]*', host) or host in ('localhost', '127.0.0.1'):
        raise ValueError('Use a configured remote SSH host or user@host')
    if not directory.startswith('/') or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', project):
        raise ValueError('Use an absolute release directory and a valid Compose project name')
    cipher(key_file)  # Validate private key custody before reading any data.
    output = Path(output)
    receipt_path = output.with_suffix(output.suffix + '.receipt.json')
    if output.exists() or receipt_path.exists():
        raise ValueError('Choose a new backup output name')
    arguments = ['docker', 'compose', '--project-directory', directory, '-p', project,
                 '--env-file', str(Path(directory) / 'release.env'), '-f', str(Path(directory) / 'compose.production.yml'),
                 'exec', '-T', 'app', 'python', '-c', REMOTE_SNAPSHOT]
    with tempfile.TemporaryDirectory(prefix='doaide-offsite-') as temporary:
        source = Path(temporary) / 'snapshot.db'
        with source.open('xb') as stream:
            source.chmod(0o600)
            try:
                result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                                         '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15',
                                         '-o', 'ServerAliveCountMax=2', host, shlex.join(arguments)],
                                        stdout=stream, stderr=subprocess.PIPE, timeout=180)
            except subprocess.TimeoutExpired as exc:
                raise ValueError('Snapshot transfer timed out; no verified receipt was written') from exc
        if result.returncode or source.stat().st_size > MAX_SNAPSHOT:
            raise ValueError('Remote snapshot failed; inspect server privately')
        summary = encrypt_backup(source, output, key_file)
        restored = Path(temporary) / 'verified.db'
        decrypt_backup(output, restored, key_file)
        receipt = {'verified_at': datetime.now(timezone.utc).isoformat(), 'source_host': host,
                   'offsite_verified': True, 'restore_integrity': 'ok', 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                   'encrypted_bytes': output.stat().st_size, 'counts': summary['counts'], 'files': summary['files']}
        private_write(receipt_path, (json.dumps(receipt, indent=2) + '\n').encode())
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--project', default='doaide-suite')
    parser.add_argument('--key-file', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(pull_backup(args.host, args.directory, args.project, args.key_file, args.output), indent=2))
