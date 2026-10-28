"""Optional Stripe test-mode checkout, portal and authoritative reconciliation.

Network work happens in durable jobs, never during a database write transaction.
Webhook payloads only trigger a fresh provider read; they do not grant entitlements.
"""
import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from .db import database
from .migrations import permit
from .commercial import configuration, entitlement, queue, log

API_VERSION = '2025-06-30.basil'


def provider(method, path, data=None, key=None, transport=None):
    from .worker import Blocked
    secret = os.environ.get('STRIPE_TEST_SECRET_KEY', '')
    if configuration()[0] != 'stripe-test' or not secret.startswith('sk_test_'):
        raise Blocked('Configure a Stripe test secret key; live keys are not accepted')
    headers = {'Stripe-Version': API_VERSION}
    if key: headers['Idempotency-Key'] = key
    with httpx.Client(timeout=30, transport=transport) as client:
        response = client.request(method, 'https://api.stripe.com/v1' + path, auth=(secret, ''),
                                  headers=headers, data=data if method == 'POST' else None,
                                  params=data if method == 'GET' else None)
        response.raise_for_status()
        result = response.json()
    if result.get('livemode') is True:
        raise Blocked('Live billing objects are not accepted')
    return result


def return_url():
    from .worker import Blocked
    value = os.environ.get('DOAIDE_PUBLIC_URL', 'http://127.0.0.1:8012').rstrip('/')
    url = urlparse(value)
    if url.username or url.password or url.query or url.fragment or not url.hostname:
        raise Blocked('Configure a valid public application URL')
    if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('127.0.0.1', 'localhost')):
        raise Blocked('Billing return URL must use HTTPS or local development HTTP')
    return value + '/?billing=returned'


def reconcile(workspace_id, path=None, transport=None, job=None):
    from .worker import Blocked
    from .operations import now
    with database(path) as db:
        row = db.execute('SELECT * FROM billing_accounts WHERE workspace_id=?', (workspace_id,)).fetchone()
    if not row or not row['customer_id']: raise Blocked('No billing customer is connected')
    customer = row['customer_id']
    def quarantine(message):
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            if job and not db.execute("SELECT 1 FROM jobs WHERE id=? AND state='running' AND attempts=? AND lease_until>?",(job['id'],job['attempts'],now())).fetchone():
                raise Blocked('Billing worker lease expired before reconciliation')
            db.execute("UPDATE billing_accounts SET status='needs-review',plan=NULL,period_end=NULL WHERE workspace_id=?",(workspace_id,))
            log(db,workspace_id,'subscription.needs-review',{'reason':message})
        raise Blocked(message)
    result = provider('GET', '/subscriptions', {'customer': customer, 'status': 'all', 'limit': '100'}, transport=transport)
    if result.get('has_more'): quarantine('More than 100 subscriptions require billing reconciliation')
    subscriptions = result.get('data', [])
    if any(s.get('livemode') is not False or s.get('customer') != customer for s in subscriptions):
        quarantine('Subscription response does not match this test customer')
    current = [s for s in subscriptions if s['status'] not in ('canceled', 'incomplete_expired')]
    if len(current) > 1: quarantine('Multiple current subscriptions require manual reconciliation')
    plan = None; period_end = None; sub_id = None; status = 'unsubscribed'
    if current:
        sub = current[0]; status = sub['status']; sub_id = sub['id']
        lines = sub.get('items', {}).get('data', [])
        if len(lines) != 1 or lines[0].get('quantity') != 1:
            quarantine('Subscription must contain one configured plan at quantity one')
        price = lines[0]['price']
        plan = next((k for k, v in configuration()[2].items() if v.get('price_id') == price['id']), None)
        if not plan or price.get('livemode') is not False:
            quarantine('Subscription Price is not in the configured test catalogue')
        period_end = lines[0].get('current_period_end', sub.get('current_period_end'))
        if type(period_end) is not int: quarantine('Subscription has no valid access period')
        if status == 'trialing' and sub.get('trial_end'): period_end = min(period_end, sub['trial_end'])
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if job:
            owned=db.execute("SELECT 1 FROM jobs WHERE id=? AND state='running' AND attempts=? AND lease_until>?",(job['id'],job['attempts'],now())).fetchone()
            if not owned:raise Blocked('Billing worker lease expired before reconciliation')
        db.execute('UPDATE billing_accounts SET subscription_id=?,plan=?,status=?,period_end=?,synced_at=? WHERE workspace_id=? AND customer_id=?',
                   (sub_id, plan, status, period_end, now(), workspace_id, customer))
        log(db, workspace_id, 'subscription.reconciled', {'status': status, 'plan': plan, 'period_end': period_end})
    return {'status': status, 'plan': plan, 'period_end': period_end}


