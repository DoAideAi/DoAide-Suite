from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import hashlib
import hmac
import io
import json
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.catalog import CATALOG
from backend.main import create_app
from backend.db import database
from backend.worker import run_once
from test_api import app, client, create


def workflow(c,r):return c.get(f'/api/records/{r["id"]}/operations').json()
def item(c,r,kind,data,status=201):
    response=c.post(f'/api/records/{r["id"]}/items/{kind}',json={'revision':workflow(c,r)['revision'],'data':data})
    assert response.status_code==status,response.text
    return response.json()
def action(c,r,name,data=None,status=200,key=None):
    response=c.post(f'/api/records/{r["id"]}/actions/{name}',json={'revision':workflow(c,r)['revision'],'data':data or {}},headers={'Idempotency-Key':key or str(uuid4())})
    assert response.status_code==status,response.text
    return response.json()
def upload(c,r,text='Required: company certificate\nEvidence verified by reviewer.'):
    response=c.post(f'/api/records/{r["id"]}/files',files={'file':('evidence.txt',text.encode(),'text/plain')})
    assert response.status_code==201,response.text
    return response.json()['id']
def date_plus(n):return (datetime.now(timezone.utc)+timedelta(days=n)).date().isoformat()
def timestamp(n):return (datetime.now(timezone.utc)+timedelta(days=n)).isoformat()
def colleague(c,app,role='reviewer',email='reviewer@example.test'):
    workspace=c.get('/api/auth/me').json()['workspace_id']
    invitation=c.post('/api/workspace/invitations',json={'email':email,'role':role});assert invitation.status_code==201,invitation.text
    other=TestClient(app);response=other.post('/api/auth/register',json={'email':email,'password':'another-long-test-password'});assert response.status_code==201
    assert other.post('/api/workspace/invitations/accept',json={'token':invitation.json()['token']}).status_code==200
    other.headers['X-Workspace-ID']=workspace
    return other


def test_workspace_roles_isolation_and_last_owner(client,app):
    r=create(client)
    viewer=colleague(client,app,'viewer')
    assert viewer.get('/api/records').json()[0]['id']==r['id']
    item(viewer,r,'baseline',{'reference':'1','text':'Agreed','file_id':''},403)
    assert viewer.put('/api/records/'+r['id'],json={'title':'wrong','payload':r['payload'],'version':1}).status_code==403
    assert viewer.post('/api/workspace/invitations',json={'email':'no@example.test','role':'owner'}).status_code==403
    me=client.get('/api/auth/me').json()
    assert client.put('/api/workspace/members/'+me['id'],json={'role':'viewer'}).status_code==422
    assert client.put('/api/workspace/members/'+viewer.get('/api/auth/me').json()['id'],json={'role':'remove'}).status_code==200
    assert viewer.get('/api/records').status_code==403


def test_invite_wrong_recipient_and_replay(client,app):
    invitation=client.post('/api/workspace/invitations',json={'email':'intended@example.test','role':'viewer'}).json()
    with TestClient(app) as other:
        other.post('/api/auth/register',json={'email':'wrong@example.test','password':'another-long-test-password'})
        assert other.post('/api/workspace/invitations/accept',json={'token':invitation['token']}).status_code==403


def test_files_private_and_evidence_zip_snapshot(client,app):
    r=create(client);file=upload(client,r)
    p=deepcopy(r['payload']);p['decision']='Change required'
    client.put('/api/records/'+r['id'],json={'title':r['title'],'payload':p,'version':1})
    item(client,r,'baseline',{'reference':'Contract page 1','text':'Marketing website','file_id':file})
    out=action(client,r,'approve',{'reason':'Approved change'});doc=out['result']['document_id']
    pdf=client.get('/api/documents/'+doc+'/pdf');assert pdf.status_code==200
    reader=PdfReader(io.BytesIO(pdf.content));assert 'CHANGE REQUEST' in reader.pages[0].extract_text()
    packet=zipfile.ZipFile(io.BytesIO(client.get('/api/documents/'+doc+'/packet').content));manifest=json.loads(packet.read('manifest.json'));assert len(manifest['files'])==1
    with TestClient(app) as other:
        other.post('/api/auth/register',json={'email':'outsider@example.test','password':'another-long-test-password'})
        assert other.get('/api/files/'+file).status_code==404
        assert other.get('/api/documents/'+doc+'/pdf').status_code==404
    assert client.post('/api/records/'+r['id']+'/files',files={'file':('x.html',b'<script>bad</script>','text/html')}).status_code==422
    assert client.post('/api/records/'+r['id']+'/files',files={'file':('x.pdf',b'not a pdf','application/pdf')}).status_code==422


