"""Tests for reveal quality rules."""

import unittest
import tempfile
import os
from pathlib import Path
from typing import Dict
from reveal.rules.bugs.B001 import B001
from reveal.rules.complexity.C901 import C901
from reveal.rules.refactoring.R913 import R913
from reveal.rules.security.S701 import S701
from reveal.rules.security.S001 import S001
from reveal.rules.imports.I001 import I001


class TestB001BareExcept(unittest.TestCase):
    """Test B001: Bare except clause detector."""

    def create_temp_python(self, content: str) -> str:
        """Helper: Create temp Python file."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "test.py")
        with open(path, 'w') as f:
            f.write(content)
        return path

    def teardown_file(self, path: str):
        """Helper: Clean up temp file."""
        os.unlink(path)
        os.rmdir(os.path.dirname(path))

    def test_bare_except_detected(self):
        """Test that bare except is detected."""
        content = """
try:
    x = 1
except:
    pass
"""
        path = self.create_temp_python(content)
        try:
            rule = B001()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].rule_code, 'B001')
            self.assertEqual(detections[0].line, 4)

        finally:
            self.teardown_file(path)

    def test_specific_exception_ok(self):
        """Test that specific exception types don't trigger."""
        content = """
try:
    x = 1
except ValueError:
    pass
"""
        path = self.create_temp_python(content)
        try:
            rule = B001()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)

    def test_exception_as_variable_ok(self):
        """Test that 'except Exception as e' is ok."""
        content = """
try:
    x = 1
except Exception as e:
    print(e)
"""
        path = self.create_temp_python(content)
        try:
            rule = B001()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)

    def test_multiple_bare_excepts(self):
        """Test multiple bare excepts are all detected."""
        content = """
try:
    x = 1
except:
    pass

try:
    y = 2
except:
    pass
"""
        path = self.create_temp_python(content)
        try:
            rule = B001()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 2)

        finally:
            self.teardown_file(path)

    def test_syntax_error_handling(self):
        """Test that syntax errors are handled gracefully."""
        content = "def foo( incomplete"
        path = self.create_temp_python(content)
        try:
            rule = B001()
            detections = rule.check(path, None, content)

            # Should return empty, not crash
            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)


class TestC901Complexity(unittest.TestCase):
    """Test C901: Function complexity detector."""

    def setUp(self):
        """Clear config cache before each test."""
        from reveal.config import RevealConfig
        RevealConfig._cache.clear()

    def tearDown(self):
        """Clear config cache after each test."""
        from reveal.config import RevealConfig
        RevealConfig._cache.clear()

    def test_simple_function_ok(self):
        """Test that simple functions pass."""
        content = """
def simple():
    return 1
"""
        rule = C901()
        structure = {'functions': [{'name': 'simple', 'line': 2, 'end_line': 3}]}
        detections = rule.check('test.py', structure, content)

        self.assertEqual(len(detections), 0)

    def test_complex_function_detected(self):
        """Test that complex functions are detected using McCabe algorithm."""
        # Create a function with McCabe complexity of 11 (verified with mccabe library)
        # Note: no leading newline so line numbers start at 1
        content = """def complex_func(x):
    if x > 0:
        if x > 10:
            if x > 100:
                for i in range(x):
                    if i % 2 == 0:
                        while i > 0:
                            if i == 5:
                                if i == 6:
                                    if i and x:
                                        if i or x:
                                            pass
                            i -= 1
    return x
"""
        rule = C901()
        # Patch get_threshold to return 10 (default) - McCabe complexity is 11
        rule.get_threshold = lambda key, default: 10
        structure = {'functions': [{'name': 'complex_func', 'line': 1, 'end_line': 14}]}
        detections = rule.check('test.py', structure, content)

        self.assertEqual(len(detections), 1)
        self.assertIn('complexity: 11', detections[0].message)  # McCabe-calculated

    def test_no_structure(self):
        """Test handling when no structure provided."""
        rule = C901()
        detections = rule.check('test.py', None, "")

        self.assertEqual(len(detections), 0)

    def test_empty_functions_list(self):
        """Test handling when functions list is empty."""
        rule = C901()
        detections = rule.check('test.py', {'functions': []}, "")

        self.assertEqual(len(detections), 0)

    def test_threshold(self):
        """Test that the default threshold is 10."""
        rule = C901()
        # Check DEFAULT_THRESHOLD attribute (class constant)
        self.assertEqual(rule.DEFAULT_THRESHOLD, 10)
        # Note: get_threshold will read from .reveal.yaml if present
        # So we just verify the DEFAULT_THRESHOLD constant exists


class TestR913TooManyArgs(unittest.TestCase):
    """Test R913: Too many arguments detector."""

    def create_temp_python(self, content: str) -> str:
        """Helper: Create temp Python file."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "test.py")
        with open(path, 'w') as f:
            f.write(content)
        return path

    def teardown_file(self, path: str):
        """Helper: Clean up temp file."""
        os.unlink(path)
        os.rmdir(os.path.dirname(path))

    def test_few_args_ok(self):
        """Test that functions with 5 or fewer args pass."""
        content = """
def ok_func(a, b, c, d, e):
    return a + b + c + d + e
"""
        path = self.create_temp_python(content)
        try:
            rule = R913()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)

    def test_too_many_args_detected(self):
        """Test that functions with >5 args are detected."""
        content = """
def too_many(a, b, c, d, e, f, g):
    return sum([a, b, c, d, e, f, g])
"""
        path = self.create_temp_python(content)
        try:
            rule = R913()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].rule_code, 'R913')
            self.assertIn('too_many', detections[0].message.lower())

        finally:
            self.teardown_file(path)

    def test_self_not_counted(self):
        """Test that 'self' is not counted as an argument."""
        content = """
class Foo:
    def method(self, a, b, c, d, e):
        pass
"""
        path = self.create_temp_python(content)
        try:
            rule = R913()
            detections = rule.check(path, None, content)

            # self + 5 args = 6 total, but self excluded = 5 args = OK
            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)

    def test_cls_not_counted(self):
        """Test that 'cls' is not counted as an argument."""
        content = """
class Foo:
    @classmethod
    def method(cls, a, b, c, d, e):
        pass
"""
        path = self.create_temp_python(content)
        try:
            rule = R913()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)

    def test_kwonly_args_counted(self):
        """Test that keyword-only args are counted."""
        content = """
def kwonly(a, b, *, c, d, e, f, g):
    pass
"""
        path = self.create_temp_python(content)
        try:
            rule = R913()
            detections = rule.check(path, None, content)

            # 2 positional + 5 kwonly = 7 args > 5
            self.assertEqual(len(detections), 1)

        finally:
            self.teardown_file(path)

    def test_async_functions(self):
        """Test async functions are also checked."""
        content = """
async def async_many(a, b, c, d, e, f):
    pass
