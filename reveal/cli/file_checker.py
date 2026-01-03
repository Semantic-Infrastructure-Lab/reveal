"""File checking utilities for recursive directory analysis.

This module handles quality checking of files in a directory tree:
- Loading and respecting .gitignore patterns
- Collecting supported files for analysis
- Running quality checks and reporting results
"""

import sys
import os
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace


def load_gitignore_patterns(directory: Path) -> List[str]:
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


def should_skip_file(relative_path: Path, gitignore_patterns: List[str]) -> bool:
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


def collect_files_to_check(directory: Path, gitignore_patterns: List[str]) -> List[Path]:
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
            if should_skip_file(relative_path, gitignore_patterns):
                continue

            # Check if file has a supported analyzer
            if get_analyzer(str(file_path), allow_fallback=False):
                files_to_check.append(file_path)

    return files_to_check


def check_and_report_file(
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
    # Build CLI overrides for config system
    cli_overrides = {}
    if args.select or args.ignore:
        rules_override = {}
        if args.select:
            rules_override['select'] = [r.strip() for r in args.select.split(',')]
        if args.ignore:
            rules_override['disable'] = [r.strip() for r in args.ignore.split(',')]
        cli_overrides['rules'] = rules_override

    # Initialize config with CLI overrides (highest precedence)
    from reveal.config import RevealConfig
    config = RevealConfig.get(start_path=directory, cli_overrides=cli_overrides if cli_overrides else None)

    # Load gitignore patterns and collect files
    gitignore_patterns = load_gitignore_patterns(directory)
    files_to_check = collect_files_to_check(directory, gitignore_patterns)

    if not files_to_check:
        print(f"No supported files found in {directory}")
        return

    # Parse select/ignore options for backwards compatibility with RuleRegistry
    select = args.select.split(',') if args.select else None
    ignore = args.ignore.split(',') if args.ignore else None

    # Check all files and collect results
    total_issues = 0
    files_with_issues = 0

    for file_path in sorted(files_to_check):
        issue_count = check_and_report_file(file_path, directory, select, ignore)
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


# Legacy underscore-prefixed names for backwards compatibility
_load_gitignore_patterns = load_gitignore_patterns
_should_skip_file = should_skip_file
_collect_files_to_check = collect_files_to_check
_check_and_report_file = check_and_report_file
