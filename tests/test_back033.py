"""Tests for BACK-033: markdown:// ?aggregate=<field> frontmatter frequency table.

Tests cover:
- _extract_aggregate helper
- aggregate_field_values in operations.py
- MarkdownQueryAdapter with ?aggregate= query
- Renderer (text and grep output)
"""

import pytest
import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from reveal.adapters.markdown.adapter import _extract_aggregate, MarkdownQueryAdapter
from reveal.adapters.markdown.operations import aggregate_field_values


def _write_md(path: Path, content: str):
    path.write_text(content, encoding='utf-8')


def _capture(fn, *args, **kwargs):
    buf = StringIO()
    with patch('sys.stdout', buf):
        fn(*args, **kwargs)
    return buf.getvalue()


# ─── _extract_aggregate ───────────────────────────────────────────────────────

class TestExtractAggregate:
    def test_extracts_aggregate_field(self):
        field, remaining = _extract_aggregate('aggregate=type')
        assert field == 'type'
        assert remaining == ''

    def test_aggregate_with_other_params(self):
        field, remaining = _extract_aggregate('status=active&aggregate=type&limit=10')
        assert field == 'type'
        assert 'status=active' in remaining
        assert 'limit=10' in remaining
        assert 'aggregate' not in remaining

    def test_no_aggregate_returns_none(self):
        field, remaining = _extract_aggregate('status=active&limit=10')
        assert field is None
        assert remaining == 'status=active&limit=10'

    def test_empty_aggregate_value_ignored(self):
        field, remaining = _extract_aggregate('aggregate=')
        assert field is None

    def test_empty_query_returns_none(self):
        field, remaining = _extract_aggregate('')
        assert field is None
        assert remaining == ''


# ─── aggregate_field_values ───────────────────────────────────────────────────

class TestAggregateFieldValues:
    def test_scalar_field_counts(self, tmp_path):
        _write_md(tmp_path / 'a.md', '---\ntype: guide\n---\n')
        _write_md(tmp_path / 'b.md', '---\ntype: guide\n---\n')
        _write_md(tmp_path / 'c.md', '---\ntype: reference\n---\n')

        result = aggregate_field_values(tmp_path, 'type', [], [], None)
        agg = {e['value']: e['count'] for e in result['aggregate']}
        assert agg['guide'] == 2
        assert agg['reference'] == 1

    def test_list_field_expanded(self, tmp_path):
        _write_md(tmp_path / 'a.md', '---\nbeth_topics:\n  - reveal\n  - deployment\n---\n')
        _write_md(tmp_path / 'b.md', '---\nbeth_topics:\n  - reveal\n  - testing\n---\n')

        result = aggregate_field_values(tmp_path, 'beth_topics', [], [], None)
        agg = {e['value']: e['count'] for e in result['aggregate']}
        assert agg['reveal'] == 2
        assert agg['deployment'] == 1
        assert agg['testing'] == 1

    def test_missing_field_counted(self, tmp_path):
        _write_md(tmp_path / 'has.md', '---\ntype: guide\n---\n')
        _write_md(tmp_path / 'missing.md', '---\ntitle: No type field\n---\n')

        result = aggregate_field_values(tmp_path, 'type', [], [], None)
        assert result['files_missing_field'] == 1
        assert result['matched_files'] == 2

    def test_sorted_by_count_descending(self, tmp_path):
        _write_md(tmp_path / 'a.md', '---\ntype: rare\n---\n')
        _write_md(tmp_path / 'b.md', '---\ntype: common\n---\n')
        _write_md(tmp_path / 'c.md', '---\ntype: common\n---\n')
        _write_md(tmp_path / 'd.md', '---\ntype: common\n---\n')

        result = aggregate_field_values(tmp_path, 'type', [], [], None)
        agg = result['aggregate']
        assert agg[0]['value'] == 'common'
        assert agg[0]['count'] == 3
        assert agg[1]['value'] == 'rare'
        assert agg[1]['count'] == 1

    def test_total_and_matched_files(self, tmp_path):
        _write_md(tmp_path / 'a.md', '---\ntype: guide\n---\n')
        _write_md(tmp_path / 'b.md', '---\ntype: reference\n---\n')

        result = aggregate_field_values(tmp_path, 'type', [], [], None)
        assert result['total_files'] == 2
        assert result['matched_files'] == 2

    def test_no_matching_files_empty_aggregate(self, tmp_path):
        result = aggregate_field_values(tmp_path, 'type', [], [], None)
        assert result['aggregate'] == []
        assert result['matched_files'] == 0

    def test_no_frontmatter_counted_as_missing(self, tmp_path):
        _write_md(tmp_path / 'no_fm.md', '# Just content\nNo frontmatter.\n')

        result = aggregate_field_values(tmp_path, 'type', [], [], None)
        assert result['files_missing_field'] == 1
        assert result['aggregate'] == []


