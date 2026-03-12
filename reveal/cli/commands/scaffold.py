"""reveal scaffold — scaffold new reveal components."""

import argparse
from argparse import Namespace


def create_scaffold_parser() -> argparse.ArgumentParser:
    """Create and return the argument parser for 'reveal scaffold'."""
    parser = argparse.ArgumentParser(
        prog='reveal scaffold',
        description='Scaffold new reveal components (adapters, analyzers, rules)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest='component', help='Component type to scaffold')
    subparsers.required = True

    adapter_parser = subparsers.add_parser('adapter', help='Scaffold a new adapter')
    adapter_parser.add_argument('name', help='Adapter name (e.g., github, docker)')
    adapter_parser.add_argument('uri', help='URI scheme (e.g., github://, docker://)')
    adapter_parser.add_argument('--force', action='store_true', help='Overwrite existing files')

    analyzer_parser = subparsers.add_parser('analyzer', help='Scaffold a new analyzer')
    analyzer_parser.add_argument('name', help='Analyzer name (e.g., kotlin, dart)')
    analyzer_parser.add_argument('extension', help='File extension (e.g., .kt, .dart)')
    analyzer_parser.add_argument('--force', action='store_true', help='Overwrite existing files')

    rule_parser = subparsers.add_parser('rule', help='Scaffold a new quality rule')
    rule_parser.add_argument('code', help='Rule code (e.g., C001, X001)')
    rule_parser.add_argument('name', help='Rule name (e.g., "custom-pattern-check")')
    rule_parser.add_argument('--category', default='custom', help='Rule category (default: custom)')
    rule_parser.add_argument('--force', action='store_true', help='Overwrite existing files')

    return parser


def run_scaffold(args: Namespace) -> None:
    """Dispatch scaffold subcommands."""
    from reveal.cli import handle_scaffold_adapter, handle_scaffold_analyzer, handle_scaffold_rule

    if args.component == 'adapter':
        handle_scaffold_adapter(args.name, args.uri, args.force)
    elif args.component == 'analyzer':
        handle_scaffold_analyzer(args.name, args.extension, args.force)
    elif args.component == 'rule':
        handle_scaffold_rule(args.code, args.name, args.category, args.force)
