# DoAide ClaimPack Scope of Work

Version 1.3 · 29 October 2026 · Engineering scope and acceptance baseline

## Outcome and target customer

Help a merchant assemble a factual and complete evidence packet for a payment dispute, with a clear deadline and traceable source records.

Primary customer: Small ecommerce brands. Pilot complexity: High. Delivery wave: 3.

## Users and responsibilities

Support operator gathers customer conversations; operations supplies fulfillment evidence; finance owns the dispute and deadline; authorized reviewer releases the packet for submission.

## Principal workflow

Register dispute and actual provider deadline → link order and reason → collect source evidence → map evidence to a versioned provider checklist → write factual chronology → review and export → separately record submission and outcome.

## Functional scope

CLAIMPACK-01 — Maintain dispute reference, payment provider, reason code, order, amount, currency, exact response deadline, timezone, assigned owner, and source of the deadline.

CLAIMPACK-02 — Use versioned provider-specific evidence templates with visible applicability dates; permit manual requirements where an adapter is unavailable.

CLAIMPACK-03 — Collect original order details, delivery/tracking proof, product descriptions, customer communications, refund records, and timestamps in private storage.

CLAIMPACK-04 — Map each factual statement and timeline event to evidence; distinguish merchant assertions, carrier claims, customer claims, and verified provider records.

CLAIMPACK-05 — Flag missing documents, unreadable files, conflicting dates, oversized attachments, and unsupported formats before packet completion.

CLAIMPACK-06 — Generate an editable factual response and evidence index without inventing delivery, consent, identity, or customer acknowledgement.

CLAIMPACK-07 — Export a provider-compatible packet with immutable source hashes and approved redactions. Reviewers must confirm the precise version being released.

CLAIMPACK-08 — Track manual submission receipts and outcomes first; add provider submission APIs only with explicit account configuration, idempotency, and visible delivery confirmation.

## Business states

Received → Gathering evidence → Needs review → Packet approved → Submitted → Won / Lost / Withdrawn. Export does not mean submission and completeness does not predict outcome.

Intake records retain Draft, Reviewed, and Archived checkpoints. The Operations tab adds the product-specific business transitions with server-side gates. External provider delivery and third-party outcomes are recorded separately.

## Planned domain data model

Every business entity is workspace-scoped directly or through a validated parent. IDs are server-generated.

- Dispute(id, workspace_id, provider_ref, reason_code, amount_minor, currency, deadline_at)

- OrderSnapshot(id, dispute_id, external_order_id, captured_at, data_hash)

- EvidenceFile(id, dispute_id, kind, file_id, checksum, source, captured_at)

- EvidenceRequirement(id, template_version_id, reason_code, required_kind)

- TimelineEvent(id, dispute_id, occurred_at, statement, evidence_id)

- PacketVersion(id, dispute_id, manifest, content_hash, reviewed_by)

- Submission(id, packet_version_id, provider_ref, submitted_at, receipt, outcome)

## First workflow input contract

- Order reference: text; required.

- Disputed amount · INR: number; required.

- Response deadline: date; required.

- Dispute category: select; required.

- Factual timeline: textarea; required.

- Evidence references · references only, no uploads yet: rows; required. Row columns: Type, File or record reference.

## Integrations and dependencies

DoAide Desk for conversations, ecommerce order export, tracking-provider records, selected payment gateway in test mode, private storage, PDF/image export.

The local implementation provides file/manual workflows and configured adapters where documented. Live provider accounts and cross-product API validation remain deployment dependencies; see BUILD_STATUS.md.

## Excluded from the initial product release

Guaranteed dispute wins, legal representation, fabricated evidence, changing provider deadlines, autonomous submission, or storing full payment-card data.

## Product acceptance scenarios

CLAIMPACK-AC-01 — A not-received dispute without delivery evidence shows the missing requirement explicitly.

CLAIMPACK-AC-02 — A filename alone is never described as verified file contents or proof of delivery.

