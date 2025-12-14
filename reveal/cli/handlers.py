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
    print(f"\nDescription:")
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


# Backward compatibility aliases (private names used in main.py)
_handle_list_supported = handle_list_supported
_handle_agent_help = handle_agent_help
_handle_agent_help_full = handle_agent_help_full
_handle_rules_list = handle_rules_list
_handle_explain_rule = handle_explain_rule
_handle_stdin_mode = handle_stdin_mode
