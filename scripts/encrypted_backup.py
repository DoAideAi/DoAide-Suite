"""Authenticated backup encryption with an independently stored Fernet key.

Commands never overwrite existing files. The key must be a private local file;
production key custody and the off-site destination are operator configuration.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from cryptography.fernet import Fernet
if __package__:
    from .backup import backup
else:
    from backup import backup


def private_write(path,content):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as handle:handle.write(content)


def cipher(key_file):
    path=Path(key_file)
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode)&0o077:
        raise ValueError('Encryption key must be a regular private file (mode 0600)')
    return Fernet(path.read_bytes().strip())


def encrypt_backup(database,output,key_file):
    encryption=cipher(key_file)
    with tempfile.TemporaryDirectory(prefix='doaide-encrypted-backup-') as directory:
        source=Path(directory)/'snapshot.db';result=backup(database,source)
        if source.stat().st_size>512*1024*1024:raise ValueError('Use a streaming backup system above 512 MiB')
        content=source.read_bytes();token=encryption.encrypt(content)
        if encryption.decrypt(token)!=content:raise ValueError('Encrypted backup verification failed')
        private_write(output,token)
    return {**result,'backup':str(output),'encryption':'Fernet authenticated encryption','encrypted_round_trip':'ok'}


def decrypt_backup(source,output,key_file):
    content=cipher(key_file).decrypt(Path(source).read_bytes())
    with tempfile.TemporaryDirectory(prefix='doaide-decrypt-check-') as directory:
        verified=Path(directory)/'restore.db';private_write(verified,content)
        with sqlite3.connect(verified) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Restored database failed validation')
    private_write(output,content)
    return {'restored':str(output),'integrity':'ok'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--key-file',required=True);parser.add_argument('--create-key',action='store_true');parser.add_argument('--database');parser.add_argument('--output');parser.add_argument('--decrypt')
    args=parser.parse_args()
    if args.create_key:
        private_write(args.key_file,Fernet.generate_key()+b'\n');print('Created private encryption key file')
    elif args.decrypt and args.output:print(json.dumps(decrypt_backup(args.decrypt,args.output,args.key_file),indent=2))
    elif args.database and args.output:print(json.dumps(encrypt_backup(args.database,args.output,args.key_file),indent=2))
    else:parser.error('Choose --create-key, --database with --output, or --decrypt with --output')
