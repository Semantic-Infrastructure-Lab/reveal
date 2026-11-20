"""BACK-2716 step 2: a bound request renders as the canonical request of each transport, and the rendering round-trips.

For each probe URI (an analysis-only scheme with a query) the bound request is rendered as the CLI line, the MCP
``reveal_run`` argv and the Python call; running each gives the JSON the URI form gives (only the echoed command
differs) and the same exit. The rendering reads the noun's declarations, so a control no flag spells fails here.
"""
import json
import shlex

import pytest

from conftest import _run_reveal_direct
from reveal.cli.routing.canonical import FORMS, render_request
from reveal.cli.routing.declared import declared_adapter_class
from reveal.utils.query_binding import prepare_declared_params

from test_declared_parity_back2053 import project  # noqa: F401  (the fixture)

# (noun, resource under the fixture project, URI query): the legacy words and repeats the retirement notes cover.
PROBES = [
    ('calls', 'proj', 'callers=serve'),
    ('calls', 'proj', 'callers=serve&depth=2'),
    ('calls', 'proj', 'rank=callers&top=5'),
    ('calls', 'proj', 'callees=serve&depth=2'),
    ('imports', 'proj', 'unused'),
    ('metrics', 'proj', 'hotspots=true'),
    ('patches', 'proj', 'limit=3'),
    ('markdown', 'proj', 'limit=2'),
]


def _bound(noun, query):
    adapter = declared_adapter_class(noun)
    return prepare_declared_params(adapter.PARAM_SPECS, query, 'uri')


def _json(run):
    return json.loads(run.stdout)


def _without_command(document):
    document = json.loads(json.dumps(document))
    if isinstance(document.get('execution'), dict):
        document['execution'].pop('command', None)
    for key in ('meta', 'metadata'):  # the note is the spelling's own, not the answer's (imports aliases metadata to meta)
        meta = document.get(key)
        if isinstance(meta, dict) and isinstance(meta.get('warnings'), list):
            meta['warnings'] = [w for w in meta['warnings'] if w.get('type') != 'retired_spelling']
    return document


def _uri_answer(noun, resource, query):
    return _run_reveal_direct(f'{noun}://{resource}?{query}', '--format', 'json', '--respect-gitignore=off')


@pytest.mark.parametrize('noun,resource,query', PROBES)
def test_the_cli_line_answers_as_the_uri_does(project, noun, resource, query):  # noqa: F811
    line = render_request('cli', noun, resource, _bound(noun, query))
    assert line.startswith(f'reveal {noun} {resource}')
    expected = _uri_answer(noun, resource, query)
    argv = shlex.split(line)[1:]
    actual = _run_reveal_direct(*argv, '--format', 'json', '--respect-gitignore=off')
    assert actual.returncode == expected.returncode
    assert _without_command(_json(actual)) == _without_command(_json(expected))


@pytest.mark.parametrize('noun,resource,query', PROBES)
def test_the_mcp_argv_is_the_cli_argv(project, noun, resource, query):  # noqa: F811
    bound = _bound(noun, query)
    argv = json.loads(render_request('mcp', noun, resource, bound).removeprefix('reveal_run(').removesuffix(')'))
    assert argv == shlex.split(render_request('cli', noun, resource, bound))[1:]


@pytest.mark.parametrize('noun,resource,query', PROBES)
def test_the_python_call_answers_as_the_uri_does(project, noun, resource, query):  # noqa: F811
    from reveal import api
    call = render_request('python', noun, resource, _bound(noun, query))
    assert call.startswith(f'api.query("{noun}", "{resource}"')
    expected = _json(_uri_answer(noun, resource, query))
    actual = eval(call, {'api': api})  # noqa: S307 (the rendering under test, with the one name it uses)
    assert _without_command(json.loads(json.dumps(actual, default=str))) == _without_command(expected)


