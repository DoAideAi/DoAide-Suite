"""Additive, restart-safe upgrades. Back up with SQLite's backup API, including files."""
import json


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0]>4:
        raise RuntimeError('This database requires a newer DoAide release')
    db.executescript("""
    CREATE TABLE IF NOT EXISTS workspaces (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
        currency TEXT NOT NULL DEFAULT 'INR', created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS memberships (
        workspace_id TEXT NOT NULL REFERENCES workspaces(id), user_id TEXT NOT NULL REFERENCES users(id),
        role TEXT NOT NULL CHECK(role IN ('owner','operator','reviewer','viewer')),
        PRIMARY KEY(workspace_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS invitations (
        token_hash TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        email TEXT NOT NULL, role TEXT NOT NULL, expires_at INTEGER NOT NULL, used_at TEXT
    );
    CREATE TABLE IF NOT EXISTS record_workspaces (
        record_id TEXT PRIMARY KEY REFERENCES records(id), workspace_id TEXT NOT NULL REFERENCES workspaces(id)
    );
    CREATE INDEX IF NOT EXISTS record_workspace_lookup ON record_workspaces(workspace_id,record_id);
    CREATE TABLE IF NOT EXISTS operations (
        record_id TEXT PRIMARY KEY REFERENCES records(id), revision INTEGER NOT NULL DEFAULT 1,
        stage TEXT NOT NULL DEFAULT 'draft', data TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS operation_items (
        id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(id), kind TEXT NOT NULL,
        data TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id), updated_by TEXT NOT NULL REFERENCES users(id),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS operation_items_record ON operation_items(record_id,kind);
    CREATE TABLE IF NOT EXISTS operation_events (
        id INTEGER PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(id), actor TEXT NOT NULL,
        action TEXT NOT NULL, revision INTEGER NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS files (
        id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(id), name TEXT NOT NULL,
        mime TEXT NOT NULL, size INTEGER NOT NULL, checksum TEXT NOT NULL, content BLOB NOT NULL,
        extracted TEXT NOT NULL, extraction_status TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS files_record ON files(record_id);
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(id), kind TEXT NOT NULL,
        number TEXT NOT NULL UNIQUE, record_version INTEGER NOT NULL, revision INTEGER NOT NULL,
        snapshot TEXT NOT NULL, checksum TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS shares (
        id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, document_id TEXT NOT NULL REFERENCES documents(id),
        recipient TEXT NOT NULL, purpose TEXT NOT NULL, expires_at INTEGER NOT NULL,
        revoked_at TEXT, accepted_at TEXT, accepted_name TEXT, accepted_email TEXT
    );
    CREATE TABLE IF NOT EXISTS ledger (
        id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id), record_id TEXT NOT NULL REFERENCES records(id),
        kind TEXT NOT NULL CHECK(kind IN ('payment','credit','refund','charge')),
        amount INTEGER NOT NULL CHECK(amount > 0), reference TEXT NOT NULL, currency TEXT NOT NULL,
        date TEXT NOT NULL, note TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(workspace_id,reference)
    );
    CREATE TABLE IF NOT EXISTS stock (
        workspace_id TEXT NOT NULL REFERENCES workspaces(id), sku TEXT NOT NULL, name TEXT NOT NULL,
        unit TEXT NOT NULL, quantity TEXT NOT NULL, held TEXT NOT NULL DEFAULT '0',
        data TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL, PRIMARY KEY(workspace_id,sku)
    );
    CREATE TABLE IF NOT EXISTS stock_movements (
        id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, record_id TEXT NOT NULL REFERENCES records(id),
        sku TEXT NOT NULL, quantity TEXT NOT NULL, kind TEXT NOT NULL, reference TEXT NOT NULL,
        actor TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(workspace_id,reference,sku)
    );
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id), record_id TEXT REFERENCES records(id),
        kind TEXT NOT NULL, dedupe_key TEXT NOT NULL, data TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
        due_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, lease_until TEXT, last_error TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(workspace_id,dedupe_key)
    );
    CREATE INDEX IF NOT EXISTS jobs_due ON jobs(state,due_at);
    CREATE TABLE IF NOT EXISTS webhook_events (
        provider TEXT NOT NULL, event_id TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(provider,event_id)
    );
    CREATE TABLE IF NOT EXISTS imports (
        id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, mapping TEXT NOT NULL, rows TEXT NOT NULL,
        state TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS idempotency (
        workspace_id TEXT NOT NULL, key TEXT NOT NULL, request_hash TEXT NOT NULL,
        response TEXT NOT NULL, PRIMARY KEY(workspace_id,key)
    );
    CREATE TABLE IF NOT EXISTS task_links (
        id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, record_id TEXT NOT NULL REFERENCES records(id),
        item_id TEXT NOT NULL REFERENCES operation_items(id), recipient TEXT NOT NULL,
        expires_at INTEGER NOT NULL, created_at TEXT NOT NULL, closed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS share_decisions (
        share_id TEXT PRIMARY KEY REFERENCES shares(id), decision TEXT NOT NULL, comments TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS file_controls (
        file_id TEXT PRIMARY KEY REFERENCES files(id), scan_status TEXT NOT NULL,
        retain_until TEXT, deleted_at TEXT, deletion_reason TEXT
    );
    CREATE TABLE IF NOT EXISTS document_blobs (
        document_id TEXT PRIMARY KEY REFERENCES documents(id), pdf BLOB NOT NULL, checksum TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS user_flags (
        user_id TEXT PRIMARY KEY REFERENCES users(id), email_verified_at TEXT
    );
    CREATE TABLE IF NOT EXISTS auth_tokens (
        token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), purpose TEXT NOT NULL,
        expires_at INTEGER NOT NULL, used_at TEXT
    );
    CREATE TABLE IF NOT EXISTS public_document_blobs (
        document_id TEXT PRIMARY KEY REFERENCES documents(id), pdf BLOB NOT NULL, checksum TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS billing_accounts (
        workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id), customer_id TEXT UNIQUE,
        subscription_id TEXT, plan TEXT, status TEXT NOT NULL DEFAULT 'unsubscribed',
        period_end INTEGER, synced_at TEXT, checkout_job TEXT REFERENCES jobs(id)
    );
    CREATE TABLE IF NOT EXISTS billing_events (
        id INTEGER PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        action TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS stock_adjustments (
        id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        record_id TEXT NOT NULL REFERENCES records(id), sku TEXT NOT NULL, reference TEXT NOT NULL,
        delta TEXT NOT NULL, before_quantity TEXT NOT NULL, after_quantity TEXT NOT NULL,
        before_held TEXT NOT NULL, after_held TEXT NOT NULL, reason TEXT NOT NULL,
        file_id TEXT NOT NULL REFERENCES files(id), actor TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(workspace_id,reference)
    );
    CREATE TABLE IF NOT EXISTS runtime_status (
        name TEXT PRIMARY KEY, last_seen TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS member_access (
        workspace_id TEXT NOT NULL REFERENCES workspaces(id), user_id TEXT NOT NULL REFERENCES users(id),
        fees_mode TEXT NOT NULL CHECK(fees_mode IN ('financial','academic')),
        PRIMARY KEY(workspace_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS ledger_evidence (
        entry_id TEXT PRIMARY KEY REFERENCES ledger(id), method TEXT NOT NULL, file_id TEXT REFERENCES files(id)
    );
    CREATE TABLE IF NOT EXISTS request_limits (
        bucket TEXT PRIMARY KEY, window INTEGER NOT NULL, count INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ledger_record ON ledger(record_id,created_at);
    CREATE INDEX IF NOT EXISTS jobs_workspace_created ON jobs(workspace_id,created_at);
    CREATE INDEX IF NOT EXISTS documents_record ON documents(record_id,created_at);
    CREATE INDEX IF NOT EXISTS operation_events_record ON operation_events(record_id,id);
    """)
    for user in db.execute("SELECT * FROM users").fetchall():
        ensure_workspace(db, dict(user))
    db.execute("INSERT OR IGNORE INTO record_workspaces SELECT id, user_id FROM records")
    db.execute("PRAGMA user_version = 4")


