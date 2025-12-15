# Reveal Enhancement Proposals

> Making reveal more awesome through carefully considered improvements

**Date:** 2025-12-09
**Author:** TIA + Scott (SIL)
**Version:** v0.18.0 baseline

---

## Overview

This document proposes enhancements to make reveal even more powerful. Each proposal includes:
- **Problem:** What user pain point does this address?
- **Solution:** Concrete implementation approach
- **Value:** Why this matters
- **Complexity:** Estimated effort

---

## Priority 1: High Value, Medium Effort

### 1.1 `reveal diff://` - Compare Two Files/URIs

**Problem:** No easy way to compare structures across files, environments, or time.

**Current workaround:**
```bash
reveal file1.py --format=json > /tmp/a.json
reveal file2.py --format=json > /tmp/b.json
diff /tmp/a.json /tmp/b.json  # Ugly, hard to read
```

**Proposed:**
```bash
# Compare two files
reveal diff://app.py:backup/app.py

# Compare with git revision
reveal diff://app.py:HEAD~1

# Compare environments
reveal diff://python://venv:python://system

# Compare database schemas
reveal diff://mysql://prod/users:mysql://staging/users
```

**Output:**
```
Structure Diff: app.py → backup/app.py

Functions:
  + process_data      [NEW - 42 lines]
  ~ handle_request    [CHANGED - lines: 30→45, complexity: 3→7]
  - deprecated_func   [REMOVED]

Classes:
  ~ UserManager       [CHANGED - 2 methods added]
```

**Value:**
- Code review acceleration
- Environment drift detection
- Regression prevention

**Complexity:** Medium (reuse existing structure parsing, add diff logic)

---

### 1.2 `reveal stats://` - Codebase Statistics

**Problem:** No quick way to get codebase health metrics.

**Proposed:**
```bash
reveal stats://./src

# Output:
📊 Codebase Statistics: ./src

Files:              47 (.py: 32, .js: 15)
Lines of Code:      12,847
Functions:          234
Classes:            28
Average Complexity: 4.2

Hotspots (top 5):
  main.py:_main_impl    [244 lines, complexity 10]
  handlers.py:process   [156 lines, complexity 8]
  ...

Quality Summary:
  Bugs (B):         3 issues
  Security (S):     0 issues
  Complexity (C):   12 functions > 10

Recommendations:
  • 5 functions exceed 100 lines (refactor candidates)
  • 12 functions have complexity > 10 (simplify)
  • 3 bare except clauses (fix for proper error handling)
```

**Value:**
- Quick project health check
- Onboarding new developers
- Technical debt tracking

**Complexity:** Medium (aggregate existing AST + check outputs)

---

### 1.3 Watch Mode (`reveal --watch`)

**Problem:** Have to re-run reveal manually after file changes.

**Proposed:**
```bash
# Watch a file for changes
reveal app.py --watch

# Watch with checks
reveal app.py --watch --check

# Watch directory
reveal src/ --watch
```

**Behavior:**
- Clear screen on change
- Re-run reveal with same arguments
- Show timestamp of last change
- Ctrl+C to exit

**Value:**
- Continuous feedback during development
- Live quality monitoring
- Pairs well with TDD

**Complexity:** Low (use inotify/fswatch, re-exec on change)

---

### 1.4 Clipboard Integration (`reveal --copy`)

**Problem:** Often want to copy revealed content to clipboard for sharing.

**Proposed:**
```bash
# Copy function to clipboard
reveal app.py process_data --copy
# Output: ✓ Copied to clipboard (42 lines)

# Copy structure as JSON
reveal app.py --format=json --copy

# Copy with line numbers for code review
reveal app.py process_data --copy --numbered
```

**Value:**
- Faster code sharing
- Seamless integration with chat/docs
- No temp files

**Complexity:** Low (pipe to pbcopy/xclip/clip.exe)

---

## Priority 2: Power Features

### 2.1 `reveal query://` - SQL-like Queries

**Problem:** Complex queries require jq gymnastics.

**Proposed:**
```bash
# SQL-like syntax
reveal 'query://./src WHERE lines > 50 AND complexity > 5 ORDER BY complexity DESC'

# Select specific fields
reveal 'query://./src SELECT name, lines, complexity WHERE type = function'

# Aggregations
reveal 'query://./src SELECT file, COUNT(*) AS funcs GROUP BY file ORDER BY funcs DESC'
```

**Value:**
- Powerful ad-hoc analysis
- Familiar SQL syntax
- No jq required

**Complexity:** High (SQL parser, query planner)

---

### 2.2 `reveal graph://` - Dependency Visualization

**Problem:** Hard to understand code dependencies.

**Proposed:**
```bash
# Show import graph
reveal graph://./src --imports

# Output (text):
app.py
├── utils.py
│   └── helpers.py
└── handlers.py
    ├── utils.py (shared)
    └── models.py

# Call graph
reveal graph://app.py:main --calls

# Output as DOT/Mermaid
reveal graph://./src --imports --format=mermaid
```

**Value:**
- Architecture understanding
- Refactoring planning
- Documentation generation

**Complexity:** High (graph construction, cycle detection, layout)

---

### 2.3 Semantic Search (`reveal search://`)

**Problem:** grep finds text, not meaning.

**Proposed:**
```bash
# Find where exceptions are handled
reveal 'search://./src "exception handling"'

# Find authentication code
reveal 'search://./src "user authentication"'

# Find data validation
reveal 'search://./src "input validation"'
```

