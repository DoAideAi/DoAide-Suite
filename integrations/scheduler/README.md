# Scheduler authoritative Suite contract

Actual source checkout: `/Users/dev/projects/doaide/DoAide-Scheduler`.
Branch: `codex/authoritative-portfolio-adapters`.
Base commit: `a9e60b027055bd7629718aea693b45ff741b6d15`.
Implementation commit: `c3973c0594d4568699ced72539b38603f4dbb6d6`.

The full patch in [0001-suite-bookings.patch](0001-suite-bookings.patch) is published in the DoAide organization repository so the new service code, migration and tests are retained alongside its Suite adapter. The existing service's remote and production deployment are unchanged.

Apply in a test checkout based on the recorded base:

```bash
git am /absolute/path/to/DoAide-Suite/integrations/scheduler/0001-suite-bookings.patch
cd backend
# Set DATABASE_URL explicitly to the initialized test database before this command.
python scripts/migrate_suite.py
python -m pytest tests -q
```

See [ownership and rollout](../../docs/AUTHORITATIVE_CONNECTIONS.md) for connection settings, business/warehouse mapping, reconciliation and limitations. Back up the target database and retain reference/tombstone history through rollback. The migration is additive and tested twice against an initialized database containing retained data.
