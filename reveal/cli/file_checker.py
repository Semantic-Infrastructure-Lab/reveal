"""File checking utilities for recursive directory analysis.

This module handles quality checking of files in a directory tree:
- Loading and respecting .gitignore patterns
- Collecting supported files for analysis
- Running quality checks and reporting results
"""

import sys
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace

# Minimum files before paying process-pool startup overhead.
# On Linux (fork), startup is cheap; on Windows/macOS (spawn) it's heavier,
# but the break-even is still low for CPU-bound work.
_PARALLEL_THRESHOLD = 4


def _parallel_worker(packed_args: tuple) -> tuple:
    """Check one file and return results without printing.

    Module-level so it is picklable by multiprocessing.

    Args:
        packed_args: (file_path, directory, select, ignore)

    Returns:
        (file_path, issue_count, detections)
    """
    file_path, directory, select, ignore = packed_args
    issue_count, detections = check_and_collect_file(file_path, directory, select, ignore)
    return file_path, issue_count, detections


def _run_parallel(files: List[Path], directory: Path, select, ignore) -> list:
    """Run file checks in parallel, preserving input order in results.

    Args:
        files: Already-sorted list of files to check
        directory: Base directory for relative paths
        select: Rule codes to select
        ignore: Rule codes to ignore

    Returns:
        List of (file_path, issue_count, detections) in same order as input
    """
    # Benchmark shows 4 workers captures ~74% of max speedup (vs 12 workers at
    # 100%). Beyond 4, marginal gain is <0.5s while fork overhead grows.
    # Capping at 4 leaves remaining cores free and reduces IPC pressure.
    workers = min(4, os.cpu_count() or 4, len(files))
    args_iter = [(f, directory, select, ignore) for f in files]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_parallel_worker, args_iter))


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
        with open(gitignore_file, encoding='utf-8') as f:
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
    from ..registry import get_analyzer

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
    from ..registry import get_analyzer
    from ..rules import RuleRegistry

    try:
        analyzer_class = get_analyzer(str(file_path), allow_fallback=False)
        if not analyzer_class:
            return 0

        analyzer = analyzer_class(str(file_path))
        # Always request links so link-checking rules (L001, L002) can reuse
        # this parse instead of creating a second analyzer for each file.
        structure = analyzer.get_structure(extract_links=True)
        content = analyzer.content

        detections = RuleRegistry.check_file(
            str(file_path), structure, content, select=select, ignore=ignore
        )

        if not detections:
            return 0

        # Print file header and detections
        # Always use CWD-relative paths so editor "click to jump" works regardless
        # of where the target argument points (matches ruff/mypy/flake8 behavior).
        cwd = Path.cwd()
        try:
            relative = file_path.relative_to(cwd)
        except ValueError:
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


def check_and_collect_file(
    file_path: Path,
    directory: Path,
    select: Optional[list[str]],
    ignore: Optional[list[str]]
) -> tuple[int, list]:
    """Check a single file and return structured results.

    Args:
        file_path: Path to file to check
        directory: Base directory for relative paths
        select: Rule codes to select (None = all)
        ignore: Rule codes to ignore

    Returns:
        Tuple of (issue_count, detections_list)
    """
    from ..registry import get_analyzer
    from ..rules import RuleRegistry

    try:
        analyzer_class = get_analyzer(str(file_path), allow_fallback=False)
        if not analyzer_class:
            return 0, []

        analyzer = analyzer_class(str(file_path))
        # Always request links so link-checking rules (L001, L002) can reuse
        # this parse instead of creating a second analyzer for each file.
        structure = analyzer.get_structure(extract_links=True)
        content = analyzer.content

        detections = RuleRegistry.check_file(
            str(file_path), structure, content, select=select, ignore=ignore
        )

        return len(detections), detections

    except Exception:
        # Skip files that can't be read or processed
        return 0, []


def _build_cli_overrides(args: 'Namespace') -> dict:
    """Build CLI overrides dictionary from args.

    Args:
        args: Parsed arguments

    Returns:
        CLI overrides dict for config system
    """
    cli_overrides = {}
    if args.select or args.ignore:
        rules_override = {}
        if args.select:
            rules_override['select'] = [r.strip() for r in args.select.split(',')]
        if args.ignore:
            rules_override['disable'] = [r.strip() for r in args.ignore.split(',')]
        cli_overrides['rules'] = rules_override
    return cli_overrides


def _handle_no_files_found(directory: Path, output_format: str) -> None:
    """Handle case when no files found to check.

    Args:
        directory: Directory that was checked
        output_format: Output format (json or text)
    """
    import json

    if output_format == 'json':
        print(json.dumps({
            "files": [],
            "summary": {
                "files_checked": 0,
                "files_with_issues": 0,
                "total_issues": 0,
                "exit_code": 0
            }
        }, indent=2))
    else:
        print(f"No supported files found in {directory}")


def _check_files_json(
    files: List[Path], directory: Path, select: Optional[List[str]], ignore: Optional[List[str]]
) -> tuple:
    """Check files and collect JSON results.

    Args:
        files: List of files to check
        directory: Base directory
        select: Rule codes to select
        ignore: Rule codes to ignore

    Returns:
        Tuple of (total_issues, files_with_issues, file_results)
    """
    total_issues = 0
    files_with_issues = 0
    file_results = []
    sorted_files = sorted(files)

    if len(sorted_files) >= _PARALLEL_THRESHOLD:
        try:
            results = _run_parallel(sorted_files, directory, select, ignore)
        except Exception:
            results = [(f, *check_and_collect_file(f, directory, select, ignore)) for f in sorted_files]
    else:
        results = [(f, *check_and_collect_file(f, directory, select, ignore)) for f in sorted_files]

    cwd = Path.cwd()
    for file_path, issue_count, detections in results:
        if issue_count > 0:
            total_issues += issue_count
            files_with_issues += 1
            try:
                rel_path = file_path.relative_to(cwd)
            except ValueError:
                rel_path = file_path.relative_to(directory)
            file_results.append({
                "file": str(rel_path),
                "issues": issue_count,
                "detections": [
                    {
                        "line": d.line,
                        "column": d.column,
                        "rule_code": d.rule_code,
                        "message": d.message,
                        "severity": d.severity.value,
                        "suggestion": d.suggestion,
                        "context": d.context
                    }
                    for d in detections
                ]
            })

    return total_issues, files_with_issues, file_results


