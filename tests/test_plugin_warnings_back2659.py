"""A user or project plugin that did not load as written is in the answer (BACK-2659, step 3b).

An analyzer plugin (``.reveal/analyzers/*_analyzer.py``), an adapter plugin (``.reveal/adapters/<pkg>/``)
or a rule module (``.reveal/rules/<category>/<CODE>.py``) that raised on import, a rule module without
its rule class, a rule with an unknown severity and the legacy rules directory were ``logger`` lines on
stderr only (a rule import failure with a full traceback): the JSON answer, the library API and MCP's
JSON said nothing, and ``check`` reported a complete run. Each is now a ``plugin_warning`` entry in
``meta.warnings``, informational (exit and completeness unchanged), with nothing on stderr in JSON mode.
Plugins load once per process, so every later discovery call replays what the load met: an MCP server
reports it on every request, not only the first.
"""
import json
import logging
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from reveal.utils.invocation_log import log_scope

GOOD = 'def ok():\n    return 1\n'
SEVERITY_RULE = '''from reveal.rules.base import BaseRule


class X003(BaseRule):
    code = "X003"
    message = "demo"
    severity = "urgent"
    category = "X"
    file_patterns = ["*.py"]

    def check(self, file_path, structure, content):
        return []
'''


def _project(root, plugins=True):
    root.mkdir(parents=True)
    (root / 'ok.py').write_text(GOOD, encoding='utf-8')
    (root / '.reveal.yaml').write_text('root: true\n', encoding='utf-8')
    if plugins:
        rules = root / '.reveal' / 'rules' / 'custom'
        rules.mkdir(parents=True)
        (rules / 'X001.py').write_text('raise RuntimeError("boom in rule")\n', encoding='utf-8')
        (rules / 'X002.py').write_text('x = 1\n', encoding='utf-8')
        (rules / 'X003.py').write_text(SEVERITY_RULE, encoding='utf-8')
        analyzers = root / '.reveal' / 'analyzers'
        analyzers.mkdir(parents=True)
        (analyzers / 'bad_analyzer.py').write_text('raise ImportError("boom in analyzer")\n', encoding='utf-8')
        adapter = root / '.reveal' / 'adapters' / 'badadp'
        adapter.mkdir(parents=True)
        (adapter / '__init__.py').write_text('raise ValueError("boom in adapter")\n', encoding='utf-8')
    return root


def _cli(root, *argv):
    """The real process, cwd at the project (plugins are discovered from the cwd)."""
    env = {key: value for key, value in os.environ.items() if not key.startswith('REVEAL_')}
    env.update(REVEAL_DISK_CACHE='0', XDG_CONFIG_HOME=str(root.parent / 'xdg-config'),
               XDG_DATA_HOME=str(root.parent / 'xdg-data'))
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], capture_output=True, text=True,
                          encoding='utf-8', env=env, cwd=root, timeout=180)


def _plugin_warnings(document, root):
    """This project's entries (a developer's own ~/.reveal plugins never take part)."""
    return [w for w in document['meta']['warnings']
            if w.get('type') == 'plugin_warning' and str(w.get('path', root.as_posix())).startswith(root.as_posix())]


STDERR_LINES = ('Plugin load failed', 'Adapter plugin load failed', 'Failed to import rule', 'Traceback',
                'does not contain a valid rule class', 'unknown severity')


@pytest.mark.cli
def test_check_json_carries_every_plugin_problem_and_stderr_is_empty(tmp_path):
    control = _cli(_project(tmp_path / 'clean', plugins=False), 'check', '.', '--format', 'json')
    root = _project(tmp_path / 'proj')
    result = _cli(root, 'check', '.', '--format', 'json')
    assert result.returncode == control.returncode == 0, result.stderr
    entries = _plugin_warnings(json.loads(result.stdout), root)
    found = sorted((w['code'], w.get('kind') or w.get('rule')) for w in entries)
    assert found == [('plugin_load_failed', 'adapter'), ('plugin_load_failed', 'analyzer'),
                     ('plugin_load_failed', 'rule'), ('rule_class_missing', 'X002'),
                     ('rule_severity_unknown', 'X003')], entries
    failed = {w['kind']: w for w in entries if w['code'] == 'plugin_load_failed'}
    assert failed['rule']['path'] == (root / '.reveal' / 'rules' / 'custom' / 'X001.py').as_posix()
    assert failed['rule']['reason'] == 'RuntimeError: boom in rule'
    assert failed['analyzer']['reason'] == 'ImportError: boom in analyzer'
    assert not [line for line in STDERR_LINES if line in result.stderr], result.stderr


