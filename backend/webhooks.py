"""Signed, replay-safe Razorpay payment-link reconciliation."""
import hashlib
import hmac
import json
import os
from fastapi import HTTPException, Request
from .db import database
from .operations import now, uid, dump, get_state, event, financial, cents, snapshot


def install_webhooks(app,path):
    @app.post('/api/webhooks/razorpay')
    async def razorpay(request:Request):
        secret=os.environ.get('RAZORPAY_WEBHOOK_SECRET')
        if not secret:raise HTTPException(503,'Payment webhook is not configured')
        raw=await request.body()
        if len(raw)>512000:raise HTTPException(413,'Webhook is too large')
        signature=request.headers.get('X-Razorpay-Signature','');expected=hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature,expected):raise HTTPException(401,'Invalid webhook signature')
        event_id=request.headers.get('X-Razorpay-Event-Id')
        if not event_id:raise HTTPException(422,'Provider event ID is required')
        try:data=json.loads(raw)
        except ValueError:raise HTTPException(422,'Invalid webhook body')
        if data.get('event') not in ('payment_link.paid','payment_link.partially_paid'):return {'ignored':True}
        try:
            link=data['payload']['payment_link']['entity'];payment=data['payload']['payment']['entity'];job_id=link['reference_id'];payment_id=payment['id'];value=payment['amount']
        except (KeyError,TypeError):raise HTTPException(422,'Payment-link and payment entities are required')
        if type(value) is not int or value<=0 or payment.get('currency')!='INR' or payment.get('status')!='captured':raise HTTPException(422,'Expected a captured INR payment in integer paise')
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM webhook_events WHERE provider=? AND event_id=?',('razorpay',event_id)).fetchone():return {'duplicate':True}
            job=db.execute("SELECT * FROM jobs WHERE id=? AND kind='payment-link'",(job_id,)).fetchone()
            if not job:raise HTTPException(404,'Payment link does not belong to this application')
            details=json.loads(job['data']);record=dict(db.execute('SELECT * FROM records WHERE id=?',(job['record_id'],)).fetchone())
            if link.get('amount')!=details['amount'] or link.get('currency')!='INR':raise HTTPException(422,'Payment-link amount or currency mismatch')
            provider=details.get('result',{}).get('provider',{})
            if provider.get('id') and provider['id']!=link.get('id'):raise HTTPException(422,'Payment-link identity mismatch')
            reference='razorpay:'+payment_id
            existing=db.execute('SELECT * FROM ledger WHERE workspace_id=? AND reference=?',(job['workspace_id'],reference)).fetchone()
            if existing:
                if existing['record_id']!=record['id'] or existing['amount']!=value:raise HTTPException(409,'Payment reference conflicts with an existing receipt')
            else:
                if any(p['payment_id']==payment_id for p in details.get('unallocated_payments',[])):
                    db.execute('INSERT INTO webhook_events VALUES (?,?,?)',('razorpay',event_id,now()))
                    return {'duplicate':True,'unallocated':True}
                balance=financial(db,record)['balance_paise']
                if value>balance:
                    db.execute("UPDATE jobs SET state='blocked',last_error=? WHERE id=?",('Captured payment exceeds outstanding balance; manual allocation required',job_id))
                    # Acknowledge and preserve the full payment for reconciliation; never discard it.
                    pending={'event_id':event_id,'payment_id':payment_id,'amount':value,'record_id':record['id']}
                    details.setdefault('unallocated_payments',[]).append(pending);db.execute('UPDATE jobs SET data=? WHERE id=?',(dump(details),job_id))
                else:
                    entry_id=uid();db.execute('INSERT INTO ledger VALUES (?,?,?,?,?,?,?,?,?,?,?)',(entry_id,job['workspace_id'],record['id'],'payment',value,reference,'INR',now()[:10],'Verified signed gateway callback','razorpay',now()))
                    s=get_state(db,record['id']);doc=snapshot(db,record,{'email':'razorpay'},'receipt',s,{'entry_id':entry_id})
                    event(db,record,{'email':'razorpay'},'payment.reconciled',{'payment_id':payment_id,'amount_paise':value,'document_id':doc},s)
            db.execute('INSERT INTO webhook_events VALUES (?,?,?)',('razorpay',event_id,now()))
        return {'received':True}
