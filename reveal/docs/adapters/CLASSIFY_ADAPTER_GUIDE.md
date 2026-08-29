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

None. `classify://` always walks the full target directory (respecting
`.gitignore`, `REVEAL_IGNORE`/`config.yaml`'s `ignore:`, and the same
well-known skip directories as `stats://`).

## Reading The Output

`files` is one entry per analyzable file: `{"file": <relative path>,
"provenance": <tag>}`. `summary.by_provenance` is a count per tag —
`summary.by_provenance.first_party / summary.total` answers "what
fraction of this codebase is first-party," the question this adapter
exists to make computable independent of any ranking.

Classification is path-only (directory-name and filename conventions) —
no file content is read, so a generated-but-not-vendored file (detected
via content markers in `reveal check`) is not distinguished here.

## Good Review Questions

- What fraction of this target is `first_party` vs. noise (`test` +
  `vendor` + `minified`)? A low fraction is itself a due-diligence signal.
- Does a directory you expected to be vendored actually show as
  `first_party` (missing from `VENDOR_DIR_NAMES`), or vice versa?

## Limits

- Path-only classification — no content-based generated-file detection
  (see `reveal check`'s `_is_generated_file` for that, at higher cost).
- Same walker and skip-directory rules as `stats://`; a file `stats://`
  can't analyze (no registered analyzer) is likewise absent here.

## See Also

- `reveal help://schemas/classify` - JSON schema
- `reveal 'hotspots://<dir>'` - ranked complexity hotspots, each tagged with provenance
- `reveal 'overview://<dir>'` - directory summary, ranked sections tagged with provenance
