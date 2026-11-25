---
title: Deep-Dive Code Navigation (Element Views)
category: guide
help_topic: nav
help_description: "Element views: reveal FILE ELEMENT --view boundary|effects|flow|exits, plus --varflow and --inputs"
help_category: feature_guides
---
# Deep-Dive Code Navigation (Element Views)

**One-line summary:** Pinpoint inspection inside a function or line range — control flow, data flow, side effects, and refactor pre-flight, all without reading the file top-to-bottom.

Nav flags work on Python, PHP, and the other tree-sitter languages (`reveal --languages`). Most flags accept `:LINE-RANGE` and work on flat procedural files (no function wrapper required).

For the full reference with output samples, see [`AGENT_HELP.md`](../AGENT_HELP.md) — search for "Navigate inside a function".

---

## At a Glance

`reveal FILE ELEMENT --view VIEW` asks how one function or line range behaves; VIEW is
`boundary`, `effects`, `flow` or `exits`. The views take modifiers: `--kind if|loop|try` on
`flow` (repeat it to combine), `--in-loops` or `--state` on `effects`, `--transitive` (with
`--depth N` call hops) on `boundary` and `effects`, and `--nesting-depth N` for the structural
depth of `flow` and `effects --in-loops`. `--inputs`, `--outputs`, `--callsites`, `--varflow`,
`--keys` and `--narrow` keep their own flags, as do MCP `reveal_nav`'s flag names (`boundary`,
`effects`, `flow`, `exits`, `inputs`, `outputs`, `callsites`, ...).

| Flag | Question it answers |
|------|---------------------|
| `--view flow` | What recognized structures are inside this selection? |
| `--scope :LINE` | What scope is this line inside, and what gates it (JSON `condition` field per ancestor)? |
| `--around N` | What's near line N? (verbatim ±N lines) |
| `--view flow --kind if` | What conditional branches exist? |
| `--view flow --kind try` | What try/except structure exists? |
| `--view exits` | Which static exit sites and syntactic gates were recorded? |
| `--callsites` | What does this call? (sub-element scope) |
| `--varflow VAR` | Where is VAR read, written, or tested? |
| `--varflow VAR --cross-calls` | Same, but follows VAR across function call boundaries |
| `--narrow VAR` | How does VAR's type narrow through control-flow branches? |
| `--inputs` | Candidate inputs (undefined reads; review bindings) |
| `--outputs` | What does this range write that's read later? |
| `--view effects` | What DB/HTTP/FS/log/sleep calls fire here? |
| `--view flow --kind loop` | What loops exist, and how are they nested? |
| `--view effects --in-loops` | Which loops make DB/HTTP/FS/log calls inside them? (N+1 / per-item fan-out review) |
| `--view effects --state` | Detected global/nonlocal/field/env/session/cache/db/file writes |
| `--keys VAR` | Which keys/properties of VAR are read, written, or tested (dict/object/array shape)? |
| `--view boundary` | One-shot contract: inputs + builtins + environment + effects |

One request asks for one answer: two views, a view beside another analysis (`--varflow`,
`--inputs`, ...), or a modifier the selected view does not read (`--kind` on `exits`,
`--in-loops` on `boundary`, `--depth` without `--transitive`) exits 2 naming what the answer
reads. Other path-read options (`--limit`, `--files`, `--head`/`--tail`, ...) are not element
options and exit 2 too; use inclusive `--range` to select lines. A directory refuses every
element view. These validation errors exit 2 before producing findings.

`--view effects` reports ordinary classified sites. Choose one exclusive mode with
`--view effects --in-loops` (loop groups) or `--view effects --state` (persistent/shared
writes). `--transitive` applies only to ordinary effects; its `--depth` accepts integers 1–5,
default 2. Loop structure depth is `--nesting-depth`, positive, default 3, with no
additional cap. Effects require one code file; URI targets, `@file` lists and `--stdin`
batches are unsupported. Early discovery/special modes (including `--show-ast`,
`--capabilities`, `--explain-file`, `--decorator-stats` and `--languages`) cannot preempt
effects. Frontmatter `--validate-schema` and specialized nginx views (`--extract`,
`--check-acl`, `--validate-nginx-acme`, `--global-audit`, `--check-conflicts`,
`--cpanel-certs`, `--diagnose`) are also exclusive with element views.

