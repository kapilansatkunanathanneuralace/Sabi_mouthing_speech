from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from sabi.runtime.asset_cache import AssetCache, AssetManifest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(root: Path, source: Path, *, sha256: str | None = None) -> Path:
    manifest = root / "fixture.toml"
    manifest.write_text(
        "\n".join(
            [
                "[manifest]",
                'name = "fixture"',
                'kind = "test"',
                "",
                "[[files]]",
                'name = "payload"',
                'kind = "test"',
                'relative_path = "payload.bin"',
                f'url = "{source.as_uri()}"',
                f'sha256 = "{sha256 or _sha256(source)}"',
            ]
        ),
        encoding="utf-8",
    )
    return manifest


def test_manifest_rejects_unsafe_relative_path(tmp_path: Path) -> None:
    manifest = tmp_path / "bad.toml"
    manifest.write_text(
        "\n".join(
            [
                "[manifest]",
                'name = "bad"',
                "",
                "[[files]]",
                'name = "escape"',
                'relative_path = "../escape.bin"',
                'url = "file:///tmp/escape.bin"',
                'sha256 = "abc"',
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        AssetManifest.load(manifest)


def test_ensure_verify_and_clear_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"cache payload")
    manifest_root = tmp_path / "manifests"
    manifest_root.mkdir()
    _manifest(manifest_root, source)
    cache = AssetCache(app_home=tmp_path / "models", manifest_root=manifest_root)
    progress = []

    missing = cache.status("fixture")
    assert missing["status"] == "missing"

    present = cache.ensure("fixture", progress=progress.append)
    assert present["status"] == "present"
    assert any(item["status"] == "verified" for item in progress)

    verified = cache.verify("fixture")
    assert verified["status"] == "present"

    cleared = cache.clear("fixture")
    assert cleared["status"] == "missing"


def test_hash_mismatch_reports_corrupt(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"expected")
    manifest_root = tmp_path / "manifests"
    manifest_root.mkdir()
    _manifest(manifest_root, source)
    cache = AssetCache(app_home=tmp_path / "models", manifest_root=manifest_root)
    cache.ensure("fixture")

    cached = tmp_path / "models" / "fixture" / "payload.bin"
    cached.write_bytes(b"tampered")

    status = cache.verify("fixture")
    assert status["status"] == "corrupt"
    assert status["entries"][0]["status"] == "corrupt"


def test_bad_download_removes_partial_file(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"payload")
    manifest_root = tmp_path / "manifests"
    manifest_root.mkdir()
    _manifest(manifest_root, source, sha256="0" * 64)
    cache = AssetCache(app_home=tmp_path / "models", manifest_root=manifest_root)

    status = cache.ensure("fixture")

    assert status["status"] == "corrupt"
    assert not list((tmp_path / "models" / "fixture").glob("*.part"))
