"""Workspace-scoped operational and accounting reports, derived from saved facts."""
import csv
import io
import json
from collections import Counter
from datetime import date

from fastapi import Depends, HTTPException, Response
from .catalog import CATALOG
from .db import database
from . import operations as op


def csv_response(rows, filename):
    output=io.StringIO(newline='');writer=csv.writer(output)
    for row in rows:
        # Untrusted titles, references and notes must not become spreadsheet formulas.
        writer.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else v for v in row])
    return Response('\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="{filename}"'})


def records(db,workspace,product=None):
    return [dict(r) for r in db.execute('SELECT r.* FROM records r JOIN record_workspaces w ON w.record_id=r.id WHERE w.workspace_id=?'+(' AND r.product=?' if product else '')+' ORDER BY r.created_at,r.id',(workspace,product) if product else (workspace,))]


def aging(fin,today,due=None):
    result={k:0 for k in ('not_due','due_today','days_1_30','days_31_60','days_61_90','days_91_plus')}
    obligations=fin.get('allocations') or [{'due':due,'outstanding_paise':fin['balance_paise']}]
    for entry in obligations:
        value=entry['outstanding_paise']
        if value<=0:continue
        days=(today-date.fromisoformat(entry['due'])).days
        bucket='not_due' if days<0 else 'due_today' if days==0 else 'days_1_30' if days<=30 else 'days_31_60' if days<=60 else 'days_61_90' if days<=90 else 'days_91_plus'
        result[bucket]+=value
    return result


def read_state(db,record_id):
    row=db.execute('SELECT stage,data FROM operations WHERE record_id=?',(record_id,)).fetchone()
    return {'stage':row['stage'],'data':json.loads(row['data'])} if row else {'stage':'draft','data':{}}


