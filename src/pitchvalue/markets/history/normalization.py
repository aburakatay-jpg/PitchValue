"""Deterministic orchestration of verified historical source-price normalization."""

from __future__ import annotations

from collections import Counter

from sqlalchemy import Engine

from pitchvalue.markets.history.config import FOOTBALL_DATA_MAPPINGS
from pitchvalue.markets.history.contracts import (
    HistoricalOddsDiagnostic,
    HistoricalOddsDiagnosticCode,
    HistoricalOddsNormalizationSummary,
    HistoricalPriceObservation,
    OddsQualityStatus,
)
from pitchvalue.markets.history.football_data import normalize_source_value
from pitchvalue.markets.history.repository import persist_historical_observation
from pitchvalue.markets.history.source import (
    iter_canonical_source_rows,
    replayed_source_row_count,
    validate_replay_consistency,
)


def _items(counter: Counter[str]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(counter.items()))


def normalize_historical_odds(engine: Engine) -> HistoricalOddsNormalizationSummary:
    diagnostics: list[HistoricalOddsDiagnostic] = []
    source_fields: Counter[str] = Counter()
    bookmakers: Counter[str] = Counter()
    markets: Counter[str] = Counter()
    competitions: Counter[str] = Counter()
    seasons: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    created = reused = missing = malformed = invalid = eligible = suspect = excluded = 0
    odds_bearing_rows = 0
    raw_mapped_values = 0
    lineage = 0
    with engine.begin() as connection:
        validate_replay_consistency(connection)
        replayed = replayed_source_row_count(connection)
        source_rows = tuple(iter_canonical_source_rows(connection))
        for row in source_rows:
            row_has_odds = False
            for mapping in FOOTBALL_DATA_MAPPINGS:
                normalized = normalize_source_value(row, mapping)
                if isinstance(normalized, HistoricalOddsDiagnostic):
                    diagnostics.append(normalized)
                    if normalized.code is HistoricalOddsDiagnosticCode.MISSING_PRICE:
                        missing += 1
                    elif normalized.code is HistoricalOddsDiagnosticCode.MALFORMED_PRICE:
                        malformed += 1
                    else:
                        invalid += 1
                    continue
                row_has_odds = True
                raw_mapped_values += 1
                if persist_historical_observation(connection, normalized):
                    created += 1
                else:
                    reused += 1
                _count_observation(
                    normalized, source_fields, bookmakers, markets, competitions, seasons, roles
                )
                if normalized.quality_status is OddsQualityStatus.ELIGIBLE:
                    eligible += 1
                elif normalized.quality_status is OddsQualityStatus.SUSPECT:
                    suspect += 1
                elif normalized.quality_status is OddsQualityStatus.EXCLUDED:
                    excluded += 1
                lineage += 1
            odds_bearing_rows += int(row_has_odds)
    ordered_diagnostics = tuple(
        sorted(
            diagnostics, key=lambda item: (item.source_field, item.code.value, item.raw_value or "")
        )
    )
    return HistoricalOddsNormalizationSummary(
        source_rows_inspected=len(source_rows),
        replayed_source_rows_ignored=replayed,
        odds_bearing_rows=odds_bearing_rows,
        raw_mapped_values=raw_mapped_values,
        created_observations=created,
        reused_observations=reused,
        missing_values=missing,
        malformed_values=malformed,
        invalid_values=invalid,
        eligible_observations=eligible,
        suspect_observations=suspect,
        excluded_observations=excluded,
        lineage_observations=lineage,
        by_source_field=_items(source_fields),
        by_bookmaker=_items(bookmakers),
        by_market=_items(markets),
        by_competition=_items(competitions),
        by_season=_items(seasons),
        by_observation_role=_items(roles),
        diagnostics=ordered_diagnostics,
    )


def _count_observation(
    observation: HistoricalPriceObservation,
    source_fields: Counter[str],
    bookmakers: Counter[str],
    markets: Counter[str],
    competitions: Counter[str],
    seasons: Counter[str],
    roles: Counter[str],
) -> None:
    source_fields[observation.source_field] += 1
    bookmakers[observation.bookmaker or observation.observation_source_kind.value] += 1
    markets[observation.market] += 1
    competitions[observation.competition_name] += 1
    seasons[observation.source_season] += 1
    roles[observation.observation_role.value] += 1
