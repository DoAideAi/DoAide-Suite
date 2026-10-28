"""Workspace-scoped authoritative Inventory/Scheduler commands and durable receipts."""
import json
import os
from datetime import datetime, timedelta, timezone
import httpx
from fastapi import HTTPException
from . import operations as op
from .db import database
from .portfolio_connections import connection


def configured(service, workspace):
    try:
        mapping = json.loads(os.environ.get('DOAIDE_' + service + '_CONNECTIONS', '{}'))
        return isinstance(mapping, dict) and workspace in mapping
    except ValueError:
        raise HTTPException(422, service + ' connection configuration is invalid')


def authority(db, service, workspace):
    row = db.execute('SELECT endpoint FROM portfolio_authorities WHERE workspace_id=? AND service=?', (workspace, service)).fetchone()
    return row[0] if row else None


def activate(db, service, user):
    # Activation is explicit, recorded and sticky even if credentials are removed.
    from .worker import Blocked
    try:
        path = db.execute('PRAGMA database_list').fetchone()[2]
        config = connection(service, user['workspace_id'], path)
    except Blocked as exc:
        raise HTTPException(422, str(exc))
    op.require(type(config.get('business_id')) is int and config['business_id'] > 0, 'Configure the authoritative business ID')
    endpoint = config['url'].rstrip('/')
    scope=op.dump({key:config.get(key) for key in ('business_id','warehouse_id')})
    previous = authority(db, service, user['workspace_id'])
    if previous:
        op.require(db.execute('SELECT scope FROM portfolio_authorities WHERE workspace_id=? AND service=?',(user['workspace_id'],service)).fetchone()[0] == scope, 'Authority business or warehouse changed; restore the original mapping before continuing')
    op.require(not previous or previous == endpoint, 'Reconcile the existing authority before changing its endpoint')
    if not previous:
        if service == 'INVENTORY':
            rows = db.execute("SELECT * FROM stock WHERE workspace_id=? AND sku NOT LIKE 'lot:%' AND sku NOT LIKE 'finished:%'", (user['workspace_id'],)).fetchall()
            op.require(not rows, 'Reconcile existing local catalogue balances before activating Inventory in this workspace; use a new workspace for initial connection testing')
        db.execute('INSERT OR IGNORE INTO portfolio_authorities VALUES (?,?,?,?,?)', (user['workspace_id'], service, endpoint, op.now(), scope))
    return config


def queue(db, r, u, service, command, payload, state, item_id=None):
    endpoint = authority(db, service, u['workspace_id'])
    op.require(endpoint, 'Activate the workspace connection first')
    data = {'command': command, 'payload': payload, 'endpoint': endpoint, 'user_id': u['id'], 'item_id': item_id}
    job = op.enqueue(db, r, u, service.lower() + '-command', data, service + ':' + r['id'] + ':' + str(state['revision']) + ':' + command + ':' + str(item_id))
    if item_id:
        item = op.one_item(db, r['id'], item_id, 'visit')
        preserved = {'_local_status_before_refresh': item['data']['_status']} if command == 'refresh' and item['data'].get('_status') in ('completed','verified') else {}
        op.store_item(db, r['id'], 'visit', {**item['data'], **preserved, '_job_id': job, '_status': 'booking-pending'}, u, item_id)
    else:
        state['data']['authority_pending'] = job
    return job


def supersede_failed(db, job_id):
    if not job_id:return
    row=db.execute('SELECT state FROM jobs WHERE id=?',(job_id,)).fetchone()
    op.require(row and row['state'] in ('blocked','failed','dead-letter'),'Wait for the pending command to finish before reconciling')
    db.execute("UPDATE jobs SET state='cancelled',last_error='Superseded by explicit authority reconciliation' WHERE id=?",(job_id,))


def before_resource(db, r, u, kind, existing):
    if r['product'] == 'orderdesk' and authority(db, 'INVENTORY', u['workspace_id']):
        op.require(kind != 'catalogue', 'Inventory owns this catalogue; refresh it from Inventory')
    if existing and existing['data'].get('_scheduler_reference'):
        raise HTTPException(409, 'Use Scheduler reschedule/cancel actions and retain the visit audit trail')


