"""Provider boundary, human-review and destructive-tool isolation checks."""
import hashlib
import hmac
import io
import json
import time
import wave
import zipfile
from copy import deepcopy
import httpx
import pytest
from cryptography.fernet import Fernet,InvalidToken
from fastapi.testclient import TestClient
from pypdf import PdfReader
from backend.db import database
from backend.worker import run_once,deliver,Blocked
from backend import operations as op
from backend.portfolio_connections import connection
from scripts.encrypted_backup import private_write,encrypt_backup,decrypt_backup
from scripts.erase_workspace import erase
from test_api import app,client,create
from test_operations import action,item,upload,workflow,colleague,date_plus,timestamp,prepare_order,approve_scope


def wav():
    data=io.BytesIO()
    with wave.open(data,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*800)
    return data.getvalue()


def test_recording_consent_source_retention_and_human_review(client,tmp_path,monkeypatch):
    r=create(client,'sop');audio=wav()
    response=client.post('/api/records/'+r['id']+'/recordings',files={'file':('training.wav',audio,'audio/wav')})
    assert response.status_code==201,response.text
    identifier=response.json()['id'];url='/api/files/'+identifier+'/transcribe'
    assert client.post(url,json={'provider_consent':False}).status_code==422
    assert client.post(url,json={'provider_consent':True}).status_code==202
    assert run_once(tmp_path/'test.db')['state']=='blocked'
    with database(tmp_path/'test.db') as db:job=dict(db.execute('SELECT * FROM jobs').fetchone());job['data']=json.loads(job['data'])
    monkeypatch.setenv('DOAIDE_DELIVERY_MODE','enabled');monkeypatch.setenv('DOAIDE_GROQ_TRANSCRIPTION_KEY','synthetic-key')
    def respond(request):
        assert request.url.host=='api.groq.com' and request.headers['Authorization']=='Bearer synthetic-key'
        assert b'whisper-large-v3-turbo' in request.content and audio in request.content
        return httpx.Response(200,json={'text':'Turn off power. Check the isolation.','duration':.1,'segments':[{'start':0,'end':.1,'text':'Turn off power. Check the isolation.'}]})
    result=deliver(job,tmp_path/'test.db',httpx.MockTransport(respond));assert result['needs_human_review']
    assert not workflow(client,r)['items']
    action(client,r,'steps_from_transcript',{'file_id':identifier,'steps':[{'instruction':'Turn off power','timestamp':'0.00s'},{'instruction':'Check isolation','timestamp':'0.05s'}],'reason':'Compared recording and transcript'})
    assert len([x for x in workflow(client,r)['items'] if x['kind']=='step'])==2
    with database(tmp_path/'test.db') as db:
        f=db.execute('SELECT * FROM files WHERE id=?',(identifier,)).fetchone()
        assert f['content']==audio and '[0.00s' in f['extracted']
    wrong=create(client,'fees')
    assert client.post('/api/records/'+wrong['id']+'/recordings',files={'file':('a.wav',audio,'audio/wav')}).status_code==422
    assert client.post('/api/records/'+r['id']+'/recordings',files={'file':('a.wav',b'not audio','audio/wav')}).status_code==422


def setup_whatsapp(client,monkeypatch):
    prepare_order(client)
    me=client.get('/api/auth/me').json()
    monkeypatch.setenv('DOAIDE_META_APP_SECRET','synthetic-webhook-secret')
    monkeypatch.setenv('DOAIDE_META_VERIFY_TOKEN','synthetic-verify')
    monkeypatch.setenv('DOAIDE_WHATSAPP_CHANNELS',json.dumps({'123':{'workspace_id':me['workspace_id'],'owner_id':me['id']}}))
    return me


def whatsapp(client,kind='text',identifier='wamid.test',phone='123',signature=True):
    message={'id':identifier,'type':kind,'from':'919999999999','timestamp':str(int(time.time())),'text':{'body':'2 BOTTLE'},'audio':{'id':'456','sha256':hashlib.sha256(wav()).hexdigest()}}
    body={'object':'whatsapp_business_account','entry':[{'changes':[{'field':'messages','value':{'metadata':{'phone_number_id':phone},'messages':[message]}}]}]}
    raw=json.dumps(body).encode();sig='sha256='+hmac.new(b'synthetic-webhook-secret',raw,hashlib.sha256).hexdigest()
    return client.post('/api/webhooks/whatsapp',content=raw,headers={'X-Hub-Signature-256':sig if signature else 'forged','Content-Type':'application/json'})


