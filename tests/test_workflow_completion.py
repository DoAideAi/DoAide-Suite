"""Acceptance journeys for workflows added after the v0.3 scope audit."""
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.catalog import CATALOG
from backend.db import database
from backend.worker import run_once
from test_api import app, client, create
from test_operations import action, colleague, date_plus, item, timestamp, upload, workflow, prepare_order


def test_scope_comparison_requires_current_cited_sources(client):
    r=create(client);item(client,r,'baseline',{'reference':'Contract §1','text':'Five page website with two revisions','file_id':''})
    result=action(client,r,'compare_baseline')['result']['comparison']
    assert result['clauses'][0]['reference']=='Contract §1' and result['uncertainty']
    action(client,r,'review_comparison',{'decision':'Change required','reason':'Login is excluded'})
    item(client,r,'baseline',{'reference':'Contract §2','text':'Customer login included','file_id':''})
    action(client,r,'review_comparison',{'decision':'In scope','reason':'New clause reviewed'},422)


def test_collection_case_outcome_stops_pause_and_is_immutable(client):
    p=deepcopy(CATALOG['collect']['sample']);p['promise']='';r=create(client,'collect',p);f=upload(client,r)
    case=item(client,r,'promise',{'kind':'Dispute','until':'','note':'Missing delivery','amount':'100','owner':'owner@example.test','next_action':'Inspect proof','file_id':f})['id']
    assert workflow(client,r)['overview']['reminder_pause']=='Open dispute'
    action(client,r,'resolve_case',{'item_id':case,'outcome':'Kept','reason':'wrong kind','file_id':f},422)
    action(client,r,'resolve_case',{'item_id':case,'outcome':'Resolved','reason':'Delivery acknowledged','file_id':f})
    assert not workflow(client,r)['overview']['reminder_pause']
    response=client.request('DELETE',f'/api/records/{r["id"]}/items/promise/{case}',json={'revision':workflow(client,r)['revision'],'data':{}})
    assert response.status_code==409
    document=action(client,r,'customer_statement')['result']['document_id']
    assert client.get('/api/documents/'+document+'/pdf').content.startswith(b'%PDF')


def test_contact_frequency_is_shared_between_customer_invoices(client):
    p=deepcopy(CATALOG['collect']['sample']);p['promise']='';p['due']=date_plus(1)
    records=[create(client,'collect',p),create(client,'collect',{**p,'invoice':'SECOND'})]
    policy={'recipient':'customer@example.test','days':'1,2,3,10','minimum_hours':'48','weekly_limit':'2','start_hour':'9','end_hour':'18','consent':'Yes','subject':'Invoice reminder','message':'Please review your statement'}
    for r in records:item(client,r,'cadence',policy)
    out=action(client,records[0],'schedule_sequence')['result'];assert out['jobs'] and out.get('skipped')
    action(client,records[1],'schedule_sequence',status=422)


def test_amc_serial_identity_customer_window_and_scoped_technician(client):
    p=deepcopy(CATALOG['amc']['sample']);p['completed']='0';r=create(client,'amc',p)
    data={'site':'Cafe','manufacturer':'Acme','serial':'SN1','model':'RO','warranty':'','coverage':'Annual service'}
    asset=item(client,r,'asset',data)['id'];item(client,r,'asset',data,422)
    other=create(client,'amc',p);item(client,other,'asset',{**data,'manufacturer':'Different maker'})
    visit={'asset_id':asset,'technician':'external@example.test','access':'Assigned link','start':timestamp(-2),'end':timestamp(-1),'chargeable':'No','checklist':'Pressure\nFilter','window_start':timestamp(-3),'window_end':timestamp(1)}
    identifier=item(client,r,'visit',visit)['id']
    item(client,r,'visit',{**visit,'window_end':timestamp(-3)},422)
    link=client.post(f'/api/records/{r["id"]}/contractor-links',json={'item_id':identifier,'recipient':'external@example.test'}).json()['path'].split('=')[1]
    public=client.get('/api/contractor/'+link).json();assert public['kind']=='amc' and 'contract_value' not in json.dumps(public)
    endpoint='/api/contractor/'+link+'/report';base={'email':'external@example.test','notes':'Serviced equipment'}
    assert client.post(endpoint,data=base,files={'file':('visit.txt',b'Service evidence')}).status_code==422
    response=client.post(endpoint,data={**base,'readings':json.dumps({'Pressure':'3 bar','Filter':'Replaced'})},files={'file':('visit.txt',b'Service evidence')})
    assert response.status_code==200,response.text
    assert client.get('/api/contractor/'+link).status_code==404
    action(client,r,'verify_visit',{'item_id':identifier})
    assert workflow(client,r)['overview']['verified_this_period']==1


