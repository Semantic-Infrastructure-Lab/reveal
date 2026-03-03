---
title: "reveal dev — Developer Tooling"
type: guide
---

# reveal dev — Developer Tooling

Scaffolding and introspection tools for extending Reveal.

## Commands

```
reveal dev new-adapter NAME [--uri SCHEME]    # Scaffold a new URI adapter
reveal dev new-analyzer NAME [--ext EXT]     # Scaffold a new file analyzer
reveal dev new-rule CODE NAME [--cat CAT]    # Scaffold a new quality rule
reveal dev inspect-config [PATH]             # Show effective .reveal.yaml config
```

## CLI Flags

| Flag | Description |
|------|-------------|
| `--uri SCHEME` | URI scheme for new adapter (e.g., `mydb`) |
| `--ext EXT` | File extension for new analyzer (e.g., `.myext`) |
| `--cat CAT` | Rule category (bugs, maintainability, performance, etc.) |

## Examples

```bash
reveal dev new-adapter mydb --uri mydb        # Creates adapters/mydb/ scaffold
reveal dev new-analyzer toml --ext .toml      # Creates analyzers/toml.py scaffold
reveal dev new-rule M999 "Too Long" --cat maintainability
reveal dev inspect-config                     # See config applied to current dir
reveal dev inspect-config /some/project/      # See config for another dir
```

## Scaffold Output

New adapters and analyzers are created in the current reveal source tree.
Rules are added to `reveal/quality/rules/`.

## See Also

- `reveal help://scaffolding` — Full scaffolding guide
- `reveal help://adapter-authoring` — How to write adapters
- `reveal dev --help` — Full flag reference
