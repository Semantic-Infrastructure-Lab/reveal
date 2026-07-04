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

import functools
import logging
import re
from pathlib import Path
from typing import FrozenSet, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Extension → tree-sitter language name for dynamic fallback analyzer creation.
# Also imported by main.py to build the --help fallback language list.
# When adding a new language: add it here once; main.py picks it up automatically.
TREESITTER_EXTENSION_MAP: Dict[str, str] = {
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
    '.ocaml': 'ocaml',
    '.erl': 'erlang',
    '.hrl': 'erlang',
}

# Registry for file type analyzers
_ANALYZER_REGISTRY: Dict[str, type] = {}

# Plugin discovery state — reset via _reset_plugin_discovery() in tests
_plugins_loaded: bool = False


def discover_plugins(cwd: Optional[Path] = None) -> None:
    """Load *_analyzer.py plugins from project-local and user-global dirs.

    Scans in order:
      1. <cwd>/.reveal/analyzers/  — project-local plugins
      2. ~/.reveal/plugins/         — user-global plugins

    Each discovered file is imported; @register decorators fire as a side
    effect, adding the analyzer to _ANALYZER_REGISTRY. Called once per
    process (no-op on subsequent calls).
    """
    global _plugins_loaded
    if _plugins_loaded:
        return
    _plugins_loaded = True

    base = cwd if cwd is not None else Path.cwd()
    plugin_dirs = [
        base / '.reveal' / 'analyzers',
        Path.home() / '.reveal' / 'plugins',
    ]
    for plugin_dir in plugin_dirs:
        if not plugin_dir.is_dir():
            continue
        for plugin_file in sorted(plugin_dir.glob('*_analyzer.py')):
            _load_plugin_file(plugin_file)


def _load_plugin_file(plugin_file: Path) -> None:
    """Import a single plugin file, logging failures without raising."""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location(plugin_file.stem, plugin_file)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            logger.debug('Loaded plugin: %s', plugin_file)
    except Exception as e:
        logger.warning('Plugin load failed (%s): %s', plugin_file.name, e)


def _reset_plugin_discovery() -> None:
    """Reset plugin discovery state — for test isolation only."""
    global _plugins_loaded
    _plugins_loaded = False


def register(*extensions, name: str = '', icon: str = '', category: str = 'code'):
    """Decorator to register an analyzer for file extensions.

    Usage:
        @register('.py', name='Python', icon='')
        class PythonAnalyzer(FileAnalyzer):
            ...

    Args:
        extensions: File extensions to register (e.g., '.py', '.rs')
        name: Display name for this file type
        icon: Emoji icon for this file type
        category: Content category — 'code', 'data', 'doc', or 'config' (default 'code')
    """
    def decorator(cls):
        for ext in extensions:
            _ANALYZER_REGISTRY[ext.lower()] = cls

        # Store metadata on class
        cls.type_name = name or cls.__name__.replace('Analyzer', '')
        cls.icon = icon
        cls.CATEGORY = category

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
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
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


def _get_nginx_analyzer_class() -> type:
    """Lazy-load and return NginxAnalyzer class."""
    from .analyzers.nginx import NginxAnalyzer
    return NginxAnalyzer


def _try_conf_detection(path: str, file_path: Path, ext: str) -> Optional[type]:
    """Try to detect analyzer for .conf files (nginx vs INI)."""
    if ext != '.conf':
        return None

    if _is_nginx_path(file_path) or _is_nginx_content(path):
        return _get_nginx_analyzer_class()

    return None


# C++-only constructs, none of which are valid C. Their presence in a `.h`
# header means it is a C++ header, not a C one. Matched as a pragmatic
# substring/regex sniff (same spirit as _is_nginx_content) — a comment or string
# containing one of these is a rare, low-cost false positive; the alternative
# (routing every `.h` to the C grammar, BACK-421) hides C++ classes declared in
# headers, which is the overwhelmingly common real-world C++ layout.
_CPP_HEADER_MARKERS = (
    re.compile(r'\btemplate\s*<'),          # template<...>
    re.compile(r'\bnamespace\s+\w'),        # namespace Foo
    re.compile(r'\bnamespace\s*\{'),        # anonymous namespace
    re.compile(r'\bclass\s+\w'),            # class Foo  (not a C keyword)
    re.compile(r'\bpublic\s*:'),            # access specifiers
    re.compile(r'\bprivate\s*:'),
    re.compile(r'\bprotected\s*:'),
    re.compile(r'\bvirtual\b'),             # virtual methods
    re.compile(r'\boperator\b'),            # operator overloads
    re.compile(r'::'),                       # scope resolution
    re.compile(r'\bstd::'),                 # std namespace usage
    re.compile(r'\btypename\b'),
    re.compile(r'\bnullptr\b'),
    re.compile(r'extern\s+"C"'),            # C++ wrapping C — only legal in C++
)