def test_amc_customer_accepts_exact_offer_before_invoice_and_rollover(client):
    r=create(client,'amc');offer={'start':date_plus(30),'end':date_plus(395),'value':'9000','included':'4','valid_until':date_plus(10),'contact':'customer@example.test','terms':'Annual service including four visits'}
    doc=action(client,r,'renewal_offer',offer)['result']['document_id']
    action(client,r,'activate_renewal',status=422)
    share=client.post(f'/api/records/{r["id"]}/shares',json={'document_id':doc,'recipient':'customer@example.test','purpose':'accept'})
    assert share.status_code==201,share.text
    token=share.json()['token'];portal=client.get('/api/portal/'+token).json()
    response=client.post('/api/portal/'+token+'/accept',json={'name':'Customer','email':'customer@example.test','checksum':portal['checksum'],'agree':True})
    assert response.status_code==200,response.text
    out=action(client,r,'activate_renewal')['result'];assert out['record_id']!=r['id'] and out['job_id']
    action(client,r,'activate_renewal',status=422)


def test_rfq_landed_components_revision_export_and_clarification_gate(client):
    r=create(client,'rfq');f=upload(client,r);req=item(client,r,'requirement',{'sku':'TEA','specification':'Tea','quantity':'10','unit':'each'})['id']
    data={'supplier':'=UNTRUSTED()','requirement_id':req,'file_id':f,'quantity':'10','unit':'each','price':'100','currency':'INR','fx':'1','fx_basis':'Same currency','discount':'0','tax':'10','freight':'100','lead_days':'2','equivalent':'Yes','exclusions':'','freight_tax':'5','duties':'20','packaging':'50','packaging_tax':'10','valid_until':date_plus(10),'payment_terms':'Net 30','source_line':'p1 line 2'}
    quote=item(client,r,'offer',data)['id']
    assert action(client,r,'compare')['workflow']['data']['comparison'][0]['total_paise']==128000
    item(client,r,'clarification',{'supplier':data['supplier'],'question':'Confirm certificate','answer':'','file_id':''})
    item(client,r,'evaluation',{'supplier':data['supplier'],'score':'90','rationale':'Meets requirements'})
    action(client,r,'award',{'supplier':data['supplier'],'reason':'Best value'},422)
    action(client,r,'quote_revision',{'item_id':quote,'price':'90','discount':'0','freight':'100','lead_days':'2','file_id':f,'reason':'Supplier revised unit price'})
    exported=action(client,r,'comparison_export')['result'];content=client.get(exported['download_url']).text
    assert "'=UNTRUSTED()" in content and 'Unanswered supplier clarification' in content
    assert workflow(client,r)['data']['quote_revisions'][0]['before']['price']=='100'


def test_targeted_tender_amendment_preserves_unaffected_verification(client):
    r=create(client,'tender');f=upload(client,r);item(client,r,'deadline',{'at':timestamp(20),'timezone':'Asia/Kolkata','decision':'Bid','portal':'Procurement portal','clarification_at':timestamp(10)})
    ids=[]
    for title in ['Registration','Insurance']:
        identifier=item(client,r,'requirement',{'text':title,'citation':'Page 1','category':'Eligibility','owner':'owner@example.test','due':date_plus(10),'file_id':f,'valid_until':date_plus(30),'interpretation':'Mandatory','condition':'','applies':''})['id'];ids.append(identifier)
        action(client,r,'verify_requirement',{'item_id':identifier,'note':'Evidence verified'})
    action(client,r,'ready')
    action(client,r,'targeted_amendment',{'file_id':f,'affected':[{'item_id':ids[0],'change':'Updated registration required'}],'reason':'Amendment reviewed against both requirements'})
    values={x['id']:x['data'] for x in workflow(client,r)['items'] if x['kind']=='requirement'}
    assert not values[ids[0]].get('_verified') and values[ids[1]]['_verified']
    action(client,r,'ready',status=422)


def test_conditional_tender_requirement_needs_human_applicability(client):
    r=create(client,'tender');f=upload(client,r)
    identifier=item(client,r,'requirement',{'text':'Import certificate','citation':'Page 5','category':'Eligibility','owner':'owner@example.test','due':date_plus(10),'file_id':'','valid_until':'','interpretation':'Conditional','condition':'For imported goods','applies':'Unreviewed'})['id']
    action(client,r,'verify_requirement',{'item_id':identifier,'note':'No imported goods'},422)


