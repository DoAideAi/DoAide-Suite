"""Maintain product-specific engineering scope documents beside their implementation."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.catalog import PRODUCTS

# Requirements describe the intended pilot release, not claims about the current build.
SPECS = {
"scope": {
"outcome": "Help an agency identify, price, agree, and invoice extra work while preserving the original statement of work and the client's decision trail.",
"roles": "Agency owner sets rates and approval rules; project manager prepares change requests; delivery staff estimate effort; client reviewer accepts or declines a specific version through a limited-access link.",
"journey": "Create a project and client → import the signed baseline → capture a new request → compare against cited deliverables → estimate effort and delivery impact → obtain internal review → request client approval → hand the approved change to Invoicer.",
"requirements": [
"Maintain projects, clients, versioned baseline documents, included deliverables, explicit exclusions, revision limits, and approval contacts. Store original evidence separately from extracted text.",
"Accept pasted requests and uploaded PDF/DOCX statements of work. Preserve document name, page or paragraph references, extraction version, and the exact excerpt supporting each comparison.",
"Offer an assisted scope assessment with In scope, Change required, and Needs clarification outcomes. The project manager makes the final assessment; a model cannot authorize pricing or contract changes.",
"Estimate quantity or hours, rates, currency, discounts, tax assumptions, milestones, dependencies, and additional delivery days. Keep calculation rules and round currency at defined boundaries.",
"Generate an editable change request showing the original commitment, requested addition, estimated price, timeline impact, validity period, and assumptions. Support PDF export and revision history.",
"Require internal approval above configured price thresholds. Client links must be expiring, scoped to one version, and revocable. Changing price or deliverables invalidates prior acceptance.",
"Record client acceptance or rejection, identity evidence, timestamp, document hash, and comments. Show the exact accepted version and distinguish internal review from client acceptance.",
"Create an idempotent draft invoice or proposal via an adapter after acceptance. Track invoice reference and billing status without silently changing the signed baseline."
],
"entities": ["Project(id, workspace_id, client_id, currency, owner_id)", "BaselineVersion(id, project_id, revision, document_id, effective_at, content_hash)", "Deliverable(id, baseline_version_id, text, source_locator)", "ChangeRequest(id, project_id, baseline_version_id, status, version, request_text)", "EstimateLine(id, change_id, quantity_decimal, unit_rate_minor, tax_rule_id)", "Approval(id, change_version_id, actor_id, decision, signed_hash, timestamp)", "InvoiceLink(change_version_id UNIQUE, external_invoice_id, sync_status)"],
"states": "New → Assessed → Internally reviewed → Sent → Accepted / Declined / Expired → Invoiced. Any commercial revision creates a new version and requires renewed approval.",
"integrations": "DoAide Contracts for baseline versions; Proposals for offer templates; Invoicer for draft billing; private object storage for source files; optional email provider for approved delivery. Existing APIs must be inspected before adapter implementation.",
"exclusions": "Automatic contract interpretation, legal conclusions, automatic customer acceptance, collecting money, full project management, and replacing a qualified electronic signature provider.",
"acceptance": ["Given an 18-hour change at INR 2,000/hour, the estimated change is INR 36,000 before separately specified taxes.", "An unassessed request cannot become internally reviewed; every suggested match preserves the baseline reference.", "A client cannot view another client's change request, and an expired or revoked link cannot accept it.", "Changing an accepted estimate produces a new version and never changes the previously accepted PDF.", "Repeated invoice handoff creates one draft invoice; failed delivery remains retryable and visible."],
"first": "Manual baseline and request entry; shared-term comparison; human assessment; effort, price, and timeline calculation; internal change draft; record persistence, revision history, review checks, print and JSON export.",
"next": "Project and baseline tables, document extraction, client acceptance links, quote PDF templates, and the Invoicer adapter.",
"metrics": "Time from new request to priced change; accepted changes as a share of sent changes; approved extra-work value; percentage of accepted changes invoiced.",
"risk": "Text similarity can miss scope conflicts. Assisted findings must remain traceable suggestions. Client acceptance and monetary amounts require a stable version boundary.",
"wave": "1", "complexity": "Medium"
},
"collect": {
"outcome": "Give a service business a reliable view of overdue money, payment commitments, and disputes, with a controlled follow-up workflow that stops when payment is confirmed.",
"roles": "Business owner configures collection policies; finance operator reconciles invoices and payments; account manager handles relationship-sensitive cases; customer sees only their balance and approved payment options.",
"journey": "Import invoices and receipts → reconcile balances → rank due follow-ups → record a dispute or promise → review a message → deliver through an enabled channel → reconcile payment events → close or escalate the case.",
"requirements": [
"Import invoice and customer CSVs with a preview, field mapping, duplicate detection, row-level errors, and reversible import batches. Support invoice IDs from Invoicer and external systems.",
"Maintain invoice totals, credits, payments, allocations, due dates, currency, and outstanding balances using exact decimal or minor-unit arithmetic. Do not sum unlike currencies.",
"Produce aging buckets and follow-up queues with explicit as-of dates and business timezone. Separate overdue amounts from future instalments and disputed balances.",
"Record promised dates and amounts, responsible owner, last contact, and promise outcome. A live promise pauses the corresponding reminder schedule until its due date.",
"Manage disputes with reason, documents, assigned owner, next action, and resolution. Pause collection reminders while disputed; resolution must state whether money remains due.",
"Prepare configurable reminder sequences, working hours, frequency limits, and opt-out handling. Require a preview and an authorized sending configuration before enabling delivery.",
"Integrate payment links and signed gateway callbacks; process duplicate callbacks idempotently, reconcile partial payments, and stop queued reminders after confirmed settlement.",
"Track delivery outcomes and failed retries; export customer statements and collection history. Never infer that an email was delivered from an enqueue success."
],
"entities": ["Customer(id, workspace_id, external_ref UNIQUE per workspace)", "Invoice(id, customer_id, currency, total_minor, due_date, source_ref)", "Payment(id, provider_event_id UNIQUE, amount_minor, confirmed_at)", "Allocation(payment_id, invoice_id, amount_minor)", "Promise(id, invoice_id, promised_date, promised_minor, status)", "Dispute(id, invoice_id, owner_id, reason, status)", "Followup(id, invoice_id, channel, scheduled_at, status, idempotency_key UNIQUE)"],
"states": "Invoice: Open → Partially paid → Paid; credit notes adjust balance explicitly. Case: Due → Promise active / Disputed / Follow-up due → Resolved. Sending is a separate queued/sent/delivered/failed state machine.",
"integrations": "DoAide Invoicer and Khata adapters; CSV import; a selected payment gateway; email and optional official WhatsApp Business messaging; customer contact preferences.",
"exclusions": "Debt purchasing, threatening or legal recovery notices, credit scoring, lending, silently sending messages, and marking payments paid from screenshots alone.",
"acceptance": ["An INR 85,000 invoice with INR 25,000 in confirmed payments shows INR 60,000 outstanding.", "A disputed invoice never enters an automated payment reminder job; an active promise defers follow-up.", "A fully settled invoice produces no new reminder, including when payment arrives while a send job is queued.", "Replaying a gateway event or import does not double-count payment or create duplicate invoices.", "Customer statements reconcile to allocation totals; overdue calculations are correct at midnight in the workspace timezone."],
"first": "Manual invoice balance, due date, promise and dispute entry; computed next action; partial-payment balance; persisted collection brief and review history. No messages or payment providers are connected.",
"next": "Normalized invoices and payment allocations, import jobs, durable follow-up queue, dispute attachments, payment reconciliation, and approved channel delivery.",
"metrics": "Overdue balance by aging bucket; median days to settle; promises kept; operator time per follow-up; delivery failure and dispute rates.",
"risk": "Stale payment state can cause inappropriate reminders. Settlement must be checked immediately before a send and every provider event must be idempotent.",
"wave": "1", "complexity": "High"
},
"amc": {
"outcome": "Help equipment service businesses maintain asset histories, honor service entitlements, schedule visits, and renew annual maintenance contracts.",
"roles": "Owner defines service plans and pricing; dispatcher assigns visits; technician records work and evidence; customer confirms access and completion.",
"journey": "Register customer and asset → select contract and entitlement → plan preventive visits → assign technician → record service and parts → verify completion → issue renewal offer before expiry.",
"requirements": [
"Maintain customers, sites, asset serials, model, installation date, warranty information, and service history. Asset serial uniqueness is scoped to manufacturer and workspace.",
"Create contract plans with validity period, included visit count, coverage, exclusions, consumables policy, service hours, and renewal pricing; preserve signed plan versions.",
"Calculate remaining entitlement, contract state, upcoming renewal windows, and overdue planned visits. Chargeable extra visits must never consume nonexistent included entitlement.",
"Generate service schedules respecting contract dates, technician availability, customer windows, and visit duration. Rescheduling preserves the old appointment audit trail.",
"Provide technician work orders with checklist, parts used, readings, notes, before-and-after evidence, and start/completion timestamps. Support a mobile layout and retry-safe submission.",
"Require supervisor or customer verification for visit completion. Prevent duplicate completion events from consuming more than one entitlement.",
"Create renewal opportunities and offer documents; distinguish offered, accepted, invoiced, and renewed. New contracts retain links to the previous period.",
"Track parts charges and invoice references; show asset history and export service reports. Provide customer access limited to their own sites and equipment."
],
"entities": ["Site(id, customer_id, address, timezone)", "Asset(id, site_id, manufacturer, serial, model)", "PlanVersion(id, terms, coverage, included_visits)", "ServiceContract(id, asset_id, plan_version_id, start_date, end_date)", "Visit(id, contract_id, technician_id, slot, status, entitlement_consumed)", "ServiceEvidence(id, visit_id, file_id, type)", "Renewal(id, predecessor_id, offer_version, status)"],
"states": "Contract: Scheduled → Active → Expiring → Renewed / Expired. Visit: Planned → Assigned → In progress → Completed → Verified; cancellation and rebooking preserve entitlement.",
"integrations": "DoAide Scheduler for appointment availability; Inventory for parts; Invoicer for service and renewal billing; optional customer messages and private photo storage.",
"exclusions": "Technician payroll, live vehicle tracking, IoT diagnostics, automatic warranty approval, and a universal field-service ERP in the first release.",
"acceptance": ["A four-visit contract with three completed included visits reports one remaining visit.", "A service outside contract validity cannot consume an included entitlement.", "Repeated completion submissions consume at most one entitlement and preserve the same work order.", "Renewal acceptance creates a new contract period without overwriting prior service history.", "Technicians can access assigned work only; customers can access their own assets only."],
"first": "Customer and equipment entry, validity checks, remaining visits, renewal status, next-service validation, saved service plan and exports.",
"next": "Assets and visits as separate records, technician assignments, Scheduler adapter, completion evidence, renewals, and customer access.",
"metrics": "Renewal rate; overdue visits; entitlement utilization; first-visit resolution; service revenue per asset.",
"risk": "Concurrent completions can overconsume entitlement. Use transactions and unique completion keys; mobile evidence upload needs retry and conflict handling.",
"wave": "1", "complexity": "High"
},
"rfq": {
"outcome": "Give purchasing teams a comparable and auditable view of supplier offers, including commercial exclusions and delivery tradeoffs.",
"roles": "Requester defines specifications; buyer gathers and normalizes quotes; technical reviewer checks equivalence; budget approver authorizes the award.",
"journey": "Create purchase requirement → gather supplier quotes → map lines and units → verify taxes and exclusions → compare cost and lead time → record reviewer questions → approve supplier → generate purchase-order draft.",
"requirements": [
"Create RFQs with line specifications, quantities, units, delivery location, requested date, budget owner, and required quality documents.",
"Capture structured supplier offers and upload original documents. Preserve quote numbers, dates, validity periods, currency, payment terms, and source line references.",
"Normalize units and specification matches explicitly. Unsupported substitutions, missing freight, and uncertain tax treatment must remain visible review items.",
"Calculate landed cost using configurable treatment of discounts, goods tax, freight tax, packaging, and duties. Version exchange rates if cross-currency comparisons are enabled.",
"Display a side-by-side comparison and configurable evaluation factors. Cost ranking must not imply technical approval or automatically award work.",
"Track supplier clarification questions and revised offers while retaining the original quote and previous ranking.",
"Route award recommendations through value-based approval limits, record rationale and conflicts, and create a purchase-order draft with an idempotent reference.",
"Export the comparison, assumptions, and decision trail as spreadsheet/PDF; preserve a stable snapshot of the approved award."
],
"entities": ["RFQ(id, workspace_id, requester_id, currency, status)", "RFQLine(id, rfq_id, specification, quantity_decimal, unit)", "Supplier(id, workspace_id, contacts)", "QuoteVersion(id, supplier_id, rfq_id, valid_until, document_id)", "QuoteLine(id, quote_version_id, rfq_line_id, unit_price, taxes, freight)", "Evaluation(id, quote_version_id, reviewer_id, criteria, decision)", "Award(id, rfq_id, approved_snapshot, purchase_order_ref)"],
"states": "Draft → Open → Quotes received → Clarification → Evaluated → Approved → Awarded / Cancelled. Revised offers require a new comparison snapshot.",
"integrations": "DoAide Inventory for catalogue and receiving references; supplier email after explicit delivery setup; object storage; purchase-order export or accounting adapter.",
"exclusions": "Supplier credit checks, autonomous awards, purchase payments, unsupported tax advice, and complex international trade accounting in the initial INR pilot.",
"acceptance": ["500 units at INR 155 plus 18% goods tax and INR 1,800 freight total INR 93,250 under the documented initial tax assumption.", "Duplicate supplier identities and missing units are rejected or flagged before comparison.", "The comparison retains each quote version and all exclusions after a supplier revises its offer.", "An approver cannot approve beyond their configured authority, and an award can be traced to its approved quote snapshot.", "Multi-currency quotes are never combined without a visible dated conversion basis."],
"first": "Manual, single-item, INR comparisons of two or more suppliers; exact total cost arithmetic; goods tax, freight, lead time, exclusions, ranking, saved review and export.",
"next": "Multi-line RFQs, uploaded quote extraction, unit mapping, tax configuration, technical review, approval limits, and PO handoff.",
"metrics": "Time to comparable quotes; clarification cycles; quoted versus received cost variance; approval turnaround.",
"risk": "The cheapest non-equivalent offer can be misleading. Specification equivalence, tax basis, and exclusions must be evaluated independently from arithmetic.",
"wave": "2", "complexity": "Medium"
},
"tender": {
"outcome": "Help a small business prepare a complete bid pack from tender documents with traceable requirements and accountable evidence collection.",
"roles": "Bid owner manages deadlines and submission checklist; subject specialist assesses eligibility; contributor supplies evidence; authorized reviewer signs off the final pack.",
"journey": "Register opportunity → upload tender and amendments → extract cited requirements → classify mandatory and conditional items → map evidence → assign gaps → review the pack → export for submission.",
"requirements": [
"Maintain opportunity reference, authority, procurement portal link, timezone-aware deadline, clarification deadline, and amendment log.",
"Parse text and scanned tender files while preserving source pages, section references, document versions, and extraction confidence.",
"Extract eligibility criteria, technical specifications, mandatory forms, experience requirements, securities, submission steps, and deadline references into editable requirements.",
"Classify each requirement as mandatory, conditional, or informational with a human-confirmed interpretation; show source citations beside every item.",
"Map company documents and evidence to requirements; track document expiry, missing information, owner, due date, and reviewer outcome.",
"Track tender amendments and identify potentially affected requirements. Invalidate earlier readiness reviews when material source documents change.",
"Generate bid/no-bid review notes and a readiness checklist without guaranteeing eligibility, legal compliance, or award likelihood.",
"Export a numbered evidence index and bid-preparation packet; retain a separate manually recorded submission receipt and exact submitted version."
],
"entities": ["Opportunity(id, workspace_id, authority, reference, deadline_at)", "TenderDocument(id, opportunity_id, revision, checksum, supersedes_id)", "Requirement(id, document_id, locator, text, classification, verified_by)", "Evidence(id, workspace_id, document_id, expires_at)", "RequirementEvidence(requirement_id, evidence_id, review_status)", "BidTask(id, requirement_id, owner_id, due_at, status)", "SubmissionSnapshot(id, opportunity_id, manifest, receipt_ref)"],
"states": "Discovered → Under review → Bid / No bid → Preparing → Ready for authorized review → Submitted / Withdrawn / Closed. Readiness is invalidated by material amendments.",
"integrations": "DoAide Docs/PDF for conversion and export, private storage, company document library, optional calendar notifications. Portal automation is a separate later integration.",
"exclusions": "Automatic government-portal submission, bypassing CAPTCHAs, legal eligibility certification, invented documents, automatic bank guarantees, or assurance of tender success.",
"acceptance": ["Every extracted requirement links to an exact source document and page or line.", "An uncertain extraction is labeled for review instead of silently treated as satisfied.", "Missing or expired evidence blocks the relevant readiness requirement.", "A material amendment marks dependent approvals stale and records why.", "The exported manifest matches the reviewed document versions and preserves deadlines with timezone."],
"first": "Pasted text, explicit requirement-marker detection with original line numbers, exact-name evidence checklist, entered deadline, missing-item checks, saved preparation brief.",
"next": "Document upload and OCR, structured requirement editing, evidence files and expiry, task assignment, amendment handling, and packet export.",
"metrics": "Preparation time per bid; missing requirements at review; amendment-to-review delay; number of bids prepared without deadline misses.",
"risk": "A document parser can miss a material condition. The complete tender remains authoritative; all extracted requirements and readiness outcomes need human verification.",
"wave": "3", "complexity": "High"
},
"handover": {
"outcome": "Provide a room-by-room inspection and repair trail so a completed property or installation can be handed over with clear evidence and customer acceptance.",
"roles": "Project manager owns the site; inspector raises and verifies snags; contractor resolves assigned issues; customer reviews and accepts a specific handover packet.",
"journey": "Create property and inspection areas → record snags and photos → assign severity and repair owner → record fix evidence → independently verify fixes → build handover report → capture customer acceptance or exceptions.",
"requirements": [
"Create sites, units, rooms, inspection templates, responsible parties, target dates, and customer contact records.",
"Capture issues with location, category, severity, description, assignee, due date, and before photos. Support mobile capture with upload retry and file type restrictions.",
"Separate reported, acknowledged, in repair, fixed, and verified states; attach repair notes and after photos to the exact issue revision.",
"Provide assignment queues, overdue reports, bulk assignment, and contractor-limited access to relevant issues.",
"Require verification by an authorized reviewer; critical unresolved issues block handover, and any waived item needs an explicit reason and customer agreement.",
"Generate branded reports grouped by room and severity with issue history, evidence references, unresolved exceptions, and the report version.",
"Capture acceptance of the report through an expiring customer link; preserve identity evidence, version hash, timestamp, and comments.",
"Reopen defects without erasing the prior handover and manage post-handover warranty items as a related workflow."
],
"entities": ["Site(id, workspace_id, customer_id)", "Area(id, site_id, label, floor)", "Inspection(id, site_id, template_version, inspector_id)", "Snag(id, area_id, severity, assignee_id, state, version)", "RepairEvidence(id, snag_id, stage, file_id, timestamp)", "Verification(id, snag_version_id, reviewer_id, outcome)", "HandoverPacket(id, site_id, manifest_hash, accepted_at, exceptions)"],
"states": "Issue: Open → Assigned → Fixed → Verified; verification may return it to Open. Handover: Preparing → Reviewed → Sent → Accepted / Changes requested. Exceptions are explicit records.",
"integrations": "DoAide Realty for property references, Contracts for agreed scope, private image storage, report export, optional notifications.",
"exclusions": "Building-code certification, safety inspection guarantees, construction project ERP, automatic contractor payments, and treating an internal review as customer acceptance.",
"acceptance": ["Open and fixed-but-unverified snags appear as outstanding; all critical defects block handover.", "A contractor cannot verify or accept work outside its assigned access scope.", "Before and after images stay associated with the correct issue version.", "Accepted reports remain immutable when an issue is later reopened.", "Mobile issue capture survives upload retry without duplicating the snag."],
"first": "Manual site and client details; editable snag register with room, severity, assignee and status; review gating until all items are verified; saved checklist and exports.",
"next": "Normalized site/issue records, private photo uploads, contractor roles, independent verification, PDF packet, and customer acceptance links.",
"metrics": "Time to resolve snags; reopen rate; issues awaiting verification; days from practical completion to accepted handover.",
"risk": "Marking work fixed is not independent verification. Preserve separate actors and immutable acceptance evidence in the pilot.",
"wave": "2", "complexity": "Medium"
},
"orderdesk": {
"outcome": "Convert messy customer orders into explicit, reviewed sales-order drafts with catalogue matches, quantities, availability checks, and a dependable handoff.",
"roles": "Sales operator reviews incoming requests; catalogue manager maintains products and aliases; customer confirms ambiguous items; warehouse staff receive accepted order lines.",
"journey": "Receive message or uploaded order → extract requested items → match catalogue → resolve uncertainty → validate units, price and stock → obtain customer confirmation → reserve inventory → create order or invoice draft.",
"requirements": [
"Maintain SKUs, product names, customer aliases, units, pack sizes, prices, tax classes, and availability snapshots with source timestamps.",
"Capture pasted orders initially, then authorized WhatsApp messages, uploaded photos, and voice notes. Retain the source and extraction references.",
"Extract quantities, units, requested dates, variants, and substitutions. Never silently assume a quantity or choose between ambiguous catalogue matches.",
"Present source text beside proposed order lines, confidence, candidate matches, and explicit clarification questions.",
"Validate quantity and pack-size conversion; aggregate repeated SKUs when checking stock; preserve price list versions and authorized overrides.",
"Generate a confirmation summary with taxes, freight, shortages, backorders, and delivery details; track the version the customer confirmed.",
"Reserve stock transactionally only after confirmation and create an idempotent sales-order/invoice handoff. Release reservations on cancellation or expiry.",
"Track downstream status, provider delivery errors, import duplicates, and corrections without overwriting the original incoming order."
],
"entities": ["CatalogueItem(id, workspace_id, sku UNIQUE per workspace, unit, price_version)", "Alias(id, item_id, customer_id, text)", "IncomingOrder(id, customer_id, source_message_id UNIQUE, source_file_id)", "DraftLine(id, order_id, source_locator, quantity, unit, matched_sku, review_state)", "Confirmation(id, order_version_id, customer_id, confirmed_at)", "Reservation(id, order_line_id UNIQUE, quantity, expires_at, status)", "OrderHandoff(id, order_version_id UNIQUE, external_order_id, status)"],
"states": "Received → Parsed → Needs clarification / Ready for review → Customer confirmed → Reserved → Handed off / Cancelled. A commercial revision requires renewed confirmation.",
"integrations": "DoAide Inventory, Invoicer and Desk; official WhatsApp Business connection when configured; optional speech-to-text and OCR; private evidence storage.",
"exclusions": "Unattended ordering from uncertain text, accepting a payment screenshot as settlement, direct inventory deductions before confirmation, and unofficial messaging automation.",
"acceptance": ["A quantity-free or unknown-product line remains unresolved and cannot be marked reviewed.", "Two order lines for the same SKU are summed for the stock check.", "Ambiguous product names are not auto-selected even if one item is cheaper or more popular.", "A repeated incoming message or handoff event creates at most one order.", "Concurrent reservations never exceed available stock; cancellations release only their own reservations."],
"first": "Pasted quantity × SKU/name lines, exact catalogue matching, duplicate-SKU rejection, combined stock checks, subtotal calculation, saved draft and exports. No reservation occurs.",
"next": "Persistent catalogue, unit and pack rules, reviewed extraction from voice/photos, confirmation links, inventory reservations, and order handoff.",
"metrics": "Order-entry time; clarification rate; item/quantity correction rate; duplicate-order rate; reservation failures.",
"risk": "Product aliases and pack sizes are high-risk ambiguity points. Conservative matching and a customer-confirmed snapshot are required before stock or billing actions.",
"wave": "2", "complexity": "High"
},
"batch": {
"outcome": "Give a small manufacturer lot-level input traceability and understandable production costs, including output variance and expiry tracking.",
"roles": "Production planner creates batches; operator records consumption and output; inventory manager manages lots; quality reviewer releases or rejects the finished batch.",
"journey": "Version recipe → select input lots → issue production batch → record actual usage, waste and finished output → calculate cost → perform quality review → release inventory → trace affected lots when needed.",
"requirements": [
"Maintain finished products, recipes with effective versions, input units, expected quantities, yield assumptions, packaging, and standard overhead categories.",
"Receive ingredient lots with supplier reference, received quantity, expiry, unit cost, and quality status; prevent consumption of quarantined or expired lots without authorized exception policy.",
"Create planned batches and reserve input lots; record actual consumed quantities, returns, wastage, operator, timestamps, and output units.",
"Calculate consumed input cost, allocated labor/overhead, packaging, finished-unit cost, and variance to plan. Do not combine unlike units or confuse output attainment with mass yield.",
"Require batch quality checks and an authorized release decision; separate physical production from inventory availability for sale.",
"Maintain finished lots and expiry rules with traceability from finished batch to each input lot and from a supplier lot to all affected outputs.",
"Support corrections through reversal/adjustment events with reasons; released production history must never be silently overwritten.",
"Generate batch sheets, label data, expiry queues, and traceability reports. Export affected order references for a separately managed recall process."
],
"entities": ["RecipeVersion(id, product_id, version, yield_basis)", "IngredientLot(id, workspace_id, supplier_lot, unit, received_qty, expiry, status)", "ProductionBatch(id, product_id, recipe_version_id, planned_units, status)", "Consumption(id, batch_id, lot_id, quantity, unit_cost_snapshot)", "BatchCost(id, batch_id, category, amount_minor, allocation_basis)", "FinishedLot(id, batch_id, quantity, expiry, release_id)", "QualityRelease(id, batch_version_id, reviewer_id, decision, evidence)"],
"states": "Planned → Inputs reserved → In production → Produced → Quality hold → Released / Rejected. Corrections use linked adjustment events.",
"integrations": "DoAide Inventory for lot balances; supplier purchase references; label/PDF export; optional barcode readers; sales-order references for traceability.",
"exclusions": "Food or cosmetics regulatory certification, laboratory testing, automated shelf-life determination, advanced factory scheduling, and automatic recall communications.",
"acceptance": ["Ingredient costs plus overhead reconcile exactly to batch cost, with documented rounding for unit cost.", "Ingredient quantities in kg and litres are never summed as a single physical yield.", "A released batch exposes all consumed supplier lot references and their cost snapshots.", "Expired or quarantined inputs cannot be consumed through ordinary operator permissions.", "Concurrent batch reservations cannot overspend lot availability; corrections retain original events."],
"first": "Manual ingredient-lot consumption and unit costs; batch overhead; total and finished-unit cost; output attainment; entered expiry checks; traceability list and exports.",
"next": "Recipe versions, inventory lot ledger, reservations, usage adjustments, quality release, finished-lot movements, and forward/reverse traceability.",
"metrics": "Batch cost variance; output attainment; material wastage by unit; traceability lookup time; inventory adjustments per batch.",
"risk": "Incorrect units or mutable cost records invalidate traceability. Recipe, lot, and cost snapshots must be immutable after release and corrected through explicit adjustments.",
"wave": "3", "complexity": "High"
},
"fees": {
"outcome": "Help tuition businesses manage agreed fees, discounts, instalments, receipts, and outstanding balances while keeping parent communications accurate.",
"roles": "Centre administrator configures courses and fees; finance operator records receipts and adjustments; counsellor views student status; guardian accesses only linked student statements.",
"journey": "Enroll student in course → agree fee and concession → schedule instalments → record or reconcile receipt → allocate payment → issue statement → follow up on outstanding dues → handle withdrawal or refund.",
"requirements": [
"Maintain student references, guardian relationships, courses, batches, enrollment dates, and minimal necessary contact details with controlled access.",
"Create versioned fee agreements, discounts, sibling concessions, scholarships, and authorised overrides; retain the reason and approver for each concession.",
"Schedule instalments whose amounts reconcile to the net fee; support timezone-aware due dates, rescheduling, and explicit late-fee policies where configured.",
"Record receipts with unique references, date, method, amount, and evidence. Provider-confirmed receipts must be distinct from manually entered records.",
"Allocate payments to instalments, show due-now versus total outstanding, and support adjustments, withdrawals, credits, and refunds as auditable transactions.",
"Generate numbered receipts and student statements with stable snapshots and export formats. Prevent duplicate receipt numbers within a centre's numbering scheme.",
"Queue reminders only for eligible guardians using configured preferences, pause rules, business hours, and confirmed current balance.",
"Provide centre-level aging and reconciliation reports plus limited parent access; separate finance permission from academic records and teaching access."
],
"entities": ["Student(id, workspace_id, external_reference)", "GuardianLink(student_id, guardian_id, access_scope)", "Enrollment(id, student_id, course_id, batch_id, status)", "FeeAgreement(id, enrollment_id, version, gross_minor, discount_minor)", "Instalment(id, agreement_id, due_date, amount_minor)", "Receipt(id, workspace_id, reference UNIQUE per workspace, payment_event_id)", "FeeAllocation(id, receipt_id, instalment_id, amount_minor)", "FeeAdjustment(id, agreement_id, reason, approver_id, amount_minor)"],
"states": "Enrollment: Pending → Active → Completed / Withdrawn. Fee agreement: Draft → Agreed → Partially paid → Settled / Adjusted. Refunds and reversals remain separate ledger events.",
"integrations": "PrepKraft or course enrollment export, optional payment gateway, authorized email/WhatsApp provider, printable receipts, accounting export.",
"exclusions": "Full school ERP, academic grading, attendance tracking, student lending, automatic penalties without a configured policy, and collecting unnecessary child information.",
"acceptance": ["A fee of INR 24,000 less INR 2,000 discount yields INR 22,000; instalments must sum to that net amount.", "With INR 8,000 paid against an INR 11,000 due instalment, due-now is INR 3,000 and total outstanding is INR 14,000.", "Duplicate payment references are rejected; repeated provider callbacks do not double-credit a student.", "An authorized refund or reversal adjusts the ledger and statement without deleting the original receipt.", "A guardian cannot enumerate or view another family's student or fee record."],
"first": "Manual student/course entry, fee and discount validation, instalment schedule, unique receipt references, oldest-first payment allocation, statement and due-now calculations, saved record/export.",
"next": "Student/enrollment models, immutable fee ledger, receipt templates, payment callbacks, parent access, concessions approval, refunds and reminder delivery.",
"metrics": "Outstanding fees by batch; collection rate by due date; reconciliation differences; receipt issue time; reminder-to-payment conversion.",
"risk": "Children's records and financial information need restricted access. Use student references where possible and isolate guardian visibility from staff-only notes.",
"wave": "2", "complexity": "Medium"
},
"renew": {
"outcome": "Give a small company a dependable calendar of contract renewals and cancellation windows with a named owner and an auditable decision.",
"roles": "Team member submits a service; budget owner reviews cost and usage; operations owner tracks renewal deadlines; finance confirms invoices and final decisions.",
"journey": "Register service and owner → record contract terms and cost → verify notice window → remind accountable owner → decide renew, cancel, or negotiate → record vendor confirmation → update next contract period.",
"requirements": [
"Maintain vendors, contracts, subscription identifiers, owners, departments, billing cadence, currencies, seats, and supporting invoices or terms.",
"Record next renewal date, term length, auto-renew setting, notice period, and explicit calendar or business-day semantics. Cite the source clause.",
"Calculate notice deadlines and annualized committed cost with visible assumptions; separate billed spend from annualized run rate.",
"Create reminder milestones before notice deadlines with owner acknowledgement and backup escalation when ownership is missing or stale.",
"Capture renew/cancel/negotiate decisions, rationale, approver, negotiated terms, and relevant version. A decision does not itself cancel a vendor contract.",
"Track cancellation or renewal requests and vendor confirmations as distinct events with evidence and the actual effective date.",
"Flag duplicate subscriptions, price increases, missing owners, and potentially unused seats from verified inputs; avoid inventing usage metrics.",
"Export a renewal calendar and portfolio report, preserve past terms, and create the next period from confirmed vendor information."
],
"entities": ["Vendor(id, workspace_id, name)", "Subscription(id, vendor_id, owner_id, department_id, external_ref)", "ContractTerm(id, subscription_id, start, renewal, notice_rule, source_document_id)", "PriceVersion(id, term_id, amount_minor, currency, cadence, seats)", "RenewalDecision(id, term_id, actor_id, decision, rationale, approved_at)", "VendorAction(id, term_id, requested_action, sent_at, confirmed_at, evidence_id)", "Reminder(id, term_id, due_at, owner_id, state, idempotency_key)"],
"states": "Tracked → Review due → Decision recorded → Action requested → Vendor confirmed → Renewed / Ended. An overdue notice window remains visible even after an internal decision.",
"integrations": "DoAide Contracts, CSV or invoice import, optional calendar feed, authorized email delivery, private terms storage; direct vendor cancellation is a later per-provider adapter.",
"exclusions": "Bank-account scanning, automatic vendor cancellation, unsupported spend-saving claims, software usage surveillance, and interpreting contractual notice rights as legal advice.",
"acceptance": ["INR 3,600 monthly annualizes to INR 43,200; quarterly and annual cadences use the documented factors.", "A 30-calendar-day notice period produces the correct deadline across month and year boundaries.", "The app distinguishes a recorded cancellation decision from vendor-confirmed cancellation.", "Changing the renewal date recomputes unsent reminders without producing duplicates.", "Historical prices and terms remain accessible after renewal and ownership changes."],
"first": "Manual vendor, owner, cost, cadence and date entry; annualized cost; calendar-day notice deadline; decision review check; saved brief and exports.",
"next": "Contract term history, evidence uploads, real reminder delivery and acknowledgements, calendar export, renewal-period rollover, and price-change reports.",
"metrics": "Renewals with assigned owners; decisions made before notice deadline; missed cancellation windows; confirmed annual committed cost changes.",
"risk": "Notice periods may use business days or special clauses. The pilot must capture the rule and source rather than assume all contracts use simple calendar subtraction.",
"wave": "2", "complexity": "Low to medium"
},
"sop": {
"outcome": "Turn a business procedure into an approved, versioned guide that employees can follow and acknowledge, with evidence of what changed and who learned it.",
"roles": "Process owner writes procedures; reviewer verifies accuracy and safety; supervisor assigns training; employee reads and acknowledges the version assigned to them.",
"journey": "Capture demonstration or write steps → draft structured procedure → review hazards and escalation → publish immutable version → assign staff → complete acknowledgement and assessment → revise and reassign affected staff.",
"requirements": [
"Create procedure collections, owners, audience, prerequisites, tools, ordered steps, safety warnings, escalation contacts, and effective dates.",
"Support manual authoring first, then uploaded recordings and transcripts with timestamp-linked draft steps and selected screenshots. Generated instructions require human review.",
"Provide editable step order, images, checklists, branching notes, and templates. Record sources and author changes in a version history.",
"Route drafts to reviewers and publish immutable versions; retain prior versions, change summaries, and retirement dates.",
"Assign published versions to employees or teams with due dates and reminders; ensure new hires receive current procedures.",
"Capture authenticated employee acknowledgements against an exact published version; never treat a manager-entered note as an employee's own acknowledgement.",
"Offer short reviewer-approved assessments, pass thresholds, retraining, and supervisor signoff for designated procedures.",
"Report current versus stale training, export printable guides, and allow controlled offline copies with a visible version and expiry policy."
],
"entities": ["Procedure(id, workspace_id, owner_id, category)", "ProcedureVersion(id, procedure_id, revision, state, effective_at, checksum)", "Step(id, version_id, position, instruction, evidence_locator, media_id)", "PublicationReview(id, version_id, reviewer_id, outcome)", "TrainingAssignment(id, employee_id, version_id, due_at)", "Acknowledgement(id, assignment_id UNIQUE, actor_id, acknowledged_at)", "AssessmentAttempt(id, assignment_id, question_version, score, passed)"],
"states": "Procedure: Draft → In review → Published → Superseded / Retired. Training: Assigned → In progress → Acknowledged → Assessed / Retraining required.",
"integrations": "DoAide Docs for export, optional transcription provider, private media storage, employee directory or Payroll read-only roster adapter, authorized reminder delivery.",
"exclusions": "Automatic safety certification, replacing professional training, covert employee monitoring, using acknowledgements as legal waivers, and publishing generated steps without review.",
"acceptance": ["Published steps cannot change in place; edits create a new draft version.", "An acknowledgement of version 1 is stale after version 2 becomes the assigned version.", "An employee cannot acknowledge on behalf of another employee.", "Every generated step can be traced to its transcript or manually authored source.", "Retired procedures cannot receive new assignments, while historical acknowledgements remain auditable."],
"first": "Manual steps, owner and safety notes; procedure version; printable checklist; manually recorded acknowledgement versions and stale-count calculation; saved revision history.",
"next": "Normalized immutable procedure versions, reviewer publication, team assignments, authenticated acknowledgements, assessments, and recording-to-draft pipeline.",
"metrics": "Procedure publication time; staff current on assigned versions; overdue training; assessment pass/retraining rates; revision-to-reacknowledgement delay.",
"risk": "Generated procedure errors can affect real operations. Reviewers must verify sequence, hazards, and escalation; sample acknowledgements are never verified employee actions.",
"wave": "3", "complexity": "High"
},
"claimpack": {
"outcome": "Help a merchant assemble a factual and complete evidence packet for a payment dispute, with a clear deadline and traceable source records.",
"roles": "Support operator gathers customer conversations; operations supplies fulfillment evidence; finance owns the dispute and deadline; authorized reviewer releases the packet for submission.",
"journey": "Register dispute and actual provider deadline → link order and reason → collect source evidence → map evidence to a versioned provider checklist → write factual chronology → review and export → separately record submission and outcome.",
"requirements": [
"Maintain dispute reference, payment provider, reason code, order, amount, currency, exact response deadline, timezone, assigned owner, and source of the deadline.",
"Use versioned provider-specific evidence templates with visible applicability dates; permit manual requirements where an adapter is unavailable.",
"Collect original order details, delivery/tracking proof, product descriptions, customer communications, refund records, and timestamps in private storage.",
"Map each factual statement and timeline event to evidence; distinguish merchant assertions, carrier claims, customer claims, and verified provider records.",
"Flag missing documents, unreadable files, conflicting dates, oversized attachments, and unsupported formats before packet completion.",
"Generate an editable factual response and evidence index without inventing delivery, consent, identity, or customer acknowledgement.",
"Export a provider-compatible packet with immutable source hashes and approved redactions. Reviewers must confirm the precise version being released.",
"Track manual submission receipts and outcomes first; add provider submission APIs only with explicit account configuration, idempotency, and visible delivery confirmation."
],
"entities": ["Dispute(id, workspace_id, provider_ref, reason_code, amount_minor, currency, deadline_at)", "OrderSnapshot(id, dispute_id, external_order_id, captured_at, data_hash)", "EvidenceFile(id, dispute_id, kind, file_id, checksum, source, captured_at)", "EvidenceRequirement(id, template_version_id, reason_code, required_kind)", "TimelineEvent(id, dispute_id, occurred_at, statement, evidence_id)", "PacketVersion(id, dispute_id, manifest, content_hash, reviewed_by)", "Submission(id, packet_version_id, provider_ref, submitted_at, receipt, outcome)"],
"states": "Received → Gathering evidence → Needs review → Packet approved → Submitted → Won / Lost / Withdrawn. Export does not mean submission and completeness does not predict outcome.",
"integrations": "DoAide Desk for conversations, ecommerce order export, tracking-provider records, selected payment gateway in test mode, private storage, PDF/image export.",
"exclusions": "Guaranteed dispute wins, legal representation, fabricated evidence, changing provider deadlines, autonomous submission, or storing full payment-card data.",
"acceptance": ["A not-received dispute without delivery evidence shows the missing requirement explicitly.", "A filename alone is never described as verified file contents or proof of delivery.", "Every generated factual assertion has an evidence reference or is clearly labeled a merchant assertion.", "The released packet retains its evidence hashes and cannot be silently changed after submission.", "Provider retries create one submission and the UI distinguishes exported, submitted, and acknowledged states."],
"first": "Manual dispute metadata and factual timeline; reason-based internal checklist; evidence references; deadline and missing-type checks; saved preparation record and export. No file contents are verified.",
"next": "Private evidence upload, order/support imports, provider-specific template validation, timeline citations, immutable packet generation and submission receipt tracking.",
"metrics": "Time to reviewed packet; missing-evidence rate; deadline misses; provider acceptance of packet format; outcome tracking by reason without causal claims.",
"risk": "Evidence labels can imply verification that never happened. Distinguish references, stored files, extracted content, and externally confirmed facts at every step.",
"wave": "3", "complexity": "High"
}}

COMMON = """## Shared implementation requirements

