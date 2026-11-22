"""The retirement seam: one table, one hook, one wording (BACK-2066 slice A, ground rule 7).

A retired spelling prints a note naming its replacement and answers as before; after the cut
release it is an error with the same text. The table is `RETIREMENTS` in cli/invocation.py and
`retirement_note` is the one reader, consulted where each kind of spelling is parsed. The
production rows are two BACK-1906 notes and Phase 2b's call-graph spellings (BACK-2066); the tests
below inject test-only rows (one per kind) so the seam is proven independently of what the table
holds today.
"""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from conftest import _run_reveal_direct, is_request_note, without_mcp_request_note, without_request_note_lines
from reveal.adapters.base import get_adapter_class
from reveal.cli import invocation
from reveal.cli.invocation import (LEGACY_CLI_MODIFIERS, RETIREMENT_KEY, RETIREMENTS, STAGES, Retirement,
                                   uri_retirement_keys)

SOURCE = 'def auth_gate(value):\n    return value\n'


@pytest.fixture
def source(tmp_path, monkeypatch):
    from claude_session_fixture import build_claude_home
    from reveal.adapters.claude.adapter import ClaudeAdapter
    home = build_claude_home(tmp_path / 'home')
    monkeypatch.setattr(ClaudeAdapter, 'CONVERSATION_BASE', home / 'projects')
    from codex_session_fixture import build_codex_home
    from reveal.adapters.codex.adapter import CodexAdapter
    codex = build_codex_home(tmp_path / 'codex-home')  # codex's legacy slice rows read a session's messages
    monkeypatch.setattr(CodexAdapter, 'CODEX_HOME', codex)
    monkeypatch.setattr(CodexAdapter, 'CODEX_DB', codex / 'state_5.sqlite')
    path = tmp_path / 'sample.py'
    path.write_text(SOURCE, encoding='utf-8')
    (tmp_path / 'rows.json').write_text('[{"n": 1}, {"n": 2}]', encoding='utf-8')  # JSON's legacy slice rows
    sample_database(tmp_path)
    sample_workbook(tmp_path)
    commit_sample(path)
    return path


def sample_database(directory):
    """A clean one-table database beside the sample: sqlite's legacy --check row answers on it (BACK-2626)."""
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(directory / 'store.db')) as connection, connection:
        connection.execute('CREATE TABLE items (id INTEGER PRIMARY KEY)')


def sample_workbook(directory):
    """A small workbook beside the sample: one sheet, Sales, a header and three rows (xlsx's rows, BACK-2626)."""
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = 'Sales'
    for row in (['name', 'n'], ['x', 1], ['y', 2], ['x total', 3]):
        wb.active.append(row)
    wb.save(directory / 'book.xlsx')


def commit_sample(path):
    """Make the sample's directory a one-commit repository: the git rows answer on it."""
    import pygit2
    repo = pygit2.init_repository(str(path.parent))
    repo.index.add(path.name)
    repo.index.write()
    signature = pygit2.Signature('Fixture', 'fixture@example.com', 1700000000, 0)
    repo.create_commit('HEAD', signature, signature, 'sample', repo.index.write_tree(), [])


def _retire(monkeypatch, key, old, replacement='NEW SPELLING', stage='note'):
    row = Retirement(old, replacement, stage, standalone=True)  # the per-key path (a covered row is the request note's)
    monkeypatch.setitem(RETIREMENTS, key, row)
    return row.text  # the row's own wording: its stage clause is the row's


def _notes(stderr, text):
    return stderr.count(f'note: {text}')


