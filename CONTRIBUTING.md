---
title: Contributing to Reveal
type: documentation
category: contributing
date: 2026-01-20
---

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

## 🚀 Scaffolding System (New!)

**Generate production-ready components in seconds:**

```bash
# Generate new adapter (2-4 hours → 30 minutes)
reveal scaffold adapter github github://

# Generate new analyzer (1-3 hours → 20 minutes)
reveal scaffold analyzer kotlin .kt

# Generate new quality rule (2-3 hours → 30 minutes)
reveal scaffold rule C999 "excessive-nesting" --category complexity
```

Each command generates:
- Complete, tested implementation
- Comprehensive test suite (passing immediately)
- Documentation template
- Next steps guide

See the scaffolding commands (`reveal scaffold --help`) for full documentation.

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

**For maintainers:** Internal planning and research artifacts are kept outside this repository. This keeps the public repo clean and focused on the OSS project.

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
python -c "from tree_sitter_language_pack import get_language; get_language('lua')"
```

A new tree-sitter language must pass `tests/test_grammar_coverage.py`. It fails on every
control-flow node kind in the grammar (`if`/`for`/`switch`/`return`/... in the name) that
`reveal/core/node_taxonomy.py` does not classify. Add each such kind to its family there. If a
kind is not runtime control flow, list it in the test's `IGNORED` with the reason.

### 2. Add URI Adapters

Extend reveal to explore non-file resources (databases, APIs, cloud resources, etc.). See [ARCHITECTURE.md](ARCHITECTURE.md) for the full adapter lifecycle.

**Minimal working adapter:**

```python
# reveal/adapters/myscheme/adapter.py
from ..base import ResourceAdapter, register_adapter
from .renderer import MySchemeRenderer

@register_adapter('myscheme')
@register_renderer(MySchemeRenderer)
class MySchemeAdapter(ResourceAdapter):
    BUDGET_LIST_FIELD = 'items'   # field --max-items applies to; omit if not applicable

    def __init__(self, resource: str):
        self.resource = resource

    def get_structure(self, **kwargs) -> dict:
        # Required. Always include the four Output Contract fields.
        return {
            'contract_version': '1.0',
            'type': 'myscheme_overview',
            'source': f'myscheme://{self.resource}',
            'source_type': 'network',  # file | directory | database | runtime | network
            'items': [...],
        }

    @classmethod
    def get_schema(cls) -> dict:
        return {
            'adapter': 'myscheme',
            'description': 'Explores myscheme resources.',
            'uri_syntax': 'myscheme://<host>',
            'output_types': [{'type': 'myscheme_overview', 'description': 'Host overview'}],
            'query_params': {},
            'example_queries': [{'uri': 'myscheme://hostname', 'description': 'Overview',
                                 'output_type': 'myscheme_overview'}],
            'notes': ['Explores myscheme resources.'],
        }
```

**Single-file vs package layout**: `reveal/adapters/` mixes both shapes with no
enforced rule, which drifts (BACK-917). Use this one: package layout
(`reveal/adapters/<scheme>/` with `__init__.py`, `adapter.py`, `renderer.py`)
is the default for any new adapter — it's what `reveal scaffold adapter`
generates and what most existing adapters (`git/`, `nginx/`, `patches/`, ...)
use. A single file (`reveal/adapters/<scheme>.py`) is acceptable only when
you're confident the adapter will stay under ~300 lines with no dedicated
renderer logic worth separating (e.g. `depends.py`/`env.py` are legacy
single-files well past that line and are debt, not the pattern to copy —
see BACK-590).

**Adapter checklist** (full details in ARCHITECTURE.md):
1. Create `reveal/adapters/<scheme>/` with `__init__.py`, `adapter.py`, `renderer.py`
   — or `reveal scaffold adapter <scheme> <scheme>://` to generate it
2. Implement `get_structure()` with all four Output Contract fields
3. Implement `get_schema()` — required for `--discover` and contract compliance tests
4. Add `get_help()` or `reveal/adapters/help_data/<scheme>.yaml`
5. Add tests, and a row in `FIXTURE_URIS` in `tests/test_output_contract_compliance.py`
   (it fails until every registered adapter has one, or a `NOT_RUNNABLE` reason). That
   harness runs each adapter on a fixture and checks the Output Contract, that a missing
   resource is an error, that an `error` result exits nonzero, and that no absolute path
   leaks
