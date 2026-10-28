"""Additional product contracts. Optional additions preserve existing saved records."""
from .catalog import field as F, money as N, integer as I, select as S, rows as R


def extend(specs, resource, action, text, day, email, ref, file, review):
    def fields(product, kind, extra):
        specs[product]['resources'][kind]['fields'].extend(extra)
    def actions(product, values):
        specs[product]['actions'].update(values)
    def resources(product, values):
        specs[product]['resources'].update(values)
    def optional(field): return {**field, 'required': False}
    reason = text('reason', 'Reason and source')
    for slug in ('orderdesk','claimpack','handover','scope','collect','sop','fees'):
        resources(slug,{'source_import':{**resource('Imported source previews',[]),'readonly':True}})
    for slug in ('orderdesk','claimpack'):
        actions(slug,{'import_desk_conversation':action('Preview Desk conversation',[F('source_id','Conversation UUID')],review),
                      'import_desk_order':action('Preview Desk order',[F('source_id','Order UUID')],review)})
    for slug in ('orderdesk','claimpack','handover','scope'):
        actions(slug,{'apply_source':action('Apply reviewed source',[ref('import_id','Imported preview','source_import'),reason],review)})
    actions('handover',{'import_realty_property':action('Preview Realty property',[I('source_id','Property ID',min=1)],review)})
    resources('handover',{'property_reference':resource('Reviewed Realty property',[F('reference','Property reference'),F('title','Property title'),F('location','Location'),text('details','Property details'),file()],singleton=True)})
    actions('scope',{'import_proposal_template':action('Preview Proposals offer template',[I('source_id','Template ID',min=1)],review)})
    resources('scope',{'offer_template':resource('Reviewed offer template',[F('reference','Template reference'),F('name','Template name'),text('terms','Offer terms'),text('sections','Offer sections'),text('pricing','Reference pricing'),file()],singleton=True)})
    actions('collect',{'import_khata_customer':action('Preview Khata customer ledger',[F('source_id','Khata customer ID')],review),
        'reconcile_khata_payment':action('Reconcile a received Khata payment',[ref('import_id','Imported preview','source_import'),F('transaction_id','Transaction ID from preview'),F('customer_confirmation','Confirm collection customer name'),reason],review)})
    actions('sop',{'import_payroll_roster':action('Preview Payroll staff roster',[],review),
        'assign_payroll_staff':action('Assign reviewed Payroll staff',[ref('import_id','Imported preview','source_import'),R('employees','Selected employees',[I('employee_id','Payroll employee ID',min=1)]),day('due','Training due date')],review)})
    actions('fees',{'preview_enrollment_csv':action('Preview course enrollment CSV',[file()],review),
        'apply_enrollment':action('Apply reviewed course enrollment',[ref('import_id','Imported preview','source_import'),F('student_reference','Student reference from CSV'),F('course_reference','Course reference from CSV'),F('student_confirmation','Confirm fee record student name / reference')],review)})
    actions('batch',{
        'connect_lot_inventory':action('Activate Inventory lot ledger',[],['owner']),
        'refresh_lots':action('Refresh Inventory lots'),
        'reconcile_lots':action('Reconcile pending Inventory lot command',[],review),
        'dispatch_batch':action('Dispatch batch through Inventory',[F('customer','Customer'),F('reference','Dispatch reference'),I('quantity','Units',min=1)]),
        'set_lot_quality':action('Review ingredient lot quality',[F('sku','Lot SKU · lot:reference'),S('quality','Quality',['Released','Quarantined']),reason,file()],review),
        'adjust_lot':action('Correct Inventory ingredient lot count',[F('sku','Lot SKU · lot:reference'),N('expected_quantity','Reviewed on-hand quantity'),N('quantity','Corrected on-hand quantity'),F('reference','Correction reference'),reason,file()],review)})
    fields('amc','part',[F('sku','Inventory catalogue SKU',required=False)])
    actions('amc',{'inventory_refresh':action('Activate / refresh Inventory parts catalogue',[],review),
        'reserve_parts':action('Reserve visit parts in Inventory',[ref('item_id','Visit','visit')]),
        'consume_parts':action('Confirm used parts in Inventory',[ref('item_id','Visit','visit')]),
        'release_parts':action('Release unused parts reservation',[ref('item_id','Visit','visit')]),
        'reconcile_parts':action('Reconcile parts reservation',[ref('item_id','Visit','visit')],review)})
    fields('amc','visit',[I('meeting_type_id','Scheduler meeting type ID',min=1,required=False),email('customer_email','Customer email for Scheduler',required=False)])
    actions('amc',{
        'connect_scheduler':action('Activate connected Scheduler for new visits',[],['owner']),
        'scheduler_retry':action('Retry a missing Scheduler booking',[ref('item_id','Visit','visit')],review),
        'scheduler_refresh':action('Refresh Scheduler booking',[ref('item_id','Visit','visit')]),
        'scheduler_cancel':action('Cancel Scheduler booking',[ref('item_id','Visit','visit')],review),
        'scheduler_reschedule':action('Reschedule through Scheduler',[ref('item_id','Visit','visit'),F('start','New start · ISO with offset'),F('end','New end · ISO with offset')],review)})
    actions('orderdesk',{
        'inventory_refresh':action('Refresh connected Inventory catalogue',[],review),
        'inventory_status':action('Reconcile Inventory reservation')})
    fields('collect', 'promise', [N('amount','Promised / disputed amount · INR', required=False), email('owner','Responsible owner',required=False), text('next_action','Next action',required=False), file(required=False)])
    resources('collect', {'cadence':resource('Reminder sequence and contact limits',[
        email('recipient','Customer email'), F('days','Days after invoice due date · comma separated'),
        I('minimum_hours','Minimum hours between contacts',min=1,max=8760), I('weekly_limit','Maximum contacts in seven days',min=1,max=20),
        I('start_hour','Working hours start',max=23),I('end_hour','Working hours end',min=1,max=24),
        S('consent','Customer allows reminders',['No','Yes']),F('subject','Subject'),text('message','Reminder message')],singleton=True)})
    actions('collect', {
        'resolve_case':action('Record promise / dispute outcome',[ref('item_id','Promise or dispute','promise'),S('outcome','Outcome',['Kept','Broken','Resolved','Withdrawn']),reason,file()],review),
        'schedule_sequence':action('Schedule eligible reminder sequence',[],review),
        'delivery_receipt':action('Reconcile delivery or bounce',[F('job_id','Email job ID'),S('status','Provider outcome',['Delivered','Bounced','Complaint']),F('reference','Provider event reference'),file()],review),
        'customer_statement':action('Freeze customer history statement')})
    actions('scope', {'import_contract':action('Import baseline from connected Contracts',[I('contract_id','Contracts document ID',min=1)],review),
        'compare_baseline':action('Compare request with cited baseline'),
        'review_comparison':action('Record comparison review',[S('decision','Assessment',['In scope','Change required','Needs clarification']),reason],review)})
    fields('amc','asset',[F('manufacturer','Manufacturer',required=False),day('installed_on','Installation date',required=False)])
    fields('amc','visit',[F('window_start','Customer window start · ISO with offset',required=False),F('window_end','Customer window end · ISO with offset',required=False),optional(S('access','Technician access',['Workspace member','Assigned link']))])
    resources('amc', {'plan':resource('Signed service plan version',[F('version','Plan version'),day('effective','Effective from'),F('service_hours','Service hours and response commitment'),text('coverage','Covered work and exclusions'),file()],singleton=True)})
    fields('amc','plan',[text('consumables','Consumables policy',required=False)])
    actions('amc', {
        'start_visit':action('Start assigned visit with before evidence',[ref('item_id','Visit','visit'),file(),text('notes','Initial condition')]),
        'service_readings':action('Record service checks and readings',[ref('item_id','Visit','visit'),R('readings','Completed checks',[F('check','Checklist item'),F('value','Reading / result'),F('unit','Unit',required=False)]),reason]),
        'renewal_offer':action('Approve renewal offer',[day('start','New start'),day('end','New expiry'),N('value','Value · INR'),I('included','Included visits',min=1),day('valid_until','Offer expires'),email('contact','Customer approval email'),text('terms','Renewal terms')],review),
        'activate_renewal':action('Activate accepted offer and prepare invoice',[],review)})
    resources('rfq', {'request':resource('Delivery and procurement request',[F('reference','Request reference'),F('destination','Delivery destination'),day('required_on','Required delivery date'),text('terms','Commercial requirements')],singleton=True),
        'clarification':resource('Supplier clarification thread',[F('supplier','Supplier'),text('question','Question'),text('answer','Supplier answer',required=False),file(required=False)])})
    fields('rfq','request',[email('budget_owner','Budget owner',required=False),text('quality_documents','Required quality documents',required=False)])
    fields('rfq','offer',[F('quote_number','Supplier quote number',required=False),day('quoted_on','Quote date',required=False)])
    fields('rfq','offer',[day('valid_until','Quote valid until',required=False),text('payment_terms','Payment terms',required=False),F('source_line','Quote page / line',required=False),N('freight_tax','Freight tax %',max=100,required=False),N('duties','Duties',required=False),N('packaging','Packaging',required=False),N('packaging_tax','Packaging tax %',max=100,required=False)])
    actions('rfq', {'quote_revision':action('Replace quote with a recorded revision',[ref('item_id','Offer','offer'),N('price','Revised price'),N('discount','Revised discount'),N('freight','Revised freight'),I('lead_days','Revised lead days'),file(),reason]),
        'comparison_export':action('Export supplier comparison spreadsheet')})
    fields('tender','deadline',[F('portal','Procurement portal / reference',required=False),F('clarification_at','Clarification deadline · ISO with offset',required=False)])
    fields('tender','requirement',[optional(S('interpretation','Requirement type',['Mandatory','Conditional','Informational'])),text('condition','Applicability condition',required=False),optional(S('applies','Condition applies',['Unreviewed','Yes','No']))])
    actions('tender', {'targeted_amendment':action('Review targeted amendment impact',[file(),R('affected','Affected requirements',[ref('item_id','Requirement','requirement'),text('change','Required change')]),reason],review)})
    resources('handover', {'contact':resource('Site contacts',[F('name','Name'),email('email','Email'),F('responsibility','Responsibility')]),
        'inspection_template':resource('Reusable inspection templates',[F('name','Template name'),R('checks','Checks',[F('category','Category'),text('description','Inspection check'),S('severity','Severity',['Minor','Major','Critical'])])])})
    fields('handover','issue',[F('category','Category',required=False)])
    actions('handover', {'apply_template':action('Create room checks from template',[ref('template_id','Template','inspection_template'),F('room','Room'),email('assignee','Assignee'),day('due','Due date')]),
        'acknowledge_issue':action('Acknowledge assigned issue',[ref('item_id','Issue','issue')]),
        'start_repair':action('Start repair',[ref('item_id','Issue','issue')]),
        'bulk_assign':action('Assign open repairs',[R('issues','Issues',[ref('item_id','Issue','issue')]),email('assignee','New assignee'),day('due','Due date')],review)})
    fields('orderdesk','catalogue',[F('variant','Variant',required=False)])
    resources('orderdesk', {'delivery':resource('Delivery instructions',[day('requested_on','Requested delivery date'),F('address','Delivery address'),N('freight','Freight · INR'),N('tax','Freight tax %',max=100),I('hold_hours','Reservation expires after hours',min=1,max=720)],singleton=True)})
    actions('orderdesk', {'review_order':action('Review candidate lines and substitutions',[R('lines','Confirmed candidate lines',[F('sku','Catalogue SKU'),I('quantity','Quantity',min=1),text('source','Source line / substitution agreement')]),reason]),
        'price_override':action('Approve a price override',[F('sku','SKU'),N('price','Approved unit price · INR'),reason,file()],review),
        'plan_backorder':action('Split unavailable quantities into a backorder',[day('promised_on','Promised date'),text('agreement','Customer agreement reference')]),
        'invoice_order':action('Prepare dispatched sales order invoice',[],review)})
    fields('batch','recipe',[day('effective_from','Effective from',required=False),day('effective_until','Effective until',required=False)])
    fields('batch','dispatch',[F('order_reference','External affected-order reference',required=False)])
    resources('batch', {'cost':resource('Packaging, labor and overhead',[S('category','Category',['Packaging','Labor','Overhead']),F('reference','Cost reference'),N('amount','Cost · INR'),file(required=False)])})
    actions('batch', {'cost_adjustment':action('Post a cost correction',[F('reference','Unique correction reference'),S('direction','Adjustment',['Increase','Decrease']),N('amount','Amount · INR',min=.01),reason,file()],review),
        'reverse_cost':action('Reverse a cost correction',[F('reference','Original correction reference'),F('reversal','Unique reversal reference'),reason,file()],review),
        'dispose_output':action('Record disposal of rejected / recalled output',[I('quantity','Units disposed',min=1),F('reference','Disposal reference'),reason,file()],review),
        'print_label':action('Freeze a batch traceability label')})
    fields('fees','enrollment',[F('concession_category','Concession category',required=False),F('concession_authority','Concession approval reference',required=False)])
    resources('fees', {'late_policy':resource('Approved late-fee policy',[F('version','Policy version'),S('mode','Calculation',['Fixed per instalment','Daily per instalment']),N('amount','Fee · INR'),I('grace_days','Grace days',max=365),N('cap','Maximum total late charges · INR'),day('effective','Effective from'),text('terms','Approved policy and notice terms')],singleton=True)})
    actions('fees', {'assess_late_fees':action('Assess configured late fees',[day('as_of','Assessment date')],review),
        'withdraw':action('Approve student withdrawal',[day('effective','Withdrawal date'),N('credit','Waived unpaid tuition · INR'),N('refund','Approved cash refund · INR'),F('reference','Settlement reference'),reason,file()],review)})
    fields('renew','terms',[day('term_start','Term starts',required=False),I('term_months','Term length · months',min=1,required=False)])
    actions('renew', {'negotiate_terms':action('Record negotiated term history',[N('cost','Proposed recurring cost · INR'),day('renewal','Proposed renewal date'),text('terms','Negotiated terms'),file()],review),
        'request_renewal':action('Record renewal request',[F('reference','Request reference'),file()],review)})
    specs['renew']['actions']['confirm_cancel']['fields'].append(day('effective','Effective cancellation date',required=False))
    resources('sop', {'publication_policy':resource('Audience and publication policy',[F('collection','Collection / team'),text('audience','Intended audience'),text('tools','Required tools'),text('escalation','Escalation instructions'),day('effective','Effective date'),I('offline_days','Offline-copy validity days',min=1,max=365),email('supervisor','Designated supervisor')],singleton=True),
        'branch':resource('Conditional procedure branches',[ref('step_id','Decision step','step'),text('condition','Condition'),ref('yes_step','If true, go to step','step'),ref('no_step','Otherwise, go to step','step')])})
    actions('sop', {'copy_template':action('Copy published procedure as a new draft',[F('title','New procedure title')],review),
        'new_hire_policy':action('Configure automatic new-hire enrollment',[S('enabled','Enroll new workspace members',['No','Yes']),I('due_days','Training due after days',min=1,max=365)],review),
        'enroll_team':action('Enroll current team members',[day('due','Training due date')],review),
        'training_reminders':action('Queue overdue training reminders',[S('consent','Assigned staff allow reminders',['No','Yes']),I('start_hour','Working hours start',max=23),I('end_hour','Working hours end',min=1,max=24)],review),
        'supervisor_signoff':action('Sign off completed training',[ref('item_id','Assignment','assignment'),reason],review),
        'offline_copy':action('Issue expiring procedure copy')})
    fields('claimpack','template',[email('owner','Case owner',required=False),F('deadline_source','Deadline source',required=False),text('applicability','Provider / reason applicability',required=False),day('reviewed_on','Instructions reviewed on',required=False)])
    fields('claimpack','timeline',[F('event_reference','Event reference for date comparison',required=False),F('statement_source','Statement author / source',required=False)])
    fields('claimpack','evidence',[F('provenance','Original author / source',required=False)])
    actions('claimpack', {'analyze_timeline':action('Check timeline provenance and date conflicts'),
        'approve_redaction':action('Approve redacted evidence copy',[ref('item_id','Evidence','evidence'),file('redacted_file_id','Redacted replacement file'),reason],review),
        'resolve_conflict':action('Record evidence-conflict resolution',[F('event_reference','Conflicting event reference'),F('accepted_at','Verified event time · ISO with offset'),reason,file()],review),
        'save_template':action('Publish reviewed provider template to workspace',[],review),
        'apply_template':action('Apply workspace provider template',[F('template_id','Workspace template ID'),F('deadline','Case deadline · ISO with offset')],review)})
    actions('orderdesk', {'review_transcript':action('Use reviewed recording as order source',[file(),F('reference','Source recording reference'),text('text','Reviewed order text'),reason])})
    actions('sop', {'steps_from_transcript':action('Create draft steps from a reviewed transcript',[file(),R('steps','Reviewed steps',[text('instruction','Instruction'),F('timestamp','Source timestamp')]),reason],review)})
