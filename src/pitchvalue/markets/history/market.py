"""Read-only adapter from canonical odds snapshots to strict market groups."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import Connection, text

from pitchvalue.markets.edge import HistoricalMarketGroup, HistoricalMarketPrice
from pitchvalue.markets.history.contracts import (
    ObservationRole,
    OddsQualityStatus,
    TimingSemantics,
)
from pitchvalue.ml.model import ML_CLASS_ORDER
from pitchvalue.prediction.contracts import MarketFamily, Selection


@dataclass(frozen=True)
class HistoricalMarketLoad:
    groups: tuple[HistoricalMarketGroup, ...]
    raw_rows: int
    incomplete_groups: int
    invalid_groups: int
    quality_excluded_groups: int
    ambiguous_groups: int
    quality_counts: tuple[tuple[str, int], ...]


_QUERY = text(
    """
    SELECT odds_snapshot_id,match_id,provider_id,bookmaker,market,selection,
           decimal_odds,observation_role,timing_semantics,observed_at,
           quality_status,quality_reasons,source_match_provider_ref_id,
           source_staging_row_id,source_field,mapping_version,
           normalization_version,quality_policy_version
    FROM odds_snapshots
    WHERE observation_origin='historical_source'
      AND bookmaker='BET365'
      AND market='match_result'
      AND observation_role IN ('source_prematch','closing')
    ORDER BY match_id,observation_role,selection,odds_snapshot_id
    """
)


def load_historical_match_result_markets(connection: Connection) -> HistoricalMarketLoad:
    rows = tuple(connection.execute(_QUERY).mappings())
    buckets: dict[tuple[str, ObservationRole], list[HistoricalMarketPrice]] = defaultdict(list)
    quality_counts: Counter[str] = Counter()
    invalid = 0
    for row in rows:
        quality_counts[str(row["quality_status"])] += 1
        try:
            price = HistoricalMarketPrice(
                int(row["odds_snapshot_id"]),
                str(row["match_id"]),
                str(row["provider_id"]),
                str(row["bookmaker"]),
                MarketFamily(str(row["market"])),
                Selection(str(row["selection"])),
                row["decimal_odds"],
                ObservationRole(str(row["observation_role"])),
                TimingSemantics(str(row["timing_semantics"])),
                row["observed_at"],
                OddsQualityStatus(str(row["quality_status"])),
                tuple(row["quality_reasons"]),
                int(row["source_match_provider_ref_id"]),
                int(row["source_staging_row_id"]),
                str(row["source_field"]),
                str(row["mapping_version"]),
                str(row["normalization_version"]),
                str(row["quality_policy_version"]),
            )
        except (TypeError, ValueError):
            invalid += 1
            continue
        buckets[(price.match_id, price.observation_role)].append(price)
    groups: list[HistoricalMarketGroup] = []
    incomplete = ambiguous = excluded = 0
    selection_order = {selection: index for index, selection in enumerate(ML_CLASS_ORDER)}
    for (match_id, role), prices in sorted(buckets.items(), key=lambda item: item[0]):
        if any(item.quality_status is not OddsQualityStatus.ELIGIBLE for item in prices):
            excluded += 1
            continue
        counts = Counter(item.selection for item in prices)
        if set(counts) != set(ML_CLASS_ORDER):
            incomplete += 1
            continue
        if any(count != 1 for count in counts.values()) or len(prices) != 3:
            ambiguous += 1
            continue
        ordered = tuple(sorted(prices, key=lambda item: selection_order[item.selection]))
        try:
            groups.append(
                HistoricalMarketGroup(
                    match_id,
                    ordered[0].bookmaker,
                    role,
                    ordered[0].timing_semantics,
                    ordered[0].observed_at,
                    ordered,
                )
            )
        except ValueError:
            invalid += 1
    return HistoricalMarketLoad(
        tuple(groups),
        len(rows),
        incomplete,
        invalid,
        excluded,
        ambiguous,
        tuple(sorted(quality_counts.items())),
    )
