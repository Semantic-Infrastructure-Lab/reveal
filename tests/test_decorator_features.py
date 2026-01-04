"""Tests for decorator-related features (B002, B003, AST queries, --filter, --decorator-stats)."""

import pytest
import tempfile
import os
from pathlib import Path


class TestB002StaticmethodWithSelf:
    """Tests for B002: @staticmethod with self parameter."""

    def test_detects_staticmethod_with_self(self):
        """B002 should detect @staticmethod methods that have self parameter."""
        from reveal.rules.bugs.B002 import B002

        code = '''
class Example:
    @staticmethod
    def bad_method(self, x):
        return x
'''
        rule = B002()
        # Create structure with decorators
        structure = {
            'functions': [
                {
                    'name': 'bad_method',
                    'decorators': ['@staticmethod'],
                    'signature': '(self, x)',
                    'line': 3
                }
            ]
        }

        detections = rule.check('test.py', structure, code)
        assert len(detections) == 1
        assert 'self' in detections[0].message

    def test_ignores_staticmethod_without_self(self):
        """B002 should not flag @staticmethod methods without self."""
        from reveal.rules.bugs.B002 import B002

        code = '''
class Example:
    @staticmethod
    def good_method(x, y):
        return x + y
'''
        rule = B002()
        structure = {
            'functions': [
                {
                    'name': 'good_method',
                    'decorators': ['@staticmethod'],
                    'signature': '(x, y)',
                    'line': 3
                }
            ]
        }

        detections = rule.check('test.py', structure, code)
        assert len(detections) == 0

    def test_ignores_regular_method_with_self(self):
        """B002 should not flag regular methods with self."""
        from reveal.rules.bugs.B002 import B002

        rule = B002()
        structure = {
            'functions': [
                {
                    'name': 'regular_method',
                    'decorators': [],
                    'signature': '(self, x)',
                    'line': 3
                }
            ]
        }

        detections = rule.check('test.py', structure, '')
        assert len(detections) == 0


class TestB004PropertyWithoutReturn:
    """Tests for B004: @property without return statement."""

    def test_detects_property_without_return(self):
        """B004 should detect @property methods missing return statement."""
        from reveal.rules.bugs.B004 import B004

        code = '''class Example:
    @property
    def broken(self):
        x = self._value * 2
        # Forgot to return!
'''
        rule = B004()
        structure = {
            'functions': [
                {
                    'name': 'broken',
                    'decorators': ['@property'],
                    'line': 2,
                    'line_count': 4
                }
            ]
        }

        detections = rule.check('test.py', structure, code)
        assert len(detections) == 1
        assert 'no return' in detections[0].message

    def test_ignores_property_with_return(self):
        """B004 should not flag @property methods with return."""
        from reveal.rules.bugs.B004 import B004

        code = '''class Example:
    @property
    def working(self):
        return self._value
'''
        rule = B004()
        structure = {
            'functions': [
                {
                    'name': 'working',
                    'decorators': ['@property'],
                    'line': 2,
                    'line_count': 3
                }
            ]
        }

        detections = rule.check('test.py', structure, code)
        assert len(detections) == 0

    def test_ignores_property_with_raise(self):
        """B004 should not flag @property methods that raise."""
        from reveal.rules.bugs.B004 import B004

        code = '''class Example:
    @property
    def not_implemented(self):
        raise NotImplementedError("Subclass must implement")
'''
        rule = B004()
        structure = {
            'functions': [
                {
                    'name': 'not_implemented',
                    'decorators': ['@property'],
                    'line': 2,
                    'line_count': 3
                }
            ]
        }

        detections = rule.check('test.py', structure, code)
        assert len(detections) == 0

    def test_ignores_abstract_property(self):
        """B004 should not flag abstract properties."""
        from reveal.rules.bugs.B004 import B004

        code = '''class Example:
    @property
    @abstractmethod
    def abstract_prop(self):
        pass
'''
        rule = B004()
        structure = {
            'functions': [
                {
                    'name': 'abstract_prop',
                    'decorators': ['@property', '@abstractmethod'],
                    'line': 2,
                    'line_count': 4
                }
            ]
        }

        detections = rule.check('test.py', structure, code)
        assert len(detections) == 0

    def test_ignores_return_in_docstring(self):
        """B004 should not be fooled by 'return' in docstrings."""
        from reveal.rules.bugs.B004 import B004

        code = '''class Example:
    @property
    def broken_with_docstring(self):
        """This will return the value."""
        x = self._value
'''
        rule = B004()
        structure = {
            'functions': [
                {
                    'name': 'broken_with_docstring',
                    'decorators': ['@property'],
                    'line': 2,
                    'line_count': 4
                }
            ]
        }

        detections = rule.check('test.py', structure, code)
        assert len(detections) == 1  # Should still detect - 'return' in docstring doesn't count


