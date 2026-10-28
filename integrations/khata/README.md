# Khata read-only ledger export

Source checkout: `/Users/dev/projects/doaide/DoAide-Khata`.
Branch: `codex/suite-ledger-export`.
Base: `451333fdedb1350a45523492def4572d4e31a30d`.
Implementation: `1b919cd080639d290de3649f620d48f4d2c26ad9`.

[Complete patch](0001-read-only-ledger-export.patch) adds authenticated `GET /api/ledger`, returning only the caller's synced document and account email. It performs no merge/write. No database migration is required. Tests cover authentication, account isolation and preservation of the ledger; a stale sitemap test was updated to the existing route list. All 41 backend tests pass.

Apply with `git am /absolute/path/to/0001-read-only-ledger-export.patch` in a test checkout at the base commit, then run `backend/.venv/bin/python -m pytest backend/tests -q`. The actual endpoint passes isolated HTTP acceptance from Suite. The existing remote and production deployment are unchanged. Configure the Suite workspace mapping only after test deployment; see [source imports](../../docs/PORTFOLIO_IMPORTS.md).
