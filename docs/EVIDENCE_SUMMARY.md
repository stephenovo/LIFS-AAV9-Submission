# Evaluation summary

## Retained release

The retained model is identified as `updated-5.0-frozen-baseline`. The
`updated-7.0` software release adds evidence reporting, saved-result export, and
integrity checks. It did not retrain or promote a model.

The saved evaluation records support retaining the selected baseline over the
challengers evaluated under the recorded protocol. This comparison does not
establish a globally optimal model. The 30-row result set remains the recorded
output of that baseline.

## Evaluation context

Animal 4 was held out from fitting in the recorded benchmark, but its results
were inspected during development. Its role is a development holdout, not a final
blind test. Retrospective cross-animal checks use the same four animals and do
not create an independent external validation set.

Sources: [evaluation policy](ANIMAL4_POLICY.md),
[cross-animal report](CROSS_ANIMAL_ROBUSTNESS_AUDIT.zh-CN.md), and
[ensemble metrics](audit_data/fit4function_multitask_ensemble_metrics.csv).

## Interpretation

- Organ-distribution labels do not establish cell-type transduction, human
  transferability, or clinical efficacy.
- Ensemble standard deviations describe disagreement among fitted models;
  they are not calibrated per-sample prediction intervals.
- The nominal packaging residual bound was estimated with a split fit and reused
  after refitting. Its calibration-set coverage is not independent coverage for
  final selected samples or external data.
- Aggregate scores do not establish improvement in every reported endpoint.
  Endpoint values and failed reference checks remain in the result table.
- The literature comparison did not establish external validation. Endpoint and
  experimental-context differences, duplicate model inputs, and observed
  direction mismatches remain part of the record.

Sources: [Model Card](../MODEL_CARD.md),
[endpoint summary](audit_data/updated_7_0/endpoint_summary.csv), and
[evidence report](audit_data/updated_7_0/evidence_summary.json).

## Reproducibility status

The repository retains source code, saved outputs, input identities, and recovered
training metadata. Historical binary weights and contemporaneous training logs
were not retained. [final_model_record.json](../logs/final_model_record.json)
marks recovered facts and unavailable fields separately.

`verify_submission.py` checks saved-file integrity and output consistency.
`prepare_submission.py` audits and exports existing results. Neither operation
establishes that the historical training run has been reproduced.

Current delivery requirements and unresolved items are listed in the
[submission guide](SUBMISSION_GUIDE.zh-CN.md).
