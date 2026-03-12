"""Base adapter interface for URI resources."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple


# ---------------------------------------------------------------------------
# Adapter initialization helpers
# These try-functions are ordered by convention type. Each returns (adapter, error).
# A non-None adapter = success. A non-None error is kept as "last error" for
# reporting if all attempts fail.
# ---------------------------------------------------------------------------

def _try_no_args_init(adapter_class: type) -> Tuple[Any, Optional[Exception]]:
    """Try no-argument initialization (env, python adapters)."""
    try:
        return adapter_class(), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
        return None, None
    except ImportError as e:
        return None, e


def _try_query_parsing_init(adapter_class: type, resource: str) -> Tuple[Any, Optional[Exception]]:
    """Try query-parsing initialization (ast, json with ?query)."""
    if '?' not in resource:
        return None, None
    try:
        path, query = resource.split('?', 1)
        path = path or '.'
        return adapter_class(path, query), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
        return None, None
    except ImportError as e:
        return None, e


def _try_keyword_args_init(adapter_class: type, resource: str) -> Tuple[Any, Optional[Exception]]:
    """Try keyword arguments initialization (markdown with base_path/query)."""
    try:
        if '?' in resource:
            path_part, query = resource.split('?', 1)
            path = path_part.rstrip('/') if path_part else '.'
        else:
            path = resource.rstrip('/') if resource else '.'
            query = None
        return adapter_class(base_path=path, query=query), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
        return None, None
    except ImportError as e:
        return None, e


def _try_resource_arg_init(adapter_class: type, resource: str) -> Tuple[Any, Optional[Exception]]:
    """Try resource argument initialization (help, git, etc)."""
    if resource is None:
        return None, None
    try:
        if '?' not in resource:
            path = resource or '.'
            try:
                return adapter_class(path, None), None
            except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
                return adapter_class(resource), None
            except ImportError as e:
                return None, e
        else:
            return adapter_class(resource), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError) as e:
        return None, e
    except ImportError as e:
        return None, e


def _try_full_uri_init(adapter_class: type, scheme: str, resource: str,
                       element: Optional[str]) -> Tuple[Any, Optional[Exception]]:
    """Try full URI initialization (mysql, sqlite)."""
    try:
        full_uri = f"{scheme}://{resource}"
        if element and '://' in full_uri:
            full_uri = f"{full_uri}/{element}"
        return adapter_class(full_uri), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError) as e:
        return None, e
    except ImportError as e:
        return None, e


def _default_from_uri(adapter_class: type, scheme: str, resource: str,
                      element: Optional[str]) -> Any:
    """Default try-chain initialization used by ResourceAdapter.from_uri.

    Available as a standalone function so the router can apply it to any
    adapter class (including test doubles that don't inherit ResourceAdapter).

    Raises:
        ImportError: If initialization failed due to a missing optional dependency.
        RuntimeError: If all initialization attempts failed.
    """
    if resource:
        init_attempts = [
            lambda: _try_query_parsing_init(adapter_class, resource),
            lambda: _try_resource_arg_init(adapter_class, resource),
            lambda: _try_keyword_args_init(adapter_class, resource),
            lambda: _try_no_args_init(adapter_class),
            lambda: _try_full_uri_init(adapter_class, scheme, resource, element),
        ]
    else:
        init_attempts = [
            lambda: _try_no_args_init(adapter_class),
            lambda: _try_query_parsing_init(adapter_class, resource),
            lambda: _try_keyword_args_init(adapter_class, resource),
            lambda: _try_resource_arg_init(adapter_class, resource),
            lambda: _try_full_uri_init(adapter_class, scheme, resource, element),
        ]

    init_error: Optional[Exception] = None
    for attempt in init_attempts:
        adapter, error = attempt()
        if adapter is not None:
            return adapter
        if error is not None:
            init_error = error

    if isinstance(init_error, ImportError):
        raise init_error
    raise RuntimeError(
        f"Could not initialize {scheme}:// adapter: {init_error}"
    )


class ResourceAdapter(ABC):
    """Base class for all resource adapters."""

    # Override in subclasses to name the top-level list field that budget
    # constraints (--max-items, --max-bytes, etc.) should apply to.
    # None = this adapter has no budget-limitable list field.
    BUDGET_LIST_FIELD: Optional[str] = None

    @classmethod
    def from_uri(cls, scheme: str, resource: str,
                 element: Optional[str]) -> 'ResourceAdapter':
        """Initialize adapter from URI components.

        Tries multiple constructor conventions in order. Override in subclasses
        for deterministic, single-call initialization without a fallback chain.

        Different adapters have different conventions:
        - No-arg: env, python (take no resource in __init__)
        - Resource-arg: help, reveal (take resource string as first arg)
        - Query-parsing: ast, json (parse resource to extract path/query)
        - URI: mysql (expect full URI like mysql://host:port)

        Raises:
            ImportError: If initialization failed due to a missing optional dependency.
            RuntimeError: If all initialization attempts failed.
        """
        return _default_from_uri(cls, scheme, resource, element)

    @abstractmethod
    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get the structure/overview of the resource.

        Returns:
            Dict containing structured representation of the resource
        """
        pass

    @staticmethod
    def create_meta(
        parse_mode: Optional[str] = None,
        confidence: Optional[float] = None,
        warnings: Optional[List[Dict[str, Any]]] = None,
        errors: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Create Output Contract v1.1 meta dict with trust metadata.

        For adapters that use parsing (tree-sitter, regex, heuristics) to provide
        quality/confidence information to AI agents.

        Args:
            parse_mode: How parsing was performed
                - "tree_sitter_full" - Complete AST parsing (high confidence)
                - "tree_sitter_partial" - Partial AST parsing (some errors)
                - "fallback" - Tree-sitter failed, used fallback
                - "regex" - Regular expression extraction
                - "heuristic" - Pattern-based heuristics
            confidence: Overall confidence (0.0-1.0)
                - 1.0 = Perfect parse
                - 0.95-0.99 = High confidence
                - 0.80-0.94 = Good confidence
                - 0.50-0.79 = Partial results
                - < 0.50 = Low confidence
            warnings: Non-fatal issues
                [{'code': 'W001', 'message': '...', 'file': '...'}]
            errors: Fatal errors with fallback info
                [{'code': 'E002', 'message': '...', 'file': '...', 'fallback': '...'}]

        Returns:
            Meta dict for Output Contract v1.1

        Example:
            meta = ResourceAdapter.create_meta(
                parse_mode='tree_sitter_full',
                confidence=0.95,
                warnings=[{
                    'code': 'W001',
                    'message': 'File encoding uncertain',
                    'file': 'legacy.py'
                }]
            )
            return {
                'contract_version': '1.1',
                'type': 'ast_query',
                'source': 'src/',
                'source_type': 'directory',
                'meta': meta,  # <- Include meta
                'results': [...]
            }
        """
        meta: Dict[str, Any] = {}

        if parse_mode is not None:
            meta['parse_mode'] = parse_mode

        if confidence is not None:
            # Clamp to [0.0, 1.0]
            meta['confidence'] = max(0.0, min(1.0, confidence))

        if warnings is not None:
            meta['warnings'] = warnings
        else:
            meta['warnings'] = []

        if errors is not None:
            meta['errors'] = errors
        else:
            meta['errors'] = []

        return meta if meta else {}

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get details about a specific element within the resource.

        Args:
            element_name: Name/identifier of the element to retrieve

        Returns:
            Dict containing element details, or None if not found
        """
        return None

    def get_available_elements(self) -> List[Dict[str, str]]:
        """Get list of available elements for this resource.

        Returns list of available elements that can be accessed via get_element().
        Each element includes name, description, and example usage.

        Returns:
            List of dicts with keys:
                - name (str): Element identifier (e.g., 'san', 'chain')
                - description (str): Human-readable description
                - example (str): Example usage (e.g., 'reveal ssl://example.com/san')

        Example:
            [
                {
                    'name': 'san',
                    'description': 'Subject Alternative Names (3 domains)',
                    'example': 'reveal ssl://example.com/san'
                },
                {
                    'name': 'chain',
                    'description': 'Certificate chain (2 certificates)',
                    'example': 'reveal ssl://example.com/chain'
                }
            ]

        Note:
            Default implementation returns empty list. Adapters with element support
            should override this method to provide discoverable elements.

            For adapters with dynamic elements (e.g., env:// with variable names,
            json:// with keys), consider returning:
                - Empty list (no static elements)
                - Sample/common elements with note
                - Top N most relevant elements from current data
        """
        return []

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the resource.

        Returns:
            Dict containing metadata (type, size, etc.)
        """
        return {'type': self.__class__.__name__}

    @staticmethod
    def get_help() -> Optional[Dict[str, Any]]:
        """Get help documentation for this adapter (optional).

        For extension authors: Implement this method to provide discoverable help.
        Your help will automatically appear in `reveal help://` and `reveal help://yourscheme`

        Returns:
            Dict containing help metadata, or None if no help available.

            Required keys:
                - name (str): Adapter scheme name (e.g., 'python', 'ast')
                - description (str): One-line summary (< 80 chars)

            Recommended keys:
                - syntax (str): Usage pattern (e.g., 'scheme://<resource>[?<filters>]')
                - examples (List[Dict]): Example URIs with descriptions
                  [{'uri': 'scheme://example', 'description': 'What it does'}]
                - notes (List[str]): Important notes, gotchas, limitations
                - see_also (List[str]): Related adapters, tools, documentation

            Optional keys (for advanced adapters):
                - operators (Dict[str, str]): Query operators (e.g., '>', '<', '==')
                - filters (Dict[str, str]): Available filters with descriptions
                - elements (Dict[str, str]): Available elements (for element-based adapters)
                - features (List[str]): Feature list
                - use_cases (List[str]): Common use cases
                - output_formats (List[str]): Supported formats ('text', 'json', 'grep')
                - coming_soon (List[str]): Planned features

        Best Practices:
            - Provide 3-7 examples (simple → complex)
            - Include multi-shot examples (input + expected output) for LLMs
            - Add breadcrumbs in see_also to guide users
            - Create comprehensive guide (ADAPTER_GUIDE.md) for complex adapters
            - Link guide in see_also: 'reveal help://yourscheme-guide - Comprehensive guide'

        For detailed guidance:
            reveal help://adapter-authoring - Complete adapter authoring guide

        Examples:
            See reveal/adapters/python.py, ast.py, env.py for reference implementations
        """
        return None

    @staticmethod
    def get_schema() -> Optional[Dict[str, Any]]:
        """Get machine-readable schema for this adapter (optional).

        For AI agent integration: Implement this method to provide discoverable
        schemas that enable agents to auto-generate valid queries.

        Returns:
            Dict containing schema metadata, or None if no schema available.

            Required keys:
                - adapter (str): Adapter scheme name (e.g., 'ssl', 'ast')
                - description (str): One-line summary
                - uri_syntax (str): URI pattern (e.g., 'ssl://<host>[:<port>][/<element>]')

            Recommended keys:
                - query_params (Dict[str, Dict]): Query parameters with type/description
                  {'param_name': {'type': 'string', 'description': '...', 'required': bool}}
                - elements (List[str]): Available elements for element-based queries
                - output_types (List[Dict]): Output structure definitions
                  [{'type': 'ssl_certificate', 'schema': {...}, 'example': {...}}]
                - cli_flags (List[str]): Available CLI flags
                - example_queries (List[Dict]): Canonical query examples
                  [{'uri': '...', 'description': '...', 'output_type': '...'}]

            Optional keys:
                - operators (Dict[str, str]): Supported query operators (>, <, =, etc.)
                - filters (Dict[str, Dict]): Available filters with type info
                - supports_batch (bool): Whether adapter supports stdin batch mode
                - supports_advanced (bool): Whether --advanced flag is supported

        Purpose:
            - AI agents discover capabilities programmatically
            - Auto-generate valid queries without hardcoding
            - Understand expected output structure
            - Generate correct query parameters

        Best Practices:
            - Include JSON Schema definitions for complex output types
            - Provide example outputs (small, realistic samples)
            - Document all query parameters with types
            - Include 3-5 example queries covering common use cases

        For detailed guidance:
            reveal help://adapter-authoring - Schema authoring guide

        Examples:
            See reveal/adapters/ssl.py, ast.py for reference implementations
        """
        return None


# Registry for URI scheme adapters
_ADAPTER_REGISTRY: Dict[str, type] = {}


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
    return _ADAPTER_REGISTRY.get(scheme.lower())


def list_supported_schemes() -> list:
    """Get list of supported URI schemes.

    Returns:
        List of registered scheme names
    """
    return sorted(_ADAPTER_REGISTRY.keys())


# Registry for URI scheme renderers
_RENDERER_REGISTRY: Dict[str, type] = {}


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
        # Store renderer class on adapter (register_adapter will use this)
        adapter_class._pending_renderer = renderer_class
        return adapter_class
    return decorator


def get_renderer_class(scheme: str) -> Optional[type]:
    """Get renderer class for a URI scheme.

    Args:
        scheme: URI scheme (e.g., 'mysql', 'sqlite')

    Returns:
        Renderer class or None if not found
    """
    return _RENDERER_REGISTRY.get(scheme.lower())


def list_renderer_schemes() -> list:
    """Get list of schemes with registered renderers.

    Returns:
        List of scheme names that have renderers
    """
    return sorted(_RENDERER_REGISTRY.keys())
