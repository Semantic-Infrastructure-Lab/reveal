"""Answers' next-step hints and truncation hints name flags, not URI query fragments (BACK-2713, D20).

COMMAND_MODEL rule 2: an analysis noun is taught as ``reveal NOUN TARGET --flags``, and an option as the noun's
flag. The self-consistency judge (``test_self_consistency_back2654.py``) runs every printed ``scheme://`` command an
answer shows and now faults the URI request's own note on those answers too; it cannot see a bare fragment
("raise ?limit=N", "use ?builtins=true", "use suppress=false") or a hint that never reaches its fixture (file
breadcrumbs, diff next steps, deps' next steps). This file checks those directly: each named line drops the old
fragment and prints the flag. The fragments are read from the product's real output where a fixture reaches them,
else from the renderer or producer itself.
"""
import json
import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from teaching_patterns import retiring_lines
from reveal.adapters.calls.adapter import CallsAdapter
from reveal.adapters.overview import DIAGNOSTIC_CUT_HINT, _next_steps
from reveal.rendering.adapters.deps import _render_circular, _render_next_steps, _render_unused
from reveal.rendering.diff import _render_diff_breadcrumbs
from reveal.utils import breadcrumbs
from reveal.utils.results import note_truncation

_COMPLEX = '''\
def {name}(value):
    if value:
        for item in value:
            if item == 'a':
                while time.time() < 0:
                    if os.getenv('X'):
                        try:
                            subprocess.run(['true'], check=False, timeout=5)
                        except OSError:
                            pass
    with open(os.devnull, encoding='utf-8') as handle:
        return {tail}
'''


@pytest.fixture(scope='module')
def proj(tmp_path_factory):
    """Three modules that import each other, call builtins, and branch deeply; tests that patch two project
    functions and ``sys.stdout`` three times each: enough rows for each cut below at ``--limit 1``."""
    root = tmp_path_factory.mktemp('hints') / 'proj'
    (root / 'pkg').mkdir(parents=True)
    (root / 'tests').mkdir()
    (root / 'pkg' / '__init__.py').write_text('', encoding='utf-8')
    (root / 'pkg' / 'app.py').write_text(
        "from pkg import core, util\n\n\ndef main():\n    size = len('ab')\n"
        "    return util.helper(core.work(str(size)))\n", encoding='utf-8')
    head = 'import os\nimport subprocess\nimport time\n'
    (root / 'pkg' / 'core.py').write_text(
        head + '\n\n' + _COMPLEX.format(name='work', tail='str(handle.read()) + str(value)'), encoding='utf-8')
    (root / 'pkg' / 'util.py').write_text(
        head + '\nfrom pkg import core\n\n\n' + _COMPLEX.format(name='helper', tail='core.work(handle.read() + value)'),
        encoding='utf-8')
    tests = ['from unittest import mock', '', 'import pkg.app', '']
    for target in ('pkg.util.helper', 'pkg.core.work', 'sys.stdout'):
        for i in range(3):
            tests += [f"@mock.patch('{target}')", f"def test_{target.replace('.', '_')}_{i}(patched):",
                      '    assert pkg.app.main is not None', '']
    (root / 'tests' / 'test_app.py').write_text('\n'.join(tests), encoding='utf-8')
    return root


def _reveal(cwd, *args, code=0):
    proc = subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=cwd, capture_output=True, text=True,
                          encoding='utf-8', timeout=120)
    assert proc.returncode == code, (args, proc.returncode, proc.stderr)
    return proc


def _cut_messages(cwd, *args):
    """The truncation messages (``FIELD: showing N of M -- HINT``) of a JSON answer."""
    doc = json.loads(_reveal(cwd, *args, '--format', 'json').stdout)
    return [w['message'] for w in doc['meta']['warnings'] if 'showing' in str(w.get('message'))]


def _printed(func, *args, **kwargs):
    out = StringIO()
    with redirect_stdout(out):
        func(*args, **kwargs)
    return out.getvalue()


def _assert_names_flags(text, gone, present):
    for fragment in gone:
        assert fragment not in text, f'still prints {fragment!r}:\n{text}'
    for fragment in present:
        assert fragment in text, f'does not print {fragment!r}:\n{text}'


# --- the shared truncation hint (utils/results.py) ---------------------------------------------------------

