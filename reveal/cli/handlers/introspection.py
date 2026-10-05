"""Introspection handlers for reveal CLI.

Implements --rules, --agent-help, --schema, --adapters, --languages,
--explain-file, --capabilities, --show-ast, --discover, --list-schemas,
and related informational flags.
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Dict, List, Any

from ...utils.formatting import shell_command

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


def _print_json(payload: Any) -> None:
    import json
    print(json.dumps(payload, indent=2))


def handle_languages(fmt: str = 'text'):
    """Handle --languages flag.

    Shows all supported languages with distinction between explicit
    analyzers (full featured) and tree-sitter fallback (basic). ``--format json``
    prints the catalog help://languages renders (it printed the text view, BACK-1606).
    """
    from ..languages import build_languages_payload, list_supported_languages
    if fmt == 'json':
        _print_json(build_languages_payload())
    else:
        print(list_supported_languages())
    sys.exit(0)


def handle_adapters(show_all: bool = False, fmt: str = 'text'):
    """Handle --adapters flag.

    Shows all URI adapters with their syntax and purpose.

    Args:
        show_all: When True (--all), also include adapters that only inspect
            reveal's own source tree (adapter_class.internal is True), never a
            user's own resources. Excluded by default.
        fmt: ``json`` prints the --discover registry for the same adapter set (it
            printed the text view, BACK-1606).
    """
    from ...adapters.base import _ADAPTER_REGISTRY, list_public_schemes

    if fmt == 'json':
        _print_json(build_discover_payload(show_all))
        sys.exit(0)

    schemes = list_public_schemes(include_internal=show_all)

    lines = ["URI Adapters\n", "=" * 70]
    lines.append(f"\n📡 Registered Adapters ({len(schemes)})")
    lines.append("-" * 70)
    lines.append("Query resources beyond files using URI schemes\n")
    if not show_all and len(schemes) < len(list_public_schemes(include_internal=True)):
        lines.append("(reveal's internal self-inspection adapters are hidden — pass --all to include them)\n")

    # Sort adapters by name
    for scheme in sorted(schemes):
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
            lines.append(f"    Example: {shell_command(example)}")
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
    from ..introspection import get_language_info_detailed, resolve_language
    _, _, error = resolve_language(language)
    if error:
        # Unknown or ambiguous: exit 1 like a missing path, not 0 (BACK-1426)
        print(error, file=sys.stderr)
        sys.exit(1)
    print(get_language_info_detailed(language))
    sys.exit(0)


def handle_agent_help():
    """Handle --agent-help flag.

    Delegates to the same progressive-disclosure path as `help://agent`
    (HelpAdapter._load_static_help) instead of dumping the raw file, so the
    two doors to the agent guide behave identically.
    """
    from ...adapters.help import HelpAdapter
    from ...rendering.adapters.help import _render_help_static_guide

    result = HelpAdapter().get_element('agent')
    if not result or 'error' in result:
        agent_help_path = Path(__file__).parent.parent.parent / 'docs' / 'AGENT_HELP.md'
        print(f"Error: AGENT_HELP.md not found at {agent_help_path}", file=sys.stderr)
        print("This is a bug - please report it at https://github.com/Semantic-Infrastructure-Lab/reveal/issues", file=sys.stderr)
        sys.exit(1)
    _render_help_static_guide(result)
    sys.exit(0)


def handle_schema(version: Optional[str] = None):
    """Handle --schema flag to show the Output Contract specification.

    Prints the current contract (CONTRACT_VERSION, which results carry). It
    printed v1.0 while every result said 1.1 (BACK-1610).

    Args:
        version: Contract version to display (defaults to the current one)
    """
    from ...reveal_types import CONTRACT_VERSION
    if version is None or version == CONTRACT_VERSION:
        print(_get_schema())
    else:
        print(f"Error: Unknown contract version '{version}'", file=sys.stderr)
        print(f"Available versions: {CONTRACT_VERSION}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def _get_schema() -> str:
    """The current Output Contract specification (summary of OUTPUT_CONTRACT.md)."""
    from ...reveal_types import CONTRACT_VERSION
    v = CONTRACT_VERSION
    return f"""Output Contract v{v}
======================

Every adapter/analyzer result includes these 4 required fields:

Required Fields:
  contract_version: '{v}'          # Contract version (semver)
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

