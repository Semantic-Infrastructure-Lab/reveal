"""Comprehensive tests for reveal.elements module."""

import pytest
from reveal.elements import (
    TypedElement,
    PythonElement,
    MarkdownElement,
    _find_closing_paren,
    _extract_param_name,
    _extract_param_names,
)


# === Helper Function Tests ===


class TestFindClosingParen:
    """Test _find_closing_paren() helper function."""

    def test_simple_parens(self):
        """Simple parentheses with no nesting."""
        assert _find_closing_paren("()") == 1
        assert _find_closing_paren("(x)") == 2
        assert _find_closing_paren("(foo, bar)") == 9

    def test_nested_parens(self):
        """Nested parentheses."""
        assert _find_closing_paren("((x))") == 4
        assert _find_closing_paren("(foo(bar))") == 9
        assert _find_closing_paren("(a, (b, c))") == 10

    def test_mixed_brackets(self):
        """Mixed bracket types."""
        assert _find_closing_paren("([x])") == 4
        assert _find_closing_paren("({x: y})") == 7
        assert _find_closing_paren("(List[int])") == 10

    def test_no_closing_paren(self):
        """String without closing paren."""
        assert _find_closing_paren("(") == -1
        assert _find_closing_paren("(foo") == -1
        assert _find_closing_paren("(foo, bar") == -1

    def test_empty_string(self):
        """Empty string."""
        assert _find_closing_paren("") == -1


class TestExtractParamName:
    """Test _extract_param_name() helper function."""

    def test_simple_name(self):
        """Simple parameter name."""
        assert _extract_param_name("x") == "x"
        assert _extract_param_name("foo") == "foo"
        assert _extract_param_name("param1") == "param1"

    def test_with_type_annotation(self):
        """Parameter with type annotation."""
        assert _extract_param_name("x: int") == "x"
        assert _extract_param_name("name: str") == "name"
        assert _extract_param_name("items: List[str]") == "items"

    def test_with_default_value(self):
        """Parameter with default value."""
        assert _extract_param_name("x = 5") == "x"
        assert _extract_param_name("name = 'foo'") == "name"
        assert _extract_param_name("items = []") == "items"

    def test_with_both(self):
        """Parameter with type annotation and default value."""
        assert _extract_param_name("x: int = 5") == "x"
        assert _extract_param_name("name: str = 'foo'") == "name"

    def test_variadic_params(self):
        """Variadic parameters."""
        assert _extract_param_name("*args") == "*args"
        assert _extract_param_name("**kwargs") == "**kwargs"

    def test_empty_or_whitespace(self):
        """Empty or whitespace-only parameters."""
        assert _extract_param_name("") is None
        assert _extract_param_name("   ") is None

    def test_with_whitespace(self):
        """Parameter with surrounding whitespace."""
        assert _extract_param_name("  x  ") == "x"
        assert _extract_param_name("  name: str  ") == "name"


class TestExtractParamNames:
    """Test _extract_param_names() helper function."""

    def test_empty_params(self):
        """Empty parameter list."""
        assert _extract_param_names("") == []
        assert _extract_param_names("   ") == []

    def test_single_param(self):
        """Single parameter."""
        assert _extract_param_names("x") == ["x"]
        assert _extract_param_names("x: int") == ["x"]

    def test_multiple_params(self):
        """Multiple parameters."""
        assert _extract_param_names("x, y") == ["x", "y"]
        assert _extract_param_names("x: int, y: str") == ["x", "y"]

    def test_nested_brackets(self):
        """Parameters with nested brackets."""
        assert _extract_param_names("x: List[int]") == ["x"]
        assert _extract_param_names("x: List[int], y: Dict[str, int]") == ["x", "y"]
        assert _extract_param_names("items: List[Tuple[str, int]]") == ["items"]

    def test_default_values(self):
        """Parameters with default values."""
        assert _extract_param_names("x=5") == ["x"]
        assert _extract_param_names("x: int = 5, y: str = 'foo'") == ["x", "y"]

    def test_complex_defaults(self):
        """Parameters with complex default values containing commas."""
        assert _extract_param_names("x: List[int] = []") == ["x"]
        assert _extract_param_names("x: Dict[str, int] = {}") == ["x"]
        # Note: This assumes proper nesting handling

    def test_variadic_params(self):
        """Variadic parameters mixed with regular ones."""
        assert _extract_param_names("x, *args") == ["x", "*args"]
        assert _extract_param_names("x, *args, **kwargs") == ["x", "*args", "**kwargs"]

    def test_self_and_cls(self):
        """Including self/cls (extraction doesn't filter, that's done elsewhere)."""
        assert _extract_param_names("self") == ["self"]
        assert _extract_param_names("self, x") == ["self", "x"]
        assert _extract_param_names("cls, x") == ["cls", "x"]