def ensure_workspace(db, user):
    created=db.execute("INSERT OR IGNORE INTO workspaces(id,name,created_at) VALUES (?,?,?)",
               (user['id'], user['email'].split('@')[0] + "'s workspace", user.get('created_at', ''))).rowcount
    # Migration/restart must never restore a deliberately revoked original owner.
    if created:db.execute("INSERT INTO memberships VALUES (?,?,'owner')", (user['id'], user['id']))


def record_access(db, record_id, user):
    from fastapi import HTTPException
    row = db.execute("SELECT r.* FROM records r JOIN record_workspaces w ON w.record_id=r.id WHERE r.id=? AND w.workspace_id=?",
                     (record_id, user['workspace_id'])).fetchone()
    if not row:
        raise HTTPException(404, 'Record not found')
    if row['product']=='fees' and user.get('fees_access')=='academic':
        raise HTTPException(403, 'Academic access excludes fee agreements, receipts and financial evidence; use the enrollment register')
    return dict(row)


def permit(user, *roles):
    from fastapi import HTTPException
    if user['role'] not in roles:
        raise HTTPException(403, 'Your workspace role cannot perform this action')


def invalidate(db, record_id):
    """New source revisions invalidate outstanding acceptance links, never past evidence."""
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).isoformat()
    db.execute("UPDATE shares SET revoked_at=? WHERE document_id IN (SELECT id FROM documents WHERE record_id=?) AND accepted_at IS NULL AND revoked_at IS NULL", (timestamp, record_id))
    row = db.execute("SELECT data FROM operations WHERE record_id=?", (record_id,)).fetchone()
    if row:
        data = json.loads(row['data'])
        for key in ('approved_document', 'accepted_document', 'published_document', 'ready'):
            data.pop(key, None)
        db.execute("UPDATE operations SET stage='draft', revision=revision+1, data=? WHERE record_id=?", (json.dumps(data), record_id))
