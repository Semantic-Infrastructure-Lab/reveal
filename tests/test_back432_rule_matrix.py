"""BACK-432 first tranche: rule-correctness matrix for non-Python languages.

The 77 `--check` rules are validated for "doesn't hang" but not for "fires
correctly per language" — several (I001/I002/I005, C901/C902/C905) advertise
universal or multi-language scope with zero non-Python test coverage. This
file adds at least one real, on-disk non-Python positive test (the rule
correctly fires) and one negative test (the rule correctly stays silent) per
rule in this first tranche, per the acceptance bar in internal-docs/BACKLOG.md
BACK-432: "no rule silently claims universal scope unless it has at least one
non-Python positive and one non-Python negative test."

I002/I005 non-Python coverage surfaced a real bug fixed alongside these tests:
every non-Python import extractor (Go/Rust/JS) left ImportStatement.source_line
at its default "" (only python.py populated it), so I005's normalization step
(`if not normalized: continue`) silently skipped every non-Python import,
making I005 blind to duplicates in every language but Python despite
advertising Python/JS/Go/Rust support. Fixed in
reveal/analyzers/imports/{go,rust,javascript}.py via a shared `_line_text`
helper; confirmed to fail (0 detections) before the fix.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from reveal.registry import get_analyzer
from reveal.rules.complexity.C901 import C901
from reveal.rules.complexity.C902 import C902
from reveal.rules.complexity.C905 import C905
from reveal.rules.imports.I002 import I002
from reveal.rules.imports.I005 import I005


class _TempDirMixin:
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix='reveal_test_back432_'))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write(self, name: str, content: str) -> Path:
        path = self.temp_dir / name
        path.write_text(content)
        return path


class TestI002CircularDependencyJavaScript(_TempDirMixin, unittest.TestCase):
    """I002 claims JS support (docstring: "Supports Python, JavaScript, Go,
    and Rust") but its whole test suite (test_rules.py) is Python-only."""

    def test_js_circular_require_detected(self):
        (self.temp_dir / 'package.json').write_text('{"name": "test"}')
        a_content = (
            "const b = require('./b');\n\n"
            "function funcA() {\n  return b.funcB();\n}\n\n"
            "module.exports = { funcA };\n"
        )
        b_content = (
            "const a = require('./a');\n\n"
            "function funcB() {\n  return a.funcA();\n}\n\n"
            "module.exports = { funcB };\n"
        )
        self._write('a.js', a_content)
        self._write('b.js', b_content)

        rule = I002()
        detections = rule.check(str(self.temp_dir / 'a.js'), None, a_content)

        self.assertGreater(len(detections), 0, "Should detect JS circular require")
        self.assertEqual(detections[0].rule_code, 'I002')
        self.assertIn('a.js', detections[0].context)
        self.assertIn('b.js', detections[0].context)

    def test_js_linear_requires_no_false_positive(self):
        (self.temp_dir / 'package.json').write_text('{"name": "test"}')
        top = "const mid = require('./mid');\nfunction top() { return mid.mid(); }\nmodule.exports = { top };\n"
        mid = "const bottom = require('./bottom');\nfunction mid() { return bottom.bottom(); }\nmodule.exports = { mid };\n"
        bottom = "function bottom() { return 1; }\nmodule.exports = { bottom };\n"
        self._write('top.js', top)
        self._write('mid.js', mid)
        self._write('bottom.js', bottom)

        rule = I002()
        for name, content in (('top.js', top), ('mid.js', mid), ('bottom.js', bottom)):
            detections = rule.check(str(self.temp_dir / name), None, content)
            self.assertEqual(detections, [], f"{name}: no cycle exists, must not false-positive")


class TestI005DuplicateImportsNonPython(_TempDirMixin, unittest.TestCase):
    """I005's file_patterns come from get_all_extensions() (.py/.js/.go/.rs/
    .ts/.tsx) but its whole test suite (test_I005.py) is Python-only.

    BACK-432: this surfaced a real bug — see module docstring — fixed by
    populating ImportStatement.source_line in the Go/Rust/JS extractors.
    """

    def test_javascript_duplicate_import_detected(self):
        content = (
            "import { foo } from 'module_a';\n"
            "import { bar } from 'module_b';\n"
            "import { foo } from 'module_a';\n"
        )
        path = self._write('dup.js', content)

        detections = I005().check(str(path), None, content)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'I005')
        self.assertEqual(detections[0].line, 3)

    def test_javascript_distinct_imports_no_false_positive(self):
        content = "import { foo } from 'module_a';\nimport { bar } from 'module_b';\n"
        path = self._write('ok.js', content)

        self.assertEqual(I005().check(str(path), None, content), [])

    def test_go_duplicate_import_detected(self):
        content = 'package main\n\nimport (\n\t"fmt"\n\t"fmt"\n)\n\nfunc main() {\n\tfmt.Println("hi")\n}\n'
        path = self._write('dup.go', content)

        detections = I005().check(str(path), None, content)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'I005')

    def test_go_distinct_imports_no_false_positive(self):
        content = 'package main\n\nimport (\n\t"fmt"\n\t"os"\n)\n\nfunc main() {\n\tfmt.Println(os.Args)\n}\n'
        path = self._write('ok.go', content)

        self.assertEqual(I005().check(str(path), None, content), [])

    def test_rust_duplicate_import_detected(self):
        content = "use std::collections::HashMap;\nuse std::io;\nuse std::collections::HashMap;\n"
        path = self._write('dup.rs', content)

        detections = I005().check(str(path), None, content)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'I005')

    def test_rust_distinct_imports_no_false_positive(self):
        content = "use std::collections::HashMap;\nuse std::io;\n"
        path = self._write('ok.rs', content)

        self.assertEqual(I005().check(str(path), None, content), [])


