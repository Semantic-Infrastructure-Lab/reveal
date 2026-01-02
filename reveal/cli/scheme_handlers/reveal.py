"""Handler for reveal:// URIs (self-inspection)."""

import sys
from typing import Optional
from argparse import Namespace


def _format_check_detections(uri: str, detections: list, output_format: str) -> None:
    """Format and print check detections in specified format.

    Args:
        uri: URI being checked
        detections: List of detection objects
        output_format: 'json', 'grep', or 'text'
    """
    from ...main import safe_json_dumps

    if output_format == 'json':
        result = {
            'file': uri,
            'detections': [d.to_dict() for d in detections],
            'total': len(detections)
        }
        print(safe_json_dumps(result))
        return

    if output_format == 'grep':
        for d in detections:
            print(f"{d.file_path}:{d.line}:{d.column}:{d.rule_code}:{d.message}")
        return

    # Text format (default)
    if not detections:
        print(f"{uri}: ✅ No issues found")
        return

    print(f"{uri}: Found {len(detections)} issues\n")
    for d in sorted(detections, key=lambda x: (x.line, x.column)):
        print(d)
        print()


def _handle_reveal_check(resource: str, args: Namespace) -> None:
    """Handle reveal:// URI with --check flag.

    Args:
        resource: Resource path from URI
        args: Command-line arguments
    """
    from ...rules import RuleRegistry

    uri = f"reveal://{resource}" if resource else "reveal://"
    select = args.select.split(',') if args.select else None
    ignore = args.ignore.split(',') if args.ignore else None

    # V-series rules don't need structure/content - they inspect reveal source directly
    detections = RuleRegistry.check_file(uri, None, "", select=select, ignore=ignore)

    _format_check_detections(uri, detections, args.format)


def handle_reveal(adapter_class: type, resource: str, element: Optional[str],
                  args: Namespace) -> None:
    """Handle reveal:// URIs (self-inspection).

    Args:
        adapter_class: Adapter class to use
        resource: Resource path from URI
        element: Optional element specification
        args: Command-line arguments
    """
    from ...rendering import render_reveal_structure

    # Handle --check: run V-series validation rules
    if getattr(args, 'check', False):
        _handle_reveal_check(resource, args)
        return

    # Handle element extraction: delegate to file analyzer
    if element and resource:
        adapter = adapter_class()
        result = adapter.get_element(resource, element, args)
        if result is None:
            print(f"Error: Could not extract '{element}' from reveal://{resource}", file=sys.stderr)
            sys.exit(1)
        return  # Rendering handled by get_element

    # Normal reveal: get and render structure
    adapter = adapter_class(resource if resource else None)
    result = adapter.get_structure()
    render_reveal_structure(result, args.format)
