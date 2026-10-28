"""Coarse public readiness and owner-only diagnostics without secrets or payloads."""
import os
from datetime import datetime, timezone
from fastapi import Depends
from fastapi.responses import JSONResponse
from .db import database
from .migrations import permit
from .malware import scanner_ready


def health(db):
    row=db.execute("SELECT last_seen FROM runtime_status WHERE name='worker'").fetchone()
    age=max(0,int((datetime.now(timezone.utc)-datetime.fromisoformat(row[0])).total_seconds())) if row else None
    busy=bool(db.execute("SELECT 1 FROM jobs WHERE state='running' AND lease_until>? LIMIT 1",(datetime.now(timezone.utc).isoformat(),)).fetchone())
    return {'schema_version':db.execute('PRAGMA user_version').fetchone()[0],'worker_age_seconds':age,'worker_has_active_lease':busy,'worker_healthy':(age is not None and age<180) or busy}


def install_diagnostics(app,path,current_user):
    @app.get('/api/ready')
    def readiness():
        try:
            with database(path) as db:state=health(db)
            ready=state['schema_version']==5 and (os.environ.get('DOAIDE_REQUIRE_WORKER','false')!='true' or state['worker_healthy'])
            if os.environ.get('DOAIDE_REQUIRE_MALWARE_SCAN')=='true':ready=ready and scanner_ready()
        except Exception:ready=False
        return JSONResponse({'ready':ready},status_code=200 if ready else 503)

    @app.get('/api/diagnostics')
    def diagnostics(user=Depends(current_user)):
        permit(user,'owner')
        with database(path) as db:
            state=health(db)
            state['jobs']=[dict(r) for r in db.execute('SELECT kind,state,count(*) AS count,min(due_at) AS oldest_due FROM jobs WHERE workspace_id=? GROUP BY kind,state',(user['workspace_id'],))]
            state['database_bytes']=db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0]
            state['delivery_mode']=os.environ.get('DOAIDE_DELIVERY_MODE','disabled')
            state['malware_screening_required']=os.environ.get('DOAIDE_REQUIRE_MALWARE_SCAN')=='true'
            if state['malware_screening_required']:state['scanner_healthy']=scanner_ready()
            return state


if __name__ == '__main__':
    # Container worker health is independent of the HTTP server and its port.
    import sys
    try:
        with database() as db:state=health(db)
        healthy=state['schema_version']==5 and state['worker_healthy']
    except Exception:healthy=False
    sys.exit(0 if healthy else 1)
