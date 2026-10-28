"""Generate synthetic layout fixtures through real API workflows, without live data."""
import io
import json
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from PIL import Image
from fastapi.testclient import TestClient
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from backend.main import create_app
from backend.catalog import CATALOG
from test_api import create
from test_operations import item,action,upload,workflow,date_plus


def generate(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);result=[]
    with tempfile.TemporaryDirectory(prefix='doaide-documents-') as directory,TestClient(create_app(Path(directory)/'test.db')) as client:
        client.post('/api/auth/register',json={'email':'layout@example.test','password':'synthetic-layout-password'})
        payload=deepcopy(CATALOG['handover']['sample'])
        for issue in payload['issues']:issue.update(severity='Minor',assignee='layout@example.test',status='Open')
        r=create(client,'handover',payload);picture=io.BytesIO();Image.new('RGB',(600,350),'#d6ded1').save(picture,format='PNG')
        photo=client.post('/api/records/'+r['id']+'/files',files={'file':('synthetic-inspection.png',picture.getvalue(),'image/png')}).json()['id']
        for issue in workflow(client,r)['items']:
            if issue['kind']!='issue':continue
            data={k:v for k,v in issue['data'].items() if not k.startswith('_')};data.update(file_id=photo,due=date_plus(5))
            response=client.put('/api/records/'+r['id']+'/items/issue/'+issue['id'],json={'revision':workflow(client,r)['revision'],'data':data});assert response.status_code==200,response.text
            action(client,r,'waive',{'item_id':issue['id'],'note':'Cosmetic repair listed for customer review; acceptance still required.'})
        docs=[('handover-room-report',action(client,r,'close')['result']['document_id'])]
        p=deepcopy(CATALOG['batch']['sample']);p['batch_number']='LAYOUT-BATCH-001'
        batch=create(client,'batch',p);evidence=upload(client,batch,'Synthetic supplier and quality record')
        item(client,batch,'recipe',{'version':'1','ingredient':'Flour','quantity':'10','unit':'kg'})
        item(client,batch,'lot',{'lot':'LAYOUT-FLOUR','ingredient':'Flour','supplier':'Example supplier','quantity':'12','unit':'kg','cost':'45','expiry':date_plus(90),'quality':'Released','file_id':evidence})
        item(client,batch,'usage',{'lot':'LAYOUT-FLOUR','quantity':'10','waste':'1','unit':'kg'})
        action(client,batch,'receive_lots');action(client,batch,'produce');action(client,batch,'quality_release',{'checks':'Synthetic fixture checks passed','file_id':evidence})
        docs.append(('batch-traceability-label',action(client,batch,'print_label')['result']['document_id']))
        amc=create(client,'amc');offer=action(client,amc,'renewal_offer',{'start':date_plus(400),'end':date_plus(765),'value':'15000','included':'4','valid_until':date_plus(30),'contact':'customer@example.test','terms':'Four scheduled visits; replacement parts require separate approval.'})
        docs.append(('amc-renewal-offer',offer['result']['document_id']))
        for name,doc in docs:
            response=client.get('/api/documents/'+doc+'/pdf');assert response.status_code==200,response.text
            path=output/(name+'.pdf');path.write_bytes(response.content)
            result.append({'file':path.name,'pages':len(PdfReader(io.BytesIO(response.content)).pages),'synthetic':True})
    return result


if __name__=='__main__':print(json.dumps(generate(ROOT/'docs/evidence'),indent=2))
