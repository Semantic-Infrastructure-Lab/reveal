"""Special mode handlers for reveal CLI.

These handlers implement --rules, --agent-help, --stdin, and other
special modes that exit early without processing files.
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Dict, List, Any

if TYPE_CHECKING:
    from argparse import Namespace


def handle_list_supported(list_supported_types_func):
    """Handle --list-supported flag.

    Args:
        list_supported_types_func: Function to list supported types
    """
    list_supported_types_func()
    sys.exit(0)


def handle_languages():
    """Handle --languages flag.

    Shows all supported languages with distinction between explicit
    analyzers (full featured) and tree-sitter fallback (basic).
    """
    from .languages import list_supported_languages
    print(list_supported_languages())
    sys.exit(0)


def handle_adapters():
    """Handle --adapters flag.

    Shows all URI adapters with their syntax and purpose.
    """
    from ..adapters.base import _ADAPTER_REGISTRY

    lines = ["URI Adapters\n", "=" * 70]
    lines.append(f"\n📡 Registered Adapters ({len(_ADAPTER_REGISTRY)})")
    lines.append("-" * 70)
    lines.append("Query resources beyond files using URI schemes\n")

    # Sort adapters by name
    for scheme in sorted(_ADAPTER_REGISTRY.keys()):
        adapter_class = _ADAPTER_REGISTRY[scheme]

        # Try to get help data from adapter class
        description = ''
        example = ''
        try:
            help_data = adapter_class.get_help()  # type: ignore[attr-defined]
            if help_data:
                description = help_data.get('description', '')
                syntax = help_data.get('syntax', f'{scheme}://<resource>')
                examples = help_data.get('examples', [])
                example = examples[0]['uri'] if examples else ''
        except (AttributeError, TypeError):
            pass

        if not description:
            description = 'No description available'

        lines.append(f"  {scheme}://")
        lines.append(f"    {description}")
        if example:
            lines.append(f"    Example: reveal {example}")
        lines.append("")

    lines.append("=" * 70)
    lines.append(f"\n💡 Usage:")
    lines.append(f"  reveal help://adapters          # Detailed adapter help")
    lines.append(f"  reveal help://<adapter>         # Help for specific adapter")

    print('\n'.join(lines))
    sys.exit(0)


def handle_explain_file(path: str, verbose: bool = False):
    """Handle --explain-file flag.

    Shows how reveal will analyze a file, including analyzer type,
    fallback status, and capabilities.
    """
    from .introspection import explain_file
    print(explain_file(path, verbose=verbose))
    sys.exit(0)


def handle_capabilities(path: str):
    """Handle --capabilities flag.

    Shows file capabilities as JSON for agent consumption.
    Pre-analysis introspection: what can be extracted, what rules apply.
    """
    import json
    from .introspection import get_capabilities
    result = get_capabilities(path)
    print(json.dumps(result, indent=2))
    sys.exit(0)


def handle_show_ast(path: str, max_depth: int = 10):
    """Handle --show-ast flag.

    Displays the tree-sitter AST for a file.
    """
    from .introspection import show_ast
    print(show_ast(path, max_depth=max_depth))
    sys.exit(0)


def handle_language_info(language: str):
    """Handle --language-info flag.

    Shows detailed information about a language's capabilities.
    """
    from .introspection import get_language_info_detailed
    print(get_language_info_detailed(language))
    sys.exit(0)


def handle_agent_help():
    """Handle --agent-help flag."""
    agent_help_path = Path(__file__).parent.parent / 'docs' / 'AGENT_HELP.md'
    try:
        with open(agent_help_path, 'r', encoding='utf-8') as f:
            print(f.read())
    except FileNotFoundError:
        print(f"Error: AGENT_HELP.md not found at {agent_help_path}", file=sys.stderr)
        print("This is a bug - please report it at https://github.com/Semantic-Infrastructure-Lab/reveal/issues", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def handle_agent_help_full():
    """Handle --agent-help-full flag."""
    agent_help_full_path = Path(__file__).parent.parent / 'docs' / 'AGENT_HELP_FULL.md'
    try:
        with open(agent_help_full_path, 'r', encoding='utf-8') as f:
            print(f.read())
    except FileNotFoundError:
        print(f"Error: AGENT_HELP_FULL.md not found at {agent_help_full_path}", file=sys.stderr)
        print("This is a bug - please report it at https://github.com/Semantic-Infrastructure-Lab/reveal/issues", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def handle_schema(version: Optional[str] = None):
    """Handle --schema flag to show Output Contract specification.

    Displays the v1.0 Output Contract schema that all adapters/analyzers
    should conform to for stable JSON output.

    Args:
        version: Contract version to display (defaults to '1.0')
    """
    if version is None or version == '1.0':
        print(_get_schema_v1())
    else:
        print(f"Error: Unknown contract version '{version}'", file=sys.stderr)
        print("Available versions: 1.0", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def _get_schema_v1() -> str:
    """Get Output Contract v1.0 specification."""
    return """Output Contract v1.0
