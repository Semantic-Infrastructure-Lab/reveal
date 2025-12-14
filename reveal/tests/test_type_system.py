"""Tests for the Type-First Architecture.

Tests the core type system: TypeRegistry, TypedElement, TypedStructure.
"""

import pytest
from reveal.type_system import EntityDef, RevealType, TypeRegistry
from reveal.elements import TypedElement, PythonElement
from reveal.structure import TypedStructure


class TestEntityDef:
    """Tests for EntityDef dataclass."""

    def test_basic_entity(self):
        """EntityDef can define containment rules."""
        entity = EntityDef(
            contains=["method", "attribute"],
            properties={"name": str, "line": int},
        )
        assert "method" in entity.contains
        assert "attribute" in entity.contains
        assert entity.properties["name"] == str

    def test_entity_with_inheritance(self):
        """EntityDef can specify inheritance."""
        method = EntityDef(
            inherits="function",
            properties={"decorators": list},
        )
        assert method.inherits == "function"


class TestRevealType:
    """Tests for RevealType dataclass."""

    def test_basic_type(self):
        """RevealType encapsulates type information."""
        py_type = RevealType(
            name="test_python",
            extensions=[".py"],
            scheme="testpy",
            entities={
                "function": EntityDef(contains=["variable"]),
                "class": EntityDef(contains=["method", "function"]),
            },
        )
        assert py_type.name == "test_python"
        assert ".py" in py_type.extensions
        assert py_type.scheme == "testpy"

    def test_get_entity(self):
        """get_entity retrieves entity definitions."""
        py_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "function": EntityDef(
                    contains=["variable"],
                    properties={"name": str},
                ),
            },
        )
        entity = py_type.get_entity("function")
        assert entity is not None
        assert "variable" in entity.contains

    def test_get_entity_with_inheritance(self):
        """get_entity resolves inheritance."""
        py_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "function": EntityDef(
                    contains=["variable"],
                    properties={"name": str, "line": int},
                ),
                "method": EntityDef(
                    inherits="function",
                    contains=["local"],
                    properties={"decorators": list},
                ),
            },
        )
        method = py_type.get_entity("method")
        assert method is not None
        # Should have parent's contains + own
        assert "variable" in method.contains
        assert "local" in method.contains
        # Should have merged properties
        assert "name" in method.properties
        assert "decorators" in method.properties

    def test_can_contain(self):
        """can_contain checks containment rules."""
        py_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["method", "function"]),
                "function": EntityDef(contains=["variable"]),
            },
        )
        assert py_type.can_contain("class", "method")
        assert py_type.can_contain("class", "function")
        assert not py_type.can_contain("class", "class")  # no nested classes
        assert py_type.can_contain("function", "variable")


class TestTypeRegistry:
    """Tests for TypeRegistry singleton."""

    def setup_method(self):
        """Clear registry before each test."""
        TypeRegistry.clear()

    def test_register_and_lookup_by_extension(self):
        """Register type and lookup by extension."""
        py_type = RevealType(
            name="test_py",
            extensions=[".py", ".pyw"],
            scheme="py",
        )
        TypeRegistry.register(py_type)

        found = TypeRegistry.from_extension(".py")
        assert found is not None
        assert found.name == "test_py"

        found2 = TypeRegistry.from_extension(".pyw")
        assert found2 is not None
        assert found2.name == "test_py"

    def test_lookup_by_scheme(self):
        """Lookup type by URI scheme."""
        py_type = RevealType(
            name="test_py",
            extensions=[".py"],
            scheme="py",
        )
        TypeRegistry.register(py_type)

        found = TypeRegistry.from_scheme("py")
        assert found is not None
        assert found.name == "test_py"

    def test_case_insensitive_lookup(self):
        """Lookups are case insensitive."""
        py_type = RevealType(
            name="test_py",
            extensions=[".PY"],
            scheme="PY",
        )
        TypeRegistry.register(py_type)

        assert TypeRegistry.from_extension(".py") is not None
        assert TypeRegistry.from_extension(".PY") is not None
        assert TypeRegistry.from_scheme("py") is not None
        assert TypeRegistry.from_scheme("PY") is not None

    def test_get_by_name(self):
        """Get type by name."""
        py_type = RevealType(
            name="test_py",
            extensions=[".py"],
            scheme="py",
        )
        TypeRegistry.register(py_type)

        found = TypeRegistry.get("test_py")
        assert found is not None
        assert found.name == "test_py"


