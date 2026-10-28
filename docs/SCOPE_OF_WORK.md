# DoAide Twelve Product Delivery Scope

Version 1.2 · 28 October 2026

This engineering scope covers Scope, Collect, AMC, RFQ, Tender, Handover, OrderDesk, Batch, Fees, Renew, SOP, and ClaimPack. Each product has an individual scope describing customer outcomes, roles, workflow, numbered functional requirements, domain entities, business states, integrations, exclusions, acceptance scenarios, current implementation, and subsequent milestones.

The local modular application now contains operational workflows for all twelve products. Shared teams, evidence files, approval links, immutable documents, financial and stock ledgers, background jobs and audit history support the product-specific commands. This remains a local operational build, with provider accounts, domain acceptance and production validation tracked separately in BUILD_STATUS.md.

## Product scope index and build order

| Product | Wave | Pilot complexity | Next milestone |
| --- | --- | --- | --- |
| [Scope](scopes/scope.md) | 1 | Medium | Operational local workflows; provider and pilot validation |
| [Collect](scopes/collect.md) | 1 | High | Operational local workflows; provider and pilot validation |
| [AMC](scopes/amc.md) | 1 | High | Operational local workflows; provider and pilot validation |
| [RFQ](scopes/rfq.md) | 2 | Medium | Operational local workflows; provider and pilot validation |
| [Tender](scopes/tender.md) | 3 | High | Operational local workflows; provider and pilot validation |
| [Handover](scopes/handover.md) | 2 | Medium | Operational local workflows; provider and pilot validation |
| [OrderDesk](scopes/orderdesk.md) | 2 | High | Operational local workflows; provider and pilot validation |
| [Batch](scopes/batch.md) | 3 | High | Operational local workflows; provider and pilot validation |
| [Fees](scopes/fees.md) | 2 | Medium | Operational local workflows; provider and pilot validation |
| [Renew](scopes/renew.md) | 2 | Low to medium | Operational local workflows; provider and pilot validation |
| [SOP](scopes/sop.md) | 3 | High | Operational local workflows; provider and pilot validation |
| [ClaimPack](scopes/claimpack.md) | 3 | High | Operational local workflows; provider and pilot validation |

## Architecture and repository decision

The source lives at /Users/dev/projects/doaide/DoAide-Suite, with the former products/doaide-suite path retained as a compatibility symlink. The Invoicer draft adapter is implemented on a separate local branch and distributed as a patch in integrations/invoicer. Production deployments have not been changed. The first version uses FastAPI, Python's SQLite interface, and React/Vite, consistent with the broad application patterns already present in DoAide. Currency calculations use Decimal. Product input contracts drive validation and form rendering; each product has a separate calculation branch with product-specific rules.

SQLite is the local operational store. Records belong to shared workspaces, with owner/operator/reviewer/viewer memberships and invitations. Separate expiring links scope external client, guardian and contractor access. Email verification and password recovery use expiring one-use links through the configurable email queue; provider delivery still needs pilot validation. Sessions use random opaque tokens, server-side hashed token storage, HttpOnly cookies, and an expiry. Passwords are scrypt-hashed with per-password salts. This is a local development authentication implementation, not a completed identity platform.

The additive schema includes memberships, entities, financial entries, stock movements, files, frozen documents, decisions, jobs and idempotency records. Product entity fields use validated JSON within typed resource rows. A pilot must assess the production database and scale requirements before migration. The existing portfolio uses PostgreSQL; InsForge is another available option, but its saved CLI authentication failed during setup. No cloud resources were created and no production credentials were copied into this repository. Backend selection for a pilot should follow the existing operational strategy and verified service access.

## Shared platform backlog

PLAT-01 — Identity and tenancy: verified identity, password reset, team memberships, roles, external-actor access, revoked sessions, and service account boundaries. Test cross-workspace access on every record, export, job and file operation.

PLAT-02 — Data and migrations: normalized product tables, versioned migrations, explicit money/currency types, timezone-aware timestamps, import batches, unique business references, optimistic locking and immutable event history.

PLAT-03 — Files and extraction: private uploads, content hashes, file limits, malware screening, OCR/extraction workers, source locators, retention, authorized download, and deletion workflows.

