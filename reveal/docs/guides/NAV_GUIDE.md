---
title: Deep-Dive Code Navigation (Nav Flags)
category: guide
help_topic: nav
help_description: "Deep-dive code navigation flags (--outline, --boundary, --varflow, --sideeffects)"
help_category: feature_guides
---
# Deep-Dive Code Navigation (Nav Flags)

**One-line summary:** Pinpoint inspection inside a function or line range — control flow, data flow, side effects, and refactor pre-flight, all without reading the file top-to-bottom.

Nav flags work on Python, PHP, and the other tree-sitter languages (`reveal --languages`). Most flags accept `:LINE-RANGE` and work on flat procedural files (no function wrapper required).

For the full reference with output samples, see [`AGENT_HELP.md`](../AGENT_HELP.md) — search for "Navigate inside a function".

---

## At a Glance

`--inputs`, `--outputs` and `--callsites` are the current names in both the CLI
and MCP `reveal_nav` (`inputs`, `outputs`, `callsites`). The retired spellings
`--deps`, `--mutations`/`--writes` and `--calls` still run and report their
replacements until the cut. JSON `meta.flag` uses the current name; an old spelling
adds a `retired_spelling` diagnostic in `meta.warnings`.

| Flag | Question it answers |
|------|---------------------|
| `--outline` | What's the shape of this function? |
| `--scope :LINE` | What scope is this line inside, and what gates it (JSON `condition` field per ancestor)? |
| `--around N` | What's near line N? (verbatim ±N lines) |
| `--ifmap` | What conditional branches exist? |
| `--catchmap` | What try/except structure exists? |
| `--exits` | Where can this range exit (return/raise/break/die)? |
| `--flowto` | Can control reach the end of this range? |
| `--callsites` | What does this call? (sub-element scope) |
| `--varflow VAR` | Where is VAR read, written, or tested? |
| `--varflow VAR --cross-calls` | Same, but follows VAR across function call boundaries |
| `--narrow VAR` | How does VAR's type narrow through control-flow branches? |
| `--inputs` | Candidate inputs (undefined reads; review bindings) |
| `--outputs` | What does this range write that's read later? |
| `--sideeffects` | What DB/HTTP/FS/log/sleep calls fire here? |
| `--loopmap` | What loops exist, and how are they nested? |
| `--fanout` | Which loops make DB/HTTP/FS/log calls inside them? (N+1 / per-item fan-out review) |
| `--statewrites` | Detected global/nonlocal/field/env/session/cache/db/file writes |
| `--keys VAR` | Which keys/properties of VAR are read, written, or tested (dict/object/array shape)? |
| `--returns` | Exit sites with enclosing syntactic conditions (not a reachability proof) |
| `--boundary` | One-shot contract: inputs + builtins + environment + effects |

For code-element `--outline`, `--ifmap`, `--catchmap`, `--loopmap` and `--fanout`,
`--depth` limits logical nesting (default 3). A TRY and its CATCH/EXCEPT/FINALLY
alternatives remain peers, including at the depth boundary. Text names the requested
depth; JSON carries `meta.depth` and `meta.depth_limited`. When the limit leaves structural
regions overlapping the selected range unexpanded, text and `meta.warnings` disclose
that boundary. Other analyses, such as fanout effect collection, may inspect those regions. This does not claim a count of omitted records or matching loops/branches;
increase `--depth` to expand those structures. Range filtering alone is not a depth cut.

---

## The Highest-Value Flags

If you only learn three, learn these:

```bash
reveal app.py process_order --boundary
# → INPUTS (undefined reads), ENVIRONMENT (PHP superglobals), EFFECTS (db/http/log/file/...)
# Best single-flag summary of what a code range receives and what it does.

reveal app.py process_order --sideeffects
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
reveal file.py :120-340 --exits       # → spot unexpected early exits
reveal file.py :120-340 --boundary    # → inputs + environment + classified effects
```

