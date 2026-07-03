"""Tests for BACK-421: `.h` header C-vs-C++ grammar routing by content sniff.

`.h` is ambiguous between C and C++. The extension table maps it to C, which
hides C++ classes/templates/namespaces declared in headers (the common real-world
C++ layout). `_try_c_header_detection` sniffs the header for C++-only constructs
and routes those to the C++ analyzer, while leaving plain-C headers on C.
"""

import os
import tempfile
import unittest
from pathlib import Path

from reveal.registry import get_analyzer, _is_cpp_header_content


class TestCHeaderRouting(unittest.TestCase):

    def _write(self, content: str, name: str = 'header.h') -> str:
        d = tempfile.mkdtemp()
        path = os.path.join(d, name)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def setUp(self):
        self._cleanup = []

    def tearDown(self):
        for p in self._cleanup:
            try:
                os.unlink(p)
                os.rmdir(os.path.dirname(p))
            except OSError:
                pass

    def _make(self, content, name='header.h'):
        path = self._write(content, name)
        self._cleanup.append(path)
        return path

    # ── plain C headers stay on C ─────────────────────────────────────────────

    def test_plain_c_header_routes_to_c(self):
        path = self._make(
            '#ifndef P_H\n#define P_H\n'
            'struct point { int x; int y; };\n'
            'int add(int a, int b);\n#endif\n'
        )
        self.assertFalse(_is_cpp_header_content(path))
        self.assertEqual(get_analyzer(path).__name__, 'CAnalyzer')

    def test_c_header_with_typedef_stays_c(self):
        path = self._make(
            '#include <stddef.h>\n'
            'typedef struct { size_t len; char *buf; } string_t;\n'
            'void string_init(string_t *s);\n'
        )
        self.assertEqual(get_analyzer(path).__name__, 'CAnalyzer')

    # ── C++ headers route to C++ ──────────────────────────────────────────────

    def test_class_header_routes_to_cpp(self):
        path = self._make(
            '#ifndef W_H\n#define W_H\n'
            'class Widget {\npublic:\n  void draw();\n};\n#endif\n'
        )
        self.assertTrue(_is_cpp_header_content(path))
        self.assertEqual(get_analyzer(path).__name__, 'CppAnalyzer')

    def test_namespace_header_routes_to_cpp(self):
        path = self._make('namespace ui { void init(); }\n')
        self.assertEqual(get_analyzer(path).__name__, 'CppAnalyzer')

    def test_template_header_routes_to_cpp(self):
        path = self._make('template <typename T>\nT max(T a, T b);\n')
        self.assertEqual(get_analyzer(path).__name__, 'CppAnalyzer')

    def test_extern_c_header_routes_to_cpp(self):
        # extern "C" is only legal in C++ — it's a C++ header wrapping a C API.
        path = self._make('extern "C" {\n#include "capi.h"\n}\n')
        self.assertEqual(get_analyzer(path).__name__, 'CppAnalyzer')

    def test_cpp_header_class_becomes_visible_in_structure(self):
        """The end-to-end payoff: a header-declared C++ class is extracted."""
        path = self._make(
            'namespace ui {\nclass Button {\npublic:\n'
            '  virtual void click();\n};\n}\n'
        )
        analyzer_cls = get_analyzer(path)
        analyzer = analyzer_cls(path)
        structure = analyzer.get_structure()
        class_names = [c['name'] for c in structure.get('classes', [])]
        self.assertIn('Button', class_names)

    # ── .hpp/.cpp/.c are unaffected by the sniff ──────────────────────────────

    def test_hpp_still_cpp_without_sniff(self):
        path = self._make('struct Plain { int x; };\n', name='thing.hpp')
        self.assertEqual(get_analyzer(path).__name__, 'CppAnalyzer')

    def test_c_source_file_unaffected(self):
        path = self._make('int main(void) { return 0; }\n', name='main.c')
        self.assertEqual(get_analyzer(path).__name__, 'CAnalyzer')


if __name__ == '__main__':
    unittest.main()
