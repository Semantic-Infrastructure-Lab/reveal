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
from reveal.rules.duplicates.D001 import D001
from reveal.rules.duplicates.D002 import D002
from reveal.rules.errors.E501 import E501
from reveal.rules.imports.I002 import I002
from reveal.rules.imports.I003 import I003
from reveal.rules.imports.I005 import I005
from reveal.rules.maintainability.M101 import M101
from reveal.rules.maintainability.M501 import M501
from reveal.rules.security.S001 import S001
from reveal.rules.urls.U501 import U501


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


class TestD001DuplicateFunctionsNonPython(_TempDirMixin, unittest.TestCase):
    """D001 declares file_patterns=['*'] ("works on any language with
    functions") but its whole suite (test_D001.py) is Python-only. It reads
    real `functions` (with line/line_end) from the analyzer's structure, so a
    silent per-language extraction gap (like BACK-461's for imports) would make
    it blind to duplicates outside Python. Positive: two byte-identical bodies
    (same identifiers) must be flagged; negative: bodies that differ only by an
    identifier must NOT be flagged (D001 does not rename variables).
    """

    def _structure(self, name: str, source: str):
        path = self._write(name, source)
        analyzer_class = get_analyzer(str(path), allow_fallback=False)
        analyzer = analyzer_class(str(path))
        return path, analyzer.get_structure(), analyzer.content

    _DUP = {
        'dup.go': (
            'package main\n\n'
            'func alpha(x int) int {\n\ttotal := x * 2\n\ttotal = total + 5\n\treturn total\n}\n\n'
            'func beta(x int) int {\n\ttotal := x * 2\n\ttotal = total + 5\n\treturn total\n}\n'
        ),
        'dup.js': (
            'function alpha(x) {\n\tlet total = x * 2;\n\ttotal = total + 5;\n\treturn total;\n}\n\n'
            'function beta(x) {\n\tlet total = x * 2;\n\ttotal = total + 5;\n\treturn total;\n}\n'
        ),
        'dup.rs': (
            'fn alpha(x: i32) -> i32 {\n\tlet mut total = x * 2;\n\ttotal = total + 5;\n\ttotal\n}\n\n'
            'fn beta(x: i32) -> i32 {\n\tlet mut total = x * 2;\n\ttotal = total + 5;\n\ttotal\n}\n'
        ),
    }

    def test_identical_bodies_flagged(self):
        for name, source in self._DUP.items():
            with self.subTest(lang=name):
                path, structure, content = self._structure(name, source)
                detections = D001().check(str(path), structure, content)
                self.assertEqual(len(detections), 1, f'{name}: {detections}')
                self.assertEqual(detections[0].rule_code, 'D001')
                self.assertIn('beta', detections[0].message)

    def test_bodies_differing_by_identifier_not_flagged(self):
        # Same shape, different variable name (x vs y) — not an exact duplicate.
        source = (
            'package main\n\n'
            'func alpha(x int) int {\n\ttotal := x + 1\n\treturn total\n}\n\n'
            'func beta(y int) int {\n\ttotal := y + 1\n\treturn total\n}\n'
        )
        path, structure, content = self._structure('near.go', source)
        self.assertEqual(D001().check(str(path), structure, content), [])


class TestM501MarkersNonPython(_TempDirMixin, unittest.TestCase):
    """M501 declares file_patterns=['*'] ("universal: all file types") but its
    marker regex only matched `#`-style comments, so every C-family/Go/Rust/JS
    (`//`, `/* */`), HTML/Markdown (`<!-- -->`) and SQL/Lua (`--`) marker was
    invisible (BACK-432 — a real bug fixed alongside this test). Positive: each
    non-`#` comment style is detected; negative: a bare marker in a string
    literal stays unflagged.
    """

    def test_non_hash_comment_styles_detected(self):
        cases = {
            'f.go': '// TODO: refactor\nx := 1 // FIXME now\n',   # 2 markers
            'f.c': '/* HACK: temp shim */\nint x = 1;\n',          # 1
            'f.html': '<!-- XXX: revisit layout -->\n',            # 1
            'f.sql': '-- TODO: add covering index\nSELECT 1;\n',   # 1
        }
        expected = {'f.go': 2, 'f.c': 1, 'f.html': 1, 'f.sql': 1}
        for name, source in cases.items():
            with self.subTest(file=name):
                path = self._write(name, source)
                detections = M501().check(str(path), None, source)
                self.assertEqual(len(detections), expected[name], f'{name}: {detections}')

    def test_marker_in_string_literal_not_flagged(self):
        # No comment introducer → must stay silent (matches the Python-only
        # test_non_comment_todo_not_flagged contract, cross-language).
        source = 'const msg = "TODO: not a real comment";\n'
        path = self._write('f.js', source)
        self.assertEqual(M501().check(str(path), None, source), [])