def deliver(job, path=None, transport=None):
    from .worker import Blocked
    workspace = job['workspace_id']; kind = job['kind']; data = job['data']
    with database(path) as db:
        row = dict(db.execute('SELECT * FROM billing_accounts WHERE workspace_id=?', (workspace,)).fetchone())
    if kind == 'billing-sync': return reconcile(workspace, path, transport, job)
    destination = data.get('return_url') or return_url()
    if kind == 'billing-checkout':
        if data['expires_at'] <= int(time.time()) + 60:
            raise Blocked('Checkout request expired; create a new request')
        plans = configuration()[2]; plan = plans.get(data['plan'])
        if not plan or not plan.get('price_id'): raise Blocked('Selected billing plan is no longer available')
        if data.get('price_id') and data['price_id']!=plan['price_id']:
            raise Blocked('The test Price changed after checkout was queued; reconcile or let this request expire')
        price = provider('GET', '/prices/' + plan['price_id'], transport=transport)
        if price.get('livemode') is not False or not price.get('active') or not price.get('recurring'):
            raise Blocked('Configure an active recurring test Price')
        if not row['customer_id']:
            customer = provider('POST', '/customers', {'metadata[doaide_workspace]': workspace},
                                'doaide-customer:' + workspace, transport)
            if customer.get('livemode') is not False or not re.fullmatch(r'cus_[A-Za-z0-9]+', customer.get('id', '')):
                raise Blocked('Unexpected billing customer response')
            with database(path) as db:
                db.execute('UPDATE billing_accounts SET customer_id=? WHERE workspace_id=?', (customer['id'], workspace))
            row['customer_id'] = customer['id']
        current = reconcile(workspace, path, transport, job)
        if current['status'] != 'unsubscribed': raise Blocked('An existing subscription must be managed through the billing portal')
        payload = {'customer': row['customer_id'], 'mode': 'subscription', 'client_reference_id': workspace,
                   'line_items[0][price]': plan['price_id'], 'line_items[0][quantity]': '1',
                   'subscription_data[metadata][doaide_workspace]': workspace,
                   'success_url': destination, 'cancel_url': destination,
                   'expires_at': str(data['expires_at'])}
        # A frozen expiry also bounds Stripe's 24-hour idempotency retention.
        if data['expires_at'] <= int(time.time()) + 60:
            raise Blocked('Checkout request expired; create a new request')
        result = provider('POST', '/checkout/sessions', payload, job['id'], transport)
        expected_host = 'checkout.stripe.com'
    elif kind == 'billing-portal':
        if not row['customer_id']: raise Blocked('No billing customer is connected')
        result = provider('POST', '/billing_portal/sessions', {'customer': row['customer_id'], 'return_url': destination}, job['id'], transport)
        expected_host = 'billing.stripe.com'
    else: raise Blocked('Unknown billing operation')
    url = urlparse(result.get('url', ''))
    if result.get('livemode') is not False or url.scheme != 'https' or url.hostname != expected_host or url.username or url.password:
        raise Blocked('Provider returned an unexpected test billing URL')
    return {'url': result['url'], 'id': result['id'], 'test_mode': True, 'expires_at': data.get('expires_at')}


def periodic(db):
    """Reconcile hourly, including missed webhooks; no external work in this call."""
    if configuration()[0] != 'stripe-test': return
    hour = datetime.now(timezone.utc).strftime('%Y%m%d%H')
    for row in db.execute('SELECT workspace_id FROM billing_accounts WHERE customer_id IS NOT NULL').fetchall():
        queue(db, row['workspace_id'], 'billing-sync', {}, 'billing-sync:hour:' + hour)


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    plan: str


