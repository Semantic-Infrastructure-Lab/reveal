# Correctness Validation: Recall of Reveal's DD Signals

This document is the **correctness** counterpart to reveal's language coverage
claims. Coverage answers "does this command run on this language?" This
answers a sharper question: **when reveal reports a fact about a codebase —
"N files import this," "this function touches the database" — how often is
that actually right, and what happens when it's wrong?**

It exists because a wrong answer is the one failure mode a due-diligence or
architecture-audit user cannot tolerate. A dependency-graph tool that
occasionally reports "nothing imports this" about a load-bearing module is
worse than no tool at all, because it looks like a confident, checked answer.
This document is the audit trail proving how that failure mode was found,
measured, and closed — and gives you what you need to re-run the check
yourself against reveal's actual source, not take our word for it.

Three signals have been through this treatment so far, each as its own
independent-oracle program on real corpora: **import/dependency recall**
(`depends://` / `imports://` fan-in), **side-effect / boundary classification
recall** (`--sideeffects` / `--boundary`), and **cross-file call-graph
recall** (`calls://`). All three are documented below, with the exact
per-language status first.

## Validation status at a glance

Reveal *supports* far more languages than are listed here (run `reveal
--languages` for the full coverage list). This table is narrower on purpose:
it says only where recall has been **measured against an independent
ground-truth oracle on a real codebase** — the difference between "the command
runs" and "we have proven the answer is right." Anything marked *not measured*
is a claim we have not yet checked, **not** a claim it is broken.

| Language | Import recall | Side-effect recall | Call-graph recall | Status |
|---|---|---|---|---|
| Python | ✅ 100% (Home Assistant, celery¹⁰) | ✅ 83.5% (Home Assistant) | ✅ 99.96%→100%³⁴ (Home Assistant, 3 query directions) | **Measured** |
| TypeScript | ✅ 100% (VS Code), ⚠️ 68.48%→81.21% (nest¹⁶, BACK-694/698/705/772 all fixed, held at 81.21% — new residual BACK-773) | ✅ 91.3%¹ (VS Code) | ✅ 100%³⁵ (VS Code) | **Measured** |
| Java | ✅ 100% (Elasticsearch, guava¹¹) | ✅ 97.5% (Elasticsearch) | ✅ 9.99%→100%³⁸ (Elasticsearch, BACK-734 fixed) | **Measured** |
| Go | ✅ 100% (Kubernetes, client_golang¹³) | ✅ 96.3% (client-go) | ✅ 100%³⁶ (Go compiler internals) | **Measured** |
| Ruby | ✅ Zeitwerk-inferred (Discourse), 100%¹⁷ (solidus, BACK-700+BACK-701 fixed) | ✅ 98.8% (Discourse) | ✅ 22.05%→100%³⁹ (Discourse, BACK-735 fixed) | **Measured** |
| Kotlin | ✅ 99.1% (tivi, 100%¹⁴ kotlinx.coroutines) | ✅ 82.5% → **92.9%** (tivi, six-category sweep, BACK-727) | ✅ 99.69%→100%⁴² (8/bucket); 99.79%⁴² (20/bucket, tivi, BACK-738 open — grammar bug, not fixable in reveal) | **Measured** |
| Rust | ✅ 100% (Meilisearch, ripgrep⁹) | ✅ 97.4% (Meilisearch) | ✅ 95.27%→100%³⁷ (Meilisearch, BACK-733 fixed) | **Measured** |
| C# | ✅ 100%¹⁹ (Jellyfin), 99.36%¹⁹ (Newtonsoft.Json, BACK-702 fixed) | ✅ 98.3% (Jellyfin) | ✅ 69.74%→100%⁴¹ (Jellyfin, BACK-737 fixed) | **Measured** |
| PHP | ✅ 100% (WordPress), 74.65% (osCommerce¹²) | ✅ 97.5% (WordPress) | ✅ 98.87%→100%⁴⁰ (WordPress, BACK-736 fixed) | **Measured** |
| Swift | ✅ 100% of declared targets resolved (Kickstarter iOS — module-index coverage, not an edge-recall ratio), 98.42%¹⁸ (swift-collections, 14,824 edges, BACK-704 fixed) | ✅ 43.3% → **100.0%** (Kickstarter iOS, six-category sweep, BACK-728) | ✅ 97.62%→99.92%⁴³ (8/bucket); 99.79%⁴³ (20/bucket, Signal-iOS, BACK-742 open — two grammar bugs, not fixable in reveal) | **Measured** |
| Scala | ✅ 100% (GitBucket — n=1 qualifying edge), 100%¹⁵ (cats-effect, 24 edges) | ✅ 66.3%³⁰ (GitBucket, `db`/Slick declined) | ✅ 96.64% → **100.00%**⁴⁵ (GitBucket, BACK-746/747 fixed) | **Measured** |
| C++ | ✅ 100%³ (Godot), 100%²⁶ (assimp) | ✅ 83.3% (Godot) | ✅ 95.73%⁴⁴ (assimp) | **Measured** |
| C | ✅ 100%⁸ (Redis, curl²¹) | ✅ 92.0%²⁷ (Redis, `http` declined) | ✅ 89.52%→100%⁴⁶ (Redis, BACK-756 open — grammar bug, not fixable in reveal) | **Measured** |
| Lua | ✅ 99.87% (Kong, 99.33%²² AwesomeWM) | ✅ 98.0%²⁸ (Kong, `truncate`/`connect` declined) | ✅ 100.00%⁴⁷ (Kong, BACK-757/758 fixed) | **Measured** |
| Dart | ✅ 99.76%⁴ (AppFlowy), 96.63%²³ (drift) — 100% of *real* edges in both, residuals are oracle false positives | ✅ 84.9%³¹ (AppFlowy, bare `File`/`Directory` declined) | ✅ 100%→97.55%⁴⁹ (AppFlowy, BACK-760/761/763/764/765/766/767/769 fixed; BACK-768 open — grammar bug, not fixable in reveal) | **Measured** |
| GDScript | ✅ 100%⁵ (godot-demo-projects), 100%²⁴ (Pixelorama) | ✅ 69.3%³² (Pixelorama, bare `print`/`request` declined) | ✅ 100.00%⁴⁸ (Pixelorama, BACK-759 fixed) | **Measured** |
| Zig | ✅ 100%⁶ (ghostty, TigerBeetle²⁰) | ✅ 98.4%²⁹ (TigerBeetle) | ✅ 92.28%→99.98% (ghostty, BACK-753/754/755 fixed) | **Measured** |
| TSX, plain JS | ✅ 100%⁷ (Excalidraw, three.js), 100%²⁵ (react-router) | ✅ 98.4%³³ (Excalidraw) | ✅ 100% (three.js + Excalidraw, BACK-751/752 fixed) | **Measured** |

**How to read this table — three caveats that the ✅ marks do not carry:**

