"""URI and file routing for reveal CLI.

This module handles dispatching to the correct handler based on:
- URI scheme (env://, ast://, help://, python://, json://, reveal://)
- File type (determined by extension)
- Directory handling
"""

import sys
import os
from pathlib import Path
from typing import Optional, Callable, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace


# ============================================================================
# Scheme-specific handlers (extracted to cli/scheme_handlers/)
# ============================================================================

from .scheme_handlers import (
    handle_env,
    handle_ast,
    handle_help,
    handle_python,
    handle_json,
    handle_reveal,
    handle_stats,
    handle_mysql,
    handle_imports,
)


# Legacy function names for backwards compatibility (to be removed later)
_handle_env = handle_env
_handle_ast = handle_ast
_handle_help = handle_help
_handle_python = handle_python
_handle_json = handle_json
_handle_reveal = handle_reveal
_handle_stats = handle_stats
_handle_mysql = handle_mysql
_handle_imports = handle_imports


# Dispatch table: scheme -> handler function
# To add a new scheme: create a _handle_<scheme> function and register here
SCHEME_HANDLERS: Dict[str, Callable] = {
    'env': _handle_env,
    'ast': _handle_ast,
    'mysql': _handle_mysql,
    'help': _handle_help,
    'python': _handle_python,
    'json': _handle_json,
    'reveal': _handle_reveal,
    'stats': _handle_stats,
    'imports': _handle_imports,
}


# ============================================================================
# Public API
# ============================================================================

def handle_uri(uri: str, element: Optional[str], args: 'Namespace') -> None:
    """Handle URI-based resources (env://, ast://, etc.).

    Args:
        uri: Full URI (e.g., env://, env://PATH)
        element: Optional element to extract
        args: Parsed command line arguments
    """
    if '://' not in uri:
        print(f"Error: Invalid URI format: {uri}", file=sys.stderr)
        sys.exit(1)

    scheme, resource = uri.split('://', 1)

    # Look up adapter from registry
    from ..adapters.base import get_adapter_class, list_supported_schemes
    from ..adapters import env, ast, help, python, json_adapter, reveal, mysql, imports  # noqa: F401 - Trigger registration

    adapter_class = get_adapter_class(scheme)
    if not adapter_class:
        print(f"Error: Unsupported URI scheme: {scheme}://", file=sys.stderr)
        schemes = ', '.join(f"{s}://" for s in list_supported_schemes())
        print(f"Supported schemes: {schemes}", file=sys.stderr)
        sys.exit(1)

    # Dispatch to scheme-specific handler
    handle_adapter(adapter_class, scheme, resource, element, args)


def handle_adapter(adapter_class: type, scheme: str, resource: str,
                   element: Optional[str], args: 'Namespace') -> None:
    """Handle adapter-specific logic for different URI schemes.

    Uses dispatch table for clean, extensible routing.

    Args:
        adapter_class: The adapter class to instantiate
        scheme: URI scheme (env, ast, etc.)
        resource: Resource part of URI
        element: Optional element to extract
        args: CLI arguments
    """
    handler = SCHEME_HANDLERS.get(scheme)
    if handler:
        handler(adapter_class, resource, element, args)
    else:
        # Fallback for unknown schemes (shouldn't happen if registry is in sync)
        print(f"Error: No handler for scheme '{scheme}'", file=sys.stderr)
        sys.exit(1)


def _load_gitignore_patterns(directory: Path) -> List[str]:
    """Load .gitignore patterns from directory.

    Args:
        directory: Directory containing .gitignore file

    Returns:
        List of gitignore patterns (empty if no .gitignore or on error)
    """
    gitignore_file = directory / '.gitignore'
    if not gitignore_file.exists():
        return []

    try:
        with open(gitignore_file) as f:
            return [
                line.strip() for line in f
                if line.strip() and not line.startswith('#')
            ]
    except Exception:
        return []


def _should_skip_file(relative_path: Path, gitignore_patterns: List[str]) -> bool:
    """Check if file should be skipped based on gitignore patterns.

    Args:
        relative_path: File path relative to repository root
        gitignore_patterns: List of gitignore patterns

    Returns:
        True if file should be skipped
    """
    import fnmatch

    for pattern in gitignore_patterns:
        if fnmatch.fnmatch(str(relative_path), pattern):
            return True
    return False


def _collect_files_to_check(directory: Path, gitignore_patterns: List[str]) -> List[Path]:
    """Collect all supported files in directory tree.

    Args:
        directory: Root directory to scan
        gitignore_patterns: Patterns to skip

    Returns:
        List of file paths to check
    """
    from ..base import get_analyzer

    files_to_check = []
    excluded_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv'}

    for root, dirs, files in os.walk(directory):
        # Filter out excluded directories
        dirs[:] = [d for d in dirs if d not in excluded_dirs]

        root_path = Path(root)
        for filename in files:
            file_path = root_path / filename
            relative_path = file_path.relative_to(directory)

            # Skip gitignored files
            if _should_skip_file(relative_path, gitignore_patterns):
                continue

            # Check if file has a supported analyzer
            if get_analyzer(str(file_path), allow_fallback=False):
                files_to_check.append(file_path)

    return files_to_check


