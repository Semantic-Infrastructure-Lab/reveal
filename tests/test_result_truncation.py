"""Truncation as an outcome (BACK-1059): one marker for a cut list, one place it is printed.

``reveal.utils.results.note_truncation`` is the one way a result says a list was cut: a
``meta.warnings`` entry ``{'type': 'truncated', 'field', 'shown', 'total', 'cause',
'message'}``. ``outcome_of`` reads it as ``truncated``, which exits 0.
``cli/routing/uri._emit_result`` prints it after the render: on stdout for text, on
stderr for grep, and not at all for JSON, which already carries it.

Before, truncation was spelled six ways, and text renderers that didn't know a given
spelling showed a cut list as complete. ``ast://DIR --max-items 3`` printed "Results: 45"
above 3 results, and its JSON ``displayed_results`` said 45. ``stats://DIR?limit=2`` and
``markdown://DIR?limit=2`` rendered 2 entries with nothing saying there were more.
"""

import json

import pytest

from conftest import _run_reveal_direct
from reveal.utils.results import (
    note_truncation, outcome_of, relabel_truncations, truncations_of,
)
from reveal.utils.warning_render import render_meta_warnings


# -- the marker --------------------------------------------------------------------------

def test_note_truncation_records_one_entry():
    result = {'type': 't', 'results': [1, 2]}
    note_truncation(result, 'results', 2, 9, 'limit')
    [cut] = truncations_of(result)
    assert cut == {
        'type': 'truncated', 'field': 'results', 'shown': 2, 'total': 9, 'cause': 'limit',
        'message': 'results: showing 2 of 9 — raise ?limit=N or page with ?offset=N',
    }


@pytest.mark.parametrize('shown, total', [(9, 9), (10, 9), (0, 0)])
def test_nothing_is_recorded_when_nothing_was_cut(shown, total):
    result = {'type': 't'}
    note_truncation(result, 'results', shown, total, 'limit')
    assert result == {'type': 't'}


@pytest.mark.parametrize('meta', [None, {}, {'warnings': None}])
def test_note_truncation_creates_what_meta_lacks(meta):
    result = {'type': 't', 'meta': meta}
    note_truncation(result, 'results', 1, 2, 'limit')
    assert len(truncations_of(result)) == 1


def test_other_warnings_are_kept():
    result = {'type': 't', 'meta': {'warnings': [{'type': 'unknown_sort_field', 'message': 'x'}]}}
    note_truncation(result, 'results', 1, 2, 'limit')
    assert [w['type'] for w in result['meta']['warnings']] == ['unknown_sort_field', 'truncated']


def test_a_second_cut_of_one_field_updates_its_entry():
    """The adapter's ?limit=10, then the router's --max-items 3: one disclosure, of 3
    against the adapter's total."""
    result = {'type': 't'}
    note_truncation(result, 'results', 10, 45, 'limit')
    note_truncation(result, 'results', 3, 10, 'max_items')
    [cut] = truncations_of(result)
    assert (cut['shown'], cut['total'], cut['cause']) == (3, 45, 'max_items')
    assert cut['message'] == 'results: showing 3 of 45 — raise --max-items'


def test_cuts_of_different_fields_are_separate():
    result = {'type': 't'}
    note_truncation(result, 'files', 1, 5, 'limit')
    note_truncation(result, 'hotspots', 2, 7, 'limit')
    assert [c['field'] for c in truncations_of(result)] == ['files', 'hotspots']


def test_a_cut_without_a_known_cause_has_no_hint():
    result = {'type': 't'}
    note_truncation(result, 'results', 1, 5, 'head')
    assert truncations_of(result)[0]['message'] == 'results: showing 1 of 5'


def test_relabel_restates_a_childs_cut_as_the_parents():
    child = {'type': 'ast_query'}
    note_truncation(child, 'results', 5, 97, 'limit')
    relabel_truncations(child, 'complex_functions', 'raise ?top=N')
    [cut] = truncations_of(child)
    assert cut['field'] == 'complex_functions'
    assert cut['message'] == 'complex_functions: showing 5 of 97 — raise ?top=N'


