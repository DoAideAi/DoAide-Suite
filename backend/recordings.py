"""Explicit, server-side Groq transcription with retained source and human review."""
import hashlib
import io
import json
import os
import wave
from pathlib import Path

import httpx
from fastapi import Depends, UploadFile
from pydantic import BaseModel, ConfigDict
from .db import database
from .migrations import permit,record_access
from .documents import MAX_FILE,MAX_TEXT,malware_screen,register_file_controls
from .commercial import admit
from . import operations as op


def audio_metadata(name,content):
    op.require(content and len(content)<=MAX_FILE,'Upload a recording up to 10 MiB')
    filename=Path(name.replace('\\','/')).name[:180];suffix=Path(filename).suffix.lower()
    mime={'.wav':'audio/wav','.ogg':'audio/ogg','.mp3':'audio/mpeg','.m4a':'audio/mp4'}.get(suffix)
    op.require(mime,'Supported recordings: WAV, OGG, MP3 and M4A')
    if suffix=='.wav':
        try:
            with wave.open(io.BytesIO(content)) as recording:
                seconds=recording.getnframes()/recording.getframerate()
                op.require(0<seconds<=600,'WAV recordings must be between zero and ten minutes')
        except (wave.Error,EOFError,ZeroDivisionError):op.fail('Upload a valid WAV recording')
    elif suffix=='.ogg':op.require(content.startswith(b'OggS'),'Invalid OGG header')
    elif suffix=='.mp3':op.require(content.startswith(b'ID3') or (len(content)>1 and content[0]==255 and content[1]&224==224),'Invalid MP3 header')
    else:op.require(len(content)>12 and content[4:8]==b'ftyp','Invalid M4A header')
    return {'name':filename,'mime':mime,'size':len(content),'checksum':hashlib.sha256(content).hexdigest(),'scan_status':malware_screen(content)}


class Transcribe(BaseModel):
    model_config=ConfigDict(extra='forbid')
    provider_consent:bool


def install_recordings(app,path,current_user):
    @app.post('/api/records/{record_id}/recordings',status_code=201)
    async def upload(record_id:str,file:UploadFile,user=Depends(current_user)):
        permit(user,'owner','operator','reviewer')
        with database(path) as db:
            r=record_access(db,record_id,user);op.require(r['product'] in ('orderdesk','sop'),'Recordings belong to OrderDesk or SOP')
        content=await file.read(MAX_FILE+1);meta=audio_metadata(file.filename or '',content)
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE');r=record_access(db,record_id,user);op.require(r['status']!='archived','Restore the record first')
            admit(db,user['workspace_id'],'source_bytes',len(content));identifier=op.uid()
            db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?)',(identifier,record_id,meta['name'],meta['mime'],meta['size'],meta['checksum'],content,'','recording-uploaded',user['id'],op.now()))
            register_file_controls(db,identifier,meta['scan_status'])
            state=op.get_state(db,record_id);op.event(db,r,user,'recording.uploaded',{'file_id':identifier},state)
        return {'id':identifier}

    @app.post('/api/files/{file_id}/transcribe',status_code=202)
    def transcribe(file_id:str,body:Transcribe,user=Depends(current_user)):
        permit(user,'owner','operator','reviewer');op.require(body.provider_consent,'Confirm permission to send this recording to the configured Groq transcription provider')
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM files WHERE id=?',(file_id,)).fetchone()
            op.require(row,'Recording not found');r=record_access(db,row['record_id'],user)
            op.require(r['product'] in ('orderdesk','sop') and row['mime'].startswith('audio/') and row['content'],'Choose an available recording')
            op.require(r['status']!='archived','Restore the record first')
            identifier=op.enqueue(db,r,user,'transcribe',{'file_id':file_id,'checksum':row['checksum'],'provider_consent_by':user['email']},'transcribe:'+file_id+':'+row['checksum'])
            return {'job_id':identifier}


def deliver(job,path,transport=None):
    from .worker import Blocked
    key=os.environ.get('DOAIDE_GROQ_TRANSCRIPTION_KEY')
    if os.environ.get('DOAIDE_DELIVERY_MODE','disabled')!='enabled' or not key:raise Blocked('Groq transcription is not enabled or configured')
    with database(path) as db:
        record=db.execute('SELECT status FROM records WHERE id=?',(job['record_id'],)).fetchone()
        if not record or record['status']=='archived':raise Blocked('Recording belongs to an archived or removed record')
        row=db.execute('SELECT * FROM files WHERE id=? AND record_id=?',(job['data']['file_id'],job['record_id'])).fetchone()
        if not row or not row['content'] or row['checksum']!=job['data']['checksum']:raise Blocked('Recording was removed or changed')
        file=dict(row)
    with httpx.Client(timeout=90,transport=transport) as client:
        response=client.post('https://api.groq.com/openai/v1/audio/transcriptions',headers={'Authorization':'Bearer '+key},files={'file':(file['name'],file['content'],file['mime'])},data={'model':'whisper-large-v3-turbo','response_format':'verbose_json','temperature':'0'})
        response.raise_for_status();result=response.json()
    if not isinstance(result,dict) or not isinstance(result.get('text'),str) or not result['text'].strip():raise Blocked('Transcription returned no reviewable text')
    if result.get('duration',0)>600:raise Blocked('Recording exceeds ten minutes; split it into shorter recordings')
    segments=result.get('segments') or []
    text='\n'.join(f'[{float(x["start"]):.2f}s–{float(x["end"]):.2f}s] {x["text"].strip()}' for x in segments) if segments else result['text']
    if len(text)>MAX_TEXT:raise Blocked('Transcript exceeds the supported length')
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        changed=db.execute("UPDATE files SET extracted=?,extraction_status='transcribed-needs-review' WHERE id=? AND checksum=? AND length(content)>0",(text,file['id'],file['checksum'])).rowcount
        if not changed:raise Blocked('Recording was removed while transcription was in progress')
    return {'file_id':file['id'],'characters':len(text),'needs_human_review':True,'provider':'Groq'}