def visit_created(db, r, u, data, item_id, state):
    if not authority(db, 'SCHEDULER', u['workspace_id']):
        return
    op.require(data.get('meeting_type_id') and data.get('customer_email'), 'Connected visits require a Scheduler meeting type ID and customer email')
    reference = 'suite-' + item_id
    data.update({'_scheduler_reference': reference, '_status': 'booking-pending'})
    op.store_item(db, r['id'], 'visit', data, u, item_id)
    queue(db, r, u, 'SCHEDULER', 'create', {'reference': reference, 'meeting_type_id': int(data['meeting_type_id']),
        'host_email': data['technician'], 'start_time': data['start'], 'end_time': data['end'],
        'guest_name': json.loads(r['payload'])['customer'], 'guest_email': data['customer_email']}, state, item_id)


def execute(db, r, u, action, data, state, result):
    slug = r['product']
    if slug == 'amc' and action == 'connect_scheduler':
        op.permit(u, 'owner')
        activate(db, 'SCHEDULER', u)
        result['authority'] = 'DoAide Scheduler'
        return True
    if slug == 'amc' and action in ('scheduler_refresh', 'scheduler_cancel', 'scheduler_reschedule', 'scheduler_retry'):
        item = op.one_item(db, r['id'], data['item_id'], 'visit');visit = item['data']
        op.require(visit.get('_scheduler_reference'), 'This visit is local; create a new connected visit')
        if action == 'scheduler_refresh':supersede_failed(db, visit.get('_job_id'))
        else:op.require(visit.get('_status') != 'booking-pending', 'Resolve the pending Scheduler job first')
        op.require(visit.get('_status') not in ('completed', 'verified') or action == 'scheduler_refresh', 'Completed service evidence is immutable')
        payload = {'reference': visit['_scheduler_reference']}
        command = action.removeprefix('scheduler_')
        if command == 'retry':
            op.require(visit.get('_status') == 'booking-missing', 'Reconcile the missing booking first')
            command = 'create'
            visit.setdefault('_scheduler_reference_history',[]).append(visit['_scheduler_reference'])
            visit['_scheduler_reference']='suite-'+op.uid()
            payload['reference']=visit['_scheduler_reference']
            op.store_item(db,r['id'],'visit',visit,u,item['id'])
            payload.update({'meeting_type_id': int(visit['meeting_type_id']), 'host_email': visit['technician'], 'start_time':visit['start'], 'end_time':visit['end'], 'guest_name':json.loads(r['payload'])['customer'], 'guest_email':visit['customer_email']})
        if command == 'reschedule':
            candidate = {**visit, 'start': data['start'], 'end': data['end']}
            op.schedule_visit(db, r, u, candidate, item['id'])
            if candidate.get('window_start'):
                op.require(candidate['window_start'] <= candidate['start'] < candidate['end'] <= candidate['window_end'], 'Reschedule must fit the agreed customer window')
            payload.update({'start_time': candidate['start'], 'end_time': candidate['end']})
        result['job_id'] = queue(db, r, u, 'SCHEDULER', command, payload, state, item['id'])
        return True
    if slug != 'orderdesk':
        return False
    if action == 'inventory_refresh':
        op.permit(u, 'owner', 'reviewer')
        pending=state['data'].get('authority_pending')
        if pending:
            old=db.execute('SELECT data FROM jobs WHERE id=?',(pending,)).fetchone()
            op.require(old and json.loads(old[0])['command']=='catalogue','Reconcile the existing reservation command first')
            supersede_failed(db,pending)
        if not authority(db, 'INVENTORY', u['workspace_id']):
            op.permit(u, 'owner')
        config = activate(db, 'INVENTORY', u)
        op.require(type(config.get('warehouse_id')) is int and config['warehouse_id'] > 0, 'Configure the Inventory warehouse ID')
        result['job_id'] = queue(db, r, u, 'INVENTORY', 'catalogue', {'warehouse_id': config['warehouse_id']}, state)
        return True
    if not authority(db, 'INVENTORY', u['workspace_id']):
        return False
    if action == 'inventory_status':supersede_failed(db, state['data'].get('authority_pending'))
    else:op.require(not state['data'].get('authority_pending'), 'Resolve the pending Inventory job first')
    op.require(action != 'publish_catalogue', 'Inventory owns stock and prices; use Refresh Inventory catalogue')
    if action not in ('reserve', 'dispatch', 'cancel', 'inventory_status'):
        return False
    if action == 'reserve':
        op.require(state['stage'] == 'confirmed', 'Confirm the exact order first')
        order = state['data']['parsed_order']
        op.require(state['data']['confirmation']['order_hash'] == op.digest(order), 'Order changed after confirmation')
        reference = 'suite-' + r['id'] + '-' + str(state['revision'])
        lines = []
        for line in order['lines']:
            row = op.stock_row(db, u, line['sku']);source = json.loads(row['data']) if row else {}
            op.require(source.get('_inventory') and op.digest(source) == line['price_version'], 'Refresh Inventory and reconfirm the order')
            lines.append({**source['_inventory'], 'quantity': line['quantity']})
        from .workflow_extensions import singleton
        hours = min(168, int(singleton(db, r, 'delivery').get('hold_hours', 24)))
        expires = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
        payload = {'reference': reference, 'lines': lines, 'expires_at': expires}
        state['data']['inventory_reference'] = reference
        state['data']['reservation_expires_at'] = expires
    else:
        reference = state['data'].get('inventory_reference')
        if action == 'cancel' and not reference:
            return False
        op.require(reference, 'No Inventory reservation exists for this order')
        if action == 'dispatch':op.require(state['stage'] == 'reserved', 'Wait for a confirmed Inventory reservation')
        payload = {'reference': reference}
        if action == 'dispatch':state['data']['requested_dispatch'] = data
        if action == 'cancel':state['data']['cancellation'] = data
    command = 'status' if action == 'inventory_status' else action
    result['job_id'] = queue(db, r, u, 'INVENTORY', command, payload, state)
    state['stage'] = 'inventory-pending'
    return True