1. **Evidence breadth varies by more than an order of magnitude.** A ✅ 100%
   backed by a full-population diff of 99,654 edges (C#/Jellyfin) and one
   backed by a single qualifying edge (Scala/GitBucket) render identically
   here. Several headline numbers rest on stratified samples covering a
   minority of known edges — C++/Godot is 450 of 7,230 oracle edges (6.2%),
   Zig/ghostty 426 of 2,334 (18%), Rust/Meilisearch 295 of 1,491 (20%).
   Sampling is stratified by fan-in precisely so a resolver bug cannot hide in
   the easy cases, but a sample is not a census. **Always read the per-language
   Sample column in the detailed results tables below before quoting a number.**
2. **This table covers three signals, not all of reveal's DD output.**
   Import/dependency recall is measured on all 18 languages listed, and
   side-effect recall breadth is now complete — every language with import
   recall measured also has a side-effect measurement (BACK-718), and every
   one of those now has the full six-category sweep (Kotlin deepened in
   BACK-727, Swift deepened in BACK-728 — the last narrow entry). Call-graph
   recall (`calls://`) is now measured for all 18 (Python, TypeScript, Go,
   Rust, Java, Ruby, PHP, C#, Kotlin, Swift, C++, Scala, JS/TSX, Zig, C, Lua,
   GDScript, Dart — BACK-730, closed).
   `surface`, `contracts`, and `patches://`/testability have **no
   ground-truth validation on any language** — see [Scope](#scope).
3. **Sample size still varies.** Java's 97.5% includes `db` and `http`
   categories with one oracle instance each, both at 0% recall — the figure
   is carried by env/file/log/sleep. Swift's own sparsest category (`env`)
   had exactly one function-reachable positive in the whole corpus (see
   [SWIFT.md](internal-docs/planning/dogfood-findings/sideeffects-recall-oracle/swift/SWIFT.md))
   — a real recall number, but an n=1 one.
4. **C's `http` category is a corpus-proven, deliberate decline, not a
   measurement gap.** C's 92.0% figure is carried entirely by `log`/`file`/
   `env`/`sleep` (each 100%); `http` recall is 0% because the real fix (bare
   POSIX socket verbs) was tried and reverted after corpus-checking showed it
   breaks classification in every other language (footnote 27).

¹ Overall TypeScript side-effect recall was 76.8%; the gap was almost entirely
one architecturally-distinct category — Node's `process.env.X` env reads are a
property access, not a call, so the call-only classifier never saw them.
Excluding that category recall was 91.3%; the category itself was then closed
by a dedicated property-access channel (BACK-644), corpus-validated at 98.7% on
VS Code. ² (retired) — formerly noted Swift's side-effect measurement as
single-category; Swift's `http`-only sample (BACK-547) was deepened to the
full six-category sweep in BACK-728, the same way Kotlin's `db`-only sample
was deepened in BACK-727. No side-effect-recall entry in this table is
single-category anymore.
³ Graduated from spot-check family to a full stratified oracle loop
(BACK-674, same per-directive-isolated `g++ -H` method as C's BACK-611).
30-target stratified sample (fan-in buckets high/mid/low), core/-rooted,
against the engine-core corpus (`core/`+`scene/`+`servers/`+`drivers/`+
`platform/`, ~2,830 files, 7,230 oracle edges): first measurement came back
33.11% — not a `_resolve_include` bug but a real `depends://` adapter-layer
gap (BACK-675) hiding under a scan-cap confound the java/python-recall-oracle
sessions had already learned to route around. `CppImportExtractor.extensions`
deliberately omits `.h` (owned by `CImportExtractor` alone, to avoid a
duplicate-registration conflict) even though most real C++ headers are named
`.h`, not `.hpp` — so BACK-525 layer 4's single-file scan-scoping optimization
silently excluded every `.cpp`/`.cc`/`.cxx` file from the parse corpus
whenever the query target was a header, and a `.cpp` file could never be
found importing its own `.h`. Fixed by widening the scan to the union of the
C and C++ extractor families whenever the target is either. Post-fix: 450
edges, 2 missing, 0 false positives — 99.56%. The 2 residual misses
(`core/math/bvh_tree.h` → its own `.inc` fragment includes) traced to a
separate bug: a `#include` sitting inside a template class body isn't valid
top-level-context grammar, so tree-sitter's C/C++ grammars degrade it to a
generic `preproc_call` fallback node — the same shape used for `#pragma`/
`#undef` inside a body — that the extractor never scanned for (BACK-676).
The same loop also found `CppImportExtractor.extensions` never claimed
`.hh` (already C++ per the structural analyzer's own registration) or
`.mm` (Obj-C++ — parses with tree-sitter's `objc` grammar but emits
identical `preproc_include`/`preproc_call` nodes, verified empirically),
so neither extension's `#include`s were ever resolved (BACK-664; Godot
corpus: 258 `.hh` + 59 `.mm` files affected). Both fixed same pass:
scan `preproc_call` too (filtered to the `#include` directive only), and
add `.hh`/`.mm` to the extractor's extensions. Re-measured: **100.00%**,
0 missing edges on the same 450-edge sample; 24 new true-positive `.mm`
importer edges surfaced (spot-checked genuine, e.g.
`platform/macos/embedded_debugger.mm`'s real `#include
"core/debugger/engine_debugger.h"`) register as this oracle's own false
positives only because `build_oracle.py`'s ground-truth builder never
scanned `.mm` as an importer candidate — a pre-existing oracle scope gap,
not a defect in the fix. Full story: [harness README](../internal-docs/planning/dogfood-findings/cpp-recall-oracle/README.md). ⁴ Sampled recall was 99.76% (823/825); the 2 residual misses were both
oracle false positives — a code-generation script's `writeln('''...''')`
embeds literal `import '...'` *text* inside a Dart template string, which
tree-sitter correctly never parses as a real import (the same class of
false positive the Lua loop's `nginx_kong.lua` case documented).
⁵ Full census (41/41 edges, no sampling — the corpus's 19 distinct targets
made a census cheaper than a stratified sample), 138 independent Godot
projects. Two bugs found and fixed: (1) `depends://`/`imports://`'s
`extra_paths` plumbing dropped the scan root as a search path whenever it
already equaled the importing file's own directory — harmless for every
file-relative resolver (which tries `base_path` first anyway) but fatal for
GDScript's project-root-relative `res://`, which never falls back to
`base_path` at all; every `res://` import in a project's own root-level file
(`main.gd`/`game.gd`/`test.gd`) silently failed to resolve. (2) `extends Foo`
naming a `class_name Foo` declared in another in-tree file — Godot's global
class-registration convention, the dominant edge shape measured (27 of 41) —
had no resolution path at all.
⁶ Stratified sample (26 of 641 distinct targets, 426 of 2,334 in-scope
edges), bucketed by fan-in. Only `.zig`-suffixed relative-file `@import`s are
in scope — Zig's other import shape, `@import("std")`/`@import("gobject")`/
named build-graph module aliases, has no static file-per-name convention
(resolving it would mean interpreting `build.zig`'s own code) and is
correctly skipped by `resolve_import`, not counted as a recall gap. No bug
found — the relative-file resolver was already correct across every fan-in
bucket sampled, up to 3 levels of `../` traversal.
⁷ One combined pass across two corpora (three.js, plain `.js`; Excalidraw,
`.tsx`/`.ts`) since `.js`/`.jsx`/`.ts`/`.tsx`/`.mjs` all share one resolver
function (`_resolve_relative_js`) — not per-extension code paths, unlike
every other language in this table. Stratified sample per corpus (30
targets / 777 edges for `.js`, 29 targets / 745 edges for `.tsx`), bucketed
by fan-in. `.js` sample was 100% on first measurement (no bug triggered —
the sample's basenames happened not to contain the shape below). `.tsx`
sample started at 98.79% (9/745 misses, 0 false positives): a dotted
basename with the file extension omitted (`./charts.constants`,
`./WelcomeScreen.Center`, `./subset-shared.chunk`) was misjudged by
`has_extension`'s naive "does the last path segment contain a dot" check as
already having a real extension, so it never reached the plain
extension-append/directory-index fallback used for genuinely extensionless
specifiers — fixed by falling through to that same shared resolution
instead of bailing (BACK-672). Grand total after the fix: 100% (1,522/1,522
edges, 0 false positives).
⁸ Graduated from the earlier grep spot-check (BACK-611) to a full stratified
oracle loop. Oracle resolves each quoted `#include "..."` directive in
isolation via `gcc -H -fsyntax-only -iquote <including-file's-dir>` — the
real compiler's own header-search algorithm, not a re-derivation of
reveal's. An earlier draft ran `gcc -H` once per whole file and read its
transitive include tree, which *undercounted*: gcc's include-guard
optimization means a header already pulled in transitively earlier in the
same file's chain never gets a fresh depth-1 entry when the file's own
explicit `#include` line for it is reached later, so real edges (e.g.
`script_lua.c`'s own `#include "monotonic.h"`, already reachable via
`server.h`) went missing from the oracle itself. Resolving each directive
as its own isolated one-line compilation fixed that. Stratified sample of
30 targets / 310 edges (Redis's `src/`, `modules/`, `tests/modules/`,
`utils/`), bucketed by fan-in: 100% recall, 0 real false positives (2
apparent ones were `deps/`-tree importers correctly found by `depends://`
but outside this oracle's deliberately narrower importer scope — vendored
third-party code with its own build system, confirmed by direct
inspection, not a reveal bug).

⁹ Overfit guard (BACK-669): re-ran the identical independent-oracle-diff
method against a second, unrelated real corpus (ripgrep, 100 files, 46
targets/100 edges — full population diffed, not sampled) to check whether
the 100% Meilisearch result generalized. It found one new real bug of the
same shape as BACK-558's, one grouping level deeper — a `use_list` item
that is itself a nested `scoped_use_list` (`use crate::{a::{x, y}, ...}`,
ripgrep's dominant `lib.rs` re-export idiom) silently dropped the whole
nested item, 56.0% → **100%** after the fix. See the [harness
README](../internal-docs/planning/dogfood-findings/rust-recall-oracle/README.md#second-corpus-back-669-ripgrep--overfit-guard)
for the full write-up.

¹⁰ Overfit guard (BACK-669): re-ran the identical independent-oracle-diff
method against a second, unrelated real corpus (celery, 417 files, 185
targets — 20-per-bucket stratified sample, 886 edges) to check whether the
100% Home Assistant result generalized. It found one new real bug (BACK-678):
a pure `from . import a, b, c` statement where some names are sibling
submodules and others are symbols living only in `__init__.py` silently
dropped the `__init__.py` edge, because the single-value "primary" resolution
stops at the first submodule match. 99.77% → **100%** after the fix. See the
[harness
README](../internal-docs/planning/dogfood-findings/python-recall-oracle/README.md#second-corpus-back-669-celery--overfit-guard)
for the full write-up.

¹¹ Overfit guard (BACK-669): re-ran the identical independent-oracle-diff
method against a second, unrelated real corpus (guava, 611 files, 159
targets — full population diffed, not sampled, 2,066 edges) to check whether
the 100% Elasticsearch result generalized. Recall held at 100% immediately,
with no fix needed — including on the exact nested-type/static-member idiom
(`import com.google.common.base.MoreObjects.ToStringHelper;`, 353 distinct
`import static` statements) that BACK-551 previously found broken, confirming
that fix generalizes past the corpus that found it. Guava's style guide
forbids wildcard imports, so that resolution path is not exercised by this
slice. See the [harness
README](../internal-docs/planning/dogfood-findings/java-recall-oracle/README.md#second-corpus-back-669-guava--overfit-guard)
for the full write-up.

¹² Overfit guard (BACK-669): re-ran the identical independent-oracle-diff
method against a second, unrelated real corpus (osCommerce `catalog/`, 436
files, 74 targets — full population diffed, not sampled, 288 edges) to check
whether the 100% WordPress result generalized. It found one new real bug
(BACK-680): PHP's parenthesized call-style require/include
(`require('includes/foo.php');` — 534/544 statements on this corpus, vs. only
10/1,521 on WordPress) broke both the concatenation AST-walk (which only
checked *direct* children, missing the target nested inside a
`parenthesized_expression`) and the bare-literal fallback (`_build()`'s
space-splitting keyword tokenizer never matches the fused `require('...')`
token), so every parenthesized-call-style require/include silently produced
zero edges. Fixed by handling both the parenthesized wrapper and a bare
string-literal target structurally, the same AST-walk approach the
concatenation idioms already used. 0.00% → **74.65%** after the fix. A
distinct, real residual (73/288 edges) traces entirely to a single further
cause — explicit `chdir()`/CWD-dependent bare-literal resolution in 6 legacy
extension scripts plus one nested bootstrap file, a shape this corpus
actually relies on but a generic per-file resolver correctly does not chase
(risking false-positive edges in other codebases) — filed as **BACK-681**,
not fixed. See the [harness
README](../internal-docs/planning/dogfood-findings/php-recall-oracle/README.md#second-corpus-back-669-oscommerce--overfit-guard)
for the full write-up.

¹³ Overfit guard (BACK-669): re-ran the identical independent-oracle-diff
method against a second, unrelated real corpus (`prometheus/client_golang`,
162 files, single-module — no `go.work`, unlike Kubernetes' multi-module
workspace — full population diffed, not sampled, 114 targets, 2,837 edges)
to check whether the 100% Kubernetes result (post-BACK-553) generalized.
Recall held at 100% immediately, no fix needed (BACK-685). 133 false
positives, all root-caused to safe over-inclusion: two `//go:build ignore`
code-generation scripts that `go list` excludes but reveal's build-tag-blind
parser doesn't (the same mechanism as the original loop's 8 Windows-build-tag
FPs), plus external test-package files (`package foo_test`) whose own import
of their parent package directory-fans-out to include themselves. See the
[harness
README](../internal-docs/planning/dogfood-findings/go-recall-oracle/README.md#second-corpus-back-669-client_golang--overfit-guard)
for the full write-up.

¹⁴ Overfit guard (BACK-669): re-ran the same content-scanned member-import
oracle technique (BACK-555) against a second, unrelated real corpus
(`kotlinx.coroutines`, 1,039 `.kt` files, a JetBrains library — contrasts
with tivi's Android/KMP app shape — full population diffed, not sampled, 34
targets, 50 edges) to check whether the 99.14% tivi result (post-BACK-555)
generalized. Recall held at 100% immediately, no fix needed (BACK-691). 11
false positives, all root-caused to safe wildcard-import fan-out (`import
kotlinx.coroutines.flow.internal.*` correctly resolving to every file
declaring that package, per `depends://`'s directory-granularity semantics)
— a broader import than the oracle's single-symbol targets, not a bug. See
the [harness
README](../internal-docs/planning/dogfood-findings/kotlin-member-import-oracle/README.md#second-corpus-back-669-kotlinxcoroutines--overfit-guard)
for the full write-up.

¹⁵ Overfit guard (BACK-669): re-ran the same content-scanned container-member
oracle technique (BACK-559) against a second, unrelated real corpus
(`typelevel/cats-effect`, 457 files, a functional-effects library — contrasts
with GitBucket's imperative Scalatra/Twirl web-app shape — full population
diffed, not sampled, 1 target, 24 edges, the well-known `import
cats.effect.unsafe.implicits.global` idiom) to check whether the 100%
GitBucket result (post-BACK-559) generalized. Recall held at 100% (24/24
edges) immediately, no fix needed (BACK-693). Along the way, two oracle-tool
bugs (not resolver bugs) were found and fixed in the measurement harness
itself: a Scaladoc string literal containing example `import` text was
initially miscounted as a real import, and Scala's legitimate local/
method-scoped imports (indented, not column-0) were initially excluded,
undercounting real edges as false positives. See the [harness
README](../internal-docs/planning/dogfood-findings/scala-member-import-oracle/README.md#second-corpus-back-669-cats-effect--overfit-guard)
for the full write-up.

¹⁶ Overfit guard (BACK-669): re-ran the identical independent-oracle-diff
method (`ts.resolveModuleName`, pinned TS 5.6.3) against a second, unrelated
real corpus (`nestjs/nest`, a pnpm/lerna workspace monorepo with no
`node_modules/@nestjs/*` — deliberately different shape from VS Code's
editor-application layout — full population diffed, not sampled, 843
targets, 2,890 edges) to check whether the 100% VS Code result generalized.
It did not: recall collapsed to **68.48%** (1,979/2,890 edges, 911 missed).
Root cause is not barrel re-export depth (that path works correctly) but
that `resolve_import()` never attempted to resolve bare/non-relative import
specifiers (`@nestjs/common`, ...) — reveal's TS/JS extractor had no
`tsconfig.json` `paths`/`baseUrl` resolution, the only way to resolve
cross-package imports in this corpus's monorepo layout. Compounding:
`is_intra_project_import()` marked these `False` (definitely external)
rather than unknown, so the misses never tripped `depends://`'s own
undercount-disclosure (`known_limits`/`confidence`) machinery — it reported
`confidence: high` on results 1–30% complete for the worst-hit barrel files
(`packages/common/index.ts`: 424 oracle importers, 13 found). Filed as
**BACK-694** (parent BACK-669) and fixed: `resolve_import`/
`is_intra_project_import` now consult the nearest `tsconfig.json`'s
`paths`/`baseUrl`. Re-running the full diff with the fix alone left recall
unchanged (68.48%) — masked by a second, distinct bug: project-root
inference stops at the nearest `package.json`, so sibling packages are never
scanned regardless of resolution (filed as **BACK-698**, child of BACK-694).
Isolating the two by forcing the correct workspace root confirmed the fix's
real impact: 81.21% (2,347/2,890, +368 edges) vs. 68.48% at the same
root without it. **BACK-698 landed** (JS/TS-specific workspace-marker tier in
`resolve_project_root` — climbs past the nearest `package.json` to an
ancestor `lerna.json`/`pnpm-workspace.yaml`/`package.json` with a
`"workspaces"` field, gated so other languages and single-package JS/TS repos
are unaffected): re-running the full diff with **no root override** now
reproduces the same **81.21%** (2,347/2,890) automatically, confirming the
root-inference fix generalizes the manual pin. The residual gap to 100% was
attributed to two further out-of-scope resolution gaps, tracked as
**BACK-705**: tsconfig `extends` chains (fixed, chilling-lightning-0723 —
`_get_tsconfig_aliases` now walks the extends chain, nearest-declared-key
wins) and `package.json` `exports` map resolution (split off to **BACK-772**,
fixed stormy-mistral-0723 — workspace-member discovery + subpath/wildcard/
conditional exports resolution as a fallback after tsconfig fails).

Re-ran the full nest-corpus diff with both fixes live
(exploding-parsec-0723): **recall held at exactly 81.21% (2,347/2,890)** —
not because the fixes are ineffective, but because of two separate
findings that surfaced only by digging into why the number didn't move:

- BACK-772 *is* correctly resolving new edges (~90, verified by hand
  against real import statements) from `*.spec.ts` test files using
  package subpath specifiers — but `ts_oracle_nest.json` never captured
  test-file imports to begin with (`build_oracle.js` walks each package's
  *build-scoped* tsconfig, which `exclude`s `test/**/*`/`*.spec.ts`), so
  these correct new resolutions score as false positives against an
  incomplete oracle rather than as recall gains. Tracked as **BACK-774**
  (oracle methodology gap, not a `depends://` bug).
- The real driver of the remaining 543 missed edges: several nest
  packages split their TS config into `tsconfig.json` (no
  `compilerOptions.paths`) and a sibling `tsconfig.build.json` (has the
  real `@nestjs/*` path map), linked via TypeScript's project
  `"references"` field rather than `"extends"`. `_find_tsconfig` only
  ever looks for a file literally named `tsconfig.json` and only chases
  `extends`, so the real path map is invisible for any importer whose
  package uses this split-config pattern — confirmed directly on
  `packages/core/router/router-execution-context.ts`. Tracked as
  **BACK-773**, a real gap distinct from BACK-694/698/772.
See the [harness
README](../internal-docs/planning/dogfood-findings/ts-recall-oracle/README.md#second-corpus-back-669-nest--overfit-guard)
for the full write-up.

¹⁷ Overfit guard (BACK-669): re-ran the require + Zeitwerk path→constant
measurement loop (a from-scratch independent oracle — there was no committed
harness from the original Discourse measurement to re-run unmodified) against
a second, unrelated real corpus (`solidusio/solidus`, a Rails Engine/
multi-gem monorepo — `core`/`api`/`backend`/`admin`/`promotions`/
`legacy_promotions`, each its own gem, deliberately different shape from
Discourse's single-app layout — full population diffed, not sampled, 576
targets, 3,199 edges). It did not fully generalize: recall started at
**88.06%** (2,817/3,199, 382 missed). Root cause #1 (**BACK-700**): a bare
`require 'a/b'` only ever tried the single project root as a search path;
Discourse's single-gemspec-at-the-root layout made that path coincide with
its one `lib/`, but Solidus's `require 'spree/testing_support/...'` needs
each gem's own `lib/` (Bundler's real `$LOAD_PATH`, one per `*.gemspec`) —
395/395 real in-tree bare `require` statements in the corpus needed this,
confirmed by direct measurement. Root cause #2 (**BACK-701**), found after
fixing #1 alone raised recall to 98.81%: a leading `::` (`::Spree::Order`,
Ruby's absolute-constant-lookup disambiguator — needed far more inside a
namespaced Rails Engine than Discourse's flatter code) was kept verbatim in
the captured constant text, so the Zeitwerk index's exact-string match
silently missed every absolute reference. Both fixed: `_ImportSpec.
load_path_manifest_glob`/`load_path_lib_dirname` (new fields, Ruby:
`*.gemspec`/`lib`) add every in-tree gem's `lib/` as an extra search root;
`extract_constant_references` strips the leading `::` before matching. The
remaining 13 apparent misses traced to **oracle** noise (heredoc/regex-
literal text — Rails generator templates and migration column-comment prose
mentioning real class names without executing as code in that file) — fixed
in the oracle, not the product, confirming a genuine **100.00%** (3,186/
3,186) once measured honestly. See the [harness
README](../internal-docs/planning/dogfood-findings/ruby-recall-oracle/README.md#second-corpus-solidus-solidusiosolidus)
for the full write-up.

¹⁸ Overfit guard (BACK-669): re-ran the module-index oracle diff
(`oracle_diff.py`, `swift package dump-package` ground truth) plus a new
from-scratch file-level import/target-membership oracle (`build_oracle.py`)
against a second, unrelated real corpus (`apple/swift-collections`, a pure
SwiftPM *library* — no app, no UI layer — with 25 targets across
`Sources/`/`Tests/`, deliberately different shape from Kickstarter iOS's
big multi-target app with custom `path:` relocations; full population, not
sampled — 696 files, 14,824 oracle edges). It did not fully generalize —
two real gaps, both **BACK-704**. Root cause #1: `_RopeModule`, one target,
is declared through a *programmatically built* `targets:` array (`.map {
$0.toTarget() }`, not a literal array `Package(targets: [...])` can walk)
whose custom relocation argument (`directory: "RopeModule"`) names a
directory segment that doesn't match the target's own sanitized identifier
— neither the manifest parse (honestly declines: no literal native `path:`
it can trust) nor the directory convention (indexes the files under
`RopeModule`, the dir name, not `_RopeModule`, the real import name) can
resolve it, and pre-fix this was *silent*: `_unresolved_intra` never
incremented, the same silent-negative BACK-547 exists to kill. Fixed
partially: a new `extract_manifest_target_names` broadens the
"target exists" scan (position-independent, name-only, no path claim) and
widens `is_intra_project_import`'s inventory, so the 3 real
`import _RopeModule` statements (234 file-level edges) are now an honest
reduced-confidence decline instead of a silent miss — full resolution
stays out of scope (the directory-segment argument would need evaluating
arbitrary Package.swift code to resolve correctly, which the buildless
design deliberately never does). Root cause #2 (**the larger effect**):
`@testable import Foo` / stacked `@_spi(Testing) @testable import Foo`
(a common real Swift test-file idiom) were not recognized at all — the
keyword-stripping tokenizer only pops tokens matching a fixed keyword set,
and an attribute's argument varies so it can never be listed there; the
un-stripped attribute text became the entire `module_name`, a garbage
string that can never match a real target. Fixed with a new
`strip_attribute_prefix` spec flag: any leading `@`-prefixed token is
stripped alongside the fixed keyword set. Recall: **88.57%** (13,130/
14,824) before the attribute fix → **98.42%** (14,590/14,824) after, with
the residual 234/234 misses all `_RopeModule` (now honestly flagged, not
silent) and 0 elsewhere. Re-running against the original Kickstarter
corpus after both fixes: still 100% module-index coverage, `unresolved_
intra` still 0, and total resolved import edges rose from 384,278 to
660,716 — the attribute-prefix fix recovers real `@testable import`
edges (1,477 real occurrences in that corpus alone) that were previously
silently lost there too. See the [harness
README](../internal-docs/planning/dogfood-findings/swift-recall-oracle/README.md#second-corpus-back-669-swift-collections-overfit-guard)
for the full write-up.

¹⁹ C#'s import-recall history (BACK-544 namespace index, BACK-554
`depends://` wiring) never got a from-scratch-oracle full-population
percentage the way every other measured language did — this closes that
gap AND runs the BACK-669 overfit guard in the same slice. Baseline
(Jellyfin, `samples/csharp`, 2,098 files): a from-scratch independent
namespace/type oracle (`build_oracle.py` — C# `using`/`using static`/alias
statements resolved via an independently regex-built namespace-declaration
index and (namespace, type) index, never calling `depends://`'s own
resolver) found **99.9970%** recall pre-fix (1,754 targets, 99,654 edges,
3 missing), then **100.00%** (0 missing) after **BACK-702**. Root cause:
`using Alias = Foo.Bar.Type;` (the dominant real alias shape, 87/96 real
alias statements) and `using static Foo.Bar.Type;` name a specific TYPE,
one dotted component past any namespace the tree declares — the
namespace-fan-out index never matches, and the plain directory-suffix
match only succeeds when the physical layout mirrors the dotted namespace
*and* the type's filename is tree-wide unique; real multi-project C# repos
violate both (Jellyfin's top-level dirs like `MediaBrowser.Controller`
embed a literal `.` as one path component, and `LinkedChildType` is
declared in two different namespaces, both under an `Entities/`
directory, making the bare-basename fallback correctly decline on
ambiguity). Fixed via a new `namespaced_type_fallback` spec flag reusing
the existing Kotlin/Scala `member_index`/`resolve_member_targets`
machinery, keyed `(namespace, type_name)` instead of `(namespace,
symbol)`. Second corpus (overfit guard): `JamesNK/Newtonsoft.Json`, a
single-project library (945 files) — deliberately different shape from
Jellyfin's large multi-project ASP.NET monorepo, and (unlike Jellyfin) uses
`#if`/`#else` multi-target-framework conditional compilation extensively
(528/945 files), stress-testing the oracle's directive handling and
BACK-702's fix on a much higher alias density (654 alias statements vs.
Jellyfin's 96, 322 resolved via the new fallback). Full population: 793
targets, 48,400 oracle edges, **99.3636%** recall (308 missing, all 308 on
one target file), 0 false positives. The one residual — filed **BACK-703**,
not fixed — is a genuine tree-sitter-c-sharp grammar limitation, not a
resolver gap: `Src/Newtonsoft.Json.Tests/TestFixtureBase.cs` uses `#if
DNXCORE50 protected TestFixtureBase() #else [SetUp] protected void
TestSetup() #endif { ... shared body ... }` — a constructor and a method
with DIFFERENT declaration headers sharing one body across branches (legal,
compiles under either symbol set) — which tree-sitter's preprocessor-blind
grammar cannot parse into any valid declaration node, producing one giant
`ERROR` node that swallows the file's entire namespace body (namespace
declared, but invisible to `extract_namespaces`/`extract_namespaced_type_names`
as a result). Correctly honest-decline caveated (`confidence: reduced`,
`undercount_possible: true`), not a silent wrong zero — verified directly.
Only 4/945 files in the corpus hit any parse ERROR at all (0/2,098 in
Jellyfin, which has zero `#if` usage), so this is a narrow, documented,
out-of-scope class, not a systemic gap. Along the way, an oracle-only bug
was found and fixed (not a `depends://` bug): the oracle's original
`#if`/`#else` handling naively kept only the `#if` branch's statements,
which silently dropped 37 real edges whose `using` sat in the `#else`
branch of a legacy-condition-first `#if NET20 ... #else ... #endif` (the
real, modern-default branch) — fixed by counting every branch's body
unconditionally (matching reveal's own preprocessor-blind, safe-over-
inclusion parse behavior, the same policy already established for Go's
`//go:build` tags, BACK-685). See the [harness
README](../internal-docs/planning/dogfood-findings/csharp-recall-oracle/README.md)
for the full write-up.

²⁰ Overfit guard (BACK-714, child of BACK-708): re-ran the identical
independent-oracle-diff method against a second, unrelated real corpus
(`tigerbeetle/tigerbeetle`, a distributed database, 245 files — mostly-flat
`src/` layout, deliberately different shape from ghostty's deep
terminal-emulator tree — full population diffed, not sampled, 215 targets,
836 edges) to check whether the 100% ghostty result generalized. It did:
**100.0000%** recall, 0 missed, 0 false positives, no fix needed. 466 of the
corpus's `@import(...)` calls are named-module aliases (`@import("vsr")`,
`@import("stdx")`, ...), correctly out of scope per the same design as
ghostty's excluded `std`/`builtin`/build-graph aliases. See the [harness
README](../internal-docs/planning/dogfood-findings/zig-recall-oracle/README.md#second-corpus-back-714-overfit-guard-tigerbeetle)
for the full write-up.

²¹ Overfit guard (BACK-710, child of BACK-708): re-ran the identical
per-directive isolated-`gcc -H` oracle method against a second, unrelated
real corpus (`curl/curl`, a client-side networking library, 468 files —
flatter `lib/`+`src/` layout with `lib/curlx`, `lib/vauth`, `lib/vquic`,
`lib/vssh`, `lib/vtls` subdirs and heavy cross-directory relative includes
such as `src/*.c` pulling `lib/curl_setup.h` and `"../include/curl/curlver.h"`
parent-relative navigation, deliberately different shape from Redis's
mostly-flat `src/` tree) to check whether the 100% Redis result generalized.
It did: **100.0000%** recall, full population diffed (not sampled, 232
targets, 2,330 edges), 0 missed. 173 apparent false positives, all confirmed
by direct grep to be genuine `#include` lines in `tests/unit/`, `tests/tunit/`,
`tests/libtest/`, `tests/server/`, and `projects/OS400/` files — the same
benign scope difference already documented for the Redis oracle (importer
scope deliberately limited to `lib/`+`src/` production code, while
`depends://`'s search root legitimately covers the whole corpus). No fix
needed. See the [harness
README](../internal-docs/planning/dogfood-findings/c-recall-oracle/README.md#second-corpus-back-710-overfit-guard-curl)
for the full write-up.

²² Overfit guard (BACK-711, child of BACK-708): re-ran the same
independent-regex oracle method against a second, unrelated real corpus
(AwesomeWM, a window manager, 882 files — no rockspec/build-manifest at all,
forcing pure directory-convention resolution vs. Kong's rockspec-backed
lookup). Found and fixed a real bug: a bare single-token `require("wibox")`
(393 call sites) was silently resolving onto an unrelated same-basename flat
file (`lib/awful/wibox.lua`) instead of the real directory-module target
(`lib/wibox/init.lua`, which showed 0 dependents) — the k=1
global-basename-uniqueness fallback used for single-token imports had no
structural relationship to the import site. Fixed by checking the
directory-index candidate first for single-token imports, falling back to
the flat file only when it's a *true sibling* of the directory (same parent
— `lib/beautiful.lua` next to `lib/beautiful/init.lua`, a second real shape
in the same corpus, correctly still resolves to the flat file). Full
population diffed (170 targets, 2,552 edges): **99.33%** recall, 0 → 2,535
matched after the fix. Residual 17 misses trace to AwesomeWM's
`tests/examples/{text,shims}/` trees literally mirroring `lib/`'s module
path structure (e.g. both `lib/gears/sort/topological.lua` and
`tests/examples/text/gears/sort/topological.lua` exist) — genuine structural
ambiguity a suffix-based resolver correctly declines rather than guesses on,
not a reveal bug. Residual 2 extras are a test-shim bare-token resolution
(`require("mouse")` → `lib/awful/mouse/init.lua`, same out-of-scope shim
class as the Kong loop's rockspec-external cases) and one testbed artifact
(search scope spanning the sibling `samples/lua` Kong corpus, an artifact of
the two corpora sharing a `samples/` root in this harness, not something a
real git-repo-bounded project would hit). 2 new regression tests
(`test_lua_bare_single_token_require_prefers_directory_module`,
`test_lua_bare_single_token_require_prefers_true_sibling_flat_file`), full
targeted suite (240 tests) green, Kong re-measured unchanged at 99.87%. See
the [harness
README](../internal-docs/planning/dogfood-findings/lua-recall-oracle/README.md#second-corpus-back-711-overfit-guard-awesomewm)
for the full write-up.

²³ Overfit guard (BACK-712, child of BACK-708): re-ran the same
independent-regex oracle method against a second, unrelated real corpus
(drift, a SQL-code-generation package — 1,171 files, 32 in-tree pubspec.yaml
packages under one melos workspace, vs. AppFlowy's 14 packages under a single
Flutter app). Baseline sampled recall was 91.24% (948/1,039 edges, 30-target
stratified sample): a real bug, concentrated almost entirely (88 of 91
misses) on drift's own barrel file (`drift/lib/drift.dart`). Root cause: a
`show`/`hide`/`deferred as` combinator clause trailing the quoted import URI
(`import 'package:drift/drift.dart' show OpeningDetails;` — 105 pure
show/hide statements in the corpus, plus more combined with `as`) was never
stripped before quote extraction. The generic `_build` parser's
strip-chars-off-both-ends pass only trims characters in the quote-strip set
from each *end* of the whole remainder; the trailing clause's characters sit
at the end instead, so nothing was trimmed and `module_name` ended up as the
literal garbage `"package:drift/drift.dart' show OpeningDetails"` — still
`package:`-prefixed enough to dispatch into `_resolve_package_uri`, but the
corrupted sub-path never matched a real file, so it silently returned `None`.
Fixed with a new opt-in `combinator_clause` spec flag: when set, `_build`
truncates the parsed remainder at the closing quote of its leading quoted
literal before extracting `module_name`, dropping any trailing clause
regardless of which keyword it uses. Re-measured: **96.63%** (1,004/1,039).
The residual 35 misses are all oracle false positives, the same class
AppFlowy's loop already documented — `drift_dev`'s own analyzer test suite
uses a `TestBackend.inTest({...})` virtual-file idiom that embeds literal
`import '...'` text inside Dart string-literal fixtures (`'a|lib/db.dart':
'''\nimport 'package:drift/drift.dart';\n...\n'''`), which tree-sitter
correctly never parses as a real import but the oracle's naive line-regex
does — **true recall on the sample is 100%** (real edges). 2 new regression
tests (`test_dart_package_uri_with_show_combinator_resolves`,
`test_dart_package_uri_with_deferred_as_combinator_resolves`), full targeted
suite (242 tests) green, AppFlowy re-measured unchanged at 99.76%. See the
[harness
README](../internal-docs/planning/dogfood-findings/dart-recall-oracle/README.md#second-corpus-back-712-overfit-guard-drift)
for the full write-up.

²⁴ Overfit guard (BACK-713, child of BACK-708): re-ran the same
independent-regex oracle method against a second, deliberately
differently-shaped corpus (Pixelorama, a pixel-art editor — 247 `.gd` files
under a single `project.godot`, vs. godot-demo-projects' 138 independent
Godot projects living side by side in one tree). Full census (small
population): 17 distinct targets, 63 edges, of which 58 (92%) resolve via
the `class_name`-based `extends` convention — the dominant edge shape here,
more so than in the v1 corpus. **100%** recall (63/63), no fix needed: the
single-project shape confirms the `class_name_convention` resolution fix
(from the v1 loop) generalizes correctly outside the many-independent-projects
topology it was built against. See the [harness
README](../internal-docs/planning/dogfood-findings/gdscript-recall-oracle/README.md#second-corpus-back-713-overfit-guard-pixelorama)
for the full write-up.

²⁵ Overfit guard (BACK-715, child of BACK-708): re-ran the same
relative-import oracle method (`JavaScriptExtractor._resolve_relative_js`,
the shared resolver behind every JS/TS/JSX/TSX extension) against a third,
deliberately differently-shaped corpus (react-router v5.3.4 — a 5-package
lerna-style monorepo, 180 `.js` files, pure JSX-in-`.js` with no `.jsx`
extension at all, vs. three.js's single-package plain-`.js` and Excalidraw's
single-package `.ts`/`.tsx`). Cross-package imports use bare package-name
specifiers (e.g. `react-router-dom` importing `"react-router"`), correctly
out of scope for this relative-import-only oracle, same as every other
node_modules bare specifier. Full census (small population): 112 distinct
targets, 222 edges. **100%** recall (222/222), 0 false positives, 0 misses
— no fix needed. Confirms the shared resolver (already fixed twice: the
TypeScript/VS Code loop, then this slice's own BACK-672 extension-omission
fix) holds up on a monorepo topology and a pure-`.js`-JSX extension mix
neither prior corpus exercised. See the [harness
README](../internal-docs/planning/dogfood-findings/js-tsx-recall-oracle/README.md#second-corpus-back-715-overfit-guard-react-router)
for the full write-up.

²⁶ Overfit guard (BACK-709, child of BACK-708, last of the seven BACK-708
languages): re-ran the same per-directive-isolated `g++ -H` oracle method
against assimp (Open Asset Import Library), deliberately different in
topology from the v1 Godot corpus — a plugin/format-importer architecture
(`code/AssetLib/<Format>/...`) instead of Godot's flat engine-core monolith,
and relative parent-directory quoted includes instead of Godot's
root-relative `-iquote` convention. Still `.h`-dominant (728 `.h` vs 23
`.hpp`), re-exercising the BACK-675 extractor-family-scoping fix under a
different directory shape. Full census (small population): 250 distinct
targets, 707 edges. **100%** recall (707/707), 0 missing — no fix needed.
50 reported false positives all spot-checked genuine: real `#include` edges
from `test/`/`tools/`/`contrib/` files the oracle's importer scope
deliberately excluded from ground truth, the same oracle-scope-gap shape as
the v1 corpus's `.mm` false positives, not a resolver defect. See the
[harness
README](../internal-docs/planning/dogfood-findings/cpp-recall-oracle/README.md#second-corpus-back-709-overfit-guard-assimp)
for the full write-up.

²⁷ First side-effect/boundary measurement for C (BACK-718/BACK-721, twelfth
language in the program), Redis `src/` corpus (5,073 functions). 40.18% pre-fix
→ 91.96% post-fix: `serverLog`/`serverPanic` (Redis's own logging/fatal-error
macros, unclassified at 800+ call sites) took `log` 0%→100%; Redis's `rio`/
`rdbWriteRaw` persistence primitives and generic `fflush`/`setenv`/`unsetenv`/
`nanosleep` (missing from every taxonomy table, not just C's) took `file`/
`env`/`sleep` each to 100%. **`http` stays at 0%, declined not fixed**: a bare
POSIX-socket addition (`connect`/`accept`/`listen`/`socket`/`send`/`recv`) was
tried and reverted after `scripts/check_taxonomy_collisions.py` found
catastrophic cross-language collision in `classify_call`'s unscoped mode
(`accept` alone: 3,947 Java hits) and broke two existing hard invariants
(`engine.connect`→db, `mailer.send`→unclassified); only the three unambiguous
`anet*` compound wrapper names were kept. Plain C's lack of receiver/dot
syntax means there is no way to scope a generic-English-verb pattern any
narrower than "the whole call" — see
[sideeffects-recall-oracle/c/C.md](../internal-docs/planning/dogfood-findings/sideeffects-recall-oracle/c/C.md)
for the full write-up.

²⁸ First side-effect/boundary measurement for Lua (BACK-718/BACK-722,
thirteenth language in the program), Kong API Gateway's `kong/` corpus
(2,551 functions). 61.62% pre-fix → 97.98% post-fix — but the pre-fix
number already reflects two structural fixes applied before any taxonomy
content: `classify_call`'s `_COMPILED_BY_LANG` fallback was silently using
the fully-unscoped table for ANY language with no entry yet (not just
`language=None`), confirmed live misclassifying ordinary `table.insert(t,
x)`/builtin `select('#', ...)` as `db` via Python/PHP's own scoped bare
verbs — fixed globally (`_COMPILED_COMMON_ONLY`), benefiting every
not-yet-measured language, not just Lua; and Lua's colon-call syntax
(`obj:method(...)`, the dominant call idiom in this corpus) was entirely
invisible to the tokenizer (`_DELIM_RE` never split on `:`) regardless of
taxonomy content — fixed, corpus-verified cross-language-safe. Taxonomy
additions: Kong's own DAO/connector verbs (`query`/`escape_literal`/
`upsert`, `pgmoon`/`cassandra`) and OpenResty's `resty.http` idiom
(`http.new`/`request_uri`/`ngx.location.capture`/`ngx.socket.`) took `db`
to 100% and `http` to 90.9%. **Declined, corroborating C's `http` finding**:
bare `insert`/`select`/`update`/`delete` (Lua stdlib `table.insert`/builtin
`select()`/OpenSSL `digest:update`/shared-dict `:delete` all collide, the
same BACK-633/636 class); bare `truncate` (clean in Lua alone, but real
POSIX-file-truncation collision in Java/Go/C++); bare `connect`/`request`
(the C loop's declined POSIX `connect` class, plus `request` would tag
Kong's own `kong.request.*` incoming-request accessors as outbound HTTP) —
see
[sideeffects-recall-oracle/lua/LUA.md](../internal-docs/planning/dogfood-findings/sideeffects-recall-oracle/lua/LUA.md)
for the full write-up.

²⁹ First side-effect/boundary measurement for Zig (BACK-718/BACK-725,
fourteenth language in the program), TigerBeetle's `src/` corpus (3,884
functions). 53.23% pre-fix → 98.39% post-fix — the pre-fix number already
reflects the Lua loop's `_COMPILED_COMMON_ONLY` fix (confirmed still
holding: no Python/PHP-scoped bare verb leaked into Zig identifiers) and
confirms Lua's `_DELIM_RE` colon fix is irrelevant here (Zig has no bare
`:` call-receiver syntax). No new reveal structural bug — instead a bug in
this loop's OWN oracle extraction code: Zig's dominant generic-type-
returning-function idiom nests real, independently queryable methods
inside an outer function's body (`message_bus.zig`'s entire public API is
declared this way); a naive brace-depth scanner that jumps past a matched
function's whole body (safe for C, which never nests function
definitions) silently swallowed every nested method into one giant outer-
named record, undercounting the corpus by more than a third before being
caught via cross-checking real `--outline` line numbers. Taxonomy
additions: TigerBeetle's own storage/network-boundary verbs
(`read_sectors`/`write_sectors`, two-segment `io.write`/`io.read`/
`io.connect`/`io.accept`/`io.listen`/`io.recv`/`io.send`, direct-POSIX
`posix.connect`/`posix.accept`/`posix.socket`/`std.net.` for call sites
bypassing the `io` wrapper) took `file`/`http` to 92.6%/100%; Zig stdlib
camelCase compounds (`openDir`/`openFile`/`makeOpenPath`/`deleteTree`/
`selfExePath`/`statFile`/`copyFileAbsolute`/`realpathAlloc`,
`getEnvVarOwned`/`getEnvMap`, `debug.print`) — the tokenizer-doesn't-split-
camelCase gap class — took `env`/`log` to 100%. Bare POSIX `pwrite`/`fsync`
corpus-collision-checked and kept (universally file-I/O-only meaning
across every corpus hit, same reasoning as Lua's kept `upsert`). Two
residual `file` misses left open, neither a taxonomy gap: a struct-literal
construction with no call node to attribute, and a genuine ORACLE
false-signal (this loop's own broad `std.fs.*` regex over-matching a pure
path-string function, `isAbsoluteWindowsWTF16`) — not a reveal recall gap.
Also corpus-confirmed, for a third time in the program, that a
pre-existing `_TAXONOMY_COMMON` bare-verb collision (`'header'`→http,
`'open'`→file) fires on TigerBeetle's own domain accessor/lifecycle
methods — not fixed (common-scoped, cross-language blast radius, out of
scope) — see
[sideeffects-recall-oracle/zig/ZIG.md](../internal-docs/planning/dogfood-findings/sideeffects-recall-oracle/zig/ZIG.md)
for the full write-up.

³⁰ First side-effect/boundary measurement for Scala (BACK-718/BACK-720,
fifteenth language in the program), GitBucket's `src/main` corpus (a real
production Scala/Scalatra Git-hosting web app, 939 functions — NOT sbt
itself despite the task's initial description). 33.72% pre-fix → 66.28%
post-fix — the pre-fix number confirms the Lua loop's `_COMPILED_COMMON_ONLY`
fix holds for a 4th language, and Lua's `_DELIM_RE` colon fix is confirmed
irrelevant (Scala's `:` is type-annotation/named-arg syntax only). New
reveal structural bug found and fixed: Scala's `new Foo(args)` constructor
calls parse to `instance_expression`, a tree-sitter node kind entirely
absent from `CALL_NODE_TYPES` (distinct from PHP/C#'s
`object_creation_expression` despite the identical source shape) — 100+
corpus call sites (`new File`, `new FileOutputStream`, `new HttpPost`) were
invisible to `--calls`/`--sideeffects` before this fix, taking `file`
0%→100% and `env` 33%→100% combined with a handful of taxonomy additions.
**Dominant finding, and the reason `db` recall stays 0% (declined, not a
gap)**: GitBucket's Slick ORM persistence layer (`.filter`/`.insert`/
`.update`/`.delete`, 151 of 939 corpus functions) is deliberately designed
to look exactly like Scala's own built-in collection/`Option` API —
`classify_call()` only ever sees callee text, never a receiver's static
type, so there is no way to scope these verbs any narrower than "the whole
call" (`check_taxonomy_collisions.py` confirmed the same catastrophic
cross-language exposure already documented for Java's `.execute`/Ruby's
`.select`/Go's `.Insert`). Also fixed a Java-interop gap: Java's own
`_TAXONOMY_BY_LANG['java']` entry for `System.getProperty` (footnote-worthy
in its own right, BACK-639) does not extend to Scala files despite both
compiling to the identical `java.lang.System` class — language-scoping has
no cross-JVM-language sharing mechanism, so Scala needed its own duplicate
entry. Found and fixed a bug in this loop's OWN oracle extraction code (not
reveal): an expression-bodied `def`'s termination heuristic silently
swallowed an entire file's remaining sibling functions into one 659-line
bogus record before being caught via the same outlier-length sanity sweep
every loop since Zig has run. Closed: `external-git` commit `ea30d2f` landed
by the orchestrating session after independent re-verification (630
passed/2 xfailed re-confirmed, docs gate clean, diff reviewed) — see
[sideeffects-recall-oracle/scala/SCALA.md](../internal-docs/planning/dogfood-findings/sideeffects-recall-oracle/scala/SCALA.md)
for the full write-up.

³¹ First side-effect/boundary measurement for Dart (BACK-718/BACK-723,
sixteenth language in the program), AppFlowy's `frontend/appflowy_flutter/lib`
corpus (5,231 functions). 44.44% pre-fix → 84.85% post-fix. New structural
bug found and fixed: `cascade_section` calls (`recv..foo()..bar(x)`, used in
289 of 1,526 corpus files) were a third distinct no-call-expression-wrapper
shape invisible to `--calls`/`--sideeffects`, fixed in `nav_calls.py` (zero
measured recall impact on this loop's six categories — cascades here are
UI-builder chaining, not effect calls). Taxonomy: `dart:io`
`readAsString`/`writeAsBytes`-family + `path_provider` dirs (`file`),
`package:http` (`http`), `Future.delayed` (`sleep`). Bare `File`/`Directory`
constructor calls declined after `check_taxonomy_collisions.py` found 311
Dart-own-corpus hits (mostly local variables literally named `file`) plus
11k+/4.9k+/2.9k+ unscoped TypeScript/Java/Go hits — residual `file`-bucket
miss, not a fix. See
[sideeffects-recall-oracle/dart/DART.md](../internal-docs/planning/dogfood-findings/sideeffects-recall-oracle/dart/DART.md).

³² First side-effect/boundary measurement for GDScript (BACK-718/BACK-724,
seventeenth language in the program), Pixelorama's full corpus (3,131
functions — a real production Godot 4 pixel-art editor). 20.00% pre-fix →
69.33% post-fix. New structural bug found and fixed: `func _init(...)`
(GDScript's fixed-name lifecycle constructor) parses to its own
`constructor_definition` node kind, entirely absent from
`FUNCTION_NODE_TYPES` — GDScript has no wrapping class node for a top-level
script, so `_init` was invisible to `--outline` and errored on direct name
lookup, not just mis-scoped. Fixed via `treesitter.py`'s
`_constructor_definition_name`. Taxonomy: Godot 4's
`FileAccess`/`DirAccess` file API, `OS.*environment` accessors,
`push_error`/`push_warning`/`printerr`/`print_rich` logging,
`OS.delay_*`/`create_timer` sleep. Bare `print` (log) and bare `request`
(http) declined — both are the single dominant call for their category in
this corpus, but collision-checking showed thousands of unrelated hits
(7,976 C++, 1,829 Zig, 1,152 TypeScript for `print`; 785 Java, 422 PHP, 308
Lua for `request`) in every other measured language. `db` recall stays
honestly 0/0: no SQL/NoSQL client exists in Godot core or GDScript stdlib.
See
[sideeffects-recall-oracle/gdscript/GDSCRIPT.md](../internal-docs/planning/dogfood-findings/sideeffects-recall-oracle/gdscript/GDSCRIPT.md).

³³ First side-effect/boundary measurement for TSX/plain-JS (BACK-718/BACK-726,
eighteenth and final language in the breadth program), Excalidraw's
`samples/tsx/excalidraw` corpus (292 `.tsx`/`.jsx` files, 606 functions).
90.16% pre-fix → 98.36% post-fix. New structural bug found and fixed: a
named component wrapped in a higher-order call (`const Name =
React.forwardRef((props, ref) => {...})` / `React.memo(...)`, 47 corpus
occurrences) was entirely invisible to `--outline`/name-lookup because the
declarator's value is a `call_expression`, not a bare arrow/function
expression — fixed via `_call_wrapped_function_literal` in `treesitter.py`,
which looks one level into the call's own argument list for a sole
function-literal argument (a curried HOC like `connect(...)(Component)`
correctly stays unmatched). Taxonomy: `console.info`/`.debug`/`.trace`
(log, only `.log`/`.error`/`.warn` existed before) and browser
`localStorage` (`db`, IndexedDB's simpler key/value counterpart). Bare
`window.open` false-tagged as `file` declined — same cross-language
collision class as Zig/Go's declined bare verbs. `db`/`env`/`file` were an
honest corpus-*scope* absence for `.tsx`/`.jsx` specifically (this same
app's `.ts` files already have `process.env`/`fs`/IndexedDB coverage from
the prior TypeScript loop). See
[sideeffects-recall-oracle/tsx/TSX.md](../internal-docs/planning/dogfood-findings/sideeffects-recall-oracle/tsx/TSX.md).

³⁴ Python `calls://` pilot (BACK-730), Home Assistant core (213 files), three
independent query directions on the same corpus: reverse-lookup (`?target=`)
99.96% (2,632/2,633 sampled edges, 100-target stratified sample) — one real
miss, decorator-argument calls invisible to `calls://`, filed as BACK-731;
forward-lookup (`?callees=`) 100.00% (201/201, 32-target stratified sample)
after a harness bug in the oracle itself was fixed (keying decorated
functions by the decorator line, not the `def` line, to match `calls://`'s
own node boundary) — one false positive filed as BACK-732 (chained/
immediately-invoked calls produce un-normalized raw text); transitive lookup
(`?target=&depth=2`) 99.98% (9,967/9,969 edges, 20-per-bucket sample),
ground truth derived by BFS over the depth-1 oracle rather than a fresh AST
walk — the only miss is BACK-731 cascading one level deeper, not a new root
cause. See [calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md).
³⁵ TypeScript `calls://` pilot (BACK-730), VS Code's `src/vs/base` (307
files, reused corpus from the import-recall loop), reverse-lookup only:
100.00% recall, 0 false positives at both an 8-per-bucket (926 edges) and a
20-per-bucket (2,557 edges) stratified sample. Also surfaced (not a recall
gap) a previously undocumented `calls://` behavior — a call inside a nested
named arrow function is attributed to *every* enclosing scope up to the
nearest declared function/method, not just its own arrow — added to
[CALLS_ADAPTER_GUIDE.md](reveal/docs/adapters/CALLS_ADAPTER_GUIDE.md)'s
Limitations section.
³⁶ Go `calls://` pilot (BACK-730), the Go compiler's own internals
(`cmd/compile/internal`, 371 files, `testdata/`/`_test.go` excluded),
reverse-lookup only: 100.00% recall, 0 false positives, clean on the first
run at both an 8-per-bucket (1,168 edges) and a 20-per-bucket (4,418 edges)
stratified sample — no oracle-methodology fix needed, unlike Python/TS.
Go structurally cannot produce the JS/TS cascading-attribution shape (no
nested named function declarations, only closures, which never get their
own scope), confirmed live against a real corpus case.
³⁷ Rust `calls://` pilot (BACK-730), Meilisearch's `milli` crate (238
files), reverse-lookup only: first measurement 96.98%/95.27% (8-/20-per-
bucket samples) surfaced a real dominant gap — turbofish generics on a
call/method callee defeat the bare-callee-name extractor's naive last-`::`-
split (`size_of::<u32>()` misparsed as callee `<u32>`), plus a minor
parenthesized-callee gap (`(f)(args)` captures `"(f)"` literally) — filed
and fixed as **BACK-733** the same session; re-measured at **100.00%**
recall, 0 false positives, matching Go/TS. See
[calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md)
("Fourth language: Rust" section) for the full write-up.
³⁸ Java `calls://` pilot (BACK-730), Elasticsearch's `server/src/main/java`
(4,837 files), reverse-lookup only: first measurement **9.99%** recall
(198/1,982 oracle edges), 167 false positives — an order of magnitude worse
than any prior language. Root cause: `method_invocation`'s grammar puts an
optional `object` field *before* the `name` field, so the generic
`child(0)`-based callee extractor (correct for Python/JS/Go's grammars)
returned the call's object/qualifier as the "callee name" for every
qualified or static call (`obj.method()`, `Class.staticMethod()`) — nearly
all real Java call sites. Filed and fixed same-session as **BACK-734**
(field-based extraction via `child_by_field_name('name')`, mirroring the
existing PHP special-case); re-measured at **100.00%** recall, 0 false
positives, at both an 8-per-bucket (1,982 edges) and a 20-per-bucket
(4,009 edges) sample. Also surfaced that `javalang` (pure-Python, the
initially-planned independent-oracle parser) silently fails to parse
20.4% of this corpus (Java records, text blocks — both post-date
`javalang`'s last update) — escalated to JavaParser (a modern,
actively-maintained parser) plus a locally-installed JDK 17 rather than
accept a biased sample. See
[calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md)
("Fifth language: Java" section) for the full write-up.
³⁹ Ruby `calls://` pilot (BACK-730), Discourse's `app/`+`lib/` (1,899 files),
reverse-lookup only: a pre-flight tree-sitter grammar dump (done before
building the oracle at all, prompted by Java's BACK-734 precedent) found
the same bug class immediately — Ruby's `'call'` node is the same tree-
sitter kind Python's plain `call()` uses, but a flat receiver/./method/args
shape, so `child(0)` returned the receiver, not the method, for every
qualified/self/static call. Filed and fixed as **BACK-735** before the
first real measurement; a deliberate pre-fix run (via `git stash`, to keep
a documented before/after pair) measured **22.05%** recall (360/1,633
oracle edges), 30 false positives. Fixing BACK-735 alone brought recall to
99.02% — two more distinct bugs surfaced in the residual tail: `setter`/
`operator`-named methods (`def x=(v)`, `def [](k)`) invisible to
`--outline` entirely (same invisibility class as BACK-638/BACK-651/
BACK-724), and `def Class.method` singleton methods (qualified by a class
constant rather than `self`) naming themselves after the constant instead
of the method (`_PARAM_LIST_KINDS` was missing Ruby's `method_parameters`
node kind, so the correct name-extraction strategy never fired for any
Ruby method). Both fixed same session; re-measured at **100.00%** recall,
0 false positives, at both an 8-per-bucket (1,633 edges) and a
20-per-bucket (5,564 edges) sample. Also required compiling Ruby 3.4.1
from source via `rbenv`/`ruby-build` (Discourse's `Gemfile` requires `~>
3.4`; Ubuntu jammy's only `apt` Ruby package, 3.0.2, failed to parse 9.4%
of the corpus — modern hash-literal shorthand syntax) rather than accept a
biased sample, same precedent as Java's JDK/JavaParser escalation. See
[calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md)
("Sixth language: Ruby" section) for the full write-up.
⁴⁰ PHP `calls://` pilot (BACK-730), WordPress core's `wp-admin/`+
`wp-includes/` (1,328 files), reverse-lookup only: a pre-flight tree-sitter
grammar dump (same discovery method as BACK-734/BACK-735) found
`self::method()`/`parent::method()`/`static::method()`/`Class::method()`
all parse to `scoped_call_expression` — a node kind entirely absent from
`CALL_NODE_TYPES`, so every PHP static/scoped call was silently invisible
(not misnamed), arguably the highest real-world-impact gap in this program
since static-method calls are PHP OOP's dominant idiom. Filed and fixed as
**BACK-736** before the first real measurement; a deliberate pre-fix run
(via `git stash`) measured **98.87%** recall (2,460/2,488 oracle edges), 0
false positives — lower impact than Java/Ruby's dominant bugs only because
WordPress's `wp-includes/` leans procedural (bare-call volume dominates).
Fixing BACK-736 alone brought recall to 99.48% — tracing the residual tail
surfaced a second, distinct bug in `adapters/calls/index.py`'s
`_bare_callee_name` (the bare-name normalization layer, not the tree-sitter
extraction layer, same bug *class* as BACK-733's Rust turbofish gap):
`new ClassName()` construction calls and PHP's leading-backslash
fully-qualified-namespace calls (`\sprintf`, `\in_array` — common in any
namespaced file referencing a global-namespace builtin) were never
stripped down to a bare name, so neither ever matched a `?target=` lookup.
Both fixed same session; re-measured at **100.00%** recall, 0 false
positives, at both an 8-per-bucket (2,488 edges) and 20-per-bucket (5,585
edges) sample. See
[calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md)
("Seventh language: PHP" section) for the full write-up.
⁴¹ C# `calls://` pilot (BACK-730), Jellyfin (2,098 files), reverse-lookup
only: unlike Java/Ruby/PHP, a pre-flight tree-sitter grammar dump found no
missing node kind — the gaps here were one level deeper, in name/callee
*text* extraction. First measurement: **69.74%** recall (1,060/1,520 oracle
edges), 8 false positives. Tracing every miss found two distinct bugs: (1)
generic methods (`private T CreateItemByName<T>(...)`, `Task
Enqueue<T>(...)`) had their own definition name misattributed to the return
type (`T`, `Task`) — C#'s `type_parameter_list` sits between the method
name and parameter list, breaking `_name_via_param_adjacent`'s "name
immediately precedes param list" check, so extraction fell through to a
first-identifier scan that finds the return type first. This is a
caller-side gap, unlike every prior language's callee-side bugs — it
corrupts the *source* of every call-graph edge from an affected method, not
just whether a specific target matches. (2) Explicit generic-argument
suffixes (`new List<Video>()`, `Method<string>()`) survived into
`_bare_callee_name`, never matching a bare `?target=` lookup — same bug
*class* as BACK-733's Rust turbofish gap. Both fixed; re-measured at
**99.90%** recall (1,011/1,012 edges) — tracing the one residual miss found
a *third*, distinct bug: multi-line fluent call chains (Moq's
`_mock.\n    Setup(...)`, a common C# test idiom) left literal
newline+indentation in the bare callee name (`"\n    Setup"` !=
`"Setup"`). Fixed (`.strip()` on the final bare segment — identifiers can
never contain whitespace, unconditionally safe). All three fixed as a
single tracker item, **BACK-737**. Also found and fixed an oracle-side bug
(a qualified type nested inside a generic argument produced a garbage key
that hung a `calls://` query for 120s+ on the full 2,098-file corpus — not
an infinite loop, a real per-query wall-time characteristic of this
corpus's size, confirmed by testing the same target scoped to a single
file). Final measurement after all three fixes: **100.00%** recall, 0
false positives, at both an 8-per-bucket (1,012 edges) and 20-per-bucket
(2,828 edges) sample. See
[calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md)
("Eighth language: C#" section) for the full write-up.
⁴² Kotlin `calls://` pilot (BACK-730), Tivi (629 `.kt` files), reverse-lookup
only: a pre-flight grammar dump found no missing node kind. First
measurement: **99.69%** recall (644/646 edges, 8/bucket) — already the
highest first measurement in this program. Both misses traced to an
oracle-side design inconsistency (not a `calls://` bug): the Kotlin oracle
attributed primary-constructor parameter-default calls to the class name,
which `calls://` never does for any language (only function/method bodies
are caller scopes). Fixed the oracle to match precedent; re-measured at
**100.00%** recall, 0 false positives (8/bucket, 661 edges). At 20/bucket
(938 edges): **99.79%** recall — the 2 residual misses trace to a real
upstream `tree-sitter-kotlin` grammar bug, not a reveal extraction bug:
an annotation directly preceding a function type (`@Composable () ->
Unit`, ubiquitous in Jetpack Compose code) cannot be parsed — the grammar
consumes the type's leading `()` as the annotation's own argument list,
producing an `ERROR` node that drops the entire enclosing function from
structure extraction (confirmed: `showInBottomSheet` in
`BottomSheetOverlay.kt` is invisible to `--outline` entirely, not just
missing calls). Not fixable in reveal's Python layer — the grammar-pack
version that might fix it is blocked by the already-tracked BACK-573/
BACK-620 core-API migration (deferred pending a concrete driver). Filed
**BACK-738**, open — a data point for that future call, not grounds to
trigger it now. See
[calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md)
("Ninth language: Kotlin" section) for the full write-up.
⁴³ Swift `calls://` pilot (BACK-730), Signal-iOS's `SignalServiceKit`
module (1,190 files), reverse-lookup only: a pre-flight grammar dump
(done just before this session) had already found and fixed a real gap
(`constructor_expression`, Swift's generic-call/generic-initializer node,
missing from `CALL_NODE_TYPES`); a second pre-flight check found and fixed
`init`/`deinit` — their own distinct node kinds
(`init_declaration`/`deinit_declaration`), entirely absent from
`FUNCTION_NODE_TYPES` — before the oracle even ran. First real
measurement: **97.62%** recall (821/841 edges, 8/bucket), 0 false
positives. Tracing every miss found two real `calls://` bugs: (1)
`!isRunning(x)` (negated predicate call) parses as one
`prefix_expression` callee node — the leading `!` survived into the index
key, never matching a bare `?target=isRunning` lookup; (2) operator
overloads (`static func -(left: CGSize, right: CGSize)`) name themselves
with a literal operator-symbol token whose tree-sitter KIND *is* the
operator text, invisible to every `_name_via_*` strategy — every operator
overload was entirely absent from `--outline`/`get_structure()`. Both
fixed: **99.92%** recall (1,178/1,179 edges, 8/bucket), 0 false
positives. At 20/bucket (2,821 edges): **99.79%** recall — the 6 residual
misses trace to two distinct upstream `tree-sitter-swift` grammar bugs,
neither fixable in reveal's Python layer: `return <name>.member` inside a
`case let .x(name):` switch pattern produces a parse `ERROR` that
cascades to drop most/all of the *rest of the file* from structure
extraction (confirmed via a 7-line repro; same "whole function vanishes"
symptom shape as Kotlin's BACK-738), and `A * B(args)`/`A - B(args)` (a
multiplicative/additive operator immediately before a call) misparses the
call suffix onto the whole binary expression instead of just the call,
corrupting the extracted callee text (comparison operators like `==` do
not exhibit this). Both blocked on the same BACK-573/BACK-620
grammar-pack ceiling as BACK-738. Filed **BACK-742**, open. See
[calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md)
("Tenth language: Swift" section) for the full write-up.

⁴⁴ C++ `calls://` pilot (BACK-730), assimp's `code/` subdir (218 `.cpp`/
~220 `.h`/`.hpp`, 400/440 files parsed clean), reverse-lookup only. Pre-
flight found no new `CALL_NODE_TYPES` gap (a prior session had already
fixed `new_expression`); the one finding, member-function-pointer
declarations without `typedef` misparsing as nested `call_expression`
(an upstream `tree-sitter-cpp` grammar ambiguity), was filed as **BACK-745**,
open, not fixable in reveal. Unusually, no `calls://` bugs were found or
fixed this session — all corrections were on the *oracle* side (built
against libclang, which semantically resolves straight through typedefs
and macro expansions to targets a syntax-only tool can never match): fixed
member-initializer-list calls being counted as caller scope, typedef/
macro over-resolution of callee names (both fixed via one general
correction — derive the name from the cursor's raw source-extent text
instead of any semantic API), direct-initialization variable declarations
(BACK-744's own ambiguity) being misread as calls, and whole-method codegen
macros collapsing every nested extent to the macro-invocation site. First
measurement: **95.28%** recall (8/bucket) → **95.73%** (3,277/3,423 edges,
20/bucket), 632 false positives — cross-checked and found to be mostly
oracle-incompleteness (the ~40 skipped files), not `calls://` bugs. Two
narrow residual misses left undiagnosed (~1% of sampled edges, a further
partial-macro-collapse variant and one unexplained case) — not filed, no
evidence either is a real `calls://` gap. See
[calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md)
("Eleventh language: C++" section) for the full write-up.

⁴⁵ Scala `calls://` measurement (BACK-730, twelfth language), GitBucket's
`src/main/scala` (213 files), reverse-lookup, oracle built against **scalameta**
(Scala's canonical syntax-only parser — the same "real compiler frontend"
precedent as JavaParser/syn/SwiftSyntax/libclang). Unlike C++, three distinct
real `calls://` bugs were found and fixed: **BACK-746** (infix method calls
`a :: b`/`list map f`/`Accounts filter pred` parse to `infix_expression`, a node
kind absent from `CALL_NODE_TYPES` — the dominant gap, since infix invocations of
`filter`/`getOrElse`/`map`/`flatMap` are ubiquitous in idiomatic Scala; the
`operator` field is the method name); **BACK-747** (qualified constructor types
`new java.io.File(...)` as a `stable_type_identifier`, and qualified generics
`new scala.Array[Byte](...)`, dropped by the `instance_expression` handler); and
a symbolic-named-method-definition residual (`def *` Slick projections, `def +`/
`def ::` operator overloads use an `operator_identifier` name node, invisible to
`--outline`/`get_structure()` or mis-named after a body/param identifier — so
calls in their bodies had no caller scope; fixed with a Scala operator-name
strategy that runs before the identifier strategies). **96.64%** → **100.00%**
recall, 0 false positives, both 8/bucket (1,039 edges) and 20/bucket (1,651
edges) samples. Symbolic-operator *callees* (`==`/`&&`/`+`/`::`) excluded from
the sampled pool as a URL-encoding edge case but verified faithful via direct
`find_callers` (matching the oracle exactly). Two oracle-side alignments (not
`calls://` bugs) mirrored established precedent: secondary constructors named
`this`, and primary-constructor parameter-default calls not counted as caller
scopes (the Kotlin-oracle rule). Also surfaced **BACK-748**, a separate,
broader bug filed not fixed: `calls://` forward-lookup (`?callees=`) and
`--rank` apply the Python-builtins filter to *all* languages, silently dropping
`.map`/`.filter`/`.zip`/`.min`/`.sum` etc. in Scala/Java/Ruby/…; the
reverse-lookup path this measurement uses is unaffected. See
[calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md)
("Twelfth language: Scala" section) for the full write-up.

⁴⁶ C `calls://` measurement (BACK-730, fifteenth language), Redis's `src/`
(125 `.c` + 83 `.h`, `deps/`/`curl/`/`modules/`/`src/modules/`/`tests/`
excluded), reverse-lookup, oracle built against **libclang** (adapted from
the C++ oracle — C is a strict subset of what libclang parses). No new
`calls://` bugs found in the extraction layer; every real fix landed in the
oracle. Two general oracle-side bugs, both new to this program: (1) Clang's
`cursor.extent` offsets are BYTE offsets, but the C++ oracle (and this one's
first draft) sliced a Python `str` — silently wrong the moment a file has any
non-ASCII byte (one curly-apostrophe comment in `networking.c` corrupted
~6 targets' extraction by 2 characters each); fixed by slicing raw `bytes`.
(2) A plain call physically nested inside a variadic logging macro's `...`
argument (`serverLog(LL_WARNING, "%s", strerror(errno))`) loses ALL position
info under macro re-expansion (`cursor.extent` collapses to zero-width,
unlike every prior macro case in this program); `cursor.spelling` is safe to
trust here (nothing is aliased, just uncoordinated), guarded to require ≥1
real argument so it doesn't also fabricate calls from object-like macro
constants like `HUGE_VAL`. The dominant false-positive source was Redis's
extensive `#ifdef`-gated optional-feature/self-test code — calls:// (never
preprocessing) sees every branch unconditionally; fixed by compiling with a
maximal "every optional feature on" flag set (`DEBUG_DEFRAG_FORCE` alone
fixed ~45 of the first run's remaining false positives, unlocking
`defrag.c`'s entire real implementation). One real, narrow tree-sitter-c
grammar bug found and filed as **BACK-756** (open, not fixed — same class as
Kotlin's BACK-738/Swift's BACK-742/C++'s BACK-745): a multi-line macro
definition in `ziplist.c` desyncs the parser into ERROR-recovery, silently
dropping the following function from `get_structure()` entirely. **89.52%**
(first run) → **100.00%** recall, 17 false positives (8/bucket, 1,196 edges),
100.00% recall, 33 false positives (20/bucket, 2,826 edges) — all remaining
false positives trace to documented, accepted residual classes (2
unparseable Solaris/BSD-only files, several headers-unavailable feature
flags, two permanently-`#if 0`-disabled dead-code blocks), none `calls://`
defects. See
[calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md)
("Fifteenth language: C" section) for the full write-up.

⁴⁷ Lua `calls://` measurement (BACK-730, sixteenth language), Kong API
gateway's `kong/` package dir (605 `.lua` files, 604 parsed clean under
luaVersion 5.3 — 1 excluded, `router/transform.lua`'s `0x01ULL`, a
LuaJIT-only 64-bit-integer literal suffix no standard-Lua parser
recognizes), reverse-lookup, oracle built against `luaparse` (npm, 0.3.1).
Two real, distinct `calls://` bugs found and fixed. **BACK-757**:
`_bare_callee_name` split only on `->`/`.`/`::`, never a lone Lua `:`
(`db:init_connector()`, `self:check_version_compat()` — Lua's DOMINANT
OOP method-call idiom, confirmed via a real Kong grep), so every
colon-method call's bare callee stayed the full `"receiver:method"`
string and never matched a bare `?target=method` lookup — the single
highest real-world-impact gap this session, same bug class as Rust's
turbofish (BACK-733) / PHP's namespace-prefix (BACK-736) / C#'s
generic-suffix (BACK-737) normalization misses; adding a plain
`rfind(':')` to the same `max(...)` is safe for `::`-using languages too
(C++/PHP/Java's `Class::method` unaffected — confirmed both by direct
test and by reasoning about where the two rfind results can land).
**BACK-758**: `name = function(...) end` / `tbl.k = function(...) end`
(module-table method idiom) / `{ key = function(...) end }`
(table-constructor field, Lua's metatable-dispatch/event-handler-table
idiom) were ALL entirely invisible to `get_structure()`/`--outline` — not
just their calls, the whole scope — found via a real Kong corpus grep
(643 occurrences of `= function(` across 176 files); fixed by adding
Lua-specific scope extraction (mirroring JS/TS's `_arrow_or_fn_value`
precedent for a function-literal value that carries no name of its own).
Fixing BACK-758 surfaced its own false-positive bug in the same session
(caught and fixed before the measurement ran, not filed separately): the
table-constructor-field extraction naively took "the first identifier
child" of a `field` node, which also matches a COMPUTED key's bracketed
expression (`{ [CONTENT_TYPE_POST] = function(...) end }`, a real
dynamic-dispatch idiom in `pdk/service/request.lua`) — misattributing the
value function's calls to the key expression's name, not a real function
name at all; fixed by requiring the identifier be the field's structural
FIRST child (a literal string key), never one preceded by `[`.
**100.00%** recall, 0 misses at both 8/bucket (1,422 edges, 11 false
positives) and 20/bucket (3,549 edges, 23 false positives) — every
remaining false positive traces to the one excluded unparseable file
(`router/transform.lua`) or one inherent bare-name-matching limitation (a
function *parameter* named `fmt` shadowing the corpus-wide `fmt` module
in `dns/stats.lua` — `calls://` does no scope/binding resolution, so a
local name shadowing a global is indistinguishable from the real thing;
not a Lua-specific bug, the same class of limitation as every other
language's bare-name matching). No cascading attribution (confirmed
empirically before writing the oracle, unlike Zig/JS-TS): Lua's
`function_declaration`/`function_definition` are both ordinary
`FUNCTION_NODE_TYPES` members, so the shared complexity/calls walk stops
at every nested function boundary the same as Go/Rust. Also confirmed via
a real-CLI dogfood detour: the installed `reveal_cli` site-packages
copy (0.107.1) is stale relative to `external-git` and gets silently
picked up instead of it whenever the CLI runs from a directory outside
`external-git` with no `PYTHONPATH` set — cost real debugging time before
being traced to `sys.path` ordering, not a new Lua-specific bug, but
worth flagging again for the next language's session. See
[calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md)
("Sixteenth language: Lua" section) for the full write-up.

⁴⁸ GDScript `calls://` measurement (BACK-730, seventeenth language),
Pixelorama (pixel-art editor), `samples/gdscript_pixelorama/` (247 `.gd`
files, one coherent Godot project — single `project.godot` — 246 parsed
clean, 1 excluded), reverse-lookup, oracle built against the npm
`tree-sitter-gdscript` package (6.1.0, native `node-tree-sitter` binding
— an independent runtime/binding from reveal's own Python
`tree_sitter_language_pack`, per this program's independence bar). One
real, dominant `calls://` bug found via a pre-flight grammar dump and
fixed. **BACK-759**: `self.foo()` / `obj.method()` / `Class.static()` /
`ClassName.new()` (GDScript has no `new` keyword — `.new()` on the class
name IS the constructor-call convention) and every segment of a chained
call (`a.b().c()`) parse to `attribute_call`, a node kind entirely absent
from `CALL_NODE_TYPES` — arguably the single most common call idiom in
any real GDScript codebase (every `self.`-qualified call and every object
instantiation), silently invisible to `calls://` entirely. Unlike every
other dotted-call node kind in this table (Java's `method_invocation`,
Ruby's `call`, PHP's `member_call_expression`), the receiver is not a
field or child of the call node — `tree-sitter-gdscript` models
`a.b().c()` as one flat `attribute` parent with a
`(receiver, '.', segment, '.', segment, ...)` sibling list, so
`attribute_call` only ever carries its own name + arguments. Fixed with a
new `_callee_name_gdscript_attribute_call` that reconstructs the
qualified name from a raw source-text span (the enclosing `attribute`
node's start up to the `.` immediately preceding this call), mirroring
Java/Ruby's receiver-qualified convention without a receiver *node* to
read from directly. This surfaced a second, narrower regression once
`attribute_call` became a `CALL_NODE_TYPES` member: `nav_calls.py`'s
`range_calls` (the `ast://`/`--calls`/`--sideeffects`/`--boundary` path,
separate from the `calls://` cross-file adapter) already had its own
GDScript-specific flat-chain reconstruction (`_extract_gdscript_
attribute_calls`, added earlier under BACK-431) that never depended on
`CALL_NODE_TYPES` membership — with `attribute_call` now a member, the
walk's generic per-node check ALSO matched it directly mid-chain,
emitting a second, wrongly-bare duplicate entry for every dotted call
(caught immediately by an existing regression test going from 1 to 2
callees on `x.field.method()`); fixed by excluding `attribute_call` from
that generic check, since the dedicated chain scan already covers it
correctly. **100.00%** recall, 0 misses at both 8/bucket (1,099 edges, 6
false positives) and 20/bucket (2,678 edges, 18 false positives) — every
false positive traces to one excluded file, `ExportDialog.gd`: it
declares and calls a function literally named `export`
(`func export() -> void: ...`), and this oracle's npm grammar build
parses the bare call `export()` as a grammar `ERROR` (`export` treated as
reserved even in call position), while reveal's own bundled
`tree_sitter_language_pack` (1.8.1) build of the identical upstream
grammar parses the same file with zero errors and correctly extracts
both the function and its one call site (confirmed directly against
`GDScriptAnalyzer.get_structure()`) — a genuine grammar-BUILD skew
between two independently vendored copies of the same grammar, running
in the OPPOSITE direction of every prior residual in this program (the
tool under test parses it fine; the oracle's tool does not), so excluding
the file is the correct call rather than fabricating a false miss. No
cascading attribution for named `function_definition`/
`constructor_definition` scopes (ordinary `FUNCTION_NODE_TYPES`
boundary-stop, same no-bleed shape as Go/Rust/Lua); GDScript's `lambda`
(anonymous/optionally-named function-VALUE syntax, `func(...): ...` /
`func inner(...): ...`) is confirmed empirically — not assumed — to get
NO scope of its own at all, named or not: calls inside any lambda bleed
straight through to the nearest enclosing named function, the identical
"transparent boundary, no cascading mechanism" shape as Lua's BACK-758
anonymous-function-value precedent, not a bug (a pre-flight corpus grep
found 0 named-lambda-variable occurrences in this exact corpus, so
low-stakes here regardless). See
[calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md)
("Seventeenth language: GDScript" section) for the full write-up.

⁴⁹ Dart `calls://` measurement (BACK-730, eighteenth and FINAL language),
AppFlowy's `frontend/appflowy_flutter/lib` (1,526 `.dart` files, one
coherent Flutter app package, 100% parsed clean), reverse-lookup, oracle
built against Dart's own canonical `package:analyzer` (purely syntactic
`parseFile`, no semantic/type resolution needed). `calls://` had
effectively NO Dart call-graph support before this session — Dart's
grammar has no dedicated call-expression node kind at all, a total blind
spot larger than any prior language's gap. Six distinct bugs found, all
but one fixed: **BACK-760** — plain/dotted/cascaded/null-safe calls parse
to a flat `(primary, selector*)` sibling run with no wrapping call node
(`argument_part`, the `(args)` selector, is the only call marker), and
`List<int>.from(...)`-style generic-typed constructor calls parse to a
separate `constructor_invocation` node — both absent from
`CALL_NODE_TYPES`. **BACK-761** — `constructor_signature`/
`factory_constructor_signature` absent from `FUNCTION_NODE_TYPES`: every
constructor had no caller scope. **BACK-763** — the explicit pre-Dart-2
`new Foo(...)` form shares `new_expression` with C++/JS/TS but neither
existing field-based extractor handles Dart's flat, field-less shape.
**BACK-764** — a constructor WITH an initializer list (`Foo(...) :
super(...) { ... }`, Flutter/BLoC's dominant constructor idiom) wedges an
`initializers` sibling between the signature and the body, defeating
`_function_end_node`'s pairing lookup and truncating the WHOLE body's
calls to empty; initializer-list calls themselves also live outside
`body_node` and need a separate merge. **BACK-765** — `const
Duration(...)`-style explicitly-const constructor calls (Flutter's
recommended default whenever every argument is constant) parse to a
third flat-constructor node, `const_object_expression`, also absent from
`CALL_NODE_TYPES`. **BACK-766**/**BACK-767** — getters/setters
(`getter_signature`/`setter_signature`) and `const`-marked constructors
(`constant_constructor_signature`) were BOTH absent from
`FUNCTION_NODE_TYPES` (no caller scope at all), and parameter DEFAULT
VALUES for any signature kind (`{int x = compute()}`) live outside
`body_node` the same way initializer lists do. **BACK-769** —
`super.method()`/`await super.method()` (override delegation) has its
qualifier as a bare sibling with no wrapping `selector` node, or nested
one level inside `await_expression`'s own children — a shape the initial
flat-sibling extractor didn't handle. A structural cascading bug was also
found and fixed pre-oracle: Dart's disjoint `function_signature`/
`function_body` sibling pairing meant the shared complexity/calls walk's
`FUNCTION_NODE_TYPES`-boundary stop condition didn't actually stop at a
NESTED named local function — its body, a separate sibling, kept being
walked by every enclosing scope, double-counting its calls; fixed by
detecting and skipping a nested signature's paired body sibling. **100%**
recall at 8/bucket (2,337 edges, 0 false positives); **97.55%** at
20/bucket (4,668/4,785 edges, 0 false positives) — every residual miss
traces to the ONE class left open, **BACK-768**: an upstream
`tree-sitter-dart` grammar ambiguity, not a reveal bug — a single-argument
generic call (`getIt<Foo>(x)`, `getIt<Foo>(name: x)`,
`BlocBuilder<A,B>(builder: ...)`) is misparsed as a
`relational_expression`/record-literal chain instead of a generic
function call whenever the argument list has exactly one element (0 or
2+ arguments parse correctly) — genuinely ambiguous to a context-free
grammar without semantic/import resolution, not fixable in reveal's
Python extraction layer. A second, oracle-side-only bug was also found
and fixed before trusting the final numbers: `package:analyzer`'s
`InstanceCreationExpression` for an un-namespaced dotted `const`/`new`
NAMED constructor call (`const EdgeInsetsDirectional.only(...)`) leaves
`constructorName.name` null and puts the WHOLE dotted path in
`constructorName.type` (can't distinguish "Class.namedCtor" from a
library-prefixed plain type without semantic info) — the oracle's first
draft used the unstripped dotted type text as ground truth, manufacturing
191 false positives against `calls://`'s own (correct) bare-last-segment
name; fixed oracle-side by taking the final dotted segment. See
[calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md)
("Eighteenth language: Dart" section) for the full write-up. This was the
LAST of the 18 `VALIDATION.md`-tracked languages — the full calls://
recall sweep BACK-730 opened is now complete.

## Import/Dependency Recall

### Method

For each language below, we built (or used) an **authoritative external
oracle** — never reveal's own code, and never a synthetic toy fixture — and
diffed it against `depends://`'s answer on a **real, unmodified open-source
codebase**:

- **The oracle is independent.** Where the language ships its own resolver,
  we called it directly: TypeScript's `ts.resolveModuleName` (the compiler's
  own API), Go's `go list -json` (the real toolchain), Python's `ast.parse`
  plus a from-scratch filesystem/`sys.path` walk. Where no callable resolver
  exists, we hand-built a buildless oracle from the language's own written
  specification (e.g., Java: JLS package/filename convention — "a class named
  `Foo` in package `a.b` lives at `a/b/Foo.java`," checked directly against
  the file tree, no `javac`/classpath involved).
- **The corpus is real, not synthetic.** A synthetic fixture measures whether
  we implemented a resolver correctly against our own mental model of the
  language; it says nothing about which idioms *actually occur* in shipped
  code, at what frequency, or in what combination. Every measurement here
  runs against a real, well-known open-source project's actual source tree
  (Kubernetes, Elasticsearch, VS Code, Home Assistant, Discourse, Meilisearch,
  Jellyfin, GitBucket, a real Android/KMP app).
- **Recall is the metric, not precision.** A false positive is a nuisance you
  can adjudicate at a glance. A false negative in a dependency graph is
  invisible — it looks exactly like "nothing imports this," which is
  indistinguishable from a right answer unless you already know the ground
  truth. Every number below is: *of every edge the oracle says truly exists,
  what fraction did reveal find?*

Each measurement loop follows the same shape: build the oracle, diff it
against reveal's output on a stratified sample (spanning low- to high-fan-in
targets so a resolver bug isn't masked by testing only easy cases), root-cause
every miss to an exact line of code, fix it, and re-measure to confirm the fix
actually closes the gap without introducing false positives.

### Results

| Language | Real corpus | Oracle | Sample | Recall: before → after | False positives | Bug(s) found & fixed |
|---|---|---|---|---|---|---|
| TypeScript | VS Code (`src/`, 7,401 files) | `ts.resolveModuleName` (real compiler API) | 29-file stratified sample, 1,714 edges | 2.98% → **100%** | 0 | Resolver stripped *characters* not a *prefix* on multi-level `../../` relatives, destroying most deep-tree imports; chained suffix-handling mangled multi-dot filenames (`foo.contribution.js`) |
| TypeScript (barrel follow-up) | VS Code extensions | same | 21-target sample, 158 edges | 98.10% → **100%** | 0 | Bare `.`/`..` directory-barrel specifiers misclassified as having a file extension, skipping directory/index resolution |
| TypeScript (overfit guard, BACK-669) | nestjs/nest (pnpm/lerna workspace monorepo, no `node_modules/@nestjs/*`) | Same oracle mechanism (`ts.resolveModuleName`, pinned TS 5.6.3), full population | Full population, 843 targets, 2,890 edges | **68.48%→81.21%** (BACK-694+BACK-698 both fixed; residual gap open) | 701 pre-fix / 1,071 post-fix (undercount, not safe over-inclusion) | Not a barrel re-export depth bug — `_parse_reexport_statement` correctly extracts `export * from`/`export { X } from` edges. Root cause: `resolve_import()` unconditionally returned `None` for any bare/non-relative specifier (`@nestjs/common`, `@nestjs/common/enums/route-paramtypes.enum`); reveal's TS/JS extractor never read `tsconfig.json` `compilerOptions.paths`/`baseUrl`, the only way to resolve cross-package imports in a workspace monorepo with no `node_modules` packages installed. Compounding: `is_intra_project_import()` classified these as `False` (definitely external) rather than unknown, so misses never incremented `_unresolved_intra` — the tool's own undercount-disclosure safety net never fired, and `depends://` reported `confidence: high` on results that were 1–30% complete for the worst-hit barrel files. Fixed in BACK-694: both functions now consult the nearest `tsconfig.json`'s `paths`/`baseUrl`. Re-running the diff with the fix alone left recall unchanged at 68.48% — masked by a second bug: project-root inference stopped at the nearest `package.json`, so sibling packages were never scanned. Forcing the correct workspace root isolated the fix's real effect: 81.21% (+368 edges) vs. 68.48% at the same root without it. Fixed in BACK-698: `resolve_project_root` now climbs past a plain `package.json` to an ancestor `lerna.json`/`pnpm-workspace.yaml`/`package.json` `"workspaces"` field, JS/TS-gated so other languages and single-package repos are unaffected. Re-running with no root override reproduces 81.21% automatically. Residual gap to 100% (tsconfig `extends` chains, `package.json` `exports` map resolution) is out of scope for both fixes and tracked as **BACK-705**. |
| Java | Elasticsearch (`server/src/main/java`, 4,837 files) | Buildless JLS package/filename convention | Stratified sample, 975 edges | 97.54% → 99.69% → **100%** | 0 | Nested-type and static-member imports (`import a.b.Outer.Inner`) never fell back from the (non-existent) `Inner.java` to the real enclosing `Outer.java` (BACK-551). The last 3/975 misses were all importers inside `org.elasticsearch.env`, a real source package silently excluded because `env` was in the global directory skip-set — closed by BACK-552 (context-sensitive `is_skippable_dir`), verified this loop: `ClusterState`/`Sets` now resolve their `env/NodeEnvironment`/`NodeRepurposeCommand` importers. |
| Java (overfit guard, BACK-669) | guava (single-library tree, 611 files) | Same oracle, unmodified, re-run on a second corpus | Full population (small corpus), 159 targets, 2,066 edges | **100%** (no fix needed) | 0 | None — full-population diff confirmed 100% recall immediately, including the exact BACK-551 nested-type/static-member idiom (`MoreObjects.ToStringHelper`, `Map.Entry`, 353 distinct `import static` statements) on a second, independent corpus; the BACK-551/BACK-552 fixes generalize. Wildcard imports (`import a.b.*;`) are not exercised — Guava's style guide forbids them — so that path remains covered only by the Elasticsearch measurement above. |
| Go | Kubernetes (`pkg/`, 2,266 files) | `go list -json` (real toolchain) + independent per-file import parse | 25-target stratified sample, 822 edges | **0%** effective (every single-file query returned zero, unconditionally) → **100%** | 8 (documented, safe — see below) | Go resolves an import to its package *directory*, but the file-level query path did an exact-key lookup against the file itself — a key that could never match a directory-keyed edge. Affected every Go dependents query, always. |
| Go (overfit guard, BACK-669) | `prometheus/client_golang` (single-module, no `go.work`, 162 files) | Same oracle mechanism (whole-repo variant — no BACK-524 scan-cap isolation needed, corpus is well under the cap) | Full population (small corpus), 114 targets, 2,837 edges | **100%** (no fix needed) | 133 (documented, safe — see below) | BACK-553's directory-key fallback generalizes cleanly off Kubernetes' package/directory-granularity shape. All 133 FPs traced to two safe over-inclusion mechanisms: (1) two `//go:build ignore` code-gen scripts (`package main`) that `go list` excludes but reveal's build-tag-blind parser doesn't, fanning their real import out to every file in the target directory — same class as this row's own 8 Windows-build-tag FPs; (2) external test-package files (`package foo_test`) whose import of parent package `foo` directory-fans-out to include themselves |
| Python | Home Assistant core (`homeassistant/`, 213 files) | `ast.parse` + independent filesystem/`sys.path` resolution | 82-target stratified sample, 790 edges | 36.74% → **100%** | 0 | Three variants of one confusion — "a package directory is not a `sys.path` root" — causing false project-root detection, self-shadowing of stdlib-named siblings, and truncation of multi-segment relative imports to their first component |
| Python (overfit guard, BACK-669) | celery (417 files, 185 targets) | Same oracle, unmodified, re-run on a second corpus | 20-per-bucket stratified sample, 886 edges | 99.77% → **100%** | 0 | Pure `from . import a, b, c` where some names are sibling submodules and others are symbols defined only in `__init__.py` (e.g. `celery/beat.py`'s `from . import __version__, platforms, signals`) silently dropped the `__init__.py` edge whenever any name also matched a submodule |
| Ruby (Zeitwerk convention) | Discourse (`app/`, 1,190 files) | Direct require-statement density + constant-reference measurement | Full-tree density scan; 5,000-file capped edge scan | Confident false negative on ~95%+ of real edges → **32,078 additional edges inferred** (vs. 8,645 from explicit `require`) | 0 (additive, exact-match only — never fabricates an edge) | Modern Rails apps express nearly all intra-app dependencies as bare constant references resolved by Zeitwerk's file-path convention, with *zero* `require` statements for reveal to see. Fixed in two stages: an honest "low coverage" caveat, then a path→constant inference pass that recovers the missing edges directly. |
| Ruby (overfit guard, BACK-669) | solidus (Rails Engine/multi-gem monorepo, 2,067 files) | Independent require + Zeitwerk path→constant oracle, built from scratch for this corpus | Full population, 576 targets, 3,199 edges | 88.06% → **100.00%** (BACK-700 + BACK-701 both fixed) | 0 | Two shapes Discourse's single-app corpus never exercised: (1) BACK-700 — a bare `require 'a/b'` only ever tried the single project root, never each gem's own `lib/` (Bundler `$LOAD_PATH`, one per `*.gemspec` in a multi-gem monorepo) — 395/395 real bare-require statements in the corpus needed this; (2) BACK-701 — a leading `::` (`::Spree::Order`, Ruby's absolute-lookup disambiguator, common in namespaced Rails Engine code) was kept in the captured constant text, breaking the Zeitwerk index's exact-string match. 13 apparent residual misses after both fixes traced to oracle noise (heredoc/regex-literal text mistaken for code), not `depends://` — closed by fixing the oracle, confirming a genuine 100%. |
| Kotlin | tivi (Android/KMP app, 629 files) | Content-scanned package + top-level-declaration oracle | Exhaustive, 233 edges | 12.0% → **99.14%** | 0 (1 residual is a grammar-library parse-recovery artifact, not a resolver bug) | Top-level function/property imports have no class/type component to resolve toward — needed a new content-scanned member index, since the existing peel logic could only ever reach type names |
| Kotlin (overfit guard, BACK-669) | kotlinx.coroutines (JetBrains library, 1,039 `.kt` files) | Same oracle mechanism, parameterized for a second package prefix | Full population (small corpus), 34 targets, 50 edges | **100%** (no fix needed) | 11 (documented, safe — see below) | None — full-population diff confirmed 100% recall immediately; the BACK-555 content-scanned member index generalizes off tivi's app shape to a pure-library corpus. All 11 FPs traced to safe wildcard-import fan-out: `import kotlinx.coroutines.flow.internal.*` correctly resolves to every file declaring that package (directory-granularity semantics), a broader edge set than the oracle's single-symbol targets — same class as Go's BACK-685 wildcard FPs |
| Scala | GitBucket (247 files) | Content-scanned package + object-member oracle | Exhaustive, 1 qualifying edge | 0% → **100%** | 0 | `lowerCamelCase` top-level singleton objects defeated the existing Uppercase-gated resolver peel the same way a package segment would |
| Scala (overfit guard, BACK-669) | cats-effect (functional-effects library, 457 files) | Same oracle mechanism, parameterized for a second corpus | Full population (small corpus), 1 target, 24 edges | **100%** (no fix needed) | 0 | None — full-population diff confirmed 100% recall (24/24) after two oracle-tool fixes (not resolver bugs): stripped a Scaladoc string-literal's example `import` text that was miscounted as real, and widened the import scan to also match Scala's legitimate indented (method-scoped) imports, which the column-0-only regex had been undercounting as false positives. The BACK-559 container-member index generalizes off GitBucket's single occurrence to cats-effect's much more heavily used `cats.effect.unsafe.implicits.global` idiom (24 real edges vs. GitBucket's 1) |
| Rust | Meilisearch (17-crate workspace, 726 files) | Independent regex-based `use`/`Cargo.toml` parser | 30-target stratified sample, 295 edges | 59.0% → **100%** | 0 | (1) Multi-segment `crate::`/`super::` paths only ever consumed their first segment, with `super::` unconditionally failing; (2) grouped `use crate::{a,b,c}` imports matched on a keyword-typed AST node the extractor didn't recognize, silently dropping the entire statement |
| Rust (overfit guard, BACK-669) | ripgrep (single-workspace crate, 100 files) | Same oracle, unmodified, re-run on a second corpus | Full population (small corpus), 46 targets, 100 edges | 56.0% → **100%** | 0 | A `use_list` item that is itself a nested `scoped_use_list` (`use crate::{a::{x, y}, ...}`, ripgrep's dominant `lib.rs` re-export idiom) silently dropped the whole nested item — same failure shape as the grouped-import bug above, one level deeper |
| C# | Jellyfin, Godot C# glue | Real-corpus grep (idiom itself was fixture-only — absent from both corpora) | Fixture + incidental real-corpus hit | N/A for the target idiom | — | Investigating the (absent) target idiom surfaced that namespace fan-out was never wired into the dependency graph at all for zero-import files |
| C# (BACK-669, missing baseline) | Jellyfin (`samples/csharp`, 2,098 files, large multi-project ASP.NET media-server monorepo) | Independent namespace/type oracle (`build_oracle.py`) — C# `using`/`using static`/alias resolved via a from-scratch regex namespace-declaration index and (namespace, type) index, never calling `depends://`'s own resolver | Full population, 1,754 targets, 99,654 edges | 99.9970% → **100.00%** (BACK-702 fixed) | 0 | `using Alias = Foo.Bar.Type;` (87/96 real alias statements) and `using static Foo.Bar.Type;` name a specific TYPE one dotted component past any namespace the tree declares — the namespace fan-out index never matches, and the directory-suffix match only succeeds when the physical layout mirrors the namespace and the type's basename is tree-wide unique; Jellyfin's per-project top-level dirs (`MediaBrowser.Controller`, a literal `.` in one path component) and a same-named `LinkedChildType` type in two different namespaces broke both. Fixed via a new `namespaced_type_fallback` spec flag reusing the existing Kotlin/Scala `member_index`/`resolve_member_targets` machinery, keyed `(namespace, type_name)` |
| C# (overfit guard, BACK-669) | Newtonsoft.Json (single-project library, 945 files, heavy `#if`/`#else` multi-target-framework conditional compilation — 528/945 files, vs. 0/2,098 in Jellyfin) | Same oracle mechanism, unmodified resolution logic | Full population, 793 targets, 48,400 edges | **99.3636%** (0 new resolver bugs — same BACK-702 fix from the baseline slice, re-confirmed) | 0 | The one residual (308/308 misses, all on one target) is a genuine tree-sitter-c-sharp grammar limitation, not a resolver gap — `TestFixtureBase.cs` shares one method BODY between a `#if DNXCORE50` constructor header and an `#else` regular-method header, which the preprocessor-blind grammar can't parse into any declaration node, producing an `ERROR` node that swallows the file's whole namespace body; correctly honest-decline caveated (`confidence: reduced`), not a silent wrong zero. Filed **BACK-703**, not fixed (4/945 files affected, narrow and documented, same class as Go's build-tag blindness, BACK-685). Also found and fixed an oracle-only bug (not `depends://`): the oracle's original #if-branch-selection heuristic (keep only the `#if` branch) silently dropped 37 real edges sitting in a legacy-condition-first `#if NET20 ... #else ...` block's `#else` (the real modern-default branch) — fixed by counting every branch unconditionally, matching reveal's own preprocessor-blind parse behavior |
| PHP | WordPress core (`samples/php`, 1,927 files) | Buildless `require`/`require_once`/`include`/`include_once` string-expression resolver (not `use`/namespace — see [harness README](../internal-docs/planning/dogfood-findings/php-recall-oracle/README.md) for why) | 80-target stratified sample, 442 edges | 0.00% → 33.85% (BACK-564) → **100.00%** (BACK-565) | 0 | `depends://`'s PHP resolver only recognized a bare string-literal require/include target; every real WordPress require/include uses string concatenation (`__DIR__ . 'x.php'`, `ABSPATH . WPINC . 'x.php'`, etc. — confirmed 0 bare-literal requires exist anywhere in the corpus). BACK-564 resolved the universal `__DIR__`/`dirname(__FILE__)` directory-relative idiom via a structural AST-walk extractor. BACK-565 (same session) closed the remaining majority: WordPress-specific framework-bootstrap constants (`ABSPATH`/`WPINC`/`WP_CONTENT_DIR`/`WP_PLUGIN_DIR`) are genuinely derivable — WordPress defines them in-tree via `define('ABSPATH', __DIR__ . '/')` and similar — so a project-wide constant index (built to a fixed point, since real constants chain through each other) now substitutes them into the same concatenation resolver. Constants with genuinely ambiguous `define()` values (measured: 3/50) are excluded from the index, never guessed |
| PHP (overfit guard, BACK-669) | osCommerce (`catalog/`, 436 files) | Same require/include oracle mechanism, adapted for one corpus-specific bootstrap constant (`OSCOM_BASE_DIR`) | Full population (small corpus), 74 targets, 288 edges | 0.00% → **74.65%** (BACK-680 fixed; BACK-681 residual filed, not fixed) | 0 | The dominant real-world statement shape here — parenthesized call-style (`require('includes/foo.php');`, 534/544 statements, vs. only 10/1,521 on WordPress) — broke both the concatenation AST-walk (only checked direct children, missing a target nested inside `parenthesized_expression`) and the bare-literal `_build()` fallback (space-splitting tokenizer never matches the fused `require('...')` token). Fixed by handling the parenthesized wrapper and bare string-literal targets structurally. Residual 73/288 edges trace to explicit `chdir()`/CWD-dependent bare-literal resolution in 6 legacy extension scripts — real PHP runtime behavior a generic per-file resolver correctly declines to chase (would need actual chdir-call symbolic tracking, and a naive ancestor-directory-walk risks false positives in other codebases) — filed as BACK-681 |
| Swift | Kickstarter iOS (`samples/swift`, 1,961 files, 8 SwiftPM packages) | `swift package dump-package` (real toolchain, target list) + independent per-file import parse | Full-tree; 21 declared targets, 164-edge precision sample | ~0% effective (123 edges / 7 dependent files) → **100% of declared targets resolved** (384,278 edges / 1,511 dependent files) | 0 (164-edge sample, none unbacked) | Swift's import granularity is the *module (SwiftPM target)*, not the file, but the resolver only matched `import Foo` → a unique `Foo.swift` — resolving ~0% of real multi-file targets, AND (worse) leaving `unresolved_intra` at 0 so no honest-decline `⚠` fired: a silent wrong "no dependents". Fixed in two buildless parts: (1) `Sources/<Target>/` directory-convention fan-out (`import Foo` → every file in target Foo, C#-namespace-style); (2) a structural `Package.swift` parse for targets that relocate sources via an explicit `path:` (real GraphAPI `path: "./Sources"`, 326 importers). The independent `dump-package` oracle caught the custom-`path:` case the directory convention alone would have silently mis-mapped |
| Swift (overfit guard, BACK-669) | swift-collections (pure SwiftPM library, 696 files, 25 targets) | `swift package dump-package` (target→path ground truth) + independent regex import scan (`build_oracle.py`), from scratch | Full population, not sampled — 14,824 edges | 88.57% → **98.42%** (BACK-704 fixed; residual 234/234 = one target, honestly declined) | 0 | Two real gaps this pure-library, no-app corpus exercised that Kickstarter's app never did: (1) `_RopeModule`'s target is declared through a *programmatically built* `targets:` array (`.map { $0.toTarget() }`), whose custom `directory:` relocation argument names a dir that doesn't match the target's own sanitized identifier — unresolvable without evaluating arbitrary manifest code, but pre-fix also *silent* (no honest-decline warning); fixed the silence, not the resolution, via a new `extract_manifest_target_names` broader name-only scan feeding `is_intra_project_import`'s inventory; (2, the bigger effect) `@testable import Foo` / stacked `@_spi(Testing) @testable import Foo` — a common test-file idiom — wasn't recognized at all: the keyword-stripping tokenizer only pops a fixed keyword set, and an attribute's argument varies so it can't be one; the un-stripped attribute text became the whole garbage `module_name`. Fixed via a new `strip_attribute_prefix` spec flag. Re-run against Kickstarter: still 100%/0 unresolved, and total resolved edges rose 384,278 → 660,716 (recovers real `@testable import` edges silently lost there too) |
| Lua | Kong (`samples/lua`, 1,309 `.lua` files) | Project's own `kong-latest.rockspec` `build.modules` table (authoritative dotted-module → file map) + independent regex `require(...)` scan | 30-target stratified sample (fan-in buckets 1 / 2-5 / 6-20 / 21-50 / 50+), 782 edges | 85.4% → 99.5% → **99.87%** | 0 | `require("a.b.c")` may name a *directory* module (`a/b/c/init.lua`, Lua's `package.path` `?/init.lua` convention) with no flat `a/b/c.lua` file at all — `_match_dotted` only ever tried appending an extension to the last dotted component, so every directory-module require silently resolved to `None`. Hit 5 real Kong targets (`kong.conf_loader`, `kong.db.declarative`, `kong.vaults.env`, `kong.dynamic_hook`, `kong.plugins.rate-limiting.policies`), each returning a confident "no dependents" despite 2-35 real importers. Fixed via a new opt-in `directory_index_filenames` spec field. Two residuals found on the same sample, both fixed in a same-program follow-up (BACK-670, which incidentally also closed BACK-671): `_longest_unique_suffix`'s bare-basename (`k=1`) fallback — shared by every `module_separator` language (Java/Kotlin/Scala/C#/PHP/Swift/Lua) — wrongly matched multi-part imports whose real qualifying prefix had already failed to match (29 false positives, e.g. external `resty.*` modules landing on same-basename in-tree `kong.tools.*` files); gated to true single-token imports only, re-measured at 99.87% with 0 new false positives, and Java/PHP/Scala re-confirmed at 100%/Kotlin at its unaffected 99.14% baseline — see [harness README](../internal-docs/planning/dogfood-findings/lua-recall-oracle/README.md) |
| Lua (overfit guard, BACK-711) | AwesomeWM (window manager, 882 files, no rockspec/build manifest at all — forces pure directory-convention resolution vs. Kong's rockspec-backed lookup) | Same independent-regex oracle mechanism, re-run on a second corpus | Full population, 170 targets, 2,552 edges | 0% → **99.33%** | 2 (documented, out-of-scope test shims) | A bare single-token `require("wibox")` (393 call sites) silently resolved onto an unrelated same-basename flat file (`lib/awful/wibox.lua`) instead of the real directory module (`lib/wibox/init.lua`, which showed 0 dependents) — the k=1 global-basename-uniqueness fallback had no structural relationship to the import site. Fixed by trying the directory-index candidate first for single-token imports, falling back to a flat file only when it is a *true sibling* of that directory. Residual 17 misses are genuine structural ambiguity (AwesomeWM's `tests/examples/{text,shims}/` trees literally mirror `lib/`'s module paths) that a suffix-based resolver correctly declines rather than guesses on |
| Dart | AppFlowy (`samples/dart/frontend/appflowy_flutter`, 1,974 `.dart` files, 14 in-tree packages) | Every in-tree `pubspec.yaml`'s declared `name:` → its own `lib/` (authoritative name→dir map) + independent regex `import '...'` scan | 30-target stratified sample (fan-in buckets 1 / 2-5 / 6-20 / 21-50 / 50+), 825 edges | 19.3% → **99.76%** (100% real — see below) | 0 | `package:<name>/x.dart` — the dominant real-world Dart import shape (5,989 of 6,290 in-tree imports in the sample corpus, vs. 301 relative imports) — had no resolution branch at all: it contains `/` and matched `_looks_like_path` before any separator logic ran, so it was always tried (and failed) as a literal file-relative path. Every `package:` self- and cross-package import in the corpus silently resolved to `None`. Fixed with a new opt-in `package_uri_scheme`/`package_manifest_filename`/`package_manifest_lib_dirname` spec triple: builds a project-wide package-name→`lib/` index from every in-tree `pubspec.yaml` (cached per scan on the shared `file_index`), the same authoritative-manifest role Lua's rockspec and Swift's `Package.swift` played. The 2 residual sampled misses were both oracle false positives — a code-generation script's `writeln('''...''')` embeds literal `import '...'` text inside a Dart template string, which tree-sitter correctly never parses as a real import (same class as Lua's `nginx_kong.lua` false positive) — so true recall on the sample is 100% (823/823 real edges) |
| Dart (overfit guard, BACK-712) | drift (SQL code-generation package, 1,171 files, 32 in-tree pubspec packages under one melos workspace, vs. AppFlowy's 14 under a single Flutter app) | Same pubspec-manifest oracle mechanism, re-run on a second corpus | 30-target stratified sample, 1,039 edges | 91.24% → **96.63%** (100% of real edges) | 0 | A `show`/`hide`/`deferred as` combinator clause trailing the quoted URI (`import 'package:drift/drift.dart' show OpeningDetails;`) was never stripped before quote extraction, so `module_name` became literal garbage that still dispatched into `_resolve_package_uri` and silently returned `None` — 88 of 91 misses landed on drift's own barrel file. Fixed with a new opt-in `combinator_clause` spec flag truncating the remainder at its closing quote. The residual 35 misses are all oracle false positives (`TestBackend.inTest({...})` fixtures embedding literal `import` text inside Dart string literals), so true recall on the sample is 100% |
| GDScript | godot-demo-projects (`samples/gdscript`, 456 `.gd` files, 138 independent Godot projects) | Independent regex scan for `preload`/`load("res://...")`, `extends "res://..."`, and `extends Foo` matched against a project-scoped `class_name Foo` index, each `res://` path resolved against its file's own nearest `project.godot` (never the whole tree) | Full census (small population: 19 distinct targets), 41 edges | 24.4% → **100%** | 0 | Two bugs: (1) `depends://`/`imports://`'s `extra_paths` construction skipped the scan root as a search path whenever it already equaled the importing file's own directory (`scan_root != base_path`) — harmless for file-relative resolvers (which try `base_path` first) but fatal for GDScript's project-root-relative `res://`, which never falls back to `base_path`; every root-level file's (`main.gd`/`game.gd`/`test.gd`-shaped) `res://` import silently failed. Fixed by always including the scan root regardless of that equality. (2) `extends Foo` naming a `class_name Foo` declared elsewhere in-tree — Godot's global class-registration convention, and the dominant edge shape measured (27 of 41) — had no resolution path: a bareword `extends` only ever matched a literal same-named file, and Godot filenames are conventionally snake_case, not the PascalCase class name. Fixed with a new opt-in `class_name_convention` flag: a project-wide `class_name` → declaring-file index (regex-scanned, cached per scan on `file_index`), tried as a fallback when the direct bare-basename match fails |
| GDScript (overfit guard, BACK-713) | Pixelorama (pixel-art editor, 247 `.gd` files under a single `project.godot`, vs. godot-demo-projects' 138 independent Godot projects side by side) | Same independent-regex oracle mechanism, re-run on a second corpus | Full census (small population), 17 targets, 63 edges | **100%** (no fix needed) | 0 | None — 58 of 63 edges (92%) resolve via the `class_name`-based `extends` convention, an even more dominant shape than in the v1 corpus, confirming the `class_name_convention` fix generalizes outside the many-independent-projects topology it was built against |
| Zig | ghostty (`samples/zig/ghostty`, 715 `.zig` files) | Independent regex scan for `@import("...")` (comment-stripped, string-aware), scoped to `.zig`-suffixed relative-file targets only — named-module imports (`std`, `builtin`, build-graph aliases) are out of scope, matching `resolve_import`'s own design | 26-target stratified sample (fan-in buckets 1 / 2-5 / 6-20 / 21-50 / 50+), 426 edges | **100%** (no baseline gap) | 0 | No bug found — the relative-file resolver (plain `(importer.parent / target).resolve()` semantics, no manifest scheme or global-registration convention involved) was already correct across every fan-in bucket sampled, including up to 3 levels of `../` traversal (`src/quirks.zig`, 113 importers) |
| Zig (overfit guard, BACK-714) | TigerBeetle (distributed database, mostly-flat `src/`, 245 files) | Same oracle, unmodified, re-run on a second corpus | Full population (small corpus), 215 targets, 836 edges | **100.0000%** (no fix needed) | 0 | None — full-population diff confirmed 100% recall immediately, same clean outcome as the ghostty baseline. 466 named-module aliases (`@import("vsr")`, `@import("stdx")`, ...) correctly excluded, same scope decision as ghostty's |
| TSX, plain JS | three.js (`samples/javascript`, 1,622 `.js` files) + Excalidraw (`samples/tsx/excalidraw`, 635 `.ts`/`.tsx` files) | Independent regex scan for static/dynamic `import`, `export ... from`, and `require(...)` (comment-stripped, string-aware), true filesystem-based extension/index resolution (not a port of `resolve_import`'s own heuristic — see Finding) | 2 stratified samples, one per corpus (fan-in buckets 1 / 2-5 / 6-20 / 21-50 / 50+): `.js` 30 targets/777 edges, `.tsx` 29 targets/745 edges | `.js` 100% (no gap); `.tsx` 98.79% → **100%** | 0 | `.js`/`.jsx`/`.ts`/`.tsx`/`.mjs` share one resolver function (`_resolve_relative_js`) — a dotted basename with the extension omitted (`./charts.constants` → `charts.constants.ts`, `./WelcomeScreen.Center` → `.tsx`, `./subset-shared.chunk` → `.ts`) was misjudged by the `has_extension` gate (only checks whether the last path segment contains *any* dot) as already having a real extension, so it tried only the literal path plus the narrow `.js/.jsx/.mjs` TS-ESM fallback map, then returned `None` instead of falling through to the plain extension-append/directory-index resolution used for genuinely extensionless specifiers (BACK-672) |
| TSX, plain JS (overfit guard, BACK-715) | react-router v5.3.4 (5-package lerna-style monorepo, 180 `.js` files, pure JSX-in-`.js` with no `.jsx` extension at all, vs. three.js's single-package plain `.js` and Excalidraw's `.ts`/`.tsx`) | Same relative-import oracle mechanism, re-run on a third corpus | Full census (small population), 112 targets, 222 edges | **100%** (no fix needed) | 0 | None — confirms the shared `_resolve_relative_js` resolver (already fixed twice: the VS Code loop, then this slice's own BACK-672) holds on a monorepo topology and a pure-`.js`-JSX extension mix neither prior corpus exercised. Cross-package bare specifiers (`react-router-dom` importing `"react-router"`) are correctly out of scope for a relative-import oracle |
| C | Redis (`samples/c`, `src/`+`modules/`+`tests/modules/`+`utils/`, 275 files) | Real preprocessor, per-directive: `gcc -H -fsyntax-only -iquote <including-file's-dir>` resolves each quoted `#include "..."` in isolation (real header search, not a re-derivation of reveal's own) | 30-target stratified sample (fan-in buckets high/mid/low), 310 edges | **100%** (no baseline gap) | 0 real (2 apparent — see below) | No bug found — `_resolve_include`'s sibling-then-search-path resolution was already correct across every fan-in bucket sampled. Graduated from BACK-611's earlier grep spot-check to this full oracle loop; the loop's *own* first draft (whole-file `gcc -H`, reading the transitive tree) had a self-inflicted undercount bug from gcc's include-guard optimization skipping already-satisfied headers — caught before it could report a false gap, see [harness README](../internal-docs/planning/dogfood-findings/c-recall-oracle/README.md). The 2 apparent false positives are `deps/`-tree (vendored third-party) files `depends://` correctly resolves but this oracle deliberately doesn't scan as importers |
| C (overfit guard, BACK-710) | curl (client-side networking library, 468 files — flatter `lib/`+`src/` layout with `lib/vauth`/`lib/vquic`/`lib/vtls` subdirs and heavy cross-directory and parent-relative includes, vs. Redis's mostly-flat `src/`) | Same per-directive isolated `gcc -H` oracle, unmodified | Full population, 232 targets, 2,330 edges | **100.0000%** (no fix needed) | 173 (documented, oracle-scope) | None — all 173 apparent FPs confirmed by direct grep to be genuine `#include` lines in `tests/unit/`, `tests/libtest/`, `tests/server/` and `projects/OS400/` files, outside the oracle's deliberately production-only importer scope but correctly found by `depends://` |
| C++ | Godot (`samples/cpp`, `core/`+`scene/`+`servers/`+`drivers/`+`platform/`, 2,830 files) | Same method as C, per-directive `g++ -H -fsyntax-only -std=c++17` isolation | 30-target stratified sample (fan-in buckets high/mid/low), core/-rooted, 450 edges | 33.11% → 99.56% → **100.00%** | 3 (BACK-664, BACK-675, BACK-676) | `CppImportExtractor.extensions` omits `.h` (owned by `CImportExtractor` alone); `depends://`'s single-file scan-scoping (BACK-525 layer 4) narrowed a `.h` target's parse corpus to `{.c, .h}`, dropping every `.cpp` importer of its own header (BACK-675). Fixed by widening to the C/C++ family union when the target is either language. The first raw measurement (33.11%) was mostly a corpus-size confound, not this bug — `root=samples/cpp` (~14,000 files) tripped `depends://`'s BACK-524 5,000-file scan cap; re-measuring against a bounded, rsync'd sub-corpus (same precedent java/python-recall-oracle already set) isolated the real gap. Residual: 2/450 edges (`core/math/bvh_tree.h`'s own `.inc` fragment includes, sitting inside a template class body) traced to a separate bug — a `#include` inside a class body isn't valid top-level-context grammar, so tree-sitter degrades it to a generic `preproc_call` fallback node the extractor never scanned (BACK-676); fixed by scanning that node type too, filtered to the `#include` directive only. Same loop also found `CppImportExtractor.extensions` never claimed `.hh` (already C++ structurally) or `.mm` (Obj-C++, parses with the `objc` tree-sitter grammar but emits identical `preproc_include`/`preproc_call` nodes, verified empirically) — silently zero import resolution for either extension (BACK-664; Godot corpus: 258 `.hh` + 59 `.mm` files affected). Re-measured after both fixes: 100.00% recall, 0 missing edges on the same 450-edge sample; 24 new true-positive `.mm` importer edges surfaced (spot-checked genuine) register as this oracle's own false positives only because `build_oracle.py`'s ground-truth builder never scanned `.mm` as an importer candidate — a pre-existing oracle scope gap, not a defect. See [harness README](../internal-docs/planning/dogfood-findings/cpp-recall-oracle/README.md) |
| C++ (overfit guard, BACK-709) | assimp (Open Asset Import Library — plugin/format-importer architecture, `code/AssetLib/<Format>/`, with relative parent-directory quoted includes, vs. Godot's flat engine-core monolith and root-relative `-iquote` convention) | Same per-directive isolated `g++ -H` oracle, unmodified | Full census, 250 targets, 707 edges | **100%** (no fix needed) | 50 (documented, oracle-scope) | None — still `.h`-dominant (728 `.h` vs 23 `.hpp`), re-exercising the BACK-675 extractor-family-scoping fix under a different directory shape. All 50 FPs spot-checked genuine: real `#include` edges from `test/`/`tools/`/`contrib/` files the oracle's importer scope deliberately excluded from ground truth |

**What this program found.** Each language got a baseline oracle loop, and
every language has since had a second, deliberately differently-shaped corpus
run through the same loop as an overfit guard (BACK-669 for the original
eleven; BACK-708 and children for C, C++, Lua, Dart, GDScript, Zig, and
TSX/plain-JS). The per-row results are the authority — this paragraph only
summarises their shape, and the tables above are what should be quoted.

- **Every baseline loop found at least one real recall bug except Zig's and
  C's**, both of which measured a clean 100% on first contact. Those two clean
  results matter as much as the failures: they are evidence the loop shape
  catches genuine gaps rather than manufacturing findings by construction.
- **Several second-corpus guards found new bugs the first corpus never
  exercised** — Rust/ripgrep (nested `scoped_use_list`), Python/celery
  (`from . import` dropping the `__init__.py` edge), Ruby/solidus (per-gem
  `$LOAD_PATH`; leading `::`), PHP/osCommerce (parenthesized call-style
  `require`), Swift/swift-collections (`@testable import` unrecognized),
  TS/nest (no `tsconfig` `paths`/`baseUrl` resolution), Lua/AwesomeWM
  (single-token `require` resolving to an unrelated same-basename file), and
  Dart/drift (`show`/`hide` combinator clause corrupting the URI). The rest
  held clean, confirming the original fixes generalize.
- **The C++ loop was the first to find a bug in the *adapter* layer**
  (`depends://`'s own scan-scoping, BACK-675) rather than in a
  language-specific resolver — a class of defect that, once found, was
  relevant to every language sharing that path.
- **Bugs in the oracles themselves were found and fixed too** (C's first-draft
  `gcc -H` undercount, Scala's Scaladoc-literal miscount, C#'s `#if`-branch
  selection, Ruby's heredoc noise). Each is called out in its row, because a
  measurement program that never finds bugs in its own instruments is not
  being run honestly.
- **Every *fixed* bug shipped with regression tests** (fail-before/pass-after
  confirmed by disabling the fix in place, not by reverting source) and a
  full-suite run showing zero regressions elsewhere.
- **Four documented residual gaps remain open**, each with a task ID and a
  stated reason it was not closed: TypeScript/nest (BACK-705), PHP/osCommerce
  (BACK-681), Swift `_RopeModule` (BACK-704 residual), and
  C#/Newtonsoft.Json (BACK-703). See
  [Open residual gaps](#open-residual-gaps).

### What the false positives mean

Recall is this program's metric, but several loops did report false positives.
Every one traced to one of three benign mechanisms, each documented in its own
row — none is a case of reveal inventing an edge that is not in the source:

1. **Conditional-compilation blindness (safe over-inclusion).** reveal's
   extraction is deliberately preprocessor- and build-tag-blind, so it reports
   edges the real toolchain would exclude for a given target platform or symbol
   set: Go/Kubernetes 8 of 822 (`//go:build windows`, oracle built `GOOS=linux`),
   Go/client_golang 133 (`//go:build ignore` code-gen scripts plus external
   `package foo_test` files). These are real precision gaps — the edge *is
   present in the source*, but would not compile into that binary. Documented,
   not filed as defects, since erring toward showing more of the source graph is
   the safer failure direction for a dependency reader.
2. **Oracle importer-scope narrower than `depends://`'s search root.** Several
   oracles deliberately scan only production code for ground truth while
   `depends://` legitimately searches the whole checkout, so genuine edges from
   test/vendor trees register as "false" positives of the oracle, not of reveal:
   C/curl 173 (`tests/`, `projects/OS400/`), C++/assimp 50 (`test/`, `tools/`,
   `contrib/`), C++/Godot's `.mm` importers, C/Redis 2 (`deps/`). All
   spot-checked against the real source and confirmed genuine.
3. **Directory-granularity fan-out broader than the oracle's symbol-level
   targets.** Kotlin/kotlinx.coroutines 11, from `import ...flow.internal.*`
   correctly resolving to every file declaring that package.

The one materially different case is **TypeScript/nest**, whose 701 pre-fix /
1,071 post-fix figures reflect an *undercount* condition rather than safe
over-inclusion — see that row and BACK-694/BACK-698.

### Open residual gaps

Four measured languages sit below 100% with a gap that is real, still open, and
tracked. They are listed here rather than left to be discovered inside a table
cell, because "what is still wrong" is the question a DD reader is entitled to
ask first:

| Language / corpus | Recall | Missing | Task | Why it is still open |
|---|---|---|---|---|
| TypeScript / nest | **81.21%** | 543 edges | **BACK-773** | `tsconfig extends`/`exports` map (BACK-705/772) both fixed and re-measured (exploding-parsec-0723) — recall held exactly at 81.21%, root-caused to a *different* gap: path aliases declared in a sibling `tsconfig.build.json` linked via TS project `"references"` (not `"extends"`) are invisible to `_find_tsconfig`. Separately, the oracle itself undercounts test-file edges (**BACK-774**), masking part of BACK-772's real effect. The lowest number in this document, on a flagship language. |
| PHP / osCommerce | **74.65%** | 73 edges | **BACK-681** | `chdir()`/CWD-dependent bare-literal `require`s in legacy scripts. Deliberately not chased: a generic resolver would need symbolic `chdir` tracking, and an ancestor-directory-walk heuristic risks false edges elsewhere. |
| Swift / swift-collections | **98.42%** | 234 edges (one target) | **BACK-704** (residual) | `_RopeModule` is declared via a programmatically-built `targets:` array; resolving it would require evaluating arbitrary `Package.swift` code, which the buildless design will not do. Now an honest reduced-confidence decline rather than a silent miss. |
| C# / Newtonsoft.Json | **99.36%** | 308 edges (one file) | **BACK-703** | tree-sitter-c-sharp cannot parse a `#if`/`#else` pair whose branches declare *different* headers over one shared body; the file's namespace body collapses into an `ERROR` node. Honest-decline caveated. 4 of 945 files affected. |

Two properties these share are the point: every one is **disclosed at query
time** (`confidence: reduced` / `undercount_possible`) rather than reported as a
confident zero, and every one has a task ID rather than living only in prose.

### Import-recall gaps — not yet measured with a full oracle loop

The following are **not** in the import-recall table above because they have
not been run through an independent-oracle diff against a real corpus. (Swift
graduated out of this list — measured with a full `swift package
dump-package` oracle loop, BACK-567; Lua graduated out via a
rockspec-manifest oracle loop, BACK-621; Dart graduated out via a
pubspec-manifest oracle loop, BACK-621; GDScript graduated out via a
`class_name`/`res://` oracle loop on godot-demo-projects, BACK-621; Zig
graduated out via a relative-`@import` oracle loop on ghostty, BACK-621 —
100% recall, no bug found; C++ graduated out via a per-directive `g++ -H`
oracle loop on Godot, BACK-674 — 33.11% → 100.00% after fixing BACK-664,
BACK-675, and BACK-676; **C graduated out** via a per-directive isolated
`gcc -H` oracle loop on Redis, BACK-611 — 100% recall, no bug found, plus a
curl second-corpus guard at 100%, BACK-710; see the Results table.):

- **Scala's selector-list imports** (`import a.b.helpers.{x, y}`) — a known,
  explicitly out-of-scope gap in the current measurement, flagged for a
  future loop.
- **Ruby's classic `autoload` calls** (distinct from the Zeitwerk convention
  measured above) — checked directly against Discourse's real source (10,458
  files) and found to occur zero times; declined as a candidate because the
  idiom is architecturally superseded, not because it was untestable.

A gap in this list is a claim we have not yet measured, not a claim the
capability is broken — see `README.md` and the language coverage notes for
what each language does support today.

## Side-Effect / Boundary Classification Recall

`--sideeffects`/`--boundary` answer a different DD question — "what does this
function actually *do* to the outside world: touch a database, make a network
call, read the filesystem or environment, log, sleep?" — and carry the same
silent-false-negative risk: a function that quietly writes to a database but
reads as pure is exactly the blast-radius surprise a DD reviewer must not miss.

Unlike import recall, **no external tool can serve as an oracle** — there is no
`go list` for "is this a side effect." So each loop's `build_oracle.py` writes
its own regex patterns over raw source, using a **different pattern set and a
different parsing strategy** (independent brace-depth scanner, not reveal's
tree-sitter parser) than the code under test — so a disagreement is a genuine
signal, not a tautology. Same shape otherwise: stratified positive sample plus
a negative control to catch false positives, every miss root-caused, fixed, and
re-measured.

| Language | Real corpus | Recall: before → after | Notable bug found & fixed |
|---|---|---|---|
| Go | Kubernetes `client-go` (2,161 files) | 57.4% → **96.3%** | Go had no `http` bucket at all — snake_case `http_get` literals never matched dotted `http.Get(`; `RoundTrip`-shaped transport calls all missed |
| Python | Home Assistant (12,150 files) | 80.4% → **83.5%** | `file` bucket missed `os.remove`/`os.makedirs` and `pathlib` `write_text`/`read_bytes` (76.9% → 100% for `file`) |
| Java | Elasticsearch | 81.0% → **97.5%** | `constructor_declaration` missing from the shared taxonomy leaked a constructor's effects into its enclosing class's whole body (BACK-638) |
| C# | Jellyfin | 91.5% → **98.3%** | `SaveChangesAsync`/`StreamReader` taxonomy gaps |
| Ruby | Discourse | 63.4% → **98.8%** | `singleton_method` (`def self.foo`) entirely absent from `FUNCTION_NODE_TYPES` — invisible to `--outline` and name lookup outright (BACK-647, the program's single largest recall jump) |
| PHP | WordPress | 78.7% → **97.5%** | Most of the gap was oracle-side; confirmed reveal's PHP classification was already sound once the oracle's own bugs were fixed |
| Rust | Meilisearch | 31.6% → **97.4%** | Taxonomy and receiver-scoping gaps across all categories |
| C++ | Godot | 24.4% → **83.3%** | Macro-hidden effects and per-category taxonomy gaps |
| TypeScript | VS Code (65,008 functions) | 75.6% → **76.8%** (91.3% ex-`env`) | `process.env.X` env reads are a property access, not a call — invisible to the call-only classifier; closed by a dedicated property-access channel (BACK-644) |
| Kotlin | tivi (full tree, six-category sweep, BACK-727) | 82.5% → **92.9%** | http-client-construction (`HttpClientFactory.create`/`OkHttpClient.Builder`), `BuildConfig.X` env property reads (BACK-644-shaped), coroutine `delay()` sleep idiom, and two oracle-side bugs (unmasked `//` comments, excluded expression bodies); remaining misses are declined bare `File(`/`client.get` (catastrophic cross-language collision) |
| Swift | Kickstarter iOS (full tree, six-category sweep, BACK-728) | 43.3% → **100.0%** | Security-framework Keychain wrapper + `UserDefaults` local storage (db), `FileManager.default.moveItem` (file), `Bundle.main.infoDictionary` env read, Firebase Crashlytics factory call (log, avoiding a collision-prone bare `record` verb), GCD `DispatchQueue.asyncAfter` (sleep), `URLSession.downloadTask` (http) — see [SWIFT.md](internal-docs/planning/dogfood-findings/sideeffects-recall-oracle/swift/SWIFT.md) |

Cross-language false-positive sweeps in the same program fixed bare-verb
subsequence over-fire (`dict.update()` misread as a db write) and unscoped
receiver-name collisions (`conn`/`session`/`cache`/`requests`), so the recall
gains did not come at the cost of precision.

## Cross-File Call-Graph Recall

`calls://` answers a third DD question, structurally distinct from the other
two — not "what does this import" or "what does this function do," but "who
calls this function, and what does it call" — a whole-project graph query
with the same silent-wrong-answer risk as `depends://`'s BACK-542 failure: a
false negative (no callers found) reads as a confident, checked "nothing
calls this," not a missing measurement (BACK-730).

### Method

Same shape as the other two signals: an execution-free, independent oracle
(Python's `ast`, TypeScript's own scope/AST rules read from `treesitter.py`,
Go's `go/parser`+`go/ast`, Rust's `syn`) diffed against `calls://`'s live
output on a real, unmodified open-source corpus, stratified by fan-in/fan-out
so a resolver bug can't hide in the easy cases. Three query directions were
exercised on the pilot (Python) corpus before extending to other languages:
reverse-lookup (`?target=`, "who calls this"), forward-lookup (`?callees=`,
"what does this call"), and transitive lookup (`?target=&depth=2`).

### Results

| Language | Real corpus | Query direction(s) | Recall: before → after | False positives | Bug(s) found & fixed |
|---|---|---|---|---|---|
| Python | Home Assistant core (213 files) | reverse, forward, transitive (depth=2) | reverse 99.96% (2,632/2,633); forward 100.00% (201/201, after an oracle-harness fix); transitive 99.98% (9,967/9,969) | 1 (forward direction — un-normalized chained/IIFE call text) | Decorator-argument calls invisible to `calls://`'s node walk (**BACK-731**, not fixed — measures, doesn't remediate; recurs in both the forward and transitive samples as the same root cause, not a new gap). Chained/immediately-invoked-call raw text un-normalized (**BACK-732**, not fixed) |
| TypeScript | VS Code `src/vs/base` (307 files) | reverse | **100.00%** (no gap) | 0 | None — also surfaced (not a recall gap) an undocumented cascading-attribution behavior: a call inside a nested named arrow is credited to every enclosing scope up to the nearest declared function/method, now documented in [CALLS_ADAPTER_GUIDE.md](reveal/docs/adapters/CALLS_ADAPTER_GUIDE.md) |
| Go | Go compiler internals `cmd/compile/internal` (371 files) | reverse | **100.00%** (no gap, clean on first run) | 0 | None — Go structurally cannot produce the JS/TS cascading-attribution shape (no nested named function declarations, only closures, which never get their own scope) |
| Rust | Meilisearch `milli` crate (238 files) | reverse | 96.98%/95.27% → **100.00%** | 0 (post-fix) | Turbofish generics on a call/method callee defeated the bare-callee-name extractor's naive last-`::`-split (`size_of::<u32>()` → misparsed callee `<u32>`), plus a minor parenthesized-callee gap (`(f)(args)` captured literally) — **BACK-733**, fixed |
| Java | Elasticsearch `server/src/main/java` (4,837 files) | reverse | **9.99%** → **100.00%** | 167 (pre-fix) → 0 (post-fix) | `method_invocation`'s `object` field precedes `name` positionally, so the generic `child(0)`-based extractor returned the call's qualifier/object as the callee name for every qualified or static call (`obj.method()`, `Class.staticMethod()`) — nearly all real Java call sites — **BACK-734**, fixed |
| Ruby | Discourse `app/`+`lib/` (1,899 files) | reverse | **22.05%** → **100.00%** | 30 (pre-fix) → 0 (post-fix) | Ruby's `'call'` node is the same tree-sitter kind Python's plain `call()` uses but a flat receiver/./method/args shape, so `child(0)` returned the receiver for every qualified/self/static call — **BACK-735**, fixed, same class as BACK-734. Two more distinct bugs found in the residual tail while at 99%: `setter`/`operator`-named methods (`def x=`/`def []`) invisible to `--outline` (same class as BACK-638/651/724), and `def Class.method` singleton methods naming themselves after the qualifying constant instead of the method (`_PARAM_LIST_KINDS` missing Ruby's `method_parameters` kind) — both fixed same session |
| PHP | WordPress `wp-admin/`+`wp-includes/` (1,328 files) | reverse | **98.87%** → **100.00%** | 0 | `self::`/`parent::`/`static::`/`Class::method()` (PHP's static/scoped call syntax) all parse to `scoped_call_expression`, a node kind entirely absent from `CALL_NODE_TYPES` — every PHP static call was silently invisible to `calls://` — **BACK-736**, fixed. A second, distinct bug surfaced in the residual tail: `_bare_callee_name` didn't strip PHP's `"new ClassName"` constructor-call prefix or a leading `\` fully-qualified-namespace marker, so neither ever matched a bare `?target=` lookup (same bug class as BACK-733's Rust turbofish gap — a bare-name-normalization miss, not an extraction miss) — fixed same session |
| C# | Jellyfin (2,098 files) | reverse | **69.74%** → **100.00%** | 8 (pre-fix) → 0 (post-fix) | Three distinct bugs, all fixed as **BACK-737**: (1) generic methods (`Task Enqueue<T>(...)`) had their definition name misattributed to the return type, since C#'s `type_parameter_list` sits between the method name and parameter list, breaking `_name_via_param_adjacent`'s "name immediately precedes param list" check — a caller-side gap, unlike every prior language's callee-side bugs, since it corrupts the source of every call-graph edge from an affected method; (2) explicit generic-argument suffixes (`new List<Video>()`, `Method<string>()`) survived into `_bare_callee_name`, never matching a bare `?target=` lookup — same bug class as BACK-733's Rust turbofish gap; (3) multi-line fluent call chains (Moq's `_mock.\n    Setup(...)`, a common C# test idiom) left literal newline+indentation in the bare callee name |
| Kotlin | Tivi (629 `.kt` files) | reverse | 99.69% → **100.00%** (8/bucket); **99.79%** (20/bucket) | 0 | An oracle-side design inconsistency (not a `calls://` bug) explained the first 2 misses: the oracle attributed primary-constructor parameter-default calls to the class name, which `calls://` never does for any language (only function/method bodies are caller scopes) — fixed in the oracle to match precedent. The remaining 20/bucket residual is the first gap in this program traced to an upstream **grammar** bug rather than a reveal extraction bug: `tree-sitter-kotlin` cannot parse `@Annotation` directly preceding a function type (`@Composable () -> Unit`, ubiquitous in Jetpack Compose code) — the `()` is consumed as the annotation's own argument list, producing an `ERROR` node that drops the entire enclosing function from structure extraction. Not fixable in reveal's Python layer (vendored grammar binary); the grammar-pack version that might fix it is blocked by the already-tracked BACK-573/BACK-620 core-API migration (deferred). Filed **BACK-738**, open |
| Swift | Signal-iOS's `SignalServiceKit` module (1,190 files) | reverse | 97.62% → **99.92%** (8/bucket); **99.79%** (20/bucket) | 0 | Two real, distinct `calls://` bugs found and fixed: (1) `!isRunning(x)` (negated predicate call) parses the whole `!isRunning` as one `prefix_expression` callee node — the leading `!` survived into the index key, never matching a bare `?target=isRunning` lookup; (2) operator overloads (`static func -(left: CGSize, right: CGSize)`) name themselves with a literal operator-symbol token whose tree-sitter KIND *is* the operator text, invisible to every `_name_via_*` strategy — every operator overload was entirely absent from `--outline`/`get_structure()`. Both fixed. The residual gap is **two** distinct upstream `tree-sitter-swift` grammar bugs, not reveal bugs: `return <name>.member` inside a `case let .x(name):` switch pattern produces a parse `ERROR` that cascades to drop most/all of the *rest of the file* from structure extraction (same "whole function vanishes" symptom shape as Kotlin's BACK-738); and `A * B(args)`/`A - B(args)` (a multiplicative/additive operator immediately before a call) misparses the call suffix onto the *whole binary expression*, corrupting the extracted callee text. Neither is fixable in reveal's Python layer — blocked on the same BACK-573/BACK-620 grammar-pack ceiling as BACK-738. Filed **BACK-742**, open |

| C++ | assimp `code/` subdir (218 `.cpp`/~220 `.h`/`.hpp`, 400/440 files parsed clean) | reverse | 95.28% (8/bucket); **95.73%** (20/bucket) | 632 (largely oracle-incompleteness, not `calls://` bugs — cross-checked `push_back`: `calls://` found 441 real project-wide callers vs. the oracle's 405, the gap fully explained by the oracle's 91% file coverage) | No new `calls://` bugs found — unusually, all corrections needed were on the *oracle* side: libclang (the ground-truth tool) semantically resolves straight through typedefs (`aiVector3D` → `aiVector3t`) and macro expansions (`ai_assert(x)` → `aiAssertViolation(...)`) to targets a syntax-only tool like `calls://` can never match, plus mis-modeling constructor member-initializer-list calls, direct-initialization declarations (BACK-744's own ambiguity), and whole-method codegen macros as real call sites. All fixed oracle-side once traced. Two narrow residual misses (a partial-function-body codegen macro, `ASSIMP_END_EXCEPTION_REGION`; one unexplained `operator<<`-chain artifact, `mOutput`) left undiagnosed, combined ~1% of sampled edges — not filed as `calls://` bugs, no evidence either is a real gap rather than oracle noise |

| Scala | GitBucket `src/main/scala` (213 files) | reverse | 96.64% → **100.00%** (both 8/bucket 1,039 edges and 20/bucket 1,651 edges) | 0 | Three distinct, real `calls://` bugs, all fixed. (1) **BACK-746**: Scala infix method calls (`a :: b`, `list map f`, `Accounts filter pred` — Scala lets any single-arg method be called without a dot/parens, and operators ARE methods) parse to `infix_expression`, a node kind entirely absent from `CALL_NODE_TYPES` — every infix call was invisible to `calls://` (the dominant gap: infix invocations of `filter`/`getOrElse`/`map`/`flatMap`). The `operator` field is the method name. (2) **BACK-747**: fully-qualified constructor types `new java.io.File(...)` (a `stable_type_identifier`, not a `field_expression`) and qualified generics `new scala.Array[Byte](...)` were dropped by the instance_expression handler. (3) A **symbolic-named method definition** residual: Slick projections (`def *`) and operator overloads (`def +`, `def ::`) use an `operator_identifier` name node — absent from `--outline`/`get_structure()` (or mis-named after a body/param identifier, e.g. `def +(o) = o` → "o"), so calls inside their bodies had no caller scope. Found via a scalameta oracle (Scala's canonical syntax-only parser). Symbolic-operator *callees* (`==`, `&&`, `+`, `::`) are excluded from the automatically-sampled target pool — a bare `?target=+` URL reverse query is a URL/CLI-encoding edge case — but were verified faithful separately via direct `find_callers` (e.g. `==` 128/128, `+` 97/97, `::` 2/2, matching the oracle exactly) |

| JS/TSX | three.js `src/` (750 `.js` files) + Excalidraw (626 `.ts`/`.tsx` files) | reverse | **100.00%** (both corpora, both 8/bucket and 20/bucket samples) | 0 | Two distinct, real `calls://` bugs, both found via a pre-flight AST dump *before* any oracle ran, both fixed: (1) **BACK-751** — `adapters/ast/adapter.py` had its own independent, unconditional `PYTHON_BUILTINS` filter on the `ast://` adapter's `calls` field, missed when BACK-748 (Scala) fixed the identical bug in `adapters/calls/index.py` — `xs.map(fn)` silently lost its `map` call. (2) **BACK-752** — `new_expression` is shared by C++ (BACK-730) and JS/TS/TSX with two mutually exclusive field shapes (C++'s callee sits in a `type` field, JS/TS/TSX's in a `constructor` field); dispatch always routed to the C++ handler, which returns `None` for the JS/TS shape, so every `new Foo()`/`new ns.Foo()` call was silently invisible. Fixed in both `treesitter.py` and `nav_calls.py` (parity), dispatched structurally on which field is populated. The oracle also needed a genuinely new scope-creation rule not modeled by the earlier TS-only oracle: Jest/Vitest `describe`/`it`/`test`/etc. callbacks (BACK-334/BACK-662) get their own synthetic scope, surfaced only once the corpus included real Jest spec files (Excalidraw) — mirrored 1:1 from `analyzers/_js_test_callbacks.py`, including a minor label quote-stripping quirk (cosmetic, not filed) |

| Zig | Ghostty `src/` (.zig only, 709 files, test/ and `*_test.zig` excluded) | reverse | 92.28% → **99.98%** (8,403/8,405 edges, 20/bucket) | 221 (pre-fix) → 0 (post-fix) | Three distinct, real gaps found via a pre-flight AST dump *before* any oracle ran, all fixed: (1) **BACK-753** — `@as`/`@import`/`@panic`/etc. (Zig's `@`-prefixed compiler builtins) parse as a `BUILTINIDENTIFIER` leaf, a distinct kind from a regular `IDENTIFIER`, so `_extract_zig_suffix_calls` never seeded a callee for them — every builtin call was invisible, despite `@import` alone appearing in nearly every real Zig file. (2) **BACK-754** — `.fixed(&buf)`/`.init(...)` (Zig's type-inferred enum-literal call syntax, e.g. `var w: std.Io.Writer = .fixed(&buf)`, common in modern Zig via result-location inference) is a bare `.` token directly followed by the name, never wrapped in `FieldOrFnCall` the way a real receiver-qualified chain segment is — silently dropped (one target, `fixed`, measured 0.48% recall pre-fix). (3) **BACK-755** — `test SomeType {}` (Zig's identifier-named test form, the idiomatic way to colocate tests with a generic type/fn factory, e.g. `test WeakRef {}`) was entirely invisible to `get_structure()` — `_get_test_name` only recognized string-literal names, so the whole test scope (and every call inside it) was missing, not just its calls. All the FPs (221 pre-fix) traced to two oracle-modeling gaps, not `calls://` bugs: the oracle initially only walked `.fn_decl` scopes (missing `test "name" {}` string-named scopes entirely — Zig colocates tests inline, unlike every prior language's separately-directoried test suite) and the staged corpus initially included Ghostty's non-Zig files (189 Swift, 32 C, plus others — the macOS GUI shell), which `calls://`'s multi-language index happily scanned. One residual miss (2/8,405 edges, both `list_themes.zig`) traced to a pre-existing `tree-sitter-zig` parse error on that one file (`has_error: true`), not reproduced in isolation — narrow, undiagnosed, not filed |

| C | Redis `src/` (125 `.c` + 83 `.h`, `deps/`/`curl/`/`modules/`/`src/modules/`/`tests/` excluded) | reverse | 89.52% → **100.00%** (both 8/bucket 1,196 edges and 20/bucket 2,826 edges) | 433 (pre-fix, 8/bucket) → 17/33 (post-fix) | No new `calls://` extraction bugs found — every real fix landed in the libclang oracle, adapted from the C++ oracle. Two general oracle-side bugs new to this program: byte-offset-vs-char-offset slicing of `cursor.extent` (silently wrong on any file with a non-ASCII byte, e.g. one curly-apostrophe comment corrupted ~6 targets' extraction), and a macro-vararg-nested call (`serverLog(level, fmt, ..., strerror(errno))`) losing ALL position info under macro re-expansion (`cursor.extent` collapses to zero-width) — a `cursor.spelling` fallback was added, guarded to require ≥1 real argument so it doesn't also fabricate calls from object-like macro constants like `HUGE_VAL`. The dominant false-positive source (433 at first run) was Redis's extensive `#ifdef`-gated optional-feature/self-test code — `calls://` (never preprocessing) sees every branch unconditionally where libclang can only compile one; fixed by building the oracle with a maximal "every optional feature on" flag set. One real, narrow tree-sitter-c grammar bug found and filed as **BACK-756** (open, not fixed, same class as Kotlin's BACK-738/Swift's BACK-742/C++'s BACK-745): a multi-line macro definition in `ziplist.c` desyncs the parser into ERROR-recovery, dropping the following function from `get_structure()` entirely. Remaining false positives all trace to documented, accepted residual classes (2 unparseable Solaris/BSD-only files, several headers-unavailable feature flags, two permanently-`#if 0`-disabled dead-code blocks), none `calls://` defects |

| Lua | Kong API gateway's `kong/` package dir (605 `.lua` files, 604 parsed clean — 1 excluded, a LuaJIT-only `0x01ULL` 64-bit-integer literal no standard-Lua parser recognizes) | reverse | **100.00%** (both 8/bucket 1,422 edges and 20/bucket 3,549 edges) | 11 (8/bucket) / 23 (20/bucket), all traced to documented residuals, none `calls://` defects | Two real, distinct `calls://` bugs found via pre-flight AND fixed: **BACK-757** — `_bare_callee_name` split only on `->`/`.`/`::`, never a lone Lua `:` (`db:init_connector()`, Lua's DOMINANT OOP method-call idiom), so every colon-method call's bare callee stayed the full `"receiver:method"` string and never matched a bare `?target=method` lookup — the single highest real-world-impact gap this session, same bug class as Rust's turbofish/PHP's namespace-prefix/C#'s generic-suffix normalization misses. **BACK-758** — `name = function(...) end` / `tbl.k = function(...) end` (module-table method idiom) / `{ key = function(...) end }` (table-constructor field, Lua's metatable-dispatch/event-handler-table idiom) were ALL entirely invisible to `get_structure()`/`--outline` — not just their calls, the whole scope — found via a real Kong corpus grep (643 occurrences of `= function(` across 176 files); fixed by adding Lua-specific scope extraction (mirroring JS/TS's `_arrow_or_fn_value` precedent for a value that carries no name of its own). Fixing BACK-758 surfaced its own false-positive bug in the same session (not filed separately, fixed pre-measurement): the table-constructor-field extraction naively took "the first identifier child" of a `field` node, which also matches a COMPUTED key's bracketed expression (`{ [CONTENT_TYPE_POST] = function(...) end }`, a dynamic-dispatch idiom) — misattributing the value function's calls to the key expression's name; fixed by requiring the identifier be the field's structural first child (a literal string key), not preceded by `[`. All remaining false positives trace to the one excluded unparseable file (`router/transform.lua`) plus one inherent bare-name-matching limitation (a function parameter named `fmt` shadowing the corpus-wide `fmt` module in `dns/stats.lua`, not a Lua-specific bug). No cascading attribution (confirmed empirically, unlike Zig/JS-TS): Lua's `function_declaration`/`function_definition` are ordinary `FUNCTION_NODE_TYPES` members, so the shared complexity/calls walk stops at every nested function boundary |

| GDScript | Pixelorama (pixel-art editor), `samples/gdscript_pixelorama/` (247 `.gd` files, one coherent Godot project — 246 parsed clean; 1 excluded, see below) | reverse | **100.00%** (both 8/bucket 1,099 edges and 20/bucket 2,678 edges) | 6 (8/bucket) / 18 (20/bucket), all traced to the one excluded file, none `calls://` defects | One real, dominant `calls://` bug found via pre-flight AND fixed: **BACK-759** — `self.foo()`/`obj.method()`/`Class.static()`/`ClassName.new()` (GDScript has no `new` keyword; `.new()` IS the constructor-call idiom) and every segment of a chained call (`a.b().c()`) parse to `attribute_call`, a node kind entirely absent from `CALL_NODE_TYPES` — the single most common GDScript call idiom (any `self.`-qualified call, and every object instantiation) was silently invisible to `calls://`. Unlike Java/Ruby/PHP's dotted-call node kinds, the receiver here is not a field/child of the call node at all — it's a preceding SIBLING inside the enclosing `attribute` node's flat `(receiver, '.', segment, '.', segment, ...)` child list — so the fix reconstructs the qualified name from a raw source-text span rather than a field lookup. Fixing this also required guarding `nav_calls.py`'s `range_calls` (the `ast://`/`--calls`/`--sideeffects`/`--boundary` path) against double-counting: it already special-cased this exact flat chain (`_extract_gdscript_attribute_calls`, added earlier under BACK-431) to reconstruct the FULL qualified callee, so once `attribute_call` became a `CALL_NODE_TYPES` member the generic per-node walk started ALSO matching it directly and emitting a second, wrongly-bare duplicate entry — caught by an existing regression test, fixed by excluding `attribute_call` from that generic check. One file, `ExportDialog.gd`, is excluded from the oracle: it contains a bare call to a function literally named `export` (`func export() -> void: ...` / `export()`), which this oracle's npm `tree-sitter-gdscript` (6.1.0) build parses as a grammar `ERROR` — `export` is treated as reserved even in plain call position — while reveal's own bundled `tree_sitter_language_pack` (1.8.1) build of the SAME upstream grammar parses the identical file with zero errors and correctly extracts the call (confirmed directly against `GDScriptAnalyzer`). A genuine grammar-BUILD skew between two independently vendored copies of the same grammar, running in the OPPOSITE direction of every prior residual in this program (the tool under test is fine; the oracle's tool is not) — excluding the file (rather than fabricating a false miss) is the correct call, and every sampled false positive traces to exactly this one file. No cascading attribution for named functions (ordinary `FUNCTION_NODE_TYPES` boundary-stop, same as Go/Rust/Lua); GDScript's anonymous/named `lambda` function-VALUE syntax is confirmed (empirically, not assumed) to have NO scope of its own at all — calls inside any lambda, named or not, bleed straight through to the nearest enclosing named function, the same "transparent boundary" shape as Lua's BACK-758 precedent, not a bug (0 named-lambda-variable occurrences in this exact corpus, so low-stakes here) |

| Dart | AppFlowy's `frontend/appflowy_flutter/lib` (1,526 `.dart` files, one coherent Flutter app package, 100% parsed clean) | reverse | 86.58% → **100.00%** (8/bucket, 2,337 edges); → **97.55%** (20/bucket, 4,785 edges) | 0 at both sample sizes, post-fix | Six distinct, real `calls://` bugs found, all but one fixed. `calls://` had effectively NO Dart call-graph support before this session (Dart's grammar has no dedicated call-expression node kind at all): (1) **BACK-760** — every plain/dotted/cascaded/null-safe call (`foo()`, `obj.method()`, `this.foo()`, `Class.static()`, `obj?.method()`, `obj!.method()`, `..method()`) parses to a flat `(primary, selector*)` sibling run with no wrapping call node, and `List<int>.from(...)`-style generic-typed constructor calls parse to a separate `constructor_invocation` node — both entirely absent from `CALL_NODE_TYPES`, the single largest total blind spot in this whole program. (2) **BACK-761** — `constructor_signature`/`factory_constructor_signature` absent from `FUNCTION_NODE_TYPES`: every constructor had no caller scope at all. (3) **BACK-763** — the explicit pre-Dart-2 `new Foo(...)` form parses to `new_expression` (shared with C++/JS/TS), but the existing field-based extractors return `None` for Dart's flat, field-less shape. (4) **BACK-764** — a constructor WITH an initializer list (`Foo(...) : super(...) { ... }`, Flutter/BLoC's dominant constructor idiom) wedges an `initializers` sibling between the signature and the real body, defeating `_function_end_node`'s pairing lookup and truncating the WHOLE body's calls to empty; initializer-list calls themselves also live outside `body_node`. (5) **BACK-765** — `const Duration(...)`-style explicitly-const-evaluated constructor calls (ubiquitous in Flutter — the recommended default whenever every argument is constant) parse to a third distinct flat-constructor node, `const_object_expression`, also absent from `CALL_NODE_TYPES`. (6) **BACK-766/BACK-767** — getters/setters (`getter_signature`/`setter_signature`) and `const`-marked constructors (`constant_constructor_signature`) were BOTH entirely absent from `FUNCTION_NODE_TYPES` (no caller scope at all), and parameter DEFAULT VALUES for any signature kind (`{int x = compute()}`) live outside `body_node` the same way initializer lists do. (7) **BACK-769** — `super.method()`/`await super.method()` (override-delegation, a common Dart idiom) has its qualifier as a BARE sibling with no wrapping `selector` node (or nested one level inside `await_expression`'s own children), a shape the initial flat-sibling extractor didn't handle. A structural cascading bug was also found and fixed pre-oracle: Dart's disjoint `function_signature`/`function_body` sibling pairing (needed for `_function_end_node`'s outline-range fix) meant the shared complexity/calls walk's `FUNCTION_NODE_TYPES`-boundary stop condition didn't actually stop at a NESTED named local function — its body, a separate sibling, kept getting walked by every enclosing scope, double-counting its calls; fixed by having the walk detect and skip a nested signature's paired body sibling. The ONE residual, left open and documented rather than worked around — **BACK-768** — is an upstream `tree-sitter-dart` grammar ambiguity, not a reveal bug: a single-argument generic call (`getIt<Foo>(x)`, `getIt<Foo>(name: x)`, `BlocBuilder<A,B>(builder: ...)`) is misparsed as a `relational_expression`/record-literal chain instead of a generic function call whenever the argument list has exactly one element (0 or 2+ arguments parse correctly) — genuinely ambiguous to a context-free grammar without semantic/import resolution, and not fixable in reveal's Python extraction layer. All 20/bucket residual misses traced to exactly this one class. A second, distinct upstream-grammar-adjacent finding was traced to the ORACLE, not `calls://`: `analyzer`'s `InstanceCreationExpression` for an un-namespaced dotted `const`/`new` NAMED constructor call (`const EdgeInsetsDirectional.only(...)`) leaves `constructorName.name` null and puts the WHOLE dotted path in `constructorName.type` (can't distinguish "Class.namedCtor" from a library-prefixed plain type without semantic info) — the oracle's first draft used the unstripped dotted type text as ground truth, manufacturing 191 false positives against `calls://`'s (correct) bare-last-segment name; fixed oracle-side by taking the final dotted segment, same bare-name convention the rest of the oracle already follows. Dart was the EIGHTEENTH and FINAL language in this program — no unmeasured languages remain. |

Full methodology, per-corpus commit/snapshot, and the harness scripts
(`build_oracle*.py`/`.rb`/`.go`/`.js`/`.php`/C# `Program.cs`, `main.rs`, Kotlin
`KotlinOracle.kt`, Swift `swift-oracle/main.swift`, C++/C via libclang, Scala
`build_oracle_scala.scala` via scalameta, `build_oracle_js.js` for JS/TSX,
`zig-oracle/build_oracle_zig.zig` for Zig via `std.zig.Ast`, `build_oracle_lua.js`
for Lua via `luaparse`, `build_oracle_gdscript.js` for GDScript via the npm
`tree-sitter-gdscript` grammar, `dart-oracle/build_oracle_dart.dart` for Dart
via `package:analyzer`, `diff_*.py`) for all eighteen languages:
[calls-recall-oracle/README.md](../internal-docs/planning/dogfood-findings/calls-recall-oracle/README.md).

All eighteen `VALIDATION.md`-tracked languages are now measured for
cross-file call-graph recall. Import/dependency and side-effect recall
remain the authority for full per-language coverage status — see those
sections' own tables; `_bare_callee_name`
/`_get_callee_name`'s other dotted-name-family languages are a reasonable place
to look next, given Java's BACK-734, Ruby's BACK-735, PHP's BACK-736, C#'s
BACK-737, Kotlin's BACK-738, Scala's BACK-746/747, JS/TSX's BACK-751/752,
Zig's BACK-753/754/755, Lua's BACK-757/758, GDScript's BACK-759, and Dart's
BACK-760/761/763/764/765/766/767/769 all show even an "unflagged" language
can hide a systemic callee-, caller-, or grammar-level bug.

## Re-running this yourself

Every loop's harness is a plain script pair — `build_oracle.*` (produces the
independent ground truth) and `diff_recall.py` (diffs it against a live reveal
run) — checked in alongside its findings, not hidden in this repo's history:

```
# Import/dependency recall — one directory per language, both corpora each
internal-docs/planning/dogfood-findings/c-recall-oracle/
internal-docs/planning/dogfood-findings/cpp-recall-oracle/
internal-docs/planning/dogfood-findings/csharp-recall-oracle/
internal-docs/planning/dogfood-findings/dart-recall-oracle/
internal-docs/planning/dogfood-findings/gdscript-recall-oracle/
internal-docs/planning/dogfood-findings/go-recall-oracle/
internal-docs/planning/dogfood-findings/java-recall-oracle/
internal-docs/planning/dogfood-findings/js-tsx-recall-oracle/
internal-docs/planning/dogfood-findings/kotlin-member-import-oracle/
internal-docs/planning/dogfood-findings/lua-recall-oracle/
internal-docs/planning/dogfood-findings/php-recall-oracle/
internal-docs/planning/dogfood-findings/python-recall-oracle/
internal-docs/planning/dogfood-findings/ruby-recall-oracle/
internal-docs/planning/dogfood-findings/rust-recall-oracle/
internal-docs/planning/dogfood-findings/scala-member-import-oracle/
internal-docs/planning/dogfood-findings/swift-recall-oracle/
internal-docs/planning/dogfood-findings/ts-recall-oracle/
internal-docs/planning/dogfood-findings/zig-recall-oracle/

# Narrower single-idiom investigations that preceded the full loops above
internal-docs/planning/dogfood-findings/csharp-global-using-oracle/
internal-docs/planning/dogfood-findings/ruby-autoload-oracle/

# Side-effect / boundary recall (per-language subdirs + program README)
internal-docs/planning/dogfood-findings/sideeffects-recall-oracle/
```

Each harness's own README documents the exact corpus commit/snapshot used,
the oracle's assumptions, and the stratified-sampling method, so a result can
be reproduced or challenged line by line rather than taken on faith.

## Scope

This artifact covers recall of three DD signals: **import/dependency-graph
recall** (`depends://` and `imports://` fan-in — the property whose failure in
BACK-542, an 18-importer module reported as having zero, motivated the whole
program), **side-effect/boundary classification recall** (`--sideeffects` /
`--boundary`), and **cross-file call-graph recall** (`calls://` — BACK-730,
the same silent-wrong-answer risk as BACK-542: a whole-project graph query
where a false negative reads as a confident, checked answer). `calls://` is now
measured for all 18 languages (Python across three query directions,
TypeScript, Go, Rust, Java, Ruby, PHP, C#, Kotlin, Swift, C++, Scala, JS/TSX,
Zig, C, Lua, GDScript, and Dart — the eighteenth and final language, see
[Cross-File Call-Graph Recall](#cross-file-call-graph-recall)) — all now
clean or fixed-and-reverified, save a handful of documented,
upstream-grammar-level residuals (Kotlin's BACK-738, Swift's BACK-742, C++'s
BACK-745, C's BACK-756, and Dart's BACK-768), none fixable in reveal's Python
extraction layer. This closes the full calls:// recall sweep BACK-730 opened.
It does not yet cover recall for `surface` or `contracts` (BACK-719) — see
`ROADMAP.md` for the forward plan.
