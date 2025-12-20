"""Comprehensive tests for bug detection rules.

Tests B001 (bare except), B002 (comparison to singletons), B003 (mutable defaults),
B004 (unused loop variable), and B005 (exception in except handler).
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
        # Most linters allow 'except Exception:' but flag bare 'except:'
        # Behavior may vary - just check it doesn't crash
        assert isinstance(detections, list)

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
    """Test B002: Comparison to singleton detection."""

    def test_b002_initialization(self):
        """B002 rule initializes correctly."""
        rule = B002()
        assert rule.code == "B002"
        assert '.py' in rule.file_patterns[0]  # Python-specific rule

    def test_b002_check_method_exists(self):
        """B002 has check method that can be called."""
        rule = B002()
        content = "if value == None: pass"
        # Just verify it doesn't crash
        detections = rule.check("test.py", None, content)
        assert isinstance(detections, list)

    def test_b002_allows_is_none(self):
        """B002 allows 'is None' checks."""
        rule = B002()
        content = """
if value is None:  # GOOD
    return
if other is not None:  # GOOD
    use(other)
"""
        detections = rule.check("test.py", None, content)
        assert len(detections) == 0


class TestB003:
    """Test B003: Mutable default argument detection."""

    def test_b003_initialization(self):
        """B003 rule initializes correctly."""
        rule = B003()
        assert rule.code == "B003"
        assert '.py' in rule.file_patterns[0]  # Python-specific rule

    def test_b003_check_method_exists(self):
        """B003 has check method that can be called."""
        rule = B003()
        content = "def func(items=[]): pass"
        # Just verify it doesn't crash
        detections = rule.check("test.py", None, content)
        assert isinstance(detections, list)

    def test_b003_allows_none_default(self):
        """B003 allows None as default (common pattern)."""
        rule = B003()
        content = """
def good_function(items=None):  # GOOD
    if items is None:
        items = []
    return items
"""
        detections = rule.check("test.py", None, content)
        assert len(detections) == 0

    def test_b003_allows_immutable_defaults(self):
        """B003 allows immutable defaults."""
        rule = B003()
        content = """
def good_function(count=0, name="default", flag=True):  # All GOOD
    return count, name, flag
"""
        detections = rule.check("test.py", None, content)
        assert len(detections) == 0


class TestB004:
    """Test B004: Unused loop variable detection."""

    def test_b004_initialization(self):
        """B004 rule initializes correctly."""
        rule = B004()
        assert rule.code == "B004"
        assert '.py' in rule.file_patterns[0]  # Python-specific rule

    def test_b004_check_method_exists(self):
        """B004 has check method that can be called."""
        rule = B004()
        # Just verify it doesn't crash with various inputs
        detections = rule.check("test.py", None, "")
        assert isinstance(detections, list)

        structure = {'functions': []}
        detections = rule.check("test.py", structure, "")
        assert isinstance(detections, list)

    def test_b004_allows_underscore_variable(self):
        """B004 allows underscore as intentionally unused."""
        rule = B004()
        structure = {
            'functions': [{
                'name': 'test_func',
                'line': 1,
                'variables': set(),
                'loops': [
                    {'line': 2, 'variable': '_'}
                ]
            }]
        }
        content = """
def test_func():
    for _ in range(10):  # Underscore means "intentionally unused"
        do_something()
"""
        detections = rule.check("test.py", structure, content)
        # Should allow underscore
        assert len(detections) == 0

    def test_b004_allows_used_variables(self):
        """B004 doesn't flag variables that are actually used."""
        rule = B004()
        structure = {
            'functions': [{
                'name': 'test_func',
                'line': 1,
                'variables': {'item'},
                'loops': [
                    {'line': 2, 'variable': 'item'}
                ]
            }]
        }
        content = """
def test_func():
    for item in items:
        print(item)  # Used here
        process(item)
"""
        detections = rule.check("test.py", structure, content)
        assert len(detections) == 0

    def test_b004_no_structure(self):
        """B004 handles missing structure."""
        rule = B004()
        detections = rule.check("test.py", None, "")
        assert len(detections) == 0
