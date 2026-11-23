"""One truncation entry names every cut that shaped its list (BACK-2653).

A noun's own ``?limit`` cuts a list, then the router's ``--max-items`` or ``--head`` cuts the page
again. ``note_truncation`` merges both into one entry with the right numbers, but it replaced the
cause and hint with the last cut's: ``ast://dir?limit=4 --max-items 1`` said "showing 1 of 24 — raise
--max-items", though raising it only reaches 4. ``cause`` stays the cut that set ``shown``; the merged
entry adds ``causes`` (that cut first, then the others) and the message names both hints, the binding
cut's first. A list cut once is unchanged: no ``causes`` key.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.utils.results import note_truncation, truncations_of

pytestmark = pytest.mark.component

LIMIT_HINT = 'raise --limit N or page with --offset N'  # the flags, not URI query fragments (BACK-2713)


def test_single_cut_is_unchanged():
    result = {}
    note_truncation(result, 'results', 4, 24, 'limit')
    (entry,) = truncations_of(result)
    assert entry == {'type': 'truncated', 'field': 'results', 'shown': 4, 'total': 24, 'exact': True,
                     'cause': 'limit', 'message': f'results: showing 4 of 24 — {LIMIT_HINT}'}


def test_router_cut_after_limit_names_both_binding_first():
    result = {}
    note_truncation(result, 'results', 4, 24, 'limit')
    note_truncation(result, 'results', 1, 4, 'max_items')
    (entry,) = truncations_of(result)
    assert (entry['shown'], entry['total'], entry['cause']) == (1, 24, 'max_items')
    assert entry['causes'] == ['max_items', 'limit']
    assert entry['message'] == f'results: showing 1 of 24 — raise --max-items; {LIMIT_HINT}'


def test_the_earlier_cuts_own_hint_is_kept():
    result = {}
    note_truncation(result, 'modules', 3, 9, 'limit', hint='raise ?top=N')
    note_truncation(result, 'modules', 1, 3, 'max_items')
    (entry,) = truncations_of(result)
    assert entry['message'] == 'modules: showing 1 of 9 — raise --max-items; raise ?top=N'


def test_a_cut_that_does_not_bind_keeps_the_binding_cause():
    result = {}
    note_truncation(result, 'rows', 2, 10, 'max_items')
    note_truncation(result, 'rows', 5, 10, 'limit')
    (entry,) = truncations_of(result)
    assert (entry['shown'], entry['cause'], entry['causes']) == (2, 'max_items', ['max_items', 'limit'])
    assert entry['message'] == f'rows: showing 2 of 10 — raise --max-items; {LIMIT_HINT}'


def test_a_hintless_binding_cut_still_names_the_other_hint():
    result = {}
    note_truncation(result, 'files', 4, 6, 'limit')
    note_truncation(result, 'files', 2, 4, 'head')
    (entry,) = truncations_of(result)
    assert (entry['cause'], entry['causes']) == ('head', ['head', 'limit'])
    assert entry['message'] == f'files: showing 2 of 6 — {LIMIT_HINT}'


def test_three_cuts_list_each_cause_once():
    result = {}
    note_truncation(result, 'files', 4, 6, 'limit')
    note_truncation(result, 'files', 3, 4, 'head')
    note_truncation(result, 'files', 1, 3, 'max_items')
    (entry,) = truncations_of(result)
    assert entry['causes'] == ['max_items', 'head', 'limit']
    assert entry['message'] == f'files: showing 1 of 6 — raise --max-items; {LIMIT_HINT}'


@pytest.fixture
def pkg(tmp_path):
    root = tmp_path / 'pkg'
    root.mkdir()
    for i in range(6):
        (root / f'm{i}.py').write_text(f'def f{i}():\n    return {i}\n\n\ndef g{i}():\n    return f{i}()\n',
                                       encoding='utf-8')
    return root


@pytest.mark.parametrize('scheme,field', [('ast', 'results'), ('metrics', 'files')])
def test_limit_then_max_items_on_the_cli(pkg, scheme, field):
    result = _run_reveal_direct(f'{scheme}://{pkg.as_posix()}?limit=4', '--max-items', '1', '--format', 'json')
    assert result.returncode == 0, result.stderr[-500:]
    (entry,) = [w for w in truncations_of(json.loads(result.stdout)) if w['field'] == field]
    assert entry['shown'] == 1 and entry['cause'] == 'max_items' and entry['causes'] == ['max_items', 'limit']
    text = _run_reveal_direct(f'{scheme}://{pkg.as_posix()}?limit=4', '--max-items', '1')
    assert f'raise --max-items; {LIMIT_HINT}' in text.stdout + text.stderr


def test_max_items_alone_has_no_causes_key(pkg):
    """Control: one cut, one cause, as before."""
    result = _run_reveal_direct(f'ast://{pkg.as_posix()}', '--max-items', '1', '--format', 'json')
    (entry,) = truncations_of(json.loads(result.stdout))
    assert entry['cause'] == 'max_items' and 'causes' not in entry