Workspace isolation applies to records, searches, attachments, exports, job runs, and audit history. The pilot needs owner, operator, reviewer, and read-only roles plus separately scoped external actors where relevant. Backend authorization is authoritative; UI visibility alone is not authorization.

Use exact monetary arithmetic, explicit currencies, workspace timezone, immutable event timestamps in UTC, unique integration references, and optimistic version checks. Unknown, incomplete, stale, and failed states must be visible. A retry must not duplicate a business action.

All uploaded files require size/type limits, malware screening, private storage, checksums, expiring authorized download links, configurable retention, and deletion handling. Any AI extraction must preserve citations, record model/version, expose uncertainty, and require review before externally consequential actions. No uploaded customer data is sent to a provider until its account and data-use configuration are selected.

The interface must work at 390px and desktop widths, support keyboard use, label controls, expose errors accessibly, and distinguish example data from real saved records. Empty states, invalid inputs, loading, retries, authorization failures, stale versions, and integration failures are part of the deliverable.

## Delivery milestones

M0 — First workflow: completed previously. Saved records, deterministic calculations, review checks and history remain available as intake tools.

M1 — Pilot core: normalize the product entities, introduce role-aware shared workspaces, private files, business state machines, search/filtering, import/export, and the product-specific next milestone. Exercise complete journeys with synthetic and consenting pilot data.