6. Add `reveal/docs/<SCHEME>_ADAPTER_GUIDE.md` and link from `reveal/docs/INDEX.md`

**Simplest examples to study**: `adapters/git/adapter.py` (resource-arg init, package layout), `adapters/nginx/adapter.py` (domain-centric, package layout with a `handlers.py` split)

### 3. Other Contributions

- **Bug fixes** - See open issues
- **Performance** - Profile and optimize
- **Documentation** - Improve guides, add examples
- **Pattern detection** - Add new `--check` rules

### 4. Add New CLI Commands

**Note**: Most components (adapters, analyzers, rules) use auto-registration and don't need CLI wiring!

**Only needed for**: Top-level commands like `reveal scaffold`, `reveal stats`, etc.

```bash
# New top-level command example
reveal mycommand subcommand --flag
```

Complete guide covers:
- When CLI wiring is needed (vs auto-registration)
- Step-by-step integration instructions
- Patterns and examples
- Testing checklist
- Pit of success safeguards (M105 rule)

**Quick pattern**:
1. Create handlers in `reveal/cli/handlers_*.py`
2. Import in `reveal/main.py`
3. Create `_handle_*_command()` function
4. Wire into `main()` early
5. Add integration tests

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

**Text encoding (breaks on Windows only):** pass `encoding='utf-8'` to every text-mode
`open()` / `read_text()` / `write_text()` (`errors='replace'` when reading user files). Windows
defaults to cp1252, so a bare call passes on Linux/macOS and fails on Windows CI.
rule V041 in `reveal reveal:// --check` blocks new offenders (`python scripts/check_text_encoding.py --update-baseline` re-freezes the legacy count after a fix), and in `reveal/` a bare call fails the
test that reaches it under `PYTHONWARNDEFAULTENCODING=1` (CI and `ci-local.sh` set it). To
reproduce a Windows encoding bug on Linux, run under the cp1252 simulator:
`PYTHONUTF8=0 PYTHONPATH=scripts/cp1252_sim reveal check some.conf`.

**Shared infrastructure (call the seam, don't copy it):** walk the user's files through
`reveal.utils.path_utils` -- `_walk_code_files` (flat), `walk_tree` (prunable dirs,
`on_hidden` tally, `sort`), `walk_with_causes` (resolution index) or `list_dir` (a renderer that
recurses itself) -- never `os.walk`/`rglob`, and pick the walk's `WalkPurpose` (`ANALYSIS`,
`EVIDENCE` for project-wide facts that `--exclude` must not shrink, `RESOLUTION`, `DISPLAY`,
`DOCS`, see the `WalkPurpose` docstring) instead of adding skip rules at the call site. Keep `sys.exit`
in `reveal/cli/` and `print` in the rendering layer. A second walker is how `--exclude` and
`REVEAL_IGNORE` came to work on some commands and silently not on others.
`scripts/check_boundaries.py` counts these per file and fails on any increase; a walk over
something that is not the user's target (reveal's own docs, a cache) takes
`# boundary-ok: walker -- <why>`. Find a project's root with `path_utils.resolve_project_root`
(bounded, honors `.reveal.yaml root: true`) and the top of a Python package with
`python_package_top`; a rule that inspects reveal's own source gets it from
`rules/validation/utils.find_reveal_root`. Each of M102, B005 and three V-rules once climbed
on its own, and they disagreed (BACK-1372).

**Executable documentation:** `tests/test_example_recipes_run.py` runs offline
help recipes in JSON and their written text format. It preserves supported pipelines
and uses positive fixtures for claimed findings. The same harness inventories
AGENT_HELP and guide commands; discovery commands run now, while examples requiring
named target/session/host fixtures remain explicit skips. A successful empty query
is not evidence for a recipe that promises a match.

**Text rendering:** put new renderer implementations in `reveal/rendering/`. Extend
`BaseRenderer` and return a text body from `_render_text`; URI emission calls
`emit_rendered`, which prints returned bodies and their diagnostics exactly once. Keep
JSON at the shared format boundary. Legacy print renderers remain compatible during
migration. Use immutable `RenderOptions` and `capped_section` for bounded sections so
omitted rows have a remainder. Do not print a failed result as an empty success.
A renderer never exits: override `exit_code(result, format)` to report findings (a fleet audit
with gaps) and the URI seam acts on it after the render, and override `_failure_detail` to add
domain lines under the router's error line.
A file-flag handler (`adapters/nginx/handlers.py`) likewise returns a `FlagOutput` (stdout, stderr,
exit code) and `file_handler._write_flag_output` is the one place it is written and exited.
The shared failure guard retains distinct `message` details and `next_steps` on
stderr; the URI boundary owns the error line and exit code.

