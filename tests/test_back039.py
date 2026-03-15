"""Tests for BACK-039: markdown:// cross-file link graph via ?link-graph.

Architecture:
  files.extract_internal_links() — regex link extraction, path resolution, base filtering
  operations.build_link_graph()  — forward edges + reverse backlinks + isolated set
  MarkdownQueryAdapter          — ?link-graph flag extracted, routed to build_link_graph
  _render_link_graph()           — text/grep rendering
"""

import pytest
from io import StringIO
from pathlib import Path

from reveal.adapters.markdown.adapter import MarkdownQueryAdapter
from reveal.adapters.markdown.files import extract_internal_links
from reveal.adapters.markdown.operations import build_link_graph
from reveal.rendering.adapters.markdown_query import render_markdown_query


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return path


# ─── extract_internal_links ───────────────────────────────────────────────────

class TestExtractInternalLinks:

    def test_extracts_relative_md_link(self, tmp_path):
        src = _write(tmp_path / 'a.md', '[B](b.md)')
        _write(tmp_path / 'b.md', '')
        result = extract_internal_links(src, tmp_path)
        assert result == ['b.md']

    def test_extracts_subdirectory_link(self, tmp_path):
        src = _write(tmp_path / 'a.md', '[Guide](docs/guide.md)')
        _write(tmp_path / 'docs' / 'guide.md', '')
        result = extract_internal_links(src, tmp_path)
        assert result == ['docs/guide.md']

    def test_skips_external_http_links(self, tmp_path):
        src = _write(tmp_path / 'a.md', '[Google](https://google.com)')
        result = extract_internal_links(src, tmp_path)
        assert result == []

    def test_skips_external_https_links(self, tmp_path):
        src = _write(tmp_path / 'a.md', '[Link](https://example.com/doc.md)')
        result = extract_internal_links(src, tmp_path)
        assert result == []

    def test_skips_anchor_only_links(self, tmp_path):
        src = _write(tmp_path / 'a.md', '[section](#heading)')
        result = extract_internal_links(src, tmp_path)
        assert result == []

    def test_skips_non_markdown_files(self, tmp_path):
        src = _write(tmp_path / 'a.md', '[Script](script.py)')
        result = extract_internal_links(src, tmp_path)
        assert result == []

    def test_strips_anchor_from_filename(self, tmp_path):
        src = _write(tmp_path / 'a.md', '[Guide](guide.md#section)')
        _write(tmp_path / 'guide.md', '')
        result = extract_internal_links(src, tmp_path)
        assert result == ['guide.md']

    def test_skips_nonexistent_targets(self, tmp_path):
        src = _write(tmp_path / 'a.md', '[Missing](missing.md)')
        result = extract_internal_links(src, tmp_path)
        assert result == []

    def test_skips_links_outside_base_path(self, tmp_path):
        src = _write(tmp_path / 'a.md', '[Outside](../outside.md)')
        result = extract_internal_links(src, tmp_path)
        assert result == []

    def test_deduplicates_repeated_links(self, tmp_path):
        src = _write(tmp_path / 'a.md', '[B](b.md)\n[B again](b.md)')
        _write(tmp_path / 'b.md', '')
        result = extract_internal_links(src, tmp_path)
        assert result == ['b.md']

    def test_returns_sorted_list(self, tmp_path):
        src = _write(tmp_path / 'a.md', '[Z](z.md)\n[A](a2.md)\n[M](m.md)')
        _write(tmp_path / 'z.md', '')
        _write(tmp_path / 'a2.md', '')
        _write(tmp_path / 'm.md', '')
        result = extract_internal_links(src, tmp_path)
        assert result == sorted(result)

    def test_handles_missing_file_gracefully(self, tmp_path):
        result = extract_internal_links(tmp_path / 'nonexistent.md', tmp_path)
        assert result == []

    def test_extracts_multiple_links(self, tmp_path):
        src = _write(tmp_path / 'a.md', '[B](b.md)\n[C](c.md)')
        _write(tmp_path / 'b.md', '')
        _write(tmp_path / 'c.md', '')
        result = extract_internal_links(src, tmp_path)
        assert 'b.md' in result
        assert 'c.md' in result

    def test_resolves_parent_directory_traversal(self, tmp_path):
        """Links like ../sibling.md should be resolved correctly."""
        _write(tmp_path / 'sibling.md', '')
        src = _write(tmp_path / 'subdir' / 'a.md', '[Sibling](../sibling.md)')
        result = extract_internal_links(src, tmp_path)
        assert result == ['sibling.md']


