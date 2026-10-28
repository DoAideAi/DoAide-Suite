"""Transactional product workflows. All money is integer paise; quantities use Decimal.

Commands run inside BEGIN IMMEDIATE, so checks, stock mutations, documents and audit
entries commit together. External effects are durable jobs, never in-transaction calls.
"""
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from .domain import DomainError, validate_fields, calculate, decimal, amount
from .operations_catalog import SPECS
from .migrations import permit, invalidate


def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return str(uuid4())
def dump(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
def digest(value): return hashlib.sha256(dump(value).encode()).hexdigest()
def fail(message): raise DomainError(message)
def require(condition, message):
    if not condition: fail(message)
def cents(value):
    n = decimal(value) * 100
    require(n == n.to_integral_value(), 'Money must have at most two decimal places')
    return int(n)
def business_today(db, user):
    tz = db.execute('SELECT timezone FROM workspaces WHERE id=?', (user['workspace_id'],)).fetchone()[0]
    return datetime.now(ZoneInfo(tz)).date()
def instant(value):
    try:
        d = datetime.fromisoformat(value)
        if d.tzinfo is None: raise ValueError()
        return d.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError): fail('Use an ISO timestamp with an offset, for example 2026-12-01T10:00:00+05:30')


def get_state(db, record_id):
    created=db.execute('INSERT OR IGNORE INTO operations(record_id) VALUES (?)', (record_id,)).rowcount
    if created:
        record=db.execute('SELECT * FROM records WHERE id=?',(record_id,)).fetchone()
        if record and record['product']=='handover':
            for issue in json.loads(record['payload'])['issues']:
                store_item(db,record_id,'issue',{k:v for k,v in issue.items() if k!='status'}|{'due':datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat(),'file_id':'','_status':'open','_intake_status':issue['status']},{'id':record['user_id']})
    row = dict(db.execute('SELECT * FROM operations WHERE record_id=?', (record_id,)).fetchone())
    row['data'] = json.loads(row['data'])
    return row


def items(db, record_id, kind=None):
    query = 'SELECT * FROM operation_items WHERE record_id=?'
    args = [record_id]
    if kind: query += ' AND kind=?'; args.append(kind)
    return [{**dict(r), 'data': json.loads(r['data'])} for r in db.execute(query+' ORDER BY created_at,id', args)]


def one_item(db, record_id, item_id, kind=None):
    result = next((i for i in items(db,record_id,kind) if i['id'] == item_id), None)
    require(result is not None, 'Select an item belonging to this record')
    return result


def store_item(db, record_id, kind, data, user, item_id=None):
    item_id = item_id or uid()
    db.execute('INSERT INTO operation_items VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated_by=excluded.updated_by,updated_at=excluded.updated_at',
               (item_id,record_id,kind,dump(data),user['id'],user['id'],now(),now()))
    return item_id


def event(db, record, user, action, data, state):
    state['revision'] += 1
    db.execute('UPDATE operations SET revision=?,stage=?,data=? WHERE record_id=?', (state['revision'],state['stage'],dump(state['data']),record['id']))
    db.execute('INSERT INTO operation_events(record_id,actor,action,revision,data,created_at) VALUES (?,?,?,?,?,?)', (record['id'],user['email'],action,state['revision'],dump(data),now()))


def editable_record(db, record):
    s = get_state(db,record['id'])
    locked = {'accepted','invoicing','invoiced','reserved','materials-reserved','dispatched','produced','released','rejected','recalled','published','superseded','submitted','won','lost','withdrawn','cancelled','vendor-confirmed','completed','awarded'}
    if s['stage'] in locked or s['data'].get('schedule_amendments') or db.execute('SELECT 1 FROM ledger WHERE record_id=?', (record['id'],)).fetchone():
        raise HTTPException(409,'This record has operational commitments. Create a new revision/record or use an explicit adjustment.')
    if items(db,record['id'],'visit') and record['product']=='amc':
        raise HTTPException(409,'Contract terms are frozen once service visits exist; create a renewed contract for new terms')
    if items(db,record['id'],'issue') and record['product']=='handover':
        raise HTTPException(409,'Manage the snag register in Operations once it is opened; create a new revision for intake changes')


