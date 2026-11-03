"""BACK-2485: an outline record's line_end ignores whitespace after the node's last token.

tree-sitter-language-pack 1.12.x-1.14.x end a Scala case_clause after the newline and indent
that follow its body, so the raw end row named the next line and flow records differed per
pack. The helper trims that whitespace; these cases need no particular pack.
"""
from types import SimpleNamespace

import pytest

from reveal.adapters.ast.nav_outline import _end_line


def _node(start_row, end_row):
    return SimpleNamespace(start_position=SimpleNamespace(row=start_row),
                           end_position=SimpleNamespace(row=end_row))


@pytest.mark.parametrize('text, start_row, end_row, expected', [
    ('case _ => 1', 4, 4, 5),                    # single line, nothing to trim
    ('case _ =>\n  1', 4, 5, 6),                 # multi-line, ends on its last token
    ('case _ => 1\n    ', 4, 5, 5),              # trailing newline + indent: next row, trimmed
    ('case _ =>\n  1\n\n   ', 4, 7, 6),          # several trailing newlines
    ('case _ => 1   ', 4, 4, 5),                 # trailing spaces only, same row
    ('\n  ', 4, 5, 6),                           # whitespace-only text is left alone
    ('x\n', 9, 9, 10),                           # never moves above the start row
])
def test_line_end_stops_at_the_last_token(text, start_row, end_row, expected):
    assert _end_line(_node(start_row, end_row), lambda node: text) == expected
