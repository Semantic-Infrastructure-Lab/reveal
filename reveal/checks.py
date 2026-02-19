"""File checking operations (schema validation, pattern detection).

This module is separate from main.py to avoid circular dependencies with cli.routing.
"""

import sys
from typing import Optional, Any, List

from .base import FileAnalyzer
from .utils import safe_json_dumps, get_file_type_from_analyzer, print_breadcrumbs


def _format_detections_json(path: str, detections: List[Any]) -> None:
    """Format detections as JSON.

    Args:
        path: File path
        detections: List of Detection objects
    """
    result = {
        'file': path,
        'detections': [d.to_dict() for d in detections],
        'total': len(detections)
    }
    print(safe_json_dumps(result))


def _format_detections_grep(detections: List[Any]) -> None:
    """Format detections as grep output.

    Args:
        detections: List of Detection objects
    """
    for d in detections:
        print(f"{d.file_path}:{d.line}:{d.column}:{d.rule_code}:{d.message}")


def _format_detections_text(path: str, detections: List[Any]) -> None:
    """Format detections as human-readable text.

    Args:
        path: File path
        detections: List of Detection objects
    """
    if not detections:
        print(f"{path}: ✅ No issues found")
        return

    print(f"{path}: Found {len(detections)} issues\n")
    for d in sorted(detections, key=lambda x: (x.line, x.column)):
        print(d)
        print()


def run_pattern_detection(
    analyzer: FileAnalyzer,
    path: str,
    output_format: str,
    args: Any,
    config: Optional[Any] = None
) -> None:
    """Run pattern detection rules on a file.

    Args:
        analyzer: File analyzer instance
        path: File path
        output_format: Output format ('text', 'json', 'grep')
        args: CLI arguments (for --select, --ignore)
        config: Optional RevealConfig for breadcrumb settings
    """
    from .rules import RuleRegistry

    # Parse select/ignore options
    select = args.select.split(',') if args.select else None
    ignore = args.ignore.split(',') if args.ignore else None

    # Get structure and content
    structure = analyzer.get_structure()
    content = analyzer.content

    # Run rules
    detections = RuleRegistry.check_file(
        path, structure, content, select=select, ignore=ignore
    )

    # Format and output results
    formatters = {
        'json': lambda: _format_detections_json(path, detections),
        'grep': lambda: _format_detections_grep(detections),
        'text': lambda: _format_detections_text(path, detections),
    }

    formatter = formatters.get(output_format, formatters['text'])
    formatter()

    # Print breadcrumbs after text output (not for json/grep)
    if output_format == 'text':
        file_type = get_file_type_from_analyzer(analyzer)
        print_breadcrumbs('quality-check', path, file_type=file_type, config=config,
                         detections=detections)


def run_schema_validation(
    analyzer: FileAnalyzer,
    path: str,
    schema_name: str,
    output_format: str,
    args: Any
) -> None:
    """Run schema validation on front matter.

    Args:
        analyzer: File analyzer instance
        path: File path
        schema_name: Schema name or path to schema file
        output_format: Output format ('text', 'json', 'grep')
        args: CLI arguments (for --select, --ignore)
    """
    from .schemas.frontmatter import load_schema
    from .rules.frontmatter import set_validation_context, clear_validation_context
    from .rules import RuleRegistry

    # Check if file is markdown (schema validation is for markdown front matter)
    if not path.lower().endswith(('.md', '.markdown')):
        print("Warning: Schema validation is designed for markdown files", file=sys.stderr)
        print(f"         File '{path}' does not appear to be markdown", file=sys.stderr)
        print("         Continuing anyway...\n", file=sys.stderr)

    # Load schema
    schema = load_schema(schema_name)
    if not schema:
        print(f"Error: Schema '{schema_name}' not found", file=sys.stderr)
        print("\nAvailable built-in schemas:", file=sys.stderr)
        from .schemas.frontmatter import list_schemas
        for name in list_schemas():
            print(f"  - {name}", file=sys.stderr)
        print("\nOr provide a path to a custom schema file", file=sys.stderr)
        sys.exit(1)

    # Get structure with frontmatter extraction enabled
    structure = analyzer.get_structure(extract_frontmatter=True)
    content = analyzer.content

    # Set schema context for F-series rules
    set_validation_context(schema)

    try:
        # Parse select/ignore options (default to F-series rules if not specified)
        select = args.select.split(',') if args.select else ['F']
        ignore = args.ignore.split(',') if args.ignore else None

        # Run rules (F003, F004, F005 will use the schema context)
        detections = RuleRegistry.check_file(
            path, structure, content, select=select, ignore=ignore
        )

        # Format and output results
        formatters = {
            'json': lambda: _format_detections_json(path, detections),
            'grep': lambda: _format_detections_grep(detections),
            'text': lambda: _format_detections_text(path, detections),
        }

        formatter = formatters.get(output_format, formatters['text'])
        formatter()

        # Exit with error code if validation failed
        if detections:
            sys.exit(1)

    finally:
        # Always clear context, even if an error occurred
        clear_validation_context()
