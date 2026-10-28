# DoAide Suite product index

Updated: 29 October 2026 · version 0.6.1

Repository: [DoAideAi/DoAide-Suite](https://github.com/DoAideAi/DoAide-Suite), private, published using `r2st`.
Local checkout: `/Users/dev/projects/doaide/DoAide-Suite`.

All twelve products run in this shared FastAPI/React/SQLite application. **Status: expanded local implementation; full original-scope/production acceptance open.** v0.6 completes the outstanding portfolio adapter code: Batch lots, AMC parts and reviewed Desk, Realty, Khata, Proposals, Payroll and course-enrollment imports. Live provider and production acceptance remain explicit work.

| Product | Implemented workflows | Detailed scope |
| --- | --- | --- |
| Scope | Baselines/comparison, approval/client acceptance, Contracts source import and invoice handoff | [Scope](docs/scopes/scope.md) |
| Collect | CSV/ledger/aging, structured cases, capped reminder sequences, payment callbacks and delivery reconciliation | [Collect](docs/scopes/collect.md) |
| AMC | Assets/signed plans/windows, authoritative Scheduler appointments, scoped service evidence and accepted renewal offers | [AMC](docs/scopes/amc.md) |
| RFQ | Quotes/FX/taxes/duties, clarification/revision history, weighted awards and frozen comparison/PO exports | [RFQ](docs/scopes/rfq.md) |
| Tender | Cited extraction/OCR, conditional interpretation, targeted amendments, readiness and submission receipt | [Tender](docs/scopes/tender.md) |
| Handover | Templates/camera/repair progress/bulk assignment, limited links, photo reports and customer acceptance | [Handover](docs/scopes/handover.md) |
| OrderDesk | WhatsApp/audio review, variants/overrides, freight/backorders, authoritative Inventory reservations/dispatch, reconciliation and invoices | [OrderDesk](docs/scopes/orderdesk.md) |
| Batch | Effective recipes/lots, reservations/usage, structured costs/corrections, release/disposal/recall and labels | [Batch](docs/scopes/batch.md) |
| Fees | Agreements/concessions/late fees, evidenced receipts, withdrawal, guardian statements and academic separation | [Fees](docs/scopes/fees.md) |
| Renew | Notice calendars/escalation, verified usage, negotiated terms, requests/confirmations and next periods | [Renew](docs/scopes/renew.md) |
| SOP | Recording review, branching templates, publication, team/new-hire training, signoff and offline expiry | [SOP](docs/scopes/sop.md) |
| ClaimPack | Provider templates, evidence/provenance/conflicts, approved attachment redactions and frozen packets | [ClaimPack](docs/scopes/claimpack.md) |

Shared controls include roles/recovery, private evidence, frozen documents, financial/stock ledgers, durable jobs, reports, plans/billing, academic access, request limits, encrypted backups and isolated workspace-data erasure. External delivery is disabled by default.

- [Implementation and evidence](docs/BUILD_STATUS.md): 187 suite tests, 35 Inventory tests and 42 Scheduler tests, 41 Khata tests; 95 retained Invoicer checks; frontend build/audit, container, PDF and backup/restore checks.
- [Remaining integrations and release acceptance](docs/REMAINING_SCOPE.md): provider accounts, current browser/accessibility testing, pilot validation and production operations.
- [Connection setup](docs/INTEGRATIONS.md), [Invoicer source patch](integrations/invoicer/README.md), [scope of work](docs/SCOPE_OF_WORK.md) and [runbook](docs/OPERATIONS.md).
- [Deployment strategy](STRATEGY.md): build off-server and release immutable images after acceptance.

Current browser acceptance remains unverified because the browser tool rejected the local URL. Historical screenshots are not v0.6 acceptance. Credentials, application data, backups and dependencies are excluded from Git.

The broader portfolio index is `/Users/dev/projects/doaide/PRODUCT_INDEX.md`; existing products retain separate repositories and release status.

Authority configuration and boundaries: [Inventory and Scheduler](docs/AUTHORITATIVE_CONNECTIONS.md). Batch lot/quality balances and AMC parts now commit in Inventory. [Reviewed source imports](docs/PORTFOLIO_IMPORTS.md) cover the remaining portfolio dependencies. Deployed-account acceptance remains open.

## v0.6.1 release package

Strict production configuration, closed registration with owner bootstrap, private ClamAV scanning/signature freshness, graceful worker shutdown, resource limits, capacity preflight, off-site backup/restore receipts and HTTPS/backup monitoring are implemented. The actual Compose stack passes isolated acceptance with real ClamAV and disposable data. See [release procedure](docs/RELEASE.md) and [evidence](docs/evidence/production-stack-check.json). The existing production host fails capacity requirements; no production deployment or provider-account activation was performed.
