"""Templates for analyzer scaffolding."""

ANALYZER_TEMPLATE = '''"""{description}."""

from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('{extension}', name='{display_name}', icon='{icon}')
class {class_name}Analyzer(TreeSitterAnalyzer):
    """{display_name} file analyzer.

    {display_name} support via tree-sitter!

    NOTE: TreeSitterAnalyzer uses generic extraction methods that may not
    work for all languages out-of-the-box. If structure extraction returns
    empty, you'll need to override extraction methods to match your language's
    specific node types.

    Prerequisites:
    - tree-sitter-{language} must be installed: pip install tree-sitter-{language}
    - If no tree-sitter grammar exists, use FileAnalyzer base class instead

    See reveal/treesitter.py for extraction methods to override:
    - _extract_functions()
    - _extract_classes()
    - _extract_imports()
    - _extract_structs()
    """
    language = '{language}'

    # Override these methods if generic extraction doesn't work:
    # def _extract_functions(self):
    #     # Custom function extraction for {display_name}
    #     pass
    #
    # def get_structure(self, **kwargs):
    #     structure = super().get_structure(**kwargs)
    #     # Add custom processing here
    #     return structure
'''

TEST_TEMPLATE = '''"""Tests for {class_name}Analyzer."""

import pytest
from pathlib import Path
from reveal.analyzers.{module_name} import {class_name}Analyzer


class Test{class_name}AnalyzerInit:
    """Test analyzer initialization."""

    def test_init(self):
        """Test analyzer can be instantiated."""
        analyzer = {class_name}Analyzer(str(Path(__file__)))
        assert analyzer is not None
        assert analyzer.language == '{language}'


class Test{class_name}AnalyzerStructure:
    """Test structure extraction."""

    def test_get_structure_sample_code(self, tmp_path):
        """Test structure extraction on sample code.

        NOTE: TreeSitterAnalyzer's generic extraction may not work out-of-the-box
        for all languages. If structure is empty, you may need to override
        extraction methods to match language-specific node types.
        """
        # TODO: Add sample {display_name} code for testing
        sample_code = """
        # Add sample {display_name} code here
        """

        test_file = tmp_path / "test{extension}"
        test_file.write_text(sample_code)

        analyzer = {class_name}Analyzer(str(test_file))

        # Verify analyzer initializes and parses correctly
        assert analyzer is not None
        assert analyzer.tree is not None, "Tree-sitter should parse code"

        structure = analyzer.get_structure()
        assert isinstance(structure, dict)
        # TODO: Add specific assertions based on expected structure
        # e.g., assert 'functions' in structure and len(structure['functions']) > 0


class Test{class_name}AnalyzerRegistration:
    """Test analyzer registration."""

    def test_analyzer_registered(self):
        """Test analyzer is registered for {extension} files."""
        from reveal.registry import get_analyzer

        test_path = "test{extension}"
        analyzer_class = get_analyzer(test_path)

        assert analyzer_class == {class_name}Analyzer
'''

DOC_TEMPLATE = '''# {display_name} Analyzer Guide

## Overview

The {display_name} analyzer provides structure extraction and navigation for `{extension}` files.

## Features

- **Structure Extraction**: Functions, classes, imports via tree-sitter
- **Element Navigation**: Extract specific functions/classes
- **Universal API**: Works with all reveal commands

## Installation

Ensure tree-sitter-{language} is installed:

```bash
pip install tree-sitter-{language}
```

If the tree-sitter grammar doesn't exist, you'll need to create a custom analyzer.

## Usage

### Basic Structure

```bash
reveal file{extension}
```

### Extract Element

```bash
reveal file{extension} function_name
```

### JSON Output

```bash
reveal file{extension} --format=json
```

## Development

### Testing

```bash
pytest tests/test_{module_name}_analyzer.py -v
```

### Customization

To add custom behavior, override methods in `{class_name}Analyzer`:

```python
def get_structure(self):
    structure = super().get_structure()
    # Add custom processing
    return structure
```

## Next Steps

1. Add sample {display_name} files for testing
2. Verify tree-sitter-{language} works correctly
3. Add language-specific features if needed
4. Update this documentation with real examples
'''
