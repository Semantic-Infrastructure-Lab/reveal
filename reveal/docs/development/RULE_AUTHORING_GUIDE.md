---
title: Reveal Custom Rule Authoring Guide
category: guide
help_topic: rule-authoring
help_description: "Write your own quality rules — user-global and project-local, auto-discovered"
help_category: dev_guides
help_token_estimate: "~1,600"
---
# Reveal Custom Rule Authoring Guide

**For anyone who wants a quality check reveal doesn't ship** — write a rule
once, outside the reveal package, and it's picked up by every `reveal --check`
without registering it anywhere.

This covers the two *external* discovery locations (user-global and
project-local). For rules meant to ship inside reveal itself, see
[SCAFFOLDING_GUIDE.md](SCAFFOLDING_GUIDE.md#reveal-scaffold-rule) — built-in
rules use the identical file layout and are discovered the same way.

## Where files go

| Scope | Location |
|---|---|
| Project-local | `<project root>/.reveal/rules/<category>/<CODE>.py` |
| User-global | `~/.local/share/reveal/rules/<category>/<CODE>.py` (XDG data dir) |
| User-global (legacy) | `~/.reveal/rules/<category>/<CODE>.py` — still discovered, but logs a one-time migration warning pointing at the XDG path |

Project-local rules are anchored to the **project root**, not the current
working directory — they're found identically whether reveal runs from the
root or a subdirectory. Both locations are scanned on every `reveal --check`
in addition to reveal's own built-in rules; there is no opt-in flag.

## The three requirements

Discovery (`RuleRegistry._discover_dir` in `reveal/rules/__init__.py`) is
strict about shape — get any of these wrong and the rule is silently skipped
(or, for a mismatched class name, logged at `WARNING`, invisible at default
verbosity):

1. **Category subdirectory is required.** Rule files must sit one level
   below the rules directory, inside a named subdirectory — `custom/X001.py`,
   not `X001.py` directly under `rules/`. The subdirectory name itself is
   free-form (it isn't matched against `RulePrefix`); `custom/` is the
   conventional choice for anything outside reveal's own categories.
2. **Filename must match `^[A-Z]+\d+$`** — a rule code like `X001` or
   `Q42`, nothing else. Files that don't match this pattern (`utils.py`,
   `helpers.py`, anything `_`-prefixed) are skipped without a warning, so
   shared helpers can live alongside rule files in the same category
   directory.
3. **Class name must equal the filename stem exactly.** `X001.py` must
   define `class X001(BaseRule)`. A file that matches the naming pattern but
   has no matching class logs `WARNING: File ... does not contain a valid
   rule class named X001` — check `reveal --check -v` if a rule you wrote
   doesn't show up in `reveal --rules`.

## Minimal example

```python
# <project root>/.reveal/rules/custom/X999.py
from reveal.rules.base import BaseRule, Detection

class X999(BaseRule):
    """Flags any file containing a TODO marker."""

    code = "X999"
    message = "todo-marker-found"
    category = "custom"      # plain string is fine — see typing below
    severity = "medium"      # plain string is fine — see typing below
    file_patterns = ['*']
    version = "1.0.0"

    def check(self, file_path, structure, content):
        detections = []
        if 'TODO' in content:
            detections.append(Detection(
                rule_code=self.code,
                message=f"{self.message}: found TODO marker",
                file_path=file_path,
                line=1,
                severity=self.severity,
            ))
        return detections
```

Works immediately, no registration step:

```bash
reveal sample.py --check --select=X
# sample.py:1:1 ⚠️  X999 todo-marker-found: found TODO marker

reveal --rules   # confirms X999 is discovered and lists its file-pattern coverage
```

## `severity` / `category` typing

Both fields accept either the real enum (`Severity.MEDIUM`,
`RulePrefix.S`) or a plain string — `RuleRegistry._normalize_rule_class`
coerces strings once, at registration time, so the ~10 call sites that read
`.severity.value` / `.category.value` don't each need to defend against a
loosely-typed rule:

- `severity = "high"` → coerced case-insensitively to `Severity.HIGH`.
  Valid values: `low`, `medium`, `high`, `critical`. An unrecognized string
  logs a warning and degrades to `Severity.MEDIUM` rather than crashing
  `reveal --rules` for every other rule.
- `category = "custom"` → coerced case-insensitively to `RulePrefix` **only
  if it matches a known single-letter prefix** (`B`, `C`, `D`, `E`, `F`,
  `I`, `M`, `N`, `S`, `V`, …). A prefix outside that set — `"custom"`
  itself is a common example — is left as the plain string you wrote; every
  consumer tolerates a `str` category by design, this isn't an error state.

## Debugging a rule that isn't showing up

```bash
reveal --rules                 # is it discovered at all?
reveal --check -v <file>       # -v surfaces the WARNING/ERROR logged by discovery
```

Most common causes, in order: file not inside a category subdirectory, class
name doesn't match the filename stem, or a real exception during import
(syntax error, bad top-level import) — the last is logged at `ERROR` with a
full traceback via `logger.error(..., exc_info=True)`.

## See Also

- [SCAFFOLDING_GUIDE.md](SCAFFOLDING_GUIDE.md) — `reveal scaffold rule` generates this same file layout plus tests, for both built-in and external rules
- [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) — the equivalent guide for external adapters (`.reveal/adapters/`, `~/.reveal/adapters/`)
