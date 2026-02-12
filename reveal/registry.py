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
    pass

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


def _is_nginx_content(path: str) -> bool:
    """Detect nginx config by content patterns.

    Args:
        path: File path to check

    Returns:
        True if file contains nginx config patterns
    """
    try:
        with open(path, 'r', errors='ignore') as f:
            # Read first 4KB for detection
            content = f.read(4096)

        # Nginx-specific patterns (unlikely in INI files)
        nginx_patterns = [
            'server {',       # Server block
            'server{',        # Compact style
            'location /',     # Location block
            'upstream ',      # Upstream block
            'listen ',        # Listen directive
            'proxy_pass ',    # Proxy directive
            'ssl_certificate',  # SSL config
        ]

        return any(pattern in content for pattern in nginx_patterns)
    except (IOError, OSError):
        return False


def _is_nginx_path(file_path: Path) -> bool:
    """Check if path indicates nginx config."""
    path_str = str(file_path.resolve())
    return '/nginx/' in path_str or '/etc/nginx/' in path_str


def _try_conf_detection(path: str, file_path: Path, ext: str) -> Optional[type]:
    """Try to detect analyzer for .conf files (nginx vs INI)."""
    if ext != '.conf':
        return None

    if _is_nginx_path(file_path):
        from .analyzers.nginx import NginxAnalyzer
        return NginxAnalyzer

    if _is_nginx_content(path):
        from .analyzers.nginx import NginxAnalyzer
        return NginxAnalyzer

    return None


def _try_extension_lookup(ext: str) -> Optional[type]:
    """Try to find analyzer by file extension."""
    if ext and ext in _ANALYZER_REGISTRY:
        return _ANALYZER_REGISTRY.get(ext)
    return None


def _try_filename_lookup(file_path: Path) -> Optional[type]:
    """Try to find analyzer by filename (Dockerfile, Makefile, etc.)."""
    filename = file_path.name.lower()
    if filename in _ANALYZER_REGISTRY:
        return _ANALYZER_REGISTRY.get(filename)
    return None


def _try_nginx_path_detection(file_path: Path) -> Optional[type]:
    """Try to detect nginx by path patterns."""
    if _is_nginx_path(file_path):
        from .analyzers.nginx import NginxAnalyzer
        return NginxAnalyzer
    return None


def _try_shebang_lookup(path: str, ext: str) -> Optional[type]:
    """Try to detect analyzer from shebang line."""
    if not ext or ext not in _ANALYZER_REGISTRY:
        shebang_ext = _detect_shebang(path)
        if shebang_ext:
            return _ANALYZER_REGISTRY.get(shebang_ext)
    return None


def _try_fallback_lookup(ext: str, allow_fallback: bool, path: str) -> Optional[type]:
    """Try TreeSitter fallback for unknown extensions."""
    if allow_fallback and ext:
        fallback = _try_treesitter_fallback(ext)
        if fallback:
            logger.debug(f"Using tree-sitter fallback for {path}")
        return fallback
    return None


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

    # Try detection strategies in order
    strategies = [
        lambda: _try_conf_detection(path, file_path, ext),
        lambda: _try_extension_lookup(ext),
        lambda: _try_filename_lookup(file_path),
        lambda: _try_nginx_path_detection(file_path),
        lambda: _try_shebang_lookup(path, ext),
        lambda: _try_fallback_lookup(ext, allow_fallback, path),
    ]

    for strategy in strategies:
        result = strategy()
        if result:
            return result

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
    from .core import suppress_treesitter_warnings

    # Suppress tree-sitter deprecation warnings (centralized in core module)
    suppress_treesitter_warnings()

    language = _guess_treesitter_language(ext)
    if not language:
        return None

    try:
        # Test if parser is available
        from tree_sitter_language_pack import get_parser
        get_parser(language)  # type: ignore[arg-type]  # language is validated at runtime

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
                'fallback_quality': 'basic',  # Tree-sitter basic analysis (functions, classes, imports)
            }
        )

        # Log fallback creation for transparency
        logger.info(
            f"Created tree-sitter fallback analyzer for {ext} (language: {language}, quality: basic)"
        )

        return dynamic_class

    except Exception as e:
        # Parser not available or import failed
        logger.debug(f"Tree-sitter fallback failed for {ext}: {e}")
        return None


def get_all_analyzers() -> Dict[str, Dict[str, Any]]:
    """Get all registered analyzers with metadata.

    Returns:
        Dict mapping extension to analyzer metadata
        e.g., {'.py': {'name': 'Python', 'icon': '', 'class': PythonAnalyzer,
                       'is_fallback': False}}
    """
    result = {}
    for ext, cls in _ANALYZER_REGISTRY.items():
        result[ext] = {
            'extension': ext,
            'name': getattr(cls, 'type_name', cls.__name__.replace('Analyzer', '')),
            'icon': getattr(cls, 'icon', ''),
            'class': cls,
            'is_fallback': getattr(cls, 'is_fallback', False),
            'fallback_quality': getattr(cls, 'fallback_quality', None),
            'fallback_language': getattr(cls, 'fallback_language', None),
        }
    return result


def get_analyzer_mapping() -> Dict[str, type]:
    """Get raw analyzer registry mapping.

    Returns:
        Dict mapping extension to analyzer class
        e.g., {'.py': PythonAnalyzer, '.rs': RustAnalyzer}
    """
    return _ANALYZER_REGISTRY.copy()