def _check_files_text(
    files: List[Path], directory: Path, select: Optional[List[str]], ignore: Optional[List[str]]
) -> tuple:
    """Check files with text output.

    Args:
        files: List of files to check
        directory: Base directory
        select: Rule codes to select
        ignore: Rule codes to ignore

    Returns:
        Tuple of (total_issues, files_with_issues)
    """
    total_issues = 0
    files_with_issues = 0
    sorted_files = sorted(files)

    if len(sorted_files) >= _PARALLEL_THRESHOLD:
        try:
            results = _run_parallel(sorted_files, directory, select, ignore)
        except Exception:
            results = [(f, *check_and_collect_file(f, directory, select, ignore)) for f in sorted_files]
    else:
        results = [(f, *check_and_collect_file(f, directory, select, ignore)) for f in sorted_files]

    cwd = Path.cwd()
    severity_icons = {"HIGH": "❌", "MEDIUM": "⚠️ ", "LOW": "ℹ️ "}
    for file_path, issue_count, detections in results:
        if issue_count > 0:
            total_issues += issue_count
            files_with_issues += 1
            try:
                relative = file_path.relative_to(cwd)
            except ValueError:
                relative = file_path.relative_to(directory)
            print(f"\n{relative}: Found {issue_count} issue{'s' if issue_count != 1 else ''}\n")
            for detection in detections:
                icon = severity_icons.get(detection.severity.value, "ℹ️ ")
                print(f"{relative}:{detection.line}:{detection.column} {icon} {detection.rule_code} {detection.message}")
                if detection.suggestion:
                    print(f"  💡 {detection.suggestion}")
                if detection.context:
                    print(f"  📝 {detection.context}")

    return total_issues, files_with_issues


def _print_json_output(
    file_results: List[dict], files_checked: int, files_with_issues: int, total_issues: int
) -> None:
    """Print JSON output with results and summary.

    Args:
        file_results: List of file result dicts
        files_checked: Total files checked
        files_with_issues: Files with issues count
        total_issues: Total issues count
    """
    import json

    result = {
        "files": file_results,
        "summary": {
            "files_checked": files_checked,
            "files_with_issues": files_with_issues,
            "total_issues": total_issues,
            "exit_code": 1 if total_issues > 0 else 0
        }
    }
    print(json.dumps(result, indent=2))


def _print_text_summary(
    files_checked: int, files_with_issues: int, total_issues: int, directory: Path, config
) -> None:
    """Print text summary with breadcrumbs.

    Args:
        files_checked: Total files checked
        files_with_issues: Files with issues count
        total_issues: Total issues count
        directory: Directory checked
        config: RevealConfig instance
    """
    print(f"\n{'='*60}")
    print(f"Checked {files_checked} files")
    if total_issues > 0:
        print(f"Found {total_issues} issue{'s' if total_issues != 1 else ''} in {files_with_issues} file{'s' if files_with_issues != 1 else ''}")
    else:
        print("✅ No issues found")

    # Print workflow breadcrumbs
    from ..utils.breadcrumbs import print_breadcrumbs
    print_breadcrumbs(
        'directory-check',
        str(directory),
        config=config,
        total_issues=total_issues,
        files_with_issues=files_with_issues,
        files_checked=files_checked
    )


def handle_recursive_check(directory: Path, args: 'Namespace') -> None:
    """Handle recursive quality checking of a directory.

    Args:
        directory: Directory to check recursively
        args: Parsed arguments
    """
    # Resolve to absolute so all downstream paths are absolute and can be
    # expressed relative to CWD (matching ruff/mypy/flake8 path behavior).
    directory = directory.resolve()

    # Build CLI overrides and initialize config
    cli_overrides = _build_cli_overrides(args)
    from reveal.config import RevealConfig
    config = RevealConfig.get(start_path=directory, cli_overrides=cli_overrides if cli_overrides else None)

    # Collect files to check
    gitignore_patterns = load_gitignore_patterns(directory)
    files_to_check = collect_files_to_check(directory, gitignore_patterns)

    # Handle no files found
    output_format = getattr(args, 'format', 'text')
    if not files_to_check:
        _handle_no_files_found(directory, output_format)
        return

    # Parse select/ignore options
    select = args.select.split(',') if args.select else None
    ignore = args.ignore.split(',') if args.ignore else None

    # Check files based on output format
    if output_format == 'json':
        total_issues, files_with_issues, file_results = _check_files_json(
            files_to_check, directory, select, ignore
        )
        _print_json_output(file_results, len(files_to_check), files_with_issues, total_issues)
    else:
        total_issues, files_with_issues = _check_files_text(
            files_to_check, directory, select, ignore
        )
        _print_text_summary(len(files_to_check), files_with_issues, total_issues, directory, config)

    # Exit with appropriate code
    sys.exit(1 if total_issues > 0 else 0)


# Legacy underscore-prefixed names for backwards compatibility
_load_gitignore_patterns = load_gitignore_patterns
_should_skip_file = should_skip_file
_collect_files_to_check = collect_files_to_check
_check_and_report_file = check_and_report_file