class TestD002NearDuplicateNonPython(_TempDirMixin, unittest.TestCase):
    """D002 declares file_patterns=['*'] and reads real `functions` from the
    analyzer structure (same extraction path as D001/BACK-461), but its suite
    (test_D002.py) is Python-only. Positive: two near-identical Go/JS functions
    (same shape, renamed vars) rank as a candidate; negative: two structurally
    different functions do not."""

    def _structure(self, name: str, source: str):
        path = self._write(name, source)
        analyzer_class = get_analyzer(str(path), allow_fallback=False)
        analyzer = analyzer_class(str(path))
        return path, analyzer.get_structure(), analyzer.content

    _NEAR = {
        'near.go': (
            'package main\n\n'
            'func processA(items []int) int {\n\ttotal := 0\n\tfor _, v := range items {\n'
            '\t\tif v > 0 {\n\t\t\ttotal += v\n\t\t}\n\t}\n\ttotal = total * 2\n\treturn total\n}\n\n'
            'func processB(values []int) int {\n\tsum := 0\n\tfor _, x := range values {\n'
            '\t\tif x > 0 {\n\t\t\tsum += x\n\t\t}\n\t}\n\tsum = sum * 2\n\treturn sum\n}\n'
        ),
        'near.js': (
            'function processA(items) {\n\tlet total = 0;\n\tfor (const v of items) {\n'
            '\t\tif (v > 0) {\n\t\t\ttotal += v;\n\t\t}\n\t}\n\ttotal = total * 2;\n\treturn total;\n}\n\n'
            'function processB(values) {\n\tlet sum = 0;\n\tfor (const x of values) {\n'
            '\t\tif (x > 0) {\n\t\t\tsum += x;\n\t\t}\n\t}\n\tsum = sum * 2;\n\treturn sum;\n}\n'
        ),
    }

    def test_near_duplicate_ranked(self):
        for name, source in self._NEAR.items():
            with self.subTest(lang=name):
                path, structure, content = self._structure(name, source)
                detections = D002().check(str(path), structure, content)
                self.assertEqual(len(detections), 1, f'{name}: {detections}')
                self.assertEqual(detections[0].rule_code, 'D002')

    def test_structurally_different_not_ranked(self):
        # Two functions doing genuinely different work (below MIN_SIMILARITY).
        source = (
            'package main\n\n'
            'func greet(name string) string {\n\tprefix := "Hello, "\n\tgreeting := prefix + name\n'
            '\tgreeting = greeting + "!"\n\treturn greeting\n}\n\n'
            'func fib(n int) int {\n\ta, b := 0, 1\n\tfor i := 0; i < n; i++ {\n'
            '\t\ta, b = b, a+b\n\t}\n\treturn a\n}\n'
        )
        path, structure, content = self._structure('diff.go', source)
        self.assertEqual(D002().check(str(path), structure, content), [])


class TestS001SecretsNonPythonFormats(_TempDirMixin, unittest.TestCase):
    """S001 declares file_patterns=['.py', '.env', '.yaml', '.yml', '.toml']
    with per-format branches, but its suite (test_rules.py) only exercises the
    Python AST path. Covers the .env/.yaml/.toml regex branches: each flags a
    real secret assigned to a secret-named key, and each stays silent on a
    placeholder value."""

    _SECRET = 'sk-ant-abc123def456ghi789'

    def test_secret_flagged_per_format(self):
        cases = {
            'config.env': f'API_KEY={self._SECRET}\n',
            'config.yaml': f'api_key: {self._SECRET}\n',
            'config.toml': f'api_key = "{self._SECRET}"\n',
        }
        for name, source in cases.items():
            with self.subTest(fmt=name):
                path = self._write(name, source)
                detections = S001().check(str(path), None, source)
                self.assertEqual(len(detections), 1, f'{name}: {detections}')
                self.assertEqual(detections[0].rule_code, 'S001')

    def test_placeholder_not_flagged_per_format(self):
        cases = {
            'safe.env': 'API_KEY=your-key-here\n',
            'safe.yaml': 'api_key: ${API_KEY}\n',
            'safe.toml': 'api_key = "changeme"\n',
        }
        for name, source in cases.items():
            with self.subTest(fmt=name):
                path = self._write(name, source)
                self.assertEqual(S001().check(str(path), None, source), [])


