# Reveal Adapter Authoring Guide

**For Extension/Plugin Authors**: How to create adapters with excellent help documentation

---

## Quick Start

### Minimal Adapter

```python
from reveal.adapters.base import ResourceAdapter, register_adapter

@register_adapter('myscheme')
class MyAdapter(ResourceAdapter):
    """Adapter for myscheme:// URIs.

    Examples:
        myscheme://resource        # Access a resource
        myscheme://resource/item   # Access specific item
    """

    def __init__(self, resource: str, item: str = None):
        self.resource = resource
        self.item = item

    def get_structure(self, **kwargs):
        """Return structure of the resource."""
        return {
            'type': 'myscheme',
            'resource': self.resource,
            'items': ['item1', 'item2', 'item3']
        }

    def get_element(self, element_name: str, **kwargs):
        """Get specific element by name."""
        if element_name == 'item1':
            return {'name': 'item1', 'data': '...'}
        return None

    @staticmethod
    def get_help():
        """Get help documentation for this adapter."""
        return {
            'name': 'myscheme',
            'description': 'Short one-line description of what this does',
            'syntax': 'myscheme://<resource>[/<item>]',
            'examples': [
                {
                    'uri': 'myscheme://config',
                    'description': 'Access configuration'
                }
            ]
        }
```

---

## Help Documentation Schema

### Required Fields

```python
{
    'name': str,           # Adapter scheme name (e.g., 'python', 'ast')
    'description': str,    # One-line summary (< 80 chars)
}
```

### Recommended Fields

```python
{
    'syntax': str,                    # Usage pattern: 'scheme://<pattern>'
    'examples': List[Dict],           # Example URIs with descriptions
    'notes': List[str],               # Important notes, gotchas, limitations
    'see_also': List[str],            # Related adapters, tools, documentation
}
```

### Optional Fields (for advanced adapters)

```python
{
    'operators': Dict[str, str],      # Query operators (ast:// adapter)
    'filters': Dict[str, str],        # Available filters (ast:// adapter)
    'elements': Dict[str, str],       # Available elements (python:// adapter)
    'features': List[str],            # Feature list
    'use_cases': List[str],           # Common use cases
    'coming_soon': List[str],         # Planned features
    'output_formats': List[str],      # Supported output formats
}
```

---

## Best Practices

### 1. Multi-Shot Examples (CRITICAL for LLMs)

❌ **Bad: Just show commands**
```python
'examples': [
    {'uri': 'myscheme://resource', 'description': 'Get resource'}
]
```

✅ **Good: Show input AND expected output**
```python
'examples': [
    {
        'uri': 'myscheme://resource',
        'description': 'Get resource metadata',
        'example_input': 'myscheme://database',
        'example_output': {
            'name': 'database',
            'tables': 10,
            'size': '1.2GB'
        }
    }
]
```

💡 **Best: Create a comprehensive guide (see PYTHON_ADAPTER_GUIDE.md)**

Include:
- Problem statement
- Command
- Full output example
- Interpretation
- Next steps

### 2. Progressive Disclosure

Structure help from simple to complex:

```python
'examples': [
    # Basic usage
    {'uri': 'scheme://simple', 'description': 'Basic usage'},

    # With parameters
    {'uri': 'scheme://resource?param=value', 'description': 'With parameters'},

    # Advanced filtering
    {'uri': 'scheme://resource?param1=X&param2>50', 'description': 'Complex filtering'},

    # Output formats
    {'uri': 'scheme://resource --format=json', 'description': 'JSON output for scripting'}
]
```

### 3. Clear Breadcrumbs

Use `see_also` to guide users:

```python
'see_also': [
    'reveal help://myscheme-guide - Comprehensive guide with examples',
    'reveal help://related - Related adapter',
    'reveal --agent-help - General agent patterns'
]
```

### 4. Document Gotchas