class TestTypedElement:
    """Tests for TypedElement navigation."""

    def test_basic_element(self):
        """Create basic element."""
        el = TypedElement(
            name="my_func",
            line=10,
            line_end=20,
            category="function",
        )
        assert el.name == "my_func"
        assert el.line == 10
        assert el.line_end == 20
        assert el.line_count == 11

    def test_containment_operator(self):
        """Test 'child in parent' syntax."""
        parent = TypedElement(name="parent", line=10, line_end=50, category="class")
        child = TypedElement(name="child", line=20, line_end=30, category="function")
        outside = TypedElement(name="outside", line=60, line_end=70, category="function")

        assert child in parent
        assert outside not in parent
        assert parent not in parent  # element not in itself

    def test_path_navigation(self):
        """Test / operator for navigation."""
        # Create a type with containment rules
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=[]),
            },
        )

        # Create elements
        my_class = TypedElement(name="MyClass", line=10, line_end=50, category="class")
        method1 = TypedElement(name="process", line=15, line_end=25, category="function")
        method2 = TypedElement(name="save", line=30, line_end=40, category="function")

        # Wire up
        all_elements = [my_class, method1, method2]
        for el in all_elements:
            el._type = test_type
            el._siblings = all_elements

        # Test navigation
        found = my_class / "process"
        assert found is not None
        assert found.name == "process"

        not_found = my_class / "nonexistent"
        assert not_found is None

    def test_children_computed(self):
        """Children are computed from line ranges + containment rules."""
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=[]),
            },
        )

        my_class = TypedElement(name="MyClass", line=10, line_end=50, category="class")
        method1 = TypedElement(name="process", line=15, line_end=25, category="function")
        method2 = TypedElement(name="save", line=30, line_end=40, category="function")
        outside = TypedElement(name="helper", line=60, line_end=70, category="function")

        all_elements = [my_class, method1, method2, outside]
        for el in all_elements:
            el._type = test_type
            el._siblings = all_elements

        children = my_class.children
        assert len(children) == 2
        assert method1 in children
        assert method2 in children
        assert outside not in children

    def test_parent_computed(self):
        """Parent is computed as innermost container."""
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=[]),
            },
        )

        my_class = TypedElement(name="MyClass", line=10, line_end=50, category="class")
        method = TypedElement(name="process", line=15, line_end=25, category="function")

        all_elements = [my_class, method]
        for el in all_elements:
            el._type = test_type
            el._siblings = all_elements

        assert method.parent is my_class
        assert my_class.parent is None

    def test_depth_computed(self):
        """Depth is computed from parent chain."""
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=["function"]),  # nested functions
            },
        )

        my_class = TypedElement(name="MyClass", line=10, line_end=100, category="class")
        method = TypedElement(name="outer", line=20, line_end=80, category="function")
        nested = TypedElement(name="inner", line=30, line_end=50, category="function")

        all_elements = [my_class, method, nested]
        for el in all_elements:
            el._type = test_type
            el._siblings = all_elements

        assert my_class.depth == 0
        assert method.depth == 1
        assert nested.depth == 2

    def test_walk(self):
        """walk() traverses element and all descendants."""
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=[]),
            },
        )

        my_class = TypedElement(name="MyClass", line=10, line_end=50, category="class")
        method1 = TypedElement(name="process", line=15, line_end=25, category="function")
        method2 = TypedElement(name="save", line=30, line_end=40, category="function")

        all_elements = [my_class, method1, method2]
        for el in all_elements:
            el._type = test_type
            el._siblings = all_elements

        walked = list(my_class.walk())
        assert len(walked) == 3
        assert my_class in walked
        assert method1 in walked
        assert method2 in walked

    def test_path_property(self):
        """path property builds full dot-separated path."""
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=["function"]),
            },
        )

        my_class = TypedElement(name="MyClass", line=10, line_end=100, category="class")
        method = TypedElement(name="process", line=20, line_end=80, category="function")
        nested = TypedElement(name="helper", line=30, line_end=50, category="function")

        all_elements = [my_class, method, nested]
        for el in all_elements:
            el._type = test_type
            el._siblings = all_elements

        assert my_class.path == "MyClass"
        assert method.path == "MyClass.process"
        assert nested.path == "MyClass.process.helper"


