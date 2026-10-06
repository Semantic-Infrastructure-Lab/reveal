"""The command line is parsed once, into an Invocation (reveal/cli/invocation.py, BACK-1058).

Everything below the entry point asks the Invocation instead of re-reading ``sys.argv``.
scripts/check_boundaries.py ('argv') keeps it that way.
"""
import json

import pytest

from reveal.cli.invocation import COMMANDS, Invocation, current_invocation, invocation_scope

pytestmark = pytest.mark.component


# ------------------------------------------------------------------ the subcommand name

@pytest.mark.parametrize('argv, command, command_argv', [
    (['reveal', 'overview', '.'], 'overview', ['.']),
    (['reveal', '--format', 'json', 'overview', '.'], 'overview', ['--format', 'json', '.']),
    (['reveal', '--format=json', 'check', 'x'], 'check', ['--format=json', 'x']),
    (['reveal', '-q', '--also-json', 'out.json', 'check', 'x'], 'check',
     ['-q', '--also-json', 'out.json', 'x']),
    (['reveal', 'file.py'], None, ['file.py']),
    (['reveal', 'ast://.'], None, ['ast://.']),
    (['reveal', './overview'], None, ['./overview']),
    # A value, not a name: --also-json takes one.
    (['reveal', '--also-json', 'overview', 'file.py'], None, ['--also-json', 'overview', 'file.py']),
    # Only global options may precede the name; after any other it is a path.
    (['reveal', '--depth', '2', 'overview'], None, ['--depth', '2', 'overview']),
    (['reveal', '--', 'overview'], None, ['--', 'overview']),
    (['reveal'], None, []),
])
def test_command_detection(argv, command, command_argv):
    inv = Invocation.parse(argv)
    assert inv.command == command
    assert inv.command_argv == command_argv


def test_every_command_loads_its_parser_and_runner():
    from argparse import ArgumentParser
    for name, spec in COMMANDS.items():
        parser, runner = spec.load()
        assert isinstance(parser, ArgumentParser) and callable(runner), name


# ------------------------------------------------------------------ normalization

def test_perf_is_taken_out_for_any_command():
    inv = Invocation.parse(['reveal', 'trace', 'x', '--perf'])
    assert inv.perf and '--perf' not in inv.argv and inv.command == 'trace'


def test_perf_after_double_dash_is_a_positional():
    inv = Invocation.parse(['reveal', '--', '--perf'])
    assert not inv.perf and inv.argv == ('--', '--perf')


def test_descending_sort_is_joined():
    assert Invocation.parse(['reveal', 'ast://.', '--sort', '-complexity']).argv == (
        'ast://.', '--sort=-complexity')
    # A real flag after --sort is left for argparse to report.
    assert Invocation.parse(['reveal', 'x', '--sort', '--limit']).argv == ('x', '--sort', '--limit')


def test_bare_ignores_perf():
    assert Invocation.parse(['reveal']).bare
    assert Invocation.parse(['reveal', '--perf']).bare
    assert not Invocation.parse(['reveal', '--help']).bare


# ------------------------------------------------------------------ typed options

@pytest.mark.parametrize('argv, expected', [
    (['reveal', 'x', '--format', 'json'], True),
    (['reveal', 'x', '--format=json'], True),
    (['reveal', 'x', '--formats'], False),
    (['reveal', 'x'], False),
    (['reveal', '--', '--format'], False),
])
def test_typed(argv, expected):
    assert Invocation.parse(argv).typed('--format') is expected


# ------------------------------------------------------------------ the current invocation

def test_scope_publishes_and_restores():
    outer, inner = Invocation.parse(['reveal', 'a']), Invocation.parse(['reveal', 'b'])
    assert current_invocation() is None
    with invocation_scope(outer):
        with invocation_scope(inner):
            assert current_invocation() is inner
        assert current_invocation() is outer
    assert current_invocation() is None


def test_provenance_names_the_invocation_not_the_host_process(monkeypatch):
    from reveal.utils.provenance import build_execution_provenance

    monkeypatch.setattr('sys.argv', ['/usr/bin/some-host'])
    with invocation_scope(Invocation.parse(['reveal', 'ast://.', '--provenance'])):
        assert build_execution_provenance()['command'] == 'reveal ast://. --provenance'
    # Outside any invocation (a library call) the host's command line is all there is.
    assert build_execution_provenance()['command'] == '/usr/bin/some-host'  # noqa: win-path (argv[0] string)


def test_mcp_provenance_names_the_equivalent_cli_command(monkeypatch, tmp_path):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query

    (tmp_path / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    monkeypatch.setattr('sys.argv', ['/usr/bin/reveal-mcp'])
    out = json.loads(reveal_query(f'ast://{tmp_path}', provenance=True))
    assert out['execution']['command'] == f'reveal ast://{tmp_path} --format json --provenance'
