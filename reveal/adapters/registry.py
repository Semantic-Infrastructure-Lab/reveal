"""Adapter and renderer registry — scheme-to-class mappings and plugin discovery.

Adapters register via @register_adapter('scheme') decorator.
Renderers register via @register_renderer(RendererClass) decorator.
A shipped adapter's module is imported on first lookup of its scheme (BACK-1870),
so a command that uses one adapter does not import the other thirty-four; anything
that enumerates the registry imports them all.
Plugin adapters outside the reveal package tree are auto-discovered from
<cwd>/.reveal/adapters/ and ~/.reveal/adapters/ on first get_adapter_class() call.
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# The adapters reveal ships, in registration order; each is the module
# reveal.adapters.<scheme>. tests/test_adapter_registry_lazy_back1870.py checks this
# tuple against what a full import registers, so it cannot drift.
BUILTIN_SCHEMES = (
    'env', 'ast', 'claude', 'diff', 'ssl', 'domain', 'help', 'imports', 'json',
    'markdown', 'mysql', 'python', 'reveal', 'sqlite', 'stats', 'xlsx', 'cpanel',
    'autossl', 'letsencrypt', 'nginx', 'calls', 'classify', 'depends', 'patches',
    'codex', 'surface', 'contracts', 'hotspots', 'deps', 'architecture', 'git',
    'overview', 'testability', 'trace', 'pack',
)
# Absent without their optional dependency; every other import failure is a bug.
_OPTIONAL_SCHEMES = frozenset({'git'})


class _SchemeRegistry(Dict[str, type]):
    """Scheme -> adapter class, filled on demand.

    A lookup of one shipped scheme (``[]``, ``get``, ``in``) imports that adapter's
    module; iteration, ``keys``/``values``/``items``, ``len`` and ``copy`` import all
    of them first, then list them in BUILTIN_SCHEMES order. Registering is a plain
    ``__setitem__`` and loads nothing.
    """

    _all_loaded = False
    _loading_all = False

    def _has(self, scheme: str) -> bool:
        return super().__contains__(scheme)

    def _load(self, scheme: Any) -> None:
        if (self._all_loaded or not isinstance(scheme, str)
                or scheme not in BUILTIN_SCHEMES or self._has(scheme)):
            return
        _import_adapter_module(scheme)

    def load_all(self) -> None:
        if self._all_loaded or self._loading_all:
            return
        self._loading_all = True
        try:
            for scheme in BUILTIN_SCHEMES:
                if not self._has(scheme):
                    _import_adapter_module(scheme)
            # Canonical order, whatever order lookups happened to load them in.
            registered = dict(super().items())
            ordered = {s: registered.pop(s) for s in BUILTIN_SCHEMES if s in registered}
            ordered.update(registered)
            super().clear()
            super().update(ordered)
            self._all_loaded = True
        finally:
            self._loading_all = False

    def __missing__(self, scheme: Any) -> type:
        self._load(scheme)
        if not self._has(scheme):
            raise KeyError(scheme)
        return super().__getitem__(scheme)

    def get(self, scheme: Any, default: Any = None) -> Any:
        self._load(scheme)
        return super().get(scheme, default)

    def __contains__(self, scheme: object) -> bool:
        self._load(scheme)
        return super().__contains__(scheme)

    def __iter__(self):
        self.load_all()
        return super().__iter__()

    def __len__(self) -> int:
        self.load_all()
        return super().__len__()

    def keys(self):
        self.load_all()
        return super().keys()

    def values(self):
        self.load_all()
        return super().values()

    def items(self):
        self.load_all()
        return super().items()

    def copy(self):
        self.load_all()
        return super().copy()


def _import_adapter_module(scheme: str) -> None:
    try:
        importlib.import_module(f'reveal.adapters.{scheme}')
    except ImportError:
        if scheme not in _OPTIONAL_SCHEMES:
            raise
        logger.debug('Optional adapter %s unavailable', scheme, exc_info=True)


# Scheme → adapter class mapping populated by @register_adapter decorators.
_ADAPTER_REGISTRY: Dict[str, type] = _SchemeRegistry()
_adapter_plugins_loaded: bool = False

# Scheme → renderer class mapping populated by @register_renderer decorators.
# Read it through get_renderer_class / list_renderer_schemes, which load the adapter first.
_RENDERER_REGISTRY: Dict[str, type] = {}


def load_all_adapters() -> None:
    """Import every shipped adapter (registers each scheme and renderer)."""
    _ADAPTER_REGISTRY.load_all()  # type: ignore[attr-defined]


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
    except Exception as e:  # boundary-ok: broad-except -- importing a user-supplied plugin runs arbitrary code (SyntaxError, ImportError, anything its module body raises); one bad plugin must not stop reveal or the other plugins, and the warning names the plugin
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


# Registered only by the scaffold template (demo://) or by a test run (test://),
# never by a shipped adapter.
_SCAFFOLD_SCHEMES = frozenset({'demo', 'test'})


def is_internal_scheme(scheme: str) -> bool:
    """True for a scheme reveal does not advertise: an adapter whose class sets
    ``internal`` (it only inspects reveal's own source, e.g. reveal://) or a
    scaffold/test scheme. Still reachable by name."""
    cls = _ADAPTER_REGISTRY.get(scheme)
    return scheme in _SCAFFOLD_SCHEMES or bool(getattr(cls, 'internal', False))


def list_public_schemes(include_internal: bool = False) -> list:
    """The adapters reveal advertises, sorted.

    One definition for every listing and count: --adapters, --discover,
    help://, help://schemas and the adapter count the docs state (BACK-1610).
    They used two predicates (the class's ``internal`` flag, and a hand-typed
    {'demo', 'test'} set in help://), so --adapters said 34 and help:// 35.
    """
    return sorted(s for s in _ADAPTER_REGISTRY
                  if include_internal or not is_internal_scheme(s))


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
    scheme = scheme.lower()
    _ADAPTER_REGISTRY._load(scheme)  # type: ignore[attr-defined]
    return _RENDERER_REGISTRY.get(scheme)


def list_renderer_schemes() -> list:
    """Get list of schemes with registered renderers."""
    load_all_adapters()
    return sorted(_RENDERER_REGISTRY.keys())
