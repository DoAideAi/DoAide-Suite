# DoAide AMC Scope of Work

Version 1.3 · 29 October 2026 · Engineering scope and acceptance baseline

## Outcome and target customer

Help equipment service businesses maintain asset histories, honor service entitlements, schedule visits, and renew annual maintenance contracts.

Primary customer: RO, AC & equipment service teams. Pilot complexity: High. Delivery wave: 1.

## Users and responsibilities

Owner defines service plans and pricing; dispatcher assigns visits; technician records work and evidence; customer confirms access and completion.

## Principal workflow

Register customer and asset → select contract and entitlement → plan preventive visits → assign technician → record service and parts → verify completion → issue renewal offer before expiry.

## Functional scope

AMC-01 — Maintain customers, sites, asset serials, model, installation date, warranty information, and service history. Asset serial uniqueness is scoped to manufacturer and workspace.

AMC-02 — Create contract plans with validity period, included visit count, coverage, exclusions, consumables policy, service hours, and renewal pricing; preserve signed plan versions.

AMC-03 — Calculate remaining entitlement, contract state, upcoming renewal windows, and overdue planned visits. Chargeable extra visits must never consume nonexistent included entitlement.

AMC-04 — Generate service schedules respecting contract dates, technician availability, customer windows, and visit duration. Rescheduling preserves the old appointment audit trail.

AMC-05 — Provide technician work orders with checklist, parts used, readings, notes, before-and-after evidence, and start/completion timestamps. Support a mobile layout and retry-safe submission.

AMC-06 — Require supervisor or customer verification for visit completion. Prevent duplicate completion events from consuming more than one entitlement.

AMC-07 — Create renewal opportunities and offer documents; distinguish offered, accepted, invoiced, and renewed. New contracts retain links to the previous period.

AMC-08 — Track parts charges and invoice references; show asset history and export service reports. Provide customer access limited to their own sites and equipment.

## Business states

Contract: Scheduled → Active → Expiring → Renewed / Expired. Visit: Planned → Assigned → In progress → Completed → Verified; cancellation and rebooking preserve entitlement.

Intake records retain Draft, Reviewed, and Archived checkpoints. The Operations tab adds the product-specific business transitions with server-side gates. External provider delivery and third-party outcomes are recorded separately.

## Planned domain data model

Every business entity is workspace-scoped directly or through a validated parent. IDs are server-generated.

- Site(id, customer_id, address, timezone)

- Asset(id, site_id, manufacturer, serial, model)

- PlanVersion(id, terms, coverage, included_visits)

- ServiceContract(id, asset_id, plan_version_id, start_date, end_date)

- Visit(id, contract_id, technician_id, slot, status, entitlement_consumed)

- ServiceEvidence(id, visit_id, file_id, type)

- Renewal(id, predecessor_id, offer_version, status)

## First workflow input contract

- Customer: text; required.

- Equipment and serial number: text; required.

- Contract start: date; required.

- Contract expiry: date; required.

- Included service visits: number; required.

- Completed visits: number; required.

- Next service date: date; optional.

- Contract value · INR: number; required.

## Integrations and dependencies

DoAide Scheduler for appointment availability; Inventory for parts; Invoicer for service and renewal billing; optional customer messages and private photo storage.

The local implementation provides file/manual workflows and configured adapters where documented. Live provider accounts and cross-product API validation remain deployment dependencies; see BUILD_STATUS.md.

## Excluded from the initial product release

Technician payroll, live vehicle tracking, IoT diagnostics, automatic warranty approval, and a universal field-service ERP in the first release.

## Product acceptance scenarios

AMC-AC-01 — A four-visit contract with three completed included visits reports one remaining visit.

AMC-AC-02 — A service outside contract validity cannot consume an included entitlement.

AMC-AC-03 — Repeated completion submissions consume at most one entitlement and preserve the same work order.

AMC-AC-04 — Renewal acceptance creates a new contract period without overwriting prior service history.

AMC-AC-05 — Technicians can access assigned work only; customers can access their own assets only.

## What is implemented now

Sites/assets/coverage, technician membership and collision checks, included/chargeable visit allocation, completion evidence, independent verification, parts costs, verified-visit draft invoices, customer service statements and new contract periods. Manufacturer-scoped serial uniqueness and installation dates; signed plan versions and consumables; customer service windows; assigned-visit-only technician links, start/before evidence, readings and completion; separate exact-offer acceptance and next-period invoicing. v0.5 adds authoritative Scheduler availability/conflict validation and durable create/reschedule/cancel/reconcile operations with business/host mapping and no automatic notifications. v0.6: Authoritative Inventory parts reservations, consumption and release with immutable committed part lines, uncertainty reconciliation and billing blocked until consumption is confirmed.

Shared workspaces with owner/operator/reviewer/viewer roles, recipient-bound invitations, email verification/recovery with one-use tokens and session revocation, optimistic workflow versions, transactional command idempotency, private bounded uploads, source extraction/OCR queue, configurable ClamAV requirement and file-retention tooling, frozen PDF bytes and checksum manifests, scoped external links, durable outbox/retries/visible blocked jobs, workspace stock/financial ledgers, application audit events, pagination, all-product portfolio/aging/accounting exports, optional Stripe test checkout/portal with signed-event reconciliation, server-owned product plans and atomic creation/seat/source-byte/job budgets, worker readiness/owner diagnostics, backup/isolated-restore tooling and off-server image packaging. Schema-4 academic access controls, bounded request bodies and persistent rate limits, authenticated encrypted backups, workspace-data erasure with preview/confirmation/isolation, and continuous test/build/container checks. v0.6.1 adds strict production origins/proxy trust, closed public registration with private owner bootstrap, secure cookies, fail-closed private ClamAV streaming with definition freshness, graceful worker shutdown, resource-limited release containers, capacity preflight, off-site encrypted snapshot/restore receipts and HTTPS/backup monitoring tools. Schema-5 durable authority activation pins service business/warehouse ownership; connected operations stay pending until external confirmation and never silently fall back to local execution. Audit storage is not externally tamper-proof.

## Next implementation milestone

Validate the updated UI in desktop/mobile browsers and accessibility checks; review representative pilot inputs and final document formats; configure and exercise approved provider accounts; apply the Invoicer adapter migration to its test deployment; apply the Inventory and Khata additive service patches to test deployments, validate the configured portfolio adapters, target-host capacity (the current primary host fails the release gate), installation of independent monitoring/backup schedules, target-host restore/rollback and production policy review. Local workflow implementation and automated tests do not establish production acceptance. See ../BUILD_STATUS.md.

## Product measures

Renewal rate; overdue visits; entitlement utilization; first-visit resolution; service revenue per asset.

These are proposed measurement definitions. No adoption, savings, or revenue performance is claimed.

## Principal risk and control

Concurrent completions can overconsume entitlement. Use transactions and unique completion keys; mobile evidence upload needs retry and conflict handling.

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

POST /api/products/amc/preview validates inputs and calculates a reviewable result. POST /api/products/amc/records saves a draft. GET /api/records?product=amc lists this workspace's records with offset/limit pagination. GET/PUT /api/records/{id} reads or revises a record with optimistic version checks. POST /api/records/{id}/status applies an allowed internal transition. GET /api/records/{id}/audit returns authorized revision history. GET /api/records/{id}/export returns a fresh dated JSON result. GET /api/records/{id}/operations returns the workflow, typed forms, resources, documents and activity. POST /api/records/{id}/items/{kind} manages operational entities. POST /api/records/{id}/actions/{action} runs a version-checked, idempotent business command. See /docs on the local server for the generated OpenAPI interface.