def approve_scope(c):
    p=deepcopy(CATALOG['scope']['sample']);p['decision']='Change required';r=create(c,payload=p)
    item(c,r,'baseline',{'reference':'Clause 3','text':'Website only','file_id':''})
    item(c,r,'estimate',{'description':'Portal','quantity':'10','rate':'1000','discount':'100','tax':'18'})
    out=action(c,r,'approve',{'reason':'Commercial terms reviewed'})
    return r,out['result']['document_id']


def test_scope_acceptance_exact_version_revocation_and_idempotent_invoice(client):
    r,doc=approve_scope(client)
    share=client.post('/api/records/'+r['id']+'/shares',json={'document_id':doc,'recipient':'client@example.test','purpose':'accept'}).json()
    portal=client.get('/api/portal/'+share['token']).json();assert 'files' not in portal['snapshot']
    body={'name':'Client Person','email':'client@example.test','checksum':portal['checksum'],'agree':True}
    assert client.post('/api/portal/'+share['token']+'/accept',json={**body,'checksum':'wrong'}).status_code==422
    assert client.post('/api/portal/'+share['token']+'/accept',json=body).status_code==200
    assert workflow(client,r)['stage']=='accepted'
    w=workflow(client,r);key=str(uuid4());request={'revision':w['revision'],'data':{}}
    response=client.post(f'/api/records/{r["id"]}/actions/invoice',json=request,headers={'Idempotency-Key':key});assert response.status_code==200
    replay=client.post(f'/api/records/{r["id"]}/actions/invoice',json=request,headers={'Idempotency-Key':key});assert replay.json()==response.json()
    assert len(workflow(client,r)['jobs'])==1
    assert client.put('/api/records/'+r['id'],json={'title':'overwrite accepted','payload':r['payload'],'version':1}).status_code==409


def test_source_change_revokes_old_approval_link(client):
    r,doc=approve_scope(client)
    share=client.post('/api/records/'+r['id']+'/shares',json={'document_id':doc,'recipient':'client@example.test','purpose':'accept'}).json()
    item(client,r,'baseline',{'reference':'Clause 4','text':'Another clause','file_id':''})
    assert client.get('/api/portal/'+share['token']).status_code==404
    assert workflow(client,r)['stage']=='draft'
    action(client,r,'invoice',status=422)


def test_stale_resource_write_rejected(client):
    r=create(client);revision=workflow(client,r)['revision']
    item(client,r,'baseline',{'reference':'1','text':'One','file_id':''})
    response=client.post(f'/api/records/{r["id"]}/items/baseline',json={'revision':revision,'data':{'reference':'2','text':'Two','file_id':''}})
    assert response.status_code==409


def test_collect_ledger_allocations_and_reminder_pauses(client):
    p=deepcopy(CATALOG['collect']['sample']);p.update(promise='',disputed='No',paid='0',amount='1000');r=create(client,'collect',p)
    action(client,r,'ledger',{'kind':'payment','amount':'250.25','reference':'receipt-001','date':date_plus(0),'note':'Bank transfer verified'})
    assert workflow(client,r)['overview']['balance_paise']==74975
    action(client,r,'ledger',{'kind':'payment','amount':'250.25','reference':'receipt-001','date':date_plus(0),'note':'Duplicate'},422)
    action(client,r,'ledger',{'kind':'payment','amount':'900','reference':'receipt-002','date':date_plus(0),'note':'Too much'},422)
    action(client,r,'ledger',{'kind':'refund','amount':'300','reference':'refund-001','date':date_plus(0),'note':'Too much'},422)
    action(client,r,'ledger',{'kind':'credit','amount':'49.75','reference':'credit-001','date':date_plus(0),'note':'Commercial credit'})
    assert workflow(client,r)['overview']['balance_paise']==70000
    item(client,r,'promise',{'kind':'Dispute','until':'','note':'Customer dispute'})
    reminder={'recipient':'customer@example.test','subject':'Invoice due','message':'Please review','due_at':timestamp(1),'start_hour':'9','end_hour':'18','consent':'Yes'}
    action(client,r,'reminder',reminder,422)
    item(client,r,'promise',{'kind':'Resolution','until':'','note':'Resolved'})
    action(client,r,'reminder',reminder)
    assert len(workflow(client,r)['jobs'])==1


def test_csv_preview_deduplication_commit_and_reverse(client):
    body={'csv':'Client,Ref,Amount,Paid,Due\nAcme,I1,1000,0,2026-12-01\nAcme,I2,500,100,2026-12-01\n','mapping':{'customer':'Client','invoice':'Ref','amount':'Amount','paid':'Paid','due':'Due'}}
    preview=client.post('/api/imports/collect/preview',json=body).json();assert preview['can_commit']
    result=client.post('/api/imports/'+preview['id']+'/commit');assert result.status_code==200,result.text
    assert client.post('/api/imports/'+preview['id']+'/commit').status_code==422
    duplicate=client.post('/api/imports/collect/preview',json=body).json();assert not duplicate['can_commit']
    assert client.post('/api/imports/'+preview['id']+'/reverse').status_code==200
    assert all(r['status']=='archived' for r in client.get('/api/records').json())


