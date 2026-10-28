"""Workspace-scoped server credentials and a read-only Contracts source adapter."""
import json
import os
import hashlib
from urllib.parse import urlparse
import httpx
from .db import database
from . import operations as op


def connection(service,workspace,path):
    from .worker import Blocked
    try:mapping=json.loads(os.environ.get('DOAIDE_'+service+'_CONNECTIONS','{}'))
    except ValueError:raise Blocked(service+' connection mapping is invalid')
    if not isinstance(mapping,dict):raise Blocked(service+' connection mapping is invalid')
    config=mapping.get(workspace)
    # Keep the original single-workspace installation setting; never share it
    # implicitly once more than one workspace exists.
    if not config and service=='INVOICE' and not mapping:
        with database(path) as db:single=db.execute('SELECT count(*) FROM workspaces').fetchone()[0]==1
        if single:config={'url':os.environ.get('DOAIDE_INVOICE_ADAPTER_URL'),'token':os.environ.get('DOAIDE_INVOICE_ADAPTER_TOKEN')}
    if not isinstance(config,dict) or not config.get('url') or not config.get('token'):raise Blocked('Configure a '+service+' connection for this workspace')
    parsed=urlparse(config['url'])
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:raise Blocked(service+' connection requires a plain HTTPS endpoint')
    return config


def import_contract(job,path,transport=None):
    from .worker import Blocked
    from .documents import register_file_controls,malware_screen,MAX_TEXT
    from .commercial import admit
    if os.environ.get('DOAIDE_DELIVERY_MODE','disabled')!='enabled':raise Blocked('External connections are disabled')
    config=connection('CONTRACTS',job['workspace_id'],path);data=job['data']
    with httpx.Client(timeout=30,transport=transport,follow_redirects=False) as client:
        url=config['url'].rstrip('/')+'/contracts/'+str(data['contract_id'])
        response=client.get(url,headers={'Authorization':'Bearer '+config['token']});response.raise_for_status();contract=response.json()
        response=client.get(url+'/clauses',headers={'Authorization':'Bearer '+config['token']});response.raise_for_status();clauses=response.json()
    if not isinstance(contract,dict) or contract.get('id')!=int(data['contract_id']) or not isinstance(clauses,list) or not 1<=len(clauses)<=500:raise Blocked('Contracts returned an empty or invalid source')
    for clause in clauses:
        if not isinstance(clause,dict) or type(clause.get('clause_index')) is not int or not isinstance(clause.get('clause_text'),str) or not clause['clause_text'].strip() or len(clause['clause_text'])>20000:raise Blocked('Contracts returned an invalid clause')
    source=op.dump({'contract':contract,'clauses':clauses});content=source.encode()
    if len(source)>MAX_TEXT:raise Blocked('Contract exceeds the supported source length')
    scan=malware_screen(content)
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM records WHERE id=?',(job['record_id'],)).fetchone()
        if not row or row['status']=='archived':raise Blocked('Source record was archived or removed')
        record=dict(row);state=op.get_state(db,record['id'])
        prior=state['data'].get('contract_imports',{}).get(job['id'])
        if prior:return prior
        if state['revision']!=data['revision'] or record['version']!=data['version']:raise Blocked('Scope changed during import; request a new import against the current draft')
        member=db.execute('SELECT u.id,u.email,m.role FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=? AND u.id=?',(job['workspace_id'],data['user_id'])).fetchone()
        if not member or member['role'] not in ('owner','reviewer'):raise Blocked('Import requester no longer has review access')
        user={**dict(member),'workspace_id':job['workspace_id']};admit(db,user['workspace_id'],'source_bytes',len(content));identifier=op.uid()
        db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?)',(identifier,record['id'],'contract-'+str(data['contract_id'])+'.txt','text/plain',len(content),hashlib.sha256(content).hexdigest(),content,source,'imported-needs-review',user['id'],op.now()))
        register_file_controls(db,identifier,scan)
        for clause in sorted(clauses,key=lambda value:value['clause_index']):
            op.store_item(db,record['id'],'baseline',{'reference':f'Contracts #{data["contract_id"]} · clause {clause["clause_index"]} · {clause.get("clause_title") or ""}','text':clause['clause_text'],'file_id':identifier},user)
        from .migrations import invalidate
        invalidate(db,record['id'])
        result={'file_id':identifier,'clauses':len(clauses),'contract_id':data['contract_id'],'needs_human_review':True}
        state['data'].setdefault('contract_imports',{})[job['id']]=result;state['stage']='draft';state['data'].pop('approved_document',None)
        op.event(db,record,user,'contracts.imported',result,state)
    return result
