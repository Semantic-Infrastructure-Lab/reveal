"""The config readers that fall back to defaults say so in the answer (BACK-2659, step 3).

``metrics``' quality-score file (``.reveal/stats-quality.yaml``), its hotspot thresholds, a rule's
settings, the import layers and ``health --all``'s ``health.targets`` each caught a config problem,
used defaults, and said so only in a ``logger.warning`` on stderr. Each is now a ``config_warning``
entry through the invocation's log, like the config loader's own problems: in ``meta.warnings`` of
a JSON answer and nothing on stderr beside it. ``health.targets`` was also unknown to the config
schema, so the documented key itself drew a warning; the schema now owns its shape.
"""
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from reveal.utils.invocation_log import log_scope

GOOD = 'def ok():\n    return 1\n'


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'ok.py').write_text(GOOD, encoding='utf-8')
    (root / '.reveal.yaml').write_text('root: true\n', encoding='utf-8')
    (tmp_path / 'xdg').mkdir()
    return root


def _cli(root, *argv, cwd=None):
    env = {key: value for key, value in os.environ.items() if not key.startswith('REVEAL_')}
    env.update(REVEAL_DISK_CACHE='0', XDG_CONFIG_HOME=str(root.parent / 'xdg'))
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], capture_output=True, text=True,
                          encoding='utf-8', env=env, cwd=cwd or root.parent, timeout=180)


def _config_warnings(document):
    return [w for w in document['meta']['warnings'] if w.get('type') == 'config_warning']


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


# --- health.targets: the schema owns its shape --------------------------------------------------