def test_amc_independent_verification_entitlement_and_renewal(client,app):
    tech=colleague(client,app,'operator','tech@example.test');p=deepcopy(CATALOG['amc']['sample']);p['completed']='0';p['included']='1';r=create(client,'amc',p)
    asset=item(client,r,'asset',{'site':'Cafe','serial':'SN1','model':'RO','warranty':'','coverage':'Filter service'})['id']
    visit={'asset_id':asset,'technician':'tech@example.test','start':timestamp(-2),'end':timestamp(-1),'chargeable':'No','checklist':'Check pump\nReplace filter'}
    identifier=item(client,r,'visit',visit)['id'];file=upload(tech,r)
    action(client,r,'complete_visit',{'item_id':identifier,'notes':'Done','file_id':file},422)
    action(tech,r,'complete_visit',{'item_id':identifier,'notes':'Pump checked; filter replaced','file_id':file})
    action(client,r,'verify_visit',{'item_id':identifier})
    assert workflow(client,r)['overview']['included_visits_remaining']==0
    item(client,r,'visit',{**visit,'start':timestamp(1),'end':timestamp(2)},422)
    action(client,r,'verify_visit',{'item_id':identifier},422)
    next_start=(datetime.fromisoformat(p['end'])+timedelta(days=1)).date().isoformat()
    action(client,r,'renew_contract',{'start':next_start,'end':date_plus(400),'value':'8000','included':'4'})
    assert len(client.get('/api/records?product=amc').json())==2


def test_rfq_complete_comparison_and_award(client):
    r=create(client,'rfq');file=upload(client,r)
    req=item(client,r,'requirement',{'sku':'BOTTLE','specification':'750 ml stainless','quantity':'100','unit':'each'})['id']
    base={'requirement_id':req,'file_id':file,'quantity':'100','unit':'each','price':'10','currency':'USD','fx':'80','fx_basis':'Approved treasury rate 2026-10-28','discount':'0','tax':'10','freight':'50','lead_days':'7','equivalent':'Yes','exclusions':''}
    item(client,r,'offer',{**base,'supplier':'A'});item(client,r,'offer',{**base,'supplier':'B','price':'11','equivalent':'No'})
    result=action(client,r,'compare');assert result['workflow']['data']['comparison'][0]['total_paise']==9200000
    action(client,r,'award',{'supplier':'B','reason':'cheapest'},422)
    item(client,r,'evaluation',{'supplier':'A','score':'95','rationale':'Matches specification'})
    action(client,r,'award',{'supplier':'A','reason':'Equivalent and lowest landed cost'})
    assert workflow(client,r)['stage']=='awarded'
    action(client,r,'award',{'supplier':'A','reason':'duplicate'},422)


def test_tender_citations_verification_amendment_reset(client):
    r=create(client,'tender');source=upload(client,r,'Required: Company registration\nMust provide: maintenance plan')
    result=action(client,r,'extract',{'file_id':source});assert result['result']['candidates']==2
    item(client,r,'deadline',{'at':timestamp(15),'timezone':'Asia/Kolkata','decision':'Bid: capability confirmed'})
    evidence=upload(client,r,'Registration and maintenance plan')
    for i in workflow(client,r)['items']:
        if i['kind']=='requirement':
            d={k:v for k,v in i['data'].items() if not k.startswith('_')};d['file_id']=evidence;d['valid_until']=date_plus(30)
            response=client.put(f'/api/records/{r["id"]}/items/requirement/{i["id"]}',json={'revision':workflow(client,r)['revision'],'data':d});assert response.status_code==200,response.text
            action(client,r,'verify_requirement',{'item_id':i['id'],'note':'Source and evidence checked'})
    action(client,r,'ready');assert workflow(client,r)['stage']=='ready'
    action(client,r,'amendment',{'file_id':source,'note':'Updated submission instruction'})
    action(client,r,'ready',status=422)
    assert all(not i['data'].get('_verified') for i in workflow(client,r)['items'] if i['kind']=='requirement')


def test_handover_independent_review_and_critical_block(client,app):
    reviewer=colleague(client,app);r=create(client,'handover');file=upload(client,r)
    issue=item(client,r,'issue',{'room':'Kitchen','description':'Socket loose','severity':'Critical','assignee':'owner@example.test','due':date_plus(2),'file_id':file})['id']
    action(client,r,'waive',{'item_id':issue,'note':'Skip'},422)
    action(client,r,'close',status=422)
    action(client,r,'fixed',{'item_id':issue,'note':'Replaced socket','file_id':file})
    action(client,r,'verify_issue',{'item_id':issue,'note':'Self verify'},422)
    action(reviewer,r,'verify_issue',{'item_id':issue,'note':'Tested electrical safety'})
    # Every original intake snag is retained and must also be independently closed.
    for original in workflow(client,r)['items']:
        if original['kind']=='issue' and original['id']!=issue:
            action(client,r,'fixed',{'item_id':original['id'],'note':'Repaired original snag','file_id':file})
            action(reviewer,r,'verify_issue',{'item_id':original['id'],'note':'Original snag independently checked'})
    action(reviewer,r,'close');assert workflow(client,r)['stage']=='approved'


