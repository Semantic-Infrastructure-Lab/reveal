---
title: Reveal Configuration Guide
category: guide
help_topic: configuration
help_description: "Configuration system (rules, env vars, precedence)"
help_category: feature_guides
---
# Reveal Configuration Guide

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
- [Plugin Auto-Discovery](#plugin-auto-discovery)

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
# See the config files read, the REVEAL_* variables applied and the merged config
reveal reveal://config

# Test with environment variable
export REVEAL_RULES_DISABLE="C901,E501"
reveal check file.py
```

---

## Configuration Precedence

Reveal merges configurations from multiple sources with the following precedence (highest to lowest):

1. **CLI flags** (`--select`, `--ignore`) - Highest priority
2. **Environment variables** (`REVEAL_RULES_DISABLE`, etc.)
3. **REVEAL_CONFIG file** — when set, it *replaces* levels 4-6 (no project, user or system config is read)
4. **Project configs** (walk up from the checked file's directory, so `reveal check /other/proj/f.py` uses `/other/proj`'s `.reveal.yaml` wherever you run it)
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
$ reveal check file.py
# Both E501 and C901 are disabled

# CLI flag overrides everything
$ reveal check file.py --select=E501
# Only E501 runs (env and file config ignored)
```

---

## File Formats

Reveal reads `.reveal.yaml`, and a `[tool.reveal]` table in `pyproject.toml` (same keys, TOML
syntax). `REVEAL_CONFIG` may point at a YAML or JSON file (JSON is valid YAML).
`.reveal.toml` and `.reveal.json` are not discovered: they are ignored without a warning.

### YAML (Recommended)
```yaml
# .reveal.yaml
rules:
  disable: [C901, E501]
```

### pyproject.toml
```toml
# pyproject.toml
[tool.reveal.rules]
disable = ["C901", "E501"]
```

### JSON (only through `REVEAL_CONFIG`)
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
- Negation: `!important.js` re-includes a file an earlier pattern ignored (`.gitignore` semantics; see `REVEAL_IGNORE` below)

### Display Options

```yaml
display:
  breadcrumbs: false  # Disable navigation hints (default: true for TTY)
```

**Note:** Breadcrumbs are hidden when output is piped, unless a config sets `display.breadcrumbs`
explicitly (an explicit `true` keeps them on in pipes).

### Layer Violations (I003)

```yaml
architecture:
  layers:
    - name: presentation
      paths: [src/ui]
      allow_imports: [src/domain, src/utils]   # may import only itself and these

    - name: domain
      paths: [src/domain]
      allow_imports: [src/utils]

    - name: utils
      paths: [src/utils]
      deny_imports: [src/ui, src/domain]       # targets this layer must not reach
```

A layer has `name`, `paths`, `allow_imports` and `deny_imports`, all prefixes. `allow_imports` is an
allow list: when the key is present a layer may import only its own files and the listed prefixes, and
`allow_imports: []` means "nothing outside this layer"; leave the key out for no allow list.
`deny_imports` always wins. Only imports of other files in the project are judged: standard-library
and third-party imports are never checked. In any other shape
`imports://?violations` exits 3 naming the bad key; `reveal check` reports I003 as unavailable with
the same reason and still exits 0 (watch the `Checks: ... unavailable` line). Full reference: the
imports guide, "Configuration (.reveal.yaml)".

---

## Environment Variables

Reveal supports configuration via environment variables with higher precedence than config files but lower than CLI flags.

### Core Environment Variables

#### `REVEAL_NO_CONFIG`
Skip all config files (use only defaults and env vars). The value must be exactly `1`;
`true`/`yes` are not recognised:

```bash
export REVEAL_NO_CONFIG=1
reveal check file.py
```

#### `REVEAL_CONFIG`
Load a specific config file instead of discovery (no project, user or system config is read
while it is set):

```bash
export REVEAL_CONFIG=/path/to/custom-config.yaml
reveal check file.py
```

### Rule Environment Variables

#### `REVEAL_RULES_DISABLE`
Comma-separated list of rules to disable:

```bash
export REVEAL_RULES_DISABLE="E501,C901,D001"
reveal check file.py
```

#### `REVEAL_RULES_SELECT`
Comma-separated list of rules/categories to select:

```bash
export REVEAL_RULES_SELECT="B,S,C901"
reveal check file.py
```

### Output Environment Variables

#### `REVEAL_FORMAT`
Set output format:

```bash
export REVEAL_FORMAT=json
reveal check file.py
```

### Ignore Patterns

#### `REVEAL_IGNORE`
Comma-separated glob patterns to ignore:

```bash
export REVEAL_IGNORE="*.min.js,vendor/**,node_modules/**"
reveal check file.py
```

Every command that walks a directory honors it -- `scheme://` URIs and the subcommands
(`reveal surface`, `reveal pack`, `reveal check`, ...) alike. Patterns are added to any
`--exclude` and match relative to the analysed path, so `vendor/**` prunes `src/vendor/`
when you run `reveal surface src`.

`--exclude`, `REVEAL_IGNORE` and the config file's `ignore:` all use `.gitignore` syntax:
a bare name (`fixtures`, `*.min.js`) matches at any depth, a pattern with a slash
(`src/gen`, `app/*`) is anchored at the analysed path, a trailing `/` matches directories
only, `**` spans directories, `!` re-includes, and everything under a matched directory is
excluded. `*` does not cross a slash: `src/*.py` is `src/a.py` but not `src/a/b.py`.

### Rule-Specific Thresholds

#### `REVEAL_C901_THRESHOLD`
Set complexity threshold for C901:

```bash
export REVEAL_C901_THRESHOLD=20
reveal check file.py
```

#### `REVEAL_E501_MAX_LENGTH`
Set max line length for E501:

```bash
export REVEAL_E501_MAX_LENGTH=120
reveal check file.py
```

#### `REVEAL_I002_MAX_FILES`
Safety ceiling on the number of source files I002 (circular-dependency rule)
will scan when building its import graph for a project. Default `20000`.

I002 scans every source file under the detected project root. If root detection
ever points at a tree far larger than a single project, the scan would otherwise
run for minutes; instead it aborts past this ceiling, logs a warning, and skips
circular-dependency analysis for that run. Raise it only for genuinely huge
monorepos:

```bash
export REVEAL_I002_MAX_FILES=50000
export REVEAL_I002_CYCLE_LIMIT=0   # see below: otherwise cycles are still skipped past 2,000 files
reveal check very-large-monorepo/
```

#### `REVEAL_I002_CYCLE_LIMIT`
I002 skips whole-project cycle detection by default past 2,000 source files (and says so),
because it can take minutes on a correct but large root. Set a higher number, or `0`, to always
run it. This is separate from `REVEAL_I002_MAX_FILES`, which aborts on a root that is probably
mis-detected.

#### `REVEAL_D005_MAX_FILES` / `REVEAL_T006_MAX_FILES`
Same kind of ceiling for the two other rules that index the whole project once per run.
Both default to `5000` `.py` files.

- **D005** (duplicate literal clusters across files): past the ceiling, cross-file duplicate
  detection is skipped for that project.
- **T006** (TypedDict available but a param uses an untyped dict): past the ceiling, T006 still
  runs but only matches TypedDicts defined in the same module as the function.

Either skip is reported in `check`/`review` output (`scan_disclosures` in JSON), so a capped scan
is never mistaken for "nothing found".

```bash
export REVEAL_T006_MAX_FILES=20000
reveal check large-python-monorepo/ --select T006
```

#### `REVEAL_BREADCRUMBS`
Control navigation hints after output:

```bash
# Disable breadcrumbs permanently
export REVEAL_BREADCRUMBS=0

# Or use the CLI command (updates config file)
reveal --disable-breadcrumbs
```

**Note:** Breadcrumbs are automatically hidden when output is piped (TTY detection).

#### `REVEAL_DISK_CACHE`
Turn the on-disk cache off. It is on unless this is set to `0`, `false`, `no`, `off` or an empty
value (case-insensitive); with it off nothing is read from or written to the cache directory.
See [Disk cache](#disk-cache) below.

```bash
export REVEAL_DISK_CACHE=0
```

#### `REVEAL_CACHE_DIR`
Where the disk cache lives, instead of `~/.reveal/cache`:

```bash
export REVEAL_CACHE_DIR=/var/tmp/reveal-cache
```

#### `REVEAL_STRUCTURE_CACHE_MAX_FILES`
How many per-file entries the `structure` and `surface-file` namespaces keep, each, before evicting the oldest. Default `100000`; raise it
only for a repository with more source files than that, or every entry is evicted before it can be
reused. A value that is not an integer is ignored.

### Environment Variable Combinations

```bash
# Disable some rules, configure others
export REVEAL_RULES_DISABLE="E501,D001"
export REVEAL_C901_THRESHOLD=20
export REVEAL_IGNORE="*.min.js,vendor/**"

reveal check src/
```

### Disk cache

Each `reveal` command is a fresh process, so an in-memory cache dies at exit. Agents and CI usually
run many commands against one unchanged checkout, so reveal keeps the expensive, deterministic
parts on disk and the second command on an unchanged tree is cheap. The cache only ever holds
values reveal can recompute; deleting it costs time, never correctness.

**Where:** `~/.reveal/cache/` (override with `REVEAL_CACHE_DIR`), laid out as

```
~/.reveal/cache/v2/<reveal version>-<build>/<namespace>/<key>.pkl
```

where `v2` is the cache schema version, `<build>` is a 12-character digest of the code that produced
the values, and `<namespace>` names the kind of artifact.

**What is cached** (one namespace each):

| Namespace | Holds |
|-----------|-------|
| `structure` | a file's parsed structure: imports, functions, classes, declarations, plus (once a full scan has collected them) the file's module-level call sites and JSX references, so a warm scan re-parses nothing for them |
| `structure-outline` | the lighter outline-only structure `--grep` uses to name each hit's enclosing function |
| `surface-file` | one source file's complete `surface` scanner result, before the type filter and the cross-file route passes, so a repeat run, or a run for another type, scans only the files that changed. A file the scanner could not parse is not stored |
| `adapter_import_graph` | the project import graph behind `imports://` |
| `import_graph_v4` | the project import graph behind the `I002` rule, including source-scan accounting |
| `python_imports`, `javascript_imports`, `go_imports`, `rust_imports`, `zig_imports`, `generic_imports` | per-language import extraction feeding those graphs |
| `markdown-headings` | a Markdown file's heading index |
| `markdown_link_graph` | the link graph behind `markdown://` link queries |
| `churn` | per-file commit counts behind `stats://` `hotspots=true` |
| `d005_literals` | a Python file's repeated-literal clusters, the per-file input of the `D005` cross-file index |

**How it stays correct (invalidation):**

- *Per entry.* A file's structure is keyed on its absolute path, modification time (nanoseconds),
  size and language, so any edit misses. Project-wide artifacts such as the import graph are keyed
  on a fingerprint of every source file's path, mtime and size; the import graphs also key on the
  scan root they resolve imports against, so `imports://src` and `imports://src/pkg` never share an
  entry. Churn counts are keyed on the commit being walked and the query options.
- *Per build.* `<build>` is computed from the path, mtime and size of every file in the `reveal`
  package plus `tree_sitter` and `tree_sitter_language_pack`. Upgrading reveal, editing a
  development checkout or swapping the language pack therefore lands in a different directory, and
  the old one is never read. A rule or extractor change cannot serve an answer computed by older code.
- *On any error* (unreadable directory, corrupt or truncated entry, full disk) reading is a miss and
  writing is skipped, so the command runs uncached and gives the same answer.
- *Failures the content did not cause.* A source file that could not be read (a denied
  permission, an I/O error), that a dead worker process never parsed, or whose analysis failed in
  reveal itself (the analyzer lookup raised, or tree-sitter could not load the grammar, for example
  when the language pack's download or cache lock failed) is reported as failed but not cached,
  nor is an `imports://` or `I002` graph that contains one, nor the outline of a JS, PHP, Ruby,
  Go, Lua, Zig or GDScript file whose imports it could not extract (the outline says its imports
  are missing), nor an `I007` project scan across MCP requests, so the next run reads it again even
  though its mtime and size did not change. A syntax error is cached like any other result: the
  same content fails the same way.

**Housekeeping:** when a new build directory appears, only the 4 most recently used build
directories are kept and the rest are deleted. Within a namespace the oldest entries are evicted past
64 entries (the `structure` and `surface-file` namespaces use `REVEAL_STRUCTURE_CACHE_MAX_FILES` instead).

**Turn it off or clear it:**

```bash
REVEAL_DISK_CACHE=0 reveal check src/    # one command, nothing read or written
rm -rf ~/.reveal/cache                   # clear everything; it is rebuilt on demand
```

Use `REVEAL_DISK_CACHE=0` when you are measuring cold-start cost or checking an analyzer change in
a development checkout. Entries are Python pickles, so do not point `REVEAL_CACHE_DIR` at a
directory other users can write to.

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
  - files: "tests/**/*.py"
    rules:
      disable: [C901, R913]  # Tests can be complex
      E501:
        max_length: 150  # Longer lines in tests

  - files: "scripts/**/*.py"
    rules:
      disable: [C901, C905]  # Scripts can be messy

  - files: "src/core/**/*.py"
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
  - files: "*.py"          # Python files at the project root only
  - files: "**/*.py"       # All Python files
  - files: "src/*.py"      # Python files directly in src/ (not src/a/b.py)
  - files: "src/**/*.py"   # Python files anywhere under src/
  - files: "**/test_*.py"  # Test files by naming convention, at any depth
  - files: "**/__init__.py" # All __init__.py files
```

A pattern is matched against the whole path relative to the project root. `*`, `?` and `[...]`
never match `/`; only a whole `**` segment spans directories (`a/**/b`, `**/b`, `a/**`).

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
    - D001  # Duplicate function detection

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
  - files: "tests/**/*.py"
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
  - files: "**/*.ts"
    rules:
      C901:
        threshold: 15  # TypeScript complexity threshold

  - files: "**/*.js"
    rules:
      C901:
        threshold: 15  # JavaScript complexity threshold

  - files: "**/*.py"
    rules:
      C901:
        threshold: 10  # Python complexity threshold

  - files: "tests/**/*"
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
reveal check src/
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
reveal check src/
```

---

## Troubleshooting

### Config Not Loading

**Problem:** Changes to `.reveal.yaml` not taking effect

**Solutions:**
1. Check file is in project root or parent directory
2. Verify YAML syntax: `python -c "import yaml; yaml.safe_load(open('.reveal.yaml'))"`
3. Check for `root: true` in parent directory stopping discovery
4. Use `reveal reveal://config` (or the shorter `reveal dev inspect-config`) to see which config files were read; a file that exists but could not be loaded is listed under `Could Not Load` with the parse error

### Rule Still Running After Disable

**Problem:** Disabled rule still reports issues

**Possible causes:**
1. CLI flag overriding: `--select` ignores config
2. A `disable` in any layer (system, user, project, env) cannot be undone by a nearer layer: lists
   are concatenated, not replaced, and `disable` is checked before `select`. Only CLI `--select`
   overrides it.
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

**Solution:** Use `reveal://config` to see what was read and what it merged to:

```bash
reveal reveal://config

# Shows:
# - Every config file read (project files nearest first, user, system, or the REVEAL_CONFIG file)
# - Files that exist but could not be loaded (their settings are not applied)
# - The config REVEAL_* variables that are set, and apart from them any other REVEAL_* variable
#   set that the config loader does not read (a cache setting, or a misspelt name)
# - The merged active config for the current directory (rules, ignore, overrides, root)
# - Precedence order explanation
```

It discovers from the current directory, not from a file you name: run it from the directory you
check. `reveal dev inspect-config` prints the same sources and the merged settings as YAML:

```
Effective reveal configuration
  Search root: /home/user/project
  Project root: /home/user/project

Config files read (highest precedence first):
  project  /home/user/project/.reveal.yaml (root)

Environment variables:
  REVEAL_C901_THRESHOLD=20

Effective settings:
  rules:
    disable:
    - E501
    select:
    - E
    - C
    C901:
      threshold: 20
```

**Manual precedence check:**
1. Check for CLI flags first
2. Check environment variables: `env | grep REVEAL_`
3. Check for `REVEAL_CONFIG` env var
4. Check `.reveal.yaml` (and `pyproject.toml` `[tool.reveal]`) in current and parent directories
5. Check user config: `~/.config/reveal/config.yaml`

### Debugging with reveal://config

**Problem:** Need to understand current configuration state

**Solution:** Use `reveal://config` for the merged state:

```bash
# Human-readable output
reveal reveal://config

# JSON for scripting
reveal reveal://config --format json

# With environment variables
REVEAL_C901_THRESHOLD=20 reveal reveal://config
```

**What it shows:**
- **Overview**: Project root, working directory, no-config mode, the number of config files read
  and of config variables set
- **Sources**: the config `REVEAL_*` variables that are set (`REVEAL_NO_CONFIG`, `REVEAL_CONFIG`,
  `REVEAL_RULES_DISABLE`, `REVEAL_RULES_SELECT`, `REVEAL_FORMAT`, `REVEAL_IGNORE`,
  `REVEAL_C901_THRESHOLD`, `REVEAL_E501_MAX_LENGTH`, `REVEAL_BREADCRUMBS`), the `REVEAL_CONFIG`
  file, the project, user and system files read, files that could not be loaded, and any other
  `REVEAL_*` variable set (JSON `sources.other_env_vars`), which does not change the config
- **Active Config**: Merged rules (disabled, selected and per-rule settings), ignore patterns, root
  flag, overrides
- **Precedence**: 7-level hierarchy explanation

**Example output** (a project with `.reveal.yaml` = `root: true` and
`rules: {disable: [E501], select: [E, C]}`, run as
`REVEAL_C901_THRESHOLD=20 REVEAL_C905_MAX_DEPTH=3 reveal reveal://config`):
```
Overview:
  Project Root: /home/user/project
  Working Directory: /home/user/project
  No-Config Mode: False
  Config Files Found: 1
  Environment Variables Set: 1

Configuration Sources:

  Environment Variables:
    * REVEAL_C901_THRESHOLD = 20

  Project Configurations:
    * /home/user/project/.reveal.yaml (root)

  Other REVEAL_* Variables (set, not read by the config loader):
    * REVEAL_C905_MAX_DEPTH = 3

Active Configuration:

  Rules:
    Disabled: E501
    Selected: E, C
    C901:
      threshold: 20

  Root:
    * root: true (stops config search)
```

A `.reveal.yaml` that fails to parse is listed, with the parser's first line, under
`Could Not Load (settings not applied):` (JSON `sources.load_failures`).

### Pattern Matching Not Working

**Problem:** `ignore` or `overrides` pattern not matching files

**Common issues:**
- Overrides anchor at the project root: write `**/name.py` to match at any depth. `*` does
  not cross `/` (`src/*.py` matches `src/b.py`, not `src/a/b.py`; use `src/**/*.py` for both).
  (`ignore:` uses `.gitignore` rules instead, where a bare name matches at any depth.)
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

## Plugin Auto-Discovery

Reveal can load custom file analyzers at startup without any registration boilerplate. Drop a Python file matching `*_analyzer.py` into one of two locations:

| Location | Scope |
|----------|-------|
| `.reveal/analyzers/` under the current working directory | Project-local plugins |
| `~/.reveal/plugins/` | User-global plugins (all projects) |

### Writing a Plugin

A plugin file must define a `FileAnalyzer` subclass decorated with `@register`:

```python
# .reveal/analyzers/myformat_analyzer.py   (relative to the directory you run reveal from)
from reveal.base import FileAnalyzer
from reveal.registry import register

@register('.myext', name='MyFormat')
class MyFormatAnalyzer(FileAnalyzer):
    def get_structure(self, **kwargs):
        # ... your analysis logic
        return {'sections': [{'name': 'hello', 'line': 1}]}
```

`register(*extensions, name=...)` is a decorator factory: pass the extensions it handles. It fires
on import — no manual registry entry needed. `reveal a.myext` then prints `Sections (1): :1 hello`.

### Discovery Behavior

- Discovery runs once per process (lazy, on first `get_analyzer()` call)
- Bad plugin files emit a warning and are skipped without crashing reveal
- No command lists the loaded plugins; a successful load is logged only at debug level
  (`Loaded plugin: <path>`)

### Testing Plugins

```python
from reveal.registry import _reset_plugin_discovery, get_analyzer

def test_my_plugin():
    _reset_plugin_discovery()  # ensure clean state
    analyzer = get_analyzer("file.myext")
    assert analyzer is not None
```

---

## Advanced Topics

### Config Discovery Algorithm

1. Start at current file's directory
2. Check for `.reveal.yaml`, then a `pyproject.toml` `[tool.reveal]` table
3. If found and `root: true`, stop
4. If found, add to config stack
5. Move to parent directory
6. Repeat until reaching filesystem root or finding `root: true`
7. Merge all configs: scalars from the nearest win; lists (such as `disable`) are concatenated

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
- Cache: `~/.reveal/cache/` (override with `REVEAL_CACHE_DIR`; not XDG)

Legacy path still read, with a migration warning:
- `~/.reveal/rules/` → `$XDG_DATA_HOME/reveal/rules/` (default `~/.local/share/reveal/rules/`)

---

## See Also

- [RECIPES.md](RECIPES.md) - Practical examples using configuration
- [MARKDOWN_GUIDE.md](../adapters/MARKDOWN_GUIDE.md) - Core functionality reference
- [AGENT_HELP.md](../AGENT_HELP.md) - Configuration mistakes to avoid
- [README.md](../README.md) - Documentation hub
- `reveal help://` - List all help topics
- `reveal check --help` - CLI usage