M2 — Integrations and reliability: deliver adapters only after inspecting their actual contracts, add durable jobs, signed webhooks, idempotency, reconciliation, retries, notification preferences, and support diagnostics. Use provider test modes first.

M3 — Production release: run cross-workspace and role tests, restore a backup into an isolated environment, check accessibility and responsive journeys, measure load against an agreed fixture size, and verify monitoring and rollback. Build immutable runtime images off-server in accordance with STRATEGY.md. Production release is a later milestone, not the status of this implementation.

## Validation and completion evidence

Unit tests must cover calculations and invalid boundary inputs; API tests must cover authorization, persistence, ownership checks, optimistic concurrency, state changes, and audit events. Integration tests must cover duplicate/out-of-order callbacks and provider failure. Browser tests must cover the principal journey, a failed input, saved-record reopen, mobile layout, and export. Human review is required for domain interpretation, contractual terms, and externally supplied evidence.

Completion evidence consists of a release checklist, test output, tested migration, API contract, example exports, pilot findings, and a rollback/restore record. A passing health check or landing page alone does not constitute completion of the product.

## Delivery responsibilities and assumptions

Implementation covers design, application code, database migrations, tests, developer setup, and operational handoff. Business ownership must supply representative source documents, approved templates, interpretation of business rules, provider accounts where required, and pilot acceptance feedback. These inputs can arrive during development; they do not block the local first workflow.

