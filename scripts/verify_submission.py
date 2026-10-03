"""Verify submission integrity; distinguish intact files from complete contest compliance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from aav9_sma.evidence import build_evidence_audit
from aav9_sma.repro import sha256_file, verify_manifest
from aav9_sma.submission import build_submission_results

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Also fail when declared submission requirements remain unresolved",
    )
    args = parser.parse_args()
    manifest = ROOT / "docs/submission_manifest.json"
    verified = verify_manifest(manifest, ROOT)
    if not verified["ok"] or not verified["files_listed"]:
        raise SystemExit("Integrity verification failed: " + json.dumps(verified))
    source = ROOT / "docs/audit_data/virtual_screen_shortlist.csv"
    result_path = ROOT / "results/results.csv"
    result_manifest = json.loads((ROOT / "results/results_manifest.json").read_text())
    for path, key in ((source, "source_sha256"), (result_path, "output_sha256")):
        if sha256_file(path) != result_manifest[key]:
            raise SystemExit(f"Result manifest checksum mismatch: {path.name}")
    actual = pd.read_csv(result_path)
    expected = build_submission_results(
        pd.read_csv(source),
        model_version=result_manifest["model_version"],
        run_version=result_manifest["run_version"],
    )
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False, rtol=1e-12, atol=1e-12)
    build_evidence_audit(
        pd.read_csv(source),
        json.loads((ROOT / "docs/audit_data/virtual_screen_summary.json").read_text()),
        pd.read_csv(ROOT / "artifacts/literature_7mers/scores_with_organs.csv"),
    )
    outstanding = json.loads(manifest.read_text())["unresolved_submission_items"]
    print(
        json.dumps(
            {
                "integrity_ok": True,
                "files_checked": verified["files_listed"],
                "submission_ready": not outstanding,
                "unresolved_submission_items": outstanding,
            },
            indent=2,
        )
    )
    if args.require_ready and outstanding:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