**Cached analysis:** store the complete analysis artifact, including diagnostic state,
before request-specific formatting. Import extraction uses `ImportExtraction`; graph builds
use `ImportAnalysis`. Do not cache a selected tuple of fields or report failures only during
a cold build. Compare cold, memory-hit and disk-hit diagnostics, and keep cached mutable
state isolated from callers. Old incomplete cache shapes must be treated as misses.

**Flags and query keys (use them, or let the ledger say so):** a URI adapter is told about
every flag and query key the user sets that its run never used
(`reveal/cli/routing/ledger.py`). An adapter needs no declaration for this. Two rules keep
it honest:
- Parse your query with `parse_query_params`, `parse_query_filters` or
  `parse_result_control`. A hand-written parser must call `note_query_parsed(query)`, or
  every key gets a "has no effect" note.
- In routing code, read a flag you might not apply with `peek(args, dest)`, and call
  `mark(args, dest)` once you have applied it or printed a note. A plain `args.x` read
  counts as used.

`tests/test_flag_ledger.py` runs every adapter with each probe flag, and fails when a flag
is neither honored nor named.

Subcommands (`reveal <name>`) get the same ledger and walk scope from
`reveal/cli/routing/subcommand.py`. A runner reads its flags from `args` as usual; a runner
that exits nonzero *after* printing its result (a findings exit code) calls
`complete(args)` first so the ledger still reports. A subcommand that walks a tree declares
`--exclude` with `add_exclude_argument(parser)` and never applies it itself: the seam
publishes it, with REVEAL_IGNORE, for every walker.

```python
# ❌ Zero-indexed lines (editors use 1-indexed)
{'line': 0, 'name': 'main'}

# ✅ 1-indexed lines
{'line': 1, 'name': 'main'}

# ❌ Silent error swallowing — makes debugging impossible
try:
    data = json.loads(content)
except:
    pass

# ✅ Catch specific exceptions; log at DEBUG so --verbose surfaces them
import logging
logger = logging.getLogger(__name__)
try:
    data = json.loads(content)
except json.JSONDecodeError as e:
    logger.debug("JSON parse failed for %s: %s", path, e)
    return {'error': 'Invalid JSON', 'detail': str(e)}

# ❌ Parsing query strings manually
params = {}
if '?' in resource:
    params = dict(p.split('=') for p in resource.split('?')[1].split('&'))

# ✅ Use the unified query parser (handles all operators: =, !=, >, ~=, ..)
from reveal.utils.query import parse_query_params
path, params = parse_query_params(resource)

# ❌ Missing Output Contract fields in adapters
return {'tables': [...]}

# ✅ Always include the four required fields
return {
    'contract_version': '1.0',
    'type': 'db_overview',
    'source': f'myscheme://{self.resource}',
    'source_type': 'database',
    'tables': [...],
}
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

**Before each commit, run the fast gates; GitHub CI is the full test gate:**

```bash
scripts/ci-local.sh --no-tests     # seconds: ratchets, lints, V-series, mypy (CI does not run mypy)
pytest tests/test_<what_you_touched>.py tests/test_flag_ledger.py tests/test_output_contract_compliance.py
```

Before a push, maintainers run `scripts/ci-local.sh --push` (~6 min: the lints and ratchets,
then the full suite on Python 3.12). Push to master, keep working, and let `scripts/ci-watch.sh`
wait for the run and print each job plus the failing tests: `test.yml` runs every Python version
on Linux, macOS and Windows (each Windows leg as two halves) plus the language-pack 1.8.1 floor;
the middle language-pack versions run weekly in `canary.yml`. A red master is fixed forward;
releases are cut from a tag only after CI is green (RELEASING.md). The rest of the local matrix
duplicates CI's Linux legs, so it is a tool to reproduce a CI failure or work offline, not a push gate:

```bash
scripts/ci-local.sh                # Python 3.12, latest deps: the CI-only steps, then pytest
scripts/ci-local.sh --matrix       # 3.10, 3.12, 3.14, then 3.12 @ the language-pack 1.8.1 floor (minutes per leg; use tmux)
scripts/ci-local.sh --matrix -- tests/test_foo.py   # only these tests, per leg
scripts/ci-local.sh --lp 1.8.1     # force a tree-sitter-language-pack version (CI's floor leg)
REVEAL_TEST_SHARD=1/2 pytest tests/  # one half of the suite, as a Windows CI leg runs it
```

Classes that pass a 3.12 run and fail elsewhere: 3.10 rejects PEP 701 f-strings (a nested
same-type quote), and 3.14 tokenizes t-strings natively. On the language-pack 1.8.1 floor
`node.start_byte` is a bound method, not a value, so a bare read passes everywhere but CI's compat
leg -- read Node accessors with `_zero_arg(node, 'start_byte')` (rule V040 in `reveal reveal:// --check`,
part of `--no-tests`, fails a bare read in seconds). The script's header also lists the Windows-only
pitfalls worth checking by hand.

