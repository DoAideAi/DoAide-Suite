import json
import httpx
from backend.worker import run_once
from test_api import app,client,create
from test_operations import action,item,workflow,upload,timestamp,colleague
from test_authority_adapters import connect


def prepare(c,m,path):
    connect(c,m,'INVENTORY');r=create(c,'amc');action(c,r,'inventory_refresh')
    def catalogue(req):return httpx.Response(200,json=[{'business_id':1,'sku':'FILTER','name':'Filter','unit':'piece','price':'100','tax':'0','product_id':3,'warehouse_id':2,'quantity':10,'held':0}])
    assert run_once(path,httpx.MockTransport(catalogue))['state']=='delivered'
    asset=item(c,r,'asset',{'site':'Cafe','serial':'SN1','model':'RO','warranty':'','coverage':'Service'})['id']
    visit=item(c,r,'visit',{'asset_id':asset,'technician':'owner@example.test','start':timestamp(-2),'end':timestamp(-1),'chargeable':'Yes','checklist':'Pressure'})['id']
    part=item(c,r,'part',{'visit_id':visit,'part':'Filter','sku':'FILTER','quantity':'2','cost':'200'})['id']
    return r,visit,part


def provider():
    receipts={}
    def respond(req):
        if req.url.path.endswith('/reservations'):
            body=json.loads(req.content);ref=body['reference'];receipts.setdefault(ref,{'business_id':1,'reference':ref,'reservation_id':1,'status':'reserved','lines':body['lines']})
        else:
            ref=req.url.path.split('/')[-2]
            if ref not in receipts:return httpx.Response(200,json={'business_id':1,'reference':ref,'status':'missing'})
            if req.url.path.endswith('/dispatch'):receipts[ref]['status']='dispatched'
            if req.url.path.endswith('/cancel'):receipts[ref]['status']='cancelled'
        return httpx.Response(200,json=receipts[ref])
    return receipts,respond


def test_parts_reserved_consumed_once_and_billing_requires_inventory(client,app,tmp_path,monkeypatch):
    c=client;path=tmp_path/'test.db';r,vid,part=prepare(c,monkeypatch,path);receipts,respond=provider()
    action(c,r,'reserve_parts',{'item_id':vid});assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
    assert c.request('DELETE','/api/records/'+r['id']+'/items/part/'+part,json={'revision':workflow(c,r)['revision'],'data':{}}).status_code==422
    file=upload(c,r);action(c,r,'complete_visit',{'item_id':vid,'notes':'Done','file_id':file})
    reviewer=colleague(c,app);action(reviewer,r,'verify_visit',{'item_id':vid})
    action(c,r,'bill_visit',{'item_id':vid,'service_charge':'100','reason':'Service and filter'},422)
    action(c,r,'consume_parts',{'item_id':vid})
    def lost(req):respond(req);raise httpx.ReadTimeout('Lost receipt',request=req)
    assert run_once(path,httpx.MockTransport(lost))['state']=='failed'
    action(c,r,'reconcile_parts',{'item_id':vid});assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
    assert len(receipts)==1 and workflow(c,r)['data']['parts_receipts'][vid]['status']=='dispatched'
    action(c,r,'consume_parts',{'item_id':vid},422)
    action(c,r,'bill_visit',{'item_id':vid,'service_charge':'100','reason':'Service and filter'})


def test_released_parts_can_be_revised_and_missing_reconciled(client,tmp_path,monkeypatch):
    c=client;path=tmp_path/'test.db';r,vid,part=prepare(c,monkeypatch,path);receipts,respond=provider()
    action(c,r,'reserve_parts',{'item_id':vid});assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
    action(c,r,'release_parts',{'item_id':vid});assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
    response=c.put('/api/records/'+r['id']+'/items/part/'+part,json={'revision':workflow(c,r)['revision'],'data':{'visit_id':vid,'part':'Filter','sku':'FILTER','quantity':'1','cost':'100'}});assert response.status_code==200,response.text
    action(c,r,'reserve_parts',{'item_id':vid})
    assert run_once(path,httpx.MockTransport(lambda req:httpx.Response(409)))['state']=='blocked'
    action(c,r,'reconcile_parts',{'item_id':vid});assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
    assert workflow(c,r)['data']['parts_receipts'][vid]['status']=='missing'
