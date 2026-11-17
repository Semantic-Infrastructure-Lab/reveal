"""A configuration problem is in the answer, said once (BACK-2659, COMMAND_MODEL "Transports").

A missing ``REVEAL_CONFIG`` file, an unloadable ``.reveal.yaml``, a non-integer ``REVEAL_*``
threshold and an unknown rule setting were ``logger`` lines on stderr only: the JSON answer, the
library API and MCP's JSON never said the user's settings were not applied, and one problem printed
once per config load (the walk root and the cwd: twice). Each is now a ``config_warning`` entry in
``meta.warnings`` of every JSON answer, with nothing on stderr in JSON mode; any other answer prints
it once on stderr, after the answer. Exit codes do not move.
"""
import json
import os
import subprocess
import sys

import pytest

pytestmark = [pytest.mark.cli]

GOOD = 'def ok():\n    return 1\n'
NOUNS = [('ast', ''), ('metrics', ''), ('calls', '?callers=ok')]


@pytest.fixture
def home(tmp_path):
    """An isolated user config home, so the developer's own config never takes part."""
    xdg = tmp_path / 'xdg'
    xdg.mkdir()
    return xdg


def _project(root, reveal_yaml='root: true\n'):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'ok.py').write_text(GOOD, encoding='utf-8')
    if reveal_yaml is not None:
        (root / '.reveal.yaml').write_text(reveal_yaml, encoding='utf-8')
    return root


def _cli(home, *argv, cwd=None, **env):
    """The real process: stderr as a terminal shows it, logging handlers included."""
    full = {key: value for key, value in os.environ.items() if not key.startswith('REVEAL_')}
    full.update(REVEAL_DISK_CACHE='0', XDG_CONFIG_HOME=str(home), **env)
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], capture_output=True, text=True,
                          encoding='utf-8', env=full, cwd=cwd, timeout=180)


def _config_warnings(document):
    return [w for w in document['meta']['warnings'] if w.get('type') == 'config_warning']


def _uri(noun, query, root):
    return f'{noun}://{root.as_posix()}{query}'


@pytest.mark.parametrize('noun,query', NOUNS)
def test_missing_reveal_config_is_in_the_json_once_and_not_on_stderr(tmp_path, home, noun, query):
    root = _project(tmp_path / 'proj', reveal_yaml=None)
    missing = tmp_path / 'nope.yaml'
    result = _cli(home, _uri(noun, query, root), '--format', 'json', cwd=tmp_path, REVEAL_CONFIG=str(missing))
    assert result.returncode == 0, result.stderr
    (entry,) = _config_warnings(json.loads(result.stdout))
    assert entry['code'] == 'config_file_missing' and entry['path'] == missing.as_posix()
    assert 'nope.yaml' in entry['message']
    assert 'nope.yaml' not in result.stderr, result.stderr


@pytest.mark.parametrize('noun,query,code', [('imports', '', 3)])
def test_missing_reveal_config_keeps_the_failing_nouns_exit(tmp_path, home, noun, query, code):
    """Pinned as it is (a cross-noun question taken to Scott): a noun that classifies tests fails
    closed on a selected configuration file it cannot read. The warning is in its JSON too."""
    root = _project(tmp_path / 'proj', reveal_yaml=None)
    result = _cli(home, _uri(noun, query, root), '--format', 'json', cwd=tmp_path,
                  REVEAL_CONFIG=str(tmp_path / 'nope.yaml'))
    assert result.returncode == code
    assert [w['code'] for w in _config_warnings(json.loads(result.stdout))] == ['config_file_missing']


def test_missing_reveal_config_check_keeps_its_failure(tmp_path, home):
    """check fails the same way (exit 3, no JSON document); the warning no answer carried is said
    once on stderr instead of being dropped."""
    root = _project(tmp_path / 'proj', reveal_yaml=None)
    result = _cli(home, 'check', root.as_posix(), '--format', 'json', cwd=tmp_path,
                  REVEAL_CONFIG=str(tmp_path / 'nope.yaml'))
    assert result.returncode == 3
    assert 'selected configuration file was not found' in result.stderr
    assert sum('nope.yaml' in line for line in result.stderr.splitlines()) == 1, result.stderr


def test_missing_reveal_config_text_answer_says_it_once_after_the_answer(tmp_path, home):
    root = _project(tmp_path / 'proj', reveal_yaml=None)
    result = _cli(home, _uri('metrics', '', root), cwd=tmp_path, REVEAL_CONFIG=str(tmp_path / 'nope.yaml'))
    assert result.returncode == 0
    lines = [line for line in result.stderr.splitlines() if 'nope.yaml' in line]
    assert len(lines) == 1 and lines[0].startswith('warning: '), result.stderr
    assert 'nope.yaml' not in result.stdout


@pytest.mark.parametrize('noun,query', NOUNS)
def test_unloadable_project_config_is_in_the_json(tmp_path, home, noun, query):
    root = _project(tmp_path / 'proj', reveal_yaml='root: true\nrules: [unclosed\n')
    result = _cli(home, _uri(noun, query, root), '--format', 'json', cwd=tmp_path)
    (entry,) = _config_warnings(json.loads(result.stdout))
    assert entry['code'] == 'config_load_failed' and entry['path'] == (root / '.reveal.yaml').as_posix()
    assert entry['reason'].startswith('ParserError')
    assert '.reveal.yaml' not in result.stderr, result.stderr