class TestTypedStructure:
    """Tests for TypedStructure container."""

    def test_basic_structure(self):
        """Create structure and access elements."""
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=[]),
            },
        )

        elements = [
            TypedElement(name="MyClass", line=10, line_end=50, category="class"),
            TypedElement(name="process", line=15, line_end=25, category="function"),
        ]

        structure = TypedStructure(
            path="test.py",
            reveal_type=test_type,
            elements=elements,
        )

        assert len(structure) == 2
        assert structure.path == "test.py"

    def test_elements_wired_up(self):
        """Structure wires up _type and _siblings on elements."""
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=[]),
            },
        )

        elements = [
            TypedElement(name="MyClass", line=10, line_end=50, category="class"),
            TypedElement(name="process", line=15, line_end=25, category="function"),
        ]

        structure = TypedStructure(
            path="test.py",
            reveal_type=test_type,
            elements=elements,
        )

        # All elements should have _type and _siblings set
        for el in structure.elements:
            assert el._type is test_type
            assert el._siblings is elements

    def test_root_navigation(self):
        """Navigate from structure root with /."""
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=[]),
            },
        )

        elements = [
            TypedElement(name="MyClass", line=10, line_end=50, category="class"),
            TypedElement(name="process", line=15, line_end=25, category="function"),
        ]

        structure = TypedStructure(
            path="test.py",
            reveal_type=test_type,
            elements=elements,
        )

        my_class = structure / "MyClass"
        assert my_class is not None
        assert my_class.name == "MyClass"

        method = my_class / "process"
        assert method is not None
        assert method.name == "process"

    def test_path_access(self):
        """Access elements by path string."""
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=[]),
            },
        )

        elements = [
            TypedElement(name="MyClass", line=10, line_end=50, category="class"),
            TypedElement(name="process", line=15, line_end=25, category="function"),
        ]

        structure = TypedStructure(
            path="test.py",
            reveal_type=test_type,
            elements=elements,
        )

        method = structure["MyClass.process"]
        assert method is not None
        assert method.name == "process"

    def test_category_accessors(self):
        """Test functions, classes, etc. accessors."""
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=[]),
            },
        )

        elements = [
            TypedElement(name="MyClass", line=10, line_end=50, category="class"),
            TypedElement(name="helper", line=60, line_end=70, category="function"),
            TypedElement(name="process", line=15, line_end=25, category="function"),
        ]

        structure = TypedStructure(
            path="test.py",
            reveal_type=test_type,
            elements=elements,
        )

        assert len(structure.classes) == 1
        assert len(structure.functions) == 2

    def test_roots(self):
        """roots returns only top-level elements."""
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=[]),
            },
        )

        elements = [
            TypedElement(name="MyClass", line=10, line_end=50, category="class"),
            TypedElement(name="method", line=15, line_end=25, category="function"),  # inside class
            TypedElement(name="helper", line=60, line_end=70, category="function"),  # top-level
        ]

        structure = TypedStructure(
            path="test.py",
            reveal_type=test_type,
            elements=elements,
        )

        roots = structure.roots
        assert len(roots) == 2  # MyClass and helper
        root_names = [r.name for r in roots]
        assert "MyClass" in root_names
        assert "helper" in root_names
        assert "method" not in root_names

    def test_find(self):
        """find() locates elements by properties."""
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=[]),
            },
        )

        elements = [
            TypedElement(name="MyClass", line=10, line_end=50, category="class"),
            TypedElement(name="method", line=15, line_end=25, category="function"),
            TypedElement(name="helper", line=60, line_end=70, category="function"),
        ]

        structure = TypedStructure(
            path="test.py",
            reveal_type=test_type,
            elements=elements,
        )

        # Find by category
        functions = list(structure.find(category="function"))
        assert len(functions) == 2

        # Find by predicate
        long_funcs = list(structure.find(lambda e: e.line_count > 10))
        assert len(long_funcs) == 3  # MyClass (41), method (11), helper (11)

    def test_find_by_line(self):
        """find_by_line locates innermost element."""
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=[]),
            },
        )

        elements = [
            TypedElement(name="MyClass", line=10, line_end=50, category="class"),
            TypedElement(name="method", line=15, line_end=25, category="function"),
        ]

        structure = TypedStructure(
            path="test.py",
            reveal_type=test_type,
            elements=elements,
        )

        # Line inside method (which is inside class)
        el = structure.find_by_line(20)
        assert el is not None
        assert el.name == "method"  # Innermost

        # Line inside class but outside method
        el = structure.find_by_line(30)
        assert el is not None
        assert el.name == "MyClass"

        # Line outside everything
        el = structure.find_by_line(100)
        assert el is None


