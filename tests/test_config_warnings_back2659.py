"""A configuration problem is in the answer, said once (BACK-2659, COMMAND_MODEL "Transports"), and a setting the
answer reads that could not be used fails the request (BACK-2677, COMMAND_MODEL "Configuration failures").

A problem that leaves the answer's settings known (a key nothing reads) is a ``config_warning`` entry in
``meta.warnings`` of every JSON answer, with nothing on stderr in JSON mode; any other answer prints it once on
stderr, after the answer. A missing ``REVEAL_CONFIG`` file, an unloadable config file and a non-integer
``REVEAL_*`` threshold used to be such warnings over an answer built from the defaults, exit 0 (ast walked the
trees the user ignored). They now fail the request: missing or invalid exits 2, unreadable exits 3, naming the
file or variable, on the CLI, the library API and MCP alike.
"""
import json
import os
import subprocess
import sys

import pytest

pytestmark = [pytest.mark.cli]

GOOD = 'def ok():\n    return 1\n'
NOUNS = [('ast', ''), ('metrics', ''), ('calls', '?callers=ok'), ('imports', '')]
# A top-level key the schema does not know: nothing reads it, so it stays a warning over a complete answer.
UNKNOWN_KEY = 'root: true\nbogus_setting: 1\n'


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


def _error(result):
    """The failed request's JSON document: its one error message, and no config warning beside it."""
    document = json.loads(result.stdout)
    assert _config_warnings(document) == [], document['meta']
    return document['error']


# --- a setting that cannot be used fails the request (BACK-2677) ---------------------------------------------

@pytest.mark.parametrize('noun,query', NOUNS)
def test_missing_reveal_config_is_an_invalid_request_naming_the_file(tmp_path, home, noun, query):
    root = _project(tmp_path / 'proj', reveal_yaml=None)
    missing = tmp_path / 'nope.yaml'
    result = _cli(home, _uri(noun, query, root), '--format', 'json', cwd=tmp_path, REVEAL_CONFIG=str(missing))
    assert result.returncode == 2, result.stderr
    assert f'REVEAL_CONFIG names {missing.as_posix()}' in _error(result)


def test_missing_reveal_config_fails_check_as_an_invalid_request(tmp_path, home):
    root = _project(tmp_path / 'proj', reveal_yaml=None)
    result = _cli(home, 'check', root.as_posix(), '--format', 'json', cwd=tmp_path,
                  REVEAL_CONFIG=str(tmp_path / 'nope.yaml'))
    assert result.returncode == 2
    assert 'used the defaults' not in result.stderr + result.stdout  # it did not: nothing ran
    assert sum('nope.yaml' in line for line in result.stderr.splitlines()) == 1, result.stderr


def test_missing_reveal_config_text_answer_prints_one_error_and_no_answer(tmp_path, home):
    root = _project(tmp_path / 'proj', reveal_yaml=None)
    result = _cli(home, _uri('metrics', '', root), cwd=tmp_path, REVEAL_CONFIG=str(tmp_path / 'nope.yaml'))
    assert result.returncode == 2
    lines = [line for line in result.stderr.splitlines() if 'nope.yaml' in line]
    assert len(lines) == 1 and 'REVEAL_CONFIG names' in lines[0], result.stderr
    assert result.stdout.strip() == ''


@pytest.mark.parametrize('noun,query', NOUNS)
def test_unloadable_project_config_leaves_the_answer_incomplete(tmp_path, home, noun, query):
    root = _project(tmp_path / 'proj', reveal_yaml='root: true\nrules: [unclosed\n')
    result = _cli(home, _uri(noun, query, root), '--format', 'json', cwd=tmp_path)
    assert result.returncode == 3, result.stderr
    message = _error(result)
    assert (root / '.reveal.yaml').as_posix() in message and 'ParserError' in message


def test_check_fails_on_an_unloadable_user_config(tmp_path, home):
    """check's own "config ... could not be loaded" disclosure over a defaults-built answer is gone: unknown
    settings cannot judge findings."""
    (home / 'reveal').mkdir()
    (home / 'reveal' / 'config.yaml').write_text('rules: [unclosed\n', encoding='utf-8')
    root = _project(tmp_path / 'proj')
    result = _cli(home, 'check', root.as_posix(), '--format', 'json', cwd=tmp_path)
    assert result.returncode == 3, result.stderr
    assert 'reveal/config.yaml could not be loaded' in result.stderr


def test_non_integer_threshold_variable_fails_the_nouns_that_read_rules(tmp_path, home):
    root = _project(tmp_path / 'proj')
    result = _cli(home, _uri('metrics', '', root), '--format', 'json', cwd=tmp_path, REVEAL_C901_THRESHOLD='abc')
    assert result.returncode == 2, result.stderr
    assert "REVEAL_C901_THRESHOLD='abc' is not an integer" in _error(result)
    # ast reads no rule setting: its answer is unaffected.
    unaffected = _cli(home, _uri('ast', '', root), '--format', 'json', cwd=tmp_path, REVEAL_C901_THRESHOLD='abc')
    assert unaffected.returncode == 0 and _config_warnings(json.loads(unaffected.stdout)) == []


