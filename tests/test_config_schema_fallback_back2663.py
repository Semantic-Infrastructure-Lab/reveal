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


def test_architecture_keeps_its_own_validation():
    """LayerConfig fails the request naming the config file (BACK-1059); the schema does not
    silently drop the layer it would reject."""
    config = {'architecture': {'layers': ['not-a-dict']}}
    RevealConfig._validate_config_schema(config, Path('p') / '.reveal.yaml')
    assert config == {'architecture': {'layers': ['not-a-dict']}}


@pytest.mark.cli
@pytest.mark.parametrize('noun', ['ast', 'metrics'])
def test_an_override_with_an_invalid_files_pattern_is_dropped_whole(project, noun):
    """Dropping only ``files`` left an override without its required pattern, and loading the
    config raised ``KeyError: 'files'`` on every noun. The whole override goes."""
    (project / '.reveal.yaml').write_text('root: true\noverrides:\n  - files: 5\n    rules: {}\n', encoding='utf-8')
    result = _cli(project.parent / 'xdg', f'{noun}://{project.as_posix()}', '--format', 'json', cwd=project.parent)
    assert 'Traceback' not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    keys = [w['key'] for w in json.loads(result.stdout)['meta']['warnings'] if w.get('type') == 'config_warning']
    assert 'overrides.0.files' in keys and 'overrides.0' in keys


def test_a_dropped_required_value_takes_its_object_with_it():
    config = {'overrides': [{'files': 5, 'rules': {}}, {'files': 'a/*'}]}
    RevealConfig._validate_config_schema(config, Path('p') / '.reveal.yaml')
    assert config == {'overrides': [{'files': 'a/*'}]}
    RevealConfig(config, Path('p'))  # parses its overrides


@pytest.mark.cli
@pytest.mark.parametrize('pyproject,key', [('[tool.reveal]\nroot = true\nignore = 5\n', 'ignore'),
                                           ('[tool]\nreveal = "x"\n', None)],
                         ids=['schema-invalid-value', 'not-a-table'])
def test_pyproject_tool_reveal_is_validated_like_a_reveal_yaml(project, pyproject, key):
    """``[tool.reveal]`` skipped the schema: ``ignore = 5`` crashed with the same TypeError, and a
    section that is not a table with ``AttributeError: 'str' object has no attribute 'get'``."""
    (project / 'pyproject.toml').write_text(pyproject, encoding='utf-8')
    result = _cli(project.parent / 'xdg', f'ast://{project.as_posix()}', '--format', 'json', cwd=project.parent)
    assert 'Traceback' not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    entries = [w for w in json.loads(result.stdout)['meta']['warnings'] if w.get('type') == 'config_warning']
    expected = [('config_schema_invalid', key)] if key else [('config_load_failed', None)]
    assert [(w['code'], w.get('key')) for w in entries] == expected
    assert entries[0]['path'] == (project / 'pyproject.toml').as_posix()


@pytest.mark.cli
def test_a_valid_pyproject_tool_reveal_still_applies(project):
    """Control: a valid ``[tool.reveal]`` ignore list is used and says nothing."""
    (project / 'pyproject.toml').write_text('[tool.reveal]\nroot = true\nignore = ["*.gen.py"]\n', encoding='utf-8')
    result = _cli(project.parent / 'xdg', f'ast://{project.as_posix()}', '--format', 'json', cwd=project.parent)
    assert result.returncode == 0 and 'skip.gen.py' not in result.stdout and 'ok.py' in result.stdout
    assert not [w for w in json.loads(result.stdout)['meta']['warnings'] if w.get('type') == 'config_warning']
