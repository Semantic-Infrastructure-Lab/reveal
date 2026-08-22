"""Regression tests for reveal.version (BACK-1126).

reveal --version and --provenance's execution.reveal_version used to report
a DIFFERENT version depending on cwd: importlib.metadata.version("reveal-cli")
scans sys.path by name and returns the first match, and Python inserts cwd
into sys.path, so a stale dist-info left over from an old install elsewhere
on sys.path could silently win over the metadata for the code actually
running.
"""

from pathlib import Path

import pytest

from reveal.version import _resolve_version

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


def _write_egg_info(directory: Path, name: str, version: str) -> None:
    egg_info = directory / f"{name}.egg-info"
    egg_info.mkdir(parents=True)
    (egg_info / "PKG-INFO").write_text(
        f"Metadata-Version: 2.1\nName: reveal-cli\nVersion: {version}\n"
    )


def test_resolves_version_from_own_install_root(tmp_path, monkeypatch):
    """Version must come from the egg-info next to the running package,
    not from any other reveal-cli metadata that happens to be on sys.path."""
    package_dir = tmp_path / "reveal"
    package_dir.mkdir()
    _write_egg_info(tmp_path, "reveal_cli", "9.9.9")

    monkeypatch.setattr("reveal.version._PACKAGE_DIR", package_dir)
    assert _resolve_version() == "9.9.9"


def test_ignores_stale_distribution_elsewhere_on_sys_path(tmp_path, monkeypatch):
    """A same-named dist-info sitting elsewhere on sys.path (the actual
    BACK-1126 failure shape -- a leftover install from a prior version)
    must not shadow the one matching the running code."""
    package_dir = tmp_path / "real_install" / "reveal"
    package_dir.mkdir(parents=True)
    _write_egg_info(tmp_path / "real_install", "reveal_cli", "2.0.0")

    stale_dist_info = tmp_path / "stale_site_packages" / "reveal_cli-1.0.0.dist-info"
    stale_dist_info.mkdir(parents=True)
    (stale_dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: reveal-cli\nVersion: 1.0.0\n"
    )

    monkeypatch.setattr("reveal.version._PACKAGE_DIR", package_dir)
    monkeypatch.syspath_prepend(str(tmp_path / "stale_site_packages"))

    assert _resolve_version() == "2.0.0"


def test_falls_back_when_no_install_root_metadata_found(tmp_path, monkeypatch):
    """No egg-info/dist-info next to the package (e.g. a plain checkout
    with no metadata at all) -- must not raise, degrade gracefully."""
    package_dir = tmp_path / "reveal"
    package_dir.mkdir()

    monkeypatch.setattr("reveal.version._PACKAGE_DIR", package_dir)
    # No reveal-cli distribution anywhere -> old name-based lookup also
    # fails -> dev fallback string, not an exception.
    result = _resolve_version()
    assert isinstance(result, str) and result
