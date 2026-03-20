"""Introspection handlers for reveal CLI.

Implements --rules, --agent-help, --schema, --adapters, --languages,
--explain-file, --capabilities, --show-ast, --discover, --list-schemas,
and related informational flags.
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Dict, List, Any

if TYPE_CHECKING:
    from argparse import Namespace


def _normalize_patterns(patterns) -> list:
    """Normalize file patterns to a list."""
    return [patterns] if isinstance(patterns, str) else patterns


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
    from ..languages import list_supported_languages
    print(list_supported_languages())
    sys.exit(0)


def handle_adapters():
    """Handle --adapters flag.

    Shows all URI adapters with their syntax and purpose.
    """
    from ...adapters.base import _ADAPTER_REGISTRY

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
    lines.append("\n💡 Usage:")
    lines.append("  reveal help://adapters          # Detailed adapter help")
    lines.append("  reveal help://<adapter>         # Help for specific adapter")

    print('\n'.join(lines))
    sys.exit(0)


def handle_explain_file(path: str, verbose: bool = False):
    """Handle --explain-file flag.

    Shows how reveal will analyze a file, including analyzer type,
    fallback status, and capabilities.
    """
    if path is None:
        print("Usage: reveal <file> --explain-file", file=sys.stderr)
        sys.exit(1)
    from ..introspection import explain_file
    print(explain_file(path, verbose=verbose))
    sys.exit(0)


def handle_capabilities(path: str):
    """Handle --capabilities flag.

    Shows file capabilities as JSON for agent consumption.
    Pre-analysis introspection: what can be extracted, what rules apply.
    """
    import json
    from ..introspection import get_capabilities
    if path is None:
        print("Usage: reveal <file> --capabilities", file=sys.stderr)
        sys.exit(1)
    result = get_capabilities(path)
    print(json.dumps(result, indent=2))
    sys.exit(0)


def handle_show_ast(path: str, max_depth: int = 10):
    """Handle --show-ast flag.

    Displays the tree-sitter AST for a file.
    """
    if path is None:
        print("Usage: reveal <file> --show-ast", file=sys.stderr)
        sys.exit(1)
    from ..introspection import show_ast
    print(show_ast(path, max_depth=max_depth))
    sys.exit(0)


def handle_language_info(language: str):
    """Handle --language-info flag.

    Shows detailed information about a language's capabilities.
    """
    from ..introspection import get_language_info_detailed
    print(get_language_info_detailed(language))
    sys.exit(0)


def handle_agent_help():
    """Handle --agent-help flag."""
    agent_help_path = Path(__file__).parent.parent.parent / 'docs' / 'AGENT_HELP.md'
    try:
        with open(agent_help_path, 'r', encoding='utf-8') as f:
            print(f.read())
    except FileNotFoundError:
        print(f"Error: AGENT_HELP.md not found at {agent_help_path}", file=sys.stderr)
        print("This is a bug - please report it at https://github.com/Semantic-Infrastructure-Lab/reveal/issues", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def handle_agent_help_full():
    """Handle --agent-help-full flag.

    AGENT_HELP.md and AGENT_HELP_FULL.md were consolidated into a single file
    at commit 9292da3. This flag is now an alias for --agent-help.
    """
    handle_agent_help()


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
    from ...rules import RuleRegistry
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
                print(f"             Files: {', '.join(_normalize_patterns(patterns))}")
        print()

    print(f"Total: {len(rules)} rules")
    print("\nUsage: reveal <file> --check --select B,S --ignore E501")
    sys.exit(0)


def handle_explain_rule(rule_code: str):
    """Handle --explain flag to explain a specific rule.

    Args:
        rule_code: Rule code to explain (e.g., "B001")
    """
    from ...rules import RuleRegistry
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

    # Show thresholds and config guidance
    thresholds = getattr(rule, 'thresholds', {})
    if thresholds:
        print("\nThresholds:")
        for key, default in thresholds.items():
            print(f"  {key}: {default} (default)")
        print("\nConfigure in .reveal.yaml:")
        print("  rules:")
        print(f"    {rule.code}:")
        for key, default in thresholds.items():
            print(f"      {key}: {default}  # change to suit your project")

    print("\nDescription:")
    print(f"  {rule.__doc__ or 'No description available.'}")

    # Show compliant example if provided
    compliant_example = getattr(rule, 'compliant_example', '')
    if compliant_example:
        print("\nCompliant Example:")
        for line in compliant_example.strip().splitlines():
            print(f"  {line}")

    sys.exit(0)


def handle_discover():
    """Handle --discover flag.

    Dumps the full adapter registry as a single JSON document.
    Each adapter entry includes its schema (output_types, query_params,
    example_queries, notes) for programmatic discovery by agents and scripts.
    """
    import json
    from ...adapters.base import _ADAPTER_REGISTRY

    adapters = {}
    for scheme in sorted(_ADAPTER_REGISTRY.keys()):
        adapter_class = _ADAPTER_REGISTRY[scheme]
        entry: dict = {'scheme': scheme}
        try:
            schema = adapter_class.get_schema()  # type: ignore[attr-defined]
            entry['description'] = schema.get('description', '')
            entry['uri_syntax'] = schema.get('uri_syntax', f'{scheme}://<target>')
            entry['output_types'] = [
                t.get('type') for t in schema.get('output_types', [])
                if isinstance(t, dict) and 'type' in t
            ]
            entry['query_params'] = list(schema.get('query_params', {}).keys())
            entry['cli_flags'] = schema.get('cli_flags', [])
            entry['supports_batch'] = schema.get('supports_batch', False)
            entry['supports_advanced'] = schema.get('supports_advanced', False)
            entry['example_queries'] = [
                q.get('uri') for q in schema.get('example_queries', [])
                if isinstance(q, dict) and 'uri' in q
            ]
            notes = schema.get('notes', [])
            entry['notes'] = notes if isinstance(notes, list) else [notes]
        except (AttributeError, TypeError):
            entry['description'] = 'Schema not available'
            entry.setdefault('output_types', [])
            entry.setdefault('query_params', [])
            entry.setdefault('cli_flags', [])
            entry.setdefault('supports_batch', False)
            entry.setdefault('supports_advanced', False)
            entry.setdefault('example_queries', [])
            entry.setdefault('notes', [])

        adapters[scheme] = entry

    result = {
        'reveal_version': None,
        'adapter_count': len(adapters),
        'adapters': adapters,
    }
    try:
        from ... import __version__ as _ver
        result['reveal_version'] = _ver
    except ImportError:
        pass

    print(json.dumps(result, indent=2))
    sys.exit(0)


def handle_list_schemas():
    """Handle --list-schemas flag to list all built-in schemas."""
    from ...schemas.frontmatter import list_schemas, load_schema

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
                print("    Required fields: (none)")
            print()

    print(f"Total: {len(schemas)} schemas")
    print("\nUsage: reveal <file.md> --validate-schema <schema-name>")
    print("       reveal <file.md> --validate-schema /path/to/custom-schema.yaml")
    sys.exit(0)
