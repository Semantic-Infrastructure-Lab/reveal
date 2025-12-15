"""Tests for reveal/structure.py - TypedStructure container.

Tests the core structure container that provides Pythonic navigation
and containment relationships for code analysis.
"""

import pytest
from reveal.structure import TypedStructure, _parse_import_name
from reveal.elements import TypedElement


class TestParseImportName:
    """Test import statement parsing."""

    def test_from_import(self):
        """'from X import Y' -> X"""
        assert _parse_import_name("from dataclasses import dataclass") == "dataclasses"
        assert _parse_import_name("from typing import Dict, List") == "typing"

    def test_simple_import(self):
        """'import X' -> X"""
        assert _parse_import_name("import os") == "os"
        assert _parse_import_name("import os.path") == "os.path"

    def test_import_as(self):
        """'import X as Y' -> X"""
        assert _parse_import_name("import numpy as np") == "numpy"
        assert _parse_import_name("import pandas as pd") == "pandas"

    def test_relative_import(self):
        """Relative imports"""
        assert _parse_import_name("from . import utils") == "."
        assert _parse_import_name("from ..core import base") == "..core"
        assert _parse_import_name("from .utils import helper") == ".utils"

    def test_empty_input(self):
        """Empty string returns empty"""
        assert _parse_import_name("") == ""
        assert _parse_import_name("   ") == ""

    def test_multiple_imports(self):
        """Multiple imports - returns first"""
        assert _parse_import_name("import os, sys, re") == "os"


class TestTypedStructureBasic:
    """Basic TypedStructure functionality."""

    def test_empty_structure(self):
        """Empty structure has no elements."""
        structure = TypedStructure(path="test.py", reveal_type=None, elements=[])
        assert len(structure) == 0
        assert not structure
        assert list(structure) == []

    def test_structure_with_elements(self):
        """Structure with elements is truthy and iterable."""
        el1 = TypedElement(name="func1", line=1, line_end=10, category="function")
        el2 = TypedElement(name="func2", line=12, line_end=20, category="function")
        structure = TypedStructure(path="test.py", reveal_type=None, elements=[el1, el2])

        assert len(structure) == 2
        assert structure
        assert list(structure) == [el1, el2]

    def test_post_init_wires_siblings(self):
        """__post_init__ sets _siblings on all elements."""
        el1 = TypedElement(name="func1", line=1, line_end=10, category="function")
        el2 = TypedElement(name="func2", line=12, line_end=20, category="function")
        structure = TypedStructure(path="test.py", reveal_type=None, elements=[el1, el2])

        assert el1._siblings == [el1, el2]
        assert el2._siblings == [el1, el2]


class TestTypedStructureCategoryAccessors:
    """Test category-based accessors."""

    @pytest.fixture
    def mixed_structure(self):
        """Structure with mixed element types."""
        elements = [
            TypedElement(name="helper", line=1, line_end=5, category="function"),
            TypedElement(name="MyClass", line=7, line_end=50, category="class"),
            TypedElement(name="process", line=10, line_end=20, category="method"),
            TypedElement(name="os", line=1, line_end=1, category="import"),
            TypedElement(name="sys", line=2, line_end=2, category="import"),
        ]
        return TypedStructure(path="test.py", reveal_type=None, elements=elements)

    def test_functions_accessor(self, mixed_structure):
        """functions property returns only functions."""
        funcs = mixed_structure.functions
        assert len(funcs) == 1
        assert funcs[0].name == "helper"

    def test_classes_accessor(self, mixed_structure):
        """classes property returns only classes."""
        classes = mixed_structure.classes
        assert len(classes) == 1
        assert classes[0].name == "MyClass"

    def test_imports_accessor(self, mixed_structure):
        """imports property returns only imports."""
        imports = mixed_structure.imports
        assert len(imports) == 2
        assert {i.name for i in imports} == {"os", "sys"}

    def test_by_category(self, mixed_structure):
        """by_category returns elements of specified category."""
        methods = mixed_structure.by_category("method")
        assert len(methods) == 1
        assert methods[0].name == "process"