# ─── MarkdownQueryAdapter: ?aggregate= dispatch ──────────────────────────────

class TestMarkdownQueryAdapterAggregate:
    def test_aggregate_sets_type(self, tmp_path):
        _write_md(tmp_path / 'a.md', '---\ntype: guide\n---\n')
        _write_md(tmp_path / 'b.md', '---\ntype: reference\n---\n')

        adapter = MarkdownQueryAdapter(str(tmp_path), 'aggregate=type')
        result = adapter.get_structure()
        assert result['type'] == 'markdown_aggregate'
        assert result['field'] == 'type'
        assert 'aggregate' in result

    def test_aggregate_combined_with_filter(self, tmp_path):
        _write_md(tmp_path / 'a.md', '---\nstatus: active\ntype: guide\n---\n')
        _write_md(tmp_path / 'b.md', '---\nstatus: active\ntype: reference\n---\n')
        _write_md(tmp_path / 'c.md', '---\nstatus: draft\ntype: guide\n---\n')

        adapter = MarkdownQueryAdapter(str(tmp_path), 'status=active&aggregate=type')
        result = adapter.get_structure()
        assert result['type'] == 'markdown_aggregate'
        # Only 2 files match status=active
        assert result['matched_files'] == 2

    def test_no_aggregate_returns_normal_query(self, tmp_path):
        _write_md(tmp_path / 'a.md', '---\ntype: guide\n---\n')
        adapter = MarkdownQueryAdapter(str(tmp_path), 'type=guide')
        result = adapter.get_structure()
        assert result['type'] == 'markdown_query'

    def test_aggregate_field_stored(self, tmp_path):
        adapter = MarkdownQueryAdapter(str(tmp_path), 'aggregate=beth_topics')
        assert adapter.aggregate_field == 'beth_topics'

    def test_no_aggregate_field_is_none(self, tmp_path):
        adapter = MarkdownQueryAdapter(str(tmp_path), 'type=guide')
        assert adapter.aggregate_field is None


# ─── Renderer: text output ────────────────────────────────────────────────────

class TestRenderAggregate:
    def _result(self, aggregate_list, field='type', source='/docs', matched=10, total=12, missing=2):
        return {
            'type': 'markdown_aggregate',
            'field': field,
            'source': source,
            'matched_files': matched,
            'total_files': total,
            'files_missing_field': missing,
            'aggregate': aggregate_list,
        }

    def test_text_output_shows_field_and_counts(self, tmp_path):
        from reveal.rendering.adapters.markdown_query import render_markdown_query
        result = self._result([
            {'value': 'guide', 'count': 10},
            {'value': 'reference', 'count': 4},
        ])
        out = _capture(render_markdown_query, result, 'text')
        assert 'Aggregate: type' in out
        assert 'guide' in out
        assert '10' in out
        assert 'reference' in out
        assert '4' in out

    def test_text_output_shows_missing_count(self, tmp_path):
        from reveal.rendering.adapters.markdown_query import render_markdown_query
        result = self._result([{'value': 'guide', 'count': 8}], missing=4)
        out = _capture(render_markdown_query, result, 'text')
        assert 'Missing' in out
        assert '4' in out

    def test_text_no_missing_line_when_zero(self):
        from reveal.rendering.adapters.markdown_query import render_markdown_query
        result = self._result([{'value': 'guide', 'count': 10}], missing=0)
        out = _capture(render_markdown_query, result, 'text')
        assert 'Missing' not in out

    def test_empty_aggregate_shows_message(self):
        from reveal.rendering.adapters.markdown_query import render_markdown_query
        result = self._result([])
        out = _capture(render_markdown_query, result, 'text')
        assert 'No values found' in out

    def test_json_output_is_json(self):
        from reveal.rendering.adapters.markdown_query import render_markdown_query
        result = self._result([{'value': 'guide', 'count': 5}])
        out = _capture(render_markdown_query, result, 'json')
        data = json.loads(out)
        assert data['type'] == 'markdown_aggregate'
        assert data['aggregate'][0]['value'] == 'guide'

    def test_grep_output_tab_separated(self):
        from reveal.rendering.adapters.markdown_query import render_markdown_query
        result = self._result([
            {'value': 'guide', 'count': 10},
            {'value': 'reference', 'count': 3},
        ])
        out = _capture(render_markdown_query, result, 'grep')
        lines = out.strip().split('\n')
        assert len(lines) == 2
        assert lines[0] == 'guide\t10'
        assert lines[1] == 'reference\t3'

    def test_bar_chart_shown(self):
        from reveal.rendering.adapters.markdown_query import render_markdown_query
        result = self._result([
            {'value': 'guide', 'count': 30},
            {'value': 'reference', 'count': 10},
        ])
        out = _capture(render_markdown_query, result, 'text')
        assert '█' in out
