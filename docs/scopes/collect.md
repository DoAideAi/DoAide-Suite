# DoAide Collect Scope of Work

Version 1.2 · 28 October 2026 · Engineering scope and acceptance baseline

## Outcome and target customer

Give a service business a reliable view of overdue money, payment commitments, and disputes, with a controlled follow-up workflow that stops when payment is confirmed.

Primary customer: Service businesses & distributors. Pilot complexity: High. Delivery wave: 1.

## Users and responsibilities

Business owner configures collection policies; finance operator reconciles invoices and payments; account manager handles relationship-sensitive cases; customer sees only their balance and approved payment options.

## Principal workflow

Import invoices and receipts → reconcile balances → rank due follow-ups → record a dispute or promise → review a message → deliver through an enabled channel → reconcile payment events → close or escalate the case.

## Functional scope

COLLECT-01 — Import invoice and customer CSVs with a preview, field mapping, duplicate detection, row-level errors, and reversible import batches. Support invoice IDs from Invoicer and external systems.

COLLECT-02 — Maintain invoice totals, credits, payments, allocations, due dates, currency, and outstanding balances using exact decimal or minor-unit arithmetic. Do not sum unlike currencies.

COLLECT-03 — Produce aging buckets and follow-up queues with explicit as-of dates and business timezone. Separate overdue amounts from future instalments and disputed balances.

COLLECT-04 — Record promised dates and amounts, responsible owner, last contact, and promise outcome. A live promise pauses the corresponding reminder schedule until its due date.

COLLECT-05 — Manage disputes with reason, documents, assigned owner, next action, and resolution. Pause collection reminders while disputed; resolution must state whether money remains due.

COLLECT-06 — Prepare configurable reminder sequences, working hours, frequency limits, and opt-out handling. Require a preview and an authorized sending configuration before enabling delivery.

COLLECT-07 — Integrate payment links and signed gateway callbacks; process duplicate callbacks idempotently, reconcile partial payments, and stop queued reminders after confirmed settlement.

COLLECT-08 — Track delivery outcomes and failed retries; export customer statements and collection history. Never infer that an email was delivered from an enqueue success.

## Business states

Invoice: Open → Partially paid → Paid; credit notes adjust balance explicitly. Case: Due → Promise active / Disputed / Follow-up due → Resolved. Sending is a separate queued/sent/delivered/failed state machine.

Intake records retain Draft, Reviewed, and Archived checkpoints. The Operations tab adds the product-specific business transitions with server-side gates. External provider delivery and third-party outcomes are recorded separately.

## Planned domain data model

Every business entity is workspace-scoped directly or through a validated parent. IDs are server-generated.

- Customer(id, workspace_id, external_ref UNIQUE per workspace)

- Invoice(id, customer_id, currency, total_minor, due_date, source_ref)

- Payment(id, provider_event_id UNIQUE, amount_minor, confirmed_at)

- Allocation(payment_id, invoice_id, amount_minor)

- Promise(id, invoice_id, promised_date, promised_minor, status)

- Dispute(id, invoice_id, owner_id, reason, status)

- Followup(id, invoice_id, channel, scheduled_at, status, idempotency_key UNIQUE)

## First workflow input contract

- Customer: text; required.

- Invoice reference: text; required.

- Invoice amount · INR: number; required.

- Total recorded payments · INR: number; required.

- Due date: date; required.

- Promised payment date: date; optional.

- Payment disputed?: select; required.

- Follow-up notes: textarea; optional.

## Integrations and dependencies

DoAide Invoicer and Khata adapters; CSV import; a selected payment gateway; email and optional official WhatsApp Business messaging; customer contact preferences.

The local implementation provides file/manual workflows and configured adapters where documented. Live provider accounts and cross-product API validation remain deployment dependencies; see BUILD_STATUS.md.

## Excluded from the initial product release