Bare `--view flow` includes all recognized skeleton records. Select with `--kind if`,
`--kind loop` or `--kind try`, or repeat `--kind` to combine them:
`--view flow --kind if --kind loop`. Unions retain source order and remove duplicate
selections. `if` includes switch/case; `try` includes handlers/finally. Unknown kinds are
rejected before analysis. File-only flow inspects the full source region; file hierarchy and
Markdown headings remain `--outline`.

```bash
reveal app.py --outline
reveal app.py process_order --view flow
reveal app.py process_order --view flow --kind if --kind loop --nesting-depth 8
reveal guide.md Setup --outline
```

Old spellings still run until the cut and print one note naming their replacement: the
element flags `--boundary`, `--effects`, `--flow[=SEL]` and `--exits` (replaced by
`--view ...`), `--sideeffects`, `--fanout`, `--statewrites`, `--ifmap`, `--loopmap`,
`--catchmap`, `--returns`, `--flowto` and the code-element `--outline`; `--deps`,
`--mutations`/`--writes` and `--calls` (replaced by `--inputs`, `--outputs`, `--callsites`).
On these old flags `--depth` keeps its old meaning (the structural depth, or the transitive
depth, 1–5 as on `--view`: a value outside it exits 2). JSON `meta.flag` names the view or operation on either spelling
(`flow`, `exits`, `boundary`, `effects` with `meta.mode` `ordinary`, `loops` or `state`, `inputs`, ...); an old spelling adds a
`retired_spelling` diagnostic in `meta.warnings`. `meta.flow_selectors` records the
normalized `--kind` union (empty for bare flow). `--view exits` reports static sites and
recorded gates rather than the retired `--flowto` reachability verdict.

Structural navigation lists recognized nodes, not every exit expression. Inspect
`--view exits` for candidate exit sites. Implicit tail returns are inferred only for the
resolved scope, not for nested callable scopes in a literal source region. Named
callables and source regions therefore need not record the same implicit tails.
JSON carries these standing rules (`meta.structure_scope`, `meta.exit_scope`); text names the
selected scope and points at them with one `Rules: --format json (...)` line. The supported
output formats for flow/exits are text and JSON; other formats are rejected.

For `--view flow` (including `--kind`) and `--view effects --in-loops`,
`--nesting-depth` limits logical nesting (default 3). A TRY and its CATCH/EXCEPT/FINALLY
alternatives remain peers, including at the depth boundary. Text names the requested
depth; JSON carries `meta.depth` and `meta.depth_limited`. When the limit leaves structural
regions overlapping the selected range unexpanded, text and `meta.warnings` disclose
that boundary. Other analyses, such as fanout effect collection, may inspect those regions. This does not claim a count of omitted records or matching loops/branches;
increase `--nesting-depth` to expand those structures. Range filtering alone is not a depth cut.

An explicit `--nesting-depth` must be a positive integer; zero and negative values are
rejected instead of becoming a default or an empty answer. This does not change file,
directory or Markdown `--depth`.

Code-analysis navigation flags reject languages explicitly classified as structure-only
(for example, SQL), data and document formats that hold no functions (Markdown, JSON, YAML,
TOML, GraphQL, Protobuf, INI, CSV, XML, office files), and files tree-sitter cannot parse,
rather than reporting no findings as though analysis completed. Use `reveal FILE` for their
supported structure view. Line navigation with `--scope` or `--around` remains available where
the analyzer supports it. A code language without conformance fixtures (Elixir) or read with a
fallback grammar answers every view with one warning naming that tier.

A target that matches nothing is an invalid request, not an empty answer: a variable that
`--varflow`, `--keys`, `--narrow` or `--cross-calls` finds no read or write of in the selected
lines, a line range or `--range`/`--callsites` range past the end of the file, a reversed line
range, `--callsites` with a value that is not a range, an empty variable name and a negative
`--around`. A variable that occurs with no events of the view's kind (no key access) is a
genuine zero; `--narrow` on an unannotated variable answers with its decline as a JSON warning.
Element views render `text` and `json`; `--format grep` or `typed` is rejected.

