"""A config value that fails the schema falls back to its default (BACK-2663).

``_validate_config_schema`` only warned, and the merged value was used as it was: ``ignore: 5``
made every walking noun exit 1 with ``TypeError: 'int' object is not iterable`` from
``ignore_patterns``. The value is now dropped, the answer says so in a ``config_schema_invalid``
warning, and the exit code is the one the request has without that setting.
"""
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from reveal.config import RevealConfig

GOOD = 'def ok():\n    return 1\n'


def _cli(home, *argv, cwd):
    env = {key: value for key, value in os.environ.items() if not key.startswith('REVEAL_')}
    env.update(REVEAL_DISK_CACHE='0', XDG_CONFIG_HOME=str(home))
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], capture_output=True, text=True,
                          encoding='utf-8', env=env, cwd=cwd, timeout=180)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'ok.py').write_text(GOOD, encoding='utf-8')
    (root / 'skip.gen.py').write_text(GOOD, encoding='utf-8')
    (tmp_path / 'xdg').mkdir()
    return root


@pytest.mark.cli
@pytest.mark.parametrize('argv', [('ast://{root}',), ('metrics://{root}',), ('calls://{root}?callers=ok',),
                                  ('imports://{root}',), ('check', '{root}')],
                         ids=['ast', 'metrics', 'calls', 'imports', 'check'])
def test_schema_invalid_ignore_falls_back_instead_of_crashing(project, argv):
    (project / '.reveal.yaml').write_text('root: true\nignore: 5\n', encoding='utf-8')
    result = _cli(project.parent / 'xdg', *[a.format(root=project.as_posix()) for a in argv], '--format', 'json',
                  cwd=project.parent)
    assert 'Traceback' not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    entries = [w for w in json.loads(result.stdout)['meta']['warnings'] if w.get('type') == 'config_warning']
    assert [(w['code'], w['key']) for w in entries] == [('config_schema_invalid', 'ignore')]
    assert 'default' in entries[0]['message']


@pytest.mark.cli
def test_valid_ignore_still_applies(project):
    """Control: a list of patterns is used as before (the generated file is left out)."""
    (project / '.reveal.yaml').write_text('root: true\nignore:\n  - "*.gen.py"\n', encoding='utf-8')
    result = _cli(project.parent / 'xdg', f'ast://{project.as_posix()}', '--format', 'json', cwd=project.parent)
    assert result.returncode == 0 and 'skip.gen.py' not in result.stdout and 'ok.py' in result.stdout
    assert not [w for w in json.loads(result.stdout)['meta']['warnings'] if w.get('type') == 'config_warning']


def test_only_the_invalid_values_are_dropped(caplog):
    config = {'root': True, 'ignore': ['*.gen.py', 5], 'rules': {'disable': 'E501', 'C901': {'threshold': 9}},
              'overrides': [{'files': 'a/*'}, {'rules': {}}], 'unknown_key': 1}
    with caplog.at_level(logging.WARNING, logger='reveal.config'):
        RevealConfig._validate_config_schema(config, Path('p') / '.reveal.yaml')
    assert config == {'root': True, 'ignore': ['*.gen.py'], 'rules': {'C901': {'threshold': 9}},
                      'overrides': [{'files': 'a/*'}], 'unknown_key': 1}
    assert len(caplog.records) == 4  # ignore[1], rules.disable, overrides[1], unknown_key


def test_test_layout_keeps_its_own_fail_closed_validation():
    config = {'test_layout': {'additional_paths': 'tests'}}
    RevealConfig._validate_config_schema(config, Path('p') / '.reveal.yaml')
    assert config == {'test_layout': {'additional_paths': 'tests'}}
