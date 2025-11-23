"""
Analyzer Registry - Decorator-based plugin system for reveal

This module provides a Pythonic way to register file type analyzers
using decorators, similar to Flask routes or Click commands.

Example:
    @analyzer.register(['.rs', '.rust'], name='Rust', icon='🦀')
    class RustAnalyzer:
        def analyze_structure(self, lines):
            return {'functions': [...]}

        def generate_preview(self, lines):
            return [(line_num, content), ...]
"""

from typing import List, Type, Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AnalyzerMetadata:
    """Metadata for a registered analyzer"""
    analyzer_class: Type
    extensions: List[str]
    name: str
    description: str = ""
    icon: str = "📄"
    features: Dict[str, Any] = field(default_factory=dict)

    @property
    def extension_list(self) -> str:
        """Formatted extension list for display"""
        return ', '.join(self.extensions)


class AnalyzerRegistry:
    """
    Global registry for file type analyzers.

    Provides decorator-based registration similar to Flask routes.
    Supports both built-in and third-party plugins via entry points.
    """

    def __init__(self):
        self._analyzers: Dict[str, AnalyzerMetadata] = {}
        self._extension_map: Dict[str, AnalyzerMetadata] = {}
        self._entry_points_loaded = False

    def register(
        self,
        extensions: Optional[List[str]] = None,
        name: Optional[str] = None,
        description: str = "",
        icon: str = "📄",
        features: Optional[Dict[str, Any]] = None
    ) -> Callable:
        """
        Decorator to register an analyzer.

        Args:
            extensions: List of file extensions (e.g., ['.py', '.pyx'])
            name: Display name for the analyzer
            description: Brief description of capabilities
            icon: Emoji icon for display
            features: Dict of feature flags

        Returns:
            Decorator function

        Example:
            @analyzer.register(['.rs', '.rust'], name='Rust', icon='🦀')
            class RustAnalyzer:
                def analyze_structure(self, lines):
                    return {'functions': [...]}

                def generate_preview(self, lines):
                    return [(i, line) for i, line in enumerate(lines)]
        """
        def decorator(cls: Type) -> Type:
            # Auto-detect name from class if not provided
            analyzer_name = name or cls.__name__.replace('Analyzer', '')

            # Get description from docstring if not provided
            analyzer_desc = description or (cls.__doc__ or "").split('\n')[0].strip()

            # Store metadata
            metadata = AnalyzerMetadata(
                analyzer_class=cls,
                extensions=extensions or [],
                name=analyzer_name,
                description=analyzer_desc,
                icon=icon,
                features=features or {}
            )

            # Register by name
            self._analyzers[analyzer_name.lower()] = metadata

            # Map each extension to this analyzer
            for ext in extensions or []:
                ext_lower = ext.lower()
                if not ext_lower.startswith('.'):
                    ext_lower = '.' + ext_lower
                self._extension_map[ext_lower] = metadata

            return cls

        return decorator

    def get_for_extension(self, extension: str) -> Optional[Type]:
        """
        Get analyzer class for file extension.

        Args:
            extension: File extension (e.g., '.py' or 'py')

        Returns:
            Analyzer class or None if not found
        """
        ext = extension.lower()
        if not ext.startswith('.'):
            ext = '.' + ext

        metadata = self._extension_map.get(ext)
        return metadata.analyzer_class if metadata else None

    def get_for_file(self, filepath: str) -> Optional[Type]:
        """
        Get analyzer class for file path.

        Args:
            filepath: Path to file

        Returns:
            Analyzer class or None if not found
        """
        ext = Path(filepath).suffix.lower()
        return self.get_for_extension(ext)

    def get_metadata(self, filepath: str) -> Optional[AnalyzerMetadata]:
        """
        Get full metadata for a file.

        Args:
            filepath: Path to file

        Returns:
            AnalyzerMetadata or None
        """
        ext = Path(filepath).suffix.lower()
        if not ext.startswith('.'):
            ext = '.' + ext
        return self._extension_map.get(ext)

    def list_all(self) -> List[AnalyzerMetadata]:
        """List all registered analyzers"""
        return sorted(self._analyzers.values(), key=lambda m: m.name)

    def list_extensions(self) -> List[str]:
        """List all supported file extensions"""
        return sorted(self._extension_map.keys())

    def discover_entry_points(self):
        """
        Discover and load plugins via setuptools entry points.

        Plugins register themselves by defining an entry point:
            entry_points={
                'reveal.analyzers': [
                    'rust = reveal_rust:RustAnalyzer',
                ],
            }

        When loaded, the plugin's @register decorator executes automatically.
        """
        if self._entry_points_loaded:
            return  # Only load once

        # Use modern importlib.metadata (Python 3.8+) instead of deprecated pkg_resources
        try:
            from importlib.metadata import entry_points
        except ImportError:
            # Fallback for Python < 3.8 (though reveal requires 3.8+)
            try:
                from importlib_metadata import entry_points
            except ImportError:
                # No entry points available, skip plugin discovery
                return

        # Get entry points for reveal analyzers
        # Python 3.9+ uses select(), Python 3.8 uses dict-style access
        try:
            eps = entry_points(group='reveal.analyzers')
        except TypeError:
            # Python 3.8 compatibility
            eps = entry_points().get('reveal.analyzers', [])
        for entry_point in eps:
            try:
                # Load the plugin (this triggers @register decorator)
                entry_point.load()
            except Exception as e:
                # Don't crash on plugin errors, just warn
                print(f"Warning: Failed to load plugin {entry_point.name}: {e}")

        self._entry_points_loaded = True


# Global registry instance
_registry = AnalyzerRegistry()


def register(*args, **kwargs) -> Callable:
    """
    Decorator to register an analyzer with the global registry.

    Can be used with or without parentheses:
        @register
        class MyAnalyzer: ...

        @register(['.ext'], name='MyType')
        class MyAnalyzer: ...

    See AnalyzerRegistry.register() for full documentation.
    """
    if len(args) == 1 and callable(args[0]) and not kwargs:
        # Used as @register without parentheses
        return _registry.register()(args[0])
    else:
        # Used as @register(...) with arguments
        return _registry.register(*args, **kwargs)


def get_analyzer(filepath: str) -> Optional[Type]:
    """
    Get analyzer class for file.

    Automatically discovers entry point plugins on first call.

    Args:
        filepath: Path to file

    Returns:
        Analyzer class or None
    """
    # Ensure plugins are discovered
    _registry.discover_entry_points()
    return _registry.get_for_file(filepath)


def get_metadata(filepath: str) -> Optional[AnalyzerMetadata]:
    """
    Get analyzer metadata for file.

    Args:
        filepath: Path to file

    Returns:
        AnalyzerMetadata or None
    """
    _registry.discover_entry_points()
    return _registry.get_metadata(filepath)


def list_analyzers() -> List[AnalyzerMetadata]:
    """List all registered analyzers"""
    _registry.discover_entry_points()
    return _registry.list_all()


def list_extensions() -> List[str]:
    """List all supported file extensions"""
    _registry.discover_entry_points()
    return _registry.list_extensions()


# Export public API
__all__ = [
    'register',
    'get_analyzer',
    'get_metadata',
    'list_analyzers',
    'list_extensions',
    'AnalyzerMetadata',
]
