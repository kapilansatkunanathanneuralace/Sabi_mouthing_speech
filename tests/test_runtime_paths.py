from __future__ import annotations

from pathlib import Path

from sabi.runtime import paths


def test_repo_root_default_points_at_checkout() -> None:
    root = paths.repo_root()
    assert (root / "pyproject.toml").is_file()
    assert paths.configs_dir() == root / "configs"
    assert paths.vsr_manifest_path() == root / "configs" / "vsr_weights.toml"


def test_runtime_path_env_overrides(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("SABI_REPO_ROOT", "C:/tmp/sabi-repo")
    monkeypatch.setenv("SABI_APP_HOME", "C:/tmp/sabi-home")
    monkeypatch.setenv("SABI_CONFIG_DIR", "C:/tmp/sabi-config")
    monkeypatch.setenv("SABI_MODELS_DIR", "C:/tmp/sabi-models")
    monkeypatch.setenv("SABI_REPORTS_DIR", "C:/tmp/sabi-reports")
    monkeypatch.setenv("SABI_CHAPLIN_DIR", "C:/tmp/chaplin")
    monkeypatch.setenv("SABI_VSR_MANIFEST", "C:/tmp/vsr.toml")

    assert paths.repo_root() == Path("C:/tmp/sabi-repo")
    assert paths.app_home() == Path("C:/tmp/sabi-home")
    assert paths.configs_dir() == Path("C:/tmp/sabi-config")
    assert paths.models_dir() == Path("C:/tmp/sabi-models")
    assert paths.reports_dir() == Path("C:/tmp/sabi-reports")
    assert paths.chaplin_dir() == Path("C:/tmp/chaplin")
    assert paths.vsr_manifest_path() == Path("C:/tmp/vsr.toml")


def test_frozen_resource_paths(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    exe_dir = tmp_path / "dist" / "sabi-sidecar"
    resources = exe_dir / "resources"
    resources.mkdir(parents=True)
    exe = exe_dir / "sabi-sidecar.exe"
    exe.write_text("", encoding="utf-8")

    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(exe))

    assert paths.frozen_resource_root() == resources
    assert paths.configs_dir() == resources / "configs"
    assert paths.chaplin_dir() == resources / "third_party" / "chaplin"
    assert paths.reports_dir() == paths.app_home() / "reports"
