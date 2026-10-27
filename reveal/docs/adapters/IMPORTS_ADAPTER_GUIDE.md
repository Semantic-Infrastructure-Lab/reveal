---
title: Imports Adapter Guide (imports://)
category: guide
---
# Imports Adapter Guide (imports://)

**Adapter**: `imports://`
**Purpose**: Import graph analysis for detecting unused imports, circular dependencies, and layer violations
**Type**: Analysis adapter
**Output Formats**: text, json

## Table of Contents

1. [Quick Start](#quick-start)
2. [URI Syntax](#uri-syntax)
3. [Import Graph Overview](#import-graph-overview)
4. [Unused Import Detection](#unused-import-detection)
5. [Circular Dependency Detection](#circular-dependency-detection)
6. [Layer Violation Checking](#layer-violation-checking)
7. [Multi-Language Support](#multi-language-support)
8. [Query Parameters](#query-parameters)
9. [CLI Flags](#cli-flags)
10. [Output Types](#output-types)
11. [Workflows](#workflows)
12. [Integration Examples](#integration-examples)
13. [Performance & Best Practices](#performance--best-practices)
14. [Troubleshooting](#troubleshooting)
15. [Limitations](#limitations)
16. [Tips & Best Practices](#tips--best-practices)
17. [Related Documentation](#related-documentation)
18. [FAQ](#faq)

---

## Quick Start

```bash
# 1. Import graph overview (all imports)
reveal imports://src

# 2. Find unused imports (dead code)
reveal 'imports://src?unused'

# 3. Detect circular dependencies
reveal 'imports://src?circular'

# 4. Check layer violations (requires .reveal.yaml)
reveal 'imports://src?violations'

# 5. Single file import inspection
reveal imports://src/main.py

# 6. Verbose output (detailed information)
reveal imports://src --verbose

# 7. JSON output for CI/CD
reveal 'imports://src?unused' --format=json

```

**Why use imports://?**
- **Clean codebase**: Find and remove unused imports (dead code)
- **Architecture health**: Detect circular dependencies (refactoring opportunities)
- **Layer enforcement**: Check architectural boundaries (clean architecture)
- **Multi-language**: Python, JavaScript/TypeScript, Go, Rust, Java, C++, and more
- **CI/CD integration**: JSON output for automated quality checks

---

## URI Syntax

```
imports://<path>[?<query>]
```

### Components

| Component | Required | Default | Description |
|-----------|----------|---------|-------------|
| `path` | No | `.` (current directory) | Directory or file to analyze |
| `query` | No | (none) | Query flag (?unused, ?circular, ?violations), plus `&lazy=include\|exclude\|only` (see [Which edges count](#which-edges-count-lazy)) |

### Examples

```bash
# Directory analysis
reveal imports://src
reveal imports://lib/utils
reveal imports://.  # Current directory

# File analysis
reveal imports://src/main.py
reveal imports://app/__init__.py

# Quality checks
reveal 'imports://src?unused'
reveal 'imports://src?circular'
reveal 'imports://src?violations'

# Absolute paths
reveal imports:///absolute/path/to/project

# Current directory
reveal imports://
reveal imports://.
```

---

## Import Graph Overview

The default view builds a complete import graph:

```bash
reveal imports://src
```

**Returns** (~300 tokens):

```
============================================================
Import Analysis: src
============================================================

  Total Files:   45
  Total Imports: 238
  Cycles Found:  ❌ Yes

  Rule: Cycles Found uses static imports between files under the scan root, tests included; TYPE_CHECKING imports excluded; function-level (lazy) imports excluded (default); ...

  ⚠️  16 code file(s) skipped — no import support for: .sh (10), .ipynb (2), ...
      (these are not counted above; import graph excludes them)

Query options:
  reveal 'imports://src?unused'    - Find unused imports
  reveal 'imports://src?circular'  - Detect circular deps
  reveal 'imports://src?violations' - Check layer violations
  reveal 'imports://src?rank=fan-in' - Rank files by fan-in (core abstractions)
```

**What you get**:
- **Total files**: Number of source files analyzed
- **Total imports**: Count of import statements
- **Cycles found**: Quick indicator if circular dependencies exist
- **Rule**: The counting rule behind the answer (edges, scope, tests, lazy imports); the full line is longer than shown here
- **Skipped files**: Code files in languages with no import support, counted separately from the totals (the count is for the whole scan root, which can be wider than the requested path)
- **Query options**: Suggested follow-up commands

**Use cases**:
- Quick health check
- Understand import complexity
- Determine next steps (unused vs circular vs violations)

---

## Unused Import Detection

Find imports that are declared but never used in code:

```bash
reveal 'imports://src?unused'
```

**Returns** (~500 tokens):

```
============================================================
Unused Imports: 12
============================================================

  api/routes.py:3 - typing (unused: Dict)
  api/routes.py:5 - datetime
  models/user.py:8 - typing (unused: Optional)
  utils/helpers.py:2 - sys
  db/session.py:4 - sqlalchemy.orm
  config.py:7 - pathlib (unused: Path)
  services/auth.py:12 - jwt.exceptions
  handlers/errors.py:5 - traceback
  middleware/logging.py:3 - json
  tests/test_api.py:15 - pytest (unused: fixture)

  ... and 2 more unused imports
  Run with --verbose to see all 12 unused imports
```

### Verbose Output

```bash
reveal 'imports://src?unused' --verbose
```

**Returns**: Full list of all unused imports with file paths and line numbers

### JSON Output

```bash
reveal 'imports://src?unused' --format=json
```

**Returns**:
```json
{
  "contract_version": "1.1",
  "type": "unused_imports",
  "source": "src",
  "source_type": "directory",
  "count": 12,
  "unused": [
    {
      "file": "src/api/routes.py",
      "line": 3,
      "module": "typing.Dict",
      "names": ["Dict"],
      "type": "from_import",
      "is_relative": false,
      "alias": null
    },
    {
      "file": "src/api/routes.py",
      "line": 5,
      "module": "datetime",
      "names": [],
      "type": "import",
      "is_relative": false,
      "alias": null
    }
  ],
  "metadata": {
    "total_imports": 238,
    "total_files": 45,
    "has_cycles": true,
    "analyzer": "imports"
  }
}
```

### How It Works

1. **Extract imports**: Parse all import statements in files
2. **Extract symbols**: Find all identifier references in code
3. **Cross-reference**: Match imports against symbol usage
4. **Flag unused**: Report imports with zero references

**Detection logic**:
- ✅ Detects: `import os` (never used)
- ✅ Detects: `from typing import Dict` (never used)
- ❌ Ignores: `from module import *` (can't verify usage)
- ❌ Ignores: Imports in `__all__` (re-exports)
- ❌ Ignores: `TYPE_CHECKING` imports (type hints only)

**Use cases**:
- Clean up dead code
- Reduce import overhead
- Improve code clarity
- Speed up module loading

---

## Circular Dependency Detection

Find import cycle groups (A imports B, B imports A):

```bash
reveal 'imports://src?circular'
```

**Returns** (~400 tokens):

```
============================================================
Circular Dependencies: 3 cycle groups
============================================================

  1. 2 files  user.py, auth.py
  2. 2 files  routes.py, users.py
  3. 3 files  models.py, session.py, base.py

  Rule: cycles use static imports between files under the scan root, tests included; TYPE_CHECKING imports excluded; ...
```

Each entry is one **strongly-connected component** (SCC) — a group of files that
mutually depend on each other. This is the meaningful count: 30 analyzers all
cycling through a shared registry appear as 1 group, not 30 separate paths.

### Verbose Output

```bash
reveal 'imports://src?circular' --verbose
```

**Returns**: All groups and all files (no truncation), plus each group's cycle edge sequence (`cycle: a.py → b.py → c.py → a.py`)

### JSON Output

```bash
reveal 'imports://src?circular' --format=json
```

**Returns**:
```json
{
  "contract_version": "1.1",
  "type": "circular_dependencies",
  "source": "src",
  "source_type": "directory",
  "count": 3,
  "cycles": [
    ["src/models/user.py", "src/services/auth.py"],
    ["src/api/routes.py", "src/handlers/users.py"],
    ["src/db/base.py", "src/db/models.py", "src/db/session.py"]
  ],
  "metadata": {
    "total_imports": 238,
    "total_files": 45,
    "has_cycles": true,
    "analyzer": "imports"
  }
}
```

Each inner array is the **members of one SCC** (sorted, no repeated last node).
`count` = number of distinct cycle groups, not number of simple paths.

### How It Works

1. **Build graph**: Create directed graph of import relationships
2. **Detect groups**: Tarjan's SCC algorithm finds all strongly-connected components
3. **Report members**: Show all files in each cycle group (≥2 members)

**Detection notes**:
- ✅ Detects: Direct cycles (A → B → A)
- ✅ Detects: Indirect cycles (A → B → C → A)
- ✅ Collapses: Hub cycles — N files cycling through a shared module = 1 group
- ❌ Ignores: `TYPE_CHECKING` imports (not runtime cycles)
- ❌ Leaves out by default: function-level (lazy) imports, which run after every module has loaded and are the usual way to break a cycle; `&lazy=include` counts them (see [Which edges count](#which-edges-count-lazy))
- ✅ Reports: All members of each cycle group, sorted

**Why circular dependencies are bad**:
- **Testing difficulty**: Can't test modules in isolation
- **Load order issues**: Module initialization becomes fragile
- **Tight coupling**: Changes cascade across modules
- **Refactoring obstacles**: Hard to restructure architecture

**How to fix**:
1. **Extract interface**: Move shared types to separate module
2. **Dependency injection**: Pass dependencies as parameters
3. **Inversion**: Make one module depend on abstraction
4. **Merge**: If modules are tightly coupled, merge them

---

## Fan-in Ranking

Rank files by how many other files import them — the single most useful architectural signal derivable from code alone:

```bash
reveal 'imports://src?rank=fan-in'
reveal 'imports://src?rank=fan-in&top=20'
```

**Returns** (~200 tokens):

```
Fan-in ranking: src
Files: 10 of 45  (fan-in = number of files that import this file)

  Rule: fan-in and fan-out count static imports between files under the scan root, tests included; ...

  FILE                            FAN-IN   FAN-OUT
  ----------------------------   -------  --------
  db/session.py                       18         2
  utils/__init__.py                   15         3
  models/base.py                      12         0
  config.py                            9         1
  api/deps.py                          7         4
  auth/tokens.py                       5         2
  core/exceptions.py                   4         0
  services/cache.py                    3         3
  api/routes.py                        0         8
  main.py                              0         3

  Note: static imports only — files loaded via dynamic dispatch
  (importlib, require(), Class.forName, autoload, etc.) show lower fan-in than actual.

⚠ Truncated entries: showing 10 of 45 — raise ?top=N
```

**Reading the output:**

| Pattern | Meaning | Action |
|---------|---------|--------|
| High fan-in (top rows) | Core abstractions — base classes, shared utils, session factories | Change carefully — ripples everywhere |
| Fan-in = 0, fan-out > 0 | Entry points — `main.py`, CLI handlers, route files | Safe starting points for exploration |
| Fan-in = 0, fan-out = 0 | Dead code candidates or standalone scripts | Investigate before deleting |

**`?top=N` parameter:**

```bash
# Top 10 most-imported files
reveal 'imports://src?rank=fan-in&top=10'
```

### JSON Output

```bash
reveal 'imports://src?rank=fan-in' --format=json
```

**Returns**:
```json
{
  "contract_version": "1.1",
  "type": "fan_in_ranking",
  "source": "src",
  "source_type": "directory",
  "total": 45,
  "entries": [
    { "file": "db/session.py", "fan_in": 18, "fan_out": 2 },
    { "file": "utils/__init__.py", "fan_in": 15, "fan_out": 3 }
  ],
  "metadata": { "total_imports": 238, "total_files": 45, "has_cycles": false }
}
```

### How It Works

1. **Build graph**: Scan all files with supported extensions, extract import statements
2. **Resolve imports**: Map module names to file paths using language-specific resolver
3. **Count reverse dependencies**: For each file, count unique files in `reverse_deps` (the files that import it)
4. **Count forward dependencies**: For each file, count unique files in `dependencies` (the files it imports)
5. **Sort**: Descending by fan-in, then fan-out, then filename

**Coverage notes**:
- ✅ Includes files with zero imports (they appear with fan-in from others)
- ✅ Includes files never imported (they appear with fan-in=0)
- ✅ Includes function-level (lazy) imports; `&lazy=exclude` counts load-time imports only
- ❌ Dynamic imports (`importlib.import_module`) not captured
- ❌ Decorator-based registration (e.g. `@app.route`) not captured

### Which edges count (`&lazy`)

The graph keeps every static import edge except `TYPE_CHECKING` ones, tagged with where the
import sits (module level or inside a function). Each edge-derived answer prints the rule it
counted by, as a `Rule:` line in text and an `edge_rule` object in JSON (`lazy`, `lazy_default`,
`type_checking`, `tests`, `scope`, `unclassified_edges`, `unclassified_languages`, `text`):

| `&lazy=` | Edges counted | Default for |
|----------|---------------|-------------|
| `include` | every edge | fan-in, `?entrypoints`, `?components`, `?violations` |
| `exclude` | load-time edges only (the architecture view) | `?circular`, `metadata.has_cycles` (`metadata.cycles_lazy` says which) |
| `only` | function-level edges only | none |

`exclude` and `only` split the edges: per file, fan-in under `include` is the sum of the other
two. Importers anywhere under the scan root count, tests included unless `&tests=exclude`
(`?entrypoints` never counts importers under a test path); `&scope=path` makes the requested path
the scan root. Python,
JavaScript, TypeScript and TSX record import scope (positionally: an import, `import()` or
`require()` in a function, method, arrow or function expression is function-level; a class field
initializer or static block is module level). Other languages' edges count as load-time under
every value, and the rule names those languages and the number of edges. An unknown value is an error.
`architecture://`, `overview://` and `pack` print the same rule for the numbers they take from this
graph; none of them accepts `&lazy`.

```bash
reveal 'imports://src?rank=fan-in&lazy=exclude'   # module-level imports only
reveal 'imports://src?circular&lazy=include'      # a lazy back-edge closes a cycle too
```

**When to use `rank=fan-in` vs `importers`:**

| Query | Question | Granularity |
|-------|----------|-------------|
| `imports://src?rank=fan-in` | Which files are most central? (ranked list) | Codebase-wide |
| `imports://src?importers=utils.py` | What exactly imports this one file? | Per-file |

Use `rank=fan-in` for orientation; use `?importers` for targeted impact analysis.

---

## Layer Violation Checking

Enforce architectural boundaries (requires .reveal.yaml configuration):

```bash
reveal 'imports://src?violations'
```

### Configuration (.reveal.yaml)

```yaml
architecture:
  layers:
    - name: presentation
      paths: [api, cli]                     # prefixes, relative to the path you pass to imports://
      allow_imports: [services, handlers, models]   # if set, may import only itself and these

    - name: application
      paths: [services, handlers]
      allow_imports: [models, entities]

    - name: domain
      paths: [models, entities]
      deny_imports: [db, external, api]     # targets this layer must not reach

    - name: infrastructure
      paths: [db, external]
      allow_imports: [models, entities]
```

A layer has `name`, `paths`, `allow_imports` and `deny_imports`, and `architecture` has only
`layers`. There is no `rules:` or `can_import` key. `paths`, `allow_imports` and `deny_imports`
are prefixes relative to the path given to `imports://`: for `imports://src?violations` write
`models`, not `src/models`; for `imports://.?violations` write `src/models`.

A malformed `architecture` block is an error, not a skipped layer, so a config in another shape
cannot pass with 0 violations. The command exits 3 and names the config file and the bad entry
when `architecture` or `layers` has the wrong type, a layer is not a mapping
(`architecture.layers[0] must be a mapping, got str`), `architecture` or a layer has a key
outside the ones above (`has unknown key(s) 'rules'`, with a "did you mean" for a near
miss), a layer has neither `allow_imports` nor a non-empty `deny_imports`, or `allow_imports` or
`deny_imports` is not a list of strings (a key written with no value is refused: for `allow_imports`
"no value" and `[]` mean opposite things).

`allow_imports` is an allow list. When the key is present, a layer may import only its own files and the
listed prefixes; `allow_imports: []` means "nothing outside this layer" (write it for a domain layer
that must depend on nothing), and leaving the key out means no allow list. `deny_imports` always wins.
Only imports of other files in the project are judged: standard-library and third-party imports are
never checked.

### Example Output

```
Layer Violations: 1
  models/user.py -> db/session.py  [domain] domain layer cannot import from db
```

Rows carry no line number. In JSON:

```json
{
  "count": 1,
  "violations": [
    {"from_file": "models/user.py", "to_file": "db/session.py",
     "layer": "domain", "reason": "domain layer cannot import from db"}
  ]
}
```

### Without Configuration

If `.reveal.yaml` is not configured:

```bash
reveal 'imports://src?violations'
```

**Returns**:
```
Layer Violations: NOT CONFIGURED
  ℹ️  Layer violation detection requires .reveal.yaml configuration
  Add layer rules to .reveal.yaml to enable this check.
```

**Use cases**:
- Enforce clean architecture
- Prevent presentation → database direct access
- Ensure domain layer purity
- Maintain layer boundaries in large codebases

---

## Multi-Language Support

imports:// supports multiple programming languages:

### Supported Languages

Support comes in tiers — be aware of which query modes actually work per language:

- **✅ Full** — listing, cross-file resolution (`?circular`, `rank=fan-in`), and
  unused-import detection (`?unused`).
- **📦 Listing + graph** — imports listed and resolved to files (`?circular`,
  `rank=fan-in` work); `?unused` is **not** reported (textual `#include` has no
  reliable per-symbol usage semantics).
- **📝 Listing only** — imports listed (counts, per-file view); cross-file
  resolution and `?unused` are not claimed (would need classpath/namespace
  resolution). `?circular`/fan-in will show no edges for these.

| Language | Extensions | Status | Notes |
|----------|-----------|--------|-------|
| Python | `.py`, `.pyi` | ✅ Full | Imports, symbols, exports, TYPE_CHECKING |
| JavaScript | `.js`, `.jsx`, `.mjs`, `.cjs` | ✅ Full | require, import/export |
| TypeScript | `.ts`, `.tsx` | ✅ Full | import/export, type imports |
| Go | `.go` | ✅ Full | import statements |
| Rust | `.rs` | ✅ Full | use statements |
| C | `.c`, `.h` | 📦 Listing + graph | `#include` (quoted resolves to files; `<system>` listed, not resolved) |
| C++ | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx` | 📦 Listing + graph | `#include` directives (same resolution rules as C) |
| Java | `.java` | 📦 Listing + graph | `import com.pkg.Type` → `com/pkg/Type.java` (package==dir, reliable); wildcards/`static`/JDK classes skip |
| PHP | `.php` | 📦 Listing + graph | `use App\Models\User` → `.../Models/User.php` (longest-unique suffix, tolerant of PSR-4 prefix); `require`/`include` file literals resolve relative to the file |
| Ruby | `.rb` | 📦 Listing + graph | `require_relative './x'` → `x.rb`; `load`/`require` of a real in-tree `.rb`; bare `require 'gem'` skips |
| Kotlin | `.kt`, `.kts` | 📦 Listing + graph | `import com.pkg.Bar` → `com/pkg/Bar.kt` when the file is named for the class (best-effort; Kotlin doesn't enforce filename==class) |
| Swift | `.swift` | 📦 Listing + graph | `import Foo` → `Foo.swift` where a module maps 1:1 to a lone file; system frameworks skip (sparse fan-in by nature) |
| Scala | `.scala` | 📦 Listing + graph | `import a.b.C` → `a/b/C.scala` (package==dir); selector `import a.b.{C, D}` and wildcard `import a.b._` list but skip file resolution (name multiple targets) |
| Dart | `.dart` | 📦 Listing + graph | relative `import './x.dart'` resolves; `package:x/y.dart` names a pub package (skipped unless it maps into the tree). `export`/`part` are out of scope for v1 |
| Lua | `.lua` | 📦 Listing + graph | `require("a.b")` → `a/b.lua` (`.`-separated path); bare stdlib/rock names with no in-tree file skip |
| Zig | `.zig` | 📦 Listing + graph | `@import("foo.zig")` → relative to the importing file; `@import("std")`/`"builtin"` and other non-`.zig` names skip |
| GDScript | `.gd` | 📦 Listing + graph | `preload`/`load`/`extends "res://path.gd"` — `res://` resolves against the Godot **project root** (nearest `project.godot`, or scan root), not the importing file |
| C# | `.cs` | 📝 Listing (+ sparse graph) | `using` directives (incl. `global using`, `using X = Y` aliases). `using X.Y` names a *namespace* (a directory), not a file, so an edge resolves only when a matching `Y.cs` exists — full C# fan-in needs a namespace index |

Every resolver above resolves **only to a file that exists in the tree** and
skips (never fabricates) when the import names a package/namespace/gem/system
module with no single backing file — the same honest-skip contract as C/C++
angle-bracket includes.

> **Note on the long tail:** the coverage above is broad but not exhaustive —
> other tree-sitter-parseable code files may not have an import extractor yet.
> Rather than silently reporting zero imports for such a file, `imports://`
> prints a "code file(s) skipped — no import support for: …" note so a low count
> is never mistaken for a clean result. Likewise `?unused`, `?external`, and `check`
> (W-CAP-2, single-file and recursive) say "Unused imports not checked" for the 📦/📝 languages
> instead of reporting ✅ (metadata field `unused_not_checked_extensions`).

### Language-Specific Examples

#### Python

```bash
# Find unused imports
reveal 'imports://src?unused'

# Detect circular imports (common in Python)
reveal 'imports://src?circular'

# Example unused:
# from typing import Dict  # Never used
# import os  # Never used
```

#### JavaScript/TypeScript

```bash
# Find unused ES6 imports
reveal 'imports://src?unused'

# Example unused:
# import { useState } from 'react';  // Never used
# const _ = require('lodash');  // Never used
```

#### Go

```bash
# Find unused imports (Go compiler catches most)
reveal 'imports://cmd?unused'

# Example circular:
# package a imports package b
# package b imports package a
```

#### Rust

```bash
# Find unused use statements
reveal 'imports://src?unused'

# Example unused:
# use std::collections::HashMap;  // Never used
```

---

## Query Parameters

### Query Flags

Use `?flag` syntax for operations:

| Flag / Param | Description | Example |
|--------------|-------------|---------|
| `unused` | Find unused imports | `imports://src?unused` |
| `circular` | Detect circular dependencies | `imports://src?circular` |
| `violations` | Check layer violations | `imports://src?violations` |
| `rank=fan-in` | Rank all files by fan-in (importer count) | `imports://src?rank=fan-in` |
| `top=N` | Limit results for `?rank` (default: all) | `imports://src?rank=fan-in&top=20` |
| `entrypoints` | Files with fan-in=0 — entry points, scripts, or dead code; sorted by fan-out | `imports://src?entrypoints` |
| `components` | Per-directory cohesion + coupling scores; top bridge file | `imports://src?components` |
| `external` | Package table: unresolved (third-party or unresolved-local) and stdlib packages by use, the languages importing each, import statements per file (`external_packages`; the deps dashboard's table, now JSON) | `imports://src?external` |
| `importers` | Who imports what: on a file (or `=FILE`, relative to the path) each importer with its import line, scope and cascade stage (`via`); on a directory every module under it with its sorted importers | `imports://src/utils.py?importers` |
| `scope=root\|path` | `root` (default): resolve at the project root, rows under the path; `path`: the path itself is the scan root | `imports://src?rank=fan-in&scope=path` |
| `tests=include\|exclude` | Count importers under a test path (`path_utils.is_test_path`), or not | `imports://src?importers&tests=exclude` |
| `root=DIR` | Pin the scan root (must contain the path; not a filesystem/home/system root; a refused value is a warning) | `imports://src/app.py?importers&root=.` |
| `lazy=include\|exclude\|only` | Function-level (lazy) import edges: include them, exclude them (load-time edges only) or show only them. Default: `?circular` excludes, every other view includes | `imports://src?rank=fan-in&lazy=exclude` |
| `format=text\|json\|dot` | Output override for `?importers` on a directory: `dot` draws one importer -> module edge per listed importer as Graphviz | `imports://src?importers&format=dot` |
| `verbose` | Show everything instead of a summary: every file in a cycle group, all unused imports, all violations, every package (same as the CLI `--verbose`) | `imports://src?circular&verbose` |
| `max_files=N` | Source files the walk may keep (default 20000); a cut is `metadata.scan_budget.capped` and a `scan_capped` warning | `imports://.?importers&max_files=50000` |

**Note**: `unused`, `circular`, and `violations` are flags (no `=value` needed). `rank` and `top` take values.

**Where an answer is resolved**: at the project root the shared climb finds (`&root=`,
`.reveal.yaml` `root: true`, the nearest package marker, the VCS root, else the requested directory),
through the shared resolution cascade (also behind `?importers`: direct, PHP `define()` constants, namespaces,
members, Swift modules, Ruby Zeitwerk naming). Rows are the requested path's files; importers come from
anywhere under the root, so `imports://pkg?rank=fan-in` counts `tests/` and `scripts/` importers of
`pkg/core.py`. `&scope=path` resolves at the path itself (what `architecture://`, `overview://`, `pack` and
the architecture diff use). `edge_rule` adds `root` (relative to the path), `root_source`, `scope_param`,
`tests_param`, `via` (counted edges by stage) and `ungated_languages`/`ungated_edges` (languages no recall
oracle measures). Swift module and Zeitwerk convention edges count as importers but never close a cycle.

**How paths are spelled**: every path in an answer (rows, `resolved`, cycle members, components,
`metadata.files_failed`, `files_lost` and `extraction_diagnostics`, failed-directory warnings) is relative to
the requested directory, which for a file target is the file's own directory: `imports://pkg/a.py` names
itself `a.py`, a sibling `b.py` and a module above it `../top.py`. A file outside the requested path is
spelled with `../`, including a target outside a pinned `&root=` or a `&scope=path` root
(`../assets/x.css`). These fields never print a host path; a module the source itself writes as an absolute
path outside the project (`#include "/opt/vendor/x.h"`) is shown as written.

```bash
# Correct
reveal 'imports://src?unused'

# Also works (but unnecessary)
reveal 'imports://src?unused=true'
```

---

## CLI Flags

### Standard Flags

| Flag | Description | Example |
|------|-------------|---------|
| `--format=<type>` | Output format (text, json) | `reveal imports://src --format=json` |
| `--verbose` | Show detailed results | `reveal imports://src --verbose` |

### Examples

```bash
# Verbose unused imports
reveal 'imports://src?unused' --verbose

# JSON output for CI/CD
reveal 'imports://src?circular' --format=json

# Filter unused imports to one package
reveal 'imports://src?unused' | grep "api/"
```

---

## Output Types

### 1. imports

**Use case**: Repository import overview (the default result)

**Schema**:
```json
{
  "contract_version": "1.1",
  "type": "imports",
  "source": "src",
  "source_type": "directory",
  "files": {"src/app.py": [{"module": "os", "line": 1}]},
  "metadata": {
    "total_files": 45,
    "total_imports": 238,
    "has_cycles": true,
    "analyzer": "imports"
  }
}
```

### 2. unused_imports

**Use case**: Find dead code

**Schema**:
```json
{
  "contract_version": "1.1",
  "type": "unused_imports",
  "source": "src",
  "source_type": "directory",
  "count": 12,
  "unused": [
    {
      "file": "src/api/routes.py",
      "line": 3,
      "module": "typing.Dict",
      "names": ["Dict"],
      "type": "from_import",
      "is_relative": false,
      "alias": null
    }
  ],
  "metadata": {
    "total_imports": 238,
    "total_files": 45,
    "has_cycles": true
  }
}
```

`count` is statements, not names. For a partly-used `from x import a, b`, `names`
lists everything the statement imports and `unused_names` only what is never
referenced (`["b"]`). The decision is shared with rule I001
(`reveal/analyzers/imports/unused.py`), so `?unused` and `check --select I001`
flag the same lines: per-name for `from` imports, honoring `# noqa`,
`// eslint-disable`, `// nolint` and `#[allow(unused)]`, and skipping star/glob
imports, `TYPE_CHECKING` imports and names re-exported via `__all__` or an `__init__.py`.

### 3. circular_dependencies

**Use case**: Architecture health check

**Schema**:
```json
{
  "contract_version": "1.1",
  "type": "circular_dependencies",
  "source": "src",
  "source_type": "directory",
  "count": 3,
  "cycles": [
    ["src/models/user.py", "src/services/auth.py"],
    ["src/db/base.py", "src/db/models.py", "src/db/session.py"]
  ],
  "metadata": {
    "total_imports": 238,
    "total_files": 45,
    "has_cycles": true
  }
}
```

**Note**: `cycles` contains one entry per SCC (strongly-connected component).
Each inner array is the sorted list of files in that cycle group — no repeated
last node. `count` = number of distinct groups, not simple paths.

### 4. layer_violations

**Use case**: Clean architecture enforcement

**Schema**:
```json
{
  "contract_version": "1.1",
  "type": "layer_violations",
  "source": "src",
  "source_type": "directory",
  "violations": [
    {
      "from_file": "models/user.py",
      "to_file": "db/session.py",
      "layer": "domain",
      "reason": "domain layer cannot import from db"
    }
  ],
  "count": 1,
  "edge_rule": {"lazy": "include", "tests": "included", "text": "Rule: violations check static imports ..."},
  "metadata": {
    "total_imports": 238,
    "total_files": 45,
    "has_cycles": true
  }
}
```

`from_file` and `to_file` are relative to the path given to `imports://`; a violation carries no
line number. `edge_rule` states which edges were counted (abridged above).

### 5. fan_in_ranking

**Use case**: Architectural orientation — surface core abstractions and entry points

**Schema**:
```json
{
  "contract_version": "1.1",
  "type": "fan_in_ranking",
  "source": "src",
  "source_type": "directory",
  "total": 45,
  "entries": [
    { "file": "db/session.py", "fan_in": 18, "fan_out": 2 },
    { "file": "utils/__init__.py", "fan_in": 15, "fan_out": 3 },
    { "file": "main.py", "fan_in": 0, "fan_out": 3 }
  ],
  "metadata": {
    "total_imports": 238,
    "total_files": 45,
    "has_cycles": false
  }
}
```

**Fields**:
- `total` — total files in the ranked list (before any `?top=N` limit)
- `entries[].fan_in` — number of files that import this file (higher = more central)
- `entries[].fan_out` — number of files this file imports

---

### 6. entrypoints

**Use case**: Find where execution starts — CLIs, runners, scripts — and surface potential dead code

**Schema**:
```json
{
  "contract_version": "1.1",
  "type": "entrypoints",
  "source": "src",
  "source_type": "directory",
  "total_scanned": 45,
  "entries": [
    { "file": "main.py", "fan_out": 8, "is_test": false, "test_only_importers": 0 },
    { "file": "cli.py", "fan_out": 3, "is_test": false, "test_only_importers": 2 },
    { "file": "legacy_util.py", "fan_out": 0, "is_test": false, "test_only_importers": 0 }
  ],
  "edge_rule": {"lazy": "include", "tests": "importers_not_counted", "text": "Rule: fan-in counts static imports ..."},
  "metadata": {"total_files": 40, "scanned_files": 45}
}
```

**Fields**:
- `total_scanned` — total files analyzed (entrypoints are a subset)
- `entries[].is_test` — the file itself sits under a test path
- `entries[].test_only_importers` — how many files under test paths import it (they are not counted as importers, which is why a tested-only file still lists as an entry point)
- `metadata.total_files` counts files with an import extractor; `metadata.scanned_files` and `total_scanned` count every scanned code file, so the two differ on a tree with files in languages without import support
- `entries[].fan_out` — how many files this entry point imports (high = real entry point; zero = likely dead code or test scaffold)

**Note**: Files loaded via dynamic dispatch (plugin registries, `importlib`, etc.) appear here as false positives — they have fan-in=0 statically but are actively loaded at runtime.

---

### 7. components

**Use case**: Validate directory-as-component hypothesis — score how self-contained each directory is

**Schema**:
```json
{
  "contract_version": "1.1",
  "type": "components",
  "source": "src",
  "source_type": "directory",
  "total": 8,
  "components": [
    {
      "component": "utils",
      "files": 4,
      "internal": 6,
      "outgoing": 0,
      "incoming": 22,
      "cohesion": 1.0,
      "top_bridge": null
    },
    {
      "component": "api",
      "files": 12,
      "internal": 8,
      "outgoing": 14,
      "incoming": 3,
      "cohesion": 0.364,
      "top_bridge": "api/router.py"
    }
  ]
}
```

**Fields**:
- `total` — number of directories analyzed
- `components[].internal` — import edges where both source and target are in this directory
- `components[].outgoing` — import edges leaving this directory
- `components[].incoming` — import edges arriving from outside this directory
- `components[].cohesion` — `internal / (internal + outgoing)`; 1.0 = fully self-contained; 0.0 = all imports cross boundaries. `null` (text: `n/a`) when more than half the directory's files are in Go, Java, Kotlin, C#, Scala or Swift: files of one package or module use each other without an import, so `internal` would read ~0 whatever the structure. The row then carries `cohesion_reason`, the response carries one `cohesion_rule` sentence, and declined components sort after every measured one (never as 0.00). Other languages keep their number
- `components[].top_bridge` — file in this directory with the most outgoing cross-boundary edges (null if none)

**Scan root**: rows are the directories under the requested path (nested directories at any depth). Edges resolve at the project root (the default `&scope=root`), so scanning a subdirectory still sees absolute-package imports and importers from outside it. With `&scope=path` the subdirectory is the scan root and those edges are missed.

---

### 8. external_packages

**Use case**: Which third-party and stdlib packages the code imports, and how often (`?external`,
`reveal imports PATH --external`). This is the package table the retired `deps://` dashboard printed in
text only; `deps://` read it at `&scope=path`, so add that for its numbers.

```json
{
  "type": "external_packages",
  "total_imports": 3412,
  "total_files": 397,
  "internal_imports": 1479,
  "external_packages": [{"package": "kombu", "uses": 250, "languages": ["python"]}],
  "stdlib_packages": [{"package": "unittest", "uses": 97}],
  "top_importers": [{"file": "celery/app/base.py", "imports": 51}]
}
```

**Fields**: every import of the files under the path is classified on resolution truth first: relative,
resolved in the tree or a declared project namespace counts in `internal_imports`; stdlib needs a
language rule or marker (Python's list is never applied to another language); the rest is an unresolved
package, which may be third-party or an unresolved local. `top_importers` counts import statements per
file. `&tests=exclude` drops the files under a test path.

---

## Workflows

### Workflow 1: Clean Up Unused Imports

**Scenario**: Remove dead code and improve maintainability

```bash
# 1. Find unused imports
reveal 'imports://src?unused'

# 2. Review list (check for false positives)
reveal 'imports://src?unused' --verbose

# 3. Remove unused imports
# (manually or with automated tools)

# 4. Verify cleanup
reveal 'imports://src?unused'
# Should show: "✅ No unused imports found!"

# 5. Commit changes
git add -u
git commit -m "refactor: Remove unused imports"
```

**Expected result**: Zero unused imports

---

### Workflow 2: Detect and Fix Circular Dependencies

**Scenario**: Find and break circular import cycles

```bash
# 1. Detect circular dependencies
reveal 'imports://src?circular'

# Example output:
# 1. 2 files  user.py, auth.py   (add &verbose for the edge sequence: cycle: user.py → auth.py → user.py)

# 2. Analyze the cycle
reveal imports://src/models/user.py
reveal imports://src/services/auth.py

# 3. Identify the problematic imports
# - user.py imports auth.py for token generation
# - auth.py imports user.py for User model

# 4. Refactor to break cycle
# Option A: Extract interface
#   Create src/interfaces/user.py with User protocol
#   auth.py imports interface, not concrete model

# Option B: Dependency injection
#   Pass User model to auth functions as parameter

# Option C: Inversion
#   Move token generation from auth.py to user.py

# 5. Verify fix
reveal 'imports://src?circular'
# Should show: "✅ No circular dependencies found!"

# 6. Commit refactoring
git add -A
git commit -m "refactor: Break circular dependency between user and auth"
```

**Expected result**: Zero circular dependencies

---

### Workflow 3: Enforce Architecture Layers

**Scenario**: Ensure clean architecture with layer boundaries

```bash
# 1. Create .reveal.yaml with layer rules. Paths are prefixes relative to the path
#    passed to imports:// (here src/), and the rules live on each layer.
cat > .reveal.yaml <<EOF
architecture:
  layers:
    - name: presentation
      paths: [api, cli]
      allow_imports: [services, models]
    - name: application
      paths: [services]
      allow_imports: [models]
    - name: domain
      paths: [models]
      deny_imports: [api, cli, services, db]
    - name: infrastructure
      paths: [db]
      allow_imports: [models]
EOF

# 2. Check for violations
reveal 'imports://src?violations'

# Example output:
#   models/user.py -> db/session.py  [domain] domain layer cannot import from db

# 3. Fix violations
# - Move database logic from domain to infrastructure
# - Use dependency injection for database access
# - Refactor models to be pure business logic

# 4. Verify compliance
reveal 'imports://src?violations'
# Should show: "✅ No violations found"

# 5. Add to CI/CD (--fail-on findings exits 1 when a violation is found;
#    without it the command exits 0 and the step never fails)
cat >> .github/workflows/ci.yml <<EOF
  - name: Check architecture layers
    run: reveal 'imports://src?violations' --fail-on findings
EOF

# 6. Commit layer config
git add .reveal.yaml .github/workflows/ci.yml
git commit -m "feat: Add architecture layer enforcement"
```

**Expected result**: Zero layer violations

---

### Workflow 4: Codebase Health Check

**Scenario**: Comprehensive import analysis

```bash
# 1. Import overview
reveal imports://src

# 2. Check for unused imports
reveal 'imports://src?unused'

# 3. Check for circular dependencies
reveal 'imports://src?circular'

# 4. Generate health report
cat > import_health_report.md <<EOF
# Import Health Report - $(date +%Y-%m-%d)

## Overview
$(reveal imports://src --format=json | jq '.metadata')

## Unused Imports
$(reveal 'imports://src?unused' --format=json | jq '.count')

## Circular Dependencies
$(reveal 'imports://src?circular' --format=json | jq '.count')

## Status
$(reveal imports://src)
EOF

# 5. Address issues
# - Remove unused imports
# - Break circular dependencies
# - Fix layer violations

# 6. Track progress over time
# Save reports: import_health_report_YYYY-MM-DD.md
```

**Expected result**: Health report with metrics

---

### Workflow 5: CI/CD Integration

**Scenario**: Automated import quality checks

```bash
# .github/workflows/import-quality.yml
name: Import Quality

on: [push, pull_request]

jobs:
  import-quality:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Install reveal
        run: pip install reveal-cli

      - name: Check for unused imports
        run: |
          UNUSED=$(reveal 'imports://src?unused' --format=json | jq '.count')
          if [ "$UNUSED" -gt 0 ]; then
            echo "❌ Found $UNUSED unused imports"
            reveal 'imports://src?unused'
            exit 1
          fi
          echo "✅ No unused imports"

      - name: Check for circular dependencies
        run: |
          CYCLES=$(reveal 'imports://src?circular' --format=json | jq '.count')
          if [ "$CYCLES" -gt 0 ]; then
            echo "❌ Found $CYCLES circular dependencies"
            reveal 'imports://src?circular'
            exit 1
          fi
          echo "✅ No circular dependencies"

      - name: Check layer violations
        run: |
          if [ -f .reveal.yaml ]; then
            VIOLATIONS=$(reveal 'imports://src?violations' --format=json | jq '.count')
            if [ "$VIOLATIONS" -gt 0 ]; then
              echo "❌ Found $VIOLATIONS layer violations"
              reveal 'imports://src?violations'
              exit 1
            fi
            echo "✅ No layer violations"
          fi
```

**Expected result**: CI fails on import quality issues

The same gate without `jq`: `--fail-on findings` exits 1 when the `?circular`, `?unused` or `?violations`
answer has a row (an incomplete answer exits 3 first; the default `--fail-on none` exits 0):

```bash
reveal 'imports://src?circular' --fail-on findings
reveal imports src --unused --fail-on findings
```

---

### Workflow 6: Refactoring Safety Check

**Scenario**: Ensure refactoring doesn't introduce cycles

```bash
# Before refactoring
reveal 'imports://src?circular' > before_refactor.txt

# Perform refactoring
# - Move functions between modules
# - Reorganize imports
# - Rename modules

# After refactoring
reveal 'imports://src?circular' > after_refactor.txt

# Compare
diff before_refactor.txt after_refactor.txt

# If new cycles introduced:
if [ "$(cat after_refactor.txt | grep 'Circular Dependencies:' | awk '{print $3}')" -gt \
     "$(cat before_refactor.txt | grep 'Circular Dependencies:' | awk '{print $3}')" ]; then
  echo "❌ Refactoring introduced new circular dependencies!"
  reveal 'imports://src?circular'
  exit 1
fi

echo "✅ Refactoring did not introduce new cycles"
```

**Expected result**: No new circular dependencies

---

## Integration Examples

### Integration 1: Combine with jq

```bash
# Count unused imports by directory
reveal 'imports://src?unused' --format=json | \
  jq -r '.unused[] | .file | split("/")[0]' | \
  sort | uniq -c

# Find files with most unused imports
reveal 'imports://src?unused' --format=json | \
  jq -r '.unused[] | .file' | \
  sort | uniq -c | sort -rn | head -10

# List unused imports from specific module
reveal 'imports://src?unused' --format=json | \
  jq -r '.unused[] | select(.file | startswith("api")) | "\(.file):\(.line) - \(.module)"'

# Extract circular dependency chains
reveal 'imports://src?circular' --format=json | \
  jq -r '.cycle_paths[] | join(" -> ")'
```

### Integration 2: Automated Cleanup Script

```bash
#!/bin/bash
# cleanup-unused-imports.sh - Remove unused imports (Python)

set -e

echo "Finding unused imports..."
UNUSED=$(reveal 'imports://src?unused' --format=json)
COUNT=$(echo "$UNUSED" | jq '.count')

if [ "$COUNT" -eq 0 ]; then
  echo "✅ No unused imports found"
  exit 0
fi

echo "Found $COUNT unused imports"

# Group by file (paths are relative to the scanned directory, so run from there: cd src)
# Only whole-statement rows are safe to delete; partly-used `from x import a, b` rows keep their used names
UNUSED=$(echo "$UNUSED" | jq -c '{unused: [.unused[] | select((.unused_names // .names) == .names)]}')
FILES=$(echo "$UNUSED" | jq -r '.unused[] | .file' | sort -u)

for file in $FILES; do
  echo "Cleaning $file..."

  # Get unused lines for this file
  LINES=$(echo "$UNUSED" | jq -r ".unused[] | select(.file == \"$file\") | .line")

  # Remove lines (in reverse order to preserve line numbers)
  for line in $(echo "$LINES" | sort -rn); do
    sed -i "${line}d" "$file"
  done
done

echo "✅ Removed $COUNT unused imports"
echo "Run tests to ensure nothing broke!"
```

### Integration 3: Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit - Prevent commits with unused imports

echo "Checking for unused imports..."

UNUSED=$(reveal 'imports://src?unused' --format=json | jq '.count')

if [ "$UNUSED" -gt 0 ]; then
  echo "❌ Cannot commit: Found $UNUSED unused imports"
  reveal 'imports://src?unused'
  echo ""
  echo "Remove unused imports before committing:"
  echo "  reveal 'imports://src?unused'"
  exit 1
fi

echo "✅ No unused imports"
```

### Integration 4: Python Integration

```python
#!/usr/bin/env python3
import subprocess
import json
from pathlib import Path

def get_import_health(path='src'):
    """Get import health metrics using reveal."""
    result = subprocess.run(
        ['reveal', 'imports://' + path, '--format=json'],
        capture_output=True,
        text=True
    )
    return json.loads(result.stdout)

def get_unused_imports(path='src'):
    """Get unused imports."""
    result = subprocess.run(
        ['reveal', f'imports://{path}?unused', '--format=json'],
        capture_output=True,
        text=True
    )
    return json.loads(result.stdout)

def get_circular_dependencies(path='src'):
    """Get circular dependencies."""
    result = subprocess.run(
        ['reveal', f'imports://{path}?circular', '--format=json'],
        capture_output=True,
        text=True
    )
    return json.loads(result.stdout)

def generate_report(path='src'):
    """Generate import health report."""
    health = get_import_health(path)
    unused = get_unused_imports(path)
    circular = get_circular_dependencies(path)

    report = {
        'summary': health['metadata'],
        'issues': {
            'unused_count': unused['count'],
            'circular_count': circular['count']
        },
        'health_score': calculate_health_score(health, unused, circular)
    }

    return report

def calculate_health_score(health, unused, circular):
    """Calculate health score (0-100)."""
    total_imports = health['metadata']['total_imports']
    unused_count = unused['count']
    circular_count = circular['count']

    # Deduct points for issues
    score = 100
    score -= (unused_count / total_imports * 100) * 0.3  # 30% weight
    score -= min(circular_count * 10, 50)  # Max 50 points deduction
    return max(0, int(score))

if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else 'src'

    print(f"Analyzing {path}...")
    report = generate_report(path)

    print(f"\n{'='*60}")
    print(f"Import Health Report")
    print(f"{'='*60}\n")
    print(f"  Total Files:   {report['summary']['total_files']}")
    print(f"  Total Imports: {report['summary']['total_imports']}")
    print(f"  Unused:        {report['issues']['unused_count']}")
    print(f"  Circular:      {report['issues']['circular_count']}")
    print(f"  Health Score:  {report['health_score']}/100")
    print()

    if report['health_score'] < 70:
        print("⚠️ Import health needs attention")
        sys.exit(1)
    else:
        print("✅ Import health is good")
```

### Integration 5: Dependency Graph Visualization

```bash
#!/bin/bash
# visualize-imports.sh - Create import graph visualization

set -e

echo "Building import graph..."

# Get circular dependencies
reveal 'imports://src?circular' --format=json > cycles.json

# Generate GraphViz dot file
cat > imports.dot <<EOF
digraph imports {
  rankdir=LR;
  node [shape=box];

  // Nodes (files)
EOF

# Add nodes from cycles
jq -r '.cycles[][] | unique' cycles.json | sort -u | while read node; do
  echo "  \"$node\";" >> imports.dot
done

echo "" >> imports.dot
echo "  // Edges (imports)" >> imports.dot

# Add edges from cycles
jq -r '.cycle_paths[] | . as $cycle | range(0; length-1) | "\($cycle[.]) -> \($cycle[.+1])"' cycles.json | while read edge; do
  echo "  $edge [color=red];" >> imports.dot
done

echo "}" >> imports.dot

# Render to PNG
dot -Tpng imports.dot -o import_graph.png

echo "✅ Graph saved to import_graph.png"
```

### Integration 6: Multi-Language Analysis

```bash
#!/bin/bash
# analyze-multilang.sh - Analyze imports across languages

echo "Analyzing Python..."
reveal 'imports://src?unused' --format=json > python_unused.json

echo "Analyzing JavaScript..."
reveal 'imports://frontend/src?unused' --format=json > js_unused.json

echo "Analyzing Go..."
reveal 'imports://cmd?unused' --format=json > go_unused.json

# Aggregate results
cat python_unused.json js_unused.json go_unused.json | \
  jq -s '{
    total_unused: map(.count) | add,
    by_language: [
      {language: "Python", count: (.[0].count // 0)},
      {language: "JavaScript", count: (.[1].count // 0)},
      {language: "Go", count: (.[2].count // 0)}
    ]
  }'
```

---

## Performance & Best Practices

### Performance Characteristics

| Operation | Speed | Scalability |
|-----------|-------|-------------|
| Import extraction | Fast | Linear O(n) files |
| Graph construction | Fast | O(n) imports |
| Unused detection | Medium | O(n*m) cross-reference |
| Circular detection | Medium | O(n+e) graph traversal |
| Layer validation | Fast | O(n) imports |

### Performance Tips

1. **Scope analysis**
   ```bash
   # Good: Analyze specific directory
   reveal 'imports://src?unused'

   # Bad: Analyze entire project including tests, docs, etc.
   reveal 'imports://.?unused'
   ```

2. **Use JSON for large results**
   ```bash
   # Fast: JSON output, pipe to jq
   reveal 'imports://src?unused' --format=json | jq '.count'

   # Slow: Text output for 1000s of results
   reveal 'imports://src?unused'
   ```

3. **Cache results**
   ```python
   # Cache import graph (expensive to build)
   @cache(ttl=300)  # 5 minutes
   def get_import_health():
       return get_imports('src')
   ```

4. **Progressive checks**
   ```bash
   # Check overview first (fast)
   reveal imports://src

   # Then specific checks if needed
   if has_cycles; then
     reveal 'imports://src?circular'
   fi
   ```

### Best Practices

1. **Regular cleanup**
   - Run `?unused` weekly in development
   - Add to PR review checklist
   - Automate in CI/CD

2. **Monitor cycles**
   - Check `?circular` during refactoring
   - Track cycle count over time
   - Break cycles before they multiply

3. **Layer enforcement**
   - Define layers in `.reveal.yaml`
   - Add `?violations` to CI
   - Review violations during design

4. **Multi-language projects**
   - Analyze each language separately
   - Aggregate results for reporting
   - Use consistent tooling

---

## Troubleshooting

### Issue: "Path not found: src"

**Problem**: Directory doesn't exist or wrong path

**Solution**:
```bash
# Check path exists
ls -la src

# Use correct relative path
reveal imports://./src

# Or absolute path
reveal imports:///absolute/path/to/src
```

### Issue: No unused imports detected (but there are some)

**Problem**: Symbol extraction missed references

**Solution**:
```bash
# Check file is being analyzed
reveal imports://src --format=json | jq '.metadata.total_files'

# Verify import is actually unused (not in __all__)
grep -n "from module import unused" src/file.py
grep -r "unused" src/

# Report false negatives on GitHub
```

### Issue: Circular dependency not detected

**Problem**: TYPE_CHECKING imports are ignored (by design)

**Solution**:
```python
# These are NOT runtime cycles (ignored)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from module import Class

# This IS a runtime cycle (detected)
from module import Class
```

### Issue: Layer violations not working

**Problem**: No `.reveal.yaml` configuration

**Solution**:
```bash
# Create .reveal.yaml with layer rules
cat > .reveal.yaml <<EOF
architecture:
  layers:
    - name: presentation
      paths: [api]
      allow_imports: [models]
    - name: domain
      paths: [models]
      deny_imports: [api]
EOF

# Then run check
reveal 'imports://src?violations'
```

---

## Limitations

Required directory-enumeration failures appear in JSON warning metadata and once
in text across Imports query modes. Surviving imports remain available, but zero
observed cycles, unused imports or entry points cannot establish a clean graph.
Diagnostics identify failed directories; the number of missing files is unknown.
Missing resolution targets can hide edges even when the scanned source count is
unchanged. Known discovery loss prevents reading or writing the resolved graph
cache. Direct Imports retains its legacy exit behavior, so exit 0 alone does not
establish complete analysis.

Resolution lookup can retain gitignored directories and file-pattern-excluded
targets even though they are not source candidates. Explicitly excluded
directories and hard ignore/noise policies remain omissions by policy. A failure
in a required resolution subtree is distinct from an intentional omission.

The I002 check rule also discloses required source or resolution-target directory
loss, so an empty observed cycle list remains a scan-incomplete result. Known
discovery loss disables its disk backing. Partial graphs remain available within
the current invocation for per-file checks and disclosures; the next MCP request
discards that partial memo before validation, even when access recovered before
the previous request finished. Clean graphs retain validated warm reuse. These
stat fingerprints do not establish content identity or successful source reads;
private builders outside the host request boundary retain their invocation memo.

1. **Language support**
   - ✅ Fully supported (incl. `?unused`): Python, JS/TS, Go, Rust
   - 📦/📝 Every other language in [Supported Languages](#supported-languages): listing/graph only, `?unused` not checked
   - ⚠️ Partial: Dynamic imports (`__import__`, `require()`)
   - ❌ Not supported: Custom import mechanisms

2. **Dynamic dispatch (all languages)**
   - All query modes analyse static imports only — the graph is built from `import`/`require`/`use` declarations in source
   - Dynamic loading is invisible regardless of language: Python `importlib.import_module`, JS/TS `require()`/`import()`, Java `Class.forName`, Ruby `autoload`, plugin registries, CLI subcommand dispatch tables, etc.
   - **Effect on fan-in**: dynamically-loaded files show lower fan-in than their true importer count
   - **Effect on entrypoints**: dynamically-loaded files appear as false-positive entry points (fan-in=0)
   - **Effect on unused**: dynamically-imported symbols may be flagged as unused
   - **Effect on circular**: cycles that pass through a dynamic call are not detected
   - This is a fundamental property of static analysis, not a Reveal limitation specifically

3. **Type-only imports**
   - `TYPE_CHECKING` imports are not counted as cycles
   - `?unused` skips `TYPE_CHECKING` imports, names listed in `__all__` and lines marked `# noqa`

4. **Layer violations**
   - Requires `.reveal.yaml` configuration
   - Manual rule definition required (`allow_imports` / `deny_imports` per layer)
   - Violations carry no line number

5. **Performance**
   - Large codebases (10k+ files) can be slow
   - Unused detection is O(n*m) complexity
   - Consider scoping analysis to specific directories

6. **Re-exports**
   - `__all__` exports are correctly handled
   - `*` imports cannot be fully validated
   - May have false positives for barrel files

---

## Tips & Best Practices

### 1. Start with Overview

```bash
# Always check overall health first
reveal imports://src

# Then drill into specific issues
reveal 'imports://src?unused'
reveal 'imports://src?circular'
```

### 2. Use Verbose for Details

```bash
# Summary (first 10 results)
reveal 'imports://src?unused'

# Full list
reveal 'imports://src?unused' --verbose
```

### 3. Automate in CI/CD

```bash
# Add to .github/workflows/ci.yml
- name: Check import quality
  run: |
    reveal 'imports://src?unused' --format=json | jq -e '.count == 0'
    reveal 'imports://src?circular' --format=json | jq -e '.count == 0'
```

### 4. Track Metrics Over Time

```bash
# Daily import health snapshot
reveal imports://src --format=json | \
  jq '{date: now, files: .metadata.total_files, imports: .metadata.total_imports, cycles: .metadata.has_cycles}' \
  >> import_metrics.jsonl
```

### 5. Fix Cycles Immediately

```bash
# Don't let cycles accumulate
# Fix them as soon as they appear
reveal 'imports://src?circular'

# If found, refactor immediately:
# - Extract interface
# - Dependency injection
# - Inversion of control
```

### 6. Review Unused Before Removal

```bash
# Not all "unused" imports are truly unused
# Check for:
# - Re-exports (__all__)
# - Type hints (TYPE_CHECKING)
# - Side-effect imports

reveal 'imports://src?unused' --verbose | \
  grep -v "__all__" | \
  grep -v "TYPE_CHECKING"
```

### 7. Combine with Other Adapters

```bash
# Find complex files with circular dependencies
reveal 'ast://src?complexity>10' --format=json | \
  jq -r '.results[].file' | sort -u | while read file; do
    reveal "imports://src/$file"
  done
```

---

## Related Documentation

- **AST Adapter**: `AST_ADAPTER_GUIDE.md` - Code structure analysis (find complex code)
- **Metrics Adapter**: [METRICS_ADAPTER_GUIDE.md](METRICS_ADAPTER_GUIDE.md) - Codebase metrics and hotspots
- **Python Adapter**: `PYTHON_ADAPTER_GUIDE.md` - Runtime inspection
- **Reveal Overview**: `../../../README.md` - Full reveal documentation

---

## FAQ

### Q: How accurate is unused import detection?

**A**: Very accurate for most cases:
- ✅ Detects: `import os` (never used)
- ✅ Detects: `from typing import Dict` (never used)
- ✅ Skipped: `TYPE_CHECKING` imports, names listed in `__all__`, lines marked `# noqa`
- ❌ False negative: Dynamic imports (`__import__("module")`)

### Q: Can I ignore specific unused imports?

**A**: Yes, use comments:

```python
# Python
from module import unused  # noqa: F401

# JavaScript
import unused from 'module';  // eslint-disable-line no-unused-vars
```

### Q: Why are TYPE_CHECKING imports not flagged as unused?

**A**: `TYPE_CHECKING` imports are type hints only, not runtime dependencies. They don't cause circular dependencies and are intentionally ignored.

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from module import TypeOnly  # Not flagged as unused (correct)
```

### Q: How do I fix circular dependencies?

**A**: Three main approaches:

1. **Extract interface**: Move shared types to separate module
2. **Dependency injection**: Pass dependencies as parameters
3. **Inversion**: Make one module depend on abstraction

See [Workflow 2](#workflow-2-detect-and-fix-circular-dependencies) for detailed examples.

### Q: Can I use this on projects with multiple languages?

**A**: Yes! Analyze each language separately:

```bash
# Python
reveal 'imports://backend/src?unused'

# JavaScript
reveal 'imports://frontend/src?unused'

# Go
reveal 'imports://services/cmd?unused'
```

### Q: What about dynamic imports / lazy loading?

**A**: All query modes cover static imports only. Dynamic dispatch is not tracked in any language:

| Language | Not tracked |
|----------|-------------|
| Python | `importlib.import_module(x)`, `__import__(x)` |
| JavaScript/TypeScript | `require(variable)`, `import(variable)` |
| Java | `Class.forName(name)` |
| Ruby | `autoload`, `require variable` |
| Any | Plugin registries, CLI dispatch tables, framework loaders |

The practical effect: files loaded this way appear with lower fan-in than their true importer count, and show up as false positives in `?entrypoints`. This is a fundamental property of static analysis — every import analysis tool shares this limitation.

Every `?entrypoints` run ends with a reminder: `Note: static imports only — files loaded via dynamic dispatch (importlib, require(), Class.forName, autoload, etc.) are false positives here.` It does not say which files those are.

### Q: How often should I check import health?

**A**: Recommended schedule:
- **Weekly**: Manual check during development
- **Per PR**: Automated check in CI/CD
- **Monthly**: Comprehensive audit with reports

### Q: Can I configure layer rules per team/project?

**A**: Yes, use `.reveal.yaml` in each project root (the nearest one above the scanned path
applies). Each layer needs `allow_imports` (possibly `[]`) or a non-empty `deny_imports`; a layer with
only `paths` is an error. Paths below are for `imports://src?violations`:

```yaml
# Project A (microservice)
architecture:
  layers:
    - name: api
      paths: [api]
      allow_imports: [models]
    - name: domain
      paths: [models]
      deny_imports: [api]

# Project B (monolith)
architecture:
  layers:
    - name: presentation
      paths: [web, cli]
      allow_imports: [services, entities]
    - name: application
      paths: [services]
      allow_imports: [entities]
    - name: domain
      paths: [entities]
      deny_imports: [web, cli, services]
```

### Q: What if analysis is slow?

**A**: Optimize scope:

```bash
# Good: Specific directory
reveal 'imports://src?unused'

# Bad: Entire project
reveal 'imports://.?unused'

# Good: Exclude tests
reveal 'imports://src?unused'

# Bad: Include tests (often have many unused test fixtures)
reveal 'imports://src?unused' && reveal 'imports://tests?unused'
```

### Q: Can I get diffs between branches?

**A**: Yes, compare JSON outputs:

```bash
# Main branch
git checkout main
reveal 'imports://src?circular' --format=json > main_cycles.json

# Feature branch
git checkout feature/new-code
reveal 'imports://src?circular' --format=json > feature_cycles.json

# Compare
diff <(jq '.count' main_cycles.json) <(jq '.count' feature_cycles.json)
```

### Q: How do I integrate with pre-commit?

**A**: Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: check-imports
        name: Check import quality
        entry: bash -c 'reveal "imports://src?unused" --format=json | jq -e ".count == 0"'
        language: system
        pass_filenames: false
```

---

## Version History

- **v1.0** (2025-02-14): Initial comprehensive guide
  - All 4 output types documented
  - Multi-language support (Python, JS/TS, Go, Rust, Java, C++, etc.)
  - Unused import detection
  - Circular dependency detection
  - Layer violation checking
  - 6 complete workflows
  - Integration examples (jq, Python, CI/CD, pre-commit)
  - Performance optimization tips
  - 52 references consolidated

## See Also

- [GIT_ADAPTER_GUIDE.md](GIT_ADAPTER_GUIDE.md) - Git repository analysis
- [QUICK_START.md](../QUICK_START.md) - General reveal usage reference