class TestPythonElement:
    """Tests for PythonElement subclass."""

    def test_python_specific_properties(self):
        """PythonElement has signature and decorators."""
        el = PythonElement(
            name="process",
            line=10,
            line_end=20,
            category="function",
            signature="(self, data: str) -> bool",
            decorators=["@staticmethod"],
        )
        assert el.signature == "(self, data: str) -> bool"
        assert "@staticmethod" in el.decorators
        assert el.is_staticmethod

    def test_is_method_detection(self):
        """is_method detects functions inside classes."""
        test_type = RevealType(
            name="test",
            extensions=[".test"],
            scheme="test",
            entities={
                "class": EntityDef(contains=["function"]),
                "function": EntityDef(contains=[]),
            },
        )

        my_class = PythonElement(name="MyClass", line=10, line_end=50, category="class")
        method = PythonElement(name="process", line=15, line_end=25, category="function")
        standalone = PythonElement(name="helper", line=60, line_end=70, category="function")

        all_elements = [my_class, method, standalone]
        for el in all_elements:
            el._type = test_type
            el._siblings = all_elements

        assert method.is_method
        assert not standalone.is_method


class TestPythonTypeIntegration:
    """Integration tests with the real PythonType."""

    def setup_method(self):
        """Clear registry and register PythonType."""
        TypeRegistry.clear()
        from reveal.types.python import PythonType
        TypeRegistry.register(PythonType)
        self.python_type = PythonType

    def test_python_type_registered(self):
        """PythonType is registered and accessible."""
        assert TypeRegistry.from_extension(".py") is not None
        assert TypeRegistry.from_scheme("py") is not None

    def test_python_containment_rules(self):
        """PythonType has correct containment rules."""
        assert self.python_type.can_contain("class", "method")
        assert self.python_type.can_contain("class", "function")
        assert self.python_type.can_contain("function", "function")  # nested
        assert not self.python_type.can_contain("function", "class")


