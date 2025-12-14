"""Typed structure container with Pythonic navigation.

Provides a container for typed elements that wires up containment
relationships and offers intuitive navigation.

Usage:
    from reveal.structure import TypedStructure
    from reveal.elements import TypedElement

    # Create structure
    structure = TypedStructure(
        path='app.py',
        reveal_type=PythonType,
        elements=[...],
    )

    # Navigate to element
    my_class = structure / 'MyClass'
    method = my_class / 'process'

    # Or use path string
    method = structure['MyClass.process']

    # Iterate
    for func in structure.functions:
        print(func.name)

    # Walk all elements
    for el in structure.walk():
        print(el.path)

Design: internal-docs/planning/CONTAINMENT_MODEL_DESIGN.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Callable, Dict, Iterator, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .type_system import RevealType

from .elements import TypedElement


@dataclass
class TypedStructure:
    """Container for typed elements with navigation.

    A TypedStructure represents the analyzed structure of a file,
    with typed elements that can navigate their containment relationships.

    On creation, automatically wires up:
    - _type reference on each element (for containment rules)
    - _siblings reference on each element (for containment computation)

    Args:
        path: File path that was analyzed
        reveal_type: The RevealType defining this file's structure
        elements: List of all elements in the file
    """

    path: str
    reveal_type: Optional[RevealType]
    elements: List[TypedElement] = field(default_factory=list)

    def __post_init__(self):
        """Wire up sibling references for containment computation."""
        for el in self.elements:
            el._type = self.reveal_type
            el._siblings = self.elements

    # === Category Accessors ===

    @cached_property
    def functions(self) -> List[TypedElement]:
        """All elements with category 'function'."""
        return [e for e in self.elements if e.category == "function"]

    @cached_property
    def classes(self) -> List[TypedElement]:
        """All elements with category 'class'."""
        return [e for e in self.elements if e.category == "class"]

    @cached_property
    def imports(self) -> List[TypedElement]:
        """All elements with category 'import'."""
        return [e for e in self.elements if e.category == "import"]

    @cached_property
    def sections(self) -> List[TypedElement]:
        """All elements with category 'section' (for Markdown)."""
        return [e for e in self.elements if e.category == "section"]

    def by_category(self, category: str) -> List[TypedElement]:
        """Get all elements with a specific category."""
        return [e for e in self.elements if e.category == category]

    # === Top-level (no parent) ===

    @cached_property
    def roots(self) -> List[TypedElement]:
        """Top-level elements only (those with no parent)."""
        return [e for e in self.elements if e.parent is None]

    # === Navigation ===

    def __truediv__(self, name: str) -> Optional[TypedElement]:
        """Navigate from root: structure / 'MyClass'."""
        for el in self.roots:
            if el.name == name:
                return el
        return None

    def __getitem__(self, path: str) -> Optional[TypedElement]:
        """Path access: structure['MyClass.process']."""
        parts = path.split(".")
        current = self / parts[0]
        for part in parts[1:]:
            if current is None:
                return None
            current = current / part
        return current

    def __len__(self) -> int:
        """Return total number of elements."""
        return len(self.elements)

    def __iter__(self) -> Iterator[TypedElement]:
        """Iterate over all elements."""
        return iter(self.elements)

    def __bool__(self) -> bool:
        """Return True if structure has any elements."""
        return len(self.elements) > 0

    # === Traversal ===

    def walk(self) -> Iterator[TypedElement]:
        """All elements, depth-first from roots."""
        for root in self.roots:
            yield from root.walk()

    def walk_flat(self) -> Iterator[TypedElement]:
        """All elements in original order (not tree order)."""
        yield from sorted(self.elements, key=lambda e: e.line)

    # === Queries ===

    def find(
        self, predicate: Optional[Callable[[TypedElement], bool]] = None, **kwargs
    ) -> Iterator[TypedElement]:
        """Find elements by predicate or properties.

        Can use either a predicate function or keyword arguments
        for property matching.

        Examples:
            # By predicate
            list(structure.find(lambda e: e.depth > 2))

            # By properties
            list(structure.find(category='function', depth=0))
        """
        for el in self.elements:
            if predicate and not predicate(el):
                continue

            if kwargs:
                matches = all(
                    getattr(el, k, None) == v for k, v in kwargs.items()
                )
                if not matches:
                    continue

            yield el

    def find_by_name(self, name: str) -> Optional[TypedElement]:
        """Find first element with matching name."""
        for el in self.elements:
            if el.name == name:
                return el
        return None

    def find_by_line(self, line: int) -> Optional[TypedElement]:
        """Find innermost element containing a line number."""
        candidates = [
            el for el in self.elements
            if el.line <= line <= el.line_end
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda e: e.line_end - e.line)

    # === Statistics ===

    @cached_property
    def stats(self) -> Dict[str, int]:
        """Statistics about the structure."""
        counts: Dict[str, int] = {}
        max_depth = 0

        for el in self.elements:
            counts[el.category] = counts.get(el.category, 0) + 1
            max_depth = max(max_depth, el.depth)

        return {
            "total": len(self.elements),
            "roots": len(self.roots),
            "max_depth": max_depth,
            **counts,
        }

    # === Serialization ===

    def to_dict(self) -> dict:
        """Convert to dict, suitable for JSON serialization."""
        return {
            "path": self.path,
            "type": self.reveal_type.name if self.reveal_type else None,
            "elements": [el.to_dict() for el in self.elements],
            "stats": self.stats,
        }

    def to_tree(self) -> dict:
        """Convert to nested tree structure."""
        def element_to_tree(el: TypedElement) -> dict:
            node = el.to_dict()
            children = el.children
            if children:
                node["children"] = [element_to_tree(c) for c in children]
            return node

        return {
            "path": self.path,
            "type": self.reveal_type.name if self.reveal_type else None,
            "roots": [element_to_tree(r) for r in self.roots],
        }