"""
        path = self.create_temp_python(content)
        try:
            rule = R913()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 1)

        finally:
            self.teardown_file(path)

    def test_syntax_error_handling(self):
        """Test that syntax errors are handled gracefully."""
        content = "def bad("
        path = self.create_temp_python(content)
        try:
            rule = R913()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)


class TestS701DockerLatest(unittest.TestCase):
    """Test S701: Docker :latest tag detector."""

    def create_temp_dockerfile(self, content: str) -> str:
        """Helper: Create temp Dockerfile."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "Dockerfile")
        with open(path, 'w') as f:
            f.write(content)
        return path

    def teardown_file(self, path: str):
        """Helper: Clean up temp file."""
        os.unlink(path)
        os.rmdir(os.path.dirname(path))

    def test_explicit_latest_detected(self):
        """Test that :latest tag is detected."""
        content = """FROM python:latest
RUN pip install flask
"""
        path = self.create_temp_dockerfile(content)
        try:
            rule = S701()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].rule_code, 'S701')
            self.assertIn('python:latest', detections[0].message)

        finally:
            self.teardown_file(path)

    def test_specific_version_ok(self):
        """Test that specific versions pass."""
        content = """FROM python:3.10-slim
RUN pip install flask
"""
        path = self.create_temp_dockerfile(content)
        try:
            rule = S701()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)

    def test_missing_tag_detected(self):
        """Test that missing tag (implies :latest) is detected."""
        content = """FROM ubuntu
RUN apt-get update
"""
        path = self.create_temp_dockerfile(content)
        try:
            rule = S701()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 1)
            self.assertIn('missing tag', detections[0].message.lower())

        finally:
            self.teardown_file(path)

    def test_multistage_build(self):
        """Test multi-stage builds with AS clause."""
        content = """FROM node:18 AS builder
WORKDIR /app
FROM nginx:1.25
COPY --from=builder /app/dist /usr/share/nginx/html
"""
        path = self.create_temp_dockerfile(content)
        try:
            rule = S701()
            detections = rule.check(path, None, content)

            # Both have specific versions
            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)

    def test_uri_check(self):
        """Test checking Docker Hub URIs."""
        rule = S701()

        # URI with :latest in content
        detections = rule.check(
            'https://hub.docker.com/r/library/python/tags',
            None,
            'Available tags: :latest, 3.10, 3.9'
        )
        self.assertEqual(len(detections), 1)

    def test_uri_no_latest(self):
        """Test URI without :latest."""
        rule = S701()

        detections = rule.check(
            'https://hub.docker.com/r/library/python/tags',
            None,
            'Available tags: 3.10, 3.9, 3.8'
        )
        self.assertEqual(len(detections), 0)

    def test_multiple_from_statements(self):
        """Test multiple FROM statements."""
        content = """FROM python:latest
FROM node:latest
FROM nginx:1.25
"""
        path = self.create_temp_dockerfile(content)
        try:
            rule = S701()
            detections = rule.check(path, None, content)

            # Two :latest tags
            self.assertEqual(len(detections), 2)

        finally:
            self.teardown_file(path)


class TestS001HardcodedSecrets(unittest.TestCase):
    """Test S001: Hardcoded secrets detector."""

    rule = S001()

    def _py(self, content: str) -> str:
        """Write content to a temp .py file and return the path."""
        d = tempfile.mkdtemp()
        path = os.path.join(d, 'test.py')
        with open(path, 'w') as f:
            f.write(content)
        return path

    def _env(self, content: str) -> str:
        d = tempfile.mkdtemp()
        path = os.path.join(d, '.env')
        with open(path, 'w') as f:
            f.write(content)
        return path

    def _yaml(self, content: str) -> str:
        d = tempfile.mkdtemp()
        path = os.path.join(d, 'config.yaml')
        with open(path, 'w') as f:
            f.write(content)
        return path

    def _check(self, path: str, content: str):
        return self.rule.check(path, None, content)

    # Python: positive cases

    def test_py_simple_assignment_flagged(self):
        content = 'API_KEY = "sk-proj-abc123xyz789"\n'
        path = self._py(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 1)
        self.assertEqual(dets[0].rule_code, 'S001')
        self.assertIn('API_KEY', dets[0].message)

    def test_py_known_prefix_always_flagged(self):
        """Known-bad prefix overrides short length / non-secret name."""
        content = 'token = "ghp_abc123"\n'
        path = self._py(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 1)

    def test_py_password_flagged(self):
        content = 'DATABASE_PASSWORD = "s3cr3t!pass"\n'
        path = self._py(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 1)

    def test_py_annotated_assignment_flagged(self):
        content = 'secret_key: str = "real-secret-value-here"\n'
        path = self._py(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 1)

    # Python: negative cases

    def test_py_env_var_reference_ok(self):
        content = 'API_KEY = os.environ.get("API_KEY")\n'
        path = self._py(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 0)

    def test_py_placeholder_ok(self):
        content = 'API_KEY = "your-api-key-here"\n'
        path = self._py(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 0)

    def test_py_angle_bracket_ok(self):
        content = 'SECRET = "<your_secret>"\n'
        path = self._py(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 0)

    def test_py_test_value_ok(self):
        content = 'api_key = "test"\n'
        path = self._py(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 0)

    def test_py_non_secret_name_ok(self):
        content = 'debug = "sk-proj-abc123"\n'
        path = self._py(content)
        # "debug" doesn't match secret name pattern
        dets = self._check(path, content)
        # Known prefix overrides for name-based — but no, S001 requires both
        # name match OR known prefix (only name-based for Python, prefix is value-based)
        # Actually: name must match for Python path. "debug" doesn't match.
        self.assertEqual(len(dets), 0)

    def test_py_none_value_ok(self):
        content = 'API_KEY = None\n'
        path = self._py(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 0)

    # .env file

    def test_env_secret_flagged(self):
        content = 'DATABASE_PASSWORD=s3cr3t!pass\n'
        path = self._env(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 1)
        self.assertIn('DATABASE_PASSWORD', dets[0].message)

    def test_env_comment_ignored(self):
        content = '# DATABASE_PASSWORD=secret\n'
        path = self._env(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 0)

    def test_env_env_var_ref_ok(self):
        content = 'API_TOKEN=${REAL_TOKEN}\n'
        path = self._env(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 0)

    # YAML

    def test_yaml_secret_flagged(self):
        content = 'api_key: "real-secret-value-here"\n'
        path = self._yaml(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 1)

    def test_yaml_placeholder_ok(self):
        content = 'api_key: <YOUR_API_KEY>\n'
        path = self._yaml(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 0)

    def test_yaml_env_ref_ok(self):
        content = 'api_key: ${API_KEY}\n'
        path = self._yaml(content)
        dets = self._check(path, content)
        self.assertEqual(len(dets), 0)


