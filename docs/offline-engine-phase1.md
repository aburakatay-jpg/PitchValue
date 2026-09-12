# Offline engine activation — Phase 1

Phase 1 is a deterministic validation path over the existing canonical historical database. It
connects the leakage-safe feature dataset, temporal RAW ML evaluation, Elo, Poisson, Form, model
agreement, role-only historical market comparison, and prediction orchestration. It does not
fetch provider data, publish predictions, or persist validation output.

## Operator command

With `DATABASE_URL` configured for the existing local PostgreSQL database:

```powershell
python -m pitchvalue.operations.offline_validation --sample-size 12
```

The command prints one canonical JSON document to stdout. The sample size must be between 1 and
100. The command opens a repeatable-read transaction and tells PostgreSQL to enforce it as read
only before the engine is invoked. It records protected table counts before and after execution
and fails if they differ.

## Deterministic selection

The sample is derived from canonical rows rather than hard-coded match IDs. Selection prioritizes:

1. the earliest row without temporal OOS model evidence, when one exists;
2. the earliest row without canonical match statistics, when one exists;
3. the earliest executable temporal OOS row from every represented competition;
4. further executable rows in canonical kickoff/row-ID order until the requested size is reached.

This yields stable coverage of ordinary executable rows and available exceptional states without
cherry-picking model outputs. Identical database state, engine versions, and arguments produce the
same sorted JSON and SHA-256 fingerprint.

## Safety and status semantics

Every selected row is classified as exactly one of:

- `EXECUTABLE`: temporal RAW ML evidence exists and all leakage checks pass;
- `INSUFFICIENT_DATA`: no eligible temporal OOS model evidence exists;
- `QUARANTINED`: a hard historical-time or target-leakage invariant fails;
- `ENGINE_FAILURE`: an isolated per-match orchestration exception occurs.

Feature availability is explicit. Missing canonical match statistics are reported independently;
they do not become zero and do not block a model whose accepted feature contract does not require
them. Confirmed lineups, injuries/suspensions, exact market timestamps, Market Stability,
Calibration Confidence, and Final Check remain unavailable. Their absence does not get replaced by
heuristics.

For every feature, Phase 1 confirms `available_at <= prediction_as_of`. Every source match must be
strictly earlier than `prediction_as_of`, must not be the target match, and must not contain target
result or target-goal provenance. The target cutoff remains strictly before kickoff.

## Market behavior

Historical Bet365 source-prematch odds have role-only timing and `observed_at = NULL`. When a
complete eligible group exists, Phase 1 may run TASK 11/TASK 19 market math and TASK 20
orchestration as an internal reference, but labels the mode `MARKET_REFERENCE_ONLY`.

`TIMESTAMP_GATE = PENDING`

`MARKET_STABILITY = UNAVAILABLE`

`FINAL_CHECK_UNAVAILABLE`

No source-prematch role is interpreted as exact T-24 availability. No request, insertion, import,
or runtime timestamp is substituted for a market observation timestamp. When no usable market
group exists, the supported models run in `MODEL_ONLY` mode and edge is unavailable.

## Read-only and publication guarantees

- PostgreSQL enforces the default command transaction as read only.
- No provider client is imported or called by the execution path.
- No row is written to `prediction_snapshots`, operational run/event tables, DQ evidence tables, or
  canonical historical tables.
- Results exist only in the stdout JSON document unless an operator redirects it explicitly.
- `publication_eligible` is always false.
- A role-only orchestration result is never promoted to an exact-time or public prediction.
- No scheduler, background polling, public API write, or live prediction path is activated.

Phase 1 validates engine execution only. It does not establish profitability, market superiority,
provider timestamp validity, Market Stability, Final Check, or public launch readiness.