def row_report(db,r,user,today,renew_index):
    p=json.loads(r['payload']);state=read_state(db,r['id']);items=op.items(db,r['id']);slug=r['product'];facts={};alerts=[];deadline=None
    if slug=='handover' and not items:items=[{'kind':'issue','data':{**i,'_status':'open'}} for i in p['issues']]
    by=lambda kind:[i for i in items if i['kind']==kind]
    if slug in ('collect','fees'):
        fin=op.financial(db,r)
        facts={k:fin[k] for k in ('total_paise','balance_paise','cash_received_paise')}
        facts['aging_paise']=aging(fin,today,p.get('due'))
        facts['due_now_paise']=fin['due_now_paise'] if slug=='fees' else fin['balance_paise'] if p['due']<=today.isoformat() else 0
        facts['reminder_pause']=op.reminder_blocker(db,r)
        if facts['due_now_paise']>0:alerts.append('Payment due')
        if facts['reminder_pause']:alerts.append('Follow-up paused: '+facts['reminder_pause'])
    elif slug=='scope':
        facts={'approved':bool(state['data'].get('approved_document')),'client_accepted':bool(state['data'].get('accepted_document')),'external_invoices':len(state['data'].get('external_invoices',{}))}
        if state['stage']=='approved':alerts.append('Client decision pending')
    elif slug=='amc':
        visits=by('visit');facts={'visits':len(visits),'awaiting_verification':sum(i['data'].get('_status')=='completed' for i in visits),
                               'included_remaining':int(p['included'])-int(p['completed'])-sum(i['data'].get('_status')=='verified' and i['data']['chargeable']=='No' for i in visits)}
        if any(i['data'].get('_status','scheduled')=='scheduled' and i['data']['end']<op.now() for i in visits):alerts.append('Scheduled visit overdue')
        deadline=p['end']
    elif slug=='rfq':
        facts={'required_lines':len(by('requirement')),'suppliers':len({i['data']['supplier'] for i in by('offer')}),'awarded':state['stage']=='awarded'}
        if not by('offer'):alerts.append('Supplier quotes missing')
    elif slug=='tender':
        requirements=by('requirement');facts={'requirements':len(requirements),'verified':sum(bool(i['data'].get('_verified')) for i in requirements)}
        deadline=by('deadline')[0]['data']['at'][:10] if by('deadline') else p['deadline']
        if facts['verified']<facts['requirements']:alerts.append('Requirements awaiting verification')
    elif slug=='handover':
        statuses=Counter(i['data'].get('_status','open') for i in by('issue'));facts={'issues':len(by('issue')),'statuses':dict(statuses)}
        if any(i['data']['severity']=='Critical' and i['data'].get('_status','open')!='verified' for i in by('issue')):alerts.append('Critical snag unresolved')
        if statuses.get('fixed'):alerts.append('Repairs awaiting independent verification')
    elif slug=='orderdesk':
        facts={'reserved':state['stage']=='reserved','dispatched':state['stage']=='dispatched','source_messages':len(by('message'))}
        if state['stage']=='reserved':alerts.append('Stock reserved; dispatch or cancel')
    elif slug=='batch':
        facts={'produced_units':int(p['produced_units']) if state['data'].get('production') else 0,'dispatches':len(by('dispatch')),'material_reservations':bool(state['data'].get('material_reservations'))}
        if state['stage']=='produced':alerts.append('Quality decision pending')
        if state['stage']=='recalled':alerts.append('Batch recalled')
        deadline=p['expiry']
    elif slug=='renew':
        terms=by('terms');sub=by('subscription');deadline=op.notice_date(r,terms)
        factors={'Monthly':12,'Quarterly':4,'Yearly':1,'Annual':1}
        # The intake's exact cadence factors remain the source of truth.
        factor=factors.get(p['cadence'],1)
        facts={'annualized_paise':op.cents(p['cost'])*factor,'actual_spend_paise':sum(op.cents(i['data']['amount']) for i in by('invoice')),
               'notice_date':deadline,'acknowledged':bool(state['data'].get('renewal_plan',{}).get('acknowledged_at'))}
        members={row[0] for row in db.execute('SELECT u.email FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.workspace_id=?',(user['workspace_id'],))}
        if not terms or terms[0]['data']['owner'] not in members:alerts.append('Responsible owner is not a workspace member')
        if not state['data'].get('renewal_plan'):alerts.append('Notice milestones not scheduled')
        if sub and terms:
            facts['verified_unused_seats']=max(0,int(terms[0]['data']['seats'])-int(sub[0]['data']['active_seats']))
            facts['usage_verified_on']=sub[0]['data']['verified_on']
            if facts['verified_unused_seats']:alerts.append('Unused seats in supplied usage evidence')
            if sub[0]['data']['verified_on']<(today.replace(day=1)).isoformat():alerts.append('Usage evidence predates the current month')
        candidates=renew_index.get((p['vendor'].strip().casefold(),sub[0]['data']['reference'].strip().casefold() if sub else p['service'].strip().casefold()),[])
        if len(candidates)>1:alerts.append('Potential duplicate subscription; compare vendor references')
        previous=state['data'].get('previous_term')
        if previous:
            old=db.execute('SELECT r.payload FROM records r JOIN record_workspaces w ON w.record_id=r.id WHERE r.id=? AND w.workspace_id=?',(previous,user['workspace_id'])).fetchone()
            if old:
                prior=json.loads(old['payload'])
                if prior['cadence']==p['cadence'] and op.cents(p['cost'])>op.cents(prior['cost']):
                    facts['price_increase_paise']=op.cents(p['cost'])-op.cents(prior['cost']);alerts.append('Price increased from previous term')
    elif slug=='sop':
        published=state['data'].get('published_document');assignments=by('assignment')
        current=lambda i:bool(published) and i['data'].get('_ack_document')==published
        facts={'assignments':len(assignments),'current_acknowledgements':sum(current(i) for i in assignments)}
        if state['stage']=='published' and any(not current(i) and i['data']['due']<today.isoformat() for i in assignments):alerts.append('Training acknowledgement overdue')
    elif slug=='claimpack':
        evidence=by('evidence');facts={'evidence_files':len(evidence),'verified':sum(bool(i['data'].get('_verified')) for i in evidence),'outcome':state['data'].get('outcome')}
        deadline=by('template')[0]['data']['deadline'][:10] if by('template') else p['deadline']
        if facts['verified']<len(evidence):alerts.append('Evidence awaiting review')
    closed=state['stage'] in ('submitted','completed','won','lost','withdrawn','vendor-confirmed','superseded')
    if deadline and deadline<today.isoformat() and not closed:alerts.append('Deadline passed')
    if r['status']=='archived' or closed:alerts=[]
    return {'record_id':r['id'],'title':r['title'],'product':slug,'status':r['status'],'stage':state['stage'],'deadline':deadline,'facts':facts,'alerts':alerts}