class TestI001UnusedImports(unittest.TestCase):
    """Test I001: Unused imports detector."""

    def create_temp_python(self, content: str) -> str:
        """Helper: Create temp Python file."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "test.py")
        with open(path, 'w') as f:
            f.write(content)
        return path

    def teardown_file(self, path: str):
        """Helper: Clean up temp file."""
        os.unlink(path)
        os.rmdir(os.path.dirname(path))

    def test_unused_import_detected(self):
        """Test that unused imports are detected."""
        content = """
import os
import sys

def main():
    print("Hello")
"""
        path = self.create_temp_python(content)
        try:
            rule = I001()
            detections = rule.check(path, None, content)

            # Both os and sys are unused
            self.assertEqual(len(detections), 2)
            self.assertEqual(detections[0].rule_code, 'I001')

        finally:
            self.teardown_file(path)

    def test_used_import_ok(self):
        """Test that used imports don't trigger detection."""
        content = """
import os

def main():
    return os.path.join('a', 'b')
"""
        path = self.create_temp_python(content)
        try:
            rule = I001()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)

    def test_from_import_unused(self):
        """Test unused from imports flag each name individually."""
        content = """
from pathlib import Path
from typing import Dict, List

def main():
    return "Hello"
"""
        path = self.create_temp_python(content)
        try:
            rule = I001()
            detections = rule.check(path, None, content)

            # Path, Dict, and List are all unused - each flagged individually
            self.assertEqual(len(detections), 3)

        finally:
            self.teardown_file(path)

    def test_from_import_partially_used(self):
        """Test partially used from imports flag each unused name (aligned with Ruff F401)."""
        content = """
from typing import Dict, List

def main(x: List[str]) -> None:
    print(x)
"""
        path = self.create_temp_python(content)
        try:
            rule = I001()
            detections = rule.check(path, None, content)

            # Dict is unused - should be flagged individually (Ruff F401 alignment)
            # List is used - should NOT be flagged
            self.assertEqual(len(detections), 1)
            self.assertIn('Dict', detections[0].context)

        finally:
            self.teardown_file(path)

    def test_star_import_skipped(self):
        """Test that star imports are skipped."""
        content = """
from os import *

def main():
    print("Hello")
"""
        path = self.create_temp_python(content)
        try:
            rule = I001()
            detections = rule.check(path, None, content)

            # Star imports can't be reliably checked
            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)

    def create_temp_file(self, content: str, ext: str) -> str:
        """Helper: Create temp file with a given extension."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, f"test{ext}")
        with open(path, 'w') as f:
            f.write(content)
        return path

    def test_skip_unused_flag_suppresses_generic_extractor_languages(self):
        """BACK-412: generic-extractor languages (C#, C, Java, ...) set
        skip_unused=True because usage detection is unreliable for them —
        I001 must honor that flag instead of flagging every import."""
        content = """
using System;
using System.IO;

class C {
    void M() { Console.WriteLine("hi"); }
}
"""
        path = self.create_temp_file(content, ".cs")
        try:
            rule = I001()
            detections = rule.check(path, None, content)
            self.assertEqual(len(detections), 0)
        finally:
            self.teardown_file(path)

    # ── BACK-420: Rust/Go I001 false positives ────────────────────────────────

    def _i001_codes(self, content: str, ext: str):
        path = self.create_temp_file(content, ext)
        try:
            return I001().check(path, None, content)
        finally:
            self.teardown_file(path)

    def test_rust_glob_use_not_flagged_unused(self):
        """BACK-420: `use X::*` (import_type 'glob_use') can't be usage-checked
        and must be skipped, not flagged as unused for the literal name '*'."""
        content = (
            "use std::collections::*;\n"
            "fn f() -> HashMap<u32, u32> { HashMap::new() }\n"
        )
        self.assertEqual(len(self._i001_codes(content, ".rs")), 0)

    def test_rust_type_position_usage_not_flagged(self):
        """BACK-420: a name used only as a struct field *type* is a real usage —
        field_declaration must not be treated as a definition context."""
        content = (
            "use roaring::RoaringBitmap;\n"
            "pub struct S { pub used: RoaringBitmap }\n"
        )
        self.assertEqual(len(self._i001_codes(content, ".rs")), 0)

    def test_rust_genuinely_unused_still_flagged(self):
        content = (
            "use roaring::RoaringBitmap;\n"
            "fn f() -> i32 { 1 }\n"
        )
        codes = self._i001_codes(content, ".rs")
        self.assertEqual(len(codes), 1)

    def test_go_aliased_import_used_not_flagged(self):
        """BACK-420: an aliased import is referenced by its *alias*, not the
        package path basename — imported_names must be the alias."""
        content = (
            "package m\n\n"
            'import util "k8s.io/apimachinery/pkg/util/runtime"\n\n'
            "func run() { util.HandleError(nil) }\n"
        )
        self.assertEqual(len(self._i001_codes(content, ".go")), 0)

    def test_go_qualified_type_usage_not_flagged(self):
        """BACK-420: a package used only for a type (`sync.WaitGroup`, a
        qualified_type node) is a real usage the symbol walk must capture."""
        content = (
            "package m\n\n"
            'import "sync"\n\n'
            "type S struct { mu sync.WaitGroup }\n"
        )
        self.assertEqual(len(self._i001_codes(content, ".go")), 0)

    def test_go_genuinely_unused_alias_still_flagged(self):
        content = (
            "package m\n\n"
            'import (\n\t"fmt"\n\tunused "k8s.io/apimachinery/pkg/util/runtime"\n)\n\n'
            'func run() { fmt.Println("hi") }\n'
        )
        codes = self._i001_codes(content, ".go")
        self.assertEqual(len(codes), 1)


class TestI002CircularDependencies(unittest.TestCase):
    """Tests for I002 circular dependency detection rule."""

    def create_temp_module(self, files: Dict[str, str]) -> Path:
        """
        Helper: Create a temporary directory with multiple Python files.

        Args:
            files: Dict mapping filename to content

        Returns:
            Path to temp directory
        """
        import tempfile
        temp_dir = Path(tempfile.mkdtemp(prefix='reveal_test_i002_'))

        for filename, content in files.items():
            file_path = temp_dir / filename
            with open(file_path, 'w') as f:
                f.write(content)

        return temp_dir

    def teardown_module(self, temp_dir: Path):
        """Helper: Clean up temp directory."""
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    def test_simple_circular_dependency(self):
        """Test detection of simple A -> B -> A circular dependency."""
        files = {
            'module_a.py': """
import module_b

def func_a():
    return module_b.func_b()
""",
            'module_b.py': """
import module_a

def func_b():
    return module_a.func_a()
"""
        }
        temp_dir = self.create_temp_module(files)
        try:
            from reveal.rules.imports.I002 import I002
            rule = I002()

            # Check module_a - should find cycle
            file_a = str(temp_dir / 'module_a.py')
            content_a = files['module_a.py']
            detections_a = rule.check(file_a, None, content_a)

            self.assertGreater(len(detections_a), 0, "Should detect circular dependency in module_a")
            self.assertEqual(detections_a[0].rule_code, 'I002')
            self.assertIn('module_a.py', detections_a[0].context)
            self.assertIn('module_b.py', detections_a[0].context)

            # Check module_b - should also find the same cycle
            file_b = str(temp_dir / 'module_b.py')
            content_b = files['module_b.py']
            detections_b = rule.check(file_b, None, content_b)

            self.assertGreater(len(detections_b), 0, "Should detect circular dependency in module_b")

        finally:
            self.teardown_module(temp_dir)

    def test_three_file_circular_dependency(self):
        """Test detection of A -> B -> C -> A circular dependency."""
        files = {
            'alpha.py': """
import beta

def func_alpha():
    return beta.func_beta()
""",
            'beta.py': """
import gamma

def func_beta():
    return gamma.func_gamma()
""",
            'gamma.py': """
import alpha

def func_gamma():
    return alpha.func_alpha()
"""
        }
        temp_dir = self.create_temp_module(files)
        try:
            from reveal.rules.imports.I002 import I002
            rule = I002()

            # Check alpha - should find 3-file cycle
            file_alpha = str(temp_dir / 'alpha.py')
            content_alpha = files['alpha.py']
            detections = rule.check(file_alpha, None, content_alpha)

            self.assertGreater(len(detections), 0, "Should detect 3-file circular dependency")
            self.assertEqual(detections[0].rule_code, 'I002')

            # Verify the cycle involves all three files
            context = detections[0].context
            self.assertIn('alpha.py', context)
            self.assertIn('beta.py', context)
            self.assertIn('gamma.py', context)

        finally:
            self.teardown_module(temp_dir)

    def test_no_circular_dependency(self):
        """Test that DAG (no cycles) produces no detections."""
        files = {
            'top.py': """
import middle

def func_top():
    return middle.func_middle()
""",
            'middle.py': """
import bottom

def func_middle():
    return bottom.func_bottom()
""",
            'bottom.py': """
def func_bottom():
    return "leaf"
"""
        }
        temp_dir = self.create_temp_module(files)
        try:
            from reveal.rules.imports.I002 import I002
            rule = I002()

            # Check all files - none should have cycles
            for filename in files.keys():
                file_path = str(temp_dir / filename)
                content = files[filename]
                detections = rule.check(file_path, None, content)
                self.assertEqual(len(detections), 0, f"{filename} should have no circular dependencies")

        finally:
            self.teardown_module(temp_dir)

    def test_unrelated_file_no_detection(self):
        """Test that files not involved in cycles produce no detections."""
        files = {
            'cycle_a.py': """
import cycle_b

def func_a():
    return cycle_b.func_b()
""",
            'cycle_b.py': """
import cycle_a

def func_b():
    return cycle_a.func_a()
""",
            'independent.py': """
def func_independent():
    return "no dependencies"
"""
        }
        temp_dir = self.create_temp_module(files)
        try:
            from reveal.rules.imports.I002 import I002
            rule = I002()

            # Check independent file - should have no detections
            file_independent = str(temp_dir / 'independent.py')
            content_independent = files['independent.py']
            detections = rule.check(file_independent, None, content_independent)

            self.assertEqual(len(detections), 0, "Independent file should have no circular dependency detections")

        finally:
            self.teardown_module(temp_dir)

    def test_multiple_cycles(self):
        """Test handling of multiple independent cycles."""
        files = {
            'cycle1_a.py': """
import cycle1_b

def func():
    return cycle1_b.func()
""",
            'cycle1_b.py': """
import cycle1_a

def func():
    return cycle1_a.func()
""",
            'cycle2_a.py': """
import cycle2_b

def func():
    return cycle2_b.func()
""",
            'cycle2_b.py': """
import cycle2_a

def func():
    return cycle2_a.func()
"""
        }
        temp_dir = self.create_temp_module(files)
        try:
            from reveal.rules.imports.I002 import I002
            rule = I002()

            # Check cycle1_a - should only report cycles involving it
            file_cycle1_a = str(temp_dir / 'cycle1_a.py')
            content_cycle1_a = files['cycle1_a.py']
            detections = rule.check(file_cycle1_a, None, content_cycle1_a)

            self.assertGreater(len(detections), 0, "Should detect cycle involving cycle1_a")

            # Verify it's the right cycle (cycle1, not cycle2)
            context = detections[0].context
            self.assertIn('cycle1', context)
            self.assertNotIn('cycle2', context)

        finally:
            self.teardown_module(temp_dir)

    def test_exception_handling(self):
        """Test I002 handles exceptions gracefully."""
        from reveal.rules.imports.I002 import I002
        rule = I002()

        # Test with non-existent file (should return empty list, not crash)
        detections = rule.check("/nonexistent/path/file.py", None, "")
        self.assertEqual(len(detections), 0, "Should handle missing files gracefully")

    def test_syntax_error_handling(self):
        """Test I002 handles Python syntax errors gracefully."""
        files = {
            'bad_syntax.py': """
import good_module
def broken(
    # Missing closing paren - syntax error
"""
        }
        temp_dir = self.create_temp_module(files)
        try:
            from reveal.rules.imports.I002 import I002
            rule = I002()

            file_path = str(temp_dir / 'bad_syntax.py')
            content = files['bad_syntax.py']

            # Should not crash, should return empty detections
            detections = rule.check(file_path, None, content)
            self.assertIsInstance(detections, list, "Should return list even with syntax errors")

        finally:
            self.teardown_module(temp_dir)

    def test_break_point_suggestion_last_in_cycle(self):
        """Test suggestion when current file is last in cycle."""
        files = {
            'first.py': """
import second

def func():
    return second.func()
""",
            'second.py': """
import first

def func():
    return first.func()
"""
        }
        temp_dir = self.create_temp_module(files)
        try:
            from reveal.rules.imports.I002 import I002
            rule = I002()

            # Check second.py (which comes last in alphabetical order)
            file_second = str(temp_dir / 'second.py')
            content_second = files['second.py']
            detections = rule.check(file_second, None, content_second)

            # Should have a suggestion
            self.assertGreater(len(detections), 0)
            self.assertIsNotNone(detections[0].suggestion)
            self.assertIn('second.py', detections[0].context)

        finally:
            self.teardown_module(temp_dir)

    def test_type_checking_import_not_flagged_as_cycle(self):
        """if TYPE_CHECKING: import X should not create a graph edge even if X imports back."""
        files = {
            'registry.py': (
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    import analyzer\n"
                "\n"
                "def register():\n"
                "    pass\n"
            ),
            'analyzer.py': (
                "from registry import register\n"
                "\n"
                "class Analyzer:\n"
                "    pass\n"
            ),
        }
        temp_dir = self.create_temp_module(files)
        try:
            from reveal.rules.imports.I002 import I002
            rule = I002()

            detections = rule.check(str(temp_dir / 'registry.py'), None, files['registry.py'])
            self.assertEqual(len(detections), 0,
                "TYPE_CHECKING import should not create a cycle edge")
        finally:
            self.teardown_module(temp_dir)

    def test_function_body_import_not_flagged_as_cycle(self):
        """Deferred imports inside function bodies must not create cycle edges."""
        files = {
            'registry.py': (
                "def get_analyzer():\n"
                "    from analyzers import Analyzer\n"
                "    return Analyzer\n"
            ),
            'analyzers.py': (
                "from registry import get_analyzer\n"
                "\n"
                "class Analyzer:\n"
                "    pass\n"
            ),
        }
        temp_dir = self.create_temp_module(files)
        try:
            from reveal.rules.imports.I002 import I002
            rule = I002()

            detections = rule.check(str(temp_dir / 'registry.py'), None, files['registry.py'])
            self.assertEqual(len(detections), 0,
                "Function-body import should not create a cycle edge")
        finally:
            self.teardown_module(temp_dir)

    def test_real_top_level_cycle_still_detected(self):
        """Regression: real top-level cycles must still be caught after the fix."""
        files = {
            'alpha.py': "import beta\n",
            'beta.py': "import alpha\n",
        }
        temp_dir = self.create_temp_module(files)
        try:
            from reveal.rules.imports.I002 import I002
            rule = I002()
            detections = rule.check(str(temp_dir / 'alpha.py'), None, files['alpha.py'])
            self.assertGreater(len(detections), 0,
                "Real top-level cycle must still be detected")
        finally:
            self.teardown_module(temp_dir)


class TestI002ProjectRootCache(unittest.TestCase):
    """Regression tests for I002 cache keying on project root, not file parent.

    Before the fix, _build_import_graph used target_path.parent as the cache
    key, so a project with 73 subdirectories triggered 73 separate graph
    builds instead of 1.  The fix uses _find_project_root() so all files in
    the same project share a single cached graph.
    """

    def setUp(self):
        import tempfile, shutil
        self.tmp = Path(tempfile.mkdtemp(prefix='reveal_test_i002_root_'))
        # Sub-packages simulate a real multi-directory project
        (self.tmp / 'pkg_a').mkdir()
        (self.tmp / 'pkg_b').mkdir()
        (self.tmp / 'pkg_a' / '__init__.py').write_text('')
        (self.tmp / 'pkg_b' / '__init__.py').write_text('')
        # Cross-package cycle: pkg_a.mod -> pkg_b.mod -> pkg_a.mod
        (self.tmp / 'pkg_a' / 'mod.py').write_text('from pkg_b import mod\n')
        (self.tmp / 'pkg_b' / 'mod.py').write_text('from pkg_a import mod\n')
        # Mark as a git repo so _find_project_root resolves to self.tmp
        (self.tmp / '.git').mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_false_positive_across_packages(self):
        """Files in sibling packages do not produce false-positive cycles (correctness).

        Note: I002 resolves imports relative to each file's directory; absolute
        cross-package imports (e.g. ``from pkg_b import mod``) are not yet
        resolved to file paths, so no cycle is reported.  This is by design —
        better silent than wrong.
        """
        from reveal.rules.imports.I002 import I002, _graph_cache
        _graph_cache.clear()
        rule = I002()
        # Neither file should produce a false positive
        detections_a = rule.check(str(self.tmp / 'pkg_a' / 'mod.py'), None, '')
        detections_b = rule.check(str(self.tmp / 'pkg_b' / 'mod.py'), None, '')
        self.assertEqual(len(detections_a), 0, "No false-positive cycle for pkg_a/mod.py")
        self.assertEqual(len(detections_b), 0, "No false-positive cycle for pkg_b/mod.py")

    def test_shared_cache_across_subdirs(self):
        """Both pkg_a and pkg_b files share the same cached graph (performance)."""
        from reveal.rules.imports.I002 import I002, _graph_cache, _find_project_root
        _graph_cache.clear()
        rule = I002()

        file_a = str(self.tmp / 'pkg_a' / 'mod.py')
        file_b = str(self.tmp / 'pkg_b' / 'mod.py')

        rule.check(file_a, None, '')
        self.assertEqual(len(_graph_cache), 1, "First check should populate exactly one cache entry")

        rule.check(file_b, None, '')
        self.assertEqual(len(_graph_cache), 1, "Second check in sibling subdir must reuse the same cache entry")

    def test_project_root_resolves_to_git_root(self):
        """_find_project_root returns .git dir when no pyproject.toml exists."""
        from reveal.rules.imports.I002 import _find_project_root
        root = _find_project_root(self.tmp / 'pkg_a' / 'mod.py')
        self.assertEqual(root, self.tmp,
                         f"Expected {self.tmp}, got {root}")


class TestI002ProjectRootBACK338(unittest.TestCase):
    """Regression tests for BACK-338: check/hotspots hang on non-Python projects.

    Root cause was _find_project_root mis-detecting the project root and making
    I002 scan tens of thousands of unrelated files. Three layered defects:
      A — Pass-2 __init__.py walk crossed project boundaries (stray ancestor
          __init__.py hijacked the root of an unrelated non-package dir).
      B — non-Python project markers (package.json/go.mod/Cargo.toml) ignored.
      + a file-count ceiling so any future mis-detection degrades to a logged
        skip instead of an infinite hang.
    """

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix='reveal_back338_'))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stray_ancestor_init_does_not_hijack_root(self):
        """Defect A: a far-ancestor __init__.py must not hijack a non-package dir.

        This is the exact BACK-338 shape: a TS file deep under a shared src/
        whose only Python marker is a stray __init__.py several levels up.
        """
        from reveal.rules.imports.I002 import _find_project_root
        stray = self.tmp / 'src'
        proj = stray / 'projects' / 'myapp' / 'server' / 'src'
        proj.mkdir(parents=True)
        (stray / '__init__.py').write_text('')   # stray, far-ancestor marker
        target = proj / 'index.ts'
        target.write_text('import {x} from "./y";\n')

        root = _find_project_root(target.resolve())
        self.assertNotEqual(root, stray,
                            "stray ancestor __init__.py hijacked the root (Defect A)")
        # With no nearer marker, falls back to the target's own directory
        self.assertEqual(root, proj.resolve())

    def test_contiguous_python_package_still_resolves_to_top(self):
        """Defect A must not regress real Python packages — contiguous chain still works."""
        from reveal.rules.imports.I002 import _find_project_root
        pkg = self.tmp / 'mypkg'
        sub = pkg / 'sub'
        sub.mkdir(parents=True)
        (pkg / '__init__.py').write_text('')
        (sub / '__init__.py').write_text('')
        mod = sub / 'mod.py'
        mod.write_text('x = 1\n')

        root = _find_project_root(mod.resolve())
        self.assertEqual(root, pkg.resolve(),
                         "contiguous __init__.py chain should resolve to package top")

    def test_package_json_marker_detected(self):
        """Defect B: package.json marks a JS/TS project root."""
        from reveal.rules.imports.I002 import _find_project_root
        proj = self.tmp / 'tia-chess' / 'server'
        src = proj / 'src'
        src.mkdir(parents=True)
        (proj / 'package.json').write_text('{"name": "server"}\n')
        target = src / 'index.ts'
        target.write_text('import {x} from "./y";\n')

        root = _find_project_root(target.resolve())
        self.assertEqual(root, proj.resolve(),
                         "package.json should mark the project root (Defect B)")

    def test_innermost_package_json_wins(self):
        """Defect B: in a monorepo, the nearest package.json is the project boundary."""
        from reveal.rules.imports.I002 import _find_project_root
        outer = self.tmp / 'monorepo'
        inner = outer / 'packages' / 'server'
        src = inner / 'src'
        src.mkdir(parents=True)
        (outer / 'package.json').write_text('{"name": "monorepo"}\n')
        (inner / 'package.json').write_text('{"name": "server"}\n')
        target = src / 'index.ts'
        target.write_text('export const x = 1;\n')

        root = _find_project_root(target.resolve())
        self.assertEqual(root, inner.resolve(),
                         "nearest package.json should win over an outer one")

    def test_go_and_rust_markers_detected(self):
        """Defect B: go.mod and Cargo.toml also mark project roots."""
        from reveal.rules.imports.I002 import _find_project_root

        go_proj = self.tmp / 'goapp'
        go_sub = go_proj / 'internal'
        go_sub.mkdir(parents=True)
        (go_proj / 'go.mod').write_text('module goapp\n')
        go_target = go_sub / 'main.go'
        go_target.write_text('package internal\n')
        self.assertEqual(_find_project_root(go_target.resolve()), go_proj.resolve())

        rust_proj = self.tmp / 'rustapp'
        rust_sub = rust_proj / 'src'
        rust_sub.mkdir(parents=True)
        (rust_proj / 'Cargo.toml').write_text('[package]\nname = "rustapp"\n')
        rust_target = rust_sub / 'lib.rs'
        rust_target.write_text('pub fn x() {}\n')
        self.assertEqual(_find_project_root(rust_target.resolve()), rust_proj.resolve())

    def test_file_count_ceiling_aborts_scan(self):
        """Hardening: scan aborts to empty graph past the file ceiling (logged skip)."""
        import os
        from unittest import mock
        from reveal.rules.imports.I002 import I002, _graph_cache
        for i in range(6):
            (self.tmp / f'm{i}.py').write_text('import os\n')
        _graph_cache.clear()
        with mock.patch.dict(os.environ, {'REVEAL_I002_MAX_FILES': '3'}):
            imports = I002()._collect_raw_imports(self.tmp)
        self.assertEqual(imports, [],
                         "scan should abort to empty list when ceiling exceeded")

    def test_ceiling_aborts_before_parsing_any_file(self):
        """BACK-418: over-ceiling trees must abort *before* parsing, not after.

        The old loop counted files as it parsed them, so it still ran tree-sitter
        on ~ceiling large real-world files before bailing — a multi-minute hang on
        big non-Python trees (a 5-file subdir under a marker root took >100s). The
        fix counts in a cheap first pass and bails before any extractor runs, so
        no import extraction happens at all when the ceiling is blown.
        """
        import os
        from unittest import mock
        from reveal.rules.imports import I002 as i002_mod
        from reveal.rules.imports.I002 import I002, _graph_cache
        for i in range(6):
            (self.tmp / f'm{i}.py').write_text('import os\n')
        _graph_cache.clear()
        real_get_extractor = i002_mod.get_extractor
        parsed = []

        def _tracking_get_extractor(path):
            parsed.append(path)
            return real_get_extractor(path)

        with mock.patch.dict(os.environ, {'REVEAL_I002_MAX_FILES': '3'}), \
                mock.patch.object(i002_mod, 'get_extractor', _tracking_get_extractor):
            imports = I002()._collect_raw_imports(self.tmp)
        self.assertEqual(imports, [], "over-ceiling scan should return empty")
        self.assertEqual(parsed, [],
                         "no file should be parsed once the ceiling is exceeded")

    def test_ceiling_env_override_invalid_falls_back_to_default(self):
        """A non-integer REVEAL_I002_MAX_FILES falls back to the default ceiling."""
        import os
        from unittest import mock
        from reveal.rules.imports.I002 import _max_graph_files, _DEFAULT_MAX_GRAPH_FILES
        with mock.patch.dict(os.environ, {'REVEAL_I002_MAX_FILES': 'not-a-number'}):
            self.assertEqual(_max_graph_files(), _DEFAULT_MAX_GRAPH_FILES)

    def test_back338_check_does_not_hang_on_ts_project(self):
        """End-to-end: I002.check on a TS file under a stray __init__.py is bounded.

        Before the fix this scanned the whole ancestor tree. Now it must return
        quickly (no cycle in a 1-file project) regardless of the stray marker.
        """
        from reveal.rules.imports.I002 import I002, _graph_cache
        stray = self.tmp / 'src'
        proj = stray / 'projects' / 'app' / 'server' / 'src'
        proj.mkdir(parents=True)
        (stray / '__init__.py').write_text('')
        target = proj / 'index.ts'
        target.write_text('import {y} from "./y";\n')
        (proj / 'y.ts').write_text('export const y = 1;\n')

        _graph_cache.clear()
        detections = I002().check(str(target), None, target.read_text())
        self.assertEqual(detections, [], "no cycle expected; scan must stay bounded")
        # The cached scan root must be the local project, never the stray ancestor
        self.assertNotIn(stray.resolve(), _graph_cache)


class TestI001EdgeCases(unittest.TestCase):
    """Additional edge case tests for I001."""

    def create_temp_python(self, content: str) -> str:
        """Helper: Create temp Python file."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "test.py")
        with open(path, 'w') as f:
            f.write(content)
        return path

    def teardown_file(self, path: str):
        """Helper: Clean up temp file."""
        os.unlink(path)
        os.rmdir(os.path.dirname(path))

    def test_syntax_error_handling(self):
        """Test I001 handles syntax errors gracefully."""
        content = """
import os
def broken(
    # Syntax error - missing closing paren
"""
        path = self.create_temp_python(content)
        try:
            from reveal.rules.imports.I001 import I001
            rule = I001()
            detections = rule.check(path, None, content)

            # Tree-sitter can extract imports from broken code (better than ast.parse()!)
            # Should detect 'os' as unused (ast.parse() would have crashed)
            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].rule_code, 'I001')

        finally:
            self.teardown_file(path)

    def test_aliased_import_unused(self):
        """Test detection of unused aliased imports."""
        content = """
import os as operating_system
import sys as system

def main():
    print("Hello")
"""
        path = self.create_temp_python(content)
        try:
            from reveal.rules.imports.I001 import I001
            rule = I001()
            detections = rule.check(path, None, content)

            # Both aliased imports are unused
            self.assertEqual(len(detections), 2)

        finally:
            self.teardown_file(path)

    def test_aliased_import_used(self):
        """Test that used aliased imports don't trigger detection."""
        content = """
import os as operating_system

def main():
    return operating_system.path.join('a', 'b')
"""
        path = self.create_temp_python(content)
        try:
            from reveal.rules.imports.I001 import I001
            rule = I001()
            detections = rule.check(path, None, content)

            # Alias is used, should not detect
            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)


