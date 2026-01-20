# The Reveal Help System

**Purpose:** Understand how reveal's help system works
**Audience:** Users and contributors
**Version:** 0.30.0

---

## Overview

Reveal has a **three-tier help system** designed for different users and use cases:

1. **`--help`** - Traditional CLI reference (for humans typing commands)
2. **`--agent-help`** - AI agent reference (llms.txt standard)
3. **`help://`** - Progressive discovery system (explorable documentation)

---

## 1. Traditional CLI Help (`--help`)

**Purpose:** Quick reference for command-line flags and options

**Usage:**
```bash
reveal --help
```

**Audience:** Human users typing commands manually

**Content:** Standard argparse output showing:
- All available flags
- Positional arguments
- Basic examples
- File type support

**When to use:** Need to know what flags exist or basic command syntax

---

## 2. AI Agent Reference (`--agent-help`)

**Purpose:** Task-based patterns optimized for AI code assistants

**Usage:**
```bash
reveal --agent-help           # Quick reference (~2,200 tokens)
reveal --agent-help-full      # Complete guide (~12,000 tokens)
```

**Audience:** AI agents (Claude Code, Copilot, Cursor, etc.)

**Content:**
- Common tasks → reveal commands
- Concrete, working examples
- Real-world scenarios
- Quick reference card
- Troubleshooting patterns

**Philosophy:** "When you need to do X, use Y" (not "explore to discover")

**When to use:**
- AI agent needs to understand how to use reveal
- Want task-oriented examples
- Need patterns that actually work

**llms.txt Standard:** Follows the llms.txt convention for CLI tools (like /robots.txt for LLMs)

---

## 3. Progressive Discovery (`help://`)

**Purpose:** Explorable, runtime documentation system

**Usage:**
```bash
reveal help://                # List all topics
reveal help://ast             # Learn about ast:// adapter
reveal help://adapters        # Summary of all adapters
reveal help://agent           # Same as --agent-help (static guide)
```

**Audience:** Humans exploring capabilities, developers

**Content:**
- **Dynamic:** URI adapter documentation (auto-discovered)
- **Static:** Markdown guides (bundled files)
- **Generated:** Summaries and indexes

**Architecture:**
- **Source attribution** - Shows where help comes from
- **Token costs** - Estimates for AI agents
- **Categorization** - Organized by type (adapters, guides, best practices)
- **Progressive** - Start broad, drill down as needed

**When to use:**
- Want to explore what's available
- Need deep dive on specific feature
- Looking for examples and workflows
- Discovering new adapters

---

## How They Work Together

### For Humans:
```bash
# Quick CLI reference
reveal --help                    # What flags exist?

# Explore capabilities
reveal help://                   # What can reveal do?
reveal help://ast                # How does ast:// work?

# Learn best practices
reveal help://tricks             # Power user workflows
reveal help://anti-patterns      # Common mistakes
```

### For AI Agents:
```bash
# Bootstrap understanding
reveal --agent-help              # Get task-based patterns

# (AI agents typically don't explore help://)
# The --agent-help guide has all the patterns needed
```

---

## help:// System Architecture

### Directory Structure
```
reveal/docs/
├── AGENT_HELP.md                    # --agent-help content (complete reference)
├── RECIPES.md                       # help://recipes (task-based workflows)
├── MARKDOWN_GUIDE.md                # help://markdown
├── REVEAL_ADAPTER_GUIDE.md          # help://reveal-guide
├── PYTHON_ADAPTER_GUIDE.md          # help://python-guide
├── ADAPTER_AUTHORING_GUIDE.md       # help://adapter-authoring
└── ...
```

### Content Sources

**Dynamic Content** (Runtime Discovery):
- URI adapter documentation (`help://ast`, `help://python`, etc.)
- Generated from adapter `get_help()` methods
- Auto-updates when new adapters registered

**Static Content** (Markdown Files):
- AI agent guides (`help://agent`, `help://agent-full`)
- Feature guides (`help://python-guide`, `help://markdown`)
- Best practices (`help://tricks`, `help://anti-patterns`)
- Development (`help://adapter-authoring`)

**Generated Content**:
- `help://adapters` - Summary of all URI adapters
- `help://` - Main index with categorization

### Source Attribution

All help topics show where content comes from:

**For static guides:**
```markdown
<!-- Source: AGENT_HELP.md | Type: Static Guide | Access: reveal help://agent or --agent-help -->
```

**For adapters:**
```markdown
**Source:** ast.py adapter (dynamic)
**Type:** URI Adapter
**Access:** reveal help://ast
```

**For main index:**
```markdown
## 📦 DYNAMIC CONTENT (Runtime Discovery)
Source: Live adapter registry
Updates: Automatic when new adapters added

## 📄 STATIC GUIDES (Markdown Files)
Source: reveal/ and reveal/adapters/ directories
Location: Bundled with installation
```

---

## Adding New Help Content

### Adding a New URI Adapter

