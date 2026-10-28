"""Workspace, operational commands, files, immutable documents and limited portals."""
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from .db import database, token_hash
from .migrations import record_access, permit
from . import operations as op
from .documents import extract_file, ocr_file, pdf_document, packet_zip, MAX_FILE, register_file_controls, stored_pdf, public_pdf
from .domain import DomainError, calculate
from .commercial import admit

class Strict(BaseModel): model_config=ConfigDict(extra='forbid')
class Change(Strict):
    revision:int=Field(ge=1)
    data:dict=Field(default_factory=dict)
class Invite(Strict):
    email:str=Field(min_length=5,max_length=254)
    role:str
class AcceptInvite(Strict): token:str=Field(min_length=20,max_length=200)
class Role(Strict): role:str
class WorkspaceSettings(Strict):
    name:str=Field(min_length=1,max_length=100)
    timezone:str
class Share(Strict):
    document_id:str
    recipient:str=Field(min_length=5,max_length=254)
    hours:int=Field(default=72,ge=1,le=720)
    purpose:str='view'
class Acceptance(Strict):
    name:str=Field(min_length=2,max_length=160)
    email:str
    checksum:str
    agree:bool
    decision:str='accept'
    comments:str=Field(default='',max_length=5000)
class ImportPreview(Strict):
    csv:str=Field(max_length=400000)
    mapping:dict


