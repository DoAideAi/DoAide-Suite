# DoAide SOP Scope of Work

Version 1.2 · 28 October 2026 · Engineering scope and acceptance baseline

## Outcome and target customer

Turn a business procedure into an approved, versioned guide that employees can follow and acknowledge, with evidence of what changed and who learned it.

Primary customer: Frontline teams & growing businesses. Pilot complexity: High. Delivery wave: 3.

## Users and responsibilities

Process owner writes procedures; reviewer verifies accuracy and safety; supervisor assigns training; employee reads and acknowledges the version assigned to them.

## Principal workflow

Capture demonstration or write steps → draft structured procedure → review hazards and escalation → publish immutable version → assign staff → complete acknowledgement and assessment → revise and reassign affected staff.

## Functional scope

SOP-01 — Create procedure collections, owners, audience, prerequisites, tools, ordered steps, safety warnings, escalation contacts, and effective dates.

SOP-02 — Support manual authoring first, then uploaded recordings and transcripts with timestamp-linked draft steps and selected screenshots. Generated instructions require human review.

SOP-03 — Provide editable step order, images, checklists, branching notes, and templates. Record sources and author changes in a version history.

SOP-04 — Route drafts to reviewers and publish immutable versions; retain prior versions, change summaries, and retirement dates.

SOP-05 — Assign published versions to employees or teams with due dates and reminders; ensure new hires receive current procedures.

SOP-06 — Capture authenticated employee acknowledgements against an exact published version; never treat a manager-entered note as an employee's own acknowledgement.

SOP-07 — Offer short reviewer-approved assessments, pass thresholds, retraining, and supervisor signoff for designated procedures.

SOP-08 — Report current versus stale training, export printable guides, and allow controlled offline copies with a visible version and expiry policy.

## Business states

Procedure: Draft → In review → Published → Superseded / Retired. Training: Assigned → In progress → Acknowledged → Assessed / Retraining required.

Intake records retain Draft, Reviewed, and Archived checkpoints. The Operations tab adds the product-specific business transitions with server-side gates. External provider delivery and third-party outcomes are recorded separately.

## Planned domain data model

Every business entity is workspace-scoped directly or through a validated parent. IDs are server-generated.

- Procedure(id, workspace_id, owner_id, category)

- ProcedureVersion(id, procedure_id, revision, state, effective_at, checksum)

- Step(id, version_id, position, instruction, evidence_locator, media_id)

- PublicationReview(id, version_id, reviewer_id, outcome)

- TrainingAssignment(id, employee_id, version_id, due_at)

- Acknowledgement(id, assignment_id UNIQUE, actor_id, acknowledged_at)

- AssessmentAttempt(id, assignment_id, question_version, score, passed)

## First workflow input contract

- Procedure name: text; required.

- Procedure owner: text; required.

- Procedure version: number; required.

- Procedure steps · one per line: textarea; required.

- Safety notes and escalation: textarea; optional.

- Recorded acknowledgements: rows; required. Row columns: Employee reference, Acknowledged version.

## Integrations and dependencies

DoAide Docs for export, optional transcription provider, private media storage, employee directory or Payroll read-only roster adapter, authorized reminder delivery.

The local implementation provides file/manual workflows and configured adapters where documented. Live provider accounts and cross-product API validation remain deployment dependencies; see BUILD_STATUS.md.

## Excluded from the initial product release

Automatic safety certification, replacing professional training, covert employee monitoring, using acknowledgements as legal waivers, and publishing generated steps without review.

## Product acceptance scenarios

SOP-AC-01 — Published steps cannot change in place; edits create a new draft version.

SOP-AC-02 — An acknowledgement of version 1 is stale after version 2 becomes the assigned version.

SOP-AC-03 — An employee cannot acknowledge on behalf of another employee.

SOP-AC-04 — Every generated step can be traced to its transcript or manually authored source.

SOP-AC-05 — Retired procedures cannot receive new assignments, while historical acknowledgements remain auditable.

## What is implemented now

Editable ordered steps with prerequisites/source timestamps/files, reviewed immutable publications, new-version supersession, named staff assignments, authenticated exact-document acknowledgements, approved quizzes, scoring/retraining history and answer-key access control. Audience/tools/escalation/effective-date policy, consented recording transcription, reviewed timestamp-linked steps, forward-only branches, reusable published templates, team/new-hire enrollment, reminders, independent supervisor signoff and expiring offline copies. v0.6: Payroll staff roster imports retain only training-relevant fields; explicit assignments require existing workspace members and published procedures. Rosters are excluded from released procedure PDFs and packets.

Shared workspaces with owner/operator/reviewer/viewer roles, recipient-bound invitations, email verification/recovery with one-use tokens and session revocation, optimistic workflow versions, transactional command idempotency, private bounded uploads, source extraction/OCR queue, configurable ClamAV requirement and file-retention tooling, frozen PDF bytes and checksum manifests, scoped external links, durable outbox/retries/visible blocked jobs, workspace stock/financial ledgers, application audit events, pagination, all-product portfolio/aging/accounting exports, optional Stripe test checkout/portal with signed-event reconciliation, server-owned product plans and atomic creation/seat/source-byte/job budgets, worker readiness/owner diagnostics, backup/isolated-restore tooling and off-server image packaging. Schema-4 academic access controls, bounded request bodies and persistent rate limits, authenticated encrypted backups, workspace-data erasure with preview/confirmation/isolation, and continuous test/build/container checks. Schema-5 durable authority activation pins service business/warehouse ownership; connected operations stay pending until external confirmation and never silently fall back to local execution. Audit storage is not externally tamper-proof.

## Next implementation milestone

Validate the updated UI in desktop/mobile browsers and accessibility checks; review representative pilot inputs and final document formats; configure and exercise approved provider accounts; apply the Invoicer adapter migration to its test deployment; apply the Inventory and Khata additive service patches to test deployments, validate the configured portfolio adapters, target-host monitoring/restore/rollback and production policy review. Local workflow implementation and automated tests do not establish production acceptance. See ../BUILD_STATUS.md.

## Product measures

Procedure publication time; staff current on assigned versions; overdue training; assessment pass/retraining rates; revision-to-reacknowledgement delay.

These are proposed measurement definitions. No adoption, savings, or revenue performance is claimed.

## Principal risk and control

Generated procedure errors can affect real operations. Reviewers must verify sequence, hazards, and escalation; sample acknowledgements are never verified employee actions.

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

POST /api/products/sop/preview validates inputs and calculates a reviewable result. POST /api/products/sop/records saves a draft. GET /api/records?product=sop lists this workspace's records with offset/limit pagination. GET/PUT /api/records/{id} reads or revises a record with optimistic version checks. POST /api/records/{id}/status applies an allowed internal transition. GET /api/records/{id}/audit returns authorized revision history. GET /api/records/{id}/export returns a fresh dated JSON result. GET /api/records/{id}/operations returns the workflow, typed forms, resources, documents and activity. POST /api/records/{id}/items/{kind} manages operational entities. POST /api/records/{id}/actions/{action} runs a version-checked, idempotent business command. See /docs on the local server for the generated OpenAPI interface.
