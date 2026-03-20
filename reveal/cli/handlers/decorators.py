"""Decorator statistics handler for reveal CLI.

Implements --decorator-stats: scans Python files and reports
decorator usage across a file or directory.
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from argparse import Namespace


def _collect_decorator_counts(structure: dict) -> Dict[str, int]:
    """Count all decorator occurrences in a file structure dict."""
    counts: Dict[str, int] = {}
    for category in ('functions', 'classes'):
        for item in structure.get(category, []):
            for dec in item.get('decorators', []):
                dec_name = dec.split('(')[0]
                counts[dec_name] = counts.get(dec_name, 0) + 1
    return counts


def _extract_decorators_from_file(file_path: str):
    """Extract decorator information from a single Python file.

    Args:
        file_path: Path to Python file to analyze

    Returns:
        Tuple of (decorators_found dict, file_has_decorators bool) or None if file can't be analyzed
    """
    from ...registry import get_analyzer

    try:
        analyzer_class = get_analyzer(file_path)
        if not analyzer_class:
            return None

        analyzer = analyzer_class(file_path)
        structure = analyzer.get_structure()
        if not structure:
            return None

        decorators_found = _collect_decorator_counts(structure)
        return (decorators_found, len(decorators_found) > 0)

    except Exception:
        return None  # Skip files we can't analyze


def _categorize_decorators(sorted_decorators, decorator_files):
    """Categorize decorators into stdlib and custom.

    Args:
        sorted_decorators: List of (decorator, count) tuples sorted by count
        decorator_files: Dict mapping decorator -> set of files

    Returns:
        Tuple of (stdlib_list, custom_list) where each is list of (name, count, file_count) tuples
    """
    stdlib_prefixes = ['@property', '@staticmethod', '@classmethod', '@abstractmethod',
                       '@dataclass', '@cached_property', '@lru_cache', '@functools.wraps',
                       '@contextmanager', '@asynccontextmanager', '@overload', '@final',
                       '@pytest.fixture', '@pytest.mark']

    stdlib_list = []
    custom_list = []

    for dec, count in sorted_decorators:
        file_count = len(decorator_files[dec])
        if any(dec.startswith(prefix) for prefix in stdlib_prefixes):
            stdlib_list.append((dec, count, file_count))
        else:
            custom_list.append((dec, count, file_count))

    return stdlib_list, custom_list


def _print_decorator_category(title, decorators_list):
    """Print a category of decorators.

    Args:
        title: Category title
        decorators_list: List of (decorator, count, file_count) tuples
    """
    if not decorators_list:
        return

    print(f"{title}:")
    for dec, count, file_count in decorators_list:
        files_text = f"{file_count} file{'s' if file_count != 1 else ''}"
        print(f"  {dec:<30s} {count:>4d} occurrences ({files_text})")
    print()


def _collect_file_decorators(file_path, decorator_counts, decorator_files):
    """Collect decorators from a single file and update statistics.

    Args:
        file_path: Path to file to analyze
        decorator_counts: Dict to update with decorator counts
        decorator_files: Dict to update with files per decorator

    Returns:
        Tuple of (file_processed, file_has_decorators)
    """
    result = _extract_decorators_from_file(str(file_path))
    if not result:
        return (False, False)

    decorators_found, has_decorators = result
    if has_decorators:
        for dec_name, count in decorators_found.items():
            decorator_counts[dec_name] += count
            decorator_files[dec_name].add(str(file_path))

    return (True, has_decorators)


def _scan_python_files(target_path):
    """Scan Python files and collect decorator statistics.

    Args:
        target_path: Path object (file or directory) to scan

    Returns:
        Tuple of (decorator_counts, decorator_files, total_files, total_decorated)
    """
    from collections import defaultdict

    decorator_counts: Dict[str, int] = defaultdict(int)
    decorator_files: Dict[str, set] = defaultdict(set)
    total_files = 0
    total_decorated = 0

    if target_path.is_file():
        processed, has_decorators = _collect_file_decorators(
            target_path, decorator_counts, decorator_files
        )
        if processed:
            total_files = 1
            total_decorated = 1 if has_decorators else 0
    elif target_path.is_dir():
        for file_path in target_path.rglob('*.py'):
            if '.venv' in str(file_path) or 'node_modules' in str(file_path):
                continue
            processed, has_decorators = _collect_file_decorators(
                file_path, decorator_counts, decorator_files
            )
            if processed:
                total_files += 1
            if processed and has_decorators:
                total_decorated += 1

    return decorator_counts, decorator_files, total_files, total_decorated


def handle_decorator_stats(path: str):
    """Handle --decorator-stats flag to show decorator usage statistics.

    Scans Python files and reports decorator usage across the codebase.

    Args:
        path: File or directory path to scan
    """
    target_path = Path(path) if path else Path('.')

    if not target_path.exists():
        print(f"Error: {path} not found", file=sys.stderr)
        sys.exit(1)

    # Scan files and collect statistics
    decorator_counts, decorator_files, total_files, total_decorated = _scan_python_files(target_path)

    if total_files == 0:
        print(f"No Python files found in {path or '.'}")
        sys.exit(0)

    # Print header
    print(f"Decorator Usage in {target_path} ({total_files} files)\n")

    if not decorator_counts:
        print("No decorators found")
        sys.exit(0)

    # Categorize and print decorators
    sorted_decorators = sorted(decorator_counts.items(), key=lambda x: -x[1])
    stdlib_list, custom_list = _categorize_decorators(sorted_decorators, decorator_files)

    _print_decorator_category("Standard Library Decorators", stdlib_list)
    _print_decorator_category("Custom/Third-Party Decorators", custom_list)

    # Summary
    print("Summary:")
    print(f"  Total decorators: {sum(decorator_counts.values())}")
    print(f"  Unique decorators: {len(decorator_counts)}")
    print(f"  Files with decorators: {total_decorated}/{total_files} ({100*total_decorated//total_files}%)")

    sys.exit(0)
