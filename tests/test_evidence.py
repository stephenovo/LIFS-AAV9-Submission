import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aav9_sma.evidence import audit_saved_evidence, build_evidence_audit

ROOT = Path(__file__).resolve().parents[1]


def saved_inputs():
    return (
        pd.read_csv(ROOT / "docs/audit_data/virtual_screen_shortlist.csv"),
        json.loads((ROOT / "docs/audit_data/virtual_screen_summary.json").read_text()),
        pd.read_csv(ROOT / "artifacts/literature_7mers/scores_with_organs.csv"),
    )


def test_frozen_evidence_does_not_convert_directionality_to_validation():
    shortlist, summary, external = saved_inputs()
    original = shortlist.copy(deep=True)
    endpoints, report, audit = build_evidence_audit(shortlist, summary, external)
    assert endpoints.set_index("endpoint").loc["spinal_cord", "passes_training_reference"] == 24
    assert audit["strict_conservative_rows"] == 7
    assert audit["aav_f_vs_s"]["brain_direction_pass"] is False
    assert audit["aav_f_vs_s"]["spinal_cord_direction_pass"] is True
    assert not audit["cns_tropism_validated"]
    assert not report["validates_cns_tropism"].any()
    pd.testing.assert_frame_equal(shortlist, original)


def test_positive_pair_still_does_not_validate_tropism():
    shortlist, summary, external = saved_inputs()
    external.loc[external.name == "AAV-F", "pred_brain_mouse"] = 2.0
    _, _, audit = build_evidence_audit(shortlist, summary, external)
    assert audit["aav_f_vs_s"]["status"] == "direction_only_pass"
    assert not audit["aav_f_vs_s"]["independent_validation"]
    assert not audit["cns_tropism_validated"]


def test_absent_pair_is_not_a_pass():
    shortlist, summary, external = saved_inputs()
    external = external[external.name != "AAV-F"]
    _, _, audit = build_evidence_audit(shortlist, summary, external)
    assert audit["aav_f_vs_s"]["status"] == "not_evaluable"


def test_audit_rejects_output_collision_before_writing(tmp_path):
    source = tmp_path / "endpoint_summary.csv"
    source.write_text("preserve this evidence")
    with pytest.raises(ValueError, match="overwrite"):
        audit_saved_evidence(source, tmp_path / "summary.json", tmp_path / "external.csv", tmp_path)
    assert source.read_text() == "preserve this evidence"


@pytest.mark.parametrize("fault", ["missing", "nonfinite", "stale_flag", "string_false"])
def test_corrupt_evidence_is_rejected(fault):
    shortlist, summary, external = saved_inputs()
    if fault == "missing":
        external = external.drop(columns="pred_spinal_cord_mouse")
    elif fault == "nonfinite":
        external.loc[0, "pred_spinal_cord_mouse"] = np.nan
    elif fault == "stale_flag":
        shortlist.loc[0, "passes_spinal_median"] = not shortlist.loc[0, "passes_spinal_median"]
    else:
        external["passes_packaging_gate"] = "False"
        _, _, audit = build_evidence_audit(shortlist, summary, external)
        assert audit["external_packaging_counts"]["passes_packaging_gate"] == 0
        return
    with pytest.raises(ValueError):
        build_evidence_audit(shortlist, summary, external)
