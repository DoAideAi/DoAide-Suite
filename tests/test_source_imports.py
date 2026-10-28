from copy import deepcopy
import json
import httpx
import pytest
from backend.catalog import CATALOG
from backend.worker import run_once
from test_api import app,client,create
from test_operations import action,item,workflow,upload,date_plus,colleague,timestamp


def connect(c,m,service,**config):
    w=c.get('/api/auth/me').json()['workspace_id']
    m.setenv('DOAIDE_'+service+'_CONNECTIONS',json.dumps({w:{'url':'https://source.test/api','token':'synthetic-only',**config}}));m.setenv('DOAIDE_DELIVERY_MODE','enabled')


def latest(c,r):return [x for x in workflow(c,r)['items'] if x['kind']=='source_import'][-1]


def run(path,respond):
    result=run_once(path,httpx.MockTransport(respond));assert result['state']=='delivered',result


def test_desk_import_pagination_review_immutable_source_and_tenant_guard(client,tmp_path,monkeypatch):
    c=client;r=create(c,'orderdesk');connect(c,monkeypatch,'DESK',business_id='B1')
    def respond(req):
        assert req.method=='GET'
        if req.url.path.endswith('/messages'):
            page=2 if req.url.params.get('cursor') else 1
            return httpx.Response(200,json={'data':[{'id':'M'+str(page),'business_id':'B1','conversation_id':'C1','created_at':timestamp(-page),'direction':'INBOUND','text_content':str(page)+' x TEA'}],'hasMore':page==1,'cursor':'second' if page==1 else None})
        return httpx.Response(200,json={'id':'C1','business_id':'B1','subject':'Order'})
    action(c,r,'import_desk_conversation',{'source_id':'C1'});run(tmp_path/'test.db',respond)
    source=latest(c,r);assert len(source['data']['source']['messages'])==2
    assert not any(x['kind']=='message' for x in workflow(c,r)['items'])
    item(c,r,'source_import',{},422)
    action(c,r,'apply_source',{'import_id':source['id'],'reason':'Reviewed customer request'})
    messages=[x for x in workflow(c,r)['items'] if x['kind']=='message'];assert messages[0]['data']['text']=='2 x TEA\n1 x TEA'
    action(c,r,'apply_source',{'import_id':source['id'],'reason':'Duplicate'},422)
    action(c,r,'import_desk_conversation',{'source_id':'C2'})
    assert run_once(tmp_path/'test.db',httpx.MockTransport(lambda req:httpx.Response(200,json={'id':'C2','business_id':'other'})))['state']=='blocked'


def test_desk_order_maps_actual_dto_and_claim_evidence_stays_unverified(client,tmp_path,monkeypatch):
    r=create(client,'claimpack');connect(client,monkeypatch,'DESK',business_id='B1')
    action(client,r,'import_desk_order',{'source_id':'O1'})
    run(tmp_path/'test.db',lambda req:httpx.Response(200,json={'id':'O1','businessId':'B1','lineItems':[{'sku':'TEA','name':'Tea','quantity':2}],'currency':'INR'}))
    source=latest(client,r);action(client,r,'apply_source',{'import_id':source['id'],'reason':'Order confirms purchase'})
    evidence=next(x for x in workflow(client,r)['items'] if x['kind']=='evidence');assert evidence['data'].get('_status')!='verified'


def test_realty_property_and_proposal_template_review(client,tmp_path,monkeypatch):
    connect(client,monkeypatch,'REALTY',agent_id=4);r=create(client,'handover');action(client,r,'import_realty_property',{'source_id':8})
    run(tmp_path/'test.db',lambda req:httpx.Response(200,json={'id':8,'agent_id':4,'title':'Flat A','city':'Pune','locality':'Central'}))
    action(client,r,'apply_source',{'import_id':latest(client,r)['id'],'reason':'Correct inspection site'})
    assert next(x for x in workflow(client,r)['items'] if x['kind']=='property_reference')['data']['title']=='Flat A'
    connect(client,monkeypatch,'PROPOSALS',business_id=2);r=create(client,'scope');action(client,r,'import_proposal_template',{'source_id':7})
    run(tmp_path/'test.db',lambda req:httpx.Response(200,json={'business':{'id':2}} if req.url.path.endswith('/me') else {'id':7,'name':'Web offer','default_terms':'Payment in 30 days','sections':[{'title':'Deliverables','content':'Five pages'}],'pricing_table':{}}))
    action(client,r,'apply_source',{'import_id':latest(client,r)['id'],'reason':'Reviewed offer template'})
    w=workflow(client,r);assert any(x['kind']=='offer_template' for x in w['items']) and not any(x['kind']=='baseline' for x in w['items'])
    assert not w['data'].get('accepted_document')


