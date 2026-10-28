"""Form contracts for operational entities and commands, shared by API and UI."""
from .catalog import field as F, money as N, integer as I, select as S, rows as R


def T(key, label, **kw): return F(key, label, 'textarea', **kw)
def D(key, label, **kw): return F(key, label, 'date', **kw)
def Ref(key, label, kind, **kw): return F(key, label, 'text', choices_from=kind, **kw)
def File(key='file_id', label='Evidence file', **kw): return Ref(key, label, 'files', **kw)
def Email(key, label, **kw): return F(key, label, 'email', **kw)
def Resource(name, fields, **kw): return {'name': name, 'fields': fields, **kw}
def Action(name, fields=None, roles=None): return {'name': name, 'fields': fields or [], 'roles': roles or ['owner','operator','reviewer']}
REVIEW = ['owner', 'reviewer']
LEDGER = [S('kind','Entry type',['payment','credit','refund','charge']), N('amount','Amount · INR',min=0.01), F('reference','Unique receipt / adjustment reference'), D('date','Effective date'), T('note','Source and reason')]
REMINDER = [Email('recipient','Recipient email'), F('subject','Subject'), T('message','Message'), F('due_at','Send after · ISO date/time with offset'), I('start_hour','Working hours start (0–23)',max=23), I('end_hour','Working hours end (1–24)',min=1,max=24), S('consent','Recipient allows reminders',['Yes','No'])]
SPECS = {
 'scope': {
  'description': 'Preserve the agreed baseline, price the change, get internal approval and record the client’s acceptance of an exact version.',
  'resources': {
   'project':Resource('Project and approval contacts',[F('project','Project reference'),Email('contact','Client approval email'),T('exclusions','Explicit exclusions'),I('revision_limit','Included revision rounds'),D('valid_until','Offer valid until'),T('dependencies','Milestones / dependencies',required=False)],singleton=True),
   'baseline':Resource('Baseline clauses',[F('reference','Clause / page reference'),T('text','Agreed text'),File(required=False)]),
   'estimate':Resource('Estimate lines',[F('description','Work description'),N('quantity','Quantity',min=.001),N('rate','Unit rate · INR'),N('discount','Discount · INR'),N('tax','Tax %',max=100)]),
   'policy':Resource('Approval policy',[N('limit','Owner approval required above · INR'),I('days','Additional delivery days')],singleton=True),
  },
  'actions':{'approve':Action('Approve change request', [T('reason','Assessment and commercial terms')], REVIEW), 'invoice':Action('Prepare accepted change for invoicing')}
 },
 'collect': {
  'description':'Keep an immutable payment and adjustment ledger; pause reminders for disputes, promises, or opt-outs, and reconcile signed gateway events.',
  'resources':{'promise':Resource('Promises and disputes',[S('kind','Type',['Promise','Dispute','Resolution','Opt out','Opt in']),D('until','Promise date',required=False),T('note','Customer conversation / reason')])},
  'actions':{'ledger':Action('Record payment or adjustment',LEDGER,REVIEW),'reminder':Action('Schedule collection reminder',REMINDER),'payment_link':Action('Request payment link',[Email('email','Customer email')])}
 },
 'amc': {
  'description':'Maintain assets, schedule technicians, capture service evidence and consume visits only after independent verification.',
  'resources':{
   'asset':Resource('Assets and coverage',[F('site','Site'),F('serial','Serial number'),F('model','Model'),D('warranty','Warranty expiry',required=False),T('coverage','Covered service / exclusions')]),
   'visit':Resource('Service visits',[Ref('asset_id','Asset','asset'),Email('technician','Technician workspace email'),F('start','Start · ISO date/time with offset'),F('end','End · ISO date/time with offset'),S('chargeable','Chargeable extra visit',['No','Yes']),T('checklist','Required checks · one per line')]),
   'part':Resource('Service parts',[Ref('visit_id','Visit','visit'),F('part','Part / stock reference'),N('quantity','Quantity',min=.001),N('cost','Cost · INR')])
  },
  'actions':{'complete_visit':Action('Record completed service',[Ref('item_id','Visit','visit'),T('notes','Completed checklist and service notes'),File()]),'verify_visit':Action('Verify service completion',[Ref('item_id','Visit','visit')],REVIEW),'bill_visit':Action('Prepare verified visit invoice',[Ref('item_id','Visit','visit'),N('service_charge','Additional service charge · INR'),T('reason','Charge approval / terms')],REVIEW),'service_statement':Action('Create customer service statement'),'renew_contract':Action('Create next contract period',[D('start','New start'),D('end','New expiry'),N('value','Contract value · INR'),I('included','Included visits',min=1)],REVIEW)}
 },
 'rfq': {
  'description':'Compare multi-line, unit-equivalent offers using an explicit exchange-rate basis, then approve an award and freeze a purchase order.',
  'resources':{
   'requirement':Resource('Required items',[F('sku','Item code'),T('specification','Specification'),N('quantity','Quantity',min=.001),F('unit','Base unit')]),
   'offer':Resource('Supplier offer lines',[F('supplier','Supplier'),Ref('requirement_id','Required item','requirement'),File(),N('quantity','Offered base-unit quantity',min=.001),F('unit','Base unit'),N('price','Price per base unit'),F('currency','Currency code'),N('fx','INR per currency unit',min=.000001),F('fx_basis','Exchange rate source and date'),N('discount','Line discount'),N('tax','Tax %',max=100),N('freight','Allocated freight / duties'),I('lead_days','Lead days'),S('equivalent','Specification confirmed',['No','Yes']),T('exclusions','Exclusions / clarification',required=False)]),
   'evaluation':Resource('Technical evaluations',[F('supplier','Supplier'),N('score','Technical score /100',max=100),T('rationale','Evaluation and resolved clarifications')])
   ,'policy':Resource('Award criteria and approval limit',[N('owner_limit','Owner approval above · INR'),I('cost_weight','Cost weight %',max=100),I('technical_weight','Technical weight %',max=100),I('lead_weight','Lead time weight %',max=100)],singleton=True)
  },
  'actions':{'compare':Action('Recalculate landed costs'),'award':Action('Approve supplier and issue PO',[F('supplier','Chosen supplier'),T('reason','Award rationale / exceptions')],REVIEW)}
 },
 'tender': {
  'description':'Extract cited requirements from uploaded documents, verify each requirement, assign evidence and invalidate readiness when an amendment arrives.',
  'resources':{
   'deadline':Resource('Submission deadline',[F('at','Deadline · ISO date/time with offset'),F('timezone','IANA timezone'),T('decision','Bid / no-bid reasoning')],singleton=True),
   'requirement':Resource('Requirements and tasks',[T('text','Requirement'),F('citation','File/page/line citation'),S('category','Category',['Eligibility','Technical','Commercial','Submission']),Email('owner','Responsible owner'),D('due','Task due date'),File(required=False),D('valid_until','Evidence valid through',required=False)]),
  },
  'actions':{'extract':Action('Extract requirement candidates',[File()]),'verify_requirement':Action('Verify requirement and evidence',[Ref('item_id','Requirement','requirement'),T('note','Verification notes')],REVIEW),'amendment':Action('Register amendment and reset verification',[File(),T('note','Amendment summary')]),'ready':Action('Approve bid readiness',[],REVIEW),'submission':Action('Record actual submission receipt',[F('reference','Submission reference'),File()],REVIEW)}
 },
 'handover': {
  'description':'Track rooms, snag owners and repair evidence. Independent verification and client acceptance preserve exactly what was handed over.',
  'resources':{
   'room':Resource('Rooms / checklist templates',[F('name','Room / area'),T('checklist','Inspection checklist')]),
   'issue':Resource('Snag register',[F('room','Room / area'),T('description','Issue'),S('severity','Severity',['Minor','Major','Critical']),Email('assignee','Contractor / operator email'),D('due','Repair due date'),File(required=False)]),
  },
  'actions':{'fixed':Action('Record repair evidence',[Ref('item_id','Issue','issue'),T('note','Repair notes'),File()]),'verify_issue':Action('Independently verify repair',[Ref('item_id','Issue','issue'),T('note','Verification notes')],REVIEW),'waive':Action('Propose minor-issue waiver',[Ref('item_id','Issue','issue'),T('note','Waiver disclosed for client acceptance')],REVIEW),'close':Action('Prepare handover for acceptance',[],REVIEW),'reopen':Action('Open warranty follow-up',[Ref('item_id','Issue','issue'),T('note','Warranty issue')])}
 },
 'orderdesk': {
  'description':'Publish a workspace catalogue, resolve messages against exact aliases, obtain customer confirmation and reserve stock transactionally.',
  'resources':{
   'catalogue':Resource('Catalogue and aliases',[F('sku','SKU'),F('name','Name'),F('aliases','Aliases · comma separated',required=False),F('unit','Base unit'),I('pack','Units per pack',min=1),N('price','Price per base unit · INR'),N('tax','Tax %',max=100),N('stock','Opening stock',min=0)]),
   'message':Resource('Incoming orders',[F('reference','Source message ID'),T('text','Customer text or reviewed transcript'),File(required=False)])
  },
  'actions':{'publish_catalogue':Action('Publish catalogue / opening stock',[],REVIEW),'parse_order':Action('Resolve order lines'),'confirm_order':Action('Confirm exact order',[T('confirmation','Customer confirmation reference')]),'reserve':Action('Reserve confirmed stock'),'dispatch':Action('Dispatch reserved order',[F('reference','Dispatch / invoice reference')]),'cancel':Action('Cancel and release reservation',[T('reason','Cancellation reason')])}
 },
 'batch': {
  'description':'Keep recipe versions and supplier lots, consume available ingredients atomically, quarantine finished output until quality release, and trace recalls.',
  'resources':{
   'recipe':Resource('Recipe versions',[F('version','Recipe version'),F('ingredient','Ingredient'),N('quantity','Planned quantity',min=.001),F('unit','Base unit')]),
   'lot':Resource('Incoming ingredient lots',[F('lot','Lot reference'),F('ingredient','Ingredient'),F('supplier','Supplier'),N('quantity','Received quantity',min=.001),F('unit','Base unit'),N('cost','Cost per unit · INR'),D('expiry','Expiry'),S('quality','Quality status',['Quarantined','Released']),File(required=False)]),
   'usage':Resource('Actual usage and waste',[F('lot','Lot reference'),N('quantity','Consumed quantity',min=.001),N('waste','Waste included in consumption'),F('unit','Base unit')]),
   'dispatch':Resource('Finished-batch destinations',[F('customer','Customer'),F('reference','Dispatch reference'),I('quantity','Units',min=1)])
  },
  'actions':{'receive_lots':Action('Receive approved ingredient lots',[],REVIEW),'reserve_materials':Action('Reserve input lots'),'release_materials':Action('Release input reservations',[T('reason','Release reason')]),'produce':Action('Consume lots and record output'),'return_material':Action('Return unused input to its lot',[F('lot','Original consumed lot reference'),N('quantity','Returned quantity',min=.001),F('reference','Unique return reference'),T('reason','Return reason')],REVIEW),'quality_release':Action('Release finished batch',[T('checks','Quality test results'),File()],REVIEW),'quality_reject':Action('Reject / quarantine finished batch',[T('reason','Quality rejection reason'),File()],REVIEW),'trace':Action('Build traceability report'),'recall':Action('Quarantine batch / create recall list',[T('reason','Recall reason')],REVIEW)}
 },
 'fees': {
  'description':'Approve the fee agreement, record receipts and adjustments without overwriting history, and share a limited guardian statement.',
  'resources':{'enrollment':Resource('Student enrollment',[F('student_reference','Student reference'),F('course_reference','Course / batch reference'),D('start','Enrollment start'),D('end','Enrollment end'),T('terms','Fee agreement and refund terms')],singleton=True),'guardian':Resource('Guardian contacts',[F('name','Guardian name'),Email('email','Guardian email'),S('reminders','Allows fee reminders',['Yes','No'])]),'instalment':Resource('Rescheduled instalments',[D('due','Due date'),N('amount','Amount · INR',min=.01),T('reason','Rescheduling reason')])},
  'actions':{'approve_agreement':Action('Approve fee / discount agreement',[T('reason','Discount / agreement approval')],REVIEW),'reschedule':Action('Approve remaining-fee reschedule',[R('instalments','Replacement unpaid instalments',[D('due','New due date'),N('amount','Amount · INR',min=.01)]),T('reason','Reason and agreed terms')],REVIEW),'ledger':Action('Record receipt, refund or adjustment',LEDGER,REVIEW),'statement':Action('Create guardian statement'),'payment_link':Action('Request guardian payment link',[Email('email','Guardian email')]),'reminder':Action('Schedule guardian reminder',REMINDER)}
 },
 'renew': {
  'description':'Track contract terms, notify owners before the notice deadline and distinguish a requested cancellation from vendor-confirmed cancellation.',
  'resources':{
   'terms':Resource('Contract terms',[F('department','Department'),I('seats','Seats'),Email('owner','Responsible owner'),Email('backup','Backup owner'),T('notice_clause','Exact notice clause'),S('business_days','Count notice in business days',['No','Yes']),T('holidays','Holiday dates · one per line',required=False),File(required=False)],singleton=True),
   'invoice':Resource('Actual spend',[F('reference','Invoice reference'),D('date','Invoice date'),N('amount','Amount · INR'),File(required=False)])
   ,'subscription':Resource('Verified subscription details',[F('reference','Vendor subscription reference'),S('auto_renew','Automatically renews',['Yes','No']),I('active_seats','Verified active seats'),D('verified_on','Usage verified on'),T('source','Usage evidence / source')],singleton=True)
   ,'reminder_policy':Resource('Notice reminder policy',[F('days','Days before notice · comma separated, e.g. 30,14,7,0'),I('escalate_after','Escalate to backup after days',min=1,max=30),I('start_hour','Working hours start',max=23),I('end_hour','Working hours end',min=1,max=24),S('consent','Owners allow email reminders',['Yes','No'])],singleton=True)
  },
  'actions':{'plan_reminders':Action('Schedule notice milestones',[],REVIEW),'acknowledge_notice':Action('Acknowledge notice responsibility',[],['owner','operator','reviewer','viewer']),'decide':Action('Approve renewal decision',[S('decision','Decision',['Renew','Cancel','Negotiate']),T('reason','Decision rationale')],REVIEW),'request_cancel':Action('Record cancellation request',[F('reference','Request reference'),File()]),'confirm_cancel':Action('Record vendor confirmation',[F('reference','Vendor confirmation'),File()],REVIEW),'rollover':Action('Create confirmed next renewal term',[D('renewal','Next renewal date'),N('cost','New recurring cost · INR'),File('file_id','Vendor renewal confirmation')],REVIEW),'reminder':Action('Schedule owner reminder',REMINDER),'calendar':Action('Prepare notice calendar event')}
 },
 'sop': {
  'description':'Publish reviewed, immutable procedures; assign named staff and record authenticated acknowledgements and approved quiz results against exact versions.',
  'resources':{
   'step':Resource('Procedure steps',[I('position','Step number',min=1),T('instruction','Instruction'),T('prerequisites','Prerequisites / tools',required=False),F('timestamp','Source recording timestamp',required=False),File(required=False)]),
   'question':Resource('Assessment questions',[T('question','Question'),T('answer','Approved answer')]),
   'assignment':Resource('Staff training assignments',[Email('employee','Staff email'),D('due','Training due date')])
  },
  'actions':{'publish':Action('Review and publish procedure',[I('pass_percent','Quiz pass percentage',min=1,max=100),T('review','Safety / process review')],REVIEW),'acknowledge':Action('Acknowledge current published procedure',[],['owner','operator','reviewer','viewer']),'assess':Action('Submit assessment',[R('answers','Answers',[Ref('question_id','Question','question'),T('answer','Your answer')])],['owner','operator','reviewer','viewer'])}
 },
 'claimpack': {
  'description':'Verify a provider-specific evidence checklist, cite factual timeline entries, export a frozen packet and separately record submission and outcome.',
  'resources':{
   'template':Resource('Provider requirements',[F('provider','Provider'),F('reason_code','Reason code'),F('version','Template version / date'),F('deadline','Deadline · ISO date/time with offset'),I('max_mb','Maximum packet size MB',min=1,max=50),T('required_kinds','Required evidence categories · one per line'),F('source','Provider instructions URL / reference')],singleton=True),
   'evidence':Resource('Evidence index',[F('kind','Evidence category'),File(),T('fact','Fact supported by this evidence'),T('redaction','Redactions already applied to the uploaded copy',required=False)]),
   'timeline':Resource('Factual timeline',[F('at','Event · ISO date/time with offset'),T('fact','Fact'),Ref('evidence_id','Supporting evidence','evidence')])
  },
  'actions':{'verify_evidence':Action('Verify evidence readability / relevance',[Ref('item_id','Evidence','evidence'),T('note','Verification notes')],REVIEW),'pack':Action('Freeze evidence packet',[],REVIEW),'submission':Action('Record provider submission',[F('reference','Provider submission receipt'),File()],REVIEW),'outcome':Action('Record provider outcome',[S('result','Outcome',['Won','Lost','Withdrawn']),T('note','Provider decision'),File()],REVIEW)}
 }
}
