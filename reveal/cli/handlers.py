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


def handle_agent_help():
    """Handle --agent-help flag."""
    agent_help_path = Path(__file__).parent.parent / 'AGENT_HELP.md'
    try:
        with open(agent_help_path, 'r', encoding='utf-8') as f:
            print(f.read())
    except FileNotFoundError:
        print(f"Error: AGENT_HELP.md not found at {agent_help_path}", file=sys.stderr)
        print("This is a bug - please report it at https://github.com/scottsen/reveal/issues", file=sys.stderr)
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
        print("This is a bug - please report it at https://github.com/scottsen/reveal/issues", file=sys.stderr)
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


def handle_decorator_stats(path: str):
    """Handle --decorator-stats flag to show decorator usage statistics.

    Scans Python files and reports decorator usage across the codebase.

    Args:
        path: File or directory path to scan
    """
    from collections import defaultdict
    from ..base import get_analyzer

    target_path = Path(path) if path else Path('.')

    # Collect decorator statistics
    decorator_counts = defaultdict(int)  # decorator -> count
    decorator_files = defaultdict(set)   # decorator -> set of files
    total_files = 0
    total_decorated = 0

    def process_file(file_path: str):
        """Process a single file for decorator statistics."""
        nonlocal total_files, total_decorated

        try:
            analyzer_class = get_analyzer(file_path)
            if not analyzer_class:
                return

            analyzer = analyzer_class(file_path)
            structure = analyzer.get_structure()
            if not structure:
                return

            total_files += 1
            file_has_decorators = False

            # Check functions and classes for decorators
            for category in ['functions', 'classes']:
                for item in structure.get(category, []):
                    decorators = item.get('decorators', [])
                    for dec in decorators:
                        # Normalize decorator (just the name, not args)
                        dec_name = dec.split('(')[0]
                        decorator_counts[dec_name] += 1
                        decorator_files[dec_name].add(file_path)
                        file_has_decorators = True

            if file_has_decorators:
                total_decorated += 1

        except Exception:
            pass  # Skip files we can't analyze

    # Scan files
    if target_path.is_file():
        process_file(str(target_path))
    elif target_path.is_dir():
        for file_path in target_path.rglob('*.py'):
            if '.venv' in str(file_path) or 'node_modules' in str(file_path):
                continue  # Skip common non-source directories
            process_file(str(file_path))
    else:
        print(f"Error: {path} not found", file=sys.stderr)
        sys.exit(1)

    if total_files == 0:
        print(f"No Python files found in {path or '.'}")
        sys.exit(0)

    # Print statistics
    print(f"Decorator Usage in {target_path} ({total_files} files)\n")

    if not decorator_counts:
        print("No decorators found")
        sys.exit(0)

    # Sort by count (descending)
    sorted_decorators = sorted(decorator_counts.items(), key=lambda x: -x[1])

    # Categorize decorators
    stdlib_decorators = ['@property', '@staticmethod', '@classmethod', '@abstractmethod',
                         '@dataclass', '@cached_property', '@lru_cache', '@functools.wraps',
                         '@contextmanager', '@asynccontextmanager', '@overload', '@final',
                         '@pytest.fixture', '@pytest.mark']

    custom_decorators = []
    stdlib_list = []

    for dec, count in sorted_decorators:
        file_count = len(decorator_files[dec])
        if any(dec.startswith(std) for std in stdlib_decorators):
            stdlib_list.append((dec, count, file_count))
        else:
            custom_decorators.append((dec, count, file_count))

    # Print stdlib decorators
    if stdlib_list:
        print("Standard Library Decorators:")
        for dec, count, file_count in stdlib_list:
            files_text = f"{file_count} file{'s' if file_count != 1 else ''}"
            print(f"  {dec:<30s} {count:>4d} occurrences ({files_text})")
        print()

    # Print custom decorators
    if custom_decorators:
        print("Custom/Third-Party Decorators:")
        for dec, count, file_count in custom_decorators:
            files_text = f"{file_count} file{'s' if file_count != 1 else ''}"
            print(f"  {dec:<30s} {count:>4d} occurrences ({files_text})")
        print()

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