======================

All adapter/analyzer outputs MUST include these 4 required fields:

Required Fields:
  contract_version: '1.0'          # Contract version (semver)
  type:             str            # Output type (snake_case)
  source:           str            # Data source identifier
  source_type:      str            # Source category

Valid source_type values:
  - 'file'        # Single file path
  - 'directory'   # Directory path
  - 'database'    # Database connection
  - 'runtime'     # Runtime/environment state
  - 'network'     # Remote resource

Type Field Rules:
  - Must use snake_case (lowercase with underscores)
  - Pattern: ^[a-z][a-z0-9_]*$
  - Examples: 'ast_query', 'mysql_server', 'environment'
  - ✗ Invalid: 'ast-query' (hyphens), 'AstQuery' (camelCase)

Recommended Optional Fields:
  metadata:     dict     # Generic counts, timestamps, metrics
  query:        dict     # Applied filters or search parameters
  next_steps:   list     # Progressive disclosure suggestions
  status:       dict     # Health assessment
  issues:       list     # Problems/warnings found

Line Number Fields:
  Use 'line_start' and 'line_end' (not 'line'):
    line_start: int      # First line (1-indexed)
    line_end:   int      # Last line (1-indexed, inclusive)

Example Compliant Output:
  {
    'contract_version': '1.0',
    'type': 'ast_query',
    'source': 'src/main.py',
    'source_type': 'file',
    'metadata': {
      'total_results': 42,
      'timestamp': '2026-01-17T14:30:00Z'
    },
    'results': [...]
  }

Validation:
  Run V023 validation rule to check compliance:
    reveal --check reveal/adapters/myadapter.py --select V023

Documentation:
  Full specification: docs/OUTPUT_CONTRACT.md
  Design rationale:   internal-docs/research/OUTPUT_CONTRACT_ANALYSIS.md

