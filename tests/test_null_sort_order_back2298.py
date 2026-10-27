"""BACK-2298: markdown:// and metrics:// ``?sort=`` put null and missing values last in both directions.

json:// and ast:// already do (BACK-2276), and keep such items in their source order.
markdown:// keyed a null ``(0, 0)`` ascending, which met ``(0, 'a')`` in a TypeError and fell back
to text, where '0' sorts before every letter; descending it keyed ``(1, 0)``, which the reverse put
first. So nulls came first both ways, against its own comment. metrics:// keyed ``value or 0``: a
missing field sorted as a zero, first ascending and among the zeros descending.
"""
import json

import pytest

from conftest import _run_reveal_direct

# (file, status): None is `status:` with no value (YAML null); MISSING has no status key.
MISSING = object()
DOCS = [('f1', 'b'), ('f2', None), ('f3', 'a'), ('f4', MISSING), ('f5', 'c'), ('f6', None)]


@pytest.fixture()
def docs(tmp_path):
    for name, status in DOCS:
        lines = ['---', f'title: {name}']
        if status is not MISSING:
            lines.append(f"status: {status or ''}".rstrip())
        (tmp_path / f'{name}.md').write_text('\n'.join([*lines, '---', 'body', '']), encoding='utf-8')
    return tmp_path


def _markdown_order(docs, monkeypatch, query):
    monkeypatch.chdir(docs)
    result = _run_reveal_direct(f'markdown://.?{query}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    return [r['title'] for r in json.loads(result.stdout)['results']]


def test_markdown_ascending_sort_puts_nulls_last(docs, monkeypatch):
    assert _markdown_order(docs, monkeypatch, 'sort=status') == ['f3', 'f1', 'f5', 'f2', 'f4', 'f6']


def test_markdown_descending_sort_puts_nulls_last(docs, monkeypatch):
    assert _markdown_order(docs, monkeypatch, 'sort=-status') == ['f5', 'f1', 'f3', 'f2', 'f4', 'f6']


def test_markdown_page_past_the_values_reaches_the_nulls(docs, monkeypatch):
    assert _markdown_order(docs, monkeypatch, 'sort=-status&offset=2&limit=2') == ['f3', 'f2']


def _metrics_order(tmp_path, query, records):
    from reveal.adapters.stats.adapter import MetricsAdapter
    adapter = MetricsAdapter(str(tmp_path), query)
    return [r['file'] for r in adapter._apply_sorting(records)]


def _record(name, total=MISSING):
    return {'file': name, 'lines': {} if total is MISSING else {'total': total}}


RECORDS = [_record('three', 3), _record('missing'), _record('zero', 0), _record('five', 5), _record('gone')]


def test_metrics_ascending_sort_puts_missing_last_not_as_zero(tmp_path):
    assert _metrics_order(tmp_path, 'sort=lines', RECORDS) == ['zero', 'three', 'five', 'missing', 'gone']


def test_metrics_descending_sort_puts_missing_last(tmp_path):
    assert _metrics_order(tmp_path, 'sort=-lines', RECORDS) == ['five', 'three', 'zero', 'missing', 'gone']


# Negative controls: what must not change.

def test_markdown_list_values_still_sort_by_their_first_element(tmp_path, monkeypatch):
    for name, tags in (('x', '[b, z]'), ('y', '[a]'), ('z', '[c]')):
        (tmp_path / f'{name}.md').write_text(f'---\ntitle: {name}\ntags: {tags}\n---\nbody\n', encoding='utf-8')
    assert _markdown_order(tmp_path, monkeypatch, 'sort=tags') == ['y', 'x', 'z']


def _mixed(tmp_path, values):
    for name, value in values:
        (tmp_path / f'{name}.md').write_text(f'---\ntitle: {name}\nstatus: {value}\n---\nbody\n'.replace(' \n', '\n'),
                                             encoding='utf-8')
    return tmp_path


def test_markdown_values_of_mixed_types_still_order_as_text(tmp_path, monkeypatch):
    # YAML reads 10 and 9 as numbers beside the text 'abc': they order as text, '10' < '9'.
    assert _markdown_order(_mixed(tmp_path, (('p', '10'), ('q', 'abc'), ('r', '9'))),
                           monkeypatch, 'sort=status') == ['p', 'r', 'q']


def test_markdown_mixed_types_with_a_null_order_as_text_with_the_null_last(tmp_path, monkeypatch):
    # The text fallback ranked a null as the text '0', before every value.
    assert _markdown_order(_mixed(tmp_path, (('p', '10'), ('q', 'abc'), ('r', '9'), ('s', ''))),
                           monkeypatch, 'sort=status') == ['p', 'r', 'q', 's']


def test_metrics_sort_without_nulls_is_unchanged(tmp_path):
    records = [_record('three', 3), _record('zero', 0), _record('five', 5)]
    assert _metrics_order(tmp_path, 'sort=lines', records) == ['zero', 'three', 'five']
    assert _metrics_order(tmp_path, 'sort=-lines', records) == ['five', 'three', 'zero']


def test_json_sort_still_puts_nulls_last(tmp_path):
    from reveal.adapters.json.adapter import JsonAdapter
    path = tmp_path / 'rows.json'
    path.write_text(json.dumps([{'n': 'a', 'v': 2}, {'n': 'nul', 'v': None}, {'n': 'b', 'v': 1}]), encoding='utf-8')
    for query, expected in (('sort=v', ['b', 'a', 'nul']), ('sort=-v', ['a', 'b', 'nul'])):
        assert [r['n'] for r in JsonAdapter(str(path), query).get_structure()['value']] == expected