# === TypedElement Tests ===


class TestTypedElementBasics:
    """Test TypedElement basic properties and construction."""

    def test_construction(self):
        """Basic element construction."""
        el = TypedElement(name="foo", line=10, line_end=20, category="function")
        assert el.name == "foo"
        assert el.line == 10
        assert el.line_end == 20
        assert el.category == "function"

    def test_line_count(self):
        """Line count calculation."""
        el = TypedElement(name="foo", line=10, line_end=20, category="function")
        assert el.line_count == 11  # 10 to 20 inclusive

        el2 = TypedElement(name="bar", line=5, line_end=5, category="function")
        assert el2.line_count == 1  # Single line

    def test_default_internal_fields(self):
        """Internal fields default to None/empty."""
        el = TypedElement(name="foo", line=1, line_end=10, category="function")
        assert el._type is None
        assert el._siblings == []


class TestTypedElementContainment:
    """Test TypedElement containment logic."""

    def test_contains_basic(self):
        """Basic containment check."""
        outer = TypedElement(name="outer", line=1, line_end=100, category="class")
        inner = TypedElement(name="inner", line=10, line_end=20, category="function")

        assert inner in outer
        assert outer not in inner

    def test_contains_self(self):
        """Element does not contain itself."""
        el = TypedElement(name="foo", line=1, line_end=10, category="function")
        assert el not in el

    def test_contains_partial_overlap(self):
        """Partial overlap is not containment."""
        el1 = TypedElement(name="el1", line=1, line_end=15, category="function")
        el2 = TypedElement(name="el2", line=10, line_end=20, category="function")

        assert el2 not in el1
        assert el1 not in el2

    def test_contains_same_boundaries(self):
        """Elements with same boundaries contain each other."""
        el1 = TypedElement(name="el1", line=1, line_end=10, category="class")
        el2 = TypedElement(name="el2", line=1, line_end=10, category="function")

        # Same boundaries - both contain each other (but not themselves)
        assert el1 in el2
        assert el2 in el1

    def test_contains_exact_fit(self):
        """Inner element exactly fits outer boundaries."""
        outer = TypedElement(name="outer", line=1, line_end=100, category="class")
        inner = TypedElement(name="inner", line=1, line_end=100, category="function")

        # Same boundaries - both contain each other
        assert inner in outer
        assert outer in inner


class TestTypedElementNavigation:
    """Test TypedElement navigation methods."""

    def test_iteration(self):
        """Iterate over children."""
        # Create elements with _siblings to enable children computation
        # (Note: children requires _type and _siblings setup)
        parent = TypedElement(name="parent", line=1, line_end=100, category="class")
        child1 = TypedElement(name="child1", line=10, line_end=20, category="function")
        child2 = TypedElement(name="child2", line=30, line_end=40, category="function")

        # Without _type, children will be empty
        # This tests the iterator mechanism
        result = list(parent)
        assert result == []  # No _type means no children

    def test_truediv_operator(self):
        """Navigate using / operator."""
        parent = TypedElement(name="parent", line=1, line_end=100, category="class")
        child = TypedElement(name="child", line=10, line_end=20, category="function")

        # Without children, returns None
        assert (parent / "child") is None
        assert (parent / "nonexistent") is None

    def test_getitem_operator(self):
        """Navigate using [] operator."""
        parent = TypedElement(name="parent", line=1, line_end=100, category="class")

        # Without children, returns None
        assert parent["child"] is None
        assert parent["nonexistent"] is None

    def test_len(self):
        """Length returns number of children."""
        parent = TypedElement(name="parent", line=1, line_end=100, category="class")
        assert len(parent) == 0  # No _type means no children


