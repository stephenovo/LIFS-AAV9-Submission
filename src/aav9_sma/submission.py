"""Competition-facing result export with a stable, validated schema."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from aav9_sma import __version__
from aav9_sma.constants import AMINO_ACIDS
from aav9_sma.evidence import CLAIM_BOUNDARY, boolean_column, finite_columns

TRACK_NAME = "赛道四：递送载体设计"
MODEL_NAME = "Ridge packaging model and five-seed shared-MLP organ ensemble"
STRUCTURE_CONTEXT = "AAV9 (K449R) capsid; 7-mer insertion between VP1 residues 588 and 589"

SOURCE_COLUMNS = {
    "variant_id",
    "AA",
    "pred_pack",
    "pred_pack_lcb",
    "pred_brain_mouse",
    "uncertainty_brain_mouse",
    "pred_spinal_cord_mouse",
    "uncertainty_spinal_cord_mouse",
    "pred_liver_mouse",
    "uncertainty_liver_mouse",
    "pred_heart_mouse",
    "uncertainty_heart_mouse",
    "pred_kidney_mouse",
    "uncertainty_kidney_mouse",
    "f_cns",
    "f_off",
    "display_score",
    "specificity_index",
    "selection_group",
    "selection_rank",
    "strict_conservative",
    "immune_annotation",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_submission_results(
    shortlist: pd.DataFrame,
    *,
    model_version: str = __version__,
    run_version: str = "main",
) -> pd.DataFrame:
    """Convert an internal shortlist into the competition-facing result schema.

    The exporter deliberately preserves endpoint-level predictions and model
    disagreement instead of collapsing every claim into one opaque score.
    """
    missing = sorted(SOURCE_COLUMNS - set(shortlist.columns))
    if missing:
        raise ValueError(f"Shortlist is missing required columns: {missing}")
    if shortlist.empty:
        raise ValueError("Shortlist must contain at least one candidate")
    if (
        shortlist["variant_id"].isna().any()
        or shortlist["variant_id"].duplicated().any()
        or shortlist["variant_id"].astype(str).str.strip().eq("").any()
    ):
        raise ValueError("Candidate identifiers must be present and unique")
    if shortlist["AA"].duplicated().any():
        raise ValueError("Candidate sequences must be unique")
    numeric_columns = sorted(
        SOURCE_COLUMNS
        - {"variant_id", "AA", "selection_group", "strict_conservative", "immune_annotation"}
    )
    finite_columns(shortlist, numeric_columns)
    boolean_column(shortlist, "strict_conservative")

    allowed = set(AMINO_ACIDS)
    invalid_sequences = [
        sequence
        for sequence in shortlist["AA"].astype(str)
        if len(sequence) != 7 or not set(sequence).issubset(allowed)
    ]
    if invalid_sequences:
        raise ValueError(f"Invalid 7-mer candidate sequences: {invalid_sequences[:5]}")

    result = pd.DataFrame(
        {
            "candidate_id": shortlist["variant_id"].astype(str),
            "track": TRACK_NAME,
            "candidate_sequence": shortlist["AA"].astype(str),
            "structure_or_component": STRUCTURE_CONTEXT,
            "predicted_packaging": shortlist["pred_pack"],
            "predicted_packaging_lower_bound": shortlist["pred_pack_lcb"],
            "predicted_brain_proxy": shortlist["pred_brain_mouse"],
            "predicted_spinal_cord_proxy": shortlist["pred_spinal_cord_mouse"],
            "predicted_liver_proxy": shortlist["pred_liver_mouse"],
            "predicted_heart_proxy": shortlist["pred_heart_mouse"],
            "predicted_kidney_proxy": shortlist["pred_kidney_mouse"],
            "predicted_cns_proxy": shortlist["f_cns"],
            "predicted_off_target_proxy": shortlist["f_off"],
            "ranking_score": shortlist["display_score"],
            "predicted_specificity_index": shortlist["specificity_index"],
            "brain_model_disagreement": shortlist["uncertainty_brain_mouse"],
            "spinal_model_disagreement": shortlist["uncertainty_spinal_cord_mouse"],
            "liver_model_disagreement": shortlist["uncertainty_liver_mouse"],
            "heart_model_disagreement": shortlist["uncertainty_heart_mouse"],
            "kidney_model_disagreement": shortlist["uncertainty_kidney_mouse"],
            "selection_group": shortlist["selection_group"].astype(str),
            "selection_rank": shortlist["selection_rank"],
            "strict_conservative": boolean_column(shortlist, "strict_conservative"),
            "model": MODEL_NAME,
            "model_version": model_version,
            "run_version": run_version,
            "notes": shortlist["immune_annotation"].astype(str),
        }
    )
    # Preserve the historical order; exporting must never select or re-rank.
    for column in (
        "passes_brain_median",
        "passes_spinal_median",
        "passes_cns_median",
        "passes_low_liver_median",
        "passes_packaging_gate",
    ):
        if column in shortlist:
            result[column] = boolean_column(shortlist, column)
    result["endpoint_units"] = "log2 enrichment relative to dataset-specific denominator"
    result["uncertainty_units"] = "ensemble standard deviation in endpoint log2 units"
    result["ranking_rule"] = "preserved source order; group-specific selection_rank"
    result["validation_status"] = "computational_hypothesis_only"
    result["claim_limitations"] = CLAIM_BOUNDARY
    return result


def export_submission_results(
    input_path: str | Path,
    output_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
    model_version: str = __version__,
    run_version: str = "main",
) -> dict[str, object]:
    """Write UTF-8 CSV results plus an optional checksum manifest."""
    source = Path(input_path)
    output = Path(output_path)
    paths = [source.resolve(), output.resolve()]
    if manifest_path is not None:
        paths.append(Path(manifest_path).resolve())
    if len(paths) != len(set(paths)):
        raise ValueError("Source, output and manifest paths must be distinct")
    shortlist = pd.read_csv(source)
    result = build_submission_results(
        shortlist,
        model_version=model_version,
        run_version=run_version,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False, encoding="utf-8")

    manifest: dict[str, object] = {
        "schema_version": 2,
        "official_competition_template_verified": False,
        "model_weights_sha256": None,
        "delivery": "frozen historical results; retraining recipe documented separately",
        "source": str(source),
        "source_sha256": _sha256(source),
        "output": str(output),
        "output_sha256": _sha256(output),
        "rows": len(result),
        "columns": list(result.columns),
        "track": TRACK_NAME,
        "model": MODEL_NAME,
        "model_version": model_version,
        "run_version": run_version,
        "claim_boundary": (
            "Computational candidates for experimental validation; not evidence of "
            "clinical efficacy, motor-neuron specificity, or experimental confirmation."
        ),
    }
    if manifest_path is not None:
        manifest_output = Path(manifest_path)
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return manifest
