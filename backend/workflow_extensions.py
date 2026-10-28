"""Versioned follow-up workflows, executed inside the caller's write transaction."""
import csv
import io
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from difflib import SequenceMatcher

from . import operations as op
from .domain import amount, decimal
from .migrations import permit, invalidate


def singleton(db, record, kind):
    rows = op.items(db, record['id'], kind)
    return rows[0]['data'] if rows else {}


def validate_resource(db, record, user, kind, data, item_id):
    slug = record['product']
    if slug == 'amc' and kind == 'asset':
        maker = data.get('manufacturer', '').casefold()
        rows = db.execute("SELECT i.id,i.data,i.record_id FROM operation_items i JOIN record_workspaces w ON w.record_id=i.record_id JOIN records r ON r.id=i.record_id WHERE w.workspace_id=? AND r.product='amc' AND i.kind='asset'", (user['workspace_id'],)).fetchall()
        for row in rows:
            prior = json.loads(row['data'])
            if row['id'] != item_id and prior['serial'].casefold() == data['serial'].casefold() and prior.get('manufacturer', '').casefold() == maker:
                op.require(prior.get('_renewed_asset') == data.get('_renewed_asset') and bool(data.get('_renewed_asset')), 'This manufacturer and serial already identify an asset in this workspace')
    if slug == 'amc' and kind == 'visit':
        start, end = data.get('window_start'), data.get('window_end')
        op.require(bool(start) == bool(end), 'Provide both customer-window times')
        if start:
            data['window_start'], data['window_end'] = op.instant(start), op.instant(end)
            op.require(data['window_start'] <= op.instant(data['start']) < op.instant(data['end']) <= data['window_end'], 'The visit must fit inside the customer service window')
    if slug == 'amc' and kind == 'plan':
        op.require(not op.items(db, record['id'], 'visit'), 'A plan with scheduled service is frozen; use a renewed period')
    if slug == 'collect' and kind == 'promise':
        if data['kind'] == 'Promise':
            op.require(data.get('until'), 'A payment promise needs a date')
        if data.get('amount'):
            op.require(0 < op.cents(data['amount']) <= max(0, op.financial(db, record)['balance_paise']), 'Case amount must fit the outstanding balance')
        if data.get('owner'):
            op.require(db.execute('SELECT 1 FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=? AND u.email=?', (user['workspace_id'], data['owner'])).fetchone(), 'Case owner must be a workspace member')
    if slug == 'collect' and kind == 'cadence':
        cadence_days(data)
        op.require(int(data['start_hour']) < int(data['end_hour']), 'Working hours must increase')
    if slug == 'rfq' and kind == 'clarification':
        op.require(any(i['data']['supplier'] == data['supplier'] for i in op.items(db, record['id'], 'offer')), 'Choose a quoted supplier')
    if slug == 'rfq' and kind == 'offer' and data.get('quoted_on') and data.get('valid_until'):
        op.require(data['quoted_on']<=data['valid_until'],'Quote validity cannot end before its issue date')
    if slug == 'tender' and kind == 'deadline' and data.get('clarification_at'):
        data['clarification_at'] = op.instant(data['clarification_at'])
        op.require(data['clarification_at'] <= op.instant(data['at']), 'Clarification must close no later than submission')
    if slug == 'tender' and kind == 'requirement' and data.get('interpretation') == 'Conditional':
        op.require(data.get('condition'), 'Describe the applicability condition')
    if slug == 'batch' and kind == 'recipe':
        if data.get('effective_from') and data.get('effective_until'):
            op.require(data['effective_from'] <= data['effective_until'], 'Recipe effective dates must increase')
    if slug == 'batch' and kind == 'cost':
        op.require(not any(i['id'] != item_id and i['data']['reference'] == data['reference'] for i in op.items(db, record['id'], kind)), 'Cost reference already exists')
    if slug == 'fees' and kind == 'late_policy':
        permit(user, 'owner', 'reviewer')
        op.require(not op.get_state(db, record['id'])['data'].get('late_assessments'), 'Assessed policies are immutable; use an explicit financial adjustment')
    if slug == 'renew' and kind == 'terms' and data.get('term_start'):
        op.require(data['term_start'] < json.loads(record['payload'])['renewal'], 'Term start must precede renewal')
    if slug == 'sop' and kind == 'publication_policy':
        op.require(db.execute("SELECT 1 FROM memberships m JOIN users u ON m.user_id=u.id WHERE m.workspace_id=? AND u.email=? AND m.role IN ('owner','reviewer')", (user['workspace_id'], data['supervisor'])).fetchone(), 'Supervisor must be a current owner or reviewer')
    if slug == 'sop' and kind == 'branch':
        op.require(len({data['step_id'], data['yes_step'], data['no_step']}) == 3, 'Decision and destination steps must differ')
        source = int(op.one_item(db, record['id'], data['step_id'], 'step')['data']['position'])
        op.require(all(int(op.one_item(db, record['id'], data[k], 'step')['data']['position']) > source for k in ('yes_step','no_step')), 'Branches must move forward to avoid procedure loops')
    if slug == 'claimpack' and kind == 'template' and data.get('reviewed_on'):
        op.require(data['reviewed_on'] <= op.business_today(db,user).isoformat(), 'Template review cannot be in the future')