def test_a_target_that_starts_with_a_dash_follows_the_double_dash():
    line = render_request('cli', 'calls', '-weird', _bound('calls', 'callers=serve'))
    assert shlex.split(line) == ['reveal', 'calls', '--callers', 'serve', '--', '-weird']


def test_a_value_that_starts_with_a_dash_stays_one_word():
    line = render_request('cli', 'calls', 'src', _bound('calls', 'callers=-x'))
    assert shlex.split(line) == ['reveal', 'calls', 'src', '--callers=-x']


def test_the_forms_are_the_three_transports():
    assert FORMS == ('cli', 'mcp', 'python')


def test_the_red_control_a_form_that_names_no_flag_fails_the_round_trip(project):  # noqa: F811
    line = render_request('cli', 'calls', 'proj', _bound('calls', 'callers=serve')).replace('--callers', '--no-such-flag')
    run = _run_reveal_direct(*shlex.split(line)[1:], '--format', 'json')
    assert run.returncode == 2


def test_a_plain_path_with_a_legacy_flag_says_no_request_note(project):  # noqa: F811
    """`reveal a.py --name X` runs an ast URI internally; the user typed none, so only the flag's own note is said."""
    run = _run_reveal_direct('proj/app.py', '--name', 'serve*')
    assert 'request is deprecated' not in run.stderr


def test_a_request_that_cannot_render_is_not_noted_and_keeps_its_own_error_answer(project):  # noqa: F811
    """The note renders after binding; a malformed control must reach the binder's answer (its own type), not turn
    into a generic invalid request because the note's rendering raised."""
    run = _run_reveal_direct('overview://proj?against=%FF', '--format', 'json')
    assert run.returncode == 2
    assert _json(run)['type'] == 'overview_diff'


def test_a_rejected_uri_request_does_not_recommend_the_command_it_spells(project):  # noqa: F811
    """`callers` with a ranking sort is refused (exit 2); the one note would recommend `reveal calls proj --callers serve
    --sort=-callers`, which fails the same way, so a rejected request says none."""
    run = _run_reveal_direct('calls://proj?callers=serve&sort=-callers', '--format', 'json')
    assert run.returncode == 2
    assert 'request is deprecated' not in run.stderr
    assert not [w for w in (_json(run).get('meta') or {}).get('warnings') or [] if w.get('field') == 'request:calls']


def test_the_request_note_marks_no_control_as_read(project):  # noqa: F811
    """Rendering the note must not hide the answer's own `control_unread_by_data` warning (patches on a tree with no
    tests): the URI and the subcommand agree besides the note."""
    uri = _run_reveal_direct('patches://proj?limit=0', '--format', 'json')
    sub = _run_reveal_direct('patches', 'proj', '--limit', '0', '--format', 'json')
    kinds = lambda run: sorted(w.get('type') for w in (_json(run).get('meta') or {}).get('warnings') or []  # noqa: E731
                               if w.get('type') != 'retired_spelling')
    assert kinds(uri) == kinds(sub)


def test_at_the_error_stage_a_uri_request_is_refused_before_it_runs(project, monkeypatch):  # noqa: F811
    """The cut turns the note to an error: exit 2 naming the flag form, the same text (BACK-2718)."""
    from reveal.cli import invocation
    monkeypatch.setattr(invocation, 'REQUEST_STAGE', 'error')
    run = _run_reveal_direct('calls://proj?callers=serve')
    assert run.returncode == 2
    assert 'reveal calls proj --callers serve' in run.stderr


def test_a_note_attached_to_an_answer_keeps_metadata_the_same_object_as_meta(project):  # noqa: F811
    """imports' `metadata` is an alias of `meta` (BACK-2601): attaching the request note rebuilds meta and must keep it."""
    from reveal import api
    answer = api.query(f'imports://{project}')
    assert any(w.get('field') == 'request:imports' for w in answer['meta']['warnings'])
    assert answer['metadata'] is answer['meta']
