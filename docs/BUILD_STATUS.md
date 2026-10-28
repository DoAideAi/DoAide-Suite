# DoAide suite implementation status

Updated 28 October 2026 · v0.3 operational local build

All twelve products now have operational workflows beyond the original intake calculators. This is **not a claim that every production requirement in the scope of work is complete**. The original scope remains the release acceptance baseline.

## Implemented product workflows

| Product | Implemented operations |
| --- | --- |
| Scope | Project/approval contacts, source clauses/files, discounted/taxed estimate lines, approval limits, frozen PDF, client accept/decline with hash/comments, expiring/revocable links, new draft revisions, draft invoice and durable handoff |
| Collect | Mapped CSV preview/import/deduplication/reversal, immutable payment/credit/refund/charge ledger, balances, disputes/promises/opt-outs, working-hour reminder queue, Razorpay payment-link creation and signed callback reconciliation |
| AMC | Sites/assets/coverage, technician availability, visit entitlement allocation, service files/notes/parts, independent verification, verified-visit invoices, customer service statements, renewed contract periods |
| RFQ | Multi-line specifications and quotes, evidence files, base-unit equivalence, FX basis, discounts/tax/freight, weighted criteria, technical review, approval threshold, frozen purchase order |
| Tender | Cited PDF/DOCX/text extraction, optional local OCR, candidate requirements, owners/due dates/evidence expiry, reviewer verification, amendment reset, timezone deadline, readiness manifest and submission receipt |
| Handover | Intake snags retained, rooms/checklists, evidence, assignees/due dates, limited contractor repair links, independent verification, minor-waiver disclosure, versioned acceptance and warranty reopening |
| OrderDesk | Shared catalogue/aliases/packs/units/tax, source-message references, exact-match clarification, price-version confirmation, atomic reservations, cancellation release, dispatch movements and audited physical-count corrections |
| Batch | Recipe versions, supplier lot receipt/quality/expiry, input reservations, actual usage/waste/cost variance, immutable return adjustments, quality release/rejection, finished-lot dispatch, traceability, recall reports and corrections retaining quarantine holds |
| Fees | Enrollment/guardian records, approved fee/discount agreement, instalments/FIFO allocation, approved remaining-fee rescheduling after receipts, separate charge obligations, immutable financial entries, numbered receipt PDFs, guardian statements, consent checks and payment links |
| Renew | Contract terms, owners/backups/seats, calendar/business-day notice and holidays, actual spend, decisions, cancellation request vs vendor confirmation, vendor-evidenced next terms, recomputed notice milestones, owner acknowledgement/backup escalation, verified-seat/duplicate/price alerts, portfolio reports and ICS |
| SOP | Ordered steps/prerequisites/source evidence, immutable publication, assignments, authenticated exact-version acknowledgement, approved assessments, scoring/retraining, superseded-version checks and protected answer keys |
| ClaimPack | Manual provider/reason templates, exact deadlines, verified evidence, cited timeline, category/size checks, frozen PDF with evidence annexes, evidence ZIP, submission receipt and outcome |

## Shared implementation

- Workspace membership and server-enforced owner/operator/reviewer/viewer permissions; invitation links bound to recipient accounts. Optional required-email-verification mode, one-use recovery tokens, non-enumerating link requests and password-reset session revocation are implemented. Email delivery must be configured and tested before requiring verification.
- Separate limited links for clients, guardians and contractors. Links authorize access by possession; names/emails are recorded and are not identity-provider verification or qualified electronic signatures.
- Additive migration preserves original records. Typed entity rows, ledger entries, stock movements, files, document snapshots/PDF bytes, decisions, jobs, events and idempotency records have separate tables. Product entity fields remain validated JSON rather than one SQL table per business subtype.
- Financial entries use integer paise. Inventory quantities use Decimal and a write transaction covering availability checks and movements.
- Private upload limits/types, checksums, source extraction, optional Tesseract/Poppler OCR. ClamAV screening is enforced when `DOAIDE_REQUIRE_MALWARE_SCAN=true`; this host has no configured scanner. File metadata exposes this state.
- Retention policy can be configured for newly uploaded source files. The retention command defaults to preview. Purging source bytes preserves manifests and frozen documents; broader record/document erasure is a separate production policy requirement.
- Frozen PDF bytes are stored once, with source/evidence hashes; repeated downloads return identical bytes. PDFs and evidence ZIPs use authorized endpoints.
- Durable outbox with leases, retry/backoff/dead-letter/blocked states; ambiguous SMTP deliveries require reconciliation instead of automatic repeat sends. Payment callbacks validate raw-body HMAC and deduplicate event and payment IDs. Overpayments remain visible as unallocated payments.
- Backup includes database-held files and PDFs. Isolated restore validation, development supervisor and off-server runtime/worker image definitions are included.