@pytest.mark.parametrize('result, expected', [
    ({'type': 't', 'meta': {'warnings': [{'type': 'truncated', 'field': 'r', 'shown': 1,
                                          'total': 2, 'message': 'm'}]}}, 'truncated'),
    # Failure wins over truncation.
    ({'type': 't', 'error': 'boom',
      'meta': {'warnings': [{'type': 'truncated', 'message': 'm'}]}}, 'failed'),
    # Other warnings are not a cut.
    ({'type': 't', 'meta': {'warnings': [{'type': 'unknown_sort_field'}]}}, 'ok'),
])
def test_outcome_of_reads_the_marker(result, expected):
    assert outcome_of(result) == expected


def test_renderers_leave_truncation_to_the_router(capsys):
    result = {'meta': {'warnings': [{'type': 'truncated', 'message': 'results: showing 1 of 2'},
                                    {'type': 'other', 'message': 'kept'}]}}
    render_meta_warnings(result)
    out = capsys.readouterr().out
    assert 'kept' in out
    assert 'showing 1 of 2' not in out


# -- the seam, end to end ----------------------------------------------------------------

@pytest.fixture
def proj(tmp_path, monkeypatch):
    for i in range(3):
        (tmp_path / f'mod{i}.py').write_text(
            ''.join(f'def f{i}_{j}():\n    return {j}\n' for j in range(3)), encoding='utf-8')
        (tmp_path / f'doc{i}.md').write_text(f'# Doc {i}\n', encoding='utf-8')
    (tmp_path / 'data.json').write_text(json.dumps([{'n': i} for i in range(4)]),
                                        encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


# (argv, field, shown, total): each was a silent cut in text before BACK-1059's slice 2.
CUTS = [
    (['ast://.?type=function', '--max-items', '2'], 'results', 2, 9),
    (['ast://.?type=function&limit=2'], 'results', 2, 9),
    (['ast://.?type=function', '--head', '1'], 'results', 1, 9),
    (['stats://.?limit=1'], 'files', 1, 7),
    (['markdown://.?limit=1'], 'results', 1, 3),
    (['json://data.json?limit=1'], 'value', 1, 4),
]


@pytest.mark.parametrize('argv, field, shown, total', CUTS)
def test_text_says_what_was_cut_once(proj, argv, field, shown, total):
    r = _run_reveal_direct(*argv)
    assert r.returncode == 0, r.stderr
    line = f'⚠ Truncated {field}: showing {shown} of {total}'
    assert r.stdout.count(line) == 1, r.stdout
    assert r.stdout.count('showing') == 1, r.stdout


@pytest.mark.parametrize('argv, field, shown, total', CUTS)
def test_json_carries_the_cut_and_prints_nothing_else(proj, argv, field, shown, total):
    r = _run_reveal_direct(*argv, '--format', 'json')
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert outcome_of(payload) == 'truncated'
    [cut] = truncations_of(payload)
    assert (cut['field'], cut['shown'], cut['total']) == (field, shown, total)
    assert len(payload[field]) == shown
    if 'displayed_results' in payload:
        assert payload['displayed_results'] == shown


def test_max_items_keeps_the_documented_budget_block(proj):
    """meta.budget (FIELD_SELECTION_GUIDE's agent loop) is still there, and now under
    meta.budget even when the result had no meta of its own."""
    r = _run_reveal_direct('markdown://.', '--max-items', '1', '--format', 'json')
    payload = json.loads(r.stdout)
    budget = payload['meta']['budget']
    assert (budget['truncated'], budget['returned'], budget['total_available']) == (True, 1, 3)


def test_grep_output_stays_parseable(proj):
    r = _run_reveal_direct('ast://.?type=function', '--max-items', '2', '--format', 'grep')
    assert r.returncode == 0
    assert len(r.stdout.splitlines()) == 2
    assert 'Truncated' not in r.stdout
    assert '⚠ Truncated results: showing 2 of 9' in r.stderr


@pytest.mark.parametrize('argv', [
    ['ast://.?type=function'],
    ['ast://.?type=function', '--max-items', '50'],
    ['stats://.'],
    ['markdown://.'],
    ['json://data.json'],
])
def test_an_uncut_answer_says_nothing(proj, argv):
    """Positive control: no cut, no line, outcome ok."""
    r = _run_reveal_direct(*argv)
    assert r.returncode == 0, r.stderr
    assert 'Truncated' not in r.stdout + r.stderr
    payload = json.loads(_run_reveal_direct(*argv, '--format', 'json').stdout)
    assert outcome_of(payload) == 'ok'


def test_a_composite_names_its_own_list(proj):
    """overview:// shows ast://'s cut results as its complex_functions, cut by ?top."""
    branches = ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(12))
    for name in ('a', 'b'):
        (proj / f'cx_{name}.py').write_text(f'def {name}(x):\n{branches}    return -1\n',
                                            encoding='utf-8')
    r = _run_reveal_direct('overview://.?top=1&no_git=true')
    assert r.returncode == 0, r.stderr
    assert '⚠ Truncated complex_functions: showing 1 of 2 — raise ?top=N' in r.stdout
    assert 'Truncated results' not in r.stdout