def test_a_pool_worker_meeting_an_unloadable_nested_config_makes_the_answer_incomplete(tmp_path, home):
    """A nested config read only inside a pool worker: the files under it are lost evidence, named in the parent's
    answer, never the default thresholds and never the worker's stderr (fork, forkserver and spawn alike)."""
    root = _project(tmp_path / 'proj')
    (root / 'sub').mkdir()
    (root / 'sub' / '.reveal.yaml').write_text('rules: [unclosed\n', encoding='utf-8')
    for i in range(12):
        (root / f'm{i}.py').write_text(GOOD, encoding='utf-8')
        (root / 'sub' / f's{i}.py').write_text(GOOD, encoding='utf-8')
    result = _cli(home, _uri('metrics', '', root), '--format', 'json', cwd=tmp_path, REVEAL_MAX_WORKERS='4')
    assert result.returncode == 3, result.stderr
    document = json.loads(result.stdout)
    (failed,) = [w for w in document['meta']['warnings'] if w.get('type') == 'analysis_failed']
    assert 'sub/s0.py' in json.dumps(failed) and 'could not be loaded' in json.dumps(failed['failures'])
    assert _config_warnings(document) == []
    assert 'Failed to load config' not in result.stderr


def test_library_query_raises_the_invalid_request(tmp_path, monkeypatch):
    from reveal import api
    from reveal.config import RevealConfig
    from reveal.errors import ConfigValidationError
    root = _project(tmp_path / 'proj', reveal_yaml=None)
    monkeypatch.setenv('REVEAL_CONFIG', str(tmp_path / 'nope.yaml'))
    RevealConfig._cache.clear()
    with pytest.raises(ConfigValidationError, match='REVEAL_CONFIG names'):
        api.query(_uri('ast', '', root))


@pytest.mark.mcp
@pytest.mark.parametrize('provenance', [True, False], ids=['json', 'text'])
def test_mcp_answers_the_failure_naming_the_file(tmp_path, monkeypatch, provenance):
    from reveal import mcp_server
    root = _project(tmp_path / 'proj', reveal_yaml=None)
    monkeypatch.setenv('REVEAL_CONFIG', str(tmp_path / 'nope.yaml'))
    text = mcp_server.reveal_query(_uri('ast', '', root), provenance=provenance)
    assert text.startswith('[reveal error: REVEAL_CONFIG names ') and text.count('nope.yaml') == 1


# --- a problem that leaves the settings known stays a warning, said once (BACK-2659) --------------------------

@pytest.mark.parametrize('noun,query', NOUNS)
def test_unknown_key_is_in_the_json_once_and_not_on_stderr(tmp_path, home, noun, query):
    root = _project(tmp_path / 'proj', reveal_yaml=UNKNOWN_KEY)
    result = _cli(home, _uri(noun, query, root), '--format', 'json', cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    (entry,) = _config_warnings(json.loads(result.stdout))
    assert entry['code'] == 'config_schema_invalid' and entry['path'] == (root / '.reveal.yaml').as_posix()
    assert 'bogus_setting' in entry['message']
    assert 'bogus_setting' not in result.stderr, result.stderr


def test_unknown_key_text_answer_says_it_once_after_the_answer(tmp_path, home):
    root = _project(tmp_path / 'proj', reveal_yaml=UNKNOWN_KEY)
    result = _cli(home, _uri('metrics', '', root), cwd=tmp_path)
    assert result.returncode == 0
    lines = [line for line in result.stderr.splitlines() if 'bogus_setting' in line]
    assert len(lines) == 1 and lines[0].startswith('warning: '), result.stderr
    assert 'bogus_setting' not in result.stdout


@pytest.mark.parametrize('argv', [('metrics://{root}',), ('check', '{root}')], ids=['metrics', 'check'])
def test_unknown_rule_setting_is_in_the_json_once(tmp_path, home, argv):
    root = _project(tmp_path / 'proj', reveal_yaml='root: true\nrules:\n  C901:\n    bogus_key: 3\n')
    result = _cli(home, *[a.format(root=root.as_posix()) for a in argv], '--format', 'json', cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    (entry,) = _config_warnings(json.loads(result.stdout))
    assert (entry['code'], entry['rule'], entry['key']) == ('config_key_unknown', 'C901', 'bogus_key')
    assert 'bogus_key' not in result.stderr, result.stderr


@pytest.mark.parametrize('noun,query', NOUNS + [('check', None)])
def test_valid_config_has_no_config_warning(tmp_path, home, noun, query):
    """The unaffected sibling: a project whose config loads answers exactly as before."""
    root = _project(tmp_path / 'proj', reveal_yaml='root: true\nignore:\n  - "*.gen.py"\n')
    argv = ('check', root.as_posix()) if query is None else (_uri(noun, query, root),)
    result = _cli(home, *argv, '--format', 'json', cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert _config_warnings(json.loads(result.stdout)) == []
    assert result.stderr == ''


def test_library_query_carries_the_warning(tmp_path):
    from reveal import api
    from reveal.config import RevealConfig
    root = _project(tmp_path / 'proj', reveal_yaml=UNKNOWN_KEY)
    RevealConfig._cache.clear()
    result = api.query(_uri('ast', '', root))
    assert [w['code'] for w in _config_warnings(result)] == ['config_schema_invalid']


@pytest.mark.mcp
def test_mcp_json_carries_the_warning_and_no_stderr_beside_it(tmp_path):
    from reveal import mcp_server
    root = _project(tmp_path / 'proj', reveal_yaml=UNKNOWN_KEY)
    text = mcp_server.reveal_query(_uri('ast', '', root), provenance=True)
    assert getattr(text, 'stderr', '') == ''
    assert [w['code'] for w in _config_warnings(json.loads(text))] == ['config_schema_invalid']


@pytest.mark.mcp
def test_mcp_text_answer_ends_with_the_warning(tmp_path):
    from reveal import mcp_server
    root = _project(tmp_path / 'proj', reveal_yaml=UNKNOWN_KEY)
    text = mcp_server.reveal_query(_uri('ast', '', root))
    assert text.rstrip('\n').splitlines()[-1].startswith('[warning: config ')
    assert text.count('bogus_setting') == 1 and '[stderr:' not in text
