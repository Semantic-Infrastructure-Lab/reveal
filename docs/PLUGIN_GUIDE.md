# Plugin Development Guide

Learn how to create plugins for `reveal` to support new file types.

## Quick Start

Creating a plugin involves two steps:

1. **Define the plugin** in YAML (levels, features, metadata)
2. **Implement analyzers** (optional - for structure/preview levels)

## YAML Plugin Structure

```yaml
# plugins/example.yaml

# Extension mapping (single or multiple)
extension: .ext
# OR
extension: [.ext1, .ext2]

# Plugin metadata
name: Example File Type
description: Description of this file type
icon: 📄  # Emoji icon (optional)

# Level definitions (0-3)
levels:
  0:
    name: metadata
    description: File statistics and basic information
    breadcrumb: "What you see at this level"
    analyzer: null  # null = built-in handler
    outputs: [file_size, line_count, encoding]
    next_levels: [1, 2, 3]

  1:
    name: structure
    description: High-level structure without details
    breadcrumb: "Structure overview"
    analyzer: example_structure  # Name of Python analyzer
    outputs: [sections, components]
    next_levels: [0, 2, 3]
    tips:
      - "Use --grep to filter sections"
      - "Add -l 2 to see previews"

  2:
    name: preview
    description: Previews with summaries
    breadcrumb: "Content previews"
    analyzer: example_preview
    outputs: [summaries, headers]
    next_levels: [0, 1, 3]

  3:
    name: full
    description: Complete file content
    breadcrumb: "Full content (paged)"
    analyzer: null
    outputs: [full_content]
    next_levels: [0, 1, 2]
    paging: true
    page_size: 120

# Features enabled for this file type
features:
  grep: true
  context: true
  paging: true
  line_numbers: true
  syntax_highlighting: false  # Future feature

# Configuration passed to analyzers
analyzer_config:
  option1: value1
  option2: value2

# Examples shown in help
examples:
  - command: "reveal file.ext"
    description: "Show metadata"
  - command: "reveal file.ext -l 1"
    description: "Show structure"
```

## Level Design Philosophy

### Level 0: Metadata
**Purpose:** Answer "What is this file?"
**No analyzer needed** - uses built-in metadata extraction
**Outputs:**
- File size
- Line count
- Encoding
- Last modified
- File-type-specific info (e.g., "valid JSON", "has 3 documents")

### Level 1: Structure
**Purpose:** Answer "What's in this file?"
**Requires analyzer**
**Outputs:**
- Top-level components (functions, classes, sections, keys)
- Counts and statistics
- Organization/hierarchy
- No implementations or values

### Level 2: Preview
**Purpose:** Answer "What does each component do?"
**Requires analyzer**
**Outputs:**
- Signatures, summaries, descriptions
- Abbreviated values
- Metadata about components
- Still no full content

### Level 3: Full Content
**Purpose:** "Show me everything"
**No analyzer needed** - uses built-in paged reader
**Outputs:**
- Complete file content
- Syntax highlighting (future)
- Full context

## Implementing Analyzers

### Basic Analyzer Template

```python
# reveal/analyzers/example_analyzer.py

from pathlib import Path
from typing import Dict, Any

class ExampleStructureAnalyzer:
    """Analyzer for level 1 (structure) of example files"""

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize analyzer with plugin config

        Args:
            config: analyzer_config from plugin YAML
        """
        self.config = config or {}

    def analyze(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze file and return structured data

        Args:
            file_path: Path to file to analyze

        Returns:
            Dictionary with analysis results
        """
        with open(file_path, 'r') as f:
            content = f.read()

        # Your analysis logic here
        result = {
            "sections": self._extract_sections(content),
            "component_count": self._count_components(content),
            "summary": "Brief summary of file",
        }

        return result

    def _extract_sections(self, content: str) -> list:
        """Helper method to extract sections"""
        # Implementation
        pass

    def _count_components(self, content: str) -> int:
        """Helper method to count components"""
        # Implementation
        pass

# Register analyzer
ANALYZERS = {
    "example_structure": ExampleStructureAnalyzer,
}
```

### Formatter

Create a formatter to display analyzer results:

```python
# reveal/formatters.py (add to existing)

def format_example_structure(result: Dict[str, Any]) -> str:
    """Format example structure analysis results"""
    lines = []

    lines.append(f"Summary: {result['summary']}\n")
    lines.append(f"Components: {result['component_count']}\n")

    if result['sections']:
        lines.append("\nSections:")
        for section in result['sections']:
            lines.append(f"  • {section['name']} ({section['type']})")

    return "\n".join(lines)
```

## Real-World Example: JSON Plugin

### YAML Definition

```yaml
# plugins/json.yaml
extension: .json
name: JSON
description: JSON data files
icon: 🔧

levels:
  0:
    name: metadata
    breadcrumb: "File stats and JSON validity"
    analyzer: null
    outputs: [file_size, line_count, valid_json, root_type]
    next_levels: [1, 2, 3]

  1:
    name: structure
    breadcrumb: "Object keys and array lengths"
    analyzer: json_structure
    outputs: [root_keys, nesting_depth, array_counts]
    next_levels: [0, 2, 3]

  2:
    name: preview
    breadcrumb: "Keys with value types and samples"
    analyzer: json_preview
    outputs: [key_value_pairs, value_types, samples]
    next_levels: [0, 1, 3]

  3:
    name: full
    breadcrumb: "Complete JSON content (formatted)"
    analyzer: null
    next_levels: [0, 1, 2]
    paging: true

features:
  grep: true
  context: true
  paging: true

analyzer_config:
  max_sample_length: 50
  pretty_print: true
```

