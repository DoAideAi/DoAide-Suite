"""AMC parts reserve and consume in the owning Inventory service."""
from datetime import datetime,timedelta,timezone
import json
from . import operations as op
from .authority_adapters import authority,queue,supersede_failed


def execute(db,r,u,a,d,s,out):
    if r['product']!='amc':return False
    if a=='inventory_refresh':
        from .authority_adapters import execute as inventory_execute
        return inventory_execute(db,{**r,'product':'orderdesk'},u,a,d,s,out)
    if a not in ('reserve_parts','consume_parts','release_parts','reconcile_parts'):return False
    op.require(authority(db,'INVENTORY',u['workspace_id']),'Activate and refresh Inventory first')
    visit=op.one_item(db,r['id'],d['item_id'],'visit');vid=visit['id']
    info=s['data'].setdefault('parts_receipts',{}).get(vid,{})
    if a=='reconcile_parts':
        op.require(info.get('reference'),'No parts reservation exists')
        pending=s['data'].get('authority_pending')
        if pending:
            queued=json.loads(db.execute('SELECT data FROM jobs WHERE id=?',(pending,)).fetchone()[0])
            op.require(queued.get('parts_visit_id')==vid,'Reconcile the visit with the pending command first')
        supersede_failed(db,pending)
    else:op.require(not s['data'].get('authority_pending'),'Resolve the pending parts command first')
    if a=='reserve_parts':
        op.require(vid not in s['data'].get('billed_visits',{}),'This visit is already billed')
        op.require(info.get('status') not in ('reserved','dispatched','pending'),'Parts are already committed')
        op.require(visit['data'].get('_status','scheduled') in ('scheduled','completed','verified'),'Resolve this appointment first')
        parts=[x for x in op.items(db,r['id'],'part') if x['data']['visit_id']==vid];op.require(parts,'Add the parts used by this visit')
        lines=[]
        for part in parts:
            stock=op.stock_row(db,u,part['data'].get('sku',''));source=json.loads(stock['data']).get('_inventory') if stock else None
            op.require(source,'Map each part to a current Inventory SKU')
            q=op.decimal(part['data']['quantity']);op.require(q>0 and q==int(q),'Connected Inventory parts use whole catalogue units')
            lines.append({'product_id':source['product_id'],'warehouse_id':source['warehouse_id'],'quantity':int(q),'unit':source['unit']})
        # Aggregate repeated parts so the service receives one line per product/location.
        merged={}
        for line in lines:
            key=(line['product_id'],line['warehouse_id'])
            if key in merged:merged[key]['quantity']+=line['quantity']
            else:merged[key]=dict(line)
        info={'reference':'suite-parts-'+op.uid(),'status':'pending','part_ids':[x['id'] for x in parts],'lines':list(merged.values())}
        payload={'reference':info['reference'],'expires_at':(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(),'lines':info['lines']};command='reserve'
        s['data']['parts_receipts'][vid]=info
    else:
        op.require(info.get('reference'),'Reserve the parts first')
        if a=='consume_parts':
            op.require(info.get('status')=='reserved','Reserve parts before consumption')
            op.require(visit['data'].get('_status') in ('completed','verified'),'Record service completion before consuming parts')
        if a=='release_parts':op.require(info.get('status')=='reserved','Only an active reservation can be released')
        command={'consume_parts':'dispatch','release_parts':'cancel','reconcile_parts':'status'}[a]
        payload={'reference':info['reference']}
    job=queue(db,r,u,'INVENTORY',command,payload,s)
    row=db.execute('SELECT data FROM jobs WHERE id=?',(job,)).fetchone();jobdata={**json.loads(row[0]),'parts_visit_id':vid}
    db.execute("UPDATE jobs SET kind='inventory-parts',data=? WHERE id=?",(op.dump(jobdata),job))
    out['job_id']=job;return True


def guard_resource(db,r,u,kind,existing,raw):
    if r['product']!='amc' or kind!='part':return
    state=op.get_state(db,r['id'])
    ids={raw.get('visit_id')}
    if existing:ids.add(existing['data']['visit_id'])
    for vid in ids:
        info=state['data'].get('parts_receipts',{}).get(vid,{})
        op.require(info.get('status') not in ('pending','reserved','dispatched'),'Committed parts are immutable; release an unused reservation before editing')


def complete(db,job,result):
    r=dict(db.execute('SELECT * FROM records WHERE id=?',(job['record_id'],)).fetchone());s=op.get_state(db,r['id']);d=job['data']
    op.require(s['data'].get('authority_pending')==job['id'],'Parts command was superseded')
    info=s['data']['parts_receipts'][d['parts_visit_id']]
    if result['status']!='missing':
        def lines(values):return sorted((x['product_id'],x['warehouse_id'],x['quantity']) for x in values)
        op.require(lines(result.get('lines',[]))==lines(info['lines']),'Inventory receipt differs from the approved parts')
    info.update(status=result['status'],receipt=result,confirmed_at=op.now())
    s['data'].pop('authority_pending',None)
    u={'id':d['user_id'],'email':'inventory-adapter','workspace_id':job['workspace_id']}
    op.event(db,r,u,'inventory.parts.'+result['status'],{'visit_id':d['parts_visit_id'],'reference':info['reference']},s)
