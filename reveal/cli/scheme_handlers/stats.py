"""Handler for stats:// URIs."""

import sys
from typing import Optional
from argparse import Namespace


def handle_stats(adapter_class: type, resource: str, element: Optional[str],
                 args: Namespace) -> None:
    """Handle stats:// URIs."""
    from ...main import safe_json_dumps

    if not resource:
        print("Error: stats:// requires a path (e.g., stats://./src)", file=sys.stderr)
        sys.exit(1)

    # Get hotspots flag if present
    hotspots = getattr(args, 'hotspots', False)

    adapter = adapter_class(resource)

    if element:
        # Get stats for specific file
        result = adapter.get_element(element)
        if result is None:
            print(f"Error: File '{element}' not found or cannot be analyzed", file=sys.stderr)
            sys.exit(1)
    else:
        # Get overall stats
        result = adapter.get_structure(hotspots=hotspots)

    # Handle output format
    if args.format == 'json':
        print(safe_json_dumps(result))
        return

    # Text format
    if 'summary' in result:
        # Directory stats
        s = result['summary']
        print(f"Codebase Statistics: {resource}\n")
        print(f"Files:      {s['total_files']}")
        print(f"Lines:      {s['total_lines']:,} ({s['total_code_lines']:,} code)")
        print(f"Functions:  {s['total_functions']}")
        print(f"Classes:    {s['total_classes']}")
        print(f"Complexity: {s['avg_complexity']:.2f} (avg)")
        print(f"Quality:    {s['avg_quality_score']:.1f}/100")

        if hotspots and 'hotspots' in result and result['hotspots']:
            print(f"\nTop Hotspots ({len(result['hotspots'])}):")
            for i, h in enumerate(result['hotspots'], 1):
                print(f"\n{i}. {h['file']}")
                print(f"   Quality: {h['quality_score']:.1f}/100 | Score: {h['hotspot_score']:.1f}")
                print(f"   Issues: {', '.join(h['issues'])}")
    else:
        # File stats
        print(f"File: {result.get('file', 'unknown')}")
        print(f"\nLines:")
        print(f"  Total:    {result['lines']['total']}")
        print(f"  Code:     {result['lines']['code']}")
        print(f"  Comments: {result['lines']['comments']}")
        print(f"  Empty:    {result['lines']['empty']}")
        print(f"\nElements:")
        print(f"  Functions: {result['elements']['functions']}")
        print(f"  Classes:   {result['elements']['classes']}")
        print(f"  Imports:   {result['elements']['imports']}")
        print(f"\nComplexity:")
        print(f"  Average:   {result['complexity']['average']:.2f}")
        print(f"  Max:       {result['complexity']['max']}")
        print(f"\nQuality:")
        print(f"  Score:     {result['quality']['score']:.1f}/100")
        print(f"  Long funcs: {result['quality']['long_functions']}")
        print(f"  Deep nest:  {result['quality']['deep_nesting']}")
