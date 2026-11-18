"""Calls and Imports applicability (COMMAND_MODEL "Applicability", BACK-2656 Step 2b).

Each control declares the answers that read it (``ParamSpec.answers``): on any other answer it is an invalid
request, refused before analysis with the one shared message, on the URI, the subcommand and ``api.query``. Calls'
own stderr notes for an unread ``limit``/``depth`` and its "detail applies to callees only" check, and Imports' unread
``limit``/``detail``/``format`` warnings (the flag ledger's), are what this replaces. Calls and Imports ``format``
declares its answers now, ahead of its retirement (Q4).
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.errors import RequestValidationError

UNREAD_WARNINGS = ('unused_query_param', 'unused_flag', 'unknown_query_param')


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / 'a.py').write_text('import b\n\n\ndef serve():\n    return helper()\n\n\ndef helper():\n    return len([])\n',
                                   encoding='utf-8')
    (tmp_path / 'b.py').write_text('X = 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


def _unread(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings') or [] if (w.get('code') or w.get('type'))
            in UNREAD_WARNINGS]


def _refused(argv, control, answer):
    run, _doc = _run(*argv)
    assert run.returncode == 2, (run.returncode, run.stdout[:300], run.stderr)
    assert f"control '{control}' is not read by this answer ({answer}" in run.stderr, run.stderr
    assert f'{control} is read by: ' in run.stderr and 'controls this answer reads: ' in run.stderr, run.stderr


# --- calls --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('argv,control,answer', [
    (('calls://.?callers=serve&kind=function',), 'kind', 'calls_query, callers, callers=serve'),
    (('calls://.?callers=serve&external',), 'external', 'calls_query'),
    (('calls://.?callers=serve&builtins',), 'builtins', 'calls_query'),
    (('calls://.?callers=serve&limit=1',), 'limit', 'calls_query'),            # a stderr-only note before
    (('calls://.?callers=serve&detail',), 'detail', 'calls_query'),            # calls' own check before
    (('calls://.?callers=serve&detail=false',), 'detail', 'calls_query'),      # given, though off
    (('calls://.?callees=serve&test-framework',), 'test-framework', 'calls_callees'),
    (('calls://.?callees=serve&limit=2',), 'limit', 'calls_callees'),
    (('calls://.?uncalled&depth=2',), 'depth', 'calls_uncalled'),              # a stderr-only note before
    (('calls://.?uncalled&builtins',), 'builtins', 'calls_uncalled'),
    (('calls://.?sort=-callers&format=json',), 'format', 'calls_ranking'),
    (('calls://.?sort=-callers&format=dot',), 'format', 'calls_ranking'),      # calls' dot check before
    (('calls://.?sort=-callers&kind=function',), 'kind', 'calls_ranking'),
    (('calls://.?modules&depth=2',), 'depth', 'calls_module_graph'),
    (('calls://.?modules&limit=1',), 'limit', 'calls_module_graph'),
    (('calls', '.', '--callers', 'serve', '--limit', '1'), 'limit', 'calls_query'),   # the subcommand
    (('calls', '.', '--uncalled', '--depth', '2'), 'depth', 'calls_uncalled'),
    (('calls://.?callers=serve', '--limit', '1'), 'limit', 'calls_query'),            # the URI and a flag
])
def test_calls_refuses_a_control_its_answer_does_not_read(proj, argv, control, answer):
    _refused(argv, control, answer)


def test_calls_api_refuses_the_same_request(proj):
    from reveal import api
    with pytest.raises(RequestValidationError, match=r"control 'builtins' is not read by this answer \(calls_query"):
        api.query('calls://.?callers=serve', builtins=True)
    with pytest.raises(RequestValidationError, match=r"control 'depth' is not read by this answer \(calls_uncalled"):
        api.query('calls://.?uncalled&depth=2')


@pytest.mark.parametrize('uri', [
    'calls://.?callers=serve&depth=2&format=json', 'calls://.?callees=serve&builtins&detail&depth=2',
    'calls://.?root=serve&depth=2&builtins', 'calls://.?sort=-callers&limit=1&builtins&test-framework',
    'calls://.?uncalled&kind=function&limit=1&test-framework&format=json', 'calls://.?modules&external',
])
def test_calls_answers_where_its_controls_are_read(proj, uri):
    run, doc = _run(uri)
    assert run.returncode in (0, 3), (run.returncode, run.stderr)  # 3: an answer with a disclosed loss
    assert doc['type'].startswith('calls_') and not _unread(doc), doc.get('meta')
    assert 'ignored' not in run.stderr, run.stderr


# --- imports ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('argv,control,answer', [
    (('imports://.?limit=1',), 'limit', 'imports, default'),
    (('imports://.?circular&limit=1',), 'limit', 'circular_dependencies'),
    (('imports://.?detail=full',), 'detail', 'imports, default'),
    (('imports://.?components&detail=full',), 'detail', 'components'),
    (('imports://.?sort=-fan-in&detail=full',), 'detail', 'fan_in_ranking'),
    (('imports://.?format=dot',), 'format', 'imports, default'),
    (('imports://.?circular&format=dot',), 'format', 'circular_dependencies'),   # a no-op note before
    (('imports://.?importers=b.py&format=json',), 'format', 'module_importers'),
    (('imports', '.', '--limit', '1'), 'limit', 'imports, default'),             # the subcommand
    (('imports', '.', '--entrypoints', '--detail', 'full'), 'detail', 'entrypoints'),
    (('imports', '.', '--verbose'), 'detail', 'imports, default'),               # verbose is detail's legacy word
    (('imports://.', '--limit', '1'), 'limit', 'imports, default'),              # the URI and a flag
])
def test_imports_refuses_a_control_its_answer_does_not_read(proj, argv, control, answer):
    _refused(argv, control, answer)


def test_imports_api_refuses_the_same_request(proj):
    from reveal import api
    with pytest.raises(RequestValidationError, match=r"control 'detail' is not read by this answer \(imports"):
        api.query('imports://.', detail='full')
    with pytest.raises(RequestValidationError, match=r"control 'format' is not read by this answer \(imports"):
        api.query('imports://.?format=dot')


@pytest.mark.parametrize('uri', [
    'imports://.?sort=-fan-in&limit=1', 'imports://.?circular&detail=full', 'imports://.?unused&detail=full',
    'imports://.?importers&format=json', 'imports://.?importers=b.py&detail=full', 'imports://.?external&detail=full',
])
def test_imports_answers_where_its_controls_are_read(proj, uri):
    run, doc = _run(uri)
    assert run.returncode == 0, (run.returncode, run.stderr)
    assert not _unread(doc), doc.get('meta')


def test_imports_dot_still_draws_the_directory_importers(proj):
    run = _run_reveal_direct('imports://.?importers&format=dot')
    assert run.returncode == 0, run.stderr
    assert run.stdout.startswith('digraph modules {')


# --- a sibling noun on the same seam ------------------------------------------------------------------------------

def test_markdown_refuses_through_its_own_declaration(proj):
    """A sibling noun on the same seam (Markdown declares since group 2d)."""
    (proj / 'guide.md').write_text('# Guide\n\n[a](a.py)\n', encoding='utf-8')
    run, _doc = _run('markdown://.?view=links&limit=1')
    assert run.returncode == 2 and "control 'limit' is not read by this answer" in run.stderr, run.stderr
