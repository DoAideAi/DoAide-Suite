# DoAide Tender Scope of Work

Version 1.2 · 28 October 2026 · Engineering scope and acceptance baseline

## Outcome and target customer

Help a small business prepare a complete bid pack from tender documents with traceable requirements and accountable evidence collection.

Primary customer: Small businesses bidding for contracts. Pilot complexity: High. Delivery wave: 3.

## Users and responsibilities

Bid owner manages deadlines and submission checklist; subject specialist assesses eligibility; contributor supplies evidence; authorized reviewer signs off the final pack.

## Principal workflow

Register opportunity → upload tender and amendments → extract cited requirements → classify mandatory and conditional items → map evidence → assign gaps → review the pack → export for submission.

## Functional scope

TENDER-01 — Maintain opportunity reference, authority, procurement portal link, timezone-aware deadline, clarification deadline, and amendment log.

TENDER-02 — Parse text and scanned tender files while preserving source pages, section references, document versions, and extraction confidence.

TENDER-03 — Extract eligibility criteria, technical specifications, mandatory forms, experience requirements, securities, submission steps, and deadline references into editable requirements.

TENDER-04 — Classify each requirement as mandatory, conditional, or informational with a human-confirmed interpretation; show source citations beside every item.

TENDER-05 — Map company documents and evidence to requirements; track document expiry, missing information, owner, due date, and reviewer outcome.

TENDER-06 — Track tender amendments and identify potentially affected requirements. Invalidate earlier readiness reviews when material source documents change.

TENDER-07 — Generate bid/no-bid review notes and a readiness checklist without guaranteeing eligibility, legal compliance, or award likelihood.

TENDER-08 — Export a numbered evidence index and bid-preparation packet; retain a separate manually recorded submission receipt and exact submitted version.

## Business states

Discovered → Under review → Bid / No bid → Preparing → Ready for authorized review → Submitted / Withdrawn / Closed. Readiness is invalidated by material amendments.

Intake records retain Draft, Reviewed, and Archived checkpoints. The Operations tab adds the product-specific business transitions with server-side gates. External provider delivery and third-party outcomes are recorded separately.

## Planned domain data model

Every business entity is workspace-scoped directly or through a validated parent. IDs are server-generated.

- Opportunity(id, workspace_id, authority, reference, deadline_at)

- TenderDocument(id, opportunity_id, revision, checksum, supersedes_id)

- Requirement(id, document_id, locator, text, classification, verified_by)

- Evidence(id, workspace_id, document_id, expires_at)

- RequirementEvidence(requirement_id, evidence_id, review_status)

- BidTask(id, requirement_id, owner_id, due_at, status)

- SubmissionSnapshot(id, opportunity_id, manifest, receipt_ref)

## First workflow input contract

- Buyer or issuing authority: text; required.

- Submission date: date; required.

- Tender excerpt · paste requirement lines: textarea; required.

- Available documents · one name per line: textarea; optional.

## Integrations and dependencies

DoAide Docs/PDF for conversion and export, private storage, company document library, optional calendar notifications. Portal automation is a separate later integration.

The local implementation provides file/manual workflows and configured adapters where documented. Live provider accounts and cross-product API validation remain deployment dependencies; see BUILD_STATUS.md.

## Excluded from the initial product release

Automatic government-portal submission, bypassing CAPTCHAs, legal eligibility certification, invented documents, automatic bank guarantees, or assurance of tender success.

## Product acceptance scenarios

TENDER-AC-01 — Every extracted requirement links to an exact source document and page or line.

TENDER-AC-02 — An uncertain extraction is labeled for review instead of silently treated as satisfied.

TENDER-AC-03 — Missing or expired evidence blocks the relevant readiness requirement.

TENDER-AC-04 — A material amendment marks dependent approvals stale and records why.

TENDER-AC-05 — The exported manifest matches the reviewed document versions and preserves deadlines with timezone.

## What is implemented now

PDF/DOCX/text extraction with source locators, optional local OCR, requirement candidates, owners/dates/evidence expiry, explicit reviewer verification, amendment invalidation, timezone-aware deadlines, readiness manifest and actual submission-receipt recording. Portal and clarification deadlines, mandatory/conditional/informational review, conditional applicability gates and targeted amendment impact reset.

Shared workspaces with owner/operator/reviewer/viewer roles, recipient-bound invitations, email verification/recovery with one-use tokens and session revocation, optimistic workflow versions, transactional command idempotency, private bounded uploads, source extraction/OCR queue, configurable ClamAV requirement and file-retention tooling, frozen PDF bytes and checksum manifests, scoped external links, durable outbox/retries/visible blocked jobs, workspace stock/financial ledgers, application audit events, pagination, all-product portfolio/aging/accounting exports, optional Stripe test checkout/portal with signed-event reconciliation, server-owned product plans and atomic creation/seat/source-byte/job budgets, worker readiness/owner diagnostics, backup/isolated-restore tooling and off-server image packaging. Schema-4 academic access controls, bounded request bodies and persistent rate limits, authenticated encrypted backups, workspace-data erasure with preview/confirmation/isolation, and continuous test/build/container checks. Audit storage is not externally tamper-proof.

## Next implementation milestone

Validate the updated UI in desktop/mobile browsers and accessibility checks; review representative pilot inputs and final document formats; configure and exercise approved provider accounts; apply the Invoicer adapter migration to its test deployment; complete the remaining portfolio integrations listed in REMAINING_SCOPE.md, target-host monitoring/restore/rollback and production policy review. Local workflow implementation and automated tests do not establish production acceptance. See ../BUILD_STATUS.md.

## Product measures

Preparation time per bid; missing requirements at review; amendment-to-review delay; number of bids prepared without deadline misses.

These are proposed measurement definitions. No adoption, savings, or revenue performance is claimed.

## Principal risk and control

A document parser can miss a material condition. The complete tender remains authoritative; all extracted requirements and readiness outcomes need human verification.

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

POST /api/products/tender/preview validates inputs and calculates a reviewable result. POST /api/products/tender/records saves a draft. GET /api/records?product=tender lists this workspace's records with offset/limit pagination. GET/PUT /api/records/{id} reads or revises a record with optimistic version checks. POST /api/records/{id}/status applies an allowed internal transition. GET /api/records/{id}/audit returns authorized revision history. GET /api/records/{id}/export returns a fresh dated JSON result. GET /api/records/{id}/operations returns the workflow, typed forms, resources, documents and activity. POST /api/records/{id}/items/{kind} manages operational entities. POST /api/records/{id}/actions/{action} runs a version-checked, idempotent business command. See /docs on the local server for the generated OpenAPI interface.
