"""Binary and one-vs-rest multiclass calibration diagnostics."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from pitchvalue.evaluation.metrics.config import MetricConfig
from pitchvalue.evaluation.metrics.contracts import (
    BinaryCalibrationResult,
    BinaryPrediction,
    BucketStatus,
    CalibrationBucket,
    ClassCalibration,
    MetricDiagnostic,
    MetricDiagnosticCode,
    MetricProvenance,
    MetricStatus,
    MulticlassCalibrationResult,
    MulticlassPrediction,
    PredictionRecordStatus,
    canonical_class_key,
)


def binary_calibration(
    records: Iterable[BinaryPrediction],
    config: MetricConfig | None = None,
    provenance: MetricProvenance | None = None,
) -> BinaryCalibrationResult:
    config = config or MetricConfig()
    rows = tuple(records)
    ready = tuple(row for row in rows if row.status is PredictionRecordStatus.READY)
    diagnostics = _excluded_diagnostics(rows)
    bucket_rows: list[list[BinaryPrediction]] = [[] for _ in range(len(config.bucket_edges) - 1)]
    for row in ready:
        assert row.probability is not None
        bucket_rows[_bucket_index(row.probability, config.bucket_edges)].append(row)
    buckets = tuple(
        _bucket_result(index, values, config) for index, values in enumerate(bucket_rows)
    )
    if not rows:
        status = MetricStatus.EMPTY_INPUT
        ece = None
    elif not ready:
        status = MetricStatus.INSUFFICIENT_SAMPLE
        ece = None
    else:
        ece = sum(
            (
                Decimal(bucket.sample_count)
                / Decimal(len(ready))
                * (bucket.absolute_calibration_gap or Decimal(0))
                for bucket in buckets
            ),
            Decimal(0),
        )
        status = (
            MetricStatus.READY
            if len(ready) >= config.minimum_total_samples
            else MetricStatus.INSUFFICIENT_SAMPLE
        )
        if status is MetricStatus.INSUFFICIENT_SAMPLE:
            diagnostics.append(MetricDiagnostic(MetricDiagnosticCode.INSUFFICIENT_TOTAL_SAMPLE))
    return BinaryCalibrationResult(
        status,
        len(rows),
        len(ready),
        len(rows) - len(ready),
        config.bucket_edges,
        buckets,
        ece,
        tuple(sorted(diagnostics, key=lambda item: ((item.prediction_id or ""), item.code.value))),
        provenance,
    )


def multiclass_calibration(
    records: Iterable[MulticlassPrediction],
    config: MetricConfig | None = None,
    provenance: MetricProvenance | None = None,
) -> MulticlassCalibrationResult:
    config = config or MetricConfig()
    rows = tuple(records)
    ready = tuple(row for row in rows if row.status is PredictionRecordStatus.READY)
    diagnostics = _excluded_diagnostics(rows)
    invalid = _invalid_probability_sums(ready, config)
    if invalid:
        return MulticlassCalibrationResult(
            MetricStatus.INVALID_PROBABILITY,
            len(rows),
            0,
            len(rows),
            (),
            None,
            tuple(invalid),
            provenance,
        )
    labels = sorted(
        {item.label for row in ready for item in row.probabilities}, key=canonical_class_key
    )
    if any({item.label for item in row.probabilities} != set(labels) for row in ready):
        diagnostic = MetricDiagnostic(
            MetricDiagnosticCode.CLASS_DOMAIN_MISMATCH, detail="class domains differ"
        )
        return MulticlassCalibrationResult(
            MetricStatus.INVALID_PROBABILITY,
            len(rows),
            0,
            len(rows),
            (),
            None,
            (diagnostic,),
            provenance,
        )
    classes: list[ClassCalibration] = []
    for label in labels:
        binary_rows = tuple(
            BinaryPrediction(
                row.prediction_id,
                row.probability_for(label),
                int(row.observed_class == label),
            )
            for row in ready
        )
        class_provenance = _class_provenance(provenance, label)
        classes.append(
            ClassCalibration(label, binary_calibration(binary_rows, config, class_provenance))
        )
    eces = [item.calibration.ece for item in classes if item.calibration.ece is not None]
    macro_ece = sum(eces, Decimal(0)) / Decimal(len(eces)) if eces else None
    if not rows:
        status = MetricStatus.EMPTY_INPUT
    elif len(ready) < config.minimum_total_samples:
        status = MetricStatus.INSUFFICIENT_SAMPLE
        diagnostics.append(MetricDiagnostic(MetricDiagnosticCode.INSUFFICIENT_TOTAL_SAMPLE))
    else:
        status = MetricStatus.READY
    return MulticlassCalibrationResult(
        status,
        len(rows),
        len(ready),
        len(rows) - len(ready),
        tuple(classes),
        macro_ece,
        tuple(sorted(diagnostics, key=lambda item: ((item.prediction_id or ""), item.code.value))),
        provenance,
    )


def _bucket_index(probability: Decimal, edges: tuple[Decimal, ...]) -> int:
    if probability == Decimal(1):
        return len(edges) - 2
    for index, (lower, upper) in enumerate(zip(edges, edges[1:], strict=False)):
        if lower <= probability < upper:
            return index
    raise ValueError("validated probability did not map to a bucket")  # pragma: no cover


def _bucket_result(
    index: int, rows: list[BinaryPrediction], config: MetricConfig
) -> CalibrationBucket:
    lower = config.bucket_edges[index]
    upper = config.bucket_edges[index + 1]
    if not rows:
        return CalibrationBucket(
            lower,
            upper,
            index == len(config.bucket_edges) - 2,
            0,
            None,
            None,
            None,
            None,
            BucketStatus.EMPTY,
        )
    probabilities = [row.probability for row in rows]
    outcomes = [row.observed for row in rows]
    assert all(item is not None for item in probabilities)
    assert all(item is not None for item in outcomes)
    mean = sum((item for item in probabilities if item is not None), Decimal(0)) / Decimal(
        len(rows)
    )
    observed = Decimal(sum(item for item in outcomes if item is not None)) / Decimal(len(rows))
    gap = mean - observed
    status = (
        BucketStatus.READY
        if len(rows) >= config.minimum_bucket_samples
        else BucketStatus.INSUFFICIENT_SAMPLE
    )
    return CalibrationBucket(
        lower,
        upper,
        index == len(config.bucket_edges) - 2,
        len(rows),
        mean,
        observed,
        gap,
        abs(gap),
        status,
    )


def _excluded_diagnostics(
    rows: tuple[BinaryPrediction | MulticlassPrediction, ...],
) -> list[MetricDiagnostic]:
    diagnostics: list[MetricDiagnostic] = []
    for row in rows:
        if row.status is not PredictionRecordStatus.READY:
            diagnostics.append(
                MetricDiagnostic(MetricDiagnosticCode(row.status.value), row.prediction_id)
            )
    return diagnostics


def _invalid_probability_sums(
    rows: tuple[MulticlassPrediction, ...], config: MetricConfig
) -> list[MetricDiagnostic]:
    diagnostics = []
    for row in rows:
        total = sum((item.probability for item in row.probabilities), Decimal(0))
        if abs(total - Decimal(1)) > config.probability_sum_tolerance:
            diagnostics.append(
                MetricDiagnostic(
                    MetricDiagnosticCode.INVALID_PROBABILITY_SUM, row.prediction_id, f"sum={total}"
                )
            )
    return diagnostics


def _class_provenance(provenance: MetricProvenance | None, label: str) -> MetricProvenance | None:
    if provenance is None:
        return None
    return MetricProvenance(
        provenance.fold_id,
        provenance.model_name,
        provenance.model_version,
        provenance.competition_id,
        provenance.season_id,
        provenance.market,
        label,
        provenance.line,
    )