1. Create adapter with `get_help()` method:
```python
class MyAdapter(ResourceAdapter):
    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'my',
            'description': 'Does something cool',
            'syntax': 'my://<path>',
            'examples': [
                {'uri': 'my://example', 'description': 'Example usage'}
            ]
        }
```

2. Register adapter:
```python
register_adapter('my', MyAdapter)
```

3. **That's it!** `help://my` now works automatically

### Adding a New Static Guide

1. Create markdown file in `reveal/` directory:
```bash
touch reveal/MY_GUIDE.md
```

2. Add to `HelpAdapter.STATIC_HELP` mapping:
```python
STATIC_HELP = {
    # ... existing entries ...
    'my-guide': 'MY_GUIDE.md'
}
```

3. Update rendering categorization in `reveal/rendering/adapters/help.py`:
```python
# Add to appropriate category in _render_help_list_mode()
feature_guides = ['python-guide', 'markdown', 'reveal-guide', 'my-guide']
```

4. **Done!** `help://my-guide` now works

---

## Design Principles

### 1. Progressive Disclosure
Start broad, drill down as needed. Don't force users to load everything.

**Good:**
```bash
reveal help://              # List (500 tokens)
reveal help://ast           # Deep dive (250 tokens)
```

**Bad:**
```bash
reveal --show-all-help      # Everything at once (20,000 tokens)
```

### 2. Source Attribution
Always show where content comes from. No mystery meat.

### 3. Token Awareness
Show estimated token costs for AI agents. Help them make informed decisions.

### 4. Realistic Usage
**For AI agents:** Give patterns that work, not exploration hints
**For humans:** Make it explorable and discoverable

### 5. Self-Documenting
New adapters auto-appear in help://. No manual catalog updates needed.

### 6. Clear Separation
- **--help**: CLI flags (humans)
- **--agent-help**: Task patterns (AI agents)
- **help://**: Progressive discovery (both)

Each has a clear purpose. No overlap, no confusion.

---

## Examples of Good Help Design

### Example 1: ast:// Adapter Help

```python
@staticmethod
def get_help() -> Dict[str, Any]:
    return {
        'name': 'ast',
        'description': 'Query code as an AST database',
        'syntax': 'ast://<path>?<filter1>&<filter2>',
        'filters': {
            'complexity>N': 'Find functions with complexity > N',
            'lines>N': 'Find functions with > N lines',
            'name=pattern': 'Wildcard name matching'
        },
        'examples': [
            {
                'uri': 'ast://./src?complexity>10',
                'description': 'Find complex functions'
            }
        ],
        'try_now': [
            "reveal 'ast://.?complexity>5'",
            "reveal 'ast://src/?name=test_*'"
        ]
    }
```

**Why this is good:**
- Clear syntax documentation
- Filter reference table
- Working examples
- Try-now commands (copy-paste ready)

### Example 2: Agent Help Structure

```markdown
## Task: "Find where X is implemented"

**Pattern:**
```bash
# Find functions by name pattern
reveal 'ast://./src?name=*authenticate*'
```

**Why this works:** AST queries don't require reading files.
```

**Why this is good:**
- Task-oriented (not feature-oriented)
- Concrete command
- Explanation of why it works

---

## Troubleshooting

**Q: My new adapter doesn't appear in `help://`**

A: Check:
1. Adapter registered with `register_adapter()`?
2. Adapter has `get_help()` static method?
3. `get_help()` returns dict with 'name' and 'description'?

**Q: Static guide not showing up**

A: Check:
1. File exists in `reveal/` directory?
2. Added to `HelpAdapter.STATIC_HELP` mapping?
3. Topic name matches mapping key?

**Q: Help rendering looks wrong**

A: Check `reveal/rendering/adapters/help.py` - may need to update `_render_help_list_mode()` categorization

**Q: Token costs seem off**

A: Update estimates in `_render_help_list_mode()` token_estimate dictionaries

---

## Future Enhancements

**Possible improvements:**
- Search within help (`help://search?q=complexity`)
- Version-specific help (`help://ast@v0.20`)
- Language-specific examples (`help://ast?lang=python`)
- Interactive examples (`help://ast --try`)
- Help diffing (`help://diff?from=v0.20&to=v0.23`)

**If you're implementing one of these:**
1. Update this guide
2. Add to CHANGELOG.md
3. Update ROADMAP.md if major feature

---

## Related Documentation

- **Implementation:** `reveal/adapters/help.py` (adapter logic)
- **Rendering:** `reveal/rendering/adapters/help.py` (display logic)
- **Content Files:** `reveal/*.md` (static guides)
- **Agent Guide:** `reveal/docs/AGENT_HELP.md` (AI agent reference)

## See Also

- [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) - Create help-enabled adapters
- [AGENT_HELP.md](AGENT_HELP.md) - AI agent reference guide
- [RECIPES.md](RECIPES.md) - Task-based workflows
- [README.md](README.md) - Documentation hub

---

**Last updated:** 2026-01-19
**Version:** 0.39.0