def before_action(db,r,u,a,d,s):
    if r['product']=='amc' and a in ('start_visit','complete_visit'):
        from .authority_adapters import require_current_booking
        require_current_booking(op.one_item(db,r['id'],d['item_id'],'visit')['data'])
    if r['product']=='rfq' and a in ('compare','award','quote_revision','comparison_export') and s['data'].get('comparison'):
        history=s['data'].setdefault('comparison_history',[])
        previous=s['data']['comparison']
        if not history or history[-1]['comparison']!=previous:
            history.append({'comparison':previous,'at':op.now(),'before_action':a,'by':u['email']})
    if r['product']=='orderdesk' and a=='dispatch':
        op.require(not s['data'].get('reservation_expires_at') or s['data']['reservation_expires_at']>op.now(),'Reservation expired; wait for release, then reprice and confirm')
    if r['product']=='renew' and a=='confirm_cancel' and d.get('effective'):
        terms=singleton(db,r,'terms')
        op.require(not terms.get('term_start') or d['effective']>=terms['term_start'],'Cancellation cannot predate the contract term')
    if r['product']=='sop' and a in ('acknowledge','assess'):
        policy=singleton(db,r,'publication_policy')
        if policy:op.require(policy['effective']<=op.business_today(db,u).isoformat(),'Procedure is not yet effective')
    if r['product']=='claimpack' and a=='pack':
        for evidence in op.items(db,r['id'],'evidence'):
            value=evidence['data']
            if value.get('redaction'):
                approved=value.get('_approved_redaction')
                op.require(approved and approved['original_file_id']==value['file_id'],'Upload and approve a redacted copy for each evidence item marked for redaction')
        analysis=timeline_analysis(db,r)
        for conflict in analysis['conflicts']:
            resolved=s['data'].get('conflict_resolutions',{}).get(conflict['event_reference'])
            op.require(resolved and resolved['source_hash']==analysis['source_hash'],'Resolve conflicting event dates against the current timeline before freezing')
        template=singleton(db,r,'template')
        if template.get('reviewed_on'):op.require(not analysis['missing_provenance'],'Record the source of each factual statement before freezing')


def after_action(db,r,u,a,d,s):
    if r['product']=='orderdesk' and a=='reserve' and not s['data'].get('inventory_reference'):
        policy=singleton(db,r,'delivery')
        hours=int(policy.get('hold_hours',24))
        s['data']['reservation_expires_at']=(datetime.now(timezone.utc)+timedelta(hours=hours)).isoformat()
    if r['product']=='orderdesk' and a=='parse_order':
        policy=singleton(db,r,'delivery');order=s['data'].get('parsed_order')
        if order and policy:
            freight=op.cents(amount(decimal(policy['freight'])*(1+decimal(policy['tax'])/100)))
            order['freight_paise']=freight;order['total_paise']+=freight
    if r['product']=='sop' and a=='publish':
        # Content fingerprints let offline-copy checks detect later supersession.
        s['data']['content_hash']=op.digest([i['data'] for i in op.items(db,r['id']) if i['kind'] not in ('assignment',)])


def periodic(db):
    rows=db.execute("SELECT r.*,w.workspace_id FROM records r JOIN record_workspaces w ON w.record_id=r.id JOIN operations o ON o.record_id=r.id WHERE r.product='orderdesk' AND o.stage='reserved'").fetchall()
    for row in rows:
        r=dict(row);s=op.get_state(db,r['id']);expiry=s['data'].get('reservation_expires_at')
        if not expiry or expiry>op.now():continue
        if s['data'].get('inventory_reference'):continue
        u={'workspace_id':r['workspace_id'],'email':'reservation-worker'}
        for line in s['data']['parsed_order']['lines']:
            stock=op.stock_row(db,u,line['sku']);quantity=decimal(line['quantity'])
            op.require(stock and decimal(stock['held'])>=quantity,'Reservation release found inconsistent inventory')
            db.execute('UPDATE stock SET held=?,updated_at=? WHERE workspace_id=? AND sku=?',(str(decimal(stock['held'])-quantity),op.now(),u['workspace_id'],line['sku']))
            op.movement(db,r,u,line['sku'],-quantity,'release','expiry:'+r['id']+':'+str(s['revision']))
        s['stage']='reservation-expired';s['data'].pop('confirmation',None)
        op.event(db,r,u,'reservation.expired',{'expired_at':expiry},s)
    rows=db.execute("SELECT r.*,w.workspace_id FROM records r JOIN record_workspaces w ON w.record_id=r.id JOIN operations o ON o.record_id=r.id WHERE r.product='sop' AND r.status!='archived' AND o.stage='published'").fetchall()
    for row in rows:
        r=dict(row);s=op.get_state(db,r['id']);policy=s['data'].get('new_hire_policy',{})
        if policy.get('enabled')!='Yes':continue
        owner=db.execute("SELECT u.id,u.email FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=? AND m.role='owner' ORDER BY u.id LIMIT 1",(r['workspace_id'],)).fetchone()
        if not owner:continue
        u={**dict(owner),'workspace_id':r['workspace_id']};existing={x['data']['employee'] for x in op.items(db,r['id'],'assignment')};added=[]
        due=(op.business_today(db,u)+timedelta(days=int(policy['due_days']))).isoformat()
        for member in db.execute('SELECT u.email FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=?',(r['workspace_id'],)):
            if member['email'] not in existing:
                op.store_item(db,r['id'],'assignment',{'employee':member['email'],'due':due,'_enrolled_by_policy':True},u);added.append(member['email'])
        if added:op.event(db,r,{'email':'training-worker'},'training.enrolled',{'employees':added,'due':due},s)


def training_blocker(db,r,data):
    s=op.get_state(db,r['id'])
    if s['stage']!='published' or s['data'].get('published_document')!=data.get('document_id'):return 'Procedure was superseded or retired'
    rows=op.items(db,r['id'],'assignment');assignment=next((x for x in rows if x['id']==data.get('assignment_id')),None)
    if not assignment or assignment['data']['employee']!=data.get('recipient'):return 'Training assignment changed'
    value=assignment['data']
    workspace=db.execute('SELECT workspace_id FROM record_workspaces WHERE record_id=?',(r['id'],)).fetchone()[0]
    if not db.execute('SELECT 1 FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=? AND u.email=?',(workspace,value['employee'])).fetchone():return 'Staff member left the workspace'
    if value.get('_ack_document')==data['document_id'] and (not op.items(db,r['id'],'question') or value.get('_training_status')=='passed'):return 'Training is already complete'
    return None


def cadence_days(policy):
    try:
        values = [int(x.strip()) for x in policy['days'].split(',')]
        op.require(values and len(values) <= 20 and len(values) == len(set(values)) and all(0 <= n <= 3650 for n in values), 'Use up to twenty distinct offsets from 0 to 3650 days')
        return sorted(values)
    except ValueError:
        op.fail('Reminder offsets must be comma-separated whole days')


