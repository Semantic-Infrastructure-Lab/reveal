"""Special mode handlers for reveal CLI.

These handlers implement --rules, --agent-help, --stdin, and other
special modes that exit early without processing files.
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING

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


def handle_explain_file(path: str, verbose: bool = False):
    """Handle --explain-file flag.

    Shows how reveal will analyze a file, including analyzer type,
    fallback status, and capabilities.
    """
    from .introspection import explain_file
    print(explain_file(path, verbose=verbose))
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
    agent_help_path = Path(__file__).parent.parent / 'AGENT_HELP.md'
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
    agent_help_full_path = Path(__file__).parent.parent / 'AGENT_HELP_FULL.md'
    try:
        with open(agent_help_full_path, 'r', encoding='utf-8') as f:
            print(f.read())
    except FileNotFoundError:
        print(f"Error: AGENT_HELP_FULL.md not found at {agent_help_full_path}", file=sys.stderr)
        print("This is a bug - please report it at https://github.com/Semantic-Infrastructure-Lab/reveal/issues", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


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
    by_category = {}
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
            if rule['file_patterns'] != ['*']:
                print(f"             Files: {', '.join(rule['file_patterns'])}")
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


def handle_stdin_mode(args: 'Namespace', handle_file_func):
    """Handle --stdin mode to process files from stdin.

    Args:
        args: Parsed arguments
        handle_file_func: Function to handle individual files
    """
    if args.element:
        print("Error: Cannot use element extraction with --stdin", file=sys.stderr)
        sys.exit(1)

    # Read file paths from stdin (one per line)
    for line in sys.stdin:
        file_path = line.strip()
        if not file_path:
            continue  # Skip empty lines

        path = Path(file_path)

        # Skip if path doesn't exist (graceful degradation)
        if not path.exists():
            print(f"Warning: {file_path} not found, skipping", file=sys.stderr)
            continue

        # Skip directories (only process files)
        if path.is_dir():
            print(f"Warning: {file_path} is a directory, skipping (use reveal {file_path}/ directly)", file=sys.stderr)
            continue

        # Process the file
        if path.is_file():
            handle_file_func(str(path), None, args.meta, args.format, args)

    sys.exit(0)


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

        decorators_found = {}  # decorator_name -> count in this file

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

    decorator_counts = defaultdict(int)
    decorator_files = defaultdict(set)
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
