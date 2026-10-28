"""Report expired private file content; --apply purges bytes but retains audit manifests.
This command is intentionally separate from ordinary server startup and backups.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import database,initialize
from backend.operations import now,get_state,event


def retention(path=None,apply=False):
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        rows=db.execute('SELECT f.id,f.record_id,f.name,f.size,c.retain_until FROM files f JOIN file_controls c ON c.file_id=f.id WHERE c.retain_until<? AND c.deleted_at IS NULL',(now(),)).fetchall()
        report=[dict(r) for r in rows]
        if apply:
            for row in rows:
                db.execute("UPDATE files SET content=X'',extracted='',extraction_status='deleted-retention' WHERE id=?",(row['id'],))
                db.execute("UPDATE file_controls SET deleted_at=?,deletion_reason='Configured retention period expired' WHERE file_id=?",(now(),row['id']))
                record=dict(db.execute('SELECT * FROM records WHERE id=?',(row['record_id'],)).fetchone());state=get_state(db,record['id'])
                event(db,record,{'email':'retention-policy'},'file.retention-deletion',{'file_id':row['id'],'name':row['name'],'original_size':row['size']},state)
        return {'mode':'applied' if apply else 'preview','files':report}


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args();initialize();print(json.dumps(retention(apply=args.apply),indent=2))
