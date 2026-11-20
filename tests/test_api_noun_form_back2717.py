"""The Python API's noun form: api.query(NOUN, TARGET, **controls) is ``reveal NOUN TARGET --flags`` (BACK-2717, D20).

COMMAND_MODEL rule 2 (Scott 2026-11-19): the Python API takes typed keywords, the noun's target positional as on the
CLI. It runs the CLI's own declared dispatch, so the answer is the CLI's JSON document and a request the CLI exits 2
on raises with the CLI's message. These tests compare it with the CLI on every declared noun, then pin the failure
meaning, the keyword spelling and the targets a URI could not carry.
"""
import json
import sys

import pytest

from conftest import _run_reveal_direct
from test_declared_parity_back2053 import CASES, NOUNS, argv_for, project  # noqa: F401  (project is a fixture)
from reveal import api
from reveal.cli.invocation import COMMANDS
from reveal.cli.routing.declared import create_declared_parser, declared_adapter_class
from reveal.cli.routing.typed import typed_options
from reveal.errors import AnalysisFailedError, RequestValidationError, UnsupportedOverrideError


def _keywords(flags):
    """CASES flags (``['--callers', 'serve']``) as the API's keywords."""
    return {flag[2:].replace('-', '_'): value for flag, value in zip(flags[::2], flags[1::2])}


def _walk(noun):
    return declared_adapter_class(noun).RESOURCE_SPEC.walks


def _cli_json(*argv):
    cli = _run_reveal_direct(*argv, '--format', 'json')
    return cli.returncode, (json.loads(cli.stdout) if cli.stdout.strip() else None), cli.stderr


