"""Pure temporal-availability semantics for historical price observations."""

from datetime import datetime

from pitchvalue.markets.history.contracts import (
    HistoricalOddsError,
    HistoricalPriceObservation,
    TemporalAvailability,
    TimingSemantics,
)


def temporal_availability(
    observation: HistoricalPriceObservation, prediction_as_of: datetime
) -> TemporalAvailability:
    if prediction_as_of.tzinfo is None or prediction_as_of.utcoffset() is None:
        raise HistoricalOddsError("prediction_as_of must be timezone-aware")
    if observation.timing_semantics is not TimingSemantics.EXACT or observation.observed_at is None:
        return TemporalAvailability.UNKNOWN
    if observation.observed_at <= prediction_as_of:
        return TemporalAvailability.AVAILABLE
    return TemporalAvailability.AFTER_AS_OF
