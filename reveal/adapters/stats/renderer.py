"""Renderer for statistics adapter results."""

import sys


class StatsRenderer:
    """Renderer for statistics adapter results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render codebase statistics.

        Args:
            result: Structure dict from StatsAdapter.get_structure()
            format: Output format ('text', 'json')
        """
        if format == 'json':
            from ...main import safe_json_dumps
            print(safe_json_dumps(result))
            return

        # Text format - single file stats
        if 'file' in result and 'summary' not in result:
            file_name = result.get('file', 'file')
            lines = result.get('lines', {})
            elements = result.get('elements', {})
            complexity = result.get('complexity', {})
            quality = result.get('quality', {})

            print(f"File Statistics: {file_name}\n")
            print(f"Lines:      {lines.get('total', 0)} ({lines.get('code', 0)} code, {lines.get('comments', 0)} comments)")
            print(f"Functions:  {elements.get('functions', 0)}")
            print(f"Classes:    {elements.get('classes', 0)}")
            print(f"Complexity: {complexity.get('average', 0):.2f} (avg), {complexity.get('max', 0)} (max)")
            print(f"Quality:    {quality.get('score', 0):.1f}/100")

            # Show issues if present
            issues = result.get('issues', {})
            long_funcs = issues.get('long_functions', [])
            deep_nesting = issues.get('deep_nesting', [])
            if long_funcs or deep_nesting:
                print("\nIssues:")
                if long_funcs:
                    print(f"  Long functions: {len(long_funcs)}")
                if deep_nesting:
                    print(f"  Deep nesting: {len(deep_nesting)}")
            return

        # Text format - directory stats
        if 'summary' in result:
            path = result.get('path', '.')
            s = result['summary']
            print(f"Codebase Statistics: {path}\n")
            print(f"Files:      {s['total_files']}")
            print(f"Lines:      {s['total_lines']:,} ({s['total_code_lines']:,} code)")
            print(f"Functions:  {s['total_functions']}")
            print(f"Classes:    {s['total_classes']}")
            print(f"Complexity: {s['avg_complexity']:.2f} (avg)")
            print(f"Quality:    {s['avg_quality_score']:.1f}/100")

            # Show hotspots if present
            if 'hotspots' in result and result['hotspots']:
                print(f"\nTop Hotspots ({len(result['hotspots'])}):")
                for i, h in enumerate(result['hotspots'], 1):
                    print(f"\n{i}. {h['file']}")
                    print(f"   Quality: {h['quality_score']:.1f}/100 | Score: {h['hotspot_score']:.1f}")
                    print(f"   Issues: {', '.join(h['issues'])}")

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render file-specific statistics.

        Args:
            result: Element dict from StatsAdapter.get_element()
            format: Output format ('text', 'json')
        """
        if format == 'json':
            from ...main import safe_json_dumps
            print(safe_json_dumps(result))
            return

        # Text format - file stats
        print(f"File: {result.get('file', 'unknown')}")
        print("\nLines:")
        print(f"  Total:    {result['lines']['total']}")
        print(f"  Code:     {result['lines']['code']}")
        print(f"  Comments: {result['lines']['comments']}")
        print(f"  Empty:    {result['lines']['empty']}")
        print("\nElements:")
        print(f"  Functions: {result['elements']['functions']}")
        print(f"  Classes:   {result['elements']['classes']}")
        print(f"  Imports:   {result['elements']['imports']}")
        print("\nComplexity:")
        print(f"  Average:   {result['complexity']['average']:.2f}")
        print(f"  Max:       {result['complexity']['max']}")
        print("\nQuality:")
        print(f"  Score:     {result['quality']['score']:.1f}/100")
        print(f"  Long funcs: {result['quality']['long_functions']}")
        print(f"  Deep nest:  {result['quality']['deep_nesting']}")

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error analyzing statistics: {error}", file=sys.stderr)