def contact_blocker(db, record, data, exclude=None, when=None):
    if record['product'] != 'collect': return None
    policy = singleton(db, record, 'cadence')
    if not policy: return None
    if policy['consent'] != 'Yes' or data.get('recipient') != policy['recipient']: return 'Customer consent or recipient changed'
    target = datetime.fromisoformat(when or op.now())
    count = 0
    for row in db.execute("SELECT * FROM jobs WHERE workspace_id=? AND kind='email' AND state NOT IN ('blocked','dead-letter')", (db.execute('SELECT workspace_id FROM record_workspaces WHERE record_id=?',(record['id'],)).fetchone()[0],)):
        prior = json.loads(row['data'])
        if row['id'] == exclude or prior.get('recipient') != data.get('recipient'): continue
        sent = datetime.fromisoformat(row['updated_at'] if row['state'] == 'delivered' else row['due_at'])
        if abs((target - sent).total_seconds()) < int(policy['minimum_hours']) * 3600: return 'Customer contact-frequency limit'
        if target - timedelta(days=7) < sent <= target: count += 1
    if count >= int(policy['weekly_limit']): return 'Customer weekly contact limit'
    return None


def scope(db,r,u,a,d,s,out):
    if a == 'import_contract':
        op.require(s['stage']=='draft','Import source clauses into a draft before approval')
        out['job_id']=op.enqueue(db,r,u,'contracts-import',{'contract_id':d['contract_id'],'revision':s['revision']+1,'version':r['version'],'user_id':u['id']},'contract-import:'+r['id']+':'+str(s['revision']))
    elif a == 'compare_baseline':
        clauses = op.items(db,r['id'],'baseline'); op.require(clauses, 'Add cited baseline clauses first')
        request = json.loads(r['payload'])['request']
        words = set(re.findall(r'\w{3,}', request.casefold()))
        comparisons = []
        for item in clauses:
            clause = item['data']; shared = sorted(words & set(re.findall(r'\w{3,}', clause['text'].casefold())))
            comparisons.append({'baseline_id':item['id'],'reference':clause['reference'],'file_id':clause['file_id'], 'text':clause['text'],'shared_terms':shared,'text_similarity':round(SequenceMatcher(None,request.casefold(),clause['text'].casefold()).ratio(),3)})
        result = {'request':request,'clauses':comparisons,'unmatched_terms':sorted(words - {w for c in comparisons for w in c['shared_terms']}), 'uncertainty':'Text similarity does not establish contractual coverage. Review quantities, exclusions, revision limits and dependencies.', 'source_hash':op.digest({'request':request,'clauses':[i['data'] for i in clauses]}),'review':None}
        s['data']['baseline_comparison'] = result; out['comparison'] = result
    elif a == 'review_comparison':
        comparison = s['data'].get('baseline_comparison'); op.require(comparison, 'Run a baseline comparison first')
        current = op.digest({'request':json.loads(r['payload'])['request'],'clauses':[i['data'] for i in op.items(db,r['id'],'baseline')]})
        op.require(comparison['source_hash'] == current, 'Baseline changed; compare it again')
        comparison['review'] = {**d,'by':u['email'],'at':op.now()}
    else: return False
    return True


def collect(db,r,u,a,d,s,out):
    if a == 'resolve_case':
        item = op.one_item(db,r['id'],d['item_id'],'promise'); value = item['data']
        op.require(not value.get('_outcome'), 'This case already has an outcome')
        allowed = ('Kept','Broken','Withdrawn') if value['kind'] == 'Promise' else ('Resolved','Withdrawn') if value['kind'] == 'Dispute' else ()
        op.require(d['outcome'] in allowed, 'Outcome does not apply to this case type')
        value.update(_outcome={**d,'at':op.now(),'by':u['email']})
        op.store_item(db,r['id'],'promise',value,u,item['id'])
    elif a == 'schedule_sequence':
        policy = singleton(db,r,'cadence'); op.require(policy, 'Configure a reminder sequence first')
        op.require(policy['consent'] == 'Yes', 'Customer consent is required')
        due = date.fromisoformat(json.loads(r['payload'])['due']); out['jobs'] = []
        from zoneinfo import ZoneInfo
        zone = ZoneInfo(db.execute('SELECT timezone FROM workspaces WHERE id=?',(u['workspace_id'],)).fetchone()[0])
        for offset in cadence_days(policy):
            local = datetime.combine(due + timedelta(days=offset), datetime.min.time(), zone).replace(hour=int(policy['start_hour']))
            while local.weekday() >= 5: local += timedelta(days=1)
            when = local.astimezone(timezone.utc).isoformat()
            if when <= op.now(): continue
            payload = {k:policy[k] for k in ('recipient','subject','message','start_hour','end_hour','consent')}; payload['due_at'] = when
            reason = contact_blocker(db,r,payload,when=when)
            if reason: out.setdefault('skipped',[]).append({'due_at':when,'reason':reason}); continue
            out['jobs'].append(op.schedule_reminder(db,r,u,payload))
        op.require(out['jobs'], 'No eligible future contacts; revise offsets or resolve the contact limit')
    elif a == 'delivery_receipt':
        job = db.execute("SELECT * FROM jobs WHERE id=? AND record_id=? AND workspace_id=? AND kind='email'",(d['job_id'],r['id'],u['workspace_id'])).fetchone()
        op.require(job and job['state'] in ('delivered','blocked'), 'Reconcile an attempted delivery for this record')
        history = s['data'].setdefault('delivery_receipts',[])
        op.require(not any(x['reference'] == d['reference'] for x in history), 'Provider event already reconciled')
        history.append({**d,'at':op.now(),'by':u['email']})
        if d['status'] in ('Bounced','Complaint'):
            op.store_item(db,r['id'],'promise',{'kind':'Opt out','until':'','note':'Delivery '+d['status']+': '+d['reference']},u)
            db.execute("UPDATE jobs SET state='blocked',last_error='Contact suspended after delivery reconciliation' WHERE record_id=? AND kind='email' AND state IN ('queued','failed')",(r['id'],))
    elif a == 'customer_statement': out['document_id'] = op.snapshot(db,r,u,'customer-history-statement',s)
    else: return False
    return True


