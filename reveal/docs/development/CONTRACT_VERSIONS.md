---
title: "Output Contract Version Policy"
type: reference
beth_topics:
  - reveal
  - contract-version
  - adapter-authoring
  - output-contract
---

# Output Contract Version Policy

Reveal adapters return results conforming to the **Output Contract** — a stable
shape (`contract_version`, `type`, `source`, `source_type`, plus adapter-specific
data) that AI agents and downstream tools can rely on.

This document explains when to use `'1.0'` vs `'1.1'` and how to add fields
without breaking consumers.

---

## Versions in use

| Version | When to use | Fields |
|---------|-------------|--------|
| `'1.0'` | Adapter has no parse uncertainty: deterministic queries (json, env, ssl cert read, mysql DDL). | `contract_version`, `type`, `source`, `source_type`, plus data. |
| `'1.1'` | Adapter uses parsing or heuristics where confidence < 1.0, or wants to report `warnings`/`errors` to agents. | All of `'1.0'` plus `meta: {parse_mode, confidence, warnings, errors}`. |

**Choose `'1.1'` if any of the following is true:**
- The adapter uses tree-sitter, regex, or pattern matching to extract structure.
- The result is approximate (e.g. call graphs that miss dynamic dispatch).
- The adapter wants to surface per-file warnings or errors to agents.
- The adapter wants to report a `confidence` score so agents can decide whether
  to trust the result.

Otherwise use `'1.0'`. There is no benefit to `'1.1'` without populated `meta`.

---

## How `'1.1'` is auto-populated

`ResultBuilder.create(contract_version='1.1', parse_mode=..., confidence=...)`
automatically adds `meta` only when at least one of `parse_mode`, `confidence`,
`warnings`, or `errors` is non-empty. Passing `'1.1'` with no meta data is the
same as passing `'1.0'` (the `meta` field is omitted).

This means **adapters can safely upgrade to `'1.1'`** without filling in meta
on every code path — the contract degrades gracefully.

---

## Adding a new field

Adding **new optional fields** to either version is backwards-compatible —
existing consumers ignore unknown keys.

Adding **required fields**, renaming, or removing fields is a breaking change
and requires:
1. A version bump (`'1.1'` → `'1.2'`).
2. Updates to `_CONTRACT_FIELDS` in `reveal/utils/results.py`.
3. A migration window where adapters return both old and new shapes.

A **version bump is also required** if the *meaning* of a field changes
(e.g. `source` going from absolute to relative path).

---

## `meta` field reference

When `contract_version='1.1'` and meta is populated:

```python
{
    'contract_version': '1.1',
    'type': 'ast_query',
    'source': 'src/',
    'source_type': 'directory',
    'meta': {
        'parse_mode': 'tree_sitter_full',  # see values below
        'confidence': 0.95,                 # 0.0–1.0
        'warnings': [],                     # list of {code, message, file}
        'errors': [],                       # list of {code, message, file, fallback}
    },
    # adapter-specific data fields below...
}
```

### `parse_mode` values

| Value | Meaning |
|-------|---------|
| `tree_sitter_full` | Complete tree-sitter parse, no errors. |
| `tree_sitter_partial` | Tree-sitter parsed but some nodes are `ERROR` nodes. |
| `fallback` | Tree-sitter failed; used regex/heuristic fallback. |
| `regex` | Pure regex extraction (no AST). |
| `heuristic` | Pattern-based, no formal parse. |

### `confidence` bands

| Score | Meaning |
|-------|---------|
| `1.0` | Perfect parse, no uncertainty. |
| `0.95–0.99` | High confidence (typical for tree-sitter on valid code). |
| `0.80–0.94` | Good confidence (some heuristic decisions, e.g. call graph). |
| `0.50–0.79` | Partial results (parse errors, fallback used). |
| `< 0.50` | Low confidence — agent should treat result skeptically. |

### `warnings` and `errors`

Both are lists of dicts:
- `warnings`: non-fatal issues. Format: `{'code': 'W001', 'message': '...', 'file': '...'}`
- `errors`: fatal failures where a fallback was used. Format includes a `fallback` key.

---

## Adapter implementation pattern

```python
from reveal.utils.results import ResultBuilder

return ResultBuilder.create(
    result_type='calls_query',
    source=self.path,
    contract_version='1.1',
    parse_mode='tree_sitter_full',
    confidence=0.85,  # call graph misses dynamic dispatch
    data={'callees': [...]},
)
```

For approximate analysis (call graphs, type narrowing, side-effect classification),
set `confidence` honestly — agents use this to decide whether to act on the result
or ask the user to verify.

---

## When not to use `'1.1'`

- Stable, deterministic adapters (env vars, JSON read, SQL DDL). They have nothing
  to express in `meta` and `'1.0'` is the clearer signal.
- One-shot health checks that already include their own diagnostic shape.