def validate_refs(db, record, fields, data):
    for f in fields:
        val = data.get(f['key'])
        if not val: continue
        if f.get('choices_from') == 'files':
            require(db.execute('SELECT 1 FROM files WHERE id=? AND record_id=? AND length(content)>0', (val,record['id'])).fetchone(), 'Evidence file must belong to this record')
        elif f.get('choices_from'):
            one_item(db,record['id'],val,f['choices_from'])
        if f['type']=='email':
            require(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',val), f"{f['label']} must be an email address")
            data[f['key']]=val.lower()


def resource(db, record, user, kind, raw, item_id=None, delete=False):
    permit(user,'owner','operator','reviewer')
    spec = SPECS[record['product']]['resources'].get(kind)
    require(spec is not None, 'Unknown resource type')
    state = get_state(db,record['id'])
    slug = record['product']
    if slug=='renew' and kind=='reminder_policy':permit(user,'owner','reviewer')
    if record['status']=='archived': raise HTTPException(409,'Restore the record before editing')
    existing = one_item(db,record['id'],item_id,kind) if item_id else None
    if slug=='batch' and kind=='dispatch' and existing:
        raise HTTPException(409,'Dispatch events are immutable; use a stock adjustment with its reference')
    if slug=='fees' and kind=='instalment' and (ledger_rows(db,record['id']) or state['data'].get('schedule_amendments')):
        raise HTTPException(409,'Use Approve remaining-fee reschedule to amend a schedule with receipts')
    # Prevent mutating the inputs behind stock, money, signatures and published procedures.
    if state['stage'] in ('accepted','invoicing','invoiced','reserved','dispatched','awarded','submitted','won','lost','withdrawn','cancelled','vendor-confirmed','superseded'):
        raise HTTPException(409,'This version is committed; create a new record for changes')
    if slug=='batch' and state['data'].get('production') and kind!='dispatch':
        raise HTTPException(409,'Consumed ingredients and recipe are immutable after production')
    if slug=='batch' and state['data'].get('material_reservations'):
        raise HTTPException(409,'Release input reservations before changing batch inputs')
    if slug=='batch' and kind=='dispatch':
        require(state['stage']=='released','Only quality-released output can be dispatched')
    if slug=='sop' and state['stage']=='published' and kind!='assignment':
        raise HTTPException(409,'Published SOP content is immutable; create a new record/version')
    if existing and existing['data'].get('_status') in ('completed','verified','waived','released'):
        raise HTTPException(409,'Use the explicit workflow action instead of overwriting completed evidence')
    if slug=='amc' and kind=='asset' and existing:
        require(not any(i['data']['asset_id']==existing['id'] and i['data'].get('_status') in ('completed','verified') for i in items(db,record['id'],'visit')),'An asset with completed visits is immutable; add a new asset version')
    if delete:
        require(not db.execute('SELECT 1 FROM task_links WHERE item_id=?',(item_id,)).fetchone(),'This item has contractor-link history; retain it for the audit trail')
        refs = [i for i in items(db,record['id']) if i['id'] != item_id and item_id in i['data'].values()]
        require(not refs,'This item is referenced by other records; remove those references first')
        db.execute('DELETE FROM operation_items WHERE id=?', (item_id,))
        data = {'id': item_id}
    else:
        data = validate_fields(spec['fields'], raw)
        if slug=='renew' and kind=='reminder_policy':
            from .renewals import policy_days
            policy_days(data)
        validate_refs(db,record,spec['fields'],data)
        if spec.get('singleton'):
            prior = items(db,record['id'],kind)
            require(not prior or (item_id and prior[0]['id']==item_id),'Edit the existing settings instead of adding another')
        if slug=='amc' and kind=='visit':
            schedule_visit(db,record,user,data,item_id)
        if slug=='amc' and kind=='part':
            require(data['visit_id'] not in state['data'].get('billed_visits',{}),'Parts on an invoiced visit require a separate adjustment record')
        if slug in ('tender','claimpack') and kind in ('deadline','template'):
            data['at' if kind=='deadline' else 'deadline']=instant(data['at' if kind=='deadline' else 'deadline'])
            if kind=='deadline':
                try: ZoneInfo(data['timezone'])
                except (KeyError,ValueError): fail('Use a valid IANA timezone')
        if slug=='claimpack' and kind=='timeline':
            data['at']=instant(data['at'])
            require(data['at']<=now(),'A factual evidence timeline cannot contain future events')
        if slug=='orderdesk' and kind in ('catalogue','message'):
            unique='sku' if kind=='catalogue' else 'reference'
            if kind=='catalogue':require(not data['sku'].casefold().startswith(('lot:','finished:')),'Lot and finished-batch SKU prefixes are reserved for Batch')
            require(not any(i['id']!=item_id and i['data'][unique].casefold()==data[unique].casefold() for i in items(db,record['id'],kind)),f'Duplicate {unique}')
        if slug=='batch' and kind=='usage': require(decimal(data['waste'])<=decimal(data['quantity']),'Waste cannot exceed total consumption')
        if slug=='batch' and kind=='dispatch':
            total=sum(int(i['data']['quantity']) for i in items(db,record['id'],kind) if i['id']!=item_id)+int(data['quantity'])
            require(total<=int(json.loads(record['payload'])['produced_units']),'Dispatch exceeds released batch output')
            require(not existing,'Dispatch records are immutable; record a separate stock correction')
        if slug=='sop' and kind=='assignment':
            member = db.execute('SELECT 1 FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=? AND u.email=?',(user['workspace_id'],data['employee'])).fetchone()
            require(member,'Assign training to a current workspace member')
            require(not any(i['id']!=item_id and i['data']['employee']==data['employee'] for i in items(db,record['id'],kind)),'This employee already has an assignment')
        if kind=='terms' and slug=='renew':
            for day in data['holidays'].splitlines():
                try: date.fromisoformat(day)
                except ValueError: fail('Holiday dates must use YYYY-MM-DD')
        if slug=='renew' and kind=='subscription':
            require(data['verified_on']<=business_today(db,user).isoformat(),'Usage evidence cannot be verified in the future')
            terms=items(db,record['id'],'terms')
            require(terms and int(data['active_seats'])<=int(terms[0]['data']['seats']),'Verified active seats must fit the recorded contract seats')
        item_id = store_item(db,record['id'],kind,data,user,item_id)
        if slug=='batch' and kind=='dispatch':
            sku='finished:'+json.loads(record['payload'])['batch_number'];row=stock_row(db,user,sku);q=decimal(data['quantity'])
            require(decimal(row['quantity'])-decimal(row['held'])>=q,'Insufficient released output for this dispatch')
            db.execute('UPDATE stock SET quantity=?,updated_at=? WHERE workspace_id=? AND sku=?',(str(decimal(row['quantity'])-q),now(),user['workspace_id'],sku))
            movement(db,record,user,sku,-q,'dispatch','batch-dispatch:'+data['reference'])
    if slug=='fees' and kind=='guardian' and existing and (delete or existing['data']['email']!=data['email']):
        db.execute('UPDATE shares SET revoked_at=? WHERE recipient=? AND document_id IN (SELECT id FROM documents WHERE record_id=?)',(now(),existing['data']['email'],record['id']))
    # Editing source inputs revokes pending links and old verification, never immutable documents.
    source_edit = slug in ('scope','rfq','tender','claimpack') or (slug=='sop' and kind!='assignment') or (slug=='orderdesk' and kind in ('catalogue','message')) or (slug=='fees' and kind=='instalment') or (slug=='handover' and kind=='issue')
    if source_edit:
        invalidate(db,record['id'])
        state=get_state(db,record['id'])
        for k in ('parsed_order','confirmation','agreement_document'):
            state['data'].pop(k,None)
    event(db,record,user,f'{kind}.{"deleted" if delete else "updated" if existing else "created"}',{'id':item_id,'data':data},state)
    if slug=='renew' and kind in ('terms','reminder_policy'):
        from .renewals import refresh
        refresh(db,record,user)
    return item_id


def schedule_visit(db, record, user, data, item_id):
    p=json.loads(record['payload'])
    data['start'],data['end']=instant(data['start']),instant(data['end'])
    require(data['start']<data['end'],'Visit end must be after its start')
    tz=db.execute('SELECT timezone FROM workspaces WHERE id=?',(user['workspace_id'],)).fetchone()[0]
    day=datetime.fromisoformat(data['start']).astimezone(ZoneInfo(tz)).date().isoformat()
    require(p['start']<=day<=p['end'],'Visit must be inside the contract period')
    require(db.execute('SELECT 1 FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=? AND u.email=? AND m.role IN (\'owner\',\'operator\',\'reviewer\')',(user['workspace_id'],data['technician'])).fetchone(),'Assign a technician who is a workspace member')
    rows=db.execute("SELECT i.id,i.data FROM operation_items i JOIN record_workspaces w ON w.record_id=i.record_id WHERE w.workspace_id=? AND i.kind='visit'",(user['workspace_id'],)).fetchall()
    for row in rows:
        if row['id']==item_id: continue
        v=json.loads(row['data'])
        require(not(v['technician']==data['technician'] and v['start']<data['end'] and data['start']<v['end']), 'Technician is already scheduled during this time')
    if data['chargeable']=='No':
        planned=sum(i['data']['chargeable']=='No' for i in items(db,record['id'],'visit') if i['id']!=item_id)
        require(planned+int(p['completed'])<int(p['included']),'All included visits are already allocated; mark an extra visit as chargeable')


def ledger_rows(db,record_id):
    return [dict(r) for r in db.execute('SELECT * FROM ledger WHERE record_id=? ORDER BY created_at,id',(record_id,))]


def financial(db,record):
    p=json.loads(record['payload'])
    if record['product']=='collect': total,opening=cents(p['amount']),cents(p['paid'])
    elif record['product']=='fees': total,opening=cents(decimal(p['fee'])-decimal(p['discount'])),sum(cents(i['amount']) for i in p['payments'])
    else: return {}
    rows=ledger_rows(db,record['id'])
    paid=opening+sum(i['amount']*(1 if i['kind'] in ('payment','credit') else -1) for i in rows)
    cash=opening+sum(i['amount']*(1 if i['kind']=='payment' else -1 if i['kind']=='refund' else 0) for i in rows)
    result={'total_paise':total,'opening_paid_paise':opening,'settled_paise':paid,'cash_received_paise':cash,'balance_paise':total-paid,'currency':'INR','entries':rows}
    if record['product']=='fees':
        changed=items(db,record['id'],'instalment');schedule=[i['data'] for i in changed] if changed else p['instalments']
        stored=db.execute('SELECT data FROM operations WHERE record_id=?',(record['id'],)).fetchone()
        state={'data':json.loads(stored['data']) if stored else {}}
        if changed and sum(cents(i['amount']) for i in schedule)!=total:
            schedule=p['instalments'];result['schedule_warning']='Draft instalments do not reconcile; allocations still use the intake schedule'
        if state['data'].get('schedule_amendments'):schedule=state['data']['schedule_amendments'][-1]['schedule']
        # Charges are separate obligations, not negative payments allocated against tuition.
        charges=[{'due':i['date'],'amount':str(Decimal(i['amount'])/100),'entry_id':i['id']} for i in rows if i['kind']=='charge']
        remaining=max(0,paid+sum(i['amount'] for i in rows if i['kind']=='charge'));allocations=[]
        for entry in sorted(schedule,key=lambda i:i['due']):
            expected=cents(entry['amount']);applied=min(remaining,expected);remaining-=applied
            allocations.append({'due':entry['due'],'amount_paise':expected,'allocated_paise':applied,'outstanding_paise':expected-applied})
        for entry in sorted(charges,key=lambda i:i['due']):
            expected=cents(entry['amount']);applied=min(remaining,expected);remaining-=applied
            allocations.append({'due':entry['due'],'amount_paise':expected,'allocated_paise':applied,'outstanding_paise':expected-applied,'charge_entry':entry['entry_id']})
        result['allocations']=allocations
        workspace=db.execute('SELECT workspace_id FROM record_workspaces WHERE record_id=?',(record['id'],)).fetchone()[0]
        result['due_now_paise']=sum(i['outstanding_paise'] for i in allocations if i['due']<=business_today(db,{'workspace_id':workspace}).isoformat())
    return result


def post_ledger(db,record,user,data):
    require(record['product'] in ('collect','fees'),'This record does not support financial entries')
    s=get_state(db,record['id'])
    if record['product']=='fees': require(s['data'].get('agreement_document'),'Approve the fee agreement before posting receipts')
    fin=financial(db,record)
    value=cents(data['amount'])
    require(data['date']<=business_today(db,user).isoformat(),'Cannot post a future payment or adjustment')
    if data['kind'] in ('payment','credit'): require(value<=fin['balance_paise'],'Payment or credit exceeds the outstanding balance')
    if data['kind']=='refund': require(value<=fin['cash_received_paise'],'Refund exceeds cash received')
    prior=db.execute('SELECT * FROM ledger WHERE workspace_id=? AND reference=?',(user['workspace_id'],data['reference'])).fetchone()
    require(not prior,'This payment / adjustment reference has already been recorded')
    identifier=uid()
    db.execute('INSERT INTO ledger VALUES (?,?,?,?,?,?,?,?,?,?,?)',(identifier,user['workspace_id'],record['id'],data['kind'],value,data['reference'],'INR',data['date'],data['note'],user['email'],now()))
    return identifier


def snapshot(db,record,user,kind,state,extra=None):
    payload=json.loads(record['payload'])
    body={'record':{k:v for k,v in record.items() if k not in ('user_id','payload')},'payload':payload,'stage':state['stage'],
          'items':items(db,record['id']),'workflow':state['data'],'financial':financial(db,record),
          'files':[dict(r) for r in db.execute('SELECT id,name,mime,size,checksum,extraction_status FROM files WHERE record_id=? ORDER BY created_at',(record['id'],))], 'extra':extra or {}}
    # Quiz answer keys and internal delivery policies never enter a customer-facing document.
    if record['product']=='sop':
        body['items']=[{**i,'data':{k:v for k,v in i['data'].items() if k!='answer'}} for i in body['items'] if i['kind']!='assignment']
    if record['product']=='claimpack':
        selected={i['data']['file_id'] for i in body['items'] if i['kind']=='evidence'}
        body['files']=[f for f in body['files'] if f['id'] in selected]
    identifier=uid(); timestamp=now()
    prefix={'receipt':'RCT','purchase-order':'PO','change-request':'CR','fee-agreement':'FEE','handover':'HO','claim-packet':'CLM'}.get(kind,'DOC')
    number=f'{prefix}-{datetime.now(timezone.utc):%Y%m%d}-{identifier[:8].upper()}'
    db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)',(identifier,record['id'],kind,number,record['version'],state['revision']+1,dump(body),digest(body),user['email'],timestamp))
    from .documents import freeze_pdf
    doc=dict(db.execute('SELECT * FROM documents WHERE id=?',(identifier,)).fetchone())
    freeze_pdf(db,doc)
    return identifier