class TestTypedStructureNavigation:
    """Test navigation operators."""

    @pytest.fixture
    def structure(self):
        """Simple structure for navigation tests."""
        elements = [
            TypedElement(name="top_func", line=1, line_end=10, category="function"),
            TypedElement(name="MyClass", line=15, line_end=50, category="class"),
        ]
        return TypedStructure(path="test.py", reveal_type=None, elements=elements)

    def test_truediv_finds_root(self, structure):
        """/ operator finds root element by name."""
        result = structure / "MyClass"
        assert result is not None
        assert result.name == "MyClass"

    def test_truediv_not_found(self, structure):
        """/ operator returns None for missing element."""
        result = structure / "NonExistent"
        assert result is None

    def test_getitem_simple(self, structure):
        """[] operator with simple path."""
        result = structure["MyClass"]
        assert result is not None
        assert result.name == "MyClass"

    def test_getitem_not_found(self, structure):
        """[] operator returns None for missing path."""
        result = structure["NonExistent"]
        assert result is None


class TestTypedStructureRoots:
    """Test root element identification."""

    def test_roots_without_type(self):
        """Without reveal_type, all elements are roots."""
        elements = [
            TypedElement(name="func1", line=1, line_end=10, category="function"),
            TypedElement(name="func2", line=12, line_end=20, category="function"),
        ]
        structure = TypedStructure(path="test.py", reveal_type=None, elements=elements)

        # Without type info, parent computation returns None, so all are roots
        roots = structure.roots
        assert len(roots) == 2


class TestTypedStructureQueries:
    """Test find methods."""

    @pytest.fixture
    def structure(self):
        """Structure for query tests."""
        elements = [
            TypedElement(name="short_func", line=1, line_end=5, category="function"),
            TypedElement(name="long_func", line=10, line_end=100, category="function"),
            TypedElement(name="MyClass", line=110, line_end=200, category="class"),
        ]
        return TypedStructure(path="test.py", reveal_type=None, elements=elements)

    def test_find_by_name(self, structure):
        """find_by_name locates element."""
        result = structure.find_by_name("long_func")
        assert result is not None
        assert result.name == "long_func"

    def test_find_by_name_not_found(self, structure):
        """find_by_name returns None if not found."""
        result = structure.find_by_name("missing")
        assert result is None

    def test_find_by_line_exact(self, structure):
        """find_by_line with exact start line."""
        result = structure.find_by_line(1)
        assert result is not None
        assert result.name == "short_func"

    def test_find_by_line_middle(self, structure):
        """find_by_line with line in middle of element."""
        result = structure.find_by_line(50)
        assert result is not None
        assert result.name == "long_func"

    def test_find_by_line_not_found(self, structure):
        """find_by_line returns None for uncontained line."""
        result = structure.find_by_line(250)
        assert result is None

    def test_find_with_predicate(self, structure):
        """find with predicate function."""
        # Find elements spanning more than 50 lines
        results = list(structure.find(lambda e: (e.line_end - e.line) > 50))
        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"long_func", "MyClass"}

    def test_find_with_kwargs(self, structure):
        """find with keyword arguments."""
        results = list(structure.find(category="class"))
        assert len(results) == 1
        assert results[0].name == "MyClass"


class TestTypedStructureTraversal:
    """Test traversal methods."""

    @pytest.fixture
    def structure(self):
        """Structure for traversal tests."""
        elements = [
            TypedElement(name="func_at_20", line=20, line_end=30, category="function"),
            TypedElement(name="func_at_1", line=1, line_end=10, category="function"),
            TypedElement(name="func_at_50", line=50, line_end=60, category="function"),
        ]
        return TypedStructure(path="test.py", reveal_type=None, elements=elements)

    def test_walk_flat_sorted_by_line(self, structure):
        """walk_flat returns elements sorted by line number."""
        names = [el.name for el in structure.walk_flat()]
        assert names == ["func_at_1", "func_at_20", "func_at_50"]