def prepare_order(client,quantity=5):
    p=deepcopy(CATALOG['orderdesk']['sample']);p['order_text']=f'{quantity} x TEA';r=create(client,'orderdesk',p)
    item(client,r,'catalogue',{'sku':'TEA','name':'Tea','aliases':'tea pack','unit':'each','pack':'10','price':'100','tax':'18','stock':'8'})
    action(client,r,'publish_catalogue');action(client,r,'parse_order');action(client,r,'confirm_order',{'confirmation':'Customer confirmed by phone reference CALL1'})
    return r


def test_order_reservations_compete_cancel_and_dispatch(client):
    first=prepare_order(client);second=prepare_order(client)
    action(client,first,'reserve');action(client,second,'reserve',status=422)
    assert client.get('/api/inventory').json()[0]['held']=='5'
    action(client,first,'cancel',{'reason':'Customer cancelled'})
    action(client,second,'reserve');action(client,second,'dispatch',{'reference':'DISPATCH1'})
    stock=client.get('/api/inventory').json()[0];assert stock['quantity']=='3' and stock['held']=='0'
    action(client,second,'dispatch',{'reference':'DISPATCH1'},422)
    # Republishing a catalogue must not restore the eight opening units.
    third=create(client,'orderdesk');item(client,third,'catalogue',{'sku':'TEA','name':'Tea','aliases':'','unit':'each','pack':'10','price':'120','tax':'18','stock':'100'})
    action(client,third,'publish_catalogue');assert client.get('/api/inventory').json()[0]['quantity']=='3'


def test_batch_atomic_consumption_quality_and_trace(client):
    r=create(client,'batch');file=upload(client,r)
    item(client,r,'recipe',{'version':'1','ingredient':'Flour','quantity':'10','unit':'kg'})
    item(client,r,'lot',{'lot':'F1','ingredient':'Flour','supplier':'Miller','quantity':'20','unit':'kg','cost':'50','expiry':date_plus(60),'quality':'Released','file_id':file})
    item(client,r,'usage',{'lot':'F1','quantity':'12','waste':'1','unit':'kg'})
    action(client,r,'receive_lots');action(client,r,'produce');assert workflow(client,r)['stage']=='produced'
    action(client,r,'produce',status=422)
    item(client,r,'dispatch',{'customer':'Shop','reference':'D1','quantity':'20'},422)
    action(client,r,'quality_release',{'checks':'Moisture and package checks passed','file_id':file})
    item(client,r,'dispatch',{'customer':'Shop','reference':'D1','quantity':'20'})
    trace=action(client,r,'trace');assert trace['workflow']['data']['trace']['inputs'][0]['affected_batches'][0]['id']==r['id']
    action(client,r,'recall',{'reason':'Supplier requested recall'})
    item(client,r,'dispatch',{'customer':'Shop','reference':'D2','quantity':'1'},422)


def test_fees_approved_agreement_receipts_refunds_and_guardian_sharing(client):
    r=create(client,'fees');p=r['payload']
    action(client,r,'ledger',{'kind':'payment','amount':'1','reference':'F1','date':date_plus(0),'note':'Cash received'},422)
    action(client,r,'approve_agreement',{'reason':'Discount approved'})
    action(client,r,'ledger',{'kind':'payment','amount':'100','reference':'F1','date':date_plus(0),'note':'Cash received'})
    out=action(client,r,'statement');doc=out['result']['document_id']
    assert client.post('/api/records/'+r['id']+'/shares',json={'document_id':doc,'recipient':'stranger@example.test'}).status_code==422
    item(client,r,'guardian',{'name':'Parent','email':'parent@example.test','reminders':'Yes'})
    assert client.post('/api/records/'+r['id']+'/shares',json={'document_id':doc,'recipient':'parent@example.test'}).status_code==201
    action(client,r,'ledger',{'kind':'refund','amount':'50','reference':'FR1','date':date_plus(0),'note':'Verified partial refund'})
    assert len(workflow(client,r)['overview']['entries'])==2


