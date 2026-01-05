"""Diff adapter for comparing two reveal resources."""

import inspect
from typing import Dict, Any, Optional
from .base import ResourceAdapter, register_adapter, get_adapter_class


@register_adapter('diff')
class DiffAdapter(ResourceAdapter):
    """Compare two reveal-compatible resources.

    URI Syntax:
        diff://<left-uri>:<right-uri>[/element]

    Examples:
        diff://app.py:backup/app.py               # File comparison
        diff://env://:env://production            # Environment comparison
        diff://mysql://prod/db:mysql://staging/db # Database schema drift
        diff://app.py:old.py/handle_request       # Element-specific diff
    """

    def __init__(self, left_uri: str, right_uri: str):
        """Initialize with two URIs to compare.

        Args:
            left_uri: Source URI (e.g., 'file:app.py', 'env://')
            right_uri: Target URI (e.g., 'file:backup/app.py', 'env://prod')
        """
        self.left_uri = left_uri
        self.right_uri = right_uri
        self.left_structure = None
        self.right_structure = None

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for diff:// adapter."""
        return {
            'name': 'diff',
            'description': 'Compare two reveal resources - semantic structural diff',
            'syntax': 'diff://<left-uri>:<right-uri>[/element]',
            'examples': [
                {
                    'uri': 'diff://app.py:backup/app.py',
                    'description': 'Compare two Python files - see function/class changes'
                },
                {
                    'uri': 'diff://file:app.py:file:old_app.py',
                    'description': 'Explicit file:// scheme (optional)'
                },
                {
                    'uri': 'diff://env://:env://production',
                    'description': 'Compare environment variables (local vs production)'
                },
                {
                    'uri': 'diff://mysql://localhost/users:mysql://staging/users',
                    'description': 'Database schema drift detection'
                },
                {
                    'uri': 'diff://app.py:old.py/handle_request',
                    'description': 'Compare specific function (element-specific diff)'
                },
                {
                    'uri': 'diff://src/:backup/src/',
                    'description': 'Compare directories (shows file-level changes)'
                }
            ],
            'features': [
                'Semantic diff - compares structure, not text',
                'Works with ANY adapter (file, env, mysql, etc.)',
                'Two-level output: summary (counts) + details (changes)',
                'Element-specific diff support',
                'Shows complexity and line count changes',
                'Language-agnostic (works with Python, JS, etc.)'
            ],
            'workflows': [
                {
                    'name': 'Code Review Workflow',
                    'scenario': 'Review what changed in a feature branch',
                    'steps': [
                        "reveal diff://main.py:feature/main.py    # See structural changes",
                        "reveal diff://main.py:feature/main.py/process_data  # Specific function",
                    ]
                },
                {
                    'name': 'Refactoring Validation',
                    'scenario': 'Verify refactoring improved complexity',
                    'steps': [
                        "reveal diff://old.py:new.py              # Check complexity delta",
                        "# Look for 'complexity: 8 → 4' in output",
                    ]
                },
                {
                    'name': 'Environment Audit',
                    'scenario': 'Compare local vs production environment',
                    'steps': [
                        "reveal diff://env://:env://production    # See config drift",
                    ]
                }
            ],
            'output_format': {
                'summary': '+N -M ~K format (added, removed, modified)',
                'details': 'Per-element changes with old → new values',
                'supports': ['text', 'json', 'markdown (future)']
            },
            'notes': [
                'Complements git diff (semantic vs line-level)',
                'Works with existing adapters via composition',
                'Future: time-travel (diff://time:file:@v1:file:@v2)',
                'For complex URIs with colons, use explicit scheme://'
            ],
            'try_now': [
                "# Create test files",
                "echo 'def foo(): return 42' > v1.py",
                "echo 'def foo(): return 42\\ndef bar(): return 99' > v2.py",
                "reveal diff://v1.py:v2.py",
            ],
            'see_also': [
                'reveal help://file - File structure analysis',
                'reveal help://env - Environment variable inspection',
                'reveal help://mysql - Database schema exploration'
            ]
        }

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get diff summary between two resources.

        Returns:
            {
                'type': 'diff',
                'left': {'uri': ..., 'type': ...},
                'right': {'uri': ..., 'type': ...},
                'summary': {
                    'functions': {'added': 2, 'removed': 1, 'modified': 3},
                    'classes': {'added': 0, 'removed': 0, 'modified': 1},
                    'imports': {'added': 5, 'removed': 2},
                },
                'diff': {
                    'functions': [...],  # Detailed function diffs
                    'classes': [...],    # Detailed class diffs
                    'imports': [...]     # Import changes
                }
            }
        """
        from ..diff import compute_structure_diff

        # Resolve both URIs using existing adapter infrastructure
        left_struct = self._resolve_uri(self.left_uri, **kwargs)
        right_struct = self._resolve_uri(self.right_uri, **kwargs)

        # Compute semantic diff
        diff_result = compute_structure_diff(left_struct, right_struct)

        return {
            'type': 'diff',
            'left': self._extract_metadata(left_struct, self.left_uri),
            'right': self._extract_metadata(right_struct, self.right_uri),
            'summary': diff_result['summary'],
            'diff': diff_result['details']
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get diff for a specific element (function, class, etc.).

        Args:
            element_name: Name of element to compare (e.g., 'handle_request')

        Returns:
            Detailed diff for that specific element
        """
        from ..diff import compute_element_diff

        left_struct = self._resolve_uri(self.left_uri, **kwargs)
        right_struct = self._resolve_uri(self.right_uri, **kwargs)

        left_elem = self._find_element(left_struct, element_name)
        right_elem = self._find_element(right_struct, element_name)

        return compute_element_diff(left_elem, right_elem, element_name)

    def _resolve_uri(self, uri: str, **kwargs) -> Dict[str, Any]:
        """Resolve a URI to its structure using existing adapters.

        This is the key composition point - we delegate to existing
        adapters instead of reimplementing parsing logic.

        Args:
            uri: URI to resolve (e.g., 'file:app.py', 'env://')

        Returns:
            Structure dict from the adapter

        Raises:
            ValueError: If URI scheme is not supported
        """
        # If it's a plain path, treat as file://
        if '://' not in uri:
            uri = f'file://{uri}'

        scheme, resource = uri.split('://', 1)

        # For file scheme, handle differently (no adapter class, uses get_analyzer)
        if scheme == 'file':
            from ..base import get_analyzer
            analyzer_class = get_analyzer(resource, allow_fallback=True)
            if not analyzer_class:
                raise ValueError(f"No analyzer found for file: {resource}")
            analyzer = analyzer_class(resource)
            return analyzer.get_structure(**kwargs)

        # Get registered adapter
        adapter_class = get_adapter_class(scheme)
        if not adapter_class:
            raise ValueError(f"Unsupported URI scheme: {scheme}://")

        # Instantiate and get structure
        adapter = self._instantiate_adapter(adapter_class, scheme, resource)
        return adapter.get_structure(**kwargs)

    def _instantiate_adapter(self, adapter_class: type, scheme: str, resource: str):
        """Instantiate adapter with appropriate arguments.

        Different adapters have different constructor signatures:
        - EnvAdapter(): No args
        - FileAnalyzer(path): Single path arg
        - MySQLAdapter(resource): Resource string

        Args:
            adapter_class: The adapter class to instantiate
            scheme: URI scheme
            resource: Resource part of URI

        Returns:
            Instantiated adapter
        """
        # For file scheme, we need to use the file analyzer
        if scheme == 'file':
            from ..base import get_analyzer
            analyzer_class = get_analyzer(resource, allow_fallback=True)
            if not analyzer_class:
                raise ValueError(f"No analyzer found for file: {resource}")
            return analyzer_class(resource)

        # Try to determine constructor signature
        try:
            sig = inspect.signature(adapter_class.__init__)
            params = list(sig.parameters.keys())

            # Remove 'self' from params
            if 'self' in params:
                params.remove('self')

            # If no parameters (like EnvAdapter), instantiate without args
            if not params:
                return adapter_class()

            # Otherwise, pass the resource string
            return adapter_class(resource)

        except Exception:
            # Fallback: try with resource, then without
            try:
                return adapter_class(resource)
            except Exception:
                return adapter_class()

    def _extract_metadata(self, structure: Dict[str, Any], uri: str) -> Dict[str, str]:
        """Extract metadata from a structure for the diff result.

        Args:
            structure: Structure dict from adapter
            uri: Original URI

        Returns:
            Metadata dict with uri and type
        """
        return {
            'uri': uri,
            'type': structure.get('type', 'unknown')
        }

    def _find_element(self, structure: Dict[str, Any], element_name: str) -> Optional[Dict[str, Any]]:
        """Find a specific element within a structure.

        Args:
            structure: Structure dict from adapter
            element_name: Name of element to find

        Returns:
            Element dict or None if not found
        """
        # Handle both nested and flat structure formats
        struct = structure.get('structure', structure)

        # Search in functions
        for func in struct.get('functions', []):
            if func.get('name') == element_name:
                return func

        # Search in classes
        for cls in struct.get('classes', []):
            if cls.get('name') == element_name:
                return cls

            # Search in class methods
            for method in cls.get('methods', []):
                if method.get('name') == element_name:
                    return method

        return None

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the diff operation.

        Returns:
            Dict with diff metadata
        """
        return {
            'type': 'diff',
            'left_uri': self.left_uri,
            'right_uri': self.right_uri
        }
