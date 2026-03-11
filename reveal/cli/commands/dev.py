"""reveal dev — developer tooling subcommand."""

import argparse
from argparse import Namespace
from pathlib import Path


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add reveal dev subcommand arguments."""
    sub = parser.add_subparsers(dest='dev_command', metavar='COMMAND')
    sub.required = True

    # new-adapter
    p = sub.add_parser('new-adapter', help='Scaffold a new URI adapter')
    p.add_argument('name', help='Adapter name (e.g., github, payments)')
    p.add_argument('--uri', metavar='SCHEME', help='URI scheme (defaults to name://)')
    p.add_argument('--force', action='store_true', help='Overwrite existing files')

    # new-analyzer
    p = sub.add_parser('new-analyzer', help='Scaffold a new language analyzer')
    p.add_argument('name', help='Analyzer name (e.g., kotlin, dart)')
    p.add_argument('--ext', metavar='EXT', help='File extension (e.g., .kt)')
    p.add_argument('--force', action='store_true', help='Overwrite existing files')

    # new-rule
    p = sub.add_parser('new-rule', help='Scaffold a new quality rule')
    p.add_argument('code', help='Rule code (e.g., C001, X001)')
    p.add_argument('name', help='Rule name (e.g., "deep-nesting")')
    p.add_argument('--category', default='custom', help='Rule category (default: custom)')
    p.add_argument('--force', action='store_true', help='Overwrite existing files')

    # inspect-config
    sub.add_parser('inspect-config', help='Show the effective .reveal.yaml configuration')


def run_dev(args: Namespace) -> None:
    """Dispatch reveal dev subcommands."""
    cmd = args.dev_command

    if cmd == 'new-adapter':
        from ..handlers_scaffold import handle_scaffold_adapter
        uri = args.uri or f'{args.name}://'
        handle_scaffold_adapter(args.name, uri, getattr(args, 'force', False))

    elif cmd == 'new-analyzer':
        from ..handlers_scaffold import handle_scaffold_analyzer
        ext = args.ext or f'.{args.name}'
        handle_scaffold_analyzer(args.name, ext, getattr(args, 'force', False))

    elif cmd == 'new-rule':
        from ..handlers_scaffold import handle_scaffold_rule
        handle_scaffold_rule(args.code, args.name, args.category, getattr(args, 'force', False))

    elif cmd == 'inspect-config':
        _run_inspect_config()


def _run_inspect_config() -> None:
    """Show the effective .reveal.yaml for the current directory."""
    from ...config import RevealConfig

    start = Path.cwd()
    config = RevealConfig.get(start)

    config_files = getattr(config, '_loaded_files', None) or getattr(config, 'config_files', None)

    print("Effective .reveal.yaml configuration")
    print(f"  Search root: {start}")
    print()

    if config_files:
        print("Config files loaded (in priority order):")
        for f in config_files:
            print(f"  {f}")
        print()
    else:
        # Try to find the config file manually
        current = start
        found = None
        while True:
            candidate = current / '.reveal.yaml'
            if candidate.exists():
                found = candidate
                break
            parent = current.parent
            if parent == current:
                break
            current = parent

        if found:
            print(f"Config file: {found}")
        else:
            print("No .reveal.yaml found (using defaults)")
        print()

    # Show effective settings
    settings = {
        'layers': getattr(config, 'layers', None),
        'complexity_threshold': getattr(config, 'complexity_threshold', None),
        'max_line_length': getattr(config, 'max_line_length', None),
        'exclude': getattr(config, 'exclude', None),
        'ignore_rules': getattr(config, 'ignore_rules', None),
        'select_rules': getattr(config, 'select_rules', None),
    }

    has_settings = any(v is not None for v in settings.values())
    if has_settings:
        print("Effective settings:")
        for key, value in settings.items():
            if value is not None:
                print(f"  {key}: {value}")
    else:
        print("Using all default settings.")
