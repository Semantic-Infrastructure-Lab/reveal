# Reveal Configuration Guide

**Version:** v0.28.0+

Reveal's configuration system provides flexible, hierarchical control over rule checking behavior through `.reveal.yaml` files and environment variables.

## Table of Contents

- [Quick Start](#quick-start)
- [Configuration Precedence](#configuration-precedence)
- [File Formats](#file-formats)
- [Configuration Options](#configuration-options)
- [Environment Variables](#environment-variables)
- [File-Specific Overrides](#file-specific-overrides)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### Create a Project Configuration

Create `.reveal.yaml` in your project root:

```yaml
# .reveal.yaml
root: true  # Stop searching upward for configs

rules:
  # Disable specific rules
  disable:
    - E501  # Line too long
    - C901  # Complexity

  # Configure rule thresholds
  C901:
    threshold: 15  # Raised from default 10

  E501:
    max_length: 120  # Raised from default 100

# Ignore files/directories
ignore:
  - "*.min.js"
  - "vendor/**"
  - "node_modules/**"
```

### Verify Configuration

```bash
# Check what config is loaded
reveal --check file.py --verbose

# Test with environment variable
export REVEAL_RULES_DISABLE="C901,E501"
reveal --check file.py
```

---

## Configuration Precedence

Reveal merges configurations from multiple sources with the following precedence (highest to lowest):

1. **CLI flags** (`--select`, `--ignore`) - Highest priority
2. **Environment variables** (`REVEAL_RULES_DISABLE`, etc.)
3. **REVEAL_CONFIG file** (if `REVEAL_CONFIG` env var is set)
4. **Project configs** (walk up from current directory)
5. **User config** (`~/.config/reveal/config.yaml`)
6. **System config** (`/etc/reveal/config.yaml`)
7. **Built-in defaults** - Lowest priority

### Example Precedence

```bash
# File config disables E501
$ cat .reveal.yaml
rules:
  disable: [E501]

# Env var adds C901 (merges with file config)
$ export REVEAL_RULES_DISABLE="C901"
$ reveal --check file.py
# Both E501 and C901 are disabled

# CLI flag overrides everything
$ reveal --check file.py --select=E501
# Only E501 runs (env and file config ignored)
```

---

## File Formats

Reveal supports YAML, TOML, and JSON configuration files:

### YAML (Recommended)
```yaml
# .reveal.yaml
rules:
  disable: [C901, E501]
```

### TOML
```toml
# .reveal.toml
[rules]
disable = ["C901", "E501"]
```

### JSON
```json
{
  "rules": {
    "disable": ["C901", "E501"]
  }
}
```

---

## Configuration Options

### Root Marker

Stop directory walk-up at this config:

```yaml
root: true
```

### Rule Configuration

#### Disable Rules

```yaml
rules:
  disable:
    - C901  # Cyclomatic complexity
    - C905  # Nesting depth
    - E501  # Line too long
```

#### Select Rules/Categories

```yaml
rules:
  select:
    - B  # Bug detection rules (B001, B002, etc.)
    - S  # Security rules (S701, etc.)
    - C901  # Specific rule
```

#### Rule-Specific Settings

```yaml
rules:
  C901:
    threshold: 15  # Complexity threshold (default: 10)

  C905:
    MAX_DEPTH: 5  # Max nesting depth (default: 4)

  E501:
    max_length: 120  # Max line length (default: 100)
```

### Ignore Patterns

```yaml
ignore:
  - "*.min.js"
  - "vendor/**"
  - "node_modules/**"
  - "tests/fixtures/**"
  - "__pycache__/**"
```

Patterns support:
- Wildcards: `*.js`, `*.min.*`
- Globstar: `vendor/**/*.py`
- Negation: `!important.js` (not yet implemented)

### Layer Violations (I003)

```yaml
layers:
  - name: presentation
    pattern: "src/ui/**"
    can_import:
      - src/domain/**
      - src/utils/**

  - name: domain
    pattern: "src/domain/**"
    can_import:
      - src/utils/**

  - name: utils
    pattern: "src/utils/**"
    can_import: []
```

---

## Environment Variables

Reveal supports configuration via environment variables with higher precedence than config files but lower than CLI flags.

### Core Environment Variables

#### `REVEAL_NO_CONFIG`
Skip all config files (use only defaults and env vars):

```bash
export REVEAL_NO_CONFIG=1
reveal --check file.py
```

#### `REVEAL_CONFIG`
Load a specific config file instead of discovery:

```bash
export REVEAL_CONFIG=/path/to/custom-config.yaml
reveal --check file.py
```

### Rule Environment Variables

#### `REVEAL_RULES_DISABLE`
Comma-separated list of rules to disable:

```bash
export REVEAL_RULES_DISABLE="E501,C901,D001"
reveal --check file.py
```

#### `REVEAL_RULES_SELECT`
Comma-separated list of rules/categories to select:

```bash
export REVEAL_RULES_SELECT="B,S,C901"
reveal --check file.py
```

### Output Environment Variables

#### `REVEAL_FORMAT`
Set output format:

```bash
export REVEAL_FORMAT=json
reveal --check file.py
```

### Ignore Patterns

#### `REVEAL_IGNORE`
Comma-separated glob patterns to ignore:

```bash
export REVEAL_IGNORE="*.min.js,vendor/**,node_modules/**"
reveal --check file.py
```

### Rule-Specific Thresholds

#### `REVEAL_C901_THRESHOLD`
Set complexity threshold for C901:

```bash
export REVEAL_C901_THRESHOLD=20
reveal --check file.py
```

#### `REVEAL_E501_MAX_LENGTH`
Set max line length for E501:

```bash
export REVEAL_E501_MAX_LENGTH=120
reveal --check file.py
```

### Environment Variable Combinations

```bash
# Disable some rules, configure others
export REVEAL_RULES_DISABLE="E501,D001"
export REVEAL_C901_THRESHOLD=20
export REVEAL_IGNORE="*.min.js,vendor/**"

reveal --check src/
```

---

## File-Specific Overrides

Apply different rules to different files using glob patterns:

```yaml
# .reveal.yaml
root: true

rules:
  disable: [C901]  # Default: disable C901 everywhere

# Override rules for specific files
overrides:
  - files: ["tests/**/*.py"]
    rules:
      disable: [C901, R913]  # Tests can be complex
      E501:
        max_length: 150  # Longer lines in tests

  - files: ["scripts/**/*.py"]
    rules:
      disable: [C901, C905]  # Scripts can be messy

  - files: ["src/core/**/*.py"]
    rules:
      C901:
        threshold: 8  # Stricter for core code
```

### How Overrides Work

1. Base config is applied to all files
2. For each file, matching override patterns are applied in order
3. Later overrides merge with earlier ones
4. Final merged config is used for that file

### Override Pattern Matching

```yaml
overrides:
  - files: ["*.py"]          # All Python files
  - files: ["src/**/*.py"]   # Python files in src/
  - files: ["test_*.py"]     # Test files by naming convention
  - files: ["**/__init__.py"] # All __init__.py files
```

---

## Examples

### Example 1: Python Project

```yaml
# .reveal.yaml
root: true

rules:
  # Disable verbose rules
  disable:
    - E501  # Line length (using black formatter)
    - D001  # Docstring rules

  # Configure complexity
  C901:
    threshold: 12

ignore:
  - "*.pyc"
  - "__pycache__/**"
  - ".venv/**"
  - "build/**"
  - "dist/**"

overrides:
  - files: ["tests/**/*.py"]
    rules:
      disable: [C901, R913]  # Tests can be complex
```

### Example 2: Multi-Language Project

```yaml
# .reveal.yaml
root: true

rules:
  disable: [E501]  # Let formatters handle line length

ignore:
  - "node_modules/**"
  - "vendor/**"
  - "*.min.js"
  - "*.min.css"
  - "build/**"
  - "dist/**"

overrides:
  - files: ["**/*.ts", "**/*.js"]
    rules:
      C901:
        threshold: 15  # JavaScript complexity threshold

  - files: ["**/*.py"]
    rules:
      C901:
        threshold: 10  # Python complexity threshold

  - files: ["tests/**/*"]
    rules:
      disable: [C901, C905, R913]
```

### Example 3: CI/CD Strict Mode

```yaml
# .reveal-strict.yaml (for CI)
root: true

rules:
  # Enable all rules
  select: [B, C, D, E, I, L, M, N, R, S, U, V]

  # Lower thresholds
  C901:
    threshold: 8  # Strict complexity

  C905:
    MAX_DEPTH: 3  # Strict nesting

  E501:
    max_length: 100  # Enforce line length

ignore:
  - "tests/fixtures/**"
  - "scripts/**"
```

Usage in CI:

```bash
export REVEAL_CONFIG=.reveal-strict.yaml
reveal --check src/
```

### Example 4: Development vs Production

Development (lenient):
```yaml
# .reveal.yaml
root: true
rules:
  disable: [E501, C901, D001]
```

CI/Production (strict):
```bash
# Use environment variables to override
export REVEAL_NO_CONFIG=1  # Ignore .reveal.yaml
export REVEAL_C901_THRESHOLD=10
export REVEAL_E501_MAX_LENGTH=100
reveal --check src/
```

---

## Troubleshooting

### Config Not Loading

**Problem:** Changes to `.reveal.yaml` not taking effect

**Solutions:**
1. Check file is in project root or parent directory
2. Verify YAML syntax: `python -c "import yaml; yaml.safe_load(open('.reveal.yaml'))"`
3. Check for `root: true` in parent directory stopping discovery
4. Use `reveal --check file.py --verbose` to see loaded config

### Rule Still Running After Disable

**Problem:** Disabled rule still reports issues

**Possible causes:**
1. CLI flag overriding: `--select` ignores config
2. Environment variable precedence: `REVEAL_RULES_SELECT` overrides file config
3. Typo in rule code: `C901` not `C9O1` (zero vs letter O)

**Debug:**
```bash
# Check effective config
python3 -c "
from reveal.config import RevealConfig
from pathlib import Path
cfg = RevealConfig.get(Path('.'))
print(cfg.dump())
"
```

### Precedence Confusion

**Problem:** Unsure which config is being used

**Solution:** Use precedence order:
1. Check for CLI flags first
2. Check environment variables: `env | grep REVEAL_`
3. Check for `REVEAL_CONFIG` env var
4. Check `.reveal.yaml` in current and parent directories
5. Check user config: `~/.config/reveal/config.yaml`

### Pattern Matching Not Working

**Problem:** `ignore` or `overrides` pattern not matching files

**Common issues:**
- Missing `**` for subdirectories: Use `src/**/*.py` not `src/*.py`
- Absolute vs relative paths: Patterns match relative to project root
- Case sensitivity: Patterns are case-sensitive on Linux/macOS

**Test patterns:**
```python
from pathlib import Path
from reveal.config import glob_match

path = Path("src/utils/helpers.py")
pattern = "src/**/*.py"
print(glob_match(path, pattern))  # Should print True
```

---

## Advanced Topics

### Config Discovery Algorithm

1. Start at current file's directory
2. Check for `.reveal.{yaml,toml,json}`
3. If found and `root: true`, stop
4. If found, add to config stack
5. Move to parent directory
6. Repeat until reaching filesystem root or finding `root: true`
7. Merge all configs (nearest has highest precedence)

### Config Caching

Reveal caches config per project root for performance. Clear cache:

```python
from reveal.config import RevealConfig
RevealConfig._cache.clear()
```

Or in tests:
```python
def setUp(self):
    RevealConfig._cache.clear()
```

### XDG Base Directory Support

Reveal follows XDG Base Directory specification:

- Config: `$XDG_CONFIG_HOME/reveal/config.yaml` (default: `~/.config/reveal/config.yaml`)
- Data: `$XDG_DATA_HOME/reveal/` (default: `~/.local/share/reveal/`)
- Cache: `$XDG_CACHE_HOME/reveal/` (default: `~/.cache/reveal/`)

Legacy paths still supported with deprecation warning:
- `~/.reveal/config.yaml` → `~/.config/reveal/config.yaml`
- `~/.reveal/rules/` → `~/.local/share/reveal/rules/`

---

## See Also

- `reveal help://` - List all help topics
- `reveal help://tricks` - Cool tricks and hidden features
- `reveal --check --help` - CLI usage
- Project README: Configuration section

---

**Last Updated:** 2026-01-02 (v0.28.0)
