# DoAide Fees Scope of Work

Version 1.2 · 28 October 2026 · Engineering scope and acceptance baseline

## Outcome and target customer

Help tuition businesses manage agreed fees, discounts, instalments, receipts, and outstanding balances while keeping parent communications accurate.

Primary customer: Coaching & tuition centres. Pilot complexity: Medium. Delivery wave: 2.

## Users and responsibilities

Centre administrator configures courses and fees; finance operator records receipts and adjustments; counsellor views student status; guardian accesses only linked student statements.

## Principal workflow

Enroll student in course → agree fee and concession → schedule instalments → record or reconcile receipt → allocate payment → issue statement → follow up on outstanding dues → handle withdrawal or refund.

## Functional scope

FEES-01 — Maintain student references, guardian relationships, courses, batches, enrollment dates, and minimal necessary contact details with controlled access.

FEES-02 — Create versioned fee agreements, discounts, sibling concessions, scholarships, and authorised overrides; retain the reason and approver for each concession.

FEES-03 — Schedule instalments whose amounts reconcile to the net fee; support timezone-aware due dates, rescheduling, and explicit late-fee policies where configured.

FEES-04 — Record receipts with unique references, date, method, amount, and evidence. Provider-confirmed receipts must be distinct from manually entered records.

FEES-05 — Allocate payments to instalments, show due-now versus total outstanding, and support adjustments, withdrawals, credits, and refunds as auditable transactions.

FEES-06 — Generate numbered receipts and student statements with stable snapshots and export formats. Prevent duplicate receipt numbers within a centre's numbering scheme.

FEES-07 — Queue reminders only for eligible guardians using configured preferences, pause rules, business hours, and confirmed current balance.

FEES-08 — Provide centre-level aging and reconciliation reports plus limited parent access; separate finance permission from academic records and teaching access.

## Business states

Enrollment: Pending → Active → Completed / Withdrawn. Fee agreement: Draft → Agreed → Partially paid → Settled / Adjusted. Refunds and reversals remain separate ledger events.

Intake records retain Draft, Reviewed, and Archived checkpoints. The Operations tab adds the product-specific business transitions with server-side gates. External provider delivery and third-party outcomes are recorded separately.

## Planned domain data model

Every business entity is workspace-scoped directly or through a validated parent. IDs are server-generated.

- Student(id, workspace_id, external_reference)

- GuardianLink(student_id, guardian_id, access_scope)

- Enrollment(id, student_id, course_id, batch_id, status)

- FeeAgreement(id, enrollment_id, version, gross_minor, discount_minor)

- Instalment(id, agreement_id, due_date, amount_minor)

- Receipt(id, workspace_id, reference UNIQUE per workspace, payment_event_id)

- FeeAllocation(id, receipt_id, instalment_id, amount_minor)

- FeeAdjustment(id, agreement_id, reason, approver_id, amount_minor)

## First workflow input contract

- Student reference or name: text; required.

- Course or batch: text; required.

- Course fee · INR: number; required.

- Agreed discount · INR: number; required.

- Instalment schedule: rows; required. Row columns: Due date, Amount · INR.

- Recorded payments: rows; required. Row columns: Receipt reference, Payment date, Amount · INR.

## Integrations and dependencies

PrepKraft or course enrollment export, optional payment gateway, authorized email/WhatsApp provider, printable receipts, accounting export.

The local implementation provides file/manual workflows and configured adapters where documented. Live provider accounts and cross-product API validation remain deployment dependencies; see BUILD_STATUS.md.

## Excluded from the initial product release

Full school ERP, academic grading, attendance tracking, student lending, automatic penalties without a configured policy, and collecting unnecessary child information.

## Product acceptance scenarios

FEES-AC-01 — A fee of INR 24,000 less INR 2,000 discount yields INR 22,000; instalments must sum to that net amount.

FEES-AC-02 — With INR 8,000 paid against an INR 11,000 due instalment, due-now is INR 3,000 and total outstanding is INR 14,000.

FEES-AC-03 — Duplicate payment references are rejected; repeated provider callbacks do not double-credit a student.

FEES-AC-04 — An authorized refund or reversal adjusts the ledger and statement without deleting the original receipt.

FEES-AC-05 — A guardian cannot enumerate or view another family's student or fee record.

## What is implemented now

Enrollment/guardian records, approved fee/discount agreements, instalment schedules and FIFO allocation, immutable receipt/refund/credit/charge entries, numbered frozen receipt PDFs, limited guardian statements, approved unpaid-instalment amendments preserving receipts, separate charge allocations, timezone-aware aging reports, opted-in reminders and payment-link adapter. Concession category/authority, immutable assessed late-fee policies, capped fixed/daily assessments, payment method/evidence, reconciled withdrawal and academic-only access excluding financial records and exports.

Shared workspaces with owner/operator/reviewer/viewer roles, recipient-bound invitations, email verification/recovery with one-use tokens and session revocation, optimistic workflow versions, transactional command idempotency, private bounded uploads, source extraction/OCR queue, configurable ClamAV requirement and file-retention tooling, frozen PDF bytes and checksum manifests, scoped external links, durable outbox/retries/visible blocked jobs, workspace stock/financial ledgers, application audit events, pagination, all-product portfolio/aging/accounting exports, optional Stripe test checkout/portal with signed-event reconciliation, server-owned product plans and atomic creation/seat/source-byte/job budgets, worker readiness/owner diagnostics, backup/isolated-restore tooling and off-server image packaging. Schema-4 academic access controls, bounded request bodies and persistent rate limits, authenticated encrypted backups, workspace-data erasure with preview/confirmation/isolation, and continuous test/build/container checks. Schema-5 durable authority activation pins service business/warehouse ownership; connected operations stay pending until external confirmation and never silently fall back to local execution. Audit storage is not externally tamper-proof.

## Next implementation milestone

Validate the updated UI in desktop/mobile browsers and accessibility checks; review representative pilot inputs and final document formats; configure and exercise approved provider accounts; apply the Invoicer adapter migration to its test deployment; complete the remaining portfolio integrations listed in REMAINING_SCOPE.md, target-host monitoring/restore/rollback and production policy review. Local workflow implementation and automated tests do not establish production acceptance. See ../BUILD_STATUS.md.

## Product measures

Outstanding fees by batch; collection rate by due date; reconciliation differences; receipt issue time; reminder-to-payment conversion.

These are proposed measurement definitions. No adoption, savings, or revenue performance is claimed.

## Principal risk and control

Children's records and financial information need restricted access. Use student references where possible and isolate guardian visibility from staff-only notes.

## Shared implementation requirements

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


## Current API surface

POST /api/products/fees/preview validates inputs and calculates a reviewable result. POST /api/products/fees/records saves a draft. GET /api/records?product=fees lists this workspace's records with offset/limit pagination. GET/PUT /api/records/{id} reads or revises a record with optimistic version checks. POST /api/records/{id}/status applies an allowed internal transition. GET /api/records/{id}/audit returns authorized revision history. GET /api/records/{id}/export returns a fresh dated JSON result. GET /api/records/{id}/operations returns the workflow, typed forms, resources, documents and activity. POST /api/records/{id}/items/{kind} manages operational entities. POST /api/records/{id}/actions/{action} runs a version-checked, idempotent business command. See /docs on the local server for the generated OpenAPI interface.
