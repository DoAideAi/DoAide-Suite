# DoAide RFQ Scope of Work

Version 1.2 · 28 October 2026 · Engineering scope and acceptance baseline

## Outcome and target customer

Give purchasing teams a comparable and auditable view of supplier offers, including commercial exclusions and delivery tradeoffs.

Primary customer: Procurement teams & manufacturers. Pilot complexity: Medium. Delivery wave: 2.

## Users and responsibilities

Requester defines specifications; buyer gathers and normalizes quotes; technical reviewer checks equivalence; budget approver authorizes the award.

## Principal workflow

Create purchase requirement → gather supplier quotes → map lines and units → verify taxes and exclusions → compare cost and lead time → record reviewer questions → approve supplier → generate purchase-order draft.

## Functional scope

RFQ-01 — Create RFQs with line specifications, quantities, units, delivery location, requested date, budget owner, and required quality documents.

RFQ-02 — Capture structured supplier offers and upload original documents. Preserve quote numbers, dates, validity periods, currency, payment terms, and source line references.

RFQ-03 — Normalize units and specification matches explicitly. Unsupported substitutions, missing freight, and uncertain tax treatment must remain visible review items.

RFQ-04 — Calculate landed cost using configurable treatment of discounts, goods tax, freight tax, packaging, and duties. Version exchange rates if cross-currency comparisons are enabled.

RFQ-05 — Display a side-by-side comparison and configurable evaluation factors. Cost ranking must not imply technical approval or automatically award work.

RFQ-06 — Track supplier clarification questions and revised offers while retaining the original quote and previous ranking.

RFQ-07 — Route award recommendations through value-based approval limits, record rationale and conflicts, and create a purchase-order draft with an idempotent reference.

RFQ-08 — Export the comparison, assumptions, and decision trail as spreadsheet/PDF; preserve a stable snapshot of the approved award.

## Business states

Draft → Open → Quotes received → Clarification → Evaluated → Approved → Awarded / Cancelled. Revised offers require a new comparison snapshot.

Intake records retain Draft, Reviewed, and Archived checkpoints. The Operations tab adds the product-specific business transitions with server-side gates. External provider delivery and third-party outcomes are recorded separately.

## Planned domain data model

Every business entity is workspace-scoped directly or through a validated parent. IDs are server-generated.

- RFQ(id, workspace_id, requester_id, currency, status)

- RFQLine(id, rfq_id, specification, quantity_decimal, unit)

- Supplier(id, workspace_id, contacts)

- QuoteVersion(id, supplier_id, rfq_id, valid_until, document_id)

- QuoteLine(id, quote_version_id, rfq_line_id, unit_price, taxes, freight)

- Evaluation(id, quote_version_id, reviewer_id, criteria, decision)

- Award(id, rfq_id, approved_snapshot, purchase_order_ref)

## First workflow input contract

- Item and specification: text; required.

- Required quantity: number; required.

- Supplier quotations · all amounts in INR: rows; required. Row columns: Supplier, Unit price, Freight, Tax %, Lead days, Exclusions.

## Integrations and dependencies

DoAide Inventory for catalogue and receiving references; supplier email after explicit delivery setup; object storage; purchase-order export or accounting adapter.

The local implementation provides file/manual workflows and configured adapters where documented. Live provider accounts and cross-product API validation remain deployment dependencies; see BUILD_STATUS.md.

## Excluded from the initial product release

Supplier credit checks, autonomous awards, purchase payments, unsupported tax advice, and complex international trade accounting in the initial INR pilot.

## Product acceptance scenarios

RFQ-AC-01 — 500 units at INR 155 plus 18% goods tax and INR 1,800 freight total INR 93,250 under the documented initial tax assumption.

RFQ-AC-02 — Duplicate supplier identities and missing units are rejected or flagged before comparison.

RFQ-AC-03 — The comparison retains each quote version and all exclusions after a supplier revises its offer.

RFQ-AC-04 — An approver cannot approve beyond their configured authority, and an award can be traced to its approved quote snapshot.

RFQ-AC-05 — Multi-currency quotes are never combined without a visible dated conversion basis.

## What is implemented now

Multi-line specifications, source quotation files, unit/quantity equivalence, currency/FX basis, discount/tax/freight costing, weighted criteria, technical reviews, owner approval threshold and immutable purchase order. Delivery/quality/budget-owner metadata, quote numbers/dates/validity/payment terms/source lines, independent freight/packaging taxes and duties, clarification/revision/ranking history and frozen comparison CSV/PDF.

Shared workspaces with owner/operator/reviewer/viewer roles, recipient-bound invitations, email verification/recovery with one-use tokens and session revocation, optimistic workflow versions, transactional command idempotency, private bounded uploads, source extraction/OCR queue, configurable ClamAV requirement and file-retention tooling, frozen PDF bytes and checksum manifests, scoped external links, durable outbox/retries/visible blocked jobs, workspace stock/financial ledgers, application audit events, pagination, all-product portfolio/aging/accounting exports, optional Stripe test checkout/portal with signed-event reconciliation, server-owned product plans and atomic creation/seat/source-byte/job budgets, worker readiness/owner diagnostics, backup/isolated-restore tooling and off-server image packaging. Schema-4 academic access controls, bounded request bodies and persistent rate limits, authenticated encrypted backups, workspace-data erasure with preview/confirmation/isolation, and continuous test/build/container checks. Schema-5 durable authority activation pins service business/warehouse ownership; connected operations stay pending until external confirmation and never silently fall back to local execution. Audit storage is not externally tamper-proof.

## Next implementation milestone

Validate the updated UI in desktop/mobile browsers and accessibility checks; review representative pilot inputs and final document formats; configure and exercise approved provider accounts; apply the Invoicer adapter migration to its test deployment; complete the remaining portfolio integrations listed in REMAINING_SCOPE.md, target-host monitoring/restore/rollback and production policy review. Local workflow implementation and automated tests do not establish production acceptance. See ../BUILD_STATUS.md.

## Product measures

Time to comparable quotes; clarification cycles; quoted versus received cost variance; approval turnaround.

These are proposed measurement definitions. No adoption, savings, or revenue performance is claimed.

## Principal risk and control

The cheapest non-equivalent offer can be misleading. Specification equivalence, tax basis, and exclusions must be evaluated independently from arithmetic.

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

POST /api/products/rfq/preview validates inputs and calculates a reviewable result. POST /api/products/rfq/records saves a draft. GET /api/records?product=rfq lists this workspace's records with offset/limit pagination. GET/PUT /api/records/{id} reads or revises a record with optimistic version checks. POST /api/records/{id}/status applies an allowed internal transition. GET /api/records/{id}/audit returns authorized revision history. GET /api/records/{id}/export returns a fresh dated JSON result. GET /api/records/{id}/operations returns the workflow, typed forms, resources, documents and activity. POST /api/records/{id}/items/{kind} manages operational entities. POST /api/records/{id}/actions/{action} runs a version-checked, idempotent business command. See /docs on the local server for the generated OpenAPI interface.
