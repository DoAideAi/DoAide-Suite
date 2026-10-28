"""Server-owned plans and atomic admission budgets. Existing records remain readable.

No prices are invented here: operators configure test Price IDs and product limits.
Budgets govern new records, memberships, source bytes and optional jobs; financial
callbacks, refunds and existing document downloads are never blocked by a quota.
"""
import json
import os
import re
import time
from datetime import datetime, timezone

from fastapi import HTTPException
from .catalog import CATALOG

METRICS = ('records', 'members', 'source_bytes', 'jobs_per_month')


def configuration():
    mode = os.environ.get('DOAIDE_BILLING_MODE', 'local')
    if mode == 'local':
        return mode, 'local', {'local': {'name': 'Local development', 'products': list(CATALOG),
                                       'limits': {k: None for k in METRICS}}}
    if mode != 'stripe-test':
        raise HTTPException(503, 'Billing supports local or stripe-test mode only')
    try:
        plans = json.loads(os.environ['DOAIDE_BILLING_PLANS'])
        base = os.environ['DOAIDE_BILLING_BASE_PLAN']
        assert isinstance(plans, dict) and base in plans and not plans[base].get('price_id')
        prices = []
        for key, plan in plans.items():
            assert isinstance(key, str) and 1 <= len(key) <= 60
            assert isinstance(plan['name'], str) and 1 <= len(plan['name']) <= 100
            assert isinstance(plan['products'], list) and set(plan['products']) <= set(CATALOG)
            assert set(plan['limits']) == set(METRICS)
            assert all(v is None or type(v) is int and v >= 0 for v in plan['limits'].values())
            if plan.get('price_id'):
                assert re.fullmatch(r'price_[A-Za-z0-9]+', plan['price_id'])
                prices.append(plan['price_id'])
        assert len(prices) == len(set(prices))
        return mode, base, plans
    except (KeyError, ValueError, TypeError, AttributeError, AssertionError):
        raise HTTPException(503, 'Billing plan configuration is invalid') from None


def usage(db, workspace_id):
    month = datetime.now(timezone.utc).strftime('%Y-%m-01T00:00:00+00:00')
    return {
        'records': db.execute('SELECT count(*) FROM record_workspaces WHERE workspace_id=?', (workspace_id,)).fetchone()[0],
        'members': db.execute('SELECT count(*) FROM memberships WHERE workspace_id=?', (workspace_id,)).fetchone()[0],
        'source_bytes': db.execute('SELECT coalesce(sum(length(f.content)),0) FROM files f JOIN record_workspaces w ON w.record_id=f.record_id WHERE w.workspace_id=?', (workspace_id,)).fetchone()[0],
        'jobs_per_month': db.execute("SELECT count(*) FROM jobs WHERE workspace_id=? AND created_at>=? AND kind NOT LIKE 'billing-%' AND kind!='auth-email'", (workspace_id, month)).fetchone()[0],
    }


def entitlement(db, workspace_id):
    mode, base, plans = configuration()
    row = db.execute('SELECT * FROM billing_accounts WHERE workspace_id=?', (workspace_id,)).fetchone()
    account = dict(row) if row else {'status': 'unsubscribed'}
    current = base
    if mode != 'local' and account.get('status') in ('active', 'trialing'):
        if account.get('period_end', 0) > int(time.time()) and account.get('plan') in plans:
            current = account['plan']
    return {'mode': mode, 'plan_id': current, 'plan': plans[current], 'account': account,
            'usage': usage(db, workspace_id), 'plans': plans}


def admit(db, workspace_id, metric=None, amount=1, product=None):
    """Call inside the same BEGIN IMMEDIATE transaction as the admitted write."""
    ent = entitlement(db, workspace_id)
    if product and product not in ent['plan']['products']:
        raise HTTPException(402, f'{product} is not included in the workspace plan. Existing records remain accessible.')
    if metric:
        limit = ent['plan']['limits'][metric]
        if limit is not None and ent['usage'][metric] + amount > limit:
            raise HTTPException(402, f'Workspace {metric.replace("_", " ")} budget reached ({limit}). Review the plan in Workspace tools.')


def queue(db, workspace_id, kind, data, key):
    from .operations import uid, now, dump
    identifier = uid()
    db.execute('INSERT OR IGNORE INTO jobs(id,workspace_id,kind,dedupe_key,data,due_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
               (identifier, workspace_id, kind, key, dump(data), now(), now(), now()))
    return db.execute('SELECT id FROM jobs WHERE workspace_id=? AND dedupe_key=?', (workspace_id, key)).fetchone()[0]


def log(db, workspace_id, action, data):
    from .operations import now, dump
    db.execute('INSERT INTO billing_events(workspace_id,action,data,created_at) VALUES (?,?,?,?)',
               (workspace_id, action, dump(data), now()))
