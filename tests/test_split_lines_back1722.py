"""split_lines: a line ends at \\n (and \\r\\n) only, like grep -n and wc -l (BACK-1722)."""

import pytest

from reveal.base import FileAnalyzer
from reveal.utils.lines import split_lines


@pytest.mark.parametrize('text,expected', [
    ('', []),
    ('\n', ['']),
    ('a', ['a']),
    ('a\n', ['a']),
    ('a\nb', ['a', 'b']),
    ('a\n\nb\n', ['a', '', 'b']),
    ('a\r\nb\r\n', ['a', 'b']),
    ('a\r\nb', ['a', 'b']),
    # negative controls against str.splitlines(): none of these end a line
    ('a\x0cb\n', ['a\x0cb']),
    ('a\x0bb\n', ['a\x0bb']),
    ('a\x1cb\x1db\x1e\n', ['a\x1cb\x1db\x1e']),
    ('a\x85b\n', ['a\x85b']),
    ('a b c', ['a b c']),
    ('\x0c\nx\n', ['\x0c', 'x']),
])
def test_split_lines_breaks_only_at_newline(text, expected):
    assert split_lines(text) == expected


@pytest.mark.parametrize('text', ['', 'a\n', 'a\nb', 'a\n\nb\n\n', 'one\ntwo\nthree\n'])
def test_split_lines_agrees_with_splitlines_on_plain_text(text):
    assert split_lines(text) == text.splitlines()


class _Reader(FileAnalyzer):
    def get_structure(self, **kwargs):
        return {}


@pytest.mark.parametrize('payload,count', [
    (b'a\nb\n', 2), (b'a\r\nb\r\n', 2), (b'a\nb', 2), (b'', 0), (b'\xef\xbb\xbfa\nb\n', 2),
    (b'a\x0c\nb\n', 2), (b'a\xe2\x80\xa8b\nc\n', 2),
    # not UTF-8: the latin-1 route, where \x85 (NEL) is a byte of text
    (b'caf\xe9\x85\nb\n', 2),
])
def test_read_file_line_count_is_the_newline_count(tmp_path, payload, count):
    path = tmp_path / 'f.txt'
    path.write_bytes(payload)
    assert len(_Reader(str(path)).lines) == count
    assert count == payload.count(b'\n') + (0 if payload.endswith(b'\n') or not payload else 1)


@pytest.mark.parametrize('text', ['', 'a', 'a\n', 'a\r\nb\n\nc', 'a\x0c\r\nb\x85\n', '\n\n'])
def test_keepends_pieces_join_back_and_count_like_the_plain_split(text):
    pieces = split_lines(text, keepends=True)
    assert ''.join(pieces) == text
    assert len(pieces) == len(split_lines(text))
    assert all(p.endswith('\n') for p in pieces[:-1])


def test_c_function_after_a_form_feed_is_on_the_line_grep_reports(tmp_path):
    """GNU C puts ^L between sections; grep -n / compilers count it inside its line."""
    data = b'/* a */\n\x0c\n/* b */\nint f(void)\n{\n  return 1;\n}\n\x0c\nint g(void)\n{\n  return 2;\n}\n'
    path = tmp_path / 'x.c'
    path.write_bytes(data)
    expected = {name: data[:data.index(b'int %s(' % name)].count(b'\n') + 1 for name in (b'f', b'g')}
    from reveal.registry import get_analyzer
    functions = get_analyzer(str(path))(str(path)).get_structure()['functions']
    assert {f['name']: f['line'] for f in functions} == {n.decode(): v for n, v in expected.items()}
    assert expected == {b'f': 4, b'g': 9}   # hand-counted
