# Operations and integration runbook

## Development

`make dev` starts the API at 127.0.0.1:8012 and the durable worker. Ctrl+C stops both. `make worker` is available when running the API separately. If `.env` exists, these Make targets load it through uv. Copy `.env.example` and set server-side values as needed; never commit credentials.

Create an intake record, save it, then open **Operations**. Add product entities under **Workflow**, attach evidence under **Files & documents**, and select a next action. The server checks the current workflow revision, membership role and prerequisites. **Activity** shows immutable operational events and background-job state. **Workspace tools** manages members, invitations, CSV imports, stock and connection status.

A committed document is not edited in place. Use **Create new draft revision** for Scope, RFQ, Tender, Handover, SOP and ClaimPack. Other products expose explicit renewal, ledger or stock actions. Old PDFs and acceptance evidence remain available. SOP publication supersedes the previous version without transferring its acknowledgements to the new one.

## Providers

`DOAIDE_DELIVERY_MODE=disabled` is the default. Jobs remain visible as blocked when a provider is unavailable. Configure provider variables, enable delivery intentionally, then retry eligible jobs from Activity. Starting the worker with delivery enabled can send already-queued jobs.

Email uses SMTP with TLS by default and a stable Message-ID. Working hours use the workspace timezone and weekdays. Consent, guardian eligibility, dispute/promise/opt-out state and current balance are checked again at delivery time. SMTP acceptance is not proof of inbox delivery; bounce/complaint callbacks are not integrated. Ambiguous SMTP failures or expired in-flight leases become blocked for reconciliation.

Razorpay uses server-only key ID/secret and webhook secret. Subscribe the configured endpoint `/api/webhooks/razorpay` to `payment_link.paid` and `payment_link.partially_paid`. Validate with test keys first. Link creation disables Razorpay's automatic email/SMS reminders. The adapter reconciles a unique reference before retrying creation. Callbacks validate HMAC-SHA256 over the raw request body, event ID, link reference, currency, amount and captured status. The same payment ID is posted only once. Overpayments are retained for manual allocation in the job result.

