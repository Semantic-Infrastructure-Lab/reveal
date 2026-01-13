# Contributing to reveal

Add new file types in 10-50 lines. Use reveal to explore reveal.

---

## Quick Start

```bash
# Clone and install
gh repo fork scottsen/reveal --clone
cd reveal
pip install -e .

# Explore the codebase with reveal itself
reveal reveal/                         # Overall structure
reveal reveal/base.py --outline        # Registration system
reveal reveal/analyzers/python.py      # Simplest example (3 lines!)

# Run tests
pip install pytest
pytest tests/
```

---

## Project Structure

This repository contains only the public-facing open source project:

```
reveal/                    # This repository (public)
├── reveal/               # Core library
│   ├── analyzers/       # File type handlers
│   ├── adapters/        # URI adapters
│   ├── rules/           # Quality checks
│   └── base.py          # Registration system
├── tests/               # Test suite
├── docs/                # Documentation
└── README.md            # Public documentation
```

**For maintainers:** Internal planning, research, and development artifacts live in `../internal-docs/` (outside this repository). This keeps the public repo clean and focused on the OSS project.

---

## Ways to Contribute

### 1. Add File Type Analyzers (Most Impactful)

Two paths depending on language support:

**Tree-sitter languages (10 lines):**
```python
# reveal/analyzers/lua.py
from ..base import register
from ..treesitter import TreeSitterAnalyzer

@register('.lua', name='Lua', icon='🌙')
class LuaAnalyzer(TreeSitterAnalyzer):
    language = 'lua'
```

**Custom analyzers (50-200 lines):**
```python
# reveal/analyzers/ini.py
from ..base import FileAnalyzer, register

@register('.ini', name='INI', icon='📋')
class IniAnalyzer(FileAnalyzer):
    def get_structure(self):
        # Return: {'sections': [{'line': int, 'name': str}, ...]}
        pass

    def extract_element(self, element_type, name):
        # Return: {'lines': 'start-end', 'content': str, 'name': str}
        pass
```

**Check tree-sitter support:**
```bash
python -c "from tree_sitter_languages import get_language; get_language('lua')"
```

### 2. Add URI Adapters

Extend reveal to explore non-file resources:

```python
# reveal/adapters/postgres.py
from .base import ResourceAdapter, register_adapter

@register_adapter('postgres')
class PostgresAdapter(ResourceAdapter):
    def get_structure(self, **kwargs):
        # Return: {'tables': [...], 'schemas': [...]}
        pass
```

### 3. Other Contributions

- **Bug fixes** - See open issues
- **Performance** - Profile and optimize
- **Documentation** - Improve guides, add examples
- **Pattern detection** - Add new `--check` rules

---

## Architecture

```
reveal <path or URI>
   │
   ├─ File? → Analyzer System
   │           ├─ base.py (registry + @register decorator)
   │           ├─ analyzers/* (18 built-in file types)
   │           └─ treesitter.py (50+ languages via tree-sitter)
   │
   └─ URI?  → Adapter System
               └─ adapters/* (env://, ast://, python://, help://)
```

**Key files:**

| File | Purpose |
|------|---------|
| `base.py` | Analyzer registration, base classes |
| `main.py` | CLI, output formatting |
| `treesitter.py` | Tree-sitter integration |
| `analyzers/*` | File type handlers |
| `adapters/*` | URI adapters |

---

## Analyzer Requirements

### Structure Format

```python
def get_structure(self):
    return {
        'functions': [
            {'line': 15, 'name': 'main', 'signature': 'main()'},
            # line = 1-indexed (matches vim/editors)
            # name = required
        ],
        'classes': [...],
        # Group by element type
    }
```

### Extract Format

```python
def extract_element(self, element_type, name):
    return {
        'lines': '15-28',      # Range
        'content': '...',      # Actual code
        'name': 'main'         # Element name
    }
    # Return None if not found
```

### Common Pitfalls

```python
# ❌ Zero-indexed lines (editors use 1-indexed)
{'line': 0, 'name': 'main'}

# ✅ 1-indexed lines
{'line': 1, 'name': 'main'}

# ❌ No error handling
data = json.loads(content)

# ✅ Graceful degradation
try:
    data = json.loads(content)
except json.JSONDecodeError:
    return {'error': 'Invalid JSON'}
```

---

## Testing

```bash
# Manual testing
reveal test.kt                    # Structure
reveal test.kt MyClass            # Element extraction
reveal test.kt --format=json      # JSON output
reveal test.kt --check            # Pattern detection

# Unit tests
pytest tests/test_your_analyzer.py -v

# Full suite
pytest tests/
```

**Test template:**

```python
def test_lua_structure():
    from reveal.analyzers.lua import LuaAnalyzer

    content = "function greet() print('Hello') end"
    analyzer = LuaAnalyzer('/tmp/test.lua', content)
    structure = analyzer.get_structure()

    assert 'functions' in structure
    assert structure['functions'][0]['name'] == 'greet'
```

---

## Submitting Changes

1. **Create branch:** `git checkout -b add-lua-support`
2. **Add analyzer** in `reveal/analyzers/`
3. **Register** in `reveal/analyzers/__init__.py`
4. **Test** manually and with pytest
5. **Commit:** `git commit -m "feat: add Lua analyzer"`
6. **Submit PR:** `gh pr create`

**Commit style:** Conventional commits (`feat:`, `fix:`, `docs:`, `test:`)

**PR checklist:**
- [ ] Analyzer registered in `__init__.py`
- [ ] Uses 1-indexed line numbers
- [ ] Includes `name` field in all elements
- [ ] Handles parse errors gracefully
- [ ] Tests added (or manual testing documented)

---

## Code Style

- **Format:** `black reveal/` (100 char line length)
- **Lint:** `ruff check reveal/`
- **Types:** Use type hints for public APIs
- **Docstrings:** Google style
- **Comments:** Explain *why*, not *what*

---

## Examples to Study

**Simplest (tree-sitter):**
- `analyzers/python.py` - 3 lines
- `analyzers/rust.py` - 3 lines

**Custom logic:**
- `analyzers/markdown.py` - Complex heading extraction
- `analyzers/nginx.py` - Domain-specific parsing

**Adapters:**
- `adapters/env.py` - Environment variables
- `adapters/python.py` - Python runtime inspection

---

## Priority Areas

**Most wanted analyzers:**
- CSV/Excel (.csv, .xlsx)
- SQL (.sql)
- Terraform (.tf)
- Protocol Buffers (.proto)
- GraphQL (.graphql)

**Most wanted features:**
- Call graph analysis
- Dependency visualization
- More pattern detection rules

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Questions?** Open an issue or discussion. PRs welcome!