---

## Legacy / Flat-File Triage Workflow (PHP, procedural)

Useful for WordPress, CodeIgniter, or any large flat PHP file.

```bash
reveal legacy_handler.php :878-2130 --ifmap        # control-flow skeleton
reveal legacy_handler.php :120-340 --boundary      # what does this slice consume + emit?
reveal legacy_handler.php :120-340 --sideeffects   # which DB / curl / session calls fire?
reveal legacy_handler.php :120-340 --returns       # exits + reported syntactic conditions
reveal legacy_handler.php :120-340 --varflow $userId  # where does $userId flow?
```

`--boundary` on PHP additionally surfaces superglobals (`$_GET`, `$_POST`, `$_SESSION`, etc.) in a separate ENVIRONMENT section.

---

## Exit Scope and Ownership

`--exits`, `--returns` and the legacy `--flowto` share one execution-ownership rule.
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
reveal_nav(path="legacy.php", element=":120-340", flag="sideeffects")
```

The typed tool has no `transitive` argument. Passing `--transitive` in
`flag_value` does not enable the CLI's transitive walk.

See [`MCP_SETUP.md`](MCP_SETUP.md) for setup and the full tool list.

---

## Disambiguation: `--callsites` vs `calls://`

- `--callsites` is **sub-element scope**: list call sites within a line range of one file.
- `calls://` is **project scope**: cross-file call graph (who calls / what does it call across the project).

Different scope, different question.

---

## Known Limitations

- `--returns` reports static syntactic gates; enclosing branch/handler conditions do not describe every preceding exit, loop iteration or runtime exception. Check source before making reachability claims.
- `--inputs` respects supported closure/with/except/catch/comprehension/range binders and preserves free captures and default-expression reads. Registered Python builtins remain visible as BUILTIN/JSON `kind: builtin`, separate from `--boundary` INPUTS. Explicit lexical shadows stay candidate inputs. Dynamic names and unsupported binding shapes still require source review.
- `--statewrites` detects Python/JS module-bound container writes and explicit Python/PHP `global` assignments; explicit Python `nonlocal` writes are separate. PHP also recognizes `$GLOBALS`. Local/parameter containers stay local. Implicit enclosing-container captures without `nonlocal`, PHP reference captures, aliases, dynamic names, and imported-object resolution remain outside coverage. An empty result does not establish that shared state is untouched.
- `--boundary` includes assignment writes in EFFECTS (JSON `via: assignment`). Under `--transitive`, call effects follow callees but assignment writes remain entry-function only; text and JSON warnings disclose this limit. Inputs/builtins/environment also remain entry-function scoped.

- `--sideeffects --transitive` and `--boundary --transitive` retain required directory enumeration failures through collection and text/JSON warnings. Surviving effects remain visible; empty results describe the analyzed portion when discovery failed. Directory counts identify failed directories, with unknown missing file populations. Existing file-analysis notes remain separate, and CLI exits retain their current policy.
- PHP `foreach` loop variables (`$k`, `$v` in `foreach($arr as $k => $v)`) are tracked but classified as READ rather than WRITE.
- Variable tracking is name-based; same-named variables in different scopes within a flat file may merge.
- `--scope` and `--around` take a single `:LINE`. A range (`:100-110`) exits 2 with an error naming the line it would have used; to print a range, drop `--around` (`reveal app.py :100-110`).
- Named-argument labels (`json` in Python `f(json=x)`, C# / Dart / Swift `f(json: x)`, Kotlin / Scala `f(json = x)`) are not reads: `--inputs`, `--boundary` and `--varflow` report only the value `x`.

---

## See Also

- [`AGENT_HELP.md`](../AGENT_HELP.md) — full reference with output samples for every flag
- [`WHAT_IS_REVEAL_GOOD_FOR.md`](WHAT_IS_REVEAL_GOOD_FOR.md) §5 — narrative use cases for nav flags
