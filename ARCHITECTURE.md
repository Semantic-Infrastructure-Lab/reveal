---
title: "Reveal Architecture"
type: reference
beth_topics:
  - reveal
  - architecture
  - adapter
  - output-contract
  - progressive-disclosure
---

# Reveal Architecture

> **One mental model**: Structure → Element → Detail, enforced by the base class, expressed through URI schemes, rendered as token-efficient structured output.

This document explains how Reveal works end-to-end: URI routing, the adapter lifecycle, output contract, query parameter pipeline, help system tiers, and subcommand orchestration. Read it before contributing an adapter or subcommand.

---

## Contents

1. [System Overview](#system-overview)
2. [URI Routing](#uri-routing)
3. [Adapter Lifecycle](#adapter-lifecycle)
4. [Output Contract](#output-contract)
5. [Query Parameter Pipeline](#query-parameter-pipeline)
6. [Help System Tiers](#help-system-tiers)
7. [Subcommand Orchestration](#subcommand-orchestration)
8. [Renderer Layer](#renderer-layer)
9. [Adding an Adapter (Checklist)](#adding-an-adapter-checklist)

---

## System Overview

```
User input (CLI)
      │
      ▼
  main.py              — entry point; dispatches to special modes or _main_impl
      │
      ▼
  cli/routing.py       — URI vs file detection; adapter instantiation; rendering
      │
  ┌───┴──────────────┐
  │                  │
  ▼                  ▼
Adapter            FileAnalyzer
(URI scheme)       (file path)
  │
  ▼
get_structure() / get_element()
  │
  ▼
Output Contract dict
  │
  ▼
Renderer / JSON / grep
```

Reveal has two parallel paths:
- **File path** → `FileAnalyzer` (tree-sitter + language analyzers) → structured output
- **URI scheme** (`ssl://`, `ast://`, etc.) → `ResourceAdapter` → structured output

Both converge on the same rendering layer and the same Output Contract format.

---

## URI Routing

**Entry point**: `reveal/cli/routing.py` → `handle_uri()`

### Detection

A target is a URI if it:
1. Matches `scheme://...` where `scheme` is a registered adapter
2. Or is explicitly treated as a file path otherwise

### Parsing

`scheme://resource[/element][?query_params]`

| Component | Example | Role |
|-----------|---------|------|
| scheme | `ssl` | Selects the adapter class from `_ADAPTER_REGISTRY` |
| resource | `example.com` or `./src` | Passed to adapter `__init__` |
| element | `users` in `sqlite:///app.db/users` | Selects `get_element()` instead of `get_structure()` |
| query_params | `?complexity>10&format=json` | Parsed by `parse_query_params()` in `utils/query.py` |

### Adapter Registry

`reveal/adapters/base.py` maintains `_ADAPTER_REGISTRY: Dict[str, type]`. Adapters register at import time via `@register_adapter('scheme')`. The registry is populated by `import reveal.adapters` (which imports all sub-packages).

```python
@register_adapter('sqlite')
@register_renderer(SqliteRenderer)
class SQLiteAdapter(ResourceAdapter):
    ...
```

---

## Adapter Lifecycle

Every adapter follows this progression:

```
__init__(resource)          — parse URI, set internal state
      │
      ▼
from_uri(scheme, resource, element)   — class method; tries 4 constructor conventions
      │                               — (no-arg, query-parsing, keyword-arg, full-URI)
      ▼
get_structure(**kwargs)     — overview: tables, functions, cert chains, etc.
      │
      ▼
get_element(name, **kwargs) — drill down: specific table, function, cert, etc.
```

The base class `ResourceAdapter` (`reveal/adapters/base.py`) enforces:
- `get_structure()` — **required**, abstract
- `get_element()` — optional (returns `None` by default)
- `get_available_elements()` — optional (for autonomous agent exploration)
- `get_schema()` — static, machine-readable schema (for `help://schemas/<adapter>` and `--discover`)
- `get_help()` — static, human-readable help (for `help://<adapter>`)

### Constructor Conventions

`from_uri()` tries four strategies in order, stopping at the first that succeeds:

1. **No-arg**: `Adapter()` — for adapters that take no resource (e.g., `env://`, `python://`)
2. **Query-parsing**: `Adapter(path, query_params)` — for adapters that parse path + query (e.g., `ast://`, `json://`)
3. **Keyword-arg**: `Adapter(resource=resource)` — generic fallback
4. **Full URI**: `Adapter(f'{scheme}://{resource}')` — for adapters that want the raw URI (e.g., `mysql://`)

Override `from_uri()` in a subclass to use a single deterministic path.

---

## Output Contract

**Spec**: `reveal/docs/OUTPUT_CONTRACT.md`

Every `get_structure()` and `get_element()` return must include these required fields:

| Field | Type | Value |
|-------|------|-------|
| `contract_version` | string | `"1.0"` or `"1.1"` |
| `type` | string | Matches a declared entry in `get_schema()['output_types']` |
| `source` | string | The URI or path that was queried |
| `source_type` | string | Semantic type: `"directory"`, `"database"`, `"host"`, `"table"`, etc. |

**v1.1 addition** — `meta` dict for parse confidence (tree-sitter adapters):

```python
{
    'contract_version': '1.1',
    'type': 'ast_query',
    'source': 'src/',
    'source_type': 'directory',
    'meta': ResourceAdapter.create_meta(
        parse_mode='tree_sitter_full',
        confidence=0.95,
        warnings=[...],
        errors=[...]
    ),
    ...
}
```

### Compliance Testing

`tests/test_output_contract_compliance.py` — 30 tests. Calls `get_structure()` on all locally-testable adapters (14 of 22) and verifies required fields + schema consistency. Network adapters (ssl, mysql, domain, autossl, cpanel) are explicitly skipped with documented skip reasons.

Run: `pytest tests/test_output_contract_compliance.py`

---

## Query Parameter Pipeline

**Parser**: `reveal/utils/query.py` → `parse_query_params(uri_or_query_string)`

All adapters MUST use `parse_query_params()`. Never parse `?` strings manually — this was unified in v0.63.0 replacing 4 hand-rolled loops.

### Supported Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `=` | Equals | `?type=function` |
| `!=` | Not equals | `?type!=method` |
| `>` / `<` | Numeric comparison | `?complexity>10` |
| `>=` / `<=` | Numeric comparison | `?lines>=50` |
| `~=` | Regex / glob match | `?name~=test_*` |
| `..` | Range (inclusive) | `?lines=10..50` |

### Budget Limits

`reveal/utils/query.py` → `apply_budget_limits(data, adapter)` applies `--max-items` and `--max-bytes` to the adapter's declared `BUDGET_LIST_FIELD`. Adapters opt in by setting `BUDGET_LIST_FIELD = 'results'` (or whatever field holds the list).

### Universal Params

These params are handled at the routing layer, not per-adapter:
- `format=json` — emit JSON instead of text
- `format=grep` — emit grep-compatible lines
- `format=dot` — emit Graphviz DOT (where supported)
- `show=calls` — override display mode (ast://, calls://)

---

## Help System Tiers

Three help tiers serve different consumers:

| Tier | Command | Audience | Token cost |
|------|---------|----------|------------|
| 1 | `reveal --help` | Humans — CLI flag reference | Low |
| 2 | `reveal help://<adapter>` | Humans + agents — structured adapter guide | Medium |
| 3 | `reveal --agent-help` / `reveal --agent-help-full` | AI agents — llms.txt-style brief | Low / High |

### Schema Discovery

`reveal help://schemas/<adapter>` → calls `get_schema()` → returns JSON schema for programmatic consumers.

`reveal --discover` → dumps all 22 adapters' schemas in one JSON document (output_types, query_params, cli_flags, examples, notes). Designed for agent capability detection.

### Help Data Sources

Adapters serve help via two patterns:

1. **`help.py` module** — rich Python-generated help (ast://, calls://, json://, etc.)
2. **YAML files** — `reveal/adapters/help_data/<adapter>.yaml` loaded via `load_help_data()` (sqlite://, domain://, ssl://, imports://, stats://, mysql://, diff://, nginx://, xlsx://, stats://)

---

## Subcommand Orchestration

Six subcommands compose adapters into higher-level workflows:

| Subcommand | File | What it composes |
|------------|------|-----------------|
| `reveal check <dir>` | `cli/commands/check.py` | Runs quality rules (B/M/I/V/L/N series) |
| `reveal review <diff>` | `cli/commands/review.py` | diff + check + hotspots + complexity delta |
| `reveal health <dir>` | `cli/commands/health.py` | CI-oriented: exit 0/1/2 for pass/warn/fail |
| `reveal pack <dir>` | `cli/commands/pack.py` | Token-budgeted context snapshots for LLMs |
| `reveal hotspots <dir>` | `cli/commands/hotspots.py` | Complexity + coupling ranking |
| `reveal dev <cmd>` | `cli/commands/dev.py` | Developer tooling (new-adapter scaffold, etc.) |

Subcommands are dispatched from `main.py` → `_dispatch_subcommand()` before the normal routing path. They call adapters programmatically (not via URI routing) and compose their outputs.

### Example: `reveal review`

```
reveal review main..feature
      │
      ├─ diff://git://main/.:git://HEAD/.    → changed functions + complexity delta
      ├─ reveal check <changed files>        → rule violations
      └─ reveal hotspots <changed files>     → complexity spikes
             │
             ▼
         Unified review report (text or JSON)
```

---

## Renderer Layer

**Location**: `reveal/rendering/`

Rendering is separate from data production. Adapters return dicts; renderers format them.

### Dispatch

`reveal/adapters/base.py` → `_RENDERER_REGISTRY` maps scheme → renderer class. `@register_renderer(MyRenderer)` on an adapter class wires this automatically.

For adapters without a custom renderer, the base renderer handles JSON, grep, and generic text output.

### Format Flags

- `--format json` → skip renderer, emit `json.dumps(result)`
- `--format grep` → grep-compatible `file:line:match` lines
- `--format dot` → Graphviz DOT (calls://)
- (default) → text renderer for the adapter's type

### Field Selection

`reveal/display/formatting.py` → `filter_fields(data, fields)` applies `--fields name,complexity` filtering post-render. Works with any adapter that returns a dict with a list field.

---

## Adding an Adapter (Checklist)

1. **Create** `reveal/adapters/<scheme>/` directory with `__init__.py`, `adapter.py`, `renderer.py`
2. **Inherit** from `ResourceAdapter`; decorate with `@register_adapter('scheme')` and `@register_renderer(MyRenderer)`
3. **Implement** `get_structure()` — required; `get_element()` — if element drill-down makes sense
4. **Output Contract**: return `contract_version`, `type`, `source`, `source_type` from both methods
5. **Schema**: implement `get_schema()` returning `output_types`, `query_params`, `cli_flags`, `example_queries`, `notes`. Every `type` returned by `get_structure()`/`get_element()` must appear in `output_types`
6. **Help**: implement `get_help()` or add `reveal/adapters/help_data/<scheme>.yaml`
7. **Tests**: add `tests/test_<scheme>_adapter.py`. Run `pytest tests/test_output_contract_compliance.py` — it will automatically test your new adapter
8. **Docs**: add `reveal/docs/<SCHEME>_ADAPTER_GUIDE.md` and link it from `reveal/docs/INDEX.md`
9. **CHANGELOG**: add entry under `[Unreleased]`

### Adapter Quality Tiers (Target)

| Tier | Requirements |
|------|-------------|
| Experimental | `get_schema()` + `get_structure()` + output contract + basic tests |
| Beta | + `get_element()` + conformance suite pass + 20+ tests + adapter guide doc |
| Stable | + production incident survival + 50+ tests + well-linked docs |

---

*Last updated: session serene-mist-0317*
