"""Read-only source adapters against isolated native Proposals, Payroll and Khata."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import date,timedelta
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_authorities import service,LocalAuthorities,json_request
import httpx
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.catalog import CATALOG
from backend.worker import run_once


def check(root):
    with tempfile.TemporaryDirectory(prefix='doaide-sources-') as temp,ExitStack() as stack:
        temp=Path(temp);pp=stack.enter_context(service(root/'DoAide-Proposals/backend',temp/'proposals.db'))
        yp=stack.enter_context(service(root/'DoAide-Payroll/backend',temp/'payroll.db'))
        # Khata uses its own SQLite document store and Google-session format.
        folder=root/'DoAide-Khata/backend';secret='isolated-source-acceptance-key-only'
        env={**os.environ,'SESSION_SECRET':secret,'KHATA_DB_PATH':str(temp/'khata.db'),'GEMINI_API_KEY':''}
        token=subprocess.check_output([str(folder/'.venv/bin/python'),'-c',"from app.auth import create_session; print(create_session('isolated','shop@example.com'))"],cwd=folder,env=env,text=True).strip()
        # Select a port only for this independent process; it never connects outward.
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));kp=sock.getsockname()[1]
        boot="import uvicorn; uvicorn.run('app.main:app',host='127.0.0.1',port="+str(kp)+",log_level='error')"
        # service() selects its own port, so use a local Khata health wait here.
        output=stack.enter_context(tempfile.TemporaryFile());process=subprocess.Popen([str(folder/'.venv/bin/python'),'-c',boot],cwd=folder,env=env,stdout=output,stderr=output)
        def stop():
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        stack.callback(stop)
        import time
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('Khata startup failed')
            try:
                with socket.create_connection(('127.0.0.1',kp),timeout=.1):break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('Khata startup timed out')
        clients={name:stack.enter_context(httpx.Client(base_url=f'http://127.0.0.1:{port}')) for name,port,prefix in [('PROPOSALS',pp,'/api'),('PAYROLL',yp,'/api/v1'),('KHATA',kp,'/api')]}
        body={'email':'owner@example.com','password':'Synthetic-only-123!','full_name':'Test Owner','business_name':'Acceptance'}
        proposals=clients['PROPOSALS'];pt=json_request(proposals,'POST','/api/auth/register',json=body)['access_token'];proposals.headers['Authorization']='Bearer '+pt
        template=json_request(proposals,'POST','/api/templates',json={'name':'Test offer','default_terms':'Payment in 30 days','sections':[{'title':'Work','content':'Reviewed deliverables'}]})
        payroll=clients['PAYROLL'];yt=json_request(payroll,'POST','/api/v1/auth/register',json={**body,'company_name':'Acceptance'})['token']['access_token'];payroll.headers['Authorization']='Bearer '+yt
        employee=json_request(payroll,'POST','/api/v1/employees',json={'employee_code':'E1','full_name':'Test Owner','email':body['email'],'date_of_joining':date.today().isoformat(),'pan':'ABCDE1234F'})
        khata=clients['KHATA'];khata.headers['Authorization']='Bearer '+token
        json_request(khata,'POST','/api/sync',json={'customers':[{'id':'C1','name':'Customer','updatedAt':1}], 'transactions':[{'id':'T1','customerId':'C1','type':'received','amount':25,'date':date.today().isoformat(),'updatedAt':1}]})
        suite=stack.enter_context(TestClient(create_app(temp/'suite.db')));json_request(suite,'POST','/api/auth/register',json={'email':body['email'],'password':body['password']})
        workspace=json_request(suite,'GET','/api/auth/me')['workspace_id'];os.environ['DOAIDE_DELIVERY_MODE']='enabled'
        transport=stack.enter_context(LocalAuthorities({'proposals.test':pp,'payroll.test':yp,'khata.test':kp}))
        for name,host,prefix,credential,identity in [('PROPOSALS','proposals','/api',pt,{'business_id':1}),('PAYROLL','payroll','/api/v1',yt,{'business_id':1}),('KHATA','khata','/api',token,{'account_email':'shop@example.com'})]:
            os.environ['DOAIDE_'+name+'_CONNECTIONS']=json.dumps({workspace:{'url':'https://'+host+'.test'+prefix,'token':credential,**identity}})
        for slug,action,data in [('scope','import_proposal_template',{'source_id':template['id']}),('sop','import_payroll_roster',{}),('collect','import_khata_customer',{'source_id':'C1'})]:
            r=json_request(suite,'POST','/api/products/'+slug+'/records',json={'title':'Source '+slug,'payload':deepcopy(CATALOG[slug]['sample'])})
            w=json_request(suite,'GET','/api/records/'+r['id']+'/operations')
            json_request(suite,'POST','/api/records/'+r['id']+'/actions/'+action,json={'revision':w['revision'],'data':data},headers={'Idempotency-Key':os.urandom(16).hex()})
            outcome=run_once(temp/'suite.db',transport);assert outcome['state']=='delivered',outcome
            w=json_request(suite,'GET','/api/records/'+r['id']+'/operations');source=next(x for x in w['items'] if x['kind']=='source_import')
            assert source['data']['review_status']=='Needs review' and 'ABCDE1234F' not in json.dumps(source)
        return {'isolated_databases':4,'real_http_services':3,'proposals_template':'passed','payroll_roster':'passed','khata_customer_ledger':'passed','private_payroll_fields_retained':False,'external_provider_requests':0}


if __name__=='__main__':print(json.dumps(check(Path(__file__).resolve().parents[2]),indent=2))
