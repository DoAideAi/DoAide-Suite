# DoAide OrderDesk Scope of Work

Version 1.3 · 29 October 2026 · Engineering scope and acceptance baseline

## Outcome and target customer

Convert messy customer orders into explicit, reviewed sales-order drafts with catalogue matches, quantities, availability checks, and a dependable handoff.

Primary customer: Wholesalers & distributors. Pilot complexity: High. Delivery wave: 2.

## Users and responsibilities

Sales operator reviews incoming requests; catalogue manager maintains products and aliases; customer confirms ambiguous items; warehouse staff receive accepted order lines.

## Principal workflow

Receive message or uploaded order → extract requested items → match catalogue → resolve uncertainty → validate units, price and stock → obtain customer confirmation → reserve inventory → create order or invoice draft.

## Functional scope

ORDERDESK-01 — Maintain SKUs, product names, customer aliases, units, pack sizes, prices, tax classes, and availability snapshots with source timestamps.

ORDERDESK-02 — Capture pasted orders initially, then authorized WhatsApp messages, uploaded photos, and voice notes. Retain the source and extraction references.

ORDERDESK-03 — Extract quantities, units, requested dates, variants, and substitutions. Never silently assume a quantity or choose between ambiguous catalogue matches.

ORDERDESK-04 — Present source text beside proposed order lines, confidence, candidate matches, and explicit clarification questions.

ORDERDESK-05 — Validate quantity and pack-size conversion; aggregate repeated SKUs when checking stock; preserve price list versions and authorized overrides.

ORDERDESK-06 — Generate a confirmation summary with taxes, freight, shortages, backorders, and delivery details; track the version the customer confirmed.

ORDERDESK-07 — Reserve stock transactionally only after confirmation and create an idempotent sales-order/invoice handoff. Release reservations on cancellation or expiry.

ORDERDESK-08 — Track downstream status, provider delivery errors, import duplicates, and corrections without overwriting the original incoming order.

## Business states

Received → Parsed → Needs clarification / Ready for review → Customer confirmed → Reserved → Handed off / Cancelled. A commercial revision requires renewed confirmation.

Intake records retain Draft, Reviewed, and Archived checkpoints. The Operations tab adds the product-specific business transitions with server-side gates. External provider delivery and third-party outcomes are recorded separately.

## Planned domain data model

Every business entity is workspace-scoped directly or through a validated parent. IDs are server-generated.

- CatalogueItem(id, workspace_id, sku UNIQUE per workspace, unit, price_version)

- Alias(id, item_id, customer_id, text)

- IncomingOrder(id, customer_id, source_message_id UNIQUE, source_file_id)

- DraftLine(id, order_id, source_locator, quantity, unit, matched_sku, review_state)

- Confirmation(id, order_version_id, customer_id, confirmed_at)

- Reservation(id, order_line_id UNIQUE, quantity, expires_at, status)

- OrderHandoff(id, order_version_id UNIQUE, external_order_id, status)

## First workflow input contract

- Customer: text; required.

- Order lines · quantity × SKU or exact product name: textarea; required.

- Product catalogue · INR: rows; required. Row columns: SKU, Product, Unit price, Available units.

## Integrations and dependencies

DoAide Inventory, Invoicer and Desk; official WhatsApp Business connection when configured; optional speech-to-text and OCR; private evidence storage.

The local implementation provides file/manual workflows and configured adapters where documented. Live provider accounts and cross-product API validation remain deployment dependencies; see BUILD_STATUS.md.

## Excluded from the initial product release

Unattended ordering from uncertain text, accepting a payment screenshot as settlement, direct inventory deductions before confirmation, and unofficial messaging automation.

## Product acceptance scenarios

ORDERDESK-AC-01 — A quantity-free or unknown-product line remains unresolved and cannot be marked reviewed.

ORDERDESK-AC-02 — Two order lines for the same SKU are summed for the stock check.

ORDERDESK-AC-03 — Ambiguous product names are not auto-selected even if one item is cheaper or more popular.