```python
'notes': [
    'This adapter requires X to be installed',
    'Quote URIs with > or < operators: \'scheme://path?val>50\'',
    'Scans recursively by default - use --depth to limit',
    'Use --format=json for programmatic filtering'
]
```

---

## Complete Example: ast:// Adapter

```python
@staticmethod
def get_help() -> Dict[str, Any]:
    """Get help documentation for ast:// adapter."""
    return {
        # Required
        'name': 'ast',
        'description': 'Query code as an AST database - find functions by complexity, size, type',

        # Syntax
        'syntax': 'ast://<path>?<filter1>&<filter2>&...',

        # Operators (for query-based adapters)
        'operators': {
            '>': 'Greater than',
            '<': 'Less than',
            '>=': 'Greater than or equal',
            '<=': 'Less than or equal',
            '==': 'Equal to'
        },

        # Filters (what can be queried)
        'filters': {
            'lines': 'Number of lines in function/class (e.g., lines>50)',
            'complexity': 'Cyclomatic complexity score 1-10 (e.g., complexity>5)',
            'type': 'Element type: function, class, method (e.g., type=function)',
            'name': 'Element name pattern with wildcards (e.g., name=test_*, name=*helper*)'
        },

        # Examples (progressive: simple → complex)
        'examples': [
            {'uri': 'ast://./src', 'description': 'All code structure in src directory'},
            {'uri': 'ast://app.py?lines>50', 'description': 'Functions with more than 50 lines'},
            {'uri': 'ast://./src?complexity>10', 'description': 'Complex functions'},
            {'uri': 'ast://.?name=test_*', 'description': 'All test functions'},
            {'uri': 'ast://src/?name=*helper*', 'description': 'Functions containing "helper"'},
            {'uri': 'ast://.?lines>30&complexity<5', 'description': 'Long but simple functions'},
            {'uri': "ast://./src?complexity>5 --format=json", 'description': 'JSON output'}
        ],

        # Important notes
        'notes': [
            'Quote URIs with > or < operators: \'ast://path?lines>50\'',
            'Scans all code files in directory recursively',
            'Supports Python, JS, TS, Rust, Go, and 50+ languages via tree-sitter',
            'Use --format=json for programmatic filtering with jq'
        ],

        # Supported output formats
        'output_formats': ['text', 'json', 'grep'],

        # Related resources
        'see_also': [
            'reveal help://env - Environment variable adapter',
            'reveal --agent-help - Agent usage patterns',
            'reveal file.py --check - Code quality checks'
        ]
    }
```

---

## Creating Comprehensive Guides

For complex adapters, create a separate markdown guide (like `PYTHON_ADAPTER_GUIDE.md`):

### Guide Template Structure

```markdown
# Adapter Name - Complete Guide

## Overview
[What this adapter does, why it exists]

## Quick Start
[Copy-paste examples]

## Features at a Glance
[Table of features]

## Problem This Solves
[Real-world scenario]

## Detailed Feature Documentation

### Feature 1: Name
**Problem Solved**: [What problem]

#### Examples

**Example 1: Scenario Name**
\`\`\`bash
$ command here
{
  "output": "here"
}
\`\`\`

**Interpretation**: [What this means]
**Next Steps**: [What to do with this information]

## Real-World Workflows

### Workflow 1: Name
\`\`\`bash
# Step 1
reveal adapter://step1

# Step 2 (if X found)
reveal adapter://step2

# Step 3
reveal adapter://step3
\`\`\`

## Integration Patterns

### With CI/CD
[Example integration]

### With LLM Agents
[Example agent prompts]

## Multi-Shot Prompting Examples (for LLMs)
[Show the pattern: Problem → Command → Output → Interpretation → Action]

## Troubleshooting

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| ... | ... | ... |

## Future Enhancements
[Planned features]
```

Then link it in the help system:

```python
# In help.py STATIC_HELP dict
'myscheme-guide': 'adapters/MYSCHEME_GUIDE.md'
```