def enqueue(db,record,user,kind,data,key,due_at=None):
    prior=db.execute('SELECT id FROM jobs WHERE workspace_id=? AND dedupe_key=?',(user['workspace_id'],key)).fetchone()
    if prior:return prior['id']
    from .commercial import admit
    admit(db,user['workspace_id'],'jobs_per_month')
    identifier=uid()
    db.execute('INSERT OR IGNORE INTO jobs(id,workspace_id,record_id,kind,dedupe_key,data,due_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',(identifier,user['workspace_id'],record['id'],kind,key,dump(data),due_at or now(),now(),now()))
    return db.execute('SELECT id FROM jobs WHERE workspace_id=? AND dedupe_key=?',(user['workspace_id'],key)).fetchone()[0]


def reminder_blocker(db,record):
    p=json.loads(record['payload']);slug=record['product']
    if record['status']=='archived': return 'Record is archived'
    if slug in ('collect','fees') and financial(db,record)['balance_paise']<=0: return 'Balance is settled'
    if slug=='fees' and financial(db,record)['due_now_paise']<=0:return 'No instalments are currently due'
    if slug=='collect':
        disputed=p['disputed']=='Yes';promise=p['promise'];optout=False
        for i in items(db,record['id'],'promise'):
            data=i['data'];kind=data['kind']
            if kind=='Dispute': disputed=True
            if kind=='Resolution': disputed=False
            if kind=='Promise': promise=data['until']
            if kind=='Opt out': optout=True
            if kind=='Opt in': optout=False
        if disputed: return 'Open dispute'
        if optout: return 'Customer opted out'
        workspace=db.execute('SELECT workspace_id FROM record_workspaces WHERE record_id=?',(record['id'],)).fetchone()[0]
        if promise and promise>=business_today(db,{'workspace_id':workspace}).isoformat(): return 'Active payment promise'
    return None


def schedule_reminder(db,record,user,data):
    require(data['consent']=='Yes','Consent is required before scheduling a reminder')
    require(int(data['start_hour'])<int(data['end_hour']),'Working-hours end must be after start')
    if record['product']=='fees':
        guardians=items(db,record['id'],'guardian')
        require(any(i['data']['email']==data['recipient'] and i['data']['reminders']=='Yes' for i in guardians),'Recipient must be an opted-in guardian for this student')
    if record['product']=='renew':
        terms=items(db,record['id'],'terms')
        require(terms and data['recipient'] in (terms[0]['data']['owner'],terms[0]['data']['backup']),'Choose the responsible owner or backup')
    reason=reminder_blocker(db,record)
    require(not reason,reason or '')
    data['due_at']=instant(data['due_at'])
    require(data['due_at']>=now(),'Reminder time must be in the future')
    return enqueue(db,record,user,'email',data,'reminder:'+digest(data),data['due_at'])


def clone_record(db,record,user,payload,title):
    from .commercial import admit
    admit(db,user['workspace_id'],'records',product=record['product'])
    payload,_=calculate(record['product'],payload)
    new_id=uid();ts=now()
    db.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?)',(new_id,user['id'],record['product'],title,dump(payload),'draft',1,ts,ts))
    db.execute('INSERT INTO record_workspaces VALUES (?,?)',(new_id,user['workspace_id']))
    db.execute('INSERT INTO audit_events(record_id,user_id,action,version,snapshot,created_at) VALUES (?,?,?,?,?,?)',(new_id,user['id'],'renewed-from:'+record['id'],1,dump(payload),ts))
    return new_id


def scope_total(record,rows):
    p=json.loads(record['payload'])
    if not rows: return cents(decimal(p['hours'])*decimal(p['rate']))
    total=0
    for i in rows:
        d=i['data']; base=decimal(d['quantity'])*decimal(d['rate'])-decimal(d['discount'])
        require(base>=0,'Estimate discount exceeds line cost')
        total+=cents(amount(base*(1+decimal(d['tax'])/100)))
    return total


