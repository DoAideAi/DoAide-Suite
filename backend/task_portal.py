"""Expiring task links expose one snag or service visit and accept one report."""
import json
import secrets
import time
from fastapi import Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, ConfigDict
from .db import database, token_hash
from .migrations import permit, record_access
from .documents import extract_file, MAX_FILE, register_file_controls
from . import operations as op

class TaskLink(BaseModel):
    model_config=ConfigDict(extra='forbid')
    item_id:str
    recipient:str
    hours:int=Field(default=72,ge=1,le=720)


def install_task_portal(app,path,current_user):
    @app.post('/api/records/{record_id}/contractor-links',status_code=201)
    def create_link(record_id:str,body:TaskLink,user=Depends(current_user)):
        permit(user,'owner','reviewer')
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE');r=record_access(db,record_id,user);op.require(r['product'] in ('handover','amc'),'Task links belong to Handover or AMC')
            kind='visit' if r['product']=='amc' else 'issue';i=op.one_item(db,record_id,body.item_id,kind)
            op.require(i['data'].get('_status','scheduled' if kind=='visit' else 'open') in ('scheduled','open','reopened','acknowledged','in-repair'),'This task is already complete')
            recipient=body.recipient.strip().lower();op.require(recipient==i['data']['technician' if kind=='visit' else 'assignee'],'Recipient must match the assigned worker email')
            token=secrets.token_urlsafe(32);identifier=op.uid()
            db.execute('INSERT INTO task_links VALUES (?,?,?,?,?,?,?,NULL)',(identifier,token_hash(token),record_id,i['id'],recipient,int(time.time())+body.hours*3600,op.now()))
            s=op.get_state(db,record_id);op.event(db,r,user,'contractor-link.created',{'id':identifier,'item_id':i['id'],'recipient':recipient},s)
        return {'id':identifier,'path':'/?task='+token}

    def access(db,token):
        link=db.execute('SELECT * FROM task_links WHERE token_hash=? AND expires_at>? AND closed_at IS NULL',(token_hash(token),int(time.time()))).fetchone()
        if not link:raise HTTPException(404,'Contractor link expired, completed or revoked')
        r=dict(db.execute('SELECT * FROM records WHERE id=?',(link['record_id'],)).fetchone())
        op.require(r['status']!='archived','This task is archived')
        visit=r['product']=='amc';i=op.one_item(db,r['id'],link['item_id'],'visit' if visit else 'issue')
        op.require(i['data']['technician' if visit else 'assignee']==link['recipient'] and i['data'].get('_status','scheduled' if visit else 'open') in ('scheduled','open','reopened','acknowledged','in-repair'),'The assignment has changed or was completed')
        return dict(link),r,i

    @app.get('/api/contractor/{token}')
    def get_task(token:str):
        with database(path) as db:link,r,i=access(db,token)
        p=json.loads(r['payload'])
        if r['product']=='amc':
            with database(path) as db:asset=op.one_item(db,r['id'],i['data']['asset_id'],'asset')['data']
            return {'kind':'amc','site':asset['site'],'recipient':link['recipient'],'issue':{'description':asset['model']+' · '+asset['serial'],'start':i['data']['start'],'end':i['data']['end'],'started_at':i['data'].get('_started_at'),'checklist':i['data']['checklist']},'checks':[x.strip() for x in i['data']['checklist'].splitlines() if x.strip()]}
        return {'kind':'handover','site':p['site'],'recipient':link['recipient'],'issue':{k:v for k,v in i['data'].items() if k in ('room','description','severity','due')}}

    @app.post('/api/contractor/{token}/start')
    async def start(token:str,file:UploadFile,notes:str=Form(min_length=5,max_length=10000),email:str=Form()):
        with database(path) as db:access(db,token)
        content=await file.read(MAX_FILE+1);metadata=extract_file(file.filename or '',content)
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE');link,r,i=access(db,token)
            op.require(r['product']=='amc' and email.strip().lower()==link['recipient'],'Use the assigned technician email')
            op.require(i['data']['start']<=op.now(),'Cannot start a future visit')
            if i['data'].get('_started_at'):return {'started_at':i['data']['_started_at']}
            from .commercial import admit
            workspace=db.execute('SELECT workspace_id FROM record_workspaces WHERE record_id=?',(r['id'],)).fetchone()[0]
            admit(db,workspace,'source_bytes',len(content));identifier=op.uid()
            db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?)',(identifier,r['id'],metadata['name'],metadata['mime'],metadata['size'],metadata['checksum'],content,metadata['extracted'],metadata['extraction_status'],'external:'+email.lower(),op.now()))
            register_file_controls(db,identifier,metadata['scan_status'])
            i['data'].update(_started_at=op.now(),_before_file=identifier,_initial_condition=notes)
            op.store_item(db,r['id'],'visit',i['data'],{'id':r['user_id']},i['id'])
            op.event(db,r,{'email':email.lower()},'technician.started',{'item_id':i['id'],'file_id':identifier},op.get_state(db,r['id']))
        return {'started_at':i['data']['_started_at']}

    @app.post('/api/contractor/{token}/report')
    async def report(token:str,file:UploadFile,notes:str=Form(min_length=5,max_length=10000),email:str=Form(),readings:str=Form(default='{}',max_length=20000)):
        with database(path) as db:access(db,token)
        content=await file.read(MAX_FILE+1);metadata=extract_file(file.filename or '',content)
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE');link,r,i=access(db,token);op.require(email.strip().lower()==link['recipient'],'Use the assigned contractor email')
            from .commercial import admit
            workspace=db.execute('SELECT workspace_id FROM record_workspaces WHERE record_id=?',(r['id'],)).fetchone()[0]
            admit(db,workspace,'source_bytes',len(content))
            identifier=op.uid();db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?)',(identifier,r['id'],metadata['name'],metadata['mime'],metadata['size'],metadata['checksum'],content,metadata['extracted'],metadata['extraction_status'],'external:'+email.lower(),op.now()))
            register_file_controls(db,identifier,metadata['scan_status'])
            if r['product']=='amc':
                op.require(i['data']['start']<=op.now(),'Cannot complete a future visit')
                try:values=json.loads(readings)
                except ValueError:op.fail('Readings must be a JSON object')
                checks={x.strip() for x in i['data']['checklist'].splitlines() if x.strip()}
                op.require(isinstance(values,dict) and set(values)==checks and all(isinstance(v,str) and 0<len(v.strip())<=1000 for v in values.values()),'Complete every service checklist reading')
                i['data'].update(_status='completed',_completed_by='external:'+email.lower(),_notes=notes,_file=identifier,_completed_at=op.now(),_readings=values)
            else:i['data'].update(_status='fixed',_fixed_by='external:'+email.lower(),_repair_note=notes,_repair_file=identifier)
            # The record owner is the internal custodian; external identity is retained separately.
            op.store_item(db,r['id'],'visit' if r['product']=='amc' else 'issue',i['data'],{'id':r['user_id']},i['id'])
            db.execute('UPDATE task_links SET closed_at=? WHERE id=?',(op.now(),link['id']))
            s=op.get_state(db,r['id'])
            if r['product']=='handover':s['stage']='draft';s['data'].pop('approved_document',None)
            op.event(db,r,{'email':email.lower()},'technician.service-reported' if r['product']=='amc' else 'contractor.repair-reported',{'item_id':i['id'],'file_id':identifier,'notes':notes},s)
        return {'recorded':True,'status':'Awaiting independent verification'}

    @app.delete('/api/contractor-links/{identifier}')
    def revoke(identifier:str,user=Depends(current_user)):
        permit(user,'owner','reviewer')
        with database(path) as db:
            link=db.execute('SELECT * FROM task_links WHERE id=?',(identifier,)).fetchone()
            if not link:raise HTTPException(404,'Link not found')
            record_access(db,link['record_id'],user);db.execute('UPDATE task_links SET closed_at=? WHERE id=?',(op.now(),identifier))
        return {'ok':True}