def amc(db,r,u,a,d,s,out):
    if a == 'start_visit':
        item=op.one_item(db,r['id'],d['item_id'],'visit');value=item['data']
        op.require(value['technician']==u['email'],'Only the assigned technician may start the visit')
        op.require(value.get('_status','scheduled')=='scheduled' and not value.get('_started_at'),'Visit was already started or completed')
        op.require(value['start']<=op.now(),'Cannot start a future visit')
        value.update(_started_at=op.now(),_before_file=d['file_id'],_initial_condition=d['notes'])
        op.store_item(db,r['id'],'visit',value,u,item['id'])
    elif a == 'service_readings':
        item = op.one_item(db,r['id'],d['item_id'],'visit'); value = item['data']
        op.require(value['technician'] == u['email'], 'Only the assigned technician may record readings')
        op.require(value.get('_status','scheduled') == 'scheduled', 'Completed visit readings are immutable')
        required = {x.strip().casefold() for x in value['checklist'].splitlines() if x.strip()}
        actual = [x['check'].casefold() for x in d['readings']]
        op.require(required <= set(actual) and len(actual) == len(set(actual)), 'Complete each required check once')
        value['_readings'] = {**d,'by':u['email'],'at':op.now()}; op.store_item(db,r['id'],'visit',value,u,item['id'])
    elif a == 'renewal_offer':
        p = json.loads(r['payload'])
        op.require(d['start'] > p['end'] and d['end'] >= d['start'], 'New period must follow the existing contract')
        op.require(d['valid_until'] >= op.business_today(db,u).isoformat(), 'Offer has already expired')
        op.require(not s['data'].get('activated_renewal'), 'The renewal was already activated')
        s['data'].pop('renewal_accepted',None)
        s['data']['renewal_offer'] = {**d,'by':u['email'],'at':op.now()}
        out['document_id'] = op.snapshot(db,r,u,'amc-renewal-offer',s, d)
        s['data']['renewal_offer_document'] = out['document_id']
        db.execute('UPDATE shares SET revoked_at=? WHERE document_id IN (SELECT id FROM documents WHERE record_id=? AND kind=?) AND accepted_at IS NULL',(op.now(),r['id'],'amc-renewal-offer'))
    elif a == 'activate_renewal':
        offer = s['data'].get('renewal_offer'); op.require(offer and s['data'].get('renewal_accepted') == s['data'].get('renewal_offer_document'), 'Customer must accept the current renewal offer')
        op.require(not s['data'].get('activated_renewal'), 'Renewal already activated')
        p = json.loads(r['payload']); new = op.clone_record(db,r,u,{**p,'start':offer['start'],'end':offer['end'],'contract_value':offer['value'],'included':offer['included'],'completed':'0','next_visit':''},r['title']+' · accepted renewal')
        for item in op.items(db,r['id'],'asset'):
            op.store_item(db,new,'asset',{**item['data'],'_renewed_asset':item['data'].get('_renewed_asset',item['id'])},u)
        out['record_id'] = new; s['data']['activated_renewal'] = new
        out['document_id'] = op.snapshot(db,r,u,'draft-invoice',s,{'total_paise':op.cents(offer['value']),'renewal_record':new,'accepted_document':s['data']['renewal_accepted']})
        out['job_id'] = op.enqueue(db,r,u,'invoice',{'document_id':out['document_id']},'amc-renewal:'+new)
    else: return False
    return True


def rfq(db,r,u,a,d,s,out):
    if a == 'quote_revision':
        op.require(s['stage'] != 'awarded', 'Awarded quotes are immutable; create a new procurement revision')
        item = op.one_item(db,r['id'],d['item_id'],'offer'); previous = item['data']
        updated = {**previous, **{k:d[k] for k in ('price','discount','freight','lead_days','file_id')}}
        op.store_item(db,r['id'],'offer',updated,u,item['id'])
        s['data'].setdefault('quote_revisions',[]).append({'item_id':item['id'],'before':previous,'after':updated,'reason':d['reason'],'by':u['email'],'at':op.now()})
        s['data'].pop('comparison',None); s['stage'] = 'draft'
    elif a == 'comparison_export':
        s['data']['comparison'] = op.compare_quotes(db,r)
        out['document_id'] = op.snapshot(db,r,u,'supplier-comparison',s)
        out['download_url'] = '/api/documents/'+out['document_id']+'/comparison.csv'
    else: return False
    return True


def tender(db,r,u,a,d,s,out):
    if a != 'targeted_amendment': return False
    op.require(d['affected'], 'Explicitly select impacted requirements; use full amendment reset if impact is uncertain')
    identifiers = [row['item_id'] for row in d['affected']]; op.require(len(identifiers) == len(set(identifiers)), 'List each affected requirement once')
    for row in d['affected']:
        item = op.one_item(db,r['id'],row['item_id'],'requirement'); value = item['data']
        value.pop('_verified',None);value.pop('_verified_by',None)
        value['_amendment'] = {'file_id':d['file_id'],'change':row['change'],'at':op.now()}
        op.store_item(db,r['id'],'requirement',value,u,item['id'])
    s['data'].setdefault('amendments',[]).append({**d,'by':u['email'],'at':op.now()})
    s['data'].pop('ready',None);s['stage']='draft'
    invalidate(db,r['id'])
    out['invalidated'] = identifiers
    return True


def handover(db,r,u,a,d,s,out):
    if a == 'apply_template':
        template = op.one_item(db,r['id'],d['template_id'],'inspection_template')['data']
        op.require(template['checks'], 'Add at least one template check')
        out['issues'] = []
        for row in template['checks']:
            out['issues'].append(op.store_item(db,r['id'],'issue',{**row,'room':d['room'],'assignee':d['assignee'],'due':d['due'],'file_id':'','_status':'open','_template':d['template_id']},u))
    elif a == 'bulk_assign':
        op.require(d['issues'], 'Select issues to assign')
        for row in d['issues']:
            item = op.one_item(db,r['id'],row['item_id'],'issue'); value = item['data']
            op.require(value.get('_status','open') in ('open','reopened','acknowledged','in-repair'), 'Only unresolved repairs can be reassigned')
            value.update(assignee=d['assignee'],due=d['due'],_status='open')
            op.store_item(db,r['id'],'issue',value,u,item['id'])
            db.execute('UPDATE task_links SET closed_at=? WHERE item_id=? AND closed_at IS NULL',(op.now(),item['id']))
    elif a in ('acknowledge_issue','start_repair'):
        item = op.one_item(db,r['id'],d['item_id'],'issue'); value = item['data']
        op.require(value['assignee'] == u['email'], 'Only the assignee can progress this repair')
        allowed = ('open','reopened') if a == 'acknowledge_issue' else ('acknowledged',)
        op.require(value.get('_status','open') in allowed, 'Acknowledge the issue before starting repair')
        value['_status'] = 'acknowledged' if a == 'acknowledge_issue' else 'in-repair'
        op.store_item(db,r['id'],'issue',value,u,item['id'])
    else: return False
    invalidate(db,r['id']);s['data'].pop('approved_document',None);s['stage']='draft'
    return True


