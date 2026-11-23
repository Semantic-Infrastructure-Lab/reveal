"""Help prose names the current spelling (BACK-2713, D20; COMMAND_MODEL "Help").

The "Help" row of COMMAND_MODEL's cross-noun table hides every argument whose flags all retire (BACK-2755), and says
prose in a description or epilog that presents a legacy flag or a query string as current is rewritten in its noun's
teaching step. Conformance column 28 checks argument listings only, so this file is the guard for the prose: each row
names text a noun's ``--help`` (or the main parser's ``--help-all``) printed as current, which is gone, and the text
that replaces it, which is present. A parenthetical "(legacy ...)" naming the old spelling as legacy stays (BACK-2713
note #7); the controls below prove the check reads the live help.
"""
import pytest

from reveal.cli.parser import create_argument_parser
from reveal.cli.routing.declared import create_declared_parser, declared_adapter_class


@pytest.fixture(autouse=True)
def _one_line_per_help(monkeypatch):
    """argparse wraps help at the terminal width, which can split a fragment; a wide terminal keeps each on one line."""
    monkeypatch.setenv('COLUMNS', '10000')


def _flat(text):
    return ' '.join(text.split())


def _noun_help(noun):
    return _flat(create_declared_parser(noun).format_help())


def _calls_syntax():
    return _flat(declared_adapter_class('calls').get_help()['syntax'])


def _main_help():
    return _flat(create_argument_parser('test', full_help=True).format_help())


# (surface, reader, fragments that presented a legacy spelling as current, the replacement text)
ROWS = [
    ('calls epilog', lambda: _noun_help('calls'),
     ('--uncalled or --modules', 'calls://<path>?callers=NAME and the rest are the same request', '(?target=, ?root=)'),
     ('One mode per request: --callers, --callees or --sort. Two modes exit 2.',
      '(legacy --target, --root, --uncalled and --modules still answer, with a note naming the replacement)')),
    ('calls syntax (help://calls)', _calls_syntax,
     ('calls://<path>?callers=', 'calls://<path>?callees=', '| --uncalled | --modules'),
     ('reveal calls <path> --callers NAME [--depth N] [--format dot]',
      'reveal calls <path>:<function> # shorthand for --callers <function>')),
    ('calls --callers', lambda: _noun_help('calls'),
     ('calls://<path>:<name> is shorthand',),
     ('reveal calls <path>:<name> is shorthand',)),
    ('imports --detail', lambda: _noun_help('imports'),
     ('Legacy verbose and the global --verbose mean full',),
     ('JSON adds "verbose": true). The default, ranking, component and entry-point views refuse it',)),
    ('imports --scan-limit', lambda: _noun_help('imports'),
     ('Legacy max_files (--max-files)',),
     ('disclosed in metadata.scan_budget and as a warning, never silently partial',)),
    ('imports --scope', lambda: _noun_help('imports'),
     ('(?root=,', 'as imports:// resolved before'),
     ('(--root, .reveal.yaml root: true,', 'as imports resolved before')),
    ('imports --external', lambda: _noun_help('imports'),
     ('&tests=exclude drops test files',),
     ('--tests exclude drops test files',)),
    ('pack --detail', lambda: _noun_help('pack'),
     ('Legacy verbose and the global --verbose mean full',),
     ('normal, or full: adds the per-file token/line-count breakdown (JSON "verbose": true)',)),
    ('metrics exit codes', lambda: _noun_help('metrics'),
     ('1 with --hotspots,',),
     ('1 with --view hotspots, an analysed file',)),
    ('json epilog', lambda: _noun_help('json'),
     ('URI: json://FILE[/KEY]?where=EXPR&view=VIEW',),
     ('URI: json://FILE[/KEY] takes the same flags (--where EXPR --view VIEW)',)),
    ('claude epilog', lambda: _noun_help('claude'),
     ('One-string form: claude://session/NAME?view=messages&limit=3',),
     ('Resource form: claude://session/NAME --view messages --limit 3',)),
    ('claude --until/--word/--patches', lambda: _noun_help('claude'),
     ('Pairs with ?since=', 'Whole-word match for ?match=', '(?patches=true)'),
     ('Pairs with --since', 'Whole-word match for --match', '(--patches true)')),
    ('--output on a declared noun', lambda: _noun_help('claude'),
     ('With --stdin it needs --check',),
     ('a write that fails exits 3 with the answer printed and the other sinks written.',)),
    ('main --output', _main_help,
     (),
     ('With --stdin it needs --check and file paths only',)),
    ('main --verbose', _main_help,
     ('truncated summary for imports://',),
     ('all results instead of a truncated summary for imports)',)),
    ('main --hotspots', _main_help,
     ('Replaced by ?view=hotspots on metrics://', 'hotspot ranking to metrics://'),
     ('Replaced by reveal metrics PATH --view hotspots; still adds the hotspot ranking, with a note',)),
    ('main --code-only', _main_help,
     ('requires metrics:// adapter',),
     ('requires reveal metrics,',)),
]


@pytest.mark.parametrize('surface,reader,gone,present', ROWS, ids=[row[0] for row in ROWS])
def test_help_prose_names_the_current_spelling(surface, reader, gone, present):
    text = reader()
    assert [fragment for fragment in gone if fragment in text] == [], surface
    assert [fragment for fragment in present if fragment not in text] == [], surface


def test_a_parenthetical_legacy_line_stays():
    """Control: "(legacy ...)" naming the old spelling as legacy is not current-tense teaching (note #7)."""
    assert '(legacy --rank callers)' in _noun_help('calls')


def test_the_readers_see_the_live_help():
    """Control: each reader returns the help it names, so an absent fragment is a rewrite, not an empty read."""
    assert 'usage: reveal calls' in _noun_help('calls')
    assert 'reveal calls <path>' in _calls_syntax()
    assert '--help-all' in _main_help() and '--hotspots' in _main_help()
    assert 'Exit codes:' in _noun_help('metrics')
