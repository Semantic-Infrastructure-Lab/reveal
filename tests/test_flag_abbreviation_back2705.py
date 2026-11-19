"""A long option is spelled in full (BACK-2705): an abbreviation is an unknown option, exit 2, on the main parser and on
every declared noun's parser.

argparse accepts any unique prefix of a long option by default, so ``--lim`` was ``--limit`` and, on a URI request,
``--no-git`` was the main parser's ``--no-gitignore`` while ``reveal overview P --no-git`` was overview's retired
``no_git``: one token, two meanings, and a spelling no declaration names (COMMAND_MODEL "Spellings": aliases are only
declared spelling variants). One owner, ``JsonUsageParser``, the base of the main parser and of every declared parser,
turns prefixes off, so an abbreviation meets the same refusal as any unknown flag: rule 3's message naming the noun's
controls on a declared noun (URI and subcommand), argparse's unrecognized-arguments error elsewhere, and the
invalid-request JSON document in JSON mode.
"""
import argparse
import json
from pathlib import Path

import pytest

from reveal.cli.invocation import COMMANDS
from reveal.cli.parser import create_argument_parser
from reveal.cli.routing.declared import create_declared_parser
from test_vocabulary_conformance_back2654 import _run, workspace  # noqa: F401  (the conformance fixture)


@pytest.mark.parametrize('parser', ['main', *sorted(name for name, spec in COMMANDS.items() if spec.declared_adapter)])
def test_every_json_usage_parser_refuses_abbreviations(parser):
    built = create_argument_parser('') if parser == 'main' else create_declared_parser(parser)
    assert built.allow_abbrev is False, f'{parser}: argparse still expands a unique prefix of a long option'


# (argv, the abbreviation, what it expanded to before BACK-2705)
ABBREVIATED = [
    (('ast://proj', '--lim', '1'), '--lim', '--limit'),
    (('ast', 'proj', '--lim', '1'), '--lim', '--limit'),
    (('metrics://proj', '--no-git'), '--no-git', 'the main parser\'s --no-gitignore'),
    (('metrics', 'proj', '--no-git'), '--no-git', 'metrics\' --no-gitignore'),
    # After a declared URI the noun's own parser reads the flags (BACK-2673): --key is Claude's control there, so the
    # abbreviation is of Claude's own --since; the main parser's --keys is no longer an option after a Claude URI.
    (('claude://sessions', '--sinc', '2020-01-01'), '--sinc', 'Claude\'s --since'),
    (('metrics', 'proj', '--code'), '--code', 'metrics\' --code-only'),
]


@pytest.mark.parametrize('argv,abbreviation,expanded', ABBREVIATED, ids=[' '.join(a[0]) for a in ABBREVIATED])
def test_an_abbreviation_on_a_declared_noun_is_an_unknown_option(workspace, argv, abbreviation, expanded):  # noqa: F811
    run = _run(*argv)
    assert run.rc == 2, f'{run.brief()}: {abbreviation} was read as {expanded}'
    assert f"unsupported control '{abbreviation}'" in run.err, run.err  # rule 3's message, naming the noun's controls
    assert 'supported controls:' in run.err
    assert not run.out.strip()


@pytest.mark.parametrize('argv', [('ast://proj', '--lim', '1'), ('ast', 'proj', '--lim', '1')], ids=['URI', 'subcommand'])
def test_an_abbreviation_in_json_mode_answers_with_the_invalid_request_document(workspace, argv):  # noqa: F811
    run = _run(*argv, '--format', 'json')
    doc = json.loads(run.out) if run.out.strip().startswith('{') else {}
    assert run.rc == 2 and [e.get('code') for e in (doc.get('meta') or {}).get('errors') or []] == ['invalid_request'], \
        run.brief()
    assert "'--lim'" in doc.get('error', '')


@pytest.mark.parametrize('abbreviation', ['--outl', '--ifm', '--flowt', '--bound'])
def test_an_abbreviation_on_a_file_is_an_unknown_option(workspace, abbreviation):  # noqa: F811
    """The main parser on a path: the former navigation abbreviations (BACK-2364 pinned them as their full flags)."""
    run = _run('proj/app.py', 'serve', abbreviation)
    assert run.rc == 2, f'{run.brief()}: {abbreviation} was expanded to a full flag'
    assert f'unrecognized arguments: {abbreviation}' in run.err


