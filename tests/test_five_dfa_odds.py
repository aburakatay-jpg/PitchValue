from __future__ import annotations

from decimal import Decimal
from typing import Any

from pitchvalue.markets.history.contracts import TimingSemantics
from pitchvalue.prediction.contracts import MarketFamily, Selection
from pitchvalue.providers.contracts import CapabilityOutcome
from pitchvalue.providers.five_dfa.degradation import ProviderShadowInput, capability_decisions
from pitchvalue.providers.five_dfa.fixtures import parse_fixture
from pitchvalue.providers.five_dfa.mapping import map_competition, map_team
from pitchvalue.providers.five_dfa.odds import OddsDiagnosticCode, normalize_bet365_snapshot


def _payload(goal_line: object = None) -> dict[str, Any]:
    return {
        "fixture_id": 422841891,
        "bookmakers": [
            {
                "name": "Bet 365",
                "slug": "bet365",
                "recorded_at": "2026-09-12T10:00:00Z",
                "odds": {
                    "1x2": {
                        "opening": {"home": 1.53, "draw": 3.75, "away": 5.0},
                        "closing": {"home": 1.18, "draw": 5.5, "away": 15.0},
                    },
                    "btts": {
                        "opening": {"yes": 1.8, "no": 1.95},
                        "closing": {"yes": 1.72, "no": 2.05},
                    },
                    "goal_line": goal_line,
                },
            }
        ],
    }


def test_1x2_and_btts_are_decimal_role_only_nonpublication_observations() -> None:
    result = normalize_bet365_snapshot(_payload())
    match_result = [
        item for item in result.observations if item.market is MarketFamily.MATCH_RESULT
    ]
    btts = [item for item in result.observations if item.market is MarketFamily.BTTS]
    assert len(match_result) == 6 and len(btts) == 4
    assert {item.selection for item in match_result} == {
        Selection.HOME,
        Selection.DRAW,
        Selection.AWAY,
    }
    assert {item.selection for item in btts} == {Selection.YES, Selection.NO}
    assert all(isinstance(item.decimal_odds, Decimal) for item in result.observations)
    assert all(item.observed_at is None for item in result.observations)
    assert all(item.timing_semantics is TimingSemantics.ROLE_ONLY for item in result.observations)
    assert all(not item.publication_safe for item in result.observations)
    assert result.timestamp_gate == "PENDING"
    assert result.market_stability == "UNAVAILABLE"


def test_source_timestamp_name_is_preserved_but_not_promoted_to_observed_at() -> None:
    result = normalize_bet365_snapshot(_payload())
    assert result.observations[0].source_timestamp_evidence == (
        ("recorded_at", "2026-09-12T10:00:00Z"),
    )
    assert result.observations[0].observed_at is None
    assert OddsDiagnosticCode.TIMESTAMP_SEMANTICS_UNPROVEN in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_goal_line_1_5_and_2_5_map_only_the_actual_line() -> None:
    for raw_line in (1.5, 2.5):
        result = normalize_bet365_snapshot(
            _payload({"opening": {"line": raw_line, "over": 1.9, "under": 1.9}})
        )
        totals = [item for item in result.observations if item.market is MarketFamily.TOTAL_GOALS]
        assert len(totals) == 2
        assert {item.line for item in totals} == {Decimal(str(raw_line))}
        assert {item.selection for item in totals} == {Selection.OVER, Selection.UNDER}


def test_goal_line_2_75_is_not_mapped_to_a_fixed_pitchvalue_line() -> None:
    result = normalize_bet365_snapshot(
        _payload({"closing": {"line": 2.75, "over": 1.85, "under": 1.95}})
    )
    assert not any(item.market is MarketFamily.TOTAL_GOALS for item in result.observations)
    assert OddsDiagnosticCode.UNSUPPORTED_GOAL_LINE in {item.code for item in result.diagnostics}


def test_missing_selection_and_invalid_price_reject_complete_snapshot() -> None:
    missing = _payload()
    missing["bookmakers"][0]["odds"]["1x2"]["opening"].pop("draw")
    result = normalize_bet365_snapshot(missing)
    assert OddsDiagnosticCode.MISSING_SELECTION in {item.code for item in result.diagnostics}
    assert (
        len([item for item in result.observations if item.market is MarketFamily.MATCH_RESULT]) == 3
    )

    invalid = _payload()
    invalid["bookmakers"][0]["odds"]["btts"]["opening"]["yes"] = 1
    result = normalize_bet365_snapshot(invalid)
    assert OddsDiagnosticCode.INVALID_PRICE in {item.code for item in result.diagnostics}


def test_other_bookmakers_and_unsupported_markets_are_not_normalized() -> None:
    payload = _payload()
    payload["bookmakers"].append({"slug": "pinnacle", "odds": {"1x2": {}}})
    payload["bookmakers"][0]["odds"]["double_chance"] = {}
    result = normalize_bet365_snapshot(payload)
    codes = {item.code for item in result.diagnostics}
    assert OddsDiagnosticCode.UNSUPPORTED_BOOKMAKER in codes
    assert OddsDiagnosticCode.UNSUPPORTED_MARKET in codes
    assert not any(item.market is MarketFamily.DOUBLE_CHANCE for item in result.observations)
    assert not any(
        item.market in {MarketFamily.HOME_TEAM_TOTAL, MarketFamily.AWAY_TEAM_TOTAL}
        for item in result.observations
    )


def test_capability_degradation_is_local_and_explicit() -> None:
    decisions = capability_decisions(
        competition="Süper Lig",
        market=MarketFamily.DOUBLE_CHANCE,
        stats_present=False,
        odds_present=False,
    )
    indexed = {item.component: item for item in decisions}
    assert indexed["competition"].outcome is CapabilityOutcome.EXCLUDED
    assert indexed["market_family"].outcome is CapabilityOutcome.UNAVAILABLE
    assert indexed["statistics"].reason_code == "STATISTICS_UNAVAILABLE"
    assert indexed["market_probability_edge"].reason_code == "ODDS_UNAVAILABLE"
    assert indexed["market_stability"].reason_code == "ODDS_HISTORY_UNAVAILABLE"
    assert indexed["final_check"].reason_code == "LINEUPS_UNAVAILABLE"
    assert indexed["injury_evidence"].reason_code == "INJURIES_UNAVAILABLE"


def test_shadow_input_can_never_enable_publication() -> None:
    competition = map_competition(1, "Premier League")
    home = map_team(2, "Home", {"2": 1}, provenance="test")
    away = map_team(3, "Away", {"3": 2}, provenance="test")
    fixture = parse_fixture(
        {
            "id": 4,
            "kickoff_utc": "2026-09-13T10:00:00+00:00",
            "status": "scheduled",
            "goals": None,
        },
        competition=competition,
        home_team=home,
        away_team=away,
    )
    shadow = ProviderShadowInput(fixture, normalize_bet365_snapshot(_payload()))
    assert not shadow.publication_eligible
    assert shadow.publication_blocker == "MODEL_READINESS_GATE_PENDING"
