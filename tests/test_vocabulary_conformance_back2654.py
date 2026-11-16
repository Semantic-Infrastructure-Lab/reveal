"""Cross-noun vocabulary conformance (BACK-2654): COMMAND_MODEL's rule table, measured on every declared noun.

COMMAND_MODEL_2026-11-09.md, "Cross-noun rules and conformance", decides a rule once for every noun; this file
checks rules 1-4 of that table on every declared noun (a subcommand in ``COMMANDS`` or a ``BOUND_QUERY_CALL``
scheme). Each probe is generated from the declarations (``PARAM_SPECS``, ``CLI_QUERY_FLAGS``, ``FLAG_SPECS``,
``RETIREMENTS``) and run per noun; the probes hold no per-noun expectations, only the recorded matrix does.

  1a  conflicting values, URI and global flag: ``noun://T?key=A --flag B`` exits 2 naming both; ``key=A --flag A``
      answers as ``key=A`` alone.
  1b  conflicting values, alias and name (URI, and subcommand flags where both have one): exit 2 naming both;
      equal values answer as the name alone.
  2   retirement notes: each supported legacy spelling (a ``note`` row of RETIREMENTS) answers with its note on
      CLI text, CLI JSON, ``api.query`` and the MCP query tool.
  3   unsupported controls: a shared control the noun does not declare exits 2 naming the noun's supported
      controls, as a URI key, a subcommand flag and a global flag reaching the URI.
  4   detail: global ``--verbose`` is ``--detail full``; where the request has no full level it exits 2 naming
      the levels.

Columns added with Scott's 2026-11-16 rulings (the table's rows "Conflicting values" through "Detail"):

  1c  the same scalar spelling given twice: different values exit 2 naming both, equal values answer once
      (URI ``?k=a&k=b`` and subcommand ``--k=a --k=b``; no last-wins).
  1d  a repeatable control's aliases accumulate: ``?match=a&body-contains=b`` answers as ``?match=a&match=b``,
      on the URI and the subcommand.
  3b  unknown keys: a key that is neither a declared control nor a field exits 2 naming the supported controls.
  5   legacy spellings: each note-stage ``param:`` row of RETIREMENTS is declared once on the noun, as an alias or
      a ``legacy`` entry of the canonical control it replaces (rows whose replacement is another scheme are
      reported, not cells).
  6   aliases: a different word carries a RETIREMENTS row and its note on every transport; a spelling-only
      variant and the D18-deferred rows (AST ``show``, Git ``type``) are note-free.
  8a  bare shared-control keys on a ``where`` noun are that control (or a declared legacy spelling with its
      note), never a field filter.
  8b  bare field filters on a ``where`` noun: ``?FIELD=VALUE`` and ``?FIELD OP VALUE`` answer as ``?where=...``.

A cell is ``conforms`` (asserted), ``not_yet`` (recorded below with the behaviour observed; the count may only
fall and must reach zero before the cut) or ``exempt`` (a written reason; the probe must find nothing to run).
A cell that starts to conform fails until it is removed from NOT_YET and NOT_YET_BASELINE is lowered, the
ratchet pattern of scripts/check_boundaries.py. To print the measured matrix, run this file with
REVEAL_CONFORMANCE_REPORT=<path>: each cell appends one JSON line (state, case count, failing evidence).
"""
import json
import os
import re
from dataclasses import dataclass

import pytest

from conftest import _run_reveal_direct
from test_declared_parity_back2053 import APP, CASES
from test_retirements_back2066 import PRODUCTION_CASES, SOURCE
from reveal.adapters.base import get_adapter_class, list_supported_schemes
from reveal.adapters.factory import uses_bound_query_call
from reveal.cli.invocation import COMMANDS, RETIREMENTS
from reveal.cli.routing.declared import create_declared_parser, declared_adapter_class
from reveal.cli.routing.flag_specs import FLAG_SPECS


def _declared_nouns():
    subcommands = {name for name, spec in COMMANDS.items() if spec.declared_adapter}
    bound = {scheme for scheme in list_supported_schemes() if uses_bound_query_call(get_adapter_class(scheme))}
    return sorted(subcommands | bound)


NOUNS = _declared_nouns()
RULES = ('1a', '1b', '1c', '1d', '2', '3', '3b', '4', '5', '6', '8a', '8b')

# The request each noun answers by default: the parity gate's table (CLI argv after the noun, URI suffix), plus
# the two declared nouns it has no row for. None: no subcommand (codex is URI-only; stats is metrics' retired scheme).
BASE = {**CASES, 'stats': (None, ''), 'codex': (None, '')}
# Targets that are not the fixture project directory.
TARGETS = {'claude': 'sessions', 'codex': '', 'json': 'proj/data.json'}

# The shared controls of COMMAND_MODEL section 1 rule 3, each with a value a supporting noun would accept.
# Left out: view (the deferred row, D18), format/output (global presentation), head/tail/range (path reads only)
# and max-entries/dir-limit (directory reads only).
SHARED_CONTROLS = {'limit': '1', 'offset': '1', 'sort': 'name', 'where': 'lines>1', 'match': 'x', 'detail': 'full',
                   'kind': 'function', 'depth': '1', 'tests': 'exclude', 'since': '2020-01-01',
                   'until': '2030-01-01', 'against': 'HEAD'}

# --- the recorded matrix -----------------------------------------------------------------------------------

# Cells with nothing to probe; the test proves the probe finds no case, so a new alias or retirement row
# turns the exemption into a failure.
_NO_ALIAS = 'declares no aliased control: there is no alias and name to give twice'
_NO_LEGACY = 'no note-stage RETIREMENTS row spells this noun: there is no legacy spelling to note'
EXEMPT = {
    **{(noun, '1b'): _NO_ALIAS for noun in ('architecture', 'claude', 'codex', 'contracts', 'deps', 'hotspots', 'json',
                                            'overview', 'pack', 'patches', 'surface', 'testability', 'trace')},
    **{(noun, '2'): _NO_LEGACY for noun in ('codex', 'contracts', 'git', 'json', 'markdown', 'overview', 'pack',
                                            'patches', 'surface')},
    **{(noun, '1d'): 'declares no repeatable control with an alias'
       for noun in NOUNS if noun not in ('markdown', 'stats')},
    **{(noun, '5'): 'no note-stage param: row whose replacement is a control of this noun' for noun in (
        'architecture', 'ast', 'codex', 'contracts', 'deps', 'git', 'hotspots', 'json', 'markdown', 'overview', 'pack',
        'patches', 'surface', 'testability', 'trace')},
    **{(noun, '6'): 'declares no alias: nothing to note or keep note-free' for noun in (
        'architecture', 'claude', 'codex', 'contracts', 'deps', 'hotspots', 'json', 'overview', 'pack', 'patches',
        'surface', 'testability', 'trace')},
    **{(noun, '8a'): 'no where expression: a bare key is never read as a field (claude\'s where is a name predicate)'
       for noun in ('architecture', 'calls', 'claude', 'codex', 'contracts', 'deps', 'hotspots', 'imports', 'overview',
                    'pack', 'patches', 'surface', 'testability', 'trace')},
    **{(noun, '8b'): 'declares no where control: there are no field filters' for noun in (
        'architecture', 'calls', 'codex', 'contracts', 'deps', 'hotspots', 'imports', 'overview', 'pack', 'patches',
        'surface', 'testability', 'trace')},
}