def orderdesk(db,r,u,a,d,s,out):
    if a=='review_transcript':
        op.require(s['stage'] not in ('reserved','dispatched','cancelled'),'Committed order sources are immutable')
        file=db.execute('SELECT * FROM files WHERE id=? AND record_id=?',(d['file_id'],r['id'])).fetchone()
        op.require(file and file['extraction_status']=='transcribed-needs-review','Transcribe this recording before using it')
        messages=op.items(db,r['id'],'message');existing=next((i for i in messages if i['data'].get('file_id')==d['file_id']),None)
        op.require(not any(i['data']['reference']==d['reference'] and (not existing or existing['id']!=i['id']) for i in messages),'Source reference already exists')
        out['item_id']=op.store_item(db,r['id'],'message',{**(existing['data'] if existing else {}),'reference':d['reference'],'text':d['text'],'file_id':d['file_id'],'_review':{'by':u['email'],'reason':d['reason'],'transcript_checksum':op.digest(file['extracted'])}},u,existing['id'] if existing else None)
        s['data'].pop('parsed_order',None);s['data'].pop('confirmation',None);s['stage']='draft'
        return True
    if a in ('review_order','price_override','plan_backorder'):
        op.require(s['stage'] not in ('reserved','dispatched','cancelled'), 'Release or finish the committed order before changing it')
    if a == 'review_order':
        op.require(d['lines'], 'Review at least one order line')
        lines=[]; seen=set(); questions=[]
        for source in d['lines']:
            row=op.stock_row(db,u,source['sku'])
            op.require(row and not source['sku'].startswith(('lot:','finished:')), 'Select a published catalogue SKU')
            op.require(source['sku'] not in seen, 'Combine repeated SKU quantities');seen.add(source['sku'])
            meta=json.loads(row['data']);q=int(source['quantity'])
            if decimal(row['quantity'])-decimal(row['held'])<q:questions.append('Insufficient available stock: '+row['sku'])
            lines.append({'sku':row['sku'],'name':row['name'],'unit':row['unit'],'quantity':q,'price':meta['price'],'tax':meta['tax'],'price_version':op.digest(meta),'source':source['source'],'total_paise':op.cents(amount(q*decimal(meta['price'])*(1+decimal(meta['tax'])/100)))})
        delivery=singleton(db,r,'delivery'); freight=op.cents(amount(decimal(delivery.get('freight',0))*(1+decimal(delivery.get('tax',0))/100)))
        s['data']['parsed_order']={'lines':lines,'questions':questions,'freight_paise':freight,'total_paise':sum(x['total_paise'] for x in lines)+freight,'source_hash':op.digest(d),'review':{'by':u['email'],'at':op.now(),'reason':d['reason']}}
        s['data'].pop('confirmation',None);s['stage']='clarification' if questions else 'quoted';out['order']=s['data']['parsed_order']
    elif a == 'price_override':
        order=s['data'].get('parsed_order');op.require(order,'Resolve the order first')
        line=next((x for x in order['lines'] if x['sku']==d['sku']),None);op.require(line,'SKU is not in this order')
        s['data'].setdefault('price_overrides',[]).append({**d,'previous_price':line['price'],'by':u['email'],'at':op.now()})
        line['price']=d['price'];line['total_paise']=op.cents(amount(decimal(d['price'])*line['quantity']*(1+decimal(line['tax'])/100)))
        order['total_paise']=sum(x['total_paise'] for x in order['lines'])+order.get('freight_paise',0)
        s['data'].pop('confirmation',None);s['stage']='clarification' if order['questions'] else 'quoted'
    elif a == 'plan_backorder':
        order=s['data'].get('parsed_order');op.require(order and order['lines'],'Resolve the order first')
        op.require(all(q.startswith('Insufficient available stock: ') for q in order['questions']), 'Resolve unknown products and quantities before splitting a backorder')
        op.require(not s['data'].get('backorder_record'), 'This order already has a backorder; work from that record')
        op.require(d['promised_on']>=op.business_today(db,u).isoformat(),'Backorder promise cannot be in the past')
        ready=[];waiting=[]
        for line in order['lines']:
            stock=op.stock_row(db,u,line['sku']); available=max(0,int(decimal(stock['quantity'])-decimal(stock['held'])))
            quantity=min(available,line['quantity'])
            for target,n in ((ready,quantity),(waiting,line['quantity']-quantity)):
                if n:target.append({**line,'quantity':n,'total_paise':op.cents(amount(n*decimal(line['price'])*(1+decimal(line['tax'])/100)))})
        op.require(ready and waiting,'A split requires both available and unavailable quantities; otherwise retain the whole order')
        p=json.loads(r['payload']); p['order_text']='\n'.join(f'{x["quantity"]} x {x["sku"]}' for x in waiting)
        new=op.clone_record(db,r,u,p,r['title']+' · backorder')
        child={'parent_order':r['id'],'backorder_agreement':d,'parsed_order':{**order,'lines':waiting,'questions':['Insufficient available stock: '+x['sku'] for x in waiting],'freight_paise':0,'total_paise':sum(x['total_paise'] for x in waiting)}}
        db.execute("INSERT INTO operations(record_id,stage,data) VALUES (?,'backorder',?)",(new,op.dump(child)))
        delivery=singleton(db,r,'delivery')
        if delivery:op.store_item(db,new,'delivery',{**delivery,'requested_on':d['promised_on'],'freight':'0'},u)
        order.update(lines=ready,questions=[],total_paise=sum(x['total_paise'] for x in ready)+order.get('freight_paise',0))
        s['data']['backorder_record']=new;s['data']['backorder_agreement']=d;s['data'].pop('confirmation',None);s['stage']='quoted';out['record_id']=new
    elif a == 'invoice_order':
        op.require(s['stage']=='dispatched','Dispatch the confirmed order before invoice handoff')
        op.require(not s['data'].get('invoice_job'),'Invoice handoff already exists')
        out['document_id']=op.snapshot(db,r,u,'draft-invoice',s,{'total_paise':s['data']['parsed_order']['total_paise'],'order':s['data']['parsed_order'],'dispatch':s['data']['dispatch']})
        out['job_id']=op.enqueue(db,r,u,'invoice',{'document_id':out['document_id']},'order-invoice:'+r['id']);s['data']['invoice_job']=out['job_id']
    else:return False
    return True


