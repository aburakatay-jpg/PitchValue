# V1 market direct code audit

This audit inspects the repository at the provider-independent checkpoint. `PARTIAL` means real
code exists for some layers but the complete probability-to-publication path does not.
Mathematical derivability is not treated as production readiness. No missing market is implemented
here.

## Shared evidence

- Canonical market/selection/line domains: `src/pitchvalue/prediction/contracts.py`,
  `MarketFamily`, `Selection`, `_MARKET_SELECTIONS`, `_MARKET_LINES`; covered by
  `tests/test_prediction_contracts.py`.
- Poisson market generation: `src/pitchvalue/models/poisson/probabilities.py`; direct market
  assertions are in `tests/test_poisson_probabilities.py`.
- Market validation/no-vig: `src/pitchvalue/markets/validation.py::MARKET_REGISTRY` and
  `src/pitchvalue/markets/implied.py::normalize_market`, version
  `task11_proportional_no_vig_v1`; covered by `tests/test_market_normalization.py`.
- Agreement: `src/pitchvalue/models/signals` behavior is represented by
  `tests/test_model_signal_agreement.py`; direction signals are not probabilities.
- Historical odds mapping: `src/pitchvalue/markets/history/config.py::FOOTBALL_DATA_MAPPINGS`
  contains Bet365 MATCH_RESULT only; tests are `tests/test_market_history_normalization.py`.
- Edge: `src/pitchvalue/markets/edge.py::build_market_probability` and
  `calculate_market_edge`, version `match_result_edge_v1`, explicitly reject non-MATCH_RESULT;
  covered by `tests/test_market_edge.py`.
- Orchestration/publication: `src/pitchvalue/prediction/orchestration.py::orchestrate_match`
  explicitly supports MATCH_RESULT only; `tests/test_prediction_orchestration.py`.
- Persistence/API are structurally market/selection capable in
  `src/pitchvalue/prediction/persistence.py`, `repository.py`, and
  `src/pitchvalue/api/prediction_models.py`, but their proven end-to-end fixtures are MATCH_RESULT
  (`tests/test_prediction_repository.py`, `tests/test_prediction_api.py`). Generic columns alone do
  not prove a new market production-ready.
- DQ evidence contracts are market-agnostic but no numeric score policy exists. Bet Score and
  public PICK remain blocked by model/evidence readiness.

## Audit matrix

| V1 market | Overall | Probability | Validation / no-vig | Edge / agreement | Persistence / API | DQ / Bet Score / publication |
|---|---|---|---|---|---|---|
| MATCH_RESULT / 1X2 | PARTIAL | RAW ML OOS plus Poisson; `ml/baseline.py`, Poisson tests | Complete mutually-exclusive three-way TASK 11 group | TASK 19 edge and TASK 10 agreement implemented | TASK 21/22 E2E tested | DQ score absent, RAW ML uncalibrated, public PICK disabled |
| OVER_UNDER_1_5 | PARTIAL | Poisson OVER/UNDER 1.5 in `tests/test_poisson_probabilities.py` | Decimal line and binary no-vig supported/tested | No production edge or orchestration path | Generic schema only; no E2E market test | Market-specific OOS/calibration, DQ, Bet Score, provider odds missing |
| OVER_UNDER_2_5 | PARTIAL | Poisson OVER/UNDER 2.5 tested | Decimal line and binary no-vig supported/tested | No production edge or orchestration path | Generic schema only | Market-specific OOS/calibration, DQ, Bet Score, provider odds missing |
| BTTS | PARTIAL | Poisson YES/NO tested | Binary validation/no-vig supported/tested | Descriptive agreement contract exists; no edge/orchestration | Generic schema only | Market OOS, DQ, Bet Score, provider odds missing |
| DOUBLE_CHANCE | PARTIAL | Poisson 1X/X2/12 sums tested | Canonical non-exclusive domain; conventional three-way no-vig intentionally rejected | No edge/orchestration | Generic schema only | Separate binary evaluation, market evidence, DQ, Bet Score missing |
| HOME_TEAM_GOALS O/U 0.5 | PARTIAL | Poisson home-team total 0.5 tested | Decimal line and binary no-vig supported/tested | No edge/orchestration | Generic schema only | Market OOS, DQ, Bet Score, provider odds missing |
| HOME_TEAM_GOALS O/U 1.5 | PARTIAL | Poisson home-team total 1.5 tested | Decimal line and binary no-vig supported/tested | No edge/orchestration | Generic schema only | Market OOS, DQ, Bet Score, provider odds missing |
| AWAY_TEAM_GOALS O/U 0.5 | PARTIAL | Poisson away-team total 0.5 tested | Decimal line and binary no-vig supported/tested | No edge/orchestration | Generic schema only | Market OOS, DQ, Bet Score, provider odds missing |
| AWAY_TEAM_GOALS O/U 1.5 | PARTIAL | Poisson away-team total 1.5 tested | Decimal line and binary no-vig supported/tested | No edge/orchestration | Generic schema only | Market OOS, DQ, Bet Score, provider odds missing |

MATCH_RESULT has the deepest implemented path, but remains `PARTIAL` for real publication because
the live provider, current DQ evidence, accepted calibration/stability evidence, and model-readiness
gate are absent. All other V1 markets are also `BLOCKED_BY_PROVIDER` for live odds and
`BLOCKED_BY_MODEL_EVIDENCE` for market-specific OOS reliability even where their overall audit
classification is `PARTIAL`.

## Recommended implementation order

1. **OVER_UNDER_2_5** — existing Poisson binary probability and TASK 11 line-aware no-vig have the
   strongest reuse; validate OOS evidence and actual provider market semantics before edge work.
2. **OVER_UNDER_1_5** — reuse the same TOTAL_GOALS path after 2.5 validates the architecture.
3. **BTTS** — complete Poisson binary and TASK 11 support, but separate OOS reliability is required.
4. **HOME/AWAY TEAM GOALS O/U 0.5**, then **1.5** — reuse binary/line primitives but introduce
   orientation and four distinct market-line evaluation surfaces.
5. **DOUBLE_CHANCE** — last because overlapping selections are not a mutually exclusive book and
   require explicit market comparison, evaluation, and policy semantics rather than a conventional
   three-way no-vig calculation.

This ordering is a recommendation from actual code reuse, missing edge/orchestration paths,
provider dependence, validation effort, and testability. It is not a frozen product roadmap.
