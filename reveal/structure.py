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


# Map analyzer output keys (plural) to category names (singular)
_CATEGORY_MAP = {
    "functions": "function",
    "classes": "class",
    "imports": "import",
    "structs": "struct",
    "sections": "section",
    "headings": "section",
    "attributes": "attribute",
    "variables": "variable",
    "methods": "method",
    "code_blocks": "code_block",
    "links": "link",
    # Add more as needed
}


def _parse_import_name(content: str) -> str:
    """Extract module name from import statement.

    Examples:
        'from dataclasses import dataclass' -> 'dataclasses'
        'from typing import Dict, List' -> 'typing'
        'import os' -> 'os'
        'import os.path' -> 'os.path'
        'from . import utils' -> '.utils'
        'from ..core import base' -> '..core'
    """
    if not content:
        return ""

    content = content.strip()

    # "from X import Y" -> X
    if content.startswith("from "):
        parts = content[5:].split(" import", 1)
        if parts:
            return parts[0].strip()

    # "import X" or "import X as Y" -> X
    if content.startswith("import "):
        rest = content[7:].strip()
        # Handle "import X as Y"
        if " as " in rest:
            rest = rest.split(" as ")[0].strip()
        # Handle "import X, Y, Z" -> just first
        if "," in rest:
            rest = rest.split(",")[0].strip()
        return rest

    return ""


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

    # === Factory Methods ===

    @classmethod
    def from_analyzer_output(
        cls,
        structure_dict: Dict[str, list],
        path: str,
        reveal_type: Optional["RevealType"] = None,
    ) -> "TypedStructure":
        """Create TypedStructure from raw analyzer output.

        Converts the dict-based output from TreeSitterAnalyzer or other
        analyzers into typed elements with containment relationships.

        Args:
            structure_dict: Raw output from analyzer.get_structure(),
                            e.g. {'functions': [...], 'classes': [...]}
            path: File path that was analyzed
            reveal_type: Optional RevealType for containment rules.
                         If None, auto-detects from file extension.

        Returns:
            TypedStructure with typed, navigable elements

        Example:
            structure = analyzer.get_structure()
            typed = TypedStructure.from_analyzer_output(
                structure, 'app.py', PythonType
            )
            for func in typed.functions:
                print(func.name, func.parent)
        """
        from pathlib import Path as PathLib

        # Auto-detect type from extension if not provided
        if reveal_type is None:
            from .type_system import TypeRegistry
            ext = PathLib(path).suffix.lower()
            reveal_type = TypeRegistry.from_extension(ext)

        # Get element class from type, or use base TypedElement
        element_class = TypedElement
        if reveal_type and reveal_type.element_class:
            element_class = reveal_type.element_class

        elements: List[TypedElement] = []

        for key, items in structure_dict.items():
            # Skip private/meta keys
            if key.startswith("_"):
                continue

            # Map plural key to singular category
            category = _CATEGORY_MAP.get(key, key.rstrip("s"))

            # Skip if items is not a list
            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue

                # Required fields
                name = item.get("name", "")
                line = item.get("line", 0)
                line_end = item.get("line_end", line)

                # For imports, parse module name from content if name is empty
                if category == "import" and not name:
                    content = item.get("content", "")
                    name = _parse_import_name(content)

                # Create element with appropriate class
                el = element_class(
                    name=name,
                    line=line,
                    line_end=line_end,
                    category=category,
                )

                # Copy additional properties from item (skip computed properties)
                skip_props = {"name", "line", "line_end", "line_count", "depth"}
                for prop_key, prop_value in item.items():
                    if prop_key in skip_props:
                        continue
                    # Only set if it's a data attribute, not a property
                    if hasattr(el, prop_key):
                        try:
                            setattr(el, prop_key, prop_value)
                        except AttributeError:
                            # Skip computed properties that can't be set
                            pass

                elements.append(el)

        return cls(path=path, reveal_type=reveal_type, elements=elements)

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
