"""Consistent database+file backup and isolated restore validation.
Usage: uv run python scripts/backup.py [--database path] [--output path]
Never restores over the active database. An isolated copy is migrated and checked.
"""
import argparse
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import DEFAULT_PATH,initialize


def backup(source,output):
    source=Path(source);output=Path(output)
    if not source.is_file():raise SystemExit('Source database does not exist')
    if source.resolve()==output.resolve() or output.exists():raise SystemExit('Choose a new output file')
    output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with sqlite3.connect(f'file:{source}?mode=ro',uri=True) as src,sqlite3.connect(output) as dst:src.backup(dst)
    output.chmod(0o600)
    with sqlite3.connect(output) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        before={table:db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('users','records','audit_events')}
    with tempfile.TemporaryDirectory(prefix='doaide-restore-') as tmp:
        restored=Path(tmp)/'restored.db'
        with sqlite3.connect(output) as src,sqlite3.connect(restored) as dst:src.backup(dst)
        initialize(restored)
        with sqlite3.connect(restored) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
            after={table:db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in before}
            assert before==after
            files=db.execute('SELECT COUNT(*) FROM files').fetchone()[0]
    return {'backup':str(output),'integrity':'ok','isolated_restore':'ok','counts':after,'files':files}


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser();parser.add_argument('--database',default=os.environ.get('DOAIDE_DB_PATH',str(DEFAULT_PATH)));parser.add_argument('--output',default=str(DEFAULT_PATH.parent/'backups'/('doaide-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'.db')));args=parser.parse_args()
    print(json.dumps(backup(args.database,args.output),indent=2))