def deliver(job, path, transport=None):
    from .worker import Blocked
    if os.environ.get('DOAIDE_DELIVERY_MODE', 'disabled') != 'enabled':
        raise Blocked('External connections are disabled')
    service = job['kind'].split('-')[0].upper();data = job['data'];payload = dict(data['payload'])
    config = connection(service, job['workspace_id'], path)
    if config['url'].rstrip('/') != data['endpoint']:
        raise Blocked('Authority endpoint changed; restore it and reconcile before retrying')
    with database(path) as db:
        pinned=db.execute('SELECT scope FROM portfolio_authorities WHERE workspace_id=? AND service=?',(job['workspace_id'],service)).fetchone()
        if not pinned or pinned[0] != op.dump({key:config.get(key) for key in ('business_id','warehouse_id')}):raise Blocked('Authority business or warehouse mapping changed; restore it before retrying')
        record = db.execute('SELECT status FROM records WHERE id=?', (job['record_id'],)).fetchone()
        member = db.execute('SELECT role FROM memberships WHERE workspace_id=? AND user_id=?', (job['workspace_id'], data['user_id'])).fetchone()
        state = op.get_state(db,job['record_id'])
        pending = state['data'].get('authority_pending') if service == 'INVENTORY' else op.one_item(db,job['record_id'],data['item_id'],'visit')['data'].get('_job_id')
        if pending != job['id']:raise Blocked('Command was superseded; use the latest reconciliation')
        if not record or record['status'] == 'archived' or not member or member['role'] not in ('owner', 'operator', 'reviewer'):
            raise Blocked('Requester no longer has operational access, or record is archived')
    if type(config.get('business_id')) is not int:raise Blocked('Configure the authoritative business ID')
    headers = {'Authorization': 'Bearer ' + config['token'], 'Idempotency-Key': job['id'], 'X-DoAide-Business-ID':str(config['business_id'])}
    command = data['command'];base = data['endpoint']
    with httpx.Client(timeout=30, transport=transport, follow_redirects=False) as client:
        if command == 'catalogue':
            rows = []
            for skip in range(0, 10000, 200):
                response = client.get(base + '/suite/stock', params={**payload, 'skip': skip, 'limit': 200}, headers=headers)
                response.raise_for_status();page = response.json()
                if not isinstance(page, list) or len(page) > 200:raise Blocked('Invalid Inventory catalogue response')
                if any(not isinstance(row,dict) or row.get('business_id') != config['business_id'] for row in page):raise Blocked('Inventory returned the wrong business')
                rows.extend(page)
                if len(page) < 200:break
            else:raise Blocked('Inventory catalogue exceeds 10,000 rows; use a smaller warehouse')
            return {'catalogue': rows}
        if service == 'INVENTORY':
            url = base + '/suite/reservations'
            if command == 'reserve':response = client.post(url, headers=headers, json=payload)
            elif command == 'status':response = client.post(url + '/' + payload['reference'] + '/reconcile', headers=headers)
            else:response = client.post(url + '/' + payload['reference'] + '/' + command, headers=headers)
        else:
            url = base + '/suite/bookings'
            if command == 'create':response = client.post(url, headers=headers, json=payload)
            elif command == 'refresh':response = client.post(url + '/' + payload['reference'], headers=headers, json={'command':'reconcile'})
            else:
                reference = payload.pop('reference')
                response = client.post(url + '/' + reference, headers=headers, json={'command': command, **payload})
        if response.status_code in (400, 401, 403, 404, 409, 410, 422):
            raise Blocked(service + ' rejected the command (' + str(response.status_code) + '); resolve it in the owning service, then retry or reconcile')
        response.raise_for_status();result = response.json()
        if not isinstance(result,dict) or result.get('business_id') != config['business_id']:raise Blocked('Authority returned the wrong business')
        if result.get('status')=='missing' and command in ('status','refresh') and result.get('reference')==data['payload']['reference']:return result
        valid = ('reserved','dispatched','cancelled','expired') if service == 'INVENTORY' else ('pending','confirmed','rescheduled','cancelled','completed','no_show')
        if not isinstance(result, dict) or result.get('reference') != data['payload']['reference'] or result.get('status') not in valid:
            raise Blocked('Invalid authority response; reconcile before retry')
        if service == 'INVENTORY' and type(result.get('reservation_id')) is not int:raise Blocked('Missing Inventory reservation ID')
        if service == 'SCHEDULER' and (type(result.get('booking_id')) is not int or not result.get('start_time') or not result.get('end_time')):raise Blocked('Missing Scheduler booking details')
        return result


