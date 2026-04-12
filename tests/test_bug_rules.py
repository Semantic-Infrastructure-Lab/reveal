"""Comprehensive tests for bug detection rules.

Tests B001 (bare except), B002 (@staticmethod with self), B003 (oversized @property),
B004 (@property without return).
"""

import pytest
from reveal.rules.bugs.B001 import B001
from reveal.rules.bugs.B002 import B002
from reveal.rules.bugs.B003 import B003
from reveal.rules.bugs.B004 import B004


class TestB001:
    """Test B001: Bare except clause detection."""

    def test_b001_initialization(self):
        """B001 rule initializes correctly."""
        rule = B001()
        assert rule.code == "B001"
        assert "bare except" in rule.message.lower() or "except:" in rule.message.lower()
        assert '.py' in rule.file_patterns[0]  # Python-specific rule

    def test_b001_detects_bare_except(self):
        """B001 detects bare except clauses."""
        rule = B001()
        content = """
try:
    risky_operation()
except:  # Bare except - BAD!
    pass
"""
        detections = rule.check("test.py", None, content)
        assert len(detections) >= 1
        assert any("except" in d.message.lower() for d in detections)

    def test_b001_allows_specific_exceptions(self):
        """B001 doesn't flag specific exception handlers."""
        rule = B001()
        content = """
try:
    risky_operation()
except ValueError:  # Specific exception - OK
    pass
except (TypeError, KeyError):  # Multiple specific - OK
    pass
"""
        detections = rule.check("test.py", None, content)
        assert len(detections) == 0

    def test_b001_allows_except_exception(self):
        """B001 allows 'except Exception:' as it's explicit."""
        rule = B001()
        content = """
try:
    risky_operation()
except Exception:  # Explicit Exception - typically OK
    log_error()
"""
        detections = rule.check("test.py", None, content)
        assert len(detections) == 0

    def test_b001_multiple_violations(self):
        """B001 detects multiple bare except clauses."""
        rule = B001()
        content = """
try:
    op1()
except:
    pass

try:
    op2()
except:
    pass
"""
        detections = rule.check("test.py", None, content)
        assert len(detections) >= 2


class TestB002:
    """Test B002: @staticmethod with self parameter detection."""

    def test_b002_detects_staticmethod_with_self(self):
        """B002 detects @staticmethod methods that still declare self."""
        rule = B002()
        structure = {
            'functions': [{
                'name': 'bad_static',
                'line': 2,
                'decorators': ['@staticmethod'],
                'signature': '(self, x)',
            }]
        }
        content = "@staticmethod\ndef bad_static(self, x):\n    return x\n"
        detections = rule.check("test.py", structure, content)
        assert len(detections) >= 1
        assert any("bad_static" in d.message for d in detections)

    def test_b002_allows_staticmethod_without_self(self):
        """B002 allows @staticmethod with no self parameter."""
        rule = B002()
        structure = {
            'functions': [{
                'name': 'good_static',
                'line': 2,
                'decorators': ['@staticmethod'],
                'signature': '(x, y)',
            }]
        }
        content = "@staticmethod\ndef good_static(x, y):\n    return x + y\n"
        detections = rule.check("test.py", structure, content)
        assert len(detections) == 0

    def test_b002_allows_regular_method_with_self(self):
        """B002 does not flag regular (non-static) instance methods."""
        rule = B002()
        structure = {
            'functions': [{
                'name': 'instance_method',
                'line': 2,
                'decorators': [],
                'signature': '(self, x)',
            }]
        }
        content = "def instance_method(self, x):\n    return x\n"
        detections = rule.check("test.py", structure, content)
        assert len(detections) == 0

    def test_b002_no_structure_returns_empty(self):
        """B002 requires structure to detect — returns no detections when structure is None."""
        rule = B002()
        detections = rule.check("test.py", None, "any content")
        assert len(detections) == 0


class TestB003:
    """Test B003: Oversized @property detection."""

    def test_b003_detects_oversized_property(self):
        """B003 detects a @property whose line count exceeds the threshold."""
        rule = B003()
        structure = {
            'functions': [{
                'name': 'big_prop',
                'line': 2,
                'line_count': 20,  # well above MAX_PROPERTY_LINES (8)
                'decorators': ['@property'],
            }]
        }
        content = "@property\ndef big_prop(self):\n" + "    x = 1\n" * 20
        detections = rule.check("test.py", structure, content)
        assert len(detections) >= 1
        assert any("big_prop" in d.message for d in detections)

    def test_b003_allows_short_property(self):
        """B003 allows a @property within the line limit."""
        rule = B003()
        structure = {
            'functions': [{
                'name': 'name',
                'line': 2,
                'line_count': 3,
                'decorators': ['@property'],
            }]
        }
        content = "@property\ndef name(self):\n    return self._name\n"
        detections = rule.check("test.py", structure, content)
        assert len(detections) == 0

    def test_b003_allows_cached_property(self):
        """B003 skips @cached_property even when oversized."""
        rule = B003()
        structure = {
            'functions': [{
                'name': 'expensive',
                'line': 2,
                'line_count': 30,
                'decorators': ['@cached_property'],
            }]
        }
        content = "@cached_property\ndef expensive(self):\n" + "    x = 1\n" * 30
        detections = rule.check("test.py", structure, content)
        assert len(detections) == 0

    def test_b003_no_structure_returns_empty(self):
        """B003 requires structure to detect — returns no detections when structure is None."""
        rule = B003()
        detections = rule.check("test.py", None, "any content")
        assert len(detections) == 0


class TestB004:
    """Test B004: @property without return statement detection."""

    def test_b004_detects_property_without_return(self):
        """B004 detects a @property that never returns (will silently return None)."""
        rule = B004()
        structure = {
            'functions': [{
                'name': 'broken_prop',
                'line': 2,
                'line_count': 3,
                'decorators': ['@property'],
            }]
        }
        content = "@property\ndef broken_prop(self):\n    self.compute()\n"
        detections = rule.check("test.py", structure, content)
        assert len(detections) >= 1
        assert any("broken_prop" in d.message for d in detections)

    def test_b004_allows_property_with_return(self):
        """B004 does not flag a @property that has a return statement."""
        rule = B004()
        structure = {
            'functions': [{
                'name': 'value',
                'line': 2,
                'line_count': 3,
                'decorators': ['@property'],
            }]
        }
        content = "@property\ndef value(self):\n    return self._value\n"
        detections = rule.check("test.py", structure, content)
        assert len(detections) == 0

    def test_b004_allows_property_that_raises(self):
        """B004 does not flag a @property that raises (raise is a valid implementation)."""
        rule = B004()
        structure = {
            'functions': [{
                'name': 'abstract_prop',
                'line': 2,
                'line_count': 3,
                'decorators': ['@property'],
            }]
        }
        content = "@property\ndef abstract_prop(self):\n    raise NotImplementedError\n"
        detections = rule.check("test.py", structure, content)
        assert len(detections) == 0

    def test_b004_no_structure_returns_empty(self):
        """B004 requires structure to detect — returns no detections when structure is None."""
        rule = B004()
        detections = rule.check("test.py", None, "")
        assert len(detections) == 0