Debt purchasing, threatening or legal recovery notices, credit scoring, lending, silently sending messages, and marking payments paid from screenshots alone.

## Product acceptance scenarios

COLLECT-AC-01 — An INR 85,000 invoice with INR 25,000 in confirmed payments shows INR 60,000 outstanding.

COLLECT-AC-02 — A disputed invoice never enters an automated payment reminder job; an active promise defers follow-up.

COLLECT-AC-03 — A fully settled invoice produces no new reminder, including when payment arrives while a send job is queued.

COLLECT-AC-04 — Replaying a gateway event or import does not double-count payment or create duplicate invoices.

COLLECT-AC-05 — Customer statements reconcile to allocation totals; overdue calculations are correct at midnight in the workspace timezone.

## What is implemented now

CSV mapping/preview/deduplication and reversible import batches; immutable payment, credit, refund and charge entries; balance/aging, promise/dispute/opt-out pauses, consent/working-hour reminder jobs, Razorpay link adapter and signed replay-safe payment reconciliation. Structured case amounts/owners/evidence/outcomes; configurable reminder cadences with workspace contact caps; evidenced delivery/bounce/complaint reconciliation and frozen customer history statements. v0.6: Account-checked read-only Khata customer ledger import and explicit received-payment reconciliation with workspace-wide source deduplication and frozen evidence.

Shared workspaces with owner/operator/reviewer/viewer roles, recipient-bound invitations, email verification/recovery with one-use tokens and session revocation, optimistic workflow versions, transactional command idempotency, private bounded uploads, source extraction/OCR queue, configurable ClamAV requirement and file-retention tooling, frozen PDF bytes and checksum manifests, scoped external links, durable outbox/retries/visible blocked jobs, workspace stock/financial ledgers, application audit events, pagination, all-product portfolio/aging/accounting exports, optional Stripe test checkout/portal with signed-event reconciliation, server-owned product plans and atomic creation/seat/source-byte/job budgets, worker readiness/owner diagnostics, backup/isolated-restore tooling and off-server image packaging. Schema-4 academic access controls, bounded request bodies and persistent rate limits, authenticated encrypted backups, workspace-data erasure with preview/confirmation/isolation, and continuous test/build/container checks. Schema-5 durable authority activation pins service business/warehouse ownership; connected operations stay pending until external confirmation and never silently fall back to local execution. Audit storage is not externally tamper-proof.

## Next implementation milestone

Validate the updated UI in desktop/mobile browsers and accessibility checks; review representative pilot inputs and final document formats; configure and exercise approved provider accounts; apply the Invoicer adapter migration to its test deployment; apply the Inventory and Khata additive service patches to test deployments, validate the configured portfolio adapters, target-host monitoring/restore/rollback and production policy review. Local workflow implementation and automated tests do not establish production acceptance. See ../BUILD_STATUS.md.

## Product measures

Overdue balance by aging bucket; median days to settle; promises kept; operator time per follow-up; delivery failure and dispute rates.

These are proposed measurement definitions. No adoption, savings, or revenue performance is claimed.

## Principal risk and control

Stale payment state can cause inappropriate reminders. Settlement must be checked immediately before a send and every provider event must be idempotent.

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

POST /api/products/collect/preview validates inputs and calculates a reviewable result. POST /api/products/collect/records saves a draft. GET /api/records?product=collect lists this workspace's records with offset/limit pagination. GET/PUT /api/records/{id} reads or revises a record with optimistic version checks. POST /api/records/{id}/status applies an allowed internal transition. GET /api/records/{id}/audit returns authorized revision history. GET /api/records/{id}/export returns a fresh dated JSON result. GET /api/records/{id}/operations returns the workflow, typed forms, resources, documents and activity. POST /api/records/{id}/items/{kind} manages operational entities. POST /api/records/{id}/actions/{action} runs a version-checked, idempotent business command. See /docs on the local server for the generated OpenAPI interface.