Status: Beta 🟡 (v1.0 in development)
"""


def handle_rules_list(version: str):
    """Handle --rules flag to list all pattern detection rules.

    Args:
        version: Reveal version string
    """
    from ..rules import RuleRegistry
    rules = RuleRegistry.list_rules()

    if not rules:
        print("No rules discovered")
        sys.exit(0)

    print(f"Reveal v{version} - Pattern Detection Rules\n")

    # Group by category
    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for rule in rules:
        cat = rule['category']
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(rule)

    # Print by category
    for category in sorted(by_category.keys()):
        cat_rules = by_category[category]
        print(f"{category.upper()} Rules ({len(cat_rules)}):")
        for rule in sorted(cat_rules, key=lambda r: r['code']):
            status = "✓" if rule['enabled'] else "✗"
            severity_icon = {"low": "ℹ️", "medium": "⚠️", "high": "❌", "critical": "🚨"}.get(rule['severity'], "")
            print(f"  {status} {rule['code']:8s} {severity_icon} {rule['message']}")
            # Show file patterns if not universal
            patterns = rule.get('file_patterns', ['*'])
            if patterns and patterns != ['*']:
                # Handle both list and string patterns
                if isinstance(patterns, str):
                    patterns = [patterns]
                print(f"             Files: {', '.join(patterns)}")
        print()

    print(f"Total: {len(rules)} rules")
    print("\nUsage: reveal <file> --check --select B,S --ignore E501")
    sys.exit(0)


def handle_explain_rule(rule_code: str):
    """Handle --explain flag to explain a specific rule.

    Args:
        rule_code: Rule code to explain (e.g., "B001")
    """
    from ..rules import RuleRegistry
    rule = RuleRegistry.get_rule(rule_code)

    if not rule:
        print(f"Error: Rule '{rule_code}' not found", file=sys.stderr)
        print("\nUse 'reveal --rules' to list all available rules", file=sys.stderr)
        sys.exit(1)

    print(f"Rule: {rule.code}")
    print(f"Message: {rule.message}")
    print(f"Category: {rule.category.value if rule.category else 'unknown'}")
    print(f"Severity: {rule.severity.value}")
    print(f"File Patterns: {', '.join(rule.file_patterns)}")
    if rule.uri_patterns:
        print(f"URI Patterns: {', '.join(rule.uri_patterns)}")
    print(f"Version: {rule.version}")
    print(f"Enabled: {'Yes' if rule.enabled else 'No'}")
    print("\nDescription:")
    print(f"  {rule.__doc__ or 'No description available.'}")
    sys.exit(0)


def handle_list_schemas():
    """Handle --list-schemas flag to list all built-in schemas."""
    from ..schemas.frontmatter import list_schemas, load_schema

    schemas = list_schemas()

    if not schemas:
        print("No built-in schemas found")
        sys.exit(0)

    print("Built-in Schemas for Front Matter Validation\n")

    # Print each schema with details
    for schema_name in sorted(schemas):
        schema = load_schema(schema_name)
        if schema:
            name = schema.get('name', schema_name)
            description = schema.get('description', 'No description')
            required = schema.get('required_fields', [])

            print(f"  {schema_name}")
            print(f"    Name: {name}")
            print(f"    Description: {description}")
            if required:
                print(f"    Required fields: {', '.join(required)}")
            else:
                print(f"    Required fields: (none)")
            print()

    print(f"Total: {len(schemas)} schemas")
    print("\nUsage: reveal <file.md> --validate-schema <schema-name>")
    print("       reveal <file.md> --validate-schema /path/to/custom-schema.yaml")
    sys.exit(0)


def _process_stdin_uri(target: str, args: 'Namespace', is_batch_mode: bool,
                       is_ssl_batch_check: bool, batch_results: list,
                       ssl_check_results: list) -> None:
    """Process a URI from stdin.

    Args:
        target: URI to process
        args: Parsed arguments
        is_batch_mode: Whether in generic batch mode
        is_ssl_batch_check: Whether in SSL batch check mode
        batch_results: List to collect batch results
        ssl_check_results: List to collect SSL check results
    """
    from .routing import handle_uri

    # Generic batch mode - collect results from any adapter
    if is_batch_mode:
        result = _collect_batch_result(target, args)
        batch_results.append(result)
        return

    # Legacy SSL-specific batch mode for backward compatibility
    if is_ssl_batch_check and target.startswith('ssl://'):
        ssl_result: Optional[Dict[str, Any]] = _collect_ssl_check_result(target, args)
        if ssl_result:
            ssl_check_results.append(ssl_result)
        return

    # Non-batch URIs go through normal path
    try:
        handle_uri(target, None, args)
    except SystemExit as e:
        # Only warn for actual failures (non-zero exit codes)
        if e.code != 0:
            print(f"Warning: {target} failed, skipping", file=sys.stderr)


def _process_stdin_file(target: str, args: 'Namespace', handle_file_func) -> None:
    """Process a file path from stdin.

    Args:
        target: File path to process
        args: Parsed arguments
        handle_file_func: Function to handle individual files
    """
    path = Path(target)

    # Skip if path doesn't exist (graceful degradation)
    if not path.exists():
        print(f"Warning: {target} not found, skipping", file=sys.stderr)
        return

    # Skip directories (only process files)
    if path.is_dir():
        print(f"Warning: {target} is a directory, skipping (use reveal {target}/ directly)", file=sys.stderr)
        return

    # Process the file
    if path.is_file():
        handle_file_func(str(path), None, args.meta, args.format, args)


def handle_stdin_mode(args: 'Namespace', handle_file_func):
    """Handle --stdin mode to process files/URIs from stdin.

    Args:
        args: Parsed arguments
        handle_file_func: Function to handle individual files

    Supports both file paths and URIs (scheme://resource).
    URIs are routed to the appropriate adapter handler.

    When --batch is used, results are aggregated across all adapters.
    When --check is used with SSL URIs, results are aggregated and
    batch flags (--summary, --only-failures, --expiring-within) are applied.
    """
    if args.element:
        print("Error: Cannot use element extraction with --stdin", file=sys.stderr)
        sys.exit(1)

    # Check if we're in batch mode (explicit --batch or SSL batch checks)
    is_batch_mode = getattr(args, 'batch', False)
    is_ssl_batch_check = getattr(args, 'check', False) and not is_batch_mode

    # Collect results for batch aggregation
    ssl_check_results = []
    batch_results = []

    # Read paths/URIs from stdin (one per line)
    for line in sys.stdin:
        target = line.strip()
        if not target:
            continue  # Skip empty lines

        # Check if this is a URI (scheme://resource)
        if '://' in target:
            _process_stdin_uri(target, args, is_batch_mode, is_ssl_batch_check,
                             batch_results, ssl_check_results)
        else:
            _process_stdin_file(target, args, handle_file_func)

    # Render aggregated batch results
    if batch_results:
        _render_batch_results(batch_results, args)
        # _render_batch_results handles exit
        return

    # Render aggregated SSL batch results if we collected any (legacy path)
    if ssl_check_results:
        _render_ssl_batch_results(ssl_check_results, args)

    sys.exit(0)


def _collect_ssl_check_result(uri: str, args: 'Namespace') -> Optional[Dict[str, Any]]:
    """Collect SSL check result without rendering.

    Args:
        uri: SSL URI (ssl://domain.com)
        args: CLI arguments

    Returns:
        Check result dict or None on error
    """
    from ..adapters.base import get_adapter_class

    try:
        adapter_class = get_adapter_class('ssl')
        if not adapter_class:
            return None

        adapter = adapter_class(uri)
        result = adapter.check()
        return result  # type: ignore[no-any-return]
    except Exception as e:
        # Return error result so it shows up in batch output
        host = uri.replace('ssl://', '')
        return {
            'host': host,
            'port': 443,
            'status': 'failure',
            'error': str(e),
            'summary': {'total': 1, 'passed': 0, 'warnings': 0, 'failures': 1},
            'exit_code': 2,
        }


def _render_ssl_batch_results(results: list, args: 'Namespace') -> None:
    """Render collected SSL check results as a batch.

    Args:
        results: List of individual check results
        args: CLI arguments with batch flags
    """
    from ..adapters.ssl.renderer import SSLRenderer

    # Build batch result structure
    total = len(results)
    passed = sum(1 for r in results if r.get('status') == 'pass')
    warnings = sum(1 for r in results if r.get('status') == 'warning')
    failures = sum(1 for r in results if r.get('status') == 'failure')

    batch_result = {
        'type': 'ssl_batch_check',
        'source': 'stdin',
        'domains_checked': total,
        'status': 'pass' if failures == 0 and warnings == 0 else (
            'warning' if failures == 0 else 'failure'
        ),
        'summary': {
            'total': total,
            'passed': passed,
            'warnings': warnings,
            'failures': failures,
        },
        'results': results,
        'exit_code': 0 if failures == 0 else 2,
    }

    # Get batch flags from args
    only_failures = getattr(args, 'only_failures', False)
    summary = getattr(args, 'summary', False)
    expiring_within = getattr(args, 'expiring_within', None)

    # Render using SSLRenderer which handles all batch flags
    SSLRenderer.render_check(
        batch_result, args.format,
        only_failures=only_failures,
        summary=summary,
        expiring_within=expiring_within
    )


def _collect_batch_result(uri: str, args: 'Namespace') -> dict:
    """Collect check result from any adapter without rendering.

    Args:
        uri: URI to check (ssl://domain.com, domain://example.com, etc.)
        args: CLI arguments

    Returns:
        Result dict with status and data, or error result
    """
    from ..adapters.base import get_adapter_class

    try:
        # Parse scheme from URI
        if '://' not in uri:
            return {
                'uri': uri,
                'status': 'error',
                'error': 'Invalid URI format (missing scheme://)',
            }

        scheme = uri.split('://')[0]
        adapter_class = get_adapter_class(scheme)

        if not adapter_class:
            return {
                'uri': uri,
                'status': 'error',
                'error': f'No adapter found for scheme: {scheme}',
            }

        # Initialize adapter
        adapter = adapter_class(uri)

        # If --check flag and adapter has check method, use it
        if getattr(args, 'check', False) and hasattr(adapter, 'check'):
            result = adapter.check(
                advanced=getattr(args, 'advanced', False),
                only_failures=getattr(args, 'only_failures', False),
            )
            return {
                'uri': uri,
                'scheme': scheme,
                'status': result.get('status', 'unknown'),
                'data': result,
            }

        # Otherwise get structure
        result = adapter.get_structure()
        return {
            'uri': uri,
            'scheme': scheme,
            'status': 'success',
            'data': result,
        }

    except Exception as e:
        return {
            'uri': uri,
            'scheme': scheme if '://' in uri else 'unknown',
            'status': 'error',
            'error': str(e),
        }


def _aggregate_batch_stats(results: list) -> dict:
    """Aggregate batch statistics.

    Args:
        results: List of individual results

    Returns:
        Dict with total, successful, warnings, failures counts
    """
    return {
        'total': len(results),
        'successful': sum(1 for r in results if r['status'] in ('success', 'pass')),
        'warnings': sum(1 for r in results if r['status'] == 'warning'),
        'failures': sum(1 for r in results if r['status'] in ('failure', 'error')),
    }


def _group_results_by_scheme(results: list) -> dict:
    """Group results by adapter scheme.

    Args:
        results: List of individual results

    Returns:
        Dict mapping scheme to list of results
    """
    by_scheme: Dict[str, List[Any]] = {}
    for result in results:
        scheme = result.get('scheme', 'unknown')
        if scheme not in by_scheme:
            by_scheme[scheme] = []
        by_scheme[scheme].append(result)
    return by_scheme


def _filter_batch_display_results(results: list, only_failures: bool) -> list:
    """Filter results to failures/warnings if requested.

    Args:
        results: All results
        only_failures: Whether to filter to failures only

    Returns:
        Filtered or original results
    """
    if only_failures:
        return [r for r in results if r['status'] in ('failure', 'error', 'warning')]
    return results


def _determine_batch_overall_status(failures: int, warnings: int) -> str:
    """Determine overall batch status.

    Args:
        failures: Number of failures
        warnings: Number of warnings

    Returns:
        Status string: 'pass', 'warning', or 'failure'
    """
    if failures == 0 and warnings == 0:
        return 'pass'
    return 'warning' if failures == 0 else 'failure'


def _get_status_indicator(status: str) -> str:
    """Get status indicator emoji.

    Args:
        status: Status string

    Returns:
        Emoji indicator
    """
    if status in ('success', 'pass'):
        return '✓'
    elif status == 'warning':
        return '⚠'
    else:
        return '✗'


def _render_batch_text_output(stats: dict, overall_status: str,
                               by_scheme: dict, display_results: list) -> None:
    """Render batch results in text format.

    Args:
        stats: Statistics dict
        overall_status: Overall status string
        by_scheme: Results grouped by scheme
        display_results: Filtered results to display
    """
    print(f"\n{'='*60}")
    print(f"BATCH CHECK RESULTS")
    print(f"{'='*60}")
    print(f"Total URIs: {stats['total']}")
    print(f"Successful: {stats['successful']} ✓")
    if stats['warnings'] > 0:
        print(f"Warnings: {stats['warnings']} ⚠")
    if stats['failures'] > 0:
        print(f"Failures: {stats['failures']} ✗")
    print(f"Overall Status: {overall_status.upper()}")

    if len(by_scheme) > 1:
        print(f"\nAdapters used: {', '.join(by_scheme.keys())}")

    print(f"{'='*60}\n")

    # Show individual results if not summary-only
    if display_results:
        for result in display_results:
            uri = result['uri']
            status = result['status']
            indicator = _get_status_indicator(status)

            print(f"{indicator} {uri}: {status.upper()}")

            # Show error details
            if 'error' in result:
                print(f"  Error: {result['error']}")


def _calculate_batch_exit_code(failures: int, warnings: int) -> int:
    """Calculate appropriate exit code.

    Args:
        failures: Number of failures
        warnings: Number of warnings

    Returns:
        Exit code (0, 1, or 2)
    """
    if failures == 0:
        return 0
    return 1 if warnings > 0 else 2


def _render_batch_results(results: list, args: 'Namespace') -> None:
    """Render collected batch results with aggregation.

    Args:
        results: List of individual results from different adapters
        args: CLI arguments with batch flags
    """
    import json

    # Aggregate statistics
    stats = _aggregate_batch_stats(results)

    # Group by scheme
    by_scheme = _group_results_by_scheme(results)

    # Filter results if requested
    display_results = _filter_batch_display_results(
        results, getattr(args, 'only_failures', False)
    )

    # Determine overall status
    overall_status = _determine_batch_overall_status(
        stats['failures'], stats['warnings']
    )

    # Build batch output
    batch_result = {
        'type': 'batch_check',
        'total': stats['total'],
        'status': overall_status,
        'summary': {
            'successful': stats['successful'],
            'warnings': stats['warnings'],
            'failures': stats['failures'],
        },
        'adapters': list(by_scheme.keys()),
        'results': display_results,
    }

    # Render based on format
    if args.format == 'json':
        print(json.dumps(batch_result, indent=2))
    else:
        _render_batch_text_output(stats, overall_status, by_scheme, display_results)

    # Exit with appropriate code
    exit_code = _calculate_batch_exit_code(stats['failures'], stats['warnings'])
    sys.exit(exit_code)


def _extract_decorators_from_file(file_path: str):
    """Extract decorator information from a single Python file.

    Args:
        file_path: Path to Python file to analyze

    Returns:
        Tuple of (decorators_found dict, file_has_decorators bool) or None if file can't be analyzed
    """
    from ..registry import get_analyzer

    try:
        analyzer_class = get_analyzer(file_path)
        if not analyzer_class:
            return None

        analyzer = analyzer_class(file_path)
        structure = analyzer.get_structure()
        if not structure:
            return None

        decorators_found: Dict[str, int] = {}  # decorator_name -> count in this file

        # Check functions and classes for decorators
        for category in ['functions', 'classes']:
            for item in structure.get(category, []):
                decorators = item.get('decorators', [])
                for dec in decorators:
                    # Normalize decorator (just the name, not args)
                    dec_name = dec.split('(')[0]
                    decorators_found[dec_name] = decorators_found.get(dec_name, 0) + 1

        return (decorators_found, len(decorators_found) > 0)

    except Exception:
        return None  # Skip files we can't analyze


def _categorize_decorators(sorted_decorators, decorator_files):
    """Categorize decorators into stdlib and custom.

    Args:
        sorted_decorators: List of (decorator, count) tuples sorted by count
        decorator_files: Dict mapping decorator -> set of files

    Returns:
        Tuple of (stdlib_list, custom_list) where each is list of (name, count, file_count) tuples
    """
    stdlib_prefixes = ['@property', '@staticmethod', '@classmethod', '@abstractmethod',
                       '@dataclass', '@cached_property', '@lru_cache', '@functools.wraps',
                       '@contextmanager', '@asynccontextmanager', '@overload', '@final',
                       '@pytest.fixture', '@pytest.mark']

    stdlib_list = []
    custom_list = []

    for dec, count in sorted_decorators:
        file_count = len(decorator_files[dec])
        if any(dec.startswith(prefix) for prefix in stdlib_prefixes):
            stdlib_list.append((dec, count, file_count))
        else:
            custom_list.append((dec, count, file_count))

    return stdlib_list, custom_list


def _print_decorator_category(title, decorators_list):
    """Print a category of decorators.

    Args:
        title: Category title
        decorators_list: List of (decorator, count, file_count) tuples
    """
    if not decorators_list:
        return

    print(f"{title}:")
    for dec, count, file_count in decorators_list:
        files_text = f"{file_count} file{'s' if file_count != 1 else ''}"
        print(f"  {dec:<30s} {count:>4d} occurrences ({files_text})")
    print()


def _collect_file_decorators(file_path, decorator_counts, decorator_files):
    """Collect decorators from a single file and update statistics.

    Args:
        file_path: Path to file to analyze
        decorator_counts: Dict to update with decorator counts
        decorator_files: Dict to update with files per decorator

    Returns:
        Tuple of (file_processed, file_has_decorators)
    """
    result = _extract_decorators_from_file(str(file_path))
    if not result:
        return (False, False)

    decorators_found, has_decorators = result
    if has_decorators:
        for dec_name, count in decorators_found.items():
            decorator_counts[dec_name] += count
            decorator_files[dec_name].add(str(file_path))

    return (True, has_decorators)


def _scan_python_files(target_path):
    """Scan Python files and collect decorator statistics.

    Args:
        target_path: Path object (file or directory) to scan

    Returns:
        Tuple of (decorator_counts, decorator_files, total_files, total_decorated)
    """
    from collections import defaultdict

    decorator_counts: Dict[str, int] = defaultdict(int)
    decorator_files: Dict[str, set] = defaultdict(set)
    total_files = 0
    total_decorated = 0

    if target_path.is_file():
        processed, has_decorators = _collect_file_decorators(
            target_path, decorator_counts, decorator_files
        )
        if processed:
            total_files = 1
            total_decorated = 1 if has_decorators else 0
    elif target_path.is_dir():
        for file_path in target_path.rglob('*.py'):
            if '.venv' in str(file_path) or 'node_modules' in str(file_path):
                continue
            processed, has_decorators = _collect_file_decorators(
                file_path, decorator_counts, decorator_files
            )
            if processed:
                total_files += 1
                if has_decorators:
                    total_decorated += 1

    return decorator_counts, decorator_files, total_files, total_decorated


def handle_decorator_stats(path: str):
    """Handle --decorator-stats flag to show decorator usage statistics.

    Scans Python files and reports decorator usage across the codebase.

    Args:
        path: File or directory path to scan
    """
    target_path = Path(path) if path else Path('.')

    if not target_path.exists():
        print(f"Error: {path} not found", file=sys.stderr)
        sys.exit(1)

    # Scan files and collect statistics
    decorator_counts, decorator_files, total_files, total_decorated = _scan_python_files(target_path)

    if total_files == 0:
        print(f"No Python files found in {path or '.'}")
        sys.exit(0)

    # Print header
    print(f"Decorator Usage in {target_path} ({total_files} files)\n")

    if not decorator_counts:
        print("No decorators found")
        sys.exit(0)

    # Categorize and print decorators
    sorted_decorators = sorted(decorator_counts.items(), key=lambda x: -x[1])
    stdlib_list, custom_list = _categorize_decorators(sorted_decorators, decorator_files)

    _print_decorator_category("Standard Library Decorators", stdlib_list)
    _print_decorator_category("Custom/Third-Party Decorators", custom_list)

    # Summary
    print("Summary:")
    print(f"  Total decorators: {sum(decorator_counts.values())}")
    print(f"  Unique decorators: {len(decorator_counts)}")
    print(f"  Files with decorators: {total_decorated}/{total_files} ({100*total_decorated//total_files}%)")

    sys.exit(0)


# Backward compatibility aliases (private names used in main.py)
_handle_list_supported = handle_list_supported
_handle_agent_help = handle_agent_help
_handle_agent_help_full = handle_agent_help_full
_handle_rules_list = handle_rules_list
_handle_explain_rule = handle_explain_rule
_handle_stdin_mode = handle_stdin_mode
_handle_decorator_stats = handle_decorator_stats
