"""URI and file routing for reveal CLI.

This module handles dispatching to the correct handler based on:
- URI scheme (env://, ast://, help://, python://, json://, reveal://)
- File type (determined by extension)
- Directory handling
"""

import sys
import os
from pathlib import Path
from typing import Optional, Callable, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace


# ============================================================================
# Scheme-specific handlers
# ============================================================================

def _handle_env(adapter_class: type, resource: str, element: Optional[str],
                args: 'Namespace') -> None:
    """Handle env:// URIs."""
    from ..rendering import render_env_structure, render_env_variable

    if getattr(args, 'check', False):
        print("Warning: --check is not supported for env:// URIs", file=sys.stderr)

    adapter = adapter_class()

    if element or resource:
        var_name = element if element else resource
        result = adapter.get_element(var_name, show_secrets=False)

        if result is None:
            print(f"Error: Environment variable '{var_name}' not found", file=sys.stderr)
            sys.exit(1)

        render_env_variable(result, args.format)
    else:
        result = adapter.get_structure(show_secrets=False)
        render_env_structure(result, args.format)


def _handle_ast(adapter_class: type, resource: str, element: Optional[str],
                args: 'Namespace') -> None:
    """Handle ast:// URIs."""
    from ..rendering import render_ast_structure

    if getattr(args, 'check', False):
        print("Warning: --check is not supported for ast:// URIs", file=sys.stderr)

    # Parse path and query from resource
    if '?' in resource:
        path, query = resource.split('?', 1)
    else:
        path = resource
        query = None

    # Default to current directory if no path
    if not path:
        path = '.'

    adapter = adapter_class(path, query)
    result = adapter.get_structure()
    render_ast_structure(result, args.format)


def _handle_help(adapter_class: type, resource: str, element: Optional[str],
                 args: 'Namespace') -> None:
    """Handle help:// URIs."""
    from ..rendering import render_help

    if getattr(args, 'check', False):
        print("Warning: --check is not supported for help:// URIs", file=sys.stderr)

    adapter = adapter_class(resource)

    if element or resource:
        topic = element if element else resource
        result = adapter.get_element(topic)

        if result is None:
            print(f"Error: Help topic '{topic}' not found", file=sys.stderr)
            available = adapter.get_structure()
            print(f"\nAvailable topics: {', '.join(available['available_topics'])}", file=sys.stderr)
            sys.exit(1)

        render_help(result, args.format)
    else:
        result = adapter.get_structure()
        render_help(result, args.format, list_mode=True)


def _handle_python(adapter_class: type, resource: str, element: Optional[str],
                   args: 'Namespace') -> None:
    """Handle python:// URIs."""
    from ..rendering import render_python_structure, render_python_element

    if getattr(args, 'check', False):
        print("Warning: --check is not supported for python:// URIs", file=sys.stderr)

    adapter = adapter_class()

    if element or resource:
        element_name = element if element else resource
        result = adapter.get_element(element_name)

        if result is None:
            print(f"Error: Python element '{element_name}' not found", file=sys.stderr)
            print("\nAvailable elements: version, env, venv, packages, imports, debug/bytecode", file=sys.stderr)
            sys.exit(1)

        render_python_element(result, args.format)
    else:
        result = adapter.get_structure()
        render_python_structure(result, args.format)


def _handle_json(adapter_class: type, resource: str, element: Optional[str],
                 args: 'Namespace') -> None:
    """Handle json:// URIs."""
    from ..rendering import render_json_result

    if getattr(args, 'check', False):
        print("Warning: --check is not supported for json:// URIs", file=sys.stderr)

    # Parse path and query from resource
    if '?' in resource:
        path, query = resource.split('?', 1)
    else:
        path = resource
        query = None

    try:
        adapter = adapter_class(path, query)
        result = adapter.get_structure()
        render_json_result(result, args.format)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def _handle_reveal(adapter_class: type, resource: str, element: Optional[str],
                   args: 'Namespace') -> None:
    """Handle reveal:// URIs (self-inspection)."""
    from ..rendering import render_reveal_structure

    # Handle --check: run V-series validation rules
    if getattr(args, 'check', False):
        from ..rules import RuleRegistry
        from ..main import safe_json_dumps

        uri = f"reveal://{resource}" if resource else "reveal://"
        select = args.select.split(',') if args.select else None
        ignore = args.ignore.split(',') if args.ignore else None

        # V-series rules don't need structure/content - they inspect reveal source directly
        detections = RuleRegistry.check_file(uri, None, "", select=select, ignore=ignore)

        if args.format == 'json':
            result = {
                'file': uri,
                'detections': [d.to_dict() for d in detections],
                'total': len(detections)
            }
            print(safe_json_dumps(result))
            return

        if args.format == 'grep':
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
        return

    adapter = adapter_class(resource if resource else None)
    result = adapter.get_structure()
    render_reveal_structure(result, args.format)