def test_renew_vendor_confirmation_and_calendar(client):
    r=create(client,'renew');file=upload(client,r)
    item(client,r,'terms',{'department':'Design','seats':'8','owner':'owner@example.test','backup':'backup@example.test','notice_clause':'Thirty calendar days notice','business_days':'No','holidays':'','file_id':file})
    action(client,r,'confirm_cancel',{'reference':'Vendor1','file_id':file},422)
    action(client,r,'decide',{'decision':'Cancel','reason':'No longer used'})
    action(client,r,'request_cancel',{'reference':'Request1','file_id':file});assert workflow(client,r)['stage']=='cancellation-requested'
    action(client,r,'confirm_cancel',{'reference':'Vendor1','file_id':file});assert workflow(client,r)['stage']=='vendor-confirmed'
    calendar=client.get('/api/records/'+r['id']+'/calendar.ics');assert calendar.status_code==200 and 'BEGIN:VEVENT' in calendar.text


def test_sop_authenticated_training_and_answer_privacy(client,app):
    staff=colleague(client,app,'viewer','staff@example.test');r=create(client,'sop')
    for n,text in enumerate(['Isolate power','Inspect protective equipment'],1):item(client,r,'step',{'position':str(n),'instruction':text,'prerequisites':'Trained operator','timestamp':'','file_id':''})
    question=item(client,r,'question',{'question':'What must be isolated?','answer':'Power'})['id']
    item(client,r,'assignment',{'employee':'staff@example.test','due':date_plus(3)})
    action(client,r,'publish',{'pass_percent':'80','review':'Safety officer approved steps'})
    assert '"answer":"Power"' not in json.dumps(workflow(staff,r),separators=(',',':'))
    action(staff,r,'assess',{'answers':[{'question_id':question,'answer':'Power'}]},422)
    action(staff,r,'acknowledge')
    failed=action(staff,r,'assess',{'answers':[{'question_id':question,'answer':'Nothing'}]});assert not failed['result']['passed']
    passed=action(staff,r,'assess',{'answers':[{'question_id':question,'answer':'power'}]});assert passed['result']['passed']
    item(client,r,'step',{'position':'3','instruction':'Change after publish','prerequisites':'','timestamp':'','file_id':''},409)


def test_claim_verified_provider_requirements_packet_and_outcome(client):
    r=create(client,'claimpack');file=upload(client,r)
    item(client,r,'template',{'provider':'Test processor','reason_code':'NR1','version':'2026-10','deadline':timestamp(10),'max_mb':'10','required_kinds':'Order\nDelivery','source':'Provider dispute checklist v2026-10'})
    evidence=[]
    for kind in ['Order','Delivery']:
        identifier=item(client,r,'evidence',{'kind':kind,'file_id':file,'fact':kind+' confirmation','redaction':''})['id'];evidence.append(identifier)
    item(client,r,'timeline',{'at':timestamp(-3),'fact':'Order delivered','evidence_id':evidence[1]})
    action(client,r,'pack',status=422)
    for identifier in evidence:action(client,r,'verify_evidence',{'item_id':identifier,'note':'Readable and matches order'})
    result=action(client,r,'pack');doc=result['result']['document_id'];assert client.get('/api/documents/'+doc+'/packet').status_code==200
    action(client,r,'submission',{'reference':'CASE123','file_id':file})
    action(client,r,'outcome',{'result':'Won','note':'Provider decided in merchant favor','file_id':file})
    assert workflow(client,r)['stage']=='won'


def test_disabled_external_delivery_is_visible_and_durable(tmp_path,monkeypatch):
    path=tmp_path/'jobs.db';monkeypatch.delenv('DOAIDE_DELIVERY_MODE',raising=False)
    with TestClient(create_app(path)) as c:
        c.post('/api/auth/register',json={'email':'owner@example.test','password':'another-long-test-password'})
        r,doc=approve_scope(c)
        with database(path) as db:
            from backend.operations import enqueue
            user=c.get('/api/auth/me').json();enqueue(db,r,user,'invoice',{'document_id':doc},'unique-invoice')
        result=run_once(path);assert result['state']=='blocked'
        assert 'disabled' in c.get('/api/jobs').json()[0]['last_error']
    with TestClient(create_app(path)) as c:
        c.post('/api/auth/login',json={'email':'owner@example.test','password':'another-long-test-password'})
        assert c.get('/api/jobs').json()[0]['state']=='blocked'