class TestI003LayerViolations(unittest.TestCase):
    """Tests for I003 architectural layer violation detection rule."""

    def create_temp_project(self, files: Dict[str, str], config: str = None) -> Path:
        """
        Helper: Create a temporary project directory with files and config.

        Args:
            files: Dict mapping filename to content
            config: Optional .reveal.yaml content

        Returns:
            Path to temp directory
        """
        import tempfile
        temp_dir = Path(tempfile.mkdtemp(prefix='reveal_test_i003_'))

        # Create .reveal.yaml if provided
        if config:
            config_path = temp_dir / '.reveal.yaml'
            with open(config_path, 'w') as f:
                f.write(config)

        # Create all files (supports nested paths)
        for filepath, content in files.items():
            file_path = temp_dir / filepath
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w') as f:
                f.write(content)

        return temp_dir

    def teardown_project(self, temp_dir: Path):
        """Helper: Clean up temp directory."""
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    def test_basic_layer_violation(self):
        """Test detection of basic layer violation (services importing from api)."""
        config = """
architecture:
  layers:
    - name: "services"
      paths: ["services/"]
      allow_imports: ["models/"]
      deny_imports: ["api/"]
"""
        files = {
            'services/user_service.py': """
from api import routes

def get_user():
    pass
""",
            'api/routes.py': """
def api_route():
    pass
""",
            'models/user.py': """
class User:
    pass
"""
        }

        temp_dir = self.create_temp_project(files, config)
        try:
            from reveal.rules.imports.I003 import I003
            rule = I003()

            # Check user_service.py - should detect violation
            file_path = str(temp_dir / 'services/user_service.py')
            content = files['services/user_service.py']
            detections = rule.check(file_path, None, content)

            self.assertGreater(len(detections), 0, "Should detect layer violation")
            self.assertEqual(detections[0].rule_code, 'I003')
            self.assertIn('services', detections[0].message.lower())

        finally:
            self.teardown_project(temp_dir)

    def test_allowed_import(self):
        """Test that allowed imports don't trigger violations."""
        config = """
architecture:
  layers:
    - name: "services"
      paths: ["services/"]
      allow_imports: ["repositories/", "models/"]
      deny_imports: []
"""
        files = {
            'services/user_service.py': """
from repositories import user_repo
from models import user

def get_user():
    pass
""",
            'repositories/user_repo.py': """
def find_user():
    pass
""",
            'models/user.py': """
class User:
    pass
"""
        }

        temp_dir = self.create_temp_project(files, config)
        try:
            from reveal.rules.imports.I003 import I003
            rule = I003()

            file_path = str(temp_dir / 'services/user_service.py')
            content = files['services/user_service.py']
            detections = rule.check(file_path, None, content)

            # Should not detect any violations
            self.assertEqual(len(detections), 0, "Allowed imports should not trigger violations")

        finally:
            self.teardown_project(temp_dir)

    def test_multiple_layers(self):
        """Test project with multiple layers enforcing different rules."""
        config = """
architecture:
  layers:
    - name: "api"
      paths: ["api/"]
      allow_imports: ["services/", "models/"]
      deny_imports: ["repositories/", "database/"]

    - name: "services"
      paths: ["services/"]
      allow_imports: ["repositories/", "models/"]
      deny_imports: ["api/"]

    - name: "repositories"
      paths: ["repositories/"]
      allow_imports: ["database/", "models/"]
      deny_imports: ["api/", "services/"]
"""
        files = {
            'api/routes.py': """
from services import user_service

def handle_request():
    pass
""",
            'services/user_service.py': """
from repositories import user_repo

def get_user():
    pass
""",
            'repositories/user_repo.py': """
from database import db

def find_user():
    pass
""",
            'database/db.py': """
def connect():
    pass
""",
            'models/user.py': """
class User:
    pass
"""
        }

        temp_dir = self.create_temp_project(files, config)
        try:
            from reveal.rules.imports.I003 import I003
            rule = I003()

            # All files should pass (no violations)
            for filepath in files.keys():
                if filepath.endswith('.py'):
                    file_path = str(temp_dir / filepath)
                    content = files[filepath]
                    detections = rule.check(file_path, None, content)
                    self.assertEqual(len(detections), 0,
                                   f"No violations expected in {filepath}")

        finally:
            self.teardown_project(temp_dir)

    def test_deny_list_violation(self):
        """Test that deny_imports are properly enforced."""
        config = """
architecture:
  layers:
    - name: "repositories"
      paths: ["repositories/"]
      allow_imports: ["database/"]
      deny_imports: ["api/", "services/"]
"""
        files = {
            'repositories/user_repo.py': """
from services import user_service

def find_user():
    pass
""",
            'services/user_service.py': """
def get_user():
    pass
"""
        }

        temp_dir = self.create_temp_project(files, config)
        try:
            from reveal.rules.imports.I003 import I003
            rule = I003()

            file_path = str(temp_dir / 'repositories/user_repo.py')
            content = files['repositories/user_repo.py']
            detections = rule.check(file_path, None, content)

            self.assertGreater(len(detections), 0, "Should detect deny_imports violation")
            self.assertEqual(detections[0].rule_code, 'I003')

        finally:
            self.teardown_project(temp_dir)

    def test_no_config_no_violations(self):
        """Test that files without .reveal.yaml don't trigger violations."""
        files = {
            'module_a.py': """
import module_b

def func_a():
    pass
""",
            'module_b.py': """
def func_b():
    pass
"""
        }

        temp_dir = self.create_temp_project(files, config=None)
        try:
            from reveal.rules.imports.I003 import I003
            rule = I003()

            file_path = str(temp_dir / 'module_a.py')
            content = files['module_a.py']
            detections = rule.check(file_path, None, content)

            # No config = no violations
            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_project(temp_dir)

    def test_external_imports_ignored(self):
        """Test that external/stdlib imports are ignored."""
        config = """
architecture:
  layers:
    - name: "services"
      paths: ["services/"]
      allow_imports: ["repositories/"]
      deny_imports: []
"""
        files = {
            'services/user_service.py': """
import os
import sys
from pathlib import Path
import requests

def get_user():
    pass
"""
        }

        temp_dir = self.create_temp_project(files, config)
        try:
            from reveal.rules.imports.I003 import I003
            rule = I003()

            file_path = str(temp_dir / 'services/user_service.py')
            content = files['services/user_service.py']
            detections = rule.check(file_path, None, content)

            # External/stdlib imports should be ignored
            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_project(temp_dir)

    def test_glob_pattern_matching(self):
        """Test that glob patterns (** wildcards) work correctly."""
        config = """
architecture:
  layers:
    - name: "api"
      paths: ["api/**"]
      allow_imports: ["services/"]
      deny_imports: ["database/"]
"""
        files = {
            'api/v1/users/routes.py': """
from database import db

def get_users():
    pass
""",
            'database/db.py': """
def connect():
    pass
"""
        }

        temp_dir = self.create_temp_project(files, config)
        try:
            from reveal.rules.imports.I003 import I003
            rule = I003()

            # Nested file should still match api layer
            file_path = str(temp_dir / 'api/v1/users/routes.py')
            content = files['api/v1/users/routes.py']
            detections = rule.check(file_path, None, content)

            self.assertGreater(len(detections), 0,
                             "Should detect violation in nested file matching glob pattern")

        finally:
            self.teardown_project(temp_dir)

    def test_file_outside_layers(self):
        """Test that files not in any layer don't trigger violations."""
        config = """
architecture:
  layers:
    - name: "services"
      paths: ["services/"]
      allow_imports: ["models/"]
      deny_imports: []
"""
        files = {
            'util.py': """
from services import user_service

def helper():
    pass
""",
            'services/user_service.py': """
def get_user():
    pass
"""
        }

        temp_dir = self.create_temp_project(files, config)
        try:
            from reveal.rules.imports.I003 import I003
            rule = I003()

            # util.py is not in any layer, so no violations
            file_path = str(temp_dir / 'util.py')
            content = files['util.py']
            detections = rule.check(file_path, None, content)

            self.assertEqual(len(detections), 0,
                           "Files outside defined layers should not trigger violations")

        finally:
            self.teardown_project(temp_dir)

    def test_syntax_error_handling(self):
        """Test graceful handling of syntax errors."""
        config = """
architecture:
  layers:
    - name: "services"
      paths: ["services/"]
      allow_imports: ["models/"]
      deny_imports: []
"""
        files = {
            'services/broken.py': """
import this is not valid python syntax
"""
        }

        temp_dir = self.create_temp_project(files, config)
        try:
            from reveal.rules.imports.I003 import I003
            rule = I003()

            file_path = str(temp_dir / 'services/broken.py')
            content = files['services/broken.py']
            detections = rule.check(file_path, None, content)

            # Should handle gracefully without crashing
            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_project(temp_dir)