def test_handover_template_assignment_and_repair_progress(client,app):
    worker=colleague(client,app,'operator','worker@example.test');r=create(client,'handover')
    template=item(client,r,'inspection_template',{'name':'Kitchen','checks':[{'category':'Plumbing','description':'Tap leak check','severity':'Minor'}]})['id']
    issue=action(client,r,'apply_template',{'template_id':template,'room':'Kitchen','assignee':'worker@example.test','due':date_plus(5)})['result']['issues'][0]
    action(client,r,'acknowledge_issue',{'item_id':issue},422)
    action(worker,r,'start_repair',{'item_id':issue},422)
    action(worker,r,'acknowledge_issue',{'item_id':issue});action(worker,r,'start_repair',{'item_id':issue})
    f=upload(worker,r);action(worker,r,'fixed',{'item_id':issue,'note':'Tap repaired','file_id':f});action(client,r,'verify_issue',{'item_id':issue,'note':'No leak'})
    action(client,r,'bulk_assign',{'issues':[{'item_id':issue}],'assignee':'owner@example.test','due':date_plus(4)},422)


def test_order_backorder_freight_override_expiry_and_invoice(client,tmp_path):
    r=prepare_order(client,5);item(client,r,'delivery',{'requested_on':date_plus(4),'address':'Shop 1','freight':'50','tax':'10','hold_hours':'1'})
    f=upload(client,r)
    action(client,r,'review_order',{'lines':[{'sku':'TEA','quantity':'12','source':'Customer approved 12 TEA'}],'reason':'Reviewed text'})
    out=action(client,r,'plan_backorder',{'promised_on':date_plus(10),'agreement':'Customer agreed partial delivery'})['result']
    assert out['record_id']!=r['id']
    order=workflow(client,r)['data']['parsed_order'];assert order['lines'][0]['quantity']==8 and order['freight_paise']==5500
    action(client,r,'price_override',{'sku':'TEA','price':'90','reason':'Manager approved customer price','file_id':f})
    action(client,r,'confirm_order',{'confirmation':'Customer confirmed partial order'});action(client,r,'reserve')
    with database(tmp_path/'test.db') as db:
        row=db.execute('SELECT data FROM operations WHERE record_id=?',(r['id'],)).fetchone();data=json.loads(row[0]);data['reservation_expires_at']=timestamp(-1);db.execute('UPDATE operations SET data=? WHERE record_id=?',(json.dumps(data),r['id']))
    action(client,r,'dispatch',{'reference':'SHIP1'},422)
    run_once(tmp_path/'test.db');assert client.get('/api/inventory').json()[0]['held']=='0'
    action(client,r,'review_order',{'lines':[{'sku':'TEA','quantity':'8','source':'Reconfirmed available stock'}],'reason':'After expiry'})
    action(client,r,'confirm_order',{'confirmation':'Fresh customer confirmation'});action(client,r,'reserve');action(client,r,'dispatch',{'reference':'SHIP1'})
    assert action(client,r,'invoice_order')['result']['job_id']
    action(client,r,'invoice_order',status=422)


def make_batch(c):
    r=create(c,'batch');f=upload(c,r)
    item(c,r,'recipe',{'version':'1','ingredient':'Flour','quantity':'10','unit':'kg','effective_from':date_plus(-10),'effective_until':date_plus(30)})
    item(c,r,'lot',{'lot':'F1','ingredient':'Flour','supplier':'Miller','quantity':'20','unit':'kg','cost':'50','expiry':date_plus(60),'quality':'Released','file_id':f})
    item(c,r,'usage',{'lot':'F1','quantity':'10','waste':'0','unit':'kg'})
    item(c,r,'cost',{'category':'Packaging','reference':'BOX1','amount':'100','file_id':f})
    action(c,r,'receive_lots');action(c,r,'produce');return r,f


