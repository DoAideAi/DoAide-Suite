"""Reviewed, immutable imports from existing portfolio APIs and enrollment CSV."""
import csv
import hashlib
import io
import json
import os
import re
from datetime import date
from urllib.parse import quote
import httpx
from fastapi import HTTPException
from . import operations as op
from .db import database
from .portfolio_connections import connection

FETCH={'import_desk_conversation':('DESK','conversation'), 'import_desk_order':('DESK','order'),
       'import_realty_property':('REALTY','property'), 'import_proposal_template':('PROPOSALS','template'),
       'import_payroll_roster':('PAYROLL','roster'), 'import_khata_customer':('KHATA','customer')}
ALLOWED={'conversation':('orderdesk','claimpack'),'order':('orderdesk','claimpack'),'property':('handover',),'template':('scope',),'roster':('sop',),'customer':('collect',),'enrollment':('fees',)}


def checked(value,message):
    from .worker import Blocked
    if not value:raise Blocked(message)


def config_for(service,u,db):
    from .worker import Blocked
    try:return connection(service,u['workspace_id'],db.execute('PRAGMA database_list').fetchone()[2])
    except Blocked as exc:raise HTTPException(422,str(exc))


def execute(db,r,u,a,d,s,out):
    if a in FETCH:
        service,kind=FETCH[a];op.require(r['product'] in ALLOWED[kind],'This source is not available for this product')
        config=config_for(service,u,db);source=str(d.get('source_id','roster'))
        op.require(re.fullmatch(r'[A-Za-z0-9_-]{1,160}',source),'Use the source record ID')
        identity=config.get('account_email') if service=='KHATA' else config.get('agent_id') if service=='REALTY' else config.get('business_id')
        op.require(identity is not None,'Configure the source business / agent / account identity')
        out['job_id']=op.enqueue(db,r,u,'source-import',{'service':service,'kind':kind,'source_id':source,'endpoint':config['url'].rstrip('/'),'identity':identity,'user_id':u['id'],'revision':s['revision']+1,'version':r['version']},'source:'+r['id']+':'+str(s['revision']))
        return True
    if a=='preview_enrollment_csv':
        f=db.execute('SELECT * FROM files WHERE id=? AND record_id=?',(d['file_id'],r['id'])).fetchone();op.require(f and f['name'].lower().endswith('.csv'),'Upload a UTF-8 enrollment CSV')
        op.require(f['size']<=200000,'Split enrollment files into at most 200 KB')
        try:reader=csv.DictReader(io.StringIO(bytes(f['content']).decode('utf-8-sig')));rows=list(reader)
        except (ValueError,UnicodeError,csv.Error):raise HTTPException(422,'Invalid UTF-8 CSV')
        required={'student_reference','course_reference','start','end','terms'}
        op.require(reader.fieldnames and required.issubset(reader.fieldnames) and len(reader.fieldnames)==len(set(reader.fieldnames)),'CSV requires student_reference, course_reference, start, end and terms headers')
        op.require(1<=len(rows)<=1000,'Import 1–1,000 enrollment rows')
        normalized=[];seen=set()
        for row in rows:
            op.require(None not in row and all(isinstance(row.get(k),str) and row[k].strip() for k in required),'Incomplete enrollment row')
            fields=op.validate_fields(op.SPECS['fees']['resources']['enrollment']['fields'],{k:row[k].strip() for k in required})
            op.require(fields['end']>=fields['start'],'Enrollment end precedes start')
            key=(fields['student_reference'],fields['course_reference']);op.require(key not in seen,'Duplicate student/course in enrollment CSV');seen.add(key);normalized.append(fields)
        out['import_id']=retain(db,r,u,{'service':'COURSE_CSV','kind':'enrollment','source_id':f['checksum'],'endpoint':'uploaded-csv','identity':u['workspace_id']},{'rows':normalized},file_id=f['id'])
        return True
    if a not in ('apply_source','reconcile_khata_payment','assign_payroll_staff','apply_enrollment'):return False
    source=op.one_item(db,r['id'],d['import_id'],'source_import');data=source['data'];kind=data['kind'];value=data['source']
    op.require(r['product'] in ALLOWED[kind],'Wrong product for this source')
    if a=='reconcile_khata_payment':
        op.require(kind=='customer','Select a Khata customer import')
        tx=next((x for x in value['transactions'] if str(x['id'])==d['transaction_id']),None)
        op.require(tx and tx.get('type')=='received' and not tx.get('deleted'),'Choose an active received payment')
        op.require(d['customer_confirmation']==json.loads(r['payload'])['customer'],'Confirm the exact customer name on this collection record')
        reference='khata:'+hashlib.sha256((data['endpoint']+'|'+str(data['identity'])+'|'+str(tx['id'])).encode()).hexdigest()
        out['entry_id']=op.post_ledger(db,r,u,{'kind':'payment','amount':tx['amount'],'date':date.fromisoformat(tx['date']).isoformat(),'reference':reference,'note':d['reason']+' · Khata '+str(tx['id']),'method':'Other','file_id':data['file_id']})
        out['document_id']=op.snapshot(db,r,u,'khata-reconciliation',s,{'entry_id':out['entry_id'],'import_id':source['id'],'transaction':tx})
    elif a=='assign_payroll_staff':
        op.require(kind=='roster' and s['stage']=='published','Select a Payroll roster for a published procedure')
        op.require(d['due']>=op.business_today(db,u).isoformat(),'Training due date is in the past')
        out['assignments']=[]
        for selected in d['employees']:
            employee=next((x for x in value['employees'] if str(x['id'])==str(selected['employee_id'])),None)
            op.require(employee and employee['is_active'] and employee['employment_status']=='active' and not employee.get('date_of_exit') and employee.get('email'),'Select active employees with workspace email addresses')
            out['assignments'].append(op.resource(db,r,u,'assignment',{'employee':employee['email'].lower(),'due':d['due']}))
        s.update(op.get_state(db,r['id']))
    elif a=='apply_enrollment':
        op.require(kind=='enrollment','Select an enrollment CSV preview')
        matches=[x for x in value['rows'] if x['student_reference']==d['student_reference'] and x['course_reference']==d['course_reference']]
        op.require(len(matches)==1,'Choose a student/course pair from the preview')
        op.require(d['student_confirmation']==json.loads(r['payload'])['student'],'Confirm the student name / reference on this fee record')
        op.require(not op.items(db,r['id'],'enrollment'),'This record already has an enrollment; review amendments explicitly')
        out['item_id']=op.resource(db,r,u,'enrollment',matches[0]);s.update(op.get_state(db,r['id']))
    else:
        op.require(kind in ('conversation','order','property','template'),'Use the matching review action for this import')
        op.require(not data.get('applied_at'),'This source was already applied')
        # A refresh of the same source cannot create a duplicate copy on this record.
        op.require(not any(x['id']!=source['id'] and x['data'].get('source_key')==data['source_key'] and x['data'].get('applied_at') for x in op.items(db,r['id'],'source_import')),'This source has already been applied; review its newer version as evidence')
        if kind in ('conversation','order'):
            if r['product']=='claimpack':
                out['item_id']=op.resource(db,r,u,'evidence',{'kind':'Customer conversation' if kind=='conversation' else 'Order','file_id':data['file_id'],'fact':d['reason'],'redaction':''})
            else:
                text='\n'.join(x['text'] for x in value['messages'] if x.get('direction')=='INBOUND' and x['text']) if kind=='conversation' else '\n'.join(str(x['quantity'])+' x '+str(x.get('sku') or x.get('name')) for x in value['lineItems'])
                op.require(text,'No incoming order text or SKU lines were found; retain the source and enter reviewed candidates')
                out['item_id']=op.resource(db,r,u,'message',{'reference':data['service']+':'+data['source_id'],'text':text,'file_id':data['file_id']})
        elif kind=='property':
            out['item_id']=op.resource(db,r,u,'property_reference',{'reference':str(value['id']),'title':value['title'],'location':', '.join(str(value.get(k) or '') for k in ('locality','city')),'details':op.dump(value),'file_id':data['file_id']})
        elif kind=='template':
            out['item_id']=op.resource(db,r,u,'offer_template',{'reference':str(value['id']),'name':value['name'],'terms':value.get('default_terms') or 'No default terms','sections':op.dump(value['sections']),'pricing':op.dump(value.get('pricing_table') or {}),'file_id':data['file_id']})
        s.update(op.get_state(db,r['id']))
        data.update(applied_at=op.now(),applied_by=u['id'],review=d['reason']);op.store_item(db,r['id'],'source_import',data,u,source['id'])
    return True