def batch(db,r,u,a,d,s,out):
    if a not in ('cost_adjustment','reverse_cost','dispose_output','print_label'):return False
    production=s['data'].get('production');op.require(production,'Record production first')
    p=json.loads(r['payload']);costs=s['data'].setdefault('cost_adjustments',[])
    if a in ('cost_adjustment','reverse_cost'):
        reference=d['reference'] if a=='cost_adjustment' else d['reversal']
        op.require(not any(x['reference']==reference for x in costs),'Cost adjustment reference already exists')
        if a=='cost_adjustment':delta=op.cents(d['amount'])*(1 if d['direction']=='Increase' else -1)
        else:
            original=next((x for x in costs if x['reference']==d['reference'] and not x.get('reverses')),None)
            op.require(original and not any(x.get('reverses')==d['reference'] for x in costs),'Select a correction that has not been reversed')
            delta=-original['delta_paise']
        total=production['total_paise']-sum(x['cost_reduction_paise'] for x in s['data'].get('returns',[]))+sum(x['delta_paise'] for x in costs)+delta
        op.require(total>=0,'Cost correction cannot make the adjusted batch cost negative')
        adjustment={**d,'reference':reference,'delta_paise':delta,'by':u['email'],'at':op.now()}
        if a=='reverse_cost':adjustment['reverses']=d['reference']
        costs.append(adjustment);s['data']['adjusted_cost_paise']=total
        out['document_id']=op.snapshot(db,r,u,'batch-cost-adjustment',s,adjustment)
    elif a=='dispose_output':
        op.require(s['stage'] in ('rejected','recalled'),'Only rejected or recalled output may use this disposal workflow')
        sku='finished:'+p['batch_number'];stock=op.stock_row(db,u,sku);quantity=decimal(d['quantity'])
        op.require(quantity<=decimal(stock['quantity']) and quantity<=decimal(stock['held']),'Disposal exceeds quarantined stock')
        op.movement(db,r,u,sku,-quantity,'disposal','disposal:'+d['reference'])
        db.execute('UPDATE stock SET quantity=?,held=?,updated_at=? WHERE workspace_id=? AND sku=?',(str(decimal(stock['quantity'])-quantity),str(decimal(stock['held'])-quantity),op.now(),u['workspace_id'],sku))
        s['data'].setdefault('disposals',[]).append({**d,'by':u['email'],'at':op.now()})
        out['document_id']=op.snapshot(db,r,u,'batch-disposal',s,d)
    else:
        op.require(s['stage']=='released','Only released batches receive dispatch labels')
        out['document_id']=op.snapshot(db,r,u,'traceability-label',s,{'product':p['product'],'batch_number':p['batch_number'],'expiry':p['expiry'],'recipe_version':production['recipe_version'],'manufactured_at':production['at'],'quality':'Released'})
    return True


def fees(db,r,u,a,d,s,out):
    if a=='assess_late_fees':
        policy=singleton(db,r,'late_policy');op.require(policy,'Configure and approve a late-fee policy first')
        op.require(s['data'].get('agreement_document'),'Approve the fee agreement first')
        op.require(not s['data'].get('withdrawal'),'Late fees stop after withdrawal')
        today=op.business_today(db,u).isoformat();op.require(policy['effective']<=d['as_of']<=today,'Assessment must be within the effective policy period and today')
        history=s['data'].setdefault('late_assessments',[])
        op.require(not history or d['as_of']>history[-1]['as_of'],'Assessment dates must increase')
        fin=op.financial(db,r);target=0;rows=[]
        for entry in fin['allocations']:
            if 'charge_entry' in entry or not entry['outstanding_paise']:continue
            begins=max(date.fromisoformat(entry['due'])+timedelta(days=int(policy['grace_days'])),date.fromisoformat(policy['effective']))
            days=max(0,(date.fromisoformat(d['as_of'])-begins).days)
            if not days:continue
            value=op.cents(policy['amount'])*(days if policy['mode']=='Daily per instalment' else 1)
            prior=sum(x['amount_paise'] for h in history for x in h['lines'] if x['due']==entry['due'])
            amount_due=max(0,value-prior);rows.append({'due':entry['due'],'days':days,'amount_paise':amount_due});target+=amount_due
        cap=max(0,op.cents(policy['cap'])-sum(h['charged_paise'] for h in history));charge=min(cap,target)
        op.require(charge>0,'No additional late fees are due under this policy')
        remaining=charge
        for row in rows:row['amount_paise']=min(remaining,row['amount_paise']);remaining-=row['amount_paise']
        entry=op.post_ledger(db,r,u,{'kind':'charge','amount':str(Decimal(charge)/100),'reference':'late:'+r['id']+':'+d['as_of'],'date':d['as_of'],'note':'Approved policy '+policy['version']})
        history.append({'as_of':d['as_of'],'policy':policy,'charged_paise':charge,'entry_id':entry,'lines':rows})
        out['document_id']=op.snapshot(db,r,u,'late-fee-assessment',s,history[-1])
    elif a=='withdraw':
        op.require(s['data'].get('agreement_document') and not s['data'].get('withdrawal'),'Approve an agreement; a withdrawal can only be settled once')
        op.require(d['effective']<=op.business_today(db,u).isoformat(),'Withdrawal cannot be future-dated')
        fin=op.financial(db,r);op.require(op.cents(d['credit'])<=max(0,fin['balance_paise']),'Waiver exceeds unpaid fees')
        op.require(op.cents(d['refund'])<=fin['cash_received_paise'],'Refund exceeds cash received')
        entries=[]
        if op.cents(d['credit']):entries.append(op.post_ledger(db,r,u,{'kind':'credit','amount':d['credit'],'reference':d['reference']+':waiver','date':d['effective'],'note':d['reason']}))
        if op.cents(d['refund']):
            entries.append(op.post_ledger(db,r,u,{'kind':'refund','amount':d['refund'],'reference':d['reference']+':refund','date':d['effective'],'note':d['reason']}))
            # A withdrawal refund reduces the agreed fee as well as cash received.
            entries.append(op.post_ledger(db,r,u,{'kind':'credit','amount':d['refund'],'reference':d['reference']+':refund-waiver','date':d['effective'],'note':'Withdrawn tuition: '+d['reason']}))
        s['data']['withdrawal']={**d,'entries':entries,'by':u['email'],'at':op.now()};s['stage']='withdrawal-settled'
        db.execute("UPDATE jobs SET state='blocked',last_error='Enrollment withdrawn; reconcile remaining balance manually' WHERE record_id=? AND kind IN ('email','payment-link') AND state IN ('queued','failed')",(r['id'],))
        out['document_id']=op.snapshot(db,r,u,'withdrawal-settlement',s,s['data']['withdrawal'])
    else:return False
    return True