def execute(db,record,user,action,raw):
    spec=SPECS[record['product']]['actions'].get(action)
    require(spec is not None,'Unknown product action')
    permit(user,*spec['roles'])
    if record['status']=='archived': raise HTTPException(409,'Restore this record before performing operations')
    data=validate_fields(spec['fields'],raw)
    validate_refs(db,record,spec['fields'],data)
    s=get_state(db,record['id']); p=json.loads(record['payload']);slug=record['product'];result={}
    if s['stage'] in ('accepted','invoicing','invoiced') and not (slug=='scope' and action=='invoice') and not (slug=='handover' and action=='reopen'):
        raise HTTPException(409,'This accepted version is immutable; create a new revision')
    if s['stage'] in ('won','lost','withdrawn') or (s['stage']=='submitted' and not (slug=='claimpack' and action=='outcome')):
        raise HTTPException(409,'Submitted evidence is immutable; create a new revision')
    if action=='ledger':
        result['entry_id']=post_ledger(db,record,user,data)
        result['document_id']=snapshot(db,record,user,'receipt',s,{'entry_id':result['entry_id']})
    elif action=='reminder': result['job_id']=schedule_reminder(db,record,user,data)
    elif action=='payment_link':
        if slug=='fees':
            require(s['data'].get('agreement_document'),'Approve the fee agreement first')
            require(any(i['data']['email']==data['email'] for i in items(db,record['id'],'guardian')),'Use a linked guardian email')
        balance=financial(db,record)['balance_paise'];require(balance>0,'This balance is settled')
        result['job_id']=enqueue(db,record,user,'payment-link',{'amount':balance,'currency':'INR','email':data['email']},f'payment-link:{record["id"]}:{balance}')
    elif slug=='scope':
        if action=='approve':
            require(p['decision'] not in ('Unreviewed','Needs clarification'),'Resolve clarification and record a human scope assessment first')
            require(items(db,record['id'],'baseline'),'Add the agreed baseline clauses and source references')
            projects=items(db,record['id'],'project')
            if projects:require(projects[0]['data']['valid_until']>=business_today(db,user).isoformat(),'The change offer has expired')
            total=scope_total(record,items(db,record['id'],'estimate'))
            policies=items(db,record['id'],'policy')
            if policies and total>cents(policies[0]['data']['limit']): permit(user,'owner')
            s['data']['commercial']={'total_paise':total,'currency':'INR','reason':data['reason']}
            s['stage']='approved';s['data']['approved_document']=snapshot(db,record,user,'change-request',s)
            result['document_id']=s['data']['approved_document']
        elif action=='invoice':
            require(s['data'].get('accepted_document'),'The client must accept the exact approved change first')
            require(not s['data'].get('invoice_job'),'Invoice handoff already exists')
            result['document_id']=snapshot(db,record,user,'draft-invoice',s,{'accepted_document':s['data']['accepted_document'],'commercial':s['data']['commercial']})
            result['job_id']=enqueue(db,record,user,'invoice',{'document_id':result['document_id']},'scope-invoice:'+s['data']['accepted_document'])
            s['data']['invoice_document']=result['document_id']
            s['data']['invoice_job']=result['job_id'];s['stage']='invoicing'
    elif slug=='amc':
        if action in ('complete_visit','verify_visit'):
            item=one_item(db,record['id'],data['item_id'],'visit');v=item['data']
            if action=='complete_visit':
                require(user['email']==v['technician'],'Only the assigned technician can record service completion')
                require(v.get('_status','scheduled')=='scheduled','This visit was already completed')
                require(v['start']<=now(),'Cannot complete a future service visit')
                v.update(_status='completed',_completed_by=user['id'],_notes=data['notes'],_file=data['file_id'],_completed_at=now())
            else:
                require(v.get('_status')=='completed','Technician completion is required before verification')
                require(v['_completed_by']!=user['id'],'A different person must independently verify service')
                v.update(_status='verified',_verified_by=user['id'],_verified_at=now())
            store_item(db,record['id'],'visit',v,user,item['id'])
        elif action=='service_statement':result['document_id']=snapshot(db,record,user,'service-statement',s)
        elif action=='bill_visit':
            visit=one_item(db,record['id'],data['item_id'],'visit');require(visit['data'].get('_status')=='verified','Independently verify service before billing')
            require(visit['id'] not in s['data'].get('billed_visits',{}),'This visit already has an invoice handoff')
            parts=[i['data'] for i in items(db,record['id'],'part') if i['data']['visit_id']==visit['id']]
            total=cents(data['service_charge'])+sum(cents(i['cost']) for i in parts)
            result['document_id']=snapshot(db,record,user,'draft-invoice',s,{'visit_id':visit['id'],'total_paise':total,'reason':data['reason']})
            result['job_id']=enqueue(db,record,user,'invoice',{'document_id':result['document_id']},'amc-invoice:'+visit['id'])
            s['data'].setdefault('billed_visits',{})[visit['id']]=result['document_id']
        elif action=='renew_contract':
            require(data['start']>p['end'] and data['end']>=data['start'],'The renewed period must start after the current contract expires')
            key=data['start']+'..'+data['end'];require(key not in s['data'].get('renewals',{}),'That renewal period already exists')
            payload={**p,'start':data['start'],'end':data['end'],'contract_value':data['value'],'included':data['included'],'completed':'0','next_visit':''}
            result['record_id']=clone_record(db,record,user,payload,record['title']+' · renewal')
            s['data'].setdefault('renewals',{})[key]=result['record_id']
    elif slug=='rfq':
        comparison=compare_quotes(db,record)
        s['data']['comparison']=comparison
        if action=='award':
            require(s['stage']!='awarded','A purchase order has already been issued')
            chosen=next((q for q in comparison if q['supplier']==data['supplier']),None)
            require(chosen and not chosen['blockers'],'Chosen supplier must have a complete, equivalent quotation')
            require(any(i['data']['supplier']==data['supplier'] for i in items(db,record['id'],'evaluation')),'Record a technical evaluation before award')
            policy=items(db,record['id'],'policy')
            if policy and chosen['total_paise']>cents(policy[0]['data']['owner_limit']):permit(user,'owner')
            s['data']['award']={**data,'total_paise':chosen['total_paise']};s['stage']='awarded'
            result['document_id']=snapshot(db,record,user,'purchase-order',s)
    elif slug=='tender': tender_action(db,record,user,action,data,s,result)
    elif slug=='handover': handover_action(db,record,user,action,data,s,result)
    elif slug=='orderdesk': order_action(db,record,user,action,data,s,result)
    elif slug=='batch': batch_action(db,record,user,action,data,s,result)
    elif slug=='fees':
        if action=='approve_agreement':
            require(not s['data'].get('schedule_amendments'),'Amended schedules retain their approved agreement; use another reschedule')
            require(not ledger_rows(db,record['id']),'Fee agreements with payments cannot be replaced; post an adjustment')
            schedule=items(db,record['id'],'instalment')
            if schedule: require(sum(cents(i['data']['amount']) for i in schedule)==cents(decimal(p['fee'])-decimal(p['discount'])),'Rescheduled instalments must equal net fees')
            s['stage']='approved';s['data']['agreement_document']=snapshot(db,record,user,'fee-agreement',s,data)
            result['document_id']=s['data']['agreement_document']
        elif action=='reschedule':
            require(s['data'].get('agreement_document'),'Approve the original agreement before rescheduling')
            fin=financial(db,record);principal=[i for i in fin['allocations'] if 'charge_entry' not in i]
            outstanding=sum(i['outstanding_paise'] for i in principal)
            require(outstanding>0,'All tuition instalments are settled; use financial adjustments for charges or refunds')
            require(data['instalments'] and sum(cents(i['amount']) for i in data['instalments'])==outstanding,'Replacement instalments must equal unpaid tuition exactly')
            require(all(i['due']>=business_today(db,user).isoformat() for i in data['instalments']),'New instalment dates cannot be in the past')
            require(len({i['due'] for i in data['instalments']})==len(data['instalments']),'Combine instalments on the same date')
            paid=[{'due':i['due'],'amount':str(Decimal(i['allocated_paise'])/100)} for i in principal if i['allocated_paise']]
            amendment={'number':len(s['data'].get('schedule_amendments',[]))+1,'at':now(),'approved_by':user['email'],'reason':data['reason'],
                       'previous_allocations':fin['allocations'],'schedule':paid+data['instalments']}
            s['data'].setdefault('schedule_amendments',[]).append(amendment)
            # Persist the version before freezing so its financial snapshot uses this schedule.
            db.execute('UPDATE operations SET data=? WHERE record_id=?',(dump(s['data']),record['id']))
            result['document_id']=snapshot(db,record,user,'fee-schedule-amendment',s,amendment)
            amendment['document_id']=result['document_id']
        elif action=='statement': result['document_id']=snapshot(db,record,user,'guardian-statement',s)
    elif slug=='renew': renew_action(db,record,user,action,data,s,result)
    elif slug=='sop': sop_action(db,record,user,action,data,s,result)
    elif slug=='claimpack': claim_action(db,record,user,action,data,s,result)
    event(db,record,user,action,{'input':data,'result':result},s)
    return result


def compare_quotes(db,record):
    requirements=items(db,record['id'],'requirement');offers=items(db,record['id'],'offer')
    require(requirements and offers,'Add required items and supplier offer lines first')
    groups={}
    for offer in offers:
        d=offer['data'];q=groups.setdefault(d['supplier'],{'supplier':d['supplier'],'total_paise':0,'lines':[],'blockers':[]})
        r=one_item(db,record['id'],d['requirement_id'],'requirement')['data']
        if any(line['requirement_id']==d['requirement_id'] for line in q['lines']): q['blockers'].append('Duplicate offer for '+r['sku'])
        if d['unit'].casefold()!=r['unit'].casefold() or decimal(d['quantity'])!=decimal(r['quantity']): q['blockers'].append('Unit / quantity mismatch: '+r['sku'])
        if d['equivalent']!='Yes': q['blockers'].append('Unconfirmed specification: '+r['sku'])
        require(re.fullmatch('[A-Z]{3}',d['currency']),'Use an uppercase three-letter currency code')
        if d['currency']=='INR': require(decimal(d['fx'])==1,'INR quotes require an exchange rate of 1')
        base=decimal(d['quantity'])*decimal(d['price'])-decimal(d['discount']);require(base>=0,'Quote discount exceeds goods value')
        total=cents(amount((base*(1+decimal(d['tax'])/100)+decimal(d['freight']))*decimal(d['fx'])))
        q['total_paise']+=total;q['lines'].append({**d,'total_paise':total})
    for q in groups.values():
        missing={r['id'] for r in requirements}-{line['requirement_id'] for line in q['lines']}
        if missing:q['blockers'].append(f'Missing {len(missing)} required item(s)')
    policy=items(db,record['id'],'policy')
    if policy:
        weights=policy[0]['data'];require(sum(int(weights[k]) for k in ('cost_weight','technical_weight','lead_weight'))==100,'Evaluation weights must total 100%')
        scores={i['data']['supplier']:decimal(i['data']['score']) for i in items(db,record['id'],'evaluation')}
        lowest=min(q['total_paise'] for q in groups.values());fastest=min(max(int(line['lead_days']) for line in q['lines']) for q in groups.values())
        for q in groups.values():
            lead=max(int(line['lead_days']) for line in q['lines'])
            costscore=Decimal(lowest)/max(1,q['total_paise']);leadscore=Decimal(fastest)/max(1,lead)
            q['weighted_score']=amount(costscore*int(weights['cost_weight'])+scores.get(q['supplier'],Decimal(0))/100*int(weights['technical_weight'])+leadscore*int(weights['lead_weight']))
    return sorted(groups.values(),key=lambda q:q['total_paise'])


