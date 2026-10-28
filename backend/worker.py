"""Durable outbox worker. Default delivery mode is disabled; OCR is always local.
Run `uv run python -m backend.worker` separately from the HTTP process.
"""
import argparse
import json
import os
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import httpx
from .db import database, initialize
from .operations import now, dump, reminder_blocker, financial, get_state, event
from .documents import ocr_file


class Blocked(Exception):pass


def claim(path=None):
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        timestamp=now()
        db.execute("INSERT INTO runtime_status VALUES ('worker',?) ON CONFLICT(name) DO UPDATE SET last_seen=excluded.last_seen",(timestamp,))
        from .billing import periodic
        periodic(db)
        from .workflow_extensions import periodic as product_periodic
        product_periodic(db)
        db.execute("UPDATE jobs SET state='blocked',last_error='Worker stopped during email delivery; reconcile SMTP logs before retry',lease_until=NULL WHERE state='running' AND lease_until<? AND kind IN ('email','auth-email')",(timestamp,))
        row=db.execute("""SELECT j.* FROM jobs j WHERE
            ((j.state IN ('queued','failed') AND j.due_at<=?) OR (j.state='running' AND j.lease_until<?))
            AND (j.kind NOT LIKE 'billing-%' OR NOT EXISTS (
                SELECT 1 FROM jobs busy WHERE busy.workspace_id=j.workspace_id AND busy.id!=j.id
                AND busy.kind LIKE 'billing-%' AND busy.state='running' AND busy.lease_until>=?))
            ORDER BY j.due_at LIMIT 1""",(timestamp,timestamp,timestamp)).fetchone()
        if not row:return None
        lease=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()
        db.execute("UPDATE jobs SET state='running',attempts=attempts+1,lease_until=?,updated_at=? WHERE id=?",(lease,timestamp,row['id']))
        job=dict(row);job['attempts']+=1;job['data']=json.loads(job['data']);return job