def portfolio(db,user,product=None):
    today=op.business_today(db,user);allrecords=records(db,user['workspace_id']);renew_index={}
    for r in allrecords:
        if r['product']!='renew' or r['status']=='archived':continue
        state=read_state(db,r['id'])
        if state['stage'] in ('completed','vendor-confirmed'):continue
        p=json.loads(r['payload']);sub=op.items(db,r['id'],'subscription')
        key=(p['vendor'].strip().casefold(),sub[0]['data']['reference'].strip().casefold() if sub else p['service'].strip().casefold())
        renew_index.setdefault(key,[]).append(r['id'])
    rows=[row_report(db,r,user,today,renew_index) for r in allrecords if not product or r['product']==product]
    totals={}
    for slug in CATALOG:
        active=[r for r in rows if r['product']==slug and r['status']!='archived']
        totals[slug]={'records':len(active),'attention':sum(bool(r['alerts']) for r in active),'stages':dict(Counter(r['stage'] for r in active))}
        if slug in ('fees','collect'):
            totals[slug].update({k:sum(r['facts'][k] for r in active) for k in ('balance_paise','cash_received_paise','due_now_paise')})
            totals[slug]['aging_paise']={k:sum(r['facts']['aging_paise'][k] for r in active) for k in aging({'balance_paise':0},today,today.isoformat())}
        if slug=='renew':totals[slug]['annualized_paise']=sum(r['facts']['annualized_paise'] for r in active if r['stage'] not in ('completed','vendor-confirmed'))
    return {'as_of':op.now(),'business_date':today.isoformat(),'currency':'INR','totals':totals,'records':rows,
            'basis':'Saved workspace facts. Archived records are excluded from totals. Collect and Fees are separate ledgers; do not add them as revenue.'}


def install_reports(app,path,current_user):
    def validate(product):
        if product and product not in CATALOG:raise HTTPException(422,'Unknown product')

    @app.get('/api/reports/portfolio')
    def report(product:str|None=None,user=Depends(current_user)):
        validate(product)
        with database(path) as db:
            db.execute('BEGIN');result=portfolio(db,user,product)
        result['total_records']=len(result['records']);result['records']=result['records'][:500]
        result['truncated']=result['total_records']>500
        return result

    @app.get('/api/reports/portfolio.csv')
    def export(product:str|None=None,user=Depends(current_user)):
        validate(product)
        with database(path) as db:
            db.execute('BEGIN');result=portfolio(db,user,product)
        rows=[['record_id','product','title','intake_status','workflow_stage','deadline','alerts','facts_json','as_of']]
        rows.extend([r['record_id'],r['product'],r['title'],r['status'],r['stage'],r['deadline'],'; '.join(r['alerts']),op.dump(r['facts']),result['as_of']] for r in result['records'])
        return csv_response(rows,'doaide-portfolio.csv')

    @app.get('/api/reports/accounting.csv')
    def accounting(product:str|None=None,user=Depends(current_user)):
        if product not in (None,'collect','fees'):raise HTTPException(422,'Accounting exports support Collect and Fees')
        rows=[['record_id','product','title','kind','reference','effective_date','currency','amount_paise','balance_effect_paise','source','actor','note']]
        with database(path) as db:
            db.execute('BEGIN')
            for r in records(db,user['workspace_id'],product):
                if r['product'] not in ('collect','fees'):continue
                fin=op.financial(db,r)
                rows.append([r['id'],r['product'],r['title'],'opening-charge','intake-v'+str(r['version']),'','INR',fin['total_paise'],fin['total_paise'],'intake','', 'Agreed initial obligation; not a provider receipt'])
                if fin['opening_paid_paise']:rows.append([r['id'],r['product'],r['title'],'opening-settlement','intake-v'+str(r['version']),'','INR',fin['opening_paid_paise'],-fin['opening_paid_paise'],'intake','','Prior payments entered in intake'])
                for entry in fin['entries']:
                    effect=entry['amount']*(-1 if entry['kind'] in ('payment','credit') else 1)
                    rows.append([r['id'],r['product'],r['title'],entry['kind'],entry['reference'],entry['date'],entry['currency'],entry['amount'],effect,'provider' if entry['actor']=='razorpay' else 'manual',entry['actor'],entry['note']])
        return csv_response(rows,'doaide-accounting.csv')
