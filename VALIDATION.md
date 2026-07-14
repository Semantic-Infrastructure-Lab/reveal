# Correctness Validation: Import/Dependency Recall

This document is the **correctness** counterpart to reveal's language coverage
claims. Coverage answers "does this command run on this language?" This
answers a sharper question: **when `depends://` (or the equivalent
`imports://` fan-in view) says "N files import this," how often is that
number actually right — and what happens when it's wrong?**

It exists because a wrong answer is the one failure mode a due-diligence or
architecture-audit user cannot tolerate. A dependency-graph tool that
occasionally reports "nothing imports this" about a load-bearing module is
worse than no tool at all, because it looks like a confident, checked answer.
This document is the audit trail proving how that failure mode was found,
measured, and closed — and gives you what you need to re-run the check
yourself against reveal's actual source, not take our word for it.

## Method

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

## Results

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

**Eleven measurement loops, eleven real bugs found, all eleven fixed** (Swift's
BACK-567 was the last, closing the premium-tier program; PHP's
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

## What the false positives mean

The only false positives observed (Go, 8 of 822) are files gated behind
`//go:build windows` tags. `go list`'s oracle was built with `GOOS=linux` and
correctly excludes them; reveal's import extraction has no build-tag
awareness and includes them anyway. This is a real precision gap, not a
recall failure — reveal reports a dependency edge that *is present in the
source* but wouldn't compile into the target binary on Linux. Documented, not
filed as a defect, since it errs toward showing you more of the source graph
rather than hiding a real edge.

## Known gaps — not yet measured with a full oracle loop

The following are **not** in the table above because they have not been
run through an independent-oracle diff against a real corpus:

- **C++, Dart, Lua, Zig, GDScript** — each shares a resolver
  family with at least one already-measured language, but has not been
  independently confirmed on its own real corpus. (Swift graduated out of
  this list — measured with a full `swift package dump-package` oracle loop,
  BACK-567; see the Results table.)
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

## Re-running this yourself

Every loop's harness is a plain script pair — `build_oracle.*` (produces the
independent ground truth) and `diff_recall.py` (diffs it against a live
`depends://` run) — checked in alongside its findings, not hidden in this
repo's history:

```
internal-docs/planning/dogfood-findings/ts-recall-oracle/
internal-docs/planning/dogfood-findings/java-recall-oracle/
internal-docs/planning/dogfood-findings/go-recall-oracle/
internal-docs/planning/dogfood-findings/python-recall-oracle/
internal-docs/planning/dogfood-findings/kotlin-member-import-oracle/
internal-docs/planning/dogfood-findings/scala-member-import-oracle/
internal-docs/planning/dogfood-findings/rust-recall-oracle/
internal-docs/planning/dogfood-findings/csharp-global-using-oracle/
internal-docs/planning/dogfood-findings/ruby-autoload-oracle/
```

Each harness's own README documents the exact corpus commit/snapshot used,
the oracle's assumptions, and the stratified-sampling method, so a result can
be reproduced or challenged line by line rather than taken on faith.

## Scope

This artifact covers **import/dependency-graph recall** (`depends://` and
`imports://` fan-in) only — the specific property whose failure
(BACK-542: an 18-importer module reported as having zero) motivated this
entire validation program. It does not (yet) cover recall for `surface`,
`contracts`, or `--sideeffects` — those are tracked as open coverage work,
separately from this correctness program. See `ROADMAP.md` for what's next.