class TestTypedStructureFactory:
    """Tests for TypedStructure.from_analyzer_output factory method."""

    def setup_method(self):
        """Clear registry and import PythonType."""
        TypeRegistry.clear()
        from reveal.types.python import PythonType
        self.python_type = PythonType

    def test_from_analyzer_output_basic(self):
        """Factory creates TypedStructure from raw dict."""
        raw = {
            "functions": [
                {"name": "foo", "line": 1, "line_end": 5, "signature": "(x)"},
                {"name": "bar", "line": 10, "line_end": 15, "signature": "(y)"},
            ],
            "classes": [
                {"name": "MyClass", "line": 20, "line_end": 50},
            ],
        }

        structure = TypedStructure.from_analyzer_output(raw, "test.py")

        assert len(structure) == 3
        assert len(structure.functions) == 2
        assert len(structure.classes) == 1

    def test_from_analyzer_output_auto_detects_type(self):
        """Factory auto-detects RevealType from extension."""
        # Ensure PythonType is registered for this test
        TypeRegistry.register(self.python_type)

        raw = {"functions": [{"name": "foo", "line": 1, "line_end": 5}]}

        structure = TypedStructure.from_analyzer_output(raw, "test.py")

        assert structure.reveal_type is not None
        assert structure.reveal_type.name == "python"

    def test_from_analyzer_output_uses_element_class(self):
        """Factory uses element_class from RevealType."""
        from reveal.elements import PythonElement

        raw = {"functions": [{"name": "foo", "line": 1, "line_end": 5}]}

        structure = TypedStructure.from_analyzer_output(
            raw, "test.py", self.python_type
        )

        assert isinstance(structure.functions[0], PythonElement)

    def test_from_analyzer_output_containment(self):
        """Factory-created structure has working containment."""
        raw = {
            "classes": [{"name": "MyClass", "line": 1, "line_end": 20}],
            "functions": [{"name": "method", "line": 5, "line_end": 10}],
        }

        structure = TypedStructure.from_analyzer_output(
            raw, "test.py", self.python_type
        )

        my_class = structure / "MyClass"
        method = structure.find_by_name("method")

        assert my_class is not None
        assert method is not None
        assert method in my_class
        assert method.parent == my_class

    def test_from_analyzer_output_skips_private_keys(self):
        """Factory skips keys starting with underscore."""
        raw = {
            "functions": [{"name": "foo", "line": 1, "line_end": 5}],
            "_meta": {"analyzer": "test"},
        }

        structure = TypedStructure.from_analyzer_output(raw, "test.py")

        assert len(structure) == 1

    def test_from_analyzer_output_handles_missing_line_end(self):
        """Factory handles items without line_end (defaults to line)."""
        raw = {
            "imports": [{"name": "os", "line": 1}],
        }

        structure = TypedStructure.from_analyzer_output(raw, "test.py")

        assert len(structure) == 1
        assert structure.imports[0].line_end == 1

    def test_from_analyzer_output_navigation(self):
        """Factory-created structure supports full navigation."""
        raw = {
            "classes": [{"name": "Parent", "line": 1, "line_end": 30}],
            "functions": [
                {"name": "outer", "line": 5, "line_end": 20},
                {"name": "inner", "line": 10, "line_end": 15},
            ],
        }

        structure = TypedStructure.from_analyzer_output(
            raw, "test.py", self.python_type
        )

        # Path navigation
        parent = structure / "Parent"
        assert parent is not None

        # Nested containment
        inner = structure.find_by_name("inner")
        outer = structure.find_by_name("outer")
        assert inner.parent == outer
        assert outer.parent == parent

        # Walk
        all_elements = list(structure.walk())
        assert len(all_elements) == 3


class TestParseImportName:
    """Tests for _parse_import_name helper function."""

    def test_from_import(self):
        """Parses 'from X import Y' format."""
        from reveal.structure import _parse_import_name

        assert _parse_import_name("from dataclasses import dataclass") == "dataclasses"
        assert _parse_import_name("from typing import Dict, List") == "typing"
        assert _parse_import_name("from os.path import join") == "os.path"

    def test_import_statement(self):
        """Parses 'import X' format."""
        from reveal.structure import _parse_import_name

        assert _parse_import_name("import os") == "os"
        assert _parse_import_name("import os.path") == "os.path"
        assert _parse_import_name("import json as j") == "json"

    def test_relative_imports(self):
        """Parses relative imports."""
        from reveal.structure import _parse_import_name

        assert _parse_import_name("from . import utils") == "."
        assert _parse_import_name("from .. import base") == ".."
        assert _parse_import_name("from .utils import helper") == ".utils"
        assert _parse_import_name("from ..core import base") == "..core"

    def test_empty_and_invalid(self):
        """Handles empty and invalid input."""
        from reveal.structure import _parse_import_name

        assert _parse_import_name("") == ""
        assert _parse_import_name("not an import") == ""
        assert _parse_import_name("x = 1") == ""

    def test_factory_uses_import_parser(self):
        """Factory method uses import parser for imports without names."""
        raw = {
            "imports": [
                {"line": 1, "content": "from dataclasses import dataclass"},
                {"line": 2, "content": "import os"},
                {"line": 3, "content": "from typing import Dict"},
            ],
        }

        structure = TypedStructure.from_analyzer_output(raw, "test.py")

        names = [e.name for e in structure.imports]
        assert names == ["dataclasses", "os", "typing"]


