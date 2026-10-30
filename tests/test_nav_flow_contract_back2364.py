"""Source-reviewed navigation records before flow/exits consolidation (BACK-2364).

The compact rows below are hand-authored from the existing fixture sources and
reviewed grammar node names. They are not captured output or an accuracy oracle
for arbitrary programs. Known omissions are recorded separately from the source
exit inventory; preserving them does not make them correct.
"""
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from importlib.metadata import version
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct

from reveal.file_handler import _resolve_func_node
from reveal.nav_handlers import (
    _NavCtx, _nav_outline, _nav_branchmap, _nav_loopmap, _nav_exits,
)
from reveal.registry import get_analyzer
from test_conformance_matrix import EXPECTED, LANGUAGES, _sample_path

pytestmark = pytest.mark.conformance

# type, keyword, label, start, end, depth, is_exit. Spans are inclusive.
ROWS = {
    'python': [
        ('try_statement', 'TRY', 'TRY', 14, 19, 1, False),
        ('with_statement', 'WITH', 'WITH  open(log_path, "a") as f', 16, 17, 2, False),
        ('except_clause', 'EXCEPT', 'EXCEPT  OSError', 18, 19, 1, False),
        ('return_statement', 'RETURN', 'RETURN  None', 19, 19, 2, True),
        ('return_statement', 'RETURN', 'RETURN  result', 21, 21, 1, True),
    ],
    'c': [
        ('if_statement', 'IF', 'IF  (result < 0)', 14, 16, 1, False),
        ('return_statement', 'RETURN', 'RETURN  -1;', 15, 15, 2, True),
        ('if_statement', 'IF', 'IF  (f == NULL)', 18, 20, 1, False),
        ('return_statement', 'RETURN', 'RETURN  -1;', 19, 19, 2, True),
        ('return_statement', 'RETURN', 'RETURN  result;', 24, 24, 1, True),
    ],
    # Observed omission: CHECK_OR_RETURN at L20 is an EXIT in --exits,
    # but the skeleton does not recognize macro calls. See gap test below.
    'cpp': [
        ('if_statement', 'IF', 'IF  (result < 0)', 17, 19, 1, False),
        ('return_statement', 'RETURN', 'RETURN  -1;', 18, 18, 2, True),
        ('if_statement', 'IF', 'IF  (f == nullptr)', 22, 24, 1, False),
        ('return_statement', 'RETURN', 'RETURN  -1;', 23, 23, 2, True),
        ('return_statement', 'RETURN', 'RETURN  result;', 28, 28, 1, True),
    ],
    'csharp': [
        ('try_statement', 'TRY', 'TRY', 22, 29, 1, False),
        ('catch_clause', 'CATCH', 'CATCH  (IOException)', 26, 29, 1, False),
        ('return_statement', 'RETURN', 'RETURN  -1;', 28, 28, 2, True),
        ('return_statement', 'RETURN', 'RETURN  result;', 31, 31, 1, True),
    ],
    'go': [
        ('if_statement', 'IF', 'IF  err != nil', 21, 23, 1, False),
        ('return_statement', 'RETURN', 'RETURN  "", err', 22, 22, 2, True),
        ('if_statement', 'IF', 'IF  err != nil', 25, 27, 1, False),
        ('return_statement', 'RETURN', 'RETURN  "", err', 26, 26, 2, True),
        ('return_statement', 'RETURN', 'RETURN  result, nil', 31, 31, 1, True),
    ],
    'java': [
        ('try_statement', 'TRY', 'TRY', 19, 23, 1, False),
        ('catch_clause', 'CATCH', 'CATCH  (IOException e)', 21, 23, 1, False),
        ('return_statement', 'RETURN', 'RETURN  -1;', 22, 22, 2, True),
        ('return_statement', 'RETURN', 'RETURN  result;', 25, 25, 1, True),
    ],
    'javascript': [
        ('try_statement', 'TRY', 'TRY', 15, 19, 1, False),
        ('catch_clause', 'CATCH', 'CATCH  (err)', 17, 19, 1, False),
        ('return_statement', 'RETURN', 'RETURN  null;', 18, 18, 2, True),
        ('return_statement', 'RETURN', 'RETURN  result;', 21, 21, 1, True),
    ],
    # Observed omissions: ? at L14 and implicit tail at L19.
    'rust': [
        ('if_expression', 'IF', 'IF  let Err(e) = fs::write("/tmp/orders.log", result.to_string())', 15, 17, 1, False),
        ('return_expression', 'RETURN', 'RETURN  Err(e)', 16, 16, 2, True),
    ],
    'typescript': [
        ('try_statement', 'TRY', 'TRY', 15, 19, 1, False),
        ('catch_clause', 'CATCH', 'CATCH  (err)', 17, 19, 1, False),
        ('return_statement', 'RETURN', 'RETURN  null;', 18, 18, 2, True),
        ('return_statement', 'RETURN', 'RETURN  result;', 21, 21, 1, True),
    ],
    'kotlin': [
        ('try_expression', 'TRY', 'TRY', 14, 22, 1, False),
        ('while_statement', 'WHILE', 'WHILE  (count < 3)', 16, 18, 2, False),
        ('jump_expression', 'RETURN', 'RETURN  result.uppercase()', 19, 19, 2, True),
        ('catch_block', 'CATCH', 'CATCH  (e: Exception)', 20, 22, 1, False),
        ('jump_expression', 'RETURN', 'RETURN  null', 21, 21, 2, True),
    ],
    'swift': [
        ('do_statement', 'TRY', 'TRY  do', 12, 23, 1, False),
        ('while_statement', 'WHILE', 'WHILE  count < 3', 16, 18, 2, False),
        ('control_transfer_statement', 'RETURN', 'RETURN  result', 20, 20, 2, True),
        ('catch_block', 'CATCH', 'CATCH', 21, 23, 1, False),
        ('control_transfer_statement', 'RETURN', 'RETURN  nil', 22, 22, 2, True),
    ],
    'ruby': [
        ('begin', 'TRY', 'TRY  begin', 12, 20, 1, False),
        ('while', 'WHILE', 'WHILE  count < 3', 14, 16, 2, False),
        ('return', 'RETURN', 'RETURN  result.upcase', 17, 17, 2, True),
        ('rescue', 'CATCH', 'CATCH  rescue StandardError', 18, 19, 1, False),
        ('return', 'RETURN', 'RETURN  nil', 19, 19, 2, True),
    ],
    'php': [
        ('try_statement', 'TRY', 'TRY', 13, 23, 1, False),
        ('while_statement', 'WHILE', 'WHILE  ($count < 3)', 17, 19, 2, False),
        ('return_statement', 'RETURN', 'RETURN  strtoupper($result);', 20, 20, 2, True),
        ('catch_clause', 'CATCH', 'CATCH  (Exception $e)', 21, 23, 1, False),
        ('return_statement', 'RETURN', 'RETURN  null;', 22, 22, 2, True),
    ],
    'lua': [
        ('if_statement', 'IF', 'IF  result == nil then', 13, 15, 1, False),
        ('return_statement', 'RETURN', 'RETURN  nil', 14, 14, 2, True),
        ('return_statement', 'RETURN', 'RETURN  result', 19, 19, 1, True),
    ],
    # The grammar's CATCH node covers its header only (L17); the handler's
    # RETURN at L18 is independently emitted. This is not a body-span claim.
    'dart': [
        ('try_statement', 'TRY', 'TRY', 14, 19, 1, False),
        ('catch_clause', 'CATCH', 'CATCH  (e)', 17, 17, 1, False),
        ('return_statement', 'RETURN', 'RETURN  -1;', 18, 18, 2, True),
        ('return_statement', 'RETURN', 'RETURN  result;', 21, 21, 1, True),
    ],
    'scala': [
        ('try_expression', 'TRY', 'TRY', 15, 21, 1, False),
        ('catch_clause', 'CATCH', 'CATCH', 19, 21, 1, False),
        ('case_clause', 'CASE', 'CASE  _: Exception => return -1', 20, 20, 2, False),
        ('return_expression', 'RETURN', 'RETURN  -1', 20, 20, 3, True),
        ('return_expression', 'RETURN', 'RETURN  result', 23, 23, 1, True),
    ],
    'gdscript': [
        ('if_statement', 'IF', 'IF  result == null', 14, 15, 1, False),
        ('return_statement', 'RETURN', 'RETURN  null', 15, 15, 2, True),
        ('return_statement', 'RETURN', 'RETURN  result', 19, 19, 1, True),
    ],
    # Observed omissions: returns at L14/17/21/24 are not in the skeleton.
    'zig': [
        ('BinaryExpr', 'CATCH', 'CATCH', 13, 15, 1, False),
        ('BinaryExpr', 'CATCH', 'CATCH', 16, 18, 1, False),
        ('BinaryExpr', 'CATCH', 'CATCH', 20, 22, 1, False),
    ],
    'tsx': [
        ('try_statement', 'TRY', 'TRY', 10, 19, 1, False),
        ('while_statement', 'WHILE', 'WHILE  (count < 3)', 13, 15, 2, False),
        ('return_statement', 'RETURN', 'RETURN  result.toUpperCase();', 16, 16, 2, True),
        ('catch_clause', 'CATCH', 'CATCH  (e)', 17, 19, 1, False),
        ('return_statement', 'RETURN', 'RETURN  null;', 18, 18, 2, True),
    ],
}
FIELDS = ('type', 'keyword', 'label', 'line_start', 'line_end', 'depth', 'is_exit')

