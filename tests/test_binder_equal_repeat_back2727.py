"""The binder's repeated-setting check compares converted values, and integer controls reject booleans (BACK-2727).

COMMAND_MODEL "Conflicting values": a scalar control given twice with different values exits 2 naming both; equal
values are accepted once. Before, the URI check compared the raw spellings, so a presence key given bare and with a
value (``?circular&circular=true``, ``?tokens&tokens=true``, ``?last&last=true``) or a boolean spelled two ways
(``?full=1&full=true``) exited 2 as "given twice with different values (True and true)", although both spellings
convert to the same value. And ``whole_number`` took a boolean as an integer (``int(True)`` is 1), so
``api.query('codex://sessions/', search=..., matches=False)`` kept every snippet (0 = all) and ``matches=True`` kept one.

Now each repeated value is compared as its control reads it (the shared codec), and ``whole_number`` refuses a bool:
an invalid value, exit 2, naming the control. Different converted values, and a value the control rejects beside
another, still exit 2 as before.
"""
import json

import pytest

from codex_session_fixture import build_codex_home
from claude_session_fixture import build_claude_home
from conftest import _run_reveal_direct
from reveal.adapters.claude.params import PARAM_SPECS as CLAUDE_SPECS
from reveal.adapters.codex.adapter import CodexAdapter
from reveal.adapters.codex.params import PARAM_SPECS as CODEX_SPECS
from reveal.adapters.imports import ImportsAdapter
from reveal.cli.routing.declared import declared_adapter_class
from reveal.errors import RequestValidationError
from reveal.utils.query_binding import bind_declared_params
from reveal.utils.query_parser import whole_number

IMPORTS_SPECS = ImportsAdapter.PARAM_SPECS


def _bound(specs, query):
    return dict(bind_declared_params(specs, query, transport='uri').peek_items())


# (noun, specs, the repeated query, the same setting given once)
EQUAL = [
    ('claude', CLAUDE_SPECS, 'tokens&tokens=true', 'tokens'),
    ('codex', CODEX_SPECS, 'last&last=true', 'last'),
    ('codex', CODEX_SPECS, 'goal=yes&goal', 'goal'),
    ('codex', CODEX_SPECS, 'full=1&full=true', 'full=true'),
    ('codex', CODEX_SPECS, 'full&full=yes', 'full'),
    ('codex', CODEX_SPECS, 'matches=3&matches=03', 'matches=3'),
    ('imports', IMPORTS_SPECS, 'circular&circular=true', 'circular'),
]


@pytest.mark.parametrize('noun,specs,repeated,once', EQUAL, ids=[f'{row[0]}:{row[2]}' for row in EQUAL])
def test_an_equal_repeated_value_is_one_setting(noun, specs, repeated, once):
    assert _bound(specs, repeated) == _bound(specs, once)


# Negative controls: different converted values, or a rejected value beside another, still conflict (unchanged).
DIFFERENT = [
    (CODEX_SPECS, 'full&full=false', 'full is given twice with different values (True and false)'),
    (CODEX_SPECS, 'full=1&full=0', 'full is given twice with different values (1 and 0)'),
    (CODEX_SPECS, 'matches=3&matches=4', 'matches is given twice with different values (3 and 4)'),
    (CODEX_SPECS, 'matches=abc&matches=3', 'matches is given twice with different values (abc and 3)'),
    (CODEX_SPECS, 'key=a&key=b', 'key is given twice with different values (a and b)'),
    (IMPORTS_SPECS, 'circular=true&circular=false', 'circular is given twice with different values (true and false)'),
]


@pytest.mark.parametrize('specs,query,message', DIFFERENT, ids=[row[1] for row in DIFFERENT])
def test_different_values_still_conflict(specs, query, message):
    with pytest.raises(RequestValidationError, match=message.replace('(', r'\(').replace(')', r'\)')):
        bind_declared_params(specs, query, transport='uri')


