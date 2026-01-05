# Production Testing & Workflows Guide

**Audience:** Developers, DevOps engineers, and teams using Reveal in production environments

This guide demonstrates real-world workflows, CI/CD integration patterns, and advanced features tested on popular open-source projects (Requests, Flask, FastAPI, Django).

---

## Table of Contents

1. [Quick Wins](#quick-wins)
2. [Advanced Features](#advanced-features)
3. [Real-World Workflows](#real-world-workflows)
4. [CI/CD Integration](#cicd-integration)
5. [Performance Guidelines](#performance-guidelines)

---

## Quick Wins

### Find Your Worst Code in <1 Second

**Quality Hotspots** - Instantly identify technical debt hotspots:

```bash
reveal 'stats://src/?hotspots=true'
```

**Output:**
```
Codebase Statistics: src/
Files:      47
Lines:      18,424 (15,807 code)
Functions:  270
Classes:    93
Quality:    94.9/100

Top Hotspots (9):
1. routing.py        Quality: 62.1/100 | 13 functions >100 lines, 2 functions depth >4
2. applications.py   Quality: 63.9/100 | 10 functions >100 lines
3. param_functions.py Quality: 55.0/100 | 7 functions >100 lines
```

**Use Cases:**
- Code review prioritization
- Refactoring planning
- Onboarding new developers
- Technical debt tracking

---

### Grep for Complexity, Not Just Text

**AST Queries** - Find code patterns with precision:

```bash
# Find high-complexity functions
reveal 'ast://src/?complexity>20'

# Find god functions
reveal 'ast://src/?lines>200'

# Find deeply nested code
reveal 'ast://src/?depth>4'

# Combine filters
reveal 'ast://src/?complexity>15&lines>100'
```

**Available Filters:**
- `complexity>N` - cyclomatic complexity threshold
- `lines>N` - function length threshold
- `depth>N` - nesting depth threshold
- `type=function|class|method` - element type

**Example Results:**
```
Found 23 functions matching complexity>20:
1. analyze_param (complexity: 74, 156 lines) - dependencies/utils.py:245
2. jsonable_encoder (complexity: 73, 236 lines) - encoders.py:12
3. setup (complexity: 30, 248 lines) - applications.py:450
```

**Use Cases:**
- Technical debt audit
- Refactoring prioritization
- Code quality gates
- Migration planning

---

### Decorator Usage Analysis

Track decorator patterns across your codebase:

```bash
reveal src/ --decorator-stats
```

**Output:**
```
Standard Library Decorators:
  @cached_property     10 occurrences (1 file)
  @classmethod          8 occurrences (2 files)
  @dataclass            6 occurrences (4 files)
  @property             6 occurrences (1 file)

Custom/Third-Party Decorators:
  @deprecated           2 occurrences (2 files)

Summary:
  Total decorators: 35
  Unique decorators: 7
  Files with decorators: 9/44 (20%)
```

**Use Cases:**
- Track @deprecated usage during migrations
- Identify inconsistent decorator patterns
- Framework upgrade planning
- Code style audits

---

## Advanced Features

### 1. Markdown Extraction

#### Link Validation

```bash
# Extract all links
reveal README.md --links

# External links only
reveal README.md --links --link-type=external

# Links to specific domain
reveal README.md --links --domain=github.com
```

**Output:**
```
Links (3):
  External (3):
    Line 22   [depended upon](https://github.com/psf/requests/network/dependents)
             -> github.com
    Line 56   [Read the Docs](https://requests.readthedocs.io)
             -> requests.readthedocs.io
```

#### Code Block Extraction

```bash
# Extract all code blocks
reveal README.md --code

# Python code only
reveal README.md --code --language=python

# Include inline code
reveal README.md --code --inline
```

**Use Cases:**
- Documentation validation
- Extract examples for testing
- Link checking (prevent broken links)
- Code snippet audits

---

### 2. Semantic Navigation

Explore large files progressively to manage AI context:

```bash
# See what's at the top
reveal file.py --head 10

# See what's at the bottom
reveal file.py --tail 10

# Explore middle sections
reveal file.py --range 20-30

# Extract specific element
reveal file.py function_name
```

**Token Efficiency Example:**
- FastAPI applications.py: 4,669 lines → 135,402 tokens (full read)
- `reveal applications.py --head 5` → ~50 tokens (**2,708x savings**)

**Use Cases:**
- Large file exploration
- AI context management
- Iterative understanding
- Focused code review

---

### 3. Recursive Quality Checks

Scan entire codebase for specific issues:

```bash
# Find all large files
reveal src/ --recursive --check --select=M101

# Find all circular dependencies
reveal src/ --recursive --check --select=I002

# Find security issues
reveal src/ --recursive --check --select=S

# Ignore specific rules
reveal src/ --recursive --check --ignore=E501
```

**Selectors:**
- `--select=B,S` - Select categories (Bugs, Security)
- `--select=B001,S701` - Select specific rules
- `--ignore=E501` - Exclude specific rules

**Use Cases:**
- Technical debt audits
- Pre-release quality scans
- Migration planning
- Quality dashboards

---

## Real-World Workflows

### 1. Pre-Commit Quality Gate

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Get changed Python files
CHANGED=$(git diff --cached --name-only --diff-filter=ACM | grep "\.py$")

if [ -n "$CHANGED" ]; then
    echo "$CHANGED" | reveal --stdin --check --format=grep | grep "❌"
    if [ $? -eq 0 ]; then
        echo "❌ Critical issues found. Fix before committing."
        exit 1
    fi
fi
```

**What it does:**
- Runs quality checks only on changed files
- Blocks commits with critical issues (❌)
- Allows commits with warnings (⚠️)
- Minimal performance overhead (<1s per file)

---

### 2. Refactoring Prioritization

```bash
# Create refactoring target list
{
  echo "=== God Functions ==="
  reveal 'ast://src/?lines>100'

  echo ""
  echo "=== High Complexity ==="
  reveal 'ast://src/?complexity>20'

  echo ""
  echo "=== Quality Hotspots ==="
  reveal 'stats://src/?hotspots=true'
} > refactor-targets.txt
```

**Workflow:**
1. Run analysis to generate target list
2. Prioritize by impact/effort matrix
3. Track progress with follow-up scans
4. Measure quality improvements

---

### 3. Documentation Validation

```bash
# Extract all external links from documentation
find docs/ -name "*.md" | reveal --stdin --links --link-type=external > links.txt

# Extract all Python code examples
find docs/ -name "*.md" | reveal --stdin --code --language=python > examples.py

# Validate code examples compile
python -m py_compile examples.py
```

**What it validates:**
- External links exist (manual check from links.txt)
- Code examples are valid Python
- Consistent code formatting
- No broken internal references

---

### 4. Migration Planning

```bash
# Track deprecated decorator usage
reveal src/ --decorator-stats | grep "@deprecated"

# Find all files using old import patterns
reveal 'ast://src/' --format=grep | grep "from old_module"

# Identify circular dependencies blocking refactor
reveal src/ --recursive --check --select=I002
```

**Use Cases:**
- Framework upgrades
- API migration tracking
- Deprecation progress
- Dependency untangling

---

## CI/CD Integration

### GitHub Actions

```yaml
name: Code Quality

on: [pull_request]

jobs:
  quality-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Install Reveal
        run: pip install reveal-cli

      - name: Check changed files
        run: |
          git diff --name-only ${{ github.event.pull_request.base.sha }} | \
          grep "\.py$" | \
          reveal --stdin --check --format=grep | \
          grep "❌" && exit 1 || exit 0
```

### GitLab CI

```yaml
code-quality:
  stage: test
  script:
    - pip install reveal-cli
    - git diff --name-only $CI_MERGE_REQUEST_DIFF_BASE_SHA | grep "\.py$" | reveal --stdin --check
  only:
    - merge_requests
```

### Jenkins

```groovy
stage('Quality Check') {
    steps {
        sh '''
            pip install reveal-cli
            git diff --name-only origin/main...HEAD | \
            grep "\\.py$" | \
            reveal --stdin --check --format=grep | \
            grep "❌" && exit 1 || exit 0
        '''
    }
}
```

---

## Performance Guidelines

### Tested at Scale

**Real-world performance** (tested on popular open-source projects):

| Operation | Files | Time | Repository |
|-----------|-------|------|------------|
| Directory scan | 2,290 entries | 0.273s | Django |
| File structure | 4,669 lines | 0.347s | FastAPI |
| Quality check | 100 files | ~2s | Various |
| Hotspots analysis | 47 files | 0.83s | FastAPI core |
| AST query | 44 files | 0.81s | FastAPI core |

### Performance Tips

1. **Use `--fast` for large directories:**
   ```bash
   reveal large-repo/ --fast
   ```

2. **Limit output with `--max-entries`:**
   ```bash
   reveal large-repo/ --max-entries=50
   ```

3. **Filter before processing:**
   ```bash
   # Good: Filter with git first
   git ls-files "*.py" | reveal --stdin --check

   # Avoid: Processing entire directory
   reveal . --recursive --check
   ```

4. **Use specific rules in CI:**
   ```bash
   # Fast: Check critical issues only
   reveal src/ --check --select=B,S

   # Slow: Check all 32 rules
   reveal src/ --check
   ```

---

## Feature Comparison Matrix

| Feature | Input | Output | Performance | Use Case |
|---------|-------|--------|-------------|----------|
| **Hotspots** | Directory | Ranked quality scores | 0.8s/47 files | Find worst files |
| **Decorator Stats** | Directory | Usage summary | 0.8s/44 files | Pattern analysis |
| **AST Queries** | Directory + filter | Matching elements | 0.8s/44 files | Find code patterns |
| **Pipeline** | stdin | grep/json format | Variable | CI/CD integration |
| **Markdown Extract** | .md file | Links/code/frontmatter | <0.3s | Doc validation |
| **Semantic Nav** | File + range | Subset of elements | <0.3s | Token efficiency |
| **Recursive Check** | Directory + rules | Filtered issues | ~2s/100 files | Mass auditing |

---

## Related Documentation

- **Performance Research:** `internal-docs/research/POPULAR_REPOS_TESTING.md`
- **Schema Validation:** `docs/SCHEMA_VALIDATION_GUIDE.md`
- **Link Validation:** `docs/LINK_VALIDATION_GUIDE.md`
- **Cool Tricks:** `reveal/COOL_TRICKS.md`

---

**Tested on:** Requests, Flask, FastAPI, Django (2026-01-04, reveal v0.29.0)
