---
title: contracts:// Adapter Guide
category: guide
---

# contracts:// Adapter Guide

`contracts://` finds contracts and architectural seams across a codebase: the
places one part of the system agrees to a shape with another. It answers
"what are the extension points and boundaries here?" across eleven languages,
each with its own native contract mechanism.

## Quick Start

```bash
reveal contracts ./src
reveal contracts .
reveal contracts . --format json
reveal contracts . --abstract-only
reveal contracts . --no-implementations
reveal contracts . --impls 0
reveal contracts . --also-json contracts.json

reveal 'contracts://src'
reveal 'contracts://.?abstract_only=true'
reveal 'contracts://.?implementations=false'
```

## Query Parameters

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `abstract_only` | `true`, `false` (default) | Show only ABCs/Protocols/interfaces/traits — skip TypedDicts, dataclasses, path-heuristic bases. |
| `implementations` | `true` (default), `false` | Show which classes/types implement each contract. |
| `impls` | whole number >= 0, default `5` | Implementers listed per contract in text output; `0` lists all. JSON always carries every implementer. |

Both spellings use the same declarations. `--abstract-only` sets
`abstract_only=true`; `--no-implementations` sets `implementations=false`.
`--impls N` matches `?impls=N`, including `3.0` as the whole number 3.
Negative values, fractions, scientific notation and boolean values for `impls`
are rejected. Boolean query controls accept `true`/`false`, `yes`/`no` and
`1`/`0`; bare presence means true, and other spellings are rejected.

Omitting the resource defaults to the current directory in both forms. URI
resources decode percent escapes once when the literal path does not exist;
an existing literal percent path takes precedence. Plus signs stay literal.
Encode URI filename delimiters such as `?` as `%3F`; direct CLI paths accept
the filename as an argument.

## Per-Language Contract Shapes

| Language | Contract form | Implementers |
|----------|---------------|--------------|
| Python | `ABC`/`ABCMeta`, `Protocol`, `TypedDict`, `@dataclass`, Pydantic `BaseModel` | Declared via inheritance |
| TypeScript/JS, Java, C#, PHP, Swift, Kotlin | `interface`, abstract classes, type aliases | Declared via `extends`/`implements` |
| Ruby | `module` (mixin) | Classes that `include`/`extend`/subclass it |
| Go | `interface` | *Computed structurally* — a struct implements an interface when its method set is a superset (embedded interfaces resolved transitively); marker/empty interfaces are excluded from matching since everything trivially satisfies them |
| Rust | `trait` | Declared via `impl Trait for Type` |
| C++ | Abstract class (≥1 pure virtual method) | Declared via inheritance |

A repo with more than one supported language present returns results nested
under `by_language` instead of the flat `abcs`/`protocols`/... shape — the
flat shape is preserved exactly for the common single-language case.

## Reading The Output

`total_contracts` retains each scanner's contract count. For Rust it counts local
traits, so implementing types can appear with `total_contracts=0` when the trait
is declared elsewhere. Text uses the actual returned groups to decide whether
the inventory is empty, preserving those implementation rows and the count.

`abcs`/`protocols`/`typeddicts`/`dataclasses`/`basemodels`/`path_heuristic`
are Python's categories; non-Python scanners reuse these same field names so
render/JSON consumers don't need per-language branching (see the per-scanner
docstrings in `reveal/adapters/contracts.py` for exactly which field each
language's contract/implementer pair maps to).

Each entry carries `implementations` (when `implementations=true`) — the
concrete types satisfying that contract, capped at 5 in text output (`?impls=N` widens it, `?impls=0` lists all) with a
"… and N more" tail.

`path_heuristic` (Python only) catches classes in files named like
`base.py`/`interface.py`/`protocol.py`/etc. that have abstract-looking
methods but no `ABC`/`Protocol` base — a heuristic net for contracts that
don't use the formal markers.

## Analysis Evidence

Recovered parses retain their extracted contracts and remain analyzed inputs.
When recovery occurs, `recovered_files` and a `parse_recovered` warning identify
those files. Failed supported inputs reduce `coverage.analyzed_files` once per
distinct file; warnings and `meta.errors` retain the consuming scanner's exact
failure cause. A separate shared analysis failure does not invalidate a successful
native contract scan. Empty and unsupported inventories remain nonfatal.

Direct `reveal contracts` and `contracts://` requests exit 0 for complete work,
2 for invalid parameters or missing resources, and 3 for required analysis or
requested output that failed or remained incomplete. Recovery and failed
supported inputs therefore exit 3 while retaining surviving contracts and
diagnostics. Empty results and disclosed unsupported-language coverage remain
complete. `--fail-on none` is supported and is the default; it does not suppress
required failures. Contracts has no findings gate.

Text output can also write the complete result with `--also-json PATH`.
Primary JSON output keeps that option as a no-op. Text implementer caps never
shrink the JSON arrays. Legacy stdin and mixed URI batches retain their existing
exit policy and reject `--fail-on` until separately qualified.

## Good Review Questions

- Are there more implementers than expected for a contract meant to be
  narrow?
- Is a contract with zero implementers dead, or about to be used?
- For Go, does the structural-match set line up with what the team actually
  intends to implement (structural typing can produce accidental matches)?
- Does a `path_heuristic` hit indicate a contract that should be formalized
  with `ABC`/`Protocol`?

## Limits

- Static analysis only — dynamically registered contracts (e.g. duck-typed
  protocols enforced only at runtime) are not detected.
- Go's structural matching is best-effort: it compares method-name sets, not
  full signatures.
- Confidence is `medium` — treat results as an inventory to review, not a
  compliance-grade contract registry.

## See Also

- `reveal help://schemas/contracts` - JSON schema
- `reveal 'ast://<path>'` - full structure for any contract's implementers
- `reveal 'calls://<dir>/?target=<method>'` - who calls into a specific implementation
