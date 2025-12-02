# Contributing to reveal

Add new file types in 10-50 lines. Explore this codebase with reveal itself.

---

## Exploring the Codebase

**Use reveal to understand reveal:**

```bash
# Overall structure
reveal reveal/

# Core components
reveal reveal/base.py --outline        # Registration system
reveal reveal/main.py --outline        # CLI
reveal reveal/treesitter.py --outline  # Tree-sitter integration

# Analyzers
reveal reveal/analyzers/python.py     # Tree-sitter (3 lines!)
reveal reveal/analyzers/nginx.py      # Custom logic example

# Adapters (URI support)
reveal reveal/adapters/env.py          # env:// adapter
```

---

## Architecture Overview

```
reveal <path or URI>
   │
   ├─ File? → Analyzer System
   │           ├─ base.py (registry + @register decorator)
   │           ├─ analyzers/* (18 built-in file types)
   │           └─ treesitter.py (50+ languages via tree-sitter)
   │
   └─ URI?  → Adapter System
               └─ adapters/* (env://, more coming)
```

**Key components:**

| File | Lines | Purpose |
|------|-------|---------|
| `base.py` | ~380 | Analyzer registration, base classes, @register decorator |
| `main.py` | ~920 | CLI, output formatting, orchestration |
| `treesitter.py` | ~345 | Tree-sitter integration (50+ languages) |
| `analyzers/*` | 10-300 | File type handlers (18 built-in) |
| `adapters/*` | ~200 | URI adapters (env://, more coming) |

**Total: ~3,400 lines**

---

## Adding File Types

### Path 1: Tree-Sitter Languages (10 lines)

For programming languages supported by tree-sitter:

**1. Create analyzer:**

```python
# reveal/analyzers/kotlin.py
from ..base import register
from ..treesitter import TreeSitterAnalyzer

@register('.kt', name='Kotlin', icon='🟣')
class KotlinAnalyzer(TreeSitterAnalyzer):
    language = 'kotlin'
```

**2. Register:**

```python
# reveal/analyzers/__init__.py
from .kotlin import KotlinAnalyzer
```

**Done!** Full support for:
- Function/class extraction
- Import detection
- Element access by name
- Accurate line numbers

**Check supported languages:**
```bash
python -c "from tree_sitter_languages import get_language; get_language('kotlin')"
```

**Supported:** Python, Rust, Go, JS, TS, C, C++, Java, C#, PHP, Ruby, Swift, Kotlin, + 40 more

### Path 2: Custom Analyzers (50-200 lines)

For structured files without tree-sitter support:

```python
# reveal/analyzers/toml.py
from ..base import FileAnalyzer, register

@register('.toml', name='TOML', icon='⚙️')
class TomlAnalyzer(FileAnalyzer):
    def get_structure(self):
        """Extract structure.

        Return format:
        {
            'sections': [{'line': int, 'name': str, ...}, ...],
            'keys': [...],
            # ... other elements
        }
        """
        import toml
        try:
            data = toml.loads(self.content)
            sections = []
            for i, line in enumerate(self.lines, 1):
                if line.strip().startswith('['):
                    sections.append({
                        'line': i,
                        'name': line.strip().strip('[]')
                    })
            return {'sections': sections}
        except Exception as e:
            return {'error': str(e)}

    def extract_element(self, element_type, name):
        """Extract specific element.

        Return format:
        {
            'lines': 'start-end',
            'content': 'actual code',
            'name': 'element name'
        }
        """
        # Find element and return lines
        for i, line in enumerate(self.lines, 1):
            if name in line:
                # Extract surrounding context
                start = max(1, i - 2)
                end = min(len(self.lines), i + 10)
                return {
                    'lines': f'{start}-{end}',
                    'content': '\n'.join(self.lines[start-1:end]),
                    'name': name
                }
        return None
```

**Required methods:**
- `get_structure()` → Dict with structure elements
- `extract_element(element_type, name)` → Dict with code

**Structure format rules:**
- All elements MUST have `'line': int` (1-indexed, not 0!)
- All elements MUST have `'name': str`
- Group by type: `'functions': [...]`, `'classes': [...]`, etc.
- Return `{'error': str}` for parse failures

**Extract format rules:**
- Return `{'lines': 'start-end', 'content': str, 'name': str}`
- Return `None` if element not found

---

## Key Design Patterns

### 1. Decorator Registration

```python
ANALYZER_REGISTRY = {}

def register(extension, name, icon='📄'):
    def decorator(cls):
        ANALYZER_REGISTRY[extension] = cls
        cls.extension = extension
        cls.display_name = name
        cls.icon = icon
        return cls
    return decorator
```

**Benefits:** Zero-config, auto-discovery at import time

### 2. Progressive Inheritance

```
FileAnalyzer (base class)
    ├─ TreeSitterAnalyzer (tree-sitter languages)
    │  └─ PythonAnalyzer, RustAnalyzer, etc. (3 lines each)
    └─ Custom analyzers (MarkdownAnalyzer, etc.)
```

### 3. Consistent Output

All analyzers output `filename:line` format:
```
app.py:15   load_config(path: str) -> Dict
app.py:28   setup_logging() -> None
```

Works with: vim, git blame, grep, awk, sed

---

## Adding URI Adapters

URI adapters let reveal explore non-file resources:

```python
# reveal/adapters/postgres.py
from ..base import URIAdapter, register_adapter

@register_adapter('postgres')
class PostgresAdapter(URIAdapter):
    def can_handle(self, uri: str) -> bool:
        return uri.startswith('postgres://')

    def get_structure(self, uri: str) -> dict:
        # Connect to postgres, list tables/schemas
        # Return: {'tables': [...], 'schemas': [...]}
        pass

    def extract_element(self, uri: str, element: str) -> dict:
        # Get table schema or query specific table
        pass
```

**Examples:** `env://`, `postgres://`, `docker://`, `https://api.example.com`

---

## Testing

### Manual Testing

```bash
# Structure extraction
reveal test.kt

# Element extraction
reveal test.kt MyClass
reveal test.kt myFunction

# Output formats
reveal test.kt --format=json
reveal test.kt --format=grep

# Metadata
reveal test.kt --meta
```

### Unit Tests

```python
# tests/test_kotlin_analyzer.py
import pytest
from reveal.analyzers.kotlin import KotlinAnalyzer

def test_kotlin_structure():
    content = """
    fun main() {
        println("Hello")
    }

    class MyClass {
        fun method() {}
    }
    """
    analyzer = KotlinAnalyzer('/tmp/test.kt', content)
    structure = analyzer.get_structure()

    assert 'functions' in structure
    assert len(structure['functions']) == 1
    assert structure['functions'][0]['name'] == 'main'

    assert 'classes' in structure
    assert len(structure['classes']) == 1
    assert structure['classes'][0]['name'] == 'MyClass'
```

### Integration Tests

```bash
# Create test samples
mkdir -p tests/samples
echo 'fun main() {}' > tests/samples/test.kt

# Test with reveal
reveal tests/samples/test.kt
reveal tests/samples/ --depth=2
```

---

## Common Pitfalls

### ❌ Zero-indexed line numbers
```python
# BAD - editors use 1-indexed
{'line': 0, 'name': 'main'}

# GOOD - matches vim/editors
{'line': 1, 'name': 'main'}
```

### ❌ Not handling parse errors
```python
# BAD - crashes on invalid files
data = json.loads(content)

# GOOD - graceful degradation
try:
    data = json.loads(content)
except json.JSONDecodeError:
    return {'error': 'Invalid JSON'}
```

### ❌ Missing required fields
```python
# BAD - no line number
{'name': 'main'}

# GOOD - includes line
{'line': 15, 'name': 'main'}
```

---

## Examples to Study

**Simplest (tree-sitter):**
- `analyzers/python.py` (3 lines)
- `analyzers/rust.py` (3 lines)
- `analyzers/go.py` (3 lines)

**Custom logic:**
- `analyzers/markdown.py` (312 lines) - Complex heading extraction
- `analyzers/nginx.py` (186 lines) - Domain-specific parsing
- `analyzers/yaml_json.py` (95 lines) - Structured data

**Adapters:**
- `adapters/env.py` (200 lines) - Environment variables

---

## Submitting Changes

1. **Fork & clone:**
   ```bash
   gh repo fork scottsen/reveal --clone
   cd reveal
   ```

2. **Install dev dependencies:**
   ```bash
   pip install -e .
   pip install pytest
   ```

3. **Add your analyzer:**
   ```bash
   # Create analyzer file
   # Add import to __init__.py
   # Test manually
   ```

4. **Test:**
   ```bash
   pytest tests/
   reveal tests/samples/
   ```

5. **Commit & PR:**
   ```bash
   git checkout -b add-kotlin-support
   git add reveal/analyzers/kotlin.py
   git commit -m "feat: add Kotlin analyzer via tree-sitter"
   gh pr create --title "Add Kotlin support"
   ```

**PR checklist:**
- [ ] Analyzer registered in `__init__.py`
- [ ] Manually tested with sample file
- [ ] Follows 1-indexed line numbers
- [ ] Includes `name` field in all elements
- [ ] Handles parse errors gracefully

---

## Architecture Decisions

**Why Python?** Cross-platform, rich parsing ecosystem, fast enough

**Why Tree-Sitter?** Battle-tested, 50+ languages, accurate parsing

**Why decorator registration?** Zero config, auto-discovery, minimal boilerplate

**Why progressive disclosure?** Token efficiency for AI agents (50 tokens vs 7,500)

---

## Resources

- **Code:** https://github.com/scottsen/reveal
- **Issues:** https://github.com/scottsen/reveal/issues
- **Discussions:** https://github.com/scottsen/reveal/discussions
- **Tree-sitter languages:** https://github.com/grantjenks/py-tree-sitter-languages

---

**Questions?** Open an issue or discussion. PRs welcome!
