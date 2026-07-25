"""Tests for BACK-813: markdown:// single-doc backlinks via ?backlinks=<path>.

Architecture:
  operations.get_backlinks()    — reuses build_link_graph(), returns one node
  MarkdownQueryAdapter          — ?backlinks=<path> extracted, routed to get_backlinks
  _render_backlinks()           — text/grep rendering
"""

from io import StringIO
from pathlib import Path

from reveal.adapters.markdown.adapter import MarkdownQueryAdapter
from reveal.adapters.markdown.operations import get_backlinks
from reveal.rendering.adapters.markdown_query import render_markdown_query


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return path


def _render(result: dict, fmt: str = 'text') -> str:
    buf = StringIO()
    import sys
    old = sys.stdout
    sys.stdout = buf
    try:
        render_markdown_query(result, fmt)
    finally:
        sys.stdout = old
    return buf.getvalue()


# ─── get_backlinks ─────────────────────────────────────────────────────────────

class TestGetBacklinks:

    def test_finds_direct_backlink(self, tmp_path):
        _write(tmp_path / 'a.md', '[link](b.md)')
        _write(tmp_path / 'b.md', 'no links')
        result = get_backlinks(tmp_path, 'b.md')
        assert result['found'] is True
        assert result['linked_by'] == ['a.md']

    def test_reports_outbound_links_too(self, tmp_path):
        _write(tmp_path / 'a.md', '[link](b.md)')
        _write(tmp_path / 'b.md', '[link](c.md)')
        _write(tmp_path / 'c.md', 'leaf')
        result = get_backlinks(tmp_path, 'b.md')
        assert result['linked_by'] == ['a.md']
        assert result['links_to'] == ['c.md']

    def test_file_with_no_backlinks(self, tmp_path):
        _write(tmp_path / 'orphan.md', 'nothing links here')
        result = get_backlinks(tmp_path, 'orphan.md')
        assert result['found'] is True
        assert result['linked_by'] == []

    def test_target_not_found(self, tmp_path):
        _write(tmp_path / 'a.md', 'content')
        result = get_backlinks(tmp_path, 'missing.md')
        assert result['found'] is False
        assert result['linked_by'] == []
        assert 'total_files' in result

    def test_exact_relative_path_match(self, tmp_path):
        _write(tmp_path / 'docs' / 'guide.md', 'x')
        _write(tmp_path / 'index.md', '[g](docs/guide.md)')
        result = get_backlinks(tmp_path, 'docs/guide.md')
        assert result['found'] is True
        assert result['target'] == 'docs/guide.md'
        assert result['linked_by'] == ['index.md']

    def test_bare_filename_resolves_by_basename(self, tmp_path):
        _write(tmp_path / 'docs' / 'guide.md', 'x')
        _write(tmp_path / 'index.md', '[g](docs/guide.md)')
        result = get_backlinks(tmp_path, 'guide.md')
        assert result['found'] is True
        assert result['target'] == 'docs/guide.md'

    def test_ambiguous_basename_across_dirs(self, tmp_path):
        _write(tmp_path / 'sub1' / 'c.md', 'x')
        _write(tmp_path / 'sub2' / 'c.md', 'y')
        result = get_backlinks(tmp_path, 'c.md')
        assert result['found'] is False
        assert result['ambiguous'] is True
        assert sorted(result['candidates']) == ['sub1/c.md', 'sub2/c.md']

    def test_leading_dot_slash_normalized(self, tmp_path):
        _write(tmp_path / 'a.md', '[link](b.md)')
        _write(tmp_path / 'b.md', 'x')
        result = get_backlinks(tmp_path, './b.md')
        assert result['found'] is True
        assert result['target'] == 'b.md'


# ─── Routing ──────────────────────────────────────────────────────────────────

class TestBacklinksRouting:

    def test_backlinks_param_routes_to_backlinks(self, tmp_path):
        _write(tmp_path / 'a.md', 'x')
        adapter = MarkdownQueryAdapter(str(tmp_path), query='backlinks=a.md')
        result = adapter.get_structure()
        assert result['type'] == 'markdown_backlinks'

    def test_without_param_routes_to_query(self, tmp_path):
        adapter = MarkdownQueryAdapter(str(tmp_path), query=None)
        result = adapter.get_structure()
        assert result['type'] == 'markdown_query'

    def test_result_has_contract_version(self, tmp_path):
        _write(tmp_path / 'a.md', 'x')
        adapter = MarkdownQueryAdapter(str(tmp_path), query='backlinks=a.md')
        result = adapter.get_structure()
        assert result['contract_version'] == '1.0'

    def test_backlinks_and_other_params_coexist(self, tmp_path):
        _write(tmp_path / 'a.md', 'x')
        adapter = MarkdownQueryAdapter(str(tmp_path), query='backlinks=a.md&sort=-modified')
        result = adapter.get_structure()
        assert result['type'] == 'markdown_backlinks'

    def test_link_graph_takes_precedence_over_backlinks(self, tmp_path):
        """Both flags present is a degenerate case; link-graph wins deterministically."""
        _write(tmp_path / 'a.md', 'x')
        adapter = MarkdownQueryAdapter(str(tmp_path), query='link-graph&backlinks=a.md')
        result = adapter.get_structure()
        assert result['type'] == 'markdown_link_graph'


# ─── Renderer ─────────────────────────────────────────────────────────────────

class TestBacklinksRenderer:

    def _make_result(self, **kwargs) -> dict:
        return {
            'type': 'markdown_backlinks',
            'source': '/path/to/docs',
            'target': 'auth.md',
            'found': True,
            'linked_by': [],
            'links_to': [],
            'total_files': 10,
            **kwargs,
        }

    def test_renders_found_with_backlinks(self):
        output = _render(self._make_result(linked_by=['guide.md', 'index.md']))
        assert 'auth.md' in output
        assert 'guide.md' in output
        assert 'index.md' in output
        assert '←' in output

    def test_renders_found_with_no_backlinks(self):
        output = _render(self._make_result(linked_by=[]))
        assert 'safe to rename' in output

    def test_renders_links_to_section(self):
        output = _render(self._make_result(links_to=['overview.md']))
        assert '→' in output
        assert 'overview.md' in output

    def test_renders_not_found(self):
        output = _render(self._make_result(found=False, target='zzz.md', total_files=4))
        assert 'zzz.md' in output
        assert '4' in output

    def test_renders_ambiguous(self):
        output = _render(self._make_result(
            found=False, ambiguous=True, target='c.md',
            candidates=['sub1/c.md', 'sub2/c.md'],
        ))
        assert 'Ambiguous' in output
        assert 'sub1/c.md' in output
        assert 'sub2/c.md' in output

    def test_grep_format_outputs_tab_separated_backlinks(self):
        output = _render(
            self._make_result(linked_by=['a.md', 'b.md']), fmt='grep'
        )
        assert 'a.md\tauth.md' in output
        assert 'b.md\tauth.md' in output

    def test_grep_format_empty_when_not_found(self):
        output = _render(self._make_result(found=False), fmt='grep')
        assert output.strip() == ''

    def test_json_format_returns_raw_data(self):
        import json
        result = self._make_result(linked_by=['a.md'])
        output = _render(result, fmt='json')
        parsed = json.loads(output)
        assert parsed['type'] == 'markdown_backlinks'
        assert parsed['linked_by'] == ['a.md']
