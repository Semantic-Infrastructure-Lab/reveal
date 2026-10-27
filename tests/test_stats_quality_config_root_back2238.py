"""BACK-2238: `.reveal/stats-quality.yaml` at the project root applies to a scan of a subdirectory.

`metrics://.` applied the root config while `metrics://src` and `metrics://src/a.py` ignored it, so
one project scored differently depending on where you pointed. The config is looked up from the
scanned directory first (a nearer file wins), then the project root, then the user's own file.
"""
import copy

import pytest

from reveal.adapters.stats.adapter import StatsAdapter
from reveal.adapters.stats.queries import QUALITY_DEFAULTS, get_quality_config

pytestmark = pytest.mark.component

_TIGHT = 'thresholds:\n  complexity_target: 1\n'
_LOOSE = 'thresholds:\n  complexity_target: 99\n'


def _config(directory, text):
    cfg = directory / '.reveal' / 'stats-quality.yaml'
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(text, encoding='utf-8')


def _user_config(home, text):
    cfg = home / '.config' / 'reveal' / 'stats-quality.yaml'
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(text, encoding='utf-8')


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project root (a .git marker) with src/pkg below it, and an empty home."""
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setattr('pathlib.Path.home', classmethod(lambda cls: home))
    root = tmp_path / 'proj'
    (root / '.git').mkdir(parents=True)
    (root / 'src' / 'pkg').mkdir(parents=True)
    return root


def _complexity_target(path):
    return get_quality_config(path)['thresholds']['complexity_target']


def test_root_config_applies_to_a_subdirectory(project):
    _config(project, _TIGHT)
    assert _complexity_target(project / 'src') == 1
    assert _complexity_target(project / 'src' / 'pkg') == 1


def test_root_config_applies_to_a_file_in_a_subdirectory(project):
    _config(project, _TIGHT)
    target = project / 'src' / 'pkg' / 'a.py'
    target.write_text('x = 1\n', encoding='utf-8')
    assert _complexity_target(target) == 1


def test_the_nearer_config_wins_and_is_not_merged(project):
    _config(project, _TIGHT)
    _config(project / 'src', _LOOSE)
    assert _complexity_target(project / 'src') == 99
    assert _complexity_target(project / 'src' / 'pkg') == 99, 'nearest ancestor, not only the scanned dir'
    assert _complexity_target(project) == 1


def test_the_project_config_beats_the_user_config(project, tmp_path):
    _user_config(tmp_path / 'home', _LOOSE)
    _config(project, _TIGHT)
    assert _complexity_target(project / 'src') == 1


def test_the_user_config_is_the_fallback(project, tmp_path):
    _user_config(tmp_path / 'home', _LOOSE)
    assert _complexity_target(project / 'src') == 99


def test_no_config_anywhere_is_the_defaults(project):
    assert get_quality_config(project / 'src') == QUALITY_DEFAULTS


def test_a_malformed_root_config_is_named_not_skipped(project, caplog):
    _config(project, 'thresholds: [unclosed\n')
    with caplog.at_level('WARNING', logger='reveal.adapters.stats.queries'):
        assert get_quality_config(project / 'src') == QUALITY_DEFAULTS
    assert 'stats-quality.yaml ignored, quality scores use the defaults' in caplog.text


def test_the_defaults_are_not_mutated_by_a_loaded_config(project):
    before = copy.deepcopy(QUALITY_DEFAULTS)
    _config(project, _TIGHT)
    _complexity_target(project / 'src')
    assert QUALITY_DEFAULTS == before


_BRANCHY = 'def f(a):\n' + ''.join(f'    if a == {i}:\n        return {i}\n' for i in range(8)) + '    return 0\n'


def test_a_scan_of_the_subdirectory_scores_like_a_scan_of_the_root(project):
    """The review's repro: the same file scored 99.5 or 90.4 depending on the path given."""
    (project / 'src' / 'a.py').write_text(_BRANCHY, encoding='utf-8')
    _config(project, 'thresholds:\n  complexity_target: 0\npenalties:\n  complexity:\n    multiplier: 30\n    max: 90\n')

    from_src = StatsAdapter(str(project / 'src')).get_element('a.py')['quality']['score']
    from_root = StatsAdapter(str(project)).get_element('src/a.py')['quality']['score']
    assert from_src == from_root < 100


def test_the_schema_note_defines_complexity_as_cyclomatic():
    """help://schemas/metrics called it 'average functions per 100 lines'; the number is the
    tree-sitter analyzer's per-function cyclomatic complexity (reveal/adapters/stats/metrics.py)."""
    notes = ' '.join(StatsAdapter.get_schema()['notes'])
    assert 'per 100 lines' not in notes
    assert 'Complexity is cyclomatic' in notes
