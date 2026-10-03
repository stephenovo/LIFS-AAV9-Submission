"""Producible-prior sampling (scheme 2) — does not replace the main 95% LCB funnel.

Workflow:
1. Sample a large random 7-mer pool (excluding observed library sequences).
2. Fit the same calibrated packaging Ridge used by ``screen-virtual``.
3. Keep peptides whose **point** ``pred_pack`` meets a configurable producible rule
   (default: ``pred_pack >= median(Production2)``).
4. Uniformly resample from that subset.
5. Optionally score organs with ``predict_organ_ensemble`` + ``rank_candidates`` when a
   reconstructed multi-organ table is provided.

This path intentionally uses a **point-estimate** packaging prior for resampling so the
prior pool is larger than the conservative 95% LCB shortlist gate. The main virtual-screen
shortlist and default 95% LCB hard gate are unchanged.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Literal

import numpy as np
import pandas as pd

from aav9_sma.features.encode import one_hot_7mer
from aav9_sma.models.evaluate import MULTIORGAN_ENDPOINTS
from aav9_sma.screening.score import rank_candidates
from aav9_sma.screening.virtual import (
    HUMAN_LIVER_TASKS,
    add_weight_sensitivity,
    annotate_sequence_liabilities,
    fit_calibrated_packaging_model,
    generate_candidate_peptides,
    predict_human_liver_annotations,
    predict_organ_ensemble,
    select_diverse_shortlist,
    training_distance_lower_bound,
)

ProducibleRule = Literal["point_median"]


def packaging_gate_counts(frame: pd.DataFrame) -> dict[str, int]:
    """Return consistently named aggregate counts for the three packaging gates."""
    return {
        "packaging_gate_passed_95_lcb": int(frame["passes_packaging_gate"].sum()),
        "packaging_gate_passed_90_lcb": int(
            frame["passes_packaging_lcb90_gate"].sum()
        ),
        "packaging_gate_passed_point": int(
            frame["passes_packaging_point_gate"].sum()
        ),
    }


def packaging_offsets(
    screen: pd.DataFrame,
    *,
    random_state: int = 42,
) -> tuple[object, float, float, float, dict[str, object]]:
    """Fit packaging Ridge once conceptually; return 95% and 90% LCB offsets.

    ``fit_calibrated_packaging_model`` is called twice with different coverages. The
    final Ridge (fit on all finite Production2 rows) is identical in both calls; only
    the calibration offset changes.
    """
    model_95, threshold, offset_95, metrics_95 = fit_calibrated_packaging_model(
        screen, random_state=random_state, coverage=0.95
    )
    _, _, offset_90, metrics_90 = fit_calibrated_packaging_model(
        screen, random_state=random_state, coverage=0.90
    )
    meta: dict[str, object] = {
        "packaging_95": metrics_95,
        "packaging_90": metrics_90,
        "packaging_threshold": float(threshold),
        "lower_bound_offset_95": float(offset_95),
        "lower_bound_offset_90": float(offset_90),
    }
    return model_95, float(threshold), float(offset_95), float(offset_90), meta


def annotate_packaging_gates(
    frame: pd.DataFrame,
    *,
    packaging_threshold: float,
    offset_95: float,
    offset_90: float,
) -> pd.DataFrame:
    """Add point / 90% LCB / 95% LCB packaging gate columns (reporting only)."""
    out = frame.copy()
    if "pred_pack" not in out.columns:
        raise ValueError("pred_pack column is required")
    out["pred_pack_lcb_95"] = out["pred_pack"] - offset_95
    out["pred_pack_lcb_90"] = out["pred_pack"] - offset_90
    # Alias used by rank_candidates / screen-virtual main gate
    out["pred_pack_lcb"] = out["pred_pack_lcb_95"]
    out["passes_packaging_point_gate"] = out["pred_pack"] >= packaging_threshold
    out["passes_packaging_lcb90_gate"] = out["pred_pack_lcb_90"] >= packaging_threshold
    out["passes_packaging_gate"] = out["pred_pack_lcb_95"] >= packaging_threshold
    out["packaging_threshold"] = packaging_threshold
    out["lower_bound_offset_95"] = offset_95
    out["lower_bound_offset_90"] = offset_90
    return out


def select_producible_subset(
    candidates: pd.DataFrame,
    *,
    packaging_threshold: float,
    rule: ProducibleRule = "point_median",
) -> pd.DataFrame:
    """Return rows that pass the configured producible-prior rule."""
    if rule != "point_median":
        raise ValueError(f"Unsupported producible rule: {rule}")
    mask = candidates["pred_pack"] >= packaging_threshold
    return candidates.loc[mask].copy()


def uniform_resample(
    frame: pd.DataFrame,
    count: int,
    *,
    random_state: int = 42,
) -> pd.DataFrame:
    """Uniformly sample ``count`` rows without replacement (or with if pool is smaller)."""
    if count < 1:
        raise ValueError("count must be positive")
    if frame.empty:
        raise ValueError("Cannot resample from an empty producible subset")
    rng = np.random.default_rng(random_state)
    replace = len(frame) < count
    indices = rng.choice(frame.index.to_numpy(), size=count, replace=replace)
    sampled = frame.loc[indices].copy().reset_index(drop=True)
    sampled["producible_resample_with_replacement"] = replace
    return sampled


def run_producible_prior_screen(
    screen: pd.DataFrame,
    *,
    reconstructed: pd.DataFrame | None = None,
    pool_size: int = 50_000,
    resample_size: int = 5_000,
    producible_rule: ProducibleRule = "point_median",
    ensemble_size: int = 5,
    random_state: int = 42,
    max_iter: int = 80,
    brain_target_weight: float = 0.50,
    spinal_target_weight: float = 0.50,
    build_shortlist: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame | None, dict[str, object]]:
    """Scheme-2 sampling + optional organ ranking.

    Returns ``(scored_resample, shortlist_or_none, summary)``.
    When ``reconstructed`` is None, organ columns / shortlist are omitted and only
    packaging annotations are returned for the resampled peptides.
    """
    observed: set[str] = set(screen["AA"].astype(str))
    if reconstructed is not None and "AA" in reconstructed.columns:
        observed |= set(reconstructed["AA"].astype(str))

    peptides = generate_candidate_peptides(
        pool_size, excluded=observed, random_state=random_state
    )
    model, threshold, offset_95, offset_90, pack_meta = packaging_offsets(
        screen, random_state=random_state
    )
    pred_pack = model.predict(one_hot_7mer(peptides))
    pool = pd.DataFrame(
        {
            "variant_id": [f"PRIOR_{index:07d}" for index in range(1, pool_size + 1)],
            "AA": peptides,
            "pred_pack": pred_pack,
            "sampling_source": "producible_prior",
        }
    )
    pool = annotate_packaging_gates(
        pool,
        packaging_threshold=threshold,
        offset_95=offset_95,
        offset_90=offset_90,
    )
    producible = select_producible_subset(
        pool, packaging_threshold=threshold, rule=producible_rule
    )
    sampled = uniform_resample(
        producible, resample_size, random_state=random_state + 1
    )
    sampled["producible_rule"] = producible_rule
    sampled["variant_id"] = [
        f"PRIOR_{index:07d}" for index in range(1, len(sampled) + 1)
    ]

    summary: dict[str, object] = {
        "mode": "producible_prior_sampling",
        "note": (
            "Does not replace screen-virtual or the primary 95% LCB shortlist funnel. "
            "Resampling uses a point-estimate producible prior."
        ),
        "random_state": random_state,
        "pool_size": pool_size,
        "resample_size": resample_size,
        "producible_rule": producible_rule,
        "observed_sequences_excluded": len(observed),
        "producible_pool_rows": int(len(producible)),
        "producible_fraction": float(len(producible) / max(len(pool), 1)),
        "resample_unique_sequences": int(sampled["AA"].nunique()),
        "resample_with_replacement": bool(
            sampled["producible_resample_with_replacement"].iloc[0]
        ),
        **pack_meta,
        **packaging_gate_counts(sampled),
        "organs_scored": reconstructed is not None,
    }

    if reconstructed is None:
        summary["organ_status"] = "skipped_no_reconstructed_input; packaging prior sampling only"
        return sampled, None, summary

    features = one_hot_7mer(sampled["AA"].tolist())
    organ_mean, organ_std, organ_meta = predict_organ_ensemble(
        reconstructed,
        features,
        ensemble_size=ensemble_size,
        random_state=random_state,
        max_iter=max_iter,
    )
    for endpoint_index, endpoint in enumerate(MULTIORGAN_ENDPOINTS):
        sampled[f"pred_{endpoint}_mouse"] = organ_mean[:, endpoint_index]
        sampled[f"uncertainty_{endpoint}_mouse"] = organ_std[:, endpoint_index]
    sampled["organ_uncertainty_mean"] = organ_std.mean(axis=1)
    sampled["training_distance_lower_bound"] = training_distance_lower_bound(
        sampled["AA"].tolist(), observed
    )
    liability = annotate_sequence_liabilities(sampled["AA"])
    human_parts: list[pd.DataFrame] = [sampled.reset_index(drop=True), liability]
    if all(column in screen.columns for column in HUMAN_LIVER_TASKS):
        human_liver, human_liver_threshold = predict_human_liver_annotations(
            screen, features
        )
        human_parts.append(human_liver)
        summary["human_liver_warning_threshold"] = human_liver_threshold
    else:
        summary["human_liver_status"] = "skipped_missing_HepG2_THLE_columns"
    sampled = pd.concat(human_parts, axis=1)
    ranked = rank_candidates(
        sampled,
        packaging_threshold=threshold,
        brain_target_weight=brain_target_weight,
        spinal_target_weight=spinal_target_weight,
    )
    # Preserve three-gate reporting columns after rank_candidates
    ranked = annotate_packaging_gates(
        ranked,
        packaging_threshold=threshold,
        offset_95=offset_95,
        offset_90=offset_90,
    )
    ranked["S"] = ranked["display_score"]
    ranked["sampling_source"] = "producible_prior"
    ranked = add_weight_sensitivity(ranked)
    summary["organ_ensemble"] = {
        "architecture": "shared_mlp_64_32",
        "members": ensemble_size,
        **organ_meta,
    }
    summary.update(packaging_gate_counts(ranked))

    shortlist = None
    if build_shortlist:
        shortlist = select_diverse_shortlist(ranked)
        shortlist["sampling_source"] = "producible_prior"
        shortlist["panel_role"] = "producible_prior_shortlist_not_primary"
        summary["shortlist_rows"] = len(shortlist)
    return ranked, shortlist, summary


def score_external_peptides(
    peptides: pd.DataFrame,
    screen: pd.DataFrame,
    *,
    reconstructed: pd.DataFrame | None = None,
    ensemble_size: int = 5,
    random_state: int = 42,
    max_iter: int = 80,
    brain_target_weight: float = 0.50,
    spinal_target_weight: float = 0.50,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Score an external AA table with packaging (+ optional organs).

    Required columns: ``AA``. Optional: ``variant_id``, ``name``, ``source``, ``note``.
    """
    if "AA" not in peptides.columns:
        raise ValueError("peptides table must contain an AA column")
    frame = peptides.copy()
    frame["AA"] = frame["AA"].astype(str).str.upper()
    illegal = frame.loc[frame["AA"].map(lambda aa: len(aa) != 7), "AA"]
    if len(illegal):
        raise ValueError(f"Non-7-mer sequences present: {illegal.head().tolist()}")
    if "variant_id" not in frame.columns:
        frame["variant_id"] = [f"EXT_{index:04d}" for index in range(1, len(frame) + 1)]
    if "source" not in frame.columns:
        frame["source"] = "external"

    model, threshold, offset_95, offset_90, pack_meta = packaging_offsets(
        screen, random_state=random_state
    )
    unique_aa = list(dict.fromkeys(frame["AA"].tolist()))
    pred_map = {
        aa: float(pred)
        for aa, pred in zip(
            unique_aa, model.predict(one_hot_7mer(unique_aa)), strict=True
        )
    }
    frame["pred_pack"] = frame["AA"].map(pred_map)
    frame = annotate_packaging_gates(
        frame,
        packaging_threshold=threshold,
        offset_95=offset_95,
        offset_90=offset_90,
    )

    summary: dict[str, object] = {
        "mode": "score_external_peptides",
        "n_rows": len(frame),
        "n_unique_7mers": len(unique_aa),
        "organs_scored": reconstructed is not None,
        "sanity_check_only": True,
        "claim_boundary": (
            "Literature / external peptide scores are a directional sanity check only; "
            "they do not validate the model or replace wet-lab evidence."
        ),
        **pack_meta,
        **packaging_gate_counts(frame),
    }

    if reconstructed is None:
        summary["organ_status"] = "skipped_no_reconstructed_input"
        frame["S"] = np.nan
        return frame, summary

    features = one_hot_7mer(unique_aa)
    organ_mean, organ_std, organ_meta = predict_organ_ensemble(
        reconstructed,
        features,
        ensemble_size=ensemble_size,
        random_state=random_state,
        max_iter=max_iter,
    )
    organ = pd.DataFrame({"AA": unique_aa})
    for endpoint_index, endpoint in enumerate(MULTIORGAN_ENDPOINTS):
        organ[f"pred_{endpoint}_mouse"] = organ_mean[:, endpoint_index]
        organ[f"uncertainty_{endpoint}_mouse"] = organ_std[:, endpoint_index]
    organ["organ_uncertainty_mean"] = organ_std.mean(axis=1)
    merged = frame.merge(organ, on="AA", how="left")
    ranked = rank_candidates(
        merged,
        packaging_threshold=threshold,
        brain_target_weight=brain_target_weight,
        spinal_target_weight=spinal_target_weight,
    )
    ranked = annotate_packaging_gates(
        ranked,
        packaging_threshold=threshold,
        offset_95=offset_95,
        offset_90=offset_90,
    )
    ranked["S"] = ranked["display_score"]
    # Restore annotation columns dropped/reordered by ranking
    for column in ("name", "source", "note", "citation", "caveat"):
        if column in merged.columns and column not in ranked.columns:
            ranked = ranked.merge(
                merged[["variant_id", column]].drop_duplicates("variant_id"),
                on="variant_id",
                how="left",
            )
    summary["organ_ensemble"] = {
        "architecture": "shared_mlp_64_32",
        "members": ensemble_size,
        **organ_meta,
    }
    summary.update(packaging_gate_counts(ranked))
    return ranked, summary


def filter_observed(
    peptides: Collection[str], observed: Collection[str]
) -> list[str]:
    """Helper kept for tests / scripts."""
    blocked = set(observed)
    return [peptide for peptide in peptides if peptide not in blocked]
