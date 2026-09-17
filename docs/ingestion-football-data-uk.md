# football-data.co.uk ingestion foundation

TASK 02A provides the auditable raw and staging boundary. TASK 02B extends that path
to canonical seasons, teams, aliases, matches, supported statistics, and data-quality
records. Canonical odds remain deliberately out of scope until TASK 02C.

## Registry and provider

The registry in `registry.py` contains exactly the seven approved domestic
competitions for seasons 2024/25 and 2025/26. Each entry records its canonical
competition, provider, source division code, country, football jurisdiction, and
explicit source URL. UEFA competitions are not registered because their ingestion
requires another source task. Adding later seasons means adding registry data; the
parser contains no season-specific behavior.

The runtime batch helper idempotently ensures one provider named
`football-data.co.uk`, with provider type `historical_csv`. No duplicate provider is
created when it already exists.

## Raw preservation and fetching

The downloader only performs HTTP retrieval and validation. It uses a 30-second
timeout, redirects, a PitchValue user agent, and normal HTTP error handling. It then
passes untouched response bytes to the raw store. Parsing never performs network
access.

Raw content is SHA-256 hashed before parsing. Files are stored beneath
`data/raw/football_data_uk` by provider, season, division code, and hash. Each new
artifact receives immutable first-seen JSON metadata recording its source URL,
competition, season, fetch instant, original filename, and byte hash. Identical bytes
resolve to the existing artifact. Changed bytes resolve to a new hash directory and
cannot overwrite earlier evidence. Real raw artifacts are ignored by Git; only the
directory placeholder is tracked.

Each CLI fetch creates an `import_batches` row before network access and ends it as
completed or failed. The batch stores the source URL and resulting source hash.

## Parsing, profiling, and staging

CSV is decoded deterministically as UTF-8 with optional BOM and parsed with Python's
standard `csv` module. Every source column, including unknown bookmaker or extra
columns, remains in the raw row object. Missing optional columns are allowed.

Blank and whitespace-only cells normalize to missing values. Literal numeric zero
remains zero. Invalid non-blank integers, decimals, dates, and times generate explicit
row errors. Decimal parsing uses `Decimal`. Dates accept only explicit day-first
`DD/MM/YYYY` and `DD/MM/YY` formats. Time is optional and is never fabricated when
absent; timezone conversion belongs to TASK 02B.

The profiler reports row count, columns, missingness, repeated deterministic row
hashes, malformed rows, date and numeric failures, and core-column availability.

`football_data_staging_rows` stores raw JSONB, source line number, row hash, parsing
status, and any rejection reason. `(import_batch_id, source_row_number)` is unique, so
retrying the same row in one batch is idempotent. Identical provider rows at different
source line numbers remain separate evidence and are surfaced by profiling.

Staging creates a running batch first and always transitions it to `completed`,
`completed_with_errors`, or `failed`. Existing database checks prevent negative batch
counters.

## Canonical mapping and validation

| Source                   | Canonical target                                                        |
| ------------------------ | ----------------------------------------------------------------------- |
| `HomeTeam`, `AwayTeam`   | `matches.home_team_id`, `matches.away_team_id` through provider aliases |
| `Date` + optional `Time` | `matches.kickoff_at_utc`; NULL when time is absent                      |
| `FTHG`, `FTAG`, `FTR`    | normal-time scores and `H`/`D`/`A` result                               |
| `HTHG`, `HTAG`           | paired nullable half-time scores                                        |
| `Referee`                | `matches.referee`                                                       |
| `HS`, `AS`, `HST`, `AST` | shots and shots on target                                               |
| `HC`, `AC`, `HF`, `AF`   | corners and fouls                                                       |
| `HY`, `AY`, `HR`, `AR`   | yellow and red cards                                                    |

Rows require the registered division, date, two distinct teams, non-negative complete
scores, and a result consistent with those scores. Half-time scores must be both
present or both absent. A malformed non-blank optional statistic makes the entire
row a staging rejection; a blank optional statistic remains NULL. A statistics row
is created only if at least one supported value exists. Possession and xG are never
fabricated.

Raw bookmaker fields are retained in staging, but TASK 02B performs no mapping into
`odds_snapshots`. Consequently `data_quality.odds_available` stays false. Imported
matches set `result_available` and deterministic `result_verified` true,
`stats_available` according to the actual supported values, and xG, lineup, injury,
and cross-provider flags false. `quality_score` remains NULL.

## Identity and idempotency

Season identity is `(competition_id, season_name)`. A source team is resolved by its
exact football-data.co.uk alias first. New aliases create new canonical teams; similar
names are never fuzzy-matched or automatically merged. Normalization uses Unicode
NFKC, conservative apostrophe/dash canonicalization, trim, whitespace collapse, and
case folding. It does not remove club words or city names.