- Workspace tools includes portfolio summaries and attention queues for all twelve products, Collect/Fees aging and accounting CSV, and verified Renew usage/duplicate/price flags. CSV text is escaped against spreadsheet formula execution. Archived records remain exportable but are excluded from operational totals.
- Optional Stripe **test-mode-only** subscriptions: hosted checkout/portal jobs, raw-body signed events, canonical provider reconciliation, hourly recovery from missed events, replay deduplication, plan expiry/fallback and owner-only billing controls. Local mode remains unlimited. Prices and budgets are server-configured, not invented prices or user-editable entitlements.
- Atomic budgets cover new records (including imports and revisions), memberships, original source-file bytes and optional jobs per UTC month. Existing records, financial corrections, callbacks and exports remain available after a budget or subscription expires. Frozen document storage is outside the source-file budget.
- Physical stock corrections require reviewer/owner, a unique reference, current reviewed count and file evidence. Reservations cannot be consumed by a correction; quarantine/recall holds remain in place. Original production and dispatch snapshots remain immutable.
- Public readiness can require a worker heartbeat or live lease; owners can inspect safe queue/schema diagnostics. Schema 3 migrations no longer reinstate a removed original owner.

## Verification evidence

- 129 domain/API/integration tests pass. The final test/build/audit output is recorded in `docs/evidence/validation.txt`.
- Tests exercise all twelve operational journeys, role/workspace isolation, stale writes, acceptance/revocation, CSV reversal, actual concurrent stock reservations, material reservations/returns, independent verification, provider failure/retry, signed callback replay, document identity, contractor boundaries, retention tombstones and a real local OCR worker round trip. Added tests cover concurrent plan admission, import/revision/membership/file budgets, Stripe checkout retries, test-only keys, forged/stale/duplicate/out-of-order events, expired/unknown subscriptions, fee amendments and refunds, renewal recomputation/acknowledgement, report isolation/reconciliation, count corrections and revoked membership after restart.
- An isolated 1,200-record, twelve-product report fixture produced all CSV rows without creating workflow state; median local response was 0.0306 seconds over three requests. This is not production load acceptance. See `docs/evidence/report-performance.json`.
- Frontend production build succeeds; npm audit reports zero known vulnerabilities.
- The Docker runtime image builds locally. A non-root container with a read-only filesystem passed registration, record creation, operational approval, portfolio/billing readiness, schema-3 state and frozen-PDF export against an isolated in-memory filesystem database. See `docs/evidence/container-check.json`.
- Existing database backup restored and migrated in an isolated directory; users, records and audit counts were preserved and SQLite integrity/foreign-key checks passed.
- A generated one-page change request was rendered with Poppler and visually checked. The examples are `docs/evidence/operations-change-request.pdf` and the new one-page `docs/evidence/fee-schedule-amendment.pdf`, whose old/revised tables and balances were rendered and visually checked.
- **Current browser validation is blocked:** the browser tool rejected the local URL under its URL policy. Earlier v0.1 screenshots and checks remain historical evidence only; they do not validate the new Operations UI. New desktop/mobile interaction and accessibility checks remain open.

## Connections and remaining release work

External sending defaults to disabled. No real outbound messages, payment transactions, tender/dispute submissions, vendor cancellations or production deployments were performed during development.

1. Configure approved SMTP and Razorpay **test** accounts and verify delivery/callback behavior against those accounts. WhatsApp, voice transcription and provider-specific dispute submission are not connected.
2. Provide a verified draft-invoice adapter. The inspected existing `DoAide-Invoicer/app/routers/invoices.py` exposes upload/extraction, list/read and update routes, but no idempotent draft-create endpoint. The suite's documented bridge contract is implemented and mock-tested; it is not a completed connection to the existing service. Contracts, Scheduler, Inventory and other portfolio integrations also require verified service adapters.
3. Configure and validate the implemented email verification/recovery flow, validate configured Stripe test prices/checkout/portal/webhooks, then complete production abuse controls and the selected production database/deployment review. Commercial controls are implemented; no real Stripe account has been exercised.
4. Validate business rules and final templates with representative pilot data: tax/invoice layouts, tender eligibility, dispute provider requirements, training assessment policy, cancellation terms and inventory adjustments. The app does not make legal/regulatory or third-party acceptance determinations.
5. Complete current desktop/mobile browser acceptance, accessibility testing, load/operational acceptance, monitoring, encrypted backup storage, restore/rollback drill in the target deployment, and comprehensive data-erasure policy.

Additional implementation work remains within the individual product scopes, including advanced RFQ terms/tax handling, order delivery/backorders/expiry, AMC renewal offers and constrained technician access, reminder cadences, late-fee policies and richer training workflows. See [remaining product scope](REMAINING_SCOPE.md). These are implementation tasks, not merely missing credentials.

These are explicit remaining scope items. The local operational release should not be described as twelve completed production SaaS products.