ORDERDESK-AC-04 — A repeated incoming message or handoff event creates at most one order.

ORDERDESK-AC-05 — Concurrent reservations never exceed available stock; cancellations release only their own reservations.

## What is implemented now

Workspace catalogue with aliases, packs, units, tax and price versions; source message IDs, exact-match clarification, customer-confirmation references, atomic competing stock reservations, cancellation release and dispatch ledger, evidence-backed physical-count corrections preserving reserved stock. Signed WhatsApp text/audio intake, consented Groq transcription with human review, reviewed variants/substitutions, evidenced price overrides, freight/delivery details, split backorders, expiring reservations and dispatched-order invoice handoff. v0.5 adds workspace-pinned authoritative Inventory catalogue, stock reservation, dispatch/cancellation, expiration reconciliation, idempotent retries and conflict recovery; the local table is only a quoted snapshot when connected. v0.6: Tenant-checked Desk conversation pagination and order imports, retained immutable previews and explicit review before order parsing.

Shared workspaces with owner/operator/reviewer/viewer roles, recipient-bound invitations, email verification/recovery with one-use tokens and session revocation, optimistic workflow versions, transactional command idempotency, private bounded uploads, source extraction/OCR queue, configurable ClamAV requirement and file-retention tooling, frozen PDF bytes and checksum manifests, scoped external links, durable outbox/retries/visible blocked jobs, workspace stock/financial ledgers, application audit events, pagination, all-product portfolio/aging/accounting exports, optional Stripe test checkout/portal with signed-event reconciliation, server-owned product plans and atomic creation/seat/source-byte/job budgets, worker readiness/owner diagnostics, backup/isolated-restore tooling and off-server image packaging. Schema-4 academic access controls, bounded request bodies and persistent rate limits, authenticated encrypted backups, workspace-data erasure with preview/confirmation/isolation, and continuous test/build/container checks. v0.6.1 adds strict production origins/proxy trust, closed public registration with private owner bootstrap, secure cookies, fail-closed private ClamAV streaming with definition freshness, graceful worker shutdown, resource-limited release containers, capacity preflight, off-site encrypted snapshot/restore receipts and HTTPS/backup monitoring tools. Schema-5 durable authority activation pins service business/warehouse ownership; connected operations stay pending until external confirmation and never silently fall back to local execution. Audit storage is not externally tamper-proof.

## Next implementation milestone

Validate the updated UI in desktop/mobile browsers and accessibility checks; review representative pilot inputs and final document formats; configure and exercise approved provider accounts; apply the Invoicer adapter migration to its test deployment; apply the Inventory and Khata additive service patches to test deployments, validate the configured portfolio adapters, target-host capacity (the current primary host fails the release gate), installation of independent monitoring/backup schedules, target-host restore/rollback and production policy review. Local workflow implementation and automated tests do not establish production acceptance. See ../BUILD_STATUS.md.

## Product measures

Order-entry time; clarification rate; item/quantity correction rate; duplicate-order rate; reservation failures.

These are proposed measurement definitions. No adoption, savings, or revenue performance is claimed.

## Principal risk and control

Product aliases and pack sizes are high-risk ambiguity points. Conservative matching and a customer-confirmed snapshot are required before stock or billing actions.

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

POST /api/products/orderdesk/preview validates inputs and calculates a reviewable result. POST /api/products/orderdesk/records saves a draft. GET /api/records?product=orderdesk lists this workspace's records with offset/limit pagination. GET/PUT /api/records/{id} reads or revises a record with optimistic version checks. POST /api/records/{id}/status applies an allowed internal transition. GET /api/records/{id}/audit returns authorized revision history. GET /api/records/{id}/export returns a fresh dated JSON result. GET /api/records/{id}/operations returns the workflow, typed forms, resources, documents and activity. POST /api/records/{id}/items/{kind} manages operational entities. POST /api/records/{id}/actions/{action} runs a version-checked, idempotent business command. See /docs on the local server for the generated OpenAPI interface.
