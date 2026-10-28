"""Preview or irreversibly erase one workspace's product data after policy review.

Account identities and memberships are retained; this is a workspace-data eraser,
not an account closure tool. Stop the API and worker before executing. Copies in
operator-managed backups must be expired separately under the approved policy.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import database


def erase(path,workspace,policy,execute=False,confirmation=None):
    if not policy.strip():raise ValueError('An approved retention / erasure policy reference is required')
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM workspaces WHERE id=?',(workspace,)).fetchone():raise ValueError('Workspace does not exist')
        records='SELECT record_id FROM record_workspaces WHERE workspace_id=?'
        documents='SELECT id FROM documents WHERE record_id IN ('+records+')'
        files='SELECT id FROM files WHERE record_id IN ('+records+')'
        entries='SELECT id FROM ledger WHERE workspace_id=?'
        counts={'records':db.execute('SELECT count(*) FROM record_workspaces WHERE workspace_id=?',(workspace,)).fetchone()[0],
                'files':db.execute('SELECT count(*) FROM files WHERE record_id IN ('+records+')',(workspace,)).fetchone()[0],
                'documents':db.execute('SELECT count(*) FROM documents WHERE record_id IN ('+records+')',(workspace,)).fetchone()[0],
                'financial_entries':db.execute('SELECT count(*) FROM ledger WHERE workspace_id=?',(workspace,)).fetchone()[0]}
        result={'workspace':workspace,'policy':policy,'counts':counts,'executed':False,'retained':'Account identities and memberships; separately managed backups'}
        if not execute:return result
        if confirmation!=workspace:raise ValueError('Execution requires the exact workspace ID as confirmation')
        if db.execute("SELECT 1 FROM jobs WHERE workspace_id=? AND state='running'",(workspace,)).fetchone():raise ValueError('Reconcile running jobs and stop the services before erasure')
        db.execute('PRAGMA secure_delete=ON')
        db.execute('DELETE FROM share_decisions WHERE share_id IN (SELECT id FROM shares WHERE document_id IN ('+documents+'))',(workspace,))
        db.execute('DELETE FROM shares WHERE document_id IN ('+documents+')',(workspace,))
        for table in ('public_document_blobs','document_blobs'):db.execute('DELETE FROM '+table+' WHERE document_id IN ('+documents+')',(workspace,))
        db.execute('DELETE FROM ledger_evidence WHERE entry_id IN ('+entries+')',(workspace,))
        for table in ('stock_adjustments','stock_movements','stock','billing_events','billing_accounts','jobs','idempotency','imports','invitations','ledger'):
            db.execute('DELETE FROM '+table+' WHERE workspace_id=?',(workspace,))
        db.execute('DELETE FROM file_controls WHERE file_id IN ('+files+')',(workspace,))
        for table in ('task_links','files','documents','operation_events','operation_items','operations','audit_events'):
            db.execute('DELETE FROM '+table+' WHERE record_id IN ('+records+')',(workspace,))
        ids=[row[0] for row in db.execute(records,(workspace,))]
        db.execute('DELETE FROM record_workspaces WHERE workspace_id=?',(workspace,))
        for identifier in ids:db.execute('DELETE FROM records WHERE id=?',(identifier,))
        db.execute("UPDATE workspaces SET name='Erased workspace' WHERE id=?",(workspace,))
        if db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Erasure would leave broken references; transaction rolled back')
        result['executed']=True
    # SQLite secure_delete scrubs freed cells; checkpoint WAL before compaction.
    with sqlite3.connect(path) as db:db.execute('PRAGMA wal_checkpoint(TRUNCATE)');db.execute('VACUUM')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database',required=True);parser.add_argument('--workspace',required=True);parser.add_argument('--policy',required=True);parser.add_argument('--execute',action='store_true');parser.add_argument('--confirm-workspace')
    args=parser.parse_args();print(json.dumps(erase(args.database,args.workspace,args.policy,args.execute,args.confirm_workspace),indent=2))