class TestE501LineTooLongNonPython(_TempDirMixin, unittest.TestCase):
    """E501 declares file_patterns=['*'] but its suite is Python-only. It is a
    pure line-length scan, so it must fire on an over-length code line in any
    language and stay silent when every line is within the limit. (skip_categories
    gating for data/doc files is applied by the rule runner, not check(), so it's
    out of scope for this unit test.)"""

    def test_long_line_flagged(self):
        long_line = 'let total = ' + ' + '.join('1' for _ in range(60)) + ';'
        for name, source in {
            'f.go': f'package main\nfunc f() {{\n\t{long_line}\n}}\n',
            'f.rs': f'fn main() {{\n\t{long_line}\n}}\n',
        }.items():
            with self.subTest(lang=name):
                path = self._write(name, source)
                detections = E501().check(str(path), None, source)
                self.assertTrue(detections, f'{name}: expected a long-line detection')
                self.assertEqual(detections[0].rule_code, 'E501')

    def test_short_lines_not_flagged(self):
        path = self._write('ok.go', 'package main\n\nfunc add(a, b int) int {\n\treturn a + b\n}\n')
        self.assertEqual(E501().check(str(path), None, 'package main\n\nfunc add(a, b int) int {\n\treturn a + b\n}\n'), [])


class TestU501GitHubHttpNonPython(_TempDirMixin, unittest.TestCase):
    """U501 declares file_patterns=['*'] but its suite is Python-only. Positive:
    an insecure http:// GitHub URL in a non-Python file is flagged; negative:
    the https:// form is not."""

    def test_insecure_github_url_flagged(self):
        source = 'const repo = "http://github.com/foo/bar";\n'
        path = self._write('f.js', source)
        detections = U501().check(str(path), None, source)
        self.assertEqual(len(detections), 1, detections)
        self.assertEqual(detections[0].rule_code, 'U501')

    def test_https_github_url_not_flagged(self):
        source = 'const repo = "https://github.com/foo/bar";\n'
        path = self._write('f.js', source)
        self.assertEqual(U501().check(str(path), None, source), [])


class TestM101FileTooLargeNonPython(_TempDirMixin, unittest.TestCase):
    """M101 declares file_patterns=['*'] but its suite is Python-only. It is a
    line-count check (WARN >500, ERROR >1000). Positive: a >500-line Go file is
    flagged; negative: a small Go file is not."""

    def test_large_file_flagged(self):
        source = 'package main\n\n' + '\n'.join(f'var x{i} = {i}' for i in range(600)) + '\n'
        path = self._write('big.go', source)
        detections = M101().check(str(path), None, source)
        self.assertEqual(len(detections), 1, detections)
        self.assertEqual(detections[0].rule_code, 'M101')

    def test_small_file_not_flagged(self):
        source = 'package main\n\nfunc main() {}\n'
        path = self._write('small.go', source)
        self.assertEqual(M101().check(str(path), None, source), [])


class TestI003ArchitecturalLayerNonPython(_TempDirMixin, unittest.TestCase):
    """I003 inherited BaseRule's default file_patterns=['*'] (universal) but its
    check() unconditionally calls extract_python_imports(), which only recognizes
    Python's tree-sitter import node kinds — on any other language it silently
    finds zero imports (no crash, no false positive, just quietly non-functional).
    Same silent-universal-scope class as BACK-461/M501: the rule ran its full
    config-load + parse path on every non-Python file for a result that could
    never be non-empty. Fixed by declaring file_patterns=['.py'] so the engine's
    matches_target() (which BOTH BACK-432's test bar and real `--check` runs go
    through) stops routing non-Python files to it at all; check() itself is left
    unchanged as a defense-in-depth no-op for any direct caller that bypasses
    matches_target (mirrors the V-rule guard precedent from BACK-468)."""

    def test_matches_target_excludes_non_python(self):
        self.assertFalse(I003.matches_target('service.go'))
        self.assertFalse(I003.matches_target('service.rs'))
        self.assertTrue(I003.matches_target('service.py'))

    def test_direct_check_on_non_python_file_is_a_safe_noop(self):
        """A caller that bypasses matches_target (e.g. an explicit --select I003
        run, or the old pre-fix behavior) must still not crash or false-positive
        on a non-Python file, even with a real violating-shaped layer config."""
        config = (
            'architecture:\n'
            '  layers:\n'
            '    - name: "services"\n'
            '      paths: ["services/"]\n'
            '      allow_imports: ["models/"]\n'
            '      deny_imports: ["api/"]\n'
        )
        (self.temp_dir / '.reveal.yaml').write_text(config)
        (self.temp_dir / 'services').mkdir()
        source = 'package services\n\nimport "myapp/api"\n\nfunc GetUser() {}\n'
        path = self._write('services/user_service.go', source)
        detections = I003().check(str(path), None, source)
        self.assertEqual(detections, [])


if __name__ == '__main__':
    unittest.main()
