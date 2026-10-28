# DoAide Renew Scope of Work

Version 1.2 · 28 October 2026 · Engineering scope and acceptance baseline

## Outcome and target customer

Give a small company a dependable calendar of contract renewals and cancellation windows with a named owner and an auditable decision.

Primary customer: Agencies & small companies. Pilot complexity: Low to medium. Delivery wave: 2.

## Users and responsibilities

Team member submits a service; budget owner reviews cost and usage; operations owner tracks renewal deadlines; finance confirms invoices and final decisions.

## Principal workflow

Register service and owner → record contract terms and cost → verify notice window → remind accountable owner → decide renew, cancel, or negotiate → record vendor confirmation → update next contract period.

## Functional scope

RENEW-01 — Maintain vendors, contracts, subscription identifiers, owners, departments, billing cadence, currencies, seats, and supporting invoices or terms.

RENEW-02 — Record next renewal date, term length, auto-renew setting, notice period, and explicit calendar or business-day semantics. Cite the source clause.

RENEW-03 — Calculate notice deadlines and annualized committed cost with visible assumptions; separate billed spend from annualized run rate.

RENEW-04 — Create reminder milestones before notice deadlines with owner acknowledgement and backup escalation when ownership is missing or stale.

RENEW-05 — Capture renew/cancel/negotiate decisions, rationale, approver, negotiated terms, and relevant version. A decision does not itself cancel a vendor contract.

RENEW-06 — Track cancellation or renewal requests and vendor confirmations as distinct events with evidence and the actual effective date.

RENEW-07 — Flag duplicate subscriptions, price increases, missing owners, and potentially unused seats from verified inputs; avoid inventing usage metrics.

RENEW-08 — Export a renewal calendar and portfolio report, preserve past terms, and create the next period from confirmed vendor information.

## Business states

Tracked → Review due → Decision recorded → Action requested → Vendor confirmed → Renewed / Ended. An overdue notice window remains visible even after an internal decision.

Intake records retain Draft, Reviewed, and Archived checkpoints. The Operations tab adds the product-specific business transitions with server-side gates. External provider delivery and third-party outcomes are recorded separately.

## Planned domain data model

Every business entity is workspace-scoped directly or through a validated parent. IDs are server-generated.

- Vendor(id, workspace_id, name)

- Subscription(id, vendor_id, owner_id, department_id, external_ref)

- ContractTerm(id, subscription_id, start, renewal, notice_rule, source_document_id)

- PriceVersion(id, term_id, amount_minor, currency, cadence, seats)

- RenewalDecision(id, term_id, actor_id, decision, rationale, approved_at)

- VendorAction(id, term_id, requested_action, sent_at, confirmed_at, evidence_id)

- Reminder(id, term_id, due_at, owner_id, state, idempotency_key)

## First workflow input contract

- Vendor: text; required.

- Subscription or contract: text; required.

- Responsible person: text; required.

- Cost per billing period · INR: number; required.

- Billing period: select; required.

- Next renewal date: date; required.

- Cancellation notice days: number; required.

- Renewal decision: select; required.

## Integrations and dependencies

DoAide Contracts, CSV or invoice import, optional calendar feed, authorized email delivery, private terms storage; direct vendor cancellation is a later per-provider adapter.

The local implementation provides file/manual workflows and configured adapters where documented. Live provider accounts and cross-product API validation remain deployment dependencies; see BUILD_STATUS.md.

## Excluded from the initial product release

Bank-account scanning, automatic vendor cancellation, unsupported spend-saving claims, software usage surveillance, and interpreting contractual notice rights as legal advice.

## Product acceptance scenarios

RENEW-AC-01 — INR 3,600 monthly annualizes to INR 43,200; quarterly and annual cadences use the documented factors.

RENEW-AC-02 — A 30-calendar-day notice period produces the correct deadline across month and year boundaries.

RENEW-AC-03 — The app distinguishes a recorded cancellation decision from vendor-confirmed cancellation.

RENEW-AC-04 — Changing the renewal date recomputes unsent reminders without producing duplicates.

RENEW-AC-05 — Historical prices and terms remain accessible after renewal and ownership changes.

## What is implemented now

Contract terms, owners/backups/seats, calendar or business-day notice with holidays, actual-spend invoices, reviewed renewal/cancel/negotiate decisions, requested versus vendor-confirmed cancellation, vendor-evidenced next-term history, recomputed notice milestones, owner acknowledgement and backup escalation, verified-seat/duplicate/price flags, portfolio reports and ICS export.

Shared workspaces with owner/operator/reviewer/viewer roles, recipient-bound invitations, email verification/recovery with one-use tokens and session revocation, optimistic workflow versions, transactional command idempotency, private bounded uploads, source extraction/OCR queue, configurable ClamAV requirement and file-retention tooling, frozen PDF bytes and checksum manifests, scoped external links, durable outbox/retries/visible blocked jobs, workspace stock/financial ledgers, application audit events, pagination, all-product portfolio/aging/accounting exports, optional Stripe test checkout/portal with signed-event reconciliation, server-owned product plans and atomic creation/seat/source-byte/job budgets, worker readiness/owner diagnostics, backup/isolated-restore tooling and off-server image packaging. Audit storage is not externally tamper-proof.

## Next implementation milestone

Validate the complete updated UI in desktop/mobile browsers; validate domain rules and final document templates with representative pilot inputs; configure and exercise approved providers in test mode; integrate any required existing DoAide services through verified API contracts; validate configured identity/recovery delivery and validate the implemented commercial controls against configured test prices; finish the product-specific gaps in REMAINING_SCOPE.md, production database and deployment/security/operational acceptance. See ../BUILD_STATUS.md for the current evidence and limitations.

## Product measures

Renewals with assigned owners; decisions made before notice deadline; missed cancellation windows; confirmed annual committed cost changes.

These are proposed measurement definitions. No adoption, savings, or revenue performance is claimed.

## Principal risk and control

Notice periods may use business days or special clauses. The pilot must capture the rule and source rather than assume all contracts use simple calendar subtraction.

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

POST /api/products/renew/preview validates inputs and calculates a reviewable result. POST /api/products/renew/records saves a draft. GET /api/records?product=renew lists this workspace's records with offset/limit pagination. GET/PUT /api/records/{id} reads or revises a record with optimistic version checks. POST /api/records/{id}/status applies an allowed internal transition. GET /api/records/{id}/audit returns authorized revision history. GET /api/records/{id}/export returns a fresh dated JSON result. GET /api/records/{id}/operations returns the workflow, typed forms, resources, documents and activity. POST /api/records/{id}/items/{kind} manages operational entities. POST /api/records/{id}/actions/{action} runs a version-checked, idempotent business command. See /docs on the local server for the generated OpenAPI interface.