# The supported floor grammar includes the catch's closing-line boundary in
# Scala's CASE node. Keep that exact representation explicit rather than
# dropping end spans or accepting arbitrary changes on all grammar versions.
if version('tree-sitter-language-pack') == '1.8.1':
    ROWS['scala'][2] = (
        'case_clause', 'CASE', 'CASE  _: Exception => return -1', 20, 21, 2, False,
    )


def _expected(language, depth=3, bounds=None, keywords=None):
    # At depth1, stopping at TRY also hides its same-depth CATCH siblings.
    # Zig's three catch operators are top-level expressions, not TRY children.
    return [dict(zip(FIELDS, row)) for row in ROWS[language]
            if row[5] <= depth
            and not (depth == 1 and language != 'zig' and row[1] in {'CATCH', 'EXCEPT'})
            and (bounds is None or bounds[0] <= row[3] <= bounds[1])
            and (keywords is None or row[1] in keywords)]


def _context(language, depth, bounds=None):
    if language == 'tsx':
        path = Path(__file__).parent / 'fixtures' / 'smoke' / 'tsx' / 'sample.tsx'
        element = 'processOrder'
    else:
        path = _sample_path(language)
        element = EXPECTED[language]['entry_function']
    analyzer = get_analyzer(str(path))(str(path))
    node, start, end = _resolve_func_node(analyzer, element)
    args = Namespace(range=bounds, ifmap=False)
    return _NavCtx(node, element, analyzer, True, args, start, end, depth, analyzer._get_node_text)


