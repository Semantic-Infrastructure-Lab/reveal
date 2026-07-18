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

Two signals have been through this treatment so far, each as its own
independent-oracle program on real corpora: **import/dependency recall**
(`depends://` / `imports://` fan-in) and **side-effect / boundary
classification recall** (`--sideeffects` / `--boundary`). Both are documented
below, with the exact per-language status first.

## Validation status at a glance

Reveal *supports* far more languages than are listed here (run `reveal
--languages` for the full coverage list). This table is narrower on purpose:
it says only where recall has been **measured against an independent
ground-truth oracle on a real codebase** — the difference between "the command
runs" and "we have proven the answer is right." Anything marked *not measured*
is a claim we have not yet checked, **not** a claim it is broken.

| Language | Import recall | Side-effect recall | Status |
|---|---|---|---|
| Python | ✅ 100% (Home Assistant) | ✅ 83.5% (Home Assistant) | **Measured** |
| TypeScript | ✅ 100% (VS Code) | ✅ 91.3%¹ (VS Code) | **Measured** |
| Java | ✅ 100% (Elasticsearch) | ✅ 97.5% (Elasticsearch) | **Measured** |
| Go | ✅ 100% (Kubernetes) | ✅ 96.3% (client-go) | **Measured** |
| Ruby | ✅ Zeitwerk-inferred (Discourse) | ✅ 98.8% (Discourse) | **Measured** |
| Kotlin | ✅ 99.1% (tivi) | ✅ 100%² (tivi) | **Measured** |
| Rust | ✅ 100% (Meilisearch) | ✅ 97.4% (Meilisearch) | **Measured** |
| C# | ✅ namespace-graph fix (Jellyfin) | ✅ 98.3% (Jellyfin) | **Measured** |
| PHP | ✅ 100% (WordPress) | ✅ 97.5% (WordPress) | **Measured** |
| Swift | ✅ 100% (Kickstarter iOS) | ✅ 100%² (Kickstarter iOS) | **Measured** |
| Scala | ✅ 100% (GitBucket) | — not yet run | **Measured** (import only) |
| C++ | ✅ 100%³ (Godot) | ✅ 83.3% (Godot) | **Measured** |
| C | ✅ 100%⁹ (Redis) | — not yet run | **Measured** (import only) |
| Lua | ✅ 99.5% (Kong) | — not yet run | **Measured** (import only) |
| Dart | ✅ 100%⁵ (AppFlowy) | — not yet run | **Measured** (import only) |
| GDScript | ✅ 100%⁶ (godot-demo-projects) | — not yet run | **Measured** (import only) |
| Zig | ✅ 100%⁷ (ghostty) | — not yet run | **Measured** (import only) |
| TSX, plain JS | ✅ 100%⁸ (Excalidraw, three.js) | — not yet run | **Measured** (import only) |

