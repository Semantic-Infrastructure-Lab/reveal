---
title: classify:// Adapter Guide
category: guide
---

# classify:// Adapter Guide

`classify://` tags every analyzable file under a directory with its
provenance (`first_party`, `test`, `vendor`, `minified`) — one row per
file, over the **full, unranked** population. This is the full-population
counterpart to `overview://`'s/`hotspots://`'s/`pack://`'s `provenance`
field, which only tags whatever ranked/capped subset each of those
adapters already selects for its own purpose.

## Quick Start

```bash
reveal 'classify://src'
reveal 'classify://src' --format json
```

## Query Parameters

`classify://` walks the full target directory (respecting `REVEAL_IGNORE`/
`config.yaml`'s `ignore:` and the same well-known skip directories as
`stats://`), skipping what git ignores by default. That is git's own answer
(`git ls-files --ignored`), so a tracked file is never skipped even when a
`.gitignore` pattern matches it.

- `respect_gitignore` (boolean, default `true`) — set to `false` (or pass
  `--no-gitignore` on the CLI) to include gitignored files:
  `classify://src?respect_gitignore=false`

## Reading The Output

`files` is one entry per analyzable file: `{"file": <relative path>,
"provenance": <tag>}`. `summary.by_provenance` is a count per tag —
`summary.by_provenance.first_party / summary.total` answers "what
fraction of this codebase is first-party," the question this adapter
exists to make computable independent of any ranking.

These counts describe discovered files with a registered analyzer. Unsupported
extensions appear separately under `summary.excluded`. If required directory
enumeration fails, text and JSON disclose the directory/cause; the missing file
population is unknown, so the observed fractions do not describe the complete
target. Clean results keep the legacy envelope; known loss adds warning metadata.
Classify retains its legacy exit behavior, so exit 0 alone does not establish a
complete walk.

Classification uses directory-name and filename conventions, with limited vendor
banner and locale-file heuristics. It is not general generated-code detection;
use `reveal check` for additional content checks.

## Good Review Questions

- What fraction of this target is `first_party` vs. noise (`test` +
  `vendor` + `minified`)? A low fraction is itself a due-diligence signal.
- Does a directory you expected to be vendored actually show as
  `first_party` (missing from `VENDOR_DIR_NAMES`), or vice versa?

## Limits

- Path conventions and limited vendor heuristics do not establish how a file was
  generated or whether it is maintained locally.
- Same walker and skip-directory rules as `stats://`; a file `stats://`
  can't analyze (no registered analyzer) is likewise absent here.

## See Also

- `reveal help://schemas/classify` - JSON schema
- `reveal 'hotspots://<dir>'` - ranked complexity hotspots, each tagged with provenance
- `reveal 'overview://<dir>'` - directory summary, ranked sections tagged with provenance