class TestTypedStructureStats:
    """Test statistics computation."""

    def test_stats_empty(self):
        """Stats for empty structure."""
        structure = TypedStructure(path="test.py", reveal_type=None, elements=[])
        stats = structure.stats

        assert stats["total"] == 0
        assert stats["roots"] == 0
        assert stats["max_depth"] == 0

    def test_stats_with_elements(self):
        """Stats for structure with elements."""
        elements = [
            TypedElement(name="f1", line=1, line_end=10, category="function"),
            TypedElement(name="f2", line=12, line_end=20, category="function"),
            TypedElement(name="C1", line=25, line_end=50, category="class"),
        ]
        structure = TypedStructure(path="test.py", reveal_type=None, elements=elements)
        stats = structure.stats

        assert stats["total"] == 3
        assert stats["function"] == 2
        assert stats["class"] == 1


class TestTypedStructureSerialization:
    """Test serialization methods."""

    def test_to_dict(self):
        """to_dict produces serializable output."""
        elements = [
            TypedElement(name="func1", line=1, line_end=10, category="function"),
        ]
        structure = TypedStructure(path="test.py", reveal_type=None, elements=elements)
        result = structure.to_dict()

        assert result["path"] == "test.py"
        assert result["type"] is None
        assert len(result["elements"]) == 1
        assert result["elements"][0]["name"] == "func1"
        assert "stats" in result

    def test_to_tree(self):
        """to_tree produces nested structure."""
        elements = [
            TypedElement(name="func1", line=1, line_end=10, category="function"),
        ]
        structure = TypedStructure(path="test.py", reveal_type=None, elements=elements)
        result = structure.to_tree()

        assert result["path"] == "test.py"
        assert result["type"] is None
        assert "roots" in result


class TestTypedStructureFromAnalyzerOutput:
    """Test factory method from analyzer output."""

    def test_basic_conversion(self):
        """Convert simple analyzer output."""
        analyzer_output = {
            "functions": [
                {"name": "helper", "line": 1, "line_end": 10},
                {"name": "process", "line": 15, "line_end": 30},
            ],
            "classes": [
                {"name": "MyClass", "line": 35, "line_end": 100},
            ],
        }
        structure = TypedStructure.from_analyzer_output(analyzer_output, "test.py")

        assert len(structure) == 3
        assert len(structure.functions) == 2
        assert len(structure.classes) == 1

    def test_skips_private_keys(self):
        """Private keys (starting with _) are skipped."""
        analyzer_output = {
            "functions": [{"name": "func", "line": 1, "line_end": 10}],
            "_metadata": {"version": "1.0"},
        }
        structure = TypedStructure.from_analyzer_output(analyzer_output, "test.py")

        assert len(structure) == 1

    def test_imports_parse_content(self):
        """Import elements get name parsed from content."""
        analyzer_output = {
            "imports": [
                {"name": "", "line": 1, "line_end": 1, "content": "from typing import Dict"},
                {"name": "", "line": 2, "line_end": 2, "content": "import os"},
            ],
        }
        structure = TypedStructure.from_analyzer_output(analyzer_output, "test.py")

        assert len(structure.imports) == 2
        names = {i.name for i in structure.imports}
        assert names == {"typing", "os"}

    def test_handles_non_list_values(self):
        """Non-list values in output are skipped."""
        analyzer_output = {
            "functions": [{"name": "func", "line": 1, "line_end": 10}],
            "file_info": {"size": 1000},  # Not a list, should be skipped
        }
        structure = TypedStructure.from_analyzer_output(analyzer_output, "test.py")

        assert len(structure) == 1

    def test_handles_non_dict_items(self):
        """Non-dict items in lists are skipped."""
        analyzer_output = {
            "functions": [
                {"name": "func", "line": 1, "line_end": 10},
                "invalid item",  # Should be skipped
                None,  # Should be skipped
            ],
        }
        structure = TypedStructure.from_analyzer_output(analyzer_output, "test.py")

        assert len(structure) == 1