def _check_and_report_file(
    file_path: Path,
    directory: Path,
    select: Optional[list[str]],
    ignore: Optional[list[str]]
) -> int:
    """Check a single file and report issues.

    Args:
        file_path: Path to file to check
        directory: Base directory for relative paths
        select: Rule codes to select (None = all)
        ignore: Rule codes to ignore

    Returns:
        Number of issues found (0 if no issues or on error)
    """
    from ..base import get_analyzer
    from ..rules import RuleRegistry

    try:
        analyzer_class = get_analyzer(str(file_path), allow_fallback=False)
        if not analyzer_class:
            return 0

        analyzer = analyzer_class(str(file_path))
        structure = analyzer.get_structure()
        content = analyzer.content

        detections = RuleRegistry.check_file(
            str(file_path), structure, content, select=select, ignore=ignore
        )

        if not detections:
            return 0

        # Print file header and detections
        relative = file_path.relative_to(directory)
        issue_count = len(detections)
        print(f"\n{relative}: Found {issue_count} issue{'s' if issue_count != 1 else ''}\n")

        for detection in detections:
            # Determine severity icon
            severity_icons = {"HIGH": "❌", "MEDIUM": "⚠️ ", "LOW": "ℹ️ "}
            icon = severity_icons.get(detection.severity.value, "ℹ️ ")

            print(f"{relative}:{detection.line}:{detection.column} {icon} {detection.rule_code} {detection.message}")

            if detection.suggestion:
                print(f"  💡 {detection.suggestion}")
            if detection.context:
                print(f"  📝 {detection.context}")

        return issue_count

    except Exception:
        # Skip files that can't be read or processed
        return 0


def handle_recursive_check(directory: Path, args: 'Namespace') -> None:
    """Handle recursive quality checking of a directory.

    Args:
        directory: Directory to check recursively
        args: Parsed arguments
    """
    # Load gitignore patterns and collect files
    gitignore_patterns = _load_gitignore_patterns(directory)
    files_to_check = _collect_files_to_check(directory, gitignore_patterns)

    if not files_to_check:
        print(f"No supported files found in {directory}")
        return

    # Parse select/ignore options once
    select = args.select.split(',') if args.select else None
    ignore = args.ignore.split(',') if args.ignore else None

    # Check all files and collect results
    total_issues = 0
    files_with_issues = 0

    for file_path in sorted(files_to_check):
        issue_count = _check_and_report_file(file_path, directory, select, ignore)
        if issue_count > 0:
            total_issues += issue_count
            files_with_issues += 1

    # Print summary
    print(f"\n{'='*60}")
    print(f"Checked {len(files_to_check)} files")
    if total_issues > 0:
        print(f"Found {total_issues} issue{'s' if total_issues != 1 else ''} in {files_with_issues} file{'s' if files_with_issues != 1 else ''}")
        sys.exit(1)
    else:
        print(f"✅ No issues found")
        sys.exit(0)


def handle_file_or_directory(path_str: str, args: 'Namespace') -> None:
    """Handle regular file or directory path.

    Args:
        path_str: Path string to file or directory
        args: Parsed arguments
    """
    from ..tree_view import show_directory_tree

    path = Path(path_str)
    if not path.exists():
        print(f"Error: {path_str} not found", file=sys.stderr)
        sys.exit(1)

    if path.is_dir():
        # Check if recursive mode is enabled with --check
        if getattr(args, 'recursive', False) and getattr(args, 'check', False):
            handle_recursive_check(path, args)
        else:
            output = show_directory_tree(str(path), depth=args.depth,
                                         max_entries=args.max_entries, fast=args.fast)
            print(output)
    elif path.is_file():
        handle_file(str(path), args.element, args.meta, args.format, args)
    else:
        print(f"Error: {path_str} is neither file nor directory", file=sys.stderr)
        sys.exit(1)


def handle_file(path: str, element: Optional[str], show_meta: bool,
                output_format: str, args: Optional['Namespace'] = None) -> None:
    """Handle file analysis.

    Args:
        path: File path
        element: Optional element to extract
        show_meta: Whether to show metadata only
        output_format: Output format ('text', 'json', 'grep')
        args: Full argument namespace (for filter options)
    """
    from ..base import get_analyzer
    from ..display import show_structure, show_metadata, extract_element

    allow_fallback = not getattr(args, 'no_fallback', False) if args else True

    analyzer_class = get_analyzer(path, allow_fallback=allow_fallback)
    if not analyzer_class:
        ext = Path(path).suffix or '(no extension)'
        print(f"Error: No analyzer found for {path} ({ext})", file=sys.stderr)
        print(f"\nError: File type '{ext}' is not supported yet", file=sys.stderr)
        print("Run 'reveal --list-supported' to see all supported file types", file=sys.stderr)
        print("Visit https://github.com/Semantic-Infrastructure-Lab/reveal to request new file types", file=sys.stderr)
        sys.exit(1)

    analyzer = analyzer_class(path)

    if show_meta:
        show_metadata(analyzer, output_format)
        return

    if args and getattr(args, 'check', False):
        from ..main import run_pattern_detection
        run_pattern_detection(analyzer, path, output_format, args)
        return

    if element:
        extract_element(analyzer, element, output_format)
        return

    show_structure(analyzer, output_format, args)


# Backward compatibility aliases
_handle_adapter = handle_adapter
_handle_file_or_directory = handle_file_or_directory