**Implementation:** Use embeddings (local or API) for semantic matching.

**Value:**
- Intent-based code discovery
- Natural language queries
- Cross-language search

**Complexity:** Very High (requires embedding model)

---

## Priority 3: Polish & UX

### 3.1 Color Themes

**Problem:** Output always looks the same.

**Proposed:**
```bash
reveal app.py --theme=dark
reveal app.py --theme=minimal
reveal app.py --theme=colorblind

# In config
echo 'theme: dark' >> ~/.config/reveal/config.yaml
```

**Value:**
- Accessibility
- User preference
- Terminal integration

**Complexity:** Low (theme definitions + color abstraction)

---

### 3.2 Interactive Mode (`reveal -i`)

**Problem:** Have to type full commands repeatedly.

**Proposed:**
```bash
reveal -i ./src

reveal> list
Functions (234), Classes (28)

reveal> show UserManager
[class structure]

reveal> check
[quality issues]

reveal> extract create_user
[function code]

reveal> quit
```

**Value:**
- Exploratory workflows
- Reduced typing
- State preservation

**Complexity:** Medium (REPL, history, completion)

---

### 3.3 Config File Support

**Problem:** Have to repeat flags.

**Proposed:**
```yaml
# ~/.config/reveal/config.yaml
default_format: json
check:
  ignore: [E501]
  select: [B, S, C]
theme: dark
aliases:
  py: "ast://.?type=function"
  complex: "ast://.?complexity>10"
```

**Usage:**
```bash
reveal @complex ./src    # Uses alias
reveal app.py            # Uses default format
```

**Value:**
- Personalization
- Project-specific settings
- Reduced repetition

**Complexity:** Medium (config parser, precedence rules)

---

## Priority 4: Integration Features

### 4.1 Git Pre-Commit Hook

**Problem:** Quality issues slip into commits.

**Proposed:**
```bash
# Install hook
reveal --install-hook pre-commit

# .git/hooks/pre-commit (auto-generated):
#!/bin/bash
git diff --cached --name-only | reveal --stdin --check --select=B,S
if [ $? -ne 0 ]; then
  echo "Quality checks failed. Fix issues or use --no-verify"
  exit 1
fi
```

**Value:**
- Automated quality gates
- Shift-left quality
- Team standards

**Complexity:** Low (hook template, installer)

---

### 4.2 GitHub Action

**Problem:** No CI/CD integration.

**Proposed:**
```yaml
# .github/workflows/reveal.yml
name: Code Quality
on: [push, pull_request]
jobs:
  reveal:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: scottsen/reveal-action@v1
        with:
          check: true
          select: B,S
          fail-on-issues: true
```

**Value:**
- PR quality gates
- Automated reviews
- Team visibility

**Complexity:** Medium (action wrapper, reporting)

---

### 4.3 VS Code Extension

**Problem:** Have to switch to terminal.

**Proposed features:**
- Hover: Show function structure
- Command palette: "Reveal: Show Structure"
- Panel: Live structure view
- Quick fix: "Reveal: Check This File"

**Value:**
- IDE integration
- Lower friction
- Broader adoption

**Complexity:** High (VS Code API, language server)

---

## Priority 5: Ecosystem Expansion

### 5.1 Plugin System

**Problem:** Can't extend reveal without forking.

**Proposed:**
```python
# ~/.reveal/plugins/my_plugin.py
from reveal import register_adapter

@register_adapter('mydb')
class MyDBAdapter:
    def get_structure(self, **kwargs):
        ...
```

```bash
reveal mydb://localhost/mydb
```

**Value:**
- Community extensions
- Custom adapters
- Private tools

**Complexity:** Medium (plugin discovery, API stability)

---

### 5.2 Remote File Support

**Problem:** Can't reveal files on remote servers directly.

**Proposed:**
```bash
# SSH-based
reveal ssh://server/path/to/file.py

# With jump host
reveal ssh://jump:server/path/to/file.py

# Using SSH config
reveal ssh://prod/app/main.py
```

**Value:**
- Production debugging
- No scp/rsync needed
- Seamless workflow

**Complexity:** Medium (SSH transport, caching)

---

## Implementation Roadmap

### Phase 1 (v0.19.0): Quick Wins
- [ ] `--copy` clipboard integration
- [ ] `--watch` mode
- [ ] Color themes

### Phase 2 (v0.20.0): Power Features
- [ ] `diff://` adapter
- [ ] `stats://` adapter
- [ ] Config file support

### Phase 3 (v0.21.0): Integration
- [ ] Git pre-commit hook
- [ ] GitHub Action
- [ ] Interactive mode

### Phase 4 (v1.0.0): Ecosystem
- [ ] Plugin system
- [ ] Remote file support
- [ ] `graph://` adapter

---

## Quick Wins Already Identified

From documentation audit (mortal-temple-1209):

1. **Fix broken link** in README: `docs/ARCHITECTURE.md` doesn't exist
2. **Update ROADMAP**: v0.11 → v0.18 (7 versions behind)
3. **Add dogfooding example**: python:// catching module shadowing
4. **Add COOL_TRICKS.md link**: From README quick reference

---

## Feedback

Want to discuss these proposals or suggest others?

- [GitHub Issues](https://github.com/Semantic-Infrastructure-Lab/reveal/issues)
- [Discussions](https://github.com/Semantic-Infrastructure-Lab/reveal/discussions)

---

*Part of [Semantic Infrastructure Lab](https://github.com/semantic-infrastructure-lab/sil)*