def install_operations(app,db_path,current_user):
    def transaction():
        return database(db_path)
    def check_revision(db,record,body):
        state=op.get_state(db,record['id'])
        if body.revision!=state['revision']:raise HTTPException(409,'Workflow changed in another window. Reload before continuing.')
    def document_access(db,identifier,user):
        doc=db.execute('SELECT * FROM documents WHERE id=?',(identifier,)).fetchone()
        if not doc:raise HTTPException(404,'Document not found')
        record_access(db,doc['record_id'],user)
        return dict(doc)

    @app.get('/api/workspaces')
    def workspaces(user=Depends(current_user)):
        with transaction() as db:
            return [dict(r) for r in db.execute('SELECT w.*,m.role FROM workspaces w JOIN memberships m ON m.workspace_id=w.id WHERE m.user_id=? ORDER BY w.created_at',(user['id'],))]

    @app.post('/api/workspaces/{workspace_id}/select')
    def select_workspace(workspace_id:str,response:Response,request:Request,user=Depends(current_user)):
        with transaction() as db:
            if not db.execute('SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?',(workspace_id,user['id'])).fetchone():raise HTTPException(403,'Workspace membership required')
        response.set_cookie('doaide_workspace',workspace_id,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=43200)
        return {'workspace_id':workspace_id}

    @app.get('/api/workspace/members')
    def members(user=Depends(current_user)):
        with transaction() as db:
            return [dict(r) for r in db.execute("SELECT u.id,u.email,m.role,coalesce(a.fees_mode,'financial') AS fees_mode FROM memberships m JOIN users u ON u.id=m.user_id LEFT JOIN member_access a ON a.workspace_id=m.workspace_id AND a.user_id=m.user_id WHERE m.workspace_id=? ORDER BY u.email",(user['workspace_id'],))]

    @app.put('/api/workspace')
    def settings(body:WorkspaceSettings,user=Depends(current_user)):
        permit(user,'owner')
        try:ZoneInfo(body.timezone)
        except (KeyError,ValueError):raise HTTPException(422,'Invalid IANA timezone')
        with transaction() as db:db.execute('UPDATE workspaces SET name=?,timezone=? WHERE id=?',(body.name.strip(),body.timezone,user['workspace_id']))
        return {'ok':True}

    @app.post('/api/workspace/invitations',status_code=201)
    def invite(body:Invite,user=Depends(current_user)):
        permit(user,'owner')
        if body.role not in ('owner','operator','reviewer','viewer'):raise HTTPException(422,'Invalid workspace role')
        email=body.email.strip().lower()
        if '@' not in email or ' ' in email:raise HTTPException(422,'Invalid email')
        token=secrets.token_urlsafe(32)
        with transaction() as db:db.execute('INSERT INTO invitations VALUES (?,?,?,?,?,NULL)',(token_hash(token),user['workspace_id'],email,body.role,int(time.time())+86400*3))
        return {'token':token,'email':email,'expires_in_hours':72,'path':'/?invite='+token}

    @app.post('/api/workspace/invitations/accept')
    def accept_invite(body:AcceptInvite,user=Depends(current_user)):
        with transaction() as db:
            db.execute('BEGIN IMMEDIATE')
            invitation=db.execute('SELECT * FROM invitations WHERE token_hash=? AND expires_at>? AND used_at IS NULL',(token_hash(body.token),int(time.time()))).fetchone()
            if not invitation or invitation['email']!=user['email']:raise HTTPException(403,'Invitation is expired or belongs to a different email')
            # Invitation acceptance must not silently demote an existing member.
            if not db.execute('SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?',(invitation['workspace_id'],user['id'])).fetchone():
                admit(db,invitation['workspace_id'],'members')
            db.execute('INSERT OR IGNORE INTO memberships VALUES (?,?,?)',(invitation['workspace_id'],user['id'],invitation['role']))
            db.execute('UPDATE invitations SET used_at=? WHERE token_hash=?',(op.now(),token_hash(body.token)))
            return {'workspace_id':invitation['workspace_id']}

    @app.put('/api/workspace/members/{member_id}')
    def member_role(member_id:str,body:Role,user=Depends(current_user)):
        permit(user,'owner')
        if body.role not in ('owner','operator','reviewer','viewer','remove'):raise HTTPException(422,'Invalid role')
        with transaction() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT role FROM memberships WHERE workspace_id=? AND user_id=?',(user['workspace_id'],member_id)).fetchone()
            if not old:raise HTTPException(404,'Member not found')
            if old['role']=='owner' and body.role!='owner':
                op.require(db.execute("SELECT COUNT(*) FROM memberships WHERE workspace_id=? AND role='owner'",(user['workspace_id'],)).fetchone()[0]>1,'A workspace must retain at least one owner')
            if body.role=='remove':db.execute('DELETE FROM memberships WHERE workspace_id=? AND user_id=?',(user['workspace_id'],member_id))
            else:db.execute('UPDATE memberships SET role=? WHERE workspace_id=? AND user_id=?',(body.role,user['workspace_id'],member_id))
        return {'ok':True}

    @app.get('/api/records/{record_id}/operations')
    def operations(record_id:str,user=Depends(current_user)):
        with transaction() as db:return op.view(db,record_access(db,record_id,user),user)

    @app.post('/api/records/{record_id}/items/{kind}',status_code=201)
    def create_item(record_id:str,kind:str,body:Change,user=Depends(current_user)):
        with transaction() as db:
            db.execute('BEGIN IMMEDIATE');r=record_access(db,record_id,user);check_revision(db,r,body)
            identifier=op.resource(db,r,user,kind,body.data)
            return {'id':identifier,'workflow':op.view(db,r,user)}

    @app.put('/api/records/{record_id}/items/{kind}/{item_id}')
    def update_item(record_id:str,kind:str,item_id:str,body:Change,user=Depends(current_user)):
        with transaction() as db:
            db.execute('BEGIN IMMEDIATE');r=record_access(db,record_id,user);check_revision(db,r,body)
            op.resource(db,r,user,kind,body.data,item_id)
            return op.view(db,r,user)

    @app.delete('/api/records/{record_id}/items/{kind}/{item_id}')
    def delete_item(record_id:str,kind:str,item_id:str,body:Change,user=Depends(current_user)):
        with transaction() as db:
            db.execute('BEGIN IMMEDIATE');r=record_access(db,record_id,user);check_revision(db,r,body)
            op.resource(db,r,user,kind,{},item_id,True)
            return op.view(db,r,user)

    @app.post('/api/records/{record_id}/actions/{action}')
    def action(record_id:str,action:str,body:Change,request:Request,user=Depends(current_user)):
        key=request.headers.get('Idempotency-Key','')
        if not 8<=len(key)<=128:raise HTTPException(422,'Provide an Idempotency-Key of 8–128 characters')
        fingerprint=op.digest({'record':record_id,'action':action,'body':body.model_dump(),'actor':user['id']})
        with transaction() as db:
            db.execute('BEGIN IMMEDIATE');r=record_access(db,record_id,user)
            cached=db.execute('SELECT * FROM idempotency WHERE workspace_id=? AND key=?',(user['workspace_id'],key)).fetchone()
            if cached:
                if cached['request_hash']!=fingerprint:raise HTTPException(409,'Idempotency key was used for a different request')
                return json.loads(cached['response'])
            check_revision(db,r,body)
            try:result=op.execute(db,r,user,action,body.data)
            except sqlite3.IntegrityError as exc:raise HTTPException(409,'This reference already exists; use the existing transaction or a new unique reference') from exc
            response={'result':result,'workflow':op.view(db,r,user)}
            db.execute('INSERT INTO idempotency VALUES (?,?,?,?)',(user['workspace_id'],key,fingerprint,op.dump(response)))
            return response

    @app.post('/api/records/{record_id}/revisions',status_code=201)
    def new_revision(record_id:str,body:Change,user=Depends(current_user)):
        permit(user,'owner','operator','reviewer')
        with transaction() as db:
            db.execute('BEGIN IMMEDIATE');r=record_access(db,record_id,user);check_revision(db,r,body)
            op.require(r['product'] in ('scope','rfq','tender','handover','sop','claimpack'),'Use the product renewal or financial adjustment action for this record')
            state=op.get_state(db,record_id)
            op.require(not state['data'].get('next_revision'),'A next revision already exists; open it from the workflow result')
            payload=json.loads(r['payload'])
            if r['product']=='sop':payload['version']=str(int(payload['version'])+1);payload['acknowledgements']=[]
            identifier=op.clone_record(db,r,user,payload,r['title']+' · revision')
            filemap={}
            copied_bytes=db.execute('SELECT coalesce(sum(length(content)),0) FROM files WHERE record_id=?',(record_id,)).fetchone()[0]
            admit(db,user['workspace_id'],'source_bytes',copied_bytes)
            for file in db.execute('SELECT * FROM files WHERE record_id=?',(record_id,)).fetchall():
                new_id=op.uid();filemap[file['id']]=new_id
                db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?)',(new_id,identifier,file['name'],file['mime'],file['size'],file['checksum'],file['content'],file['extracted'],file['extraction_status'],user['id'],op.now()))
                control=db.execute('SELECT * FROM file_controls WHERE file_id=?',(file['id'],)).fetchone()
                if control:
                    op.require(not control['deleted_at'],'Remove references to purged evidence before creating another revision')
                    db.execute('INSERT INTO file_controls VALUES (?,?,?,?,?)',(new_id,control['scan_status'],control['retain_until'],None,None))
            olditems=op.items(db,record_id);itemmap={i['id']:op.uid() for i in olditems}
            for i in olditems:
                clean={k:filemap.get(v,itemmap.get(v,v)) if isinstance(v,str) else v for k,v in i['data'].items() if not k.startswith('_')}
                if i['kind']=='issue':clean['_status']='open'
                op.store_item(db,identifier,i['kind'],clean,user,itemmap[i['id']])
            # Insert directly so a copied handover does not duplicate its intake snags.
            db.execute('INSERT INTO operations(record_id,data) VALUES (?,?)',(identifier,op.dump({'previous_revision':record_id})))
            state['data']['next_revision']=identifier;op.event(db,r,user,'revision.created',{'record_id':identifier},state)
            return {'record_id':identifier}

    @app.post('/api/records/{record_id}/files',status_code=201)
    async def upload(record_id:str,file:UploadFile,user=Depends(current_user)):
        permit(user,'owner','operator','reviewer')
        with transaction() as db:record_access(db,record_id,user)
        content=await file.read(MAX_FILE+1);metadata=extract_file(file.filename or '',content);identifier=op.uid()
        with transaction() as db:
            db.execute('BEGIN IMMEDIATE');r=record_access(db,record_id,user)
            if r['status']=='archived':raise HTTPException(409,'Restore this record before uploading')
            admit(db,user['workspace_id'],'source_bytes',len(content))
            db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?)',(identifier,record_id,metadata['name'],metadata['mime'],metadata['size'],metadata['checksum'],content,metadata['extracted'],metadata['extraction_status'],user['id'],op.now()))
            register_file_controls(db,identifier,metadata['scan_status'])
            s=op.get_state(db,record_id);op.event(db,r,user,'file.uploaded',{'id':identifier,'name':metadata['name'],'checksum':metadata['checksum']},s)
        return {'id':identifier,**metadata}

    @app.get('/api/files/{file_id}')
    def download_file(file_id:str,user=Depends(current_user)):
        with transaction() as db:
            row=db.execute('SELECT * FROM files WHERE id=?',(file_id,)).fetchone()
            if not row:raise HTTPException(404,'File not found')
            record_access(db,row['record_id'],user)
            control=db.execute('SELECT * FROM file_controls WHERE file_id=?',(file_id,)).fetchone()
            if control and control['deleted_at']:raise HTTPException(410,'File content was deleted under the recorded retention policy')
            return Response(row['content'],media_type=row['mime'],headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['name']),'Content-Security-Policy':"sandbox"})

    @app.post('/api/files/{file_id}/ocr')
    def request_ocr(file_id:str,user=Depends(current_user)):
        permit(user,'owner','operator','reviewer')
        with transaction() as db:
            db.execute('BEGIN IMMEDIATE')
            f=db.execute('SELECT * FROM files WHERE id=?',(file_id,)).fetchone()
            if not f:raise HTTPException(404,'File not found')
            r=record_access(db,f['record_id'],user)
            identifier=op.enqueue(db,r,user,'ocr',{'file_id':file_id},'ocr:'+file_id)
        return {'job_id':identifier}

    @app.get('/api/documents/{document_id}')
    def document(document_id:str,user=Depends(current_user)):
        with transaction() as db:
            d=document_access(db,document_id,user);d['snapshot']=json.loads(d['snapshot']);return d

    @app.get('/api/documents/{document_id}/pdf')
    def document_pdf(document_id:str,user=Depends(current_user)):
        with transaction() as db:
            d=document_access(db,document_id,user);content=stored_pdf(db,d)
        return Response(content,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{d["number"]}.pdf"'})

    @app.get('/api/documents/{document_id}/packet')
    def document_packet(document_id:str,user=Depends(current_user)):
        with transaction() as db:
            d=document_access(db,document_id,user);content=packet_zip(db,d)
        return Response(content,media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{d["number"]}-packet.zip"'})

    @app.get('/api/documents/{document_id}/comparison.csv')
    def comparison_csv(document_id:str,user=Depends(current_user)):
        with transaction() as db:d=document_access(db,document_id,user)
        op.require(d['kind']=='supplier-comparison','Choose a frozen supplier comparison')
        snap=json.loads(d['snapshot']);output=io.StringIO();writer=csv.writer(output)
        writer.writerow(['Supplier','Item reference','Quantity','Unit','Currency','FX to INR','Goods unit price','Discount','Goods tax %','Freight','Freight tax %','Duties','Packaging','Packaging tax %','Landed INR','Lead days','Valid until','Payment terms','Source line','Blockers'])
        def safe(value):
            text=str(value)
            return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r')) else text
        for supplier in snap['workflow']['comparison']:
            for line in supplier['lines']:
                values=[supplier['supplier']]+[line.get(k,'') for k in ('requirement_id','quantity','unit','currency','fx','price','discount','tax','freight','freight_tax','duties','packaging','packaging_tax')]+[format(line['total_paise']/100,'.2f')]+[line.get(k,'') for k in ('lead_days','valid_until','payment_terms','source_line')]+['; '.join(supplier['blockers'])]
                writer.writerow([safe(v) for v in values])
        return Response('\ufeff'+output.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{d["number"]}.csv"'})

    @app.get('/api/documents/{document_id}/validity')
    def document_validity(document_id:str,user=Depends(current_user)):
        with transaction() as db:
            d=document_access(db,document_id,user);snap=json.loads(d['snapshot']);s=op.get_state(db,d['record_id'])
            if d['kind']!='controlled-procedure-copy':return {'current':True,'expires_at':None}
            extra=snap['extra']
            return {'current':extra['expires_at']>op.now() and s['stage']=='published' and s['data'].get('published_document')==extra['source_document'],'expires_at':extra['expires_at'],'source_document':extra['source_document']}

    @app.post('/api/records/{record_id}/shares',status_code=201)
    def share(record_id:str,body:Share,user=Depends(current_user)):
        permit(user,'owner','reviewer')
        if body.purpose not in ('view','accept'):raise HTTPException(422,'Invalid sharing purpose')
        with transaction() as db:
            db.execute('BEGIN IMMEDIATE');r=record_access(db,record_id,user);d=document_access(db,body.document_id,user)
            op.require(d['record_id']==record_id,'Choose a document from this record')
            s=op.get_state(db,record_id)
            if body.purpose=='accept':
                op.require(r['product'] in ('scope','handover','amc'),'Acceptance is available for changes, handovers and renewal offers')
                approved='renewal_offer_document' if r['product']=='amc' else 'approved_document'
                accepted='renewal_accepted' if r['product']=='amc' else 'accepted_document'
                op.require(s['data'].get(approved)==d['id'] and d['record_version']==r['version'],'Only the current approved document can be accepted')
                op.require(not s['data'].get(accepted),'This document has already been accepted')
            email=body.recipient.strip().lower();op.require('@' in email and ' ' not in email,'Enter the recipient email')
            if r['product']=='fees':op.require(any(i['data']['email']==email for i in op.items(db,r['id'],'guardian')),'Share student records only with a linked guardian')
            if r['product']=='scope' and body.purpose=='accept':
                projects=op.items(db,r['id'],'project')
                if projects:op.require(email==projects[0]['data']['contact'],'Send acceptance to the project approval contact')
            token=secrets.token_urlsafe(32);identifier=op.uid()
            expiry=int(time.time())+body.hours*3600
            if r['product']=='amc' and body.purpose=='accept':
                offer=s['data']['renewal_offer'];op.require(email==offer['contact'],'Send the offer to its customer approval contact')
                zone=db.execute('SELECT timezone FROM workspaces WHERE id=?',(user['workspace_id'],)).fetchone()[0]
                expiry=min(expiry,int(datetime.fromisoformat(offer['valid_until']+'T23:59:59').replace(tzinfo=ZoneInfo(zone)).timestamp()))
                op.require(expiry>int(time.time()),'Renewal offer expired')
            if r['product']=='scope' and body.purpose=='accept' and projects:
                zone=db.execute('SELECT timezone FROM workspaces WHERE id=?',(user['workspace_id'],)).fetchone()[0]
                validity=datetime.fromisoformat(projects[0]['data']['valid_until']+'T23:59:59').replace(tzinfo=ZoneInfo(zone))
                expiry=min(expiry,int(validity.timestamp()));op.require(expiry>int(time.time()),'The offer has expired')
            db.execute('INSERT INTO shares VALUES (?,?,?,?,?,?,NULL,NULL,NULL,NULL)',(identifier,token_hash(token),d['id'],email,body.purpose,expiry))
            op.event(db,r,user,'share.created',{'id':identifier,'document_id':d['id'],'recipient':email,'purpose':body.purpose},s)
        return {'id':identifier,'path':'/?portal='+token,'token':token}

    @app.delete('/api/shares/{share_id}')
    def revoke(share_id:str,user=Depends(current_user)):
        permit(user,'owner','reviewer')
        with transaction() as db:
            db.execute('BEGIN IMMEDIATE');s=db.execute('SELECT * FROM shares WHERE id=?',(share_id,)).fetchone()
            if not s:raise HTTPException(404,'Link not found')
            d=document_access(db,s['document_id'],user);r=record_access(db,d['record_id'],user)
            db.execute('UPDATE shares SET revoked_at=? WHERE id=?',(op.now(),share_id))
            state=op.get_state(db,r['id']);op.event(db,r,user,'share.revoked',{'id':share_id},state)
        return {'ok':True}

    def portal_access(db,token):
        row=db.execute('SELECT * FROM shares WHERE token_hash=? AND expires_at>? AND revoked_at IS NULL',(token_hash(token),int(time.time()))).fetchone()
        if not row:raise HTTPException(404,'This link has expired or was revoked')
        doc=dict(db.execute('SELECT * FROM documents WHERE id=?',(row['document_id'],)).fetchone())
        return dict(row),doc

    def public_snapshot(d):
        snap=json.loads(d['snapshot'])
        if d['kind']=='amc-renewal-offer':
            return {'record':snap['record'],'payload':{'customer':snap['payload']['customer']},'extra':snap['extra'],'items':[],'stage':'renewal-offered'}
        # External links expose only the selected record and document. No workspace,
        # raw file download, internal event feed, assignment or answer key is exposed.
        snap['items']=[{'kind':i['kind'],'data':i['data']} for i in snap['items'] if i['kind'] not in ('policy','guardian','assignment','question')]
        snap.pop('files',None)
        for k in ('invoice_job','publication','amendments'):snap.get('workflow',{}).pop(k,None)
        return snap

    @app.get('/api/portal/{token}')
    def portal(token:str):
        with transaction() as db:
            s,d=portal_access(db,token);decision=db.execute('SELECT decision,comments FROM share_decisions WHERE share_id=?',(s['id'],)).fetchone()
        return {'number':d['number'],'kind':d['kind'],'checksum':d['checksum'],'created_at':d['created_at'],'purpose':s['purpose'],'recipient':s['recipient'],'accepted_at':s['accepted_at'],'accepted_name':s['accepted_name'],'decision':dict(decision) if decision else None,'snapshot':public_snapshot(d)}

    @app.post('/api/portal/{token}/accept')
    def accept_document(token:str,body:Acceptance):
        with transaction() as db:
            db.execute('BEGIN IMMEDIATE');share,d=portal_access(db,token)
            op.require(share['purpose']=='accept','This link is view-only')
            op.require(body.decision in ('accept','decline'),'Choose accept or decline')
            op.require(body.agree and body.checksum==d['checksum'],'Confirm acceptance of this exact document')
            op.require(body.email.strip().lower()==share['recipient'],'Use the recipient email associated with this link')
            if share['accepted_at']:return {'accepted_at':share['accepted_at'],'checksum':d['checksum']}
            r=dict(db.execute('SELECT * FROM records WHERE id=?',(d['record_id'],)).fetchone());s=op.get_state(db,r['id'])
            approved='renewal_offer_document' if r['product']=='amc' else 'approved_document'
            accepted='renewal_accepted' if r['product']=='amc' else 'accepted_document'
            op.require(s['data'].get(approved)==d['id'] and r['version']==d['record_version'],'The document changed; request a new link')
            op.require(not s['data'].get(accepted),'The document has already been accepted through another link')
            timestamp=op.now();db.execute('UPDATE shares SET accepted_at=?,accepted_name=?,accepted_email=? WHERE id=?',(timestamp,body.name.strip(),body.email.lower(),share['id']))
            db.execute('INSERT INTO share_decisions VALUES (?,?,?)',(share['id'],body.decision,body.comments))
            if r['product']!='amc':s['stage']='accepted' if body.decision=='accept' else 'declined'
            if body.decision=='accept':s['data'][accepted]=d['id']
            else:s['data'].pop(approved,None)
            s['data']['acceptance']={'name':body.name.strip(),'email':body.email.lower(),'checksum':d['checksum'],'decision':body.decision,'comments':body.comments,'at':timestamp}
            op.event(db,r,{'email':body.email.lower()},'client.'+s['stage'],s['data']['acceptance'],s)
        return {'accepted_at':timestamp,'checksum':d['checksum']}

    @app.get('/api/portal/{token}/pdf')
    def portal_pdf(token:str):
        with transaction() as db:
            _,d=portal_access(db,token);content=public_pdf(db,d)
        return Response(content,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{d["number"]}.pdf"'})

    @app.get('/api/records/{record_id}/calendar.ics')
    def calendar(record_id:str,user=Depends(current_user)):
        with transaction() as db:
            r=record_access(db,record_id,user);op.require(r['product']=='renew','Calendar exports are available for Renew')
            day=op.notice_date(r,op.items(db,record_id,'terms')).replace('-','');p=json.loads(r['payload'])
        def esc(value):return value.replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(',','\\,').replace(';','\\;')
        next_day=(datetime.strptime(day,'%Y%m%d')+timedelta(days=1)).strftime('%Y%m%d')
        text='\r\n'.join(['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//DoAide//Renew//EN','BEGIN:VEVENT',f'UID:{record_id}@doaide',f'DTSTAMP:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}',f'DTSTART;VALUE=DATE:{day}',f'DTEND;VALUE=DATE:{next_day}','SUMMARY:'+esc('Notice deadline: '+p['service']),'DESCRIPTION:'+esc(p['vendor']+' · '+p['owner']),'END:VEVENT','END:VCALENDAR',''])
        return Response(text,media_type='text/calendar',headers={'Content-Disposition':'attachment; filename="renewal-notice.ics"'})

    @app.get('/api/inventory')
    def inventory(user=Depends(current_user)):
        with transaction() as db:return [{**dict(r),'data':json.loads(r['data'])} for r in db.execute('SELECT * FROM stock WHERE workspace_id=? ORDER BY sku',(user['workspace_id'],))]

    @app.get('/api/jobs')
    def jobs(user=Depends(current_user)):
        with transaction() as db:
            restriction=" AND (record_id IS NULL OR record_id NOT IN (SELECT id FROM records WHERE product='fees'))" if user.get('fees_access')=='academic' else ''
            return [dict(r) for r in db.execute('SELECT id,record_id,kind,state,due_at,attempts,last_error,updated_at FROM jobs WHERE workspace_id=?'+restriction+' ORDER BY created_at DESC LIMIT 500',(user['workspace_id'],))]

    @app.post('/api/jobs/{job_id}/retry')
    def retry_job(job_id:str,user=Depends(current_user)):
        permit(user,'owner')
        with transaction() as db:
            changed=db.execute("UPDATE jobs SET state='queued',due_at=?,last_error=NULL,attempts=0 WHERE id=? AND workspace_id=? AND state IN ('blocked','failed','dead-letter')",(op.now(),job_id,user['workspace_id'])).rowcount
            if not changed:raise HTTPException(409,'Only blocked or failed jobs can be retried')
        return {'ok':True}

    @app.get('/api/integrations')
    def integrations(user=Depends(current_user)):
        import shutil
        from .authority_adapters import authority,configured
        with transaction() as db:
            connections={service.lower():{'configured':configured(service,user['workspace_id']),'active':bool(authority(db,service,user['workspace_id']))} for service in ('INVENTORY','SCHEDULER')}
        return {'authorities':connections,'delivery_mode':os.environ.get('DOAIDE_DELIVERY_MODE','disabled'),'email':bool(os.environ.get('DOAIDE_SMTP_HOST')),'payments':bool(os.environ.get('RAZORPAY_KEY_ID') and os.environ.get('RAZORPAY_KEY_SECRET') and os.environ.get('RAZORPAY_WEBHOOK_SECRET')),'invoice_adapter':bool(os.environ.get('DOAIDE_INVOICE_ADAPTER_URL')),'ocr':bool(shutil.which('tesseract') and shutil.which('pdftoppm'))}

    @app.post('/api/imports/collect/preview',status_code=201)
    def import_preview(body:ImportPreview,user=Depends(current_user)):
        permit(user,'owner','operator','reviewer')
        required={'customer','invoice','amount','paid','due'};op.require(set(body.mapping)==required,'Map customer, invoice, amount, paid and due columns')
        reader=csv.DictReader(io.StringIO(body.csv));op.require(reader.fieldnames and set(body.mapping.values())<=set(reader.fieldnames),'CSV column mapping is invalid')
        rows=[];seen=set()
        for n,row in enumerate(reader,2):
            if len(rows)>=1000:raise HTTPException(422,'Import at most 1,000 invoices at once')
            p={key:row[column] for key,column in body.mapping.items()};p.update(promise='',disputed='No',notes='Imported CSV')
            errors=[]
            try:p,_=calculate('collect',p)
            except DomainError as e:errors.append(str(e))
            key=(str(p.get('customer','')).casefold(),str(p.get('invoice','')).casefold())
            if key in seen:errors.append('Duplicate invoice in this CSV')
            seen.add(key);rows.append({'line':n,'payload':p,'errors':errors})
        op.require(rows,'CSV has no data rows')
        with transaction() as db:
            existing={(json.loads(r['payload'])['customer'].casefold(),json.loads(r['payload'])['invoice'].casefold()) for r in db.execute("SELECT r.payload FROM records r JOIN record_workspaces w ON w.record_id=r.id WHERE w.workspace_id=? AND r.product='collect' AND r.status!='archived'",(user['workspace_id'],))}
            for row in rows:
                key=(row['payload']['customer'].casefold(),row['payload']['invoice'].casefold())
                if key in existing:row['errors'].append('Invoice already exists in this workspace')
            identifier=op.uid();db.execute('INSERT INTO imports VALUES (?,?,?,?,?,?,?)',(identifier,user['workspace_id'],op.dump(body.mapping),op.dump(rows),'preview',user['id'],op.now()))
        return {'id':identifier,'rows':rows,'can_commit':not any(r['errors'] for r in rows)}

    @app.post('/api/imports/{import_id}/commit')
    def import_commit(import_id:str,user=Depends(current_user)):
        permit(user,'owner','operator','reviewer')
        with transaction() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM imports WHERE id=? AND workspace_id=?',(import_id,user['workspace_id'])).fetchone()
            if not row:raise HTTPException(404,'Import not found')
            op.require(row['state']=='preview','Import is already committed or reversed');rows=json.loads(row['rows'])
            op.require(not any(r['errors'] for r in rows),'Fix import errors and preview again')
            admit(db,user['workspace_id'],'records',len(rows),product='collect')
            existing={(json.loads(r[0])['customer'].casefold(),json.loads(r[0])['invoice'].casefold()) for r in db.execute("SELECT r.payload FROM records r JOIN record_workspaces w ON w.record_id=r.id WHERE w.workspace_id=? AND r.product='collect' AND r.status!='archived'",(user['workspace_id'],))}
            for item in rows:
                p=item['payload'];key=(p['customer'].casefold(),p['invoice'].casefold());op.require(key not in existing,'An invoice was added since preview; preview again')
                identifier=op.uid();timestamp=op.now();db.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?)',(identifier,user['id'],'collect',p['invoice']+' · '+p['customer'],op.dump(p),'draft',1,timestamp,timestamp));db.execute('INSERT INTO record_workspaces VALUES (?,?)',(identifier,user['workspace_id']))
                db.execute('INSERT INTO audit_events(record_id,user_id,action,version,snapshot,created_at) VALUES (?,?,?,?,?,?)',(identifier,user['id'],'imported:'+import_id,1,op.dump(p),timestamp));item['record_id']=identifier;existing.add(key)
            db.execute("UPDATE imports SET state='committed',rows=? WHERE id=?",(op.dump(rows),import_id))
        return {'import_id':import_id,'records':[r['record_id'] for r in rows]}

    @app.post('/api/imports/{import_id}/reverse')
    def reverse_import(import_id:str,user=Depends(current_user)):
        permit(user,'owner')
        with transaction() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM imports WHERE id=? AND workspace_id=?',(import_id,user['workspace_id'])).fetchone()
            if not row:raise HTTPException(404,'Import not found')
            op.require(row['state']=='committed','Only a committed import can be reversed')
            rows=json.loads(row['rows'])
            for item in rows:
                r=record_access(db,item['record_id'],user)
                op.require(r['version']==1 and not db.execute('SELECT 1 FROM operation_events WHERE record_id=?',(r['id'],)).fetchone(),'An imported record was used or edited; reverse it with explicit adjustments')
            for item in rows:
                db.execute("UPDATE records SET status='archived',version=version+1,updated_at=? WHERE id=?",(op.now(),item['record_id']))
                db.execute('INSERT INTO audit_events(record_id,user_id,action,version,snapshot,created_at) VALUES (?,?,?,?,?,?)',(item['record_id'],user['id'],'import-reversed',2,op.dump(item['payload']),op.now()))
            db.execute("UPDATE imports SET state='reversed' WHERE id=?",(import_id,))
        return {'ok':True}

    from .webhooks import install_webhooks
    install_webhooks(app,db_path)
    from .task_portal import install_task_portal
    install_task_portal(app,db_path,current_user)