def _handle_stats(adapter_class: type, resource: str, element: Optional[str],
                  args: 'Namespace') -> None:
    """Handle stats:// URIs."""
    from ..main import safe_json_dumps

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


def _handle_mysql(adapter_class: type, resource: str, element: Optional[str],
                  args: 'Namespace') -> None:
    """Handle mysql:// URIs."""
    import json

    # Build connection string from resource and element
    connection_string = f"mysql://{resource}"

    adapter = adapter_class(connection_string)

    # Handle --check flag: run health checks with thresholds
    if getattr(args, 'check', False):
        result = adapter.check()

        # Render check results
        if args.format == 'json':
            print(json.dumps(result, indent=2))
        else:
            _render_mysql_check_result(result)

        # Exit with appropriate code
        sys.exit(result['exit_code'])

    # If element is specified, get element details
    if adapter.element:
        result = adapter.get_element(adapter.element)
        if result is None:
            print(f"Error: Element '{adapter.element}' not found", file=sys.stderr)
            print(f"Available elements: connections, performance, innodb, replication, storage, errors, variables, health, databases", file=sys.stderr)
            sys.exit(1)
    else:
        # Get structure (health overview)
        result = adapter.get_structure()

    # Render output
    if args.format == 'json':
        print(json.dumps(result, indent=2))
    else:
        # Pretty-print the structure
        _render_mysql_result(result, args.format)


def _render_mysql_result(result: dict, format: str = 'text'):
    """Render MySQL adapter results in human-readable format."""
    import json

    if format == 'json':
        print(json.dumps(result, indent=2))
        return

    # Handle different result types
    result_type = result.get('type', 'mysql_server')

    if result_type == 'mysql_server':
        # Main health overview
        print(f"MySQL Server: {result['server']}")
        print(f"Version: {result['version']}")
        print(f"Uptime: {result['uptime']}")
        print()

        conn = result['connection_health']
        print(f"Connection Health: {conn['status']}")
        print(f"  Current: {conn['current']} / {conn['max']} max ({conn['percentage']})")
        print()

        perf = result['performance']
        print("Performance:")
        print(f"  QPS: {perf['qps']} queries/sec")
        print(f"  Slow Queries: {perf['slow_queries']}")
        print(f"  Threads Running: {perf['threads_running']}")
        print()

        innodb = result['innodb_health']
        print(f"InnoDB Health: {innodb['status']}")
        print(f"  Buffer Pool Hit Rate: {innodb['buffer_pool_hit_rate']}")
        print(f"  Row Lock Waits: {innodb['row_lock_waits']}")
        print(f"  Deadlocks: {innodb['deadlocks']}")
        print()

        repl = result['replication']
        print(f"Replication: {repl['role']}")
        if 'lag' in repl:
            print(f"  Lag: {repl['lag']}s")
        if 'slaves' in repl:
            print(f"  Slaves: {repl['slaves']}")
        print()

        storage = result['storage']
        print("Storage:")
        print(f"  Total: {storage['total_size_gb']:.2f} GB across {storage['database_count']} databases")
        print(f"  Largest: {storage['largest_db']}")
        print()

        print(f"Health Status: {result['health_status']}")
        print("Issues:")
        for issue in result['health_issues']:
            print(f"  • {issue}")
        print()

        print("Next Steps:")
        for step in result['next_steps']:
            print(f"  {step}")

    else:
        # Element-specific results - just JSON for now
        print(json.dumps(result, indent=2))


