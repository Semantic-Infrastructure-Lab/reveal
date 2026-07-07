---
title: Elixir Analyzer Guide
category: guide
help_topic: elixir
help_description: "Elixir analyzer internals (see BACK-480: known-broken structure extraction)"
help_category: dev_guides
help_token_estimate: "~400"
---
# Elixir Analyzer Guide

## Overview

**Status: working (BACK-480 resolved, extragalactic-journey-0706).** Elixir has
no dedicated `function_definition`/`class_definition` grammar nodes — every
definition is a macro **call**: `def add(a, b) do … end` parses as a `call`
whose first child is `identifier('def')`, and `defmodule Foo do … end` as a
call to `defmodule`. `ElixirAnalyzer` overrides `_extract_functions`,
`_extract_classes`, and `extract_element` to match on the leading macro keyword
and read the defined name out of the call's `arguments` subtree, so
`reveal file.ex` now lists functions and modules (previously: byte/line count
only).

- **Functions**: `def`, `defp`, `defmacro`, `defmacrop`, `defguard`,
  `defguardp`, `defdelegate`, `defn`. Handles zero-arg (`def ready do`), `when`
  guards (`def f(x) when x > 0`), single-line `, do:` clauses, and default
  args.
- **Modules**: `defmodule Foo.Bar do` surfaces as a class named `Foo.Bar`.

**Known characteristic** (not a bug): because a `def` is itself a call, a
function's `calls`/complexity walk covers the whole `def` — so control-flow
macros (`case`/`if`/`cond`/`with`) and the def's own name can appear in its
`calls` list. This is correct for complexity (they are real branch points) but
mildly noisy for `calls://`. Elixir remains `[untested]` tier: the nav-flag
surface (`--varflow`/`--sideeffects`/…) has no ground-truth fixtures yet.

## Installation

No separate install step is needed. The Elixir tree-sitter grammar is bundled
via `tree-sitter-language-pack` — do **not** `pip install tree-sitter-elixir`
separately; that instruction predates the v0.95.0 tree-sitter-language-pack
migration and no longer applies.

## Usage

### Basic Structure

```bash
reveal file.ex
```

### Extract Element

```bash
reveal file.ex function_name
```

### JSON Output

```bash
reveal file.ex --format=json
```

## Development

### Testing

```bash
pytest tests/test_elixir_analyzer.py -v
```

### Customization

To add custom behavior, override methods in `ElixirAnalyzer`:

```python
def get_structure(self):
    structure = super().get_structure()
    # Add custom processing
    return structure
```

## Status

Function/module structure extraction and element extraction work (BACK-480
resolved). Nav-flag support (`--varflow` etc.) is not yet fixture-verified —
Elixir stays `[untested]` tier in `reveal --languages` until it is.

## See Also

- [QUICK_START.md](../QUICK_START.md) - Getting started with reveal
- [ANALYZER_PATTERNS.md](ANALYZER_PATTERNS.md) - Common analyzer implementation patterns
