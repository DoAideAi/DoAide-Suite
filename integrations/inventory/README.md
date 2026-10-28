# Inventory authoritative Suite contract

Actual source checkout: `/Users/dev/projects/doaide/DoAide-Inventory`.
Branch: `codex/lot-and-parts-integration`.
Base commit: `2302fde10e218715ee880db6bf306a3191ac5e85`.
Implementation commits: `14082a4`, `4179e459232b8fc589229939dfec7b34f7cfbbbc` and `46ffc65eba293acab0fedb1a4023fb4ce90af27c`.

The complete patches [0001-suite-reservations.patch](0001-suite-reservations.patch) , [0002-show-reserved-balances.patch](0002-show-reserved-balances.patch) and [0003-authoritative-lot-ledger.patch](0003-authoritative-lot-ledger.patch) are published in the DoAide organization repository so the new service code, migration and tests are retained alongside its Suite adapter. The existing service's remote and production deployment are unchanged.

Apply in a test checkout based on the recorded base:

```bash
git am /absolute/path/to/DoAide-Suite/integrations/inventory/*.patch
cd backend
# Set DATABASE_URL explicitly to the initialized test database before this command.
python scripts/migrate_suite.py
python -m pytest tests -q
```

See [ownership and rollout](../../docs/AUTHORITATIVE_CONNECTIONS.md) for connection settings, business/warehouse mapping, reconciliation and limitations. Back up the target database and retain reference/tombstone history through rollback. The migration is additive and tested twice against an initialized database containing retained data.
