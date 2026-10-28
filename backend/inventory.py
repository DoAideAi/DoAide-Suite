"""Audited physical-count corrections; original dispatch/production evidence stays frozen."""
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .db import database
from .migrations import record_access, permit
from .domain import validate_fields, decimal
from .catalog import money
from . import operations as op


class Adjustment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    record_id:str
    sku:str=Field(max_length=200)
    reference:str=Field(min_length=1,max_length=120)
    delta:str=Field(max_length=40)
    expected_quantity:str=Field(max_length=40)
    expected_held:str=Field(max_length=40)
    reason:str=Field(min_length=5,max_length=2000)
    file_id:str


def install_inventory(app,path,current_user):
    @app.post('/api/inventory/adjustments')
    def adjust(body:Adjustment,user=Depends(current_user)):
        permit(user,'owner','reviewer')
        values=validate_fields([money('delta','Adjustment',min=-1_000_000_000),money('quantity','Expected quantity'),money('held','Expected held')],
                               {'delta':body.delta,'quantity':body.expected_quantity,'held':body.expected_held})
        q=decimal(values['delta']);op.require(q!=0,'Correction must change the physical quantity')
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE');r=record_access(db,body.record_id,user)
            op.require(r['product'] in ('orderdesk','batch'),'Link stock corrections to an order or batch')
            op.require(r['status']!='archived','Restore the record before recording a correction')
            existing=db.execute('SELECT * FROM stock_adjustments WHERE workspace_id=? AND reference=?',(user['workspace_id'],body.reference)).fetchone()
            if existing:
                same=existing['record_id']==body.record_id and existing['sku']==body.sku and decimal(existing['delta'])==q and existing['reason']==body.reason and existing['file_id']==body.file_id
                if not same:raise HTTPException(409,'Correction reference already belongs to another adjustment')
                return dict(existing)
            stock=op.stock_row(db,user,body.sku);op.require(stock,'Choose existing workspace stock')
            if decimal(stock['quantity'])!=decimal(values['quantity']) or decimal(stock['held'])!=decimal(values['held']):
                raise HTTPException(409,'Stock changed since review. Refresh inventory before correcting it.')
            evidence=db.execute('SELECT 1 FROM files WHERE id=? AND record_id=? AND length(content)>0',(body.file_id,body.record_id)).fetchone()
            op.require(evidence,'Upload count evidence on the linked record first')
            quantity=decimal(stock['quantity'])+q;held=decimal(stock['held'])
            op.require(quantity>=0,'Correction cannot create negative stock')
            import json
            metadata=json.loads(stock['data'])
            op.require(not metadata.get('_inventory'),'Adjust this balance in DoAide Inventory, then refresh the catalogue')
            if metadata.get('quality') in ('Quarantined','Rejected','Recalled'):
                # Correcting quarantined physical stock never releases it for use.
                op.require(held==decimal(stock['quantity']),'Quality hold needs reconciliation before correction')
                held=quantity
            op.require(quantity>=held,'Correction would consume stock reserved for other work')
            identifier=op.uid();timestamp=op.now()
            db.execute('UPDATE stock SET quantity=?,held=?,updated_at=? WHERE workspace_id=? AND sku=?',(str(quantity),str(held),timestamp,user['workspace_id'],body.sku))
            db.execute('INSERT INTO stock_adjustments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(identifier,user['workspace_id'],body.record_id,body.sku,body.reference,str(q),stock['quantity'],str(quantity),stock['held'],str(held),body.reason,body.file_id,user['email'],timestamp))
            op.movement(db,r,user,body.sku,q,'count-adjustment','adjustment:'+body.reference)
            state=op.get_state(db,r['id']);op.event(db,r,user,'stock.corrected',{'id':identifier,'sku':body.sku,'delta':str(q),'reference':body.reference,'reason':body.reason,'file_id':body.file_id},state)
            return dict(db.execute('SELECT * FROM stock_adjustments WHERE id=?',(identifier,)).fetchone())

    @app.get('/api/inventory/adjustments')
    def history(user=Depends(current_user)):
        with database(path) as db:return [dict(r) for r in db.execute('SELECT * FROM stock_adjustments WHERE workspace_id=? ORDER BY created_at DESC LIMIT 500',(user['workspace_id'],))]
