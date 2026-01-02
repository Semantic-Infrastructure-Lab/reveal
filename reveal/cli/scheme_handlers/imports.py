"""Handler for imports:// URIs."""

import sys
from typing import Optional
from argparse import Namespace


def _render_unused_imports(result: dict, verbose: bool) -> None:
    """Render unused imports results."""
    count = result['count']
    print(f"\n{'='*60}")
    print(f"Unused Imports: {count}")
    print(f"{'='*60}\n")

    if count == 0:
        print("  ✅ No unused imports found!\n")
    else:
        if verbose:
            # Detailed mode: show all
            for imp in result['unused']:
                print(f"  {imp['file']}:{imp['line']} - {imp['module']}")
        else:
            # Summary mode: show first 10, then count
            for imp in result['unused'][:10]:
                print(f"  {imp['file']}:{imp['line']} - {imp['module']}")
            if count > 10:
                print(f"\n  ... and {count - 10} more unused imports")
                print(f"  Run with --verbose to see all {count} unused imports\n")


def _render_circular_dependencies(result: dict, verbose: bool) -> None:
    """Render circular dependency results."""
    count = result['count']
    print(f"\n{'='*60}")
    print(f"Circular Dependencies: {count}")
    print(f"{'='*60}\n")

    if count == 0:
        print("  ✅ No circular dependencies found!\n")
    else:
        if verbose:
            # Detailed mode: show all cycles
            for i, cycle in enumerate(result['cycles'], 1):
                print(f"  {i}. {' -> '.join(cycle)}")
        else:
            # Summary mode: show first 5 cycles
            for i, cycle in enumerate(result['cycles'][:5], 1):
                print(f"  {i}. {' -> '.join(cycle)}")
            if count > 5:
                print(f"\n  ... and {count - 5} more circular dependencies")
                print(f"  Run with --verbose to see all {count} cycles\n")


def _render_layer_violations(result: dict, verbose: bool) -> None:
    """Render layer violation results."""
    count = result['count']
    print(f"\n{'='*60}")
    print(f"Layer Violations: {count}")
    print(f"{'='*60}\n")

    if count == 0:
        print(f"  ✅ {result.get('note', 'No violations found')}\n")
    else:
        violations = result.get('violations', [])
        if verbose:
            # Detailed mode: show all
            for v in violations:
                print(f"  {v['file']}:{v['line']} - {v['message']}")
        else:
            # Summary mode: show first 10
            for v in violations[:10]:
                print(f"  {v['file']}:{v['line']} - {v['message']}")
            if count > 10:
                print(f"\n  ... and {count - 10} more violations")
                print(f"  Run with --verbose to see all {count} violations\n")


def _render_import_summary(result: dict, resource: str) -> None:
    """Render import analysis summary."""
    metadata = result.get('metadata', {})
    total_files = metadata.get('total_files', 0)
    total_imports = metadata.get('total_imports', 0)
    has_cycles = metadata.get('has_cycles', False)

    print(f"\n{'='*60}")
    print(f"Import Analysis: {resource}")
    print(f"{'='*60}\n")
    print(f"  Total Files:   {total_files}")
    print(f"  Total Imports: {total_imports}")
    print(f"  Cycles Found:  {'❌ Yes' if has_cycles else '✅ No'}")
    print()
    print(f"Query options:")
    print(f"  reveal 'imports://{resource}?unused'    - Find unused imports")
    print(f"  reveal 'imports://{resource}?circular'  - Detect circular deps")
    print(f"  reveal 'imports://{resource}?violations' - Check layer violations")
    print()


def handle_imports(adapter_class: type, resource: str, element: Optional[str],
                   args: Namespace) -> None:
    """Handle imports:// URIs."""
    from ...main import safe_json_dumps

    if not resource:
        resource = '.'

    adapter = adapter_class()
    uri = f"imports://{resource}"

    if element:
        # Get imports for specific file
        result = adapter.get_element(element)
        if result is None:
            print(f"Error: File '{element}' not found", file=sys.stderr)
            sys.exit(1)
    else:
        # Get import analysis
        result = adapter.get_structure(uri=uri)

    # Handle output format
    if args.format == 'json':
        print(safe_json_dumps(result))
        return

    # Text format with progressive disclosure
    verbose = getattr(args, 'verbose', False)

    if 'type' in result:
        result_type = result['type']
        if result_type == 'unused_imports':
            _render_unused_imports(result, verbose)
        elif result_type == 'circular_dependencies':
            _render_circular_dependencies(result, verbose)
        elif result_type == 'layer_violations':
            _render_layer_violations(result, verbose)
        else:
            # Default: show import analysis summary
            _render_import_summary(result, resource)
    else:
        # Fallback to JSON if unknown structure
        print(safe_json_dumps(result))
