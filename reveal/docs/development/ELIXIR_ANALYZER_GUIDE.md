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

**Status: broken (BACK-480).** `reveal/analyzers/elixir.py` is a bare
`TreeSitterAnalyzer` subclass with no Elixir-specific node taxonomy. Elixir's
`defmodule`/`def` are macro-call shapes, not distinct node kinds the way
Python's `function_definition` is, so the generic dispatch extracts **zero
functions or modules** on real `.ex` files — `reveal file.ex` shows only
byte/line count. Fixing this is real feature work (teaching the analyzer
Elixir's macro-call-based function/module shapes), not a doc issue — tracked
separately in BACK-480, not done as part of this docs pass.

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

See "Overview" above — function/module detection is **not** currently implemented; `reveal file.ex` extracts no structure. Run it yourself to confirm current behavior before relying on this analyzer.

## See Also

- [QUICK_START.md](../QUICK_START.md) - Getting started with reveal
- [ANALYZER_PATTERNS.md](ANALYZER_PATTERNS.md) - Common analyzer implementation patterns
