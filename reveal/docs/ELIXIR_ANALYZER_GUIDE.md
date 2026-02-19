---
title: Elixir Analyzer Guide
category: guide
---
# Elixir Analyzer Guide

## Overview

The Elixir analyzer provides structure extraction and navigation for `.ex` files.

## Features

- **Structure Extraction**: Functions, classes, imports via tree-sitter
- **Element Navigation**: Extract specific functions/classes
- **Universal API**: Works with all reveal commands

## Installation

Ensure tree-sitter-elixir is installed:

```bash
pip install tree-sitter-elixir
```

If the tree-sitter grammar doesn't exist, you'll need to create a custom analyzer.

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

## Next Steps

1. Add sample Elixir files for testing
2. Verify tree-sitter-elixir works correctly
3. Add language-specific features if needed
4. Update this documentation with real examples

## See Also

- [QUICK_START.md](QUICK_START.md) - Getting started with reveal
- [ANALYZER_PATTERNS.md](ANALYZER_PATTERNS.md) - Common analyzer implementation patterns