def test_non_integer_threshold_variable_is_in_the_json(tmp_path, home):
    root = _project(tmp_path / 'proj')
    result = _cli(home, _uri('ast', '', root), '--format', 'json', cwd=tmp_path, REVEAL_C901_THRESHOLD='abc')
    assert result.returncode == 0
    (entry,) = _config_warnings(json.loads(result.stdout))
    assert entry['code'] == 'config_env_invalid' and entry['path'] == 'REVEAL_C901_THRESHOLD'
    assert 'REVEAL_C901_THRESHOLD' not in result.stderr


@pytest.mark.parametrize('argv', [('metrics://{root}',), ('check', '{root}')], ids=['metrics', 'check'])
def test_unknown_rule_setting_is_in_the_json_once(tmp_path, home, argv):
    root = _project(tmp_path / 'proj', reveal_yaml='root: true\nrules:\n  C901:\n    bogus_key: 3\n')
    result = _cli(home, *[a.format(root=root.as_posix()) for a in argv], '--format', 'json', cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    (entry,) = _config_warnings(json.loads(result.stdout))
    assert (entry['code'], entry['rule'], entry['key']) == ('config_key_unknown', 'C901', 'bogus_key')
    assert 'bogus_key' not in result.stderr, result.stderr


def test_check_states_an_unloadable_user_config_in_its_json(tmp_path, home):
    """check's own "config ... could not be loaded" disclosure is replaced by the shared entry."""
    (home / 'reveal').mkdir()
    (home / 'reveal' / 'config.yaml').write_text('rules: [unclosed\n', encoding='utf-8')
    root = _project(tmp_path / 'proj')
    result = _cli(home, 'check', root.as_posix(), '--format', 'json', cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    (entry,) = _config_warnings(document)
    assert entry['code'] == 'config_load_failed' and entry['path'].endswith('reveal/config.yaml')
    assert 'could not be loaded' not in json.dumps({k: v for k, v in document.items() if k != 'meta'})
    text = _cli(home, 'check', root.as_posix(), cwd=tmp_path)
    assert text.stderr.count('could not be loaded') == 1 and 'could not be loaded' not in text.stdout


@pytest.mark.parametrize('noun,query', NOUNS + [('check', None)])
def test_valid_config_has_no_config_warning(tmp_path, home, noun, query):
    """The unaffected sibling: a project whose config loads answers exactly as before."""
    root = _project(tmp_path / 'proj', reveal_yaml='root: true\nignore:\n  - "*.gen.py"\n')
    argv = ('check', root.as_posix()) if query is None else (_uri(noun, query, root),)
    result = _cli(home, *argv, '--format', 'json', cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert _config_warnings(json.loads(result.stdout)) == []
    assert result.stderr == ''


def test_a_pool_worker_hands_its_config_warning_to_the_answer(tmp_path, home):
    """A nested config read only inside a pool worker reaches the parent's answer, never the
    worker's stderr (fork, forkserver and spawn alike)."""
    root = _project(tmp_path / 'proj')
    (root / 'sub').mkdir()
    (root / 'sub' / '.reveal.yaml').write_text('rules: [unclosed\n', encoding='utf-8')
    for i in range(12):
        (root / f'm{i}.py').write_text(GOOD, encoding='utf-8')
        (root / 'sub' / f's{i}.py').write_text(GOOD, encoding='utf-8')
    result = _cli(home, _uri('metrics', '', root), '--format', 'json', cwd=tmp_path, REVEAL_MAX_WORKERS='4')
    codes = [w['code'] for w in _config_warnings(json.loads(result.stdout))]
    assert codes == ['config_load_failed'], result.stderr
    assert 'could not be loaded' not in result.stderr and 'Failed to load config' not in result.stderr


def test_library_query_carries_the_warning(tmp_path, monkeypatch):
    from reveal import api
    from reveal.config import RevealConfig
    root = _project(tmp_path / 'proj', reveal_yaml=None)
    monkeypatch.setenv('REVEAL_CONFIG', str(tmp_path / 'nope.yaml'))
    RevealConfig._cache.clear()
    result = api.query(_uri('ast', '', root))
    assert [w['code'] for w in _config_warnings(result)] == ['config_file_missing']


@pytest.mark.mcp
def test_mcp_json_carries_the_warning_and_no_stderr_beside_it(tmp_path, monkeypatch):
    from reveal import mcp_server
    root = _project(tmp_path / 'proj', reveal_yaml=None)
    monkeypatch.setenv('REVEAL_CONFIG', str(tmp_path / 'nope.yaml'))
    text = mcp_server.reveal_query(_uri('ast', '', root), provenance=True)
    assert getattr(text, 'stderr', '') == ''
    assert [w['code'] for w in _config_warnings(json.loads(text))] == ['config_file_missing']


@pytest.mark.mcp
def test_mcp_text_answer_ends_with_the_warning(tmp_path, monkeypatch):
    from reveal import mcp_server
    root = _project(tmp_path / 'proj', reveal_yaml=None)
    monkeypatch.setenv('REVEAL_CONFIG', str(tmp_path / 'nope.yaml'))
    text = mcp_server.reveal_query(_uri('ast', '', root))
    assert text.rstrip('\n').splitlines()[-1].startswith('[warning: REVEAL_CONFIG names ')
    assert text.count('nope.yaml') == 1 and '[stderr:' not in text