# ─── build_link_graph ─────────────────────────────────────────────────────────

class TestBuildLinkGraph:

    def test_basic_forward_edge(self, tmp_path):
        _write(tmp_path / 'a.md', '[B](b.md)')
        _write(tmp_path / 'b.md', '')
        result = build_link_graph(tmp_path)
        node_a = next(n for n in result['nodes'] if n['file'] == 'a.md')
        assert 'b.md' in node_a['links_to']

    def test_backlinks_populated(self, tmp_path):
        _write(tmp_path / 'a.md', '[B](b.md)')
        _write(tmp_path / 'b.md', '')
        result = build_link_graph(tmp_path)
        node_b = next(n for n in result['nodes'] if n['file'] == 'b.md')
        assert 'a.md' in node_b['linked_by']

    def test_isolated_files_detected(self, tmp_path):
        _write(tmp_path / 'alone.md', 'no links here')
        result = build_link_graph(tmp_path)
        assert 'alone.md' in result['isolated']

    def test_linked_files_not_isolated(self, tmp_path):
        _write(tmp_path / 'a.md', '[B](b.md)')
        _write(tmp_path / 'b.md', '')
        result = build_link_graph(tmp_path)
        assert 'a.md' not in result['isolated']
        assert 'b.md' not in result['isolated']

    def test_total_files_count(self, tmp_path):
        for i in range(4):
            _write(tmp_path / f'f{i}.md', '')
        result = build_link_graph(tmp_path)
        assert result['total_files'] == 4

    def test_total_edges_count(self, tmp_path):
        _write(tmp_path / 'a.md', '[B](b.md)\n[C](c.md)')
        _write(tmp_path / 'b.md', '')
        _write(tmp_path / 'c.md', '')
        result = build_link_graph(tmp_path)
        assert result['total_edges'] == 2

    def test_empty_directory(self, tmp_path):
        result = build_link_graph(tmp_path)
        assert result['total_files'] == 0
        assert result['total_edges'] == 0
        assert result['nodes'] == []
        assert result['isolated'] == []

    def test_nodes_sorted_alphabetically(self, tmp_path):
        for name in ('z.md', 'a.md', 'm.md'):
            _write(tmp_path / name, '')
        result = build_link_graph(tmp_path)
        files_in_order = [n['file'] for n in result['nodes']]
        assert files_in_order == sorted(files_in_order)

    def test_result_has_required_keys(self, tmp_path):
        result = build_link_graph(tmp_path)
        assert 'total_files' in result
        assert 'total_edges' in result
        assert 'nodes' in result
        assert 'isolated' in result

    def test_node_has_required_fields(self, tmp_path):
        _write(tmp_path / 'a.md', '')
        result = build_link_graph(tmp_path)
        node = result['nodes'][0]
        assert 'file' in node
        assert 'links_to' in node
        assert 'linked_by' in node

    def test_cross_directory_links(self, tmp_path):
        _write(tmp_path / 'index.md', '[Guide](docs/guide.md)')
        _write(tmp_path / 'docs' / 'guide.md', '')
        result = build_link_graph(tmp_path)
        index_node = next(n for n in result['nodes'] if n['file'] == 'index.md')
        assert 'docs/guide.md' in index_node['links_to']
        guide_node = next(n for n in result['nodes'] if n['file'] == 'docs/guide.md')
        assert 'index.md' in guide_node['linked_by']


# ─── Routing ──────────────────────────────────────────────────────────────────

