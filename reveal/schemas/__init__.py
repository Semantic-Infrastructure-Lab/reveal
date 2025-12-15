"""Type definitions for reveal.

This package contains RevealType definitions for different file formats.
Types are auto-registered when imported.

Usage:
    # Import registers the types automatically
    from reveal.schemas import python

    # Or import specific types
    from reveal.schemas.python import PythonType

    # Core classes from type_system module
    from reveal.type_system import EntityDef, RevealType, TypeRegistry
"""

# Re-export core classes for convenience
from ..type_system import EntityDef, RevealType, TypeRegistry

__all__ = ["EntityDef", "RevealType", "TypeRegistry"]
