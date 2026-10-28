# DoAide Scope Scope of Work

Version 1.2 · 28 October 2026 · Engineering scope and acceptance baseline

## Outcome and target customer

Help an agency identify, price, agree, and invoice extra work while preserving the original statement of work and the client's decision trail.

Primary customer: Agencies & independent studios. Pilot complexity: Medium. Delivery wave: 1.

## Users and responsibilities

Agency owner sets rates and approval rules; project manager prepares change requests; delivery staff estimate effort; client reviewer accepts or declines a specific version through a limited-access link.

## Principal workflow

Create a project and client → import the signed baseline → capture a new request → compare against cited deliverables → estimate effort and delivery impact → obtain internal review → request client approval → hand the approved change to Invoicer.

## Functional scope

SCOPE-01 — Maintain projects, clients, versioned baseline documents, included deliverables, explicit exclusions, revision limits, and approval contacts. Store original evidence separately from extracted text.

SCOPE-02 — Accept pasted requests and uploaded PDF/DOCX statements of work. Preserve document name, page or paragraph references, extraction version, and the exact excerpt supporting each comparison.

SCOPE-03 — Offer an assisted scope assessment with In scope, Change required, and Needs clarification outcomes. The project manager makes the final assessment; a model cannot authorize pricing or contract changes.

SCOPE-04 — Estimate quantity or hours, rates, currency, discounts, tax assumptions, milestones, dependencies, and additional delivery days. Keep calculation rules and round currency at defined boundaries.

SCOPE-05 — Generate an editable change request showing the original commitment, requested addition, estimated price, timeline impact, validity period, and assumptions. Support PDF export and revision history.

SCOPE-06 — Require internal approval above configured price thresholds. Client links must be expiring, scoped to one version, and revocable. Changing price or deliverables invalidates prior acceptance.

SCOPE-07 — Record client acceptance or rejection, identity evidence, timestamp, document hash, and comments. Show the exact accepted version and distinguish internal review from client acceptance.

SCOPE-08 — Create an idempotent draft invoice or proposal via an adapter after acceptance. Track invoice reference and billing status without silently changing the signed baseline.

## Business states

New → Assessed → Internally reviewed → Sent → Accepted / Declined / Expired → Invoiced. Any commercial revision creates a new version and requires renewed approval.

Intake records retain Draft, Reviewed, and Archived checkpoints. The Operations tab adds the product-specific business transitions with server-side gates. External provider delivery and third-party outcomes are recorded separately.

## Planned domain data model

Every business entity is workspace-scoped directly or through a validated parent. IDs are server-generated.

- Project(id, workspace_id, client_id, currency, owner_id)

- BaselineVersion(id, project_id, revision, document_id, effective_at, content_hash)

- Deliverable(id, baseline_version_id, text, source_locator)

- ChangeRequest(id, project_id, baseline_version_id, status, version, request_text)

- EstimateLine(id, change_id, quantity_decimal, unit_rate_minor, tax_rule_id)

- Approval(id, change_version_id, actor_id, decision, signed_hash, timestamp)

- InvoiceLink(change_version_id UNIQUE, external_invoice_id, sync_status)

## First workflow input contract

- Client: text; required.

- Agreed deliverables · one per line: textarea; required.

- New client request: textarea; required.

- Estimated extra hours: number; required.

- Hourly rate · INR: number; required.

- Additional delivery days: number; required.

- Your scope assessment: select; required.

## Integrations and dependencies

DoAide Contracts for baseline versions; Proposals for offer templates; Invoicer for draft billing; private object storage for source files; optional email provider for approved delivery. Existing APIs must be inspected before adapter implementation.

The local implementation provides file/manual workflows and configured adapters where documented. Live provider accounts and cross-product API validation remain deployment dependencies; see BUILD_STATUS.md.

## Excluded from the initial product release

Automatic contract interpretation, legal conclusions, automatic customer acceptance, collecting money, full project management, and replacing a qualified electronic signature provider.

## Product acceptance scenarios

SCOPE-AC-01 — Given an 18-hour change at INR 2,000/hour, the estimated change is INR 36,000 before separately specified taxes.

SCOPE-AC-02 — An unassessed request cannot become internally reviewed; every suggested match preserves the baseline reference.

SCOPE-AC-03 — A client cannot view another client's change request, and an expired or revoked link cannot accept it.

SCOPE-AC-04 — Changing an accepted estimate produces a new version and never changes the previously accepted PDF.

SCOPE-AC-05 — Repeated invoice handoff creates one draft invoice; failed delivery remains retryable and visible.

## What is implemented now

Versioned project/baseline records and uploaded sources, cited human assessment, estimate lines with discounts/tax, owner approval thresholds, frozen PDF, expiring/revocable exact-version client acceptance or rejection, new draft revisions, invoice draft and durable adapter handoff. Cited baseline/request comparison with explicit uncertainty and recorded reviewer decisions; workspace-scoped Contracts clause import; real authenticated Invoicer draft endpoint supplied with migration and tests.

Shared workspaces with owner/operator/reviewer/viewer roles, recipient-bound invitations, email verification/recovery with one-use tokens and session revocation, optimistic workflow versions, transactional command idempotency, private bounded uploads, source extraction/OCR queue, configurable ClamAV requirement and file-retention tooling, frozen PDF bytes and checksum manifests, scoped external links, durable outbox/retries/visible blocked jobs, workspace stock/financial ledgers, application audit events, pagination, all-product portfolio/aging/accounting exports, optional Stripe test checkout/portal with signed-event reconciliation, server-owned product plans and atomic creation/seat/source-byte/job budgets, worker readiness/owner diagnostics, backup/isolated-restore tooling and off-server image packaging. Schema-4 academic access controls, bounded request bodies and persistent rate limits, authenticated encrypted backups, workspace-data erasure with preview/confirmation/isolation, and continuous test/build/container checks. Audit storage is not externally tamper-proof.

## Next implementation milestone

Validate the updated UI in desktop/mobile browsers and accessibility checks; review representative pilot inputs and final document formats; configure and exercise approved provider accounts; apply the Invoicer adapter migration to its test deployment; complete the remaining portfolio integrations listed in REMAINING_SCOPE.md, target-host monitoring/restore/rollback and production policy review. Local workflow implementation and automated tests do not establish production acceptance. See ../BUILD_STATUS.md.

## Product measures

Time from new request to priced change; accepted changes as a share of sent changes; approved extra-work value; percentage of accepted changes invoiced.

These are proposed measurement definitions. No adoption, savings, or revenue performance is claimed.

## Principal risk and control

Text similarity can miss scope conflicts. Assisted findings must remain traceable suggestions. Client acceptance and monetary amounts require a stable version boundary.

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

POST /api/products/scope/preview validates inputs and calculates a reviewable result. POST /api/products/scope/records saves a draft. GET /api/records?product=scope lists this workspace's records with offset/limit pagination. GET/PUT /api/records/{id} reads or revises a record with optimistic version checks. POST /api/records/{id}/status applies an allowed internal transition. GET /api/records/{id}/audit returns authorized revision history. GET /api/records/{id}/export returns a fresh dated JSON result. GET /api/records/{id}/operations returns the workflow, typed forms, resources, documents and activity. POST /api/records/{id}/items/{kind} manages operational entities. POST /api/records/{id}/actions/{action} runs a version-checked, idempotent business command. See /docs on the local server for the generated OpenAPI interface.
