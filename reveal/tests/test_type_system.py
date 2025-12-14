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
        """Clear registry and import PythonType."""
        TypeRegistry.clear()
        # Import to register
        from reveal.types.python import PythonType
        self.python_type = PythonType

    def test_python_type_registered(self):
        """PythonType is registered on import."""
        assert TypeRegistry.from_extension(".py") is not None
        assert TypeRegistry.from_scheme("py") is not None

    def test_python_containment_rules(self):
        """PythonType has correct containment rules."""
        assert self.python_type.can_contain("class", "method")
        assert self.python_type.can_contain("class", "function")
        assert self.python_type.can_contain("function", "function")  # nested
        assert not self.python_type.can_contain("function", "class")
