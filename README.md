# DoAide product suite

Operational local workflows for **Scope, Collect, AMC, RFQ, Tender, Handover, OrderDesk, Batch, Fees, Renew, SOP and ClaimPack** in one workspace.

See the [product index](PRODUCT_INDEX.md), [implementation status](docs/BUILD_STATUS.md), [remaining scope](docs/REMAINING_SCOPE.md), the [detailed scope of work](docs/SCOPE_OF_WORK.md), and the [operations runbook](docs/OPERATIONS.md). The app now includes shared teams, operational entities, evidence files, approvals, frozen documents, financial/stock ledgers and durable jobs. v0.6 completes the outstanding portfolio adapter code, including authoritative Batch lots and AMC parts, reviewed Desk/Realty/Khata/Proposals/Payroll imports and course enrollment CSVs. See [authority setup](docs/AUTHORITATIVE_CONNECTIONS.md) and [source imports](docs/PORTFOLIO_IMPORTS.md). v0.6.1 adds the production runtime, real ClamAV scanning, graceful worker lifecycle and release/backup/monitoring tools. Follow the [release procedure](docs/RELEASE.md); the existing host fails capacity checks. Configured-account, browser, pilot and production acceptance remain open.

Repository: [DoAideAi/DoAide-Suite](https://github.com/DoAideAi/DoAide-Suite). All twelve products share this repository and application.

## Start

Requires Python 3.12+, uv and Node.js 20.19+.

```bash
cd /Users/dev/projects/doaide/DoAide-Suite
make setup
make build
make dev
```

Open [DoAide locally](http://127.0.0.1:8012). Create or sign in to a local account. Open a product, load a synthetic example or enter details, and **Save record**. Use **Operations** for the actual product workflow; **Files & documents** holds evidence and immutable exports. **Workspace tools** provides portfolio reports, accounting CSV exports, plan/usage controls, team invitations, imports and stock. Fees can reschedule unpaid instalments after receipts. Renew can schedule notice milestones and backup escalation. OrderDesk and Batch include evidence-backed stock-count corrections.

`make dev` starts both the API and job worker. Ctrl+C stops both. Files and PDFs are stored privately in `var/doaide.db`, so database backups include the evidence. Existing accounts and records migrate additively to schema 5; removed memberships remain removed across restarts. A verified backup of the pre-upgrade database is retained in ignored `var/backups`.

External delivery defaults to disabled. Configure `.env` from `.env.example` and follow the runbook before enabling any provider. The app never treats an unavailable integration as a successful message, invoice, payment or submission.

## macOS terminal issue

If Make reports `getcwd: Operation not permitted`, leave the inaccessible current directory first:

```bash
cd /
cd /Users/dev/projects/doaide/DoAide-Suite
make dev
```

The suite now lives outside Documents. An existing checkout at `/Users/dev/Documents/doaide/products/doaide-suite` links to this new location for compatibility; use the new path in terminal commands. The `dev` target exists in this suite's Makefile. For other folders with denied access, see [Apple's file-access instructions](https://support.apple.com/en-ie/guide/mac-help/mchld5a35146/27/mac/27).

## Validate and maintain

```bash
make check       # domain/API/integration tests, frontend build, npm audit
make backup      # consistent backup plus isolated restore verification
make scopes      # regenerate the 12 detailed scopes and index
```

The API reference is available at `/docs`. The frontend can be edited with `npm --prefix frontend run dev` while the API runs; Vite proxies `/api` to 8012. Build again to update the static app served by FastAPI.

## Source map

| File | Purpose |
| --- | --- |
| `backend/catalog.py`, `domain.py` | Intake contracts and deterministic calculations |
| `backend/operations_catalog.py`, `operations.py` | Operational forms, entities, state transitions and transactional business rules |
| `backend/operations_api.py`, `task_portal.py` | Team/workflow/file/document/client/contractor APIs |
| `backend/migrations.py`, `db.py` | Additive schema, SQLite transactions and credential hashing |
| `backend/documents.py` | Private ingestion, extraction, OCR and frozen PDF/evidence packets |
| `backend/commercial.py`, `billing.py` | Plans, budgets, Stripe test checkout/portal and authoritative reconciliation |
| `backend/reports.py`, `renewals.py`, `inventory.py`, `diagnostics.py` | Portfolio/accounting reports, notice automation, stock corrections and readiness |
| `backend/worker.py`, `webhooks.py`, `whatsapp.py`, `recordings.py`, `portfolio_connections.py` | Durable jobs, signed callbacks, audio review and workspace-scoped service adapters |
| `backend/workflow_catalog.py`, `workflow_extensions.py`, `access.py`, `security.py` | v0.4 workflow additions, academic permissions and request boundaries |
| `frontend/src/Operations.jsx` | Operational UI, workspace tools and limited external portals |
| `tests/test_commercial_reports.py` | Budget races, billing retries/signatures, rescheduling, report reconciliation, stock corrections and restart permissions |
| `tests/test_operations.py` | Product journeys, boundaries, concurrency and provider failure/replay tests |
| `scripts/backup.py`, `encrypted_backup.py`, `erase_workspace.py`, `retention.py`, `dev.py` | Backups/encryption, policy-driven erasure and local lifecycle |
| `Dockerfile`, `compose.production.yml` | Off-server build and immutable deployment definitions |

The Invoicer, Inventory, Scheduler and Khata service changes are separately committed; complete, base-pinned patches are included under `integrations/`. Production services were not changed. Follow [STRATEGY.md](STRATEGY.md) for releases: build off-server, deploy immutable runtime images, and verify restore/rollback.
