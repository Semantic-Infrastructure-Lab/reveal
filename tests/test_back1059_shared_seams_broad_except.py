"""BACK-1059 slice M: the shared seams catch what their body can raise, not every Exception.

For each narrowed handler: the expected failure still takes the old path (control), and an
unexpected exception type (a bug, injected here as _Bug) propagates instead of being logged
and read as a clean fallback.
"""
import subprocess
from types import SimpleNamespace

import pytest
import yaml

from reveal import config as cfg
from reveal.core import disk_cache
from reveal.cli.routing import uri as uri_mod
from reveal.display import element as element_mod
from reveal.utils import parallel


class _Bug(Exception):
    """Stands in for an unexpected exception: not OSError, ValueError, YAMLError."""


def _raise_bug(*_a, **_k):
    raise _Bug("injected")


@pytest.fixture(autouse=True)
def _fresh_build_fingerprint():
    """build_fingerprint is memoised per process; do not let a failing one disable the cache for later tests."""
    disk_cache.build_fingerprint.cache_clear()
    yield
    disk_cache.build_fingerprint.cache_clear()


# -- config ----------------------------------------------------------------------------

def test_yaml_loader_still_turns_bad_yaml_into_none(tmp_path):
    bad = tmp_path / "c.yaml"
    bad.write_text("a: [unclosed", encoding="utf-8")
    assert cfg._try_load_yaml_file(bad) is None


def test_yaml_loader_does_not_swallow_a_bug(tmp_path, monkeypatch):
    ok = tmp_path / "c.yaml"
    ok.write_text("a: 1", encoding="utf-8")
    monkeypatch.setattr(cfg.yaml, "safe_load", _raise_bug)
    with pytest.raises(_Bug):
        cfg._try_load_yaml_file(ok)


def test_config_load_file_still_turns_bad_yaml_into_none(tmp_path):
    bad = tmp_path / "c.yaml"
    bad.write_text("a: [unclosed", encoding="utf-8")
    assert cfg.RevealConfig._load_file(bad) is None


def test_config_load_file_does_not_swallow_a_bug(tmp_path, monkeypatch):
    ok = tmp_path / "c.yaml"
    ok.write_text("a: 1", encoding="utf-8")
    monkeypatch.setattr(cfg.RevealConfig, "_validate_config_schema", classmethod(_raise_bug))
    with pytest.raises(_Bug):
        cfg.RevealConfig._load_file(ok)


@pytest.mark.skipif(cfg.tomllib is None, reason="no TOML reader")
def test_pyproject_loader_still_turns_bad_toml_into_none(tmp_path):
    bad = tmp_path / "pyproject.toml"
    bad.write_text("[tool.reveal\n", encoding="utf-8")
    assert cfg.RevealConfig._try_load_pyproject_reveal(bad) is None


@pytest.mark.skipif(cfg.tomllib is None, reason="no TOML reader")
def test_pyproject_loader_does_not_swallow_a_bug(tmp_path, monkeypatch):
    ok = tmp_path / "pyproject.toml"
    ok.write_text("[tool.reveal]\nx = 1\n", encoding="utf-8")
    monkeypatch.setattr(cfg.tomllib, "load", _raise_bug)
    with pytest.raises(_Bug):
        cfg.RevealConfig._try_load_pyproject_reveal(ok)


def test_write_user_config_reports_an_unwritable_path(tmp_path, monkeypatch, capsys):
    target = tmp_path / "dir_not_file"
    target.mkdir()
    monkeypatch.setattr(cfg.RevealConfig, "_get_user_config_path", staticmethod(lambda: target))
    assert cfg._write_user_config({"a": 1}, "ok") is False
    assert "Failed to update config" in capsys.readouterr().err


def test_write_user_config_does_not_swallow_a_bug(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.RevealConfig, "_get_user_config_path",
                        staticmethod(lambda: tmp_path / "c.yaml"))
    monkeypatch.setattr(cfg.yaml, "dump", _raise_bug)
    with pytest.raises(_Bug):
        cfg._write_user_config({"a": 1}, "ok")


# -- disk cache ------------------------------------------------------------------------

def test_build_fingerprint_fails_open_on_oserror(monkeypatch):
    monkeypatch.setattr(disk_cache, "_package_files", lambda *_a: (_ for _ in ()).throw(OSError("x")))
    assert disk_cache.build_fingerprint() is None


def test_build_fingerprint_does_not_swallow_a_bug(monkeypatch):
    monkeypatch.setattr(disk_cache, "_package_files", _raise_bug)
    with pytest.raises(_Bug):
        disk_cache.build_fingerprint()


def test_prune_ignores_a_vanished_dir(tmp_path):
    disk_cache._prune(tmp_path / "gone", 1)  # OSError from scandir: housekeeping, no raise


