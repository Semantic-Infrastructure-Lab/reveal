"""BACK-2543: a construct's bare keyword token does not open a second nesting level.

Most grammars put an anonymous keyword token under its construct (`if_statement > 'if'`,
Ruby `if > 'if'`); both share a nesting kind, so a lone `if` read depth 2 in every language.
"""
import pytest
from tree_sitter_language_pack import get_parser

from reveal.complexity import calculate_complexity_and_depth
from reveal.core.treesitter_compat import _zero_arg, tree_root, ts_parse

LONE_IF = {
    'python': 'def f(a):\n    if a:\n        return 1\n    return 2\n',
    'javascript': 'function f(a){ if (a) { return 1; } return 2; }',
    'c': 'int f(int a){ if (a) { return 1; } return 2; }',
    'rust': 'fn f(a: bool) -> i32 { if a { return 1; } 2 }',
    'go': 'package p\nfunc f(a bool) int { if a { return 1 }; return 2 }',
    'java': 'class C { int f(boolean a){ if (a) { return 1; } return 2; } }',
    'php': '<?php function f($a){ if ($a) { return 1; } return 2; }',
    'ruby': 'def f(a)\n if a\n  return 1\n end\n return 2\nend',
    'lua': 'function f(a) if a then return 1 end return 2 end',
}

IF_IN_FOR = {
    'python': 'def f(xs):\n    for x in xs:\n        if x:\n            return 1\n',
    'javascript': 'function f(xs){ for (const x of xs) { if (x) { return 1; } } }',
    'ruby': 'def f(xs)\n for x in xs\n  if x\n   return 1\n  end\n end\nend',
}


def _depth(language, source):
    root = tree_root(ts_parse(get_parser(language), source))
    assert not _zero_arg(root, 'has_error'), source
    return calculate_complexity_and_depth(root)


@pytest.mark.parametrize('language', sorted(LONE_IF))
def test_lone_if_is_depth_one(language):
    assert _depth(language, LONE_IF[language]) == (2, 1)


@pytest.mark.parametrize('language', sorted(IF_IN_FOR))
def test_if_inside_for_is_depth_two(language):
    assert _depth(language, IF_IN_FOR[language]) == (3, 2)


@pytest.mark.parametrize('language,source', [
    ('ruby', 'def f(a)\n return 1 if a\n 2\nend'),       # modifier: a decision, not a block
    ('python', 'def f(a):\n    return 1 if a else 2\n'),  # conditional expression
])
def test_inline_conditional_opens_no_level(language, source):
    assert _depth(language, source) == (2, 0)


def test_outline_reports_the_same_depth(tmp_path):
    from conftest import _run_reveal_direct
    path = tmp_path / 'one.js'
    path.write_text(LONE_IF['javascript'] + '\n', encoding='utf-8')
    result = _run_reveal_direct(str(path))
    assert result.returncode == 0
    assert 'depth:1]' in result.stdout
