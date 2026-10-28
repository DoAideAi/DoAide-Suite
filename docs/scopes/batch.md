# DoAide Batch Scope of Work

Version 1.2 · 28 October 2026 · Engineering scope and acceptance baseline

## Outcome and target customer

Give a small manufacturer lot-level input traceability and understandable production costs, including output variance and expiry tracking.

Primary customer: Small food & specialty manufacturers. Pilot complexity: High. Delivery wave: 3.

## Users and responsibilities

Production planner creates batches; operator records consumption and output; inventory manager manages lots; quality reviewer releases or rejects the finished batch.

## Principal workflow

Version recipe → select input lots → issue production batch → record actual usage, waste and finished output → calculate cost → perform quality review → release inventory → trace affected lots when needed.

## Functional scope

BATCH-01 — Maintain finished products, recipes with effective versions, input units, expected quantities, yield assumptions, packaging, and standard overhead categories.

BATCH-02 — Receive ingredient lots with supplier reference, received quantity, expiry, unit cost, and quality status; prevent consumption of quarantined or expired lots without authorized exception policy.

BATCH-03 — Create planned batches and reserve input lots; record actual consumed quantities, returns, wastage, operator, timestamps, and output units.

BATCH-04 — Calculate consumed input cost, allocated labor/overhead, packaging, finished-unit cost, and variance to plan. Do not combine unlike units or confuse output attainment with mass yield.

BATCH-05 — Require batch quality checks and an authorized release decision; separate physical production from inventory availability for sale.

BATCH-06 — Maintain finished lots and expiry rules with traceability from finished batch to each input lot and from a supplier lot to all affected outputs.

BATCH-07 — Support corrections through reversal/adjustment events with reasons; released production history must never be silently overwritten.

BATCH-08 — Generate batch sheets, label data, expiry queues, and traceability reports. Export affected order references for a separately managed recall process.

## Business states

Planned → Inputs reserved → In production → Produced → Quality hold → Released / Rejected. Corrections use linked adjustment events.

Intake records retain Draft, Reviewed, and Archived checkpoints. The Operations tab adds the product-specific business transitions with server-side gates. External provider delivery and third-party outcomes are recorded separately.

## Planned domain data model

Every business entity is workspace-scoped directly or through a validated parent. IDs are server-generated.

- RecipeVersion(id, product_id, version, yield_basis)

- IngredientLot(id, workspace_id, supplier_lot, unit, received_qty, expiry, status)

- ProductionBatch(id, product_id, recipe_version_id, planned_units, status)

- Consumption(id, batch_id, lot_id, quantity, unit_cost_snapshot)

- BatchCost(id, batch_id, category, amount_minor, allocation_basis)

- FinishedLot(id, batch_id, quantity, expiry, release_id)

- QualityRelease(id, batch_version_id, reviewer_id, decision, evidence)

## First workflow input contract

- Finished product: text; required.

- Batch reference: text; required.

- Planned finished units: number; required.

- Actual finished units: number; required.

- Finished batch expiry: date; required.

- Batch overhead · INR: number; required.

- Ingredients consumed: rows; required. Row columns: Ingredient, Supplier lot, Consumed quantity, Unit, Cost per unit · INR.

## Integrations and dependencies

DoAide Inventory for lot balances; supplier purchase references; label/PDF export; optional barcode readers; sales-order references for traceability.

The local implementation provides file/manual workflows and configured adapters where documented. Live provider accounts and cross-product API validation remain deployment dependencies; see BUILD_STATUS.md.

## Excluded from the initial product release

Food or cosmetics regulatory certification, laboratory testing, automated shelf-life determination, advanced factory scheduling, and automatic recall communications.

## Product acceptance scenarios

BATCH-AC-01 — Ingredient costs plus overhead reconcile exactly to batch cost, with documented rounding for unit cost.

BATCH-AC-02 — Ingredient quantities in kg and litres are never summed as a single physical yield.

BATCH-AC-03 — A released batch exposes all consumed supplier lot references and their cost snapshots.

BATCH-AC-04 — Expired or quarantined inputs cannot be consumed through ordinary operator permissions.

BATCH-AC-05 — Concurrent batch reservations cannot overspend lot availability; corrections retain original events.

## What is implemented now

Versioned recipes, supplier lots with expiry/quality status, atomic input reservations, actual consumption and waste, immutable cost/variance snapshots, material-return adjustments, quality release/rejection, finished-stock dispatch, forward/reverse traceability and recall reports, evidence-backed count adjustments preserving quarantine holds. Effective recipe dates, packaging/labor/overhead categories, reversible cost corrections with nonnegative adjusted cost, rejected/recalled stock disposal, affected-order references and a 100 × 150 mm traceability label.

Shared workspaces with owner/operator/reviewer/viewer roles, recipient-bound invitations, email verification/recovery with one-use tokens and session revocation, optimistic workflow versions, transactional command idempotency, private bounded uploads, source extraction/OCR queue, configurable ClamAV requirement and file-retention tooling, frozen PDF bytes and checksum manifests, scoped external links, durable outbox/retries/visible blocked jobs, workspace stock/financial ledgers, application audit events, pagination, all-product portfolio/aging/accounting exports, optional Stripe test checkout/portal with signed-event reconciliation, server-owned product plans and atomic creation/seat/source-byte/job budgets, worker readiness/owner diagnostics, backup/isolated-restore tooling and off-server image packaging. Schema-4 academic access controls, bounded request bodies and persistent rate limits, authenticated encrypted backups, workspace-data erasure with preview/confirmation/isolation, and continuous test/build/container checks. Audit storage is not externally tamper-proof.

## Next implementation milestone

Validate the updated UI in desktop/mobile browsers and accessibility checks; review representative pilot inputs and final document formats; configure and exercise approved provider accounts; apply the Invoicer adapter migration to its test deployment; complete the remaining portfolio integrations listed in REMAINING_SCOPE.md, target-host monitoring/restore/rollback and production policy review. Local workflow implementation and automated tests do not establish production acceptance. See ../BUILD_STATUS.md.

## Product measures

Batch cost variance; output attainment; material wastage by unit; traceability lookup time; inventory adjustments per batch.

These are proposed measurement definitions. No adoption, savings, or revenue performance is claimed.

## Principal risk and control

Incorrect units or mutable cost records invalidate traceability. Recipe, lot, and cost snapshots must be immutable after release and corrected through explicit adjustments.

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

POST /api/products/batch/preview validates inputs and calculates a reviewable result. POST /api/products/batch/records saves a draft. GET /api/records?product=batch lists this workspace's records with offset/limit pagination. GET/PUT /api/records/{id} reads or revises a record with optimistic version checks. POST /api/records/{id}/status applies an allowed internal transition. GET /api/records/{id}/audit returns authorized revision history. GET /api/records/{id}/export returns a fresh dated JSON result. GET /api/records/{id}/operations returns the workflow, typed forms, resources, documents and activity. POST /api/records/{id}/items/{kind} manages operational entities. POST /api/records/{id}/actions/{action} runs a version-checked, idempotent business command. See /docs on the local server for the generated OpenAPI interface.