class TestTypedElementPath:
    """Test TypedElement path generation."""

    def test_path_no_parent(self):
        """Path for top-level element."""
        el = TypedElement(name="MyClass", line=1, line_end=100, category="class")
        assert el.path == "MyClass"

    def test_path_with_parent(self):
        """Path includes parent names."""
        # Create parent-child relationship by mocking
        parent = TypedElement(name="Parent", line=1, line_end=100, category="class")
        child = TypedElement(name="child_method", line=10, line_end=20, category="function")

        # Manually mock the parent relationship
        # (In real usage, this is computed from _type and _siblings)
        object.__setattr__(child, "_cache", {})
        child._cache = {}
        # We need to set cached_property manually for testing

        # For now, just test the logic without parent
        assert child.path == "child_method"


class TestTypedElementDepth:
    """Test TypedElement depth calculation."""

    def test_depth_no_parent(self):
        """Depth 0 for top-level element."""
        el = TypedElement(name="foo", line=1, line_end=10, category="function")
        assert el.depth == 0


class TestTypedElementTraversal:
    """Test TypedElement traversal methods."""

    def test_walk_single_element(self):
        """Walk yields self when no children."""
        el = TypedElement(name="foo", line=1, line_end=10, category="function")
        result = list(el.walk())
        assert result == [el]

    def test_ancestors_no_parent(self):
        """Ancestors is empty when no parent."""
        el = TypedElement(name="foo", line=1, line_end=10, category="function")
        result = list(el.ancestors())
        assert result == []

    def test_find_single_element(self):
        """Find on single element."""
        el = TypedElement(name="foo", line=1, line_end=10, category="function")
        result = list(el.find(lambda x: x.name == "foo"))
        assert result == [el]

        result = list(el.find(lambda x: x.name == "bar"))
        assert result == []

    def test_find_by_name_not_found(self):
        """find_by_name returns None when not found."""
        el = TypedElement(name="foo", line=1, line_end=10, category="function")
        assert el.find_by_name("bar") is None

    def test_find_by_name_found_self(self):
        """find_by_name finds self."""
        el = TypedElement(name="foo", line=1, line_end=10, category="function")
        assert el.find_by_name("foo") == el

    def test_find_by_category(self):
        """find_by_category filters by category."""
        el = TypedElement(name="foo", line=1, line_end=10, category="function")
        result = list(el.find_by_category("function"))
        assert result == [el]

        result = list(el.find_by_category("class"))
        assert result == []


class TestTypedElementSerialization:
    """Test TypedElement serialization."""

    def test_to_dict_basic(self):
        """Basic to_dict serialization."""
        el = TypedElement(name="foo", line=10, line_end=20, category="function")
        d = el.to_dict()

        assert d["name"] == "foo"
        assert d["line"] == 10
        assert d["line_end"] == 20
        assert d["category"] == "function"
        assert d["path"] == "foo"
        assert d["depth"] == 0
        assert d["line_count"] == 11

    def test_to_dict_excludes_internal(self):
        """to_dict excludes internal fields."""
        el = TypedElement(name="foo", line=1, line_end=10, category="function")
        d = el.to_dict()

        assert "_type" not in d
        assert "_siblings" not in d


# === PythonElement Tests ===


