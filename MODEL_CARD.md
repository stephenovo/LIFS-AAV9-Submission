# Model card — frozen baseline, updated-7.0 audit release

## Identity and scope

Software branch: `updated-7.0`. Package version remains `0.1.0`.
Model identifier: `updated-5.0-frozen-baseline`; no model promotion in 7.0.
Baseline source revision: `0ba7f09` (updated-6.0).
The saved shortlist last changed at `b34b01776d70ede1fbbd77598ca84f12515e79ed`;
this is an artifact provenance commit, not proof of the exact historical training commit.

This research system prioritizes computational hypotheses using mouse-organ
biodistribution proxies. It does not establish CNS tropism, motor-neuron specificity,
reduced hepatotoxicity, clinical efficacy, or human transferability.

## Architecture and inputs

Positional one-hot encoding of a 7-mer in the documented AAV9 background yields
140 features. Packaging uses scikit-learn Ridge with alpha 1. Five shared MLPs
(64, 32 hidden units; ReLU; Adam; batch 512; initial learning rate 0.001;
max_iter 80; seeds 42–46) predict brain, spinal cord, liver, heart and kidney.
Targets are standardized separately. Complete cases across all five tasks are
used for the retained organ model; missing labels are not replaced with zero.
Early stopping uses a 10% internal validation split and n_iter_no_change=8.

The retained production fit uses Animals 1–3. The Animal 4 benchmark additionally
holds out sequences with the documented distance-2 split. These are different
fits: production organ training has 92,725 rows, whereas the saved Animal 4
ensemble benchmark has 73,553 training rows. Animal 4 has informed development
and is not a blind test. Labels are log2 tissue enrichment relative to the
production-virus reference; this is not a cell-type transduction measurement.

Input sources, upstream commit and real file hashes are in
`docs/source_manifest.json` and `docs/data_manifest.json`. Input schema and
missing-value construction are in `docs/DATA_CONTRACT.md` and the reconstruction
code. Raw public data is not bundled.

## Outputs and evaluation

Saved 30-row predictions are in `docs/audit_data/virtual_screen_shortlist.csv`.
`export-results` preserves the sequence set and order in `results/results.csv`.
The five endpoint predictions, ensemble standard deviations, separate brain and
spinal reference flags, original group/rank and score are reported together.
Predictions use log2 enrichment units; ensemble SD is model disagreement, not a
calibrated prediction interval. Specificity index is a derived ratio, not measured
biological specificity. Rankings reflect multiple objectives and group quotas.

Animal 4 Pearson r: brain 0.5539; spinal cord 0.5705; liver 0.7854; heart 0.4585;
kidney 0.6346. See saved metrics for sample sizes, MAE, R² and sequence-bootstrap
intervals. Across held-out animals, brain r varies from 0.358 to 0.554 and spinal
cord from 0.453 to 0.571; sequence-bootstrap intervals do not quantify animal-level
or study-level transfer uncertainty.

The existing 95% packaging field is an empirical residual lower bound. Its offset
is estimated using a split model, then reused after an all-data Ridge refit.
The reported calibration-set coverage is not independent coverage for the final
refit, selected candidates or external capsids. It is not a per-candidate 95%
success probability. Published capsid exclusions do not establish the in-domain
false-negative rate.

External literature predictions have not validated the model. F/S fails the brain
direction check, while the spinal difference is nearly zero. Endothelial results
have endpoint mismatch; PHP.B/PHP.eB have indistinguishable 7-mer inputs.
`docs/EVIDENCE_SUMMARY.md` summarizes the evaluation and its limitations.

## Delivery and reproducibility

No historical binary weights were retained. Their SHA256 is unavailable.
`logs/final_model_record.json` preserves recoverable training facts with their
source hashes and marks unavailable timing/environment/stopping information.
It is a retrospective provenance record, not a contemporaneous training log.

Existing data-processing and execution documentation is retained in
`docs/FIT4FUNCTION_RUNBOOK.md`. Fixed seeds and locked dependencies support
repeatability, but bitwise identity across numerical libraries/platforms has not
been established. Do not silently replace the frozen 30-row deliverable with a
re-fit's results. `scripts/prepare_submission.py` reproduces the audit/export
without fitting; its execution record captures its actual source hashes and
environment. Result/source checksums are in `results/results_manifest.json` and
`docs/submission_manifest.json`.

The official competition result template and project redistribution license still
require confirmation; see `LICENSE_STATUS.md` and `THIRD_PARTY_NOTICES.md`.
