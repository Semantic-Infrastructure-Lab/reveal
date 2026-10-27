"""BACK-2281: a closing fence on the last line with no trailing newline is not code.

tree-sitter-markdown emits no closing ``fenced_code_block_delimiter`` there and puts the fence in
``code_fence_content``, so ``reveal e.md --code`` showed ``source: "x\\n```"``.
"""
import json

import pytest

from conftest import _run_reveal_direct


def _blocks(tmp_path, text):
    path = tmp_path / 'e.md'
    path.write_bytes(text.encode('utf-8'))
    r = _run_reveal_direct(str(path), '--code', '--format', 'json')
    assert r.returncode == 0, r.stderr
    return [(b['source'], b['line_count'], b['line_end'])
            for b in json.loads(r.stdout)['structure']['code_blocks']]


@pytest.mark.parametrize('text, expected', [
    ('# T\n\n```\nx\n```', [('x\n', 1, 5)]),
    ('# T\n\n```py\nx\ny\n  ```  ', [('x\ny\n', 2, 6)]),
    ('# T\n\n```\n```', [('', 0, 4)]),
    # A shorter fence does not close a longer one: the inner ``` stays, the last line closes.
    ('# T\n\n````\nx\n```\n````', [('x\n```\n', 2, 6)]),
    ('# T\n\n~~~\nx\n~~~', [('x\n', 1, 5)]),
])
def test_closing_fence_at_eof_is_not_in_the_source(tmp_path, text, expected):
    assert _blocks(tmp_path, text) == expected


@pytest.mark.parametrize('text, expected', [
    # Negative controls: a trailing newline (the grammar closes the block itself) ...
    ('# T\n\n```\nx\n```\n', [('x\n', 1, 5)]),
    # ... an unclosed fence keeps all its content ...
    ('# T\n\n```\nx\n```py', [('x\n```py', 2, 5)]),
    ('# T\n\n````\nx\n```', [('x\n```', 2, 5)]),
    ('# T\n\n```\nx\n~~~', [('x\n~~~', 2, 5)]),
    # ... and so does a block that runs to EOF without any closing line.
    ('# T\n\n```\nx', [('x', 1, 4)]),
])
def test_other_fence_endings_are_unchanged(tmp_path, text, expected):
    assert _blocks(tmp_path, text) == expected