@pytest.fixture
def app(tmp_path, monkeypatch):
    (tmp_path / 'app.py').write_text(
        'import os\n\n\ndef process_order(order):\n    total = order["total"]\n    return total\n\n\n'
        'def main():\n    return process_order({"total": 1})\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize('noun', NOUNS)
def test_the_answer_is_the_clis_json_document_on_every_declared_noun(project, noun):  # noqa: F811
    argv = argv_for(noun, 'cli')
    walk = ['--respect-gitignore=off'] if _walk(noun) else []
    code, expected, stderr = _cli_json(*argv, *walk)
    assert code == 0, stderr
    assert expected.get('type'), 'an empty answer would compare equal vacuously'
    controls = _keywords(CASES[noun][0])
    if walk:
        controls['respect_gitignore'] = False
    assert api.query(noun, argv[1], **controls) == expected


def test_every_declared_control_has_a_keyword_read_from_the_nouns_parser():
    """The keyword set is the parser's long flags, never a typed table: each control a subcommand generates is one."""
    for noun, spec in sorted(COMMANDS.items()):
        adapter = declared_adapter_class(spec.declared_adapter) if spec.declared_adapter else None
        if adapter is None:
            continue
        options = typed_options(create_declared_parser(spec.declared_adapter), adapter)
        for control in adapter.PARAM_SPECS:
            if control.cli is None:
                continue
            flag = next(f for f in control.cli.flags if f.startswith('--'))
            assert options[flag[2:].replace('-', '_')][0] == flag, (noun, flag)


def test_a_flag_that_takes_no_value_takes_true_and_false_selects_nothing(app):
    code, expected, _ = _cli_json('imports', '.', '--unused')
    assert code == 0 and expected['type'] == 'unused_imports'
    assert api.query('imports', '.', unused=True) == expected
    assert api.query('imports', '.', unused=False) == api.query('imports', '.')


def test_a_repeatable_control_takes_a_list(app):
    code, expected, _ = _cli_json('ast', '.', '--where', 'lines>1', '--where', 'type=function')
    assert code == 0 and expected['results'], 'positive control: the filter keeps something'
    assert api.query('ast', '.', where=['lines>1', 'type=function']) == expected


def test_a_value_that_starts_with_a_dash_stays_the_value(app):
    code, expected, _ = _cli_json('ast', '.', '--sort=-lines', '--limit', '1')
    assert code == 0
    assert api.query('ast', '.', sort='-lines', limit=1) == expected


def test_an_omitted_target_is_the_nouns_default(app):
    assert api.query('calls', callers='main') == api.query('calls', '.', callers='main')


@pytest.mark.skipif(sys.platform == 'win32', reason="'?' is not a valid Windows file name character")
def test_a_target_keeps_every_character_a_uri_would_split_or_read_as_a_flag(app):
    for name in ('odd?name', '-dash'):
        (app / name).mkdir()
        (app / name / 'mod.py').write_text('def f():\n    return 1\n', encoding='utf-8')
        answer = api.query('ast', name)
        assert [row['name'] for row in answer['results']] == ['f'], name


def test_a_retired_noun_notes_as_its_subcommand_does(app):
    code, expected, _ = _cli_json('trace', '.', '--from', 'main')
    assert code == 0
    answer = api.query('trace', '.', **{'from': 'main'})
    assert answer == expected
    assert any(w.get('code') == 'retired_spelling' for w in answer['meta']['warnings'])


def test_a_legacy_flag_keyword_notes_as_its_flag_does(app):
    code, expected, _ = _cli_json('metrics', '.', '--summary-only')
    assert code == 0
    answer = api.query('metrics', '.', summary_only=True)
    assert answer == expected
    assert any(w.get('code') == 'retired_spelling' for w in answer['meta']['warnings'])


@pytest.mark.parametrize('noun,target,controls,exception', [
    ('calls', '.', {'callers': 'no_such_fn'}, RequestValidationError),   # a target that matches nothing
    ('calls', 'no_such_dir', {'callers': 'main'}, RequestValidationError),  # a path that does not exist
    ('ast', '.', {'limit': 'x'}, RequestValidationError),                 # a value the control rejects
    ('imports', '.', {'detail': 'nope'}, RequestValidationError),         # a value outside the choices
    ('metrics', '.', {'top': 1}, RequestValidationError),                 # a control this answer does not read
    ('metrics', '.', {'top': 1, 'limit': 2}, RequestValidationError),     # two spellings of one control
])
def test_a_request_the_cli_exits_2_on_raises_with_the_clis_message(app, capsys, noun, target, controls, exception):
    flags = [word for key, value in controls.items() for word in (f"--{key.replace('_', '-')}", str(value))]
    code, document, stderr = _cli_json(noun, target, *flags)
    assert code == 2, stderr
    capsys.readouterr()
    with pytest.raises(exception) as raised:
        api.query(noun, target, **controls)
    message = str(raised.value)
    assert message in stderr or (document is not None and message == document['meta']['errors'][0]['message'])
    out, err = capsys.readouterr()
    assert (out, err) == ('', ''), 'nothing prints: not the answer, not the ledger\'s unused-flag notes'


@pytest.mark.parametrize('noun', ['pack', 'json'])
def test_a_usage_error_from_the_nouns_own_parser_raises_and_prints_nothing(app, capsys, noun):
    """The parser's own errors (a required target missing) reach the caller as its message, not as an exit."""
    cli = _run_reveal_direct(noun)
    assert cli.returncode == 2 and 'required: path' in cli.stderr
    capsys.readouterr()
    with pytest.raises(RequestValidationError, match='the following arguments are required: path'):
        api.query(noun)
    assert capsys.readouterr() == ('', '')


@pytest.mark.parametrize('keyword', ['nope', 'format', 'output', 'fail_on', 'copy', 'provenance', 'help'])
def test_a_keyword_that_names_no_request_control_is_the_unsupported_control_error(app, keyword):
    with pytest.raises(UnsupportedOverrideError) as raised:
        api.query('calls', '.', callers='main', **{keyword: 'json'})
    assert isinstance(raised.value, TypeError)
    assert f"unsupported control '{keyword}'" in str(raised.value) and 'callers' in str(raised.value)


def test_a_single_value_control_given_several_values_is_refused_before_anything_runs(app):
    with pytest.raises(RequestValidationError, match='limit takes one value'):
        api.query('ast', '.', limit=[1, 2])


@pytest.mark.parametrize('word,match', [
    ('codex', r"no subcommand: name the resource by its URI, query\('codex://"),
    ('frobnicate', r'neither a noun nor a URI\. Nouns: .*calls'),
])
def test_a_word_that_is_not_a_noun_names_what_to_use(word, match):
    with pytest.raises(ValueError, match=match):
        api.query(word)


@pytest.mark.skipif(sys.platform == 'win32', reason='chmod 000 does not deny reads on Windows')
def test_an_incomplete_answer_returns_marked_and_a_failed_one_raises_with_the_clis_document(app):
    import os
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        pytest.skip('root reads a chmod 000 file')
    locked = app / 'locked.py'
    locked.write_text('def g():\n    return 2\n', encoding='utf-8')
    locked.chmod(0)
    try:
        code, expected, _ = _cli_json('metrics', '.')
        assert code == 3
        answer = api.query('metrics', '.')
        assert answer == expected
        assert any(w.get('type') == 'analysis_incomplete' for w in answer['meta']['warnings'])
        code, expected, _ = _cli_json('calls', '.', '--callers', 'main')
        assert code == 3  # calls fails the query on a failed read (plan section 2.1)
        with pytest.raises(AnalysisFailedError, match='locked.py') as raised:
            api.query('calls', '.', callers='main')
        assert raised.value.result == expected
    finally:
        locked.chmod(0o644)


def test_each_call_is_one_host_request_so_an_edit_between_calls_is_seen(app):
    assert [c['caller'] for c in api.query('calls', '.', callers='process_order')['levels'][0]['callers']] == ['main']
    source = (app / 'app.py').read_text(encoding='utf-8')
    (app / 'app.py').write_text(source + '\n\ndef audit():\n    return process_order({"total": 2})\n', encoding='utf-8')
    callers = api.query('calls', '.', callers='process_order')['levels'][0]['callers']
    assert sorted(c['caller'] for c in callers) == ['audit', 'main']


def test_the_uri_form_is_unchanged(app):
    """A resource URI and the older query spelling still answer through the URI path, with its element argument."""
    answer = api.query('calls://.?callers=process_order')
    assert answer['type'] == 'calls_query'
    with pytest.raises(RequestValidationError):
        api.query('calls://.', 'process_order')  # a declared noun reads no element (BACK-2687)