class TestPythonElementDisplayProperties:
    """Tests for PythonElement display helper properties."""

    def setup_method(self):
        """Set up test elements."""
        from reveal.elements import PythonElement

        # A method inside a class (simulated via _siblings)
        self.method = PythonElement(
            name="process",
            line=10,
            line_end=20,
            category="function",
            signature="(self, data: str) -> bool",
        )
        self.cls = PythonElement(
            name="MyClass",
            line=1,
            line_end=50,
            category="class",
        )
        # Wire up siblings for parent detection
        self.method._siblings = [self.cls, self.method]
        self.cls._siblings = [self.cls, self.method]

        # Need to set up type for containment
        TypeRegistry.clear()
        from reveal.types.python import PythonType

        self.method._type = PythonType
        self.cls._type = PythonType

    def test_display_category_method(self):
        """Methods inside classes show as 'method'."""
        assert self.method.display_category == "method"

    def test_display_category_property(self):
        """Functions with @property decorator show as 'property'."""
        from reveal.elements import PythonElement

        prop = PythonElement(
            name="value",
            line=5,
            line_end=7,
            category="function",
            decorators=["@property"],
        )
        assert prop.display_category == "property"

    def test_display_category_classmethod(self):
        """Functions with @classmethod show as 'classmethod'."""
        from reveal.elements import PythonElement

        cm = PythonElement(
            name="create",
            line=5,
            line_end=10,
            category="function",
            decorators=["@classmethod"],
        )
        assert cm.display_category == "classmethod"

    def test_display_category_staticmethod(self):
        """Functions with @staticmethod show as 'staticmethod'."""
        from reveal.elements import PythonElement

        sm = PythonElement(
            name="helper",
            line=5,
            line_end=10,
            category="function",
            decorators=["@staticmethod"],
        )
        assert sm.display_category == "staticmethod"

    def test_display_category_standalone_function(self):
        """Standalone functions show as 'function'."""
        from reveal.elements import PythonElement

        func = PythonElement(
            name="main",
            line=1,
            line_end=10,
            category="function",
        )
        assert func.display_category == "function"

    def test_compact_signature_simple(self):
        """Compact signature extracts parameter names."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="foo",
            line=1,
            line_end=5,
            category="function",
            signature="(self, x, y)",
        )
        assert el.compact_signature == "(x, y)"

    def test_compact_signature_with_types(self):
        """Compact signature strips type annotations."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="foo",
            line=1,
            line_end=5,
            category="function",
            signature="(self, x: int, y: str) -> bool",
        )
        assert el.compact_signature == "(x, y)"

    def test_compact_signature_with_defaults(self):
        """Compact signature strips default values."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="foo",
            line=1,
            line_end=5,
            category="function",
            signature="(self, x=10, y='hello')",
        )
        assert el.compact_signature == "(x, y)"

    def test_compact_signature_complex_types(self):
        """Compact signature handles complex nested types."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="foo",
            line=1,
            line_end=5,
            category="function",
            signature="(self, predicate: Callable[[TypedElement], bool]) -> Iterator[TypedElement]",
        )
        assert el.compact_signature == "(predicate)"

    def test_compact_signature_many_params(self):
        """Compact signature truncates when more than 4 params."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="foo",
            line=1,
            line_end=5,
            category="function",
            signature="(self, a, b, c, d, e, f)",
        )
        assert el.compact_signature == "(a, b, c, ...)"

    def test_compact_signature_cls(self):
        """Compact signature removes cls for classmethods."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="create",
            line=1,
            line_end=5,
            category="function",
            signature="(cls, data: dict)",
            decorators=["@classmethod"],
        )
        assert el.compact_signature == "(data)"

    def test_compact_signature_empty(self):
        """Compact signature handles empty params."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="foo",
            line=1,
            line_end=5,
            category="function",
            signature="(self)",
        )
        assert el.compact_signature == "()"

    def test_return_type_simple(self):
        """Return type extracts from signature."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="foo",
            line=1,
            line_end=5,
            category="function",
            signature="(self) -> str",
        )
        assert el.return_type == "str"

    def test_return_type_complex(self):
        """Return type handles complex types."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="foo",
            line=1,
            line_end=5,
            category="function",
            signature="(self) -> Dict[str, int]",
        )
        assert el.return_type == "Dict[str, int]"

    def test_return_type_none(self):
        """Return type is empty when not specified."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="foo",
            line=1,
            line_end=5,
            category="function",
            signature="(self)",
        )
        assert el.return_type == ""

    def test_decorator_prefix_property(self):
        """Decorator prefix shows @property."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="value",
            line=1,
            line_end=5,
            category="function",
            decorators=["@property"],
        )
        assert el.decorator_prefix == "@property"

    def test_decorator_prefix_priority(self):
        """Decorator prefix prioritizes semantic decorators."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="value",
            line=1,
            line_end=5,
            category="function",
            decorators=["@lru_cache", "@classmethod"],
        )
        # @classmethod takes priority over @lru_cache
        assert el.decorator_prefix == "@classmethod"

    def test_decorator_prefix_custom(self):
        """Decorator prefix shows custom decorators."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="handler",
            line=1,
            line_end=5,
            category="function",
            decorators=["@app.route"],
        )
        assert el.decorator_prefix == "@app.route"

    def test_compact_signature_no_signature(self):
        """Compact signature returns empty for no signature."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="foo",
            line=1,
            line_end=5,
            category="function",
            signature="",
        )
        assert el.compact_signature == ""

    def test_return_type_long_truncated(self):
        """Long return types are truncated."""
        from reveal.elements import PythonElement

        el = PythonElement(
            name="foo",
            line=1,
            line_end=5,
            category="function",
            signature="(self) -> Dict[str, List[Tuple[int, str, float]]]",
        )
        # Should truncate the very long type
        assert "[...]" in el.return_type or len(el.return_type) <= 30


