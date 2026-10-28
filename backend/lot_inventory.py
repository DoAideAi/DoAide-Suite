"""Batch stock stays pending until Inventory commits; local rows are projections."""
from copy import deepcopy
import json
import os
import httpx
from . import operations as op
from .db import database
from .authority_adapters import authority, activate, supersede_failed
from .portfolio_connections import connection

ACTIONS={'receive_lots','reserve_materials','release_materials','produce','return_material','quality_release','quality_reject','recall','dispose_output','dispatch_batch','set_lot_quality','adjust_lot'}


def active(db,workspace):return authority(db,'INVENTORY_LOTS',workspace)


def local_apply(db,r,u,a,d,s,out):
    if a=='dispatch_batch':
        out['item_id']=op.resource(db,r,u,'dispatch',d,internal_authority=True)
        current=op.get_state(db,r['id']);s.update(current)
    elif a=='adjust_lot':
        row=op.stock_row(db,u,d['sku']);op.require(row and d['sku'].startswith('lot:'),'Choose an ingredient lot')
        op.require(op.decimal(row['quantity'])==op.decimal(d['expected_quantity']),'Stock changed; refresh before correcting')
        q=op.decimal(d['quantity']);meta=json.loads(row['data']);held=op.decimal(row['held']) if meta['quality']=='Released' else q
        op.require(q>=held,'Correction cannot consume reserved stock')
        delta=q-op.decimal(row['quantity']);op.require(delta!=0,'Correction must change the physical quantity')
        op.require(not db.execute('SELECT 1 FROM stock_adjustments WHERE workspace_id=? AND reference=?',(u['workspace_id'],d['reference'])).fetchone(),'Correction reference already exists')
        pending=db.execute("SELECT 1 FROM jobs WHERE workspace_id=? AND kind='inventory-lots' AND state NOT IN ('cancelled','delivered') AND json_extract(data,'$.action')='adjust_lot' AND json_extract(data,'$.input.reference')=?",(u['workspace_id'],d['reference'])).fetchone()
        op.require(not pending,'This correction reference has a pending Inventory command')
        identifier=op.uid()
        db.execute('INSERT INTO stock_adjustments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(identifier,u['workspace_id'],r['id'],d['sku'],d['reference'],str(delta),row['quantity'],str(q),row['held'],str(held),d['reason'],d['file_id'],u['email'],op.now()))
        out['adjustment_id']=identifier
        op.movement(db,r,u,d['sku'],q-op.decimal(row['quantity']),'count-adjustment','lot-adjust:'+d['reference'])
        db.execute('UPDATE stock SET quantity=?,held=?,updated_at=? WHERE workspace_id=? AND sku=?',(str(q),str(held),op.now(),u['workspace_id'],d['sku']))
    else:
        from .workflow_extensions import batch
        if not batch(db,r,u,a,d,s,out):op.batch_action(db,r,u,a,d,s,out)


def payload(db,r,u,a,d,s):
    p=json.loads(r['payload'])
    if a=='receive_lots':return {'lots':[x['data'] for x in op.items(db,r['id'],'lot')]}
    if a in ('reserve_materials','produce'):
        result={'usage':[x['data'] for x in op.items(db,r['id'],'usage')]}
        if a=='produce':result['output']={'sku':'finished:'+p['batch_number'],'name':p['product'],'quantity':p['produced_units'],'expiry':p['expiry'],'data':{'quality':'Quarantined','record_id':r['id'],'expiry':p['expiry']}}
        return result
    return d


def queue(db,r,u,s,data):
    config=connection('INVENTORY',u['workspace_id'],db.execute('PRAGMA database_list').fetchone()[2])
    op.require(type(config.get('warehouse_id')) is int,'Configure the Inventory warehouse ID')
    pinned=db.execute('SELECT scope FROM portfolio_authorities WHERE workspace_id=? AND service=?',(u['workspace_id'],'INVENTORY_LOTS')).fetchone()
    op.require(pinned and pinned[0]==op.dump({k:config.get(k) for k in ('business_id','warehouse_id')}) and active(db,u['workspace_id'])==config['url'].rstrip('/'),'Restore the activated lot authority mapping before continuing')
    data={**data,'endpoint':active(db,u['workspace_id']),'user_id':u['id'],'warehouse_id':config['warehouse_id'],'business_id':config['business_id']}
    job=op.enqueue(db,r,u,'inventory-lots',data,'inventory-lots:'+r['id']+':'+str(s['revision']))
    s['data']['authority_pending']=job
    return job


def execute(db,r,u,a,d,s,out):
    if r['product']!='batch':return False
    if a=='connect_lot_inventory':
        op.permit(u,'owner')
        if not active(db,u['workspace_id']):
            op.require(not db.execute("SELECT 1 FROM stock WHERE workspace_id=? AND (sku LIKE 'lot:%' OR sku LIKE 'finished:%')",(u['workspace_id'],)).fetchone(),'Reconcile existing local lot balances before activating Inventory; start acceptance in a clean workspace')
            config=activate(db,'INVENTORY',u)
            scope=op.dump({k:config.get(k) for k in ('business_id','warehouse_id')})
            db.execute('INSERT INTO portfolio_authorities VALUES (?,?,?,?,?)',(u['workspace_id'],'INVENTORY_LOTS',config['url'].rstrip('/'),op.now(),scope))
        out['authority']='DoAide Inventory lot ledger';return True
    if a not in ACTIONS|{'refresh_lots','reconcile_lots'}:return False
    if not active(db,u['workspace_id']):
        op.require(a not in ('refresh_lots','reconcile_lots'),'Activate the Inventory lot ledger first')
        if a in ('dispatch_batch','adjust_lot'):local_apply(db,r,u,a,d,s,out);return True
        return False
    if a=='reconcile_lots':
        pending=s['data'].get('authority_pending');op.require(pending,'No pending lot command to reconcile')
        prior=dict(db.execute('SELECT * FROM jobs WHERE id=?',(pending,)).fetchone());data=json.loads(prior['data'])
        op.require(data['action']!='refresh','Retry a failed refresh with Refresh Inventory lots')
        supersede_failed(db,pending)
        out['job_id']=queue(db,r,u,s,{**data,'reconcile':True});return True
    pending=s['data'].get('authority_pending')
    if pending and a=='refresh_lots':
        prior=json.loads(db.execute('SELECT data FROM jobs WHERE id=?',(pending,)).fetchone()[0]);op.require(prior['action']=='refresh','Reconcile the pending stock mutation first');supersede_failed(db,pending)
    else:op.require(not pending,'Resolve the pending Inventory command before making another change')
    if a=='refresh_lots':out['job_id']=queue(db,r,u,s,{'action':'refresh','original_stage':s['stage']});return True
    # Validate all Suite commercial/evidence rules without publishing any local stock or documents.
    db.execute('SAVEPOINT lot_preflight')
    try:local_apply(db,r,u,a,d,deepcopy(s),{})
    finally:db.execute('ROLLBACK TO SAVEPOINT lot_preflight');db.execute('RELEASE SAVEPOINT lot_preflight')
    reference='suite-lot-'+op.uid()
    out['job_id']=queue(db,r,u,s,{'action':a,'input':d,'payload':payload(db,r,u,a,d,s),'reference':reference,'original_stage':s['stage']})
    s['stage']='inventory-pending';return True


def deliver(job,path,transport=None):
    from .worker import Blocked
    if os.environ.get('DOAIDE_DELIVERY_MODE','disabled')!='enabled':raise Blocked('External connections are disabled')
    config=connection('INVENTORY',job['workspace_id'],path);d=job['data']
    if config['url'].rstrip('/')!=d['endpoint'] or any(config.get(k)!=d[k] for k in ('business_id','warehouse_id')):raise Blocked('Inventory authority mapping changed')
    with database(path) as db:
        s=op.get_state(db,job['record_id'])
        member=db.execute('SELECT role FROM memberships WHERE workspace_id=? AND user_id=?',(job['workspace_id'],d['user_id'])).fetchone()
        roles=op.SPECS['batch']['actions'][d['action'] if d['action']!='refresh' else 'refresh_lots']['roles']
        if s['data'].get('authority_pending')!=job['id'] or not member or member[0] not in roles:raise Blocked('Command superseded or requester lost operational access')
    headers={'Authorization':'Bearer '+config['token'],'X-DoAide-Business-ID':str(config['business_id'])}
    with httpx.Client(timeout=30,transport=transport,follow_redirects=False) as client:
        base=d['endpoint']+'/suite/lots'
        if d['action']=='refresh':
            rows=[]
            for skip in range(0,10000,200):
                response=client.get(base,params={'warehouse_id':d['warehouse_id'],'skip':skip,'limit':200},headers=headers);response.raise_for_status();part=response.json()
                if part.get('business_id')!=d['business_id'] or part.get('warehouse_id')!=d['warehouse_id'] or not isinstance(part.get('balances'),list):raise Blocked('Invalid Inventory lot response')
                rows.extend(part['balances'])
                if len(part['balances'])<200:break
            else:raise Blocked('Lot catalogue exceeds 10,000 rows')
            return {'status':'refreshed','balances':rows}
        if d.get('reconcile'):response=client.post(base+'/commands/'+d['reference']+'/reconcile',headers=headers)
        else:response=client.post(base+'/commands',headers=headers,json={'reference':d['reference'],'batch':'suite-'+job['record_id'],'warehouse_id':d['warehouse_id'],'action':d['action'],'data':d['payload']})
        if response.status_code in (400,401,403,404,409,410,422):raise Blocked('Inventory rejected the lot command ('+str(response.status_code)+'); reconcile before retrying')
        response.raise_for_status();result=response.json()
        if result.get('business_id')!=d['business_id'] or result.get('reference')!=d['reference']:raise Blocked('Inventory returned the wrong command receipt')
        if result.get('status')=='missing' and d.get('reconcile'):return result
        if result.get('status')!='committed' or result.get('action')!=d['action'] or result.get('batch')!='suite-'+job['record_id'] or result.get('warehouse_id')!=d['warehouse_id']:raise Blocked('Invalid Inventory lot receipt')
        return result


def project(db,u,rows):
    for sku,row in rows.items():
        op.require(isinstance(sku,str) and sku.startswith(('lot:','finished:')),'Invalid lot SKU')
        if row is None:db.execute('DELETE FROM stock WHERE workspace_id=? AND sku=?',(u['workspace_id'],sku));continue
        op.require(row['sku']==sku and 0<=op.decimal(row['held'])<=op.decimal(row['quantity']),'Invalid authoritative lot balance')
        db.execute('INSERT INTO stock VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(workspace_id,sku) DO UPDATE SET name=excluded.name,unit=excluded.unit,quantity=excluded.quantity,held=excluded.held,data=excluded.data,updated_at=excluded.updated_at',
            (u['workspace_id'],sku,row['name'],row['unit'],str(row['quantity']),str(row['held']),op.dump(row['data']),op.now()))


def complete(db,job,result):
    r=dict(db.execute('SELECT * FROM records WHERE id=?',(job['record_id'],)).fetchone());s=op.get_state(db,r['id']);d=job['data']
    op.require(s['data'].get('authority_pending')==job['id'],'Lot command was superseded')
    member=db.execute('SELECT u.id,u.email,m.role FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.workspace_id=? AND u.id=?',(job['workspace_id'],d['user_id'])).fetchone()
    op.require(member,'Requesting member no longer exists');u={**dict(member),'workspace_id':job['workspace_id']};out={}
    s['data'].pop('authority_pending');s['stage']=d['original_stage']
    db.execute('UPDATE operations SET stage=?,data=? WHERE record_id=?',(s['stage'],op.dump(s['data']),r['id']))
    if result['status']=='refreshed':
        rows={x['sku']:x for x in result['balances']};op.require(len(rows)==len(result['balances']),'Duplicate lot SKU');project(db,u,rows)
    elif result['status']=='committed':
        op.require(isinstance(result.get('before'),dict) and isinstance(result.get('after'),dict),'Lot receipt is missing balances')
        action=d['action'];payload=d['payload']
        if action=='receive_lots':expected={'lot:'+x['lot'] for x in payload['lots']}
        elif action=='reserve_materials':expected={'lot:'+x['lot'] for x in payload['usage']}
        elif action=='release_materials':expected=set(s['data'].get('material_reservations',{}))
        elif action=='produce':expected={'lot:'+x['lot'] for x in payload['usage']}|set(s['data'].get('material_reservations',{}))|{payload['output']['sku']}
        elif action=='return_material':expected={'lot:'+d['input']['lot']}
        elif action in ('adjust_lot','set_lot_quality'):expected={d['input']['sku']}
        else:expected={'finished:'+json.loads(r['payload'])['batch_number']}
        op.require(expected and set(result['before'])==set(result['after'])==expected,'Lot receipt omitted or added affected balances')
        project(db,u,result['before']);local_apply(db,r,u,d['action'],d['input'],s,out)
        for sku,row in result['after'].items():
            local=op.stock_row(db,u,sku)
            op.require(local and op.decimal(local['quantity'])==op.decimal(row['quantity']) and op.decimal(local['held'])==op.decimal(row['held']) and json.loads(local['data'])==row['data'],'Local projection differs from the committed Inventory receipt')
        project(db,u,result['after']);s['data'].setdefault('inventory_lot_receipts',{})[d['reference']]={'action':d['action'],'confirmed_at':op.now()}
    else:op.require(result['status']=='missing','Invalid reconciliation status')
    op.event(db,r,u,'inventory.lots.'+result['status'],{'action':d['action'],'reference':d.get('reference'),**out},s)