def tender_action(db,record,user,action,data,s,result):
    if action in ('extract','amendment'):
        file=db.execute('SELECT * FROM files WHERE id=? AND record_id=?',(data['file_id'],record['id'])).fetchone()
        if action=='extract':
            text=file['extracted'];require(text.strip(),'No extractable text; upload a readable or OCR-processed document')
            count=0
            for line in text.splitlines():
                if re.search(r'\b(required|must|shall|mandatory)\b',line,re.I):
                    if any(i['data']['citation']==file['name']+' · '+line[:120] for i in items(db,record['id'],'requirement')):continue
                    store_item(db,record['id'],'requirement',{'text':line[:20000],'citation':file['name']+' · '+line[:120],'category':'Submission','owner':user['email'],'due':json.loads(record['payload'])['deadline'],'file_id':'','valid_until':'','_source_file':file['id']},user);count+=1
            require(count,'No new explicit requirements found; add and cite requirements manually')
            result['candidates']=count
        else:
            for i in items(db,record['id'],'requirement'):
                d=i['data'];d.pop('_verified',None);d.pop('_verified_by',None);store_item(db,record['id'],'requirement',d,user,i['id'])
            s['data'].setdefault('amendments',[]).append({**data,'at':now()})
        invalidate(db,record['id']);s['stage']='draft';s['data'].pop('ready',None)
    elif action=='verify_requirement':
        item=one_item(db,record['id'],data['item_id'],'requirement');r=item['data']
        require(r['file_id'],'Attach the required evidence file before verification')
        deadlines=items(db,record['id'],'deadline')
        deadline=(datetime.fromisoformat(deadlines[0]['data']['at']).astimezone(ZoneInfo(deadlines[0]['data']['timezone'])).date().isoformat() if deadlines else json.loads(record['payload'])['deadline'])
        require(not r['valid_until'] or r['valid_until']>=deadline,'Evidence expires before the tender deadline')
        r.update(_verified=True,_verified_by=user['email'],_note=data['note']);store_item(db,record['id'],'requirement',r,user,item['id'])
    elif action=='ready':
        deadlines=items(db,record['id'],'deadline');require(deadlines,'Set an exact deadline with timezone')
        require(deadlines[0]['data']['at']>now(),'Tender deadline has passed')
        reqs=items(db,record['id'],'requirement');require(reqs and all(i['data'].get('_verified') for i in reqs),'Every requirement needs verified evidence')
        s['stage']='ready';s['data']['ready']=True;result['document_id']=snapshot(db,record,user,'tender-manifest',s)
    elif action=='submission':
        require(s['data'].get('ready') and s['stage']=='ready','Approve readiness before recording submission')
        s['stage']='submitted';s['data']['submission']={**data,'recorded_at':now()}


def handover_action(db,record,user,action,data,s,result):
    if action=='close':
        issues=items(db,record['id'],'issue');require(issues,'Add issues to the operational snag register')
        require(all(i['data'].get('_status') in ('verified','waived') for i in issues),'Verify repairs or disclose minor waivers before handover')
        s['stage']='approved';s['data']['approved_document']=snapshot(db,record,user,'handover',s);result['document_id']=s['data']['approved_document']
        return
    i=one_item(db,record['id'],data['item_id'],'issue');d=i['data'];status=d.get('_status','open')
    if action=='fixed':
        require(status in ('open','reopened'),'This issue is already fixed or verified')
        require(user['role']=='owner' or user['email']==d['assignee'],'Only the assigned operator can report the repair')
        d.update(_status='fixed',_fixed_by=user['id'],_repair_note=data['note'],_repair_file=data['file_id'])
    elif action=='verify_issue':
        require(status=='fixed','Record the repair first');require(d['_fixed_by']!=user['id'],'A different person must independently verify this repair')
        d.update(_status='verified',_verified_by=user['email'],_verification=data['note'])
    elif action=='waive':
        require(d['severity']=='Minor','Major and critical issues cannot be waived')
        require(s['stage']!='accepted','Accepted handovers cannot gain new waivers')
        d.update(_status='waived',_waiver=data['note'])
    elif action=='reopen':
        require(status in ('verified','waived'),'Only a closed issue can be reopened')
        d.update(_status='reopened',_warranty_note=data['note']);s['stage']='warranty';s['data'].pop('approved_document',None)
        if s['data'].get('acceptance'):s['data'].setdefault('previous_acceptances',[]).append(s['data'].pop('acceptance'))
        s['data'].pop('accepted_document',None)
    store_item(db,record['id'],'issue',d,user,i['id'])
    if action!='reopen':
        db.execute('UPDATE shares SET revoked_at=? WHERE document_id IN (SELECT id FROM documents WHERE record_id=?) AND accepted_at IS NULL',(now(),record['id']))
        s['data'].pop('approved_document',None);s['stage']='draft'


def stock_row(db,user,sku):
    row=db.execute('SELECT * FROM stock WHERE workspace_id=? AND sku=?',(user['workspace_id'],sku)).fetchone()
    return dict(row) if row else None


def movement(db,record,user,sku,quantity,kind,reference):
    db.execute('INSERT INTO stock_movements VALUES (?,?,?,?,?,?,?,?,?)',(uid(),user['workspace_id'],record['id'],sku,str(quantity),kind,reference,user['email'],now()))