The initial design targets small businesses, INR examples, English UI, and Asia/Kolkata business dates. Additional currencies, languages, statutory content, multi-branch policies, and unusual approval structures require explicit requirements. No delivery date or fixed commercial budget is implied by this scope. Effort estimates should be established after pilot discovery and adapter inspection.
"""


from backend.release_notes import CAPABILITIES, COMMON_IMPLEMENTED, REMAINING


def build():
    out = ROOT / "docs" / "scopes"
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for p in PRODUCTS:
        slug = p["slug"]
        s = SPECS[slug]
        prefix = slug.upper()
        chunks = [f"# DoAide {p['name']} Scope of Work\n\nVersion 1.2 · 28 October 2026 · Engineering scope and acceptance baseline\n",
            f"## Outcome and target customer\n\n{s['outcome']}\n\nPrimary customer: {p['buyer']}. Pilot complexity: {s['complexity']}. Delivery wave: {s['wave']}.\n",
            f"## Users and responsibilities\n\n{s['roles']}\n",
            f"## Principal workflow\n\n{s['journey']}\n",
            "## Functional scope\n\n" + "\n\n".join(f"{prefix}-{i:02d} — {r}" for i,r in enumerate(s["requirements"],1)) + "\n",
            f"## Business states\n\n{s['states']}\n\nIntake records retain Draft, Reviewed, and Archived checkpoints. The Operations tab adds the product-specific business transitions with server-side gates. External provider delivery and third-party outcomes are recorded separately.\n",
            "## Planned domain data model\n\nEvery business entity is workspace-scoped directly or through a validated parent. IDs are server-generated.\n\n" + "\n\n".join("- " + e for e in s["entities"]) + "\n",
            "## First workflow input contract\n\n" + "\n\n".join(f"- {f['label']}: {f['type']}; {'required' if f.get('required') else 'optional'}." + (" Row columns: " + ", ".join(c['label'] for c in f['columns']) + "." if f['type']=='rows' else "") for f in p["fields"]) + "\n",
            f"## Integrations and dependencies\n\n{s['integrations']}\n\nThe local implementation provides file/manual workflows and configured adapters where documented. Live provider accounts and cross-product API validation remain deployment dependencies; see BUILD_STATUS.md.\n",
            f"## Excluded from the initial product release\n\n{s['exclusions']}\n",
            "## Product acceptance scenarios\n\n" + "\n\n".join(f"{prefix}-AC-{i:02d} — {r}" for i,r in enumerate(s["acceptance"],1)) + "\n",
            f"## What is implemented now\n\n{CAPABILITIES[slug]}\n\n{COMMON_IMPLEMENTED} Audit storage is not externally tamper-proof.\n",
            f"## Next implementation milestone\n\n{REMAINING}\n",
            f"## Product measures\n\n{s['metrics']}\n\nThese are proposed measurement definitions. No adoption, savings, or revenue performance is claimed.\n",
            f"## Principal risk and control\n\n{s['risk']}\n", COMMON,
            f"\n## Current API surface\n\nPOST /api/products/{slug}/preview validates inputs and calculates a reviewable result. POST /api/products/{slug}/records saves a draft. GET /api/records?product={slug} lists this workspace's records with offset/limit pagination. GET/PUT /api/records/{{id}} reads or revises a record with optimistic version checks. POST /api/records/{{id}}/status applies an allowed internal transition. GET /api/records/{{id}}/audit returns authorized revision history. GET /api/records/{{id}}/export returns a fresh dated JSON result. GET /api/records/{{id}}/operations returns the workflow, typed forms, resources, documents and activity. POST /api/records/{{id}}/items/{{kind}} manages operational entities. POST /api/records/{{id}}/actions/{{action}} runs a version-checked, idempotent business command. See /docs on the local server for the generated OpenAPI interface.\n"]
        (out / f"{slug}.md").write_text("\n".join(chunks))
        index.append(f"| [{p['name']}](scopes/{slug}.md) | {s['wave']} | {s['complexity']} | Operational local workflows; provider and pilot validation |")
    (ROOT / "docs" / "SCOPE_OF_WORK.md").write_text("""# DoAide Twelve Product Delivery Scope

