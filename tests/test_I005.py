"""Tests for I005: Duplicate imports detector."""

import unittest
from reveal.rules.imports.I005 import I005


def _imp(content, line=1, statement=None):
    """Build a minimal import dict as the Python analyzer produces."""
    d = {'content': content, 'line': line}
    if statement is not None:
        d['statement'] = statement
    return d


class TestI005Basic(unittest.TestCase):
    """Basic guard-rail tests."""

    def setUp(self):
        self.rule = I005()

    def test_no_structure_returns_empty(self):
        result = self.rule.check("f.py", None, "")
        self.assertEqual(result, [])

    def test_empty_structure_returns_empty(self):
        result = self.rule.check("f.py", {}, "")
        self.assertEqual(result, [])

    def test_no_imports_key_returns_empty(self):
        result = self.rule.check("f.py", {"functions": []}, "")
        self.assertEqual(result, [])

    def test_empty_imports_list_returns_empty(self):
        result = self.rule.check("f.py", {"imports": []}, "")
        self.assertEqual(result, [])

    def test_single_import_no_detection(self):
        structure = {"imports": [_imp("import os", line=1)]}
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(result, [])


class TestI005Detection(unittest.TestCase):
    """Duplicate-import detection tests."""

    def setUp(self):
        self.rule = I005()

    def test_exact_duplicate_detected(self):
        structure = {
            "imports": [
                _imp("import os", line=1),
                _imp("import os", line=5),
            ]
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].line, 5)
        self.assertIn("import os", result[0].message)
        self.assertIn("line 1", result[0].message)

    def test_three_duplicates_flags_second_and_third(self):
        structure = {
            "imports": [
                _imp("from json import loads", line=1),
                _imp("from json import loads", line=10),
                _imp("from json import loads", line=20),
            ]
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].line, 10)
        self.assertEqual(result[1].line, 20)

    def test_different_imports_no_detection(self):
        structure = {
            "imports": [
                _imp("import os", line=1),
                _imp("import sys", line=2),
                _imp("from pathlib import Path", line=3),
            ]
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(result, [])

    def test_duplicate_uses_first_as_original(self):
        """Message should reference line 1 as the original."""
        structure = {
            "imports": [
                _imp("import re", line=1),
                _imp("import re", line=42),
            ]
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(len(result), 1)
        self.assertIn("line 1", result[0].message)
        self.assertIn("line 1", result[0].suggestion)

    def test_rule_code_is_I005(self):
        structure = {
            "imports": [
                _imp("import os", line=1),
                _imp("import os", line=2),
            ]
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(result[0].rule_code, "I005")

    def test_file_path_propagated(self):
        structure = {
            "imports": [
                _imp("import os", line=1),
                _imp("import os", line=2),
            ]
        }
        result = self.rule.check("mypackage/utils.py", structure, "")
        self.assertEqual(result[0].file_path, "mypackage/utils.py")


class TestI005Normalization(unittest.TestCase):
    """_normalize_import handles various dict shapes."""

    def setUp(self):
        self.rule = I005()

    def test_content_key_used(self):
        """Python analyzer emits 'content' — must be primary key."""
        imp = {'content': 'import os', 'line': 1}
        normalized = self.rule._normalize_import(imp)
        self.assertEqual(normalized, 'import os')

    def test_statement_key_fallback(self):
        """If 'content' is absent, fall back to 'statement'."""
        imp = {'statement': 'import sys', 'line': 1}
        normalized = self.rule._normalize_import(imp)
        self.assertEqual(normalized, 'import sys')

    def test_source_key_fallback(self):
        """If neither 'content' nor 'statement', try 'source'."""
        imp = {'source': 'import re', 'line': 1}
        normalized = self.rule._normalize_import(imp)
        self.assertEqual(normalized, 'import re')

    def test_module_symbol_reconstruction(self):
        """No text keys — reconstruct from module + symbol."""
        imp = {'module': 'os.path', 'symbol': 'join', 'line': 1}
        normalized = self.rule._normalize_import(imp)
        self.assertEqual(normalized, 'from os.path import join')

    def test_module_only_reconstruction(self):
        imp = {'module': 'sys', 'line': 1}
        normalized = self.rule._normalize_import(imp)
        self.assertEqual(normalized, 'import sys')

    def test_empty_dict_returns_none(self):
        normalized = self.rule._normalize_import({})
        self.assertIsNone(normalized)

    def test_whitespace_normalized(self):
        """Extra spaces should be collapsed."""
        imp1 = {'content': 'import  os', 'line': 1}
        imp2 = {'content': 'import os', 'line': 2}
        n1 = self.rule._normalize_import(imp1)
        n2 = self.rule._normalize_import(imp2)
        self.assertEqual(n1, n2)

    def test_case_insensitive(self):
        """Normalization is case-insensitive (for robustness)."""
        imp1 = {'content': 'Import OS', 'line': 1}
        imp2 = {'content': 'import os', 'line': 2}
        n1 = self.rule._normalize_import(imp1)
        n2 = self.rule._normalize_import(imp2)
        self.assertEqual(n1, n2)

    def test_content_takes_priority_over_statement(self):
        """'content' (Python analyzer key) wins over 'statement'."""
        imp = {'content': 'import os', 'statement': 'import sys', 'line': 1}
        normalized = self.rule._normalize_import(imp)
        self.assertEqual(normalized, 'import os')


class TestI005MixedDuplicates(unittest.TestCase):
    """One duplicate pair does not affect unrelated imports."""

    def setUp(self):
        self.rule = I005()

    def test_only_duplicates_flagged(self):
        structure = {
            "imports": [
                _imp("import os", line=1),
                _imp("import sys", line=2),
                _imp("import os", line=10),   # duplicate
                _imp("import re", line=11),
            ]
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].line, 10)

    def test_multiple_duplicate_pairs(self):
        structure = {
            "imports": [
                _imp("import os", line=1),
                _imp("import sys", line=2),
                _imp("import os", line=5),    # dup of line 1
                _imp("import sys", line=6),   # dup of line 2
            ]
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(len(result), 2)
        lines = {r.line for r in result}
        self.assertEqual(lines, {5, 6})


if __name__ == '__main__':
    unittest.main()