An existing provider reference `(provider, source URL, source row hash)` takes
precedence for match replay. Otherwise, a timed row is reconciled on competition,
season, canonical teams, and UTC kickoff. A date-only row is reconciled through its
staging lineage, source date, and URL. Multiple candidates are recorded as ambiguous
and not merged. Provider match IDs remain NULL because these CSVs provide none; URL,
row hash, batch, staged-row identity, and explicit lineage retain traceability.

## Timezones and transactions

Local times are converted with `zoneinfo`: England and Scotland use `Europe/London`,
France `Europe/Paris`, Germany `Europe/Berlin`, Türkiye `Europe/Istanbul`, Portugal
`Europe/Lisbon`, and Spain `Europe/Madrid`. IANA rules provide DST behavior. No time
is invented when the source cell is blank.

Each attempt creates an audit batch before fetching. Immutable raw evidence is stored
before parsing. Staging and canonical work for one source then run in one transaction;
an unsafe failure rolls both back and marks the already-created batch failed in a new
transaction. Row-level deterministic validation issues produce
`completed_with_errors`. Replaying an identical file creates a new audit batch and
staging evidence but reuses canonical seasons, teams, aliases, matches, provider
references, and statistics.

## Commands

After setting `DATABASE_URL`, the Windows-compatible commands are:

```powershell
pitchvalue-ingest sources
pitchvalue-ingest profile tests/fixtures/football_data_uk/sample.csv
pitchvalue-ingest fetch E0:2024/25
pitchvalue-ingest stage E0:2024/25 data/raw/football_data_uk/<artifact-path>.csv
pitchvalue-ingest import-all
pitchvalue-ingest import-local E0:2024/25 data/manual/football_data_uk/E0_2425.csv
```

## Offline/manual recovery

When HTTPS acquisition is unavailable, place original provider files in the ignored
`data/manual/football_data_uk` drop directory and run `import-local` once per registry
entry. Expected filenames are `E0_2425.csv`, `E0_2526.csv`, `F1_2425.csv`,
`F1_2526.csv`, `D1_2425.csv`, `D1_2526.csv`, `T1_2425.csv`, `T1_2526.csv`,
`P1_2425.csv`, `P1_2526.csv`, `SP1_2425.csv`, `SP1_2526.csv`, `SC0_2425.csv`, and
`SC0_2526.csv`.

The command accepts only a registered source key. It checks that the file exists and
is non-empty, rejects HTML/XML error pages, parses the CSV, requires all core columns
and at least one data row, and requires every populated `Div` value to match the
selected registry entry. Valid original bytes are SHA-256 hashed and copied into the
same immutable content-addressed raw store used by network acquisition. First-seen
metadata records `acquisition_mode: local_manual`, the original local filename, and
the registry URL. That URL—not the local path—remains the import-batch source identity.

## Primary and fallback acquisition policy

Acquisition priority is deliberately fixed: (1) direct football-data.co.uk origin,
(2) a user-supplied original origin file, (3) an explicitly allowlisted and verified
raw-equivalent mirror, and otherwise (4) wait or request manual review. The system
never silently falls through to arbitrary URLs.

`mirrors.py` is the configuration allowlist. Each entry records its project homepage,
fixed URL template, upstream identity, source and season coverage, enabled state,
license note, limitations, and one of `raw_equivalent`, `likely_raw`, `transformed`,
or `unsupported`. Only enabled `raw_equivalent` entries can be fetched automatically.
`likely_raw` artifacts require review; transformed datasets cannot enter the raw
fallback path. At present, research found no candidate meeting the automatic
raw-equivalent threshold, so every configured candidate remains disabled.

The fallback downloader retains normal TLS verification, redirects, timeout, HTTP
error handling, and a fixed user agent. Valid bytes pass the same CSV/core-column and
division checks as manual input, then enter the same immutable raw store. Metadata
keeps `source_url` and `source_key` for canonical football-data.co.uk identity while
recording `acquisition_mode: verified_mirror`, `mirror_url`, `mirror_id`, mirror name,
timestamp, original filename, and SHA-256 separately. A mirror never redefines the
provider or canonical source URL.

`compare-artifacts` performs a read-only deterministic comparison. It reports both
hashes, row and column counts, columns present on only one side, conservative match-key
coverage, rows present on only one side, differing common-field values, and duplicate
key ambiguity. Identity is `Div`, `Date`, `HomeTeam`, and `AwayTeam`, with `Time` added
only when consistently populated in both inputs. It returns exact byte match,
semantic match with byte difference, data difference, or ambiguity without fuzzy team
matching.

```powershell
pitchvalue-ingest mirrors
pitchvalue-ingest fetch-fallback E0:2024/25 <approved-mirror-id>
pitchvalue-ingest compare-artifacts origin.csv mirror.csv
```

Fallback fetching only preserves reviewed raw evidence. It does not stage or import
canonical data; a later explicitly approved TASK 02B recovery step must do that.

Tests use only synthetic local fixtures and mocked HTTP responses. Live provider
availability is not required.
