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
from .detectors import detect_file_type
import os


def parse_file_location(file_arg: str) -> tuple[str, Optional[int], Optional[int]]:
    """
    Parse file argument that may include line numbers.

    Supports:
      - file.sql           → (file.sql, None, None)
      - file.sql:32        → (file.sql, 32, 32)
      - file.sql:10-50     → (file.sql, 10, 50)

    Args:
        file_arg: File argument from command line

    Returns:
        Tuple of (file_path, start_line, end_line)
    """
    if ':' not in file_arg:
        return file_arg, None, None

    # Split on last colon (handles paths like C:\Users\file.txt on Windows)
    file_path, line_spec = file_arg.rsplit(':', 1)

    try:
        if '-' in line_spec:
            # Range: file.sql:10-50
            start_str, end_str = line_spec.split('-', 1)
            start_line = int(start_str) if start_str else 1
            end_line = int(end_str) if end_str else None
            return file_path, start_line, end_line
        else:
            # Single line: file.sql:32
            line_num = int(line_spec)
            return file_path, line_num, line_num
    except ValueError:
        # Not a valid line number, treat whole thing as file path
        return file_arg, None, None


def get_analyzer(file_path: str, lines: List[str],
                 focus_start: Optional[int] = None,
                 focus_end: Optional[int] = None):
    """
    Get appropriate analyzer for file.

    Uses the plugin registry to find registered analyzers.
    Falls back to TextAnalyzer if no specific analyzer is registered.

    Args:
        file_path: Path to the file (used to determine extension)
        lines: File content lines
        focus_start: Optional start line for focused analysis
        focus_end: Optional end line for focused analysis

    Returns:
        Analyzer instance
    """
    # Get analyzer class from registry (automatically discovers plugins)
    analyzer_class = get_analyzer_for_file(file_path)

    # Fall back to text analyzer if no specific analyzer registered
    if not analyzer_class:
        analyzer_class = TextAnalyzer

    return analyzer_class(
        lines,
        file_path=file_path,
        focus_start=focus_start,
        focus_end=focus_end
    )


def reveal_level_0(summary: FileSummary) -> List[str]:
    """Generate Level 0 (metadata) output."""
    return format_metadata(summary)


def reveal_level_1(
    summary: FileSummary,
    grep_pattern: Optional[str] = None,
    case_sensitive: bool = False,
    focus_start: Optional[int] = None,
    focus_end: Optional[int] = None
) -> List[str]:
    """Generate Level 1 (structure) output."""
    analyzer = get_analyzer(
        str(summary.path),
        summary.lines,
        focus_start=focus_start,
        focus_end=focus_end
    )
    structure = analyzer.analyze_structure()

    # Check if analyzer provides custom formatting
    custom_lines = analyzer.format_structure(structure)
    if custom_lines is not None:
        # Use analyzer's custom formatter (pluggable!)
        lines = custom_lines
    else:
        # Fall back to generic formatter
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
    context: int = 0,
    focus_start: Optional[int] = None,
    focus_end: Optional[int] = None
) -> List[str]:
    """Generate Level 2 (preview) output."""
    analyzer = get_analyzer(
        str(summary.path),
        summary.lines,
        focus_start=focus_start,
        focus_end=focus_end
    )
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


def analyze_directory_level_0(dir_path: Path) -> List[str]:
    """Analyze directory metadata (level 0)."""
    lines = []
    lines.append("=== DIRECTORY METADATA (Level 0) ===")
    lines.append("")

    # Count files and gather stats
    all_files = []
    total_size = 0
    file_types = {}

    for root, dirs, files in os.walk(dir_path):
        for file in files:
            file_path = Path(root) / file
            try:
                size = file_path.stat().st_size
                total_size += size
                file_type = detect_file_type(file_path)
                file_types[file_type] = file_types.get(file_type, 0) + 1
                all_files.append((file_path, size, file_type))
            except:
                pass

    lines.append(f"Path:            {dir_path.name}/")
    lines.append(f"Total files:     {len(all_files):,}")
    lines.append(f"Total size:      {total_size:,} bytes ({total_size / 1024:.1f} KB)")
    lines.append("")

    if file_types:
        lines.append("File types:")
        for ftype, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {ftype:15} {count:4} files")

    lines.append("")
    lines.append("→ Next: --level 1 (file listing)")
    lines.append("  Tip: Use --grep to filter by filename or type")

    return lines


