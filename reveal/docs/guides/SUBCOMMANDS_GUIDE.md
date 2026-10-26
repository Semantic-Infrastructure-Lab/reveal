---
title: "reveal Subcommands"
type: guide
help_topic: subcommands
help_description: "High-level workflow subcommands (dev, health, pack, review, ...)"
help_category: feature_guides
---

# reveal Subcommands

Reference for reveal's top-level subcommands. These are high-level workflow commands distinct from URI adapters.

---

## reveal dev — Developer Tooling

Scaffolding and introspection tools for extending Reveal.

### Commands

```
reveal dev new-adapter NAME [--uri SCHEME]        # Scaffold a new URI adapter
reveal dev new-analyzer NAME [--ext EXT]          # Scaffold a new file analyzer
reveal dev new-rule CODE NAME [--category CAT]    # Scaffold a new quality rule
reveal dev inspect-config                         # Show effective .reveal.yaml config
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--uri SCHEME` | URI scheme for new adapter (e.g., `mydb`) |
| `--ext EXT` | File extension for new analyzer (e.g., `.myext`) |
| `--category CAT` | Rule category (bugs, maintainability, performance, etc.) |

### Examples

```bash
reveal dev new-adapter mydb --uri mydb        # Creates adapters/mydb/ scaffold
reveal dev new-analyzer toml --ext .toml      # Creates analyzers/toml.py scaffold
reveal dev new-rule M999 "Too Long" --category maintainability
reveal dev inspect-config                     # See config applied to current dir
```

### Scaffold Output

New adapters and analyzers are created in the current reveal source tree.
Rules are added to `reveal/rules/`.

### See Also

- `reveal help://scaffolding` — Full scaffolding guide
- `reveal help://adapter-authoring` — How to write adapters
- `reveal dev --help` — Full flag reference

---

## reveal review — Retired

`reveal review` is folded into `reveal check --changed RANGE` (the rule pass) and the
`diff://` adapter (the structural diff). It still answers as before, prints a
replaced-by note on stderr, and carries a `retired_spelling` entry in JSON
`meta.warnings`, until the cut release.

### Replacements

| Was | Now |
|-----|-----|
| the rule pass over a git range | `reveal check --changed main..feature` |
| the rule pass over a directory | `reveal check ./src` |
| the structural changes section | `reveal 'diff://git://main/.:git://feature/.'` |
| the hotspots section | `reveal hotspots <path>` |
| the complex-functions section | `reveal 'ast://<path>?complexity>10&sort=-complexity'` |

### Exit Codes

The retired command keeps its own table until the cut: `0` pass, `1` warn (only
`medium`/`low` violations), `2` fail (a `high` or `critical` violation) or an invalid
target (unknown revision, not a git repository, missing path), `3` incomplete (a
check crashed or skipped files, or the hotspot step could not rank some files). JSON
carries `overall_status` (`pass` / `warn` / `fail` / `incomplete` / `error`) and
`exit_code`. `reveal check --changed` uses `check`'s table instead: `0` clean, `1` any
finding, `2` an unusable range, `3` incomplete; `--fail-on none` reports findings
without failing.

### CI/CD Integration

```bash
# Fail on any finding in the files a PR changed
reveal check --changed main..HEAD

# The same gate written against the JSON
reveal check --changed main..HEAD --format json | jq -e '.summary.total_issues == 0'

# Fail on high/critical issues only
reveal check --changed main..HEAD --severity high
```

`jq -e` is what makes the jq line a gate: without it jq prints `false` and exits 0.

### See Also

- `reveal check` — Run quality rules on files, directories or a git range
- `reveal health` — Health check for services (ssl, domain, mysql, sqlite, nginx)

---

## reveal health — Ops Health Check

Health check across the operational resource types. Routes automatically based on
target type — no need to know which adapter to use. Code quality is `reveal check`:
a local code path still answers here until the cut, with a note naming `reveal check`.

### Usage

```
reveal health TARGET [TARGET ...]
reveal health --all
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--all` | Check `health.targets` from `.reveal.yaml` (without it, the detected source dir: a code path, so noted) |
| `--select RULES` | Rule categories for a code path (retired; use `reveal check --select`) |
| `--format json` | Machine-readable output |
| `--verbose` | Show detailed check results |

### Target Types (Auto-detected)

| Target | What it checks |
|--------|----------------|
| `site.conf` | nginx config health |
| `ssl://example.com` | SSL certificate validity, expiry, chain |
| `mysql://host` | MySQL connectivity, replication health |
| `domain://example.com` | DNS, registrar, HTTPS availability |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Every target checked and passed |
| `1` | A finding matches the gate (`--fail-on findings`, the default) |
| `3` | A check was lost: target not found, unsupported scheme, child error, signal, timeout or malformed answer |

`health` never exits 2. `--fail-on none` reports findings without failing. A lost
check is never reported as healthy: the text summary says `INCOMPLETE` and the JSON
carries `overall_exit: 3`. JSON also records an `outcome` for each file, directory or
URI target.

### Examples

```bash
reveal health ssl://example.com         # SSL cert health
reveal health domain://example.com      # Domain + DNS health

# Composable: check multiple targets
reveal health ssl://api.example.com mysql://localhost

# Configure targets in .reveal.yaml for `--all`:
# health:
#   targets: [src/, ssl://api.example.com]

# CI/CD: fail on warnings or failures
reveal health ssl://example.com --format json | jq -e '.overall_exit == 0'
```

### See Also

- `reveal check --changed RANGE` — Rules on the files a PR changed
- `reveal check` — Code quality rules
- `reveal health --help` — Full flag reference