def test_whatsapp_signature_channel_mapping_and_replay(client,monkeypatch):
    setup_whatsapp(client,monkeypatch)
    assert client.get('/api/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=synthetic-verify&hub.challenge=abc').text=='abc'
    assert client.get('/api/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=wrong').status_code==403
    assert whatsapp(client,signature=False).status_code==401
    assert whatsapp(client,phone='unmapped').status_code==422
    result=whatsapp(client);assert result.status_code==200,result.text
    r={'id':result.json()['records'][0]};assert any(x['data'].get('reference')=='wamid.test' for x in workflow(client,r)['items'])
    assert whatsapp(client).json()['records']==[]
    assert workflow(client,r)['stage']=='draft'


def test_whatsapp_audio_download_is_host_bound_and_reviewed(client,tmp_path,monkeypatch):
    setup_whatsapp(client,monkeypatch);r={'id':whatsapp(client,'audio').json()['records'][0]}
    monkeypatch.setenv('DOAIDE_DELIVERY_MODE','enabled');monkeypatch.setenv('DOAIDE_META_ACCESS_TOKEN','synthetic-media-token');monkeypatch.setenv('DOAIDE_META_GRAPH_VERSION','v99.0')
    def respond(request):
        if request.url.host=='graph.facebook.com':return httpx.Response(200,json={'url':'https://lookaside.fbsbx.com/media/456','mime_type':'audio/wav'})
        assert request.url.host=='lookaside.fbsbx.com'
        return httpx.Response(200,content=wav())
    result=run_once(tmp_path/'test.db',httpx.MockTransport(respond));assert result['state']=='delivered',result
    message=next(x for x in workflow(client,r)['items'] if x['kind']=='message');identifier=message['data']['file_id'];assert identifier
    action(client,r,'review_transcript',{'file_id':identifier,'reference':'wamid.test','text':'2 BOTTLE','reason':'Reviewed'},422)
    with database(tmp_path/'test.db') as db:
        db.execute("UPDATE files SET extraction_status='transcribed-needs-review',extracted='2 BOTTLE' WHERE id=?",(identifier,))
        job=dict(db.execute("SELECT * FROM jobs WHERE kind='whatsapp-media'").fetchone());job['data']=json.loads(job['data'])
    action(client,r,'review_transcript',{'file_id':identifier,'reference':'wamid.test','text':'2 BOTTLE','reason':'Checked audio'})
    assert len([x for x in workflow(client,r)['items'] if x['kind']=='message'])==1
    calls=[]
    def malicious(request):calls.append(str(request.url));return httpx.Response(200,json={'url':'https://attacker.example/media','mime_type':'audio/wav'})
    with pytest.raises(Blocked,match='host'):deliver(job,tmp_path/'test.db',httpx.MockTransport(malicious))
    assert len(calls)==1


def test_contracts_import_preserves_sources_and_blocks_stale_draft(client,tmp_path,monkeypatch):
    r=create(client);me=client.get('/api/auth/me').json();path=tmp_path/'test.db'
    monkeypatch.setenv('DOAIDE_DELIVERY_MODE','enabled');monkeypatch.setenv('DOAIDE_CONTRACTS_CONNECTIONS',json.dumps({me['workspace_id']:{'url':'https://contracts.example/api','token':'synthetic-token'}}))
    def respond(request):
        assert request.headers['Authorization']=='Bearer synthetic-token'
        return httpx.Response(200,json=[{'id':11,'clause_index':1,'clause_title':'Deliverables','clause_text':'Five website pages'}] if request.url.path.endswith('/clauses') else {'id':7,'title':'Signed baseline'})
    action(client,r,'import_contract',{'contract_id':'7'})
    result=run_once(path,httpx.MockTransport(respond));assert result['state']=='delivered',result
    baseline=next(x for x in workflow(client,r)['items'] if x['kind']=='baseline')
    assert 'Contracts #7' in baseline['data']['reference'] and baseline['data']['file_id']
    with database(path) as db:f=db.execute('SELECT * FROM files').fetchone();assert hashlib.sha256(f['content']).hexdigest()==f['checksum']
    action(client,r,'import_contract',{'contract_id':'7'});item(client,r,'baseline',{'reference':'new','text':'Changed locally','file_id':''})
    assert run_once(path,httpx.MockTransport(respond))['state']=='blocked'
    with pytest.raises(Blocked):connection('CONTRACTS','other-workspace',path)