def complete(db, job, result):
    r = dict(db.execute('SELECT * FROM records WHERE id=?', (job['record_id'],)).fetchone());s = op.get_state(db, r['id'])
    u = {'id': job['data']['user_id'], 'email': 'portfolio-adapter', 'workspace_id': job['workspace_id']}
    if job['kind'] == 'inventory-command':
        op.require(s['data'].get('authority_pending') == job['id'], 'Inventory job was superseded')
        if job['data']['command'] == 'catalogue':
            # Cache is only for matching and quoting. Reservations always commit remotely.
            seen = set()
            for row in result['catalogue']:
                op.require(isinstance(row, dict) and isinstance(row.get('sku'), str) and row['sku'] and row['sku'] not in seen and not row['sku'].startswith(('lot:', 'finished:')), 'Invalid or duplicate Inventory SKU')
                seen.add(row['sku'])
                op.require(type(row.get('quantity')) is int and type(row.get('held')) is int and 0 <= row['held'] <= row['quantity'], 'Invalid Inventory balance')
                op.require(type(row.get('product_id')) is int and row.get('warehouse_id') == job['data']['payload']['warehouse_id'], 'Invalid Inventory source reference')
                data = {'sku': row['sku'], 'name': row['name'], 'unit': row['unit'], 'price': str(op.decimal(row['price'])), 'tax': str(op.decimal(row['tax'])), 'pack': 1, 'aliases': '',
                        '_inventory': {'product_id': row['product_id'], 'warehouse_id': row['warehouse_id'], 'price': str(op.decimal(row['price'])), 'tax': str(op.decimal(row['tax'])), 'unit': row['unit']}}
                db.execute('INSERT INTO stock VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(workspace_id,sku) DO UPDATE SET name=excluded.name,unit=excluded.unit,quantity=excluded.quantity,held=excluded.held,data=excluded.data,updated_at=excluded.updated_at',
                    (u['workspace_id'], row['sku'], row['name'], row['unit'], str(row['quantity']), str(row['held']), op.dump(data), op.now()))
            for row in db.execute('SELECT sku,data FROM stock WHERE workspace_id=?', (u['workspace_id'],)).fetchall():
                if json.loads(row['data']).get('_inventory') and row['sku'] not in seen:db.execute('DELETE FROM stock WHERE workspace_id=? AND sku=?', (u['workspace_id'], row['sku']))
            s['data']['inventory_refreshed_at'] = op.now()
        else:
            s['data']['inventory_receipt'] = result
            s['stage'] = 'reservation-expired' if result['status'] == 'expired' else 'confirmed' if result['status'] == 'missing' else result['status']
            if result['status'] == 'missing':
                s['data'].pop('inventory_reference',None)
                s['data'].pop('reservation_expires_at',None)
            if result['status'] == 'dispatched' and not s['data'].get('dispatch_document'):
                s['data']['dispatch'] = {**s['data'].get('requested_dispatch', {}), 'at': op.now(), 'inventory_reservation_id': result['reservation_id']}
                s['data']['dispatch_document'] = op.snapshot(db, r, u, 'dispatch-note', s)
        s['data'].pop('authority_pending', None)
    else:
        item = op.one_item(db, r['id'], job['data']['item_id'], 'visit');visit = item['data']
        op.require(visit.get('_job_id') == job['id'], 'Scheduler job was superseded')
        visit['_scheduler_receipt'] = result
        visit['_scheduler_checked_at'] = op.now()
        status = result['status']
        if visit.get('_local_status_before_refresh'):
            visit['_status'] = visit.pop('_local_status_before_refresh')
        else:
            visit['_status'] = 'scheduled' if status in ('confirmed', 'rescheduled') else 'booking-' + status
            if result['status'] != 'missing':visit['start'], visit['end'] = op.instant(result['start_time']), op.instant(result['end_time'])
        if result.get('host_email') and result['host_email'].casefold() != visit['technician'].casefold():
            visit['_scheduler_issue']='Scheduler host differs from the assigned technician; reconcile before service'
            if visit['_status'] not in ('completed','verified'):visit['_status']='booking-review-required'
        else:visit.pop('_scheduler_issue',None)
        visit.pop('_job_id', None)
        op.store_item(db, r['id'], 'visit', visit, u, item['id'])
    op.event(db, r, u, job['kind'] + '.confirmed', result if 'catalogue' not in result else {'catalogue_rows': len(result['catalogue'])}, s)


def require_current_booking(visit):
    if not visit.get('_scheduler_reference'):return
    op.require(visit.get('_status')=='scheduled' and not visit.get('_scheduler_issue'),'Resolve the Scheduler appointment before service')
    checked=visit.get('_scheduler_checked_at')
    op.require(checked and datetime.fromisoformat(checked) > datetime.now(timezone.utc)-timedelta(minutes=5), 'Refresh Scheduler booking before starting or completing this connected visit')
    op.require(visit.get('_scheduler_receipt',{}).get('status') in ('confirmed','rescheduled'), 'Scheduler has not confirmed this appointment')