Official contracts inspected: [Razorpay payment-link events](https://razorpay.com/docs/webhooks/payment-links/), [webhook validation](https://razorpay.com/docs/webhooks/validate-test/), [payment-link APIs](https://razorpay.com/docs/api/payments/payment-links/).

## Draft invoice bridge contract

`DOAIDE_INVOICE_ADAPTER_URL` must be an HTTPS endpoint controlled by the organization; `DOAIDE_INVOICE_ADAPTER_TOKEN` remains server-only. The bridge must authenticate the bearer token and guarantee one draft per `Idempotency-Key`, including after timeouts. A POST body contains `source` (`doaide-scope` or `doaide-amc`) and an immutable `document` with source version, checksum and snapshot. Success must return JSON with a stable `invoice_id`. The worker records that reference and advances Scope to invoiced only after success.

The existing Invoicer upload/extraction endpoint is not compatible with this contract and is intentionally not called. Implement and validate the bridge against the chosen invoice API before enabling it. A draft-invoice PDF remains available locally while handoff is blocked.

## Files, OCR and retention

Uploads accept PDF, DOCX, PNG, JPEG, UTF-8 TXT and CSV up to 10 MiB. PDF extraction is limited to 100 pages, DOCX expanded content to 30 MiB, and images to 25 megapixels. OCR accepts up to 20 pages and uses local Tesseract and Poppler; the API process never calls an external AI service. OCR output is marked as needing review. File references do not count as verified business evidence until a reviewer performs the relevant action.

Install/configure ClamAV and maintained definitions, then set `DOAIDE_REQUIRE_MALWARE_SCAN=true` for a pilot requiring screening. Uploads fail closed when the required scanner is absent or fails. Without this setting, local files show `not-configured` scan status rather than a false clean result.

`DOAIDE_FILE_RETENTION_DAYS=0` keeps source files until a policy is chosen. A positive value applies a retention deadline to new uploads. `uv run python scripts/retention.py` previews expired source files. `--apply` removes their original bytes/extracted text, preserves checksums and metadata, and writes deletion events. Frozen PDFs/manifests remain; this is not comprehensive account-data erasure. Existing file references cannot be reused after source deletion.

## Backup, restore and rollback

Run `make backup`. SQLite's online backup API creates a new mode-0600 backup including file/PDF BLOBs. The script checks integrity and foreign keys, restores into a temporary directory, applies additive migrations, compares core counts and never overwrites the active database. Copy backups to approved encrypted storage separately.

Before a deployment, stop the worker and take a backup. Build immutable images off-server. Deploy the app and worker using `compose.production.yml` with image digests, a shared local volume, and environment credentials. The provided deployment keeps the API bound to host loopback; a reviewed HTTPS reverse proxy is required for external access. SQLite deployment is one host with one API/worker pair; multi-host scaling requires a database migration.

Build API: `docker build --target runtime -t <immutable-tag> .`

Build optional OCR worker: `docker build --target ocr-worker -t <immutable-tag> .`

For rollback, stop both processes, retain the current database and logs, deploy the previous image, and restore the pre-upgrade backup into a **new** volume if its schema is required. Verify integrity, record counts, health and a read-only sample before switching traffic. Reconcile provider jobs before restarting the worker; database rollback cannot undo an external message or payment.

## Known deployment limits

Email verification and recovery endpoints are implemented and use the SMTP queue. Enable required verification only after testing delivery. Recipient-entered names on client links are not independently verified legal identities. Malware screening, encryption at rest, provider credentials, reverse proxy/TLS, production monitoring, workload limits and pilot acceptance require deployment configuration and validation. Commercial plans, usage budgets and Stripe test-mode billing are implemented as described below. Configured-provider and production acceptance remain open.

## Verification and recovery

The sign-in screen can request a verification or password-reset email. Requests use the same response for eligible and unknown accounts. Tokens are random, stored hashed in the token table, expire (24 hours for verification, one hour for reset), and can be used once. New requests supersede older tokens; the worker will not deliver expired, used or replaced links. Password reset revokes all previous sessions. Access logs redact portal, contractor, invitation and auth bearer tokens.

Keep `DOAIDE_REQUIRE_VERIFIED_EMAIL=false` for local-only work without SMTP. After SMTP delivery has been tested, set `DOAIDE_PUBLIC_URL` to the reviewed HTTPS app URL and `DOAIDE_REQUIRE_VERIFIED_EMAIL=true`. New registration queues verification; existing unverified accounts must request verification before their next login. `DOAIDE_DELIVERY_MODE=enabled` is also required to send mail. Never enable required verification before the delivery configuration is usable.


## v0.3 plans, budgets and test billing

`DOAIDE_BILLING_MODE=local` preserves unlimited local use. The only alternative is `stripe-test`; live modes and live secret keys are rejected. Configure `STRIPE_TEST_SECRET_KEY`, `STRIPE_TEST_WEBHOOK_SECRET`, `DOAIDE_BILLING_BASE_PLAN` and a JSON `DOAIDE_BILLING_PLANS` map. Each plan has `name`, `products` (suite slugs), and `limits` with exactly `records`, `members`, `source_bytes`, `jobs_per_month`. Each limit is a nonnegative integer or null (unlimited). The base plan has no `price_id`; subscription plans map to unique recurring Stripe test Price IDs. Choose actual pricing and budgets with the business owner before configuring them.

Example shape only, with no actual price or commercial recommendation:

```json
{"base":{"name":"Evaluation","products":["scope"],"limits":{"records":20,"members":2,"source_bytes":10485760,"jobs_per_month":50}},"suite":{"name":"Configured suite plan","price_id":"price_REPLACE","products":["scope","collect","amc","rfq","tender","handover","orderdesk","batch","fees","renew","sop","claimpack"],"limits":{"records":null,"members":null,"source_bytes":null,"jobs_per_month":null}}}
```

Keep this catalogue server-side. Owner-only Workspace tools → Plan & usage prepares checkout or portal jobs; follow the returned Stripe test link manually. No access is granted by the return URL. Subscribe the provider webhook to `checkout.session.completed`, `customer.subscription.created/updated/deleted`, `invoice.paid` and `invoice.payment_failed`, targeting `/api/webhooks/stripe-billing`. Configure a test-mode snapshot-event endpoint. The adapter pins API version `2025-06-30.basil`.

Signed events check the raw body, HMAC and five-minute timestamp tolerance, deduplicate events and enqueue current-subscription reads. Billing jobs serialize per workspace; provider state, rather than event order, controls entitlements. An hourly job recovers missed events. Active/trial access expires at the provider period/trial end; inactive, unknown or conflicting plans revert to the base plan. Network failures retain previously verified access only until that bounded expiry. Multiple current subscriptions are blocked for reconciliation. No proration, seat quantity billing, tax policy or live charging is inferred.

Record budgets include archived records and all creation paths. Source-byte budgets include source BLOBs copied into revisions, but not generated immutable PDFs. Job budgets count optional jobs created in the current UTC calendar month; auth email, billing reconciliation and financial callbacks are exempt. Seat admission is checked when an invitation is accepted. All admissions run inside the same write transaction as the mutation. Product entitlements control creation; they do not revoke access to previously saved records or block financial corrections.

Provider contracts inspected: [Checkout Sessions](https://docs.stripe.com/api/checkout/sessions/create), [portal sessions](https://docs.stripe.com/api/customer_portal/sessions/create), [subscriptions](https://docs.stripe.com/api/subscriptions/retrieve), and [webhook handling](https://docs.stripe.com/webhooks). Adapter behavior is mock-tested; real account acceptance is still required.

## Reports, schedule amendments and stock corrections

Workspace tools → Reports provides all-product summaries, attention queues, financial aging and CSV exports. Report totals omit archived records; accounting exports retain them. Collect and Fees are separate books and may represent the same underlying obligation: do not add their balances as revenue. Accounting exports identify intake carry-forwards separately from manual and verified-provider ledger entries and keep integer paise. This is an operational export, not a statutory chart of accounts.

Fees → Approve remaining-fee reschedule replaces only unpaid tuition, retains the paid portion on its original dates, records reviewer/reason and freezes an amendment PDF. Previous receipt bytes and schedule snapshots are unchanged. Later refunds reopen the original paid obligation. Charges are separate dated obligations; allocation pays tuition first, then charges. Draft schedules that do not reconcile use the intake schedule for balances with an explicit warning.

Renew → Notice reminder policy specifies offsets, working hours, consent and backup delay. Schedule notice milestones creates deduplicated owner and backup jobs. Past offsets collapse into one catch-up reminder; missed offsets stay visible. A current named owner/backup can acknowledge responsibility, cancelling pending jobs. Changing dates, terms, owners or policy recomputes unsent jobs and clears the old acknowledgement; delivery rechecks the current fingerprint. If budgets prevent replanning, old jobs are cancelled and the workflow reports that new scheduling is needed. No email is sent without the separate delivery configuration. Rollover requires vendor evidence and retains previous-term links and copied terms.

OrderDesk/Batch Operations → Correct a physical stock count requires current quantities, evidence, reference and reviewer authority. Counts cannot become negative or consume another order's reserved stock. Quarantined/recalled additions and removals remain fully held. These are quantity adjustments, not automatic restatement of historical production cost or financial credit notes.

## Readiness and diagnostics

`GET /api/ready` reports schema/database readiness without exposing details. `DOAIDE_REQUIRE_WORKER=true` also requires a poll within 180 seconds or an unexpired running-job lease (up to fifteen minutes). `GET /api/diagnostics` is owner-only and reports safe schema/worker/queue information. Docker health checks use readiness. These endpoints do not replace external alerting or uptime monitoring.

`uv run python scripts/check_reports.py` runs a temporary 1,200-record reporting fixture. It does not modify the live database, create provider transactions or establish production load capacity. Schema 4 remains additive; restore the pre-upgrade backup into a new volume when rolling back to an older image.


## v0.4 connections and access

See [INTEGRATIONS.md](INTEGRATIONS.md) for workspace-specific Invoicer/Contracts credentials, the real Invoicer migration, signed WhatsApp intake and consented Groq transcription. Copy the blank variables from `.env.example`; keep secrets off Git and out of browser bundles.

Owners can set a member's Fees access to Academic in Workspace tools. That member sees an enrollment register without fee amounts, financial documents, receipts, evidence, jobs or accounting exports. Owners retain financial access. This restriction is enforced by API authorization and report filtering.

SOP → Configure automatic new-hire enrollment explicitly enables worker enrollment for new workspace members on the current published procedure. Assignments are deduplicated. It does not acknowledge training or pass assessments for anyone. Disable the policy to stop future automatic assignments. Reminder consent is a separate action.

OrderDesk reservations receive an expiry (24 hours by default, configurable in Delivery). The worker releases expired holds and removes confirmation. Dispatch also checks expiry, so a stopped worker does not make an expired reservation dispatchable. Reprice and confirm before reserving again.

ClaimPack redaction requires a separately uploaded redacted file and reviewer approval against the verified original. Released PDF/ZIP attachments use the approved derivative and retain original/replacement hashes. The private source remains intact. Review the exported packet, factual narrative and any hidden text/metadata in replacement PDFs; merely drawing an opaque box is not secure redaction.

## Authenticated encrypted backups

Use a private key file stored separately from backups. No key is generated or written into the repository automatically.

```bash
uv run python scripts/encrypted_backup.py --create-key --key-file /private/path/doaide-backup.key
uv run python scripts/encrypted_backup.py --key-file /private/path/doaide-backup.key --database var/doaide.db --output /private/backup/path/doaide-snapshot.enc
uv run python scripts/encrypted_backup.py --key-file /private/path/doaide-backup.key --decrypt /private/backup/path/doaide-snapshot.enc --output /private/restore/path/restored.db
```

Each command creates a new file and refuses overwrite. Keys must be regular private files (0600); encryption uses authenticated Fernet and verifies a round trip. Decryption checks SQLite integrity/foreign keys before publishing a restored file. Keep plaintext restoration isolated. The tool supports snapshots up to 512 MiB; larger deployments need a streaming backup system. Configure private off-site storage, key custody/rotation and backup expiry in the target environment. Fernet authenticates content but exposes token creation time; see [Fernet documentation](https://cryptography.io/en/latest/fernet/).

## Workspace-data erasure

Stop the API and worker, reconcile any running jobs, and review an approved retention/erasure policy before execution. Preview first:

```bash
uv run python scripts/erase_workspace.py --database var/doaide.db --workspace WORKSPACE_ID --policy APPROVED_POLICY_REFERENCE
```

Only an explicit repeat with `--execute --confirm-workspace WORKSPACE_ID` erases that workspace's product records, files, documents, financial/stock entries, imports, jobs and operational audit data. It checks foreign keys and compacts SQLite after the transaction. Account identities/memberships and provider-event deduplication identifiers are retained. Separately expire backup copies and handle account closure under the approved policy. This tool has been tested only on disposable fixtures during implementation; no real workspace was erased.

## Request and release checks

The API bounds request bodies before parsing and keeps rate counters in SQLite across processes. Defaults are 600 API and 120 public-link/webhook requests per minute per client IP. Configure limits for your traffic. Forwarded headers are not trusted by the middleware; configure Uvicorn's trusted proxy addresses deliberately so legitimate clients do not share a proxy's bucket. Do not expose diagnostic or administration endpoints through a public bypass.

`uv run python scripts/check_documents.py` creates synthetic PDF fixtures through actual API workflows. Render and review them after layout changes. GitHub Actions runs locked dependency setup, tests, frontend build/audit and isolated container checks; it does not deploy.
