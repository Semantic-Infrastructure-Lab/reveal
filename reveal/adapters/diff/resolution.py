"""General URI resolution and utilities for diff adapter."""

import inspect
from pathlib import Path
from typing import Dict, Any, Optional, Iterator, cast

from .git import resolve_git_ref, resolve_git_adapter, read_git_text
from ..base import get_adapter_class
from ...diff.structure_diff import element_categories
from ...errors import NotApplicableError
from ...registry import get_analyzer
from ...utils.path_utils import _walk_code_files
from reveal.utils.lines import split_lines


_CODE_KEYS = ('functions', 'classes', 'imports')


def require_comparable(structure: Dict[str, Any], uri: str) -> Dict[str, Any]:
    """Return ``structure`` if diff:// can compare it, else decline (BACK-1689).

    diff:// compares a code structure's element categories (functions, classes, imports,
    interfaces, structs ...; BACK-1732). A code analyzer's structure is untyped (an empty
    file has no keys at all) or carries functions, classes or imports, flat or under
    ``structure``; a directory aggregate is typed 'directory'/'git_directory'. Anything
    else (sqlite, env, JSON, YAML, Markdown, TOML ...) has none of them and would
    compare as "No structural changes detected" whatever differs: a false clean.
    """
    struct = structure.get('structure', structure)
    kind = structure.get('type')
    if kind in (None, 'directory', 'git_directory') or any(k in struct for k in _CODE_KEYS):
        return structure
    raise NotApplicableError(
        f"diff:// compares functions, classes and imports; {uri} ({kind}) has none, "
        f"so a structural diff would not show what differs. "
        f"Diff each side's own output with the shell diff instead.")


def resolve_uri(uri: str, **kwargs) -> Dict[str, Any]:
    """Resolve a URI to its structure, declining what diff:// cannot compare.

    Raises NotApplicableError for a resource with no functions, classes or imports
    (see ``require_comparable``).
    """
    return require_comparable(_resolve_structure(uri, **kwargs), uri)


def _resolve_structure(uri: str, **kwargs) -> Dict[str, Any]:
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

    directory = Path(dir_path).resolve()
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {dir_path}")

    # Every element category any file has, not only functions/classes/imports (BACK-1732).
    aggregated: Dict[str, list] = {'functions': [], 'classes': [], 'imports': []}
    file_count = 0

    for file_path in find_analyzable_files(directory):
        rel_path = file_path.relative_to(directory)
        analyzer_class = get_analyzer(str(file_path), allow_fallback=False)
        if analyzer_class:
            file_count += 1
            analyzer = analyzer_class(str(file_path))
            structure = analyzer.get_structure()

            # Extract structure (handle both nested and flat)
            struct = structure.get('structure', structure)

            # Add file context to each element
            for category in element_categories(struct):
                for item in struct[category]:
                    if isinstance(item, dict):
                        item['file'] = rel_path.as_posix()
                    aggregated.setdefault(category, []).append(item)

    return {
        **aggregated,
        'type': 'directory',
        'path': str(directory),
        'file_count': file_count,
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
        except TypeError:
            return adapter_class()


def find_analyzable_files(directory: Path) -> Iterator[Path]:
    """Yield files in directory that can be analyzed.

    Args:
        directory: Directory path to scan

    Yields:
        File paths that have analyzers (generator — avoids materializing
        the full list into memory before processing begins).
    """
    # The shared walk (BACK-1223): its own os.walk applied .gitignore (BACK-1386) and the
    # skip-dir list (BACK-552) but not REVEAL_IGNORE or --exclude.
    for file_path in _walk_code_files(directory):
        if get_analyzer(str(file_path), allow_fallback=False):
            yield file_path


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


def _iter_elements(structure: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    """Yield every element a diff can address: functions, classes and class methods.

    Handles both the nested (``{'structure': {...}}``) and flat structure formats.
    """
    struct = structure.get('structure', structure)
    yield from struct.get('functions', [])
    for cls in struct.get('classes', []):
        yield cls
        yield from cls.get('methods', [])


def find_element(structure: Dict[str, Any], element_name: str) -> Optional[Dict[str, Any]]:
    """Find a specific element within a structure.

    Args:
        structure: Structure dict from adapter
        element_name: Name of element to find

    Returns:
        Element dict or None if not found
    """
    for element in _iter_elements(structure):
        if element.get('name') == element_name:
            return element
    return None


def element_names(structure: Dict[str, Any]) -> list:
    """Names of the elements ``find_element`` can find in a structure, in order, once each."""
    return list(dict.fromkeys(e['name'] for e in _iter_elements(structure) if e.get('name')))


def read_source_text(uri: str) -> Optional[str]:
    """Return the whole source text of the resource ``uri`` names.

    Only single-file resources (plain path, ``file://``, ``git://``) carry
    source; directories and other adapters return None, meaning "not comparable".
    """
    scheme, _, resource = uri.partition('://') if '://' in uri else ('file', '', uri)
    if scheme == 'git':
        return read_git_text(resource)
    if scheme == 'file':
        try:
            return Path(resource).read_text(encoding='utf-8', errors='replace')
        except OSError:
            return None
    return None


def read_element_source(uri: str, element: Dict[str, Any]) -> Optional[str]:
    """Return the source text of ``element`` in the resource ``uri`` names, or None
    where ``read_source_text`` has none."""
    start, end = element.get('line'), element.get('line_end')
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    text = read_source_text(uri)
    if text is None:
        return None
    return '\n'.join(split_lines(text)[start - 1:end])