def fetch(job,path,transport=None):
    from .worker import Blocked
    checked(os.environ.get('DOAIDE_DELIVERY_MODE','disabled')=='enabled','External connections are disabled')
    d=job['data'];service=d['service'];kind=d['kind'];config=connection(service,job['workspace_id'],path)
    identity=config.get('account_email') if service=='KHATA' else config.get('agent_id') if service=='REALTY' else config.get('business_id')
    checked(config['url'].rstrip('/')==d['endpoint'] and identity==d['identity'],'Source connection identity changed; request a new import')
    with database(path) as db:requester(db,job)
    with httpx.Client(timeout=30,transport=transport,follow_redirects=False,headers={'Authorization':'Bearer '+config['token']}) as client:
        def get(route,params=None):
            with client.stream('GET',d['endpoint']+route,params=params) as response:
                response.raise_for_status();chunks=[];size=0
                for chunk in response.iter_bytes():
                    size+=len(chunk);checked(size<=2000000,'Source response exceeds 2 MB');chunks.append(chunk)
                return json.loads(b''.join(chunks))
        sid=quote(d['source_id'],safe='')
        if service=='DESK':
            value=get(('/conversations/' if kind=='conversation' else '/orders/')+sid)
            checked(str(value.get('business_id',value.get('businessId')))==str(identity) and str(value.get('id'))==d['source_id'],'Desk returned a different tenant or source')
            if kind=='conversation':
                messages=[];cursor=None;seen=set()
                for _ in range(10):
                    page=get('/conversations/'+sid+'/messages',{'limit':100,**({'cursor':cursor} if cursor else {})})
                    checked(isinstance(page.get('data'),list),'Invalid Desk message page')
                    for row in page['data']:
                        checked(str(row.get('business_id'))==str(identity) and row.get('conversation_id')==d['source_id'] and row.get('id') not in seen,'Invalid or repeated Desk message')
                        seen.add(row['id']);content=row.get('content') or {};text=row.get('text_content') or (content.get('text') if isinstance(content,dict) else '') or ''
                        checked(isinstance(text,str),'Invalid Desk message text')
                        messages.append({'id':row['id'],'at':row['created_at'],'direction':row['direction'],'text':text,'type':row.get('type'),'media_reference':row.get('media_url')})
                    if not page.get('hasMore'):break
                    checked(page.get('cursor') and page['cursor']!=cursor,'Invalid Desk pagination');cursor=page['cursor']
                else:raise Blocked('Split conversations exceeding 1,000 messages')
                value={'id':value['id'],'subject':value.get('subject'),'messages':sorted(messages,key=lambda x:(x['at'],x['id']))}
            else:
                checked(isinstance(value.get('lineItems'),list) and 0<len(value['lineItems'])<=200,'Invalid Desk order lines')
                value={key:value.get(key) for key in ('id','orderNumber','status','currency','lineItems','subtotal','taxAmount','shippingFee','total','placedAt')}
        elif service=='REALTY':
            value=get('/properties/'+sid);checked(str(value.get('agent_id'))==str(identity) and str(value.get('id'))==d['source_id'],'Realty returned a different agent or property')
            value={k:value.get(k) for k in ('id','title','property_type','bhk','size_sqft','size_unit','locality','city','status','rera_project_number','updated_at')}
            checked(isinstance(value.get('title'),str) and value['title'],'Invalid Realty property')
        elif service in ('PROPOSALS','PAYROLL'):
            me=get('/auth/me');me=me['data'] if service=='PAYROLL' else me
            checked(me.get('business',{}).get('id')==identity,'Connected account belongs to a different business')
            if service=='PROPOSALS':
                value=get('/templates/'+sid);checked(str(value.get('id'))==d['source_id'] and isinstance(value.get('sections'),list),'Invalid proposal template')
            else:
                employees=[];seen=set()
                for skip in range(0,10000,200):
                    page=get('/employees',{'skip':skip,'limit':200})['data'];rows=page['employees']
                    checked(isinstance(rows,list) and len(rows)<=200,'Invalid Payroll roster')
                    for row in rows:
                        checked(row.get('id') not in seen,'Payroll returned duplicate employees');seen.add(row['id'])
                        employees.append({k:row.get(k) for k in ('id','employee_code','full_name','email','department','date_of_joining','date_of_exit','employment_status','is_active')})
                    if skip+len(rows)>=page['total']:break
                    checked(len(rows)>0,'Payroll pagination stopped before the total')
                else:raise Blocked('Split rosters exceeding 10,000 employees')
                value={'employees':employees}
        else:
            result=get('/ledger');checked(result.get('account_email')==identity,'Khata account does not match this workspace connection')
            ledger=result['ledger'];customer=next((x for x in ledger['customers'] if str(x.get('id'))==d['source_id'] and not x.get('deleted')),None)
            checked(customer,'Khata customer is missing or deleted')
            transactions=[x for x in ledger['transactions'] if str(x.get('customerId'))==d['source_id'] and not x.get('deleted')]
            for tx in transactions:
                checked(tx.get('id') and tx.get('type') in ('gave','received') and op.decimal(tx['amount'])>0,'Invalid Khata transaction')
                date.fromisoformat(tx['date'])
            checked(len({str(x['id']) for x in transactions})==len(transactions),'Duplicate Khata transaction IDs')
            value={'customer':customer,'transactions':transactions,'bills':[x for x in ledger.get('bills',[]) if str(x.get('customerId'))==d['source_id'] and not x.get('deleted')]}
    checked(len(op.dump(value).encode())<=200000,'Source exceeds the supported retained preview size')
    return {'source':value}