def order_action(db,record,user,action,data,s,result):
    catalogue=items(db,record['id'],'catalogue');p=json.loads(record['payload'])
    require(s['stage'] not in ('dispatched','cancelled'),'This order is closed; create a new order')
    require(s['stage']!='reserved' or action in ('dispatch','cancel'),'Reserved orders can only be dispatched or cancelled')
    if action=='publish_catalogue':
        require(catalogue,'Add catalogue rows with units, prices, aliases and opening stock')
        for i in catalogue:
            d=i['data'];prior=stock_row(db,user,d['sku'])
            if prior: require(prior['unit'].casefold()==d['unit'].casefold(),'A SKU cannot change its inventory unit')
            # Republishing prices must never reset existing on-hand or reserved stock.
            db.execute('INSERT INTO stock VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(workspace_id,sku) DO UPDATE SET name=excluded.name,data=excluded.data,updated_at=excluded.updated_at',(user['workspace_id'],d['sku'],d['name'],d['unit'],d['stock'],'0',dump(d),now()))
        s['data']['catalogue_version']=digest([i['data'] for i in catalogue]);s['stage']='catalogue-ready'
    elif action=='parse_order':
        require(s['stage'] not in ('reserved','dispatched','cancelled'),'Order is already committed')
        rows=db.execute('SELECT * FROM stock WHERE workspace_id=? AND sku NOT LIKE \'lot:%\' AND sku NOT LIKE \'finished:%\'',(user['workspace_id'],)).fetchall()
        require(rows,'Publish a catalogue before resolving orders')
        source=items(db,record['id'],'message');text='\n'.join(i['data']['text'] for i in source) if source else p['order_text']
        parsed={};questions=[]
        for line in text.splitlines():
            if not line.strip():continue
            match=re.fullmatch(r'\s*(\d+)\s*(?:x|×)\s*(.+?)\s*',line,re.I)
            if not match: questions.append('Use explicit quantity x SKU: '+line);continue
            if len(match[1])>9:questions.append('Quantity exceeds the supported range: '+match[2]);continue
            count=int(match[1]);name=match[2].casefold();pack=False
            if name.endswith(' [pack]'):name=name[:-7].strip();pack=True
            matches=[]
            for row in rows:
                d=json.loads(row['data']);aliases=[row['sku'],row['name']]+d.get('aliases','').split(',')
                if name in {a.strip().casefold() for a in aliases if a.strip()}:matches.append((row,d))
            if len(matches)!=1:questions.append('Unknown or ambiguous product: '+match[2]);continue
            row,d=matches[0];quantity=count*(int(d['pack']) if pack else 1)
            if quantity<=0:questions.append('Quantity must be positive: '+line);continue
            item=parsed.setdefault(row['sku'],{'sku':row['sku'],'name':row['name'],'unit':row['unit'],'quantity':0,'price':d['price'],'tax':d['tax'],'price_version':digest(d)})
            item['quantity']+=quantity
        require(parsed or questions,'Enter at least one order line')
        total=0
        for item in parsed.values():
            stock=stock_row(db,user,item['sku']);available=decimal(stock['quantity'])-decimal(stock['held'])
            if item['quantity']>available:questions.append('Insufficient available stock: '+item['sku'])
            item['total_paise']=cents(amount(decimal(item['price'])*item['quantity']*(1+decimal(item['tax'])/100)));total+=item['total_paise']
        s['data']['parsed_order']={'lines':list(parsed.values()),'questions':questions,'total_paise':total,'source_hash':digest(text)}
        s['data'].pop('confirmation',None);s['stage']='clarification' if questions else 'quoted'
        result['order']=s['data']['parsed_order']
    elif action=='confirm_order':
        order=s['data'].get('parsed_order');require(order and not order['questions'] and s['stage']=='quoted','Resolve every clarification before confirmation')
        s['data']['confirmation']={'reference':data['confirmation'],'order_hash':digest(order),'by':user['email'],'at':now()};s['stage']='confirmed'
        result['document_id']=snapshot(db,record,user,'order-confirmation',s)
    elif action=='reserve':
        require(s['stage']=='confirmed','Confirm the exact order before reserving stock')
        order=s['data']['parsed_order'];require(s['data']['confirmation']['order_hash']==digest(order),'Order changed after confirmation')
        for line in order['lines']:
            row=stock_row(db,user,line['sku']);require(row and decimal(row['quantity'])-decimal(row['held'])>=line['quantity'],'Stock changed; revise and reconfirm the order')
            require(digest(json.loads(row['data']))==line['price_version'],'Catalogue changed; reprice and reconfirm the order')
            db.execute('UPDATE stock SET held=?,updated_at=? WHERE workspace_id=? AND sku=?',(str(decimal(row['held'])+line['quantity']),now(),user['workspace_id'],line['sku']))
            movement(db,record,user,line['sku'],line['quantity'],'reserve','reserve:'+record['id'])
        s['stage']='reserved'
    elif action=='dispatch':
        require(s['stage']=='reserved','Reserve stock before dispatch')
        for line in s['data']['parsed_order']['lines']:
            row=stock_row(db,user,line['sku']);q=decimal(line['quantity'])
            require(decimal(row['held'])>=q and decimal(row['quantity'])>=q,'Inventory reservation is inconsistent')
            db.execute('UPDATE stock SET quantity=?,held=?,updated_at=? WHERE workspace_id=? AND sku=?',(str(decimal(row['quantity'])-q),str(decimal(row['held'])-q),now(),user['workspace_id'],line['sku']))
            movement(db,record,user,line['sku'],-q,'dispatch','dispatch:'+record['id'])
        s['stage']='dispatched';s['data']['dispatch']={**data,'at':now()};result['document_id']=snapshot(db,record,user,'dispatch-note',s)
    elif action=='cancel':
        require(s['stage'] in ('quoted','clarification','confirmed','reserved'),'Only an open order can be cancelled')
        if s['stage']=='reserved':
            for line in s['data']['parsed_order']['lines']:
                row=stock_row(db,user,line['sku']);q=decimal(line['quantity'])
                db.execute('UPDATE stock SET held=?,updated_at=? WHERE workspace_id=? AND sku=?',(str(decimal(row['held'])-q),now(),user['workspace_id'],line['sku']))
                movement(db,record,user,line['sku'],-q,'release','cancel:'+record['id'])
        s['stage']='cancelled';s['data']['cancellation']=data


