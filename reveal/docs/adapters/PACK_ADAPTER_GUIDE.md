---
title: pack:// Adapter Guide
category: guide
---

# pack:// Adapter Guide

Pointer stub — the canonical guide is the "reveal pack" section of
[Subcommands Guide](../guides/SUBCOMMANDS_GUIDE.md) (`reveal help://pack`),
which now also documents the `pack://` URI form. This file
exists only to satisfy V024 (every registered adapter must have a
`docs/adapters/` guide file); it intentionally does not duplicate content
(one home per fact).

All query params, for V027 coherence (full docs in the guide linked above):

```
reveal 'pack://src?budget=4000&focus=auth&exclude=spec/*,vendor/*&since=main&content=true&architecture=true&detail=full'
```

`detail=full` — per-file token/line-count breakdown (JSON `"verbose": true`), same as the CLI `--detail full`. It replaced `verbose` and the global `--verbose`, which still work with a note.