def test_batch_cost_reversal_and_disposal_preserve_original_production(client):
    r,f=make_batch(client);original=workflow(client,r)['data']['production'];assert original['total_paise']==60000
    action(client,r,'cost_adjustment',{'reference':'COR1','direction':'Increase','amount':'25','reason':'Packaging invoice correction','file_id':f})
    action(client,r,'reverse_cost',{'reference':'COR1','reversal':'REV1','reason':'Supplier withdrew correction','file_id':f})
    action(client,r,'reverse_cost',{'reference':'COR1','reversal':'REV2','reason':'Duplicate attempt','file_id':f},422)
    assert workflow(client,r)['data']['production']==original
    action(client,r,'cost_adjustment',{'reference':'ZERO','direction':'Decrease','amount':'600','reason':'Fully credited cost','file_id':f})
    before=client.get('/api/inventory').json()
    action(client,r,'return_material',{'lot':'F1','quantity':'1','reference':'RETURN-ZERO','reason':'Would double-credit cost'},422)
    assert client.get('/api/inventory').json()==before and not workflow(client,r)['data'].get('returns')
    action(client,r,'quality_reject',{'reason':'Failed moisture check','file_id':f})
    action(client,r,'dispose_output',{'quantity':'10','reference':'DISP1','reason':'Witnessed disposal','file_id':f})
    stock=next(x for x in client.get('/api/inventory').json() if x['sku'].startswith('finished:'))
    assert stock['quantity']==stock['held'] and Decimal(stock['quantity'])==Decimal(r['payload']['produced_units'])-10
    action(client,r,'print_label',status=422)


def test_fee_late_assessment_repeats_cannot_double_charge_and_withdrawal_reconciles(client):
    p=deepcopy(CATALOG['fees']['sample']);p['payments']=[];p['instalments']=[{'due':date_plus(-10),'amount':str(Decimal(str(p['fee']))-Decimal(str(p['discount'])))}]
    r=create(client,'fees',p);f=upload(client,r);action(client,r,'approve_agreement',{'reason':'Approved fees'})
    policy={'version':'1','mode':'Fixed per instalment','amount':'100','grace_days':'2','cap':'200','effective':date_plus(-20),'terms':'Customer agreed published policy'}
    item(client,r,'late_policy',policy)
    action(client,r,'assess_late_fees',{'as_of':date_plus(-1)})
    action(client,r,'assess_late_fees',{'as_of':date_plus(0)},422)
    action(client,r,'ledger',{'kind':'payment','amount':'500','reference':'PAY1','date':date_plus(0),'note':'Receipt'})
    before=workflow(client,r)['overview'];balance=Decimal(before['balance_paise'])/100
    action(client,r,'withdraw',{'effective':date_plus(0),'credit':str(balance),'refund':'200','reference':'WD1','reason':'Approved refund policy','file_id':f})
    after=workflow(client,r)['overview'];assert after['balance_paise']==0 and after['cash_received_paise']==30000
    action(client,r,'assess_late_fees',{'as_of':date_plus(0)},422)
    assert after['reminder_pause']


def test_renew_request_and_confirmation_keep_negotiation_history(client):
    r=create(client,'renew');f=upload(client,r)
    item(client,r,'terms',{'department':'Ops','seats':'10','owner':'owner@example.test','backup':'backup@example.test','notice_clause':'30 days before renewal','business_days':'No','holidays':'','file_id':f,'term_start':date_plus(-300),'term_months':'12'})
    action(client,r,'negotiate_terms',{'cost':'1000','renewal':date_plus(400),'terms':'Lower annual rate','file_id':f})
    action(client,r,'request_renewal',{'reference':'R1','file_id':f},422)
    action(client,r,'decide',{'decision':'Renew','reason':'Owner approved negotiated offer'})
    action(client,r,'request_renewal',{'reference':'R1','file_id':f})
    assert workflow(client,r)['stage']=='renewal-requested'
    action(client,r,'rollover',{'renewal':date_plus(400),'cost':'1000','file_id':f})
    assert workflow(client,r)['data']['negotiations'][0]['cost']=='1000'


def test_sop_team_training_supervisor_and_offline_expiry(client,app):
    staff=colleague(client,app,'viewer','staff@example.test');r=create(client,'sop')
    for n,text in enumerate(['Isolate power','Inspect guard'],1):item(client,r,'step',{'position':str(n),'instruction':text,'prerequisites':'','timestamp':'','file_id':''})
    item(client,r,'publication_policy',{'collection':'Workshop','audience':'All staff','tools':'Lockout kit','escalation':'Safety lead','effective':date_plus(-1),'offline_days':'7','supervisor':'owner@example.test'})
    action(client,r,'publish',{'pass_percent':'80','review':'Reviewed by safety lead'})
    action(client,r,'enroll_team',{'due':date_plus(-1)});assignments=[x for x in workflow(client,r)['items'] if x['kind']=='assignment']
    identifier=next(x['id'] for x in assignments if x['data']['employee']=='staff@example.test')
    action(client,r,'supervisor_signoff',{'item_id':identifier,'reason':'Observed safe practice'},422)
    action(staff,r,'acknowledge');action(client,r,'supervisor_signoff',{'item_id':identifier,'reason':'Observed safe practice'})
    doc=action(client,r,'offline_copy')['result']['document_id'];assert client.get('/api/documents/'+doc+'/validity').json()['current']
    out=action(client,r,'training_reminders',{'consent':'Yes','start_hour':'9','end_hour':'18'})['result']
    assert len(out['jobs'])==1  # owner has not acknowledged; staff has completed training