class TestI004StdlibShadowing(unittest.TestCase):
    """Test I004: Standard library shadowing detector."""

    def create_temp_python(self, filename: str, content: str) -> str:
        """Helper: Create temp Python file with specific name."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, filename)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def teardown_file(self, path: str):
        """Helper: Clean up temp file."""
        os.unlink(path)
        os.rmdir(os.path.dirname(path))

    def test_logging_py_shadows_stdlib(self):
        """Test that logging.py is detected as shadowing stdlib."""
        from reveal.rules.imports.I004 import I004

        content = "import logging\n\nlogger = logging.getLogger(__name__)\n"
        path = self.create_temp_python("logging.py", content)
        try:
            rule = I004()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].rule_code, 'I004')
            self.assertIn('shadows', detections[0].context.lower())
            self.assertIn('logging', detections[0].context)

        finally:
            self.teardown_file(path)

    def test_json_py_shadows_stdlib(self):
        """Test that json.py is detected as shadowing stdlib."""
        from reveal.rules.imports.I004 import I004

        content = "# Custom JSON utilities\n"
        path = self.create_temp_python("json.py", content)
        try:
            rule = I004()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].rule_code, 'I004')

        finally:
            self.teardown_file(path)

    def test_types_py_shadows_stdlib(self):
        """Test that types.py is detected as shadowing stdlib."""
        from reveal.rules.imports.I004 import I004

        content = "# Type definitions\n"
        path = self.create_temp_python("types.py", content)
        try:
            rule = I004()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 1)
            self.assertIn('types', detections[0].context)

        finally:
            self.teardown_file(path)

    def test_non_stdlib_name_ok(self):
        """Test that non-stdlib names don't trigger detection."""
        from reveal.rules.imports.I004 import I004

        content = "# My utilities\n"
        path = self.create_temp_python("my_utils.py", content)
        try:
            rule = I004()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)

    def test_test_file_allowed(self):
        """Test that test files are allowed to shadow (test_logging.py)."""
        from reveal.rules.imports.I004 import I004

        content = "# Tests for logging\n"
        path = self.create_temp_python("test_logging.py", content)
        try:
            rule = I004()
            detections = rule.check(path, None, content)

            # Test files should be allowed
            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)

    def test_test_suffix_allowed(self):
        """Test that _test suffix files are allowed (logging_test.py)."""
        from reveal.rules.imports.I004 import I004

        content = "# Tests for logging\n"
        path = self.create_temp_python("logging_test.py", content)
        try:
            rule = I004()
            detections = rule.check(path, None, content)

            # Test suffix files should be allowed
            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)

    def test_noqa_comment_suppresses(self):
        """Test that # noqa: I004 suppresses detection."""
        from reveal.rules.imports.I004 import I004

        content = "# noqa: I004\nimport logging\n"
        path = self.create_temp_python("logging.py", content)
        try:
            rule = I004()
            detections = rule.check(path, None, content)

            # noqa should suppress
            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)

    def test_generic_noqa_suppresses(self):
        """Test that generic # noqa suppresses detection."""
        from reveal.rules.imports.I004 import I004

        content = "# noqa\nimport logging\n"
        path = self.create_temp_python("logging.py", content)
        try:
            rule = I004()
            detections = rule.check(path, None, content)

            # Generic noqa should suppress
            self.assertEqual(len(detections), 0)

        finally:
            self.teardown_file(path)

    def test_suggestion_includes_rename(self):
        """Test that detection includes rename suggestion."""
        from reveal.rules.imports.I004 import I004

        content = "# Custom logging\n"
        path = self.create_temp_python("logging.py", content)
        try:
            rule = I004()
            detections = rule.check(path, None, content)

            self.assertEqual(len(detections), 1)
            self.assertIsNotNone(detections[0].suggestion)
            self.assertIn('rename', detections[0].suggestion.lower())

        finally:
            self.teardown_file(path)

    def test_in_tests_directory_allowed(self):
        """Test that files in tests/ directory are allowed."""
        from reveal.rules.imports.I004 import I004

        temp_dir = tempfile.mkdtemp()
        tests_dir = os.path.join(temp_dir, "tests")
        os.makedirs(tests_dir)
        path = os.path.join(tests_dir, "logging.py")
        content = "# Test logging utilities\n"
        with open(path, 'w') as f:
            f.write(content)

        try:
            rule = I004()
            detections = rule.check(path, None, content)

            # Files in tests/ should be allowed
            self.assertEqual(len(detections), 0)

        finally:
            os.unlink(path)
            os.rmdir(tests_dir)
            os.rmdir(temp_dir)


if __name__ == '__main__':
    unittest.main()
