"""BACK-2716 step 2: a bound request renders as the canonical request of each transport, and the rendering round-trips.

For each probe URI (an analysis-only scheme with a query) the bound request is rendered as the CLI line, the MCP
``reveal_run`` argv and the Python call; running each gives the JSON the URI form gives (only the echoed command
differs) and the same exit. The rendering reads the noun's declarations, so a control no flag spells fails here.
"""
import json
import shlex

import pytest

from conftest import _run_reveal_direct
from reveal.cli.routing import canonical
from reveal.cli.routing.canonical import FORMS
from reveal.cli.routing.declared import create_declared_parser, declared_adapter_class
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
    # Step 4: a walk control with no binding of its own (--all) and a store_false flag (--no-suppress).
    ('overview', 'proj', 'all=true'),
    ('patches', 'proj', 'suppress=false'),
]


def render_request(form, noun, target, params):
    return canonical.render_request(form, noun, target, params, parser=create_declared_parser(noun),
                                    adapter=declared_adapter_class(noun))


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
    # The URI answer below walks with --respect-gitignore=off; the call carries the same walk policy (overview's next
    # steps repeat it).
    call = canonical.render_request('python', noun, resource, _bound(noun, query), parser=create_declared_parser(noun),
                                    adapter=declared_adapter_class(noun), walk_policy=False)
    assert call.startswith(f'api.query("{noun}", "{resource}"') and "respect_gitignore='off'" in call
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


# --- step 4: what the all-probe column (rule 24) found in the renderer -----------------------------------------------

def _render_uri(form, noun, resource, query, walk_policy=None):
    adapter = declared_adapter_class(noun)
    return canonical.render_uri_request(form, noun, resource, _bound(noun, query), parser=create_declared_parser(noun),
                                        adapter=adapter, walk_policy=walk_policy)


def test_a_switch_is_given_on_or_off_and_never_its_opposite():
    """patches' --suppress on|off: ?suppress=false is `--suppress off` and ?suppress=true `--suppress on` (the former
    --no-suppress flag rendered the opposite request for true; BACK-2625 removed the last store_false flag)."""
    assert shlex.split(_render_uri('cli', 'patches', 'proj', 'suppress=false')) == ['reveal', 'patches', 'proj',
                                                                                      '--suppress', 'off']
    assert shlex.split(_render_uri('cli', 'patches', 'proj', 'suppress=true')) == ['reveal', 'patches', 'proj',
                                                                                     '--suppress', 'on']
    assert _render_uri('python', 'patches', 'proj', 'suppress=false') == 'api.query("patches", "proj", suppress=\'off\')'


def test_a_control_with_no_binding_of_its_own_is_its_shared_flag():
    """overview's ``all`` has no CLI binding of its own: the walk's --all reads it (it was dropped from the note)."""
    assert _render_uri('cli', 'overview', 'proj', 'all=true') == 'reveal overview proj --all'
    assert _render_uri('python', 'overview', 'proj', 'all=true') == 'api.query("overview", "proj", all=True)'


def test_a_uri_format_is_the_format_flag_of_the_cli_and_mcp_forms_only(project):  # noqa: F811
    """?format=json is --format json on the CLI and MCP; a Python answer is the JSON document, so its call has none."""
    line = _render_uri('cli', 'calls', 'proj', 'callers=serve&format=json')
    assert shlex.split(line) == ['reveal', 'calls', 'proj', '--callers', 'serve', '--format', 'json']
    assert '"--format", "json"' in _render_uri('mcp', 'calls', 'proj', 'callers=serve&format=json')
    assert _render_uri('python', 'calls', 'proj', 'callers=serve&format=json') == \
        'api.query("calls", "proj", callers=\'serve\')'
    uri = _run_reveal_direct('calls://proj?callers=serve&format=json')
    canonical_run = _run_reveal_direct(*shlex.split(line)[1:])
    assert canonical_run.returncode == uri.returncode
    uri_doc = _without_command(_json(uri))
    assert uri_doc.pop('_query_format') == 'json'  # the URI route's renderer-steering key, leaked into its JSON (filed)
    assert _without_command(_json(canonical_run)) == uri_doc