def deliver(job,path=None,transport=None):
    data=job['data'];kind=job['kind']
    if kind in ('inventory-command','scheduler-command'):
        from .authority_adapters import deliver as authority_deliver
        return authority_deliver(job,path,transport)
    if kind=='contracts-import':
        from .portfolio_connections import import_contract
        return import_contract(job,path,transport)
    if kind=='transcribe':
        from .recordings import deliver as transcribe
        return transcribe(job,path,transport)
    if kind=='whatsapp-media':
        from .whatsapp import deliver as media
        return media(job,path,transport)
    if kind.startswith('billing-'):
        from .billing import deliver as deliver_billing
        return deliver_billing(job,path,transport)
    if kind=='ocr':
        with database(path) as db:file=dict(db.execute('SELECT * FROM files WHERE id=?',(data['file_id'],)).fetchone())
        extracted=ocr_file(file)
        if not extracted:raise Blocked('OCR found no text; supply a readable source')
        with database(path) as db:db.execute("UPDATE files SET extracted=?,extraction_status='ocr-needs-review' WHERE id=?",(extracted,file['id']))
        return {'extracted_characters':len(extracted)}
    if kind=='auth-email':
        with database(path) as db:
            active=db.execute('SELECT 1 FROM auth_tokens WHERE token_hash=? AND expires_at>? AND used_at IS NULL',(data['token_hash'],int(time.time()))).fetchone()
        if not active:raise Blocked('Authentication link was used, expired or replaced; request a fresh link')
        if int(data['expires_at'])<=int(time.time()):raise Blocked('Authentication link expired; request a fresh link')
        if os.environ.get('DOAIDE_DELIVERY_MODE','disabled')!='enabled':raise Blocked('Email delivery is disabled; configure the provider before retry')
        return smtp_send(job,data)
    with database(path) as db:
        record=dict(db.execute('SELECT * FROM records WHERE id=?',(job['record_id'],)).fetchone())
        tz=db.execute('SELECT timezone FROM workspaces WHERE id=?',(job['workspace_id'],)).fetchone()[0]
        if kind in ('email','payment-link'):
            blocker=reminder_blocker(db,record)
            if blocker:raise Blocked(blocker)
        if kind=='email' and record['product']=='fees':
            guardians=[json.loads(r[0]) for r in db.execute("SELECT data FROM operation_items WHERE record_id=? AND kind='guardian'",(record['id'],))]
            if not any(g['email']==data['recipient'] and g['reminders']=='Yes' for g in guardians):raise Blocked('Guardian consent no longer permits this reminder')
        if kind=='email' and record['product']=='collect':
            from .workflow_extensions import contact_blocker
            blocker=contact_blocker(db,record,data,exclude=job['id'])
            if blocker:raise Blocked(blocker)
        if kind=='email' and record['product']=='renew':
            from .renewals import delivery_blocker
            blocker=delivery_blocker(db,record,data)
            if blocker:raise Blocked(blocker)
        if kind=='email' and record['product']=='sop':
            from .workflow_extensions import training_blocker
            blocker=training_blocker(db,record,data)
            if blocker:raise Blocked(blocker)
        if kind=='payment-link' and financial(db,record)['balance_paise']!=data['amount']:raise Blocked('Balance changed; request a fresh payment link')
    if os.environ.get('DOAIDE_DELIVERY_MODE','disabled')!='enabled':raise Blocked('External delivery is disabled. Configure the provider, then enable delivery and retry.')
    if kind=='email':
        local=datetime.now(ZoneInfo(tz))
        if local.weekday()>=5 or not int(data['start_hour'])<=local.hour<int(data['end_hour']):
            next_time=local.replace(hour=int(data['start_hour']),minute=0,second=0,microsecond=0)
            if next_time<=local:next_time+=timedelta(days=1)
            while next_time.weekday()>=5:next_time+=timedelta(days=1)
            return {'reschedule_at':next_time.astimezone(timezone.utc).isoformat()}
        return smtp_send(job,data)
    if kind=='payment-link':
        key=os.environ.get('RAZORPAY_KEY_ID');secret=os.environ.get('RAZORPAY_KEY_SECRET')
        if not key or not secret or not os.environ.get('RAZORPAY_WEBHOOK_SECRET'):raise Blocked('Payment gateway and webhook credentials are not configured')
        with httpx.Client(timeout=30,transport=transport) as client:
            # Razorpay reference_id is unique: reconcile before retrying a potentially successful POST.
            existing=client.get('https://api.razorpay.com/v1/payment_links',params={'reference_id':job['id']},auth=(key,secret));existing.raise_for_status()
            matches=[x for x in existing.json().get('payment_links',[]) if x.get('reference_id')==job['id']]
            if matches:return {'provider':matches[0]}
            response=client.post('https://api.razorpay.com/v1/payment_links',auth=(key,secret),json={'amount':data['amount'],'currency':data['currency'],'accept_partial':True,'reference_id':job['id'],'description':'DoAide invoice payment','customer':{'email':data['email']},'notify':{'sms':False,'email':False},'reminder_enable':False,'notes':{'doaide_job_id':job['id'],'doaide_record_id':job['record_id']}})
            response.raise_for_status();return {'provider':response.json()}
    if kind=='invoice':
        from .portfolio_connections import connection
        config=connection('INVOICE',job['workspace_id'],path);url,token=config['url'],config['token']
        with database(path) as db:doc=dict(db.execute('SELECT * FROM documents WHERE id=?',(data['document_id'],)).fetchone())
        with httpx.Client(timeout=30,transport=transport) as client:
            response=client.post(url,headers={'Authorization':'Bearer '+token,'Idempotency-Key':job['id']},json={'source':'doaide-'+record['product'],'document':{**doc,'snapshot':json.loads(doc['snapshot'])}})
            response.raise_for_status();result=response.json()
            if not result.get('invoice_id'):raise Blocked('Adapter response has no invoice_id; reconcile before retry')
            return {'invoice_id':result['invoice_id']}
    raise Blocked('No delivery adapter for '+kind)


