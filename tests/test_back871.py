"""Tests for BACK-871: markdown:// frontmatter lint via ?lint[&lint-fields=f1,f2].

Architecture:
  files.extract_frontmatter_diagnostic() — distinguishes missing vs malformed vs ok
  operations.lint_frontmatter()          — scans a tree, builds the issue list
  MarkdownQueryAdapter                   — ?lint / ?lint-fields= extracted, routed
  _render_lint()                         — text/grep rendering
"""

from io import StringIO
from pathlib import Path

import pytest

from reveal.adapters.markdown.adapter import MarkdownQueryAdapter
from reveal.adapters.markdown.files import extract_frontmatter, extract_frontmatter_diagnostic
from reveal.adapters.markdown.operations import lint_frontmatter
from reveal.rendering.adapters.markdown_query import render_markdown_query

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


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


# ─── extract_frontmatter_diagnostic ───────────────────────────────────────────

class TestExtractFrontmatterDiagnostic:
    def test_valid_frontmatter_is_ok(self, tmp_path):
        f = _write(tmp_path / 'good.md', '---\ntitle: Good\n---\nBody.\n')
        diag = extract_frontmatter_diagnostic(f)
        assert diag['status'] == 'ok'
        assert diag['frontmatter'] == {'title': 'Good'}
        assert diag['error'] is None

    def test_no_frontmatter_block(self, tmp_path):
        f = _write(tmp_path / 'plain.md', '# Heading\n\nJust text.\n')
        diag = extract_frontmatter_diagnostic(f)
        assert diag['status'] == 'missing'
        assert diag['frontmatter'] is None

    def test_unclosed_delimiter_is_malformed(self, tmp_path):
        f = _write(tmp_path / 'unclosed.md', '---\ntitle: Oops\n\nBody with no closing delimiter.\n')
        diag = extract_frontmatter_diagnostic(f)
        assert diag['status'] == 'malformed'
        assert 'closing' in diag['error']

    def test_invalid_yaml_is_malformed(self, tmp_path):
        f = _write(tmp_path / 'bad_yaml.md', '---\ntitle: "unclosed quote\ntype: guide\n---\nBody.\n')
        diag = extract_frontmatter_diagnostic(f)
        assert diag['status'] == 'malformed'
        assert diag['error']

    def test_non_mapping_yaml_is_malformed(self, tmp_path):
        f = _write(tmp_path / 'list_yaml.md', '---\n- one\n- two\n---\nBody.\n')
        diag = extract_frontmatter_diagnostic(f)
        assert diag['status'] == 'malformed'
        assert 'mapping' in diag['error']

    def test_empty_block_is_malformed(self, tmp_path):
        f = _write(tmp_path / 'empty.md', '---\n---\nBody.\n')
        diag = extract_frontmatter_diagnostic(f)
        assert diag['status'] == 'malformed'

    def test_extract_frontmatter_still_returns_none_on_malformed(self, tmp_path):
        # Backward-compat: existing callers of extract_frontmatter() see None
        # for both 'missing' and 'malformed' — only lint distinguishes them.
        f = _write(tmp_path / 'bad.md', '---\ntitle: "oops\n---\nBody.\n')
        assert extract_frontmatter(f) is None


# ─── operations.lint_frontmatter ──────────────────────────────────────────────

class TestLintFrontmatter:
    def _make_corpus(self, tmp_path):
        _write(tmp_path / 'good.md', '---\ntitle: Good\ntype: guide\n---\nBody.\n')
        _write(tmp_path / 'no_fm.md', '# No frontmatter\n\nJust text.\n')
        _write(tmp_path / 'bad_yaml.md', '---\ntitle: "unclosed\n---\nBody.\n')
        _write(tmp_path / 'missing_type.md', '---\ntitle: Has title only\n---\nBody.\n')
        return tmp_path

    def test_reports_no_frontmatter(self, tmp_path):
        base = self._make_corpus(tmp_path)
        result = lint_frontmatter(base)
        no_fm = [i for i in result['issues'] if i['issue'] == 'no_frontmatter']
        assert len(no_fm) == 1
        assert no_fm[0]['file'] == 'no_fm.md'
        assert no_fm[0]['detail'] is None

    def test_reports_malformed_yaml_with_detail(self, tmp_path):
        base = self._make_corpus(tmp_path)
        result = lint_frontmatter(base)
        malformed = [i for i in result['issues'] if i['issue'] == 'malformed_yaml']
        assert len(malformed) == 1
        assert malformed[0]['file'] == 'bad_yaml.md'
        assert malformed[0]['detail']

    def test_no_required_fields_ignores_missing_field_case(self, tmp_path):
        base = self._make_corpus(tmp_path)
        result = lint_frontmatter(base, required_fields=None)
        assert not any(i['issue'] == 'missing_fields' for i in result['issues'])
        # good.md and missing_type.md both have valid frontmatter, no issue without a required-fields list
        assert result['total_files'] == 4
        assert result['issues_found'] == 2  # no_fm + bad_yaml only

    def test_required_fields_flags_missing_field(self, tmp_path):
        base = self._make_corpus(tmp_path)
        result = lint_frontmatter(base, required_fields=['title', 'type'])
        missing = [i for i in result['issues'] if i['issue'] == 'missing_fields']
        assert len(missing) == 1
        assert missing[0]['file'] == 'missing_type.md'
        assert missing[0]['detail'] == ['type']

    def test_required_fields_does_not_double_flag_no_frontmatter_files(self, tmp_path):
        # no_fm.md has no block at all — reported as no_frontmatter, not also missing_fields
        base = self._make_corpus(tmp_path)
        result = lint_frontmatter(base, required_fields=['title'])
        no_fm_files = [i['file'] for i in result['issues'] if i['file'] == 'no_fm.md']
        assert len(no_fm_files) == 1

    def test_clean_corpus_has_no_issues(self, tmp_path):
        _write(tmp_path / 'a.md', '---\ntitle: A\n---\nBody.\n')
        _write(tmp_path / 'b.md', '---\ntitle: B\n---\nBody.\n')
        result = lint_frontmatter(tmp_path, required_fields=['title'])
        assert result['issues_found'] == 0
        assert result['issues'] == []


