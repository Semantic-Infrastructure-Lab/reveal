"""Command-line interface for Progressive Reveal."""

import sys
import argparse
from pathlib import Path
from typing import List, Optional, Dict, Any

from .core import FileSummary, create_file_summary
from .analyzers import TextAnalyzer  # Fallback only
from .formatters import format_metadata, format_structure, format_preview, format_full_content
from .grep_filter import apply_grep_filter
from .registry import get_analyzer as get_analyzer_for_file


def get_analyzer(file_path: str, lines: List[str]):
    """
    Get appropriate analyzer for file.

    Uses the plugin registry to find registered analyzers.
    Falls back to TextAnalyzer if no specific analyzer is registered.

    Args:
        file_path: Path to the file (used to determine extension)
        lines: File content lines

    Returns:
        Analyzer instance
    """
    # Get analyzer class from registry (automatically discovers plugins)
    analyzer_class = get_analyzer_for_file(file_path)

    # Fall back to text analyzer if no specific analyzer registered
    if not analyzer_class:
        analyzer_class = TextAnalyzer

    return analyzer_class(lines)


def reveal_level_0(summary: FileSummary) -> List[str]:
    """Generate Level 0 (metadata) output."""
    return format_metadata(summary)


def reveal_level_1(
    summary: FileSummary,
    grep_pattern: Optional[str] = None,
    case_sensitive: bool = False
) -> List[str]:
    """Generate Level 1 (structure) output."""
    analyzer = get_analyzer(str(summary.path), summary.lines)
    structure = analyzer.analyze_structure()

    lines = format_structure(summary, structure, grep_pattern)

    # Apply grep filter if specified
    if grep_pattern:
        from .grep_filter import filter_structure_output
        lines = filter_structure_output(lines, grep_pattern, case_sensitive)

    return lines


def reveal_level_2(
    summary: FileSummary,
    grep_pattern: Optional[str] = None,
    case_sensitive: bool = False,
    context: int = 0
) -> List[str]:
    """Generate Level 2 (preview) output."""
    analyzer = get_analyzer(str(summary.path), summary.lines)
    preview = analyzer.generate_preview()

    # Apply grep filter if specified
    if grep_pattern:
        preview = apply_grep_filter(preview, grep_pattern, case_sensitive, context)

    return format_preview(summary, preview, grep_pattern)


def reveal_level_3(
    summary: FileSummary,
    page_size: int = 120,
    grep_pattern: Optional[str] = None,
    case_sensitive: bool = False,
    context: int = 0
) -> List[str]:
    """Generate Level 3 (full content) output."""
    # Create line tuples
    lines_with_numbers = [(i + 1, line) for i, line in enumerate(summary.lines)]

    # Apply grep filter if specified
    if grep_pattern:
        lines_with_numbers = apply_grep_filter(
            lines_with_numbers,
            grep_pattern,
            case_sensitive,
            context
        )

    # Apply paging
    total_lines = len(lines_with_numbers)
    if total_lines <= page_size:
        return format_full_content(summary, lines_with_numbers, grep_pattern, is_end=True)

    # For simplicity, show first page
    # In a real implementation, this would be interactive
    page_lines = lines_with_numbers[:page_size]
    return format_full_content(summary, page_lines, grep_pattern, is_end=False)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Progressive Reveal CLI - Explore files at different levels of detail',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Levels:
  0 = metadata
  1 = structural synopsis
  2 = content preview
  3 = full content (paged)

Examples:
  reveal myfile.yaml
  reveal myfile.json --level 1
  reveal myfile.py --level 2 --grep "class"
  reveal myfile.md --level 3 --page-size 50
        """
    )

    parser.add_argument('file', type=str, help='File to reveal')
    parser.add_argument('--level', type=int, default=0, choices=[0, 1, 2, 3],
                        help='Revelation level (default: 0)')
    parser.add_argument('--grep', '-m', type=str, dest='grep_pattern',
                        help='Filter pattern (regex)')
    parser.add_argument('--context', '-C', type=int, default=0,
                        help='Context lines around matches (default: 0)')
    parser.add_argument('--grep-case-sensitive', action='store_true',
                        help='Use case-sensitive grep matching')
    parser.add_argument('--page-size', type=int, default=120,
                        help='Page size for level 3 (default: 120)')
    parser.add_argument('--force', action='store_true',
                        help='Force read of large or binary files')

    args = parser.parse_args()

    try:
        # Create file path
        file_path = Path(args.file).resolve()

        # Create file summary
        summary = create_file_summary(file_path, force=args.force)

        # Handle errors
        if summary.parse_error and summary.is_binary and not args.force:
            print(f"Error: {summary.parse_error}", file=sys.stderr)
            sys.exit(1)

        # Generate output based on level
        if args.level == 0:
            output = reveal_level_0(summary)
        elif args.level == 1:
            if summary.parse_error and summary.is_binary:
                print(f"Error: {summary.parse_error}", file=sys.stderr)
                sys.exit(1)
            output = reveal_level_1(
                summary,
                grep_pattern=args.grep_pattern,
                case_sensitive=args.grep_case_sensitive
            )
        elif args.level == 2:
            if summary.parse_error and summary.is_binary:
                print(f"Error: {summary.parse_error}", file=sys.stderr)
                sys.exit(1)
            output = reveal_level_2(
                summary,
                grep_pattern=args.grep_pattern,
                case_sensitive=args.grep_case_sensitive,
                context=args.context
            )
        elif args.level == 3:
            if summary.parse_error and summary.is_binary:
                print(f"Error: {summary.parse_error}", file=sys.stderr)
                sys.exit(1)
            output = reveal_level_3(
                summary,
                page_size=args.page_size,
                grep_pattern=args.grep_pattern,
                case_sensitive=args.grep_case_sensitive,
                context=args.context
            )

        # Print output
        for line in output:
            print(line)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
