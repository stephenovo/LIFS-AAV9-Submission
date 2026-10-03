"""Reproduce the frozen-result audit and export; never fit models or select sequences."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from aav9_sma.evidence import ENDPOINTS, audit_saved_evidence
from aav9_sma.repro import sha256_file, verify_manifest
from aav9_sma.submission import export_submission_results

ROOT = Path(__file__).resolve().parents[1]


def command_output(command: list[str]) -> str | None:
    try:
        return subprocess.check_output(
            command, cwd=ROOT, stderr=subprocess.DEVNULL, text=True, timeout=10
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root", type=Path, help="Optionally verify existing raw/derived inputs"
    )
    args = parser.parse_args()
    started = datetime.now(UTC).isoformat()
    start = time.monotonic()
    os.chdir(ROOT)
    head = command_output(["git", "rev-parse", "HEAD"])
    dirty = bool(command_output(["git", "status", "--porcelain"]))
    source_paths = sorted(
        {
            *ROOT.glob("src/**/*.py"),
            *ROOT.glob("scripts/*.py"),
            *ROOT.glob("tests/*.py"),
            ROOT / "pyproject.toml",
            ROOT / "uv.lock",
            ROOT / "configs/default.yaml",
        }
    )
    source_hashes = {str(p.relative_to(ROOT)): sha256_file(p) for p in source_paths}
    data_check = {"status": "not_requested", "verified": []}
    counts = None
    if args.data_root:
        verification = verify_manifest(ROOT / "docs/data_manifest.json", args.data_root)
        if not verification["ok"]:
            raise SystemExit("Data manifest verification failed: " + json.dumps(verification))
        data_check = {"status": "verified", "verified": verification["verified"]}
        columns = [f"log2enr_whitelist__{ep}_animals_1_3__over__virus_prod2" for ep in ENDPOINTS]
        frame = pd.read_csv(
            args.data_root / "data/processed/fit4function_multiorgan_reconstructed.csv.gz",
            usecols=columns,
        )
        numeric = frame.apply(pd.to_numeric, errors="coerce").replace(
            [float("inf"), -float("inf")], float("nan")
        )
        counts = {
            ep: {
                "observed_rows": int(numeric[col].notna().sum()),
                "missing_rows": int(numeric[col].isna().sum()),
            }
            for ep, col in zip(ENDPOINTS, columns, strict=True)
        }
        counts["complete_case_rows"] = int(numeric.notna().all(axis=1).sum())

    shortlist = Path("docs/audit_data/virtual_screen_shortlist.csv")
    summary_path = Path("docs/audit_data/virtual_screen_summary.json")
    external = Path("artifacts/literature_7mers/scores_with_organs.csv")
    audit_saved_evidence(shortlist, summary_path, external, Path("docs/audit_data/updated_7_0"))
    export_submission_results(
        shortlist,
        "results/results.csv",
        manifest_path="results/results_manifest.json",
        model_version="updated-5.0-frozen-baseline",
        run_version=f"{head or 'git-unavailable'}{' + working-tree changes' if dirty else ''}",
    )
    summary = json.loads(summary_path.read_text())
    write_json(
        ROOT / "logs/final_model_record.json",
        {
            "record_type": "retrospective_recovery_not_contemporaneous_training_log",
            "historical_model_id": "updated-5.0-frozen-baseline",
            "baseline_code_revision": "0ba7f09",
            "shortlist_artifact_revision": "b34b01776d70ede1fbbd77598ca84f12515e79ed",
            "exact_historical_training_commit": None,
            "evidence_sources": {str(p): sha256_file(p) for p in (shortlist, summary_path)},
            "input_manifest_sha256": sha256_file("docs/data_manifest.json"),
            "upstream": json.loads(Path("docs/source_manifest.json").read_text()),
            "random_state": summary["random_state"],
            "member_seeds": list(range(42, 47)),
            "organ_fit": summary["organ_ensemble"],
            "packaging_fit": summary["packaging"],
            "observations_recomputed_at_audit": counts,
            "missing_label_policy": "complete cases across five standardized organ targets",
            "historical_training_wall_seconds": None,
            "historical_hardware": None,
            "historical_dependency_versions": None,
            "member_stopping_reasons": None,
            "weights_sha256": None,
            "unavailable_reason": (
                "Historical weights and contemporaneous execution metadata not retained"
            ),
            "training_recipe": "docs/FIT4FUNCTION_RUNBOOK.md",
            "new_training_executed": False,
        },
    )
    packages = {
        dist.metadata["Name"]: dist.version
        for dist in importlib.metadata.distributions()
        if dist.metadata.get("Name")
    }
    Path("logs").mkdir(exist_ok=True)
    Path("logs/audit_environment_requirements.txt").write_text(
        "# Audit environment only; not evidence of historical training dependencies.\n"
        + "\n".join(
            f"{name}=={version}"
            for name, version in sorted(packages.items())
            if name.lower().replace("_", "-") != "lifs-comp-aav9"
        )
        + "\n"
    )
    tools = {
        name: command_output([name, "--version"])
        for name in ("bowtie2", "fasterq-dump", "prefetch")
    }
    write_json(
        ROOT / "logs/submission_audit_run.json",
        {
            "activity": "saved_predictions_audit_and_export_not_training",
            "started_utc": started,
            "completed_utc": datetime.now(UTC).isoformat(),
            "wall_seconds": time.monotonic() - start,
            "command": "PYTHONPATH=src python scripts/prepare_submission.py"
            + (" --data-root <verified-input-root>" if args.data_root else ""),
            "git_head": head,
            "working_tree_dirty_at_start": dirty,
            "source_sha256": source_hashes,
            "python": sys.version,
            "os": platform.platform(),
            "machine": platform.machine(),
            "cpu": command_output(["sysctl", "-n", "machdep.cpu.brand_string"]),
            "logical_cpus": os.cpu_count(),
            "memory_bytes": command_output(["sysctl", "-n", "hw.memsize"]),
            "execution_device": "cpu",
            "gpu_required": False,
            "cuda_driver_and_toolkit": "not used by this audit or the default sklearn model",
            "optional_reconstruction_tool_versions": tools,
            "packages": packages,
            "data_verification": data_check,
            "exit_status": 0,
        },
    )
    deliverables = [
        "MODEL_CARD.md",
        "LICENSES/Fit4Function-BSD-3-Clause.txt",
        "README.md",
        "README.zh-CN.md",
        "LICENSE_STATUS.md",
        "THIRD_PARTY_NOTICES.md",
        "requirements.txt",
        "docs/SUBMISSION_GUIDE.zh-CN.md",
        "docs/EVIDENCE_SUMMARY.md",
        "docs/README.md",
        "docs/REPRODUCIBILITY.md",
        "docs/data_manifest.json",
        "docs/source_manifest.json",
        str(shortlist),
        str(summary_path),
        str(external),
        "docs/audit_data/experimental_validation_panel.csv",
        "docs/audit_data/updated_7_0/endpoint_summary.csv",
        "docs/audit_data/updated_7_0/external_endpoint_report.csv",
        "docs/audit_data/updated_7_0/evidence_summary.json",
        "results/results.csv",
        "results/results_manifest.json",
        "logs/final_model_record.json",
        "logs/release_validation.json",
        "logs/submission_audit_run.json",
        "logs/audit_environment_requirements.txt",
    ]
    write_json(
        ROOT / "docs/submission_manifest.json",
        {
            "schema_version": 1,
            "files": [
                {"path": path, "sha256": sha256_file(path)}
                for path in sorted(set(deliverables) | set(source_hashes))
            ],
            "unresolved_submission_items": [
                "Official competition output template has not been checked",
                "Project redistribution license requires a rights-holder decision",
                "Historical weights and contemporaneous training log are unavailable; "
                "use documented refit recipe",
            ],
        },
    )
    print("Frozen-result audit/export complete. No model was trained or candidate selected.")


if __name__ == "__main__":
    main()