def test_a_dot_format_is_noted_as_its_format_flag(project):  # noqa: F811
    """calls:// answers ?format=dot (a Graphviz graph). It had no canonical form while the subcommand's --format offered
    no dot (no request note); --format dot is its flag form now (BACK-2722), so the note recommends it, and that command
    draws the same graph."""
    line = _render_uri('cli', 'calls', 'proj', 'callers=serve&format=dot')
    assert shlex.split(line) == ['reveal', 'calls', 'proj', '--callers', 'serve', '--format', 'dot']
    run = _run_reveal_direct('calls://proj?callers=serve&format=dot')
    assert run.returncode == 0 and 'digraph' in run.stdout
    assert f'request is deprecated and works until 1.0; use {line}.' in run.stderr
    canonical_run = _run_reveal_direct(*shlex.split(line)[1:])
    assert (canonical_run.returncode, canonical_run.stdout) == (run.returncode, run.stdout)


def test_the_walk_policy_a_uri_splits_off_is_repeated_as_its_flag(project):  # noqa: F811
    """Every URI entry point splits ?respect_gitignore= off before binding, so the note never saw it: the recommended
    command walked the ignored files away. With an ignored file the answers show it (the positive control: the
    policy changes this answer)."""
    (project / '.gitignore').write_text('ignored.py\n', encoding='utf-8')
    (project / 'ignored.py').write_text('def ignored():\n    return 1\n', encoding='utf-8')
    uri = _run_reveal_direct('metrics://proj?respect_gitignore=off', '--format', 'json')
    notes = [w['replacement'] for w in _json(uri)['meta']['warnings'] if w.get('field') == 'request:metrics']
    assert notes == ['reveal metrics proj --respect-gitignore off']
    canonical_run = _run_reveal_direct(*shlex.split(notes[0])[1:], '--format', 'json')
    assert _without_command(_json(canonical_run)) == _without_command(_json(uri))
    walked = _run_reveal_direct('metrics', 'proj', '--format', 'json')
    assert _without_command(_json(walked)) != _without_command(_json(uri))
    from reveal import api
    answer = api.query('metrics://proj?respect_gitignore=off')
    assert [w['replacement'] for w in answer['meta']['warnings'] if w.get('field') == 'request:metrics'] == [
        'api.query("metrics", "proj", respect_gitignore=\'off\')']


def test_a_request_giving_a_control_no_flag_spells_has_no_canonical_form():
    """git ?raw has no flag yet (BACK-2616): recommending the request without it recommended a different answer."""
    with pytest.raises(canonical.UnrenderableRequest):
        _render_uri('cli', 'git', 'proj/app.py', 'raw=true')


def test_a_flag_another_declaration_binds_is_not_the_controls_flag():
    """Claude's --tail is the flag-only row slice (tail_rows), not the legacy ?tail turn slice: no --tail for ?tail=2."""
    with pytest.raises(canonical.UnrenderableRequest):
        _render_uri('cli', 'claude', 'session/my-session', 'tail=2')


def test_api_query_of_a_uri_echoes_the_target_as_the_caller_named_it(project):  # noqa: F811
    """imports:// and metrics:// answered api.query with the absolute path the adapter resolved; the CLI's URI route
    and the noun form echo the caller's spelling (BACK-1366), so the note's Python call answered differently."""
    from reveal import api
    for noun in ('imports', 'metrics'):
        assert api.query(f'{noun}://proj')['source'] == 'proj' == api.query(noun, 'proj')['source']


def test_a_uri_format_a_typed_format_overrides_is_not_repeated(project):  # noqa: F811
    """With --format json typed, a URI's ?format=text lost to it: the note names the request without it, since repeating
    --format text beside the caller's --format json is a conflict (rule 18)."""
    run = _run_reveal_direct('calls://proj?callers=serve&format=text', '--format', 'json')
    assert [w['replacement'] for w in _json(run)['meta']['warnings'] if w.get('field') == 'request:calls'] == [
        'reveal calls proj --callers serve']
