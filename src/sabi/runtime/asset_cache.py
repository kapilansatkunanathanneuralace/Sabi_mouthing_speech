"""Managed model asset cache for packaged desktop installs."""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field, field_validator

from sabi.runtime.paths import manifests_dir, models_dir, repo_root

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py<3.11 fallback
    import tomli as tomllib  # type: ignore[import-not-found]

CHUNK = 1 << 20
ProgressCallback = Callable[[dict[str, Any]], None]
CacheStatus = Literal["present", "missing", "corrupt", "unsupported"]


class AssetEntry(BaseModel):
    name: str
    url: str = ""
    sha256: str = ""
    relative_path: str
    kind: str = "model"
    size_bytes: int | None = Field(default=None, ge=0)

    @field_validator("relative_path")
    @classmethod
    def _relative_path_is_safe(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe relative_path: {value}")
        return value

    @property
    def downloadable(self) -> bool:
        return bool(self.url and self.sha256)


class AssetManifest(BaseModel):
    name: str
    kind: str = "model"
    description: str = ""
    files: list[AssetEntry] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "AssetManifest":
        with path.open("rb") as f:
            raw = tomllib.load(f)
        meta = raw.get("manifest", {})
        name = str(meta.get("name") or path.stem)
        kind = str(meta.get("kind") or path.stem)
        description = str(meta.get("description") or "")
        files = []
        for entry in raw.get("files", []):
            files.append({"kind": entry.get("kind") or kind, **entry})
        return cls(name=name, kind=kind, description=description, files=files)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(url) as resp, tmp.open("wb") as out:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
        tmp.replace(dest)
    finally:
        if tmp.exists():
            tmp.unlink()


class AssetCache:
    """Download, verify, and clear model assets under the app-controlled cache root."""

    def __init__(self, app_home: Path | None = None, manifest_root: Path | None = None) -> None:
        self.root = app_home or models_dir()
        self.manifest_root = manifest_root or manifests_dir()

    def manifest_path(self, manifest_name: str) -> Path:
        path = self.manifest_root / f"{manifest_name}.toml"
        if not path.is_file():
            raise ValueError(f"unknown manifest: {manifest_name}")
        return path

    def load_manifest(self, manifest_name: str, manifest_path: Path | None = None) -> AssetManifest:
        return AssetManifest.load(manifest_path or self.manifest_path(manifest_name))

    def path_of(self, manifest_name: str, asset_name: str) -> Path:
        manifest = self.load_manifest(manifest_name)
        for entry in manifest.files:
            if entry.name == asset_name:
                return self._entry_path(manifest, entry)
        raise ValueError(f"unknown asset: {asset_name}")

    def status(self, manifest_name: str, manifest_path: Path | None = None) -> dict[str, Any]:
        manifest = self.load_manifest(manifest_name, manifest_path)
        return self._status_for_manifest(manifest)

    def status_manifest(self, manifest: AssetManifest) -> dict[str, Any]:
        return self._status_for_manifest(manifest)

    def verify(self, manifest_name: str, manifest_path: Path | None = None) -> dict[str, Any]:
        return self.status(manifest_name, manifest_path)

    def ensure(
        self,
        manifest_name: str,
        *,
        manifest_path: Path | None = None,
        force: bool = False,
        progress: ProgressCallback | None = None,
        migrate: bool = True,
    ) -> dict[str, Any]:
        manifest = self.load_manifest(manifest_name, manifest_path)
        return self.ensure_manifest(manifest, force=force, progress=progress, migrate=migrate)

    def ensure_manifest(
        self,
        manifest: AssetManifest,
        *,
        force: bool = False,
        progress: ProgressCallback | None = None,
        migrate: bool = True,
    ) -> dict[str, Any]:
        downloadable = [entry for entry in manifest.files if entry.downloadable]
        if not downloadable:
            return self._status_for_manifest(manifest)

        total = len(downloadable)
        if migrate:
            self._migrate_vsr_if_available(manifest, progress)

        for index, entry in enumerate(downloadable, start=1):
            dest = self._entry_path(manifest, entry)
            self._notify(progress, manifest, entry, index, total, "checking")
            if force or not dest.exists() or _sha256_file(dest) != entry.sha256.lower():
                self._notify(progress, manifest, entry, index, total, "downloading")
                try:
                    _download(entry.url, dest)
                except Exception as exc:  # noqa: BLE001 - report in status/progress
                    self._notify(
                        progress,
                        manifest,
                        entry,
                        index,
                        total,
                        "error",
                        error=str(exc),
                    )
                    continue
            self._notify(progress, manifest, entry, index, total, "verifying")
            digest = _sha256_file(dest)
            if digest != entry.sha256.lower():
                self._notify(
                    progress,
                    manifest,
                    entry,
                    index,
                    total,
                    "sha256_mismatch",
                    sha256=digest,
                )
                continue
            self._notify(progress, manifest, entry, index, total, "verified", sha256=digest)

        return self._status_for_manifest(manifest)

    def clear(self, manifest_name: str, manifest_path: Path | None = None) -> dict[str, Any]:
        manifest = self.load_manifest(manifest_name, manifest_path)
        target = self.root / manifest.name
        if target.exists():
            shutil.rmtree(target)
        return self._status_for_manifest(manifest)

    def _status_for_manifest(self, manifest: AssetManifest) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        status: CacheStatus = "present"
        size_bytes = 0
        downloadable = [entry for entry in manifest.files if entry.downloadable]
        if not downloadable:
            status = "unsupported"

        for entry in manifest.files:
            path = self._entry_path(manifest, entry)
            exists = path.is_file()
            digest: str | None = None
            entry_status: CacheStatus = "unsupported" if not entry.downloadable else "missing"
            entry_size = path.stat().st_size if exists else 0
            size_bytes += entry_size
            if entry.downloadable and exists:
                digest = _sha256_file(path)
                entry_status = "present" if digest == entry.sha256.lower() else "corrupt"
            if entry_status == "missing" and status != "corrupt":
                status = "missing"
            if entry_status == "corrupt":
                status = "corrupt"
            entries.append(
                {
                    "name": entry.name,
                    "kind": entry.kind,
                    "relative_path": entry.relative_path,
                    "path": str(path),
                    "status": entry_status,
                    "size_bytes": entry_size,
                    "sha256": digest,
                    "expected_sha256": entry.sha256,
                }
            )

        return {
            "manifest": manifest.name,
            "kind": manifest.kind,
            "description": manifest.description,
            "status": status,
            "root": str(self.root / manifest.name),
            "size_bytes": size_bytes,
            "entries": entries,
            "migration_candidate": self._migration_candidate(manifest),
        }

    def _entry_path(self, manifest: AssetManifest, entry: AssetEntry) -> Path:
        return self.root / manifest.name / entry.relative_path

    def _migration_candidate(self, manifest: AssetManifest) -> str | None:
        if manifest.name != "vsr":
            return None
        candidate = repo_root() / "data" / "models" / "vsr"
        return str(candidate) if candidate.exists() else None

    def _migrate_vsr_if_available(
        self,
        manifest: AssetManifest,
        progress: ProgressCallback | None,
    ) -> None:
        candidate = self._migration_candidate(manifest)
        if not candidate:
            return
        source_root = Path(candidate)
        for index, entry in enumerate(manifest.files, start=1):
            source = source_root / entry.relative_path
            dest = self._entry_path(manifest, entry)
            if not source.is_file() or dest.exists():
                continue
            if entry.sha256 and _sha256_file(source) != entry.sha256.lower():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            self._notify(progress, manifest, entry, index, len(manifest.files), "migrated")

    def _notify(
        self,
        progress: ProgressCallback | None,
        manifest: AssetManifest,
        entry: AssetEntry,
        index: int,
        total: int,
        status: str,
        **extra: Any,
    ) -> None:
        if progress is None:
            return
        progress(
            {
                "manifest": manifest.name,
                "name": entry.name,
                "index": index,
                "total": total,
                "status": status,
                **extra,
            }
        )