def test_legacy_invoice_credentials_cannot_cross_workspaces(client,app,tmp_path,monkeypatch):
    monkeypatch.setenv('DOAIDE_INVOICE_ADAPTER_URL','https://invoice.example/api/v1/invoices/drafts');monkeypatch.setenv('DOAIDE_INVOICE_ADAPTER_TOKEN','synthetic')
    workspace=client.get('/api/auth/me').json()['workspace_id'];assert connection('INVOICE',workspace,tmp_path/'test.db')
    colleague(client,app)
    with pytest.raises(Blocked):connection('INVOICE',workspace,tmp_path/'test.db')


def test_sop_template_remaps_branches_and_new_hire_policy_is_idempotent(client,app,tmp_path):
    r=create(client,'sop');file=upload(client,r)
    ids=[item(client,r,'step',{'position':str(n),'instruction':'Step '+str(n),'prerequisites':'','file_id':file})['id'] for n in range(1,4)]
    item(client,r,'branch',{'step_id':ids[0],'condition':'Power off','yes_step':ids[1],'no_step':ids[2]})
    action(client,r,'publish',{'review':'Checked procedure','pass_percent':'80'})
    action(client,r,'new_hire_policy',{'enabled':'Yes','due_days':'5'});run_once(tmp_path/'test.db')
    initial=len([x for x in workflow(client,r)['items'] if x['kind']=='assignment'])
    colleague(client,app,'operator','newhire@example.test');run_once(tmp_path/'test.db');run_once(tmp_path/'test.db')
    assert len([x for x in workflow(client,r)['items'] if x['kind']=='assignment'])==initial+1
    clone={'id':action(client,r,'copy_template',{'title':'Different process'})['result']['record_id']}
    copied=workflow(client,clone);assert copied['stage']=='draft' and not any(x['kind']=='assignment' for x in copied['items'])
    branch=next(x['data'] for x in copied['items'] if x['kind']=='branch')
    newids={x['id'] for x in copied['items'] if x['kind']=='step'}
    assert {branch['step_id'],branch['yes_step'],branch['no_step']}==newids and not newids.intersection(ids)
    action(client,clone,'publish',{'review':'Reviewed independently','pass_percent':'80'})
    assert workflow(client,r)['stage']=='published'


def test_encrypted_backup_roundtrip_tamper_and_private_key(client,tmp_path):
    create(client);path=tmp_path/'test.db';key=tmp_path/'key';private_write(key,Fernet.generate_key())
    encrypted=tmp_path/'backup.enc';result=encrypt_backup(path,encrypted,key);assert result['encrypted_round_trip']=='ok'
    restored=tmp_path/'restored.db';assert decrypt_backup(encrypted,restored,key)['integrity']=='ok'
    with database(restored) as db:assert db.execute('SELECT count(*) FROM records').fetchone()[0]==1
    with pytest.raises(FileExistsError):decrypt_backup(encrypted,restored,key)
    raw=bytearray(encrypted.read_bytes());raw[-10]^=1;encrypted.write_bytes(raw)
    with pytest.raises(InvalidToken):decrypt_backup(encrypted,tmp_path/'tampered.db',key)
    assert not (tmp_path/'tampered.db').exists()
    key.chmod(0o644)
    with pytest.raises(ValueError,match='private'):encrypt_backup(path,tmp_path/'bad.enc',key)