@pytest.mark.parametrize('cause, gone, present', [
    ('limit', ['?limit=N', '?offset=N'], ['raise --limit N or page with --offset N']),
    ('auto_cap', ['?limit=N'], ['add filters, or set --limit N']),
])
def test_the_shared_truncation_hint_names_flags(cause, gone, present):
    result = {}
    note_truncation(result, 'rows', 1, 2, cause)
    [message] = [w['message'] for w in result['meta']['warnings']]
    _assert_names_flags(message, gone, present)
    assert not retiring_lines(message)


@pytest.mark.parametrize('cause, hint', [('max_items', 'raise --max-items'),
                                         ('display_cap', 'use --all for everything, or --max-items N')])
def test_the_flag_hints_are_unchanged(cause, hint):
    """Negative control: the causes whose hint already named a flag print it as before."""
    result = {}
    note_truncation(result, 'rows', 1, 2, cause)
    assert result['meta']['warnings'][0]['message'] == f'rows: showing 1 of 2 — {hint}'


# --- each noun's own truncation hint, on its real answer ---------------------------------------------------

@pytest.mark.parametrize('args, field, present', [
    (('imports', '.', '--sort=-fan-in'), 'entries', 'raise --limit N (0 = all)'),     # adapters/imports.py
    (('patches', 'tests'), 'groups', 'raise --limit N'),                               # adapters/patches/adapter.py
    (('patches', '.', '--view', 'pressure'), 'patch_hotspots', 'raise --limit N'),    # testability/report.py
    (('metrics', '.', '--view', 'hotspots'), 'hotspots', 'raise --limit N'),           # adapters/stats/adapter.py
    (('calls', '.', '--sort=-callers'), 'entries', 'raise --limit N (0 = all)'),       # adapters/calls/adapter.py
], ids=['imports-fan-in', 'patches', 'patches-pressure', 'metrics-hotspots', 'calls-ranking'])
def test_a_noun_truncation_hint_names_its_flag(proj, args, field, present):
    messages = [m for m in _cut_messages(proj, *args, '--limit', '1') if m.startswith(f'{field}:')]
    assert messages, f'{args}: no {field} cut at --limit 1 (the fixture went vacuous)'
    for message in messages:
        _assert_names_flags(message, ['?limit', '?top', '?offset'], [present])
        assert not retiring_lines(message)


# --- bare control fragments in answer text -----------------------------------------------------------------

@pytest.mark.parametrize('extra, gone, present', [
    ((), ['use ?builtins=true'], ['builtin(s) hidden — use --builtins to include']),         # renderer 220
    (('--depth', '2'), ['use ?builtins=true'], ['hidden at level 1 — use --builtins to include']),  # 256
], ids=['callees', 'callee-walk'])
def test_calls_builtins_line_names_the_flag(proj, extra, gone, present):
    _assert_names_flags(_reveal(proj, 'calls', '.', '--callees', 'main', *extra).stdout, gone, present)


def test_calls_schema_note_names_the_builtins_flag():
    """help://schemas/calls prints this note."""
    notes = ' '.join(CallsAdapter.get_schema()['notes'])
    _assert_names_flags(notes, ['use ?builtins=true'], ['--builtins includes them'])


def test_patches_suppression_line_names_the_flag(proj):
    _assert_names_flags(_reveal(proj, 'patches', 'tests').stdout, ['use suppress=false'],
                        ['suppressed — use --suppress off to include'])


def test_calls_limit_error_names_limit(proj):
    """``--limit -1`` is refused naming the flag's own word, not the retired ``top``."""
    err = _reveal(proj, 'calls', '.', '--sort=-callers', '--limit', '-1', code=2).stderr
    _assert_names_flags(err, ['top must be'], ["limit must be a non-negative integer (got '-1')"])


# --- next-step hints ---------------------------------------------------------------------------------------

def test_imports_default_answer_teaches_its_flags(proj):
    text = _reveal(proj, 'imports', '.').stdout
    _assert_names_flags(text, ['Query options:', "imports://"],
                        ['reveal imports . --unused', 'reveal imports . --circular',
                         'reveal imports . --violations', 'reveal imports . --sort=-fan-in'])
    assert not retiring_lines(text)


