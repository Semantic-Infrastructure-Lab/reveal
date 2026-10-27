"""Query operators that silently matched nothing (BACK-2213 C13, C15, C18)."""
import datetime
import os

from reveal.adapters.json.queries import matches_all_filters, compare
from reveal.adapters.markdown import MarkdownQueryAdapter
from reveal.utils.query_eval import compare_values
from reveal.utils.query_parser import parse_query_filters


def test_date_field_orders_against_iso_string():
    d = datetime.date(2026, 2, 1)
    assert compare_values(d, '>', '2026-01-01') is True
    assert compare_values(d, '<', '2026-01-01') is False
    assert compare_values(d, '<=', '2026-02-01') is True


def test_non_date_text_still_does_not_order_when_coercing():
    assert compare_values('banana', '>', 'apple') is False


def test_json_missing_field_filter():
    items = [{'n': 'zed'}, {'n': 'bob', 'tags': ['a']}, {'n': 'x', 'tags': ''}]
    filters = parse_query_filters('!tags', record=False)
    got = [i['n'] for i in items
           if matches_all_filters(i, filters, lambda o, f: o.get(f), compare)]
    assert got == ['zed', 'x']


def test_markdown_not_regex(tmp_path):
    (tmp_path / 'a.md').write_text('---\nstatus: draft\n---\nx\n', encoding='utf-8')
    (tmp_path / 'b.md').write_text('---\nstatus: Complete\n---\nx\n', encoding='utf-8')
    (tmp_path / 'c.md').write_text('---\nstatus: archived\n---\nx\n', encoding='utf-8')
    adapter = MarkdownQueryAdapter(str(tmp_path), 'status!~draft')
    names = sorted(os.path.basename(r['path']) for r in adapter.get_structure()['results'])
    assert names == ['b.md', 'c.md']
