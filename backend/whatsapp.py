"""Signed inbound WhatsApp orders. No outbound messages are sent by this adapter."""
import base64
import hashlib
import hmac
import json
import os
import re
import time
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException,Request,Response
from .db import database
from .commercial import admit
from .domain import calculate
from .documents import MAX_FILE,register_file_controls
from .recordings import audio_metadata
from . import operations as op


def channels():
    try:value=json.loads(os.environ.get('DOAIDE_WHATSAPP_CHANNELS','{}'))
    except ValueError:raise HTTPException(503,'WhatsApp channel mapping is invalid')
    if not isinstance(value,dict):raise HTTPException(503,'WhatsApp channel mapping is invalid')
    return value


def install_whatsapp(app,path):
    @app.get('/api/webhooks/whatsapp')
    def verify(request:Request):
        expected=os.environ.get('DOAIDE_META_VERIFY_TOKEN','')
        if not expected or request.query_params.get('hub.mode')!='subscribe' or not hmac.compare_digest(request.query_params.get('hub.verify_token',''),expected):raise HTTPException(403,'Webhook verification failed')
        return Response(request.query_params.get('hub.challenge',''),media_type='text/plain')

    @app.post('/api/webhooks/whatsapp')
    async def receive(request:Request):
        secret=os.environ.get('DOAIDE_META_APP_SECRET','');raw=await request.body()
        if not secret:raise HTTPException(503,'WhatsApp webhook is not configured')
        signature='sha256='+hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature,request.headers.get('x-hub-signature-256','')):raise HTTPException(401,'Invalid webhook signature')
        try:body=json.loads(raw)
        except ValueError:raise HTTPException(422,'Invalid webhook JSON')
        op.require(isinstance(body,dict) and body.get('object')=='whatsapp_business_account','Expected a WhatsApp business webhook')
        mapping=channels();created=[];seen=0
        op.require(isinstance(body.get('entry',[]),list),'Invalid webhook entries')
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            for entry in body.get('entry',[]):
                op.require(isinstance(entry,dict) and isinstance(entry.get('changes',[]),list),'Invalid webhook changes')
                for change in entry.get('changes',[]):
                    op.require(isinstance(change,dict),'Invalid webhook change')
                    if change.get('field')!='messages':continue
                    value=change.get('value',{});op.require(isinstance(value,dict),'Invalid message payload');messages=value.get('messages',[])
                    op.require(isinstance(messages,list) and isinstance(value.get('metadata',{}),dict),'Invalid message list')
                    if not messages:continue  # delivery status callbacks are not incoming orders
                    phone=value.get('metadata',{}).get('phone_number_id','');config=mapping.get(phone)
                    op.require(config and isinstance(config,dict),'Incoming phone number is not mapped to a workspace')
                    member=db.execute("SELECT u.id,u.email FROM memberships m JOIN users u ON m.user_id=u.id WHERE m.workspace_id=? AND m.user_id=? AND m.role='owner'",(config.get('workspace_id'),config.get('owner_id'))).fetchone()
                    op.require(member,'Configured channel owner is no longer a workspace owner')
                    user={**dict(member),'workspace_id':config['workspace_id'],'role':'owner'}
                    for message in messages:
                        op.require(isinstance(message,dict) and isinstance(message.get('text',{}),dict) and isinstance(message.get('audio',{}),dict),'Invalid message')
                        seen+=1;op.require(seen<=100,'Webhook contains too many messages')
                        identifier=message.get('id','');kind=message.get('type')
                        op.require(isinstance(identifier,str) and 1<=len(identifier)<=512,'Invalid message reference')
                        if db.execute('SELECT 1 FROM webhook_events WHERE provider=? AND event_id=?',('whatsapp:'+phone,identifier)).fetchone():continue
                        if kind not in ('text','audio'):continue
                        sender=message.get('from','');op.require(isinstance(sender,str) and re.fullmatch(r'[0-9]{5,20}',sender),'Invalid sender reference')
                        try:stamp=int(message.get('timestamp','0'))
                        except (ValueError,TypeError):op.fail('Invalid message timestamp')
                        op.require(0<stamp<=int(time.time())+300,'Incoming message time is invalid')
                        text=message.get('text',{}).get('body','') if kind=='text' else 'Voice recording awaiting transcription and human review'
                        op.require(isinstance(text,str) and 0<len(text)<=20000,'Incoming text is empty or too long')
                        catalogue=[]
                        for stock in db.execute("SELECT * FROM stock WHERE workspace_id=? AND sku NOT LIKE 'lot:%' AND sku NOT LIKE 'finished:%' ORDER BY sku LIMIT 200",(user['workspace_id'],)):
                            meta=json.loads(stock['data']);catalogue.append({'sku':stock['sku'],'name':stock['name'],'price':meta['price'],'stock':max(0,int(op.decimal(stock['quantity'])-op.decimal(stock['held'])))})
                        op.require(catalogue,'Publish the workspace catalogue before connecting incoming orders')
                        payload,_=calculate('orderdesk',{'customer':'WhatsApp '+sender,'order_text':text,'catalog':catalogue})
                        admit(db,user['workspace_id'],'records',product='orderdesk');rid=op.uid();ts=op.now()
                        db.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?)',(rid,user['id'],'orderdesk','WhatsApp order · '+sender,op.dump(payload),'draft',1,ts,ts))
                        db.execute('INSERT INTO record_workspaces VALUES (?,?)',(rid,user['workspace_id']))
                        db.execute('INSERT INTO audit_events(record_id,user_id,action,version,snapshot,created_at) VALUES (?,?,?,?,?,?)',(rid,user['id'],'whatsapp.received',1,op.dump(payload),ts))
                        record=dict(db.execute('SELECT * FROM records WHERE id=?',(rid,)).fetchone())
                        item_id=op.store_item(db,rid,'message',{'reference':identifier,'text':text,'file_id':'','_sender':sender,'_provider_timestamp':stamp},user)
                        if kind=='audio':
                            audio=message.get('audio',{});media=audio.get('id','');op.require(isinstance(media,str) and re.fullmatch(r'[0-9]{1,100}',media),'Invalid media ID')
                            op.enqueue(db,record,user,'whatsapp-media',{'media_id':media,'item_id':item_id,'phone_number_id':phone,'owner_id':user['id'],'sha256':audio.get('sha256','')},'whatsapp-media:'+identifier)
                        db.execute('INSERT INTO webhook_events VALUES (?,?,?)',('whatsapp:'+phone,identifier,ts));created.append(rid)
        return {'received':True,'records':created}