These requests exit 2 with a diagnostic on stderr, including under `--format json`; they do not
print an empty findings answer. Registered MCP navigation reports the rejection as an error. A
supported analysis with no findings still succeeds.

---

## The Highest-Value Flags

If you only learn three, learn these:

```bash
reveal app.py process_order --view boundary
# → INPUTS (undefined reads), ENVIRONMENT (PHP superglobals), EFFECTS (db/http/log/file/...)
# Best single-flag summary of what a code range receives and what it does.

reveal app.py process_order --view effects
# → flat list of classified external calls, in line order
# Useful for blast-radius assessment and retry-safety review.

reveal app.py :123 --around
# → ±20 lines around line 123 with a marker on the target
# Useful when a stack trace or grep result hands you a line number.
```

---

## Refactor Pre-Flight Workflow

Planning to extract a block of lines into a new function?

```bash
reveal file.py :120-340 --inputs        # → candidate parameters; review bindings
reveal file.py :120-340 --outputs   # → candidate return values
reveal file.py :120-340 --view exits       # → spot unexpected early exits
reveal file.py :120-340 --view boundary    # → inputs + environment + classified effects
```

---

## Legacy / Flat-File Triage Workflow (PHP, procedural)

Useful for WordPress, CodeIgniter, or any large flat PHP file.

```bash
reveal legacy_handler.php :878-2130 --view flow --kind if        # control-flow skeleton
reveal legacy_handler.php :120-340 --view boundary      # what does this slice consume + emit?
reveal legacy_handler.php :120-340 --view effects   # which DB / curl / session calls fire?
reveal legacy_handler.php :120-340 --view exits       # exits + reported syntactic conditions
reveal legacy_handler.php :120-340 --varflow $userId  # where does $userId flow?
```

`--view boundary` on PHP additionally surfaces superglobals (`$_GET`, `$_POST`, `$_SESSION`, etc.) in a separate ENVIRONMENT section.

---

## Exit Scope and Ownership

`--view exits` reports static candidate sites with recorded syntactic gate chains.
When the resolved target is a qualified callable, separately owned nested function,
method and lambda bodies are excluded. Expressions evaluated while forming a nested
declaration remain where qualified: Python decorators/defaults, JavaScript computed
method names, and C++/Swift capture initializers can belong to the enclosing execution.
For the selected callable, invocation-time parameter defaults are retained where
qualified; its own Python declaration-time defaults and JavaScript computed method name
are outside that execution scope. These are static sites, not a reachability proof.

A source range or named class/aggregate is instead a source-scope inventory that may
contain sites from multiple callable owners. Existing element resolution decides the
scope; adding a colon does not itself establish callable ownership. Implicit-tail
inference still uses the resolved scope, so a literal region is not interchangeable
with named-callable analysis.

Text names this scope, and JSON includes `meta.exit_scope.mode`, its selection `reason`
and counting `rule`. Unqualified resolved scopes remain inventories with an explicit
scope warning. Ruby dynamic block binding, Kotlin inline/label semantics and other
unqualified execution edges retain potential sites with `ownership_unresolved`
diagnostics. Python generator bodies, assignment targets, filters and later iterables likewise retain
potential sites with a deferred-execution warning, as do Rust async-block sites; the leftmost iterable is evaluated
when the generator is formed, and eager list comprehensions keep their existing scope.
Each diagnostic identifies actual recorded sites by kind, text, line and
parser-source byte span (zero-based, half-open offsets in parser input, not a promise
about on-disk offsets after newline normalization); it does not count unseen findings. Empty ambiguous blocks do
not create unknown-site claims. Review these sites before attributing them to one function.

Dart's existing resolver supplies a function body separately from its signature and
constructor initializer context. Named Dart results disclose that limitation; use a
source-region inventory to inspect syntax outside the resolved body. These ownership
rules do not establish compiler validity, call binding or complete language recall.

## MCP Equivalent

Primary nav operations are exposed via the MCP server's `reveal_nav` tool:

```python
reveal_nav(path="app.py", element="process_order", flag="boundary")
reveal_nav(path="legacy.php", element=":120-340", flag="effects")
```