def requester(db,job):
    d=job['data'];row=db.execute('SELECT * FROM records WHERE id=?',(job['record_id'],)).fetchone()
    checked(row and row['status']!='archived','Import record was archived or removed')
    r=dict(row);s=op.get_state(db,r['id'])
    member=db.execute('SELECT u.id,u.email,m.role FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.workspace_id=? AND u.id=?',(job['workspace_id'],d['user_id'])).fetchone()
    checked(member and member['role'] in ('owner','reviewer'),'Importer no longer has review access')
    checked(r['version']==d['version'] and s['revision']==d['revision'],'Record changed during import; request a new preview')
    return r,s,{**dict(member),'workspace_id':job['workspace_id']}


def retain(db,r,u,metadata,value,file_id=None):
    from .documents import register_file_controls,malware_screen
    from .commercial import admit
    source=op.dump(value);content=source.encode();op.require(len(content)<=200000,'Source preview exceeds 200 KB')
    if not file_id:
        scan=malware_screen(content);admit(db,u['workspace_id'],'source_bytes',len(content));file_id=op.uid()
        db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?)',(file_id,r['id'],metadata['service'].lower()+'-'+metadata['source_id']+'.txt','text/plain',len(content),hashlib.sha256(content).hexdigest(),content,source,'imported-needs-review',u['id'],op.now()))
        register_file_controls(db,file_id,scan)
    source_key=hashlib.sha256(op.dump({k:metadata[k] for k in ('service','kind','source_id','endpoint','identity')}).encode()).hexdigest()
    return op.store_item(db,r['id'],'source_import',{**metadata,'file_id':file_id,'source':value,'source_key':source_key,'imported_at':op.now(),'review_status':'Needs review'},u)


def complete(db,job,result):
    r,s,u=requester(db,job);metadata={k:job['data'][k] for k in ('service','kind','source_id','endpoint','identity')}
    identifier=retain(db,r,u,metadata,result['source'])
    op.event(db,r,u,'source.imported',{'import_id':identifier,'service':metadata['service'],'needs_human_review':True},s)
