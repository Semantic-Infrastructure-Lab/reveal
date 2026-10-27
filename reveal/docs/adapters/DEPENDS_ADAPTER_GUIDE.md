---
title: depends:// Adapter Guide (retired)
category: guide
---

# depends:// Adapter Guide (retired)

`depends://` is retired: the reverse import graph is the `imports://` engine's own build, and
`imports://` answers it directly with `?importers`, listing each importer with its import line,
scope and cascade stage. The graph, its rules and its limits are documented once, in
[IMPORTS_ADAPTER_GUIDE.md](IMPORTS_ADAPTER_GUIDE.md).

| Retired | Use instead |
|---------|-------------|
| `reveal depends://src/utils.py` | `reveal 'imports://src/utils.py?importers'` or `reveal 'imports://src?importers=utils.py'` |
| `reveal depends://src` | `reveal 'imports://src?importers'` (each module with its importers) |
| `reveal 'depends://src?top=10'` | `reveal 'imports://src?rank=fan-in&top=10'` |
| `reveal 'depends://src?format=dot'` | no DOT equivalent; `imports://` answers text and JSON |

`depends://` counts function-level (lazy) imports and takes no `&lazy`; `imports://` counts
them by default too and adds `&lazy=exclude` for the load-time view.

## Until the cut release

`depends://` still answers as before, with one `note: depends:// is deprecated; use ...` line
on stderr. At the cut the same text becomes an exit-2 error. It exits 0 also on a partial
answer, where `imports://` exits 3. The graph uses depends' own scan root, 5,000-file cap and,
for a file target, its own extension family.

- **Parameters:** `top` (caps the module or dependent list), `root` (override the scan root),
  `verbose` (directory targets: list each module's importers under its row; a file target
  already prints one row per importing statement) and `format`. Only `?format=dot` changes the
  output, and only for a directory target; for JSON use the CLI `--format json`. Any other
  `format` value, and `dot` on a file target, falls back to text without a warning.
- **File target (`module_dependents`):** text prints a `Rule:` line, then
  `N file(s) import this module:` (`N file(s) import this module (showing K):` under `?top=`,
  followed by a `⚠ Truncated dependents` line), one `file:line  ← names` row per importing
  statement, and `ℹ Import-graph analysis — dynamic imports not followed.` JSON carries
  `target`, `dependents` (each `file`, `line`, `module`, `names`, `type`, `is_relative`,
  `alias`), `count`, `edge_rule`, `metadata`, `_meta` (`analysis_kind`, `confidence`,
  `known_limits`) and `undercount_possible`.
- **Directory target (`dependency_summary`):** text prints a `Rule:` line, then
  `N module(s) imported internally (M total import edges)` (capped:
  `Top N of M module(s) imported internally (K import edges shown)`), one bar row per module,
  a `Tip:` line, the `ℹ` line and, when capped, `⚠ Truncated modules: showing N of M`. JSON
  carries `modules` (each `module`, `dependent_count`, `dependents`), `total_modules`,
  `edge_rule`, `metadata`, `_meta` and `undercount_possible`, plus an internal `_format` field.
- **Disclosure:** `metadata.scan_capped` means the scan hit the 5,000-file cap;
  `metadata.root_inferred` means no project marker was found, so only the target's own
  directory was scanned. Directory loss during the scan is reported in `meta.warnings`, with
  `_meta.confidence` `reduced` and `undercount_possible` true.

## See Also

- `reveal help://imports` - the replacement
- `reveal help://schemas/depends` - the retired result types' JSON schema
- [IMPORTS_ADAPTER_GUIDE.md](IMPORTS_ADAPTER_GUIDE.md)