Version 1.2 · 28 October 2026

This engineering scope covers Scope, Collect, AMC, RFQ, Tender, Handover, OrderDesk, Batch, Fees, Renew, SOP, and ClaimPack. Each product has an individual scope describing customer outcomes, roles, workflow, numbered functional requirements, domain entities, business states, integrations, exclusions, acceptance scenarios, current implementation, and subsequent milestones.

The local modular application now contains operational workflows for all twelve products. Shared teams, evidence files, approval links, immutable documents, financial and stock ledgers, background jobs and audit history support the product-specific commands. This remains a local operational build, with provider accounts, domain acceptance and production validation tracked separately in BUILD_STATUS.md.

## Product scope index and build order

| Product | Wave | Pilot complexity | Next milestone |
| --- | --- | --- | --- |
""" + "\n".join(index) + """

## Architecture and repository decision

The source lives under products/doaide-suite in the current DoAide workspace. This keeps all newly authorized work reviewable without altering existing product checkouts or production deployments. The first version uses FastAPI, Python's SQLite interface, and React/Vite, consistent with the broad application patterns already present in DoAide. Currency calculations use Decimal. Product input contracts drive validation and form rendering; each product has a separate calculation branch with product-specific rules.

SQLite is the local operational store. Records belong to shared workspaces, with owner/operator/reviewer/viewer memberships and invitations. Separate expiring links scope external client, guardian and contractor access. Email verification and password recovery use expiring one-use links through the configurable email queue; provider delivery still needs pilot validation. Sessions use random opaque tokens, server-side hashed token storage, HttpOnly cookies, and an expiry. Passwords are scrypt-hashed with per-password salts. This is a local development authentication implementation, not a completed identity platform.

