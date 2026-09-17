# ML calibration

TASK 17 evaluates a single global temperature-scaling candidate for the TASK 16
`multinomial_logistic_v1` MATCH_RESULT model. Temperature scaling was chosen because it has one
positive parameter, preserves HOME/DRAW/AWAY ordering, is deterministic, and can be implemented
with the standard library. The semantic version is `temperature_scaling_v1`.

Calibration improvement is not assumed; it must be demonstrated out-of-sample. The real-data
evaluation rejects this candidate: aggregate Log Loss and Brier worsened despite a small macro
ECE-like improvement. Raw TASK 16 probabilities are preserved. No automatic project policy switch
is made.

## Temporal design

Each existing TASK 13 outer fold is split chronologically:

1. observations before the last 90 days of the outer training window form **Base-train**;
2. the last 90 days of that outer training window form **Calibration**;
3. the untouched outer test window forms **Test**.

The base model and train-only preprocessing are fit on Base-train. Predictions for Calibration are
therefore out of sample relative to that base-model fit. The scalar temperature is fit from those
predictions and Calibration labels, then applied to future Test logits. The raw comparator is the
output of the same reduced base-model fit on the same Test rows.

Calibration is fit only on data available before the evaluated test period. Base-train timestamps
are strictly earlier than Calibration timestamps; Calibration timestamps are strictly earlier than
Test timestamps. Same-time use is rejected. Test labels never enter preprocessing, base-model, or
calibrator fitting. There is no random split, shuffled validation split, per-competition
calibrator, or per-season calibrator.

Defaults require at least 100 Calibration rows and 10 observations of each class. Folds below
TASK 13 test support or calibration support are retained with explicit diagnostics. In the 12
evaluated folds, 6,868 of 35,466 summed outer-training observations (19.37%, with observations
repeated across expanding folds) were reserved for Calibration rather than Base-train.

## Probability and numerical semantics

TASK 16 now exposes its three finite logits alongside its raw probabilities. For a positive
temperature `T`, calibrated probabilities are `softmax(logits / T)`. Optimization is a fixed
80-iteration golden-section search over `T` in `[0.25, 4]`, including `T=1` and both bounds as
deterministic candidates. Only the scalar optimization crosses into standard-library binary
floating-point math; serialized probabilities and parameters use stable Decimal representations.

A calibrated prediction contains both the original raw prediction and a separate calibrated
probability vector, plus class order, base-model/calibrator versions, calibration support,
trained-through time, status, and diagnostics. It never overwrites raw values and never silently
falls back to raw output. A calibrator trained at or after `prediction_as_of` is rejected.

Calibration does not use bookmaker odds. The feature profile remains
`FOOTBALL_PERFORMANCE_ONLY`; no market prices, implied probabilities, no-vig values, or price
movement enter fitting.

## Real historical evidence

The read-only evaluation used all 4,460 candidate/usable historical rows (4,196 complete, 264
partial, zero unavailable). Fourteen outer folds were planned. Twelve were evaluated; fold 3 was
skipped for insufficient test support (9 rows) and fold 4 was an empty test window. All 2,701 raw
outer-fold OOS rows were calibratable, so raw and calibrated metrics have identical denominators.

| Metric                     | Same-fit raw | Temperature-scaled | Difference (calibrated - raw) |
| -------------------------- | -----------: | -----------------: | ----------------------------: |
| Log Loss                   | 1.0045505605 |       1.0073852858 |                 +0.0028347253 |
| Brier                      | 0.5996794098 |       0.6013666050 |                 +0.0016871952 |
| Accuracy (supporting only) |     50.6479% |           50.6479% |                             0 |
| Macro ECE-like             | 0.0289316711 |       0.0270303068 |                 -0.0019013643 |

Accuracy is unchanged because a positive scalar temperature preserves the top-class ordering. It
is supporting information and is not used as the calibration-selection objective.

### Fold results

