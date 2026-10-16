"""resolve_project_root climbs once for its three marker searches (BACK-1878)."""

import subprocess

from reveal.utils import path_utils
from reveal.utils.path_utils import (
    _SharedClimb, _has_package_marker, _has_vcs_marker,
    resolve_project_root, search_parents_within_ceiling,
)


def _tree(tmp_path):
    root = tmp_path / "repo"
    deep = root / "pkg" / "sub" / "leaf"
    deep.mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "pkg" / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (deep / "m.py").write_text("x = 1\n", encoding="utf-8")
    return root, deep


def test_first_matches_search_parents_within_ceiling(tmp_path):
    root, deep = _tree(tmp_path)
    climb = _SharedClimb(deep / "m.py")
    for cond in (_has_vcs_marker, _has_package_marker, lambda p: False):
        assert climb.first(cond) == search_parents_within_ceiling(deep / "m.py", cond)
    assert climb.first(_has_vcs_marker) == root
    assert climb.first(_has_package_marker) == root / "pkg"


def test_ceiling_is_checked_once_per_level(tmp_path, monkeypatch):
    _root, deep = _tree(tmp_path)
    checked = []
    real = path_utils.is_unsafe_scan_root
    monkeypatch.setattr(path_utils, "is_unsafe_scan_root",
                        lambda p: checked.append(p) or real(p))
    # no reveal-root, a VCS root two levels up, a package marker one level up: all
    # three searches run, but each ancestor is ceiling-checked only once
    assert resolve_project_root(deep / "m.py") == root_of(deep)
    assert len(checked) == len(set(checked))


def root_of(deep):
    return deep.parent.parent  # pkg/, the nearest package marker inside the repo


def test_unsafe_roots_memoized_but_follow_patched_inputs(tmp_path, monkeypatch):
    first = path_utils._unsafe_scan_roots()
    assert path_utils._unsafe_scan_roots() is first
    monkeypatch.setattr(path_utils.tempfile, "gettempdir", lambda: str(tmp_path))
    import os
    assert os.path.realpath(str(tmp_path)) in path_utils._unsafe_scan_roots()


def test_climb_stops_at_the_unsafe_ceiling(tmp_path, monkeypatch):
    root, deep = _tree(tmp_path)
    import os
    monkeypatch.setattr(path_utils, "_unsafe_scan_roots",
                        lambda: frozenset({os.path.realpath(str(root / "pkg"))}))
    # the ceiling is pkg/: nothing at or above it may be returned
    assert resolve_project_root(deep / "m.py") is None
    assert _SharedClimb(deep / "m.py").first(_has_vcs_marker) is None