def _render_mysql_check_result(result: dict):
    """Render MySQL health check results in human-readable format."""
    status = result['status']
    summary = result['summary']

    # Header with overall status
    status_icon = '✅' if status == 'pass' else '⚠️' if status == 'warning' else '❌'
    print(f"\nMySQL Health Check: {status_icon} {status.upper()}")
    print(f"\nSummary: {summary['passed']}/{summary['total']} passed, {summary['warnings']} warnings, {summary['failures']} failures")
    print()

    # Group checks by status for better readability
    failures = [c for c in result['checks'] if c['status'] == 'failure']
    warnings = [c for c in result['checks'] if c['status'] == 'warning']
    passes = [c for c in result['checks'] if c['status'] == 'pass']

    # Show failures first
    if failures:
        print("❌ Failures:")
        for check in failures:
            print(f"  • {check['name']}: {check['value']} (threshold: {check['threshold']}, severity: {check['severity']})")
        print()

    # Then warnings
    if warnings:
        print("⚠️  Warnings:")
        for check in warnings:
            print(f"  • {check['name']}: {check['value']} (threshold: {check['threshold']}, severity: {check['severity']})")
        print()

    # Finally passes (if verbose or no issues)
    if passes and (not failures and not warnings):
        print("✅ All Checks Passed:")
        for check in passes:
            print(f"  • {check['name']}: {check['value']} (threshold: {check['threshold']})")
        print()

    # Exit code hint
    print(f"Exit code: {result['exit_code']}")


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
    from ..adapters import env, ast, help, python, json_adapter, reveal, mysql  # noqa: F401 - Trigger registration

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


def handle_recursive_check(directory: Path, args: 'Namespace') -> None:
    """Handle recursive quality checking of a directory.

    Args:
        directory: Directory to check recursively
        args: Parsed arguments
    """
    from ..base import get_analyzer
    import fnmatch

    # Collect all supported files
    files_to_check = []

    # Try to load .gitignore patterns if available
    gitignore_patterns = []
    gitignore_file = directory / '.gitignore'
    if gitignore_file.exists():
        try:
            with open(gitignore_file) as f:
                gitignore_patterns = [
                    line.strip() for line in f
                    if line.strip() and not line.startswith('#')
                ]
        except Exception:
            pass

    # Walk directory tree
    for root, dirs, files in os.walk(directory):
        root_path = Path(root)

        # Filter directories (remove .git, __pycache__, etc.)
        dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', '.venv', 'venv'}]

        # Check files
        for filename in files:
            file_path = root_path / filename

            # Skip if matches .gitignore patterns
            relative_path = file_path.relative_to(directory)
            skip = False
            for pattern in gitignore_patterns:
                if fnmatch.fnmatch(str(relative_path), pattern):
                    skip = True
                    break

            if skip:
                continue

            # Check if file has a supported analyzer
            if get_analyzer(str(file_path), allow_fallback=False):
                files_to_check.append(file_path)

    if not files_to_check:
        print(f"No supported files found in {directory}")
        return

    # Run checks on all files
    total_issues = 0
    files_with_issues = 0

    for file_path in sorted(files_to_check):
        try:
            # Get analyzer for this file
            analyzer_class = get_analyzer(str(file_path), allow_fallback=False)
            if not analyzer_class:
                continue

            analyzer = analyzer_class(str(file_path))

            # Run pattern detection
            from ..rules import RuleRegistry

            # Parse select/ignore options
            select = args.select.split(',') if args.select else None
            ignore = args.ignore.split(',') if args.ignore else None

            # Get structure and content
            structure = analyzer.get_structure()
            content = analyzer.content

            # Run rules
            detections = RuleRegistry.check_file(str(file_path), structure, content, select=select, ignore=ignore)

            if detections:
                # Print file header
                relative = file_path.relative_to(directory)
                print(f"\n{relative}: Found {len(detections)} issue{'s' if len(detections) != 1 else ''}\n")

                # Print each detection
                for detection in detections:
                    severity_icon = "⚠️ " if detection.severity.value == "MEDIUM" else "❌" if detection.severity.value == "HIGH" else "ℹ️ "
                    print(f"{relative}:{detection.line}:{detection.column} {severity_icon} {detection.rule_code} {detection.message}")
                    if detection.suggestion:
                        print(f"  💡 {detection.suggestion}")
                    if detection.context:
                        print(f"  📝 {detection.context}")

                total_issues += len(detections)
                files_with_issues += 1

        except Exception as e:
            # Skip files that can't be read or processed
            continue

    # Print summary
    print(f"\n{'='*60}")
    print(f"Checked {len(files_to_check)} files")
    if total_issues > 0:
        print(f"Found {total_issues} issue{'s' if total_issues != 1 else ''} in {files_with_issues} file{'s' if files_with_issues != 1 else ''}")
        sys.exit(1)  # Exit with error code if issues found
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
