"""Smoke-test a locally built runtime image in an isolated, disposable container."""
import argparse
import io
import json
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
import httpx
from pypdf import PdfReader
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.catalog import CATALOG


def check(image,host=None):
    docker=['docker']+(['--host',host] if host else [])
    def run(*args):return subprocess.check_output(docker+list(args),text=True).strip()
    container=run('run','--rm','-d','--read-only','--tmpfs','/tmp:rw,noexec,nosuid','--tmpfs','/data:rw,uid=10001,gid=10001,mode=0700','-p','127.0.0.1::8012',image)
    try:
        address=run('port',container,'8012/tcp').splitlines()[0]
        with httpx.Client(base_url='http://'+address,timeout=10) as client:
            for _ in range(40):
                try:
                    if client.get('/api/ready').status_code==200:break
                except httpx.TransportError:pass
                time.sleep(.25)
            else:raise AssertionError('Container did not become ready')
            specification=client.get('/openapi.json').json();version=specification['info']['version']
            assert version=='0.6.1'
            assert all(route in specification['paths'] for route in ('/api/fees/academic','/api/webhooks/whatsapp','/api/records/{record_id}/recordings','/api/contractor/{token}/start'))
            response=client.post('/api/auth/register',json={'email':'container-check@example.test','password':'synthetic-container-test-password'})
            assert response.status_code==201,response.text
            payload={**CATALOG['scope']['sample'],'decision':'Change required'}
            response=client.post('/api/products/scope/records',json={'title':'Container validation','payload':payload});assert response.status_code==201,response.text
            identifier=response.json()['id'];base='/api/records/'+identifier
            workflow=client.get(base+'/operations').json()
            response=client.post(base+'/items/baseline',json={'revision':workflow['revision'],'data':{'reference':'Clause 1','text':'Website scope only','file_id':''}});assert response.status_code==201,response.text
            revision=response.json()['workflow']['revision']
            approved=client.post(base+'/actions/approve',json={'revision':revision,'data':{'reason':'Synthetic review'}},headers={'Idempotency-Key':str(uuid4())});assert approved.status_code==200,approved.text
            doc=approved.json()['result']['document_id'];pdf=client.get('/api/documents/'+doc+'/pdf')
            assert pdf.status_code==200 and len(PdfReader(io.BytesIO(pdf.content)).pages)>=1
            assert client.get('/api/documents/'+doc+'/pdf').content==pdf.content
            assert client.get('/api/billing').json()['mode']=='local'
            assert client.get('/api/integrations').json()['authorities']=={'inventory':{'configured':False,'active':False},'scheduler':{'configured':False,'active':False},'inventory_lots':{'configured':False,'active':False}}
            report=client.get('/api/reports/portfolio').json();assert report['total_records']==1 and len(report['totals'])==12
            run('exec',container,'python','-m','backend.worker','--once')
            state=client.get('/api/diagnostics').json();assert state['schema_version']==5 and state['worker_healthy']
            uid=run('exec',container,'id','-u');assert uid=='10001'
            return {'version':version,'image_id':run('image','inspect',image,'--format','{{.Id}}'),'user_id':uid,'read_only_root':True,'ephemeral_database':True,'registration':'passed','operational_approval':'passed','frozen_pdf_identity':'passed','portfolio_products':12,'billing_mode':'local','schema_version':5,'worker_readiness':'passed','external_provider_requests':0}
    finally:run('rm','-f',container)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--image',default='doaide-suite:local-validation');parser.add_argument('--host');args=parser.parse_args()
    print(json.dumps(check(args.image,args.host),indent=2))
