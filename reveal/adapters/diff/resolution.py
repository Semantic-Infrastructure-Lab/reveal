"""General URI resolution and utilities for diff adapter."""

import inspect
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, cast

from .git import resolve_git_ref, resolve_git_adapter
from ..base import get_adapter_class


def resolve_uri(uri: str, **kwargs) -> Dict[str, Any]:
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
            return resolve_git_adapter(resource)
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
            return resolve_git_ref(git_ref, path)
        else:
            # Repository overview
            return resolve_git_adapter(resource)

    # For file scheme, handle differently (no adapter class, uses get_analyzer)
    if scheme == 'file':
        # Check if it's a directory
        file_path = Path(resource).resolve()
        if file_path.is_dir():
            return resolve_directory(str(file_path))

        # Single file - use analyzer
        from ...registry import get_analyzer
        analyzer_class = get_analyzer(resource, allow_fallback=True)
        if not analyzer_class:
            raise ValueError(f"No analyzer found for file: {resource}")
        analyzer = analyzer_class(resource)
        return cast(Dict[str, Any], analyzer.get_structure(**kwargs))

    # Get registered adapter
    adapter_class = get_adapter_class(scheme)
    if not adapter_class:
        raise ValueError(f"Unsupported URI scheme: {scheme}://")

    # Instantiate and get structure
    adapter = instantiate_adapter(adapter_class, scheme, resource)
    return cast(Dict[str, Any], adapter.get_structure(**kwargs))


def resolve_directory(dir_path: str) -> Dict[str, Any]:
    """Resolve a directory to aggregated structure.

    Args:
        dir_path: Path to directory

    Returns:
        Dict with aggregated structures from all files
    """
    from ...registry import get_analyzer

    directory = Path(dir_path).resolve()
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {dir_path}")

    files = find_analyzable_files(directory)

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


def instantiate_adapter(adapter_class: type, scheme: str, resource: str):
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
        from ...registry import get_analyzer
        analyzer_class = get_analyzer(resource, allow_fallback=True)
        if not analyzer_class:
            raise ValueError(f"No analyzer found for file: {resource}")
        return analyzer_class(resource)

    # Try to determine constructor signature
    try:
        sig = inspect.signature(adapter_class.__init__)  # type: ignore[misc]
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


def find_analyzable_files(directory: Path) -> List[Path]:
    """Find all files in directory that can be analyzed.

    Args:
        directory: Directory path to scan

    Returns:
        List of file paths that have analyzers
    """
    from ...registry import get_analyzer

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


def extract_metadata(structure: Dict[str, Any], uri: str) -> Dict[str, str]:
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


def find_element(structure: Dict[str, Any], element_name: str) -> Optional[Dict[str, Any]]:
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
            return cast(Dict[str, Any], func)

    # Search in classes
    for cls in struct.get('classes', []):
        if cls.get('name') == element_name:
            return cast(Dict[str, Any], cls)

        # Search in class methods
        for method in cls.get('methods', []):
            if method.get('name') == element_name:
                return cast(Dict[str, Any], method)

    return None