# -- the subcommand forms (BACK-1544) -----------------------------------------------------

def _two_complex_functions(proj, branches=12):
    branches = ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(branches))
    for name in ('a', 'b'):
        (proj / f'cx_{name}.py').write_text(f'def {name}(x):\n{branches}    return -1\n',
                                            encoding='utf-8')


def test_the_subcommand_says_what_its_uri_form_says(proj):
    """``reveal overview`` printed its cut line until slice 2 left cut lists to the URI
    router, which subcommands never reach; it then printed nothing (BACK-1544)."""
    _two_complex_functions(proj)
    r = _run_reveal_direct('overview', '.', '--top', '1', '--no-git')
    assert r.returncode == 0, r.stderr
    assert r.stdout.count('⚠ Truncated complex_functions: showing 1 of 2 — raise ?top=N') == 1
    uri = _run_reveal_direct('overview://.?top=1&no_git=true')
    assert uri.stdout.splitlines()[-1] == r.stdout.splitlines()[-1]


def test_a_subcommand_cut_is_printed_before_its_findings_exit(proj):
    """hotspots exits 1 on findings (EXIT_CODE_CONTRACT); the cut line still prints first."""
    _two_complex_functions(proj, branches=24)  # complexity > 20 is a hotspots finding
    r = _run_reveal_direct('hotspots', '.', '--top', '1', '--min-complexity', '1')
    assert r.returncode == 1
    assert '⚠ Truncated function_hotspots: showing 1 of ' in r.stdout
    payload = json.loads(_run_reveal_direct(
        'hotspots', '.', '--top', '1', '--min-complexity', '1', '--format', 'json').stdout)
    # Both files score as hotspots too; that cut was silent until BACK-1543.
    assert sorted(c['field'] for c in truncations_of(payload)) == [
        'file_hotspots', 'function_hotspots']


def test_an_uncut_subcommand_says_nothing(proj):
    """Negative control for the two tests above."""
    _two_complex_functions(proj)
    r = _run_reveal_direct('overview', '.', '--no-git')
    assert r.returncode == 0, r.stderr
    assert 'Truncated' not in r.stdout + r.stderr


# -- an adapter's own cap (BACK-1543) -------------------------------------------------------

def _two_hotspot_files(proj):
    """Two files deep nesting alone makes hotspots of (no churn: tmp_path is no git repo)."""
    nested = 'def f(x):\n' + ''.join('    ' * (i + 1) + f'if x > {i}:\n' for i in range(6)) \
        + '    ' * 7 + 'return x\n    return 0\n'
    for name in ('a', 'b'):
        (proj / f'deep_{name}.py').write_text(nested, encoding='utf-8')


# (argv, field): stats ranked every hotspot file, then kept ?top=N and dropped the total.
OWN_CAPS = [
    (['stats://.?hotspots=true&top=1'], 'hotspots'),
    (['hotspots://.?top=1'], 'file_hotspots'),
    (['hotspots', '.', '--top', '1'], 'file_hotspots'),
    (['overview://.?top=1&no_git=true&no_imports=true'], 'hotspots'),
    (['overview', '.', '--top', '1', '--no-git', '--no-imports'], 'hotspots'),
]


