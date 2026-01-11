"""Analyzer registry for reveal - file type registration and lookup.

This module provides the central registry for file analyzers:
- @register() decorator to register analyzers for file extensions
- get_analyzer() to look up analyzer by file path
- get_all_analyzers() for introspection

Design:
    The registry is separate from the base FileAnalyzer class to maintain
    clean separation of concerns. Analyzers register themselves at import
    time using the decorator, and the registry handles all lookup logic
    including shebang detection and TreeSitter fallback.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .base import FileAnalyzer

logger = logging.getLogger(__name__)

# Registry for file type analyzers
_ANALYZER_REGISTRY: Dict[str, type] = {}


def register(*extensions, name: str = '', icon: str = ''):
    """Decorator to register an analyzer for file extensions.

    Usage:
        @register('.py', name='Python', icon='')
        class PythonAnalyzer(FileAnalyzer):
            ...

    Args:
        extensions: File extensions to register (e.g., '.py', '.rs')
        name: Display name for this file type
        icon: Emoji icon for this file type
    """
    def decorator(cls):
        for ext in extensions:
            _ANALYZER_REGISTRY[ext.lower()] = cls

        # Store metadata on class
        cls.type_name = name or cls.__name__.replace('Analyzer', '')
        cls.icon = icon

        return cls

    return decorator


def get_analyzer(path: str, allow_fallback: bool = True) -> Optional[type]:
    """Get analyzer class for a file path.

    Args:
        path: File path
        allow_fallback: Enable TreeSitter fallback for unknown extensions

    Returns:
        Analyzer class or None if not found
    """
    file_path = Path(path)
    ext = file_path.suffix.lower()

    # If we have an extension, use it
    if ext and ext in _ANALYZER_REGISTRY:
        return _ANALYZER_REGISTRY.get(ext)

    # No extension or not found - check special filenames (Dockerfile, Makefile)
    filename = file_path.name.lower()
    if filename in _ANALYZER_REGISTRY:
        return _ANALYZER_REGISTRY.get(filename)

    # Path-based detection for nginx configs (handles /etc/nginx/sites-available/*, etc.)
    path_str = str(file_path.resolve())
    if '/nginx/' in path_str or '/etc/nginx/' in path_str:
        # Import here to avoid circular imports
        from .analyzers.nginx import NginxAnalyzer
        return NginxAnalyzer

    # Still no match - check shebang for extensionless scripts
    if not ext or ext not in _ANALYZER_REGISTRY:
        shebang_ext = _detect_shebang(path)
        if shebang_ext:
            return _ANALYZER_REGISTRY.get(shebang_ext)

    # TreeSitter fallback for unknown extensions
    if allow_fallback and ext:
        return _try_treesitter_fallback(ext)

    return None


def _detect_shebang(path: str) -> Optional[str]:
    """Detect file type from shebang line.

    Args:
        path: File path

    Returns:
        Extension to use (e.g., '.py', '.sh') or None
    """
    try:
        with open(path, 'rb') as f:
            first_line = f.readline()

        # Decode with error handling
        try:
            shebang = first_line.decode('utf-8', errors='ignore').strip()
        except (UnicodeDecodeError, AttributeError):
            # UnicodeDecodeError: decode failed despite errors='ignore'
            # AttributeError: first_line is None or invalid
            return None

        if not shebang.startswith('#!'):
            return None

        # Map shebangs to extensions
        shebang_lower = shebang.lower()

        # Python
        if 'python' in shebang_lower:
            return '.py'

        # Shell scripts (bash, sh, zsh)
        if any(shell in shebang_lower for shell in ['bash', '/sh', 'zsh']):
            return '.sh'

        return None

    except (IOError, OSError):
        return None


def _guess_treesitter_language(ext: str) -> Optional[str]:
    """Map file extension to TreeSitter language name.

    Args:
        ext: File extension (e.g., '.cpp', '.java')

    Returns:
        TreeSitter language name or None
    """
    # Common extension to TreeSitter language mappings
    EXTENSION_MAP = {
        '.c': 'c',
        '.h': 'c',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.cxx': 'cpp',
        '.hpp': 'cpp',
        '.hxx': 'cpp',
        '.java': 'java',
        '.rb': 'ruby',
        '.php': 'php',
        '.swift': 'swift',
        '.scala': 'scala',
        '.cs': 'c_sharp',
        '.lua': 'lua',
        '.r': 'r',
        '.elm': 'elm',
        '.ex': 'elixir',
        '.exs': 'elixir',
        '.zig': 'zig',
        '.v': 'verilog',
        '.sv': 'verilog',
        '.svh': 'verilog',
        '.m': 'objc',
        '.mm': 'objc',
        '.sql': 'sql',
        '.hs': 'haskell',
        '.ml': 'ocaml',
        '.mli': 'ocaml',
        '.erl': 'erlang',
        '.hrl': 'erlang',
    }
    return EXTENSION_MAP.get(ext.lower())


def _try_treesitter_fallback(ext: str) -> Optional[type]:
    """Try to create a dynamic TreeSitter analyzer for unknown extension.

    Args:
        ext: File extension

    Returns:
        Dynamic analyzer class or None if TreeSitter doesn't support it
    """
    import warnings

    # Suppress tree-sitter deprecation warnings
    warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')

    language = _guess_treesitter_language(ext)
    if not language:
        return None

    try:
        # Test if parser is available
        from tree_sitter_language_pack import get_parser
        get_parser(language)

        # Import TreeSitterAnalyzer dynamically to avoid circular import
        from .treesitter import TreeSitterAnalyzer

        # Create dynamic analyzer class
        class_name = f'Dynamic{language.title().replace("_", "")}Analyzer'
        dynamic_class = type(
            class_name,
            (TreeSitterAnalyzer,),
            {
                'language': language,
                'type_name': language.replace('_', ' ').title(),
                'is_fallback': True,
                'fallback_language': language,
            }
        )

        return dynamic_class

    except Exception:
        # Parser not available or import failed
        return None


def get_all_analyzers() -> Dict[str, Dict[str, Any]]:
    """Get all registered analyzers with metadata.

    Returns:
        Dict mapping extension to analyzer metadata
        e.g., {'.py': {'name': 'Python', 'icon': '', 'class': PythonAnalyzer}}
    """
    result = {}
    for ext, cls in _ANALYZER_REGISTRY.items():
        result[ext] = {
            'extension': ext,
            'name': getattr(cls, 'type_name', cls.__name__.replace('Analyzer', '')),
            'icon': getattr(cls, 'icon', ''),
            'class': cls,
        }
    return result