def _is_cpp_header_content(path: str) -> bool:
    """Detect a C++ header (`.h`) by C++-only content markers.

    `.h` is ambiguous between C and C++; the extension table routes it to C,
    which hides header-declared C++ classes/templates/namespaces entirely
    (BACK-421). Sniff the file for constructs that are illegal in C, and if any
    are present route the header to the C++ grammar instead.
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(8192)
    except (IOError, OSError):
        return False
    return any(marker.search(content) for marker in _CPP_HEADER_MARKERS)


def _try_c_header_detection(path: str, file_path: Path, ext: str) -> Optional[type]:
    """Route a `.h` header to the C++ analyzer when it holds C++-only constructs."""
    if ext != '.h':
        return None
    if _is_cpp_header_content(path):
        return _ANALYZER_REGISTRY.get('.cpp')
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
        return _get_nginx_analyzer_class()
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
    discover_plugins()
    file_path = Path(path)
    ext = file_path.suffix.lower()

    # Try detection strategies in order
    strategies = [
        lambda: _try_conf_detection(path, file_path, ext),
        lambda: _try_c_header_detection(path, file_path, ext),
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
    return TREESITTER_EXTENSION_MAP.get(ext.lower())


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
                'CATEGORY': 'code',
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
            'category': getattr(cls, 'CATEGORY', 'code'),
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


def get_analyzer_for_extension(ext: str) -> Optional[type]:
    """Look up the registered analyzer class for one extension, or None.

    Single-entry counterpart to get_analyzer_mapping() — for callers that
    only need one extension, this skips copying the entire registry.
    """
    return _ANALYZER_REGISTRY.get(ext.lower())


def language_for_extension(ext: str) -> Optional[str]:
    """Return the canonical tree-sitter language slug for *ext*, or None.

    Single source of truth for "what language is this extension" — used by
    BACK-431 Issue B to derive the coarser per-consumer views (call-graph
    family, non-Python-language display name, etc.) that used to be
    hand-maintained parallel extension tables. Prefers the dedicated
    analyzer's `language` class attribute (set on every TreeSitterAnalyzer
    subclass, e.g. 'csharp', 'typescript', 'tsx') when one is registered;
    falls back to TREESITTER_EXTENSION_MAP for extensions handled only via
    dynamic tree-sitter fallback (no dedicated analyzer file).

    Args:
        ext: File extension including the leading dot (e.g. '.rs', '.CS')

    Returns:
        Language slug (e.g. 'rust', 'c_sharp') or None if unknown to reveal
    """
    ext = ext.lower()
    cls = _ANALYZER_REGISTRY.get(ext)
    lang = getattr(cls, 'language', None) if cls is not None else None
    return lang or TREESITTER_EXTENSION_MAP.get(ext)


# Coarse per-language display name, layered on top of language_for_extension()
# for consumers that want a human-readable label rather than the tree-sitter
# slug (e.g. 'csharp' -> 'C#'). Deliberately covers only languages that need
# a name distinct from their capitalized slug — Title-casing the slug is the
# fallback for everything else (see display_name_for_extension()).
LANGUAGE_DISPLAY_NAMES: Dict[str, str] = {
    'javascript': 'JavaScript', 'typescript': 'TypeScript', 'tsx': 'TypeScript',
    'csharp': 'C#', 'cpp': 'C++', 'objc': 'Objective-C',
    'php': 'PHP', 'gdscript': 'GDScript', 'sql': 'SQL',
    'yaml': 'YAML', 'json': 'JSON', 'toml': 'TOML', 'graphql': 'GraphQL',
    'powershell': 'PowerShell', 'bash': 'Shell', 'hcl': 'HCL',
    'proto': 'Protobuf',
}

# Same-language, different-desired-name overrides, keyed by *extension* rather
# than language slug — for the rare case where two extensions share one
# language (BACK-431 Issue B #5) but should display differently. `.tf`/`.hcl`
# is the only known instance: both resolve to language_for_extension == 'hcl',
# but Terraform files warrant their own label rather than the generic HCL one.
EXTENSION_DISPLAY_OVERRIDES: Dict[str, str] = {
    '.tf': 'Terraform',
}


def display_name_for_extension(ext: str) -> str:
    """Return a human-readable language name for *ext*, or '' if unknown.

    Layers EXTENSION_DISPLAY_OVERRIDES and LANGUAGE_DISPLAY_NAMES over
    language_for_extension() so consumers needing a coarse display label
    (e.g. "Objective-C" for both .m and .mm) don't each hand-maintain their
    own extension→name table.
    """
    ext = ext.lower()
    if ext in EXTENSION_DISPLAY_OVERRIDES:
        return EXTENSION_DISPLAY_OVERRIDES[ext]
    lang = language_for_extension(ext)
    if not lang:
        return ''
    return LANGUAGE_DISPLAY_NAMES.get(lang, lang.capitalize())


@functools.lru_cache(maxsize=None)
def get_code_extensions() -> FrozenSet[str]:
    """Return all extensions that represent code files.

    Combines extensions from explicitly registered 'code'-category analyzers
    with all keys in TREESITTER_EXTENSION_MAP (those are always programming
    languages). Must be called after analyzers have been imported — in normal
    usage this is guaranteed because reveal's adapter layer imports analyzers
    before any path-scanning function runs.

    Returns:
        Frozenset of lowercase extensions (e.g. {'.py', '.rs', '.zig', ...})
    """
    explicit = frozenset(
        ext for ext, cls in _ANALYZER_REGISTRY.items()
        if getattr(cls, 'CATEGORY', 'code') == 'code'
    )
    treesitter = frozenset(TREESITTER_EXTENSION_MAP.keys())
    return explicit | treesitter
