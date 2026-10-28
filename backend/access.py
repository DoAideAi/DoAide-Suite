"""Academic enrollment access is deliberately separate from financial records."""
import json
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import Literal
from .db import database
from .migrations import permit
from . import operations as op


class Access(BaseModel):
    model_config=ConfigDict(extra='forbid')
    fees_mode:Literal['financial','academic']


def install_access(app,path,current_user):
    @app.put('/api/workspace/members/{member_id}/access')
    def update(member_id:str,body:Access,user=Depends(current_user)):
        permit(user,'owner')
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            member=db.execute('SELECT role FROM memberships WHERE workspace_id=? AND user_id=?',(user['workspace_id'],member_id)).fetchone()
            if not member:raise HTTPException(404,'Member not found')
            op.require(member['role']!='owner' or body.fees_mode=='financial','Owners retain financial administration')
            db.execute('INSERT INTO member_access VALUES (?,?,?) ON CONFLICT(workspace_id,user_id) DO UPDATE SET fees_mode=excluded.fees_mode',(user['workspace_id'],member_id,body.fees_mode))
        return {'fees_mode':body.fees_mode}

    @app.get('/api/fees/academic')
    def academic(user=Depends(current_user)):
        with database(path) as db:
            result=[]
            for r in db.execute("SELECT r.* FROM records r JOIN record_workspaces w ON w.record_id=r.id WHERE w.workspace_id=? AND r.product='fees' ORDER BY r.title,r.id",(user['workspace_id'],)):
                p=json.loads(r['payload']);enrollments=op.items(db,r['id'],'enrollment')
                data=enrollments[0]['data'] if enrollments else {}
                state=db.execute('SELECT data FROM operations WHERE record_id=?',(r['id'],)).fetchone()
                withdrawn=bool(state and json.loads(state[0]).get('withdrawal'))
                result.append({'record_id':r['id'],'student':p['student'],'course':p['course'],'status':'Withdrawn' if withdrawn else 'Archived' if r['status']=='archived' else 'Active',**{k:data.get(k,'') for k in ('student_reference','course_reference','start','end')}})
        return result