For `flag="effects"`, keyword-only `mode` selects `ordinary` (default), `loops`,
or `state`. `transitive=True` follows ordinary effects into project-local callees;
optional `depth` accepts integers 1–5 there (default 2), or positive structural
nesting depth for loops (default 3). Other flags reject nondefault controls.
`flag_value` does not encode effects modifiers. The first four positional arguments
and text return remain unchanged; line-reference elements continue to work.

Failure to open the requested navigation source or resolve a selected function
or method produces an authored MCP tool error (`is_error=true`). Complete empty
answers and warning-bearing results retain their existing successful behavior.
Invalid effects controls, types and directory requests also produce tool errors.
Unsupported-analyzer and other legacy exits retain their captured-text behavior;
inspect diagnostics rather than treating a successful tool marker as proof of
complete analysis.

```python
reveal_nav("app.py", "process_order", "effects", transitive=True, depth=2)
reveal_nav("app.py", "process_batch", "effects", mode="loops", depth=8)
reveal_nav("app.py", "process_order", "effects", mode="state")
```

See [`MCP_SETUP.md`](MCP_SETUP.md) for setup and the full tool list.

---

## Disambiguation: `--callsites` vs `calls://`

- `--callsites` is **sub-element scope**: list call sites within a line range of one file.
- `calls://` is **project scope**: cross-file call graph (who calls / what does it call across the project).

Different scope, different question.

---

## Known Limitations

- `--view exits` reports static syntactic gates; enclosing branch/handler conditions do not describe every preceding exit, loop iteration or runtime exception. Check source before making reachability claims.
- `--inputs` respects supported closure/with/except/catch/comprehension/range binders and preserves free captures and default-expression reads. Registered Python builtins remain visible as BUILTIN/JSON `kind: builtin`, separate from `--view boundary` INPUTS. Explicit lexical shadows stay candidate inputs. Dynamic names and unsupported binding shapes still require source review.
- `--view effects --state` detects Python/JS module-bound container writes and explicit Python/PHP `global` assignments; explicit Python `nonlocal` writes are separate. PHP also recognizes `$GLOBALS`. Local/parameter containers stay local. Implicit enclosing-container captures without `nonlocal`, PHP reference captures, aliases, dynamic names, and imported-object resolution remain outside coverage. An empty result does not establish that shared state is untouched.
- `--view boundary` includes assignment writes in EFFECTS (JSON `via: assignment`). Under `--transitive`, call effects follow callees but assignment writes remain entry-function only; JSON `meta.warnings` carries this limit and text points at it with one `Rules:` line. Inputs/builtins/environment also remain entry-function scoped.

- `--view effects --transitive` and `--view boundary --transitive` identify each callee effect with a JSON `file` alongside `line` and a text `[file:line]` suffix. Callee paths follow the target's absolute or relative spelling. Entry-function effects keep their existing request-file context without a new `file` field. These modes retain required directory enumeration failures through collection and text/JSON warnings. Surviving effects remain visible; empty results describe the analyzed portion when discovery failed. Directory counts identify failed directories, with unknown missing file populations. Existing file-analysis notes remain separate, and CLI exits retain their current policy.
- PHP `foreach` loop variables (`$k`, `$v` in `foreach($arr as $k => $v)`) are tracked but classified as READ rather than WRITE.
- Variable tracking is name-based; same-named variables in different scopes within a flat file may merge.
- `--scope` and `--around` take a single `:LINE`. A range (`:100-110`) exits 2 with an error naming the line it would have used; to print a range, drop `--around` (`reveal app.py :100-110`).
- Named-argument labels (`json` in Python `f(json=x)`, C# / Dart / Swift `f(json: x)`, Kotlin / Scala `f(json = x)`) are not reads: `--inputs`, `--view boundary` and `--varflow` report only the value `x`.

---

## See Also

- [`AGENT_HELP.md`](../AGENT_HELP.md) — full reference with output samples for every flag
- [`WHAT_IS_REVEAL_GOOD_FOR.md`](WHAT_IS_REVEAL_GOOD_FOR.md) §5 — narrative use cases for nav flags
