"""Isolated cross-service acceptance using real Inventory/Scheduler HTTP applications.

Runs with sibling service checkouts and their backend/.venv dependencies installed.
All three databases are temporary; no deployed account, email or calendar is used.
The transport maps synthetic HTTPS authority hosts to the temporary local servers.
"""
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.catalog import CATALOG
from backend.worker import run_once


@contextmanager
def service(folder, database):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(database),'JWT_SECRET':'isolated-contract-test-key-only','BCRYPT_ROUNDS':'4','ENVIRONMENT':'development','OPENROUTER_API_KEY':''}
    boot="import app.models; from app.core.database import Base,engine; Base.metadata.create_all(engine); import uvicorn; uvicorn.run('app.main:app',host='127.0.0.1',port="+str(port)+",log_level='error')"
    with tempfile.TemporaryFile() as output:
        process=subprocess.Popen([str(folder/'.venv/bin/python'),'-c',boot],cwd=folder,env=env,stdout=output,stderr=output)
        try:
            for _ in range(100):
                if process.poll() is not None:raise RuntimeError('Isolated service failed to start')
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('Isolated service startup timed out')
            yield port
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()


class LocalAuthorities(httpx.BaseTransport):
    def __init__(self, ports):self.ports=ports;self.transport=httpx.HTTPTransport()
    def handle_request(self, request):
        if request.url.host not in self.ports:raise AssertionError('Unexpected provider host')
        url=request.url.copy_with(scheme='http',host='127.0.0.1',port=self.ports[request.url.host])
        return self.transport.handle_request(httpx.Request(request.method,url,headers=request.headers,content=request.content))
    def close(self):self.transport.close()


def json_request(c, method, url, **kwargs):
    r=c.request(method,url,**kwargs)
    assert r.is_success,(url,r.status_code,r.text[:500])
    return r.json()


def check(inventory,scheduler):
    with tempfile.TemporaryDirectory(prefix='doaide-authorities-') as temporary:
        temp=Path(temporary)
        with service(inventory,temp/'inventory.db') as ip,service(scheduler,temp/'scheduler.db') as sp:
            with httpx.Client(base_url=f'http://127.0.0.1:{ip}') as inv,httpx.Client(base_url=f'http://127.0.0.1:{sp}/api/v1/') as sched:
                body={'email':'authority@example.com','password':'Synthetic-only-123!','business_name':'Isolated acceptance','full_name':'Test Owner'}
                itoken=json_request(inv,'POST','/auth/register',json=body)['access_token'];inv.headers['Authorization']='Bearer '+itoken
                stoken=json_request(sched,'POST','auth/register',json=body)['access_token'];sched.headers['Authorization']='Bearer '+stoken
                product=json_request(inv,'POST','/products',json={'sku':'TEA','name':'Tea','unit':'piece','selling_price':100,'tax_rate':5})
                warehouse=json_request(inv,'POST','/warehouses',json={'name':'Test warehouse'})
                json_request(inv,'POST','/stock',json={'product_id':product['id'],'warehouse_id':warehouse['id'],'quantity':10})
                meeting=json_request(sched,'POST','meeting-types/',json={'name':'AMC visit','duration_minutes':30})
                start=(datetime.now(timezone.utc)+timedelta(days=2)).replace(hour=10,minute=0,second=0,microsecond=0)
                json_request(sched,'POST','availability/',json={'day_of_week':start.weekday(),'start_time':'09:00','end_time':'17:00'})
                with TestClient(create_app(temp/'suite.db')) as suite,LocalAuthorities({'inventory.test':ip,'scheduler.test':sp}) as transport:
                    json_request(suite,'POST','/api/auth/register',json={'email':body['email'],'password':body['password']})
                    me=json_request(suite,'GET','/api/auth/me');workspace=me['workspace_id']
                    os.environ['DOAIDE_INVENTORY_CONNECTIONS']=json.dumps({workspace:{'url':'https://inventory.test','token':itoken,'business_id':1,'warehouse_id':warehouse['id']}})
                    os.environ['DOAIDE_SCHEDULER_CONNECTIONS']=json.dumps({workspace:{'url':'https://scheduler.test/api/v1','token':stoken,'business_id':1}})
                    os.environ['DOAIDE_DELIVERY_MODE']='enabled'
                    def create(slug):return json_request(suite,'POST','/api/products/'+slug+'/records',json={'title':'Isolated '+slug,'payload':deepcopy(CATALOG[slug]['sample'])})
                    def workflow(r):return json_request(suite,'GET','/api/records/'+r['id']+'/operations')
                    def command(r,a,data=None):return json_request(suite,'POST','/api/records/'+r['id']+'/actions/'+a,json={'revision':workflow(r)['revision'],'data':data or {}},headers={'Idempotency-Key':os.urandom(16).hex()})
                    def item(r,kind,data):return json_request(suite,'POST','/api/records/'+r['id']+'/items/'+kind,json={'revision':workflow(r)['revision'],'data':data})
                    def deliver():
                        result=run_once(temp/'suite.db',transport);assert result['state']=='delivered',result
                    order=create('orderdesk');command(order,'inventory_refresh');deliver()
                    item(order,'message',{'reference':'synthetic-order','text':'2 x TEA','file_id':''})
                    command(order,'parse_order');command(order,'confirm_order',{'confirmation':'Synthetic customer approval'})
                    command(order,'reserve');deliver();assert workflow(order)['stage']=='reserved'
                    command(order,'dispatch',{'reference':'synthetic-dispatch'});deliver();assert workflow(order)['stage']=='dispatched'
                    assert json_request(inv,'GET','/stock')[0]['quantity']==8
                    contract=create('amc');command(contract,'connect_scheduler')
                    asset=item(contract,'asset',{'site':'Test site','serial':'TEST-1','model':'Test unit','warranty':'','coverage':'Service'})['id']
                    visit=item(contract,'visit',{'asset_id':asset,'technician':body['email'],'start':start.isoformat(),'end':(start+timedelta(minutes=30)).isoformat(),'chargeable':'No','checklist':'Check pressure','meeting_type_id':str(meeting['id']),'customer_email':'customer@example.com'})['id']
                    deliver();assert next(x for x in workflow(contract)['items'] if x['id']==visit)['data']['_status']=='scheduled'
                    command(contract,'scheduler_reschedule',{'item_id':visit,'start':(start+timedelta(hours=1)).isoformat(),'end':(start+timedelta(minutes=90)).isoformat()});deliver()
                    command(contract,'scheduler_cancel',{'item_id':visit});deliver()
                    bookings=json_request(sched,'GET','bookings/');assert len(bookings)==1 and bookings[0]['status']=='cancelled'
                    return {'isolated_databases':3,'real_http_services':2,'inventory_reserve_dispatch':'passed','scheduler_create_reschedule_cancel':'passed','stock_remaining':8,'bookings_created':1,'external_provider_requests':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--inventory',type=Path,required=True);parser.add_argument('--scheduler',type=Path,required=True);args=parser.parse_args()
    print(json.dumps(check(args.inventory.resolve(),args.scheduler.resolve()),indent=2))
