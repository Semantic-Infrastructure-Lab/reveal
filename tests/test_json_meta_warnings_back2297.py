"""BACK-2297: json:// put its warnings at the top level of the result, not in ``meta.warnings``.

``JsonAdapter._build_success_result`` copied the query metadata onto the result with
``result.update(metadata)``, so ``unknown_filter_field``, ``unknown_sort_field`` and
``sort_failed`` landed in a top-level ``warnings`` list. Every other adapter records them in
``meta.warnings`` (``note_warning``), which is where the output seam reads the ``?sort=``
notes it prints once after the render, and where a JSON reader looks. Each entry now goes
through ``note_warning`` with its keys unchanged, and ``sort_failed`` is a result-control
note like ``unknown_sort_field``.
"""

import json

import pytest

from conftest import _run_reveal_in
from reveal.adapters.json.adapter import JsonAdapter
from reveal.adapters.json.renderer import JsonRenderer
from reveal.utils.results import RESULT_CONTROL_WARNINGS, result_control_notes_of

_SORT_FAILED = "Not sorted by 'a'"
_UNKNOWN_SORT = "sort field 'nosuch' is not a field of any result"
_UNKNOWN_FILTER = "Filter field(s) 'zzz' never appear on any scanned item"


@pytest.fixture
def data(tmp_path):
    (tmp_path / 'mixed.json').write_text(json.dumps([{'a': 1}, {'a': 'x'}, {'a': 3}]),
                                         encoding='utf-8')
    (tmp_path / 'arr.json').write_text(json.dumps([{'a': 2}, {'a': 1}]), encoding='utf-8')
    return tmp_path


# (file, query, the one warning it records with every key it had before the move)
_CASES = [
    ('mixed.json', 'sort=a', {
        'type': 'sort_failed',
        'message': "Not sorted by 'a': '<' not supported between instances of 'str' and 'int'",
    }),
    ('arr.json', 'sort=-nosuch', {
        'type': 'unknown_sort_field',
        'field': 'nosuch',
        'message': "sort field 'nosuch' is not a field of any result, so results are unsorted. "
                   "Sortable: a",
    }),
    ('arr.json', 'zzz=1', {
        'type': 'unknown_filter_field',
        'message': "Filter field(s) 'zzz' never appear on any scanned item — this may be a "
                   "typo rather than a genuine zero-match. See: reveal help://json",
    }),
]
_IDS = [warning['type'] for _f, _q, warning in _CASES]


@pytest.mark.parametrize('name, query, expected', _CASES, ids=_IDS)
def test_warning_is_in_meta_warnings_with_its_keys(data, name, query, expected):
    result = JsonAdapter(str(data / name), query).get_structure()
    assert 'warnings' not in result
    assert result['meta']['warnings'] == [expected]


@pytest.mark.parametrize('name, query, expected', _CASES, ids=_IDS)
def test_json_output_carries_it_in_meta(data, name, query, expected):
    run = _run_reveal_in(data, f'json://{name}?{query}', '--format', 'json')
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert 'warnings' not in result
    assert result['meta']['warnings'] == [expected]


@pytest.mark.parametrize('name, query, message', [
    ('mixed.json', 'sort=a', _SORT_FAILED),
    ('arr.json', 'sort=-nosuch', _UNKNOWN_SORT),
    ('arr.json', 'zzz=1', _UNKNOWN_FILTER),
], ids=_IDS)
def test_text_output_says_it_once(data, name, query, message):
    run = _run_reveal_in(data, f'json://{name}?{query}')
    assert run.returncode == 0, run.stderr
    assert run.stdout.count(message) == 1, run.stdout
    assert message not in run.stderr


def test_sort_failed_is_a_result_control_note():
    """``?sort=`` did not apply: the answer cannot show that, so the seam prints it."""
    assert 'sort_failed' in RESULT_CONTROL_WARNINGS
    result = {'meta': {'warnings': [{'type': 'sort_failed', 'message': 'm'}]}}
    assert result_control_notes_of(result) == [{'type': 'sort_failed', 'message': 'm'}]


def test_renderer_prints_meta_warnings_but_leaves_result_control_notes(capsys):
    result = {
        'type': 'json_value', 'file': 'f.json', 'path': '(root)', 'value_type': 'Array[empty]',
        'value': [],
        'meta': {'warnings': [
            {'type': 'unknown_filter_field', 'message': 'filter note'},
            {'type': 'sort_failed', 'message': 'sort note'},
            {'type': 'truncated', 'field': 'value', 'message': 'cut note'},
        ]},
    }
    JsonRenderer.render_structure(result, 'text')
    out = capsys.readouterr().out
    assert out.count('⚠ filter note') == 1
    # The output seam prints these once after the render; the renderer must not.
    assert 'sort note' not in out and 'cut note' not in out


# Negative controls: what must not change.

def test_clean_sort_has_no_warnings(data):
    result = JsonAdapter(str(data / 'arr.json'), 'sort=a').get_structure()
    assert [v['a'] for v in result['value']] == [1, 2]
    assert 'warnings' not in result and 'meta' not in result


def test_limit_cut_and_counts_stay_where_they_were(data):
    result = JsonAdapter(str(data / 'arr.json'), 'sort=a&limit=1').get_structure()
    assert (result['displayed_results'], result['total_matches']) == (1, 2)
    assert [w['type'] for w in result['meta']['warnings']] == ['truncated']
    assert 'warnings' not in result


def test_markdown_unknown_sort_field_unchanged(data):
    docs = data / 'docs'
    docs.mkdir()
    (docs / 'one.md').write_text('---\ntitle: One\n---\n# One\n', encoding='utf-8')
    run = _run_reveal_in(data, 'markdown://docs?sort=-nosuch', '--format', 'json')
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert [w['field'] for w in result['meta']['warnings']
            if w['type'] == 'unknown_sort_field'] == ['nosuch']
    assert 'warnings' not in result
