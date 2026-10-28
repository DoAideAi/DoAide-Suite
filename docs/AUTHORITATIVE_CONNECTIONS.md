# Inventory and Scheduler ownership

28 October 2026 · Suite v0.5 · schema 5

The existing Inventory service owns connected OrderDesk product/warehouse quantities and reservations. Scheduler owns connected AMC appointments. Suite owns order review/confirmation, contract terms and service evidence. Unconnected workspaces retain their local workflows. Neither adapter sends notifications.

## Service installation

The actual service implementations are in the local `DoAide-Inventory` and `DoAide-Scheduler` checkouts on `codex/authoritative-portfolio-adapters`. Complete patches, base commits and installation instructions are retained under `integrations/inventory` and `integrations/scheduler` in this organization repository. Production services have not been changed.

Apply the relevant patch to a test checkout. From that service's `backend/`, with an explicitly configured **test** `DATABASE_URL`, run `python scripts/migrate_suite.py` before starting the new server. This creates only `suite_reservations` or `suite_bookings`, checks business/reference uniqueness and preserves existing data. Re-running is safe. Scheduler checks that deleted bookings leave a retained reference tombstone. Back up the deployment database before rollout; roll back application code without deleting reference history.

## Workspace configuration and activation

Keep tokens in deployment secrets. Both services use their existing bearer authentication and enforce business access. Inventory requires staff or above; Scheduler requires owner/admin. Tokens can expire and must be rotated by the operator; an expired token blocks delivery visibly.

Configure one mapping entry per Suite workspace ID:

```json
{"workspace-id":{"url":"https://inventory.example","token":"PRIVATE","business_id":1,"warehouse_id":2}}
```

Use `DOAIDE_INVENTORY_CONNECTIONS` for that mapping. Inventory's URL is its service root. For Scheduler use `DOAIDE_SCHEDULER_CONNECTIONS` with `url` ending in `/api/v1`, the private token and `business_id`; omit `warehouse_id`.

`DOAIDE_DELIVERY_MODE=enabled` permits the worker to call configured services. It remains disabled by default. HTTPS endpoints reject redirects and embedded credentials. Each command includes the expected business ID; the service rejects a token belonging to another business **before any mutation**. The Suite pins the endpoint, business and warehouse at activation. Restoring credentials never changes ownership. Switching a pinned business/warehouse requires an explicit migration; changing environment values does not silently retarget outstanding commands.

An owner activates Inventory with **Refresh connected Inventory catalogue** on an OrderDesk record. Existing local catalogue rows prevent activation: balances, reservations and historical references need a deliberate migration, or use a clean test workspace. Refresh caches up to 10,000 catalogue rows in one selected warehouse. Cached counts are labelled as snapshots and cannot be adjusted locally. Pack size defaults to one base unit. Product prices, taxes and units are checked again by Inventory when reserving. Explicit Suite price overrides remain recorded commercial decisions; they do not edit Inventory's price list.

An owner activates Scheduler with **Activate connected Scheduler for new visits**. Existing local visits retain their original mode; new visits require a Scheduler meeting-type ID, customer email and a technician email that matches an active host in the connected business. Duration must match the meeting type. Availability uses the host's timezone; conflict checks include both meetings' buffers and the daily limit. Hosts and availability rules are managed in Scheduler.

## Command lifecycle and recovery

- Inventory reservations are business/reference unique, compare immutable contents and expire within seven days. A replay returns the current status. Dispatch deducts on-hand stock once; cancel/expiry releases the hold. Native count edits, adjustments, purchase receiving and sales shipping share the business transaction lock. Native shipping cannot consume held stock.
- Scheduler bookings are business/reference unique. Create, reschedule and cancel do not send email. Reschedule/cancel use stable command keys. Native/public booking writers share the calendar lock and conflict checks. Deleted bookings retain a tombstone and cannot be recreated by a retry.
- Suite freezes a command in its durable outbox and shows pending status until it receives an authoritative receipt. Timeouts retry the same reference. Removed credentials, changed endpoints, inactive members and rejected commands block visibly. No local balance/booking is substituted.
- For a transient failure, an owner retries the same job in Workspace tools. For a conflict or ambiguous outcome, use **Reconcile Inventory reservation** or **Refresh Scheduler booking**. Only finished failed/blocked jobs can be superseded; an in-flight job cannot be replaced. Reconciliation serializes with writes and retains a tombstone when the reference is absent, preventing a delayed original request from committing afterward. A confirmed missing reservation restores the order to confirmation; a missing booking uses a new linked reference through **Retry a missing Scheduler booking**. Superseded jobs cannot be retried.
- Refresh failures can be retried with the same refresh action. Invalid multi-row catalogue results roll back completely. Service-side changes to a booking are read by refresh; a different host requires review. Connected visits must have a confirmed Scheduler refresh within five minutes before starting or reporting completion. Completion and independent verification remain evidence-based Suite actions.
- Records with pending external commands or open connected appointments cannot be archived. The worker does not dispatch stock, book appointments or send messages merely because it sees an unreviewed incoming order.