def analyze_directory_level_1(dir_path: Path, grep_pattern: Optional[str] = None) -> List[str]:
    """Analyze directory structure (level 1) - list files with brief info."""
    lines = []
    lines.append("=== DIRECTORY STRUCTURE (Level 1) ===")
    lines.append("")

    # Gather files
    files_by_type = {}
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            file_path = Path(root) / file
            try:
                file_type = detect_file_type(file_path)
                rel_path = file_path.relative_to(dir_path)
                size = file_path.stat().st_size

                # Apply grep filter if specified
                if grep_pattern and grep_pattern.lower() not in str(rel_path).lower():
                    continue

                if file_type not in files_by_type:
                    files_by_type[file_type] = []
                files_by_type[file_type].append((rel_path, size))
            except:
                pass

    # Format output by type
    for file_type in sorted(files_by_type.keys()):
        file_list = sorted(files_by_type[file_type])
        lines.append(f"{file_type.title()} files ({len(file_list)}):")
        for rel_path, size in file_list[:20]:  # Limit to 20 per type
            size_kb = size / 1024
            lines.append(f"  {str(rel_path):50} {size_kb:8.1f} KB")
        if len(file_list) > 20:
            lines.append(f"  ... and {len(file_list) - 20} more")
        lines.append("")

    lines.append("→ Next: --level 2 (detailed summaries)")
    lines.append("  Tip: Use 'reveal <filename>' to analyze individual files")

    return lines


def analyze_directory_level_2(dir_path: Path, grep_pattern: Optional[str] = None) -> List[str]:
    """Analyze directory with file summaries (level 2)."""
    lines = []
    lines.append("=== DIRECTORY DETAILS (Level 2) ===")
    lines.append("")

    files_analyzed = 0
    for root, dirs, files in os.walk(dir_path):
        for file in sorted(files)[:30]:  # Limit to 30 files
            file_path = Path(root) / file
            try:
                rel_path = file_path.relative_to(dir_path)

                # Apply grep filter
                if grep_pattern and grep_pattern.lower() not in str(rel_path).lower():
                    continue

                # Quick analysis
                file_type = detect_file_type(file_path)
                size = file_path.stat().st_size

                # Try to get line count for text files
                line_count = "?"
                try:
                    if size < 1024 * 1024:  # Only for files < 1MB
                        with open(file_path, 'r', encoding='utf-8') as f:
                            line_count = str(sum(1 for _ in f))
                except:
                    pass

                lines.append(f"📄 {rel_path}")
                lines.append(f"   Type: {file_type}, Size: {size / 1024:.1f} KB, Lines: {line_count}")
                lines.append("")
                files_analyzed += 1
            except:
                pass

    if files_analyzed == 0:
        lines.append("No files found matching criteria.")

    lines.append("→ Use 'reveal <specific-file>' for detailed analysis")

    return lines


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
  reveal schema.sql:32              # Jump to line 32
  reveal schema.sql:10-50           # Show lines 10-50
  reveal code.py:125 --level 1      # What's at line 125?
        """
    )

    parser.add_argument('file', type=str, help='File to reveal (supports file:line or file:start-end)')
    parser.add_argument('--level', '-l', type=int, default=0, choices=[0, 1, 2, 3],
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
        # Parse file location (may include :line or :start-end)
        file_str, focus_start, focus_end = parse_file_location(args.file)

        # Create file path
        file_path = Path(file_str).resolve()

        # Check if it's a directory
        if file_path.is_dir():
            # Handle directory analysis
            if args.level == 0:
                output = analyze_directory_level_0(file_path)
            elif args.level == 1:
                output = analyze_directory_level_1(file_path, args.grep_pattern)
            elif args.level == 2:
                output = analyze_directory_level_2(file_path, args.grep_pattern)
            else:  # level 3
                print("Error: Level 3 (full content) not supported for directories", file=sys.stderr)
                print("Hint: Use --level 2 for detailed file summaries", file=sys.stderr)
                sys.exit(1)

            # Print directory output
            for line in output:
                print(line)
            return

        # Regular file handling
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
                case_sensitive=args.grep_case_sensitive,
                focus_start=focus_start,
                focus_end=focus_end
            )
        elif args.level == 2:
            if summary.parse_error and summary.is_binary:
                print(f"Error: {summary.parse_error}", file=sys.stderr)
                sys.exit(1)
            output = reveal_level_2(
                summary,
                grep_pattern=args.grep_pattern,
                case_sensitive=args.grep_case_sensitive,
                context=args.context,
                focus_start=focus_start,
                focus_end=focus_end
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
