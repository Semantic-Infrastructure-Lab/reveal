"""Tests for TreeSitterAnalyzer._code_line_count() -- the comment/docstring-
aware line count that feeds C902's length threshold, distinct from the raw
line_count span used everywhere else (e.g. LLM-cost estimates).
"""

import os
import tempfile
import unittest

from reveal.analyzers.python import PythonAnalyzer


def _structure_for(code: str):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(code)
        f.flush()
        temp_path = f.name
    try:
        analyzer = PythonAnalyzer(temp_path)
        structure = analyzer.get_structure()
    finally:
        os.unlink(temp_path)
    return structure


def _func(structure, name: str):
    matches = [f for f in structure['functions'] if f['name'] == name]
    assert len(matches) == 1, f"expected exactly one {name!r}, found {len(matches)}"
    return matches[0]


class TestCodeLineCount(unittest.TestCase):
    """code_line_count excludes blank lines and lines fully consumed by a
    comment or leading docstring; a line that mixes code and a trailing
    comment still counts as code.
    """

    def test_docstring_excluded(self):
        code = (
            "def f():\n"
            '    """This is a long docstring.\n'
            "    It explains something non-obvious.\n"
            '    """\n'
            "    x = 1\n"
            "    return x\n"
        )
        f = _func(_structure_for(code), 'f')
        # 6-line span; 3 docstring lines excluded -> 3 code lines remain
        # (def line, x = 1, return x).
        self.assertEqual(f['line_count'], 6)
        self.assertEqual(f['code_line_count'], 3)

    def test_standalone_comment_excluded(self):
        code = (
            "def f():\n"
            "    # explains why the next line is shaped this way\n"
            "    x = 1\n"
            "    return x\n"
        )
        f = _func(_structure_for(code), 'f')
        self.assertEqual(f['line_count'], 4)
        self.assertEqual(f['code_line_count'], 3)

    def test_blank_lines_excluded(self):
        code = (
            "def f():\n"
            "    x = 1\n"
            "\n"
            "    return x\n"
        )
        f = _func(_structure_for(code), 'f')
        self.assertEqual(f['line_count'], 4)
        self.assertEqual(f['code_line_count'], 3)

    def test_trailing_comment_line_still_counts_as_code(self):
        code = (
            "def f():\n"
            "    x = 1  # why x starts at 1, not 0\n"
            "    return x\n"
        )
        f = _func(_structure_for(code), 'f')
        # The comment shares its line with real code -- must not be blanked.
        self.assertEqual(f['line_count'], 3)
        self.assertEqual(f['code_line_count'], 3)

    def test_dense_function_without_comments_unaffected(self):
        code = (
            "def f():\n"
            "    x = 1\n"
            "    y = 2\n"
            "    return x + y\n"
        )
        f = _func(_structure_for(code), 'f')
        self.assertEqual(f['line_count'], f['code_line_count'])

    def test_non_docstring_leading_string_expression_not_special_cased(self):
        # A bare string literal anywhere but the very first statement isn't
        # a docstring -- must not be excluded.
        code = (
            "def f():\n"
            "    x = 1\n"
            "    'not a docstring, just a stray expression statement'\n"
            "    return x\n"
        )
        f = _func(_structure_for(code), 'f')
        self.assertEqual(f['line_count'], f['code_line_count'])


if __name__ == '__main__':
    unittest.main()
