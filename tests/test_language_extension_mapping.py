"""Tests for BACK-431 Issue B: single-sourced extension→language mapping.

Guards against the extension knowledge re-scattering into new parallel
tables the way it did before (calls/index.py's _LANG_FAMILY_EXTS and
path_utils.py's _NON_PYTHON_LANG_EXTS were both hand-maintained copies of
what the analyzer registry already knew; the latter was itself created to
fix BACK-403, a drift bug in an even earlier ad-hoc table).
"""

import unittest
from pathlib import Path

from reveal.registry import language_for_extension, display_name_for_extension
from reveal.adapters.calls.index import _lang_family
from reveal.utils.path_utils import detect_non_python_language


class TestLanguageForExtension(unittest.TestCase):
    """language_for_extension() covers both dedicated-analyzer and fallback-only extensions."""

    def test_dedicated_analyzer_extensions(self):
        cases = {
            '.py': 'python', '.rs': 'rust', '.go': 'go', '.rb': 'ruby',
            '.java': 'java', '.cs': 'csharp', '.kt': 'kotlin', '.kts': 'kotlin',
            '.ts': 'typescript', '.tsx': 'tsx', '.js': 'javascript',
            '.jsx': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript',
            '.swift': 'swift', '.scala': 'scala', '.lua': 'lua', '.dart': 'dart',
            '.c': 'c', '.h': 'c',
            '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp', '.hpp': 'cpp', '.hh': 'cpp', '.h++': 'cpp',
        }
        for ext, expected in cases.items():
            self.assertEqual(language_for_extension(ext), expected, ext)

    def test_fallback_only_extension(self):
        # .hxx has no dedicated analyzer — resolved via TREESITTER_EXTENSION_MAP.
        self.assertEqual(language_for_extension('.hxx'), 'cpp')
        self.assertEqual(language_for_extension('.m'), 'objc')
        self.assertEqual(language_for_extension('.mm'), 'objc')

    def test_unknown_extension_returns_none(self):
        self.assertIsNone(language_for_extension('.definitely-not-a-real-ext'))

    def test_case_insensitive(self):
        self.assertEqual(language_for_extension('.PY'), 'python')


class TestDisplayNameForExtension(unittest.TestCase):
    def test_overridden_names(self):
        self.assertEqual(display_name_for_extension('.cs'), 'C#')
        self.assertEqual(display_name_for_extension('.cpp'), 'C++')
        self.assertEqual(display_name_for_extension('.m'), 'Objective-C')
        self.assertEqual(display_name_for_extension('.js'), 'JavaScript')

    def test_capitalize_fallback(self):
        self.assertEqual(display_name_for_extension('.rs'), 'Rust')
        self.assertEqual(display_name_for_extension('.go'), 'Go')

    def test_unknown_returns_empty(self):
        self.assertEqual(display_name_for_extension('.definitely-not-a-real-ext'), '')


class TestCallGraphLanguageFamily(unittest.TestCase):
    """_lang_family() (BACK-405) reproduces the original hand-written table exactly."""

    def test_c_and_cpp_share_family(self):
        for ext in ('.c', '.h', '.cpp', '.cc', '.cxx', '.hpp', '.hh', '.h++', '.hxx'):
            self.assertEqual(_lang_family(f'file{ext}'), 'c', ext)

    def test_js_and_ts_share_family(self):
        for ext in ('.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx'):
            self.assertEqual(_lang_family(f'file{ext}'), 'js', ext)

    def test_distinct_families(self):
        cases = {
            '.py': 'python', '.go': 'go', '.rs': 'rust', '.java': 'java',
            '.cs': 'csharp', '.rb': 'ruby', '.php': 'php', '.kt': 'kotlin',
            '.kts': 'kotlin', '.swift': 'swift', '.scala': 'scala',
            '.lua': 'lua', '.dart': 'dart',
        }
        for ext, expected in cases.items():
            self.assertEqual(_lang_family(f'file{ext}'), expected, ext)

    def test_unknown_extension_returns_empty(self):
        self.assertEqual(_lang_family('file.txt'), '')


class TestDetectNonPythonLanguage(unittest.TestCase):
    """detect_non_python_language() (BACK-403) reproduces the original table exactly."""

    def test_single_file_cases(self, tmp_path=None):
        import tempfile
        cases = {
            'a.ts': 'TypeScript', 'a.tsx': 'TypeScript',
            'a.js': 'JavaScript', 'a.jsx': 'JavaScript',
            'a.mjs': 'JavaScript', 'a.cjs': 'JavaScript',
            'a.go': 'Go', 'a.rs': 'Rust', 'a.rb': 'Ruby', 'a.java': 'Java',
            'a.cs': 'C#', 'a.c': 'C', 'a.h': 'C',
            'a.cpp': 'C++', 'a.cc': 'C++', 'a.cxx': 'C++',
            'a.hpp': 'C++', 'a.hh': 'C++', 'a.h++': 'C++',
            'a.php': 'PHP', 'a.swift': 'Swift', 'a.scala': 'Scala', 'a.lua': 'Lua',
            'a.kt': 'Kotlin', 'a.kts': 'Kotlin', 'a.dart': 'Dart', 'a.gd': 'GDScript',
            'a.ex': 'Elixir', 'a.exs': 'Elixir', 'a.zig': 'Zig',
            'a.m': 'Objective-C', 'a.mm': 'Objective-C',
        }
        with tempfile.TemporaryDirectory() as d:
            for fname, expected in cases.items():
                f = Path(d) / fname
                f.write_text('')
                self.assertEqual(detect_non_python_language(f), expected, fname)
                f.unlink()

    def test_python_and_unknown_return_empty(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            py = Path(d) / 'main.py'
            py.write_text('')
            self.assertEqual(detect_non_python_language(py), '')
            txt = Path(d) / 'readme.txt'
            txt.write_text('')
            self.assertEqual(detect_non_python_language(txt), '')


if __name__ == '__main__':
    unittest.main()
