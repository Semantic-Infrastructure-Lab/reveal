"""Go, Rust and Ruby find their module root through one bounded climb (BACK-1054 note 3).

Each had its own loop up to the filesystem root, so a stray ``~/go.mod`` (or a
``Cargo.toml``/``Gemfile.lock`` anywhere above the project) became the module root of every
file below it. They now share ``imports.base.nearest_marker_dir``, which stops at
``search_parents_within_ceiling``'s ceiling: ``$HOME``, the temp dir, a filesystem boundary.
"""

import pytest

from reveal.analyzers.imports.generic import _find_ruby_project_root
from reveal.analyzers.imports.go import GoExtractor
from reveal.analyzers.imports.rust import RustExtractor

# BACK-1149: in-process resolver helpers
pytestmark = pytest.mark.component

FINDERS = [
    ('go.mod', lambda start: GoExtractor()._find_go_module_root(start)),
    ('Cargo.toml', lambda start: RustExtractor()._find_cargo_root(start)),
    ('Gemfile.lock', _find_ruby_project_root),
]


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    (home / 'proj' / 'pkg').mkdir(parents=True)
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    return home


@pytest.mark.parametrize('marker,find', FINDERS, ids=[m for m, _ in FINDERS])
def test_the_projects_own_marker_is_found(home, marker, find):
    (home / 'proj' / marker).write_text('', encoding='utf-8')
    assert find(home / 'proj' / 'pkg') == (home / 'proj').resolve()


@pytest.mark.parametrize('marker,find', FINDERS, ids=[m for m, _ in FINDERS])
def test_a_marker_in_home_is_not_the_module_root(home, marker, find):
    (home / marker).write_text('', encoding='utf-8')
    assert find(home / 'proj' / 'pkg') is None
