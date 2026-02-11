"""Templates for analyzer scaffolding."""

ANALYZER_TEMPLATE = '''"""{description}."""

from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('{extension}', name='{display_name}', icon='{icon}')
class {class_name}Analyzer(TreeSitterAnalyzer):
    """{display_name} file analyzer.

    Full {display_name} support via tree-sitter!

    Automatically extracts:
    - Functions/methods
    - Classes/structs
    - Imports/modules
    - Comments and docstrings

    NOTE: This assumes tree-sitter-{language} is available.
    Install it with: pip install tree-sitter-{language}

    If tree-sitter grammar doesn't exist, you'll need to:
    1. Create a custom FileAnalyzer subclass instead
    2. Implement get_structure() manually
    3. See reveal/base.py for FileAnalyzer base class
    """
    language = '{language}'

    # Optional: Override these for custom behavior
    # def get_structure(self):
    #     structure = super().get_structure()
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
        """Test structure extraction on sample code."""
        # TODO: Add sample {display_name} code for testing
        sample_code = """
        # Add sample {display_name} code here
        """

        test_file = tmp_path / "test{extension}"
        test_file.write_text(sample_code)

        analyzer = {class_name}Analyzer(str(test_file))
        structure = analyzer.get_structure()

        # TODO: Add assertions based on expected structure
        assert structure is not None
        assert 'type' in structure
        # assert structure['functions']  # Example assertion


class Test{class_name}AnalyzerRegistration:
    """Test analyzer registration."""

    def test_analyzer_registered(self):
        """Test analyzer is registered for {extension} files."""
        from reveal.registry import get_analyzer_for_file

        test_path = f"test{extension}"
        analyzer_class = get_analyzer_for_file(test_path)

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
