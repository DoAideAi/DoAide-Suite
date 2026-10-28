# DoAide suite implementation status

Updated 28 October 2026 · v0.5 · schema 5

All twelve products have executable local operational workflows. v0.4 implements the product-feature gaps identified in the v0.3 audit. **Full original-scope and production acceptance remain open**, including additional portfolio adapters. See [REMAINING_SCOPE.md](REMAINING_SCOPE.md).

The current product-by-product implementations and acceptance criteria are in the [product index](../PRODUCT_INDEX.md) and twelve detailed scopes. v0.4 adds cited comparison and Contracts import; collection case/cadence controls; constrained technician access and renewal offers; RFQ costing/history/exports; targeted tender amendments; inspection templates/photo reports; WhatsApp/audio intake/backorders/expiry; batch cost corrections/disposal/labels; fee policies/withdrawal/academic permissions; renewal negotiation; SOP templates/new-hire training; and ClaimPack provenance/conflicts/redacted derivatives.

## Authoritative connections added in v0.5

Inventory owns connected OrderDesk stock/holds; Scheduler owns connected AMC appointments. Native service writers share transaction locks, commands retain retry/tombstone history, and the Suite waits for authoritative receipts. Real applications pass isolated HTTP acceptance with three temporary databases. Service patches and configuration are documented in [AUTHORITATIVE_CONNECTIONS.md](AUTHORITATIVE_CONNECTIONS.md). Batch lots/quality, parts consumption and deployed-account acceptance remain open.

## Shared implementation

- Workspace roles, invitations, verification/recovery/session revocation, optimistic revisions and idempotent commands. Academic access excludes fee finances, evidence, jobs, accounting and portfolio data at the server.
- SQLite write transactions protect money, reservations, admission limits and immutable events. Money is integer paise; quantities use Decimal. Product entities are validated JSON in typed resource rows rather than a separate SQL table per business subtype.
- Private files, checksums, extraction/OCR, optional enforced ClamAV, retention tombstones and frozen PDF bytes. Customer PDFs are frozen at issuance, including report images. ClaimPack includes approved replacement attachments while privately retaining originals. Reviewers must also check narrative text and replacement files for hidden content.
- Durable leases/retries/dead-letter/blocked jobs, signed replay-safe callbacks, workspace-specific credentials, explicit transcription consent and disabled external delivery by default. SMTP uncertainty requires reconciliation.
- Plans/usage budgets, Stripe test subscriptions, portfolio/aging/accounting exports, persistent request limits, bounded streamed bodies, safe diagnostics and worker readiness.
- Verified backups, authenticated encryption with separately held keys, workspace-data erasure preview/confirmation, additive migrations, non-root/read-only containers and continuous test/build/container checks.

## Verification evidence

- **166 suite tests pass**, covering all twelve journeys, role/workspace isolation, stale input, stock races, callbacks/retries, contact limits, technician links, backorders/expiry, late fees/withdrawal, academic privacy, new-hire enrollment, redaction exports, transcription consent, WhatsApp signatures/media-host restrictions, encrypted restore and erasure isolation.
- **29 Inventory tests and 42 Scheduler tests pass**, including competing operations, native-writer protection, replay, business fencing and additive migrations.
- **95 Invoicer tests pass**, including new API cases for authenticated drafts, exact totals, retries, source checksums and account isolation. The endpoint source/migration/tests are distributed in [integrations/invoicer](../integrations/invoicer).
- Frontend production build and npm audit pass. Final output: [validation.txt](evidence/validation.txt).
- The runtime image passes non-root/read-only/ephemeral-database checks, v0.5 routes, schema 5, worker health, twelve-product reporting and immutable PDF download: [container-check.json](evidence/container-check.json).
- The existing database is backed up before migration; isolated restoration preserves user/record/audit counts and passes integrity/foreign-key checks. Local runtime evidence: [local-runtime-check.json](evidence/local-runtime-check.json).
- Synthetic renewal-offer, room/photo handover and 100 × 150 mm traceability-label PDFs were generated through API workflows, rendered with Poppler and visually inspected. Reproduce with `uv run python scripts/check_documents.py`. Fixtures are in `docs/evidence`.
- The earlier 1,200-record report timing remains a local fixture measurement, not production capacity acceptance.
- **Current browser validation remains unverified:** the browser tool rejected the local URL. No alternate browser route was used to evade that policy. API/build/PDF checks do not replace mobile, interaction or accessibility acceptance.

Configured provider acceptance, remaining portfolio adapters, pilot validation and production operations are itemized in [REMAINING_SCOPE.md](REMAINING_SCOPE.md). No actual payments, external messages, provider submissions, vendor cancellations or production deployments occurred during implementation.