def smtp_send(job,data):
    host=os.environ.get('DOAIDE_SMTP_HOST');sender=os.environ.get('DOAIDE_SMTP_FROM')
    if not host or not sender:raise Blocked('SMTP host and sender are not configured')
    message=EmailMessage();message['From']=sender;message['To']=data['recipient'];message['Subject']=data['subject'];message['Message-ID']=f'<{job["id"]}@doaide>';message.set_content(data['message'])
    with smtplib.SMTP(host,int(os.environ.get('DOAIDE_SMTP_PORT','587')),timeout=30) as smtp:
        smtp.ehlo()
        if os.environ.get('DOAIDE_SMTP_TLS','true')=='true':smtp.starttls();smtp.ehlo()
        if os.environ.get('DOAIDE_SMTP_USER'):smtp.login(os.environ['DOAIDE_SMTP_USER'],os.environ['DOAIDE_SMTP_PASSWORD'])
        smtp.send_message(message)
    return {'accepted_by_smtp':True,'message_id':message['Message-ID']}


def run_once(path=None,transport=None):
    job=claim(path)
    if not job:return None
    try:
        result=deliver(job,path,transport)
        if result.get('reschedule_at'):state='queued';due=result['reschedule_at']
        else:state='delivered';due=job['due_at']
        error=None
    except Blocked as exc:state='blocked';error=str(exc);result={};due=job['due_at']
    except Exception as exc:
        # SMTP can accept a message immediately before a network timeout. Do not
        # blindly retry ambiguous email deliveries and send duplicate reminders.
        state='blocked' if job['kind'] in ('email','auth-email') else 'dead-letter' if job['attempts']>=5 else 'failed'
        error=f'{type(exc).__name__}: delivery failed; inspect provider logs before retrying' if job['kind']=='email' else f'{type(exc).__name__}: provider or extraction failed'
        result={};due=(datetime.now(timezone.utc)+timedelta(seconds=min(3600,30*2**job['attempts']))).isoformat()
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        applied=db.execute("UPDATE jobs SET state=?,data=?,due_at=?,lease_until=NULL,last_error=?,updated_at=? WHERE id=? AND state='running' AND attempts=?",(state,dump({**job['data'],'result':result}),due,error,now(),job['id'],job['attempts'])).rowcount
        if not applied:return {'id':job['id'],'state':'superseded','error':'Worker lease no longer owns this job'}
        if state=='delivered' and job['kind'] in ('inventory-command','scheduler-command'):
            from .authority_adapters import complete
            db.execute('SAVEPOINT authority_result')
            try:
                complete(db,job,result)
                db.execute('RELEASE SAVEPOINT authority_result')
            except Exception:
                db.execute('ROLLBACK TO SAVEPOINT authority_result')
                db.execute('RELEASE SAVEPOINT authority_result')
                state='blocked';error='Authority result failed validation; reconcile before retrying'
                db.execute("UPDATE jobs SET state='blocked',last_error=? WHERE id=?",(error,job['id']))
        if state=='delivered' and job['kind']=='invoice':
            record=dict(db.execute('SELECT * FROM records WHERE id=?',(job['record_id'],)).fetchone());workflow=get_state(db,record['id'])
            workflow['data'].setdefault('external_invoices',{})[job['data']['document_id']]=result['invoice_id']
            if record['product']=='scope':workflow['stage']='invoiced'
            event(db,record,{'email':'invoice-adapter'},'invoice.created',result,workflow)
    return {'id':job['id'],'state':state,'error':error}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args();initialize()
    while True:
        result=run_once()
        if result:print(json.dumps(result),flush=True)
        if args.once:return
        if result is None:time.sleep(2)


if __name__=='__main__':main()