class TestTypedStructureNavigation:
    """Tests for TypedStructure navigation methods."""

    def setup_method(self):
        """Set up test structure."""
        TypeRegistry.clear()
        from reveal.types.python import PythonType
        TypeRegistry.register(PythonType)

        raw = {
            "classes": [{"name": "MyClass", "line": 1, "line_end": 50}],
            "functions": [
                {"name": "method1", "line": 5, "line_end": 15},
                {"name": "method2", "line": 20, "line_end": 30},
                {"name": "standalone", "line": 60, "line_end": 70},
            ],
            "imports": [
                {"line": 1, "content": "import os"},
            ],
        }
        self.structure = TypedStructure.from_analyzer_output(raw, "test.py", PythonType)

    def test_stats(self):
        """Stats returns correct counts."""
        stats = self.structure.stats
        assert stats["total"] == 5  # 1 class + 3 functions + 1 import
        assert stats["class"] == 1
        assert stats["function"] == 3
        assert stats["import"] == 1

    def test_to_dict(self):
        """to_dict serializes structure."""
        d = self.structure.to_dict()
        assert d["path"] == "test.py"
        assert "elements" in d

    def test_to_tree(self):
        """to_tree returns hierarchical structure."""
        tree = self.structure.to_tree()
        assert "roots" in tree
        assert len(tree["roots"]) > 0

    def test_walk(self):
        """walk iterates all elements."""
        elements = list(self.structure.walk())
        assert len(elements) == 5

    def test_walk_flat(self):
        """walk_flat iterates all elements without tree structure."""
        elements = list(self.structure.walk_flat())
        assert len(elements) == 5

    def test_find_by_line(self):
        """find_by_line returns element at line."""
        el = self.structure.find_by_line(10)
        assert el is not None
        assert el.name == "method1"

    def test_bool(self):
        """bool returns True for non-empty structure."""
        assert bool(self.structure)

        empty = TypedStructure(path="empty.py", reveal_type=None, elements=[])
        assert not bool(empty)

    def test_iter(self):
        """iter yields elements."""
        elements = list(self.structure)
        assert len(elements) == 5


class TestMarkdownElement:
    """Tests for MarkdownElement."""

    def test_markdown_element_creation(self):
        """MarkdownElement can be created."""
        from reveal.elements import MarkdownElement

        el = MarkdownElement(
            name="Introduction",
            line=1,
            line_end=10,
            category="section",
            level=1,
        )
        assert el.name == "Introduction"
        assert el.level == 1

    def test_markdown_to_dict(self):
        """MarkdownElement.to_dict includes level."""
        from reveal.elements import MarkdownElement

        el = MarkdownElement(
            name="Overview",
            line=1,
            line_end=5,
            category="section",
            level=2,
        )
        d = el.to_dict()
        assert d["level"] == 2
        assert d["name"] == "Overview"