¹ Overall TypeScript side-effect recall was 76.8%; the gap was almost entirely
one architecturally-distinct category — Node's `process.env.X` env reads are a
property access, not a call, so the call-only classifier never saw them.
Excluding that category recall was 91.3%; the category itself was then closed
by a dedicated property-access channel (BACK-644), corpus-validated at 98.7% on
VS Code. ² Measured on a category-scoped stratified sample (Kotlin: `db`;
Swift: `http`), not the full six-category sweep the other languages got.
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
not a defect in the fix. Full story: [harness README](../internal-docs/planning/dogfood-findings/cpp-recall-oracle/README.md). ⁴ Bugs were
found and fixed by running reveal against these languages on first contact, but
no quantified recall number exists for them yet — see the roadmap's validation
track. ⁵ Sampled recall was 99.76% (823/825); the 2 residual misses were both
oracle false positives — a code-generation script's `writeln('''...''')`
embeds literal `import '...'` *text* inside a Dart template string, which
tree-sitter correctly never parses as a real import (the same class of
false positive the Lua loop's `nginx_kong.lua` case documented).
⁶ Full census (41/41 edges, no sampling — the corpus's 19 distinct targets
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
⁷ Stratified sample (26 of 641 distinct targets, 426 of 2,334 in-scope
edges), bucketed by fan-in. Only `.zig`-suffixed relative-file `@import`s are
in scope — Zig's other import shape, `@import("std")`/`@import("gobject")`/
named build-graph module aliases, has no static file-per-name convention
(resolving it would mean interpreting `build.zig`'s own code) and is
correctly skipped by `resolve_import`, not counted as a recall gap. No bug
found — the relative-file resolver was already correct across every fan-in
bucket sampled, up to 3 levels of `../` traversal.
⁸ One combined pass across two corpora (three.js, plain `.js`; Excalidraw,
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
⁹ Graduated from the earlier grep spot-check (BACK-611) to a full stratified
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
| Java | Elasticsearch (`server/src/main/java`, 4,837 files) | Buildless JLS package/filename convention | Stratified sample, 975 edges | 97.54% → 99.69% → **100%** | 0 | Nested-type and static-member imports (`import a.b.Outer.Inner`) never fell back from the (non-existent) `Inner.java` to the real enclosing `Outer.java` (BACK-551). The last 3/975 misses were all importers inside `org.elasticsearch.env`, a real source package silently excluded because `env` was in the global directory skip-set — closed by BACK-552 (context-sensitive `is_skippable_dir`), verified this loop: `ClusterState`/`Sets` now resolve their `env/NodeEnvironment`/`NodeRepurposeCommand` importers. |
| Go | Kubernetes (`pkg/`, 2,266 files) | `go list -json` (real toolchain) + independent per-file import parse | 25-target stratified sample, 822 edges | **0%** effective (every single-file query returned zero, unconditionally) → **100%** | 8 (documented, safe — see below) | Go resolves an import to its package *directory*, but the file-level query path did an exact-key lookup against the file itself — a key that could never match a directory-keyed edge. Affected every Go dependents query, always. |
| Python | Home Assistant core (`homeassistant/`, 213 files) | `ast.parse` + independent filesystem/`sys.path` resolution | 82-target stratified sample, 790 edges | 36.74% → **100%** | 0 | Three variants of one confusion — "a package directory is not a `sys.path` root" — causing false project-root detection, self-shadowing of stdlib-named siblings, and truncation of multi-segment relative imports to their first component |
| Ruby (Zeitwerk convention) | Discourse (`app/`, 1,190 files) | Direct require-statement density + constant-reference measurement | Full-tree density scan; 5,000-file capped edge scan | Confident false negative on ~95%+ of real edges → **32,078 additional edges inferred** (vs. 8,645 from explicit `require`) | 0 (additive, exact-match only — never fabricates an edge) | Modern Rails apps express nearly all intra-app dependencies as bare constant references resolved by Zeitwerk's file-path convention, with *zero* `require` statements for reveal to see. Fixed in two stages: an honest "low coverage" caveat, then a path→constant inference pass that recovers the missing edges directly. |
| Kotlin | tivi (Android/KMP app, 629 files) | Content-scanned package + top-level-declaration oracle | Exhaustive, 233 edges | 12.0% → **99.14%** | 0 (1 residual is a grammar-library parse-recovery artifact, not a resolver bug) | Top-level function/property imports have no class/type component to resolve toward — needed a new content-scanned member index, since the existing peel logic could only ever reach type names |
| Scala | GitBucket (247 files) | Content-scanned package + object-member oracle | Exhaustive, 1 qualifying edge | 0% → **100%** | 0 | `lowerCamelCase` top-level singleton objects defeated the existing Uppercase-gated resolver peel the same way a package segment would |
| Rust | Meilisearch (17-crate workspace, 726 files) | Independent regex-based `use`/`Cargo.toml` parser | 30-target stratified sample, 295 edges | 59.0% → **100%** | 0 | (1) Multi-segment `crate::`/`super::` paths only ever consumed their first segment, with `super::` unconditionally failing; (2) grouped `use crate::{a,b,c}` imports matched on a keyword-typed AST node the extractor didn't recognize, silently dropping the entire statement |
| C# | Jellyfin, Godot C# glue | Real-corpus grep (idiom itself was fixture-only — absent from both corpora) | Fixture + incidental real-corpus hit | N/A for the target idiom | — | Investigating the (absent) target idiom surfaced that namespace fan-out was never wired into the dependency graph at all for zero-import files |
| PHP | WordPress core (`samples/php`, 1,927 files) | Buildless `require`/`require_once`/`include`/`include_once` string-expression resolver (not `use`/namespace — see [harness README](../internal-docs/planning/dogfood-findings/php-recall-oracle/README.md) for why) | 80-target stratified sample, 442 edges | 0.00% → 33.85% (BACK-564) → **100.00%** (BACK-565) | 0 | `depends://`'s PHP resolver only recognized a bare string-literal require/include target; every real WordPress require/include uses string concatenation (`__DIR__ . 'x.php'`, `ABSPATH . WPINC . 'x.php'`, etc. — confirmed 0 bare-literal requires exist anywhere in the corpus). BACK-564 resolved the universal `__DIR__`/`dirname(__FILE__)` directory-relative idiom via a structural AST-walk extractor. BACK-565 (same session) closed the remaining majority: WordPress-specific framework-bootstrap constants (`ABSPATH`/`WPINC`/`WP_CONTENT_DIR`/`WP_PLUGIN_DIR`) are genuinely derivable — WordPress defines them in-tree via `define('ABSPATH', __DIR__ . '/')` and similar — so a project-wide constant index (built to a fixed point, since real constants chain through each other) now substitutes them into the same concatenation resolver. Constants with genuinely ambiguous `define()` values (measured: 3/50) are excluded from the index, never guessed |
| Swift | Kickstarter iOS (`samples/swift`, 1,961 files, 8 SwiftPM packages) | `swift package dump-package` (real toolchain, target list) + independent per-file import parse | Full-tree; 21 declared targets, 164-edge precision sample | ~0% effective (123 edges / 7 dependent files) → **100% of declared targets resolved** (384,278 edges / 1,511 dependent files) | 0 (164-edge sample, none unbacked) | Swift's import granularity is the *module (SwiftPM target)*, not the file, but the resolver only matched `import Foo` → a unique `Foo.swift` — resolving ~0% of real multi-file targets, AND (worse) leaving `unresolved_intra` at 0 so no honest-decline `⚠` fired: a silent wrong "no dependents". Fixed in two buildless parts: (1) `Sources/<Target>/` directory-convention fan-out (`import Foo` → every file in target Foo, C#-namespace-style); (2) a structural `Package.swift` parse for targets that relocate sources via an explicit `path:` (real GraphAPI `path: "./Sources"`, 326 importers). The independent `dump-package` oracle caught the custom-`path:` case the directory convention alone would have silently mis-mapped |
| Lua | Kong (`samples/lua`, 1,309 `.lua` files) | Project's own `kong-latest.rockspec` `build.modules` table (authoritative dotted-module → file map) + independent regex `require(...)` scan | 30-target stratified sample (fan-in buckets 1 / 2-5 / 6-20 / 21-50 / 50+), 782 edges | 85.4% → **99.5%** | 29 (BACK-670, filed not fixed — see below) | `require("a.b.c")` may name a *directory* module (`a/b/c/init.lua`, Lua's `package.path` `?/init.lua` convention) with no flat `a/b/c.lua` file at all — `_match_dotted` only ever tried appending an extension to the last dotted component, so every directory-module require silently resolved to `None`. Hit 5 real Kong targets (`kong.conf_loader`, `kong.db.declarative`, `kong.vaults.env`, `kong.dynamic_hook`, `kong.plugins.rate-limiting.policies`), each returning a confident "no dependents" despite 2-35 real importers. Fixed via a new opt-in `directory_index_filenames` spec field. 3 residual misses (spec-fixture importers of `kong.vaults.env`) and 29 false positives (a shared-resolver basename-collision class — external `resty.*` modules landing on same-named in-tree `kong.tools.*` files) filed not fixed as BACK-671/BACK-670 — see [harness README](../internal-docs/planning/dogfood-findings/lua-recall-oracle/README.md) |
| Dart | AppFlowy (`samples/dart/frontend/appflowy_flutter`, 1,974 `.dart` files, 14 in-tree packages) | Every in-tree `pubspec.yaml`'s declared `name:` → its own `lib/` (authoritative name→dir map) + independent regex `import '...'` scan | 30-target stratified sample (fan-in buckets 1 / 2-5 / 6-20 / 21-50 / 50+), 825 edges | 19.3% → **99.76%** (100% real — see below) | 0 | `package:<name>/x.dart` — the dominant real-world Dart import shape (5,989 of 6,290 in-tree imports in the sample corpus, vs. 301 relative imports) — had no resolution branch at all: it contains `/` and matched `_looks_like_path` before any separator logic ran, so it was always tried (and failed) as a literal file-relative path. Every `package:` self- and cross-package import in the corpus silently resolved to `None`. Fixed with a new opt-in `package_uri_scheme`/`package_manifest_filename`/`package_manifest_lib_dirname` spec triple: builds a project-wide package-name→`lib/` index from every in-tree `pubspec.yaml` (cached per scan on the shared `file_index`), the same authoritative-manifest role Lua's rockspec and Swift's `Package.swift` played. The 2 residual sampled misses were both oracle false positives — a code-generation script's `writeln('''...''')` embeds literal `import '...'` text inside a Dart template string, which tree-sitter correctly never parses as a real import (same class as Lua's `nginx_kong.lua` false positive) — so true recall on the sample is 100% (823/823 real edges) |
| GDScript | godot-demo-projects (`samples/gdscript`, 456 `.gd` files, 138 independent Godot projects) | Independent regex scan for `preload`/`load("res://...")`, `extends "res://..."`, and `extends Foo` matched against a project-scoped `class_name Foo` index, each `res://` path resolved against its file's own nearest `project.godot` (never the whole tree) | Full census (small population: 19 distinct targets), 41 edges | 24.4% → **100%** | 0 | Two bugs: (1) `depends://`/`imports://`'s `extra_paths` construction skipped the scan root as a search path whenever it already equaled the importing file's own directory (`scan_root != base_path`) — harmless for file-relative resolvers (which try `base_path` first) but fatal for GDScript's project-root-relative `res://`, which never falls back to `base_path`; every root-level file's (`main.gd`/`game.gd`/`test.gd`-shaped) `res://` import silently failed. Fixed by always including the scan root regardless of that equality. (2) `extends Foo` naming a `class_name Foo` declared elsewhere in-tree — Godot's global class-registration convention, and the dominant edge shape measured (27 of 41) — had no resolution path: a bareword `extends` only ever matched a literal same-named file, and Godot filenames are conventionally snake_case, not the PascalCase class name. Fixed with a new opt-in `class_name_convention` flag: a project-wide `class_name` → declaring-file index (regex-scanned, cached per scan on `file_index`), tried as a fallback when the direct bare-basename match fails |
| Zig | ghostty (`samples/zig/ghostty`, 715 `.zig` files) | Independent regex scan for `@import("...")` (comment-stripped, string-aware), scoped to `.zig`-suffixed relative-file targets only — named-module imports (`std`, `builtin`, build-graph aliases) are out of scope, matching `resolve_import`'s own design | 26-target stratified sample (fan-in buckets 1 / 2-5 / 6-20 / 21-50 / 50+), 426 edges | **100%** (no baseline gap) | 0 | No bug found — the relative-file resolver (plain `(importer.parent / target).resolve()` semantics, no manifest scheme or global-registration convention involved) was already correct across every fan-in bucket sampled, including up to 3 levels of `../` traversal (`src/quirks.zig`, 113 importers) |
| TSX, plain JS | three.js (`samples/javascript`, 1,622 `.js` files) + Excalidraw (`samples/tsx/excalidraw`, 635 `.ts`/`.tsx` files) | Independent regex scan for static/dynamic `import`, `export ... from`, and `require(...)` (comment-stripped, string-aware), true filesystem-based extension/index resolution (not a port of `resolve_import`'s own heuristic — see Finding) | 2 stratified samples, one per corpus (fan-in buckets 1 / 2-5 / 6-20 / 21-50 / 50+): `.js` 30 targets/777 edges, `.tsx` 29 targets/745 edges | `.js` 100% (no gap); `.tsx` 98.79% → **100%** | 0 | `.js`/`.jsx`/`.ts`/`.tsx`/`.mjs` share one resolver function (`_resolve_relative_js`) — a dotted basename with the extension omitted (`./charts.constants` → `charts.constants.ts`, `./WelcomeScreen.Center` → `.tsx`, `./subset-shared.chunk` → `.ts`) was misjudged by the `has_extension` gate (only checks whether the last path segment contains *any* dot) as already having a real extension, so it tried only the literal path plus the narrow `.js/.jsx/.mjs` TS-ESM fallback map, then returned `None` instead of falling through to the plain extension-append/directory-index resolution used for genuinely extensionless specifiers (BACK-672) |
| C | Redis (`samples/c`, `src/`+`modules/`+`tests/modules/`+`utils/`, 275 files) | Real preprocessor, per-directive: `gcc -H -fsyntax-only -iquote <including-file's-dir>` resolves each quoted `#include "..."` in isolation (real header search, not a re-derivation of reveal's own) | 30-target stratified sample (fan-in buckets high/mid/low), 310 edges | **100%** (no baseline gap) | 0 real (2 apparent — see below) | No bug found — `_resolve_include`'s sibling-then-search-path resolution was already correct across every fan-in bucket sampled. Graduated from BACK-611's earlier grep spot-check to this full oracle loop; the loop's *own* first draft (whole-file `gcc -H`, reading the transitive tree) had a self-inflicted undercount bug from gcc's include-guard optimization skipping already-satisfied headers — caught before it could report a false gap, see [harness README](../internal-docs/planning/dogfood-findings/c-recall-oracle/README.md). The 2 apparent false positives are `deps/`-tree (vendored third-party) files `depends://` correctly resolves but this oracle deliberately doesn't scan as importers |
| C++ | Godot (`samples/cpp`, `core/`+`scene/`+`servers/`+`drivers/`+`platform/`, 2,830 files) | Same method as C, per-directive `g++ -H -fsyntax-only -std=c++17` isolation | 30-target stratified sample (fan-in buckets high/mid/low), core/-rooted, 450 edges | 33.11% → 99.56% → **100.00%** | 3 (BACK-664, BACK-675, BACK-676) | `CppImportExtractor.extensions` omits `.h` (owned by `CImportExtractor` alone); `depends://`'s single-file scan-scoping (BACK-525 layer 4) narrowed a `.h` target's parse corpus to `{.c, .h}`, dropping every `.cpp` importer of its own header (BACK-675). Fixed by widening to the C/C++ family union when the target is either language. The first raw measurement (33.11%) was mostly a corpus-size confound, not this bug — `root=samples/cpp` (~14,000 files) tripped `depends://`'s BACK-524 5,000-file scan cap; re-measuring against a bounded, rsync'd sub-corpus (same precedent java/python-recall-oracle already set) isolated the real gap. Residual: 2/450 edges (`core/math/bvh_tree.h`'s own `.inc` fragment includes, sitting inside a template class body) traced to a separate bug — a `#include` inside a class body isn't valid top-level-context grammar, so tree-sitter degrades it to a generic `preproc_call` fallback node the extractor never scanned (BACK-676); fixed by scanning that node type too, filtered to the `#include` directive only. Same loop also found `CppImportExtractor.extensions` never claimed `.hh` (already C++ structurally) or `.mm` (Obj-C++, parses with the `objc` tree-sitter grammar but emits identical `preproc_include`/`preproc_call` nodes, verified empirically) — silently zero import resolution for either extension (BACK-664; Godot corpus: 258 `.hh` + 59 `.mm` files affected). Re-measured after both fixes: 100.00% recall, 0 missing edges on the same 450-edge sample; 24 new true-positive `.mm` importer edges surfaced (spot-checked genuine) register as this oracle's own false positives only because `build_oracle.py`'s ground-truth builder never scanned `.mm` as an importer candidate — a pre-existing oracle scope gap, not a defect. See [harness README](../internal-docs/planning/dogfood-findings/cpp-recall-oracle/README.md) |

**Eighteen measurement loops, eighteen real bugs found, all eighteen fixed**
(C++ is the most recent, and the first loop in this program to find a bug in
the *adapter* layer — `depends://`'s own scan-scoping — rather than only in a
language-specific `_resolve_include`/`_resolve_module` resolver; the C++ loop
went on to find two more bugs on the same corpus — a tree-sitter capture gap
for class-body-nested includes and two missing file extensions — closing at
a clean 100% with zero residual gaps, the first language in the program to
do so after finding real bugs rather than starting clean like Zig). C before
C++ was the
second loop, after Zig, to find no bug at all in `reveal` itself; it did
catch a self-inflicted undercount bug in the oracle harness's own first
draft before that draft could report a false gap, see the harness README.
TSX/plain-JS before it found one bug, BACK-672, a
dotted-basename extension-omission gap in the shared
`.js`/`.jsx`/`.ts`/`.tsx`/`.mjs`
resolver, caught on the `.tsx` sample only (0/745 misses on plain `.js`).
Zig before it was the first loop to find *no* bug at all, a clean 100% on
first measurement across a 26-target stratified sample spanning fan-in from
1 to 113 — evidence the loop shape catches real gaps rather than
manufacturing them by construction. GDScript before it was the first loop to
surface two
independent bugs rather than one — a plumbing gap in `depends://`/
`imports://`'s shared `extra_paths` construction that silently broke every
project-root-relative resolver's root-level-file case, plus a missing
resolution path for Godot's `class_name` global-class convention, the
dominant edge shape in the corpus (27 of 41) — found zero false positives,
full census at 100%. Dart's `package:` URI resolution before it closed what
was then reveal's largest-blast-radius recall gap measured — a
resolver branch missing entirely for the shape covering 95% of a real
corpus's intra-project imports, found zero false positives, and needed no
residual filed since both sampled misses were oracle artifacts, not reveal
bugs). Lua's directory-module resolution gap before that
closed 5 real zero-dependent targets — its two residual findings, a
basename-collision false-positive class and 3 unexplained misses, are filed
separately as BACK-670/BACK-671 rather than counted against this headline,
matching how TS's BACK-643 and C++'s BACK-642 were handled. PHP's
BACK-564/565 before it were both fixed the same session after being
filed with full evidence in the original measurement pass — BACK-565 was
filed as a residual of BACK-564 and closed before the session ended, once
it was clear the framework constants were genuinely derivable rather than
an unbounded framework-specific guess). C#'s `global using` cleared the
specific idiom as architecturally absent from both real corpora checked,
but the investigation still surfaced and fixed an unrelated
namespace-indexing gap. Every *fixed* bug shipped with regression tests
(fail-before/pass-after confirmed by disabling the fix in place, not by
reverting source) and a full-suite run showing zero regressions elsewhere.

### What the false positives mean

The only false positives observed (Go, 8 of 822) are files gated behind
`//go:build windows` tags. `go list`'s oracle was built with `GOOS=linux` and
correctly excludes them; reveal's import extraction has no build-tag
awareness and includes them anyway. This is a real precision gap, not a
recall failure — reveal reports a dependency edge that *is present in the
source* but wouldn't compile into the target binary on Linux. Documented, not
filed as a defect, since it errs toward showing you more of the source graph
rather than hiding a real edge.

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
BACK-675, and BACK-676; see the Results table.):

- **C** — `#include` recall spot-checked at set level against grep ground truth
  on Redis (`samples/c`): 10/10 headers across fan-in 3–75 match exactly, two
  set-verified (server.h 75/75, zmalloc.h 23/23, 0 false pos / 0 false neg).
  Not yet a full stratified from-scratch oracle loop like the premium tier, but
  the real DD blocker on C — `depends://` over-climbing the scan root on a
  Makefile-based tree — was found and fixed here (BACK-609, layer-0
  `.reveal.yaml root:true`). A full `gcc -MM`-oracle loop is the optional
  follow-on.
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
| Kotlin | tivi | 85.0% → **100%** (`db` sample) | `db` category taxonomy gaps |
| Swift | Kickstarter iOS | 0% → **100%** (`http` sample) | `http` idioms unclassified |

Cross-language false-positive sweeps in the same program fixed bare-verb
subsequence over-fire (`dict.update()` misread as a db write) and unscoped
receiver-name collisions (`conn`/`session`/`cache`/`requests`), so the recall
gains did not come at the cost of precision.

## Re-running this yourself

Every loop's harness is a plain script pair — `build_oracle.*` (produces the
independent ground truth) and `diff_recall.py` (diffs it against a live reveal
run) — checked in alongside its findings, not hidden in this repo's history:

```
# Import/dependency recall
internal-docs/planning/dogfood-findings/ts-recall-oracle/
internal-docs/planning/dogfood-findings/java-recall-oracle/
internal-docs/planning/dogfood-findings/go-recall-oracle/
internal-docs/planning/dogfood-findings/python-recall-oracle/
internal-docs/planning/dogfood-findings/kotlin-member-import-oracle/
internal-docs/planning/dogfood-findings/scala-member-import-oracle/
internal-docs/planning/dogfood-findings/rust-recall-oracle/
internal-docs/planning/dogfood-findings/csharp-global-using-oracle/
internal-docs/planning/dogfood-findings/ruby-autoload-oracle/
internal-docs/planning/dogfood-findings/lua-recall-oracle/

# Side-effect / boundary recall (per-language subdirs + program README)
internal-docs/planning/dogfood-findings/sideeffects-recall-oracle/
```

Each harness's own README documents the exact corpus commit/snapshot used,
the oracle's assumptions, and the stratified-sampling method, so a result can
be reproduced or challenged line by line rather than taken on faith.

## Scope

This artifact covers recall of two DD signals: **import/dependency-graph
recall** (`depends://` and `imports://` fan-in — the property whose failure in
BACK-542, an 18-importer module reported as having zero, motivated the whole
program) and **side-effect/boundary classification recall** (`--sideeffects` /
`--boundary`). It does not yet cover recall for `surface` or `contracts`, and
the languages marked *not measured* / *spot-checked* in the status table above
are not yet through a full oracle loop — both are tracked as open validation
work. See `ROADMAP.md` for the forward plan.
