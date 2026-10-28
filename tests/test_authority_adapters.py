"""Outbox recovery, authoritative receipts, ownership and tenant boundary contracts."""
import json
from datetime import datetime, timedelta, timezone
import httpx
from backend.db import database
from backend.worker import run_once
from test_api import app,client,create
from test_operations import action,item,workflow,timestamp,prepare_order,upload


def connect(c,monkeypatch,service):
    workspace=c.get('/api/auth/me').json()['workspace_id']
    monkeypatch.setenv('DOAIDE_'+service+'_CONNECTIONS',json.dumps({workspace:{'url':'https://authority.test/api','token':'synthetic-test-token','business_id':1,'warehouse_id':2}}))
    monkeypatch.setenv('DOAIDE_DELIVERY_MODE','enabled')


def inventory_provider():
    receipts={};calls=[]
    def respond(request):
        assert request.headers['X-DoAide-Business-ID']=='1'
        calls.append(request)
        if request.url.path.endswith('/stock'):
            return httpx.Response(200,json=[{'business_id':1,'sku':'TEA','name':'Tea','unit':'piece','price':'100.00','tax':'5','product_id':3,'warehouse_id':2,'quantity':10,'held':0}])
        if request.url.path.endswith('/reservations'):
            body=json.loads(request.content);ref=body['reference']
            assert body['lines']==[{'product_id':3,'warehouse_id':2,'quantity':2,'price':'100.00','tax':'5','unit':'piece'}]
            receipts.setdefault(ref,{'business_id':1,'reference':ref,'reservation_id':4,'status':'reserved','expires_at':body['expires_at'],'lines':body['lines']})
            return httpx.Response(200,json=receipts[ref])
        parts=request.url.path.split('/');ref=parts[-1] if request.method=='GET' else parts[-2]
        if ref not in receipts:return httpx.Response(200,json={'business_id':1,'reference':ref,'status':'missing'})
        if request.method=='POST' and parts[-1]!='reconcile':receipts[ref]['status']='dispatched' if parts[-1]=='dispatch' else 'cancelled'
        return httpx.Response(200,json=receipts[ref])
    return receipts,calls,respond


def order(c,m,path,respond):
    connect(c,m,'INVENTORY');r=create(c,'orderdesk')
    action(c,r,'inventory_refresh');assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
    item(c,r,'message',{'reference':'order-1','text':'2 x TEA','file_id':''})
    action(c,r,'parse_order');action(c,r,'confirm_order',{'confirmation':'Customer approved two teas'})
    return r


def test_authoritative_reserve_dispatch_and_cache_read_only(client,tmp_path,monkeypatch):
    receipts,calls,respond=inventory_provider();path=tmp_path/'test.db';r=order(client,monkeypatch,path,respond)
    action(client,r,'publish_catalogue',status=422)
    action(client,r,'reserve');assert workflow(client,r)['stage']=='inventory-pending'
    action(client,r,'dispatch',{'reference':'D1'},422)
    assert client.get('/api/inventory').json()[0]['held']=='0'
    assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
    assert workflow(client,r)['stage']=='reserved'
    action(client,r,'dispatch',{'reference':'D1'})
    assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
    w=workflow(client,r);assert w['stage']=='dispatched' and w['data']['dispatch']['inventory_reservation_id']==4
    assert len([x for x in w['documents'] if x['kind']=='dispatch-note'])==1
    file=upload(client,r)
    response=client.post('/api/inventory/adjustments',json={'record_id':r['id'],'sku':'TEA','reference':'C1','delta':'1','expected_quantity':'10','expected_held':'0','reason':'Count correction','file_id':file})
    assert response.status_code==422 and 'DoAide Inventory' in response.text


def test_commit_then_timeout_replays_same_reservation(client,tmp_path,monkeypatch):
    receipts,calls,respond=inventory_provider();path=tmp_path/'test.db';r=order(client,monkeypatch,path,respond)
    action(client,r,'reserve')
    def timeout(request):
        respond(request)
        raise httpx.ReadTimeout('Simulated response loss',request=request)
    assert run_once(path,httpx.MockTransport(timeout))['state']=='failed'
    assert len(receipts)==1 and workflow(client,r)['stage']=='inventory-pending'
    job=client.get('/api/jobs').json()[0]['id'];assert client.post('/api/jobs/'+job+'/retry').status_code==200
    assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
    assert len(receipts)==1 and workflow(client,r)['stage']=='reserved'


def test_conflict_reconcile_missing_and_removed_connection_never_falls_back(client,tmp_path,monkeypatch):
    receipts,calls,respond=inventory_provider();path=tmp_path/'test.db';r=order(client,monkeypatch,path,respond)
    action(client,r,'reserve')
    assert run_once(path,httpx.MockTransport(lambda request:httpx.Response(409,json={'detail':'Stock changed'})))['state']=='blocked'
    action(client,r,'inventory_status')
    assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
    assert workflow(client,r)['stage']=='confirmed'
    old=next(j for j in client.get('/api/jobs').json() if j['state']=='cancelled')
    assert client.post('/api/jobs/'+old['id']+'/retry').status_code==409
    monkeypatch.delenv('DOAIDE_INVENTORY_CONNECTIONS')
    action(client,r,'reserve');assert run_once(path)['state']=='blocked'
    assert client.get('/api/inventory').json()[0]['held']=='0'
    action(client,r,'publish_catalogue',status=422)


