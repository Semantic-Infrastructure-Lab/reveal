"""A config value that fails the schema never crashes a reader (BACK-2663) and fails the request that reads it
(BACK-2677, COMMAND_MODEL "Configuration failures").

``_validate_config_schema`` only warned, and the merged value was used as it was: ``ignore: 5``
made every walking noun exit 1 with ``TypeError: 'int' object is not iterable`` from
``ignore_patterns``. BACK-2663 dropped the value and used the default with a warning, exit 0, which
walked the trees the user meant to hide. The value is still dropped (no reader meets a shape it cannot
read), and an answer that reads its key exits 2 naming the file and key; a noun that does not read it is
unaffected.
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
def test_schema_invalid_ignore_is_an_invalid_request_naming_file_and_key(project, argv):
    (project / '.reveal.yaml').write_text('root: true\nignore: 5\n', encoding='utf-8')
    result = _cli(project.parent / 'xdg', *[a.format(root=project.as_posix()) for a in argv], '--format', 'json',
                  cwd=project.parent)
    assert 'Traceback' not in result.stderr, result.stderr
    assert result.returncode == 2, result.stderr
    expected = f"config {(project / '.reveal.yaml').as_posix()}: ignore: 5 is not of type 'array'"
    assert expected in result.stderr
    if argv[0] != 'check':  # check answers its usage errors in text only (the BACK-2671 class)
        document = json.loads(result.stdout)
        assert expected in document['error'] and 'ok.py' not in json.dumps(document)


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
@pytest.mark.parametrize('noun,code', [('ast', 0), ('metrics', 2)])
def test_an_override_with_an_invalid_files_pattern_fails_only_the_nouns_that_read_rules(project, noun, code):
    """Dropping only ``files`` left an override without its required pattern, and loading the
    config raised ``KeyError: 'files'`` on every noun; the whole override is still dropped. Metrics reads
    the rule settings and fails naming the key; ast reads none and answers as without the override."""
    (project / '.reveal.yaml').write_text('root: true\noverrides:\n  - files: 5\n    rules: {}\n', encoding='utf-8')
    result = _cli(project.parent / 'xdg', f'{noun}://{project.as_posix()}', '--format', 'json', cwd=project.parent)
    assert 'Traceback' not in result.stderr, result.stderr
    assert result.returncode == code, result.stderr
    if code == 2:
        assert 'overrides.0.files' in json.loads(result.stdout)['error']


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
    section that is not a table with ``AttributeError: 'str' object has no attribute 'get'``. An invalid
    value is an invalid request (2) naming the key; a section that cannot be read leaves every setting in
    it unknown (3)."""
    (project / 'pyproject.toml').write_text(pyproject, encoding='utf-8')
    result = _cli(project.parent / 'xdg', f'ast://{project.as_posix()}', '--format', 'json', cwd=project.parent)
    assert 'Traceback' not in result.stderr, result.stderr
    assert result.returncode == (2 if key else 3), result.stderr
    error = json.loads(result.stdout)['error']
    assert (project / 'pyproject.toml').as_posix() in error
    assert (f': {key}: ' in error) if key else ('could not be loaded' in error)


@pytest.mark.cli
def test_a_valid_pyproject_tool_reveal_still_applies(project):
    """Control: a valid ``[tool.reveal]`` ignore list is used and says nothing."""
    (project / 'pyproject.toml').write_text('[tool.reveal]\nroot = true\nignore = ["*.gen.py"]\n', encoding='utf-8')
    result = _cli(project.parent / 'xdg', f'ast://{project.as_posix()}', '--format', 'json', cwd=project.parent)
    assert result.returncode == 0 and 'skip.gen.py' not in result.stdout and 'ok.py' in result.stdout
    assert not [w for w in json.loads(result.stdout)['meta']['warnings'] if w.get('type') == 'config_warning']
