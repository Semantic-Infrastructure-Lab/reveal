"""Diff adapter for comparing two reveal resources."""

import inspect
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List
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
                    'uri': 'diff://src/:backup/src/',
                    'description': 'Compare directories (aggregates all files)'
                },
                {
                    'uri': 'diff://git://HEAD~1/app.py:git://HEAD/app.py',
                    'description': 'Compare file across git commits'
                },
                {
                    'uri': 'diff://git://HEAD/src/:src/',
                    'description': 'Compare git HEAD vs working tree (pre-commit validation)'
                },
                {
                    'uri': 'diff://git://main/.:git://feature/refactor/.',
                    'description': 'Compare branches (merge impact assessment)'
                },
                {
                    'uri': 'diff://app.py:old.py/handle_request',
                    'description': 'Compare specific function (element-specific diff)'
                },
                {
                    'uri': 'diff://env://:env://production',
                    'description': 'Compare environment variables (local vs production)'
                },
                {
                    'uri': 'diff://mysql://localhost/users:mysql://staging/users',
                    'description': 'Database schema drift detection'
                }
            ],
            'features': [
                'Semantic diff - compares structure, not text',
                'Works with ANY adapter (file, env, mysql, etc.)',
                'Directory comparison - aggregates changes from all files',
                'Git integration - compare commits, branches, working tree',
                'Two-level output: summary (counts) + details (changes)',
                'Element-specific diff support',
                'Shows complexity and line count changes',
                'Language-agnostic (works with Python, JS, etc.)'
            ],
            'workflows': [
                {
                    'name': 'Pre-Commit Validation',
                    'scenario': 'Check uncommitted changes before commit',
                    'steps': [
                        "reveal diff://git://HEAD/src/:src/ --format=json  # See what changed",
                        "# Flag if complexity increased significantly",
                    ]
                },
                {
                    'name': 'Code Review Workflow',
                    'scenario': 'Review what changed in a feature branch',
                    'steps': [
                        "reveal diff://git://main/.:git://feature/.  # Full branch comparison",
                        "reveal diff://git://main/app.py:git://feature/app.py/process_data  # Specific function",
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
                    'name': 'Migration Validation',
                    'scenario': 'Ensure no functionality lost during migration',
                    'steps': [
                        "reveal diff://legacy_system/:new_system/  # Compare directory structures",
                        "# Verify all functions/classes migrated",
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
                'Git URI format: git://REF/path (e.g., git://HEAD~1/file.py, git://main/src/)',
                'Directory diffs aggregate all analyzable files (skips .git, node_modules, etc.)',
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

    def _find_analyzable_files(self, directory: Path) -> List[Path]:
        """Find all files in directory that can be analyzed.

        Args:
            directory: Directory path to scan

        Returns:
            List of file paths that have analyzers
        """
        from ..base import get_analyzer

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

    def _resolve_git_file(self, git_ref: str, path: str) -> Dict[str, Any]:
        """Get structure from a file in git.

        Args:
            git_ref: Git reference
            path: File path in git tree

        Returns:
            Structure dict
        """
        from ..base import get_analyzer

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
        from ..base import get_analyzer

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
        from ..base import get_analyzer

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

        # Handle git scheme: git://REF/path
        if scheme == 'git':
            # Parse git://REF/path format (e.g., git://HEAD~1/file.py, git://main/src/)
            if '/' not in resource:
                raise ValueError("Git URI must be in format git://REF/path (e.g., git://HEAD~1/file.py)")
            git_ref, path = resource.split('/', 1)
            return self._resolve_git_ref(git_ref, path)

        # For file scheme, handle differently (no adapter class, uses get_analyzer)
        if scheme == 'file':
            # Check if it's a directory
            path = Path(resource).resolve()
            if path.is_dir():
                return self._resolve_directory(str(path))

            # Single file - use analyzer
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