The additive schema includes memberships, entities, financial entries, stock movements, files, frozen documents, decisions, jobs and idempotency records. Product entity fields use validated JSON within typed resource rows. A pilot must assess the production database and scale requirements before migration. The existing portfolio uses PostgreSQL; InsForge is another available option, but its saved CLI authentication failed during setup. No cloud resources were created and no production credentials were copied into this repository. Backend selection for a pilot should follow the existing operational strategy and verified service access.

## Shared platform backlog

PLAT-01 — Identity and tenancy: verified identity, password reset, team memberships, roles, external-actor access, revoked sessions, and service account boundaries. Test cross-workspace access on every record, export, job and file operation.

PLAT-02 — Data and migrations: normalized product tables, versioned migrations, explicit money/currency types, timezone-aware timestamps, import batches, unique business references, optimistic locking and immutable event history.

PLAT-03 — Files and extraction: private uploads, content hashes, file limits, malware screening, OCR/extraction workers, source locators, retention, authorized download, and deletion workflows.

PLAT-04 — Durable work: transactional outbox, deduplicated job IDs, exponential retry with limits, dead-letter inspection, provider idempotency, signed callback validation, and reconciliation jobs.

PLAT-05 — Integrations: inspect actual DoAide product APIs before writing adapters; use separate test accounts; implement health/status checks and feature flags. An unavailable adapter must leave a clearly marked manual workflow.