class TestLinkGraphRouting:

    def test_link_graph_flag_routes_to_link_graph(self, tmp_path):
        adapter = MarkdownQueryAdapter(str(tmp_path), query='link-graph')
        result = adapter.get_structure()
        assert result['type'] == 'markdown_link_graph'

    def test_link_graph_underscore_variant(self, tmp_path):
        adapter = MarkdownQueryAdapter(str(tmp_path), query='link_graph')
        result = adapter.get_structure()
        assert result['type'] == 'markdown_link_graph'

    def test_without_flag_routes_to_query(self, tmp_path):
        adapter = MarkdownQueryAdapter(str(tmp_path), query=None)
        result = adapter.get_structure()
        assert result['type'] == 'markdown_query'

    def test_result_has_contract_version(self, tmp_path):
        adapter = MarkdownQueryAdapter(str(tmp_path), query='link-graph')
        result = adapter.get_structure()
        assert result['contract_version'] == '1.0'

    def test_result_source_is_base_path(self, tmp_path):
        adapter = MarkdownQueryAdapter(str(tmp_path), query='link-graph')
        result = adapter.get_structure()
        assert result['source'] == str(tmp_path)

    def test_link_graph_and_other_params_coexist(self, tmp_path):
        """?link-graph can appear alongside other query params."""
        adapter = MarkdownQueryAdapter(str(tmp_path), query='link-graph&sort=-modified')
        result = adapter.get_structure()
        assert result['type'] == 'markdown_link_graph'


# ─── Renderer ─────────────────────────────────────────────────────────────────

class TestLinkGraphRenderer:

    def _render(self, result: dict, fmt: str = 'text') -> str:
        buf = StringIO()
        import sys
        old = sys.stdout
        sys.stdout = buf
        try:
            render_markdown_query(result, fmt)
        finally:
            sys.stdout = old
        return buf.getvalue()

    def _make_result(self, nodes=None, isolated=None, **kwargs) -> dict:
        return {
            'type': 'markdown_link_graph',
            'source': '/path/to/docs',
            'total_files': 10,
            'total_edges': 5,
            'nodes': nodes or [],
            'isolated': isolated or [],
            **kwargs,
        }

    def test_renders_header(self):
        output = self._render(self._make_result())
        assert 'Link graph' in output
        assert '/path/to/docs' in output

    def test_renders_file_counts(self):
        output = self._render(self._make_result(total_files=10, total_edges=5))
        assert '10' in output
        assert '5' in output

    def test_renders_node_with_links_to(self):
        nodes = [{'file': 'a.md', 'links_to': ['b.md'], 'linked_by': []}]
        output = self._render(self._make_result(nodes=nodes))
        assert 'a.md' in output
        assert 'b.md' in output
        assert '→' in output

    def test_renders_linked_by_count(self):
        nodes = [{'file': 'b.md', 'links_to': [], 'linked_by': ['a.md', 'c.md']}]
        output = self._render(self._make_result(nodes=nodes))
        assert 'linked by 2' in output

    def test_renders_isolated_section(self):
        output = self._render(self._make_result(isolated=['orphan.md']))
        assert 'orphan.md' in output
        assert 'Isolated' in output

    def test_isolated_count_in_header(self):
        output = self._render(self._make_result(isolated=['a.md', 'b.md']))
        assert '2' in output

    def test_no_isolated_section_when_empty(self):
        output = self._render(self._make_result(isolated=[]))
        assert 'Isolated' not in output

    def test_grep_format_outputs_tab_separated_edges(self):
        nodes = [
            {'file': 'a.md', 'links_to': ['b.md', 'c.md'], 'linked_by': []},
            {'file': 'b.md', 'links_to': [], 'linked_by': ['a.md']},
        ]
        output = self._render(self._make_result(nodes=nodes), fmt='grep')
        assert 'a.md\tb.md' in output
        assert 'a.md\tc.md' in output

    def test_grep_format_excludes_nodes_with_no_links_to(self):
        nodes = [
            {'file': 'b.md', 'links_to': [], 'linked_by': ['a.md']},
        ]
        output = self._render(self._make_result(nodes=nodes), fmt='grep')
        assert output.strip() == ''

    def test_json_format_returns_raw_data(self):
        import json
        result = self._make_result()
        output = self._render(result, fmt='json')
        parsed = json.loads(output)
        assert parsed['type'] == 'markdown_link_graph'

    def test_empty_graph_renders_gracefully(self):
        output = self._render(self._make_result(total_files=0, total_edges=0))
        assert 'Link graph' in output
        assert '0' in output
