# DoAide Suite product index

Updated: 28 October 2026 · version 0.3.0

Repository: [DoAideAi/DoAide-Suite](https://github.com/DoAideAi/DoAide-Suite), owned by the DoAide organization and published using `r2st`.
Local checkout: `/Users/dev/projects/doaide/DoAide-Suite`.

All twelve products run in this shared FastAPI, React and SQLite application. **Status: operational local workflows; full scope incomplete; not deployed to production.** Each product retains its original acceptance criteria. The remaining work includes product features as well as provider configuration and production acceptance.

| Product | Implemented local workflows | Detailed scope |
| --- | --- | --- |
| Scope | Baselines, estimates, approval limits, frozen change requests, client acceptance and invoice handoff jobs | [Scope](docs/scopes/scope.md) |
| Collect | CSV imports, immutable collection ledger, aging, disputes/promises, consent-aware reminders and payment-link adapters | [Collect](docs/scopes/collect.md) |
| AMC | Assets, technician scheduling, entitlements, service evidence, independent verification and renewed periods | [AMC](docs/scopes/amc.md) |
| RFQ | Specifications, supplier quotes, units/FX, weighted comparison, approvals and frozen purchase orders | [RFQ](docs/scopes/rfq.md) |
| Tender | Cited extraction/OCR, verified requirements, evidence expiry, amendment reset and submission readiness | [Tender](docs/scopes/tender.md) |
| Handover | Rooms/snags, assignment, contractor links, independent verification, client acceptance and warranty reopening | [Handover](docs/scopes/handover.md) |
| OrderDesk | Catalogue/aliases, clarification, price confirmation, stock reservation, cancellation, dispatch and count corrections | [OrderDesk](docs/scopes/orderdesk.md) |
| Batch | Recipes/lots, material reservations, production/returns, quality holds, dispatch, traceability and recall | [Batch](docs/scopes/batch.md) |
| Fees | Enrollment, agreements, instalments, payment/refund allocation, receipt PDFs, rescheduling and guardian statements | [Fees](docs/scopes/fees.md) |
| Renew | Notice calendars, owner acknowledgement, backup escalation, spend/usage flags, cancellation evidence and term rollover | [Renew](docs/scopes/renew.md) |
| SOP | Versioned publication, assignment, exact-version acknowledgement, assessments and retraining history | [SOP](docs/scopes/sop.md) |
| ClaimPack | Manual provider templates, verified evidence, cited timelines, frozen packets, submission receipts and outcomes | [ClaimPack](docs/scopes/claimpack.md) |

Shared features include workspace roles, recovery/verification flows, private evidence files, immutable exports, durable jobs, portfolio reports, accounting CSV, plan limits and Stripe test-mode billing adapters. External delivery is disabled by default. Provider adapters have synthetic/mock coverage; actual provider-account acceptance remains open.

- [Implementation and verification details](docs/BUILD_STATUS.md): 129 automated tests, frontend build, dependency audit, isolated container checks and backup/restore checks.
- [Remaining scope for every product](docs/REMAINING_SCOPE.md): product features, existing-product adapters, real provider test accounts, browser/accessibility acceptance and production operations.
- [Master scope of work](docs/SCOPE_OF_WORK.md) and [operations runbook](docs/OPERATIONS.md).
- [Deployment strategy](STRATEGY.md): build off-server and deploy immutable images after release acceptance.

Current Operations UI browser acceptance remains unverified because the browser tool rejected the local URL. Historical screenshots are not current release acceptance. Local application data, credentials, backups and dependencies are excluded from Git.

The broader local portfolio index is `/Users/dev/projects/doaide/PRODUCT_INDEX.md`; other portfolio products have separate repositories and release status.