def renew(db,r,u,a,d,s,out):
    if a=='negotiate_terms':
        op.require(s['stage'] not in ('vendor-confirmed','completed'),'Closed contract terms are immutable')
        op.require(d['renewal']>op.business_today(db,u).isoformat(),'Proposed renewal must be in the future')
        s['data'].setdefault('negotiations',[]).append({**d,'by':u['email'],'at':op.now()})
        out['document_id']=op.snapshot(db,r,u,'negotiated-renewal-terms',s,d)
    elif a=='request_renewal':
        op.require(s['data'].get('decision',{}).get('decision')=='Renew' and s['stage']=='decision-approved','Approve renewal before recording a vendor request')
        op.require(not s['data'].get('renewal_request'),'Renewal request already recorded')
        s['data']['renewal_request']={**d,'by':u['email'],'at':op.now()};s['stage']='renewal-requested'
    else:return False
    return True


def sop(db,r,u,a,d,s,out):
    if a=='copy_template':
        op.require(s['stage']=='published','Choose a published procedure as the source template')
        from .commercial import admit
        source=op.items(db,r['id']);source=[i for i in source if i['kind']!='assignment']
        p=json.loads(r['payload']);p.update(version='1',acknowledgements=[])
        identifier=op.clone_record(db,r,u,p,d['title']);filemap={};itemmap={i['id']:op.uid() for i in source}
        for file_id in {i['data'].get('file_id') for i in source if i['data'].get('file_id')}:
            file=db.execute('SELECT * FROM files WHERE id=? AND record_id=?',(file_id,r['id'])).fetchone()
            control=db.execute('SELECT * FROM file_controls WHERE file_id=?',(file_id,)).fetchone()
            op.require(file and file['content'] and (not control or not control['deleted_at']),'Replace purged source evidence before copying this template')
            admit(db,u['workspace_id'],'source_bytes',len(file['content']));new_id=op.uid();filemap[file_id]=new_id
            db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?)',(new_id,identifier,file['name'],file['mime'],file['size'],file['checksum'],file['content'],file['extracted'],file['extraction_status'],u['id'],op.now()))
            if control:db.execute('INSERT INTO file_controls VALUES (?,?,?,?,?)',(new_id,control['scan_status'],control['retain_until'],None,None))
        for i in source:
            clean={k:filemap.get(v,itemmap.get(v,v)) if isinstance(v,str) else v for k,v in i['data'].items() if not k.startswith('_')}
            op.store_item(db,identifier,i['kind'],clean,u,itemmap[i['id']])
        db.execute('INSERT INTO operations(record_id,data) VALUES (?,?)',(identifier,op.dump({'template_source':r['id'],'template_document':s['data']['published_document']})))
        out['record_id']=identifier
        return True
    if a=='steps_from_transcript':
        op.require(s['stage']=='draft','Published procedures are immutable')
        file=db.execute('SELECT * FROM files WHERE id=? AND record_id=?',(d['file_id'],r['id'])).fetchone()
        op.require(file and file['extraction_status']=='transcribed-needs-review' and d['steps'],'Transcribe the recording and review its steps first')
        start=max([int(i['data']['position']) for i in op.items(db,r['id'],'step')],default=0)
        out['steps']=[]
        for n,value in enumerate(d['steps'],start+1):out['steps'].append(op.store_item(db,r['id'],'step',{**value,'position':str(n),'prerequisites':'','file_id':d['file_id'],'_transcript_review':{'by':u['email'],'reason':d['reason']}},u))
        return True
    if a not in ('new_hire_policy','enroll_team','training_reminders','supervisor_signoff','offline_copy'):return False
    op.require(s['stage']=='published' and s['data'].get('published_document'),'Publish the current procedure first')
    policy=singleton(db,r,'publication_policy');doc=s['data']['published_document']
    if a=='new_hire_policy':
        s['data']['new_hire_policy']={**d,'by':u['email'],'at':op.now()}
    elif a=='enroll_team':
        existing={x['data']['employee'] for x in op.items(db,r['id'],'assignment')};out['assigned']=[]
        for member in db.execute('SELECT u.email FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=?',(u['workspace_id'],)):
            if member['email'] not in existing:
                op.store_item(db,r['id'],'assignment',{'employee':member['email'],'due':d['due']},u);out['assigned'].append(member['email'])
    elif a=='training_reminders':
        op.require(d['consent']=='Yes' and int(d['start_hour'])<int(d['end_hour']),'Consent and valid working hours are required')
        out['jobs']=[]
        for item in op.items(db,r['id'],'assignment'):
            value=item['data']
            if value['due']>op.business_today(db,u).isoformat() or (value.get('_ack_document')==doc and (not op.items(db,r['id'],'question') or value.get('_training_status')=='passed')):continue
            payload={**d,'recipient':value['employee'],'subject':'Training due: '+r['title'],'message':'Please review and complete your assigned current procedure in DoAide.','assignment_id':item['id'],'document_id':doc}
            out['jobs'].append(op.enqueue(db,r,u,'email',payload,'training:'+item['id']+':'+doc+':'+op.business_today(db,u).isoformat()))
    elif a=='supervisor_signoff':
        op.require(policy and policy['supervisor']==u['email'],'Only the designated supervisor can sign off')
        item=op.one_item(db,r['id'],d['item_id'],'assignment');value=item['data']
        op.require(value['employee']!=u['email'],'A supervisor cannot sign off their own training')
        op.require(value.get('_ack_document')==doc,'Staff member must acknowledge the current version')
        op.require(not op.items(db,r['id'],'question') or (value.get('_attempts') and value['_attempts'][-1]['document_id']==doc and value['_attempts'][-1]['passed']),'Staff member must pass the current assessment')
        op.require(not value.get('_signoff') or value['_signoff']['document_id']!=doc,'Training already signed off')
        value['_signoff']={**d,'document_id':doc,'by':u['email'],'at':op.now()};op.store_item(db,r['id'],'assignment',value,u,item['id'])
    else:
        op.require(policy,'Configure an offline-copy validity policy')
        op.require(policy['effective']<=op.business_today(db,u).isoformat(),'Procedure is not yet effective')
        expiry=(datetime.now(timezone.utc)+timedelta(days=int(policy['offline_days']))).isoformat()
        out['document_id']=op.snapshot(db,r,u,'controlled-procedure-copy',s,{'source_document':doc,'issued_to':u['email'],'expires_at':expiry,'refresh':'Reopen the current published procedure in DoAide before use after expiry.'})
        s['data'].setdefault('offline_copies',[]).append({'document_id':out['document_id'],'source_document':doc,'expires_at':expiry,'issued_to':u['email']})
    return True