def test_signed_webhook_replay_and_payment_reference_deduplication(tmp_path,monkeypatch):
    path=tmp_path/'webhook.db';secret='synthetic-webhook-test-secret';monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET',secret)
    with TestClient(create_app(path)) as c:
        c.post('/api/auth/register',json={'email':'owner@example.test','password':'another-long-test-password'})
        p=deepcopy(CATALOG['collect']['sample']);p.update(promise='',paid='0',amount='1000');r=create(c,'collect',p)
        job=action(c,r,'payment_link',{'email':'customer@example.test'})['result']['job_id']
        body={'event':'payment_link.partially_paid','payload':{'payment_link':{'entity':{'id':'plink_TEST','reference_id':job,'amount':100000,'currency':'INR'}},'payment':{'entity':{'id':'pay_TEST','amount':25000,'currency':'INR','status':'captured'}}}}
        raw=json.dumps(body).encode();signature=hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest();headers={'X-Razorpay-Signature':signature,'X-Razorpay-Event-Id':'evt1'}
        assert c.post('/api/webhooks/razorpay',content=raw).status_code==401
        assert c.post('/api/webhooks/razorpay',content=raw,headers=headers).status_code==200
        assert c.post('/api/webhooks/razorpay',content=raw,headers=headers).json()['duplicate']
        headers['X-Razorpay-Event-Id']='evt2';assert c.post('/api/webhooks/razorpay',content=raw,headers=headers).status_code==200
        assert workflow(c,r)['overview']['balance_paise']==75000
        assert len(workflow(c,r)['overview']['entries'])==1


def test_new_scope_revision_preserves_accepted_pdf(client):
    r,doc=approve_scope(client)
    before=client.get('/api/documents/'+doc).json()
    response=client.post('/api/records/'+r['id']+'/revisions',json={'revision':workflow(client,r)['revision'],'data':{}})
    assert response.status_code==201,response.text
    new={'id':response.json()['record_id']};assert workflow(client,new)['stage']=='draft'
    assert len(workflow(client,new)['items'])==2
    assert client.get('/api/documents/'+doc).json()['checksum']==before['checksum']
    assert client.get('/api/records/'+new['id']).json()['payload']==r['payload']


def test_batch_reservations_and_returns_preserve_history(client):
    first=create(client,'batch');file=upload(client,first)
    item(client,first,'lot',{'lot':'SHARED','ingredient':'Flour','supplier':'Miller','quantity':'20','unit':'kg','cost':'50','expiry':date_plus(50),'quality':'Released','file_id':file})
    action(client,first,'receive_lots')
    item(client,first,'recipe',{'version':'1','ingredient':'Flour','quantity':'10','unit':'kg'})
    item(client,first,'usage',{'lot':'SHARED','quantity':'12','waste':'1','unit':'kg'})
    p=deepcopy(CATALOG['batch']['sample']);p['batch_number']='SECOND';second=create(client,'batch',p)
    item(client,second,'recipe',{'version':'1','ingredient':'Flour','quantity':'10','unit':'kg'})
    item(client,second,'usage',{'lot':'SHARED','quantity':'12','waste':'0','unit':'kg'})
    action(client,first,'reserve_materials');action(client,second,'reserve_materials',status=422)
    action(client,first,'produce')
    initial=workflow(client,first)['data']['production']['total_paise']
    action(client,first,'return_material',{'lot':'SHARED','quantity':'4','reference':'RETURN1','reason':'Unused material returned'})
    assert workflow(client,first)['data']['production']['total_paise']==initial
    assert workflow(client,first)['data']['returns'][0]['cost_reduction_paise']==20000
    action(client,second,'reserve_materials')
    assert next(i for i in client.get('/api/inventory').json() if i['sku']=='lot:SHARED')['held']=='12'


def test_contractor_link_is_limited_to_assigned_snag(client,app):
    r=create(client,'handover');i=item(client,r,'issue',{'room':'Office','description':'Repair hinge','severity':'Minor','assignee':'contractor@example.test','due':date_plus(3),'file_id':''})['id']
    response=client.post('/api/records/'+r['id']+'/contractor-links',json={'item_id':i,'recipient':'contractor@example.test'});assert response.status_code==201,response.text
    token=response.json()['path'].split('=')[1]
    with TestClient(app) as external:
        task=external.get('/api/contractor/'+token);assert task.status_code==200
        assert task.json()['issue']['room']=='Office' and 'Kitchen' not in task.text
        assert external.get('/api/records/'+r['id']).status_code==401
        report=external.post('/api/contractor/'+token+'/report',data={'email':'contractor@example.test','notes':'Hinge replaced and tested'},files={'file':('photo-notes.txt',b'Repair evidence','text/plain')});assert report.status_code==200,report.text
        assert external.get('/api/contractor/'+token).status_code==404
    action(client,r,'verify_issue',{'item_id':i,'note':'Checked repaired hinge'})


