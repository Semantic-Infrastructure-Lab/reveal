"""BACK-2275: reveal://config and `reveal dev inspect-config` show the config that was merged.

Before: `reveal://config` listed no project config file (it kept a discovered config only
``if 'path' in cfg``, a key loaded YAML never has), listed REVEAL_* variables the loader never
reads (REVEAL_C905_MAX_DEPTH, REVEAL_M101_THRESHOLD, REVEAL_CONFIG_DEBUG) and left out ones it
does read (REVEAL_RULES_SELECT, REVEAL_IGNORE, REVEAL_FORMAT, REVEAL_BREADCRUMBS); the text view
dropped ``rules.select``. `reveal dev inspect-config` read attributes RevealConfig does not
define, so it always ended with "Using all default settings.".
"""

import ast
import io
import os
import re
from contextlib import redirect_stdout
from pathlib import Path

import pytest

import reveal.config as config_module
from reveal.config import RevealConfig

from conftest import _run_reveal_direct

_ALL_REVEAL_VARS = re.compile(r'^REVEAL_[A-Z0-9_]+$')


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """A project dir with no user/system/env config leaking in, and fresh config caches."""
    for name in list(os.environ):
        if name.startswith('REVEAL_') and name not in ('REVEAL_DISK_CACHE', 'REVEAL_MAX_WORKERS'):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    project = tmp_path / 'proj'
    project.mkdir()
    monkeypatch.chdir(project)
    RevealConfig.reset_request_cache()
    yield project
    RevealConfig.reset_request_cache()


def _write_project_config(project: Path) -> Path:
    cfg = project / '.reveal.yaml'
    cfg.write_text('root: true\nrules:\n  disable: [E501]\n  select: [E, C]\n', encoding='utf-8')
    return cfg


def _view():
    from reveal.adapters.reveal.config import get_config
    return get_config(Path('.'))


def _config_module_env_names():
    """Every REVEAL_* string constant in reveal/config.py outside docstrings: the names the
    config loader reads."""
    tree = ast.parse(Path(config_module.__file__).read_text(encoding='utf-8'))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr) \
                    and isinstance(node.body[0].value, ast.Constant):
                docstrings.add(id(node.body[0].value))
    return {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in docstrings and _ALL_REVEAL_VARS.match(node.value)
    }


def test_project_config_file_is_listed(isolated):
    cfg = _write_project_config(isolated)
    view = _view()
    paths = [entry['path'] for entry in view['sources']['project_configs']]
    assert Path(paths[0]).resolve() == cfg.resolve(), paths
    assert view['sources']['project_configs'][0]['root'] is True
    assert view['metadata']['config_files_count'] == 1
    # the file's settings are the ones in effect
    assert view['active_config']['rules']['disable'] == ['E501']


def test_no_config_file_lists_none(isolated):
    """Negative control: an empty project lists no file and counts 0."""
    view = _view()
    assert view['sources']['project_configs'] == []
    assert view['metadata']['config_files_count'] == 0


def test_env_vars_the_loader_reads_are_listed(isolated, monkeypatch):
    monkeypatch.setenv('REVEAL_RULES_SELECT', 'B')
    monkeypatch.setenv('REVEAL_IGNORE', 'vendor/**')
    monkeypatch.setenv('REVEAL_FORMAT', 'json')
    monkeypatch.setenv('REVEAL_BREADCRUMBS', '0')
    monkeypatch.setenv('REVEAL_C901_THRESHOLD', '20')
    env_vars = _view()['sources']['env_vars']
    assert env_vars == {
        'REVEAL_RULES_SELECT': 'B',
        'REVEAL_IGNORE': 'vendor/**',
        'REVEAL_FORMAT': 'json',
        'REVEAL_BREADCRUMBS': '0',
        'REVEAL_C901_THRESHOLD': '20',
    }


def test_env_vars_the_loader_never_reads_are_not_listed_as_config(isolated, monkeypatch):
    for name in ('REVEAL_C905_MAX_DEPTH', 'REVEAL_M101_THRESHOLD', 'REVEAL_CONFIG_DEBUG'):
        monkeypatch.setenv(name, '3')
    assert _view()['sources']['env_vars'] == {}


def test_every_variable_config_py_reads_is_listed_when_set(isolated, monkeypatch, tmp_path):
    """Guard: a REVEAL_* variable read by reveal/config.py but missing from reveal://config fails."""
    names = _config_module_env_names()
    assert 'REVEAL_RULES_DISABLE' in names  # positive control for the scan
    custom = tmp_path / 'custom.yaml'
    custom.write_text('rules:\n  disable: [X1]\n', encoding='utf-8')
    values = {name: '1' for name in names}
    values['REVEAL_CONFIG'] = str(custom)
    values['REVEAL_NO_CONFIG'] = '0'  # '1' would skip every layer
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    assert set(_view()['sources']['env_vars']) == names


def test_text_view_shows_select_and_the_file(isolated):
    cfg = _write_project_config(isolated)
    out = _run_reveal_direct('reveal://config').stdout
    assert 'Selected: E, C' in out, out
    assert 'Config Files Found: 1' in out, out
    assert cfg.name in out


def _inspect_config():
    from reveal.cli.commands.dev import _run_inspect_config
    buf = io.StringIO()
    with redirect_stdout(buf):
        _run_inspect_config()
    return buf.getvalue()


def test_inspect_config_shows_the_files_settings(isolated):
    cfg = _write_project_config(isolated)
    out = _inspect_config()
    assert 'Using all default settings.' not in out, out
    assert 'E501' in out, out
    assert str(cfg.resolve().name) in out


def test_inspect_config_defaults_when_nothing_applies(isolated, monkeypatch):
    """Negative control: REVEAL_NO_CONFIG=1 skips the project file, so the defaults line stays."""
    _write_project_config(isolated)
    monkeypatch.setenv('REVEAL_NO_CONFIG', '1')
    out = _inspect_config()
    assert 'Using all default settings.' in out, out
    assert 'E501' not in out, out
