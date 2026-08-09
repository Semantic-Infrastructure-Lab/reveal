---
title: "Output & Diagnostics Guide"
type: guide
help_topic: output-diagnostics
help_description: "The four ways to get extra context out of a reveal call: --format, meta.warnings/errors/confidence, --provenance, --perf — what each is for and when to reach for it"
help_category: feature_guides
help_token_estimate: "~1,100"
---

# Output & Diagnostics Guide

Reveal has four separate mechanisms for "extra information about a call,"
each with a different activation model. This guide exists because they're
easy to conflate — they answer different questions and none of them is a
superset of the others.

## Quick Reference

| Mechanism | Answers | Activation | Where it lives |
|---|---|---|---|
| `--format {text,json,typed,grep}` | What shape should the primary result be? | Always specified (defaults to `text`) | The command's own stdout |
| `meta.warnings` / `meta.errors` / `meta.confidence` | Can I trust this result? | **Always on** — folded into JSON output automatically when non-empty | Embedded inside the adapter's own result dict |
| `--provenance` | How do I reproduce/cite this exact result? | Opt-in flag, **JSON output only** | Embedded `execution` block in the result dict |
| `--perf` | Was this call itself slow? | Opt-in flag (or `REVEAL_PERF_LOG=1` for every call) | **External file** — not part of the command's own output at all |

## When to reach for each

**`--format json`** — when a downstream script/agent needs to parse the
result, not just read it. Text stays the better default for anything a human
reads directly (`overview`/`architecture`/`hotspots`/`ast`/`calls`/`stats`/
`git` ownership all have well-organized text renderers). JSON earns its keep
specifically where text doesn't expose structure you need — e.g. `check`'s
per-rule-code tally isn't in its text summary, only in `detections[]`.

**The `meta` trust envelope** — read this before treating a clean/empty
result as "nothing found." A composite adapter (`overview`, `architecture`,
`hotspots`, `deps` — anything built from several sub-scans via
`ResourceAdapter.compose()`) attributes a failed sub-scan to `meta.errors`
instead of silently rendering an empty section (BACK-984). `meta.confidence`
on a composite result is the *minimum* of all its parts — a composite is
only as trustworthy as its weakest sub-scan. Always non-`None`-checked, never
opt-in: if you're only reading the primary result and skipping `meta`, you
can miss a degraded-but-plausible-looking answer.

**`--provenance`** — add it whenever a finding needs to be citeable or
reproduced later (a due-diligence memo, a bug report, an audit trail). It
attaches `reveal_version`, the exact `command`, `platform`, `python_version`,
target-repo `commit`/`dirty` state, and a `config_digest` — everything needed
to answer "what exactly produced this number, and would re-running it now
give the same answer." JSON-only: it has nothing to attach to on text output,
since there's no result dict to extend.

**`--perf`** — add it when you're chaining multiple reveal calls in a
pipeline and want to know which one is slow, or watching for regressions
over time. Appends one JSON line (`elapsed_s`, `peak_rss_kb`, `argv`,
`exit_code`, `pid`, `ts`) per invocation to `~/.reveal/perf.jsonl` (override
with `REVEAL_PERF_LOG_PATH`). Never fails the underlying command even if the
log write itself fails. For a slow `check` specifically, follow up with
`check --profile-rules` — a per-rule wall-time breakdown in one real pass,
not a diff of two runs.

**Known gap**: none of the above currently breaks down time *inside* a
composite command (`overview`/`architecture`/`hotspots`/`deps` sequentially
call several sub-adapters) — `--perf` gives the total for the whole call,
not a per-sub-adapter split, the way `check --profile-rules` does for
`check`'s rules. Tracked as `BACK-1025`.

## Combining them

They compose freely — `--format json --provenance --perf` is a normal,
supported combination: JSON result with an embedded `execution` block, plus
a separate perf-log line for the invocation itself. There's no flag that
subsumes another; pick each independently based on what you actually need
from that specific call.

## What this guide is not

This isn't about *orchestrating* multiple reveal commands into one report —
that's deliberately out of reveal's scope (see `reveal help://quick` and the
rejected `reveal dd`/single-composite-report proposals). Cross-command result
correlation (e.g. joining a `hotspots://` finding to its `check` detections)
is the caller's job today — there's no shared identity between commands yet
(tracked as `BACK-882`/`BACK-883`).
