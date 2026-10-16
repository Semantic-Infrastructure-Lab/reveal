"""URI adapters for exploring non-file resources."""

from . import base
from .base import (
    ResourceAdapter,
    Stability,
    register_adapter,
    register_renderer,
    get_adapter_class,
    get_renderer_class,
    list_supported_schemes,
    list_renderer_schemes,
)

from .registry import load_all_adapters

# The adapter classes are exported lazily (PEP 562): `reveal.adapters.X` on first use
# imports every shipped adapter and returns the registered class, so importing
# reveal.adapters.base for the registry no longer imports all of them (BACK-1870).


def __getattr__(name: str):
    if name.endswith('Adapter'):
        load_all_adapters()
        for cls in base._ADAPTER_REGISTRY.values():
            if cls.__name__ == name:
                globals()[name] = cls
                return cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Base classes and registry functions
    'ResourceAdapter',
    'Stability',
    'register_adapter',
    'register_renderer',
    'get_adapter_class',
    'get_renderer_class',
    'list_supported_schemes',
    'list_renderer_schemes',
    # Adapter classes
    'EnvAdapter',
    'AstAdapter',
    'ClaudeAdapter',
    'DiffAdapter',
    'DomainAdapter',
    'HelpAdapter',
    'ImportsAdapter',
    'JsonAdapter',
    'MarkdownQueryAdapter',
    'MySQLAdapter',
    'PythonAdapter',
    'RevealAdapter',
    'SQLiteAdapter',
    'SSLAdapter',
    'StatsAdapter',
    'XlsxAdapter',
    'CpanelAdapter',
    'AutosslAdapter',
    'LetsEncryptAdapter',
    'NginxUriAdapter',
    'CallsAdapter',
    'ClassifyAdapter',
    'DependsAdapter',
    'PatchesAdapter',
    'CodexAdapter',
    'SurfaceAdapter',
    'ContractsAdapter',
]
