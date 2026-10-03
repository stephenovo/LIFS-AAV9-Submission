#!/usr/bin/env python3
"""Score published literature 7-mers (wrapper around aav9-sma score-external-peptides)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from aav9_sma.screening.producible_prior import score_external_peptides


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--peptides-csv",
        type=Path,
        default=Path("docs/audit_data/literature_public_7mers.csv"),
    )
    parser.add_argument("--screen-csv", type=Path, required=True)
    parser.add_argument("--reconstructed-csv", type=Path)
    parser.add_argument("--ensemble-size", type=int, default=5)
    parser.add_argument("--max-iter", type=int, default=80)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("artifacts/literature_public_7mer_scores.csv"),
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=Path("artifacts/literature_public_7mer_summary.json"),
    )
    args = parser.parse_args()

    peptides = pd.read_csv(args.peptides_csv)
    screen = pd.read_csv(args.screen_csv)
    reconstructed = (
        pd.read_csv(args.reconstructed_csv) if args.reconstructed_csv is not None else None
    )
    scored, summary = score_external_peptides(
        peptides,
        screen,
        reconstructed=reconstructed,
        ensemble_size=args.ensemble_size,
        random_state=args.random_state,
        max_iter=args.max_iter,
    )
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(args.output_csv, index=False)
    args.output_summary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    cols = [
        column
        for column in (
            "variant_id",
            "AA",
            "source",
            "pred_pack",
            "pred_pack_lcb_95",
            "pred_pack_lcb_90",
            "passes_packaging_gate",
            "passes_packaging_lcb90_gate",
            "passes_packaging_point_gate",
            "pred_brain_mouse",
            "pred_spinal_cord_mouse",
            "pred_liver_mouse",
            "S",
            "caveat",
        )
        if column in scored.columns
    ]
    print(scored[cols].to_string(index=False))
    print("Wrote", args.output_csv)
    print("Wrote", args.output_summary)
    print(
        "Reminder: literature_public_7mer sanity check only — "
        "do not merge into virtual_screen_shortlist.csv."
    )


if __name__ == "__main__":
    main()
