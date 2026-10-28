"""Notice milestones derived from current terms, with stale-delivery protection."""
import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from . import operations as op


def policy_days(policy):
    try:
        values=[int(v.strip()) for v in policy['days'].split(',')]
        assert 1<=len(values)<=12 and len(set(values))==len(values) and all(0<=v<=365 for v in values)
        assert int(policy['start_hour'])<int(policy['end_hour'])
    except (ValueError, AssertionError):op.fail('Use 1–12 distinct reminder offsets from 0 to 365 days and valid working hours')
    return sorted(values,reverse=True)


def basis(db,record):
    terms=op.items(db,record['id'],'terms');policies=op.items(db,record['id'],'reminder_policy')
    if not terms or not policies:return None
    workspace=db.execute('SELECT w.* FROM workspaces w JOIN record_workspaces r ON r.workspace_id=w.id WHERE r.record_id=?',(record['id'],)).fetchone()
    p=json.loads(record['payload'])
    return {'terms':terms[0]['data'],'policy':policies[0]['data'],'notice':op.notice_date(record,terms),
            'renewal':p['renewal'],'vendor':p['vendor'],'service':p['service'],'timezone':workspace['timezone']}


def delivery_blocker(db,record,data):
    state=op.get_state(db,record['id'])
    if state['stage'] in ('vendor-confirmed','completed'):return 'Renewal action is complete'
    terms=op.items(db,record['id'],'terms')
    if not terms or data['recipient'] not in (terms[0]['data']['owner'],terms[0]['data']['backup']):return 'Responsible owners changed'
    if data.get('renewal_plan'):
        current=basis(db,record)
        if not current or current['policy']['consent']!='Yes' or op.digest(current)!=data['renewal_plan']:return 'Renewal terms or reminder policy changed'
        plan=state['data'].get('renewal_plan',{})
        if plan.get('fingerprint')!=data['renewal_plan']:return 'Reminder plan was replaced'
        if plan.get('acknowledged_at'):return 'Responsible owner acknowledged this notice plan'
    return None


def plan(db,record,user,state):
    current=basis(db,record)
    op.require(current,'Add contract terms and a notice reminder policy first')
    policy=current['policy'];offsets=policy_days(policy)
    op.require(policy['consent']=='Yes','Owners must allow email reminders')
    op.require(state['stage'] not in ('vendor-confirmed','completed'),'This renewal action is already complete')
    fingerprint=op.digest(current)
    prior=state['data'].get('renewal_plan',{})
    if prior.get('fingerprint')==fingerprint:return prior
    db.execute("UPDATE jobs SET state='cancelled',last_error='Replaced by changed renewal terms' WHERE record_id=? AND dedupe_key LIKE 'renewal:%' AND state IN ('queued','failed','blocked','dead-letter')",(record['id'],))
    tz=ZoneInfo(current['timezone']);local=datetime.now(tz);notice=date.fromisoformat(current['notice'])
    dates=[];missed=[]
    for offset in offsets:
        scheduled=datetime.combine(notice-timedelta(days=offset),datetime.min.time(),tzinfo=tz).replace(hour=int(policy['start_hour']))
        while scheduled.weekday()>=5:scheduled-=timedelta(days=1)
        if scheduled<=local:missed.append(offset)
        else:dates.append(scheduled)
    if missed:
        catchup=local.replace(hour=int(policy['start_hour']),minute=0,second=0,microsecond=0)
        if catchup<=local:catchup+=timedelta(days=1)
        while catchup.weekday()>=5:catchup+=timedelta(days=1)
        dates.append(catchup)
    dates=sorted(set(dates));job_ids=[]
    for scheduled in dates:
        for recipient,at,escalation in ((current['terms']['owner'],scheduled,False),(current['terms']['backup'],scheduled+timedelta(days=int(policy['escalate_after'])),True)):
            while at.weekday()>=5:at+=timedelta(days=1)
            data={'recipient':recipient,'subject':('Backup review: ' if escalation else 'Renewal notice: ')+current['service'],
                  'message':f"{current['vendor']} / {current['service']}: notice deadline {current['notice']}; renewal {current['renewal']}. Review the recorded terms and acknowledge responsibility in DoAide Renew.",
                  'start_hour':policy['start_hour'],'end_hour':policy['end_hour'],'consent':'Yes',
                  'renewal_plan':fingerprint,'escalation':escalation}
            key='renewal:'+fingerprint+':'+op.digest({'recipient':recipient,'at':at.isoformat(),'escalation':escalation})
            job_ids.append(op.enqueue(db,record,user,'email',data,key,at.astimezone(timezone.utc).isoformat()))
    result={'fingerprint':fingerprint,'notice_date':current['notice'],'job_ids':job_ids,'missed_offsets':missed,'created_at':op.now()}
    state['data']['renewal_plan']=result
    return result


def renewal_command(db,record,user,action,state,result):
    if action=='plan_reminders':result.update(plan(db,record,user,state))
    else:
        current=basis(db,record);stored=state['data'].get('renewal_plan',{})
        op.require(current and stored.get('fingerprint')==op.digest(current),'Schedule the current notice plan before acknowledging')
        op.require(user['email'] in (current['terms']['owner'],current['terms']['backup']),'Only the named owner or backup can acknowledge responsibility')
        op.require(not stored.get('acknowledged_at'),'This notice plan was already acknowledged')
        stored.update(acknowledged_at=op.now(),acknowledged_by=user['email'])
        db.execute("UPDATE jobs SET state='cancelled',last_error='Notice acknowledged by responsible owner' WHERE record_id=? AND dedupe_key LIKE 'renewal:%' AND state IN ('queued','failed','blocked','dead-letter')",(record['id'],))
        result.update(acknowledged_at=stored['acknowledged_at'])


def refresh(db,record,user):
    state=op.get_state(db,record['id']);prior=state['data'].get('renewal_plan')
    if not prior or state['stage'] in ('vendor-confirmed','completed') or record['status']=='archived':return
    current=basis(db,record)
    if current and op.digest(current)==prior.get('fingerprint'):return
    db.execute("UPDATE jobs SET state='cancelled',last_error='Renewal terms or consent changed' WHERE record_id=? AND dedupe_key LIKE 'renewal:%' AND state IN ('queued','failed','blocked','dead-letter')",(record['id'],))
    if current and current['policy']['consent']=='Yes':
        db.execute('SAVEPOINT renewal_replan')
        try:plan(db,record,user,state)
        except HTTPException as exc:
            if exc.status_code!=402:raise
            db.execute('ROLLBACK TO renewal_replan')
            state['data']['renewal_plan']={'invalidated_at':op.now(),'reason':'Job budget reached. Schedule the milestones after reviewing the plan.'}
        finally:db.execute('RELEASE renewal_replan')
    else:state['data']['renewal_plan']={'invalidated_at':op.now(),'reason':'Terms or consent missing'}
    op.event(db,record,user,'renewal.plan-recomputed',state['data']['renewal_plan'],state)