PLAT-04 — Durable work: transactional outbox, deduplicated job IDs, exponential retry with limits, dead-letter inspection, provider idempotency, signed callback validation, and reconciliation jobs.

PLAT-05 — Integrations: inspect actual DoAide product APIs before writing adapters; use separate test accounts; implement health/status checks and feature flags. An unavailable adapter must leave a clearly marked manual workflow.

PLAT-06 — Commercial controls: tenant plans, entitlements, billing in provider test mode, usage budgets and accounting exports. Pricing and willingness to pay remain discovery work.

PLAT-07 — Experience: keyboard and mobile journeys, useful empty states, accessible errors, import previews, date/currency formatting, confirmation of irreversible business actions, and version-aware review screens.

PLAT-08 — Operations: structured logs with sensitive fields excluded, error reporting, health/readiness checks, service limits, encrypted backups, verified restoration, immutable off-server builds, rollback artifacts, and data retention documentation.

## Delivery sequence

Wave 0 establishes the shared local application and all twelve first workflows, along with individual scopes and domain/API tests. This is the work started in this change.

Wave 1 deepens Scope, Collect, and AMC into pilots because they share client, invoice, contract, and scheduling concepts. Pilot discovery determines the actual API dependencies and required external communication channels.

Wave 2 adds RFQ, Handover, OrderDesk, Fees, and Renew using the tested shared identity, file, job, and document components. RFQ and Renew can precede provider-heavy workflows when adapter access is incomplete.

Wave 3 adds the document- and evidence-heavy Tender, Batch, SOP, and ClaimPack pilots. These require stronger versioning, source evidence, domain review, and in Batch's case a transactional inventory ledger.

This sequence is a dependency plan, not an instruction to ship every product simultaneously. Each pilot should complete its own acceptance scenarios before expansion. Calendar dates and budget estimates should be set after inspecting real source samples, provider access, and integration contracts; no fixed delivery promise is made here.

## Deliverables for each product

1. Versioned product scope and acceptance criteria.
2. User journeys, responsive interface, and empty/error/conflict states.
3. Backend input contracts, domain logic, authorization and durable records.
4. Tested domain migrations and a documented API.
5. Import/export and evidence handling where specified in the individual scope.
6. Verified integration adapters, retry behavior, and operator diagnostics where applicable.
7. Domain, API, integration and browser validation evidence.
8. Developer setup, example fixtures, operational runbook, backup/restore and rollback instructions.

## Current milestone boundaries

All twelve products have operational local workflows described in their current implementation sections. External sending is disabled by default; credentials and explicit server configuration are required to enable provider jobs. No live messages, payments, bids, disputes or production deployments were performed during development.

The suite is not certified as completing every production requirement in this scope. Configured email/recovery delivery, existing-product adapters, configured billing-provider acceptance, pilot-approved templates and current browser acceptance remain open. The v0.4 workflow additions close the product-feature checklist from v0.3; remaining portfolio adapters and release acceptance are tracked in REMAINING_SCOPE.md. Plan entitlements, usage budgets, test-mode billing adapters and reporting are now implemented. Scope requirements are retained rather than silently reduced. See BUILD_STATUS.md for tested behavior and remaining release work.

## Dependency and scope management

Business stakeholders should supply anonymized representative inputs, approved templates, definitions of pricing/tax/notice rules, and pilot feedback. Provider-specific behavior must be verified against current official documentation when implementing the adapter. Requirements that change evidence semantics, monetary rules, authority, or external actions need a versioned scope update and corresponding acceptance tests.

Reuse existing DoAide products through adapters rather than direct cross-product database writes. Keep stable external references and idempotency keys. Existing products retain their data ownership and release processes. No production server should build this application; follow the workspace STRATEGY.md for image creation, deployment, health checks, and rollback.

## Engineering references

- FastAPI security primitives: https://fastapi.tiangolo.com/tutorial/security/
- Python sqlite3 and transaction behavior: https://docs.python.org/3/library/sqlite3.html
- Vite development and build workflow: https://vite.dev/guide/
- Suite product index: [PRODUCT_INDEX.md](../PRODUCT_INDEX.md)
- Local portfolio reference: /Users/dev/projects/doaide/PRODUCT_INDEX.md
- Deployment requirements: [STRATEGY.md](../STRATEGY.md)