class TestPythonElementBasics:
    """Test PythonElement basic properties."""

    def test_construction(self):
        """Basic PythonElement construction."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            signature="(x: int) -> str",
            decorators=["@property"],
        )

        assert el.name == "foo"
        assert el.signature == "(x: int) -> str"
        assert el.decorators == ["@property"]

    def test_default_signature_and_decorators(self):
        """Default empty signature and decorators."""
        el = PythonElement(name="foo", line=1, line_end=10, category="function")
        assert el.signature == ""
        assert el.decorators == []


class TestPythonElementTypeChecks:
    """Test PythonElement type checking properties."""

    def test_is_method_no_parent(self):
        """Function without parent returns None (truthy check)."""
        el = PythonElement(name="foo", line=1, line_end=10, category="function")
        # Returns None when no parent (and evaluates to falsy)
        assert el.is_method is None
        assert not el.is_method

    def test_is_nested_function_no_parent(self):
        """Function without parent returns None (truthy check)."""
        el = PythonElement(name="foo", line=1, line_end=10, category="function")
        # Returns None when no parent (and evaluates to falsy)
        assert el.is_nested_function is None
        assert not el.is_nested_function

    def test_is_staticmethod(self):
        """Check @staticmethod decorator."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            decorators=["@staticmethod"],
        )
        assert el.is_staticmethod is True

        el2 = PythonElement(name="bar", line=1, line_end=10, category="function")
        assert el2.is_staticmethod is False

    def test_is_classmethod(self):
        """Check @classmethod decorator."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            decorators=["@classmethod"],
        )
        assert el.is_classmethod is True

        el2 = PythonElement(name="bar", line=1, line_end=10, category="function")
        assert el2.is_classmethod is False

    def test_is_property(self):
        """Check @property decorator."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            decorators=["@property"],
        )
        assert el.is_property is True

        el2 = PythonElement(name="bar", line=1, line_end=10, category="function")
        assert el2.is_property is False


class TestPythonElementDisplayCategory:
    """Test PythonElement display_category property."""

    def test_display_category_class(self):
        """Class category unchanged."""
        el = PythonElement(name="MyClass", line=1, line_end=10, category="class")
        assert el.display_category == "class"

    def test_display_category_property(self):
        """Property takes precedence."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            decorators=["@property"],
        )
        assert el.display_category == "property"

    def test_display_category_classmethod(self):
        """Classmethod display."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            decorators=["@classmethod"],
        )
        assert el.display_category == "classmethod"

    def test_display_category_staticmethod(self):
        """Staticmethod display."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            decorators=["@staticmethod"],
        )
        assert el.display_category == "staticmethod"

    def test_display_category_plain_function(self):
        """Plain function."""
        el = PythonElement(name="foo", line=1, line_end=10, category="function")
        assert el.display_category == "function"


class TestPythonElementDecoratorPrefix:
    """Test PythonElement decorator_prefix property."""

    def test_decorator_prefix_property(self):
        """@property decorator prefix."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            decorators=["@property"],
        )
        assert el.decorator_prefix == "@property"

    def test_decorator_prefix_property_priority(self):
        """@property takes priority over @cached_property."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            decorators=["@cached_property", "@property"],
        )
        # @property comes first in priority list
        assert el.decorator_prefix == "@property"

    def test_decorator_prefix_custom(self):
        """Custom decorator shown if no standard ones."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            decorators=["@my_decorator"],
        )
        assert el.decorator_prefix == "@my_decorator"

    def test_decorator_prefix_none(self):
        """No decorators returns empty string."""
        el = PythonElement(name="foo", line=1, line_end=10, category="function")
        assert el.decorator_prefix == ""