@pytest.mark.cli
def test_documented_health_targets_draw_no_config_warning(project):
    _write(project / '.reveal.yaml', 'root: true\nhealth:\n  targets:\n    - src\n')
    result = _cli(project, f'ast://{project.as_posix()}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert _config_warnings(json.loads(result.stdout)) == []
    assert result.stderr == ''


@pytest.mark.cli
@pytest.mark.parametrize('section,key', [('health:\n  targets: 5\n', 'health.targets'), ('health: 5\n', 'health')],
                         ids=['targets-not-a-list', 'health-not-a-mapping'])
def test_health_targets_of_the_wrong_shape_fall_back_in_the_json(project, section, key):
    control = _cli(project, 'health', '--all', '--format', 'json', cwd=project)
    _write(project / '.reveal.yaml', 'root: true\n' + section)
    result = _cli(project, 'health', '--all', '--format', 'json', cwd=project)
    assert result.returncode == control.returncode, result.stderr
    entries = _config_warnings(json.loads(result.stdout))
    assert [(w['code'], w['key']) for w in entries] == [('config_schema_invalid', key)]
    assert 'health.targets ignored' not in result.stderr, result.stderr


@pytest.mark.cli
def test_a_config_warning_does_not_make_health_report_an_incomplete_check(project):
    """A config warning is informational (exit and completeness unchanged). health judged any
    warning in its child check's JSON as lost evidence: once config problems reached that JSON,
    an unknown rule setting turned ``code: healthy`` (exit 0) into ``incomplete check`` (exit 3)."""
    control = _cli(project, 'health', project.as_posix(), '--format', 'json')
    _write(project / '.reveal.yaml', 'root: true\nrules:\n  C901:\n    bogus_key: 3\n')
    result = _cli(project, 'health', project.as_posix(), '--format', 'json')
    assert result.returncode == control.returncode == 0, result.stdout
    document = json.loads(result.stdout)
    assert [r['verdict'] for r in document['results']] == ['healthy']
    assert [w['code'] for w in _config_warnings(document)] == ['config_key_unknown']


# --- metrics' quality-score file ---------------------------------------------------------------

@pytest.mark.cli
def test_unloadable_quality_file_is_in_the_json_and_not_on_stderr(project):
    quality = project / '.reveal' / 'stats-quality.yaml'
    _write(quality, 'thresholds: [unclosed\n')
    result = _cli(project, f'metrics://{project.as_posix()}', '--format', 'json')
    entries = [w for w in _config_warnings(json.loads(result.stdout)) if w.get('path') == quality.as_posix()]
    assert [w['code'] for w in entries] == ['config_load_failed'], result.stdout
    assert 'while parsing' in entries[0]['reason'] and 'default' in entries[0]['message']
    assert 'quality scores use the defaults' not in result.stderr, result.stderr


@pytest.mark.cli
def test_valid_quality_file_draws_no_config_warning(project):
    """Control: a quality file that loads says nothing."""
    _write(project / '.reveal' / 'stats-quality.yaml', 'thresholds:\n  function_length: 40\n')
    result = _cli(project, f'metrics://{project.as_posix()}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert _config_warnings(json.loads(result.stdout)) == []
    assert result.stderr == ''


@pytest.mark.mcp
def test_mcp_json_carries_the_quality_file_warning_and_no_stderr(project):
    from reveal import mcp_server
    _write(project / '.reveal' / 'stats-quality.yaml', 'thresholds: [unclosed\n')
    text = mcp_server.reveal_query(f'metrics://{project.as_posix()}', provenance=True)
    assert getattr(text, 'stderr', '') == ''
    assert 'config_load_failed' in [w['code'] for w in _config_warnings(json.loads(text))]


# --- readers whose config failed to resolve (the loader no longer raises on any file it can
# read; KeyError('files') is what an override missing its pattern raised before BACK-2663) -------

def _broken_config(*_args, **_kwargs):
    raise KeyError('files')


def test_hotspot_thresholds_fallback_is_recorded_not_logged(project, monkeypatch, caplog):
    from reveal.adapters.stats import metrics
    from reveal.rules import RuleRegistry
    monkeypatch.setattr(RuleRegistry, 'get_configured_rule', classmethod(_broken_config))
    with caplog.at_level(logging.WARNING), log_scope(to_stderr=False) as log:
        assert metrics._get_check_thresholds(project / 'ok.py') == (100, 4)
    (entry,) = log.warnings.values()
    assert (entry['type'], entry['code']) == ('config_warning', 'config_load_failed')
    assert "KeyError: 'files'" in entry['message'] and project.as_posix() not in entry['message']
    assert caplog.records == []


def test_rule_settings_fallback_is_recorded_not_logged(monkeypatch, caplog):
    from reveal.config import RevealConfig
    from reveal.rules import RuleRegistry
    rule = RuleRegistry.get_rule('C901')()  # discovery reads the config too: before the break
    monkeypatch.setattr(RevealConfig, 'get', classmethod(_broken_config))
    with caplog.at_level(logging.WARNING), log_scope(to_stderr=False) as log:
        assert rule.get_threshold('threshold', 7) == 7
    (entry,) = log.warnings.values()
    assert (entry['code'], entry['rule']) == ('config_load_failed', 'C901')
    assert caplog.records == []


def test_layer_config_fallback_is_recorded_not_logged(project, monkeypatch, caplog):
    from reveal.analyzers.imports.layers import load_layer_config
    from reveal.config import RevealConfig
    monkeypatch.setattr(RevealConfig, 'get', classmethod(_broken_config))
    with caplog.at_level(logging.WARNING), log_scope(to_stderr=False) as log:
        assert load_layer_config(project).layers == []  # the direct read: a .reveal.yaml without layers
    (entry,) = log.warnings.values()
    assert entry['code'] == 'config_load_failed' and 'nearest .reveal.yaml' in entry['message']
    assert caplog.records == []


def test_outside_an_invocation_the_fallback_is_still_logged(project, monkeypatch, caplog):
    """A plain library call has no answer to carry the fact: it is logged, as before."""
    from reveal.adapters.stats import metrics
    from reveal.rules import RuleRegistry
    monkeypatch.setattr(RuleRegistry, 'get_configured_rule', classmethod(_broken_config))
    with caplog.at_level(logging.WARNING):
        metrics._get_check_thresholds(Path(project / 'ok.py'))
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