@pytest.mark.parametrize('argv, field', OWN_CAPS)
def test_an_adapters_own_cap_is_disclosed(proj, argv, field):
    _two_hotspot_files(proj)
    r = _run_reveal_direct(*argv)
    assert f'⚠ Truncated {field}: showing 1 of 2 — raise ?top=N' in r.stdout, r.stdout
    payload = json.loads(_run_reveal_direct(*argv, '--format', 'json').stdout)
    cuts = {c['field']: (c['shown'], c['total']) for c in truncations_of(payload)}
    assert cuts[field] == (1, 2)


@pytest.mark.parametrize('argv', [
    ['stats://.?hotspots=true&top=0'],
    ['hotspots://.?top=0'],
])
def test_top_zero_lists_every_hotspot(proj, argv):
    """0 means no cap (BACK-1505); stats:// gave [:0], an empty list that reads as clean."""
    _two_hotspot_files(proj)
    payload = json.loads(_run_reveal_direct(*argv, '--format', 'json').stdout)
    field = 'hotspots' if 'hotspots' in payload else 'file_hotspots'
    assert len(payload[field]) == 2
    assert truncations_of(payload) == []


def test_all_reaches_the_overview_uri_forms_data(proj):
    """--all lifted overview://'s render cap only: the data kept ?top's default 5, so
    'overview://X --all' printed 'showing 5 of 387' complex functions (BACK-1543)."""
    branches = ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(12))
    for i in range(6):
        (proj / f'cx_{i}.py').write_text(f'def c{i}(x):\n{branches}    return -1\n',
                                         encoding='utf-8')
    capped = _run_reveal_direct('overview://.?no_git=true&no_imports=true')
    assert '⚠ Truncated complex_functions: showing 5 of 6' in capped.stdout
    r = _run_reveal_direct('overview://.?no_git=true&no_imports=true', '--all')
    assert r.returncode == 0, r.stderr
    assert 'Truncated' not in r.stdout + r.stderr


class _Args:
    def __init__(self, fmt):
        self.format = fmt


def _emit(result, fmt, capsys):
    from reveal.cli.routing.subcommand import emit_subcommand_result
    rendered = []
    code = 0
    try:
        emit_subcommand_result(result, _Args(fmt), name='demo', source='/src',
                               render=rendered.append)
    except SystemExit as exc:
        code = exc.code
    out, err = capsys.readouterr()
    return code, out, err, rendered


def test_emit_subcommand_result_prints_a_cut_after_the_render(capsys):
    result = {'items': [1]}
    note_truncation(result, 'items', 1, 5, 'limit')
    code, out, err, rendered = _emit(result, 'text', capsys)
    assert (code, rendered) == (0, [result])
    assert out.strip().startswith('⚠ Truncated items: showing 1 of 5 — raise ?limit=N')
    code, out, err, rendered = _emit(result, 'grep', capsys)
    assert (code, out.strip()) == (0, '')
    assert '⚠ Truncated items: showing 1 of 5' in err


def test_emit_subcommand_result_json_is_the_subcommands_envelope(capsys):
    result = {'contract_version': '1.1', 'type': 'demo_scan', 'source': 'rel', 'items': [1]}
    note_truncation(result, 'items', 1, 5, 'limit')
    code, out, err, rendered = _emit(result, 'json', capsys)
    payload = json.loads(out)
    assert (code, rendered, err) == (0, [], '')
    assert (payload['contract_version'], payload['type'], payload['source']) == ('1.1', 'demo', '/src')
    assert truncations_of(payload)[0]['field'] == 'items'


@pytest.mark.parametrize('fmt', ['text', 'json'])
def test_emit_subcommand_result_fails_a_failed_result(fmt, capsys):
    """A top-level error exits 1 after the output, as the URI form does (BACK-1059)."""
    code, out, err, rendered = _emit({'error': 'boom'}, fmt, capsys)
    assert code == 1
    assert 'Error (reveal demo): boom' in err
    if fmt == 'json':
        assert json.loads(out)['error'] == 'boom'
    else:
        assert rendered == [{'error': 'boom'}]
