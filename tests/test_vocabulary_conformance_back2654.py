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

A cell is ``conforms`` (asserted), ``not_yet`` (recorded below with the behaviour observed; the count may only
fall and must reach zero before the cut) or ``exempt`` (a written reason; the probe must find nothing to run).
A cell that starts to conform fails until it is removed from NOT_YET and NOT_YET_BASELINE is lowered, the
ratchet pattern of scripts/check_boundaries.py. To print the measured matrix, run this file with
REVEAL_CONFORMANCE_REPORT=<path>: each cell appends one JSON line (state, case count, failing evidence).
"""
import json
import os
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
RULES = ('1a', '1b', '2', '3', '4')

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
}

# Cells that do not conform yet: (noun, rule) -> the behaviour observed at fac0718b. May only shrink; every
# entry reaches zero before the cut. "URI wins" is flag_specs' note "--X ignored on N:// -- the URI already
# sets K=V", exit 0; "reported unused" is a meta.warnings unused_flag entry for a flag whose value equals the URI's.
_URI_WINS = 'URI wins with a note, exit 0: '
NOT_YET = {
    ('architecture', '1a'): _URI_WINS + '--no-gitignore, --all, --verbose',
    ('ast', '1a'): _URI_WINS + '--no-gitignore, --all, --sort, --limit; --all equal to ?limit= is reported unused',
    ('calls', '1a'): _URI_WINS + '--no-gitignore, --all, --limit; --all equal to ?top= is reported unused',
    ('claude', '1a'): _URI_WINS + '--since, --until, --limit',
    ('codex', '1a'): _URI_WINS + '--since, --until',
    ('contracts', '1a'): _URI_WINS + '--no-gitignore',
    ('deps', '1a'): _URI_WINS + '--no-gitignore',
    ('git', '1a'): _URI_WINS + '--since, --until, --all, --verbose, --sort, --limit; --all and --verbose equal to '
                   'the URI value are reported unused',
    ('hotspots', '1a'): _URI_WINS + '--no-gitignore, --all, --limit; --all and --limit equal to ?top= are reported '
                        'unused',
    ('imports', '1a'): _URI_WINS + '--no-gitignore, --verbose, --limit',
    ('json', '1a'): _URI_WINS + '--sort, --limit',
    ('markdown', '1a'): _URI_WINS + '--no-gitignore, --sort, --limit',
    ('metrics', '1a'): _URI_WINS + '--since, --no-gitignore, --all, --code-only, --sort, --limit (only --hotspots '
                       'rejects: the BACK-2621 opt-in); --all, --hotspots and --code-only equal to the URI value '
                       'are reported unused',
    ('overview', '1a'): _URI_WINS + '--no-gitignore, --all, --verbose',
    ('pack', '1a'): _URI_WINS + '--no-gitignore',
    ('patches', '1a'): _URI_WINS + '--no-gitignore, --all, --limit; --all equal to ?limit= is reported unused',
    ('stats', '1a'): 'as metrics, and ?hotspots=false --hotspots exits 1 (adapter_error) where metrics:// exits 2',
    ('surface', '1a'): _URI_WINS + '--no-gitignore',
    ('testability', '1a'): _URI_WINS + '--no-gitignore, --all, --limit; --limit equal to ?top= is reported unused',
    ('trace', '1a'): _URI_WINS + '--no-gitignore',
    ('git', '1b'): '?view= with ?type=, and ?scan-limit= with ?scan_limit=, raise an uncaught ValueError (a '
                   "traceback) from git's uri_result_type on the invalid-request path instead of exiting 2",
    ('stats', '1b'): '?code-only=true&code_only=false exits 1 (adapter_error) where metrics:// exits 2',
    ('architecture', '2'): 'api.query omits the scheme:architecture note; CLI text, CLI JSON and MCP carry it',
    ('ast', '2'): 'api.query omits the ?calls=, ?callee_of= and ?show=calls notes (no declared alias carries them); '
                  'CLI and MCP carry them',
    ('calls', '2'): 'api.query omits the ?root=, ?target=, ?modules, ?external and ?uncalled notes (parameters of '
                    'their own, not aliases); CLI and MCP carry them',
    ('claude', '2'): 'api.query omits all eight legacy-parameter notes (summary, search, contains, filter, tail, '
                     'last, full, raw); CLI and MCP carry them',
    ('deps', '2'): 'api.query omits the scheme:deps note (not a bound adapter: get_structure runs outside any '
                   'invocation)',
    ('hotspots', '2'): 'api.query omits the scheme:hotspots, ?functions_only and ?files_only notes (not a bound '
                       'adapter)',
    ('stats', '2'): 'api.query omits the scheme:stats note',
    ('testability', '2'): 'api.query omits the scheme:testability note (not a bound adapter)',
    ('trace', '2'): 'api.query omits the scheme:trace note',
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
    ('stats', '3'): 'URI against: exit 0; URI match, kind, depth, until: exit 1 where metrics:// exits 2; global '
                    '--until on the URI: exit 0',
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
    ('stats', '4'): 'as metrics on the URI (no subcommand)',
    ('surface', '4'): 'no detail declaration; --verbose: "has no effect" note, exit 0',
    ('testability', '4'): 'no detail declaration; --verbose accepted silently, exit 0',
    ('trace', '4'): 'no detail declaration; --verbose: "has no effect" note, exit 0',
}

NOT_YET_BASELINE = {'1a': 20, '1b': 2, '2': 9, '3': 20, '4': 18}


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


PROBES = {'1a': probe_uri_and_flag, '1b': probe_alias_and_name, '3': probe_unsupported_controls,
          '4': probe_verbose_is_detail_full}


def measure(noun, rule, sample):
    """(state, cases) for one cell, measured now."""
    cases = probe_retirement_notes(noun, sample) if rule == '2' else PROBES[rule](noun)
    if not cases:
        return 'exempt', cases
    return ('conforms' if all(case.ok for case in cases) else 'not_yet'), cases


# --- the tests ---------------------------------------------------------------------------------------------

def test_every_declared_noun_has_a_base_request():
    assert sorted(BASE) == NOUNS, 'a new declared noun needs its default request in BASE (and its cells below)'


def test_the_recorded_cells_name_real_nouns_and_rules():
    for noun, rule in [*EXEMPT, *NOT_YET]:
        assert noun in NOUNS and rule in RULES, (noun, rule)
    assert not set(EXEMPT) & set(NOT_YET)
    assert all(reason.strip() for reason in [*EXEMPT.values(), *NOT_YET.values()])


def test_not_yet_count_only_falls():
    counted = {rule: sum(1 for (_noun, r) in NOT_YET if r == rule) for rule in RULES}
    assert counted == NOT_YET_BASELINE, 'NOT_YET and NOT_YET_BASELINE disagree; the baseline may only fall'


# A probe that could only fail would measure nothing: each rule's probe passes a conforming answer where one
# exists today (1b and 4 also have whole conforming cells: ast, calls, imports, markdown, metrics; git, imports).
POSITIVE_CONTROLS = [('metrics', '1a', '--hotspots vs ?hotspots= conflict'),
                     ('calls', '2', 'param:calls.root CLI JSON'), ('calls', '2', 'param:calls.root MCP'),
                     ('imports', '3', '?match='), ('metrics', '3', 'subcommand --match')]


@pytest.mark.parametrize('noun,rule,label', POSITIVE_CONTROLS)
def test_a_probe_passes_a_conforming_case(workspace, noun, rule, label):
    if rule == '2':
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
    if rule == '2':
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