And reference it in your adapter's get_help():

```python
'see_also': [
    'reveal help://myscheme-guide - Comprehensive guide with multi-shot examples',
    ...
]
```

---

## Testing Your Help

### 1. Check help appears in listing
```bash
reveal help://
# Should show your adapter
```

### 2. Check inline help
```bash
reveal help://myscheme
# Should show your get_help() content
```

### 3. Check guide (if created)
```bash
reveal help://myscheme-guide
# Should show your comprehensive guide
```

### 4. Verify examples work
```bash
# Run each example from your help documentation
# Verify output matches what you described
```

---

## Common Mistakes

### Mistake 1: No examples
```python
❌ 'examples': []
✅ 'examples': [{'uri': '...', 'description': '...'}]
```

### Mistake 2: Vague descriptions
```python
❌ 'description': 'Does stuff with things'
✅ 'description': 'Query code as AST database - find functions by complexity'
```

### Mistake 3: No breadcrumbs
```python
❌ No 'see_also' field
✅ 'see_also': ['reveal help://guide', 'reveal help://related']
```

### Mistake 4: Complex-first examples
```python
❌ Start with: 'ast://.?name=*foo*&complexity>8&lines<50'
✅ Start with: 'ast://file.py'
```

### Mistake 5: No comprehensive guide for complex adapters
```python
❌ Only inline help for 20+ features
✅ Create ADAPTER_GUIDE.md with multi-shot examples
```

---

## Checklist for Good Help

- [ ] Implemented `get_help()` staticmethod
- [ ] Included name and description (required)
- [ ] Added syntax string showing URI pattern
- [ ] Provided 3-7 examples (simple → complex)
- [ ] Added notes for gotchas/limitations
- [ ] Included see_also breadcrumbs
- [ ] If complex: Created comprehensive guide
- [ ] If has guide: Linked in help.py STATIC_HELP
- [ ] If has guide: Referenced in get_help() see_also
- [ ] Tested all examples work as documented
- [ ] Included multi-shot examples (input + output) for LLMs

---

## Resources

### Reference Implementation (Start Here!)

- **🆕 reveal:// adapter**: `reveal/adapters/reveal.py` - Complete working example showing:
  - How to create non-file adapters
  - How to write validation rules
  - How to integrate with --check flag
  - **Guide**: `reveal/REVEAL_ADAPTER_GUIDE.md` or `reveal help://reveal`

### Other Examples

- **🆕 ssl:// adapter**: `reveal/adapters/ssl/` - Network-based adapter showing:
  - How to fetch external data (SSL certificates)
  - How to implement health checks (--check)
  - Clean separation: `certificate.py` (fetching), `adapter.py` (API), `renderer.py` (display)
  - YAML-based help: `reveal/adapters/help_data/ssl.yaml`
- **Example adapters**: `reveal/adapters/python.py`, `ast.py`, `env.py`
- **Comprehensive guide example**: `reveal/docs/PYTHON_ADAPTER_GUIDE.md`
- **Help system**: `reveal/adapters/help.py`
- **Base adapter**: `reveal/adapters/base.py`
- **Anti-patterns guide**: `reveal/AGENT_HELP.md`

---

## Questions?

- Check existing adapters for patterns
- Read PYTHON_ADAPTER_GUIDE.md for multi-shot example format
- Test with `reveal help://your-adapter`
- Dogfood your own adapter before releasing!

## See Also

- [PYTHON_ADAPTER_GUIDE.md](PYTHON_ADAPTER_GUIDE.md) - Python adapter examples
- [ANALYZER_PATTERNS.md](ANALYZER_PATTERNS.md) - Analysis patterns
- [AGENT_HELP.md](AGENT_HELP.md) - Mistakes to avoid
- [HELP_SYSTEM_GUIDE.md](HELP_SYSTEM_GUIDE.md) - Help system integration
- [README.md](README.md) - Documentation hub