def test_invoice_adapter_retries_with_stable_key_and_records_external_id(tmp_path,monkeypatch):
    import httpx
    path=tmp_path/'adapter.db';monkeypatch.setenv('DOAIDE_DELIVERY_MODE','enabled');monkeypatch.setenv('DOAIDE_INVOICE_ADAPTER_URL','https://adapter.example.test/draft-invoices');monkeypatch.setenv('DOAIDE_INVOICE_ADAPTER_TOKEN','synthetic-token')
    with TestClient(create_app(path)) as c:
        c.post('/api/auth/register',json={'email':'owner@example.test','password':'another-long-test-password'});r,doc=approve_scope(c)
        with database(path) as db:
            from backend.operations import enqueue
            job_id=enqueue(db,r,c.get('/api/auth/me').json(),'invoice',{'document_id':doc},'adapter-test')
        calls=[]
        def respond(request):
            calls.append(request.headers['Idempotency-Key'])
            return httpx.Response(503 if len(calls)==1 else 200,json={} if len(calls)==1 else {'invoice_id':'DRAFT-123'})
        transport=httpx.MockTransport(respond)
        assert run_once(path,transport)['state']=='failed'
        with database(path) as db:db.execute("UPDATE jobs SET due_at='2000-01-01T00:00:00+00:00' WHERE id=?",(job_id,))
        assert run_once(path,transport)['state']=='delivered'
        assert calls==[job_id,job_id]
        assert workflow(c,r)['data']['external_invoices'][doc]=='DRAFT-123'


def test_file_retention_keeps_manifest_and_revokes_bytes(tmp_path,monkeypatch):
    from scripts.retention import retention
    path=tmp_path/'retention.db'
    with TestClient(create_app(path)) as c:
        c.post('/api/auth/register',json={'email':'owner@example.test','password':'another-long-test-password'});r=create(c);file=upload(c,r)
        with database(path) as db:db.execute("UPDATE file_controls SET retain_until='2000-01-01T00:00:00+00:00' WHERE file_id=?",(file,))
        assert len(retention(path)['files'])==1
        assert c.get('/api/files/'+file).status_code==200
        assert retention(path,True)['mode']=='applied'
        assert c.get('/api/files/'+file).status_code==410
        assert workflow(c,r)['files'][0]['checksum']
        item(c,r,'baseline',{'reference':'Purged source','text':'Cannot cite unavailable content','file_id':file},422)


def test_client_decline_blocks_invoice(client):
    r,doc=approve_scope(client);share=client.post('/api/records/'+r['id']+'/shares',json={'document_id':doc,'recipient':'client@example.test','purpose':'accept'}).json();portal=client.get('/api/portal/'+share['token']).json()
    body={'name':'Client Person','email':'client@example.test','checksum':portal['checksum'],'agree':True,'decision':'decline','comments':'Please reduce the scope'}
    assert client.post('/api/portal/'+share['token']+'/accept',json=body).status_code==200
    assert client.get('/api/portal/'+share['token']).json()['decision']['decision']=='decline'
    assert workflow(client,r)['stage']=='declined'
    action(client,r,'invoice',status=422)


