# Invoicer draft handoff

The existing Invoicer had upload/extract/list/update routes but no draft-create endpoint. This directory contains the complete implementation patch, migration and tests.

- Local checkout: `/Users/dev/projects/doaide/DoAide-Invoicer`
- Base: `df72b36e8c8afd64659c73f9b1f99274c09e8dbd`
- Implementation: `436a1cc` on `codex/suite-invoice-handoff`
- Validation: all 95 Invoicer tests pass.

On a clean test-service checkout at the base commit, apply `git am /absolute/path/to/0001-suite-invoice-drafts.patch`, install the existing dependencies and run `python scripts/migrate_suite_handoffs.py` with an explicitly configured test `DATABASE_URL`. Run `python -m pytest -q` before releasing that service. The local checkout already contains this commit; do not apply it again there. Production has not been migrated.

`POST /api/v1/invoices/drafts` accepts `{source, document}` with the existing JWT bearer authentication and `Idempotency-Key` header. It verifies the canonical SHA-256 snapshot, source identity and integer-paise total; creates one draft/line item; retains the source snapshot; increments usage once; and returns `invoice_id`. Identical retries return the same invoice, conflicting content returns 409, and references are scoped to the authenticated account.

GST breakdown and final tax-invoice approval remain in the Invoicer workflow. The adapter does not invent tax classifications from a combined source total. Configure its full HTTPS route and authorized account token under the suite workspace's `DOAIDE_INVOICE_CONNECTIONS` entry. Token rotation and actual deployed-service acceptance remain operator work.

Retries report the invoice’s current status. Deleted invoices retain a handoff tombstone and return 410 rather than recreating the draft. Authenticated owners can read `GET /api/v1/invoices/{id}/suite-source`. The existing detail UI now supports review/approval of imported drafts.

The additive installer verifies existing users/invoices tables, creates only `suite_handoffs`, validates columns/uniqueness/deletion semantics and is repeatable. It does not run or rewrite legacy Alembic history: the inspected history has a missing `001` predecessor for revision `002` and no complete initial-schema migration. Repairing that legacy history is separate existing-product maintenance.