PLAT-06 — Commercial controls: tenant plans, entitlements, billing in provider test mode, usage budgets and accounting exports. Pricing and willingness to pay remain discovery work.

PLAT-07 — Experience: keyboard and mobile journeys, useful empty states, accessible errors, import previews, date/currency formatting, confirmation of irreversible business actions, and version-aware review screens.

PLAT-08 — Operations: structured logs with sensitive fields excluded, error reporting, health/readiness checks, service limits, encrypted backups, verified restoration, immutable off-server builds, rollback artifacts, and data retention documentation.

## Delivery sequence

Wave 0 establishes the shared local application and all twelve first workflows, along with individual scopes and domain/API tests. This is the work started in this change.

Wave 1 deepens Scope, Collect, and AMC into pilots because they share client, invoice, contract, and scheduling concepts. Pilot discovery determines the actual API dependencies and required external communication channels.

Wave 2 adds RFQ, Handover, OrderDesk, Fees, and Renew using the tested shared identity, file, job, and document components. RFQ and Renew can precede provider-heavy workflows when adapter access is incomplete.

Wave 3 adds the document- and evidence-heavy Tender, Batch, SOP, and ClaimPack pilots. These require stronger versioning, source evidence, domain review, and in Batch's case a transactional inventory ledger.

This sequence is a dependency plan, not an instruction to ship every product simultaneously. Each pilot should complete its own acceptance scenarios before expansion. Calendar dates and budget estimates should be set after inspecting real source samples, provider access, and integration contracts; no fixed delivery promise is made here.

