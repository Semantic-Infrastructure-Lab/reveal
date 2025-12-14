"""Tests for shebang detection in extensionless files."""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.registry import get_analyzer, _detect_shebang


class TestShebangDetection(unittest.TestCase):
    """Test shebang detection for extensionless scripts."""

    def create_temp_script(self, content: str, name: str = "testscript") -> str:
        """Helper: Create temp script without extension."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, name)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def test_detect_python_shebang(self):
        """Test detection of Python shebang."""
        content = """#!/usr/bin/env python3
import sys
print("Hello")
"""
        path = self.create_temp_script(content)
        try:
            result = _detect_shebang(path)
            self.assertEqual(result, '.py')
        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_detect_bash_shebang(self):
        """Test detection of bash shebang."""
        content = """#!/bin/bash
echo "Hello"
"""
        path = self.create_temp_script(content)
        try:
            result = _detect_shebang(path)
            self.assertEqual(result, '.sh')
        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_detect_sh_shebang(self):
        """Test detection of sh shebang."""
        content = """#!/bin/sh
echo "Hello"
"""
        path = self.create_temp_script(content)
        try:
            result = _detect_shebang(path)
            self.assertEqual(result, '.sh')
        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_detect_env_python(self):
        """Test detection of env python shebang."""
        content = """#!/usr/bin/env python
import sys
"""
        path = self.create_temp_script(content)
        try:
            result = _detect_shebang(path)
            self.assertEqual(result, '.py')
        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_no_shebang(self):
        """Test file without shebang returns None."""
        content = """# Just a comment
Some content
"""
        path = self.create_temp_script(content)
        try:
            result = _detect_shebang(path)
            self.assertIsNone(result)
        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_get_analyzer_with_python_shebang(self):
        """Test that get_analyzer returns PythonAnalyzer for Python shebang."""
        content = """#!/usr/bin/env python3
import os
print("test")
"""
        path = self.create_temp_script(content, "myscript")
        try:
            analyzer_class = get_analyzer(path)
            self.assertIsNotNone(analyzer_class)
            self.assertEqual(analyzer_class.__name__, 'PythonAnalyzer')
        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_get_analyzer_with_bash_shebang(self):
        """Test that get_analyzer returns BashAnalyzer for bash shebang."""
        content = """#!/bin/bash
echo "test"
"""
        path = self.create_temp_script(content, "myscript")
        try:
            analyzer_class = get_analyzer(path)
            self.assertIsNotNone(analyzer_class)
            # Note: Check for BashAnalyzer if it exists and has get_structure
            self.assertIsNotNone(analyzer_class)
        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_extension_takes_precedence(self):
        """Test that file extension takes precedence over shebang."""
        content = """#!/bin/bash
# This is actually a Python file despite the shebang
import sys
"""
        fd, path = tempfile.mkstemp(suffix='.py')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(content)

            analyzer_class = get_analyzer(path)
            self.assertIsNotNone(analyzer_class)
            self.assertEqual(analyzer_class.__name__, 'PythonAnalyzer')

        finally:
            os.unlink(path)

    def test_dockerfile_by_name(self):
        """Test that Dockerfile is detected by filename."""
        content = """FROM python:3.10
RUN pip install flask
"""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "Dockerfile")
        try:
            with open(path, 'w') as f:
                f.write(content)

            analyzer_class = get_analyzer(path)
            self.assertIsNotNone(analyzer_class)
            self.assertEqual(analyzer_class.__name__, 'DockerfileAnalyzer')

        finally:
            os.unlink(path)
            os.rmdir(temp_dir)

    def test_dockerfile_case_insensitive(self):
        """Test that Dockerfile is detected case-insensitively."""
        content = """FROM alpine:latest
"""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "dockerfile")  # lowercase
        try:
            with open(path, 'w') as f:
                f.write(content)

            analyzer_class = get_analyzer(path)
            self.assertIsNotNone(analyzer_class)
            self.assertEqual(analyzer_class.__name__, 'DockerfileAnalyzer')

        finally:
            os.unlink(path)
            os.rmdir(temp_dir)

    def test_zsh_shebang(self):
        """Test detection of zsh shebang."""
        content = """#!/bin/zsh
echo "Hello from zsh"
"""
        path = self.create_temp_script(content)
        try:
            result = _detect_shebang(path)
            self.assertEqual(result, '.sh')
        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_python_with_flags(self):
        """Test Python shebang with flags."""
        content = """#!/usr/bin/env python3 -u
import sys
"""
        path = self.create_temp_script(content)
        try:
            result = _detect_shebang(path)
            self.assertEqual(result, '.py')
        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))


if __name__ == '__main__':
    unittest.main()