## Acceptance and boundaries

`uv run python scripts/check_authorities.py --inventory ../DoAide-Inventory/backend --scheduler ../DoAide-Scheduler/backend` starts both real applications with temporary databases and exercises Suite → Inventory reserve/dispatch and Suite → Scheduler create/reschedule/cancel. Synthetic HTTPS hostnames are routed only to those isolated HTTP processes; this validates contracts and persistence, not deployed TLS or account configuration. It creates no real customer booking or message.

Unit/integration tests cover concurrent competing holds/bookings, replay after response loss, stock protection from native writers, conflict recovery, business/role isolation, deleted-booking tombstones and repeatable additive migrations. SQLite concurrency is exercised; deployment-specific PostgreSQL load, TLS, provider calendar synchronization and configured-account acceptance remain rollout checks.

**Deployment boundaries:** Scheduler's Google calendar integration remains an existing service capability; this adapter checks Scheduler bookings and availability. Applying the service patches, configuring accounts and accepting the deployed integration remain rollout requirements. See [REMAINING_SCOPE.md](REMAINING_SCOPE.md).


## v0.6 Batch lots and AMC parts

Apply the third Inventory patch and rerun `backend/scripts/migrate_suite.py` against the backed-up test database. It creates `suite_lots`, `suite_batches` and `suite_lot_commands` in addition to the existing reservations table, verifies uniqueness, and preserves all existing tables and records. Native product balances remain integer quantities; the separate lot ledger uses exact decimal strings with up to six decimal places. The Inventory Stock screen shows lot on-hand, held, quality and expiry by warehouse.

For **Batch**, an owner uses **Activate Inventory lot ledger** in a workspace without existing local lot/finished balances. Existing catalogue activation is shared with OrderDesk/AMC. Historical local balances need an explicit reconciled migration; the activation never copies or overwrites them implicitly. The endpoint, business and warehouse remain pinned. Receive quarantined/released lots; reserve inputs; record production; return unused non-waste inputs; release or reject output; dispatch; recall and dispose through the Batch actions. Quality and count corrections require reviewer approval and evidence in Suite, and a manager/owner credential in Inventory. Expiry is checked on the Inventory host's calendar date; keep that host's timezone consistent with the business operating calendar.

Each mutation validates Suite's recipe, costing, stage and evidence rules in a rolled-back preflight transaction. Inventory then commits the lot operation atomically under its business lock and retains the command fingerprint and before/after balances. Only a matching receipt publishes the Suite stock projection, stage and documents. A cache mismatch blocks completion for reconciliation. Pending commands freeze edits. A timeout retries the same reference; **Reconcile pending Inventory lot command** retrieves its receipt or fences a missing command against late delivery. A failed refresh can be replaced by **Refresh Inventory lots**. Native warehouse deletion rejects nonzero lot or product balances and active product holds.

For **AMC**, **Activate / refresh Inventory parts catalogue** connects the same warehouse. Map each part to an Inventory SKU; connected parts use whole catalogue units. **Reserve visit parts in Inventory** creates a 24-hour reservation for all lines on the visit. After service completion, **Confirm used parts in Inventory** consumes the reserved parts exactly once. Release unused reservations or reconcile an uncertain command before editing. Reserved/consumed part lines cannot be overwritten or deleted, and records with active holds cannot be archived. Billing requires confirmed Inventory consumption, plus the existing independent service verification. Parts sale charges remain reviewed Suite amounts and do not change Inventory catalogue prices.

The cross-service acceptance script now also exercises fractional receiving, reservation, production, return, quality release, dispatch, recall/disposal and AMC parts consumption. It uses three temporary databases, with zero external provider requests. Deployment-specific PostgreSQL concurrency, configured-account acceptance and migration of pre-existing local balances remain explicit rollout work.
