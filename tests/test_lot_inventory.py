import json
import httpx
from backend.worker import run_once
from test_api import app,client,create
from test_operations import action,item,workflow,date_plus,upload
from test_authority_adapters import connect


def prepared(c,m):
    connect(c,m,'INVENTORY');r=create(c,'batch');action(c,r,'connect_lot_inventory')
    f=upload(c,r);lot={'lot':'L1','ingredient':'Flour','supplier':'Mill','quantity':'10.125','unit':'kg','cost':'50','expiry':date_plus(30),'quality':'Quarantined','file_id':f}
    item(c,r,'lot',lot)
    return r,lot


def receipt(request):
    body=json.loads(request.content);lot=body['data']['lots'][0];sku='lot:'+lot['lot']
    row={'sku':sku,'name':lot['ingredient'],'unit':lot['unit'],'quantity':lot['quantity'],'held':lot['quantity'],'data':lot}
    return httpx.Response(200,json={**{k:body[k] for k in ('reference','warehouse_id','batch','action')},'business_id':1,'status':'committed','before':{sku:None},'after':{sku:row}})


def test_lot_receipt_retry_is_atomic_and_pending_freezes_inputs(client,tmp_path,monkeypatch):
    c=client;r,lot=prepared(c,monkeypatch);action(c,r,'receive_lots');path=tmp_path/'test.db';calls=[]
    def lost(req):calls.append(json.loads(req.content)['reference']);raise httpx.ReadTimeout('lost',request=req)
    assert run_once(path,httpx.MockTransport(lost))['state']=='failed'
    assert c.get('/api/inventory').json()==[]
    item(c,r,'recipe',{'version':'1','ingredient':'Flour','quantity':2,'unit':'kg'},422)
    job=c.get('/api/jobs').json()[0]['id'];assert c.post('/api/jobs/'+job+'/retry').status_code==200
    def respond(req):calls.append(json.loads(req.content)['reference']);return receipt(req)
    assert run_once(path,httpx.MockTransport(respond))['state']=='delivered'
    assert calls[0]==calls[1] and len(c.get('/api/inventory').json())==1
    assert workflow(c,r)['stage']=='materials-ready'


def test_lot_scope_mapping_cannot_be_changed_at_enqueue(client,monkeypatch):
    r,lot=prepared(client,monkeypatch)
    key='DOAIDE_INVENTORY_CONNECTIONS';mapping=json.loads(__import__('os').environ[key]);next(iter(mapping.values()))['warehouse_id']=3;monkeypatch.setenv(key,json.dumps(mapping))
    action(client,r,'receive_lots',status=422)
    assert client.get('/api/inventory').json()==[]


def test_malformed_lot_receipt_rolls_back_local_projection(client,tmp_path,monkeypatch):
    r,lot=prepared(client,monkeypatch);action(client,r,'receive_lots')
    def malformed(req):
        response=receipt(req).json();response['after']['lot:L1']['quantity']='999';return httpx.Response(200,json=response)
    assert run_once(tmp_path/'test.db',httpx.MockTransport(malformed))['state']=='blocked'
    assert client.get('/api/inventory').json()==[] and workflow(client,r)['stage']=='inventory-pending'


def test_lot_correction_preserves_reviewed_evidence_and_unique_reference(client):
    r=create(client,'batch');f=upload(client,r)
    item(client,r,'lot',{'lot':'L1','ingredient':'Flour','supplier':'Mill','quantity':'10.125','unit':'kg','cost':'50','expiry':date_plus(30),'quality':'Quarantined','file_id':f})
    action(client,r,'receive_lots')
    body={'sku':'lot:L1','expected_quantity':'10.125','quantity':'9.5','reference':'COUNT1','reason':'Physical count evidence','file_id':f}
    action(client,r,'adjust_lot',body)
    history=client.get('/api/inventory/adjustments').json();assert len(history)==1 and history[0]['file_id']==f and history[0]['delta']=='-0.625'
    action(client,r,'adjust_lot',{**body,'expected_quantity':'9.5','quantity':'8'},422)
    balance=client.get('/api/inventory').json()[0];assert balance['quantity']==balance['held']=='9.5'