def test_claim_conflicts_require_current_evidence_resolution_and_template_isolation(client):
    r=create(client,'claimpack');f=upload(client,r)
    item(client,r,'template',{'provider':'Test provider','reason_code':'ND','version':'1','deadline':timestamp(10),'max_mb':'10','required_kinds':'Delivery','source':'Reviewed provider instructions','owner':'owner@example.test','deadline_source':'Case notice','applicability':'Domestic delivery claims','reviewed_on':date_plus(0)})
    evidence=item(client,r,'evidence',{'kind':'Delivery','file_id':f,'fact':'Delivered','redaction':'','provenance':'Carrier record'})['id']
    action(client,r,'verify_evidence',{'item_id':evidence,'note':'Carrier evidence verified'})
    for day in (-3,-2):item(client,r,'timeline',{'at':timestamp(day),'fact':'Delivery occurred','evidence_id':evidence,'event_reference':'DELIVERY','statement_source':'Carrier'})
    analysis=action(client,r,'analyze_timeline')['result'];assert len(analysis['conflicts'])==1
    action(client,r,'pack',status=422)
    action(client,r,'resolve_conflict',{'event_reference':'DELIVERY','accepted_at':timestamp(-2),'reason':'Carrier corrected original entry','file_id':f})
    action(client,r,'pack')
    template=action(client,r,'save_template')['result']['template_id']
    second=create(client,'claimpack');action(client,second,'apply_template',{'template_id':template,'deadline':timestamp(20)})
    assert any(x['kind']=='template' for x in workflow(client,second)['items'])


def test_academic_access_cannot_read_fees_through_any_export(client,app):
    staff=colleague(client,app,'operator','academic@example.test');r=create(client,'fees');f=upload(client,r)
    item(client,r,'enrollment',{'student_reference':'ST1','course_reference':'C1','start':date_plus(-20),'end':date_plus(100),'terms':'Private refund terms'})
    doc=action(client,r,'approve_agreement',{'reason':'Financial approval'})['result']['document_id']
    member=staff.get('/api/auth/me').json()['id']
    assert client.put('/api/workspace/members/'+member+'/access',json={'fees_mode':'academic'}).status_code==200
    assert staff.get('/api/records').json()==[]
    for url in ['/api/records/'+r['id'], '/api/records/'+r['id']+'/operations','/api/files/'+f,'/api/documents/'+doc+'/pdf','/api/records/'+r['id']+'/export']:
        assert staff.get(url).status_code==403,url
    assert not staff.get('/api/reports/portfolio').json()['records']
    assert r['id'] not in staff.get('/api/reports/accounting.csv').text
    register=staff.get('/api/fees/academic').json();assert register[0]['student_reference']=='ST1'
    assert 'Private refund terms' not in json.dumps(register) and 'fee' not in register[0]
    assert staff.post('/api/products/fees/records',json={'title':'Not allowed','payload':r['payload']}).status_code==403
    assert staff.put('/api/workspace/members/'+member+'/access',json={'fees_mode':'financial'}).status_code==403


def test_payment_evidence_must_belong_to_same_student(client):
    first=create(client,'fees');second=create(client,'fees');f=upload(client,second)
    action(client,first,'approve_agreement',{'reason':'Approved agreement'})
    entry={'kind':'payment','amount':'100','reference':'BANK-1','date':date_plus(0),'note':'Bank receipt','method':'Bank transfer','file_id':f}
    action(client,first,'ledger',entry,422)
    entry['file_id']=upload(client,first)
    action(client,first,'ledger',entry)
    assert workflow(client,first)['overview']['entries'][0]['method']=='Bank transfer'


def test_rate_limits_and_streamed_body_limits(client,monkeypatch):
    monkeypatch.setenv('DOAIDE_API_REQUESTS_PER_MINUTE','1')
    response=client.get('/api/records');assert response.status_code==429 and 'Retry-After' in response.headers
    monkeypatch.setenv('DOAIDE_API_REQUESTS_PER_MINUTE','600')
    response=client.post('/api/products/scope/preview',content=iter([b' '*300000,b' '*300000]),headers={'Content-Type':'application/json'})
    assert response.status_code==413,response.text
