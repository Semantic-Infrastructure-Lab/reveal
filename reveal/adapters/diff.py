"""Diff adapter for comparing two reveal resources."""

import inspect
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from .base import ResourceAdapter, register_adapter, register_renderer, get_adapter_class
from .help_data import load_help_data


class DiffRenderer:
    """Renderer for diff comparison results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render diff structure comparison.

        Args:
            result: Diff result from adapter
            format: Output format (text, json, grep)
        """
        from ..rendering.diff import render_diff
        render_diff(result, format, is_element=False)

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render element-specific diff.

        Args:
            result: Element diff result
            format: Output format
        """
        from ..rendering.diff import render_diff
        render_diff(result, format, is_element=True)

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render error message.

        Args:
            error: Exception to render
        """
        print(f"Error: {error}", file=sys.stderr)
        if isinstance(error, ValueError):
            print(file=sys.stderr)
            print("Examples:", file=sys.stderr)
            print("  reveal diff://app.py:backup/app.py", file=sys.stderr)
            print("  reveal diff://env://:env://production", file=sys.stderr)
            print("  reveal diff://mysql://prod/db:mysql://staging/db", file=sys.stderr)
            print(file=sys.stderr)
            print("Learn more: reveal help://diff", file=sys.stderr)


@register_adapter('diff')
@register_renderer(DiffRenderer)
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

    def __init__(self, resource: Optional[str] = None, right_uri: Optional[str] = None):
        """Initialize with either a combined resource string or two URIs.

        Args:
            resource: Either combined "left:right" string or left_uri
            right_uri: Right URI (if resource is left_uri)

        The adapter supports two initialization styles:
        1. DiffAdapter("left:right") - single combined string (new style, for generic handler)
        2. DiffAdapter("left", "right") - two separate URIs (old style, backward compatibility)

        Raises:
            TypeError: When called with no arguments (wrong initialization pattern)
            ValueError: When resource format is invalid
        """
        # No args provided - wrong initialization pattern
        if resource is None and right_uri is None:
            raise TypeError(
                "DiffAdapter requires arguments. "
                "Use DiffAdapter('left:right') or DiffAdapter('left', 'right')"
            )

        if right_uri is not None:
            # Old style: two arguments
            self.left_uri = resource
            self.right_uri = right_uri
        elif resource and ':' in resource:
            # New style: parse combined resource string
            self.left_uri, self.right_uri = self._parse_diff_uris(resource)
        else:
            # Resource provided but invalid format
            raise ValueError(
                "DiffAdapter requires 'left:right' format. "
                "Got: {!r}. Example: diff://app.py:backup/app.py".format(resource)
            )
        self.left_structure = None
        self.right_structure = None

    @staticmethod
    def _parse_diff_uris(resource: str) -> Tuple[str, str]:
        """Parse left:right from diff resource string.

        Handles complex URIs that may contain colons:
        - Simple: "app.py:backup/app.py" → ("app.py", "backup/app.py")
        - Complex: "mysql://prod/db:mysql://staging/db" → ("mysql://prod/db", "mysql://staging/db")
        - Nested: "env://:env://production" → ("env://", "env://production")

        Args:
            resource: The resource string to parse

        Returns:
            Tuple of (left_uri, right_uri)

        Raises:
            ValueError: If parsing fails
        """
        # Count :// occurrences to determine complexity
        scheme_count = resource.count('://')

        if scheme_count == 0:
            # Simple case: "file1:file2"
            if ':' not in resource:
                raise ValueError("diff:// requires format: left:right")
            left, right = resource.split(':', 1)
            return left, right

        elif scheme_count == 1:
            # One scheme: "scheme://resource:file" or "file:scheme://resource"
            parts = resource.split('://')
            if ':' not in parts[0]:
                # Format: "scheme://resource:file"
                scheme = parts[0]
                rest = parts[1]
                if ':' not in rest:
                    raise ValueError(f"Invalid diff format: {resource}")
                resource_part, right = rest.rsplit(':', 1)
                left = f"{scheme}://{resource_part}"
                return left, right
            else:
                # Format: "file:scheme://resource"
                left, rest = parts[0].split(':', 1)
                right = f"{rest}://{parts[1]}"
                return left, right

        elif scheme_count == 2:
            # Two schemes: "scheme1://resource1:scheme2://resource2"
            parts = resource.split('://')
            # parts = ['scheme1', 'resource1:scheme2', 'resource2']
            if len(parts) != 3:
                raise ValueError(f"Invalid diff format: {resource}")

            scheme1 = parts[0]
            middle = parts[1]  # "resource1:scheme2"
            scheme2_resource = parts[2]

            # Split middle on the last colon to separate resource1 and scheme2
            if ':' not in middle:
                raise ValueError(f"Invalid diff format: {resource}")

            resource1, scheme2 = middle.rsplit(':', 1)
            left = f"{scheme1}://{resource1}"
            right = f"{scheme2}://{scheme2_resource}"
            return left, right

        else:
            # Too complex
            raise ValueError(
                f"Too many schemes in URI (found {scheme_count}). "
                "For complex URIs, use explicit format: diff://scheme1://res1:scheme2://res2"
            )

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for diff:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'diff',
            'description': 'Compare two reveal-compatible resources to detect changes, schema drift, or configuration differences',
            'uri_syntax': 'diff://<left-uri>:<right-uri>[/element]',
            'query_params': {},  # No query parameters
            'elements': {},  # Element names depend on resources being compared
            'cli_flags': [],
            'supports_batch': False,
            'supports_advanced': False,
            'comparison_types': [
                'File to file comparison',
                'Environment to environment comparison',
                'Database schema drift detection',
                'Configuration comparison',
                'Element-specific diff (functions, classes, etc.)'
            ],
            'output_types': [
                {
                    'type': 'diff',
                    'description': 'Comparison result showing differences between resources',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'diff'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string', 'const': 'comparison'},
                            'left': {
                                'type': 'object',
                                'properties': {
                                    'uri': {'type': 'string'},
                                    'type': {'type': 'string'}
                                }
                            },
                            'right': {
                                'type': 'object',
                                'properties': {
                                    'uri': {'type': 'string'},
                                    'type': {'type': 'string'}
                                }
                            },
                            'summary': {
                                'type': 'object',
                                'properties': {
                                    'added': {'type': 'integer'},
                                    'removed': {'type': 'integer'},
                                    'modified': {'type': 'integer'},
                                    'unchanged': {'type': 'integer'}
                                }
                            },
                            'diff_lines': {'type': 'array'}
                        }
                    },
                    'example': {
                        'contract_version': '1.0',
                        'type': 'diff',
                        'source': 'diff://app.py:backup/app.py',
                        'source_type': 'comparison',
                        'left': {'uri': 'app.py', 'type': 'file'},
                        'right': {'uri': 'backup/app.py', 'type': 'file'},
                        'summary': {
                            'added': 5,
                            'removed': 3,
                            'modified': 2,
                            'unchanged': 100
                        }
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'diff://app.py:backup/app.py',
                    'description': 'Compare two files',
                    'output_type': 'diff'
                },
                {
                    'uri': 'diff://app.py:git://app.py@HEAD~1',
                    'description': 'Compare current file to git version (1 commit ago)',
                    'output_type': 'diff',
                    'note': 'Git URIs use path@ref format, not ref:path'
                },
                {
                    'uri': 'diff://git://app.py@main:git://app.py@develop',
                    'description': 'Compare file across two git branches',
                    'output_type': 'diff'
                },
                {
                    'uri': 'diff://env://:env://production',
                    'description': 'Compare local environment to production',
                    'output_type': 'diff'
                },
                {
                    'uri': 'diff://mysql://prod/db:mysql://staging/db',
                    'description': 'Database schema drift detection',
                    'output_type': 'diff'
                },
                {
                    'uri': 'diff://app.py:old.py/handle_request',
                    'description': 'Compare specific function across versions',
                    'element': 'handle_request',
                    'output_type': 'diff'
                }
            ],
            'notes': [
                'Supports any two reveal URIs that resolve to comparable structures',
                'Automatically detects resource types and adapts comparison strategy',
                'Element-specific diffs extract and compare individual functions/classes',
                'Works with files, databases, environments, and other adapters',
                'Git URIs use path@ref format: git://file.py@HEAD~1 (not git://HEAD~1:file.py)',
                'Git ref format matches git adapter syntax, not git CLI show command'
            ]
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for diff:// adapter.

        Help data loaded from reveal/adapters/help_data/diff.yaml
        to reduce function complexity.
        """
        return load_help_data('diff') or {}

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
            'contract_version': '1.0',
            'type': 'diff_comparison',
            'source': f"{self.left_uri} vs {self.right_uri}",
            'source_type': 'runtime',
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

    def _find_analyzable_files(self, directory: Path) -> List[Path]:
        """Find all files in directory that can be analyzed.

        Args:
            directory: Directory path to scan

        Returns:
            List of file paths that have analyzers
        """
        from ..registry import get_analyzer

        analyzable = []
        for root, dirs, files in os.walk(directory):
            # Skip common ignore directories
            dirs[:] = [d for d in dirs if d not in {
                '.git', '__pycache__', 'node_modules', '.venv', 'venv',
                'dist', 'build', '.pytest_cache', '.mypy_cache', '.tox',
                'htmlcov', '.coverage', 'eggs', '*.egg-info'
            }]

            for file in files:
                file_path = Path(root) / file
                # Check if reveal can analyze this file
                if get_analyzer(str(file_path), allow_fallback=False):
                    analyzable.append(file_path)

        return analyzable

    def _resolve_git_ref(self, git_ref: str, path: str) -> Dict[str, Any]:
        """Resolve a git reference to a structure.

        Args:
            git_ref: Git reference (HEAD, main, HEAD~1, etc.)
            path: Path to file or directory in the git tree

        Returns:
            Structure dict from the git version

        Raises:
            ValueError: If git command fails or path not found
        """
        # Check if we're in a git repository
        try:
            subprocess.run(['git', 'rev-parse', '--git-dir'],
                          check=True, capture_output=True)
        except subprocess.CalledProcessError:
            raise ValueError("Not in a git repository")

        # Check if it's a directory or file in git
        try:
            # Try to list the path to see if it's a directory
            result = subprocess.run(
                ['git', 'ls-tree', '-r', git_ref, path],
                capture_output=True, text=True, check=True
            )

            if not result.stdout.strip():
                raise ValueError(f"Path not found in {git_ref}: {path}")

            # If we got multiple lines, it's a directory
            lines = result.stdout.strip().split('\n')
            is_directory = len(lines) > 1 or lines[0].split()[1] == 'tree'

        except subprocess.CalledProcessError as e:
            raise ValueError(f"Git error: {e.stderr}")

        if is_directory:
            return self._resolve_git_directory(git_ref, path)
        else:
            return self._resolve_git_file(git_ref, path)

    def _resolve_git_adapter(self, resource: str) -> Dict[str, Any]:
        """Resolve git:// adapter URI to structure.

        Supports git:// adapter format: git://path@REF or git://.@REF

        Args:
            resource: Resource part of git:// URI (e.g., "reveal/main.py@HEAD" or ".@main")

        Returns:
            Structure dict from the git version (analyzed code structure, not file metadata)

        Raises:
            ImportError: If GitAdapter is not available (pygit2 not installed)
            ValueError: If URI format is invalid or resolution fails
        """
        try:
            from .git.adapter import GitAdapter
        except ImportError:
            raise ImportError(
                "GitAdapter not available. Install with: pip install reveal-cli[git]\n"
                "Note: diff:// also supports git CLI format: git://REF/path"
            )

        # Validate git URI format - should have path@REF or .@REF format
        # Detect common mistake: REF:path instead of path@REF
        if ':' in resource and '@' not in resource:
            # Likely wrong format: "HEAD~1:file.py" instead of "file.py@HEAD~1"
            parts = resource.split(':', 1)
            raise ValueError(
                f"Git URI format error. Got '{resource}' but expected 'path@ref' format.\n"
                f"Hint: Use 'git://{parts[1]}@{parts[0]}' instead of 'git://{resource}'\n"
                f"Example: 'git://app.py@HEAD~1' (not 'git://HEAD~1:app.py')"
            )

        # Simple check: if no @ and no / in resource, it's likely just a ref without path
        if '@' not in resource and '/' not in resource and resource:
            raise ValueError(
                f"Git URI must be in format 'path@REF' or '.@REF'. "
                f"Got: '{resource}'. Example: 'main.py@HEAD' or '.@main'"
            )

        try:
            # GitAdapter will parse the resource (handles path@REF format)
            adapter = GitAdapter(resource=resource)
            git_result = adapter.get_structure()

            # If it's a file, we need to analyze its content to get code structure
            # GitAdapter returns file content/metadata, not analyzed code structure
            if git_result.get('type') in ['file', 'file_at_ref']:
                # Get the file content
                content = git_result.get('content', '')
                # Use the path for analyzer selection
                file_path = git_result.get('path', resource.split('@')[0])

                # Analyze the content to get code structure
                from ..registry import get_analyzer
                analyzer_class = get_analyzer(file_path, allow_fallback=True)
                if not analyzer_class:
                    raise ValueError(f"No analyzer found for file: {file_path}")

                # Create temporary file or use in-memory analysis
                # Most analyzers can work with content directly
                import tempfile
                import os
                with tempfile.NamedTemporaryFile(mode='w', suffix=os.path.splitext(file_path)[1], delete=False) as f:
                    f.write(content)
                    temp_path = f.name

                try:
                    analyzer = analyzer_class(temp_path)
                    return analyzer.get_structure()
                finally:
                    os.unlink(temp_path)

            # For repository/ref views, return as-is
            return git_result

        except Exception as e:
            raise ValueError(f"Failed to resolve git:// adapter URI: {e}")

    def _resolve_git_file(self, git_ref: str, path: str) -> Dict[str, Any]:
        """Get structure from a file in git.

        Args:
            git_ref: Git reference
            path: File path in git tree

        Returns:
            Structure dict
        """
        from ..registry import get_analyzer

        # Get file content from git
        try:
            result = subprocess.run(
                ['git', 'show', f'{git_ref}:{path}'],
                capture_output=True, text=True, check=True
            )
            content = result.stdout
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Failed to get file from git: {e.stderr}")

        # Write to temp file for analysis
        with tempfile.NamedTemporaryFile(mode='w', suffix=Path(path).suffix, delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            analyzer_class = get_analyzer(temp_path, allow_fallback=True)
            if not analyzer_class:
                raise ValueError(f"No analyzer found for file: {path}")
            analyzer = analyzer_class(temp_path)
            return analyzer.get_structure()
        finally:
            os.unlink(temp_path)

    def _resolve_git_directory(self, git_ref: str, dir_path: str) -> Dict[str, Any]:
        """Get aggregated structure from a directory in git.

        Args:
            git_ref: Git reference
            dir_path: Directory path in git tree

        Returns:
            Aggregated structure dict
        """
        from ..registry import get_analyzer

        # Get list of files in the directory
        try:
            result = subprocess.run(
                ['git', 'ls-tree', '-r', git_ref, dir_path],
                capture_output=True, text=True, check=True
            )
            if not result.stdout.strip():
                raise ValueError(f"Directory not found in {git_ref}: {dir_path}")
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Git error: {e.stderr}")

        # Parse git ls-tree output
        all_functions = []
        all_classes = []
        all_imports = []
        file_count = 0

        for line in result.stdout.strip().split('\n'):
            parts = line.split(maxsplit=3)
            if len(parts) < 4:
                continue

            mode, obj_type, sha, file_path = parts
            if obj_type != 'blob':  # Only process files, not trees
                continue

            # Check if we have an analyzer for this file type
            if not get_analyzer(file_path, allow_fallback=False):
                continue

            # Get file content and analyze
            try:
                content_result = subprocess.run(
                    ['git', 'show', f'{git_ref}:{file_path}'],
                    capture_output=True, text=True, check=True
                )
                content = content_result.stdout

                # Write to temp file
                with tempfile.NamedTemporaryFile(mode='w', suffix=Path(file_path).suffix, delete=False) as f:
                    f.write(content)
                    temp_path = f.name

                # Analyze
                analyzer_class = get_analyzer(temp_path, allow_fallback=False)
                if analyzer_class:
                    analyzer = analyzer_class(temp_path)
                    structure = analyzer.get_structure()
                    struct = structure.get('structure', structure)

                    # Add file context
                    rel_path = file_path
                    if dir_path and dir_path != '.':
                        rel_path = file_path[len(dir_path.rstrip('/')) + 1:]

                    for func in struct.get('functions', []):
                        func['file'] = rel_path
                        all_functions.append(func)

                    for cls in struct.get('classes', []):
                        cls['file'] = rel_path
                        all_classes.append(cls)

                    for imp in struct.get('imports', []):
                        imp['file'] = rel_path
                        all_imports.append(imp)

                    file_count += 1

                os.unlink(temp_path)

            except (subprocess.CalledProcessError, Exception):
                # Skip files that fail to process
                continue

        return {
            'type': 'git_directory',
            'ref': git_ref,
            'path': dir_path,
            'file_count': file_count,
            'functions': all_functions,
            'classes': all_classes,
            'imports': all_imports
        }

    def _resolve_directory(self, dir_path: str) -> Dict[str, Any]:
        """Resolve a directory to aggregated structure.

        Args:
            dir_path: Path to directory

        Returns:
            Dict with aggregated structures from all files
        """
        from ..registry import get_analyzer

        directory = Path(dir_path).resolve()
        if not directory.is_dir():
            raise ValueError(f"Not a directory: {dir_path}")

        files = self._find_analyzable_files(directory)

        # Aggregate all structures
        all_functions = []
        all_classes = []
        all_imports = []

        for file_path in files:
            rel_path = file_path.relative_to(directory)
            analyzer_class = get_analyzer(str(file_path), allow_fallback=False)
            if analyzer_class:
                analyzer = analyzer_class(str(file_path))
                structure = analyzer.get_structure()

                # Extract structure (handle both nested and flat)
                struct = structure.get('structure', structure)

                # Add file context to each element
                for func in struct.get('functions', []):
                    func['file'] = str(rel_path)
                    all_functions.append(func)

                for cls in struct.get('classes', []):
                    cls['file'] = str(rel_path)
                    all_classes.append(cls)

                for imp in struct.get('imports', []):
                    imp['file'] = str(rel_path)
                    all_imports.append(imp)

        return {
            'type': 'directory',
            'path': str(directory),
            'file_count': len(files),
            'functions': all_functions,
            'classes': all_classes,
            'imports': all_imports
        }

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

        # Handle git scheme: supports two formats
        # 1. git:// adapter format: git://path@REF (uses GitAdapter with pygit2)
        # 2. diff legacy format: git://REF/path (uses git CLI directly)
        if scheme == 'git':
            # Check if it's git:// adapter format (path@REF)
            if '@' in resource:
                # git:// adapter format: git://path@REF
                # Delegate to GitAdapter
                return self._resolve_git_adapter(resource)
            elif ':' in resource and '/' in resource:
                # Common mistake: git://REF:path instead of git://path@REF
                # Detect and provide helpful error
                parts = resource.split(':', 1)
                raise ValueError(
                    f"Git URI format error. Got 'git://{resource}' but git:// URIs must use:\n"
                    f"  1. Modern format:  git://path@ref  (e.g., git://app.py@HEAD~1)\n"
                    f"  2. Legacy format:  git://ref/path  (e.g., git://HEAD~1/app.py)\n"
                    f"Hint: Try 'git://{parts[1]}@{parts[0].split('/')[0]}' or fix the separator"
                )
            elif '/' in resource:
                # diff legacy format: git://REF/path
                # Parse git://REF/path format (e.g., git://HEAD~1/file.py, git://main/src/)
                git_ref, path = resource.split('/', 1)
                return self._resolve_git_ref(git_ref, path)
            else:
                # Repository overview
                return self._resolve_git_adapter(resource)

        # For file scheme, handle differently (no adapter class, uses get_analyzer)
        if scheme == 'file':
            # Check if it's a directory
            path = Path(resource).resolve()
            if path.is_dir():
                return self._resolve_directory(str(path))

            # Single file - use analyzer
            from ..registry import get_analyzer
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
            from ..registry import get_analyzer
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