# Rules 1, 2, 5 and 6 are the shared seams' defaults (Scott 2026-11-16; BACK-2654 Step 3): their cells must conform
# on every noun, and none may be recorded below.
DEFAULT_NOW = ('1a', '1b', '1c', '1d', '2', '5', '6')
# Rule 9: the retired stats:// scheme is exempt (deleted at the cut); metrics' cells measure the owner it shares.
RULED_EXEMPT_NOUNS = {'stats': 'rule 9: the retired stats:// scheme is deleted at the cut; metrics:// is measured'}

# Cells that do not conform yet: (noun, rule) -> the behaviour observed at fac0718b. May only shrink; every
# entry reaches zero before the cut.
NOT_YET = {
    ('architecture', '3'): 'URI limit, offset, sort, where, match, detail, kind, depth, since, until: exit 0; '
                           'subcommand offset, sort, where, match, detail, kind, depth, since, until: argparse '
                           'error; global --limit, --sort, --since, --until on the URI: exit 0',
    ('ast', '3'): 'URI match, detail, depth, tests, since, until, against: exit 0 (bare keys become where fields); '
                  'subcommand match, detail, depth, tests, since, until, against: argparse error; global --since, '
                  '--until on the URI: exit 0',
    ('calls', '3'): 'URI tests, against: exit 0; URI offset, where, match, since, until: exit 2 without the '
                    'supported controls; subcommand offset, where, match, tests, since, until, against: argparse '
                    'error; global --since, --until on the URI: exit 0',
    ('claude', '3'): 'URI kind, depth, tests, against: exit 0; subcommand kind, depth, tests, against: argparse '
                     'error',
    ('codex', '3'): 'URI limit, offset, sort, where, match, detail, kind, depth, tests, against: exit 0; global '
                    '--limit, --sort on the URI: exit 0 (no subcommand)',
    ('contracts', '3'): 'all 12 shared controls: URI exit 0, subcommand argparse error; global --limit, --sort, '
                        '--since, --until on the URI: exit 0',
    ('deps', '3'): 'all 12 shared controls: URI exit 0, subcommand argparse error; global --limit, --sort, --since, '
                   '--until on the URI: exit 0',
    ('git', '3'): 'URI match, kind, depth, tests, against: exit 0; subcommand match, kind, depth, tests, against: '
                  'argparse error',
    ('hotspots', '3'): 'all 12 shared controls: URI exit 0, subcommand argparse error; global --sort, --since, '
                       '--until on the URI: exit 0',
    ('imports', '3'): 'URI against: exit 0; subcommand offset, where, match, kind, depth, since, until, against: '
                      'argparse error (the URI names the supported controls); global --since, --until on the URI: '
                      'exit 0',
    ('json', '3'): 'URI match, kind, depth, tests, since, until, against: exit 0; subcommand the same seven: '
                   'argparse error; global --since, --until on the URI: exit 0',
    ('markdown', '3'): 'URI detail, kind, depth, tests, since, until, against: exit 0; subcommand the same seven: '
                       'argparse error; global --since, --until on the URI: exit 0',
    ('metrics', '3'): 'URI against: exit 0; subcommand against: argparse error; global --until on the URI: exit 0 '
                      '(match, kind, depth, until are declared to reject; against is not in that list)',
    ('overview', '3'): 'URI limit, offset, sort, where, match, detail, kind, depth, since, until: exit 0; '
                       'subcommand offset, sort, where, match, detail, kind, depth, since, until: argparse error; '
                       'global --limit, --sort, --since, --until on the URI: exit 0',
    ('pack', '3'): 'URI limit, offset, sort, where, match, detail, kind, depth, tests, until, against: exit 0; '
                   'subcommand the same eleven: argparse error; global --limit, --sort, --since, --until on the '
                   'URI: exit 0',
    ('patches', '3'): 'URI offset, sort, where, match, detail, kind, depth, since, until, against: exit 0; '
                      'subcommand the same ten: argparse error; global --sort, --since, --until on the URI: exit 0',
    ('surface', '3'): 'URI limit, offset, sort, where, match, detail, kind, tests, since, until, against: exit 0; '
                      'subcommand the same eleven: argparse error; global --limit, --sort, --since, --until on the '
                      'URI: exit 0',
    ('testability', '3'): 'URI limit, offset, sort, where, match, detail, kind, depth, since, until, against: exit '
                          '0; subcommand the same eleven: argparse error; global --sort, --since, --until on the '
                          'URI: exit 0',
    ('trace', '3'): 'URI limit, offset, sort, where, match, detail, kind, tests, since, until, against: exit 0; '
                    'subcommand the same eleven: argparse error; global --limit, --sort, --since, --until on the '
                    'URI: exit 0',
    ('architecture', '4'): 'no detail declaration; --verbose is its own verbose control (expanded sections), exit 0',
    ('ast', '4'): 'no detail declaration; --verbose: "has no effect" note, exit 0',
    ('calls', '4'): 'the callers view rejects detail=full (exit 2) but --verbose answers with a "has no effect" '
                    'note, exit 0',
    ('claude', '4'): 'the sessions listing rejects detail=full (exit 2) but --verbose answers silently, exit 0',
    ('codex', '4'): 'no detail declaration; --verbose: "has no effect" note, exit 0',
    ('contracts', '4'): 'no detail declaration; --verbose: "has no effect" note, exit 0',
    ('deps', '4'): 'no detail declaration; --verbose accepted silently, exit 0',
    ('hotspots', '4'): 'no detail declaration; --verbose accepted silently, exit 0',
    ('json', '4'): 'the default view rejects detail=full (flatten only, exit 2) but --verbose answers with a "has '
                   'no effect" note, exit 0',
    ('markdown', '4'): 'no detail declaration; --verbose: "has no effect" note, exit 0',
    ('metrics', '4'): 'levels normal|summary; --verbose: "has no effect" note, exit 0 (kept by BACK-2621 for this '
                      'package)',
    ('overview', '4'): 'no detail declaration; --verbose is its own verbose control (expanded sections), exit 0',
    ('pack', '4'): 'no detail declaration; --verbose is its own verbose control, exit 0',
    ('patches', '4'): 'no detail declaration; --verbose: "has no effect" note, exit 0',
    ('surface', '4'): 'no detail declaration; --verbose: "has no effect" note, exit 0',
    ('testability', '4'): 'no detail declaration; --verbose accepted silently, exit 0',
    ('trace', '4'): 'no detail declaration; --verbose: "has no effect" note, exit 0',
    ('codex', '3b'): '?zz-unknown=1: warned and ignored, exit 0 (no subcommand)',
    ('ast', '3b'): '?zz-unknown=1 is read as a where field: a zero-row answer, exit 0; subcommand: argparse error',
    ('ast', '8a'): 'bare match, detail, depth, tests, since, until, against are read as where fields, exit 0 (depth '
                   'is nesting depth, with no note)',
    ('git', '8a'): 'bare match, kind, depth, tests, against: exit 0',
    ('json', '8a'): 'bare match, kind, depth, tests, since, until, against: exit 0',
    ('markdown', '8a'): 'bare detail, kind, depth, tests, since, until, against: exit 0',
    ('metrics', '8a'): 'bare against: exit 0 (match, kind, depth, until reject)',
    ('claude', '8b'): '?session~=session is warned unknown and ignored; ?where=session~=session filters',
    ('metrics', '8b'): '?lines=5 is warned unknown and ignored; ?where=lines=5 filters (?lines>10 already filters)',
    ('architecture', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('calls', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('claude', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('contracts', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('deps', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('git', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('hotspots', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('imports', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('json', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('markdown', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('metrics', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('overview', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('pack', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('patches', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('surface', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('testability', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
    ('trace', '3b'): '?zz-unknown=1: warned and ignored, exit 0; subcommand --zz-unknown: argparse error',
}

NOT_YET_BASELINE = {'1a': 0, '1b': 0, '1c': 0, '1d': 0, '2': 0, '3': 19, '3b': 19, '4': 17, '5': 0, '6': 0,
                    '8a': 5, '8b': 2}


# --- the fixture -------------------------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """The parity gate's project (code, tests, JSON, one git commit), Claude and Codex homes, and the
    retirement cases' sample file in a directory of its own."""
    from claude_session_fixture import build_claude_home
    from codex_session_fixture import build_codex_home
    monkeypatch.chdir(tmp_path)
    claude_adapter = declared_adapter_class('claude')
    claude = build_claude_home(tmp_path / 'home')
    monkeypatch.setattr(claude_adapter, 'CLAUDE_HOME', claude)
    monkeypatch.setattr(claude_adapter, 'CONVERSATION_BASE', claude / 'projects')
    codex_adapter = get_adapter_class('codex')
    codex = build_codex_home(tmp_path / 'codex-home')
    monkeypatch.setattr(codex_adapter, 'CODEX_HOME', codex)
    monkeypatch.setattr(codex_adapter, 'CODEX_DB', codex / 'state_5.sqlite')
    root = tmp_path / 'proj'
    (root / 'tests').mkdir(parents=True)
    (root / 'app.py').write_text(APP, encoding='utf-8')
    (root / 'data.json').write_text('{"items": [1, 2]}', encoding='utf-8')
    (root / 'rows.json').write_text('[{"name": "a", "n": 1}, {"name": "b", "n": 2}]', encoding='utf-8')
    (root / 'guide.md').write_text('---\ntitle: Guide\nn: 3\n---\n# Guide\n\nBody text.\n', encoding='utf-8')
    (root / 'tests' / 'test_app.py').write_text(
        'from app import serve\n\n\ndef test_serve():\n    assert serve("") is None\n', encoding='utf-8')
    import pygit2
    repo = pygit2.init_repository(str(root))
    for file in ('app.py', 'data.json', 'tests/test_app.py'):
        repo.index.add(file)
    repo.index.write()
    signature = pygit2.Signature('Fixture', 'fixture@example.com', 1700000000, 0)
    repo.create_commit('HEAD', signature, signature, 'fixture', repo.index.write_tree(), [])
    sample = tmp_path / 'sample' / 'sample.py'
    sample.parent.mkdir()
    sample.write_text(SOURCE, encoding='utf-8')
    return sample


# --- requests ----------------------------------------------------------------------------------------------

def _adapter(noun):
    return declared_adapter_class(noun) if noun in COMMANDS else get_adapter_class(noun)


def _specs(noun):
    """The noun's declared controls; a spec declared only to reject a shared control is not one."""
    return [spec for spec in _adapter(noun).PARAM_SPECS if spec.role != 'unsupported']


def _spec_for(noun, key):
    return next((spec for spec in _specs(noun) if key in (spec.name, *spec.aliases)), None)


def _uri(noun, *pairs, base=True):
    """The noun's default URI plus *pairs*; ``base=False`` drops its default operation (an operation control
    under test would otherwise be a second mode)."""
    query = BASE[noun][1].lstrip('?') if base else ''
    parts = [part for part in (query, *pairs) if part]
    return f'{noun}://{TARGETS.get(noun, "proj")}' + ('?' + '&'.join(parts) if parts else '')


def _sub(noun, *extra, base=True):
    """The subcommand argv, or None when the noun has no subcommand."""
    cli = BASE[noun][0]
    return None if cli is None else [noun, TARGETS.get(noun, 'proj'), *(cli if base else ()), *extra]


@dataclass(frozen=True)
class Run:
    argv: tuple
    rc: object  # the exit code, or 'crash' when reveal raised out of main()
    out: str
    err: str

    def says(self, *words):
        return all(word in self.err for word in words)

    def brief(self):
        lines = [line.strip() for line in self.err.splitlines()
                 if line.strip() and not line.startswith(('usage:', ' '))]
        plain = next((line for line in lines if not line.startswith('note:')), '')
        first = next((line for line in lines if 'rror' in line), plain)
        return f"`reveal {' '.join(self.argv)}` -> exit {self.rc}" + (f': {first[:160]}' if first else '')


def _run(*argv):
    try:
        result = _run_reveal_direct(*argv)
    except Exception as exc:  # an uncaught error is a measured outcome (a crash), not a broken probe
        return Run(tuple(argv), 'crash', '', f'{type(exc).__name__}: {exc}')
    return Run(tuple(argv), result.returncode, result.stdout, result.stderr)


def _spellings(noun):
    """Every spelling of each declared control (name, aliases, flags, global flags reaching it) -> its name."""
    names = {}
    for spec in _specs(noun):
        for spelling in (spec.name, *spec.aliases, *(spec.cli.flags if spec.cli else ())):
            names[spelling] = spec.name
        for flag, _value in spec.cli_flags:
            names[f'--{flag}'] = spec.name
    for flag in FLAG_SPECS:
        fragment = _received(noun, flag)
        if fragment is not None:
            key = fragment.partition('=')[0]
            names[flag.option] = names.get(key, key)
    return names


def _answer(run, noun):
    """What a request answered: exit and stdout. Retirement facts name the spelling used, and an unused-input
    warning names the control as the caller spelled it, so both are compared by the control they name."""
    try:
        doc = json.loads(run.out)
    except ValueError:
        return run.rc, run.out
    meta = doc.get('meta') if isinstance(doc, dict) else None
    if isinstance(meta, dict) and 'warnings' in meta:
        names = _spellings(noun)
        warnings = []
        for warning in meta['warnings']:
            if warning.get('code') == 'retired_spelling':
                continue
            if warning.get('code') in ('unused_flag', 'unused_query_param'):
                fields = sorted({names.get(field, field) for field in warning.get('fields', [])})
                warning = {'code': 'unused_input', 'fields': fields}
            if warning not in warnings:  # two spellings of one unused control are one fact
                warnings.append(warning)
        meta['warnings'] = warnings
    return run.rc, doc


@dataclass(frozen=True)
class Case:
    label: str
    ok: bool
    evidence: str


def _conflict_case(label, conflict, names):
    """Rule 1, different values: exit 2 naming both spellings."""
    return Case(f'{label} conflict', conflict.rc == 2 and conflict.says(*names),
                f'{conflict.brief()} (wants exit 2 naming {" and ".join(names)})')


def _equal_case(label, noun, pair, single):
    """Rule 1, equal values: the same answer as the value given once."""
    return Case(f'{label} equal', _answer(pair, noun) == _answer(single, noun),
                f'{pair.brief()} answers differently from {single.brief()}')


# --- rule 1a: a URI value and a global flag for the same key ----------------------------------------------

def _received(noun, flag):
    """The query fragment a global flag reaches this noun's URI with (flag_specs' own routing), or None when
    the key it sets is not one the noun reads."""
    adapter = _adapter(noun)
    declared = getattr(adapter, 'CLI_QUERY_FLAGS', None) or {}
    fragment = declared.get(flag.dest) or (flag.universal if getattr(adapter, 'HONORS_RESULT_CONTROL', True) else None)
    if not fragment or '=' not in fragment:
        return None
    key = fragment.partition('=')[0]
    walk_policy = key == 'respect_gitignore' and adapter.RESOURCE_SPEC.walks
    return fragment if walk_policy or _spec_for(noun, key) is not None else None


def _other(spec, value):
    """A valid value of *spec* different from *value* (no spec: a switch)."""
    if spec is None or spec.type in ('boolean', 'flag'):
        return 'false' if value in ('true', '1', '') else 'true'
    others = [str(choice) for choice in spec.choices if choice and str(choice) != value]
    if others:
        return others[0]
    return '1' if value != '1' else '2'


def _value_pair(flag, spec):
    """(flag value, a different URI value) for a flag that carries a value."""
    if flag.dest in ('since', 'until'):
        return '2021-01-01', '2020-01-01'
    if len(spec.choices) >= 2:
        return str(spec.choices[0]), str(spec.choices[1])
    if flag.dest == 'sort':
        example = next((e.partition('=')[2] for e in spec.examples if e.startswith('sort=')), '-name')
        return example, example[1:] if example.startswith('-') else f'-{example}'
    if spec.type in ('integer', 'number'):
        return '2', '1'
    return 'b', 'a'


def probe_uri_and_flag(noun):
    cases = []
    for flag in FLAG_SPECS:
        fragment = _received(noun, flag)
        if fragment is None:
            continue
        key, _, template = fragment.partition('=')
        spec = None if key == 'respect_gitignore' else _spec_for(noun, key)  # the walk policy is a switch
        base = spec is None or spec.role != 'operation'
        if '{value}' in template:
            flag_value, uri_value = _value_pair(flag, spec)
            flag_argv = [f'{flag.option}={flag_value}']
        else:
            flag_value, uri_value = template, _other(spec, template)
            flag_argv = [flag.option]
        label = f'{flag.option} vs ?{key}='
        cases.append(_conflict_case(label, _run(_uri(noun, f'{key}={uri_value}', base=base), *flag_argv, '--format',
                                                'json'), (flag.option, f'{key}={uri_value}')))
        cases.append(_equal_case(label, noun,
                                 _run(_uri(noun, f'{key}={flag_value}', base=base), *flag_argv, '--format', 'json'),
                                 _run(_uri(noun, f'{key}={flag_value}', base=base), '--format', 'json')))
    return cases


# --- rule 1b: an alias and its name -----------------------------------------------------------------------

def _candidate_values(spec):
    """Values of *spec* to try, the declaration's own first."""
    if spec.type in ('boolean', 'flag'):
        return ['true', 'false']
    choices = [str(choice) for choice in spec.choices if choice]
    if choices:
        return choices
    if spec.type in ('integer', 'number'):
        low = spec.minimum or 0
        return [str(low + 2), str(low + 1)]
    spellings = (spec.name, *spec.aliases)
    example = next((e.partition('=')[2] for e in spec.examples if e.partition('=')[0] in spellings), '')
    return [example or 'function', 'other']


def _alias_spelling(spec, alias, value):
    """How *alias* spells *value*: the value itself, or the legacy form its normalizer maps to it."""
    if spec.alias_normalize is None:
        return value
    for candidate in (value, value.lstrip('-'), 'true'):
        try:
            if spec.alias_normalize(alias, candidate) == value:
                return candidate
        except ValueError:
            continue
    return None


def _alias_values(spec, alias):
    """(value, the alias's spelling of it, a different valid value or None)."""
    values = _candidate_values(spec)
    for value in values:
        same = _alias_spelling(spec, alias, value)
        if same is not None:
            return value, same, next((other for other in values if other != value), None)
    return None


def _flag_spelling(spec, name):
    if spec.cli is None:
        return None
    return next((flag for flag in spec.cli.flags if flag[2:] in (name, name.replace('_', '-'))), None)


def _alias_on_subcommand(noun, spec, alias, values):
    name_flag, alias_flag = _flag_spelling(spec, spec.name), _flag_spelling(spec, alias)
    legacy = dict(spec.cli_flags).get(alias)  # a global flag that spells the alias (--verbose is detail=full)
    if _sub(noun) is None or name_flag is None:
        return []
    value, same, other = values
    base = spec.role != 'operation'
    if alias_flag is not None and alias_flag != name_flag:
        conflict = _sub(noun, f'{name_flag}={other}', f'{alias_flag}={same}', base=base) if other else None
        pair = _sub(noun, f'{name_flag}={value}', f'{alias_flag}={same}', base=base)
        names = (name_flag, alias_flag)
    elif legacy is not None:
        value, other = legacy, _other(spec, legacy)
        conflict = _sub(noun, f'{name_flag}={other}', f'--{alias}', base=base)
        pair = _sub(noun, f'{name_flag}={value}', f'--{alias}', base=base)
        names = (name_flag, f'--{alias}')
    else:
        return []
    label = f'{names[0]} vs {names[1]}'
    cases = [_conflict_case(label, _run(*conflict, '--format', 'json'), names)] if conflict else []
    single = _sub(noun, f'{name_flag}={value}', base=base)
    return cases + [_equal_case(label, noun, _run(*pair, '--format', 'json'), _run(*single, '--format', 'json'))]


def probe_alias_and_name(noun):
    cases = []
    for spec in _specs(noun):
        if spec.cli is not None and spec.cli.action == 'append':
            continue  # a repeated control ANDs its values: not settled by the table (reported, not a cell)
        for alias in spec.aliases:
            values = _alias_values(spec, alias)
            if values is None:
                continue
            value, same, other = values
            base = spec.role != 'operation'
            label = f'?{spec.name}= vs ?{alias}='
            if other is not None:  # a control with one valid value cannot be given two
                conflict = _uri(noun, f'{spec.name}={other}', f'{alias}={same}', base=base)
                cases.append(_conflict_case(label, _run(conflict, '--format', 'json'), (spec.name, alias)))
            pair = _uri(noun, f'{spec.name}={value}', f'{alias}={same}', base=base)
            cases.append(_equal_case(label, noun, _run(pair, '--format', 'json'),
                                     _run(_uri(noun, f'{spec.name}={value}', base=base), '--format', 'json')))
            cases += _alias_on_subcommand(noun, spec, alias, values)
    return cases


# --- rule 1c: the same scalar spelling twice ---------------------------------------------------------------

def _repeatable(spec):
    """A control that accumulates when given again (``--where``, ``--match``): its CLI action appends."""
    return spec.cli is not None and spec.cli.action == 'append'


def _distinct_values(spec):
    """(a, b): a valid value and a different one, distinctive enough to find in a message (b None: one value)."""
    if spec.type in ('integer', 'number'):
        low = spec.minimum or 0
        return str(low + 3), str(low + 7)
    values = _candidate_values(spec)
    return values[0], (values[1] if len(values) > 1 else None)


def _in_base(noun, spec):
    """The noun's default request already gives this control (trace's ``from``): repeating it would be three."""
    query = BASE[noun][1].lstrip('?')
    return any(pair.partition('=')[0] in (spec.name, *spec.aliases) for pair in query.split('&') if pair)


def _takes_no_value(noun, flag):
    return create_declared_parser(noun)._option_string_actions[flag].nargs == 0


def probe_repeated_spelling(noun):
    cases = []
    for spec in _specs(noun):
        if _repeatable(spec) or spec.type == 'array' or spec.role == 'scope':
            continue  # a list value given twice is not settled by rule 1 (reported); scope keys are walk policy
        a, b = _distinct_values(spec)
        base = spec.role != 'operation' and not _in_base(noun, spec)
        label = f'?{spec.name}= twice'
        if b is not None:
            cases.append(_conflict_case(label, _run(_uri(noun, f'{spec.name}={a}', f'{spec.name}={b}', base=base),
                                                    '--format', 'json'), (spec.name, a, b)))
        twice = _uri(noun, f'{spec.name}={a}', f'{spec.name}={a}', base=base)
        cases.append(_equal_case(label, noun, _run(twice, '--format', 'json'),
                                 _run(_uri(noun, f'{spec.name}={a}', base=base), '--format', 'json')))
        flag = spec.cli.flags[0] if spec.cli is not None else None
        if _sub(noun) is None or flag is None:
            continue
        label = f'{flag} twice'
        if _takes_no_value(noun, flag):
            pair, single = _sub(noun, flag, flag, base=base), _sub(noun, flag, base=base)
        else:
            if b is not None:
                cases.append(_conflict_case(label, _run(*_sub(noun, f'{flag}={a}', f'{flag}={b}', base=base),
                                                        '--format', 'json'), (flag, a, b)))
            pair, single = _sub(noun, f'{flag}={a}', f'{flag}={a}', base=base), _sub(noun, f'{flag}={a}', base=base)
        cases.append(_equal_case(label, noun, _run(*pair, '--format', 'json'), _run(*single, '--format', 'json')))
    return cases


# --- rule 1d: a repeatable control's aliases accumulate ----------------------------------------------------

def probe_repeatable_aliases(noun):
    cases = []
    for spec in _specs(noun):
        if not _repeatable(spec):
            continue
        for alias in spec.aliases:
            label = f'?{spec.name}= with ?{alias}='
            mixed = _run(_uri(noun, f'{spec.name}=a', f'{alias}=b'), '--format', 'json')
            same = _run(_uri(noun, f'{spec.name}=a', f'{spec.name}=b'), '--format', 'json')
            cases.append(Case(f'{label} accumulates', same.rc != 2 and _answer(mixed, noun) == _answer(same, noun),
                              f'{mixed.brief()} answers differently from {same.brief()}'))
            name_flag, alias_flag = _flag_spelling(spec, spec.name), _flag_spelling(spec, alias)
            if _sub(noun) is None or name_flag is None or alias_flag is None or alias_flag == name_flag:
                continue
            mixed = _run(*_sub(noun, name_flag, 'a', alias_flag, 'b'), '--format', 'json')
            same = _run(*_sub(noun, name_flag, 'a', name_flag, 'b'), '--format', 'json')
            cases.append(Case(f'{name_flag} with {alias_flag} accumulates',
                              same.rc != 2 and _answer(mixed, noun) == _answer(same, noun),
                              f'{mixed.brief()} answers differently from {same.brief()}'))
    return cases


# --- rule 2: a legacy spelling's note on every transport --------------------------------------------------

def _rows(noun):
    """The note-stage RETIREMENTS rows that spell this noun: its scheme, subcommand, parameters and values."""
    prefixes = (f'scheme:{noun}', f'subcommand:{noun}')
    return sorted(key for key, entry in RETIREMENTS.items() if entry.stage == 'note' and (
        key in prefixes or key.startswith((f'param:{noun}.', f'value:{noun}.'))))


def _uri_of(argv):
    """The one-string spelling of a retirement case: its URI, or the subcommand argv's flags as query keys
    through the noun's declared parser (a flag that takes no value is ``key=true``). None for a subcommand row."""
    if '://' in argv[0]:
        return argv[0]
    noun, path, *flags = argv
    actions = create_declared_parser(noun)._option_string_actions
    pairs, index = [], 0
    while index < len(flags):
        option = flags[index]
        spec = next(s for s in _specs(noun) if s.cli is not None and option in s.cli.flags)
        key = next((n for n in (spec.name, *spec.aliases) if option[2:] in (n, n.replace('_', '-'))), spec.name)
        if actions[option].nargs == 0:
            pairs.append(f'{key}=true')
            index += 1
        else:
            pairs.append(f'{key}={flags[index + 1]}')
            index += 2
    return f'{noun}://{path}?' + '&'.join(pairs)


def _retired_fields(doc):
    return [w.get('field') for w in ((doc or {}).get('meta') or {}).get('warnings') or []
            if w.get('code') == 'retired_spelling']


def probe_retirement_notes(noun, sample):
    from reveal import api
    from reveal.mcp_server import reveal_query
    cases = []
    for key in _rows(noun):
        entry, argv = RETIREMENTS[key], PRODUCTION_CASES[key](str(sample))
        text = _run(*argv)
        cases.append(Case(f'{key} CLI text', text.err.count(f'note: {entry.text}') == 1,
                          f'{text.brief()} (wants one note line)'))
        as_json = _run(*argv, '--format', 'json')
        doc = json.loads(as_json.out) if as_json.out.strip().startswith('{') else None
        cases.append(Case(f'{key} CLI JSON', key in _retired_fields(doc),
                          f'{as_json.brief()}: retired_spelling fields {_retired_fields(doc)}'))
        if key.startswith('subcommand:'):
            continue  # api.query and MCP take a URI; the scheme row is their spelling of the noun
        uri = _uri_of(argv)
        try:
            fields = _retired_fields(api.query(uri))
            evidence = f'api.query({uri!r}): retired_spelling fields {fields}'
        except Exception as exc:  # the probe records any failure as evidence, never as a pass
            fields, evidence = [], f'api.query({uri!r}) raised {type(exc).__name__}: {str(exc)[:120]}'
        cases.append(Case(f'{key} api.query', key in fields, evidence))
        try:
            out = reveal_query(uri)
        except Exception as exc:  # a ToolError is a failed tool call: evidence, not a pass
            out = f'raised {type(exc).__name__}: {str(exc)[:120]}'
        cases.append(Case(f'{key} MCP', entry.text in out, f'reveal_query({uri!r}): {out[-160:]!r}'))
    return cases


# --- rule 3: a shared control the noun does not declare ---------------------------------------------------

def _teaches(run, noun, control):
    """Exit 2 naming the control and every control the noun declares, in reveal's own words: an argparse
    usage dump lists every flag but is the bare parser error the rule replaces."""
    supported = [spec.name for spec in _specs(noun)]
    argparse_error = any(line.startswith('usage:') for line in run.err.splitlines())
    return run.rc == 2 and not argparse_error and run.says(control, *supported)


def probe_unsupported_controls(noun):
    keys = {name for spec in _specs(noun) for name in (spec.name, *spec.aliases)}
    flags = {flag for spec in _specs(noun) for flag in (spec.cli.flags if spec.cli else ())}
    flags |= {f'--{flag}' for spec in _specs(noun) for flag, _value in spec.cli_flags}
    global_flags = {flag.option[2:]: flag for flag in FLAG_SPECS}
    wants = 'wants exit 2 naming the control and the supported controls'
    cases = []
    for control, value in SHARED_CONTROLS.items():
        if control not in keys:
            run = _run(_uri(noun, f'{control}={value}'), '--format', 'json')
            cases.append(Case(f'?{control}=', _teaches(run, noun, control), f'{run.brief()} ({wants})'))
        if _sub(noun) is not None and f'--{control}' not in flags:
            run = _run(*_sub(noun, f'--{control}', value), '--format', 'json')
            cases.append(Case(f'subcommand --{control}', _teaches(run, noun, control), f'{run.brief()} ({wants})'))
        flag = global_flags.get(control)
        if flag is not None and _received(noun, flag) is None:
            run = _run(_uri(noun), f'--{control}', value, '--format', 'json')
            cases.append(Case(f'URI with global --{control}', _teaches(run, noun, control), f'{run.brief()} ({wants})'))
    return cases


# --- rule 4: global --verbose is --detail full ------------------------------------------------------------

def _levels(noun):
    spec = _spec_for(noun, 'detail')
    if spec is None:
        return ()
    if spec.choices:
        return tuple(str(choice) for choice in spec.choices)
    return tuple(e.partition('=')[2] for e in spec.examples if e.startswith('detail='))


def _mentions(run, option):
    """A stderr line about *option* other than a retirement note ("--verbose has no effect")."""
    return any(option in line for line in run.err.splitlines() if not line.startswith('note:'))


def probe_verbose_is_detail_full(noun):
    levels = _levels(noun)
    forms = {'URI': (lambda *pairs: [_uri(noun, *pairs)], 'detail=full')}
    if _sub(noun) is not None:
        forms['subcommand'] = (lambda *pairs: _sub(noun, *(['--detail', 'full'] if pairs else [])), None)
    cases = []
    for form, (request, full_pair) in forms.items():
        verbose = _run(*request(), '--verbose', '--format', 'json')
        if 'full' not in levels:
            ok = verbose.rc == 2 and verbose.says('detail', *levels)
            wants = f'wants exit 2 naming its levels {levels}' if levels else 'wants exit 2: no detail levels'
            cases.append(Case(f'{form} --verbose', ok, f'{verbose.brief()} ({wants})'))
            continue
        full = _run(*request(full_pair or 'detail=full'), '--format', 'json')
        if full.rc == 2:  # this request's view has no full level: --verbose must reject as --detail full does
            cases.append(Case(f'{form} --verbose', verbose.rc == 2 and verbose.says('detail'),
                              f'{verbose.brief()} (the view rejects detail=full: {full.brief()})'))
        else:
            ok = _answer(verbose, noun) == _answer(full, noun) and not _mentions(verbose, '--verbose')
            cases.append(Case(f'{form} --verbose', ok, f'{verbose.brief()} vs {full.brief()} (wants the same answer)'))
    return cases


# --- rule 3b: unknown keys ----------------------------------------------------------------------------------

UNKNOWN = 'zz-unknown'


def probe_unknown_keys(noun):
    wants = 'wants exit 2 naming the key and the supported controls'
    run = _run(_uri(noun, f'{UNKNOWN}=1'), '--format', 'json')
    cases = [Case(f'?{UNKNOWN}=', _teaches(run, noun, UNKNOWN), f'{run.brief()} ({wants})')]
    if _sub(noun) is not None:
        run = _run(*_sub(noun, f'--{UNKNOWN}', '1'), '--format', 'json')
        cases.append(Case(f'subcommand --{UNKNOWN}', _teaches(run, noun, UNKNOWN), f'{run.brief()} ({wants})'))
    return cases


# --- rule 5: one legacy-spelling declaration ----------------------------------------------------------------

def _replacement_elsewhere(noun, entry):
    """A replacement in another scheme (``calls ?modules`` -> ``imports://``) has no canonical control here."""
    return any(scheme != noun for scheme in re.findall(r'([a-z][a-z0-9+.-]*)://', entry.replacement))


def _legacy_names(spec):
    return tuple(getattr(entry, 'name', entry) for entry in getattr(spec, 'legacy', ()))


def probe_legacy_declarations(noun, sample):
    """Each note-stage ``param:`` row names a spelling declared exactly once on the noun: an alias, or a ``legacy``
    entry of the canonical control, and not a parameter of its own (that is ``ParamSpec.retired``'s shape)."""
    cases = []
    specs = list(_adapter(noun).PARAM_SPECS)
    for key in _rows(noun):
        entry = RETIREMENTS[key]
        if not key.startswith('param:') or _replacement_elsewhere(noun, entry):
            continue
        legacy = key.partition('.')[2]
        owners = [spec.name for spec in specs if legacy in spec.aliases or legacy in _legacy_names(spec)]
        own = [spec.name for spec in specs if spec.name == legacy]
        cases.append(Case(f'{key} declared', len(owners) == 1 and not own,
                          f'{legacy}: declared on {owners or "no control"}'
                          + (f', and still a parameter of its own ({own[0]})' if own else '')))
        cases += _legacy_conflict_cases(noun, key, legacy, specs, sample)
    return cases


def _legacy_conflict_cases(noun, key, legacy, specs, sample):
    """Rule 1 for legacy and canonical, generated from the declaration: the retirement case's legacy value
    translates to canonical values; a different canonical value exits 2 naming both, the same answers once."""
    entry = next((e for spec in specs for e in getattr(spec, 'legacy', ()) if getattr(e, 'name', None) == legacy), None)
    uri = _uri_of(PRODUCTION_CASES[key](str(sample)))
    if entry is None or '://' not in uri:
        return []
    base, _, query = uri.partition('?')
    pairs = [pair for pair in query.split('&') if pair]
    raw = next((pair.partition('=')[2] for pair in pairs if pair.partition('=')[0] == legacy), '')
    without = base + '?' + '&'.join(pair for pair in pairs if pair.partition('=')[0] != legacy)
    cases = []
    for name, value in dict(entry.translate(raw)).items():
        spec = _spec_for(noun, name)
        if spec is None or _repeatable(spec):
            continue  # a repeatable canonical control accumulates the legacy term (rule 1)
        other = next((v for v in _candidate_values(spec) if v != str(value)), None)
        label = f'?{legacy}= vs ?{name}='
        if other is not None:
            cases.append(_conflict_case(label, _run(f'{uri}&{name}={other}', '--format', 'json'), (legacy, name)))
        cases.append(_equal_case(label, noun, _run(f'{uri}&{name}={value}', '--format', 'json'),
                                 _run(f'{without}&{name}={value}'.replace('?&', '?'), '--format', 'json')))
    return cases


# --- rule 6: aliases, different words and spelling variants -----------------------------------------------

# D18-deferred selector renames stay note-free until the pre-cut checkpoint (rule 6).
DEFERRED_ALIASES = {('ast', 'show'), ('git', 'type')}


def _spelling_only(spec, alias):
    return alias.replace('_', '-') == spec.name.replace('_', '-')


def probe_alias_notes(noun, sample):
    from reveal import api
    from reveal.mcp_server import reveal_query
    cases = []
    for spec in _specs(noun):
        for alias in spec.aliases:
            values = _alias_values(spec, alias)
            if values is None:
                continue
            key = f'param:{noun}.{alias}'
            uri = _uri(noun, f'{alias}={values[1]}', base=spec.role != 'operation')
            noted = not _spelling_only(spec, alias) and (noun, alias) not in DEFERRED_ALIASES
            as_json = _run(uri, '--format', 'json')
            doc = json.loads(as_json.out) if as_json.out.strip().startswith('{') else None
            if not noted:
                ok = key not in RETIREMENTS and key not in _retired_fields(doc)
                cases.append(Case(f'?{alias}= note-free', ok, f'{as_json.brief()}: retired_spelling fields '
                                                              f'{_retired_fields(doc)}; row {key in RETIREMENTS}'))
                continue
            row = RETIREMENTS.get(key)
            cases.append(Case(f'{key} row', row is not None and row.stage == 'note', f'no note-stage row {key}'))
            if row is None:
                continue
            cases.append(Case(f'?{alias}= CLI JSON', key in _retired_fields(doc),
                              f'{as_json.brief()}: retired_spelling fields {_retired_fields(doc)}'))
            text = _run(uri)
            cases.append(Case(f'?{alias}= CLI text', text.err.count(f'note: {row.text}') == 1, text.brief()))
            try:
                fields = _retired_fields(api.query(uri))
            except Exception as exc:  # recorded as evidence, never a pass
                fields = [f'raised {type(exc).__name__}: {str(exc)[:100]}']
            cases.append(Case(f'?{alias}= api.query', key in fields, f'api.query({uri!r}): {fields}'))
            try:
                out = reveal_query(uri)
            except Exception as exc:  # a ToolError is a failed call: evidence, not a pass
                out = f'raised {type(exc).__name__}: {str(exc)[:100]}'
            cases.append(Case(f'?{alias}= MCP', row.text in out, f'reveal_query({uri!r}): {out[-120:]!r}'))
    return cases


# --- rule 8: bare URI keys on a where noun ------------------------------------------------------------------

def _has_where(noun):
    return _spec_for(noun, 'where') is not None


def probe_bare_shared_keys(noun):
    if _spec_for(noun, 'where') is None or _spec_for(noun, 'where').role != 'filter-expression':
        return []
    keys = {name for spec in _specs(noun) for name in (spec.name, *spec.aliases)}
    cases = []
    for control, value in SHARED_CONTROLS.items():
        if control in keys:
            continue
        run = _run(_uri(noun, f'{control}={value}'), '--format', 'json')
        doc = json.loads(run.out) if run.out.strip().startswith('{') else None
        ok = run.rc == 2 or f'param:{noun}.{control}' in _retired_fields(doc)
        cases.append(Case(f'?{control}= is the control', ok,
                          f'{run.brief()} (wants exit 2, or the declared legacy spelling with its note)'))
    return cases


# One filterable field per where noun, with a value the fixture holds, until rule 8's per-noun field declaration
# exists (Step 4 replaces this table with it). Targets other than the noun's default are given here.
FIELD_SAMPLES = {
    'ast': ('proj', [('name', '=', 'serve'), ('lines', '>', '3')]),
    'claude': ('sessions', [('session', '~=', 'session')]),
    'git': ('proj', [('author', '=', 'Fixture')]),
    'json': ('proj/rows.json', [('name', '=', 'a'), ('n', '>', '1')]),
    'markdown': ('proj', [('title', '=', 'Guide'), ('n', '>', '1')]),
    'metrics': ('proj', [('lines', '=', '5'), ('lines', '>', '10')]),
    'stats': ('proj', [('lines', '=', '5'), ('lines', '>', '10')]),
}


def probe_bare_field_filters(noun):
    if not _has_where(noun):
        return []
    target, samples = FIELD_SAMPLES[noun]
    cases = []
    for field, op, value in samples:
        bare = _run(f'{noun}://{target}?{field}{op}{value}', '--format', 'json')
        where = _run(f'{noun}://{target}?where={field}{op}{value}', '--format', 'json')
        cases.append(Case(f'?{field}{op}{value}', where.rc != 2 and _answer(bare, noun) == _answer(where, noun),
                          f'{bare.brief()} answers differently from {where.brief()}'))
    return cases


PROBES = {'1a': probe_uri_and_flag, '1b': probe_alias_and_name, '1c': probe_repeated_spelling,
          '1d': probe_repeatable_aliases, '3': probe_unsupported_controls, '3b': probe_unknown_keys,
          '4': probe_verbose_is_detail_full, '8a': probe_bare_shared_keys,
          '8b': probe_bare_field_filters}
# These also run the retirement cases' sample file.
SAMPLE_PROBES = {'2': probe_retirement_notes, '5': probe_legacy_declarations, '6': probe_alias_notes}


def measure(noun, rule, sample):
    """(state, cases) for one cell, measured now."""
    cases = SAMPLE_PROBES[rule](noun, sample) if rule in SAMPLE_PROBES else PROBES[rule](noun)
    if not cases:
        return 'exempt', cases
    return ('conforms' if all(case.ok for case in cases) else 'not_yet'), cases


# --- the tests ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize('owner,field,present', [
    ('FlagSpec', 'reject_conflict', False),    # rule 1 is the injection seam's default, not a per-flag opt-in
    ('ParamSpec', 'retired', False),           # rule 5: a legacy spelling is not a parameter of its own
    ('ParamSpec', 'legacy_selectors', False),  # rule 5: JSON's first-position selectors are legacy spellings too
    ('ParamSpec', 'legacy', True),             # rule 5: the one declaration, on the canonical control
])
def test_one_legacy_declaration_replaces_the_opt_in_seams(owner, field, present):
    from dataclasses import fields
    from reveal.cli.routing.flag_specs import FlagSpec
    from reveal.utils.query_parser import ParamSpec
    names = {item.name for item in fields({'FlagSpec': FlagSpec, 'ParamSpec': ParamSpec}[owner])}
    assert (field in names) is present, f'{owner}.{field} should {"" if present else "not "}exist'


def test_every_legacy_entry_names_its_spelling_and_translation():
    """The declaration's shape (rule 5): a spelling and a translation of its raw value into canonical controls."""
    for noun in NOUNS:
        for spec in _adapter(noun).PARAM_SPECS:
            for entry in getattr(spec, 'legacy', ()):
                assert isinstance(entry.name, str) and entry.name and callable(entry.translate), (noun, spec.name)

def test_every_declared_noun_has_a_base_request():
    assert sorted(BASE) == NOUNS, 'a new declared noun needs its default request in BASE (and its cells below)'


def test_the_recorded_cells_name_real_nouns_and_rules():
    for noun, rule in [*EXEMPT, *NOT_YET]:
        assert noun in NOUNS and rule in RULES, (noun, rule)
        assert noun not in RULED_EXEMPT_NOUNS, (noun, rule)
    assert not [cell for cell in NOT_YET if cell[1] in DEFAULT_NOW], 'rules 1, 2, 5 and 6 have no not-yet cells'
    assert not set(EXEMPT) & set(NOT_YET)
    assert all(reason.strip() for reason in [*EXEMPT.values(), *NOT_YET.values()])


def test_not_yet_count_only_falls():
    counted = {rule: sum(1 for (_noun, r) in NOT_YET if r == rule) for rule in RULES}
    assert counted == NOT_YET_BASELINE, 'NOT_YET and NOT_YET_BASELINE disagree; the baseline may only fall'


# A probe that could only fail would measure nothing: each rule's probe passes a conforming answer where one
# exists today (1b, 4, 5, 6 and 8b also have whole conforming cells). 3b has none anywhere: its matcher is
# proven by test_the_matchers_reject_the_answers_the_rules_replace.
POSITIVE_CONTROLS = [('metrics', '1a', '--hotspots vs ?hotspots= conflict'),
                     ('calls', '2', 'param:calls.root CLI JSON'), ('calls', '2', 'param:calls.root MCP'),
                     ('imports', '3', '?match='), ('metrics', '3', 'subcommand --match'),
                     ('imports', '1c', '?limit= twice equal'),
                     ('markdown', '1d', '--match with --body-contains accumulates'),
                     ('metrics', '8a', '?match= is the control')]


@pytest.mark.parametrize('noun,rule,label', POSITIVE_CONTROLS)
def test_a_probe_passes_a_conforming_case(workspace, noun, rule, label):
    if rule in SAMPLE_PROBES:
        pytest.importorskip('mcp')
    _state, cases = measure(noun, rule, workspace)
    assert [case.ok for case in cases if case.label == label] == [True], [c for c in cases if c.label == label]


def test_the_matchers_reject_the_answers_the_rules_replace():
    names = ' '.join(spec.name for spec in _specs('imports'))
    usage = Run(('imports',), 2, '',
                f'usage: reveal imports {names}\nreveal imports: error: unrecognized arguments: --match x\n')
    taught = Run(('imports',), 2, '',
                 f'Error (imports://): imports does not support match; supported controls: {names}\n')
    assert not _teaches(usage, 'imports', 'match') and _teaches(taught, 'imports', 'match')
    assert not _teaches(Run((), 0, '', taught.err), 'imports', 'match')
    uri_wins = Run((), 0, '', 'Note: --limit ignored on ast:// -- the URI already sets limit=1.\n')
    rejected = Run((), 2, '', 'Error (ast://): --limit conflicts with limit=1 in the URI\n')
    assert not _conflict_case('x', uri_wins, ('--limit', 'limit=1')).ok
    assert _conflict_case('x', rejected, ('--limit', 'limit=1')).ok
    assert _mentions(Run((), 0, '', 'Note: --verbose has no effect on ast:// queries\n'), '--verbose')
    assert not _mentions(Run((), 0, '', 'note: imports ?verbose (--verbose) is deprecated\n'), '--verbose')


@pytest.mark.parametrize('rule', RULES)
@pytest.mark.parametrize('noun', NOUNS)
def test_cell(workspace, noun, rule):
    if noun in RULED_EXEMPT_NOUNS:
        pytest.skip(RULED_EXEMPT_NOUNS[noun])
    if rule in SAMPLE_PROBES:
        pytest.importorskip('mcp')
    state, cases = measure(noun, rule, workspace)
    failing = [f'{case.label}: {case.evidence}' for case in cases if not case.ok]
    report = os.environ.get('REVEAL_CONFORMANCE_REPORT')
    if report:  # regenerate the matrix: one JSON line per measured cell
        with open(report, 'a', encoding='utf-8') as sink:
            sink.write(json.dumps({'noun': noun, 'rule': rule, 'state': state, 'cases': len(cases),
                                   'failing': failing}) + '\n')
    if (noun, rule) in EXEMPT:
        assert state == 'exempt', f'{noun} x {rule} is recorded exempt ({EXEMPT[noun, rule]}) but has cases: ' + \
            '; '.join(case.label for case in cases)
    elif (noun, rule) in NOT_YET:
        assert state == 'not_yet', (f'{noun} x {rule} now conforms: remove it from NOT_YET and lower '
                                    f'NOT_YET_BASELINE[{rule!r}] (ratchets only fall)')
    else:
        assert state == 'conforms', f'{noun} x {rule} does not conform:\n  ' + '\n  '.join(failing or ['no cases'])