---

## reveal pack — Token-Budgeted Context Snapshot

Creates a curated context snapshot: it picks the most important files whose raw size fits
a token budget. With `--content`, it also emits changed files raw and the reveal structure of
the key files, so an agent gets context without a second round of `Read` calls. The budget
bounds the files selected, not the output: the output is names plus structure, usually far
smaller than the budget.

### Usage

```
reveal pack PATH [--budget N] [--focus TOPIC] [--since REF] [--content] [--verbose]
```

`PATH` accepts a directory or a single file. For a file with `--since`, Git
discovery starts from its containing directory, while only that file remains
eligible for the pack. The changed-file count describes the repository diff;
other changed files are not added to a single-file selection.

### CLI Flags

| Flag | Description |
|------|-------------|
| `--budget N` | Token budget (e.g., `--budget 4000`). Default: 2000 |
| `--budget N-lines` | Line budget instead of tokens (e.g., `--budget 500-lines`) |
| `--since REF` | Boost files changed since `REF` (branch, commit, or `HEAD~N`) to top priority |
| `--focus TOPIC` | Emphasize files matching this name pattern (e.g., `--focus auth`), plus files structurally related to a match via the import/dependency graph (BACK-833: a personalized-PageRank relevance score, so a helper a matching file imports ranks above an unrelated file even without a name match) |
| `--content` | Emit content for the selected files: changed files raw (first 500 lines), key files as structure, the rest by name only |
| `--architecture` | Boost high fan-in (core abstraction) files; prepend architecture brief |
| `--verbose` | Show per-file token/line counts |
| `--format json` | Machine-readable output |

`--architecture` fan-in and `--focus` relevance read the import graph and state their rule: a `Rule:` line under
the header, `edge_rule` in JSON, and none when neither flag is given. Every static import edge except
`TYPE_CHECKING` ones counts, function-level imports and test importers included. `pack` takes no `&lazy`;
`imports://<dir>?rank=fan-in&lazy=exclude` is the load-time view.

### Discovery evidence

Actual candidate-directory enumeration failures appear in `meta.warnings` and in
human output for the CLI, URI and specialized MCP tool. Counts and rankings then
cover observed eligible files; the missing file population is unknown. Surviving
selected files and content remain available.

An empty selection with observed candidates can still reflect the budget. If no
candidates were observed under discovery loss, the text says the candidate population
is unavailable instead of attributing the empty result to the budget. This decision
uses candidate counts before budget and presentation cuts. Healthy empty scans and
intentional exclusions keep their existing behavior.

Pack retains its legacy exits and ordinary MCP responses, including under discovery
loss; inspect the warnings to distinguish that uncertainty. This disclosure does not
establish completeness of optional import-graph ranking or file reads and parsing.
URI requests support `--output json=PATH` artifacts and global field/item cuts; the native
Pack subcommand retains its existing supported flags.

### File measurements and budgets

Candidate stat or line-count read failures appear separately in `meta.warnings`
as `file_measurement_failed`, with file paths, operations and causes. A candidate
whose stat cannot be measured is omitted while healthy siblings remain available.
Counts then describe observed measured eligible candidates. If none can be
measured, text reports unavailable measurements rather than budget exclusion.
Independent directory and file-measurement warnings remain visible together.

A readable stat still supplies the approximate token cost when the line count
is unavailable. Machine consumers should handle these loss-only values:

| Field | Meaning under measurement loss |
|-------|--------------------------------|
| `files[].lines: null` | This selected file's line count is unavailable. |
| `meta.used_lines: null` | A token-budget selection contains an unknown line count; no complete selected line total is available. |
| `meta.line_budget_incomplete: true` | Line-budget selection omitted candidates whose line costs were unavailable. |

Token budgets can still select a file with unknown lines using its stat-derived
cost. If the token budget omits that file, it does not make the selected healthy
files' line total unknown. Line budgets conservatively skip unknown costs and
retain the exact line total of the known-cost files selected. Skipped-file text
distinguishes budget exclusion from unavailable line costs.

Healthy JSON values remain unchanged. Genuine zero-byte files and readable files
with no final newline retain the existing cost rules. Text shows unknown line
measurements explicitly; it does not substitute a zero or known subtotal.
These cases retain legacy CLI exit 0 and ordinary MCP responses. Candidate
measurement loss does not imply that a separate requested content read failed.

### Priority Algorithm

Files are scored and selected in this order:

1. **Changed files** (when `--since` is used) — files in `git diff --name-only <ref>...HEAD`, boosted above all else
2. **Entry points** — `main.py`, `app.py`, `index.js`, the root config file (`package.json`, `pyproject.toml`, ...)
3. **`--focus` matches** — files whose path contains the topic, then files tied to them by imports
4. **Key directories** — `api/`, `core/`, `models/`, `auth/`, `routes/`, ... and, with `--architecture`, widely imported files
5. **Other files** — fill the remaining budget; tests, vendor code and docs rank last

Ties go to the most recently modified file. There is no complexity term in the score.

Near-empty files (e.g., stub `__init__.py`) are excluded automatically.

### Optional graph ranking

Fan-in and focus graph relevance are additive ranking signals. When their
Imports graph carries native directory or file-integrity diagnostics, Pack
rejects that partial numeric input and uses filename/entry-point heuristics and
recency instead. `meta.relevance_warning` retains the requested root and original
causes, explaining that the signals were not computed completely. In text output, the
command and the URI both print this advisory notice on stderr; JSON carries it in meta. Primary candidate measurements and selected
content remain available, with exit 0; an unusable `--since` ref is advisory in the
same way, with its cause in `meta.since_error`.

