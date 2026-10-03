import hashlib
import json
import subprocess
from zipfile import ZipFile

import pytest

from scripts.package_submission import build_package, include_path, verify_inventory


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repository"
    root.mkdir()
    (root / "docs").mkdir()
    (root / "README.md").write_text("Example project\n")
    manifest = {
        "files": [
            {"path": "README.md", "sha256": hashlib.sha256(b"Example project\n").hexdigest()}
        ],
        "unresolved_submission_items": ["Model checkpoint unavailable"],
    }
    (root / "docs/submission_manifest.json").write_text(json.dumps(manifest))
    (root / ".gitignore").write_text(".venv/\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Fixture",
        ],
        check=True,
    )
    return root


def test_package_excludes_local_files_and_records_checksums(repository, tmp_path):
    (repository / "docs/private-note.md").write_text("untracked private note")
    (repository / ".venv").mkdir()
    (repository / ".venv/private.txt").write_text("local environment")
    output = tmp_path / "source.zip"
    report = build_package(repository, output)
    assert report["submission_ready"] is False
    with ZipFile(output) as archive:
        assert set(archive.namelist()) == {
            "README.md",
            "docs/submission_manifest.json",
            "PACKAGE_MANIFEST.json",
        }
        inventory = json.loads(archive.read("PACKAGE_MANIFEST.json"))
        for entry in inventory["files"]:
            assert hashlib.sha256(archive.read(entry["path"])).hexdigest() == entry["sha256"]
    with pytest.raises(ValueError, match="already exists"):
        build_package(repository, output)


def test_package_rejects_uncommitted_changes(repository, tmp_path):
    (repository / "README.md").write_text("Uncommitted change")
    with pytest.raises(ValueError, match="tracked changes"):
        build_package(repository, tmp_path / "source.zip")


def test_package_rejects_unresolved_delivery_when_required(repository, tmp_path):
    output = tmp_path / "source.zip"
    with pytest.raises(ValueError, match="not ready"):
        build_package(repository, output, require_ready=True)
    assert not output.exists()


def test_inventory_rejects_tampering():
    manifest = {
        "files": [{"path": "README.md", "sha256": "0" * 64}],
        "unresolved_submission_items": [],
    }
    with pytest.raises(ValueError, match="Checksum mismatch"):
        verify_inventory(
            {
                "docs/submission_manifest.json": json.dumps(manifest).encode(),
                "README.md": b"changed",
            },
            require_ready=False,
        )


@pytest.mark.parametrize(
    "path",
    [
        "../secret.txt",
        "/private.txt",
        "docs/../../secret.txt",
        "docs/.venv/token",
        "docs/recording.MP4",
        "data/raw/input.csv",
        ".git/config",
        "artifacts/demo/example.csv",
    ],
)
def test_path_filter_excludes_non_delivery_files(path):
    assert not include_path(path)