Your dev environment drifts from CI (dependency versions, Python version, stale bytecode),
so a plain local `pytest` can pass while every CI job fails -- that is exactly how a
`Node.to_sexp()` call, present only on the older vendored tree-sitter node, broke CI. `ci-local.sh`
builds a dedicated venv under `~/.cache/reveal-ci/`, installs the way CI does, and also runs the
steps that are CI-only: the V-series self-validation (e.g. V004: every analyzer needs a test
file; V039-V042 lint Windows paths, floor-only tree-sitter accessors, text I/O encoding and POSIX-only env variables), the doc-hygiene ratchet, the B006 ratchet and the mypy ratchet (`scripts/check_mypy_baseline.py`, run on
system `python3` -- the interpreter its baseline was built with; CI does not run mypy). It cannot run Windows or macOS;
`reveal reveal:// --check` (rule V039) is the local guard for the Windows path class (`str(path)` uses
backslashes, so never split or compare paths as `'/'` strings).

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

> **Current roadmap**: See [ROADMAP.md](ROADMAP.md) for detailed status and priorities.

**Good first contributions:**
- More pattern detection rules (see `reveal/rules/` — run `reveal --rules` for the current count and categories)
- Language analyzer improvements (see `reveal/analyzers/`)
- Documentation fixes and examples
- Tests for edge cases in existing adapters

**Active backlog**:
- `reveal file.py :N` — extract the semantic unit at a given line number (BACK-099)
- `calls://?uncalled` — dead code detection (BACK-071)
- `imports://?violations` — architecture layer enforcement (BACK-100)
- nginx N008–N012 security rules

**Not planned**: See [ROADMAP.md — Explicitly Not Planned](ROADMAP.md#explicitly-not-planned)

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Questions?** Open an issue or discussion. PRs welcome!

Flag-ledger fixtures must contain enough matching data to exercise a cut or exclusion.
`tests/test_flag_ledger.py` uses ranking-mode calls, several dependency targets and
patch groups, and test files that contribute real edges. Its strict `KNOWN_SILENT`
list shrinks when these controls expose an effect. Read a query key only in the view
that applies it: the ledger can then name a bound such as `codex:// --since` that the
bare session-list view does not use.

The first `ParamSpec` pilot lives in `utils/query_parser.py` and patches' `limit`/`min`
controls. Frozen records derive numeric parsing, schema/default/zero-policy details
and CLI query fragments; call `read()` where the value is applied so schema discovery
never claims it as used. This pilot preserves legacy values, including negative
values; strict new bounds require a separate behavior change. Other fields still
use their established parser until migrated. `BudgetAccounting` in `query_control.py`
labels a count as scan, match, page or text. The existing page and text helpers use
it without changing their output; common scan-cap policy is a later migration.

Import graph discovery/resolution now has a public analysis-layer service in
`analyzers/imports/service.py`. Its frozen `ScanScope`, `ImportFileSet` and
`ResolutionContext` carry scan policy and resolution inputs explicitly. `discover`
uses the existing file-index walker; `resolve_graph` updates the complete
`ImportAnalysis` artifact. `resolve_primary` preserves imports' startup-cycle policy;
`resolve_targets` preserves depends' multi-target Python imports. Both use the same
extractor dispatch. Keep depends' namespace/member/module fallback policies explicit;
this first migration does not merge its full indexing engine or I002.