Trust metadata (added in v1.1, optional):
  meta:
    parse_mode:   str        # tree_sitter_full | tree_sitter_partial | fallback | regex | heuristic
    confidence:   float      # 0.0-1.0
    warnings:     list       # Non-fatal issues; a cut list is a {{'type': 'truncated', ...}} entry
    errors:       list       # Fatal issues (with fallback info)

Outcomes (exit code from the router):
  failed          a non-empty top-level 'error' string        exit 1
  not applicable  'applicable': false plus a 'reason'         exit 0
  truncated       a meta.warnings entry of type 'truncated'   exit 0
  ok              none of these (an empty answer is still ok) exit 0

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
  {{
    'contract_version': '{v}',
    'type': 'ast_query',
    'source': 'src/main.py',
    'source_type': 'file',
    'meta': {{'parse_mode': 'tree_sitter_full', 'warnings': []}},
    'results': [...]
  }}

Validation:
  Run V023 validation rule to check compliance:
    reveal reveal/adapters/myadapter.py --check --select V023

Documentation:
  Full specification: reveal help://output  (reveal/docs/development/OUTPUT_CONTRACT.md)
"""


def handle_rules_list(version: str, show_all: bool = False, fmt: str = 'text'):
    """Handle --rules flag to list all pattern detection rules.

    Args:
        version: Reveal version string
        show_all: When True (--all), also include reveal's internal self-check
            rules (rule_class.internal is True) that can never fire against an
            external user's codebase. Excluded by default.
        fmt: ``json`` prints the rule list as data (it printed the text view, BACK-1606).
    """
    from ...rules import RuleRegistry
    rules = RuleRegistry.list_rules(include_internal=show_all)

    if fmt == 'json':
        _print_json({'reveal_version': version, 'rule_count': len(rules),
                     'enabled_count': sum(1 for r in rules if r['enabled']),
                     'rules': sorted(rules, key=lambda r: r['code'])})
        sys.exit(0)

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
    enabled_count = sum(1 for r in rules if r['enabled'])
    disabled_count = len(rules) - enabled_count
    for category in sorted(by_category.keys()):
        cat_rules = by_category[category]
        print(f"{category.upper()} Rules ({len(cat_rules)}):")
        for rule in sorted(cat_rules, key=lambda r: r['code']):
            status = "✓" if rule['enabled'] else "○"
            severity_icon = {"low": "ℹ️", "medium": "⚠️", "high": "❌", "critical": "🚨"}.get(rule['severity'], "")
            opt_in_tag = " [opt-in]" if not rule['enabled'] else ""
            print(f"  {status} {rule['code']:8s} {severity_icon} {rule['message']}{opt_in_tag}")
            # Show file patterns if not universal
            patterns = rule.get('file_patterns', ['*'])
            if patterns and patterns != ['*']:
                print(f"             Files: {', '.join(_normalize_patterns(patterns))}")
            # Show correctness-verified languages/formats (BACK-466 part 1) so a
            # user sees where a rule is trustworthy vs best-effort at a glance.
            verified = rule.get('verified_languages') or []
            if verified:
                print(f"             Verified: {', '.join(verified)}")
        print()

    # Spelled out (total vs enabled) rather than the old "Total: N rules (M
    # opt-in)" where N was actually the *enabled* count and N+M the real
    # total — that phrasing double-reads as "N is the total" and undercounts
    # by the opt-in rules, same fix already applied to help://rules's renderer.
    print(f"Total: {len(rules)} rules ({enabled_count} enabled, {disabled_count} opt-in — "
          f"enable via --select <code>)")
    print("Verified = correctness-checked on these languages/formats (BACK-432 matrix); "
          "rules still run beyond them as best-effort.")
    if not show_all:
        print("(reveal's internal self-check rules are hidden — 'reveal --rules --all' includes them)")
    print("\nUsage: reveal <file> --check --select B,S --ignore E501")
    sys.exit(0)


def handle_profiles_list():
    """Handle --profiles flag to list available rule profiles."""
    from ...rules.profiles import list_profiles
    profiles = list_profiles()

    print("Available rule profiles\n")
    for p in profiles:
        builtin_tag = "" if p['builtin'] else " [project]"
        print(f"  {p['name']}{builtin_tag}")
        print(f"    {p['description']}")
        if p['select']:
            print(f"    select: {', '.join(p['select'])}")
        if p['ignore']:
            print(f"    ignore: {', '.join(p['ignore'])}")
        print()

    print("Usage: reveal check <path> --profile maintenance")
    print("       reveal check <path> --profile security --ignore N")
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
    category = rule.category
    category_value = category if isinstance(category, str) else (category.value if category else 'unknown')
    print(f"Category: {category_value}")
    print(f"Severity: {rule.severity.value}")
    print(f"File Patterns: {', '.join(rule.file_patterns)}")
    if rule.uri_patterns:
        print(f"URI Patterns: {', '.join(rule.uri_patterns)}")
    from ...rules.coverage import derive_verified_languages
    # get_rule returns the rule *class* (not an instance), so pass it straight
    # through — derive_* reads class attributes off whatever it's given.
    verified = derive_verified_languages(rule)
    if verified:
        print(f"Verified on: {', '.join(verified)} (BACK-432 correctness matrix)")
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


def build_discover_payload(show_all: bool = False) -> dict:
    """Build the full adapter registry as a single JSON-serializable dict.

    Each adapter entry includes its schema (output_types, query_params,
    example_queries, notes) for programmatic discovery by agents and scripts.
    Shared by --discover (CLI) and help://schemas/all (BACK-840) so both
    surfaces stay byte-identical rather than drifting into two builders.

    Args:
        show_all: When True (--all), also include adapters that only inspect
            reveal's own source tree (adapter_class.internal is True). Excluded
            by default so external users/agents see only adapters that apply
            to their own resources.
    """
    from ...adapters.base import _ADAPTER_REGISTRY, list_public_schemes

    schemes = list_public_schemes(include_internal=show_all)

    adapters = {}
    for scheme in sorted(schemes):
        adapter_class = _ADAPTER_REGISTRY[scheme]
        entry: dict = {'scheme': scheme}
        try:
            schema = adapter_class.get_schema()  # type: ignore[attr-defined]
        except (AttributeError, TypeError):
            schema = None

        if isinstance(schema, dict):
            entry['description'] = schema.get('description', '')
            entry['uri_syntax'] = schema.get('uri_syntax', f'{scheme}://<target>')
            entry['output_types'] = [
                t.get('type') for t in schema.get('output_types', [])
                if isinstance(t, dict) and 'type' in t
            ]
            entry['query_params'] = list(schema.get('query_params', {}).keys())
            entry['cli_flags'] = schema.get('cli_flags', [])
            entry['cli_only_flags'] = schema.get('cli_only_flags', {})
            entry['supports_batch'] = schema.get('supports_batch', False)
            entry['supports_advanced'] = schema.get('supports_advanced', False)
            entry['example_queries'] = [
                q.get('uri') for q in schema.get('example_queries', [])
                if isinstance(q, dict) and 'uri' in q
            ]
            notes = schema.get('notes', [])
            entry['notes'] = notes if isinstance(notes, list) else [notes]
        else:
            # Schema-less adapter (get_schema() returns None): no machine-readable query
            # schema by design, but it's still a real, advertised adapter — so
            # describe it honestly from get_help() rather than dumping a
            # "Schema not available" entry that reads as broken to a
            # discovering agent (BACK-473). Falls through to empty defaults only
            # if get_help() is also unavailable.
            help_data = {}
            try:
                help_data = adapter_class.get_help() or {}  # type: ignore[attr-defined]
            except Exception as exc:
                help_data = {'description': f'Help unavailable: {type(exc).__name__}: {exc}'}
            entry['description'] = help_data.get('description', '') or 'Schema not available'
            entry['uri_syntax'] = help_data.get('syntax', f'{scheme}://<target>')
            entry['output_types'] = []
            entry['query_params'] = []
            entry['cli_flags'] = []
            entry['cli_only_flags'] = {}
            entry['supports_batch'] = False
            entry['supports_advanced'] = False
            entry['example_queries'] = [
                ex.get('uri') for ex in help_data.get('examples', [])
                if isinstance(ex, dict) and 'uri' in ex
            ]
            notes = help_data.get('notes', [])
            entry['notes'] = notes if isinstance(notes, list) else [notes]

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

    return result


def handle_discover(show_all: bool = False):
    """Handle --discover flag.

    Dumps the full adapter registry as a single JSON document (see
    build_discover_payload for what it contains).
    """
    _print_json(build_discover_payload(show_all))
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
