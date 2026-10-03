"""Tests for scheme-2 producible-prior sampling (synthetic fixtures only)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from aav9_sma.constants import AMINO_ACIDS
from aav9_sma.screening.producible_prior import (
    annotate_packaging_gates,
    run_producible_prior_screen,
    score_external_peptides,
    select_producible_subset,
    uniform_resample,
)


def _synthetic_screen(n: int = 80, random_state: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    peptides: list[str] = []
    seen: set[str] = set()
    while len(peptides) < n:
        peptide = "".join(rng.choice(list(AMINO_ACIDS), size=7))
        if peptide in seen:
            continue
        seen.add(peptide)
        peptides.append(peptide)
    # Make Production2 somewhat sequence-dependent so Ridge has signal
    scores = []
    for peptide in peptides:
        charge = peptide.count("K") + peptide.count("R") - peptide.count("D") - peptide.count("E")
        scores.append(0.3 * charge + rng.normal(0.0, 0.4))
    return pd.DataFrame({"AA": peptides, "Production2": scores})


def _synthetic_reconstructed(screen: pd.DataFrame, random_state: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    frame = screen[["AA"]].copy()
    for endpoint in ("brain", "spinal_cord", "liver", "heart", "kidney"):
        column = f"log2enr_whitelist__{endpoint}_animals_1_3__over__virus_prod2"
        # Weak inverse liver vs CNS signal
        base = rng.normal(0.0, 0.3, size=len(frame))
        if endpoint in {"brain", "spinal_cord"}:
            frame[column] = base + 0.15
        elif endpoint == "liver":
            frame[column] = -base
        else:
            frame[column] = rng.normal(0.0, 0.2, size=len(frame))
    return frame


def test_select_producible_subset_point_median() -> None:
    frame = pd.DataFrame(
        {
            "AA": ["AAAAAAA", "CCCCCCC", "DDDDDDD"],
            "pred_pack": [-1.0, 0.0, 1.0],
        }
    )
    selected = select_producible_subset(frame, packaging_threshold=0.0)
    assert set(selected["AA"]) == {"CCCCCCC", "DDDDDDD"}


def test_uniform_resample_is_deterministic() -> None:
    frame = pd.DataFrame({"AA": [f"A{index:06d}" for index in range(20)], "pred_pack": 1.0})
    first = uniform_resample(frame, 5, random_state=3)
    second = uniform_resample(frame, 5, random_state=3)
    assert first["AA"].tolist() == second["AA"].tolist()


def test_annotate_three_packaging_gates() -> None:
    frame = pd.DataFrame({"AA": ["AAAAAAA"], "pred_pack": [0.0]})
    annotated = annotate_packaging_gates(
        frame, packaging_threshold=-0.5, offset_95=2.0, offset_90=1.0
    )
    assert annotated["pred_pack_lcb_95"].iloc[0] == -2.0
    assert annotated["pred_pack_lcb_90"].iloc[0] == -1.0
    assert bool(annotated["passes_packaging_point_gate"].iloc[0])
    assert not bool(annotated["passes_packaging_lcb90_gate"].iloc[0])
    assert not bool(annotated["passes_packaging_gate"].iloc[0])


def test_producible_prior_packaging_only_small_pool() -> None:
    screen = _synthetic_screen(96, random_state=2)
    scored, shortlist, summary = run_producible_prior_screen(
        screen,
        reconstructed=None,
        pool_size=40,
        resample_size=8,
        random_state=5,
    )
    assert shortlist is None
    assert summary["organs_scored"] is False
    assert len(scored) == 8
    assert "pred_pack" in scored.columns
    assert "passes_packaging_point_gate" in scored.columns
    assert scored["pred_pack"].ge(summary["packaging_threshold"]).all()
    assert summary["packaging_gate_passed_point"] == 8
    assert summary["resample_unique_sequences"] == 8
    assert summary["resample_with_replacement"] is False
    assert summary["organ_status"].startswith("skipped_no_reconstructed_input")


def test_producible_prior_with_synthetic_organs() -> None:
    screen = _synthetic_screen(120, random_state=7)
    reconstructed = _synthetic_reconstructed(screen, random_state=8)
    scored, shortlist, summary = run_producible_prior_screen(
        screen,
        reconstructed=reconstructed,
        pool_size=30,
        resample_size=6,
        ensemble_size=2,
        max_iter=20,
        random_state=11,
        build_shortlist=True,
    )
    assert summary["organs_scored"] is True
    assert "pred_brain_mouse" in scored.columns
    assert "display_score" in scored.columns
    assert shortlist is not None
    assert len(shortlist) <= 30
    assert shortlist["panel_role"].eq("producible_prior_shortlist_not_primary").all()


def test_score_external_peptides_reports_three_gates() -> None:
    screen = _synthetic_screen(100, random_state=13)
    peptides = pd.DataFrame(
        {
            "variant_id": ["lit_a", "lit_b"],
            "AA": [screen["AA"].iloc[0], "WWWWWWW"],
            "source": "literature_public_7mer",
        }
    )
    scored, summary = score_external_peptides(peptides, screen, reconstructed=None)
    assert summary["sanity_check_only"] is True
    assert set(
        [
            "passes_packaging_gate",
            "passes_packaging_lcb90_gate",
            "passes_packaging_point_gate",
        ]
    ) <= set(scored.columns)
    assert scored["source"].eq("literature_public_7mer").all()
    assert summary["packaging_gate_passed_point"] == int(
        scored["passes_packaging_point_gate"].sum()
    )
    assert summary["packaging_gate_passed_90_lcb"] == int(
        scored["passes_packaging_lcb90_gate"].sum()
    )
    assert summary["packaging_gate_passed_95_lcb"] == int(
        scored["passes_packaging_gate"].sum()
    )