def install_billing(app, db_path, current_user):
    @app.get('/api/billing')
    def status(user=Depends(current_user)):
        with database(db_path) as db:
            result = entitlement(db, user['workspace_id'])
            result['account'] = {k: v for k, v in result['account'].items() if k not in ('customer_id', 'subscription_id', 'checkout_job')}
            result['jobs'] = []
            if user['role'] == 'owner':
                rows = db.execute("SELECT id,kind,state,last_error,data,created_at FROM jobs WHERE workspace_id=? AND kind LIKE 'billing-%' ORDER BY created_at DESC LIMIT 30", (user['workspace_id'],))
                result['jobs'] = [{**{k: r[k] for k in ('id', 'kind', 'state', 'last_error', 'created_at')},
                                   'result': json.loads(r['data']).get('result', {})} for r in rows]
            result['owner'] = user['role'] == 'owner'
            result['configured'] = bool(os.environ.get('STRIPE_TEST_SECRET_KEY', '').startswith('sk_test_') and os.environ.get('STRIPE_TEST_WEBHOOK_SECRET'))
            return result

    @app.post('/api/billing/checkout')
    def checkout(body: PlanRequest, user=Depends(current_user)):
        permit(user, 'owner')
        mode, _, plans = configuration()
        if mode != 'stripe-test' or not plans.get(body.plan, {}).get('price_id'):
            raise HTTPException(422, 'Choose a configured Stripe test plan')
        with database(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO billing_accounts(workspace_id) VALUES (?)', (user['workspace_id'],))
            account = db.execute('SELECT * FROM billing_accounts WHERE workspace_id=?', (user['workspace_id'],)).fetchone()
            if account['subscription_id']:
                raise HTTPException(409, 'Use the billing portal for the existing subscription')
            if account['checkout_job']:
                job = db.execute('SELECT * FROM jobs WHERE id=?', (account['checkout_job'],)).fetchone()
                old = json.loads(job['data'])
                if old['expires_at'] > int(time.time()):
                    if old['plan'] != body.plan: raise HTTPException(409, 'A checkout for another plan is still pending')
                    return {'job_id': job['id']}
            expires = int(time.time()) + 3600
            from .worker import Blocked
            try:destination=return_url()
            except Blocked as exc:raise HTTPException(503,str(exc)) from None
            identifier = queue(db, user['workspace_id'], 'billing-checkout', {'plan': body.plan, 'price_id':plans[body.plan]['price_id'], 'expires_at': expires,'return_url':destination}, 'billing-checkout:' + str(expires))
            db.execute('UPDATE billing_accounts SET checkout_job=? WHERE workspace_id=?', (identifier, user['workspace_id']))
            log(db, user['workspace_id'], 'checkout.requested', {'plan': body.plan, 'actor': user['email']})
            return {'job_id': identifier}

    @app.post('/api/billing/{operation}')
    def control(operation: str, user=Depends(current_user)):
        permit(user, 'owner')
        if operation not in ('portal', 'sync'): raise HTTPException(404, 'Unknown billing action')
        with database(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM billing_accounts WHERE workspace_id=?', (user['workspace_id'],)).fetchone()
            if not row or not row['customer_id']: raise HTTPException(409, 'No billing customer is connected')
            return {'job_id': queue(db, user['workspace_id'], 'billing-' + operation, {}, 'billing-' + operation + ':' + str(int(time.time()) // 60))}

    @app.post('/api/webhooks/stripe-billing')
    async def webhook(request: Request):
        secret = os.environ.get('STRIPE_TEST_WEBHOOK_SECRET')
        if configuration()[0] != 'stripe-test' or not secret: raise HTTPException(503, 'Test billing webhook is not configured')
        raw = await request.body()
        try:
            parts = [x.split('=', 1) for x in request.headers.get('Stripe-Signature', '').split(',')]
            times = [v for k, v in parts if k == 't']
            assert len(times) == 1 and abs(int(time.time()) - int(times[0])) <= 300
            expected = hmac.new(secret.encode(), times[0].encode() + b'.' + raw, hashlib.sha256).hexdigest()
            assert any(k == 'v1' and hmac.compare_digest(expected, v) for k, v in parts)
            event = json.loads(raw)
            assert event['livemode'] is False and isinstance(event['id'], str) and len(event['id']) <= 200
            obj = event['data']['object']
            assert isinstance(obj,dict) and isinstance(event.get('type'),str)
            customer = obj.get('customer')
            assert customer is None or isinstance(customer, str)
        except (ValueError, KeyError, TypeError, AssertionError):
            raise HTTPException(400, 'Invalid test billing event or signature') from None
        supported = event.get('type', '').startswith('customer.subscription.') or event.get('type') in ('checkout.session.completed', 'invoice.paid', 'invoice.payment_failed')
        if not supported: return {'received': True, 'ignored': True}
        with database(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            account = db.execute('SELECT workspace_id FROM billing_accounts WHERE customer_id=?', (customer,)).fetchone()
            if not account: return {'received': True, 'ignored': True}
            inserted = db.execute("INSERT OR IGNORE INTO webhook_events VALUES ('stripe-billing',?,?)", (event['id'], datetime.now(timezone.utc).isoformat())).rowcount
            if inserted: queue(db, account['workspace_id'], 'billing-sync', {}, 'billing-event:' + event['id'])
        return {'received': True, 'duplicate': not bool(inserted)}
