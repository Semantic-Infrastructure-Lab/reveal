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

### 🎯 Critical Pattern: Universal Line Numbers

**All analyzers MUST return line numbers for composability with CLI tools.**

The framework provides helpers via `BaseAnalyzer` that make this easy:

```python
from reveal.analyzers.base import BaseAnalyzer
from reveal.registry import register

@register(['.toml'], name='TOML', icon='⚙️')
class TOMLAnalyzer(BaseAnalyzer):
    def __init__(self, lines, **kwargs):
        super().__init__(lines, **kwargs)  # ✅ Accepts file_path, focus_start, focus_end

    def analyze_structure(self):
        keys = []
        for key_name in self.parsed_data.keys():
            # Use find_definition() helper to locate key in source
            line_num = self.find_definition(f'{key_name} =')

            keys.append({
                'name': key_name,
                'line': line_num if line_num else 1
            })

        return {'top_level_keys': keys}
```

**Key Helpers from BaseAnalyzer:**

- `self.find_definition(text)` - Find where text appears in source file
- `self.format_location(line_num)` - Returns `filename:32` or `L0032`
- `self.with_location(text, line_num)` - Formats aligned output
- `self.in_focus_range(line_num)` - Check if line in user-specified range

**Output Format:**

✅ **Correct** (dict with line):
```python
{'name': 'my_function', 'line': 42}
```

❌ **Wrong** (just a string):
```python
'my_function'  # No way to find it in the file!
```

**Why This Matters:**

Reveal's line numbers work with ALL Unix tools:
```bash
# Find something
$ reveal config.yaml --level 1 | grep database
config.yaml:12  database

# Jump to it
$ vim config.yaml:12

# Check history
$ git blame config.yaml -L 12,20
```

**Reference Implementations:**
- `reveal/analyzers/json_analyzer.py` - Uses `find_definition()` for keys
- `reveal/analyzers/yaml_analyzer.py` - Handles comments correctly
- `reveal/analyzers/toml_analyzer.py` - Separates sections from keys
- `reveal/analyzers/python_analyzer.py` - Uses AST node.lineno
- `reveal/analyzers/sql_analyzer.py` - Complex AST + regex approach
- `reveal/analyzers/rust_analyzer.py` - Tree-sitter based (see below)
- `reveal/analyzers/csharp_analyzer.py` - Tree-sitter based (see below)

### 🌳 Tree-Sitter: Multi-Language Support Made Easy