def _answer(ctx, handler):
    out = StringIO()
    with redirect_stdout(out):
        handler(ctx)
    return json.loads(out.getvalue())['findings']


@pytest.mark.parametrize('language', sorted(ROWS))
@pytest.mark.parametrize('depth', [1, 3, 8])
def test_full_named_skeleton_records(language, depth):
    assert _answer(_context(language, depth), _nav_outline) == _expected(language, depth)


def test_fixture_language_set_is_complete():
    assert set(ROWS) == set(LANGUAGES) | {'tsx'}


@pytest.mark.parametrize('language', sorted(ROWS))
@pytest.mark.parametrize('flag,keywords', [
    ('ifmap', {'IF', 'ELIF', 'ELSE', 'UNLESS', 'SWITCH', 'CASE', 'DEFAULT'}),
    ('catchmap', {'TRY', 'CATCH', 'EXCEPT', 'FINALLY'}),
    ('loopmap', {'FOR', 'WHILE', 'LOOP', 'DO'}),
])
def test_selectors_keep_full_records_and_order(language, flag, keywords):
    ctx = _context(language, 3)
    ctx.args.ifmap = flag == 'ifmap'
    handler = _nav_loopmap if flag == 'loopmap' else _nav_branchmap
    assert _answer(ctx, handler) == _expected(language, keywords=keywords)


@pytest.mark.parametrize('language', sorted(ROWS))
@pytest.mark.parametrize('offset', [0, 1])
def test_range_selects_start_lines_without_clipping_spans(language, offset):
    first = ROWS[language][0][3] + offset
    bounds = (first, first)
    assert _answer(_context(language, 3, bounds), _nav_outline) == _expected(language, bounds=bounds)


@pytest.mark.parametrize('language', sorted(ROWS))
def test_cli_named_skeleton_uses_same_source_expectations(language):
    ctx = _context(language, 3)
    result = _run_reveal_direct(
        ctx.analyzer.path, ctx.element, '--outline', '--depth', '3', '--format', 'json',
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['findings'] == _expected(language)


@pytest.mark.parametrize('language,missing_lines', [
    ('cpp', {20}),
    ('rust', {14, 19}),
    ('zig', {14, 17, 21, 24}),
])
def test_known_skeleton_omissions_are_exits_in_sibling_view(language, missing_lines):
    """Qualification records a disagreement; it does not bless missing exits."""
    ctx = _context(language, 3)
    ctx.args.flowto = False
    exits = _answer(ctx, _nav_exits)
    assert missing_lines <= {record['line'] for record in exits}
    assert missing_lines.isdisjoint(
        record['line_start'] for record in _expected(language) if record['is_exit']
    )


@pytest.mark.parametrize('language,missing_lines', [
    ('cpp', {20}),
    ('rust', {14, 19}),
    ('zig', {14, 17, 21, 24}),
])
@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason='BACK-2364: skeleton omits source exits recognized by sibling view')
def test_source_exit_sites_should_also_appear_in_skeleton(language, missing_lines):
    records = _answer(_context(language, 3), _nav_outline)
    assert missing_lines <= {record['line_start'] for record in records if record['is_exit']}
