"""Tests for _extract_relationships() wiring — BACK-112.

Covers:
- TreeSitterAnalyzer._extract_relationships(): intra-file call edge extraction
- _render_json_output(): 'relationships' key present when non-empty, absent when empty
"""

import json
import pytest
from io import StringIO
from unittest.mock import MagicMock, patch

from reveal.treesitter import TreeSitterAnalyzer
from reveal.display.structure import _render_json_output


# ─── TreeSitterAnalyzer._extract_relationships ──────────────────────────────

class TestExtractRelationships:
    """Unit tests for TreeSitterAnalyzer._extract_relationships()."""

    def _make_analyzer(self):
        """Return a TreeSitterAnalyzer subclass instance with no real file."""
        class StubAnalyzer(TreeSitterAnalyzer):
            type_name = 'stub'
            language = 'python'
            extensions = ['.stub']
            def get_structure(self, **kwargs):
                return {}

        a = StubAnalyzer.__new__(StubAnalyzer)
        a.tree = None
        return a

    def test_empty_structure_returns_empty(self):
        a = self._make_analyzer()
        assert a._extract_relationships({}) == {}

    def test_no_calls_returns_empty(self):
        a = self._make_analyzer()
        structure = {
            'functions': [{'name': 'foo', 'line': 1, 'calls': []}],
        }
        assert a._extract_relationships(structure) == {}

    def test_single_call_edge(self):
        a = self._make_analyzer()
        structure = {
            'functions': [{'name': 'foo', 'line': 5, 'calls': ['bar']}],
        }
        result = a._extract_relationships(structure)
        assert result == {'calls': [{'from': 'foo', 'from_line': 5, 'to': 'bar'}]}

    def test_multiple_callees(self):
        a = self._make_analyzer()
        structure = {
            'functions': [{'name': 'main', 'line': 1, 'calls': ['parse', 'run', 'cleanup']}],
        }
        result = a._extract_relationships(structure)
        assert len(result['calls']) == 3
        froms = {e['from'] for e in result['calls']}
        tos = {e['to'] for e in result['calls']}
        assert froms == {'main'}
        assert tos == {'parse', 'run', 'cleanup'}

    def test_multiple_functions(self):
        a = self._make_analyzer()
        structure = {
            'functions': [
                {'name': 'a', 'line': 1, 'calls': ['b']},
                {'name': 'b', 'line': 10, 'calls': ['c', 'd']},
            ],
        }
        result = a._extract_relationships(structure)
        assert len(result['calls']) == 3
        assert {'from': 'a', 'from_line': 1, 'to': 'b'} in result['calls']
        assert {'from': 'b', 'from_line': 10, 'to': 'c'} in result['calls']
        assert {'from': 'b', 'from_line': 10, 'to': 'd'} in result['calls']

    def test_methods_category_included(self):
        a = self._make_analyzer()
        structure = {
            'methods': [{'name': 'validate', 'line': 20, 'calls': ['_check']}],
        }
        result = a._extract_relationships(structure)
        assert result == {'calls': [{'from': 'validate', 'from_line': 20, 'to': '_check'}]}

    def test_functions_and_methods_combined(self):
        a = self._make_analyzer()
        structure = {
            'functions': [{'name': 'run', 'line': 1, 'calls': ['helper']}],
            'methods': [{'name': 'execute', 'line': 50, 'calls': ['run']}],
        }
        result = a._extract_relationships(structure)
        assert len(result['calls']) == 2

    def test_attribute_call_preserved(self):
        """Callee names like 'self.validate' or 'json.dumps' are included as-is."""
        a = self._make_analyzer()
        structure = {
            'functions': [{'name': 'process', 'line': 5, 'calls': ['self.validate', 'json.dumps']}],
        }
        result = a._extract_relationships(structure)
        tos = {e['to'] for e in result['calls']}
        assert 'self.validate' in tos
        assert 'json.dumps' in tos

    def test_empty_callee_name_skipped(self):
        a = self._make_analyzer()
        structure = {
            'functions': [{'name': 'foo', 'line': 1, 'calls': ['', 'bar', '']}],
        }
        result = a._extract_relationships(structure)
        assert len(result['calls']) == 1
        assert result['calls'][0]['to'] == 'bar'

    def test_unnamed_function_skipped(self):
        a = self._make_analyzer()
        structure = {
            'functions': [{'name': '', 'line': 1, 'calls': ['bar']}],
        }
        assert a._extract_relationships(structure) == {}

    def test_missing_calls_key_skipped(self):
        a = self._make_analyzer()
        structure = {
            'functions': [{'name': 'foo', 'line': 1}],  # no 'calls' key
        }
        assert a._extract_relationships(structure) == {}

    def test_non_code_categories_ignored(self):
        """imports, classes, etc. should not contribute edges."""
        a = self._make_analyzer()
        structure = {
            'imports': [{'content': 'import os', 'line': 1}],
            'classes': [{'name': 'MyClass', 'line': 5}],
        }
        assert a._extract_relationships(structure) == {}


# ─── _render_json_output wiring ─────────────────────────────────────────────

class TestRenderJsonOutputRelationships:
    """Verify 'relationships' appears in JSON output iff _extract_relationships is non-empty."""

    def _make_analyzer(self, relationships=None):
        a = MagicMock()
        a.path = '/tmp/test.py'
        a.is_fallback = False
        a.fallback_language = None
        a.__class__.__name__ = 'PythonAnalyzer'
        a._extract_relationships.return_value = relationships or {}
        return a

    def _run(self, analyzer, structure):
        out = StringIO()
        with patch('sys.stdout', out):
            _render_json_output(analyzer, structure)
        return json.loads(out.getvalue())

    def test_relationships_absent_when_empty(self):
        analyzer = self._make_analyzer(relationships={})
        result = self._run(analyzer, {'functions': []})
        assert 'relationships' not in result

    def test_relationships_present_when_non_empty(self):
        rels = {'calls': [{'from': 'foo', 'from_line': 1, 'to': 'bar'}]}
        analyzer = self._make_analyzer(relationships=rels)
        result = self._run(analyzer, {'functions': [{'name': 'foo', 'line': 1, 'calls': ['bar']}]})
        assert 'relationships' in result
        assert result['relationships'] == rels

    def test_relationships_calls_extract_relationships_with_structure(self):
        analyzer = self._make_analyzer()
        structure = {'functions': [{'name': 'x', 'line': 1}]}
        self._run(analyzer, structure)
        analyzer._extract_relationships.assert_called_once_with(structure)