def test_two_concurrent_stock_reservations_cannot_overspend(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path=tmp_path/'concurrency.db'
    with TestClient(create_app(path)) as c:
        c.post('/api/auth/register',json={'email':'owner@example.test','password':'another-long-test-password'})
        records=[prepare_order(c),prepare_order(c)]
        versions={r['id']:workflow(c,r)['revision'] for r in records};cookies=dict(c.cookies)
        def reserve(r):
            with TestClient(create_app(path)) as other:
                other.cookies.update(cookies)
                return other.post('/api/records/'+r['id']+'/actions/reserve',json={'revision':versions[r['id']],'data':{}},headers={'Idempotency-Key':str(uuid4())}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(reserve,records))
        assert sorted(statuses)==[200,422]
        assert c.get('/api/inventory').json()[0]['held']=='5'


def test_order_cannot_republish_catalogue_while_stock_is_reserved(client):
    r=prepare_order(client);action(client,r,'reserve')
    action(client,r,'publish_catalogue',status=422)
    assert workflow(client,r)['stage']=='reserved'
    action(client,r,'cancel',{'reason':'Release test reservation'})
    assert client.get('/api/inventory').json()[0]['held']=='0'


def test_superseded_sop_cannot_be_republished(client):
    r=create(client,'sop')
    for n in (1,2):item(client,r,'step',{'position':str(n),'instruction':f'Safety step {n}','prerequisites':'','timestamp':'','file_id':''})
    action(client,r,'publish',{'pass_percent':'80','review':'Reviewed'})
    revision=client.post('/api/records/'+r['id']+'/revisions',json={'revision':workflow(client,r)['revision'],'data':{}}).json();new={'id':revision['record_id']}
    action(client,new,'publish',{'pass_percent':'80','review':'Updated review'})
    assert workflow(client,r)['stage']=='superseded'
    action(client,r,'publish',{'pass_percent':'80','review':'Revive old version'},422)


def test_local_ocr_worker_preserves_source_locators(tmp_path):
    import shutil,subprocess
    if not shutil.which('tesseract') or not shutil.which('pdftoppm'):pytest.skip('Local OCR binaries are optional')
    from reportlab.pdfgen import canvas
    path=tmp_path/'ocr.db';pdf=tmp_path/'source.pdf'
    document=canvas.Canvas(str(pdf));document.setFont('Helvetica',24);document.drawString(70,700,'Required: company registration');document.save()
    subprocess.run(['pdftoppm','-singlefile','-r','120','-png',str(pdf),str(tmp_path/'scan')],check=True,capture_output=True)
    with TestClient(create_app(path)) as c:
        c.post('/api/auth/register',json={'email':'ocr@example.test','password':'another-long-test-password'});r=create(c,'tender')
        uploaded=c.post('/api/records/'+r['id']+'/files',files={'file':('scan.png',(tmp_path/'scan.png').read_bytes(),'image/png')});assert uploaded.status_code==201,uploaded.text
        file_id=uploaded.json()['id'];assert uploaded.json()['extraction_status']=='needs-ocr'
        assert c.post('/api/files/'+file_id+'/ocr').status_code==200
        result=run_once(path);assert result['state']=='delivered'
        file=workflow(c,r)['files'][0];assert file['extraction_status']=='ocr-needs-review'
        assert '[OCR page 1, line' in file['extracted'] and 'registration' in file['extracted'].lower()


def auth_link_from_queue(path):
    from urllib.parse import urlsplit,parse_qs
    with database(path) as db:
        data=json.loads(db.execute("SELECT data FROM jobs WHERE kind='auth-email' ORDER BY created_at DESC LIMIT 1").fetchone()[0])
        link=next(line for line in data['message'].splitlines() if line.startswith('http'))
    return parse_qs(urlsplit(link).query)['token'][0]


def test_email_verification_required_and_single_use(tmp_path,monkeypatch):
    path=tmp_path/'verification.db';monkeypatch.setenv('DOAIDE_REQUIRE_VERIFIED_EMAIL','true')
    with TestClient(create_app(path)) as c:
        credentials={'email':'verify@example.test','password':'another-long-test-password'}
        response=c.post('/api/auth/register',json=credentials);assert response.status_code==201 and response.json()['verification_required']
        assert c.get('/api/records').status_code==401
        assert c.post('/api/auth/login',json=credentials).status_code==403
        token=auth_link_from_queue(path)
        assert c.post('/api/auth/verify',json={'token':token}).status_code==200
        assert c.post('/api/auth/verify',json={'token':token}).status_code==422
        assert c.post('/api/auth/login',json=credentials).status_code==200
        assert c.get('/api/records').status_code==200


def test_password_recovery_revokes_sessions_and_old_links(tmp_path):
    path=tmp_path/'recovery.db'
    with TestClient(create_app(path)) as c:
        credentials={'email':'recover@example.test','password':'another-long-test-password'}
        c.post('/api/auth/register',json=credentials);old_cookie=c.cookies.get('doaide_session')
        exists=c.post('/api/auth/request-reset',json={'email':credentials['email']})
        absent=c.post('/api/auth/request-reset',json={'email':'missing@example.test'})
        assert exists.json()==absent.json()
        first=auth_link_from_queue(path)
        c.post('/api/auth/request-reset',json={'email':credentials['email']});latest=auth_link_from_queue(path)
        assert first!=latest
        body={'token':first,'password':'new-synthetic-test-password'}
        assert c.post('/api/auth/reset',json=body).status_code==422
        assert c.post('/api/auth/reset',json={**body,'token':latest}).status_code==200
        assert c.get('/api/records',headers={'Cookie':'doaide_session='+old_cookie}).status_code==401
        assert c.post('/api/auth/login',json=credentials).status_code==401
        assert c.post('/api/auth/login',json={**credentials,'password':body['password']}).status_code==200
        assert c.post('/api/auth/reset',json={**body,'token':latest}).status_code==422


def test_access_logs_redact_bearer_links():
    from backend.logging_config import redact_path
    assert redact_path('/api/portal/secret-value/accept')=='/api/portal/[redacted]/accept'
    assert redact_path('/api/contractor/secret-value/report')=='/api/contractor/[redacted]/report'
    assert 'secret-value' not in redact_path('/?auth=reset&token=secret-value')
    assert 'secret-value' not in redact_path('/?invite=secret-value')
    assert redact_path('/api/records?offset=500')=='/api/records?offset=500'


def test_shared_pdf_is_frozen_and_omits_internal_approval_policy(client):
    r,doc=approve_scope(client)
    item(client,r,'policy',{'limit':'12345','days':'5'})
    doc=action(client,r,'approve',{'reason':'Approved for customer review'})['result']['document_id']
    link=client.post('/api/records/'+r['id']+'/shares',json={'document_id':doc,'recipient':'customer@example.test'}).json()
    first=client.get('/api/portal/'+link['token']+'/pdf');assert first.status_code==200
    assert first.content==client.get('/api/portal/'+link['token']+'/pdf').content
    text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(first.content)).pages)
    assert '12345' not in text and 'Change estimate' in text
    client.delete('/api/shares/'+link['id'])
    assert client.get('/api/portal/'+link['token']+'/pdf').status_code==404
