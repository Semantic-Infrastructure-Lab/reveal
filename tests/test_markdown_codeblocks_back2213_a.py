"""Markdown --code: fenced block line ranges and --inline spans (BACK-2213 lane A, F45/F46).

F45: ``--code --inline`` re-reported every fenced block as an inline snippet, because the
markdown_inline parse runs over the whole file and sees a ```` ```bash ```` fence as a code span.
F46: a fenced block's ``line_end`` was the row after the closing fence (tree-sitter's end
position sits at column 0 of the next line), and ``line_count`` counted the trailing newline
of the body as a line, so a one-line body reported 2 lines and a fence at EOF ended past EOF.
"""

from reveal.analyzers.markdown import MarkdownAnalyzer

DOC = "# T\n\nUse `x`.\n\n```bash\necho hi\n```\n"
#      1    2  3          4  5        6        7


def _blocks(tmp_path, content, **kwargs):
    path = tmp_path / 'doc.md'
    path.write_text(content, encoding='utf-8')
    return MarkdownAnalyzer(str(path)).get_structure(extract_code=True, **kwargs)['code_blocks']


def test_fenced_block_ends_on_closing_fence(tmp_path):
    (block,) = _blocks(tmp_path, DOC)
    assert (block['line_start'], block['line_end']) == (5, 7)
    assert block['line_count'] == 1
    assert block['source'] == 'echo hi\n'


def test_multiline_fence_counts_body_lines_only(tmp_path):
    content = "# T\n\n```python\na = 1\nb = 2\nc = 3\n```\n\nafter\n"
    (block,) = _blocks(tmp_path, content)
    assert (block['line_start'], block['line_end']) == (3, 7)
    assert block['line_count'] == 3


def test_fence_without_trailing_newline_at_eof(tmp_path):
    content = "# T\n\n```\nx\n```"
    (block,) = _blocks(tmp_path, content)
    assert (block['line_start'], block['line_end']) == (3, 5)  # not past EOF


def test_inline_does_not_repeat_fenced_blocks(tmp_path):
    blocks = _blocks(tmp_path, DOC, inline_code=True)
    inline = [b for b in blocks if b['type'] == 'inline']
    assert [(b['line'], b['source']) for b in inline] == [(3, 'x')]
    assert len([b for b in blocks if b['type'] == 'fenced']) == 1


def test_inline_regex_fallback_skips_fences(tmp_path):
    path = tmp_path / 'doc.md'
    path.write_text("Use `x`.\n\n```\nsee `y` here\n```\n", encoding='utf-8')
    analyzer = MarkdownAnalyzer(str(path))
    assert [(b['line'], b['source']) for b in analyzer._extract_inline_code()] == [(1, 'x')]


def test_text_preview_has_no_phantom_blank_line(tmp_path, capsys):
    from pathlib import Path
    from reveal.display.formatting import _format_fenced_block
    (block,) = _blocks(tmp_path, DOC)
    _format_fenced_block(block, Path('doc.md'), 'text')
    assert capsys.readouterr().out == "    Lines 5-7 (1 line)\n      echo hi\n"
