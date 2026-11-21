"""BACK-2722: calls and imports ``?format=dot`` (Graphviz) has the flag form ``--format dot``.

The format query parameter retires into the global ``--format`` (COMMAND_MODEL one-vocabulary table, "Output format").
Before this task the subcommand's ``--format`` offered only the global text/json/typed/grep, so a URI request giving
``format=dot`` had no canonical command and said no request note (D20 gap). A noun that declares ``dot`` among its
output formats now offers it on its own ``--format``, and the typed value is that noun's format control, as the URI
spells it: the same graph where the view draws one, and the same exit 2 and message where it does not. Nouns that do
not declare ``dot``, and the path route, still reject it.
"""
import pytest

from conftest import _run_reveal_direct as run


@pytest.fixture
def calls_project(tmp_path, monkeypatch):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'app.py').write_text('def sink():\n    return 1\n\n\ndef middle():\n    return sink()\n\n\n'
                                 'def top():\n    return middle()\n\n\ndef orphan():\n    return 0\n', encoding='utf-8')
    (root / 'b.py').write_text('from app import top\n\n\ndef entry():\n    return top()\n', encoding='utf-8')
    monkeypatch.chdir(root)
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    return root


@pytest.fixture
def imports_project(tmp_path, monkeypatch):
    root = tmp_path / 'proj'
    for rel, text in {'pkg/__init__.py': '', 'pkg/a.py': 'import json\n', 'pkg/b.py': 'from pkg import a\n',
                      'main.py': 'from pkg import a\nfrom pkg import b\n'}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    monkeypatch.chdir(root)
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    return root


def _uri(scheme, project, controls):
    return f'{scheme}://{project.as_posix()}?{controls}'


def _same_outcome(uri_args, flag_args):
    """Both spellings answer with the same stdout and exit; a refusal names the same error."""
    old, new = run(*uri_args), run(*flag_args)
    assert (new.returncode, new.stdout) == (old.returncode, old.stdout), (new.stderr, old.stderr)
    return old, new


# Calls: the views that draw a graph (callers, a callees walk, modules) and the ones that do not.
CALLS_GRAPHS = [
    ('callers=sink', ('--callers', 'sink')),
    ('callees=top&depth=2', ('--callees', 'top', '--depth', '2')),
    ('modules', ('--modules',)),
]
CALLS_REFUSALS = [
    ('callees=top', ('--callees', 'top'), 'callees at depth 1 has none'),
    ('uncalled', ('--uncalled',), 'uncalled has none'),
    ('rank=callers', ('--sort=-callers',), "control 'format' is not read by this answer"),
]


@pytest.mark.parametrize('controls, flags', CALLS_GRAPHS, ids=[c for c, _ in CALLS_GRAPHS])
def test_calls_format_dot_flag_draws_the_uri_graph(calls_project, controls, flags):
    old, new = _same_outcome([_uri('calls', calls_project, f'{controls}&format=dot')],
                             ['calls', str(calls_project), *flags, '--format', 'dot'])
    assert new.returncode == 0 and new.stdout.startswith('digraph'), new.stderr


@pytest.mark.parametrize('controls, flags, reason', CALLS_REFUSALS, ids=[c for c, _, _ in CALLS_REFUSALS])
def test_calls_format_dot_flag_refuses_where_the_uri_refuses(calls_project, controls, flags, reason):
    old, new = _same_outcome([_uri('calls', calls_project, f'{controls}&format=dot')],
                             ['calls', str(calls_project), *flags, '--format', 'dot'])
    assert new.returncode == 2 and reason in old.stderr and reason in new.stderr, new.stderr


def test_calls_format_dot_flag_after_the_uri_is_the_same_request(calls_project):
    """A flag after a URI is the subcommand's flag (BACK-2673)."""
    _same_outcome([_uri('calls', calls_project, 'callers=sink&format=dot')],
                  [_uri('calls', calls_project, 'callers=sink'), '--format', 'dot'])


def test_calls_dot_uri_request_notes_its_flag_form(calls_project):
    """The request note recommends the canonical command, which now exists (it said none before)."""
    result = run(_uri('calls', calls_project, 'callers=sink&format=dot'))
    assert result.returncode == 0 and result.stdout.startswith('digraph')
    assert f'use reveal calls {calls_project.as_posix()} --callers sink --format dot' in result.stderr.replace(
        str(calls_project), calls_project.as_posix()), result.stderr


def test_calls_help_lists_dot():
    result = run('calls', '--help')
    assert '--format {text,json,dot}' in result.stdout


def test_imports_format_dot_flag_draws_the_uri_graph(imports_project):
    old, new = _same_outcome([_uri('imports', imports_project, 'importers&format=dot')],
                             ['imports', str(imports_project), '--importers', '--format', 'dot'])
    assert new.returncode == 0 and new.stdout.startswith('digraph modules'), new.stderr


def test_imports_format_dot_flag_refuses_where_the_uri_refuses(imports_project):
    old, new = _same_outcome([_uri('imports', imports_project, 'rank=fan-in&format=dot')],
                             ['imports', str(imports_project), '--sort=-fan-in', '--format', 'dot'])
    reason = "control 'format' is not read by this answer (fan_in_ranking"
    assert new.returncode == 2 and reason in old.stderr and reason in new.stderr, new.stderr


def test_imports_dot_uri_request_notes_its_flag_form(imports_project):
    result = run(_uri('imports', imports_project, 'importers&format=dot'))
    assert result.returncode == 0 and result.stdout.startswith('digraph modules')
    assert '--importers --format dot' in result.stderr, result.stderr


@pytest.mark.parametrize('argv', [
    ('ast', '.', '--format', 'dot'),          # a declared noun that renders no dot
    ('metrics', '.', '--format', 'dot'),
    ('app.py', '--format', 'dot'),            # the path route: the global --format is unchanged
], ids=lambda a: ' '.join(a))
def test_format_dot_stays_refused_where_no_noun_declares_it(calls_project, argv):
    result = run(*argv)
    assert result.returncode == 2 and 'dot' in result.stderr, result.stderr
    assert result.stdout == ''


# Shared owner (reveal/cli/routing/declared.py, formats.py): the declared parser's --format offers a format the noun
# declares beyond the presentation layer's own, and only that noun's parser does.

def _format_choices(parser):
    return next(action.choices for action in parser._actions if '--format' in action.option_strings)


def test_a_declared_format_beyond_the_presentation_layers_is_offered_by_that_nouns_parser_only(monkeypatch):
    from reveal.adapters.ast import AstAdapter
    from reveal.cli.routing.declared import create_declared_parser
    from reveal.cli.routing.formats import noun_formats
    global_choices = list(_format_choices(create_declared_parser('ast')))
    assert noun_formats(AstAdapter) == ()
    help_data = AstAdapter.get_help()
    monkeypatch.setattr(AstAdapter, 'get_help', staticmethod(
        lambda: {**help_data, 'output_formats': ['text', 'json', 'grep', 'svg']}))
    assert noun_formats(AstAdapter) == ('svg',)  # grep is the presentation layer's own
    assert list(_format_choices(create_declared_parser('ast'))) == [*global_choices, 'svg']
    assert list(_format_choices(create_declared_parser('metrics'))) == global_choices
