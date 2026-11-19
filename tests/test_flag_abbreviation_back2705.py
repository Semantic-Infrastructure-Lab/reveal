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
import json

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
    (('claude://sessions', '--key', 'model'), '--key', 'the main parser\'s --keys'),
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


# Negative controls: full spellings, the attached-value form and short options answer as before.
FULL = [('ast://proj', '--limit', '1'), ('ast', 'proj', '--limit', '1'), ('ast', 'proj', '--limit=1'),
        ('metrics://proj', '--no-gitignore'), ('metrics', 'proj', '--no-gitignore'),
        ('metrics', 'proj', '--code-only'), ('ast://proj', '-q'), ('proj/app.py', 'serve', '--flow')]


@pytest.mark.parametrize('argv', FULL, ids=[' '.join(a) for a in FULL])
def test_a_full_spelling_still_answers(workspace, argv):  # noqa: F811
    run = _run(*argv)
    assert run.rc == 0, run.brief()