CLAIMPACK-AC-03 — Every generated factual assertion has an evidence reference or is clearly labeled a merchant assertion.

CLAIMPACK-AC-04 — The released packet retains its evidence hashes and cannot be silently changed after submission.

CLAIMPACK-AC-05 — Provider retries create one submission and the UI distinguishes exported, submitted, and acknowledged states.

## What is implemented now

Versioned manual provider templates/reason codes/deadlines, private evidence with checksums and verification, cited factual timelines, missing-category/size/deadline checks, frozen PDF including evidence annexes, evidence ZIP manifest, submission receipts and provider outcomes. Case ownership/deadline provenance, workspace-published provider templates, statement provenance and conflicting-date resolution; reviewer-approved redacted derivatives replace original attachments in released PDF/ZIP while retaining original hashes and private source files. v0.6: Desk conversation/order evidence imports require explicit application and normal evidence verification; raw import previews are excluded from released document narratives.

Shared workspaces with owner/operator/reviewer/viewer roles, recipient-bound invitations, email verification/recovery with one-use tokens and session revocation, optimistic workflow versions, transactional command idempotency, private bounded uploads, source extraction/OCR queue, configurable ClamAV requirement and file-retention tooling, frozen PDF bytes and checksum manifests, scoped external links, durable outbox/retries/visible blocked jobs, workspace stock/financial ledgers, application audit events, pagination, all-product portfolio/aging/accounting exports, optional Stripe test checkout/portal with signed-event reconciliation, server-owned product plans and atomic creation/seat/source-byte/job budgets, worker readiness/owner diagnostics, backup/isolated-restore tooling and off-server image packaging. Schema-4 academic access controls, bounded request bodies and persistent rate limits, authenticated encrypted backups, workspace-data erasure with preview/confirmation/isolation, and continuous test/build/container checks. v0.6.1 adds strict production origins/proxy trust, closed public registration with private owner bootstrap, secure cookies, fail-closed private ClamAV streaming with definition freshness, graceful worker shutdown, resource-limited release containers, capacity preflight, off-site encrypted snapshot/restore receipts and HTTPS/backup monitoring tools. Schema-5 durable authority activation pins service business/warehouse ownership; connected operations stay pending until external confirmation and never silently fall back to local execution. Audit storage is not externally tamper-proof.

## Next implementation milestone

Validate the updated UI in desktop/mobile browsers and accessibility checks; review representative pilot inputs and final document formats; configure and exercise approved provider accounts; apply the Invoicer adapter migration to its test deployment; apply the Inventory and Khata additive service patches to test deployments, validate the configured portfolio adapters, target-host capacity (the current primary host fails the release gate), installation of independent monitoring/backup schedules, target-host restore/rollback and production policy review. Local workflow implementation and automated tests do not establish production acceptance. See ../BUILD_STATUS.md.

## Product measures

Time to reviewed packet; missing-evidence rate; deadline misses; provider acceptance of packet format; outcome tracking by reason without causal claims.

These are proposed measurement definitions. No adoption, savings, or revenue performance is claimed.

## Principal risk and control

Evidence labels can imply verification that never happened. Distinguish references, stored files, extracted content, and externally confirmed facts at every step.

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

POST /api/products/claimpack/preview validates inputs and calculates a reviewable result. POST /api/products/claimpack/records saves a draft. GET /api/records?product=claimpack lists this workspace's records with offset/limit pagination. GET/PUT /api/records/{id} reads or revises a record with optimistic version checks. POST /api/records/{id}/status applies an allowed internal transition. GET /api/records/{id}/audit returns authorized revision history. GET /api/records/{id}/export returns a fresh dated JSON result. GET /api/records/{id}/operations returns the workflow, typed forms, resources, documents and activity. POST /api/records/{id}/items/{kind} manages operational entities. POST /api/records/{id}/actions/{action} runs a version-checked, idempotent business command. See /docs on the local server for the generated OpenAPI interface.