def test_workspace_erasure_preview_confirmation_and_isolation(client,app,tmp_path):
    r,doc=approve_scope(client);file=upload(client,r)
    client.post('/api/records/'+r['id']+'/shares',json={'document_id':doc,'purpose':'view','recipient':'client@example.test'})
    workspace=client.get('/api/auth/me').json()['workspace_id'];path=tmp_path/'test.db'
    fees=create(client,'fees');proof=upload(client,fees);action(client,fees,'approve_agreement',{'reason':'Approved fee terms'})
    action(client,fees,'ledger',{'kind':'payment','amount':'10','reference':'ERASE-PAYMENT','date':date_plus(0),'note':'Verified receipt','method':'Cash','file_id':proof})
    prepare_order(client)
    with TestClient(app) as other:
        other.post('/api/auth/register',json={'email':'other@example.test','password':'another-long-password'});keep=create(other)
        assert erase(path,workspace,'approved-test-policy')['counts']['records']==3
        with pytest.raises(ValueError):erase(path,workspace,'approved-test-policy',True,'wrong')
        assert client.get('/api/records/'+r['id']).status_code==200
        result=erase(path,workspace,'approved-test-policy',True,workspace);assert result['executed']
        assert client.get('/api/records').json()==[] and other.get('/api/records/'+keep['id']).status_code==200
        assert client.get('/api/files/'+file).status_code==404 and client.get('/api/documents/'+doc+'/pdf').status_code==404
    with database(path) as db:assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_claim_redaction_exports_only_approved_derivative_and_retains_original(client):
    r=create(client,'claimpack');original=upload(client,r,'Private original: SECRET-ACCOUNT-123. Delivery confirmed.');redacted=upload(client,r,'Delivery confirmed. Account [REDACTED].')
    item(client,r,'template',{'provider':'Test provider','reason_code':'ND','version':'1','deadline':timestamp(10),'max_mb':'10','required_kinds':'Delivery','source':'Test instructions'})
    evidence=item(client,r,'evidence',{'kind':'Delivery','file_id':original,'fact':'Delivery confirmed','redaction':'Remove account number'})['id']
    action(client,r,'verify_evidence',{'item_id':evidence,'note':'Original verified'})
    item(client,r,'timeline',{'at':timestamp(-1),'fact':'Delivery confirmed','evidence_id':evidence})
    action(client,r,'pack',status=422)
    action(client,r,'approve_redaction',{'item_id':evidence,'redacted_file_id':redacted,'reason':'Reviewed replacement; account removed'})
    doc=action(client,r,'pack')['result']['document_id']
    pdf=client.get('/api/documents/'+doc+'/pdf').content
    assert 'SECRET-ACCOUNT' not in '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    packet=zipfile.ZipFile(io.BytesIO(client.get('/api/documents/'+doc+'/packet').content));manifest=json.loads(packet.read('manifest.json'))
    assert [x['id'] for x in manifest['files']]==[redacted]
    assert manifest['approved_attachment_redactions'][0]['original_file_id']==original
    for name in packet.namelist():
        if name.endswith('.txt'):assert b'SECRET-ACCOUNT' not in packet.read(name)
    assert b'SECRET-ACCOUNT' in client.get('/api/files/'+original).content


def test_external_service_start_records_before_evidence_once(client,tmp_path):
    r=create(client,'amc');asset=item(client,r,'asset',{'site':'Test site','serial':'START-1','model':'Pump','warranty':'','coverage':'Service'})['id']
    visit=item(client,r,'visit',{'asset_id':asset,'technician':'external@example.test','start':timestamp(-2),'end':timestamp(-1),'chargeable':'No','checklist':'Pressure','access':'Assigned link'})['id']
    token=client.post('/api/records/'+r['id']+'/contractor-links',json={'item_id':visit,'recipient':'external@example.test'}).json()['path'].split('=')[1]
    data={'email':'external@example.test','notes':'Before service inspection'};files={'file':('before.txt',b'Pressure low','text/plain')}
    first=client.post('/api/contractor/'+token+'/start',data=data,files=files);assert first.status_code==200,first.text
    repeat=client.post('/api/contractor/'+token+'/start',data=data,files=files);assert repeat.json()==first.json()
    with database(tmp_path/'test.db') as db:assert db.execute('SELECT count(*) FROM files WHERE record_id=?',(r['id'],)).fetchone()[0]==1
    assert client.get('/api/contractor/'+token).json()['issue']['started_at']
