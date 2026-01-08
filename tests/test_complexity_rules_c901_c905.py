"""Comprehensive tests for complexity detection rules.

Tests C901 (cyclomatic complexity), C902 (function length), and C905 (nesting depth).
"""

import pytest
from reveal.rules.complexity.C901 import C901
from reveal.rules.complexity.C902 import C902
from reveal.rules.complexity.C905 import C905


class TestC901:
    """Test C901: Cyclomatic complexity detection."""

    def test_c901_initialization(self):
        """C901 rule initializes correctly."""
        rule = C901()
        assert rule.code == "C901"
        assert rule.message == "Function is too complex"
        assert rule.file_patterns == ['*']  # Applies to all files

    def test_c901_simple_function(self):
        """C901 doesn't flag simple functions."""
        rule = C901()
        structure = {
            'functions': [{
                'name': 'simple_func',
                'line': 1,
                'complexity': 5
            }]
        }
        detections = rule.check("test.py", structure, "")
        assert len(detections) == 0

    def test_c901_complex_function(self):
        """C901 flags functions with high complexity."""
        rule = C901()
        structure = {
            'functions': [{
                'name': 'complex_func',
                'line': 10,
                'complexity': 25  # Above threshold
            }]
        }
        detections = rule.check("test.py", structure, "")
        assert len(detections) == 1
        assert detections[0].rule_code == "C901"
        assert detections[0].line == 10
        assert "complex_func" in detections[0].message or "25" in detections[0].message

    def test_c901_multiple_violations(self):
        """C901 can detect multiple complex functions."""
        rule = C901()
        structure = {
            'functions': [
                {'name': 'func1', 'line': 5, 'complexity': 30},
                {'name': 'func2', 'line': 15, 'complexity': 5},  # Below threshold
                {'name': 'func3', 'line': 25, 'complexity': 40},
            ]
        }
        detections = rule.check("test.py", structure, "")
        assert len(detections) == 2
        assert detections[0].line == 5
        assert detections[1].line == 25

    def test_c901_no_structure(self):
        """C901 handles missing structure gracefully."""
        rule = C901()
        detections = rule.check("test.py", None, "")
        assert len(detections) == 0

    def test_c901_no_functions(self):
        """C901 handles structure without functions."""
        rule = C901()
        structure = {'classes': []}  # No functions key
        detections = rule.check("test.py", structure, "")
        assert len(detections) == 0

    def test_c901_function_without_complexity(self):
        """C901 handles functions without complexity metric."""
        rule = C901()
        structure = {
            'functions': [{
                'name': 'func1',
                'line': 10
                # No complexity key
            }]
        }
        detections = rule.check("test.py", structure, "")
        assert len(detections) == 0


class TestC902:
    """Test C902: Function length detection."""

    def test_c902_initialization(self):
        """C902 rule initializes correctly."""
        rule = C902()
        assert rule.code == "C902"
        assert rule.message == "Function is too long"
        assert rule.file_patterns == ['*']  # Applies to all files

    def test_c902_short_function(self):
        """C902 doesn't flag short functions."""
        rule = C902()
        structure = {
            'functions': [{
                'name': 'short_func',
                'line': 1,
                'line_count': 30
            }]
        }
        detections = rule.check("test.py", structure, "")
        assert len(detections) == 0

    def test_c902_long_function(self):
        """C902 flags very long functions."""
        rule = C902()
        structure = {
            'functions': [{
                'name': 'long_func',
                'line': 10,
                'line_count': 150  # Above typical threshold
            }]
        }
        detections = rule.check("test.py", structure, "")
        assert len(detections) == 1
        assert detections[0].rule_code == "C902"
        assert detections[0].line == 10

    def test_c902_multiple_violations(self):
        """C902 detects multiple long functions."""
        rule = C902()
        structure = {
            'functions': [
                {'name': 'func1', 'line': 5, 'line_count': 200},
                {'name': 'func2', 'line': 300, 'line_count': 20},  # Short
                {'name': 'func3', 'line': 400, 'line_count': 180},
            ]
        }
        detections = rule.check("test.py", structure, "")
        assert len(detections) == 2

    def test_c902_no_structure(self):
        """C902 handles missing structure."""
        rule = C902()
        detections = rule.check("test.py", None, "")
        assert len(detections) == 0


class TestC905:
    """Test C905: Nesting depth detection."""

    def test_c905_initialization(self):
        """C905 rule initializes correctly."""
        rule = C905()
        assert rule.code == "C905"
        assert "nest" in rule.message.lower()
        assert rule.file_patterns == ['*']  # Applies to all files

    def test_c905_shallow_nesting(self):
        """C905 doesn't flag shallow nesting."""
        rule = C905()
        structure = {
            'functions': [{
                'name': 'func',
                'line': 1,
                'depth': 3
            }]
        }
        detections = rule.check("test.py", structure, "")
        assert len(detections) == 0

    def test_c905_deep_nesting(self):
        """C905 flags deeply nested code."""
        rule = C905()
        structure = {
            'functions': [{
                'name': 'nested_func',
                'line': 10,
                'depth': 8  # Very deep nesting
            }]
        }
        detections = rule.check("test.py", structure, "")
        assert len(detections) == 1
        assert detections[0].rule_code == "C905"
        assert detections[0].line == 10

    def test_c905_multiple_violations(self):
        """C905 detects multiple deeply nested functions."""
        rule = C905()
        structure = {
            'functions': [
                {'name': 'func1', 'line': 5, 'depth': 9},
                {'name': 'func2', 'line': 50, 'depth': 2},  # Shallow
                {'name': 'func3', 'line': 100, 'depth': 7},
            ]
        }
        detections = rule.check("test.py", structure, "")
        # Depending on threshold, may flag 1 or 2
        assert len(detections) >= 1

    def test_c905_no_structure(self):
        """C905 handles missing structure."""
        rule = C905()
        detections = rule.check("test.py", None, "")
        assert len(detections) == 0