def timeline_analysis(db,r):
    rows=op.items(db,r['id'],'timeline');groups={};missing=[]
    for item in rows:
        value=item['data'];key=value.get('event_reference')
        if key:groups.setdefault(key,[]).append({'item_id':item['id'],'at':value['at'],'evidence_id':value['evidence_id']})
        if not value.get('statement_source'):missing.append(item['id'])
    conflicts=[{'event_reference':key,'versions':values} for key,values in groups.items() if len({v['at'] for v in values})>1]
    return {'conflicts':conflicts,'missing_provenance':missing,'source_hash':op.digest([i['data'] for i in rows]),'at':op.now()}


def claimpack(db,r,u,a,d,s,out):
    if a=='approve_redaction':
        item=op.one_item(db,r['id'],d['item_id'],'evidence');value=item['data']
        op.require(value.get('_verified') and value.get('redaction'),'Verify the original evidence and describe its required redactions first')
        op.require(value['file_id']!=d['redacted_file_id'],'Upload a separate redacted file; retain the original unchanged')
        original=db.execute('SELECT * FROM files WHERE id=?',(value['file_id'],)).fetchone()
        replacement=db.execute('SELECT * FROM files WHERE id=?',(d['redacted_file_id'],)).fetchone()
        op.require(replacement['content'] and replacement['mime'] in ('text/plain','application/pdf','image/png','image/jpeg'),'Approve an available flattened image, PDF or plain-text redacted copy')
        value['_approved_redaction']={**d,'original_file_id':value['file_id'],'original_sha256':original['checksum'],'replacement_sha256':replacement['checksum'],'approved_by':u['email'],'approved_at':op.now()}
        op.store_item(db,r['id'],'evidence',value,u,item['id'])
        invalidate(db,r['id']);s['stage']='draft';s['data'].pop('packet_document',None)
    elif a=='analyze_timeline':s['data']['timeline_analysis']=timeline_analysis(db,r);out.update(s['data']['timeline_analysis'])
    elif a=='resolve_conflict':
        analysis=timeline_analysis(db,r);conflict=next((x for x in analysis['conflicts'] if x['event_reference']==d['event_reference']),None)
        op.require(conflict,'There is no current conflict for this event reference')
        d['accepted_at']=op.instant(d['accepted_at']);op.require(d['accepted_at']<=op.now(),'Verified events cannot be in the future')
        s['data'].setdefault('conflict_resolutions',{})[d['event_reference']]={**d,'source_hash':analysis['source_hash'],'by':u['email'],'at':op.now()}
    elif a=='save_template':
        template=singleton(db,r,'template');op.require(template and template.get('reviewed_on') and template.get('applicability'),'Review the instructions and applicability before publishing a reusable template')
        identifier=op.digest({'provider':template['provider'],'reason_code':template['reason_code'],'version':template['version']})
        catalogue=s['data'].setdefault('published_templates',[])
        op.require(not any(x['id']==identifier for x in catalogue),'This template version was already published')
        value={k:v for k,v in template.items() if k!='deadline'}
        catalogue.append({'id':identifier,'template':value,'by':u['email'],'at':op.now()});out['template_id']=r['id']+':'+identifier
    elif a=='apply_template':
        source,_,key=d['template_id'].partition(':')
        from .migrations import record_access
        other=record_access(db,source,u);op.require(other['product']=='claimpack','Select a ClaimPack template')
        value=next((x for x in op.get_state(db,source)['data'].get('published_templates',[]) if x['id']==key),None)
        op.require(value,'Template version does not exist');op.require(not op.items(db,r['id'],'template'),'This case already has a template')
        deadline=op.instant(d['deadline']);op.require(deadline>op.now(),'Case deadline has passed')
        op.store_item(db,r['id'],'template',{**value['template'],'deadline':deadline},u);s['data']['template_source']=d['template_id']
    else:return False
    return True


HANDLERS = {'scope':scope,'collect':collect,'amc':amc,'rfq':rfq,'tender':tender,'handover':handover,'orderdesk':orderdesk,'batch':batch,'fees':fees,'renew':renew,'sop':sop,'claimpack':claimpack}


def execute(db,record,user,action,data,state,result):
    handler = HANDLERS.get(record['product'])
    return bool(handler and handler(db,record,user,action,data,state,result))