def test_an_equal_raw_value_the_control_rejects_is_still_its_value_error():
    with pytest.raises(RequestValidationError, match=r'matches must be a whole number, got .abc.'):
        bind_declared_params(CODEX_SPECS, 'matches=abc&matches=abc', transport='uri')


@pytest.mark.parametrize('value', [True, False])
def test_whole_number_rejects_a_boolean(value):
    with pytest.raises(ValueError):
        whole_number(value)


@pytest.mark.parametrize('value,expected', [(3, 3), ('3', 3), (3.0, 3), (0, 0), ('0', 0)])
def test_whole_number_keeps_its_accepted_spellings(value, expected):
    assert whole_number(value) == expected and type(whole_number(value)) is int


def test_whole_number_still_rejects_a_fraction():
    with pytest.raises(ValueError):
        whole_number(1.5)


# ---- end to end: the typed API (Codex), the URI (Claude, Imports) ----

@pytest.fixture
def codex(tmp_path, monkeypatch):
    home = build_codex_home(tmp_path / 'codex-home')
    monkeypatch.setattr(CodexAdapter, 'CODEX_HOME', home)
    monkeypatch.setattr(CodexAdapter, 'CODEX_DB', home / 'state_5.sqlite')
    monkeypatch.chdir(tmp_path)
    return home


@pytest.mark.parametrize('value', [True, False])
def test_the_typed_api_refuses_a_boolean_snippet_count(codex, value):
    from reveal import api
    with pytest.raises(RequestValidationError, match=f'matches must be a whole number, got {value}'):
        api.query('codex://sessions/', search='auth', matches=value)


def test_the_typed_api_keeps_an_integer_snippet_count(codex):
    from reveal import api
    assert api.query('codex://sessions/', search='auth', matches=1)['type'] == 'codex_content_search'


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


def _answer(doc):
    """The answer without its echo of the request's spelling."""
    return {key: value for key, value in doc.items() if key != 'source'}


@pytest.fixture
def claude(tmp_path, monkeypatch):
    adapter = declared_adapter_class('claude')
    home = build_claude_home(tmp_path / 'claude-home')
    monkeypatch.setattr(adapter, 'CLAUDE_HOME', home)
    monkeypatch.setattr(adapter, 'CONVERSATION_BASE', home / 'projects')
    monkeypatch.setattr(adapter, 'CLAUDE_JSON', home.parent / '.claude.json')
    for name, folder in (('PLANS_DIR', 'plans'), ('AGENTS_DIR', 'agents'), ('HOOKS_DIR', 'hooks')):
        monkeypatch.setattr(adapter, name, home / folder)
    monkeypatch.setattr(adapter, 'SESSIONS_DIR', None)
    monkeypatch.chdir(tmp_path)
    return home


def test_claude_tokens_given_bare_and_true_answers_as_tokens(claude):
    once, once_doc = _json('claude://session/my-session?tokens')
    twice, twice_doc = _json('claude://session/my-session?tokens&tokens=true')
    assert once.returncode == 0, once.stderr
    assert (twice.returncode, _answer(twice_doc)) == (0, _answer(once_doc)), twice.stderr


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / 'proj'
    for rel, text in {'.reveal.yaml': 'root: true\n', 'pkg/__init__.py': '', 'pkg/a.py': 'from pkg import b\n',
                      'pkg/b.py': 'from pkg import a\n'}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    monkeypatch.chdir(root)
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    return root


def test_imports_circular_given_bare_and_true_answers_as_circular(project):
    base = f'imports://{project.as_posix()}'
    once, once_doc = _json(f'{base}?circular')
    twice, twice_doc = _json(f'{base}?circular&circular=true')
    assert once.returncode == 0, once.stderr
    assert (twice.returncode, _answer(twice_doc)) == (0, _answer(once_doc)), twice.stderr


def test_imports_circular_true_and_false_still_exit_2(project):
    run, _ = _json(f'imports://{project.as_posix()}?circular=true&circular=false')
    assert run.returncode == 2