def batch_action(db,record,user,action,data,s,result):
    p=json.loads(record['payload'])
    if action=='receive_lots':
        require(not s['data'].get('production') and not s['data'].get('material_reservations'),'Receiving is closed after inputs are reserved or consumed')
        lots=items(db,record['id'],'lot');require(lots,'Add supplier lots first')
        for i in lots:
            d=i['data'];sku='lot:'+d['lot'];prior=stock_row(db,user,sku)
            if prior:
                require(json.loads(prior['data'])==d,'Lot reference is already used with different receiving details')
                continue
            require(d['quality']=='Released','Quarantined supplier lots cannot enter available stock')
            require(d['expiry']>=business_today(db,user).isoformat(),'Cannot receive an expired ingredient lot')
            db.execute('INSERT INTO stock VALUES (?,?,?,?,?,?,?,?)',(user['workspace_id'],sku,d['ingredient'],d['unit'],d['quantity'],'0',dump(d),now()))
            movement(db,record,user,sku,d['quantity'],'receive','receive:'+d['lot'])
        s['stage']='materials-ready'
    elif action=='reserve_materials':
        require(not s['data'].get('production') and not s['data'].get('material_reservations'),'Inputs are already reserved or consumed')
        usage=items(db,record['id'],'usage');require(usage,'Record planned lot quantities before reserving')
        totals={}
        for i in usage:
            d=i['data'];sku='lot:'+d['lot'];row=stock_row(db,user,sku);require(row,'Receive lot '+d['lot']+' first')
            metadata=json.loads(row['data']);require(metadata['quality']=='Released' and metadata['expiry']>=business_today(db,user).isoformat(),'Lot is quarantined or expired')
            require(row['unit'].casefold()==d['unit'].casefold(),'Reservation units must match lot units')
            totals[sku]=totals.get(sku,Decimal(0))+decimal(d['quantity'])
        for sku,q in totals.items():
            row=stock_row(db,user,sku);require(decimal(row['quantity'])-decimal(row['held'])>=q,'Insufficient unreserved quantity: '+sku)
            db.execute('UPDATE stock SET held=?,updated_at=? WHERE workspace_id=? AND sku=?',(str(decimal(row['held'])+q),now(),user['workspace_id'],sku))
            movement(db,record,user,sku,q,'reserve','batch-reserve:'+record['id']+':'+str(s['revision']))
        s['data']['material_reservations']={sku:str(q) for sku,q in totals.items()};s['stage']='materials-reserved'
    elif action=='release_materials':
        require(s['data'].get('material_reservations') and not s['data'].get('production'),'No unconsumed reservations to release')
        for sku,q in s['data']['material_reservations'].items():
            row=stock_row(db,user,sku)
            db.execute('UPDATE stock SET held=?,updated_at=? WHERE workspace_id=? AND sku=?',(str(decimal(row['held'])-decimal(q)),now(),user['workspace_id'],sku))
            movement(db,record,user,sku,-decimal(q),'release','batch-release:'+record['id']+':'+str(s['revision']))
        s['data'].pop('material_reservations');s['stage']='materials-ready'
    elif action=='produce':
        require(not s['data'].get('production'),'This batch has already consumed its lots')
        usage=items(db,record['id'],'usage');recipe=items(db,record['id'],'recipe')
        require(usage and recipe,'Add a recipe version and actual lot usage')
        versions={i['data']['version'] for i in recipe};require(len(versions)==1,'One batch must use a single recipe version')
        require(p['expiry']>=business_today(db,user).isoformat(),'Finished-batch expiry is in the past')
        total=cents(p['overhead']);consumed=[];actual={}
        for i in usage:
            d=i['data'];sku='lot:'+d['lot'];row=stock_row(db,user,sku);require(row,'Receive ingredient lot '+d['lot']+' first')
            lot=json.loads(row['data']);q=decimal(d['quantity'])
            require(row['unit'].casefold()==d['unit'].casefold(),'Consumption units must match lot units; convert explicitly before posting')
            require(lot['expiry']>=business_today(db,user).isoformat() and lot['quality']=='Released','Expired or quarantined lot cannot be consumed')
            reserved=decimal(s['data'].get('material_reservations',{}).get(sku,'0'))
            require(decimal(row['quantity'])-decimal(row['held'])+reserved>=q,'Insufficient available lot quantity: '+d['lot'])
            require(any(r['data']['ingredient'].casefold()==lot['ingredient'].casefold() and r['data']['unit'].casefold()==row['unit'].casefold() for r in recipe),'Consumed ingredient / unit is not in the selected recipe')
            cost=cents(amount(q*decimal(lot['cost'])));total+=cost
            released=min(q,reserved)
            db.execute('UPDATE stock SET quantity=?,held=?,updated_at=? WHERE workspace_id=? AND sku=?',(str(decimal(row['quantity'])-q),str(decimal(row['held'])-released),now(),user['workspace_id'],sku))
            if reserved:s['data']['material_reservations'][sku]=str(reserved-released)
            movement(db,record,user,sku,-q,'consume','produce:'+record['id']+':'+i['id'])
            consumed.append({**d,'ingredient':lot['ingredient'],'cost_paise':cost,'supplier':lot['supplier']})
            key=(lot['ingredient'].casefold(),row['unit'].casefold());actual[key]=actual.get(key,Decimal(0))+q
        variance=[]
        for i in recipe:
            r=i['data'];q=actual.get((r['ingredient'].casefold(),r['unit'].casefold()),Decimal(0))
            require(q>0,'Missing actual consumption for recipe ingredient '+r['ingredient'])
            variance.append({'ingredient':r['ingredient'],'unit':r['unit'],'planned':r['quantity'],'actual':str(q),'variance':str(q-decimal(r['quantity']))})
        sku='finished:'+p['batch_number'];require(not stock_row(db,user,sku),'Finished batch number already exists')
        db.execute('INSERT INTO stock VALUES (?,?,?,?,?,?,?,?)',(user['workspace_id'],sku,p['product'],'unit',p['produced_units'],p['produced_units'],dump({'quality':'Quarantined','record_id':record['id'],'expiry':p['expiry']}),now()))
        s['data']['production']={'inputs':consumed,'recipe_version':next(iter(versions)),'variance':variance,'total_paise':total,'unit_cost_paise':int((Decimal(total)/int(p['produced_units'])).quantize(Decimal(1))),'produced_by':user['id'],'at':now()};s['stage']='produced'
        s['data'].pop('material_reservations',None)
        result['document_id']=snapshot(db,record,user,'batch-manufacturing-record',s)
    elif action=='return_material':
        require(s['data'].get('production'),'Record production before returning unused material')
        original=[i for i in s['data']['production']['inputs'] if i['lot']==data['lot']];require(original,'This lot was not consumed by this batch')
        returned=sum(decimal(i['quantity']) for i in s['data'].get('returns',[]) if i['lot']==data['lot'])
        q=decimal(data['quantity']);require(q+returned<=sum(decimal(i['quantity'])-decimal(i['waste']) for i in original),'Return exceeds original non-waste consumption')
        sku='lot:'+data['lot'];row=stock_row(db,user,sku)
        movement(db,record,user,sku,q,'return','return:'+data['reference'])
        db.execute('UPDATE stock SET quantity=?,updated_at=? WHERE workspace_id=? AND sku=?',(str(decimal(row['quantity'])+q),now(),user['workspace_id'],sku))
        adjustment={**data,'by':user['email'],'at':now(),'cost_reduction_paise':cents(amount(q*decimal(json.loads(row['data'])['cost'])))}
        s['data'].setdefault('returns',[]).append(adjustment)
        result['document_id']=snapshot(db,record,user,'material-return-adjustment',s,adjustment)
    elif action=='quality_release':
        require(s['stage']=='produced','Record production before quality release')
        s['data']['quality']={**data,'by':user['email'],'at':now()};s['stage']='released'
        sku='finished:'+p['batch_number'];row=stock_row(db,user,sku);metadata=json.loads(row['data']);metadata['quality']='Released'
        db.execute('UPDATE stock SET held=\'0\',data=?,updated_at=? WHERE workspace_id=? AND sku=?',(dump(metadata),now(),user['workspace_id'],sku))
        result['document_id']=snapshot(db,record,user,'batch-release-and-label',s)
    elif action=='quality_reject':
        require(s['stage']=='produced','Quality rejection applies to produced output awaiting release')
        s['stage']='rejected';s['data']['quality_rejection']={**data,'by':user['email'],'at':now()}
        result['document_id']=snapshot(db,record,user,'quality-rejection',s)
    elif action in ('trace','recall'):
        require(s['data'].get('production'),'Produce the batch first')
        traced=[]
        for lot in s['data']['production']['inputs']:
            rows=db.execute("SELECT DISTINCT r.id,r.title FROM stock_movements m JOIN records r ON r.id=m.record_id WHERE m.workspace_id=? AND m.sku=? AND m.kind='consume'",(user['workspace_id'],'lot:'+lot['lot'])).fetchall()
            traced.append({'lot':lot['lot'],'affected_batches':[dict(r) for r in rows]})
        s['data']['trace']={'inputs':traced,'destinations':[i['data'] for i in items(db,record['id'],'dispatch')]}
        if action=='recall':
            s['stage']='recalled';s['data']['recall']={**data,'at':now()}
            sku='finished:'+p['batch_number'];row=stock_row(db,user,sku);metadata=json.loads(row['data']);metadata['quality']='Recalled'
            db.execute('UPDATE stock SET held=quantity,data=? WHERE workspace_id=? AND sku=?',(dump(metadata),user['workspace_id'],sku))
        result['document_id']=snapshot(db,record,user,'recall-report' if action=='recall' else 'traceability-report',s)


def notice_date(record,terms):
    p=json.loads(record['payload']);day=date.fromisoformat(p['renewal']);remaining=int(p['notice_days'])
    d=terms[0]['data'] if terms else {};holidays=set(d.get('holidays','').splitlines())
    while remaining:
        day-=timedelta(days=1)
        if d.get('business_days')!='Yes' or (day.weekday()<5 and day.isoformat() not in holidays):remaining-=1
    return day.isoformat()


def renew_action(db,record,user,action,data,s,result):
    p=json.loads(record['payload']);terms=items(db,record['id'],'terms')
    s['data']['notice_date']=notice_date(record,terms)
    s['data']['actual_spend_paise']=sum(cents(i['data']['amount']) for i in items(db,record['id'],'invoice'))
    if action in ('plan_reminders','acknowledge_notice'):
        from .renewals import renewal_command
        renewal_command(db,record,user,action,s,result)
    elif action=='decide':
        require(terms,'Add the actual contract terms and responsible owners')
        require(s['stage'] not in ('cancellation-requested','vendor-confirmed'),'Resolve the existing cancellation workflow first')
        s['data']['decision']={**data,'approved_by':user['email'],'at':now()};s['stage']='decision-approved'
        result['document_id']=snapshot(db,record,user,'renewal-decision',s)
    elif action=='request_cancel':
        require(s['data'].get('decision',{}).get('decision')=='Cancel' and s['stage']=='decision-approved','Approve a cancellation decision first')
        s['stage']='cancellation-requested';s['data']['cancel_request']={**data,'at':now()}
    elif action=='confirm_cancel':
        require(s['stage']=='cancellation-requested','Record the cancellation request first')
        s['stage']='vendor-confirmed';s['data']['cancel_confirmation']={**data,'at':now()}
    elif action=='rollover':
        require(s['data'].get('decision',{}).get('decision')=='Renew','Approve renewal before creating a new term')
        require(data['renewal']>p['renewal'],'New renewal must be after the current renewal date')
        require(not s['data'].get('next_term'),'A next term has already been created')
        result['record_id']=clone_record(db,record,user,{**p,'renewal':data['renewal'],'cost':data['cost'],'decision':'Undecided'},record['title']+' · next term')
        for term in terms:
            copied={**term['data'],'file_id':'','_carried_from':record['id']}
            store_item(db,result['record_id'],'terms',copied,user)
        db.execute('INSERT INTO operations(record_id,data) VALUES (?,?)',(result['record_id'],dump({'previous_term':record['id']})))
        s['data']['renewal_confirmation']={'file_id':data['file_id'],'confirmed_by':user['email'],'at':now()}
        s['data']['next_term']=result['record_id'];s['stage']='completed'
    elif action=='calendar': result['calendar_url']=f'/api/records/{record["id"]}/calendar.ics'


