"""Pure Brier, log-loss, and supporting accuracy calculations."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from decimal import Decimal

from pitchvalue.evaluation.metrics.config import MetricConfig
from pitchvalue.evaluation.metrics.contracts import (
    BinaryPrediction,
    MetricDiagnostic,
    MetricDiagnosticCode,
    MetricName,
    MetricProvenance,
    MetricResult,
    MetricStatus,
    MulticlassPrediction,
    PredictionRecordStatus,
)


def binary_brier_score(
    records: Iterable[BinaryPrediction],
    config: MetricConfig | None = None,
    provenance: MetricProvenance | None = None,
) -> MetricResult:
    config = config or MetricConfig()
    return _binary_metric(records, config, MetricName.BRIER_BINARY, _binary_brier, provenance)


def binary_log_loss(
    records: Iterable[BinaryPrediction],
    config: MetricConfig | None = None,
    provenance: MetricProvenance | None = None,
) -> MetricResult:
    config = config or MetricConfig()
    return _binary_metric(
        records,
        config,
        MetricName.LOG_LOSS_BINARY,
        lambda row: _binary_log(row, config.log_loss_epsilon),
        provenance,
    )


def binary_accuracy(
    records: Iterable[BinaryPrediction],
    config: MetricConfig | None = None,
    provenance: MetricProvenance | None = None,
) -> MetricResult:
    config = config or MetricConfig()
    return _binary_metric(
        records,
        config,
        MetricName.ACCURACY_BINARY,
        lambda row: _binary_accuracy_value(row, config.binary_threshold),
        provenance,
    )


def multiclass_brier_score(
    records: Iterable[MulticlassPrediction],
    config: MetricConfig | None = None,
    provenance: MetricProvenance | None = None,
) -> MetricResult:
    config = config or MetricConfig()
    return _multiclass_metric(
        records, config, MetricName.BRIER_MULTICLASS, _multiclass_brier, provenance
    )


def multiclass_log_loss(
    records: Iterable[MulticlassPrediction],
    config: MetricConfig | None = None,
    provenance: MetricProvenance | None = None,
) -> MetricResult:
    config = config or MetricConfig()
    return _multiclass_metric(
        records,
        config,
        MetricName.LOG_LOSS_MULTICLASS,
        lambda row: _multiclass_log(row, config.log_loss_epsilon),
        provenance,
    )


def multiclass_accuracy(
    records: Iterable[MulticlassPrediction],
    config: MetricConfig | None = None,
    provenance: MetricProvenance | None = None,
) -> MetricResult:
    config = config or MetricConfig()
    rows = tuple(records)
    ready, diagnostics = _usable_multiclass(rows)
    invalid = _invalid_sum_diagnostics(ready, config)
    if invalid:
        return _invalid_result(MetricName.ACCURACY_MULTICLASS, rows, invalid, provenance)
    values: list[Decimal] = []
    for row in ready:
        maximum = max(item.probability for item in row.probabilities)
        winners = [item.label for item in row.probabilities if item.probability == maximum]
        if len(winners) != 1:
            diagnostics.append(
                MetricDiagnostic(MetricDiagnosticCode.AMBIGUOUS_TOP_CLASS, row.prediction_id)
            )
            continue
        values.append(Decimal(int(winners[0] == row.observed_class)))
    return _result(
        MetricName.ACCURACY_MULTICLASS,
        rows,
        values,
        diagnostics,
        config,
        provenance,
    )


def _binary_metric(
    records: Iterable[BinaryPrediction],
    config: MetricConfig,
    name: MetricName,
    calculate: Callable[[BinaryPrediction], Decimal],
    provenance: MetricProvenance | None,
) -> MetricResult:
    rows = tuple(records)
    ready, diagnostics = _usable_binary(rows)
    return _result(name, rows, [calculate(row) for row in ready], diagnostics, config, provenance)


def _multiclass_metric(
    records: Iterable[MulticlassPrediction],
    config: MetricConfig,
    name: MetricName,
    calculate: Callable[[MulticlassPrediction], Decimal],
    provenance: MetricProvenance | None,
) -> MetricResult:
    rows = tuple(records)
    ready, diagnostics = _usable_multiclass(rows)
    invalid = _invalid_sum_diagnostics(ready, config)
    if invalid:
        return _invalid_result(name, rows, diagnostics + invalid, provenance)
    return _result(name, rows, [calculate(row) for row in ready], diagnostics, config, provenance)


def _binary_brier(row: BinaryPrediction) -> Decimal:
    assert row.probability is not None and row.observed is not None
    return (row.probability - Decimal(row.observed)) ** 2


def _binary_accuracy_value(row: BinaryPrediction, threshold: Decimal) -> Decimal:
    assert row.probability is not None and row.observed is not None
    return Decimal(int((row.probability >= threshold) == bool(row.observed)))


def _multiclass_brier(row: MulticlassPrediction) -> Decimal:
    assert row.observed_class is not None
    return sum(
        (
            (item.probability - Decimal(int(item.label == row.observed_class))) ** 2
            for item in row.probabilities
        ),
        Decimal(0),
    )


def _binary_log(row: BinaryPrediction, epsilon: Decimal) -> Decimal:
    assert row.probability is not None and row.observed is not None
    p = min(max(row.probability, epsilon), Decimal(1) - epsilon)
    value = -math.log(float(p if row.observed == 1 else Decimal(1) - p))
    return Decimal(str(value))


def _multiclass_log(row: MulticlassPrediction, epsilon: Decimal) -> Decimal:
    assert row.observed_class is not None
    p = max(row.probability_for(row.observed_class), epsilon)
    return Decimal(str(-math.log(float(p))))


def _usable_binary(
    records: tuple[BinaryPrediction, ...],
) -> tuple[list[BinaryPrediction], list[MetricDiagnostic]]:
    ready: list[BinaryPrediction] = []
    diagnostics: list[MetricDiagnostic] = []
    for row in records:
        if row.status is PredictionRecordStatus.READY:
            ready.append(row)
        else:
            diagnostics.append(
                MetricDiagnostic(MetricDiagnosticCode(row.status.value), row.prediction_id)
            )
    return ready, diagnostics


def _usable_multiclass(
    records: tuple[MulticlassPrediction, ...],
) -> tuple[list[MulticlassPrediction], list[MetricDiagnostic]]:
    ready: list[MulticlassPrediction] = []
    diagnostics: list[MetricDiagnostic] = []
    for row in records:
        if row.status is PredictionRecordStatus.READY:
            ready.append(row)
        else:
            diagnostics.append(
                MetricDiagnostic(MetricDiagnosticCode(row.status.value), row.prediction_id)
            )
    return ready, diagnostics


def _invalid_sum_diagnostics(
    rows: list[MulticlassPrediction], config: MetricConfig
) -> list[MetricDiagnostic]:
    diagnostics: list[MetricDiagnostic] = []
    for row in rows:
        total = sum((item.probability for item in row.probabilities), Decimal(0))
        if abs(total - Decimal(1)) > config.probability_sum_tolerance:
            diagnostics.append(
                MetricDiagnostic(
                    MetricDiagnosticCode.INVALID_PROBABILITY_SUM,
                    row.prediction_id,
                    f"sum={total}",
                )
            )
    return diagnostics


def _invalid_result(
    name: MetricName,
    rows: tuple[object, ...],
    diagnostics: list[MetricDiagnostic],
    provenance: MetricProvenance | None,
) -> MetricResult:
    return MetricResult(
        name,
        None,
        len(rows),
        0,
        len(rows),
        MetricStatus.INVALID_PROBABILITY,
        tuple(sorted(diagnostics, key=lambda item: ((item.prediction_id or ""), item.code.value))),
        provenance,
    )


def _result(
    name: MetricName,
    rows: tuple[object, ...],
    values: list[Decimal],
    diagnostics: list[MetricDiagnostic],
    config: MetricConfig,
    provenance: MetricProvenance | None,
) -> MetricResult:
    if not rows:
        status = MetricStatus.EMPTY_INPUT
        value = None
    elif not values:
        status = MetricStatus.INSUFFICIENT_SAMPLE
        value = None
    else:
        value = sum(values, Decimal(0)) / Decimal(len(values))
        status = (
            MetricStatus.READY
            if len(values) >= config.minimum_total_samples
            else MetricStatus.INSUFFICIENT_SAMPLE
        )
        if status is MetricStatus.INSUFFICIENT_SAMPLE:
            diagnostics.append(MetricDiagnostic(MetricDiagnosticCode.INSUFFICIENT_TOTAL_SAMPLE))
    ordered = tuple(
        sorted(diagnostics, key=lambda item: ((item.prediction_id or ""), item.code.value))
    )
    return MetricResult(
        name, value, len(rows), len(values), len(rows) - len(values), status, ordered, provenance
    )
