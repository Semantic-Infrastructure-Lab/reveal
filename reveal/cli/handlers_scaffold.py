"""CLI handlers for scaffolding commands."""

import sys

from ..cli.scaffold import scaffold_adapter, scaffold_analyzer, scaffold_rule


def handle_scaffold_adapter(name: str, uri: str, force: bool = False) -> None:
    """Handle scaffold adapter command.

    Args:
        name: Adapter name
        uri: URI scheme
        force: Overwrite existing files
    """
    result = scaffold_adapter(name, uri, output_dir=None, force=force)

    if 'error' in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        if 'existing_files' in result:
            print(f"Existing files: {', '.join(result['existing_files'])}", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Created adapter scaffolding for '{name}'")
    print(f"\nFiles created:")
    print(f"  • {result['adapter_file']}")
    print(f"  • {result['test_file']}")
    print(f"  • {result['doc_file']}")
    print(f"\nNext steps:")
    for step in result['next_steps']:
        print(f"  {step}")


def handle_scaffold_analyzer(name: str, extension: str, force: bool = False) -> None:
    """Handle scaffold analyzer command.

    Args:
        name: Analyzer name
        extension: File extension
        force: Overwrite existing files
    """
    result = scaffold_analyzer(name, extension, output_dir=None, force=force)

    if 'error' in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        if 'existing_files' in result:
            print(f"Existing files: {', '.join(result['existing_files'])}", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Created analyzer scaffolding for '{name}'")
    print(f"\nFiles created:")
    print(f"  • {result['analyzer_file']}")
    print(f"  • {result['test_file']}")
    print(f"  • {result['doc_file']}")
    print(f"\nNext steps:")
    for step in result['next_steps']:
        print(f"  {step}")


def handle_scaffold_rule(code: str, name: str, category: str = 'custom', force: bool = False) -> None:
    """Handle scaffold rule command.

    Args:
        code: Rule code
        name: Rule name
        category: Rule category
        force: Overwrite existing files
    """
    result = scaffold_rule(code, name, category, output_dir=None, force=force)

    if 'error' in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        if 'existing_files' in result:
            print(f"Existing files: {', '.join(result['existing_files'])}", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Created rule scaffolding for '{code}'")
    print(f"\nFiles created:")
    print(f"  • {result['rule_file']}")
    print(f"  • {result['test_file']}")
    print(f"  • {result['doc_file']}")
    print(f"\nNext steps:")
    for step in result['next_steps']:
        print(f"  {step}")