# ─── Adapter routing ───────────────────────────────────────────────────────────

class TestLintRouting:
    def test_lint_param_routes_to_lint(self, tmp_path):
        _write(tmp_path / 'plain.md', 'No frontmatter.\n')
        adapter = MarkdownQueryAdapter(str(tmp_path), 'lint')
        result = adapter.get_structure()
        assert result['type'] == 'markdown_frontmatter_lint'
        assert result['issues_found'] == 1

    def test_without_lint_param_routes_to_query(self, tmp_path):
        _write(tmp_path / 'plain.md', '---\ntitle: X\n---\nBody.\n')
        adapter = MarkdownQueryAdapter(str(tmp_path), 'title=X')
        result = adapter.get_structure()
        assert result['type'] == 'markdown_query'

    def test_lint_fields_param_combines_with_lint(self, tmp_path):
        _write(tmp_path / 'missing.md', '---\ntitle: X\n---\nBody.\n')
        adapter = MarkdownQueryAdapter(str(tmp_path), 'lint&lint-fields=title,owner')
        result = adapter.get_structure()
        assert result['type'] == 'markdown_frontmatter_lint'
        missing = [i for i in result['issues'] if i['issue'] == 'missing_fields']
        assert missing[0]['detail'] == ['owner']

    def test_lint_fields_without_lint_is_a_noop(self, tmp_path):
        _write(tmp_path / 'a.md', '---\ntitle: X\n---\nBody.\n')
        adapter = MarkdownQueryAdapter(str(tmp_path), 'lint-fields=title')
        result = adapter.get_structure()
        assert result['type'] == 'markdown_query'

    def test_result_has_contract_version(self, tmp_path):
        _write(tmp_path / 'a.md', 'No frontmatter.\n')
        adapter = MarkdownQueryAdapter(str(tmp_path), 'lint')
        result = adapter.get_structure()
        assert result['contract_version'] == '1.1'

    def test_link_graph_takes_precedence_over_lint(self, tmp_path):
        _write(tmp_path / 'a.md', 'No frontmatter.\n')
        adapter = MarkdownQueryAdapter(str(tmp_path), 'link-graph&lint')
        result = adapter.get_structure()
        assert result['type'] == 'markdown_link_graph'


# ─── Renderer ──────────────────────────────────────────────────────────────────

class TestLintRenderer:
    def _make_result(self, **kwargs):
        base = {
            'contract_version': '1.0',
            'type': 'markdown_frontmatter_lint',
            'source': '/tmp/docs',
            'source_type': 'directory',
            'total_files': 3,
            'issues_found': 2,
            'issues': [
                {'file': 'no_fm.md', 'issue': 'no_frontmatter', 'detail': None},
                {'file': 'bad.md', 'issue': 'malformed_yaml', 'detail': 'while scanning...\nfound unexpected end'},
            ],
        }
        base.update(kwargs)
        return base

    def test_renders_summary_line(self):
        out = _render(self._make_result())
        assert '3 files scanned' in out
        assert '2 issue(s) found' in out

    def test_renders_no_frontmatter_issue(self):
        out = _render(self._make_result())
        assert 'no_fm.md' in out
        assert '[no frontmatter]' in out

    def test_renders_malformed_yaml_first_line_only(self):
        out = _render(self._make_result())
        assert 'bad.md' in out
        assert '[malformed YAML]' in out
        assert 'found unexpected end' not in out  # only first line of the error shown

    def test_renders_missing_fields(self):
        result = self._make_result(issues=[
            {'file': 'x.md', 'issue': 'missing_fields', 'detail': ['title', 'owner']},
        ])
        out = _render(result)
        assert 'title, owner' in out

    def test_renders_clean_corpus_message(self):
        result = self._make_result(issues=[], issues_found=0)
        out = _render(result)
        assert 'No frontmatter issues found.' in out

    def test_grep_format_outputs_tab_separated(self):
        out = _render(self._make_result(), fmt='grep')
        assert 'no_fm.md\tno_frontmatter' in out
        assert 'bad.md\tmalformed_yaml' in out

    def test_json_format_returns_raw_data(self):
        import json
        out = _render(self._make_result(), fmt='json')
        parsed = json.loads(out)
        assert parsed['type'] == 'markdown_frontmatter_lint'
        assert parsed['issues_found'] == 2