def test_prune_does_not_swallow_a_bug(tmp_path, monkeypatch):
    monkeypatch.setattr(disk_cache.os, "scandir", _raise_bug)
    with pytest.raises(_Bug):
        disk_cache._prune(tmp_path, 1)


def test_prune_builds_ignores_a_vanished_dir(tmp_path):
    disk_cache._prune_builds(tmp_path / "gone" / "current")


def test_prune_builds_does_not_swallow_a_bug(tmp_path, monkeypatch):
    (tmp_path / "current").mkdir()
    monkeypatch.setattr(disk_cache.Path, "iterdir", _raise_bug)
    with pytest.raises(_Bug):
        disk_cache._prune_builds(tmp_path / "current")


# -- uri frontmatter -------------------------------------------------------------------

def test_frontmatter_bad_yaml_is_still_a_value_error():
    with pytest.raises(ValueError, match="failed to parse as YAML"):
        uri_mod._parse_text_frontmatter("---\na: [unclosed\n---\nbody\n")


def test_frontmatter_does_not_relabel_a_bug_as_bad_yaml(monkeypatch):
    monkeypatch.setattr(yaml, "safe_load", _raise_bug)
    with pytest.raises(_Bug):
        uri_mod._parse_text_frontmatter("---\na: 1\n---\nbody\n")


# -- display/element -------------------------------------------------------------------

def test_read_lines_unreadable_is_none_with_a_warning(tmp_path, capsys):
    assert element_mod._read_lines(tmp_path / "missing.py", 1, 2) is None
    assert "could not read lines" in capsys.readouterr().err


def test_read_lines_does_not_swallow_a_bug(tmp_path, monkeypatch):
    f = tmp_path / "a.py"
    f.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr("builtins.open", _raise_bug)
    with pytest.raises(_Bug):
        element_mod._read_lines(f, 1, 1)


def test_extract_line_range_unreadable_is_none_with_a_warning(tmp_path, capsys):
    analyzer = SimpleNamespace(path=tmp_path / "missing.py")
    assert element_mod._extract_line_range(analyzer, 1, 2) is None
    assert "could not extract lines" in capsys.readouterr().err


def test_extract_line_range_does_not_swallow_a_bug(tmp_path, monkeypatch):
    f = tmp_path / "a.py"
    f.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr("builtins.open", _raise_bug)
    with pytest.raises(_Bug):
        element_mod._extract_line_range(SimpleNamespace(path=f), 1, 1)


# -- parallel grep worker --------------------------------------------------------------

def test_scan_one_unreadable_file_is_a_non_match(tmp_path):
    assert parallel._scan_one((tmp_path / "missing.txt", (b"x",))) is None


def test_scan_one_does_not_swallow_a_bug(tmp_path, monkeypatch):
    f = tmp_path / "a.txt"
    f.write_bytes(b"x")
    monkeypatch.setattr("builtins.open", _raise_bug)
    with pytest.raises(_Bug):
        parallel._scan_one((f, (b"x",)))


# -- main @file ------------------------------------------------------------------------

def test_at_file_unreadable_exits_1(tmp_path, capsys):
    from reveal import main as main_mod
    d = tmp_path / "list.txt"
    d.mkdir()  # exists, but open() raises IsADirectoryError
    with pytest.raises(SystemExit) as exc:
        main_mod._handle_at_file(str(d), SimpleNamespace())
    assert exc.value.code == 1
    assert "Error reading" in capsys.readouterr().err


def test_at_file_does_not_swallow_a_bug(tmp_path, monkeypatch):
    from reveal import main as main_mod
    f = tmp_path / "list.txt"
    f.write_text("a.py\n", encoding="utf-8")
    monkeypatch.setattr("builtins.open", _raise_bug)
    with pytest.raises(_Bug):
        main_mod._handle_at_file(str(f), SimpleNamespace())


# -- review changed files --------------------------------------------------------------

def test_changed_files_git_missing_is_empty_with_a_warning(monkeypatch, capsys):
    from reveal.cli.commands import review
    monkeypatch.setattr(review.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("git")))
    assert review._changed_files("a..b") == []
    assert "could not determine changed files" in capsys.readouterr().err


def test_changed_files_timeout_is_empty_with_a_warning(monkeypatch, capsys):
    from reveal.cli.commands import review

    def slow(*a, **k):
        raise subprocess.TimeoutExpired("git", 10)
    monkeypatch.setattr(review.subprocess, "run", slow)
    assert review._changed_files("a..b") == []


def test_changed_files_does_not_swallow_a_bug(monkeypatch):
    from reveal.cli.commands import review
    monkeypatch.setattr(review.subprocess, "run", _raise_bug)
    with pytest.raises(_Bug):
        review._changed_files("a..b")
