"""Import analysis framework for reveal.

This module provides language-agnostic import graph analysis for detecting:
- Unused imports
- Circular dependencies
- Layer violations

Core types are in types.py; language-specific extractors are in submodules.
"""

# Import core types from types.py (avoids circular imports)
from .types import ImportStatement, ImportGraph


# Import extractors and layer config after core types are defined (avoid circular imports)
from .layers import LayerRule, LayerConfig, load_layer_config

# Import extractor classes to trigger @register_extractor decorator
# This populates the registry in base.py
from .python import PythonExtractor, extract_python_imports, extract_python_symbols
from .javascript import JavaScriptExtractor, extract_js_imports
from .go import GoExtractor, extract_go_imports
from .rust import RustExtractor, extract_rust_imports

# Import base registry functions
from .base import (
    LanguageExtractor,
    get_extractor,
    get_all_extensions,
    get_supported_languages,
)


__all__ = [
    # Core types
    'ImportStatement',
    'ImportGraph',
    # Layer config
    'LayerRule',
    'LayerConfig',
    'load_layer_config',
    # Base extractor infrastructure
    'LanguageExtractor',
    'get_extractor',
    'get_all_extensions',
    'get_supported_languages',
    # Language extractors (new class-based API)
    'PythonExtractor',
    'JavaScriptExtractor',
    'GoExtractor',
    'RustExtractor',
    # Deprecated function-based API (backward compatibility)
    'extract_python_imports',
    'extract_python_symbols',
    'extract_js_imports',
    'extract_go_imports',
    'extract_rust_imports',
]
