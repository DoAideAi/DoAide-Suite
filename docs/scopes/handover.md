# DoAide Handover Scope of Work

Version 1.2 · 28 October 2026 · Engineering scope and acceptance baseline

## Outcome and target customer

Provide a room-by-room inspection and repair trail so a completed property or installation can be handed over with clear evidence and customer acceptance.

Primary customer: Interior studios & property managers. Pilot complexity: Medium. Delivery wave: 2.

## Users and responsibilities

Project manager owns the site; inspector raises and verifies snags; contractor resolves assigned issues; customer reviews and accepts a specific handover packet.

## Principal workflow

Create property and inspection areas → record snags and photos → assign severity and repair owner → record fix evidence → independently verify fixes → build handover report → capture customer acceptance or exceptions.

## Functional scope

HANDOVER-01 — Create sites, units, rooms, inspection templates, responsible parties, target dates, and customer contact records.

HANDOVER-02 — Capture issues with location, category, severity, description, assignee, due date, and before photos. Support mobile capture with upload retry and file type restrictions.

HANDOVER-03 — Separate reported, acknowledged, in repair, fixed, and verified states; attach repair notes and after photos to the exact issue revision.

HANDOVER-04 — Provide assignment queues, overdue reports, bulk assignment, and contractor-limited access to relevant issues.

HANDOVER-05 — Require verification by an authorized reviewer; critical unresolved issues block handover, and any waived item needs an explicit reason and customer agreement.

HANDOVER-06 — Generate branded reports grouped by room and severity with issue history, evidence references, unresolved exceptions, and the report version.

HANDOVER-07 — Capture acceptance of the report through an expiring customer link; preserve identity evidence, version hash, timestamp, and comments.

HANDOVER-08 — Reopen defects without erasing the prior handover and manage post-handover warranty items as a related workflow.

## Business states

Issue: Open → Assigned → Fixed → Verified; verification may return it to Open. Handover: Preparing → Reviewed → Sent → Accepted / Changes requested. Exceptions are explicit records.

Intake records retain Draft, Reviewed, and Archived checkpoints. The Operations tab adds the product-specific business transitions with server-side gates. External provider delivery and third-party outcomes are recorded separately.

## Planned domain data model

Every business entity is workspace-scoped directly or through a validated parent. IDs are server-generated.

- Site(id, workspace_id, customer_id)

- Area(id, site_id, label, floor)

- Inspection(id, site_id, template_version, inspector_id)

- Snag(id, area_id, severity, assignee_id, state, version)

- RepairEvidence(id, snag_id, stage, file_id, timestamp)

- Verification(id, snag_version_id, reviewer_id, outcome)

- HandoverPacket(id, site_id, manifest_hash, accepted_at, exceptions)

## First workflow input contract

- Client or property owner: text; required.

- Site or property: text; required.

- Snag register: rows; required. Row columns: Room / area, Issue, Severity, Assigned to, Status.

## Integrations and dependencies

DoAide Realty for property references, Contracts for agreed scope, private image storage, report export, optional notifications.

The local implementation provides file/manual workflows and configured adapters where documented. Live provider accounts and cross-product API validation remain deployment dependencies; see BUILD_STATUS.md.

## Excluded from the initial product release

Building-code certification, safety inspection guarantees, construction project ERP, automatic contractor payments, and treating an internal review as customer acceptance.

## Product acceptance scenarios

HANDOVER-AC-01 — Open and fixed-but-unverified snags appear as outstanding; all critical defects block handover.

HANDOVER-AC-02 — A contractor cannot verify or accept work outside its assigned access scope.

HANDOVER-AC-03 — Before and after images stay associated with the correct issue version.

HANDOVER-AC-04 — Accepted reports remain immutable when an issue is later reopened.

HANDOVER-AC-05 — Mobile issue capture survives upload retry without duplicating the snag.

## What is implemented now

All intake snags retained in the operational register, rooms/checklists, due dates and photos/files, scoped contractor repair links, independent verification, critical/major waiver blocks, disclosed minor waivers, versioned handover acceptance and warranty reopening. Inspection templates, contacts and categories, acknowledged/in-repair progress, bulk assignment, mobile camera upload, and frozen room/severity reports with inspection and repair images. v0.6: Agent-checked Realty property imports with retained source and reviewed property references.

Shared workspaces with owner/operator/reviewer/viewer roles, recipient-bound invitations, email verification/recovery with one-use tokens and session revocation, optimistic workflow versions, transactional command idempotency, private bounded uploads, source extraction/OCR queue, configurable ClamAV requirement and file-retention tooling, frozen PDF bytes and checksum manifests, scoped external links, durable outbox/retries/visible blocked jobs, workspace stock/financial ledgers, application audit events, pagination, all-product portfolio/aging/accounting exports, optional Stripe test checkout/portal with signed-event reconciliation, server-owned product plans and atomic creation/seat/source-byte/job budgets, worker readiness/owner diagnostics, backup/isolated-restore tooling and off-server image packaging. Schema-4 academic access controls, bounded request bodies and persistent rate limits, authenticated encrypted backups, workspace-data erasure with preview/confirmation/isolation, and continuous test/build/container checks. Schema-5 durable authority activation pins service business/warehouse ownership; connected operations stay pending until external confirmation and never silently fall back to local execution. Audit storage is not externally tamper-proof.

## Next implementation milestone

Validate the updated UI in desktop/mobile browsers and accessibility checks; review representative pilot inputs and final document formats; configure and exercise approved provider accounts; apply the Invoicer adapter migration to its test deployment; apply the Inventory and Khata additive service patches to test deployments, validate the configured portfolio adapters, target-host monitoring/restore/rollback and production policy review. Local workflow implementation and automated tests do not establish production acceptance. See ../BUILD_STATUS.md.

## Product measures

Time to resolve snags; reopen rate; issues awaiting verification; days from practical completion to accepted handover.

These are proposed measurement definitions. No adoption, savings, or revenue performance is claimed.

## Principal risk and control

Marking work fixed is not independent verification. Preserve separate actors and immutable acceptance evidence in the pilot.

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

POST /api/products/handover/preview validates inputs and calculates a reviewable result. POST /api/products/handover/records saves a draft. GET /api/records?product=handover lists this workspace's records with offset/limit pagination. GET/PUT /api/records/{id} reads or revises a record with optimistic version checks. POST /api/records/{id}/status applies an allowed internal transition. GET /api/records/{id}/audit returns authorized revision history. GET /api/records/{id}/export returns a fresh dated JSON result. GET /api/records/{id}/operations returns the workflow, typed forms, resources, documents and activity. POST /api/records/{id}/items/{kind} manages operational entities. POST /api/records/{id}/actions/{action} runs a version-checked, idempotent business command. See /docs on the local server for the generated OpenAPI interface.