Lost candidate discovery or file measurement is different: Pack exits 3 (incomplete, or
failed when no candidate survived) on the command and the URI, and the generic MCP tool
returns the attributed cause as an error only when nothing survived. The check uses the
uncapped candidate counts, so `--budget`, `--fields` and `--max-items` cannot hide it.

The specialized `reveal_pack` MCP tool runs the same declared path, so
`architecture` and `focus` build the same optional graph signals, a requested signal
that could not be built is named in its text, and a total loss of candidates is a tool
error. Its defaults remain 8000 tokens with content enabled, compared with the CLI/URI
defaults of 2000 tokens and content disabled, and it keeps its own text layout.
These presentation differences remain separate from candidate-measurement diagnostics. Native integrity notes do not
establish completeness of every parser, file-read or dynamic-import channel.

### Examples

```bash
reveal pack .                              # Default 2000-token budget
reveal pack . --budget 4000              # Larger budget
reveal pack . --budget 500-lines          # Line-based budget
reveal pack . --focus auth                # Emphasize auth module
reveal pack ./src --budget 8000 --verbose # Show per-file token counts
reveal pack . --content                   # Structure content, not just file list
reveal pack src/ --since main --content --budget 8000  # Full agent context: changed + structure
reveal pack src/ --since main --budget 8000    # PR context: changed files first (manifest only)
reveal pack src/ --since HEAD~3 --budget 4000  # Since 3 commits ago
reveal pack . --architecture              # Boost core abstractions; show architecture hint
reveal pack . --format json               # For agent consumption

# pack:// is also a queryable URI in its own right (BACK-961)
reveal 'pack://.?budget=4000'
reveal 'pack://.?since=main&content=true'
```

### Agent-Ready Output with --content

Without `--content`, pack outputs a file manifest — which files are most important. Agents still have to read those files themselves.

With `--content`, pack adds a content section after the manifest. Each selected file is shown
by tier: a changed file raw (first 500 lines), a key file as its reveal structure, and the
remaining selected files by name only. A small directory can have no key files, and then the
section is names only.

```
Pack: src/  [~8000 tokens budget]  [since main]
Changed files: 3 (boosted to top priority)
Selected 12 of 47 files (~7340 tokens, 892 lines)

── Changed files (since main) ──
  auth.py
  ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTENT  (changed=full · key files=structure · low priority=names)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

── auth.py  ◀ CHANGED (full content) ──
import hashlib
...

── models/user.py ──
File: user.py (3.2KB, 94 lines)
Imports (3): ...
Functions (4): authenticate_user, refresh_token, ...

── Low-priority files (selected, structure omitted) ──
  utils/strings.py
```

### JSON Output for Agents

```bash
# File list only (for targeted Read calls):
reveal pack . --budget 8000 --format json | jq '.files[].relative'

# Structure content in JSON (agent-consumable):
reveal pack . --budget 8000 --content --format json
```

Without `--content`: top-level JSON keys: `path`, `budget`, `since`, `meta`, `files`.
With `--content`: also includes `content` — a list of `{file, changed, content_type, content}` dicts, where `content_type` is `full`, `structure` or `name_only`, plus `error` when a file could not be read or analyzed.

### See Also

- `reveal check --changed RANGE` — Rules on the files a PR changed
- `reveal pack --help` — Full flag reference

---

## reveal calls — Cross-File Call Graph

