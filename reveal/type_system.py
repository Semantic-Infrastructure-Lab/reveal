"""Type-First Architecture for Reveal.

This module is the source of truth that drives:
- Extension -> adapter mapping (.py -> PythonType)
- URI scheme -> adapter mapping (py:// -> PythonType)
- Containment rules (class contains method)
- Element navigation patterns

Usage:
    from reveal.type_system import TypeRegistry, RevealType, EntityDef

    # Register a type
    TypeRegistry.register(PythonType)

    # Look up by extension or scheme
    reveal_type = TypeRegistry.from_extension('.py')
    reveal_type = TypeRegistry.from_scheme('py')

Design: internal-docs/planning/CONTAINMENT_MODEL_DESIGN.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from .elements import TypedElement

logger = logging.getLogger(__name__)


@dataclass
class EntityDef:
    """Defines what an element type can contain.

    Used to declare containment rules for element navigation.
    For example, a Python class contains methods and attributes.

    Args:
        contains: List of entity type names this entity can contain
        properties: Property names and their types for this entity
        inherits: Parent entity type (for type inheritance)

    Examples:
        # A class contains methods and nested classes
        class_def = EntityDef(
            contains=['method', 'attribute', 'class'],
            properties={'name': str, 'line': int, 'bases': list},
        )

        # A method inherits from function
        method_def = EntityDef(
            inherits='function',
            properties={'decorators': list},
        )
    """

    contains: List[str] = field(default_factory=list)
    properties: Dict[str, type] = field(default_factory=dict)
    inherits: Optional[str] = None


@dataclass
class RevealType:
    """Complete type definition for a file format.

    A RevealType encapsulates everything reveal needs to know about
    a file format: which extensions it handles, what URI scheme to use,
    what entities exist and their containment rules, and which adapters
    to use for different analysis modes.

    Args:
        name: Unique identifier for this type (e.g., 'python', 'markdown')
        extensions: File extensions this type handles (e.g., ['.py', '.pyw'])
        scheme: URI scheme for the rich adapter (e.g., 'py' for py://)
        entities: Dict mapping entity names to their definitions
        adapters: Dict mapping mode names to adapter class names
        element_class: Class to use for typed elements (default: TypedElement)

    Examples:
        PythonType = RevealType(
            name='python',
            extensions=['.py', '.pyw', '.pyi'],
            scheme='py',
            entities={
                'module': EntityDef(contains=['class', 'function', 'import']),
                'class': EntityDef(
                    contains=['method', 'attribute', 'class'],
                    properties={'name': str, 'line': int, 'bases': list},
                ),
                'function': EntityDef(
                    contains=['function', 'variable'],
                    properties={'name': str, 'line': int, 'signature': str},
                ),
                'method': EntityDef(inherits='function'),
            },
            adapters={
                'structure': 'TreeSitterAnalyzer',
                'deep': 'PythonDeepAdapter',
            },
        )
    """

    name: str
    extensions: List[str]
    scheme: str

    # What elements exist and their containment rules
    entities: Dict[str, EntityDef] = field(default_factory=dict)

    # Adapter chain: mode -> adapter class name
    adapters: Dict[str, str] = field(default_factory=dict)

    # Element class for typed navigation (set at runtime to avoid circular import)
    element_class: Optional[Type[TypedElement]] = None

    def get_entity(self, name: str) -> Optional[EntityDef]:
        """Get entity definition by name, resolving inheritance.

        Args:
            name: Entity type name (e.g., 'function', 'method')

        Returns:
            EntityDef with inherited properties merged, or None if not found
        """
        entity = self.entities.get(name)
        if not entity:
            return None

        # If it inherits, merge with parent
        if entity.inherits:
            parent = self.get_entity(entity.inherits)
            if parent:
                # Merge: child overrides parent
                merged_contains = list(set(parent.contains + entity.contains))
                merged_properties = {**parent.properties, **entity.properties}
                return EntityDef(
                    contains=merged_contains,
                    properties=merged_properties,
                    inherits=entity.inherits,
                )

        return entity

    def can_contain(self, parent_category: str, child_category: str) -> bool:
        """Check if parent category can contain child category.

        Args:
            parent_category: The parent element's category (e.g., 'class')
            child_category: The child element's category (e.g., 'method')

        Returns:
            True if parent can contain child according to entity definitions
        """
        entity = self.get_entity(parent_category)
        if not entity:
            return False
        return child_category in entity.contains


class TypeRegistry:
    """Central registry mapping extensions and schemes to types.

    This is a class-level registry (singleton pattern) that maps:
    - File extensions (.py, .md) to RevealType
    - URI schemes (py://, md://) to RevealType

    Usage:
        # Register a type
        TypeRegistry.register(PythonType)

        # Look up by extension
        reveal_type = TypeRegistry.from_extension('.py')

        # Look up by URI scheme
        reveal_type = TypeRegistry.from_scheme('py')

        # Get all registered types
        all_types = TypeRegistry.all()
    """

    _types: Dict[str, RevealType] = {}
    _by_extension: Dict[str, RevealType] = {}
    _by_scheme: Dict[str, RevealType] = {}

    @classmethod
    def register(cls, reveal_type: RevealType) -> None:
        """Register a RevealType.

        Registers the type and creates extension/scheme lookups.

        Args:
            reveal_type: The RevealType to register
        """
        cls._types[reveal_type.name] = reveal_type

        for ext in reveal_type.extensions:
            ext_lower = ext.lower()
            if ext_lower in cls._by_extension:
                logger.warning(
                    f"Extension '{ext}' already registered to "
                    f"'{cls._by_extension[ext_lower].name}', "
                    f"overwriting with '{reveal_type.name}'"
                )
            cls._by_extension[ext_lower] = reveal_type

        if reveal_type.scheme:
            scheme_lower = reveal_type.scheme.lower()
            if scheme_lower in cls._by_scheme:
                logger.warning(
                    f"Scheme '{reveal_type.scheme}' already registered to "
                    f"'{cls._by_scheme[scheme_lower].name}', "
                    f"overwriting with '{reveal_type.name}'"
                )
            cls._by_scheme[scheme_lower] = reveal_type

        logger.debug(
            f"Registered type '{reveal_type.name}' "
            f"(extensions: {reveal_type.extensions}, scheme: {reveal_type.scheme})"
        )

    @classmethod
    def from_extension(cls, ext: str) -> Optional[RevealType]:
        """Look up RevealType by file extension.

        Args:
            ext: File extension including dot (e.g., '.py')

        Returns:
            RevealType if found, None otherwise
        """
        return cls._by_extension.get(ext.lower())

    @classmethod
    def from_scheme(cls, scheme: str) -> Optional[RevealType]:
        """Look up RevealType by URI scheme.

        Args:
            scheme: URI scheme without :// (e.g., 'py')

        Returns:
            RevealType if found, None otherwise
        """
        return cls._by_scheme.get(scheme.lower())

    @classmethod
    def get(cls, name: str) -> Optional[RevealType]:
        """Look up RevealType by name.

        Args:
            name: Type name (e.g., 'python')

        Returns:
            RevealType if found, None otherwise
        """
        return cls._types.get(name)

    @classmethod
    def all(cls) -> Dict[str, RevealType]:
        """Get all registered types.

        Returns:
            Dict mapping type names to RevealType instances
        """
        return dict(cls._types)

    @classmethod
    def extensions(cls) -> Dict[str, RevealType]:
        """Get all extension mappings.

        Returns:
            Dict mapping extensions to RevealType instances
        """
        return dict(cls._by_extension)

    @classmethod
    def schemes(cls) -> Dict[str, RevealType]:
        """Get all scheme mappings.

        Returns:
            Dict mapping schemes to RevealType instances
        """
        return dict(cls._by_scheme)

    @classmethod
    def clear(cls) -> None:
        """Clear all registered types.

        Primarily useful for testing.
        """
        cls._types.clear()
        cls._by_extension.clear()
        cls._by_scheme.clear()
