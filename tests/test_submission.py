import pandas as pd
import pytest

from aav9_sma.submission import build_submission_results, export_submission_results


def _shortlist() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "variant_id": ["candidate_1"],
            "AA": ["ACDEFGH"],
            "pred_pack": [0.8],
            "pred_pack_lcb": [0.6],
            "pred_brain_mouse": [0.3],
            "uncertainty_brain_mouse": [0.1],
            "pred_spinal_cord_mouse": [0.4],
            "uncertainty_spinal_cord_mouse": [0.1],
            "pred_liver_mouse": [-0.2],
            "uncertainty_liver_mouse": [0.1],
            "pred_heart_mouse": [0.0],
            "uncertainty_heart_mouse": [0.1],
            "pred_kidney_mouse": [0.1],
            "uncertainty_kidney_mouse": [0.1],
            "f_cns": [0.35],
            "f_off": [0.05],
            "display_score": [0.2],
            "specificity_index": [1.5],
            "selection_group": ["balanced"],
            "selection_rank": [1],
            "strict_conservative": [True],
            "immune_annotation": ["No sequence-specific immune claim."],
        }
    )


def test_build_submission_results_has_required_competition_fields() -> None:
    result = build_submission_results(_shortlist(), run_version="test-run")

    assert result.loc[0, "candidate_id"] == "candidate_1"
    assert result.loc[0, "candidate_sequence"] == "ACDEFGH"
    assert result.loc[0, "track"] == "赛道四：递送载体设计"
    assert result.loc[0, "run_version"] == "test-run"
    assert "predicted_packaging_lower_bound" in result
    assert "model" in result


def test_export_submission_results_writes_csv_and_manifest(tmp_path) -> None:
    source = tmp_path / "shortlist.csv"
    output = tmp_path / "results.csv"
    manifest = tmp_path / "results_manifest.json"
    _shortlist().to_csv(source, index=False)

    payload = export_submission_results(source, output, manifest_path=manifest)

    assert output.exists()
    assert manifest.exists()
    assert payload["rows"] == 1
    assert len(payload["output_sha256"]) == 64


def test_submission_export_rejects_invalid_sequence() -> None:
    shortlist = _shortlist()
    shortlist.loc[0, "AA"] = "ACDEXGH"

    with pytest.raises(ValueError, match="Invalid 7-mer"):
        build_submission_results(shortlist)


def test_export_preserves_endpoint_failures_and_order():
    shortlist = _shortlist()
    shortlist["passes_spinal_median"] = "False"
    result = build_submission_results(shortlist)
    assert not result.loc[0, "passes_spinal_median"]
    assert result.loc[0, "validation_status"] == "computational_hypothesis_only"


def test_export_rejects_nonfinite_prediction():
    shortlist = _shortlist()
    shortlist.loc[0, "pred_brain_mouse"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        build_submission_results(shortlist)


def test_export_cannot_overwrite_its_source(tmp_path):
    source = tmp_path / "source.csv"
    _shortlist().to_csv(source, index=False)
    before = source.read_bytes()
    with pytest.raises(ValueError, match="distinct"):
        export_submission_results(source, source)
    assert source.read_bytes() == before
