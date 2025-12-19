"""Typed elements with Pythonic navigation.

Provides navigable, typed elements for code structure analysis.
Elements know their type, can compute their containment relationships,
and support intuitive Python operators for navigation.

Usage:
    from reveal.elements import TypedElement, PythonElement

    # Elements support Pythonic navigation
    for method in my_class.children:
        print(method.name)

    # Path navigation with /
    helper = structure / 'MyClass' / 'process' / 'inner_helper'

    # Check containment
    if method in my_class:
        print("method is inside my_class")

    # Walk all descendants
    for el in my_class.walk():
        print(el.path)

Design: internal-docs/planning/CONTAINMENT_MODEL_DESIGN.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Callable, Iterator, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .type_system import RevealType


@dataclass
class TypedElement:
    """Base class for navigable, typed elements.

    An element represents a semantic code construct (function, class, section, etc.)
    with line range information that enables containment computation.

    Key insight: Containment is computed from EntityDef.contains + line ranges.
    No storage of parent/children needed - it's all computed from line ranges.

    Args:
        name: Element name (function name, class name, etc.)
        line: Starting line number (1-indexed)
        line_end: Ending line number (inclusive)
        category: Element type ('function', 'class', 'method', 'section', etc.)

    Internal attributes (set by TypedStructure):
        _type: The RevealType for containment rules
        _siblings: All elements in the same structure (for containment computation)
    """

    name: str
    line: int
    line_end: int
    category: str

    # Internal references (not serialized, set by TypedStructure)
    _type: Optional[RevealType] = field(repr=False, default=None, compare=False)
    _siblings: List[TypedElement] = field(
        repr=False, default_factory=list, compare=False
    )

    # === Containment (computed from EntityDef.contains + line ranges) ===

    @cached_property
    def children(self) -> List[TypedElement]:
        """Elements contained within this one.

        Computed by finding siblings that:
        1. Are of a category this element can contain (per EntityDef)
        2. Have line ranges entirely within this element's line range

        Returns:
            List of direct child elements (not grandchildren)
        """
        if not self._type:
            return []

        # What categories can this element contain?
        entity_def = self._type.get_entity(self.category)
        if not entity_def:
            return []
        allowed = set(entity_def.contains)

        # Find siblings that are inside our line range and allowed type
        candidates = [
            el
            for el in self._siblings
            if el is not self
            and el.category in allowed
            and el in self  # Uses __contains__
        ]

        # Filter to direct children only (no intermediate container)
        direct_children = []
        for candidate in candidates:
            is_grandchild = any(
                other is not candidate and candidate in other
                for other in candidates
            )
            if not is_grandchild:
                direct_children.append(candidate)

        return direct_children

    @cached_property
    def parent(self) -> Optional[TypedElement]:
        """The element that directly contains this one.

        Finds the innermost container (smallest line range) that:
        1. Has this element's line range entirely within its range
        2. Can contain this element's category (per EntityDef)

        Returns:
            Parent element or None if top-level
        """
        if not self._type:
            return None

        candidates = []
        for el in self._siblings:
            if el is self:
                continue
            if self not in el:
                continue

            entity_def = self._type.get_entity(el.category)
            if entity_def and self.category in entity_def.contains:
                candidates.append(el)

        if candidates:
            return min(candidates, key=lambda e: e.line_end - e.line)
        return None

    @property
    def depth(self) -> int:
        """Nesting depth (0 = top-level)."""
        if self.parent is None:
            return 0
        return self.parent.depth + 1

    @property
    def line_count(self) -> int:
        """Number of lines this element spans."""
        return self.line_end - self.line + 1

    # === Python Magic Methods ===

    def __contains__(self, other: TypedElement) -> bool:
        """Support 'child in parent' syntax."""
        if other is self:
            return False
        return self.line <= other.line and other.line_end <= self.line_end

    def __iter__(self) -> Iterator[TypedElement]:
        """Iterate over direct children."""
        return iter(self.children)

    def __truediv__(self, name: str) -> Optional[TypedElement]:
        """Navigate via '/': element / 'child_name'."""
        for child in self.children:
            if child.name == name:
                return child
        return None

    def __getitem__(self, key: str) -> Optional[TypedElement]:
        """Navigate via []: element['child_name']."""
        return self / key

    def __len__(self) -> int:
        """Return number of direct children."""
        return len(self.children)

    # === Traversal ===

    def walk(self) -> Iterator[TypedElement]:
        """Depth-first traversal of this element and all descendants."""
        yield self
        for child in self.children:
            yield from child.walk()

    def ancestors(self) -> Iterator[TypedElement]:
        """Walk up the containment chain."""
        current = self.parent
        while current:
            yield current
            current = current.parent

    def find(self, predicate: Callable[[TypedElement], bool]) -> Iterator[TypedElement]:
        """Find descendants matching predicate."""
        for el in self.walk():
            if predicate(el):
                yield el

    def find_by_name(self, name: str) -> Optional[TypedElement]:
        """Find first descendant with matching name."""
        for el in self.walk():
            if el.name == name:
                return el
        return None

    def find_by_category(self, category: str) -> Iterator[TypedElement]:
        """Find all descendants with matching category."""
        return self.find(lambda el: el.category == category)

    # === Path ===

    @cached_property
    def path(self) -> str:
        """Full path from root: 'MyClass.process.helper'."""
        if self.parent:
            return f"{self.parent.path}.{self.name}"
        return self.name

    # === Serialization ===

    def to_dict(self) -> dict:
        """Convert to dict, excluding internal references."""
        return {
            "name": self.name,
            "line": self.line,
            "line_end": self.line_end,
            "category": self.category,
            "path": self.path,
            "depth": self.depth,
            "line_count": self.line_count,
        }


@dataclass
class PythonElement(TypedElement):
    """Python-specific element with extra properties."""

    signature: str = ""
    decorators: List[str] = field(default_factory=list)

    @property
    def is_method(self) -> bool:
        """True if this function is a method (inside a class)."""
        return (self.category == "function" and self.parent and
                self.parent.category == "class")

    @property
    def is_nested_function(self) -> bool:
        """True if this function is nested inside another function."""
        return (self.category == "function" and self.parent and
                self.parent.category == "function")

    @property
    def is_staticmethod(self) -> bool:
        """True if decorated with @staticmethod."""
        return "@staticmethod" in self.decorators

    @property
    def is_classmethod(self) -> bool:
        """True if decorated with @classmethod."""
        return "@classmethod" in self.decorators

    @property
    def is_property(self) -> bool:
        """True if decorated with @property."""
        return "@property" in self.decorators

    @cached_property
    def display_category(self) -> str:
        """Semantic category for display (method, property, classmethod, etc.)."""
        if self.category != "function":
            return self.category

        if self.is_property:
            return "property"
        if self.is_classmethod:
            return "classmethod"
        if self.is_staticmethod:
            return "staticmethod"
        if self.is_method:
            return "method"
        if self.is_nested_function:
            return "function"  # nested, but still a function
        return "function"

    @cached_property
    def decorator_prefix(self) -> str:
        """Decorator prefix for display (e.g., '@cached_property')."""
        # Priority: show the most semantically meaningful decorator
        priority = ["@property", "@cached_property", "@classmethod", "@staticmethod"]
        for dec in priority:
            if dec in self.decorators:
                return dec
        # Show first non-standard decorator if any
        for dec in self.decorators:
            if dec not in priority:
                return dec
        return ""

    @cached_property
    def compact_signature(self) -> str:
        """Compact signature for display (truncated params)."""
        if not self.signature:
            return ""

        sig = self.signature.strip()

        # Extract just the params part: (x, y, z) -> "x, y, z"
        if sig.startswith("("):
            # Find matching closing paren (handle nested brackets)
            depth = 0
            end = 0
            for i, c in enumerate(sig):
                if c in "([{":
                    depth += 1
                elif c in ")]}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break

            # Extract parameter list (handle nested parens)
            if end > 0:
                params = sig[1:end]
            elif sig.endswith(")"):
                params = sig[1:-1]
            else:
                params = sig[1:]

            # Remove self/cls
            params = params.strip()
            if params.startswith("self"):
                params = params[4:].lstrip(",").strip()
            elif params.startswith("cls"):
                params = params[3:].lstrip(",").strip()

            # Split on commas, respecting brackets
            simplified = []
            current = ""
            depth = 0
            for c in params:
                if c in "([{":
                    depth += 1
                    current += c
                elif c in ")]}":
                    depth -= 1
                    current += c
                elif c == "," and depth == 0:
                    # End of parameter
                    param = current.strip()
                    if param:
                        # Get just the name (before : or =)
                        name = param.split(":")[0].split("=")[0].strip()
                        if name.startswith("*"):
                            simplified.append(name)
                        elif name:
                            simplified.append(name)
                    current = ""
                else:
                    current += c

            # Don't forget last parameter
            param = current.strip()
            if param:
                name = param.split(":")[0].split("=")[0].strip()
                if name.startswith("*"):
                    simplified.append(name)
                elif name:
                    simplified.append(name)

            # Truncate if too many
            if len(simplified) > 4:
                return f"({', '.join(simplified[:3])}, ...)"
            elif simplified:
                return f"({', '.join(simplified)})"
            return "()"

        return ""

    @cached_property
    def return_type(self) -> str:
        """Extract return type from signature."""
        if not self.signature:
            return ""

        sig = self.signature.strip()
        if " -> " in sig:
            ret = sig.split(" -> ", 1)[1].strip()
            # Clean up quotes
            ret = ret.strip('"').strip("'")
            # Simplify long types
            if len(ret) > 25:
                # Try to get just the main type
                if "[" in ret:
                    ret = ret.split("[")[0] + "[...]"
            return ret
        return ""

    def to_dict(self) -> dict:
        """Convert to dict with Python-specific fields."""
        d = super().to_dict()
        d["signature"] = self.signature
        d["decorators"] = self.decorators
        d["is_method"] = self.is_method
        d["is_nested_function"] = self.is_nested_function
        return d


@dataclass
class MarkdownElement(TypedElement):
    """Markdown-specific element."""

    level: int = 1

    @property
    def subsections(self) -> List[MarkdownElement]:
        """Direct child sections."""
        return [c for c in self.children if c.category == "section"]

    def to_dict(self) -> dict:
        """Convert to dict with Markdown-specific fields."""
        d = super().to_dict()
        d["level"] = self.level
        return d