def test_khata_payment_requires_review_deduplicates_across_records_and_preserves_account(client,tmp_path,monkeypatch):
    c=client;connect(c,monkeypatch,'KHATA',account_email='shop@example.test');r=create(c,'collect')
    tx={'id':'TX1','customerId':'C1','type':'received','amount':'100.25','date':date_plus(0)}
    def respond(req):return httpx.Response(200,json={'account_email':'shop@example.test','ledger':{'customers':[{'id':'C1','name':'Customer'}],'transactions':[tx],'bills':[]}})
    action(c,r,'import_khata_customer',{'source_id':'C1'});run(tmp_path/'test.db',respond)
    before=workflow(c,r)['overview']['balance_paise'];source=latest(c,r)
    body={'import_id':source['id'],'transaction_id':'TX1','customer_confirmation':r['payload']['customer'],'reason':'Matched bank receipt and customer'}
    action(c,r,'reconcile_khata_payment',{**body,'customer_confirmation':'Wrong'},422)
    action(c,r,'reconcile_khata_payment',body);assert workflow(c,r)['overview']['balance_paise']==before-10025
    action(c,r,'reconcile_khata_payment',body,422)
    second=create(c,'collect');action(c,second,'import_khata_customer',{'source_id':'C1'});run(tmp_path/'test.db',respond)
    action(c,second,'reconcile_khata_payment',{**body,'import_id':latest(c,second)['id']},422)


def test_payroll_whitelist_assigns_only_existing_members(client,app,tmp_path,monkeypatch):
    c=client;connect(c,monkeypatch,'PAYROLL',business_id=2);r=create(c,'sop')
    item(c,r,'step',{'position':1,'instruction':'Wash hands','prerequisites':'','timestamp':'','file_id':''})
    item(c,r,'step',{'position':2,'instruction':'Check equipment','prerequisites':'','timestamp':'','file_id':''})
    item(c,r,'question',{'question':'First step?','answer':'Wash hands'})
    action(c,r,'publish',{'pass_percent':80,'review':'Approved safe procedure'})
    action(c,r,'import_payroll_roster')
    employees=[{'id':1,'employee_code':'E1','email':'owner@example.test','full_name':'Owner','is_active':True,'employment_status':'active','pan':'PRIVATE'},{'id':2,'employee_code':'E2','email':'outsider@example.test','is_active':True,'employment_status':'active'}]
    run(tmp_path/'test.db',lambda req:httpx.Response(200,json={'data':{'business':{'id':2}}} if req.url.path.endswith('/me') else {'data':{'employees':employees,'total':2}}))
    source=latest(c,r);assert 'PRIVATE' not in json.dumps(source)
    action(c,r,'assign_payroll_staff',{'import_id':source['id'],'employees':[{'employee_id':2}],'due':date_plus(7)},422)
    assert not any(x['kind']=='assignment' for x in workflow(c,r)['items'])
    action(c,r,'assign_payroll_staff',{'import_id':source['id'],'employees':[{'employee_id':1}],'due':date_plus(7)})
    assert any(x['kind']=='assignment' for x in workflow(c,r)['items'])


def test_enrollment_csv_preview_and_explicit_record_match(client):
    r=create(client,'fees');content='student_reference,course_reference,start,end,terms\nST1,COURSE1,'+date_plus(0)+','+date_plus(90)+',Approved terms\n'
    f=client.post('/api/records/'+r['id']+'/files',files={'file':('enrollment.csv',content.encode(),'text/csv')}).json()['id']
    action(client,r,'preview_enrollment_csv',{'file_id':f});source=latest(client,r)
    body={'import_id':source['id'],'student_reference':'ST1','course_reference':'COURSE1','student_confirmation':r['payload']['student']}
    action(client,r,'apply_enrollment',body)
    assert next(x for x in workflow(client,r)['items'] if x['kind']=='enrollment')['data']['course_reference']=='COURSE1'
    action(client,r,'apply_enrollment',body,422)


def test_stale_import_never_overwrites_edited_draft(client,tmp_path,monkeypatch):
    connect(client,monkeypatch,'REALTY',agent_id=4);r=create(client,'handover');action(client,r,'import_realty_property',{'source_id':8})
    item(client,r,'room',{'name':'Kitchen','checklist':'Lights'})
    calls=[]
    result=run_once(tmp_path/'test.db',httpx.MockTransport(lambda req:calls.append(req)))
    assert result['state']=='blocked' and not calls and not any(x['kind']=='source_import' for x in workflow(client,r)['items'])
