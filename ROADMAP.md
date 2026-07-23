# Reveal Roadmap
> **Last updated**: 2026-07-15 (glossy-spectrum-0715 — v0.109.0 release: 11-language contracts/surface, disk-cache program, depends:// scan-root rewrite, CI-red recovery)

This document outlines reveal's development priorities and future direction. For contribution opportunities, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## What We've Shipped

Full release history with per-item detail lives in [CHANGELOG.md](CHANGELOG.md).

### v0.109.0 — contracts/surface 11-language coverage complete + persistent disk-cache program + depends:// scan-root rewrite + master CI red recovery
- ✅ `contracts`/`surface` reach all 11 languages — Go, Rust, C++ added, plus C++ `.h`-only classes and plain JS/JSX residuals closed (BACK-403 pt 2 / BACK-588).
- ✅ Persistent disk caching for structure, import graph, churn, and imports extraction — up to ~100x on repeat invocations; I002 auto-skips above 2,000 files instead of hanging (BACK-535/536/608/614/615/624/625/626/627).
- ✅ `depends://` scan-root resolution rewrite — explicit `.reveal.yaml root: true`, `?root=` override, all 5 divergent project-root resolvers consolidated onto one (BACK-609/610/612).
- ✅ BACK-547 `--sideeffects`/`--boundary` recall-oracle program continued across Go/Python/Java/Ruby/PHP/C#, closing real structural bugs (Ruby `singleton_method` invisible to `--outline`, Java/C# constructor effects leaking the whole class body) alongside taxonomy gaps.
- ✅ `master` CI red 11h+ across 2 pushes restored to green — treesitter-accessor ratchet migration, stale test line ranges, a taxonomy-mirroring gap, and a dead-code CI-only failure all root-caused and fixed.

### v0.108.1 — critical fix: v0.108.0 broke on every fresh install (tree-sitter-language-pack 1.12.5 incompatibility)
- ✅ Capped `tree-sitter-language-pack` to `<1.12.5` — 1.12.5 changed `Parser.parse()`'s required type and `Tree.root_node`'s calling convention, silently breaking parsing for every language on every OS on any fresh `pip install` (BACK-573).
- ✅ Fixed a Windows-only regression in PHP `__DIR__`/constant-anchor import resolution (path vs. namespace-separator collision).
- ✅ CI "Tests" workflow green on all 6 platform/Python combinations for the first time in ~2 days.

### v0.108.0 — contracts/surface 8-language coverage + --transitive blast-radius + architecture --against + BACK-547 recall-oracle program complete
- ✅ `contracts`/`surface` extended from 2 to 8 languages — Java, C#, PHP, Swift, Kotlin, Ruby added, matching Python/TypeScript (BACK-403 pt 2).
- ✅ `--sideeffects --transitive` / `--boundary --transitive` — interprocedural blast-radius walk into project-local helpers (BACK-545/546).
- ✅ `reveal architecture <path> --against REF` — architectural diff against a git ref (BACK-441).
- ✅ **BACK-547 DD-correctness recall-oracle program complete** — 11 independent-oracle measurement loops (TS, Java, Go, Python, Ruby, Kotlin, Scala, Rust, C#, PHP, Swift), all 11 found and fixed real false-negative bugs; worst were Swift SwiftPM module resolution (~0%→100%, BACK-567) and PHP require/include concatenation (0%→100% on WordPress core, BACK-564/565). See [VALIDATION.md](VALIDATION.md).
- ✅ `_build_graph` complexity 68→21 decomposition, `nav_surface_*.py` duplicate-helper cleanup (BACK-566, BACK-570).

### v0.107.1 — Windows crash fix + due-diligence-sweep bugfixes + check --limit/--profile-rules
- ✅ **0.107.0 crashed on every Windows invocation** (even `--version`) due to an unconditional POSIX-only `import resource` — fixed (BACK-541).
- ✅ `check`'s per-tree I002 warning deduped across `ProcessPoolExecutor` workers, and its import-graph build parallelized (2.3x on large trees) (BACK-531, BACK-536).
- ✅ `reveal review <git-range>` now scopes its quality pass to the diff's changed files instead of the whole auto-walked tree (BACK-538).
- ✅ `surface` crash on bare-name decorators (e.g. `@property`) fixed; `pack` no longer misprioritizes data/test files; arrow-function class properties now resolve; L004 `IndexError` on docs-only directories fixed (BACK-533, BACK-526, BACK-527, BACK-528).
- ✅ New `check --limit N` caps unbounded text output on huge corpora (default 50, `--limit 0` disables); new `check --profile-rules` prints a per-rule wall-time cost breakdown (BACK-539, BACK-540).

### v0.107.0 — Import-graph coverage for 5 more languages + coverage-warning disclosure + depends:// scan-root resolution rewrite
- ✅ Import-graph coverage added for Scala, Dart, GDScript, Lua, and Zig — these five previously built a confidently-wrong graph out of vendored/incidental files with no warning (BACK-514).
- ✅ Coverage-warning disclosure when a project's dominant language has no import-graph support, across `surface`/`contracts`/`architecture`/`overview` (BACK-518).
- ✅ `depends://`'s "hang" on some files root-caused as an unbounded ancestor-repo scan, fixed via a widened project-root marker table, a scan-file cap safety net, and a full rewrite to tiered, ceiling-bounded, deterministic scan-root resolution (BACK-515/524/525).
- ✅ `overview`'s "Recent changes" now discloses when the shown git history belongs to an enclosing repo rather than the target directory itself (BACK-516).
- ✅ Class-field arrow-function methods (`private foo = () => {}`) were invisible file-wide to structure extraction — fixed (BACK-519).
- ✅ INI/TOML fixes: repeated-key data loss, `:?` line-number rendering bug, `.service`/`.timer` extension mapping (BACK-520/521/523).
- ✅ `/digest` and `/exchanges` composed views added to `claude://` (BACK-513); new `--perf` flag for CLI timing/RSS logging.

### v0.106.0 — --section bug fix + unknown-query-param warnings + git activity timelines + tier-1 language expansion
- ✅ `reveal file.md --section NAME` fixed — was silently dumping the whole file instead of the named section, a user-reported CLI-only regression (BACK-508).
- ✅ Closed-param adapters now warn on unrecognized query params instead of silently returning a base result with no signal (BACK-507).
- ✅ Git activity timelines — `?type=history&bucket=week|month` returns bucketed commit/author counts over time, for file/dir/repo scope (BACK-484).
- ✅ Commit churn folded into hotspot scoring, so complex files under constant churn rank above equally complex but untouched files (BACK-483).
- ✅ Kotlin, Swift, Ruby, and PHP promoted to tier-1 verified conformance — every catalogued nav-layer gap closed and regression-pinned, growing verified-language coverage from 9 to 13 (BACK-477).
- ✅ `diff://REF/path` git resolution rewritten from `git` CLI subprocess calls to in-process `pygit2` (BACK-505).

### v0.105.0 — Import-graph edges for 5 more languages + depends:// cross-module fix + Kotlin/Swift/Ruby nav bugs
- ✅ `reveal architecture` now produces a real fan-in/fan-out graph for Java, PHP, Ruby, Swift, and Kotlin, up from Python/JS/TS/Go/Rust-only (BACK-487/488).
- ✅ `depends://` fixed for Java/Kotlin/C#/PHP/Swift — cross-package-directory dependents were silently under-reported due to a project-root/file-discovery mismatch with `imports://` (BACK-498).
- ✅ Elixir structure extraction — `reveal file.ex` now extracts functions/modules instead of byte/line counts only (BACK-480).
- ✅ Kotlin/Swift bare-`throw` exit detection + full throw-text rendering, Ruby statement-modifier gates/`case`-`when`/`raise`/compound-ivar-write nav fixes (BACK-497/499/500).
- ✅ HTML CSS-selector/id/tag/positional extraction fixed — was erroring "Element not found" on all of it (BACK-481).
- ✅ `reveal architecture` no longer hangs on repos with large dependency cycles — exponential cycle-path search rewritten as BFS (BACK-496).

### v0.104.0 — Multi-language nav-layer conformance + rule-correctness matrix complete + help-system coherence
- ✅ Nav-layer flags (`--varflow`/`--sideeffects`/`--catchmap`/`--fanout`/`--statewrites`/`--loopmap`, `Class.method`) closed every catalogued gap for Kotlin/Swift/Ruby/PHP, now regression-pinned in the conformance matrix (BACK-476/477/478).
- ✅ Rule-correctness matrix complete: all 77 `--check` rules verified to fire *correctly* (not just avoid hanging) across languages — 12 real bugs found and fixed across 8 tranches (BACK-432).
- ✅ Cross-language taxonomy fixes: Go/Rust struct extraction, PHP/Kotlin import detection, C++/PHP/TS/Rust `--scope` class/struct/impl detection, Kotlin/Swift assignment & fluent-call-chain classification (BACK-474/475/478).
- ✅ Per-rule verified-language coverage now surfaced in `--rules`/`--explain`, so users see where each rule is trustworthy vs. best-effort before relying on it (BACK-466 part 1).
- ✅ Full 52-file help-system content-accuracy sweep plus help-index coherence fixes — ~28 files had real drift corrected, 15 previously-invisible guides now indexed (BACK-479).

### v0.103.0 — Agent onboarding sprint complete (M1–M4)
- ✅ `help://quick` command block now derived live from the adapter registry instead of hand-maintained, fixing drift risk and surfacing project-local plugin adapters for the first time (BACK-391, M4 — last open item of the onboarding strategy).
- ✅ Breadcrumbs teach the outline≠content mental model, not just extraction mechanics — markdown output now frames its "Next:" hint honestly and suggests `--section '<first heading>'` by name (BACK-390, M1).
- ✅ `--agent-help` / `help://agent` now obey progressive disclosure instead of dumping the full ~40K-token guide regardless of need; the CLI flag and `help://` adapter now share one code path (BACK-389).

### v0.102.0 — Render-mode registry refactor + doc/help count corrections
- ✅ `ElementRenderMode` registry replaces the 87-line render-mode if/elif chain in `_render_element` (BACK-360). No behavior change.
- ✅ Heading-aware markdown outline collapse in default text mode — indents by level, auto-collapses past 25 headings (BACK-387).
- ✅ E501 no longer false-flags data/doc files (BACK-386).
- ✅ Doc/help honesty pass: corrected adapter count (→25), language count (→84), AGENT_HELP token estimate (→~40K) across 13 docs + 3 code files; rewrote the language-count integrity test to assert against `reveal --languages` instead of the raw tree-sitter pack. Filed BACK-388 to generate these counts instead of hand-typing them.

### v0.101.0 — Commit-share ownership queries + production-only surface scan
- ✅ `git://<path>?type=ownership` — commit-share authorship for file / directory / whole repo: primary author, per-author %, contributor count, last-touch date. Foundation for bus-factor / key-person reads; scope extends to directories and the whole repo (subtree oid comparison). `?merges=1`, `?limit=N`, shallow-clone warning (BACK-383).
- ✅ `reveal surface --source-only` — excludes test files and directories from surface scans so security reviews see only production surface. Prunes `tests/`, `__tests__/`, `test_*.py`, `*.test.ts`, etc. Dogfood: 2248 → 286 entries (BACK-380).
- ✅ Bug fixes: `mock.patch` decorators no longer misclassified as HTTP PATCH routes (BACK-377); `imports://` flood on committed `venv/` fixed via `os.walk` + `SKIP_DIRECTORIES` (BACK-378); shallow-clone warning for `?type=blame` (BACK-379).

Earlier highlights (newest first):

| Version | Headline |
|---------|----------|
| v0.100.2 | TypeScript-aware `contracts`/`surface`/`patches://`, confidence metadata, letsencrypt snap fix |
| v0.100.1 | TypeScript/TSX class method extraction by name |
| v0.100.0 | Data-driven audit (BACK-366–369), D005 cross-file literal duplication, help-system overhaul |
| v0.99.1  | `claude://` remote-session fixes + URI routing correctness |
| v0.99.0  | `claude://` adapter quality pass |
| v0.98.0  | Zig analyzer fixes + `check`/`hotspots` hang fix |
| v0.97.0  | `codex://` adapter + agent discoverability |
| v0.96.0  | Named profiles, PHP call graphs, import-rule false-positive fixes |
| v0.95.0  | tree-sitter-language-pack 1.x migration (+140 languages) |
| v0.94.0  | `reveal testability` + `patches://` adapter + frontmatter help metadata |
| v0.93.0  | `--grep` text search |
| v0.92.0  | Architecture hardening sweep |

Earlier releases (v0.33–v0.91) and full per-item notes: [CHANGELOG.md](CHANGELOG.md).

---

## Current Focus: Path to v1.0

### Test Coverage & Quality
- Test count: **9,400 passing** (v0.101.0) — 22 skipped (intentional: PowerPivot fixtures, network adapters)
- Coverage: **~68%** — target 90%+
- UX query/navigation surface: complete (query operators, field selection, element discovery, `--outline`/`--scope`/`--varflow`/`--calls` range)

### Stability & Polish (open)
- Output contract v1.1 enforcement across the remaining adapters
- Performance on very large codebases (multi-process `check`/`hotspots` landed; profiling continues)
- Windows signed-binary distribution (see Technical Debt below)
- TypeScript/React depth — JSX component tree (`react://`) held pending demand (BACK-337)

### Validation & Trust — DD correctness (active track)
The distinction that matters for due-diligence use: *supported* ("the command
runs on this language") is not *validated* ("we have proven the answer is
right"). Silent false negatives — a load-bearing module reported as having zero
importers, a db-writing function reported as pure — are the one failure mode a
DD reviewer cannot tolerate, because a wrong answer looks exactly like a
checked one. The program that closes this is documented in
[VALIDATION.md](VALIDATION.md): per language, build an **independent
ground-truth oracle** (the real toolchain where one exists — `go list`,
`swift package dump-package`, `ts.resolveModuleName` — else a from-spec oracle
that shares no code with reveal), diff it against reveal's output on a **real
open-source codebase**, root-cause every miss, fix, and re-measure.

- **Done:** import/dependency recall measured on **19 languages** (Python,
  TypeScript, Java, Go, Ruby, Kotlin, Rust, C#, PHP, Swift, Scala, C, C++, Lua,
  Dart, GDScript, Zig, TSX, plain JS), **each against two independent corpora**;
  side-effect / boundary recall now measured on **all of them, and every one
  at the full six-category sweep** (BACK-718 fully closed — GDScript
  20.00%→69.33% on Pixelorama, TSX/plain-JS 90.16%→98.36% on Excalidraw, the
  last two breadth gaps; Kotlin's original `db`-only sample deepened to
  82.5%→92.9%, Swift's original `http`-only sample deepened to
  43.3%→100.0%, the two narrow-depth gaps, both now closed). Every baseline
  loop found a real bug except Zig's and C's (both clean 100% on first
  measurement); every found bug is fixed, and three documented residuals
  remain tracked (BACK-681, BACK-704 residual, BACK-703) — BACK-772
  (package.json exports-map resolution) fixed stormy-mistral-0723. **The
  single-corpus overfit-guard sweep is complete** — BACK-669 for the
  original eleven languages, and BACK-708 with children BACK-709–715 for C,
  C++, Lua, Dart, GDScript, Zig, and TSX/plain-JS (closed
  merging-universe-0720). BACK-621's original six-language breadth plan is
  fully closed. Honest-decline invariant shipped (reveal caveats an
  unresolved result instead of asserting a false "nothing here"), and
  release is now gated on CI (BACK-578).
- **Next, in priority order.** Import recall and side-effect recall are both
  now the program's strongest signals — 19 languages (two corpora each) and
  18 languages (full six-category sweep each) respectively. The remaining
  confidence gaps are in the *other* DD signals and in a handful of tracked
  residuals; the ordering below is by cost-to-close and dependency, not
  strictly by gap size — item 2 is actually the largest remaining gap (zero
  validation vs. item 1's partial-credit percentages), but item 1 reuses
  harness and infrastructure that's already built and warm, so it's
  sequenced first:

  1. **Close the tracked import-recall residuals, worst first:**
     TypeScript/nest 81.21% (both known resolution gaps now fixed —
     tsconfig-extends chains chilling-lightning-0723, package.json
     exports-map stormy-mistral-0723 — but neither yet re-measured against
     nest; still the lowest number in VALIDATION.md, on a flagship
     language, with real headroom pending that re-measurement),
     PHP/osCommerce 74.65% (BACK-681),
     C#/Newtonsoft.Json 99.36% (BACK-703). The latter two are documented as
     deliberately out of scope for a generic resolver; revisit only if a
     corpus shows the shape is commoner than measured.
  2. **Design a ground-truth methodology for `surface` and `contracts`.**
     These reach 11 languages of *coverage* but have **zero** recall validation
     on any language — the single largest remaining confidence gap in this
     track, ahead of item 1 by size, but sequenced after it since there is
     no existing harness to reuse. Unlike import recall there is no external
     oracle to borrow (no `go list` equivalent for "what is this module's
     public surface"), so this needs a design doc before any measurement —
     closer to the side-effect program's from-scratch-oracle shape (BACK-719).

  *Not on this list, deliberately:* `patches://`/testability language breadth
  past Python + TS is filed as an idea rather than committed work — see
  `tt show BACK-632`. Note that `surface`/`contracts` themselves already reached
  11-language parity (BACK-588/630/631); only `patches://`/testability is still
  Python + TS. Swift's `_RopeModule` residual is closed by design (BACK-704):
  resolving it would require evaluating arbitrary `Package.swift` code, which
  the buildless architecture will not do.

---

## Architecture Hardening Track — ✅ Complete (cukite-0512)

All 12 items (the v0.92.0 hardening sweep) shipped in a single session. See the v0.92.0 entry in [CHANGELOG.md](CHANGELOG.md) for per-ticket detail.

Remaining hotspots from the original review that were **not in scope** for this sweep (deferred to future sessions, will be tackled when their adapters need maintenance):
- `_run_fleet_audit` in `nginx/adapter.py` (cx:31)
- `get_structure` in `ssl/adapter.py` (cx:31)
- `get_structure` in `claude/adapter.py` (cx:30)
- `get_file_blame` in `git/files.py` (cx:30)
- `_infer_shape` in `ast/nav_reveal_type.py` (cx:29)

The kernel (mcp_server, adapters/base, file_handler) and the worst complexity offenders (`reveal_pack`, `_handle_if`, `find_callees_recursive`) are now in much better shape.

---

## Design Specs & Open Backlog

Shipped capabilities (BACK-071 through BACK-294) are recorded in [CHANGELOG.md](CHANGELOG.md);
their original design notes remain in git history. The specs below are the ones still worth
keeping inline — one open item and one reference spec.


### BACK-295: Extend `get_structure()` to collect module-level variable assignments as `type=variable`

**Status**: Open (hold — BACK-294 shipped in v0.91.3; revisit if hint proves insufficient)
**Value**: Medium | **Lift**: Medium
**Filed**: burning-asteroid-0510 (2026-05-10)

Full root-cause fix for the BACK-294 class of bug. Adds a `variables` category to the element collection layer so `--search`, `name~=`, and `--type variable` work for module-level constants.

```bash
reveal bot.py --search "LIVE_SIGNALS"   # finds it after this fix
reveal src/ --type variable             # all module-level constants across project
reveal 'ast://src/?name~=^[A-Z_]+$'    # all SCREAMING_SNAKE constants
```

**Implementation:**

- `treesitter.py`: add `_extract_variables()` — walk top-level nodes for `assignment` and `augmented_assignment` where LHS is a simple identifier. Scope to module-level only (depth 0) to avoid function-local noise. Populate a `variables` list in the structure dict returned by `get_structure()`.
- `adapters/ast/filtering.py`: add `'variable'` / `'variables'` to `normalize_type_condition()`.
- Default unfiltered output: **do not** include variables in the default listing (too noisy); require `--type variable` or explicit `name~=` to surface them. Or include only when querying a single file.
- `ELEMENT_TYPE_MAP` in `treesitter.py`: add `'variable': ('assignment', 'augmented_assignment')`.

**Risk:** Python `assignment` nodes are extremely common — naive extraction would flood directory-mode output. The depth-0 guard (module-level only) is essential. May still be too noisy for `reveal src/` without `--type variable`.

**Revisit trigger:** BACK-294 ships and users still hit the wall (hint alone not enough), or a second distinct user asks to search for constants.

---

### BACK-296: `codex://` adapter — Codex CLI session analysis

**Status:** ✅ Phase 1 shipped v0.97.0 — retained as the `claude://`-vs-`codex://` structural reference and Phase 2/3 plan.
**Design doc:** `internal-docs/design/CODEX_ADAPTER_DESIGN_2026-05-24.md`

A peer adapter to `claude://` for navigating [OpenAI Codex CLI](https://github.com/openai/codex) sessions. Codex stores sessions differently from Claude Code — SQLite index + per-session JSONL with a typed event envelope — so this is a new adapter, not a fork of `claude://`.

**What it enables:**

```bash
reveal 'codex://'                            # list sessions from SQLite threads table
reveal 'codex://sessions/?search=auth-refactor'     # fast metadata search (SQLite)
reveal 'codex://019e5cc5'                    # session overview (turns, tools, tokens, duration)
reveal 'codex://019e5cc5?last'               # last agent message — recovery pattern
reveal 'codex://info'                        # resolved paths, DB stats
reveal 'codex://history'                     # ~/.codex/history.jsonl
reveal 'codex://config'                      # ~/.codex/config.toml (secrets masked)
reveal 'codex://memories'                    # ~/.codex/memories/ (MEMORY.md + summaries)
reveal 'codex://rules'                       # ~/.codex/rules/*.rules (Starlark permission rules)
```

Phase 2 adds session analysis depth (`/tools`, `/shell`, `/errors`, `?tokens`, content search).  
Phase 3 adds `/workflow`, `/timeline`, goal tracking, memory pipeline introspection.

**Key structural differences from `claude://`:**

| Dimension | Claude | Codex |
|---|---|---|
| Session ID | Named slug (`amber-fire-0425`) | UUID — surface `threads.title` for display |
| Primary index | Filesystem scan of `~/.claude/projects/` | SQLite `threads` table — use this first |
| Tool calls | `tool_use`/`tool_result` inside message blocks | `function_call`/`function_call_output` as separate JSONL lines linked by `call_id` |
| Reasoning | `thinking` blocks — readable | `encrypted_content` — opaque; show count only |
| Shell execution | Bash tool call | Dedicated `exec_command_begin/end` events with exit code + duration |
| Config | JSON | TOML |
| Goals | None | `goals_1.sqlite/thread_goals` — per-thread objective + token budget |
| Memory citation | None | `agent_message.memory_citation` — names the memory file cited |

**JSONL record types** (Rust source: `codex-rs/protocol/src/protocol.rs`):
- `session_meta` — id, cwd, model_provider, git state, thread_source
- `turn_context` — model, sandbox_policy, approval_policy, effort (per-turn)
- `event_msg` — user_message, agent_message, task_started, task_complete, exec_command_begin/end, token_count, error, warning, request_permissions
- `response_item` — message, reasoning (encrypted), function_call, function_call_output, local_shell_call, web_search_call

**Shared infrastructure to build first:**

`reveal/adapters/agent_base.py` — `pair_tool_calls(calls, outputs, call_id_field)` utility. Structurally identical logic needed in both `claude://` (matches `tool_use` → `tool_result` by `id`) and `codex://` (matches `function_call` → `function_call_output` by `call_id`). Build once, test once.

**File layout** (mirrors `claude/` exactly):

```
reveal/adapters/codex/
  __init__.py
  adapter.py               ← routing, SQLite path resolution, dispatch
  handlers/
    sessions.py            ← list (SQLite-first), metadata search, content search
    system.py              ← history, config (TOML), rules, memories
  analysis/
    messages.py            ← user/agent turns, memory citations
    tools.py               ← function_call pairing, shell tracking, success rates
    errors.py              ← error/warning/guardian_warning events
    overview.py            ← session metrics, duration, goal status
    search.py              ← cross-session content search
    timeline.py            ← chronological event stream
  renderer.py + render_*.py
```

**Environment overrides:** `REVEAL_CODEX_HOME` (default `~/.codex`), `REVEAL_CODEX_DB` (default `~/.codex/state_5.sqlite`).

**Do not** build a unified `agent://` namespace yet — wait until a third agent adapter (Gemini CLI, etc.) makes the abstraction earn its keep.

---

### BACK-297: `xlsx://` — pivot table inspection (`?pivots=list/schema`)

**Status**: Open
**Value**: High | **Lift**: Medium
**Filed**: infinite-antimatter-0628 (2026-06-28)

Add `?pivots=list` and `?pivots=schema` query params to the xlsx adapter. Discovered need while analysing BMD thin workbooks — 8 pivot tables in a single thin had to be extracted by manually unzipping and parsing `xl/pivotTables/*.xml` and `xl/pivotCache/pivotCacheDefinition*.xml`. This is the core of understanding how any thin workbook wires to a Power Pivot / SSAS model.

**What it enables:**
```bash
reveal "xlsx:///path/thin.xlsx?pivots=list"    # names, sheet locations, cache ids
reveal "xlsx:///path/thin.xlsx?pivots=schema"  # full field breakdown per pivot
```

**Expected output (`?pivots=schema`):**
```
Pivot Tables (8):
  pivotTable1  →  cache 1  (Daily Flash, A8:Y267)
    Rows:    [Warehouses].[Division], [Warehouses].[Desc FIN Whs]
    Cols:    [Measures].[Sales SEL], [Budgeted Sales], [GM Pct SEL] ...
    Filters: [Periods].[Period with Current]

  pivotTable2  →  cache 2  (As of Current Date, B7:D10)
    Rows:    [Periods].[Period with Current]
    Cols:    [Measures].[Current As Of Date], [Workdays SEL] ...
```

**Implementation sources:**
- `xl/pivotTables/pivotTable*.xml` — `<pivotField>` with `axis=axisRow/axisCol/axisPage`; field names resolved via cache index
- `xl/pivotCache/pivotCacheDefinition*.xml` — `<cacheField name="[Measures].[Sales SEL]">` — the MDX field references
- `xl/workbook.xml` — `<pivotCache cacheId>` links pivot table → cache definition

---

### BACK-298: `xlsx://` — expose full OLAP connection string in `?connections=show`

**Status**: Open
**Value**: High | **Lift**: Low
**Filed**: infinite-antimatter-0628 (2026-06-28)

`?connections=show` currently returns name and type but silently drops the actual connection string from `dbPr/@connection`. For OLAP-connected workbooks (type 5, MSOLAP.5) this is the essential fact — it identifies which model and instance the file queries.

**Fix:** Surface the full `dbPr/@connection` string and `dbPr/@command` in `?connections=show` output. Also surface `olapPr` attributes (sendLocale, rowDrillCount).

**Example of what's currently missing:**
```
Provider=MSOLAP.5;Integrated Security=SSPI;
Initial Catalog=BMD_Core_<guid>_SSPM;
Data Source=https://bmdbi.portalfront.com/Shared%20Documents/Cores/BMD_Core.xlsx;
MDX Compatibility=1;Safety Options=2;command=Sandbox
```

Discovered by having to read `xl/connections.xml` raw to find which core model a thin was pointed at.

---

### BACK-299: `xlsx://` — explain empty Power Pivot schema on OLAP-connected thin files

**Status**: Open
**Value**: Medium | **Lift**: Low
**Filed**: infinite-antimatter-0628 (2026-06-28)

When `?powerpivot=schema` is run on an OLAP-connected thin (no embedded `xl/model`), the adapter returns `Tables (0)` with no explanation. This is confusing — the workbook clearly has a Power Pivot connection but the model lives externally.

**Fix:** Detect the "thin" pattern — MSOLAP external connection + no embedded xl/model — and return a diagnostic instead:

```
⚡ Power Pivot model: externally connected (no embedded tables)
   OLAP source: BMD_Core_<guid>_SSPM
   Data Source: https://bmdbi.portalfront.com/.../BMD_Core.xlsx
   → Run ?pivots=schema to see what this file queries from the model
   → Run ?connections=show for full connection string
```

Detection heuristic: `xl/customData/item1.data` present (Power Pivot flag) + `xl/connections.xml` has a type-5 (OLAP) connection + `Tables (0)` after parsing.

---

### Additional Subcommands

Eight subcommands (`check`, `review`, `pack`, `health`, `dev`, `hotspots`, `overview`, `deps`) shipped. Remaining subcommand ideas:

```bash
reveal onboarding            # First-day guide for unfamiliar codebases
```
*(`reveal audit` was listed here — dropped: "audit" names the consumer's activity, not data (see [Scope Test](#scope-test-what-belongs-in-reveal)), and it's already `check --profile security` from BACK-321.)*

#### Structural Egress & Ownership Queries (field notes: yenifada-0629; reframed flux-carnage-0629)

Field-validated on 6 real codebases (Saleor ~909K LOC, LiteLLM ~4.6K py files, 4 internal repos) during a security/architecture review. The use-case validated cleanly **on the primitives reveal already has** (`overview`, `architecture`, `surface`, `git://blame`). These items extend those primitives with new *data categories* — they do not add verdicts. The interpretive layer (AI-washing call, exposure verdict, debt valuation, review playbook) lives in the **consumer's** tooling, not reveal — see [Scope Test](#scope-test-what-belongs-in-reveal).

| Item | BACK | Pri | Data revealed (reveal's half) | Judgment (consumer's half) |
|------|------|-----|-------------------------------|----------------------------|
| `surface --source-only` | BACK-380 | ✅ | Scope flag: drop test files/dirs in one pass | — (pure scoping) |
| `git://?type=ownership` | BACK-383 | ✅ | Per-file/dir/repo commit-share ownership: primary author, commit-share %, contributor count, last-touch | "bus-factor risk" ranking + key-person call |

This whole track is now shipped or closed. `git://?type=ownership` (commit-share, file/dir/repo) builds on the BACK-379 shallow-clone detection. The bus-factor ranking is a consumer recipe composing it with `imports://`/`calls://` fan-in.

`reveal dd`, `reveal debt --rate`, vendor-specific `surface` sub-categories (BACK-381/382), and other consumer workflows are **out of charter** — moved to [Explicitly Not Planned](#explicitly-not-planned).

### Relationship Queries (Call Graphs)
- ✅ **`calls://` shipped v0.62.0** — `?target=fn`, `?callees=fn`, `?depth=N`, `?rank=callers`, `?format=dot`. See [CALLS_ADAPTER_GUIDE.md](reveal/docs/adapters/CALLS_ADAPTER_GUIDE.md).
- ✅ **`depends://src/module/`** — inverse module dependency graph (what depends *on* this module, not just what this module imports). Different from `imports://` which is forward-only. **Shipped v0.73.0 (yaponuxo-0406)**.

### Git-Aware Defaults
```bash
reveal .                    # Defaults to changed files on branch
reveal --since HEAD~3       # Changes since commit
reveal --pr                 # PR context auto-detection
```
**Why valuable**: Makes tool instantly relevant to daily workflows.

---

---

## Lower Priority / Speculative

| Feature | Notes |
|---------|-------|
| PostgreSQL adapter | mysql:// proves pattern; diminishing returns |
| Docker adapter | `docker inspect` already exists |
| LSP integration | Big effort; IDEs have good tools |
| --watch mode | Nice UX but not core; use `watch reveal file.py` |

---

## Technical Debt & Planned Infrastructure

### Windows Code Signing (SignPath Foundation)

**Status**: 🔬 Planned — application to SignPath Foundation not yet submitted
**Value**: High | **Lift**: Medium
**Doc**: [`reveal/docs/development/WINDOWS_SIGNING.md`](reveal/docs/development/WINDOWS_SIGNING.md)

pip generates `reveal.exe` unsigned at install time — structurally unresolvable through pip. On Windows machines with ACP/WDAC enabled, upgrades break the tool. Observed concretely 2026-05-25 (hidden-sword-0525).

Plan:
1. **Phase 1** — Apply to [SignPath Foundation](https://signpath.org/) (free Authenticode signing for OSS, HSM-backed, GitHub Actions native)
2. **Phase 2** — Add `reveal/__main__.py` so `python -m reveal` works as ACP-safe fallback (one-file fix, no cert needed)
3. **Phase 3** — PyInstaller `--onedir` `reveal.exe` (folder, not `--onefile` — onefile's temp extraction is an AV heuristic; BACK-495), signed in GitHub Actions, distributed as GitHub Release binary — build side shipped (`windows-binary.yml`), signing still to enable
4. **Phase 4** — Document signed binary as the recommended Windows install path in README/QUICK_START

Discovery: hidden-sword-0525 (2026-05-25)

---

### tree-sitter-language-pack 1.x Migration

**Status**: ✅ **Complete** (lightning-sphinx-0522, 2026-05-22) — pin lifted, all 8700 tests passing on 1.8.1
**Value delivered**: +140 languages (165 → 305), active maintenance, security patches
**Approach taken**: Direct migration (no compat shim) — 28 production files updated, mechanical API renames + 3 consolidated helpers in `reveal/core/treesitter_compat.py` (`node_children`, `node_prev_sibling`, `node_next_sibling`)
**Investigated**: enigmatic-helix-0522 (2026-05-22)
**Migrated**: lightning-sphinx-0522 (2026-05-22)

#### Background

`tree-sitter-language-pack` 0.x (last release: 0.13.0, late 2024) is frozen and abandoned — no security patches, no new languages, unlikely to get Python 3.14 wheels. The 1.x series (kreuzberg-dev, Rust/PyO3 rewrite) is actively maintained with releases every 2–3 weeks.

The 1.x package is **not API-compatible** with 0.x. It is a completely different Rust/PyO3 implementation. `get_parser()` returns `builtins.Parser` (not `tree_sitter.Parser`), and every Node attribute became a method call instead of a property:

| API | 0.x (current) | 1.x |
|-----|--------------|-----|
| Parse input | `parser.parse(bytes)` | `parser.parse(str)` |
| Root node | `tree.root_node` *(property)* | `tree.root_node()` *(method)* |
| Node type | `node.type` | `node.kind()` |
| Children list | `node.children` | `[node.child(i) for i in range(node.child_count())]` |
| Named children | `node.named_children` | `[node.named_child(i) for i in range(node.named_child_count())]` |
| Node text | `node.text` | `src[node.start_byte():node.end_byte()]` |
| Byte offsets | `node.start_byte` *(property)* | `node.start_byte()` *(method)* |
| Position | `node.start_point` → `(row, col)` | `node.start_position()` → `Point` |
| Predicates | `node.is_named` *(property)* | `node.is_named()` *(method)* |

#### Platform compatibility (1.x)

- **Linux wheels tagged `manylinux_2_34`** — excludes Ubuntu 20.04 (glibc 2.31) and Debian 11 (glibc 2.31). Both are past or near EOL (Ubuntu 20.04 standard support ended April 2025). Low severity for reveal's developer-skewing user base; not a blocker.
- **Alpine/musl**: no musllinux wheels — Alpine Docker images unsupported.
- **macOS**: Intel (10.12+) and Apple Silicon (11.0+) both supported.
- **Windows**: `win_amd64` and `win_arm64` — full support.
- **Python**: single `abi3` wheel covers 3.10–3.14+.

#### Offline/CI story (1.x)

Grammars are downloaded on first use and cached (`~/.cache/tree-sitter-language-pack` on Linux). Pre-fetch at Docker build time or CI setup:

```python
from tree_sitter_language_pack import download_all
download_all()  # fetch all 305 grammars; no-op if already cached
```

Cache directory is configurable (`PackConfig(cache_dir="/path")`). Cache is keyed to grammar ABI version, not library version — minor upgrades don't force re-downloads.

#### Migration plan (4 phases)

**Phase 1 — Investigation** ✅ Complete (enigmatic-helix-0522)

**Phase 2 — Direct migration** ✅ Complete (lightning-sphinx-0522)

Compat shim was rejected in favor of direct migration once the real scope was understood: ~25 production files use tree-sitter node APIs directly (not just `treesitter.py`), so a shim wrapping nodes at `_parse_tree()` would have required wrapping every node returned through every internal API — same blast radius as direct migration, with extra indirection.

Mechanical changes applied across 28 files:
- `node.type` → `node.kind()`
- `node.children` → `node_children(node)` helper (aliased `_children`)
- `node.start_point[0]` → `node.start_position().row`
- `node.start_byte`/`end_byte`/`root_node`/`is_named`/`child_count` → method calls
- `node.parent` → `node.parent()` (tree-sitter only — pathlib `.parent` untouched)
- `node.prev_sibling`/`next_sibling` (removed in 1.x) → `node_prev_sibling`/`node_next_sibling` helpers (walk parent's children by `start_byte()` since 1.x node equality is unreliable)
- `node.text` (removed) → byte-slice from source
- `parser.parse(bytes)` → `parser.parse(str)`
- `parent.children[0] == node` (broken equality) → `parent.child(0).start_byte() == node.start_byte()`

Helpers consolidated in `reveal/core/treesitter_compat.py`. Two new regression tests guard against drift: `tests/test_treesitter_compat.py` (14 helper tests) and `tests/test_no_tree_sitter_0x_api_leak.py` (greps production tree for 0.x API patterns; fails CI if reintroduced).

**Phase 3 — Lift the pin** ✅ Complete

`tree-sitter-language-pack>=1.8.1` in `pyproject.toml`. All 8700 tests pass on 1.8.1.

**Phase 4 — Native migration (optional, not yet done)**

1.x's `process()` API does structured extraction (functions, classes, imports) natively — may allow deleting large chunks of reveal's own extraction logic. Defer until there's a concrete win to chase.

---

## Scope Test (What Belongs in Reveal)

Reveal exposes **structural data**; the consumer applies **judgment**. Run every proposed feature through this test before filing it. Requests captured during a specific engagement drift toward that engagement's use-case — name and scope by the *data*, not the *verdict*.

A feature belongs in reveal when **all** of these hold:

1. **It reveals data that structurally exists** in the artifact (imports, calls, blame, complexity, cert dates) — not a derived opinion.
2. **It's named after the data, not the consumer's activity.** `imports`, `surface`, `ownership` name data; `audit`, `dd`, `debt-in-dollars` name what the consumer concludes. If the name describes a verdict or a workflow, stop.
3. **It applies no domain or business judgment.** Deterministic, domain-agnostic rules (complexity > N, circular imports, hardcoded-secret patterns) are fine — those are universal code properties. "Is this AI real," "is this a DD red flag," "what's the debt in dollars" are not.
4. **It extends an existing primitive** (`surface` category, `calls://` / `git://` query) where it can, rather than adding a top-level subcommand named after a use-case.
5. **It's a single reveal, not an orchestrated playbook.** Pipes compose; reveal does not run named multi-step sequences on the consumer's behalf.

**Smell words in a proposed name:** *audit, assess, score, grade, verdict, rate, `*-in-dollars`*, or any consumer's process name (`dd`, `onboarding-review`). When you see them, the feature is usually a *consumer* of reveal's output and belongs in that consumer's tooling. Reframe to the data primitive it would have to read, and ship that instead.

This is the positive form of the list below.

---

## Explicitly Not Planned

These violate reveal's mission ("reveal reveals, doesn't modify") or fail the [Scope Test](#scope-test-what-belongs-in-reveal):

| Feature | Why Not |
|---------|---------|
| `--fix` auto-fix | Mission violation. Use Ruff/Black for formatting/fixes. |
| `reveal dd` & other consumer-workflow composites | Named after a consumer's process, not the data; orchestrates a named multi-step playbook. Reveal composes via pipes — it doesn't run playbooks. Build the DD first-pass in consumer tooling over the existing primitives (`overview`→`architecture`→`surface`→`hotspots`→`git://blame`→`pack`). Decision: flux-carnage-0629 (BACK-384). |
| `reveal debt --rate N` / debt-in-dollars scoring | A business opinion (dollar rate) layered on structural metrics. The inputs (`hotspots`/`circular`/`check`/`overview` counts) are already JSON-exportable; compute the valuation in the consumer's script. Decision: flux-carnage-0629 (BACK-385). |
| Vendor-specific `surface` sub-categories (`ai-provider`, `agent-framework`, etc.) | A curated vendor list names the *vendor identity*, not the *coupling type* — breaking the pattern of every other category (`network`, `db`, `sdk`, `env`). The data is already in `surface --type sdk`; the list would be stale the week a new framework ships. Use `reveal surface . --type sdk \| grep -E 'openai\|anthropic\|litellm'`. Decision: poxinuku-0629 (BACK-381/382). |
| `--no-fail` / `--exit-zero` | `\|\| true` is the Unix idiom. The flag conflates "checking" with "what to do about findings" — callers decide that, not the tool. Documented in AGENT_HELP under "Exit code 2 is breaking my pipeline." |
| `semantic://` embedding search | Requires ML infrastructure; over-engineered |
| `trace://` execution traces | Wrong domain (debugging tools) |
| `live://` real-time monitoring | Wrong domain (observability tools) |
| `ssh://user@host/adapter://` meta-adapter (SSH proxy mode) | Wrong layer. Filesystem adapters (`cpanel://`, `autossl://`, `letsencrypt://`) read local files — SSH is a transport workaround, not a native protocol like TLS or TCP. Solve it at the SSH config layer: `ProxyJump` in `~/.ssh/config` eliminates the double-hop quoting hell in 3 lines without touching Reveal. Decision: cataclysmic-eagle-0410. |
| Parquet/Arrow | Binary formats, not human-readable. Use pandas. |

---

## Language Support Status

**Current counts drift with every language/adapter addition — this section is qualitative only.**
Run `reveal --languages` for the live explicit-vs-fallback breakdown and exact count (source of truth, same one README.md quotes).

**Supported ≠ recall-validated.** The list below is *coverage* — the command
runs and extracts structure. It is a separate question from whether a
cross-file signal's *answer* has been measured correct against a ground-truth
oracle; for that per-language status — and, just as importantly, *which signal*
was measured, since import recall covers 19 languages while side-effect recall
covers 11 and `surface`/`contracts` none — see [VALIDATION.md](VALIDATION.md).

### Production-Ready (structure & nav coverage)
Python, JavaScript, TypeScript, Rust, Go, Java, C, C++, C#, Ruby, PHP, Kotlin, Swift, Dart, Zig, Scala, Lua, GDScript, Bash, SQL

### Config & Data
Nginx, Dockerfile, TOML, YAML, JSON, JSONL, Markdown, HTML, CSV, XML, INI, HCL/Terraform, GraphQL, Protobuf

### Office Formats
Excel (.xlsx), Word (.docx), PowerPoint (.pptx), LibreOffice (ODF)

### Tree-Sitter Fallback
Remaining tree-sitter grammars get basic structure extraction with no dedicated analyzer: Perl, R, Haskell, Elixir, OCaml, and more.

---

## Adapter Status

**Current count drifts with every adapter addition — run `reveal --adapters` for the live, current list (source of truth).**

| Adapter | Description |
|---------|-------------|
| `ast://` | Query code as database (complexity, size, type filters) |
| `autossl://` | cPanel AutoSSL run logs — per-domain TLS outcomes, DCV failures |
| `calls://` | Cross-file call graph — callers, callees, coupling metrics, Graphviz export |
| `claude://` | Claude conversation analysis and install introspection |
| `codex://` | OpenAI Codex CLI session analysis |
| `cpanel://` | cPanel user environments — domains, SSL certs, ACL health |
| `depends://` | Reverse module dependency graph — find everything that imports a given module |
| `diff://` | Compare files or git revisions |
| `domain://` | Domain registration, DNS records, health status + HTTP response check |
| `env://` | Environment variable inspection |
| `git://` | Repository history, blame, commits |
| `help://` | Built-in documentation |
| `imports://` | Dependency analysis, circular detection |
| `json://` | JSON/JSONL deep inspection |
| `letsencrypt://` | Let's Encrypt certificate inventory — orphan detection, duplicate SAN detection |
| `markdown://` | Markdown document inspection and related-file discovery |
| `mysql://` | MySQL database schema inspection |
| `nginx://` | Nginx vhost inspection — config file, ports, upstreams, auth, locations, fleet audit |
| `patches://` | Structured patch/diff generation |
| `python://` | Python runtime inspection |
| `reveal://` | Reveal's own codebase (internal self-inspection) |
| `sqlite://` | SQLite database inspection |
| `ssl://` | SSL/TLS certificate inspection |
| `stats://` | Codebase statistics |
| `xlsx://` | Excel spreadsheet inspection and data extraction |

### Planned
| Adapter | Notes |
|---------|-------|

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add analyzers, adapters, or rules.

**Good first contributions:**
- Language analyzer improvements
- Pattern detection rules
- Documentation and examples