The `calls://` adapter as a subcommand: the flags are generated from the same parameter
declarations as the URI's query keys, and both spellings run through one execution path, so
`reveal calls src --callers helper` and `reveal 'calls://src?callers=helper'` print the same answer
(JSON equal, same exit code). The retired `--target`/`?target=` and `--root`/`?root=` still answer,
with a note naming `--callers` and `--callees NAME --depth N` ([retired spellings](../adapters/CALLS_ADAPTER_GUIDE.md#retired-spellings)).

### Usage

```
reveal calls [PATH] --callers NAME [--depth N]
reveal calls [PATH] --callees NAME|FILE:NAME [--depth N] [--detail] [--builtins]
reveal calls [PATH] --rank callers [--top N] [--builtins] [--test-framework]
reveal calls [PATH] --modules [--external]
```

### CLI Flags

| Flag | URI key | Description |
|------|---------|-------------|
| `--callers NAME` | `callers` | Who calls NAME (reverse lookup); a bare NAME (`FILE:NAME` exits 2). `PATH:NAME` as the path is shorthand when no other mode is given |
| `--target NAME` | `target` | Retired name of `--callers`: the same mode and answer, with a note |
| `--callees NAME` | `callees` | What every definition of NAME (or `FILE:NAME`, one file's) calls (builtins hidden); with `--depth 2-5` a level-by-level walk, each definition expanded once at its shallowest level |
| `--detail` | `detail` | With `--callees`: params and effects of every definition reached; any other mode exits 2 |
| `--root NAME` | `root` | Retired: `--callees NAME --depth N` is the same walk (`--root` defaulted to depth 2); prints a note |
| `--depth N` | `depth` | Signed whole integer, clamped 1–5: callers levels (default 1), callee walk levels for `--callees` (default 1) and the retired `--root` (default 2); other modes ignore it with a warning |
| `--rank callers` | `rank=callers` | Rank every function by caller count |
| `--top N` | `top` | Entries for `--rank` (default 10) or the retired `--uncalled` (default all); 0 = all; negative values reject |
| `--uncalled` | `uncalled` | Retired (D8): functions/methods with no callers; `--callers NAME` for one function, the language's own tool for a project-wide list; prints a note and no confidence |
| `--type KIND` | `type` | With the retired `--uncalled`: `function` (module-level only) or `method` |
| `--modules` | `modules` | Retired: module graph, one edge per import under PATH (`reveal imports PATH --importers --scope path`); prints a note |
| `--external` | `external` | Retired, with `--modules`: importers from the whole project root (`reveal imports PATH --importers`) |
| `--builtins` | `builtins` | Include language builtins in callees (every depth), the retired root and rank output |
| `--test-framework` | `test-framework` | Count test-framework entrypoints (rank callers, and the retired `--uncalled`) |

`?format=dot` (Graphviz) has no subcommand spelling; `--format` takes `text` or `json`.
`--all`/`--limit` lift or set `top` on the URI only; the subcommand takes `--top N`.

Exactly one mode per request: two modes (for example `--callers a --callees b`, or `--callers a
--target a`) exit 2 and name both, where the URI used to answer one of them silently; so does the
`PATH:NAME` shorthand with an explicit mode. A name is never coerced (`--callers 123` looks for the
name `123`), and a malformed value exits 2 naming the parameter (`--depth abc`, `--top -1`,
`--rank often`, `--callers a.py:f`, `--detail` without `--callees`). Exits follow the declared-noun
policy: 0 complete; 2 rejected before analysis (bad request, no mode, missing path), or a name that
names nothing in PATH (`--callees`: no definition; `--callers`: no definition and no call site; the
empty answer is still printed); 3 required analysis or output incomplete (a file or directory could
not be read: the answer is still printed with the warning). `--fail-on` accepts `none` only.

A callee walk beyond depth 1 and `--detail` are not measured in any language: the answer carries
W-CALLS-9 and its `walk_rule` (a `Rule:` line in text) says `beyond_depth_1: false, detail: false`.
A language in PATH that yields call sources and has no recall snapshot (Elixir, Objective-C)
withholds the confidence and is named (W-CALLS-10); shell, SQL and other files with no call edges do not.
The retired `?uncalled` withholds it in every language (W-CALLS-11 also names the measured precision for JavaScript, TypeScript, TSX, Java and PHP).

A directory named `calls` in the current directory is shadowed by the verb: `reveal calls`
prints `note: ./calls/ exists — use ./calls or calls/ to target it`; `reveal calls/` is the path.

### Examples

```bash
reveal calls src --callers validate_item           # who calls validate_item?
reveal calls src --callers process --depth 2       # callers of callers
reveal calls src --callees validate_item           # what it calls
reveal calls src --callees main --depth 3 --detail # what that calls, 3 levels, params/effects
reveal calls src --rank callers --top 20           # most-called functions
reveal imports src --importers --scope path        # was: reveal calls src --modules (module graph)
```

### Side-effect tags

With `--detail` each reached definition lists its classified side effects:

| Tag | Meaning |
|-----|---------|
| `db` | Database call |
| `http` | Outbound HTTP |
| `cache` | Cache read/write |
| `file` | Filesystem I/O |
| `log` | Logging call |
| `sleep` | Blocking sleep |
| `env` | Environment/config read |
| `hard_stop` | Process exit: `sys.exit`/`os._exit`, PHP `exit`/`die` (a `raise` is not a side effect) |

### See Also

- [CALLS_ADAPTER_GUIDE.md](../adapters/CALLS_ADAPTER_GUIDE.md) — the full parameter and output reference
- `reveal calls --help` — Full flag reference

---

## reveal trace — Retired (use `reveal calls --callees`)

`reveal trace` and `trace://` are retired: trace merged into `reveal calls`, whose callee walk they
already answered from. Until the cut release they still print trace's frames (text and JSON, the
same exits: 0 complete, 2 invalid input or a proven absent root, 3 incomplete), with one note on
stderr and a `retired_spelling` entry in JSON `meta.warnings`. The MCP tool `reveal_trace` keeps its
name for now.

| Retired | Use instead |
|---------|-------------|
| `reveal trace PATH --from FUNC [--depth N]` | `reveal calls PATH --callees FUNC --depth N --detail` (trace's default depth was 2) |
| `reveal 'trace://PATH?from=FUNC&depth=N'` | `reveal 'calls://PATH?callees=FUNC&depth=N&detail'` |
| `--from FILE:FUNC` | `--callees FILE:FUNC` |

`--detail` adds each reached definition's `params:` and `effects:`; the effect tags are listed in
[the calls section](#side-effect-tags).

---

## reveal contracts — Contract & Seam Inventory

Find all architectural contracts in a codebase: ABCs, Protocols, TypedDicts, `@dataclass` classes, Pydantic BaseModels, and path-heuristic base classes. Lists abstract methods per contract and which classes implement each one.

### Usage

```
reveal contracts [PATH] [--abstract-only] [--no-implementations] [--impls N] [--format FORMAT]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--abstract-only` | Show only ABCs and Protocols; skip TypedDicts, dataclasses, path-heuristic |
| `--no-implementations` | Skip showing which classes implement each contract |
| `--impls N` | Implementers per contract in text (default 5; 0 displays all); JSON arrays remain complete |
| `--output json=PATH` | Write the complete JSON result alongside text output; `--output text=PATH` writes the text render beside a JSON stdout, and the flag repeats for several files |
| `--fail-on none` | Default policy; required analysis/output failures still exit 3 |
| `--format` | `text` (default), `json` |

### Examples

```bash
reveal contracts ./src               # All contracts in src/
reveal contracts .                   # Entire project
reveal contracts . --abstract-only   # Only ABCs and Protocols
reveal contracts . --format json     # Machine-readable output
reveal contracts . --impls 0          # Display every implementer
```

Both spellings share declared controls and answers. `--no-implementations`
matches `?implementations=false`; `--impls 3.0` matches `?impls=3.0` as 3.
Boolean controls reject unrecognized values. Implementer limits reject booleans,
negative/fractional values and scientific notation. Complete answers exit 0;
invalid requests exit 2; required missing analysis or output failures exit 3.
Recovery retains surviving contracts and exits 3. Empty/unsupported inventories
remain complete. See [the adapter guide](../adapters/CONTRACTS_ADAPTER_GUIDE.md)
for resource encoding and legacy batch boundaries.

### See Also

- `reveal surface` — External boundary map (HTTP routes, env vars, etc.)
- `reveal contracts --help` — Full flag reference

---

## reveal surface — External Boundary Map

Map every external surface the system touches: CLI arguments, HTTP routes, MCP tool registrations, environment variables, network I/O, database/SDK imports, and filesystem writes. Answers "what does this system touch outside itself?"

### Usage

```
reveal surface [PATH] [--type TYPE] [--format FORMAT]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--type TYPE` | Filter to one surface type (see table below) |
| `--top N` | Show only the top N entries per surface type (default: all) |
| `--source-only` | Exclude test files/dirs (`test_*.py`, `tests/`, `*.spec.ts`, etc.) |
| `--by dir` | Per-directory counts by category (which layer owns which boundary); `--top N` then caps directories |
| `--depth N` | With `--by dir`: roll directories up to their first N path segments (default 0: full directory) |
| `--format` | `text` (default), `json` |

### Surface Types

| Type | What it finds |
|------|--------------|
| `cli` | CLI arguments (`argparse`, `click`) |
| `http` | HTTP route handlers (Flask/FastAPI decorators) |
| `mcp` | MCP tool registrations |
| `env` | Environment variable reads (`os.getenv`, `os.environ.get`) |
| `network` | Outbound network imports (`requests`, `httpx`, etc.) and socket clients (Go `net.Dial`, Rust `TcpStream`, C# `TcpClient`, ...) |
| `fs` | Filesystem writes (`open(…,'w')`, `Path.write_text`) |
| `db` | Database/ORM imports |
| `sdk` | Third-party SDK imports |
| `subprocess` | Process spawns (`subprocess.run`, Go `exec.Command`, Java `ProcessBuilder`, C `system`/`popen`, ...) |

A category a language does not implement yet is reported as "not implemented", not as 0; `--format json` carries the full language × category `matrix`.

### Examples

```bash
reveal surface ./src                 # All surfaces in src/
reveal surface .                     # Entire project
reveal surface . --type env          # Only env var reads
reveal surface . --type http         # Only HTTP route handlers
reveal surface . --format json       # Machine-readable output
```

### Known Limitations

- **`env` type false positives (BACK-250):** Any dict `.get()` call (`cache.get("key")`, `config.get("val")`) is currently misclassified as an environment variable read. Until fixed, `--type env` output will be noisy on codebases that use dict `.get()` heavily. Cross-check with `grep -r 'os.getenv\|os.environ' <path>` to identify true env var reads.
- **Python-only** — surface scans `.py` files only.

### See Also

- `reveal contracts` — Architectural contracts (ABCs, Protocols, TypedDicts)
- `reveal surface --help` — Full flag reference

---

## reveal hotspots — Complexity Hotspot Finder

Identifies high-complexity files and functions that need the most attention.
Surfaces the worst 10 (or N) files by cyclomatic complexity.

### Usage

```
reveal hotspots [PATH] [--top N] [--min-complexity N]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--top N` | Retained items per ranking, including JSON (default: 10; 0 = all; negative rejects) |
| `--min-complexity N` | Signed whole-valued minimum complexity to report (default: 10) |
| `--functions-only` | Show only complex functions, skip file-level hotspots |
| `--files-only` | Show only file-level hotspots, skip function analysis |
| `--format json` | Machine-readable output |

Both spellings return `hotspots_scan` and default to `--fail-on none` (completed
findings exit 0). `--fail-on findings` exits 1 for file quality below 70 or function
complexity above 20 using evidence before ranking/field cuts. Invalid requests
exit 2; incomplete required analysis or requested output failure exits 3. Numeric
controls accept whole decimal/scientific values and reject fractions/booleans.
`--verbose` lifts ranking caps for text and JSON in either transport. CLI `--all`
is rejected; URI `--all` expands only without explicit `top`.

### Test Coverage Heuristic

Complex functions in hotspot output include a test-coverage indicator:

- **✅** — a `test_<func>` function exists in `tests/`/`test/`/`spec/`, **or** a `test_<module>.py` file covers the module (e.g. `test_liquidity_sweep.py` covers any function in `liquidity_sweep.py`)
- **⚪** — neither match found; the function may still be tested indirectly

JSON output (`--format json`) includes `has_test_hint: true/false/null` per function (`null` = unknown for that language, not untested), enabling scripted filtering:

```bash
reveal hotspots . --format json | jq '.function_hotspots[] | select(.has_test_hint == false and .complexity > 15)'
```

### Examples

```bash
reveal hotspots ./src              # Hotspots in a directory
reveal hotspots .                  # Entire project
reveal hotspots ./src --top 20     # Show top 20 files
reveal hotspots . --format json    # Machine-readable output
reveal hotspots . --functions-only # Only show complex functions
reveal hotspots . --files-only     # Only file-level view
```

### See Also

- `reveal check` — Full quality rules (not just complexity)
- `reveal check --changed RANGE` — Rules on the files a PR changed
- `reveal hotspots --help` — Full flag reference

---

## reveal overview — Codebase Dashboard

One-glance dashboard synthesising stats, language breakdown, quality pulse, top
hotspots, complex functions, architecture overview (entry points, core
abstractions, component cohesion, circular count), and recent git activity into
a single view. Its architecture section states the rule it counted by (`Rule:` lines in text, `edge_rule` in
JSON under `architecture`): every static import edge except `TYPE_CHECKING` ones, function-level imports
included; circulars use the load-time view. `overview` takes no `&lazy`; `imports://<dir>?rank=fan-in&lazy=exclude`
is the load-time view.

### Usage

```
reveal overview [PATH] [--top N] [--no-git] [--no-imports] [--all] [--fail-on none]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--top N` | Items to show per section (default: 5) |
| `--no-git` | Skip the recent git activity section |
| `--no-imports` | Skip the Architecture section (import graph analysis) |
| `--all`, `--verbose` | Expand analysis and text rankings, overriding explicit top |
| `--fail-on none` | Default and only policy; required failures still exit 3 |
| `--format json` | Machine-readable output |

### Examples

```bash
reveal overview                      # Current directory
reveal overview ./src                # Specific directory
reveal overview . --top 10           # 10 items per section
reveal overview . --no-git           # Skip git history
reveal overview . --format json      # Machine-readable output
```

Direct `overview` and `overview://` return the same `overview` answer. Completed
work exits 0; invalid resources/parameters exit 2; required child analysis or
requested output failure exits 3. There is no adverse-findings gate. Whole-valued
top spellings such as `3.0` and `3e0` normalize; negative values, fractions and
booleans reject. With neither expansion flag, top0 retains all Stats hotspots but
zero complex-function/Git entries. URI query exclusions preserve their existing
Stats/scope/Imports scope; global `--exclude` also filters AST complex functions.

### See Also

- `reveal hotspots` — Deep dive into complexity hotspots
- `reveal imports --external` — Third-party and stdlib packages (`--circular`, `--unused`)
- `reveal overview --help` — Full flag reference

---

## reveal architecture — Architectural Brief

Targeted architectural briefing for a directory. Answers "what do I need to
know before editing this code?" Composes entry points, core abstractions,
component cohesion, circular dependency groups, and derived risks into one
output. Designed for agent consumption and subdirectory targeting.

### Usage

```
reveal architecture [PATH] [--top N] [--no-imports | --against REF] [--format json]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--top N` | Items per section and complexity analysis population (default: 5; ordinary `top*4`, diff `max(top,1)*4`) |
| `--no-imports` | Skip import graph analysis |
| `--against REF` | Return `architecture_diff` against a Git ref; rejects explicit no-imports/verbose |
| `--format json` | Machine-readable output: `{path, facts, risks[], next_commands[]}` |

### Output Sections

- **Entry Points** — files with fan-in=0, sorted by fan-out (active callers of other code)
- **Core Abstractions** — files most imported by others (high fan-in)
- **Components** — directory cohesion bars
- **Risks** — derived from findings: circular groups, high-complexity entry points, load-bearing files
- **Next Commands** — specific `reveal` follow-up commands generated from what was found

Every count states its rule (`Rule:` lines in text, `edge_rule` and `edge_rule_sections` in JSON): every static
import edge except `TYPE_CHECKING` ones, function-level imports included (entry points ignore importers under a
test path); cycles use the load-time view. `architecture` takes no `&lazy`; `imports://<dir>?rank=fan-in&lazy=exclude`
is the load-time view. `--against` prints the rule once for both snapshots.

### Examples

```bash
reveal architecture src/            # Brief for a specific directory
reveal architecture .               # Whole project
reveal architecture src/ --format json  # Machine-readable for agents
reveal architecture src/ --no-imports   # Skip import analysis (faster)
reveal architecture src/ --against main --format json
reveal 'architecture://src?against=main' --format json
```

The two spellings share answers and support human output with `--output json=PATH`.
Architecture exits 0 for completed answers, 2 for invalid requests and 3 for
required analysis/output failure or missing evidence. `--fail-on none` retains
required failures; no adverse-risk gate is declared. Ordinary verbose expands
both analysis and text. See [the adapter guide](../adapters/ARCHITECTURE_ADAPTER_GUIDE.md)
for URI encoding, scope and completeness rules.

### Notes

Static imports only — dynamically loaded files (plugins, registries) may appear
as entry points. High entry point counts often indicate dynamic loading patterns.

### See Also

- `reveal overview` — Full codebase health dashboard (stats, quality, git)
- `reveal imports --external` — Third-party and stdlib packages (`--circular`, `--unused` for the rest of dependency health)
- `reveal architecture --help` — Full flag reference

---

## reveal deps — Dependency Health Dashboard (retired: use reveal imports)

`reveal deps` and `deps://` are retired spellings: each prints a replaced-by note and still answers with its
old shape (`deps_scan`) and exit codes until the cut. Their sections are imports views: `reveal imports PATH
--external` (the package table, now JSON too), `--circular` and `--unused`; `reveal imports PATH --circular
--fail-on findings` is the gate. The dashboard reads all three from one import graph build of the requested
path (`&scope=path`): external package count, circular dependency detection, unused imports, top importers. The circular verdict counts
load-time edges only; the text prints that rule under the Health line (`Rule:`, `circular.edge_rule` in JSON).

### Usage

```
reveal deps [PATH] [--top N] [--no-unused] [--no-circular]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--top N` | Top packages/importers to show (default: 10) |
| `--no-unused` | Skip unused imports section (Health says "not checked"; JSON `skipped`) |
| `--no-circular` | Skip circular dependency section (Health says "not checked", not ✅; JSON `skipped`) |
| `--summary-only` | Primary JSON only: replace `base.files` with counts, keeping analysis/findings evidence |
| `--fail-on none\|findings` | Default none; opt into the circular/unused findings gate |
| `--format json` | Machine-readable output |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Requested analysis completed; no enabled findings gate matched |
| 1 | `--fail-on findings` matched circular groups or unused imports |
| 2 | Invalid request/resource/parameter |
| 3 | Required analysis or requested output failed or remained incomplete |

Use `--fail-on findings` to retain the previous text-mode findings gate. Both
spellings and formats now use this policy and `deps_scan` identity. Summary and
text caps preserve full analysis/gate counts. `--verbose` expands text in both
forms; `--all` remains available only on the URI form.

### Examples

```bash
reveal imports . --external                     # The package table (deps' Unresolved/stdlib sections)
reveal imports ./src --circular                 # Circular dependency groups
reveal imports . --unused --format json         # Unused imports, machine-readable for CI
reveal imports . --circular --fail-on findings  # Gate on complete circular findings
```

### See Also

- `imports://` — Full import graph queries (`?external`, `?circular`, `?unused`)
- `reveal overview` — Includes dependency summary
- `reveal imports --help` — Full flag reference

---

## reveal check — Quality Rule Engine

Run 55 built-in quality rules against a file or directory (79 including internal self-check rules, shown with `--all`). Covers bugs, complexity, imports, maintainability, security, types, and more. Exit codes: 0 = complete and clean, 1 = findings, 2 = usage error, 3 = incomplete analysis (including capped or skipped rule-wide scans, and a file that did not parse inside a project-wide rule's index, even when the file you checked is clean). A rule that does not apply to a file's language is a printed note and does not change the exit code. `--exit-zero` overrides scan exits while retaining diagnostics.

T006 also discloses actual directory loss while discovering project-wide TypedDict
and dict-alias evidence. Surviving suggestions remain available, including matches
from the checked module, but absent suggestions do not establish that no matching
type exists. These disclosures appear in `scan_disclosures` and make the CLI scan
incomplete (exit 3 unless `--exit-zero` is set), even when the checked file parsed
successfully. An earlier directory error remains visible if the scan later reaches
its file ceiling. Report exclusions do not narrow this evidence walk.

Serialized MCP requests rebuild traversal-incomplete T006 indexes on the next
request, including after access recovers. Healthy retained indexes still reuse
the existing stat-based validation. This does not establish complete evidence
for separate file-read or parse failures.

I007 likewise discloses directory loss while discovering Python or Rust project
imports. Its notes identify the project root and language: a dependency reported
as unused may be used in omitted inputs. Check retains surviving findings, but
known directory loss makes the CLI scan incomplete even when no findings remain
(exit 3 unless `--exit-zero`). The same notes reach ordinary MCP Check results.
Traversal-incomplete import facts rebuild at the next serialized host request;
healthy facts retain existing validation and reuse. This directory-loss handling
does not change the separate public policy for skipped-file-only I007 outcomes.

M102 discloses directory loss while discovering project-wide Python importers.
Its root-attributed note warns that orphan findings and removal suggestions may
be false positives because imports may be missing. Surviving heuristic findings
remain visible; known loss makes the CLI scan incomplete (exit 3 unless
`--exit-zero`), including after severity or display cuts. Ordinary MCP Check
results carry the same notes. Do not interpret the finding count as a lower
bound or remove a module solely on an uncertain orphan result.

M102 notes apply to requested Python targets eligible for the rule, with their
per-file configuration respected. Entry points, tests and disabled targets do
not adopt another cached root's warning. Explicit `--select M102` retains the
existing override of config disabling. A parallel preload may still prepare an
index for a disabled rule; that alone does not make the requested answer
incomplete. This is eligibility/config scope, not an execution ledger.

Traversal-incomplete M102 inventories are retried at the next normal serialized
host request, even if access recovered before the earlier request finished.
Healthy inventories retain their existing validation and reuse. This handling
covers directory enumeration, not the separate importer-file read or
`__init__.py` fallback-read failure channels. M102 is a cross-file rule, so it is not part
of the quality scores and rankings of `stats://`, `overview` and `hotspots`, which count
file-local rules only ([what the issue count counts](../adapters/METRICS_ADAPTER_GUIDE.md#what-the-issue-count-counts)).

### Usage

```
reveal check [path] [flags]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--select RULES` | Run only specific rules or categories: `B,S` or `B001,I002` |
| `--changed RANGE` | Check only the files a git range changed (`main..HEAD`; a single ref such as `HEAD` means uncommitted changes). PATH, default `.`, bounds the search. `scope.changed` / a `Scope:` line states the range and file count; an unusable range exits 2 |
| `--ignore RULES` | Skip rules or categories |
| `--profile NAME` | Apply a named rule preset (e.g., `maintenance`, `security`, `ci-strict`); list with `reveal --profiles` |
| `--config FILE` | Config file (`.reveal.yaml` or `pyproject.toml`) |
| `--only-failures` | Hide passing checks; show violations only |
| `--recursive, -r` | Recurse into directories (default: on) |
| `--advanced` | Enable deeper validation checks |
| `--severity LEVEL` | Minimum level: `low`, `medium`, `high`, `critical` |
| `--format` | `text` (default), `json`, `typed`, `grep` |
| `--rules` | List all available rules with descriptions |
| `--explain CODE` | Explain a specific rule (e.g., `--explain B001`) |

### Rule Categories

| Category | Code | What it checks |
|----------|------|----------------|
| Bugs | B | Bare excepts, bad decorators, unresolvable imports |
| Complexity | C | Cyclomatic complexity, function length, nesting depth |
| Duplicates | D | Duplicate function detection |
| Errors | E | Line length and style errors |
| Frontmatter | F | Markdown frontmatter presence, required fields, type validity |
| Imports | I | Unused imports, circular dependencies, layer violations |
| Links | L | Broken internal links, missing index files, low cross-reference density |
| Maintainability | M | File size, orphaned files, version mismatches, hardcoded lists |
| Infrastructure | N | nginx config: SSL, ACME, proxy headers, timeout mismatches |
| Refactoring | R | Too many function arguments |
| Security | S | Docker `:latest` tags and security anti-patterns |
| Types | T | Type annotation gaps: `Optional[]` on nullable params (T001–T004), annotation coverage (T005), TypedDict suggestions for bare-dict params (T006) |
| URLs | U | Insecure `http://` GitHub URLs, URL/canonical mismatches |
| Validation | V | Reveal self-checks: version consistency, adapter contracts, doc accuracy |

### Examples

```bash
reveal check src/                          # check all files recursively
reveal check file.py                       # single file
reveal check src/ --select B,S            # bugs and security only
reveal check src/ --format json           # machine-readable
reveal check src/ --severity high         # high/critical issues only
reveal check --changed main..HEAD          # rules on the files a PR changed
reveal check --rules                      # list active rules
reveal check --explain C901              # explain the complexity rule
git diff --name-only | reveal --stdin --check  # check only changed files
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Complete and clean, or explicit `--exit-zero` |
| `1` | One or more violations found with no known scan incompleteness |
| `2` | Usage error |
| `3` | Incomplete analysis, including disclosed rule-wide evidence loss, or a requested `--output json=PATH` artifact that could not be written |

Exit code 1 is set consistently across all invocation forms: single file, directory, and `--stdin --check` piped file lists.

A requested `--output json=PATH` that cannot be written (the path is a directory, the parent is missing or read-only) exits 3 in all three forms: the report on stdout is still printed in full, and `Error: Requested JSON artifact failed: ...` is printed once on stderr. This outranks issues found (1) and the legacy `--exit-zero`. With `--format json` the artifact would equal the printed document, so `--output json=PATH` is not written and cannot fail. (Before this, `check` printed a `Warning:` and kept the scan's exit code, so a gate could read 0 for a run whose artifact was never written.) `printf 'a.py\nb.py\n' | reveal --stdin --check --output json=PATH` writes PATH once, for the whole run, as one `check` document with a `files[]` entry per input; it used to be rewritten per file, so it held only the last one.

### See Also

- `reveal check --changed RANGE` — Rules on the files a PR changed (replaces the retired review)
- `reveal hotspots` — Complexity-focused view
- `reveal check --help` — Full flag reference

---

## reveal scaffold — Component Generator

Scaffold new reveal components (adapters, analyzers, rules) with correct structure and boilerplate.

### Usage

```
reveal scaffold adapter NAME URI       # e.g. mydb mydb://
reveal scaffold analyzer NAME EXT      # e.g. toml .toml
reveal scaffold rule CODE NAME         # e.g. B007 "too-long"
```

### Examples

```bash
reveal scaffold adapter mydb mydb://          # new URI adapter skeleton
reveal scaffold analyzer toml .toml           # new file type analyzer
reveal scaffold rule B007 "too-long"          # new quality rule stub
```

### See Also

- `reveal dev` — Developer tooling (includes scaffold wrappers)
- [ADAPTER_AUTHORING_GUIDE.md](../development/ADAPTER_AUTHORING_GUIDE.md) — Full adapter authoring guide
- [RECIPES.md](RECIPES.md) — Task patterns that exercise the subcommands
- `reveal help://scaffolding` — In-tool scaffolding reference

---

## reveal patches --view pressure — Testability Pressure Finder (was reveal testability)

Joins test patch usage with production boundary fan-out to find review targets
where repeated mocking and runtime-boundary complexity overlap — not "mocking
is bad," but where patching and boundary fan-out compound.

`reveal patches PATH --view pressure` and `patches://PATH?view=pressure` return `testability_report`; `reveal testability` and `testability://` are retired spellings of the same answer and print a replaced-by note. Direct requests reject
missing explicit test roots before scanning (exit 2), retain required evidence
loss before display cuts (exit 3), and keep genuine clean zero results and
omitted-tests non-applicability at exit 0. Only `--fail-on none` is supported.
See the full guide for uncapped observation counts, path encoding and artifacts.

### Usage

```
reveal patches [PATH] --view pressure [--tests PATHS...] [--top N] [--min-patches N] [--min-categories N]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--tests PATHS...` | Test paths to scan (default: `tests/`, `test/`, or `spec/` under the source root) |
| `--top N` | Maximum patch and boundary groups to show (default: 20) |
| `--min-patches N` | Minimum patches for a target group to be reported (default: 3) |
| `--min-categories N` | Minimum boundary categories for unpatched functions to be reported (default: 3) |
| `--include-unresolved` | Include low-count unresolved patch targets in text/JSON results |
| `--format json` | Machine-readable output |

### Examples

```bash
reveal patches src --view pressure --tests tests
reveal patches . --view pressure --tests tests integration_tests --top 20
reveal patches src --view pressure --tests tests --format json
```

### See Also

- `reveal 'patches://tests?group=target'` — Raw patch-pressure scan (what this command joins against production boundaries)
- `reveal help://testability` — Full testability workflow guide (interpretation, boundary taxonomy, false-positive notes)