class TestB003ComplexProperty:
    """Tests for B003: Complex @property detection."""

    def test_detects_complex_property(self):
        """B003 should detect @property methods that are too long."""
        from reveal.rules.bugs.B003 import B003

        rule = B003()
        structure = {
            'functions': [
                {
                    'name': 'complex_prop',
                    'decorators': ['@property'],
                    'line': 1,
                    'line_count': 15  # Over threshold
                }
            ]
        }

        detections = rule.check('test.py', structure, '')
        assert len(detections) == 1
        assert '15 lines' in detections[0].message

    def test_ignores_simple_property(self):
        """B003 should not flag simple properties."""
        from reveal.rules.bugs.B003 import B003

        rule = B003()
        structure = {
            'functions': [
                {
                    'name': 'simple_prop',
                    'decorators': ['@property'],
                    'line': 1,
                    'line_count': 3
                }
            ]
        }

        detections = rule.check('test.py', structure, '')
        assert len(detections) == 0


class TestASTDecoratorQuery:
    """Tests for AST decorator query functionality."""

    def test_decorator_filter_exact_match(self):
        """AST adapter should filter by exact decorator match."""
        from reveal.adapters.ast import AstAdapter

        adapter = AstAdapter('.', 'decorator=property')
        assert adapter.query['decorator']['op'] == '=='
        assert adapter.query['decorator']['value'] == 'property'

    def test_decorator_filter_wildcard(self):
        """AST adapter should support wildcard decorator matching."""
        from reveal.adapters.ast import AstAdapter

        adapter = AstAdapter('.', 'decorator=*cache*')
        assert adapter.query['decorator']['op'] == 'glob'
        assert adapter.query['decorator']['value'] == '*cache*'

    def test_matches_decorator_exact(self):
        """_matches_decorator should match exact decorators."""
        from reveal.adapters.ast import AstAdapter

        adapter = AstAdapter('.', '')
        adapter.query = {}

        # Test exact match
        condition = {'op': '==', 'value': 'property'}
        assert adapter._matches_decorator(['@property'], condition) is True
        assert adapter._matches_decorator(['@staticmethod'], condition) is False

    def test_matches_decorator_wildcard(self):
        """_matches_decorator should support wildcards."""
        from reveal.adapters.ast import AstAdapter

        adapter = AstAdapter('.', '')
        adapter.query = {}

        condition = {'op': 'glob', 'value': '*cache*'}
        assert adapter._matches_decorator(['@lru_cache(maxsize=100)'], condition) is True
        assert adapter._matches_decorator(['@cached_property'], condition) is True
        assert adapter._matches_decorator(['@property'], condition) is False


class TestTypedFilter:
    """Tests for --filter flag in typed output."""

    def test_filter_flag_parsed(self):
        """Parser should accept --filter flag."""
        from reveal.cli.parser import create_argument_parser

        parser = create_argument_parser('0.0.0')
        args = parser.parse_args(['test.py', '--typed', '--filter', 'property'])

        assert args.typed is True
        assert args.filter == 'property'


class TestDecoratorStats:
    """Tests for --decorator-stats command."""

    def test_decorator_stats_handler_exists(self):
        """handle_decorator_stats should be importable."""
        from reveal.cli.handlers import handle_decorator_stats
        assert callable(handle_decorator_stats)

    def test_decorator_stats_counts_decorators(self, tmp_path):
        """--decorator-stats should count decorators correctly."""
        # Create test file with decorators
        test_file = tmp_path / "test_decorators.py"
        test_file.write_text('''
class Example:
    @property
    def name(self):
        return self._name

    @staticmethod
    def helper():
        pass

    @property
    def value(self):
        return self._value
''')

        # Run decorator stats via CLI - use reveal command directly
        import subprocess
        result = subprocess.run(
            ['reveal', str(tmp_path), '--decorator-stats'],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )

        assert '@property' in result.stdout
        assert '@staticmethod' in result.stdout
        assert '2 occurrences' in result.stdout or '2 occurence' in result.stdout  # @property appears twice