### Structure Analyzer Implementation

```python
# reveal/analyzers/json_analyzer.py
import json
from typing import Dict, Any

class JSONStructureAnalyzer:
    """Analyze JSON file structure"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

    def analyze(self, file_path: str) -> Dict[str, Any]:
        with open(file_path, 'r') as f:
            data = json.load(f)

        return {
            "root_type": type(data).__name__,
            "root_keys": list(data.keys()) if isinstance(data, dict) else None,
            "nesting_depth": self._max_depth(data),
            "total_keys": self._count_keys(data),
            "array_counts": self._count_arrays(data),
        }

    def _max_depth(self, obj, current=0):
        if isinstance(obj, dict):
            return max([self._max_depth(v, current + 1) for v in obj.values()] or [current])
        elif isinstance(obj, list):
            return max([self._max_depth(item, current + 1) for item in obj] or [current])
        return current

    def _count_keys(self, obj):
        if isinstance(obj, dict):
            return len(obj) + sum(self._count_keys(v) for v in obj.values())
        elif isinstance(obj, list):
            return sum(self._count_keys(item) for item in obj)
        return 0

    def _count_arrays(self, obj):
        count = 0
        if isinstance(obj, list):
            count = 1
        if isinstance(obj, (dict, list)):
            items = obj.values() if isinstance(obj, dict) else obj
            count += sum(self._count_arrays(item) for item in items)
        return count

ANALYZERS = {
    "json_structure": JSONStructureAnalyzer,
}
```

## Best Practices

### 1. Design for Progressive Disclosure

Each level should reveal MORE, not DIFFERENT information:

✅ Good:
- Level 0: File has 250 lines, 3 classes
- Level 1: Class names: UserManager, Database, APIClient
- Level 2: UserManager has 5 methods, Database has 3 methods...
- Level 3: Full source code

❌ Bad:
- Level 1: Show classes
- Level 2: Show functions (different category!)

### 2. Keep Levels Fast

Users should be able to quickly explore levels 0-2:
- Level 0: < 10ms (metadata only)
- Level 1: < 100ms (structure extraction)
- Level 2: < 200ms (preview generation)
- Level 3: Can be slower (full parsing/highlighting)

### 3. Provide Clear Breadcrumbs

Always tell users what they can do next:

```yaml
levels:
  1:
    next_levels: [0, 2, 3]  # Always list other levels
    tips:
      - "Use --grep 'ClassName' to filter specific classes"
      - "See full content with --level 3"
```

### 4. Handle Errors Gracefully

```python
def analyze(self, file_path: str) -> Dict[str, Any]:
    try:
        # Analysis logic
        pass
    except UnicodeDecodeError:
        return {"error": "File is not valid UTF-8"}
    except SyntaxError as e:
        return {"error": f"Parse error: {e}"}
    except Exception as e:
        return {"error": f"Analysis failed: {e}"}
```

## Testing Your Plugin

```python
# tests/test_example_plugin.py
import pytest
from reveal.plugin_loader import PluginLoader

def test_example_plugin_loaded():
    """Test that plugin is loaded"""
    loader = PluginLoader()
    plugin = loader.get_plugin_for_file("test.ext")
    assert plugin is not None
    assert plugin.name == "Example File Type"

def test_example_structure_analyzer():
    """Test structure analyzer"""
    from reveal.analyzers.example_analyzer import ExampleStructureAnalyzer

    analyzer = ExampleStructureAnalyzer()
    result = analyzer.analyze("tests/fixtures/sample.ext")

    assert "sections" in result
    assert len(result["sections"]) > 0
    assert "component_count" in result
```

## Publishing Your Plugin

Once your plugin is working:

1. **Add to README** in "Supported File Types" section
2. **Add example** in `docs/examples/`
3. **Submit PR** with:
   - Plugin YAML
   - Analyzer implementation (if needed)
   - Tests
   - Example file
   - Documentation updates

## Advanced Topics

### Composable Analyzers

Reuse existing analyzers:

```python
class TypeScriptStructureAnalyzer:
    """Analyze TypeScript - builds on JavaScript analyzer"""

    def __init__(self, config):
        self.js_analyzer = JavaScriptStructureAnalyzer(config)
        self.config = config

    def analyze(self, file_path: str):
        # Start with JS analysis
        result = self.js_analyzer.analyze(file_path)

        # Add TS-specific analysis
        result["interfaces"] = self._extract_interfaces(file_path)
        result["type_aliases"] = self._extract_type_aliases(file_path)

        return result
```

### Binary File Support

```yaml
extension: .xlsx
levels:
  0:
    name: metadata
    outputs: [file_size, sheet_count, row_count]
  1:
    name: structure
    analyzer: xlsx_structure  # Reads sheet names, dimensions
  2:
    name: preview
    analyzer: xlsx_preview  # Shows first N rows
  3:
    name: full
    analyzer: xlsx_full  # Shows all data (paged)
```

### Plugin Dependencies

Specify optional dependencies in `pyproject.toml`:

```toml
[project.optional-dependencies]
excel = ["openpyxl>=3.0"]
jupyter = ["nbformat>=5.0"]
```

## Questions?

- Check [examples](examples/) for inspiration
- Open an issue with `[Plugin Help]` tag
- Look at existing analyzers in `reveal/analyzers/`

---

**Happy plugin building!** 🔌
