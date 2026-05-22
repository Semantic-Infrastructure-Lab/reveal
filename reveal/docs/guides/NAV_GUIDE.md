---
title: Deep-Dive Code Navigation (Nav Flags)
category: guide
help_topic: nav
help_description: "Deep-dive code navigation flags (--outline, --boundary, --varflow, --sideeffects)"
help_category: feature_guides
help_token_estimate: "~2,000"
---
# Deep-Dive Code Navigation (Nav Flags)

**One-line summary:** Pinpoint inspection inside a function or line range — control flow, data flow, side effects, and refactor pre-flight, all without reading the file top-to-bottom.

Nav flags work on Python, PHP, and 35+ tree-sitter languages. Most flags accept `:LINE-RANGE` and work on flat procedural files (no function wrapper required).

For the full reference with output samples, see [`AGENT_HELP.md`](../AGENT_HELP.md) — search for "Navigate inside a function".

---

## At a Glance

| Flag | Question it answers |
|------|---------------------|
| `--outline` | What's the shape of this function? |
| `--scope :LINE` | What scope is this line inside? |
| `--around N` | What's near line N? (verbatim ±N lines) |
| `--ifmap` | What conditional branches exist? |
| `--catchmap` | What try/except structure exists? |
| `--exits` | Where can this range exit (return/raise/break/die)? |
| `--flowto` | Can control reach the end of this range? |
| `--calls` | What does this call? (sub-element scope) |
| `--varflow VAR` | Where is VAR read, written, or tested? |
| `--varflow VAR --cross-calls` | Same, but follows VAR across function call boundaries |
| `--narrow VAR` | How does VAR's type narrow through control-flow branches? |
| `--deps` | What variables flow INTO this range? |
| `--mutations` (alias `--writes`) | What does this range write that's read later? |
| `--sideeffects` | What DB/HTTP/FS/log/sleep calls fire here? |
| `--returns` | Each exit + the condition chain that gates it |
| `--boundary` | One-shot contract: inputs + environment + effects |

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
reveal file.py :120-340 --deps        # → these become parameters
reveal file.py :120-340 --mutations   # → these become return values
reveal file.py :120-340 --exits       # → spot unexpected early exits
reveal file.py :120-340 --boundary    # → unified view of all of the above
```

---

## Legacy / Flat-File Triage Workflow (PHP, procedural)

Useful for WordPress, CodeIgniter, or any large flat PHP file.

```bash
reveal legacy_handler.php :878-2130 --ifmap        # control-flow skeleton
reveal legacy_handler.php :120-340 --boundary      # what does this slice consume + emit?
reveal legacy_handler.php :120-340 --sideeffects   # which DB / curl / session calls fire?
reveal legacy_handler.php :120-340 --returns       # each exit + the gates that lead to it
reveal legacy_handler.php :120-340 --varflow $userId  # where does $userId flow?
```

`--boundary` on PHP additionally surfaces superglobals (`$_GET`, `$_POST`, `$_SESSION`, etc.) in a separate ENVIRONMENT section.

---

## MCP Equivalent

All nav flags are exposed via the MCP server's `reveal_nav` tool:

```python
reveal_nav(path="app.py", element="process_order", flag="boundary")
reveal_nav(path="legacy.php", element=":120-340", flag="sideeffects")
```

See [`MCP_SETUP.md`](MCP_SETUP.md) for setup and the full tool list.

---

## Disambiguation: `--calls` vs `calls://`

- `--calls` is **sub-element scope**: list call sites within a line range of one file.
- `calls://` is **project scope**: cross-file call graph (who calls / what does it call across the project).

Different scope, different question.

---

## Known Limitations

- PHP `foreach` loop variables (`$k`, `$v` in `foreach($arr as $k => $v)`) are tracked but classified as READ rather than WRITE.
- Variable tracking is name-based; same-named variables in different scopes within a flat file may merge.
- `--scope` and `--around` require a single `:LINE` — they do not accept ranges.

---

## See Also

- [`AGENT_HELP.md`](../AGENT_HELP.md) — full reference with output samples for every flag
- [`WHAT_IS_REVEAL_GOOD_FOR.md`](WHAT_IS_REVEAL_GOOD_FOR.md) §5 — narrative use cases for nav flags