@pytest.mark.cli
def test_ast_json_carries_the_plugin_load_failures(tmp_path):
    root = _project(tmp_path / 'proj')
    result = _cli(root, 'ast://.', '--format', 'json')
    assert result.returncode == 0, result.stderr
    kinds = sorted(w['kind'] for w in _plugin_warnings(json.loads(result.stdout), root)
                   if w['code'] == 'plugin_load_failed')
    assert kinds == ['adapter', 'analyzer']
    assert 'load failed' not in result.stderr, result.stderr


@pytest.mark.cli
def test_text_answer_says_each_once_after_the_answer_without_a_traceback(tmp_path):
    root = _project(tmp_path / 'proj')
    result = _cli(root, 'check', '.')
    assert 'Traceback' not in result.stderr
    lines = [line for line in result.stderr.splitlines() if 'X001.py' in line]
    assert len(lines) == 1 and lines[0].startswith('warning: '), result.stderr


@pytest.mark.cli
def test_no_plugins_no_plugin_warning(tmp_path):
    """The unaffected sibling: a project without plugin directories answers exactly as before."""
    root = _project(tmp_path / 'proj', plugins=False)
    result = _cli(root, 'check', '.', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert _plugin_warnings(json.loads(result.stdout), root) == []
    assert result.stderr == ''


@pytest.fixture
def fresh_plugins():
    from reveal.adapters.registry import _reset_adapter_plugin_discovery
    from reveal.registry import _reset_plugin_discovery
    _reset_plugin_discovery()
    _reset_adapter_plugin_discovery()
    yield
    _reset_plugin_discovery()
    _reset_adapter_plugin_discovery()


@pytest.mark.mcp
def test_mcp_reports_the_plugin_on_every_request_not_only_the_first(tmp_path, monkeypatch, fresh_plugins):
    from reveal import mcp_server
    root = _project(tmp_path / 'proj')
    monkeypatch.chdir(root)
    for _ in range(2):
        text = mcp_server.reveal_query(f'ast://{root.as_posix()}', provenance=True)
        assert getattr(text, 'stderr', '') == ''
        kinds = sorted(w['kind'] for w in _plugin_warnings(json.loads(text), root)
                       if w['code'] == 'plugin_load_failed')
        assert kinds == ['adapter', 'analyzer']


def test_legacy_rules_directory_is_recorded_not_logged(tmp_path, caplog):
    from reveal.rules import RuleRegistry
    legacy = tmp_path / 'legacy-rules'
    legacy.mkdir()
    config = SimpleNamespace(user_data_dir=tmp_path / 'data', get_legacy_paths=lambda: {'rules_user': legacy})
    with caplog.at_level(logging.WARNING), log_scope(to_stderr=False) as log:
        RuleRegistry._discover_user_rules(config)
    (entry,) = log.warnings.values()
    assert (entry['type'], entry['code'], entry['path']) == ('plugin_warning', 'rules_dir_legacy', legacy.as_posix())
    assert entry['replacement'] == (tmp_path / 'data' / 'rules').as_posix()
    assert caplog.records == []


def test_outside_an_invocation_a_failed_plugin_is_still_logged(tmp_path, monkeypatch, caplog, fresh_plugins):
    """A plain library call has no answer to carry the fact: it is logged, as before."""
    from reveal.registry import discover_plugins
    root = _project(tmp_path / 'proj')
    with caplog.at_level(logging.WARNING, logger='reveal.registry'):
        discover_plugins(root)
    assert 'bad_analyzer.py' in caplog.text