| Fold | Base rows | Calibration rows (H/D/A) | Test |        T | Raw / calibrated Log Loss         | Raw / calibrated Brier | Raw / calibrated ECE |
| ---- | --------: | ------------------------ | ---: | -------: | --------------------------------- | ---------------------- | -------------------- |
| 0001 |     1,053 | 697 (304/159/234)        |  257 | 0.896080 | 0.999918 / 1.001678               | 0.597639 / 0.598259    | 0.071942 / 0.070557  |
| 0002 |     1,284 | 723 (316/156/251)        |  232 | 0.942608 | 1.012503 / 1.013411               | 0.600964 / 0.600828    | 0.047487 / 0.047030  |
| 0003 |     1,539 | 700 (299/154/247)        |    9 |        — | skipped: insufficient test sample | —                      | —                    |
| 0004 |     1,750 | 498 (209/111/178)        |    0 |        — | skipped: empty test window        | —                      | —                    |
| 0005 |     2,007 | 241 (98/55/88)           |  130 | 1.012665 | 0.951002 / 0.951762               | 0.564797 / 0.565326    | 0.079044 / 0.077599  |
| 0006 |     2,239 | 139 (63/33/43)           |  204 | 0.648570 | 1.026347 / 1.075386               | 0.616800 / 0.646431    | 0.082720 / 0.127626  |
| 0007 |     2,248 | 334 (141/91/102)         |  231 | 1.012909 | 1.005830 / 1.005865               | 0.597199 / 0.597319    | 0.039218 / 0.040581  |
| 0008 |     2,248 | 565 (246/142/177)        |  193 | 1.003683 | 0.974135 / 0.974213               | 0.583162 / 0.583198    | 0.058769 / 0.055425  |
| 0009 |     2,378 | 628 (276/159/193)        |  255 | 1.064711 | 0.974563 / 0.975756               | 0.580433 / 0.581210    | 0.044534 / 0.034640  |
| 0010 |     2,582 | 679 (301/168/210)        |  218 | 0.930106 | 0.992359 / 0.994385               | 0.592063 / 0.593280    | 0.082102 / 0.070414  |
| 0011 |     2,813 | 666 (290/181/195)        |  280 | 0.952061 | 0.988265 / 0.990289               | 0.586437 / 0.587301    | 0.048863 / 0.051629  |
| 0012 |     3,006 | 753 (331/202/220)        |  241 | 1.049169 | 1.002877 / 1.001603               | 0.599141 / 0.598396    | 0.058188 / 0.050584  |
| 0013 |     3,261 | 739 (326/202/211)        |  183 | 1.132272 | 1.024660 / 1.019456               | 0.618195 / 0.614246    | 0.071092 / 0.056551  |
| 0014 |     3,479 | 704 (315/189/200)        |  277 | 1.176970 | 1.073226 / 1.061725               | 0.643170 / 0.637677    | 0.078684 / 0.082829  |

Only 3 of 12 evaluated folds improved Log Loss. Temperatures ranged from 0.648570 to 1.176970,
with median 1.008174. Fold 6 shows material instability and harm from an unusually sharp fitted
temperature.

### Diagnostic slices

Competition and season results are diagnostics, not separate fitted calibrators.

| Competition          |   N | Raw / calibrated Log Loss | Raw / calibrated Brier | Raw / calibrated ECE |
| -------------------- | --: | ------------------------- | ---------------------- | -------------------- |
| Bundesliga           | 369 | 1.004885 / 1.006587       | 0.601048 / 0.602797    | 0.040550 / 0.042018  |
| La Liga              | 472 | 1.003900 / 1.006949       | 0.595000 / 0.597648    | 0.053049 / 0.052951  |
| Ligue 1              | 369 | 1.035979 / 1.036511       | 0.620782 / 0.620521    | 0.056607 / 0.053281  |
| Premier League       | 471 | 1.023208 / 1.028117       | 0.615731 / 0.618109    | 0.038459 / 0.043082  |
| Primeira Liga        | 371 | 0.952315 / 0.955403       | 0.566328 / 0.567455    | 0.051043 / 0.044224  |
| Scottish Premiership | 270 | 0.996210 / 0.997201       | 0.592911 / 0.594064    | 0.045395 / 0.047110  |
| Süper Lig            | 379 | 1.008324 / 1.012725       | 0.601149 / 0.603547    | 0.035352 / 0.038559  |

| Season  |     N | Raw / calibrated Log Loss | Raw / calibrated Brier | Raw / calibrated ECE |
| ------- | ----: | ------------------------- | ---------------------- | -------------------- |
| 2024/25 |   489 | 1.005889 / 1.007245       | 0.599216 / 0.599478    | 0.047602 / 0.049648  |
| 2025/26 | 2,212 | 1.004255 / 1.007416       | 0.599782 / 0.601784    | 0.036541 / 0.033875  |

### Class-wise calibration

| Class | Observed support | Observed frequency | Raw / calibrated mean probability | Raw / calibrated signed gap | Raw / calibrated ECE |
| ----- | ---------------: | -----------------: | --------------------------------- | --------------------------- | -------------------- |
| HOME  |            1,184 |           0.438356 | 0.410678 / 0.413022               | -0.027678 / -0.025334       | 0.038594 / 0.039316  |
| DRAW  |              690 |           0.255461 | 0.264242 / 0.261580               | +0.008781 / +0.006119       | 0.016819 / 0.011460  |
| AWAY  |              827 |           0.306183 | 0.325080 / 0.325398               | +0.018897 / +0.019215       | 0.031381 / 0.030315  |

DRAW mean calibration and ECE improve, while HOME ECE and AWAY signed mean gap worsen slightly.
TASK 14 bucket definitions remain the authority for these bucket-sensitive ECE-like diagnostics.

## Decision and boundaries

Decision: `CALIBRATION_CANDIDATE_REJECT`.

The ECE-like gain is not enough to justify the worse aggregate Log Loss, worse Brier, poor fold
consistency, fold-6 harm, and added support/operational complexity. The original TASK 16 benchmark
(Log Loss 1.001187, Brier 0.597547, accuracy 50.9071%, macro ECE-like 0.026983) remains context
only because it uses the larger outer-training fit; the fair candidate comparison above uses the
same reduced fit and identical OOS rows.

TASK 17 does not implement ensemble weighting. It also does not implement odds use, edge/EV/ROI,
Kelly, Bet Score, publication decisions, settlement, database persistence, migrations, or binary
model artifacts. TASK 18 and later work remain deferred.