**For compiled languages** (Rust, C#, Go, Java, TypeScript, C++, etc.), tree-sitter provides a **universal parsing solution** that preserves exact line numbers and handles complex syntax.

**Why tree-sitter?**
- ✅ **50+ languages** supported out of the box
- ✅ **Native line numbers** - no `find_definition()` workarounds needed
- ✅ **Fast and accurate** - battle-tested by GitHub, Neovim, etc.
- ✅ **Consistent API** - one pattern works for all languages
- ✅ **Easy to extend** - add a new language in ~30 minutes

**Installation:**
```bash
pip install 'reveal-cli[treesitter]'
# Or: pip install tree-sitter==0.21.3 tree-sitter-languages>=1.10.0
```

#### Creating a Tree-Sitter Analyzer

**Step 1: Inherit from TreeSitterAnalyzer**

```python
from reveal.analyzers.treesitter_base import TreeSitterAnalyzer
from reveal.registry import register

@register(['.rs'], name='Rust', icon='🦀')
class RustAnalyzer(TreeSitterAnalyzer):
    """Analyzer for Rust source files"""

    # Set the tree-sitter language name
    language_name = 'rust'

    def __init__(self, lines, **kwargs):
        """Initialize with node type mappings"""
        # Map generic names to Rust-specific node types
        self.node_type_map = {
            'function': 'function_item',
            'struct': 'struct_item',
            'class': 'struct_item',  # Rust uses structs, not classes
            'import': 'use_declaration',
        }
        super().__init__(lines, **kwargs)
```

**That's it!** The base class automatically:
- Parses the code using tree-sitter
- Extracts functions, classes, structs, imports
- Returns dictionaries with `{'name': ..., 'line': ...}`
- Provides line numbers from the AST (no searching needed!)

**Step 2: Add Language-Specific Extractions (Optional)**

```python
    def extract_custom(self):
        """Extract Rust-specific items beyond the basics"""
        return {
            'enums': self._extract_nodes('enum_item', name_field='name'),
            'traits': self._extract_nodes('trait_item', name_field='name'),
            'impls': self._extract_impl_blocks(),  # Custom extraction
            'mods': self._extract_nodes('mod_item', name_field='name'),
        }

    def _extract_impl_blocks(self):
        """Custom extraction for trait implementations"""
        impls = []
        cursor = self.tree.walk()

        def visit(cursor):
            node = cursor.node
            if node.type == 'impl_item':
                # Get trait and type being implemented
                trait_node = node.child_by_field_name('trait')
                type_node = node.child_by_field_name('type')

                if trait_node and type_node:
                    name = f"{trait_node.text.decode()} for {type_node.text.decode()}"
                else:
                    name = type_node.text.decode() if type_node else "<impl>"

                impls.append({
                    'name': name,
                    'line': node.start_point[0] + 1  # Tree-sitter uses 0-indexed
                })

            # Recurse to children
            if cursor.goto_first_child():
                visit(cursor)
                while cursor.goto_next_sibling():
                    visit(cursor)
                cursor.goto_parent()

        visit(cursor)
        return impls
```

**Step 3: Custom Formatting (Optional)**

```python
    def format_structure(self, structure):
        """Custom output formatting for Rust"""
        lines = []

        # Use statements
        imports = structure.get('imports', [])
        if imports:
            lines.append(f"\nUse statements ({len(imports)}):")
            for item in imports[:10]:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}")

        # Structs
        structs = structure.get('structs', [])
        if structs:
            lines.append(f"\nStructs ({len(structs)}):")
            for item in structs:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}")

        # Functions
        functions = structure.get('functions', [])
        if functions:
            lines.append(f"\nFunctions ({len(functions)}):")
            for item in functions:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  fn {item['name']}()")

        return lines
```

#### Tree-Sitter Node Types

Each language has its own node types. Find them by exploring:

```python
from tree_sitter_languages import get_parser

parser = get_parser('rust')
tree = parser.parse(b'fn main() {}')

# Explore node types
def print_tree(node, indent=0):
    print("  " * indent + node.type)
    for child in node.children:
        print_tree(child, indent + 1)

print_tree(tree.root_node)
```

**Common node type patterns:**
- **Rust**: `function_item`, `struct_item`, `enum_item`, `impl_item`, `use_declaration`
- **C#**: `class_declaration`, `method_declaration`, `interface_declaration`, `using_directive`
- **Go**: `function_declaration`, `type_declaration`, `import_declaration`
- **Java**: `class_declaration`, `method_declaration`, `import_declaration`
- **TypeScript**: `function_declaration`, `class_declaration`, `interface_declaration`

#### Helper Methods from TreeSitterAnalyzer

```python
# Extract all nodes of a type
results = self._extract_nodes('function_item', name_field='name')

# Extract with custom text (for imports)
imports = self._extract_nodes('use_declaration', use_text=True)

# Access the parse tree directly
if self.tree:
    cursor = self.tree.walk()
    # Walk the tree yourself for complex logic
```

#### Example: Adding Go Support (15 minutes!)

```python
from reveal.analyzers.treesitter_base import TreeSitterAnalyzer
from reveal.registry import register

@register(['.go'], name='Go', icon='🐹')
class GoAnalyzer(TreeSitterAnalyzer):
    """Go language analyzer using tree-sitter"""

    language_name = 'go'

    def __init__(self, lines, **kwargs):
        self.node_type_map = {
            'function': 'function_declaration',
            'struct': 'type_declaration',  # Go types
            'import': 'import_declaration',
        }
        super().__init__(lines, **kwargs)

    def extract_custom(self):
        """Extract Go-specific items"""
        return {
            'interfaces': self._extract_nodes('interface_type', name_field='name'),
            'methods': self._extract_nodes('method_declaration', name_field='name'),
        }
```

**That's it!** Go support in ~20 lines of code.

#### Available Languages (50+)

Tree-sitter supports: Rust, C#, Go, Java, JavaScript, TypeScript, Python, C, C++, Ruby, PHP, Swift, Kotlin, Scala, Haskell, OCaml, Bash, Lua, R, HTML, CSS, and many more!

Check available languages:
```python
from reveal.analyzers.treesitter_base import TreeSitterAnalyzer

analyzer = TreeSitterAnalyzer([], language_name='dummy')
print(analyzer.get_supported_languages())
```

#### Graceful Degradation

Tree-sitter is **optional**. If not installed, files fall back to text analyzer:

```python
# In your analyzer
if not TREE_SITTER_AVAILABLE:
    return {
        'error': 'tree-sitter not installed',
        'install': 'pip install reveal-cli[treesitter]'
    }
```

Users without tree-sitter can still use reveal, just without advanced language analysis.

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
