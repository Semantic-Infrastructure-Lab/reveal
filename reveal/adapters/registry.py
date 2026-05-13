"""Adapter and renderer registry — scheme-to-class mappings and plugin discovery.

Adapters register via @register_adapter('scheme') decorator.
Renderers register via @register_renderer(RendererClass) decorator.
Plugin adapters outside the reveal package tree are auto-discovered from
<cwd>/.reveal/adapters/ and ~/.reveal/adapters/ on first get_adapter_class() call.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Scheme → adapter class mapping populated by @register_adapter decorators.
_ADAPTER_REGISTRY: Dict[str, type] = {}
_adapter_plugins_loaded: bool = False

# Scheme → renderer class mapping populated by @register_renderer decorators.
_RENDERER_REGISTRY: Dict[str, type] = {}


def _load_adapter_plugin_dir(plugin_dir: Path) -> None:
    """Import a single adapter package directory, logging failures without raising."""
    import importlib.util
    init_file = plugin_dir / '__init__.py'
    if not init_file.exists():
        return
    module_name = f'reveal_plugin_adapter_{plugin_dir.name}'
    try:
        spec = importlib.util.spec_from_file_location(
            module_name,
            init_file,
            submodule_search_locations=[str(plugin_dir)],
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
            logger.debug('Loaded adapter plugin: %s', plugin_dir.name)
    except Exception as e:
        logger.warning('Adapter plugin load failed (%s): %s', plugin_dir.name, e)


def discover_adapter_plugins(cwd: Optional[Path] = None) -> None:
    """Load adapter packages from project-local and user-global plugin dirs.

    Scans in order:
      1. <cwd>/.reveal/adapters/  — project-local plugins
      2. ~/.reveal/adapters/       — user-global plugins

    Each discovered subdirectory with an __init__.py is imported; @register_adapter
    decorators fire as a side effect, adding the adapter to _ADAPTER_REGISTRY.
    Called once per process (no-op on subsequent calls).

    Plugin adapters must use absolute imports from reveal.adapters.base rather
    than relative imports, since they live outside the reveal package tree.
    """
    global _adapter_plugins_loaded
    if _adapter_plugins_loaded:
        return
    _adapter_plugins_loaded = True

    base = cwd if cwd is not None else Path.cwd()
    plugin_dirs = [
        base / '.reveal' / 'adapters',
        Path.home() / '.reveal' / 'adapters',
    ]
    for plugin_dir in plugin_dirs:
        if not plugin_dir.is_dir():
            continue
        for entry in sorted(plugin_dir.iterdir()):
            if entry.is_dir():
                _load_adapter_plugin_dir(entry)


def _reset_adapter_plugin_discovery() -> None:
    """Reset plugin discovery state — for test isolation only."""
    global _adapter_plugins_loaded
    _adapter_plugins_loaded = False


def register_adapter(scheme: str):
    """Decorator to register an adapter for a URI scheme.

    Usage:
        @register_adapter('postgres')
        class PostgresAdapter(ResourceAdapter):
            ...

        # With renderer:
        @register_adapter('postgres')
        @register_renderer(PostgresRenderer)
        class PostgresAdapter(ResourceAdapter):
            ...

    Args:
        scheme: URI scheme to register (e.g., 'env', 'ast', 'postgres')
    """
    def decorator(cls):
        _ADAPTER_REGISTRY[scheme.lower()] = cls
        cls.scheme = scheme

        # If a renderer was pending (from @register_renderer), register it now
        if hasattr(cls, '_pending_renderer'):
            renderer_class = cls._pending_renderer
            _RENDERER_REGISTRY[scheme.lower()] = renderer_class
            cls.renderer = renderer_class
            delattr(cls, '_pending_renderer')  # Clean up

        return cls
    return decorator


def get_adapter_class(scheme: str) -> Optional[type]:
    """Get adapter class for a URI scheme.

    Args:
        scheme: URI scheme (e.g., 'env', 'ast')

    Returns:
        Adapter class or None if not found
    """
    discover_adapter_plugins()
    return _ADAPTER_REGISTRY.get(scheme.lower())


def list_supported_schemes() -> list:
    """Get list of supported URI schemes."""
    return sorted(_ADAPTER_REGISTRY.keys())


def register_renderer(renderer_class):
    """Decorator to register a renderer for an adapter.

    Usage:
        @register_adapter('mysql')
        @register_renderer(MySQLRenderer)
        class MySQLAdapter(ResourceAdapter):
            ...

    The renderer is automatically paired with the adapter's scheme.

    Note: Decorators are applied bottom-up, so register_renderer runs BEFORE
    register_adapter. We store the renderer on the class and let register_adapter
    complete the registration.

    Args:
        renderer_class: Renderer class with render_structure() method

    Returns:
        Decorator function that registers the renderer
    """
    def decorator(adapter_class):
        adapter_class._pending_renderer = renderer_class
        return adapter_class
    return decorator


def get_renderer_class(scheme: str) -> Optional[type]:
    """Get renderer class for a URI scheme."""
    return _RENDERER_REGISTRY.get(scheme.lower())


def list_renderer_schemes() -> list:
    """Get list of schemes with registered renderers."""
    return sorted(_RENDERER_REGISTRY.keys())
