---
title: Reveal Scaffolding System
category: guide
---
# Reveal Scaffolding System

**Generate production-ready components in seconds**

The scaffolding system generates complete, tested code for new reveal components:
- **Adapters**: URI protocol handlers (e.g., `github://`, `docker://`)
- **Analyzers**: Language parsers (e.g., `.kt`, `.ex`)
- **Rules**: Quality checks (e.g., `C999`, `X001`)

## Quick Start

### Scaffold an Adapter

```bash
reveal scaffold adapter github github://
```

Creates:
- `reveal/adapters/github.py` - Adapter implementation
- `tests/test_github_adapter.py` - 17 comprehensive tests
- `reveal/docs/GITHUB_ADAPTER_GUIDE.md` - Documentation

**Time saved**: 2-4 hours → 30 minutes

### Scaffold an Analyzer

```bash
reveal scaffold analyzer kotlin .kt
```

Creates:
- `reveal/analyzers/kotlin.py` - Tree-sitter analyzer
- `tests/test_kotlin_analyzer.py` - Tests
- `reveal/docs/KOTLIN_ANALYZER_GUIDE.md` - Documentation

**Time saved**: 1-3 hours → 20 minutes

### Scaffold a Quality Rule

```bash
reveal scaffold rule C999 "excessive-nesting" --category complexity
```

Creates:
- `reveal/rules/complexity/C999.py` - Rule implementation
- `tests/test_c999_rule.py` - Tests
- `reveal/docs/rules/C999.md` - Documentation

**Time saved**: 2-3 hours → 30 minutes

## Command Reference

### `reveal scaffold adapter`

Generate a new URI adapter.

```bash
reveal scaffold adapter <name> <uri> [--force]

Arguments:
  name        Adapter name (e.g., "github", "docker")
  uri         URI scheme (e.g., "github://", "docker://")

Options:
  --force     Overwrite existing files

Examples:
  reveal scaffold adapter github github://
  reveal scaffold adapter docker docker://
  reveal scaffold adapter npm npm://
```

**What you get**:
- `@register_adapter()` decorator setup
- `@register_renderer()` for output formatting
- `get_schema()` - AI agent integration (contract v1.0)
- `get_help()` - Examples, workflows, anti-patterns
- `get_structure()` - Structure extraction
- `get_element()` - Element extraction
- `get_metadata()` - Adapter metadata
- Renderer with 3 formats (text, json, grep)
- 17 comprehensive tests (all pass immediately)
- Documentation template

**Next steps**:
1. Implement TODOs in adapter file
2. Run tests: `pytest tests/test_<name>_adapter.py`
3. Test manually: `reveal <uri>://`
4. Document usage

### `reveal scaffold analyzer`

Generate a new language analyzer.

```bash
reveal scaffold analyzer <name> <extension> [--force]

Arguments:
  name        Analyzer name (e.g., "kotlin", "elixir")
  extension   File extension (e.g., ".kt", ".ex")

Options:
  --force     Overwrite existing files

Examples:
  reveal scaffold analyzer kotlin .kt
  reveal scaffold analyzer elixir .ex
  reveal scaffold analyzer dart .dart
```

**What you get**:
- `TreeSitterAnalyzer` subclass (3 lines for full language support!)
- `@register()` decorator with extension, name, icon
- Automatic structure extraction (functions, classes, imports)
- Tests for initialization, structure, registration
- Documentation template

**Requirements**:
- Tree-sitter grammar must exist: `pip install tree-sitter-<language>`
- If no grammar exists, implement custom `FileAnalyzer` subclass

**Next steps**:
1. Install tree-sitter grammar
2. Add sample code to tests
3. Run tests: `pytest tests/test_<name>_analyzer.py`
4. Test manually: `reveal file<extension>`

### `reveal scaffold rule`

Generate a new quality rule.

```bash
reveal scaffold rule <code> <name> [--category <cat>] [--force]

Arguments:
  code        Rule code (e.g., "C999", "X001")
  name        Rule name (e.g., "excessive-nesting")

Options:
  --category  Rule category (default: "custom")
  --force     Overwrite existing files

Examples:
  reveal scaffold rule C999 "excessive-nesting" --category complexity
  reveal scaffold rule X001 "custom-pattern" --category custom
  reveal scaffold rule S999 "security-check" --category security
```

**What you get**:
- `BaseRule` subclass with all required attributes
- `check()` method skeleton with examples
- Configuration support via `.reveal.yaml`
- Tests for initialization, detection, configuration
- Documentation template with examples

**Rule prefixes**:
- `B` - Bugs (HIGH severity)
- `C` - Complexity (MEDIUM severity)
- `D` - Duplicates (MEDIUM severity)
- `E` - Errors/Style (LOW severity)
- `F` - Frontmatter/Format (MEDIUM severity)
- `I` - Imports (LOW severity)
- `M` - Maintainability (MEDIUM severity)
- `N` - Naming/Infrastructure (LOW severity)
- `S` - Security (HIGH severity)
- `V` - Versioning (MEDIUM severity)
- `X` - Custom (MEDIUM severity)

**Next steps**:
1. Implement detection logic in rule file
2. Add test cases
3. Run tests: `pytest tests/test_<code>_rule.py`
4. Test manually: `reveal <file> --check --select=<prefix>`

