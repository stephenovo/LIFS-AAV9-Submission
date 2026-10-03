"""Build a source ZIP from a committed revision and verify its file inventory."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    "README.md",
    "README.zh-CN.md",
    "MODEL_CARD.md",
    "LICENSE_STATUS.md",
    "THIRD_PARTY_NOTICES.md",
    "requirements.txt",
    "pyproject.toml",
    "uv.lock",
}
DIRECTORIES = {"src", "scripts", "tests", "configs", "docs", "logs", "results", "LICENSES"}
SAVED_ARTIFACTS = {"literature_7mers", "producible_prior"}
EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".mp4", ".mov", ".mkv"}


def include_path(name: str) -> bool:
    """Select project files without collecting local files or Git metadata."""
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return False
    if set(path.parts) & EXCLUDED_PARTS or path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if path.name == ".gitkeep":
        return False
    if name in ROOT_FILES or path.parts[0] in DIRECTORIES:
        return True
    return len(path.parts) > 2 and path.parts[0] == "artifacts" and path.parts[1] in SAVED_ARTIFACTS


def verify_inventory(files: dict[str, bytes], *, require_ready: bool) -> list[str]:
    """Verify the committed delivery manifest against the files to be packaged."""
    manifest = json.loads(files["docs/submission_manifest.json"])
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Delivery manifest must list at least one file")
    seen: set[str] = set()
    for entry in entries:
        name = entry["path"]
        if name in seen:
            raise ValueError(f"Duplicate manifest entry: {name}")
        seen.add(name)
        if name not in files:
            raise ValueError(f"Manifest file missing from archive: {name}")
        if hashlib.sha256(files[name]).hexdigest() != entry["sha256"]:
            raise ValueError(f"Checksum mismatch: {name}")
    outstanding = manifest.get("unresolved_submission_items")
    if not isinstance(outstanding, list) or any(not isinstance(x, str) for x in outstanding):
        raise ValueError("Manifest must declare unresolved_submission_items as a list of strings")
    if require_ready and outstanding:
        raise ValueError("Submission is not ready: " + "; ".join(outstanding))
    return outstanding


def build_package(root: Path, output: Path, *, require_ready: bool = False) -> dict:
    """Package HEAD only; fail rather than silently omit tracked working changes."""
    root = root.resolve()

    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", "-C", str(root), *args])

    if git("status", "--porcelain", "--untracked-files=no").strip():
        raise ValueError("Commit or resolve tracked changes before packaging")
    output = output.resolve()
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    revision = git("rev-parse", "HEAD").decode().strip()
    archive = git("archive", "--format=zip", revision)
    files: dict[str, bytes] = {}
    with ZipFile(io.BytesIO(archive)) as source:
        for entry in source.infolist():
            if entry.is_dir() or not include_path(entry.filename):
                continue
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"Symlink is not supported in source package: {entry.filename}")
            files[entry.filename] = source.read(entry)
    outstanding = verify_inventory(files, require_ready=require_ready)
    inventory = {
        "schema_version": 1,
        "source_commit": revision,
        "scope": "committed_source_and_saved_results",
        "submission_ready": not outstanding,
        "unresolved_submission_items": outstanding,
        "files": [
            {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for name, data in sorted(files.items())
        ],
    }
    files["PACKAGE_MANIFEST.json"] = (
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
    ).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Write a complete ZIP first; exclusive creation prevents overwriting another artifact.
    with tempfile.TemporaryFile() as temporary:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=6) as target:
            for name, data in sorted(files.items()):
                entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                target.writestr(entry, data)
        temporary.seek(0)
        with output.open("xb") as destination:
            for chunk in iter(lambda: temporary.read(1024 * 1024), b""):
                destination.write(chunk)
    return {
        "output": str(output),
        "source_commit": revision,
        "files": len(files),
        "bytes": output.stat().st_size,
        "submission_ready": not outstanding,
        "unresolved_submission_items": outstanding,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    try:
        report = build_package(ROOT, args.output, require_ready=args.require_ready)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Packaging failed: {error}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
