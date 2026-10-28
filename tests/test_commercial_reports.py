from copy import deepcopy
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import hmac
import io
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.catalog import CATALOG
from backend.db import database
from backend.worker import run_once, claim, deliver, Blocked
from test_api import app, client, create
from test_operations import action, item, workflow, upload, colleague, date_plus, prepare_order


def plans(monkeypatch, **limits):
    quotas={k:None for k in ('records','members','source_bytes','jobs_per_month')};quotas.update(limits)
    config={'base':{'name':'Trial fixture','products':list(CATALOG),'limits':quotas},
            'suite':{'name':'Suite fixture','products':list(CATALOG),'limits':{k:None for k in quotas},'price_id':'price_testSuite'}}
    monkeypatch.setenv('DOAIDE_BILLING_MODE','stripe-test');monkeypatch.setenv('DOAIDE_BILLING_BASE_PLAN','base')
    monkeypatch.setenv('DOAIDE_BILLING_PLANS',json.dumps(config));monkeypatch.setenv('STRIPE_TEST_SECRET_KEY','sk_test_synthetic')
    monkeypatch.setenv('STRIPE_TEST_WEBHOOK_SECRET','whsec_synthetic')
    return config


def billing_event(c,event_id='evt_one',customer='cus_fixture',event_type='customer.subscription.updated',ts=None,signature=None,live=False):
    raw=json.dumps({'id':event_id,'livemode':live,'type':event_type,'data':{'object':{'customer':customer}}}).encode()
    stamp=str(int(time.time()) if ts is None else ts)
    sig=hmac.new(b'whsec_synthetic',stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    return c.post('/api/webhooks/stripe-billing',content=raw,headers={'Stripe-Signature':signature or f't={stamp},v1={sig}'})


def test_quotas_admit_atomically_and_keep_existing_work_accessible(client,app,monkeypatch):
    plans(monkeypatch,records=1)
    def save(_):return client.post('/api/products/scope/records',json={'title':'Quota race','payload':CATALOG['scope']['sample']}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(save,range(2)))==[201,402]
    r=client.get('/api/records').json()[0]
    assert client.get('/api/records/'+r['id']+'/export').status_code==200
    response=client.post('/api/records/'+r['id']+'/revisions',json={'revision':workflow(client,r)['revision'],'data':{}})
    assert response.status_code==402
    assert len(client.get('/api/records').json())==1


def test_product_entitlement_and_bulk_import_cannot_bypass_budget(client,monkeypatch):
    config=plans(monkeypatch,records=1);config['base']['products']=['collect'];monkeypatch.setenv('DOAIDE_BILLING_PLANS',json.dumps(config))
    assert client.post('/api/products/scope/records',json={'title':'No','payload':CATALOG['scope']['sample']}).status_code==402
    preview=client.post('/api/imports/collect/preview',json={'csv':'customer,invoice,amount,paid,due\nA,I1,100,0,2026-01-01\nB,I2,100,0,2026-01-01','mapping':{k:k for k in ('customer','invoice','amount','paid','due')}}).json()
    assert client.post('/api/imports/'+preview['id']+'/commit',json={}).status_code==402
    assert client.get('/api/records').json()==[]


def test_source_and_membership_budgets(client,app,monkeypatch):
    r=create(client);plans(monkeypatch,source_bytes=4,members=1)
    assert client.post('/api/records/'+r['id']+'/files',files={'file':('x.txt',b'12345','text/plain')}).status_code==402
    assert workflow(client,r)['files']==[]
    invite=client.post('/api/workspace/invitations',json={'email':'limited@example.test','role':'viewer'}).json()
    other=TestClient(app);other.post('/api/auth/register',json={'email':'limited@example.test','password':'another-test-password'})
    assert other.post('/api/workspace/invitations/accept',json={'token':invite['token']}).status_code==402
    assert len(client.get('/api/workspace/members').json())==1


def test_checkout_worker_test_only_idempotent_retry_and_reconciliation(client,tmp_path,monkeypatch):
    plans(monkeypatch);path=tmp_path/'test.db';requests=[];subscription=[];failed=[False]
    def respond(request):
        requests.append(request)
        p=request.url.path
        if p.startswith('/v1/prices/'):return httpx.Response(200,json={'id':'price_testSuite','active':True,'livemode':False,'recurring':{'interval':'month'}})
        if p=='/v1/customers':return httpx.Response(200,json={'id':'cus_fixture','livemode':False})
        if p=='/v1/subscriptions':return httpx.Response(200,json={'data':subscription,'has_more':False})
        if p=='/v1/checkout/sessions':
            if not failed[0]:failed[0]=True;return httpx.Response(503)
            return httpx.Response(200,json={'id':'cs_test_fixture','livemode':False,'url':'https://checkout.stripe.com/c/pay/cs_test_fixture'})
        if p=='/v1/billing_portal/sessions':return httpx.Response(200,json={'id':'bps_fixture','livemode':False,'url':'https://billing.stripe.com/p/session/test_fixture'})
        raise AssertionError(p)
    transport=httpx.MockTransport(respond)
    requested=client.post('/api/billing/checkout',json={'plan':'suite'});assert requested.status_code==200
    job=requested.json()['job_id'];assert client.post('/api/billing/checkout',json={'plan':'suite'}).json()['job_id']==job
    assert run_once(path,transport)['state']=='failed'
    with database(path) as db:db.execute("UPDATE jobs SET due_at='2000-01-01T00:00:00+00:00' WHERE id=?",(job,))
    assert run_once(path,transport)['state']=='delivered'
    posts=[r for r in requests if r.url.path=='/v1/checkout/sessions'];assert len(posts)==2
    assert posts[0].headers['Idempotency-Key']==posts[1].headers['Idempotency-Key'] and posts[0].content==posts[1].content
    assert client.get('/api/billing').json()['plan_id']=='base' # Return URL is not proof of subscription.
    subscription.append({'id':'sub_fixture','customer':'cus_fixture','livemode':False,'status':'active','items':{'data':[{'quantity':1,'price':{'id':'price_testSuite','livemode':False},'current_period_end':int(time.time())+86400}]}})
    assert billing_event(client).status_code==200
    assert billing_event(client).json()['duplicate'] is True
    for _ in range(5):
        if run_once(path,transport) is None:break
    assert client.get('/api/billing').json()['plan_id']=='suite'
    # An old cancellation notification cannot roll back a current provider subscription.
    assert billing_event(client,'evt_old',event_type='customer.subscription.deleted').status_code==200
    run_once(path,transport);assert client.get('/api/billing').json()['plan_id']=='suite'
    subscription[0]['status']='canceled';billing_event(client,'evt_cancelled');run_once(path,transport)
    assert client.get('/api/billing').json()['plan_id']=='base'
    assert client.post('/api/billing/portal',json={}).status_code==200
    run_once(path,transport)
    assert any(j['result'].get('url','').startswith('https://billing.stripe.com/') for j in client.get('/api/billing').json()['jobs'])


def test_billing_rejects_live_keys_forged_stale_and_foreign_events(client,tmp_path,monkeypatch,app):
    plans(monkeypatch)
    assert billing_event(client,signature='t=1,v1=bad').status_code==400
    assert billing_event(client,ts=int(time.time())-301).status_code==400
    assert billing_event(client,live=True).status_code==400
    assert billing_event(client,customer='cus_other').json()['ignored'] is True
    viewer=colleague(client,app,'viewer')
    assert viewer.post('/api/billing/checkout',json={'plan':'suite'}).status_code==403
    assert viewer.get('/api/billing').json()['jobs']==[]
    monkeypatch.setenv('STRIPE_TEST_SECRET_KEY','sk_live_forbidden')
    client.post('/api/billing/checkout',json={'plan':'suite'})
    def forbidden(request):raise AssertionError('Live-key configuration must never contact a provider')
    assert run_once(tmp_path/'test.db',httpx.MockTransport(forbidden))['state']=='blocked'


def test_expired_subscription_falls_back_without_deleting_data(client,tmp_path,monkeypatch):
    r=create(client);plans(monkeypatch,records=0)
    ws=client.get('/api/auth/me').json()['workspace_id']
    with database(tmp_path/'test.db') as db:db.execute("INSERT INTO billing_accounts(workspace_id,plan,status,period_end) VALUES (?,'suite','active',?)",(ws,int(time.time())-1))
    assert client.get('/api/billing').json()['plan_id']=='base'
    assert client.get('/api/records/'+r['id']).status_code==200
    assert client.post('/api/products/scope/records',json={'title':'No','payload':CATALOG['scope']['sample']}).status_code==402


def fees_record(c):
    p=deepcopy(CATALOG['fees']['sample']);p.update(fee='1000',discount='0',payments=[],instalments=[{'due':date_plus(-10),'amount':'500'},{'due':date_plus(20),'amount':'500'}])
    r=create(c,'fees',p);action(c,r,'approve_agreement',{'reason':'Agreed tuition'})
    return r


def test_fee_amendment_preserves_receipts_paid_dates_and_refund_history(client):
    r=fees_record(client)
    receipt=action(client,r,'ledger',{'kind':'payment','amount':'300','reference':'P1','date':date_plus(-1),'note':'Bank receipt'})['result']['document_id']
    frozen=client.get('/api/documents/'+receipt+'/pdf').content
    amendment=action(client,r,'reschedule',{'instalments':[{'due':date_plus(30),'amount':'350'},{'due':date_plus(60),'amount':'350'}],'reason':'Guardian-approved extension'})
    fin=amendment['workflow']['overview'];assert fin['balance_paise']==70000 and fin['due_now_paise']==0
    assert fin['allocations'][0]['due']==date_plus(-10) and fin['allocations'][0]['allocated_paise']==30000
    assert client.get('/api/documents/'+receipt+'/pdf').content==frozen
    assert len(amendment['workflow']['data']['schedule_amendments'])==1
    action(client,r,'reschedule',{'instalments':[{'due':date_plus(60),'amount':'699'}],'reason':'Wrong total'},422)
    action(client,r,'ledger',{'kind':'refund','amount':'100','reference':'R1','date':date_plus(0),'note':'Approved reversal'})
    fin=workflow(client,r)['overview'];assert fin['balance_paise']==80000 and fin['due_now_paise']==10000
    assert len(fin['entries'])==2


def test_fee_charge_is_due_separately_and_allocations_reconcile(client):
    r=fees_record(client)
    action(client,r,'ledger',{'kind':'charge','amount':'50','reference':'C1','date':date_plus(0),'note':'Explicit authorized charge'})
    fin=workflow(client,r)['overview'];assert fin['balance_paise']==105000 and fin['due_now_paise']==55000
    assert sum(i['outstanding_paise'] for i in fin['allocations'])==fin['balance_paise']
    action(client,r,'ledger',{'kind':'payment','amount':'1050','reference':'Pfull','date':date_plus(0),'note':'Bank receipt'})
    assert workflow(client,r)['overview']['due_now_paise']==0


def renew_record(c):
    r=create(c,'renew')
    terms={'department':'Operations','seats':'10','owner':'owner@example.test','backup':'backup@example.test','notice_clause':'30 calendar days','business_days':'No','holidays':'','file_id':''}
    item(c,r,'terms',terms)
    policy={'days':'30,14,7,0','escalate_after':'2','start_hour':'9','end_hour':'17','consent':'Yes'}
    item(c,r,'reminder_policy',policy)
    return r,terms,policy


def test_renewal_milestones_acknowledgement_and_recompute(client,tmp_path):
    r,terms,policy=renew_record(client);first=action(client,r,'plan_reminders')['result']
    assert first['job_ids'] and first['missed_offsets']==[30]
    assert action(client,r,'plan_reminders')['result']['job_ids']==first['job_ids']
    action(client,r,'acknowledge_notice')
    assert all(j['state']=='cancelled' for j in workflow(client,r)['jobs'])
    payload={**r['payload'],'renewal':date_plus(90)}
    response=client.put('/api/records/'+r['id'],json={'title':r['title'],'version':r['version'],'payload':payload});assert response.status_code==200,response.text
    plan=workflow(client,r)['data']['renewal_plan'];assert plan['fingerprint']!=first['fingerprint'] and not plan.get('acknowledged_at')
    assert len(set(plan['job_ids'])&set(first['job_ids']))==0
    assert all(j['state']=='queued' for j in workflow(client,r)['jobs'] if j['id'] in plan['job_ids'])


def test_renewal_changed_owners_block_old_delivery_and_usage_validated(client,tmp_path,app):
    r,terms,policy=renew_record(client);action(client,r,'plan_reminders')
    outsider=colleague(client,app,'operator')
    action(outsider,r,'acknowledge_notice',status=422)
    path=tmp_path/'test.db'
    with database(path) as db:
        old=dict(db.execute("SELECT * FROM jobs WHERE record_id=? LIMIT 1",(r['id'],)).fetchone());old['data']=json.loads(old['data'])
    term=next(i for i in workflow(client,r)['items'] if i['kind']=='terms')
    response=client.put(f'/api/records/{r["id"]}/items/terms/{term["id"]}',json={'revision':workflow(client,r)['revision'],'data':{**terms,'owner':'new@example.test'}})
    assert response.status_code==200,response.text
    with pytest.raises(Blocked,match='changed'):deliver(old,path)
    usage={'reference':'S1','auto_renew':'Yes','active_seats':'8','verified_on':date_plus(1),'source':'Admin report'}
    item(client,r,'subscription',usage,422)
    item(client,r,'subscription',{**usage,'verified_on':date_plus(0),'active_seats':'11'},422)


def test_reports_all_products_isolated_and_accounting_reconciles(client,app):
    for slug in CATALOG:create(client,slug)
    r=fees_record(client);action(client,r,'ledger',{'kind':'payment','amount':'300','reference':'=UNTRUSTED','date':date_plus(0),'note':'=FORMULA()'})
    result=client.get('/api/reports/portfolio');assert result.status_code==200,result.text
    report=result.json();assert len(report['records'])==13 and set(report['totals'])==set(CATALOG)
    rows=list(csv.DictReader(io.StringIO(client.get('/api/reports/accounting.csv?product=fees').text.lstrip('\ufeff'))))
    entry=next(row for row in rows if row['kind']=='payment');assert entry['reference']=="'=UNTRUSTED" and entry['note']=="'=FORMULA()"
    ours=[row for row in rows if row['record_id']==r['id']]
    assert sum(int(row['balance_effect_paise']) for row in ours)==70000
    other=TestClient(app);other.post('/api/auth/register',json={'email':'private@example.test','password':'another-long-password'})
    assert other.get('/api/reports/portfolio').json()['records']==[]
    assert len(list(csv.reader(io.StringIO(other.get('/api/reports/accounting.csv').text))))==1


def test_renewal_portfolio_flags_duplicates_prices_and_verified_seats(client):
    r,terms,_=renew_record(client)
    item(client,r,'subscription',{'reference':'SUB1','auto_renew':'Yes','active_seats':'6','verified_on':date_plus(0),'source':'Admin usage export'})
    duplicate=create(client,'renew');item(client,duplicate,'terms',terms)
    item(client,duplicate,'subscription',{'reference':'SUB1','auto_renew':'Yes','active_seats':'6','verified_on':date_plus(0),'source':'Admin usage export'})
    report=client.get('/api/reports/portfolio?product=renew').json();row=next(i for i in report['records'] if i['record_id']==r['id'])
    assert row['facts']['annualized_paise']==4320000 and row['facts']['verified_unused_seats']==4
    assert any('duplicate' in flag for flag in row['alerts'])
    action(client,r,'decide',{'decision':'Renew','reason':'Vendor confirmed next term'})
    f=upload(client,r);new=action(client,r,'rollover',{'renewal':date_plus(410),'cost':'4000','file_id':f})['result']['record_id']
    row=next(i for i in client.get('/api/reports/portfolio?product=renew').json()['records'] if i['record_id']==new)
    assert row['facts']['price_increase_paise']==40000


def test_stock_corrections_protect_reservations_and_freeze_audit(client,app):
    r=prepare_order(client);f=upload(client,r);action(client,r,'reserve')
    body={'record_id':r['id'],'sku':'TEA','reference':'COUNT-1','delta':'-4','expected_quantity':'8','expected_held':'5','reason':'Physical count reconciliation','file_id':f}
    assert client.post('/api/inventory/adjustments',json=body).status_code==422
    body['delta']='-2';response=client.post('/api/inventory/adjustments',json=body);assert response.status_code==200,response.text
    assert response.json()['after_quantity']=='6' and response.json()['after_held']=='5'
    assert client.post('/api/inventory/adjustments',json=body).json()['id']==response.json()['id']
    assert client.post('/api/inventory/adjustments',json={**body,'reference':'COUNT-2'}).status_code==409
    assert client.post('/api/inventory/adjustments',json={**body,'delta':'-1'}).status_code==409
    operator=colleague(client,app,'operator');assert operator.post('/api/inventory/adjustments',json=body).status_code==403
    action(client,r,'dispatch',{'reference':'D1'});assert client.get('/api/inventory').json()[0]['quantity']=='1'
    assert len(client.get('/api/inventory/adjustments').json())==1
    other=create(client,'orderdesk')
    item(client,other,'catalogue',{'sku':'lot:FORGED','name':'Forbidden','aliases':'','unit':'kg','pack':'1','price':'10','tax':'0','stock':'4'},422)


def test_count_correction_does_not_release_quarantined_batch(client):
    r=create(client,'batch');f=upload(client,r)
    item(client,r,'recipe',{'version':'1','ingredient':'Flour','quantity':'10','unit':'kg'})
    item(client,r,'lot',{'lot':'F1','ingredient':'Flour','supplier':'Miller','quantity':'20','unit':'kg','cost':'50','expiry':date_plus(60),'quality':'Released','file_id':f})
    item(client,r,'usage',{'lot':'F1','quantity':'12','waste':'1','unit':'kg'})
    action(client,r,'receive_lots');action(client,r,'produce')
    stock=next(s for s in client.get('/api/inventory').json() if s['sku'].startswith('finished:'))
    response=client.post('/api/inventory/adjustments',json={'record_id':r['id'],'sku':stock['sku'],'reference':'COUNT-Q','delta':'2','expected_quantity':stock['quantity'],'expected_held':stock['held'],'reason':'Two additional sealed units found','file_id':f})
    assert response.status_code==200,response.text
    assert response.json()['after_quantity']==response.json()['after_held']
    assert workflow(client,r)['stage']=='produced'


def test_readiness_and_diagnostics_respect_worker_health_and_role(client,tmp_path,monkeypatch,app):
    assert client.get('/api/ready').json()=={'ready':True}
    monkeypatch.setenv('DOAIDE_REQUIRE_WORKER','true');assert client.get('/api/ready').status_code==503
    assert run_once(tmp_path/'test.db') is None
    assert client.get('/api/ready').status_code==200
    assert client.get('/api/diagnostics').json()['worker_healthy'] is True
    viewer=colleague(client,app,'viewer');assert viewer.get('/api/diagnostics').status_code==403


def test_unknown_provider_plan_removes_entitlement_pending_reconciliation(client,tmp_path,monkeypatch):
    plans(monkeypatch);ws=client.get('/api/auth/me').json()['workspace_id'];path=tmp_path/'test.db'
    with database(path) as db:db.execute("INSERT INTO billing_accounts(workspace_id,customer_id,plan,status,period_end) VALUES (?,'cus_fixture','suite','active',?)",(ws,int(time.time())+10000))
    billing_event(client)
    transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'data':[{'id':'sub_bad','livemode':False,'customer':'cus_fixture','status':'active','items':{'data':[{'quantity':1,'price':{'id':'price_unknown','livemode':False},'current_period_end':int(time.time())+10000}]}}]}))
    assert run_once(path,transport)['state']=='blocked'
    status=client.get('/api/billing').json();assert status['plan_id']=='base' and status['account']['status']=='needs-review'


def test_restart_does_not_restore_revoked_original_workspace_owner(client,app,tmp_path):
    from backend.db import initialize
    owner=client.get('/api/auth/me').json();replacement=colleague(client,app,'owner')
    assert replacement.put('/api/workspace/members/'+owner['id'],json={'role':'remove'}).status_code==200
    initialize(tmp_path/'test.db')
    assert client.get('/api/records').status_code==403
    assert all(member['id']!=owner['id'] for member in replacement.get('/api/workspace/members').json())