## Template Structure

### Adapter Template

```python
@register_adapter('<scheme>')
class <Name>Adapter(ResourceAdapter):
    """Adapter for <scheme>:// URIs."""

    def get_schema(self) -> Dict[str, Any]:
        """AI agent integration (contract v1.0)"""

    def get_help(self) -> Dict[str, Any]:
        """Usage examples and workflows"""

    def get_structure(self) -> Dict[str, Any]:
        """Extract structure from resource"""

    def get_element(self, element_id: str) -> Optional[Dict[str, Any]]:
        """Extract specific element"""

    def get_metadata(self) -> Dict[str, Any]:
        """Resource metadata"""

@register_renderer('<scheme>')
class <Name>Renderer:
    """Render adapter results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render in text/json/grep format"""
```

### Analyzer Template

```python
@register('<extension>', name='<Name>', icon='<emoji>')
class <Name>Analyzer(TreeSitterAnalyzer):
    """<Name> file analyzer."""
    language = '<language>'
```

**That's it!** Full language support in 3 lines.

### Rule Template

```python
class <CODE>(BaseRule):
    """<Name>."""

    code = "<CODE>"
    message = "<name>"
    category = RulePrefix.<PREFIX>
    severity = Severity.<SEVERITY>
    file_patterns = ['*']  # or ['*.py'], etc.
    version = "1.0.0"

    DEFAULT_THRESHOLD = 10  # Configurable

    def check(self, file_path: str, structure: dict, content: str) -> List[Detection]:
        """Detect pattern violations."""
        detections = []
        # Implementation here
        return detections
```

## Integration with Reveal

### Testing

All scaffolded components include comprehensive tests:

```bash
# Run specific component tests
pytest tests/test_<name>_adapter.py -v
pytest tests/test_<name>_analyzer.py -v
pytest tests/test_<code>_rule.py -v

# Run all tests
pytest tests/
```

### Manual Testing

```bash
# Test adapter
reveal <scheme>://resource
reveal <scheme>://resource --format=json
reveal <scheme>://resource element_id

# Test analyzer
reveal file<extension>
reveal file<extension> --outline
reveal file<extension> function_name

# Test rule
reveal file --check
reveal file --check --select=<PREFIX>
```

## Best Practices

### Adapters

1. **Start with schema**: Define what your adapter can do
2. **Follow URI patterns**: Use standard URI query parameters
3. **Test early**: The 17 generated tests should all pass
4. **Document examples**: Add real-world usage to get_help()

### Analyzers

1. **Check tree-sitter availability**: Install grammar first
2. **Test with real code**: Add sample files to tests
3. **Customize if needed**: Override `get_structure()` for special cases
4. **Update icon**: Choose appropriate emoji for language

### Rules

1. **Clear detection logic**: Make violations obvious
2. **Helpful suggestions**: Include fix recommendations
3. **Configurable thresholds**: Use `get_threshold()` for flexibility
4. **Good test cases**: Cover passing and failing scenarios

## Overwriting Files

By default, scaffolding will not overwrite existing files:

```bash
$ reveal scaffold adapter github github://
Error: Files already exist (use --force to overwrite)
Existing files: reveal/adapters/github.py, ...
```

Use `--force` to overwrite:

```bash
$ reveal scaffold adapter github github:// --force
✓ Created adapter scaffolding for 'github'
```

## Contributing

After scaffolding and implementing your component:

1. **Run tests**: `pytest tests/ -v`
2. **Check quality**: `reveal . --check`
3. **Update docs**: Complete the generated documentation
4. **Submit PR**: Include tests, docs, and examples

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for full guidelines.

## Architecture

The scaffolding system:
- Lives in `reveal/cli/scaffold/`
- Uses templates from `reveal/templates/`
- Integrates with CLI via `reveal/main.py`
- Generates to standard locations:
  - Adapters: `reveal/adapters/`
  - Analyzers: `reveal/analyzers/`
  - Rules: `reveal/rules/<category>/`
  - Tests: `tests/`
  - Docs: `reveal/docs/`

## Impact

**Before scaffolding**:
- New adapter: 2-4 hours
- New analyzer: 1-3 hours
- New rule: 2-3 hours
- Total barrier: High expertise required

**After scaffolding**:
- New adapter: 30 minutes
- New analyzer: 20 minutes
- New rule: 30 minutes
- Total barrier: Fill in TODOs

**Result**: 10x faster component authoring, community contribution unlocked.

## Examples

See the demo adapter created by scaffolding:

```bash
# Generate demo adapter
reveal scaffold adapter demo demo://

# Test it
pytest tests/test_demo_adapter.py  # 17/17 pass
reveal demo://                      # Works immediately

# Read the code
reveal reveal/adapters/demo.py
```

All scaffolded components follow the same high-quality pattern.

## Support

- **Questions**: Open an issue on GitHub
- **Bugs**: Report with scaffold command and error
- **Features**: Suggest template improvements

---

**Scaffolding system**: Reducing barrier to entry, enabling community growth.

## See Also

- [CLI_INTEGRATION_GUIDE.md](CLI_INTEGRATION_GUIDE.md) - Wiring commands into the CLI
- [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) - Comprehensive adapter creation guide
