# Authenticated 5DFA Free shadow run

The manual shadow command connects the authenticated 5DFA Free fixture feed to the existing
PitchValue model stack without enabling a scheduler, public PICK, or production prediction write.
The PostgreSQL transaction is enforced as read-only. Because no provider-neutral live-sync
repository currently exists, current-season fixture synchronization is a deterministic dry-run;
provider rows and mapping decisions are reported rather than inserted into canonical tables.

```powershell
$env:DATABASE_URL = "postgresql+psycopg://pitchvalue:local-development-only@localhost:5432/pitchvalue"
python -m pitchvalue.operations.manual_shadow_run `
  --start-date 2026-09-13 `
  --end-date 2026-09-13 `
  --as-of 2026-09-13T02:15:00+03:00 `
  --report-directory "$HOME/PitchValue Engine Reports"
```

`FIVEDFA_API_KEY` is resolved first from the process environment and then from the ignored root
`.env`. Its value is never serialized or included in error/report contracts. Runtime competition
names are mapped through explicit aliases. Team mappings require an exact normalized canonical or
alias match; no fuzzy merge occurs. Unsupported competitions and unresolved teams are quarantined.

The engine trains the accepted RAW ML baseline only from rows before `prediction_as_of`, creates an
outcome-free inference row, and runs Elo, Poisson, Form, and agreement where the safe-data gate
passes. Every feature and source-match timestamp is rechecked against the cutoff.

Current Bet365 responses retain their provider timestamp fields only as source evidence. They do
not establish canonical `market_observed_at`, so usable odds remain `MARKET_REFERENCE_ONLY` and no
publication-safe edge is calculated.

- `TIMESTAMP_GATE = PENDING`
- `MARKET_STABILITY = UNAVAILABLE`
- `FINAL_CHECK_UNAVAILABLE`
- `bet_score = NULL`
- `publication_eligible = false`

Reports are written to `YEAR/RUN_ID` beneath the selected local report root. The seven artifacts
contain deterministic machine-readable results and no credentials. No operational event or shadow
prediction is persisted until a provider-neutral, replay-safe live-sync/shadow persistence boundary
is separately implemented and reviewed.
