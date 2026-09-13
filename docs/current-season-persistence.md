# Current-season persistence and shadow durability

This batch adds the provider-neutral boundary between authenticated source reads and durable
internal shadow evidence. It does not activate scheduling, publication, or a paid provider plan.

## Schema review

The canonical `providers`, `competition_provider_refs`, `seasons`, `matches`,
`match_provider_refs`, `match_statistics`, and `odds_snapshots` tables remain the owners of
resolved football entities. Three gaps required revision `20260913_0011`:

- `source_entity_references` retains resolved and unresolved competition, team, and fixture
  source identities without making provider IDs canonical business IDs.
- `run_quarantines` can identify an unresolved source fixture without fabricating a canonical
  match.
- `shadow_analysis_snapshots` stores internal partial model evidence under a database check that
  permanently requires `publication_eligible = false`.

No provider-specific canonical table was introduced. `prediction_snapshots` was deliberately not
weakened: its historical staging-lineage and exact-publication contracts remain intact.

## Identity and mapping workflow

Source references are unique by provider, entity type, and provider entity ID. Exact canonical or
existing alias name matches may create a candidate mapping; there is no fuzzy merge. Unresolved
teams remain `UNRESOLVED`. An operator reviews those rows and calls the explicit assignment
boundary with an existing canonical team ID and a reviewed mapping version. Conflict and review
states remain representable. Unknown teams are not automatically inserted.

The provider registry stores `5DollarFootballAPI` with plan metadata `FREE`; no credentials are
stored. Runtime competition aliases map to existing canonical competitions. Serie A stays
unsupported. One `2026/27` season row is reused or created for each observed supported competition.

## Fixtures, results, and statistics

Canonical fixture identity uses competition, season, home team, away team, and kickoff. The
provider fixture ID is an external reference. Exact replay is unchanged. A kickoff change revises
the existing scheduled fixture. An apparent provider-ID replacement is quarantined for review.

Only an explicit `finished` provider status can persist a final score. A changed score for an
already-final match becomes `RESULT_REVISION_REVIEW`; it is never silently overwritten.

Only returned shots-on-target, possession, corners, and card values are persisted. Missing remains
NULL and explicit zero remains zero. No xG, total shots, or unsupported derived statistic is
invented.

## Operations, DQ, odds, and shadow output

Authenticated persisted runs reuse `engine_runs`, `operational_events`, `run_quarantines`, and the
versioned LIVE_OPERATIONAL data-quality tables. Run, event, quarantine, DQ, source, fixture, odds,
and shadow identities are replay-safe.

Provider odds are stored as `live_source` reference evidence with `observed_at = NULL`,
`timing_semantics = role_only`, and `timestamp_semantics_unproven`. Request, ingestion, database,
and runtime timestamps are not market observation timestamps. `TIMESTAMP_GATE = PENDING` and
`MARKET_STABILITY = UNAVAILABLE` remain unchanged.

Shadow analysis stores available RAW ML, Elo, Poisson, Form, agreement, DQ, odds mode, and version
evidence. Missing components remain unavailable. Bet Score remains NULL/PARTIAL. The dedicated
table rejects publication eligibility at the database level, and the public API reads only
`prediction_snapshots`; therefore internal shadow evidence cannot appear as a public PICK.

## Replay and transactions

Source and fixture sync is transactional. Each resolved fixture write uses a nested fixture-local
transaction, while systemic database failure aborts the run transaction. The analysis persistence
transaction atomically stores internal shadow, DQ, and odds evidence. An identical payload and
arguments reuse the same deterministic run identity and create no duplicate canonical fixture,
season, provider reference, event, quarantine, odds, DQ, or shadow row.

The authenticated command is:

```text
python -m pitchvalue.operations.persisted_shadow_run --start-date YYYY-MM-DD \
  --end-date YYYY-MM-DD --as-of ISO-8601 --report-directory PATH
```

It keeps the existing local report archive and never writes credentials. Scheduler activation,
public prediction generation, The Odds API, provider upgrades, and public PICK publication remain
outside this batch.