def sop_action(db,record,user,action,data,s,result):
    if action=='publish':
        require(s['stage']=='draft','Only a new draft procedure can be published')
        steps=items(db,record['id'],'step');require(len(steps)>=2,'Add at least two procedure steps')
        positions=[int(i['data']['position']) for i in steps];require(len(set(positions))==len(positions),'Step numbers must be unique')
        require(json.loads(record['payload'])['hazards'].strip(),'Review and record safety hazards before publication')
        s['stage']='published';s['data']['publication']={**data,'by':user['email'],'at':now()}
        s['data']['published_document']=snapshot(db,record,user,'published-procedure',s)
        previous=s['data'].get('previous_revision')
        if previous:
            old=get_state(db,previous);old['stage']='superseded';old['data']['superseded_by']=s['data']['published_document']
            oldrecord=dict(db.execute('SELECT * FROM records WHERE id=?',(previous,)).fetchone())
            event(db,oldrecord,user,'publication.superseded',{'new_record':record['id'],'document_id':s['data']['published_document']},old)
        result['document_id']=s['data']['published_document']
    else:
        require(s['stage']=='published' and s['data'].get('published_document'),'Publish the procedure first')
        assignment=next((i for i in items(db,record['id'],'assignment') if i['data']['employee']==user['email']),None)
        require(assignment,'You must be assigned to this procedure to acknowledge or take its assessment')
        d=assignment['data'];doc=s['data']['published_document']
        if action=='acknowledge':
            d.update(_ack_document=doc,_acknowledged_at=now(),_acknowledged_by=user['id']);result['document_id']=doc
        elif action=='assess':
            require(d.get('_ack_document')==doc,'Acknowledge this published version before assessment')
            questions=items(db,record['id'],'question');require(questions,'No quiz has been approved for this procedure')
            answers={a['question_id']:a['answer'] for a in data['answers']};require(len(answers)==len(data['answers']) and set(answers)=={q['id'] for q in questions},'Answer every approved question exactly once')
            normalize=lambda v:' '.join(v.casefold().split())
            correct=sum(normalize(answers[q['id']])==normalize(q['data']['answer']) for q in questions)
            score=100*correct//len(questions);passed=score>=int(s['data']['publication']['pass_percent'])
            attempt={'document_id':doc,'score':score,'passed':passed,'at':now()}
            d.setdefault('_attempts',[]).append(attempt);d['_training_status']='passed' if passed else 'retraining-required';result.update(attempt)
        store_item(db,record['id'],'assignment',d,user,assignment['id'])


def claim_action(db,record,user,action,data,s,result):
    if action=='verify_evidence':
        i=one_item(db,record['id'],data['item_id'],'evidence');d=i['data']
        f=db.execute('SELECT * FROM files WHERE id=? AND record_id=?',(d['file_id'],record['id'])).fetchone()
        require(f and f['extraction_status']!='unreadable','Upload readable evidence before verifying')
        d.update(_verified=True,_verified_by=user['email'],_note=data['note']);store_item(db,record['id'],'evidence',d,user,i['id'])
    elif action=='pack':
        require(s['stage'] not in ('submitted','won','lost','withdrawn'),'Submitted packets are immutable')
        templates=items(db,record['id'],'template');require(templates,'Add provider-specific requirements and their source')
        t=templates[0]['data'];require(t['deadline']>now(),'The provider deadline has passed')
        evidence=items(db,record['id'],'evidence');require(evidence and all(i['data'].get('_verified') for i in evidence),'Verify every evidence item')
        required={v.strip().casefold() for v in t['required_kinds'].splitlines() if v.strip()};available={i['data']['kind'].casefold() for i in evidence}
        require(required and required<=available,'Missing required evidence categories: '+', '.join(sorted(required-available)))
        require(items(db,record['id'],'timeline'),'Add a factual, evidence-linked timeline')
        file_ids={i['data']['file_id'] for i in evidence};size=sum(db.execute('SELECT size FROM files WHERE id=?',(f,)).fetchone()[0] for f in file_ids)
        require(size<int(t['max_mb'])*1024*1024,'Evidence files exceed the provider size limit')
        s['stage']='packed';s['data']['packet_document']=snapshot(db,record,user,'claim-packet',s);result['document_id']=s['data']['packet_document']
    elif action=='submission':
        require(s['stage']=='packed' and s['data'].get('packet_document'),'Freeze the evidence packet before recording submission')
        s['stage']='submitted';s['data']['submission']={**data,'document_id':s['data']['packet_document'],'at':now()}
    elif action=='outcome':
        require(s['stage']=='submitted','Record the provider submission before its outcome')
        s['stage']=data['result'].lower();s['data']['outcome']={**data,'at':now()}


def view(db,record,user):
    s=get_state(db,record['id']);allitems=items(db,record['id'])
    if user['role'] not in ('owner','reviewer'):
        for i in allitems:
            if i['kind']=='question': i['data'].pop('answer',None)
    if record['product']=='sop':
        for i in allitems:
            if i['kind']=='assignment':
                i['data']['_current']=s['stage']=='published' and i['data'].get('_ack_document')==s['data'].get('published_document') and bool(s['data'].get('published_document'))
    files=[dict(r) for r in db.execute('SELECT f.id,f.name,f.mime,f.size,f.checksum,f.extracted,f.extraction_status,f.created_at,c.scan_status,c.retain_until,c.deleted_at FROM files f LEFT JOIN file_controls c ON c.file_id=f.id WHERE f.record_id=? ORDER BY f.created_at DESC',(record['id'],))]
    docs=[dict(r) for r in db.execute('SELECT id,kind,number,checksum,record_version,revision,created_by,created_at FROM documents WHERE record_id=? ORDER BY created_at DESC',(record['id'],))]
    events=[{**dict(r),'data':json.loads(r['data'])} for r in db.execute('SELECT * FROM operation_events WHERE record_id=? ORDER BY id DESC LIMIT 200',(record['id'],))]
    if record['product']=='sop' and user['role'] not in ('owner','reviewer'):
        events=[e for e in events if e['action'] not in ('question.created','question.updated','assess')]
    jobs=[]
    for row in db.execute('SELECT * FROM jobs WHERE record_id=? ORDER BY created_at DESC',(record['id'],)):
        job={k:v for k,v in dict(row).items() if k!='data'};stored=json.loads(row['data']);delivery=stored.get('result',{})
        job['result']={k:v for k,v in delivery.items() if k!='provider'}
        if delivery.get('provider'):job['result']['payment_url']=delivery['provider'].get('short_url');job['result']['provider_id']=delivery['provider'].get('id')
        if stored.get('unallocated_payments'):job['unallocated_payments']=stored['unallocated_payments']
        jobs.append(job)
    shares=[dict(r) for r in db.execute('SELECT s.id,s.document_id,s.recipient,s.purpose,s.expires_at,s.revoked_at,s.accepted_at,s.accepted_name,c.decision FROM shares s JOIN documents d ON d.id=s.document_id LEFT JOIN share_decisions c ON c.share_id=s.id WHERE d.record_id=?',(record['id'],))]
    overview={}
    if record['product'] in ('collect','fees'):
        overview=financial(db,record);overview['reminder_pause']=reminder_blocker(db,record)
    elif record['product']=='amc':
        p=json.loads(record['payload']);verified=sum(i['data'].get('_status')=='verified' and i['data']['chargeable']=='No' for i in allitems if i['kind']=='visit')
        overview={'included_visits_remaining':int(p['included'])-int(p['completed'])-verified,'verified_this_period':verified}
    elif record['product']=='renew':
        overview={'notice_date':notice_date(record,items(db,record['id'],'terms')),'actual_spend_paise':sum(cents(i['data']['amount']) for i in items(db,record['id'],'invoice'))}
        current=items(db,record['id'],'subscription');terms=items(db,record['id'],'terms')
        if current and terms:
            overview['verified_unused_seats']=max(0,int(terms[0]['data']['seats'])-int(current[0]['data']['active_seats']))
            overview['usage_verified_on']=current[0]['data']['verified_on']
    return {'revision':s['revision'],'stage':s['stage'],'data':s['data'],'definition':SPECS[record['product']],'items':allitems,'files':files,'documents':docs,'events':events,'jobs':jobs,'shares':shares,'overview':overview,'role':user['role']}