def test_overview_next_steps_are_subcommands():
    commands = [step['command'] for step in _next_steps('src', ['vendor'], False)]
    assert commands == [
        'reveal imports src --sort=-fan-in --scope path --respect-gitignore off --exclude vendor',
        'reveal imports src --components --scope path --respect-gitignore off --exclude vendor',
        'reveal imports src --entrypoints --scope path --respect-gitignore off --exclude vendor',
        'reveal imports src --circular --scope path --respect-gitignore off --exclude vendor',
        'reveal metrics src --respect-gitignore off --exclude vendor',
        'reveal ast src --kind function --sort=-complexity --respect-gitignore off --exclude vendor',
        'reveal check src --respect-gitignore off --exclude vendor',
    ]
    assert "'my dir'" in _next_steps('my dir', [], True)[0]['command']  # a path with a space stays one word
    _assert_names_flags(DIAGNOSTIC_CUT_HINT, ['imports://'], ['reveal imports'])


def test_deps_next_steps_are_subcommands():
    text = '\n'.join(_render_next_steps(Path('src')) + _render_circular([['a.py', 'b.py']] * 2, 2, Path('src'), 1)
                     + _render_unused([{'file': 'a.py', 'line': 1}] * 2, Path('src'), 1))
    _assert_names_flags(text, ['imports://'], ['reveal imports src --circular', 'reveal imports src --unused',
                                               'reveal imports src --violations'])
    assert not retiring_lines(text)


@pytest.fixture
def every_hint(monkeypatch):
    """Show-once hints print every time, so each producer's line is read."""
    monkeypatch.setattr(breadcrumbs, '_show_hint_once', lambda hint_id, lines: [print(line) for line in lines] or True)


def test_file_breadcrumbs_are_subcommands(every_hint):
    text = _printed(breadcrumbs._suggest_imports_analysis, 'app.py', 'python', {'imports': [{}] * 6})
    text += _printed(breadcrumbs._suggest_ast_queries_for_large_file, 'app.py', 'python', {'functions': [{}] * 21})
    text += _printed(breadcrumbs._handle_quality_check, 'app.py', 'python',
                     detections=[SimpleNamespace(rule_code='E501', context='')])
    text += _printed(breadcrumbs._handle_directory_check, 'src', None, total_issues=2, files_checked=3)
    _assert_names_flags(text, ['imports://', 'ast://', 'metrics://'],
                        ['reveal imports app.py', "reveal ast app.py --where 'complexity>10'",
                         "reveal ast app.py --where 'lines>50'", 'reveal metrics app.py', 'reveal metrics src'])
    assert not retiring_lines(text)


@pytest.mark.parametrize('left, right', [({'uri': 'git://HEAD/app.py'}, {'uri': 'git://.//app.py', 'file': 'app.py'}),
                                         ({'uri': 'fa.py'}, {'uri': 'app.py', 'file': 'app.py'})],
                         ids=['code-review', 'file-pair'])
def test_diff_next_steps_are_subcommands(left, right):
    text = _printed(_render_diff_breadcrumbs, left, right, {'functions': []})
    _assert_names_flags(text, ['metrics://', 'imports://'], ['reveal metrics app.py'])
    if 'git://' in left['uri']:
        assert 'reveal imports . --circular' in text
    assert not retiring_lines(text)


# --- the checks bite ---------------------------------------------------------------------------------------

@pytest.mark.parametrize('line', [
    "entries: showing 1 of 5 — raise ?limit=N (--limit N; 0 = all)",
    'rows: showing 1 of 2 — raise ?limit=N or page with ?offset=N',
    'entries: showing 2 of 393 — raise ?top=N',
    "  reveal 'imports://.?unused'       - Find unused imports",
    "      reveal 'ast://app.py?complexity>10'   # Find complex functions",
    '      reveal metrics://app.py      # Analyze complexity trends',
    'reveal imports://src?sort=-fan-in&scope=path',
    'imports:// on the same path with --format json names every file',
])
def test_the_retiring_check_bites_today_s_lines(line):
    """Positive control: lines these producers printed before this change are flagged."""
    assert retiring_lines(line) == [line.strip()]


@pytest.mark.parametrize('line', ['raise --limit N or page with --offset N', 'reveal imports . --unused',
                                  "reveal ast app.py --where 'complexity>10'", 'use --suppress off to include'])
def test_the_retiring_check_passes_flags(line):
    assert retiring_lines(line) == []
