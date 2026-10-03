"""Report the evidence in saved predictions without fitting or selecting candidates."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from aav9_sma.repro import sha256_file

ENDPOINTS = ("brain", "spinal_cord", "liver", "heart", "kidney")
CLAIM_BOUNDARY = (
    "Retrospective computational diagnostics, not independent biological validation. "
    "Training-median flags are relative reference checks, not efficacy thresholds. "
    "Packaging residual bounds do not establish a per-candidate success probability."
)


def finite_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Reject absent or nonfinite evidence rather than silently skipping it."""
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing numeric evidence columns: {missing}")
    numeric = frame[columns].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric.to_numpy(float)).all():
        raise ValueError("Evidence contains missing or nonfinite numeric values")
    return numeric


def boolean_column(frame: pd.DataFrame, column: str) -> pd.Series:
    """Parse CSV booleans explicitly; the string 'False' must remain false."""
    if column not in frame:
        raise ValueError(f"Missing boolean evidence column: {column}")
    values = frame[column].map({True: True, False: False, "True": True, "False": False})
    if values.isna().any():
        raise ValueError(f"Invalid or missing boolean evidence: {column}")
    return values.astype(bool)


def build_evidence_audit(
    shortlist: pd.DataFrame, summary: dict, external: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Describe the frozen baseline; no output authorizes model promotion."""
    if shortlist.empty or external.empty:
        raise ValueError("Evidence tables must not be empty")
    for frame, key in ((shortlist, "variant_id"), (external, "name")):
        if key not in frame or frame[key].isna().any() or frame[key].duplicated().any():
            raise ValueError(f"Evidence requires present, unique {key} values")
    columns = [f"pred_{endpoint}_mouse" for endpoint in ENDPOINTS]
    predictions = finite_columns(shortlist, columns)
    external_predictions = finite_columns(external, columns)
    thresholds = summary["strict_conservative_thresholds"]
    checks = {}
    rows = []
    for endpoint in ENDPOINTS:
        values = predictions[f"pred_{endpoint}_mouse"]
        row = {
            "endpoint": endpoint,
            "rows": len(values),
            "minimum_prediction": float(values.min()),
            "median_prediction": float(values.median()),
            "maximum_prediction": float(values.max()),
            "positive_prediction_rows": int((values > 0).sum()),
        }
        if endpoint in ("brain", "spinal_cord", "liver"):
            threshold = float(thresholds[f"{endpoint}_training_median"])
            if not np.isfinite(threshold):
                raise ValueError("Training reference thresholds must be finite")
            flag = {
                "brain": "passes_brain_median",
                "spinal_cord": "passes_spinal_median",
                "liver": "passes_low_liver_median",
            }[endpoint]
            actual = values <= threshold if endpoint == "liver" else values >= threshold
            if not np.array_equal(actual.to_numpy(), boolean_column(shortlist, flag).to_numpy()):
                raise ValueError(f"Stored {flag} disagrees with saved predictions and threshold")
            checks[endpoint] = actual
            row.update(training_median=threshold, passes_training_reference=int(actual.sum()))
        rows.append(row)

    both = checks["brain"] & checks["spinal_cord"]
    if not np.array_equal(both.to_numpy(), boolean_column(shortlist, "passes_cns_median")):
        raise ValueError("Stored joint CNS flag disagrees with separate endpoint checks")
    strict = boolean_column(shortlist, "strict_conservative")
    expected_strict = (
        both
        & checks["liver"]
        & boolean_column(shortlist, "passes_packaging_gate")
        & boolean_column(shortlist, "passes_low_uncertainty")
    )
    if not np.array_equal(strict.to_numpy(), expected_strict.to_numpy()):
        raise ValueError("Stored conservative subgroup flags are inconsistent")

    # Descriptive score decomposition only; the baseline weights are unchanged.
    components = pd.DataFrame(
        {
            "cns": 0.45 * (predictions[columns[0]] + predictions[columns[1]]) / 2,
            "liver": -0.35 * predictions[columns[2]],
            "off_target": -0.20 * (predictions[columns[3]] + predictions[columns[4]]) / 2,
        }
    )
    scores = finite_columns(shortlist, ["display_score"])["display_score"]
    if not np.allclose(components.sum(axis=1), scores, atol=1e-6, rtol=1e-5):
        raise ValueError("Saved score does not match the declared baseline weights")

    names = external["name"].astype(str)
    roles = names.map(
        lambda name: (
            "task_mismatch_endothelial"
            if name in {"AAV-X1", "AAV-BI30", "AAV-PHP.V1", "AAV-PHP.V2"}
            else "retrospective_directionality"
            if name in {"AAV-F", "AAV-S"}
            else "exploratory_external_context"
        )
    )
    external_report = pd.DataFrame({"name": names, "evidence_role": roles})
    for column in ("published_role", "citation", "caveat"):
        if column in external:
            external_report[column] = external[column]
    for column in columns:
        external_report[column] = external_predictions[column]
    external_report["validates_cns_tropism"] = False

    pair = {"status": "not_evaluable", "reason": "AAV-F or AAV-S is absent"}
    if {"AAV-F", "AAV-S"}.issubset(set(names)):
        by_name = external_report.set_index("name")
        deltas = {
            ep: float(
                by_name.loc["AAV-F", f"pred_{ep}_mouse"] - by_name.loc["AAV-S", f"pred_{ep}_mouse"]
            )
            for ep in ("brain", "spinal_cord", "liver")
        }
        pair = {
            "status": "direction_only_pass"
            if deltas["brain"] > 0 and deltas["spinal_cord"] > 0
            else "direction_check_failed",
            "f_minus_s": deltas,
            "brain_direction_pass": deltas["brain"] > 0,
            "spinal_cord_direction_pass": deltas["spinal_cord"] > 0,
        }
    pair.update(
        independent_validation=False,
        retrospective=True,
        uncertainty_of_paired_difference="not_available_from_saved_means",
    )
    gates = {
        col: int(boolean_column(external, col).sum())
        for col in (
            "passes_packaging_point_gate",
            "passes_packaging_lcb90_gate",
            "passes_packaging_gate",
        )
    }
    report = {
        "schema_version": 1,
        "claim_boundary": CLAIM_BOUNDARY,
        "candidate_selection_changed": False,
        "model_retrained": False,
        "shortlist_rows": len(shortlist),
        "both_cns_training_medians": int(both.sum()),
        "strict_conservative_rows": int(strict.sum()),
        "score_component_medians": {
            key: float(value) for key, value in components.median().items()
        },
        "score_component_medians_note": "Medians of terms need not sum to median score.",
        "external_rows": len(external),
        "external_packaging_counts": gates,
        "external_packaging_interpretation": (
            "Exclusion of published capsids under a different task; "
            "not a measured in-domain false-negative rate."
        ),
        "aav_f_vs_s": pair,
        "cns_tropism_validated": False,
    }
    return pd.DataFrame(rows), external_report.sort_values("name"), report


def audit_saved_evidence(shortlist: Path, summary: Path, external: Path, output: Path) -> dict:
    """Write endpoint reports and their source/output checksums."""
    sources = {path.resolve() for path in (shortlist, summary, external)}
    destinations = {
        (output / name).resolve()
        for name in (
            "endpoint_summary.csv",
            "external_endpoint_report.csv",
            "evidence_summary.json",
        )
    }
    if sources & destinations:
        raise ValueError("Audit outputs must not overwrite source evidence")
    endpoints, external_report, report = build_evidence_audit(
        pd.read_csv(shortlist), json.loads(summary.read_text()), pd.read_csv(external)
    )
    output.mkdir(parents=True, exist_ok=True)
    endpoints.to_csv(output / "endpoint_summary.csv", index=False)
    external_report.to_csv(output / "external_endpoint_report.csv", index=False)
    report["input_sha256"] = {
        str(path): sha256_file(path) for path in (shortlist, summary, external)
    }
    report["output_sha256"] = {
        name: sha256_file(output / name)
        for name in ("endpoint_summary.csv", "external_endpoint_report.csv")
    }
    (output / "evidence_summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )
    return report
