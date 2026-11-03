"""Import analysis rules.

Shared constants and utilities for import-related rules.
"""

from ...conventions import PYTHON_STDLIB

# Python standard library top-level names, used for shadowing (I004), unresolvable
# imports (B005) and import classification. One list, owned by `reveal.conventions`.
STDLIB_MODULES = PYTHON_STDLIB

__all__ = ['STDLIB_MODULES']
