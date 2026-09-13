# Explicit mapping and multi-window shadow durability

The 2026/27 5DFA mapping review is an explicit provider-team-ID manifest in
`providers/five_dfa/team_mapping_review.py`. Normalized names may help an operator discover a
candidate, but they never authorize assignment. Every accepted mapping records the reviewed
source ID, canonical target, review version, provider alias, and provenance. Teams seen only in
Serie A are retained as source identities with `UNSUPPORTED` status and are not added merely to
improve a completeness metric.

The reviewed inventory currently contains 27 supported-scope decisions and 18 out-of-scope
decisions. Nine supported 2026/27 teams absent from the historical canonical corpus may be created
only through those explicit decisions. Reapplying the manifest reuses both canonical teams and
provider aliases. The combined mapping contract version participates in deterministic run identity,
so changing either the provider mapping or explicit review version creates a distinct semantic run
without rewriting older evidence.

## Bounded authenticated replay

The persisted shadow command accepts `--max-fixtures` to select the first bounded set ordered by
kickoff and opaque provider fixture ID. `--verify-replay` fetches the fixture window once, caches
per-fixture odds responses in memory, and persists the same semantic input twice. This validates
fixture, source-reference, statistics, odds, DQ, operational, quarantine, and shadow idempotency
without doubling provider requests.

```powershell
python -m pitchvalue.operations.persisted_shadow_run `
  --start-date 2026-09-13 `
  --end-date 2026-09-13 `
  --as-of 2026-09-12T23:20:22.592946+00:00 `
  --max-fixtures 3 `
  --verify-replay `
  --report-directory "C:\Users\admin\PitchValue Engine Reports"
```

Runs remain internal. Shadow rows are database-constrained to
`publication_eligible = false`; public prediction snapshots are not created. Final fixtures may
persist authentic scores, but finished or in-play fixtures are not analyzed as upcoming targets.
Missing statistics remain `NULL`, explicit zero remains zero, and unsupported statistics are not
invented.

Role-only odds remain `MARKET_REFERENCE_ONLY` with canonical `observed_at = NULL`.
`TIMESTAMP_GATE = PENDING`, `MARKET_STABILITY = UNAVAILABLE`, Bet Score remains nullable, and no
repeated local collection is treated as exact-time market history. The Free plan, public scheduler,
public PICK generation, rejected calibration, and rejected ensemble remain inactive.
