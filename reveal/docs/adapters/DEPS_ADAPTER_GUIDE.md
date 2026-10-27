---
title: deps:// Adapter Guide (retired)
category: guide
---

# deps:// Adapter Guide (retired)

`deps://` and `reveal deps` are retired: the dashboard was always three views of one
`imports://` graph build (the package table, `?circular` and `?unused`), and each view is now
asked for directly. The import graph, its views and their limits are documented once, in
[IMPORTS_ADAPTER_GUIDE.md](IMPORTS_ADAPTER_GUIDE.md).

| Retired | Use instead |
|---------|-------------|
| `reveal deps src` (package table) | `reveal 'imports://src?external&scope=path'` (or `reveal imports src --external`) |
| `reveal deps src` (cycles) / `--fail-on findings` | `reveal imports src --circular --fail-on findings` |
| `reveal deps src` (unused imports) | `reveal 'imports://src?unused'` (or `reveal imports src --unused`) |
| `reveal 'deps://src?no_unused=true'` / `?no_circular=true` | leave that view out of the set above |

`&scope=path` gives the package numbers the dashboard printed, counted over the requested
path. The circular verdict counts load-time edges only, as before; `imports://` adds
`&lazy=include` to count function-level imports too.

## Until the cut release

`reveal deps` and `deps://` still answer as before, with one
`note: reveal deps is deprecated; use ...` line on stderr. At the cut the same text becomes an
exit-2 error.

- **Parameters:** `top` (text rows per section, default `10`; `0` shows none; JSON always
  returns all), `no_unused`, `no_circular`, `summary_only` (primary JSON only: replaces
  `base.files` with `total_files`/`total_imports`). `--verbose` lifts the text cap.
- **Exits:** the default findings policy is `--fail-on none`, so a completed analysis exits 0
  even when cycles or unused imports are present. `--fail-on findings` exits 1 when there are
  any. Invalid requests exit 2; incomplete or failed required analysis or output exits 3.
- **JSON (`deps_scan`):** `base` is the raw `imports://` file map. `circular` carries `cycles`,
  `cycle_paths`, `count` and `edge_rule`. `unused` is a flat list of the `imports://` import
  records that are unused: `file`, `line`, `module`, `names` (every name the statement
  imports) and `unused_names` (the ones actually unused; use this field, since `names` is
  empty for a plain `import X`), plus `type`, `classification`, `resolved`, `alias` and
  `is_relative`. `skipped` lists the checks turned off with `no_circular`/`no_unused`, so an
  empty `circular`/`unused` there means "not checked", not "clean". `analysis.complete`,
  `analysis.components` (each with its `completeness`) and `analysis.findings` (full counts,
  before text caps or summary projection) state whether every requested view completed.
- **Text:** a Summary line (files, imports, unresolved and stdlib package counts), a Health
  line with the cycle `Rule:`, an "Unresolved packages (third-party or unresolved-local)" usage
  table, the cycles, the unused imports and a "Top importers" ranking.

## See Also

- `reveal help://imports` - the replacement
- `reveal help://schemas/deps` - the retired result type's JSON schema
- [IMPORTS_ADAPTER_GUIDE.md](IMPORTS_ADAPTER_GUIDE.md)
