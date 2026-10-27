"""reveal dev — developer tooling subcommand."""

import argparse
from argparse import Namespace


def create_dev_parser() -> argparse.ArgumentParser:
    """Create and return the argument parser for 'reveal dev'."""
    parser = argparse.ArgumentParser(
        prog='reveal dev',
        description='Developer tooling: scaffold adapters, analyzers, and rules; inspect config.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal dev new-adapter payments --uri pay  # Scaffold new adapter\n"
            "  reveal dev new-analyzer kotlin --ext .kt   # Scaffold new analyzer\n"
            "  reveal dev new-rule C001 deep-nesting      # Scaffold new rule\n"
            "  reveal dev inspect-config                  # Show effective .reveal.yaml\n"
        )
    )
    add_arguments(parser)
    return parser


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
    """Show the config in effect for the current directory: the files read, the REVEAL_*
    variables applied and the merged settings (the same data as ``reveal reveal://config``)."""
    import yaml

    from ...adapters.reveal.config import get_config

    view = get_config()
    sources, meta = view['sources'], view['metadata']

    print("Effective reveal configuration")
    print(f"  Search root: {meta['working_directory']}")
    print(f"  Project root: {meta['project_root']}")
    print()

    # highest precedence first
    files = ([('custom', sources['custom_config'])] if sources['custom_config'] else [])
    files += [('project', p['path'] + (' (root)' if p['root'] else '')) for p in sources['project_configs']]
    files += [(layer, sources[f'{layer}_config']) for layer in ('user', 'system') if sources[f'{layer}_config']]
    if meta['no_config_mode']:
        print("Config files: skipped (REVEAL_NO_CONFIG=1)")
    elif files:
        print("Config files read (highest precedence first):")
        for layer, path in files:
            print(f"  {layer:<8} {path}")
    else:
        print("No config files found.")
    for failure in sources['load_failures']:
        print(f"  could not load {failure['path']}: {failure['reason']} (its settings are not applied)")
    print()

    if sources['env_vars']:
        print("Environment variables:")
        for name, value in sources['env_vars'].items():
            print(f"  {name}={value}")
        print()

    settings = {key: value for key, value in view['active_config'].items() if key != 'root' and value}
    if settings:
        print("Effective settings:")
        dumped = yaml.safe_dump(settings, default_flow_style=False, sort_keys=False)
        for line in dumped.rstrip('\n').split('\n'):
            print(f"  {line}")
    else:
        print("Using all default settings.")