def deliver(job,path,transport=None):
    from .worker import Blocked
    token=os.environ.get('DOAIDE_META_ACCESS_TOKEN');version=os.environ.get('DOAIDE_META_GRAPH_VERSION','')
    if os.environ.get('DOAIDE_DELIVERY_MODE','disabled')!='enabled' or not token or not re.fullmatch(r'v[0-9]+\.[0-9]+',version):raise Blocked('Configure and enable the Meta media connection and Graph API version')
    config=channels().get(job['data']['phone_number_id'],{})
    if config.get('workspace_id')!=job['workspace_id'] or config.get('owner_id')!=job['data']['owner_id']:raise Blocked('Channel mapping changed; review the pending media job')
    with httpx.Client(timeout=45,transport=transport,follow_redirects=False) as client:
        metadata=client.get('https://graph.facebook.com/'+version+'/'+job['data']['media_id'],headers={'Authorization':'Bearer '+token},params={'phone_number_id':job['data']['phone_number_id']});metadata.raise_for_status();meta=metadata.json()
        url=meta.get('url','');parsed=urlparse(url)
        if parsed.scheme!='https' or parsed.hostname!='lookaside.fbsbx.com' or parsed.port not in (None,443) or parsed.username:raise Blocked('Meta returned an unsupported media download host')
        chunks=[];size=0
        with client.stream('GET',url,headers={'Authorization':'Bearer '+token}) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                size+=len(chunk)
                if size>MAX_FILE:raise Blocked('Incoming recording exceeds 10 MiB')
                chunks.append(chunk)
        content=b''.join(chunks)
    checksum=hashlib.sha256(content);expected=job['data'].get('sha256') or meta.get('sha256')
    if expected and expected not in (checksum.hexdigest(),base64.b64encode(checksum.digest()).decode()):raise Blocked('Incoming media checksum does not match the provider manifest')
    suffix={'audio/ogg':'.ogg','audio/mpeg':'.mp3','audio/mp4':'.m4a','audio/wav':'.wav'}.get(meta.get('mime_type','').split(';')[0])
    if not suffix:raise Blocked('Unsupported incoming audio format')
    file=audio_metadata('whatsapp-'+job['data']['media_id']+suffix,content)
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        record=db.execute('SELECT * FROM records WHERE id=?',(job['record_id'],)).fetchone()
        if not record or record['status']=='archived':raise Blocked('Order was archived or removed')
        item=op.one_item(db,job['record_id'],job['data']['item_id'],'message')
        if item['data'].get('file_id'):return {'file_id':item['data']['file_id'],'needs_transcription':True}
        admit(db,job['workspace_id'],'source_bytes',len(content));identifier=op.uid()
        db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?)',(identifier,job['record_id'],file['name'],file['mime'],file['size'],file['checksum'],content,'','recording-uploaded',job['data']['owner_id'],op.now()));register_file_controls(db,identifier,file['scan_status'])
        item['data']['file_id']=identifier;op.store_item(db,job['record_id'],'message',item['data'],{'id':job['data']['owner_id']},item['id'])
    return {'file_id':identifier,'needs_transcription':True}