def _all_retired(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings') or [] if w.get('code') == 'retired_spelling']


def _warnings(doc):
    """The spellings' own retirement warnings: a URI request's one request note (BACK-2716) is `_request_field`."""
    return [w for w in _all_retired(doc) if not is_request_note(w)]


def _request_field(argv):
    """The one request note a command line says: a URI to an analysis-only scheme, or any noted scheme that spells a query
    string; a retired twin's own row is its note (BACK-2716)."""
    scheme, sep, rest = argv[0].partition('://')
    if not sep or not invocation.request_noted(scheme):
        return []
    if not (getattr(get_adapter_class(scheme), 'ANALYSIS_ONLY', False) or '?' in rest):
        return []
    return [f'request:{scheme}'] if _renders(scheme, rest) else []


def _renders(scheme, rest):
    """Whether the bound request has a canonical form: a control no flag of the noun spells (Claude's standalone
    ``?summary``) has none, so the request says no note and each covered spelling says its own row."""
    from reveal.cli.routing.canonical import UnrenderableRequest, render_uri_request
    from reveal.cli.routing.declared import create_declared_parser, declared_adapter_class
    from reveal.utils.gitignore import split_respect_gitignore
    from reveal.utils.query_binding import prepare_declared_params
    resource, _, query = split_respect_gitignore(rest)[0].partition('?')
    adapter = declared_adapter_class(scheme)
    try:
        render_uri_request('cli', scheme, resource, prepare_declared_params(adapter.PARAM_SPECS, query, 'uri'),
                           parser=create_declared_parser(scheme), adapter=adapter)
    except UnrenderableRequest:
        return False
    return True


def _without_retirement_warning(doc):
    """The answer minus the retirement fact, an emptied warnings list or meta dropped: what an unretired
    spelling prints."""
    meta = doc.get('meta')
    if isinstance(meta, dict) and 'warnings' in meta:
        meta['warnings'] = [w for w in meta['warnings'] if w.get('code') != 'retired_spelling']
        if not meta['warnings']:
            del meta['warnings']
        if not meta:
            del doc['meta']
    return doc


# One test-only row per kind of spelling, each with the command line that spells it.
# (key, old spelling, argv builder taking the sample file)
KINDS = {
    'subcommand': ('subcommand:check', 'reveal check',
                   lambda f: ['check', f, '--select', 'B001']),
    'scheme': ('scheme:ast', 'ast://', lambda f: [f'ast://{f}?kind=function']),
    'param': ('param:ast.name', 'ast://?name=', lambda f: [f'ast://{f}?name=auth*']),
    'value': ('value:ast.kind=function', 'ast://?kind=function',
              lambda f: [f'ast://{f}?kind=function']),
    # hotspots:// carries a production row since BACK-2149, so the declared-noun case uses metrics://.
    'declared scheme': ('scheme:metrics', 'metrics://', lambda f: [f'metrics://{f}']),
}


@pytest.mark.parametrize('kind', KINDS)
def test_a_retired_spelling_prints_one_note_and_the_answer_is_unchanged(monkeypatch, source, kind):
    key, old, argv = KINDS[kind]
    argv = argv(str(source))
    base_json = _run_reveal_direct(*argv, '--format', 'json')
    base_text = _run_reveal_direct(*argv)
    assert not base_json.stderr.count('deprecated') and 'deprecated' not in without_request_note_lines(base_text.stderr)

    text = _retire(monkeypatch, key, old)
    as_json = _run_reveal_direct(*argv, '--format', 'json')
    as_text = _run_reveal_direct(*argv)

    # Said exactly once: in the JSON answer's meta.warnings (never also on stderr beside it, BACK-2659),
    # or on stderr after a text answer; the exit code and the answer do not move.
    assert _notes(as_json.stderr, text) == 0
    assert _notes(as_text.stderr, text) == 1
    assert as_json.returncode == base_json.returncode
    assert as_text.returncode == base_text.returncode
    assert as_text.stdout == base_text.stdout
    # JSON stdout still parses and carries the same fact as a meta.warnings entry.
    doc = json.loads(as_json.stdout)
    entries = _warnings(doc)
    assert [(w['old'], w['replacement'], w['stage']) for w in entries] == [(old, 'NEW SPELLING', 'note')]
    assert entries[0]['message'] == text
    assert _without_retirement_warning(doc) == _without_retirement_warning(json.loads(base_json.stdout))


@pytest.mark.parametrize('kind', KINDS)
def test_a_spelling_that_is_not_retired_prints_nothing(monkeypatch, source, kind):
    """Negative control: a table row for another spelling leaves this command line alone."""
    key, old, argv = KINDS[kind]
    _retire(monkeypatch, 'scheme:never-spelled', 'never-spelled://')
    result = _run_reveal_direct(*argv(str(source)), '--format', 'json')
    assert 'deprecated' not in without_request_note_lines(result.stderr)
    assert not _warnings(json.loads(result.stdout))


def test_a_note_names_the_spelling_that_was_used_not_a_sibling(monkeypatch, source):
    """A retired value does not retire its parameter, and a retired parameter not its scheme."""
    text = _retire(monkeypatch, 'value:ast.kind=class', 'ast://?kind=class')
    result = _run_reveal_direct(f'ast://{source}?kind=function', '--format', 'json')
    assert 'deprecated' not in result.stderr and text not in result.stderr
    _retire(monkeypatch, 'param:calls.root', 'calls://?root=')
    result = _run_reveal_direct(f'ast://{source}?name=auth*', '--format', 'json')
    assert 'deprecated' not in result.stderr


def test_the_same_parameter_on_another_scheme_is_a_different_spelling(monkeypatch, source):
    """depends://?root= is the scan root; only calls://?root= is retired."""
    assert uri_retirement_keys('depends://src?root=/x') == [
        'scheme:depends', 'param:depends.root', 'value:depends.root=/x']
    assert uri_retirement_keys('calls://src?root=main&depth=2') == [
        'scheme:calls', 'param:calls.root', 'value:calls.root=main',
        'param:calls.depth', 'value:calls.depth=2']
    text = _retire(monkeypatch, 'param:calls.root', 'calls://?root=')
    result = _run_reveal_direct(f'depends://{source}?root={source.parent}', '--format', 'json')
    assert text not in result.stderr


def test_an_operator_spells_the_parameter_before_it():
    assert uri_retirement_keys('ast://src?calls~=a*&callers>2&lines<=9&name!=x&type=function') == [
        'scheme:ast', 'param:ast.calls', 'param:ast.callers', 'param:ast.lines', 'param:ast.name',
        'param:ast.type', 'value:ast.type=function']


def test_a_repeated_spelling_notes_once_per_invocation(monkeypatch, source):
    text = _retire(monkeypatch, 'param:ast.name', 'ast://?name=')
    result = _run_reveal_direct(f'ast://{source}?name=auth*&name=gate*', '--format', 'json')
    assert _notes(result.stderr, text) == 0
    assert len(_warnings(json.loads(result.stdout))) == 1
    assert _notes(_run_reveal_direct(f'ast://{source}?name=auth*&name=gate*').stderr, text) == 1


def test_two_retired_spellings_are_two_notes_and_two_warnings(monkeypatch, source):
    one = _retire(monkeypatch, 'param:ast.name', 'ast://?name=', 'A')
    two = _retire(monkeypatch, 'value:ast.kind=function', 'ast://?kind=function', 'B')
    result = _run_reveal_direct(f'ast://{source}?kind=function&name=auth*', '--format', 'json')
    assert _notes(result.stderr, one) == _notes(result.stderr, two) == 0
    assert sorted(w['replacement'] for w in _warnings(json.loads(result.stdout))) == ['A', 'B']
    text = _run_reveal_direct(f'ast://{source}?kind=function&name=auth*')
    assert _notes(text.stderr, one) == _notes(text.stderr, two) == 1


def test_phase7_is_recorded_and_prints_nothing(monkeypatch, source):
    _retire(monkeypatch, 'scheme:ast', 'ast://', stage='phase7')
    result = _run_reveal_direct(f'ast://{source}?kind=function', '--format', 'json')
    assert result.returncode == 0 and 'deprecated' not in result.stderr
    assert not _warnings(json.loads(result.stdout))


@pytest.mark.parametrize('kind', KINDS)
def test_the_error_stage_exits_2_with_the_same_text(monkeypatch, source, kind):
    key, old, argv = KINDS[kind]
    text = _retire(monkeypatch, key, old, stage='error')
    result = _run_reveal_direct(*argv(str(source)), '--format', 'json')
    assert result.returncode == 2
    assert f'error: {text}' in result.stderr
    assert result.stdout == ''


def test_a_retirement_row_validates_itself():
    with pytest.raises(ValueError):
        Retirement('x', 'y', 'later')
    with pytest.raises(ValueError):
        Retirement('x', '')
    with pytest.raises(ValueError):
        Retirement('', 'y')


# --- the production table -------------------------------------------------------------------

# Every production row and one command line that spells it. A row without a case fails the
# last test, so a later phase cannot add a spelling it never exercised.
# An answer of each noun that reads its legacy CLI modifiers, and the flags typed after it.
_MODIFIER_REQUESTS = {
    **{noun: (lambda noun: lambda f: [f'{noun}://{Path(f).parent}'])(noun)
       for noun in ('ast', 'git', 'hotspots', 'markdown', 'metrics', 'pack', 'patches')},
    'calls': lambda f: [f'calls://{Path(f).parent}?sort=-callers'],
    'claude': lambda f: ['claude://session/my-session?view=messages'],
    'codex': lambda f: ['codex://019e5cc5-0000-7000-8000-000000000001/messages'],  # codex_session_fixture.DOC_SESSION_ID
    'imports': lambda f: [f'imports://{Path(f).parent}?sort=-fan-in'],
    'json': lambda f: [f'json://{Path(f).parent / "rows.json"}'],
    'xlsx': lambda f: [f'xlsx://{(Path(f).parent / "book.xlsx").as_posix()}'],
    'testability': lambda f: [f'testability://{Path(f).parent}?tests={Path(f).parent}'],
}
_MODIFIER_ARGV = {'--head': ['--head', '1'], '--tail': ['--tail', '1'], '--range': ['--range', '1-1'],
                  '--type': ['--type', 'Read'], '--name': ['--name', 'x'], '--search': ['--search', 'x'],
                  '--check': ['--check'], '--lint': ['--lint']}
# Claude's legacy filters are read by the workflow view (and --check by every answer).
_FLAG_REQUESTS = {('claude', flag): (lambda f: ['claude://session/my-session/workflow'])
                  for flag in ('--type', '--name', '--search')}
PRODUCTION_CASES = {
    # D9: architecture delegates to the canonical compact overview.
    'subcommand:architecture': lambda f: ['architecture', str(Path(f).parent)],
    'scheme:architecture': lambda f: [f'architecture://{Path(f).parent}'],
    'flag:--deps': lambda f: [f, 'auth_gate', '--deps'],
    'flag:--mutations': lambda f: [f, 'auth_gate', '--mutations'],
    'flag:--writes': lambda f: [f, 'auth_gate', '--writes'],
    'flag:--calls': lambda f: [f, 'auth_gate', '--calls'],
    'target:nav.outline': lambda f: [f, 'auth_gate', '--outline'],
    'flag:--ifmap': lambda f: [f, 'auth_gate', '--ifmap'],
    'flag:--loopmap': lambda f: [f, 'auth_gate', '--loopmap'],
    'flag:--catchmap': lambda f: [f, 'auth_gate', '--catchmap'],
    'flag:--returns': lambda f: [f, 'auth_gate', '--returns'],
    'flag:--flowto': lambda f: [f, 'auth_gate', '--flowto'],
    'flag:--sideeffects': lambda f: [f, 'auth_gate', '--sideeffects'],
    'flag:--fanout': lambda f: [f, 'auth_gate', '--fanout'],
    'flag:--statewrites': lambda f: [f, 'auth_gate', '--statewrites'],
    'flag:--search': lambda f: [f, '--search', 'auth'],
    'flag:--check': lambda f: [f, '--check', '--select', 'B001'],
    # Phase 3 slice 5a (BACK-2089): --output json=PATH is the sink, --also-json its retired spelling.
    'flag:--also-json': lambda f: ['check', str(Path(f).parent), '--also-json', str(Path(f).parent / 'artifact.json')],
    # Phase 2b (BACK-2066); every spelling of each row is in tests/test_retired_call_spellings_back2066.py.
    'param:calls.root': lambda f: [f'calls://{Path(f).parent}?root=auth_gate'],
    'param:calls.target': lambda f: [f'calls://{Path(f).parent}?target=auth_gate'],
    'param:calls.rank': lambda f: [f'calls://{Path(f).parent}?rank=callers&limit=1'],
    'param:calls.top': lambda f: [f'calls://{Path(f).parent}?sort=-callers&top=1'],
    'param:calls.type': lambda f: [f'calls://{Path(f).parent}?uncalled&type=function'],
    # Imports vocabulary (BACK-2620): each legacy spelling beside its canonical companions.
    'param:imports.rank': lambda f: [f'imports://{Path(f).parent}?rank=fan-in&limit=1'],
    'param:imports.top': lambda f: [f'imports://{Path(f).parent}?sort=-fan-in&top=1'],
    'param:imports.verbose': lambda f: [f'imports://{Path(f).parent}?circular&verbose'],
    'param:imports.max_files': lambda f: [f'imports://{Path(f).parent}?sort=-fan-in&max_files=100'],
    # Rule 4 (BACK-2654, note #17): the global --verbose is --detail full, or the noun's legacy word verbose.
    'flag:--verbose': lambda f: [f'calls://{Path(f).parent}?callees=auth_gate', '--verbose'],
    # Rule 15 (BACK-2654): each presentation switch's --no-NAME is --NAME off, on every parser that carries it.
    'flag:--no-breadcrumbs': lambda f: [f, '--no-breadcrumbs'],
    'flag:--no-fallback': lambda f: [f, '--no-fallback'],
    'flag:--no-group': lambda f: ['check', f, '--no-group'],
    'flag:--no-snippets': lambda f: ['check', f, '--no-snippets'],
    'flag:--no-gitignore': lambda f: [str(Path(f).parent), '--no-gitignore'],
    'param:git.verbose': lambda f: [f'git://{f}?view=blame&verbose'],  # detail is blame's (BACK-2656)
    # Git vocabulary (BACK-2616): URI spellings say the request note that covers them; flags and values say their rows.
    'param:git.type': lambda f: [f'git://{f}?type=history'],
    'param:git.raw': lambda f: [f'git://{f}?raw=1'],
    'param:git.no_merges': lambda f: ['git', str(Path(f).parent), '--view', 'history', '--no-merges'],
    'value:git.view=log': lambda f: ['git', f, '--view', 'log'],
    'value:git.detail=summary': lambda f: ['git', f, '--view', 'blame', '--detail', 'summary'],
    'param:pack.verbose': lambda f: [f'pack://{Path(f).parent}?verbose'],
    'param:overview.verbose': lambda f: [f'overview://{Path(f).parent}?verbose'],
    'param:overview.top': lambda f: ['overview', str(Path(f).parent), '--top', '1'],
    'param:overview.no_imports': lambda f: ['overview', str(Path(f).parent), '--no-imports'],
    'param:patches.group': lambda f: ['patches', str(Path(f).parent), '--group', 'file'],
    'param:patches.top': lambda f: ['patches', str(Path(f).parent), '--view', 'pressure', '--top', '2'],
    'param:patches.no_suppress': lambda f: ['patches', str(Path(f).parent), '--no-suppress'],
    'param:patches.min_patches': lambda f: ['patches', str(Path(f).parent), '--view', 'pressure', '--min-patches', '2'],
    'param:patches.min_categories': lambda f: ['patches', str(Path(f).parent), '--view', 'pressure',
                                               '--min-categories', '2'],
    # JSON's first bare selectors (BACK-2615): each alone, on the fixture's rows.json.
    'param:json.schema': lambda f: [f'json://{Path(f).parent / "rows.json"}?schema'],
    'param:json.flatten': lambda f: [f'json://{Path(f).parent / "rows.json"}?flatten'],
    'param:json.gron': lambda f: [f'json://{Path(f).parent / "rows.json"}?gron'],
    'param:json.type': lambda f: [f'json://{Path(f).parent / "rows.json"}?type'],
    'param:json.keys': lambda f: [f'json://{Path(f).parent / "rows.json"}?keys'],
    'param:json.length': lambda f: [f'json://{Path(f).parent / "rows.json"}?length'],
    'param:json.data-only': lambda f: [f'json://{Path(f).parent / "rows.json"}?view=flatten&data-only'],
    'param:sqlite.check': lambda f: ['sqlite', str(Path(f).parent / 'store.db'), '--check'],
    'param:xlsx.range': lambda f: [f"xlsx://{(Path(f).parent / 'book.xlsx').as_posix()}?sheet=Sales&range=A1:B2"],
    'param:xlsx.search': lambda f: [f"xlsx://{(Path(f).parent / 'book.xlsx').as_posix()}?search=x"],
    'param:contracts.impls': lambda f: ['contracts', str(Path(f).parent), '--impls', '1'],
    'param:contracts.no_implementations': lambda f: ['contracts', str(Path(f).parent), '--no-implementations'],
    'param:surface.type': lambda f: ['surface', str(Path(f).parent), '--type', 'env'],
    'param:surface.source_only': lambda f: ['surface', str(Path(f).parent), '--source-only'],
    'param:surface.by': lambda f: ['surface', str(Path(f).parent), '--by', 'dir'],
    'param:surface.depth': lambda f: ['surface', str(Path(f).parent), '--view', 'dir', '--depth', '1'],
    'param:surface.top': lambda f: ['surface', str(Path(f).parent), '--top', '1'],
    'param:architecture.verbose': lambda f: [f'architecture://{Path(f).parent}?verbose'],
    'param:hotspots.verbose': lambda f: [f'hotspots://{Path(f).parent}?verbose'],
    'param:testability.verbose': lambda f: [f'testability://{Path(f).parent}?tests={Path(f).parent}&verbose'],
    'param:deps.verbose': lambda f: [f'deps://{Path(f).parent}?verbose'],
    # Metrics vocabulary (BACK-2621): each legacy spelling alone, on the one source file.
    'param:metrics.hotspots': lambda f: [f'metrics://{f}?hotspots=true'],
    'param:metrics.top': lambda f: [f'metrics://{f}?view=hotspots&top=1'],
    'param:hotspots.top': lambda f: [f'hotspots://{Path(f).parent}?top=1'],
    'param:testability.top': lambda f: [f'testability://{Path(f).parent}?tests={Path(f).parent}&top=1'],
    'param:metrics.min_lines': lambda f: [f'metrics://{f}?min_lines=1'],
    'param:metrics.max_lines': lambda f: [f'metrics://{f}?max_lines=1000'],
    'param:metrics.min_functions': lambda f: [f'metrics://{f}?min_functions=0'],
    'param:metrics.min_complexity': lambda f: [f'metrics://{f}?min_complexity=0'],
    'param:metrics.max_complexity': lambda f: [f'metrics://{f}?max_complexity=100'],
    'param:metrics.no_churn': lambda f: ['metrics', f, '--view', 'hotspots', '--no-churn'],
    'param:metrics.no_merges': lambda f: [f'metrics://{f}?view=hotspots&no_merges=true'],
    'param:metrics.summary_only': lambda f: [f'metrics://{f}?summary_only=true'],
    # Phase 2 slice S5 (BACK-1054): ?modules answers from imports ?importers; tests/test_calls_modules_shim_back1054.py
    # pins its edges, shape and exit codes. ?external is spelled with callers here, where it never applied, so the
    # row is its one note (with ?modules it is the second).
    'param:calls.modules': lambda f: [f'calls://{Path(f).parent}?modules'],
    'param:calls.external': lambda f: [f'calls://{Path(f).parent}?modules&external'],  # external is modules' (BACK-2656)
    # BACK-2195 (D8): ?uncalled is retired; every spelling is in tests/test_retired_call_spellings_back2066.py.
    'param:calls.uncalled': lambda f: [f'calls://{Path(f).parent}?uncalled'],
    'param:claude.summary': lambda f: ['claude://session/my-session?summary'],
    'param:claude.search': lambda f: ['claude://session/my-session?search=token'],
    'param:claude.contains': lambda f: ['claude://session/my-session/messages?contains=Fixed'],
    'param:claude.filter': lambda f: ['claude://sessions?filter=my-session'],
    'param:claude.tail': lambda f: ['claude://session/my-session?tail=2'],
    'param:claude.last': lambda f: ['claude://session/my-session?last'],
    'param:claude.full': lambda f: ['claude://session/my-session/exchanges?full'],
    'param:claude.raw': lambda f: ['claude://session/my-session/messages?raw'],
    # Codex's legacy words (BACK-2618), on codex_session_fixture.DOC_SESSION_ID and its catalog
    'param:codex.filter': lambda f: ['codex://sessions/?filter=auth'],
    'param:codex.search': lambda f: ['codex://sessions/?search=auth'],
    'param:codex.full': lambda f: ['codex://019e5cc5-0000-7000-8000-000000000001/exchanges?full'],
    'param:codex.last': lambda f: ['codex://019e5cc5-0000-7000-8000-000000000001?last'],
    'param:codex.tokens': lambda f: ['codex://019e5cc5-0000-7000-8000-000000000001?tokens'],
    'param:codex.goal': lambda f: ['codex://019e5cc5-0000-7000-8000-000000000001?goal'],
    'param:ast.calls': lambda f: [f'ast://{f}?calls=auth_gate'],
    # BACK-2654: different-word aliases became legacy entries with rows.
    'param:ast.type': lambda f: [f'ast://{f}?type=function'],
    'param:ast.depth': lambda f: [f'ast://{f}?depth=0'],
    'param:markdown.body-contains': lambda f: [f'markdown://{Path(f).parent}?body-contains=auth'],
    'param:markdown.fields': lambda f: [f'markdown://{Path(f).parent}?fields=title'],
    # BACK-2614: the legacy selectors are --view links / --view lint; aggregate is a standalone legacy word.
    'param:markdown.link-graph': lambda f: [f'markdown://{Path(f).parent}?link-graph'],
    'param:markdown.lint': lambda f: [f'markdown://{Path(f).parent}?lint'],
    'param:markdown.aggregate': lambda f: [f'markdown://{Path(f).parent}?aggregate=title'],
    'param:ast.callee_of': lambda f: [f'ast://{f}?callee_of=auth_gate'],
    'value:ast.show=calls': lambda f: [f'ast://{f}?show=calls'],
    # BACK-2613: show is --view; the calls view is a retired value on both spellings.
    'param:ast.show': lambda f: ['ast', f, '--show', 'dict-heatmap'],
    'value:ast.view=calls': lambda f: ['ast', f, '--view', 'calls'],
    'subcommand:trace': lambda f: ['trace', str(Path(f).parent), '--from', 'auth_gate'],
    'scheme:trace': lambda f: [f'trace://{Path(f).parent}?from=auth_gate'],
    # Phase 3 slice 3b (BACK-2068): review folded into check --changed plus diff.
    'subcommand:review': lambda f: ['review', str(Path(f).parent)],
    # Phase 3 slice 3c (BACK-2068): health is ops-only; a code path is check's.
    'target:health.code': lambda f: ['health', str(Path(f).parent)],
    # Phase 3 step 5 (BACK-2069): stats became metrics and absorbed classify; tests/test_metrics_acceptance_back2069.py
    # proves each old spelling answers like the new one.
    'scheme:stats': lambda f: [f'stats://{Path(f).parent}'],
    'scheme:classify': lambda f: [f'classify://{Path(f).parent}'],
    # Phase 4 lane P4-B (BACK-2160): testability became patches ?view=pressure; tests/test_patches_pressure_back2160.py
    # proves the old spellings answer like the new one.
    'subcommand:testability': lambda f: ['testability', str(Path(f).parent), '--tests', str(Path(f).parent)],
    'scheme:testability': lambda f: [f'testability://{Path(f).parent}?tests={Path(f).parent}'],
    # Phase 2 slice S6 (BACK-1054): depends answers from the imports:// engine's build; tests/test_depends_shim_back1054.py
    # and tests/test_dd_call_exit_contract_back2181.py prove the old shapes and exit code are kept.
    'scheme:depends': lambda f: [f'depends://{f}'],
    # Phase 2 slice S4 (BACK-1054): deps answers from one imports build; tests/test_deps_shim_back1054.py and
    # tests/test_dd_call_exit_contract_back2181.py prove the old shapes and exit codes are kept.
    'subcommand:deps': lambda f: ['deps', str(Path(f).parent)],
    'scheme:deps': lambda f: [f'deps://{Path(f).parent}'],
    # BACK-2225: python:// was removed outright and starts at the error stage; tests/test_python_scheme_removed_back2225.py
    # covers its other spellings.
    'scheme:python': lambda f: ['python://'],
    # BACK-2149: hotspots answers as before until the cut; tests/test_hotspots_retirement_back2149.py runs each
    # replacement and proves it gives the same ranking. A retired parameter of the retired noun notes beside it.
    'subcommand:hotspots': lambda f: ['hotspots', str(Path(f).parent)],
    'scheme:hotspots': lambda f: [f'hotspots://{Path(f).parent}'],
    'param:hotspots.functions_only': lambda f: [f'hotspots://{Path(f).parent}?functions_only=true'],
    'param:hotspots.files_only': lambda f: ['hotspots', str(Path(f).parent), '--files-only'],
    # BACK-2673: the main parser's flags a declared noun keeps, typed after an answer that reads them (one row per flag
    # per noun, generated from LEGACY_CLI_MODIFIERS; tests/test_legacy_slice_flags_back2673.py runs each on both
    # spellings).
    **{f'flag:{noun}.{flag}': (lambda request, typed: lambda f: [*request(f), *typed])(
        _FLAG_REQUESTS.get((noun, flag), _MODIFIER_REQUESTS[noun]), _MODIFIER_ARGV[flag])
       for noun, flags in LEGACY_CLI_MODIFIERS.items() for flag in flags},
}
# The row a case notes beside its own: a parameter of a noun that is itself retired.
ALSO_NOTED = {'param:hotspots.functions_only': 'scheme:hotspots', 'param:hotspots.files_only': 'subcommand:hotspots',
              'param:architecture.verbose': 'scheme:architecture', 'param:hotspots.verbose': 'scheme:hotspots',
              'param:testability.verbose': 'scheme:testability', 'param:deps.verbose': 'scheme:deps',
              'param:hotspots.top': 'scheme:hotspots', 'param:testability.top': 'scheme:testability',
              **{f'flag:{noun}.{flag}': f'scheme:{noun}' for noun in ('hotspots', 'testability')
                 for flag in LEGACY_CLI_MODIFIERS[noun]},
              'param:calls.type': 'param:calls.uncalled', 'param:calls.external': 'param:calls.modules',
              # ?show=calls spells show too; the retired value leaves no canonical form, so show says its row (BACK-2613)
              'value:ast.show=calls': 'param:ast.show'}


def test_every_production_row_is_well_formed():
    assert RETIREMENTS, 'the two BACK-1906 notes live in the table'
    for key, entry in RETIREMENTS.items():
        assert RETIREMENT_KEY.match(key), key
        assert entry.replacement.strip() and entry.old.strip(), key
        assert entry.stage in STAGES, key


def test_every_production_row_is_exercised_and_prints_once(source):
    # Tooling prints help rather than a data envelope; exercised separately below.
    assert set(RETIREMENTS) == set(PRODUCTION_CASES) | {'subcommand:scaffold'}
    for key, argv in PRODUCTION_CASES.items():
        if RETIREMENTS[key].stage == 'error':
            continue  # no answer to note on: the error-stage test below runs it
        result = _run_reveal_direct(*argv(str(source)), '--format', 'json')
        text = RETIREMENTS[key].text
        if result.stdout.lstrip().startswith('['):  # a bare legacy array (JSON ?data-only) has no meta: said on stderr
            assert _notes(result.stderr, text) == 1, (key, result.stderr)
            continue
        assert _notes(result.stderr, text) == 0, (key, result.stderr)  # the JSON carries it (BACK-2659)
        expected = [ALSO_NOTED[key], key] if key in ALSO_NOTED else [key]
        request = _request_field(argv(str(source)))
        own = [field for field in expected if not (request and invocation.request_note_covers(field))]  # the request note replaces a covered row
        assert sorted(w['field'] for w in _all_retired(json.loads(result.stdout))) == sorted(own + request), key


def test_a_removed_row_says_removed_and_is_an_error_from_the_start():
    # A note-stage row says how long it works (agent help: old spellings still work until 1.0, BACK-2716).
    assert Retirement('old://', 'new://').text == 'old:// is deprecated and works until 1.0; use new://.'
    # The cut wording of a renamed spelling does not change; only a removed one says so.
    assert Retirement('old://', 'new://', 'error').text == 'old:// is deprecated; use new://.'
    assert Retirement('old://', 'new://', 'error', removed=True).text == 'old:// was removed; use new://.'
    with pytest.raises(ValueError):
        Retirement('old://', 'new://', removed=True)
    assert [k for k, row in RETIREMENTS.items() if row.removed] == ['scheme:python']
    assert RETIREMENTS['scheme:python'].stage == 'error'
    assert RETIREMENTS['scheme:python'].text.startswith('python:// was removed; use python -m site')


def test_the_moved_notes_keep_their_wording():
    assert RETIREMENTS['flag:--search'].text == '--search is deprecated and works until 1.0; use --name PATTERN (regex).'
    assert RETIREMENTS['flag:--check'].text == (
        'file --check/--lint is deprecated and works until 1.0; use reveal check <path>.')


@pytest.mark.parametrize('key', ['subcommand:trace', 'scheme:trace', 'param:calls.root',
                                 'value:ast.show=calls', 'flag:--search', 'mcp:reveal_trace'])
def test_the_key_scheme_accepts_each_kind(key):
    assert RETIREMENT_KEY.match(key)


@pytest.mark.parametrize('key', ['trace', 'param:root', 'flag:search', 'Scheme:x', 'mcp:Reveal',
                                 'subcommand:'])
def test_the_key_scheme_rejects_an_unnamespaced_or_malformed_key(key):
    assert not RETIREMENT_KEY.match(key)


# --- MCP: the fact is in the tool result, never on stderr ------------------------------------

def test_mcp_returns_the_note_in_the_result_and_not_on_stderr(monkeypatch, source, capsys):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query
    uri = f'ast://{source}?name=auth*'
    base = reveal_query(uri)
    text = _retire(monkeypatch, 'param:ast.name', 'ast://?name=')
    capsys.readouterr()
    out = reveal_query(uri)
    assert capsys.readouterr().err == ''
    assert out.count(text) == 1 and base.count(text) == 0
    assert out.startswith(without_mcp_request_note(base).rstrip('\n'))
    # Provenance forces JSON: the fact is a parseable meta.warnings entry.
    doc = json.loads(reveal_query(uri, provenance=True))
    assert [w['old'] for w in _warnings(doc)] == ['ast://?name=']


def test_mcp_does_not_note_a_spelling_that_is_not_retired(monkeypatch, source):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query
    _retire(monkeypatch, 'param:ast.type', 'ast://?type=')
    out = reveal_query(f'ast://{source}?name=auth*')
    assert 'deprecated' not in without_mcp_request_note(out)
    assert not _warnings(json.loads(reveal_query(f'ast://{source}?name=auth*', provenance=True)))


def test_mcp_tool_names_are_a_kind_of_spelling(monkeypatch, source):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_trace
    base = reveal_trace(str(source.parent), 'auth_gate')
    text = _retire(monkeypatch, 'mcp:reveal_trace', 'reveal_trace', stage='phase7')
    assert reveal_trace(str(source.parent), 'auth_gate') == base
    text = _retire(monkeypatch, 'mcp:reveal_trace', 'reveal_trace', stage='note')
    out = reveal_trace(str(source.parent), 'auth_gate')
    assert out.count(text) == 1 and out.startswith(base.rstrip('\n'))


def test_the_log_is_per_invocation(monkeypatch, source):
    """A second invocation in the same process notes again (nothing leaks between calls)."""
    text = _retire(monkeypatch, 'param:ast.name', 'ast://?name=')
    for _ in range(2):
        result = _run_reveal_direct(f'ast://{source}?name=auth*')
        assert _notes(result.stderr, text) == 1
    assert not invocation.noted_retirements()


@pytest.mark.parametrize('key', sorted(PRODUCTION_CASES))
def test_a_production_row_at_the_error_stage_exits_2_with_its_text(monkeypatch, source, key):
    """The cut release flips a row's stage and nothing else: same text, exit 2, no answer. A removed row
    (python://) is already at the error stage and runs as it ships."""
    monkeypatch.setitem(RETIREMENTS, key, replace(RETIREMENTS[key], stage='error'))
    result = _run_reveal_direct(*PRODUCTION_CASES[key](str(source)), '--format', 'json')
    assert result.returncode == 2
    assert f'error: {RETIREMENTS[key].text}' in result.stderr
    assert result.stdout == ''


def test_declared_alias_flag_notes_the_spelling_used(monkeypatch, source):
    text = _retire(monkeypatch, 'param:ast.type', 'ast ?type= (--type)', 'kind= (--kind)')
    alias = _run_reveal_direct('ast', str(source), '--type', 'function', '--format', 'json')
    canonical = _run_reveal_direct('ast', str(source), '--kind', 'function', '--format', 'json')
    assert alias.returncode == canonical.returncode == 0
    assert _notes(alias.stderr, text) == 0  # the JSON carries it (BACK-2659)
    assert not _warnings(json.loads(canonical.stdout))
    assert _warnings(json.loads(alias.stdout))[0]['field'] == 'param:ast.type'
    assert _without_retirement_warning(json.loads(alias.stdout)) == _without_retirement_warning(json.loads(canonical.stdout))


@pytest.mark.parametrize('stage', ['note', 'error'])
def test_scaffold_retirement_on_its_text_help_path(monkeypatch, stage):
    row = replace(RETIREMENTS['subcommand:scaffold'], stage=stage)
    monkeypatch.setitem(RETIREMENTS, 'subcommand:scaffold', row)
    result = _run_reveal_direct('scaffold', '--help')
    assert result.returncode == (0 if stage == 'note' else 2)
    assert result.stderr.count(row.text) == 1
    if stage == 'note':
        assert 'Scaffold new reveal components' in result.stdout