def _with_subparsers(name, parser):
    """*parser* and every subcommand parser under it (``reveal dev``, ``reveal scaffold``), labelled."""
    yield name, parser
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub_name, sub in action.choices.items():
                yield from _with_subparsers(f'{name} {sub_name}', sub)


def _every_parser():
    """Every parser reveal builds at run time: the main parser, the global options parent, every subcommand's parser
    (declared nouns and the plain commands) with its own subparsers, and the MCP server's."""
    from reveal.cli.parser import _build_global_options_parser
    yield from _with_subparsers('main', create_argument_parser(''))
    yield 'global options parent', _build_global_options_parser()
    for name in sorted(COMMANDS):
        yield from _with_subparsers(name, COMMANDS[name].load()[0])
    from reveal.mcp_server import create_mcp_parser
    yield 'reveal-mcp', create_mcp_parser()


def test_every_parser_reveal_builds_refuses_abbreviations():
    pytest.importorskip('mcp')
    expands = [name for name, parser in _every_parser() if parser.allow_abbrev is not False]
    assert not expands, f'these parsers still expand a unique prefix of a long option: {expands}'


def test_no_module_builds_a_parser_outside_the_owner():
    """A new parser cannot miss the rule: every parser reveal builds is a ``RevealArgumentParser``
    (``reveal/cli/argparsing.py``), so no module constructs ``argparse.ArgumentParser`` itself."""
    import ast
    import reveal
    root = Path(reveal.__file__).parent
    owner = root / 'cli' / 'argparsing.py'
    found = []
    for path in sorted(root.rglob('*.py')):
        if path == owner:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            func = node.func if isinstance(node, ast.Call) else None
            name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
            if name == 'ArgumentParser':
                found.append(f'{path.relative_to(root).as_posix()}:{node.lineno}')
    assert not found, f'build parsers with reveal.cli.argparsing.RevealArgumentParser: {found}'


@pytest.mark.parametrize('argv,abbreviation', [(('check', 'proj', '--sel', 'B001'), '--sel'),
                                               (('review', 'proj', '--fail', 'none'), '--fail')])
def test_an_abbreviation_on_a_plain_command_is_an_unknown_option(workspace, argv, abbreviation):  # noqa: F811
    run = _run(*argv)
    assert run.rc == 2, f'{run.brief()}: {abbreviation} was expanded to a full flag'
    assert abbreviation in run.err


# Negative controls: full spellings, the attached-value form and short options answer as before.
FULL = [('ast://proj', '--limit', '1'), ('ast', 'proj', '--limit', '1'), ('ast', 'proj', '--limit=1'),
        ('metrics://proj', '--no-gitignore'), ('metrics', 'proj', '--no-gitignore'),
        ('metrics', 'proj', '--code-only'), ('ast://proj', '-q'), ('proj/app.py', 'serve', '--flow'),
        ('check', 'proj', '--select', 'B001')]


@pytest.mark.parametrize('argv', FULL, ids=[' '.join(a) for a in FULL])
def test_a_full_spelling_still_answers(workspace, argv):  # noqa: F811
    run = _run(*argv)
    assert run.rc == 0, run.brief()


@pytest.mark.parametrize('extra,flag', [(('--output', 'text', '--inputs'), '--inputs'),
                                        (('--state', '--effects'), '--effects')],
                         ids=['--output before --inputs', '--state before --effects'])
def test_the_depth_diagnostic_names_the_navigation_flag_typed_not_a_prefix_of_one(tmp_path, extra, flag):
    """The recursion-limit diagnostic (BACK-2529) names the element flag as typed. It matched every token that is a
    prefix of a navigation flag's name, a leftover of abbreviation support, so a full --output (outputs) or --state
    (statewrites) typed first was named as the flag that could not analyze the element."""
    from test_nav_deep_nesting_back2529 import DEEP, _nested_python, _run_deep
    source = _nested_python(tmp_path / 'deep.py', DEEP)
    result = _run_deep(str(source), 'f', *extra)
    assert result.returncode == 3, result.stderr[-300:]
    assert result.stderr.startswith(f'Error: {flag} could not analyze'), result.stderr[:160]
