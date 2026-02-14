# CLI Integration Guide

**When you need this**: Adding a new top-level command to reveal (like `reveal scaffold`)

**When you DON'T need this**:
- Creating adapters (use `@register_adapter` decorator - auto-discovered)
- Creating analyzers (use `@register` decorator - auto-discovered)
- Creating rules (use `BaseRule` subclass - auto-discovered)

## Architecture Overview

Reveal uses **two different patterns** for CLI integration:

### 1. Auto-Registration Pattern (Most Components)

Components that use decorators or file conventions are automatically discovered:

```python
# Adapters - auto-registered via decorator
@register_adapter('myscheme')
class MyAdapter(ResourceAdapter):
    pass

# Analyzers - auto-registered via decorator
@register('.myext', name='mylang')
class MyAnalyzer(TreeSitterAnalyzer):
    pass

# Rules - auto-discovered via file system
class C999(BaseRule):
    code = "C999"
    # ...
```

**No CLI wiring needed!** Just create the file and it works.

### 2. Manual Wiring Pattern (Top-Level Commands)

Top-level commands (like `reveal scaffold`, `reveal help`, etc.) must be manually wired:

```bash
reveal scaffold adapter myname myscheme://  # New command type
reveal --languages                           # Flag-based command
```

These require explicit integration in `main.py`.

## Adding a New Top-Level Command

**Example**: Adding `reveal stats` command

### Step 1: Create Handler Functions

Create `reveal/cli/handlers_stats.py`:

```python
"""CLI handlers for stats commands."""

def handle_stats_overview() -> None:
    """Show statistics overview."""
    print("Statistics Overview")
    # Implementation...

def handle_stats_by_language(language: str) -> None:
    """Show statistics for specific language."""
    print(f"Statistics for {language}")
    # Implementation...
```

### Step 2: Import Handlers in main.py

Add to imports at top of `reveal/main.py`:

```python
from .cli import (
    # ... existing imports ...
    handle_stats_overview,
    handle_stats_by_language,
)
```

### Step 3: Create Command Handler Function

Add function in `reveal/main.py`:

```python
def _handle_stats_command() -> bool:
    """Handle 'reveal stats' subcommands.

    Returns:
        bool: True if stats command was handled, False otherwise
    """
    import argparse

    if len(sys.argv) < 2 or sys.argv[1] != 'stats':
        return False

    # Create stats subcommand parser
    parser = argparse.ArgumentParser(
        prog='reveal stats',
        description='Show reveal statistics and metrics',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='stats_type', help='Type of statistics')
    subparsers.required = True

    # Overview subcommand
    overview_parser = subparsers.add_parser('overview', help='Statistics overview')

    # By-language subcommand
    lang_parser = subparsers.add_parser('by-language', help='Statistics by language')
    lang_parser.add_argument('language', help='Language name')

    # Parse args (skip 'reveal stats' from argv)
    args = parser.parse_args(sys.argv[2:])

    # Route to handlers
    if args.stats_type == 'overview':
        handle_stats_overview()
    elif args.stats_type == 'by-language':
        handle_stats_by_language(args.language)

    return True
```

### Step 4: Wire into main()

Add call in `reveal/main.py` `main()` function, **early** (before argument parsing):

```python
def main():
    """Main entry point for reveal CLI."""

    # Handle stats subcommands early (before copy mode setup)
    if _handle_stats_command():
        return

    # Handle scaffold subcommands early (before copy mode setup)
    if _handle_scaffold_command():
        return

    # ... rest of main() ...
```

### Step 5: Add Documentation

Update `reveal/docs/SCAFFOLDING_GUIDE.md` or create new guide documenting the command.

### Step 6: Add Tests

Create `tests/test_cli_stats.py`:

```python
"""Tests for stats CLI commands."""

import subprocess

def test_stats_overview():
    """Test stats overview command."""
    result = subprocess.run(
        ['reveal', 'stats', 'overview'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert 'Statistics Overview' in result.stdout

def test_stats_by_language():
    """Test stats by-language command."""
    result = subprocess.run(
        ['reveal', 'stats', 'by-language', 'python'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert 'python' in result.stdout.lower()
```

## Checklist for New Commands

- [ ] Create handler functions in `reveal/cli/handlers_*.py`
- [ ] Import handlers in `reveal/main.py`
- [ ] Create `_handle_*_command()` function in `reveal/main.py`
- [ ] Wire into `main()` function (call early, before arg parsing)
- [ ] Add to `--help` output or document in guide
- [ ] Create integration tests
- [ ] Update CHANGELOG.md
- [ ] Consider adding to `help://` system

## Common Patterns

### Pattern 1: Simple Command (No Subcommands)

```python
def _handle_simple_command() -> bool:
    """Handle 'reveal simple' command."""
    if len(sys.argv) < 2 or sys.argv[1] != 'simple':
        return False

    handle_simple()
    return True
```

### Pattern 2: Command with Subcommands

See Step 3 example above for full subcommand pattern.

### Pattern 3: Command with Flags

```python
def _handle_flagged_command() -> bool:
    """Handle 'reveal command --flag' pattern."""
    if len(sys.argv) < 2 or sys.argv[1] != 'command':
        return False

    import argparse
    parser = argparse.ArgumentParser(prog='reveal command')
    parser.add_argument('--flag', action='store_true')
    args = parser.parse_args(sys.argv[2:])

    handle_command(flag=args.flag)
    return True
```

## Why Manual Wiring?

**Question**: Why not auto-discover commands like we do for adapters/analyzers/rules?

**Answer**: Top-level commands are fewer, more varied, and need explicit control:
- Explicit ordering (which commands run first)
- Namespace control (avoid command conflicts)
- Argument parsing complexity (subcommands, flags, etc.)
- Clear visibility of all entry points in one place

Auto-discovery works great for homogeneous components (adapters, analyzers, rules) that follow a strict pattern. Commands are heterogeneous and benefit from explicit wiring.

## Pit of Success: Catching Missing Wiring

### Rule: Orphaned Handler Detection

Create rule `C998` (Custom/CLI orphaned handler) to detect handlers not wired to CLI.

### Test Pattern: CLI Integration Tests

Always create integration tests that actually invoke `reveal <command>` via subprocess to verify wiring works.

### Documentation Pattern: This Guide

Reference this guide in:
- CONTRIBUTING.md (How to add new commands)
- SCAFFOLDING_GUIDE.md (Note: scaffolding is for adapters/analyzers/rules, not commands)
- Internal architecture docs

## Real Example: The Scaffold Command

See `reveal/main.py` `_handle_scaffold_command()` for a complete, production example of:
- Subcommand architecture
- Multiple subparsers (adapter, analyzer, rule)
- Handler routing
- Help text integration

## Questions?

- "Do I need to wire my adapter?" → **NO** - adapters use `@register_adapter` decorator
- "Do I need to wire my analyzer?" → **NO** - analyzers use `@register` decorator
- "Do I need to wire my rule?" → **NO** - rules use file system convention
- "Do I need to wire my new command?" → **YES** - follow this guide

## See Also

- `reveal/cli/handlers_scaffold.py` - Example handlers
- `reveal/main.py` - Main entry point and wiring examples
- `SCAFFOLDING_GUIDE.md` - For creating adapters/analyzers/rules
- `CONTRIBUTING.md` - General contribution guide
