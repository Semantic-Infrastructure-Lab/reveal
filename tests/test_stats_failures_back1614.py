"""BACK-1614: stats:// says which files it could not analyze.

A file whose analysis raised used to be returned as None, the same value an
unsupported file gets, so the totals silently left it out and read as the whole
tree; a single file that failed reported 0 files and exit 0; a malformed
stats-quality.yaml was ignored without a word.
"""

import logging

import pytest

from reveal.adapters.stats import adapter as stats_adapter, metrics
from reveal.adapters.stats.adapter import StatsAdapter
from reveal.adapters.stats.queries import QUALITY_DEFAULTS, get_quality_config
from reveal.adapters.stats.renderer import StatsRenderer
from reveal.utils.results import outcome_of


@pytest.fixture
def broken_on_bad_py(monkeypatch):
    real = metrics.calculate_file_stats

    def _calc(file_path, *args, **kwargs):
        if file_path.name == 'bad.py':
            raise RuntimeError('analyzer bug')
        return real(file_path, *args, **kwargs)

    monkeypatch.setattr(metrics, 'calculate_file_stats', _calc)  # the worker's import
    monkeypatch.setattr(stats_adapter, 'calculate_file_stats', _calc)  # single file, element


def test_directory_scan_discloses_the_failed_file(tmp_path, broken_on_bad_py, capsys):
    (tmp_path / 'good.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'bad.py').write_text('def g():\n    return 2\n', encoding='utf-8')
    result = StatsAdapter(str(tmp_path)).get_structure()
    assert result['summary']['total_files'] == 1
    warning, = [w for w in result['meta']['warnings'] if w['type'] == 'analysis_failed']
    assert warning['count'] == 1 and warning['files'] == ['bad.py']
    StatsRenderer.render_structure(result, 'text')
    assert '⚠ 1 file(s) failed analysis and are not counted: bad.py' in capsys.readouterr().out


def test_clean_scan_has_no_failure_warning(tmp_path):
    (tmp_path / 'good.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    result = StatsAdapter(str(tmp_path)).get_structure()
    assert not [w for w in (result.get('meta') or {}).get('warnings', [])
                if w['type'] == 'analysis_failed']


def test_single_file_failure_is_a_failed_result(tmp_path, broken_on_bad_py):
    bad = tmp_path / 'bad.py'
    bad.write_text('def g():\n    return 2\n', encoding='utf-8')
    result = StatsAdapter(str(bad)).get_structure()
    assert outcome_of(result) == 'failed'
    assert 'analysis failed: RuntimeError: analyzer bug' in result['error']


def test_element_failure_is_a_failed_result(tmp_path, broken_on_bad_py):
    (tmp_path / 'bad.py').write_text('def g():\n    return 2\n', encoding='utf-8')
    result = StatsAdapter(str(tmp_path)).get_element('bad.py')
    assert result == {'error': 'bad.py: analysis failed: RuntimeError: analyzer bug'}


def test_malformed_quality_config_is_named(tmp_path, caplog):
    cfg = tmp_path / '.reveal' / 'stats-quality.yaml'
    cfg.parent.mkdir()
    cfg.write_text('thresholds: [unclosed\n', encoding='utf-8')
    with caplog.at_level(logging.WARNING, logger='reveal.adapters.stats.queries'):
        config = get_quality_config(tmp_path)
    assert config == QUALITY_DEFAULTS
    assert 'stats-quality.yaml ignored, quality scores use the defaults' in caplog.text