## Deliverables for each product

1. Versioned product scope and acceptance criteria.
2. User journeys, responsive interface, and empty/error/conflict states.
3. Backend input contracts, domain logic, authorization and durable records.
4. Tested domain migrations and a documented API.
5. Import/export and evidence handling where specified in the individual scope.
6. Verified integration adapters, retry behavior, and operator diagnostics where applicable.
7. Domain, API, integration and browser validation evidence.
8. Developer setup, example fixtures, operational runbook, backup/restore and rollback instructions.

## Current milestone boundaries

All twelve products have operational local workflows described in their current implementation sections. External sending is disabled by default; credentials and explicit server configuration are required to enable provider jobs. No live messages, payments, bids, disputes or production deployments were performed during development.

The suite is not certified as completing every production requirement in this scope. Configured email/recovery delivery, existing-product adapters, configured billing-provider acceptance, pilot-approved templates and current browser acceptance remain open. Additional local product gaps are tracked in REMAINING_SCOPE.md. Plan entitlements, usage budgets, test-mode billing adapters and reporting are now implemented. Scope requirements are retained rather than silently reduced. See BUILD_STATUS.md for tested behavior and remaining release work.

## Dependency and scope management

Business stakeholders should supply anonymized representative inputs, approved templates, definitions of pricing/tax/notice rules, and pilot feedback. Provider-specific behavior must be verified against current official documentation when implementing the adapter. Requirements that change evidence semantics, monetary rules, authority, or external actions need a versioned scope update and corresponding acceptance tests.

Reuse existing DoAide products through adapters rather than direct cross-product database writes. Keep stable external references and idempotency keys. Existing products retain their data ownership and release processes. No production server should build this application; follow the workspace STRATEGY.md for image creation, deployment, health checks, and rollback.

## Engineering references

- FastAPI security primitives: https://fastapi.tiangolo.com/tutorial/security/
- Python sqlite3 and transaction behavior: https://docs.python.org/3/library/sqlite3.html
- Vite development and build workflow: https://vite.dev/guide/
- Suite product index: [PRODUCT_INDEX.md](../PRODUCT_INDEX.md)
- Local portfolio reference: /Users/dev/projects/doaide/PRODUCT_INDEX.md
- Deployment requirements: [STRATEGY.md](../STRATEGY.md)
""")
    print(f"Wrote {len(PRODUCTS)} individual scopes and the master delivery scope.")


if __name__ == "__main__":
    build()
