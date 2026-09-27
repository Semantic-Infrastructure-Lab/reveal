---
title: CLI Integration Guide
category: guide
help_topic: cli-integration
help_description: "Adding a new top-level subcommand to reveal's CLI"
help_category: dev_guides
help_token_estimate: "~2,000"
---
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

### 2. One Registry Entry (Top-Level Commands)

Top-level commands (`reveal overview`, `reveal check`, `reveal dev`, ...) are listed in one
table, `COMMANDS` in `reveal/cli/invocation.py`:

```bash
reveal overview .                  # a subcommand: COMMANDS['overview']
reveal --format json overview .    # the same; global options may precede the name
reveal --languages                 # a flag-based mode of the path form, not a command
```

`main.py` never inspects the command line itself. `main()` parses `sys.argv` once into an
`Invocation`, which finds the subcommand name. `main._dispatch_and_run` then runs the
same steps for a subcommand and for the path/URI form:
- parse with the command's own parser;
- apply the global flags;
- honor `--copy`;
- run through `reveal/cli/routing/subcommand.py`'s `dispatch_subcommand`, which applies the flag ledger and
the `--exclude`/REVEAL_IGNORE walk scope (BACK-1539).

A new command gets all of these without wiring. Code
that needs to know what was typed asks `reveal.cli.invocation.current_invocation()`.
`scripts/check_boundaries.py` rejects a `sys.argv` read anywhere else (BACK-1058).

## Adding a New Top-Level Command

**Example**: adding `reveal stats`.

### Step 1: Create the Command Module

Create `reveal/cli/commands/stats.py` with a parser factory and a runner:

```python
"""reveal stats — statistics overview."""

import argparse
from argparse import Namespace

from ..parser import _build_global_options_parser


def create_stats_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='reveal stats',
        description='Show reveal statistics and metrics',
        parents=[_build_global_options_parser()],  # --format, --copy, --provenance, ...
    )
    parser.add_argument('path', nargs='?', default='.', help='Directory to measure')
    return parser


def run_stats(args: Namespace) -> None:
    ...  # render the result for args.format
```

Take `--format`, `--copy`, `--provenance` and the other global options from
`_build_global_options_parser()`; never re-declare them. If the command walks a tree, also
call `add_exclude_argument(parser)` and `add_gitignore_arguments(parser)` from
`reveal/cli/global_flags.py`.

### Step 2: Register It

Add one line to `COMMANDS` in `reveal/cli/invocation.py`:

```python
    'stats':        _spec('stats'),
```

`_spec(name)` means module `reveal.cli.commands.<name>`, `create_<name>_parser` and
`run_<name>`. If there is no same-named URI adapter to declare the output formats, pass the
formats the runner renders, for example `_spec('stats', ('text', 'json'))`. Any other `--format` is
then rejected instead of printed as text (BACK-1425).

### Step 3: List It in `--help`

Add a line to `_build_subcommands_section()` in `reveal/cli/parser.py`.

### Step 4: Add Tests

Drive the real entry point in-process with `main(argv)`:

```python
from reveal.main import main


def test_stats_json(capsys, tmp_path):
    main(['reveal', 'stats', str(tmp_path), '--format', 'json'])
    assert capsys.readouterr().out.lstrip().startswith('{')
```

`tests/test_subcommand_flag_matrix.py` and `tests/test_flag_ledger.py` read `COMMANDS`,
so they cover the new command automatically. Every flag its parser accepts must be honored
or reported in a note.

## Checklist for New Commands

- [ ] `reveal/cli/commands/<name>.py` with `create_<name>_parser()` and `run_<name>(args)`
- [ ] Global options come from `_build_global_options_parser()`, and walkers call `add_exclude_argument`
- [ ] One `COMMANDS` entry in `reveal/cli/invocation.py`
- [ ] A line in `--help` (`_build_subcommands_section`)
- [ ] Tests via `main(['reveal', '<name>', ...])`; the flag matrices pick it up
- [ ] Update CHANGELOG.md
- [ ] Consider adding it to the `help://` system

## Why a Registry, Not Auto-Discovery?

**Question**: Why not auto-discover commands like we do for adapters/analyzers/rules?

**Answer**: A command name takes a word away from the path namespace: `reveal overview`
means the command, not a `./overview` directory (BACK-1112). One explicit table keeps the
reserved words visible in one place, and `help://schemas/<name>` reads the same table to
tell a CLI-only command from an unknown name (BACK-1028).

## Real Example: The Scaffold Command

See `reveal/cli/commands/scaffold.py` for a complete example of:
- Subcommand architecture
- Multiple subparsers (adapter, analyzer, rule)
- Handler routing
- Help text integration

## Questions?

- "Do I need to wire my adapter?" → **NO** - adapters use `@register_adapter` decorator
- "Do I need to wire my analyzer?" → **NO** - analyzers use `@register` decorator
- "Do I need to wire my rule?" → **NO** - rules use file system convention
- "Do I need to wire my new command?" → **YES** - one `COMMANDS` entry; follow this guide

## See Also

- `reveal/cli/invocation.py` - `COMMANDS` and the `Invocation`
- `reveal/main.py` - the entry point: parse once, then `_dispatch_and_run`
- `SCAFFOLDING_GUIDE.md` - For creating adapters/analyzers/rules
- `CONTRIBUTING.md` - General contribution guide
- [SCAFFOLDING_GUIDE.md](SCAFFOLDING_GUIDE.md) - Creating adapters, analyzers, and rules
- [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) - Deep dive on adapter creation