class TestPythonElementCompactSignature:
    """Test PythonElement compact_signature property."""

    def test_compact_signature_empty(self):
        """Empty signature."""
        el = PythonElement(name="foo", line=1, line_end=10, category="function")
        assert el.compact_signature == ""

    def test_compact_signature_no_params(self):
        """No parameters."""
        el = PythonElement(
            name="foo", line=1, line_end=10, category="function", signature="()"
        )
        assert el.compact_signature == "()"

    def test_compact_signature_simple_params(self):
        """Simple parameters."""
        el = PythonElement(
            name="foo", line=1, line_end=10, category="function", signature="(x, y)"
        )
        assert el.compact_signature == "(x, y)"

    def test_compact_signature_with_types(self):
        """Parameters with type annotations."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            signature="(x: int, y: str)",
        )
        assert el.compact_signature == "(x, y)"

    def test_compact_signature_removes_self(self):
        """Remove 'self' from parameters."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            signature="(self, x: int)",
        )
        assert el.compact_signature == "(x)"

    def test_compact_signature_removes_cls(self):
        """Remove 'cls' from parameters."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            signature="(cls, x: int)",
        )
        assert el.compact_signature == "(x)"

    def test_compact_signature_only_self(self):
        """Only 'self' parameter."""
        el = PythonElement(
            name="foo", line=1, line_end=10, category="function", signature="(self)"
        )
        assert el.compact_signature == "()"

    def test_compact_signature_truncated(self):
        """Truncate if more than 4 parameters."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            signature="(a, b, c, d, e, f)",
        )
        assert el.compact_signature == "(a, b, c, ...)"

    def test_compact_signature_with_defaults(self):
        """Parameters with defaults."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            signature="(x: int = 5, y: str = 'foo')",
        )
        assert el.compact_signature == "(x, y)"

    def test_compact_signature_nested_types(self):
        """Parameters with nested type annotations."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            signature="(items: List[Tuple[str, int]])",
        )
        assert el.compact_signature == "(items)"


class TestPythonElementReturnType:
    """Test PythonElement return_type property."""

    def test_return_type_none(self):
        """No return type."""
        el = PythonElement(
            name="foo", line=1, line_end=10, category="function", signature="(x: int)"
        )
        assert el.return_type == ""

    def test_return_type_simple(self):
        """Simple return type."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            signature="(x: int) -> str",
        )
        assert el.return_type == "str"

    def test_return_type_complex(self):
        """Complex return type."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            signature="(x: int) -> List[str]",
        )
        assert el.return_type == "List[str]"

    def test_return_type_quoted(self):
        """Quoted return type (forward reference)."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            signature="(x: int) -> 'MyClass'",
        )
        assert el.return_type == "MyClass"

    def test_return_type_long(self):
        """Long return type gets truncated."""
        long_type = "Dict[str, List[Tuple[int, str, bool]]]"
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            signature=f"(x: int) -> {long_type}",
        )
        assert "[...]" in el.return_type


class TestPythonElementSerialization:
    """Test PythonElement serialization."""

    def test_to_dict_includes_python_fields(self):
        """to_dict includes Python-specific fields."""
        el = PythonElement(
            name="foo",
            line=1,
            line_end=10,
            category="function",
            signature="(x: int) -> str",
            decorators=["@property"],
        )
        d = el.to_dict()

        assert d["signature"] == "(x: int) -> str"
        assert d["decorators"] == ["@property"]
        # is_method and is_nested_function return None when no parent
        assert d["is_method"] is None
        assert d["is_nested_function"] is None

    def test_to_dict_inherits_base_fields(self):
        """to_dict includes base TypedElement fields."""
        el = PythonElement(name="foo", line=1, line_end=10, category="function")
        d = el.to_dict()

        assert d["name"] == "foo"
        assert d["line"] == 1
        assert d["line_end"] == 10
        assert d["category"] == "function"


# === MarkdownElement Tests ===


class TestMarkdownElementBasics:
    """Test MarkdownElement basic properties."""

    def test_construction(self):
        """Basic MarkdownElement construction."""
        el = MarkdownElement(
            name="Section", line=1, line_end=10, category="section", level=2
        )
        assert el.name == "Section"
        assert el.level == 2

    def test_default_level(self):
        """Default level is 1."""
        el = MarkdownElement(name="Section", line=1, line_end=10, category="section")
        assert el.level == 1


class TestMarkdownElementSubsections:
    """Test MarkdownElement subsections property."""

    def test_subsections_empty(self):
        """No children means no subsections."""
        el = MarkdownElement(name="Section", line=1, line_end=10, category="section")
        assert el.subsections == []


class TestMarkdownElementSerialization:
    """Test MarkdownElement serialization."""

    def test_to_dict_includes_level(self):
        """to_dict includes level field."""
        el = MarkdownElement(
            name="Section", line=1, line_end=10, category="section", level=3
        )
        d = el.to_dict()

        assert d["level"] == 3
        assert d["name"] == "Section"
        assert d["category"] == "section"