class TestComplexityRulesRealGoFixtures(_TempDirMixin, unittest.TestCase):
    """C901/C902/C905 declare file_patterns=['*'] (universal) but their test
    suites (test_complexity_rules_c901_c905.py, test_C905.py) only exercise
    hand-built mock `structure` dicts, never a real non-Python analyzer.
    Uses Go here since GoAnalyzer computes real complexity/depth/line_count
    per function, exercising the actual structure-extraction path these
    rules read from, not just their own arithmetic.
    """

    def _go_structure(self, name: str, source: str):
        path = self._write(name, source)
        analyzer_class = get_analyzer(str(path), allow_fallback=False)
        analyzer = analyzer_class(str(path))
        return path, analyzer.get_structure(), analyzer.content

    def test_c901_flags_real_high_complexity_go_function(self):
        lines = ["package main", "", "func classify(x int) string {"]
        for i in range(1, 30):
            kw = "if" if i == 1 else "} else if"
            lines.append(f"\t{kw} x == {i} {{")
            lines.append(f"\t\treturn \"{i}\"")
        lines.append("\t}")
        lines.append('\treturn "unknown"')
        lines.append("}")
        path, structure, content = self._go_structure("complex.go", "\n".join(lines) + "\n")

        detections = C901().check(str(path), structure, content)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'C901')

    def test_c901_no_false_positive_on_simple_go_function(self):
        path, structure, content = self._go_structure(
            "simple.go", 'package main\n\nfunc add(a, b int) int {\n\treturn a + b\n}\n'
        )

        self.assertEqual(C901().check(str(path), structure, content), [])

    def test_c902_flags_real_long_go_function(self):
        lines = ["package main", "", "func longFunc() int {"]
        for i in range(120):
            lines.append(f"\tx{i} := {i}")
        lines.append("\treturn 0")
        lines.append("}")
        path, structure, content = self._go_structure("long.go", "\n".join(lines) + "\n")

        detections = C902().check(str(path), structure, content)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'C902')

    def test_c902_no_false_positive_on_short_go_function(self):
        path, structure, content = self._go_structure(
            "short.go", 'package main\n\nfunc shortFunc() int {\n\treturn 1\n}\n'
        )

        self.assertEqual(C902().check(str(path), structure, content), [])

    def test_c905_flags_real_deeply_nested_go_function(self):
        depth = 9
        lines = ["package main", "", "func deepNest(x int) int {"]
        indent = "\t"
        for i in range(depth):
            lines.append(f"{indent}if x > {i} {{")
            indent += "\t"
        lines.append(f"{indent}return x")
        for _ in range(depth):
            indent = indent[:-1]
            lines.append(f"{indent}}}")
        lines.append("\treturn 0")
        lines.append("}")
        path, structure, content = self._go_structure("nest.go", "\n".join(lines) + "\n")

        detections = C905().check(str(path), structure, content)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'C905')

    def test_c905_no_false_positive_on_shallow_go_function(self):
        path, structure, content = self._go_structure(
            "shallow.go",
            'package main\n\nfunc shallow(x int) int {\n\tif x > 0 {\n\t\treturn x\n\t}\n\treturn 0\n}\n',
        )

        self.assertEqual(C905().check(str(path), structure, content), [])


if __name__ == '__main__':
    unittest.main()