def test_local_stock_requires_explicit_migration_before_activation(client,monkeypatch):
    r=prepare_order(client);connect(client,monkeypatch,'INVENTORY')
    action(client,r,'inventory_refresh',status=422)


def appointment(c,m):
    connect(c,m,'SCHEDULER');r=create(c,'amc');action(c,r,'connect_scheduler')
    asset=item(c,r,'asset',{'site':'Cafe','serial':'SN1','model':'RO','warranty':'','coverage':'Service'})['id']
    start=datetime.now(timezone.utc)+timedelta(days=1)
    visit=item(c,r,'visit',{'asset_id':asset,'technician':'owner@example.test','start':start.isoformat(),'end':(start+timedelta(minutes=30)).isoformat(),
        'chargeable':'No','checklist':'Check pressure','meeting_type_id':'1','customer_email':'customer@example.test'})['id']
    return r,visit


def test_scheduler_pending_confirmation_reschedule_cancel_and_freeze(client,tmp_path,monkeypatch):
    r,visit=appointment(client,monkeypatch);path=tmp_path/'test.db';receipts={}
    def respond(req):
        assert req.headers['X-DoAide-Business-ID']=='1'
        body=json.loads(req.content) if req.content else {}
        ref=body.get('reference') or req.url.path.split('/')[-1]
        if req.url.path.endswith('/bookings'):
            receipts[ref]={'business_id':1,'reference':ref,'booking_id':7,'status':'confirmed','start_time':body['start_time'],'end_time':body['end_time'],'host_email':body['host_email'],'notifications_sent':False}
        elif body.get('command')=='reschedule':receipts[ref].update(status='rescheduled',start_time=body['start_time'],end_time=body['end_time'])
        elif body.get('command')=='cancel':receipts[ref]['status']='cancelled'
        return httpx.Response(200,json=receipts[ref])
    w=workflow(client,r);v=next(x for x in w['items'] if x['id']==visit);assert v['data']['_status']=='booking-pending'
    file=upload(client,r);action(client,r,'complete_visit',{'item_id':visit,'notes':'Done','file_id':file},422)
    assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
    w=workflow(client,r);v=next(x for x in w['items'] if x['id']==visit);assert v['data']['_status']=='scheduled'
    start=datetime.now(timezone.utc)+timedelta(days=2)
    action(client,r,'scheduler_reschedule',{'item_id':visit,'start':start.isoformat(),'end':(start+timedelta(minutes=30)).isoformat()})
    assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
    action(client,r,'scheduler_cancel',{'item_id':visit})
    assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
    v=next(x for x in workflow(client,r)['items'] if x['id']==visit);assert v['data']['_status']=='booking-cancelled'
    action(client,r,'complete_visit',{'item_id':visit,'notes':'Done','file_id':file},422)


def test_scheduler_missing_recovery(client,tmp_path,monkeypatch):
    r,visit=appointment(client,monkeypatch);path=tmp_path/'test.db'
    assert run_once(path,httpx.MockTransport(lambda req:httpx.Response(409,json={'detail':'Conflict'})))['state']=='blocked'
    action(client,r,'scheduler_refresh',{'item_id':visit})
    assert run_once(path,httpx.MockTransport(lambda req:httpx.Response(200,json={'business_id':1,'reference':req.url.path.split('/')[-1],'status':'missing'})))['state']=='delivered'
    action(client,r,'scheduler_retry',{'item_id':visit})
    assert workflow(client,r)['items'][-1]['data'].get('_status')=='booking-pending'


def test_malformed_catalogue_rolls_back_and_can_refresh_again(client,tmp_path,monkeypatch):
    connect(client,monkeypatch,'INVENTORY');r=create(client,'orderdesk');action(client,r,'inventory_refresh')
    def bad(req):
        return httpx.Response(200,json=[{'business_id':1,'sku':'TEA','name':'Tea','unit':'piece','price':'100','tax':'5','product_id':3,'warehouse_id':2,'quantity':10,'held':0},
            {'business_id':1,'sku':'BAD','quantity':1,'held':2}])
    assert run_once(tmp_path/'test.db',httpx.MockTransport(bad))['state']=='blocked'
    assert client.get('/api/inventory').json()==[]
    action(client,r,'inventory_refresh')
    receipts,calls,respond=inventory_provider()
    assert run_once(tmp_path/'test.db',httpx.MockTransport(respond))['state']=='delivered'
    assert len(client.get('/api/inventory').json())==1


def test_changed_business_mapping_is_blocked_before_call(client,tmp_path,monkeypatch):
    receipts,calls,respond=inventory_provider();path=tmp_path/'test.db';r=order(client,monkeypatch,path,respond)
    action(client,r,'reserve');before=len(calls)
    config=json.loads(__import__('os').environ['DOAIDE_INVENTORY_CONNECTIONS']);next(iter(config.values()))['business_id']=2
    monkeypatch.setenv('DOAIDE_INVENTORY_CONNECTIONS',json.dumps(config))
    assert run_once(path,httpx.MockTransport(respond))['state']=='blocked' and len(calls)==before


def test_pending_commit_prevents_record_archival(client,tmp_path,monkeypatch):
    receipts,calls,respond=inventory_provider();path=tmp_path/'test.db';r=order(client,monkeypatch,path,respond)
    action(client,r,'reserve')
    assert client.post('/api/records/'+r['id']+'/status',json={'status':'archived','version':r['version']}).status_code==409
    assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
