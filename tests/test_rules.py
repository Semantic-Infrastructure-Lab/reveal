"""Tests for reveal quality rules."""

import unittest
import tempfile
import os
from reveal.rules.bugs.B001 import B001
from reveal.rules.complexity.C901 import C901
from reveal.rules.refactoring.R913 import R913
from reveal.rules.security.S701 import S701


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
        """Test that complex functions are detected."""
        # Create a very complex function that exceeds threshold of 10
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
        structure = {'functions': [{'name': 'complex_func', 'line': 1, 'end_line': 14}]}
        detections = rule.check('test.py', structure, content)

        self.assertEqual(len(detections), 1)
        self.assertIn('complexity', detections[0].message.lower())

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
        """Test that the threshold is 10."""
        rule = C901()
        self.assertEqual(rule.THRESHOLD, 10)


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


if __name__ == '__main__':
    unittest.main()
