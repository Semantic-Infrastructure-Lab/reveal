---
title: Probe Parity Gaps and Validation Tracker
category: maintainer
status: active
updated: 2026-05-05
---
# Probe Parity Gaps and Validation Tracker

Purpose:
- capture where `reveal` already overlaps with `probe`
- capture where that overlap is poorly documented or hard to discover
- track real feature gaps that still exist
- give maintainers a concrete validation checklist after docs or feature updates

This document is intentionally maintainer-facing. It is not a product overview.

---

## Current Assessment

`reveal` already contains a meaningful set of probe-inspired capabilities, but a large part of that surface area is hidden behind nav flags and MCP nav modes rather than URI adapters.

That means there are two distinct classes of gaps:

1. **Docs/help/discoverability gaps**
   - feature exists, but reasonable users do not realize it
2. **Real feature gaps**
   - feature class is still missing or only partially implemented

This distinction matters. We should not keep planning already-shipped features as if they do not exist.

---

## Features Already Present in Reveal

These are the strongest `probe` overlaps already present in `reveal`:

- `--around`
- `--scope`
- `--varflow`
- `--calls`
- `--ifmap`
- `--catchmap`
- `--exits`
- `--flowto`
- `--deps`
- `--mutations` / `--writes`
- `--sideeffects`
- `--returns`
- `--boundary`
- PHP support for the nav flags above
- `imports://` and `depends://` for include/import graphs
- `reveal trace` for execution narrative from an entry point
- `reveal surface` for env/route/tool/network/DB/filesystem boundary inventory
- `reveal_nav` MCP tool for the nav layer

Representative references:
- `docs/AGENT_HELP.md`
- `reveal/cli/parser.py`
- `reveal/file_handler.py`
- `reveal/adapters/ast/nav_*.py`
- `reveal/mcp_server.py`

---

## Gap Type 1: Docs / Help / Discoverability

### D1. Top-level docs under-sell probe-like nav functionality

Problem:
- README heavily emphasizes URI adapters and subcommands.
- The nav layer (`--around`, `--deps`, `--mutations`, `--sideeffects`, `--returns`, `--boundary`) is not prominent in the top-level product story.
- A user can read the adapter list and incorrectly conclude that these features do not exist.

Why this matters:
- creates false feature-gap reports
- lowers adoption of one of the most differentiated parts of Reveal
- makes `probe` look strictly more capable than Reveal even when it is not

Potential fixes:
- add a “Deep-Dive Nav Flags” section to the root README
- add one or two nav examples near the opening usage examples
- mention nav explicitly in `WHY_REVEAL.md` and `WHAT_IS_REVEAL_GOOD_FOR.md`

Validation:
- can a new user discover `--boundary` or `--deps` without reading `AGENT_HELP.md`?

Status:
- partially shipped 2026-05-05 — README now has a "Deep-dive code navigation" block with PHP and Python examples; `WHAT_IS_REVEAL_GOOD_FOR.md` §5 expanded with `--boundary`/`--sideeffects`/`--deps` and a flat-PHP example
- still open: `WHY_REVEAL.md` "Top Capabilities" list does not yet have a nav entry — only the MCP-server bullet was updated

### D2. `help://` is adapter-centric, not nav-centric

Problem:
- `help://` teaches adapters well.
- It does not surface nav flags as a first-class capability family.

Potential fixes:
- add `help://nav`
- add `help://probe-mapping`
- add nav examples to `help://relationships` or a generated “deep dive” topic

Validation:
- `reveal help://` should make it obvious that `reveal file.php :120-340 --boundary` is a supported pattern.

Status:
- open

### D3. MCP docs do not prominently advertise `reveal_nav`

Problem:
- README MCP section describes “five tools”.
- `reveal_nav` is a real MCP tool and is the most probe-like deep-inspection capability.

Potential fixes:
- update README MCP section and MCP guide
- document the split explicitly:
  - `reveal_structure`
  - `reveal_element`
  - `reveal_nav`
  - `reveal_query`
  - `reveal_pack`
  - `reveal_check`

Validation:
- MCP docs and actual tool list match
- examples include at least one `reveal_nav(..., 'boundary')` call

Status:
- shipped 2026-05-05 — README, `WHY_REVEAL.md`, and `WHAT_IS_REVEAL_GOOD_FOR.md` now list six tools including `reveal_nav`. `MCP_SETUP.md` already documented all six (no change needed).
- still open: no example yet shows an MCP-style `reveal_nav(..., 'boundary')` call signature in user-facing docs

### D4. Release history mentions probe inspiration, but product docs do not connect that thread

Problem:
- `AGENT_HELP.md` changelog already records “probe-inspired nav flags”.
- That historical context is buried.

Potential fixes:
- add a short “flat-file forensic analysis” subsection in user docs
- show PHP/procedural examples outside agent-only docs

Validation:
- product docs expose at least one flat PHP example using nav flags

Status:
- open

---

## Gap Type 2: Real Feature Gaps

### F1. SQL semantic auditing is still shallow

Current state:
- `--sideeffects` can classify DB-like calls by callee name.
- Reveal does not inspect SQL structure deeply enough to replace probe commands like:
  - `dynamic_sql`
  - `sqlescapes`
  - `sqlwhere`
  - `sqlmap`
  - `writesto`

High-value additions:
- detect interpolated SQL and classify risk
- extract WHERE columns
- extract written table/column names
- classify escaped vs unescaped variables in SQL arguments

Likely fit:
- nav flag family and/or `check` rules

Status:
- open

### F2. HTTP/curl safety auditing is still shallow

Current state:
- `--sideeffects` can classify HTTP-ish calls.
- Reveal does not perform semantic checks equivalent to:
  - `curl_audit`
  - `responsecheck`
  - timeout presence checks on curl wrappers
  - “call result is never checked” heuristics

High-value additions:
- missing timeout detection for common HTTP/curl paths
- unchecked response detection
- wrapper-call to branch correlation for common patterns

Likely fit:
- `check` rules first
- later: richer nav mode if needed

Status:
- open

### F3. Session/lock/cache lifecycle audits are missing

Current state:
- cache/session calls can be classified as side effects
- no semantic lifecycle auditing equivalent to:
  - `session_audit`
  - `lockaudit`
  - `memcache_audit`

High-value additions:
- detect suspicious lock acquire-without-release patterns
- detect network I/O inside session lock windows
- detect compare-and-set / memcache TOCTOU shapes

Likely fit:
- plugin or project adapter first
- only promote to core if repeated cross-project demand emerges

Status:
- open

### F4. PHP array-key and field-oriented tracing is still weak

Current state:
- `--varflow` tracks variables, not rich PHP array-key access patterns.
- Reveal does not have first-class equivalents for:
  - `arraykeys`
  - `condtrack var[key]`
  - `strcheck`

High-value additions:
- array-key read/write/cond tracking
- “where is `$foo['bar']` used?” analysis
- condition-oriented tracking for one field/key

Likely fit:
- nav layer

Status:
- open

### F5. Domain-specific cross-layer mutation tracing is missing

Current state:
- `--deps`, `--mutations`, `--boundary` are generic
- no direct equivalents for:
  - `statusflow`
  - `statewrites`
  - `storagepattern`
  - `platformmap`

Assessment:
- useful, but probably too domain-shaped for core Reveal right now
- better first as plugins or project adapters

Status:
- open

---

## Suggested Priorities

### Priority 0: Fix discoverability before building more

Reason:
- several “missing” features are already present
- docs/help debt is currently producing false negatives

Recommended changes:
1. README: add nav/deep-dive section
2. `help://nav` or equivalent
3. MCP docs: advertise `reveal_nav`
4. product docs: add flat PHP examples

### Priority 1: SQL and HTTP semantic checks

Reason:
- broad applicability
- strong overlap with what makes `probe` feel powerful
- fits Reveal’s static-analysis + rule architecture

Recommended first slices:
1. SQL interpolation / escaping / WHERE-column inspection
2. curl timeout presence checks
3. unchecked HTTP response heuristics

### Priority 2: PHP structure-specific nav improvements

Recommended first slices:
1. array-key tracking
2. field/key condition tracking
3. better foreach assignment semantics in PHP varflow

### Priority 3: lifecycle/domain audits as plugins first

Reason:
- higher complexity
- more project-specific
- better to validate demand before hardening into core

---

## Validation Checklist

Run this after any docs/help/feature update:

### Docs / Help

- [ ] README top-level examples expose at least one nav/deep-dive capability
- [ ] `help://` or linked docs make nav features discoverable without opening `AGENT_HELP.md`
- [ ] MCP docs/tool count matches implementation
- [ ] docs distinguish clearly between:
  - adapters
  - nav flags
  - subcommands
  - MCP tools

### Feature Presence

- [ ] `reveal file.php :120-340 --boundary` works and is documented
- [ ] `reveal file.php :120-340 --sideeffects` works and is documented
- [ ] `reveal file.php :120-340 --deps` works and is documented
- [ ] `reveal file.php :120-340 --mutations` works and is documented
- [ ] PHP examples exist outside changelog-only context

### Probe-Parity Reality Check

- [ ] no docs claim or imply Reveal has SQL semantic audits if it only has DB call classification
- [ ] no docs claim or imply Reveal has curl/session/lock semantic audits if it only has side-effect labels
- [ ] if new parity claims are added, they link to executable examples

### Candidate Feature Validation

Before promoting a new feature into core:
- [ ] is it general-purpose rather than one project’s forensic workflow?
- [ ] does it compose with existing Reveal concepts cleanly?
- [ ] can it be explained in one screen of docs?
- [ ] would a plugin or project adapter be a better first home?

---

## Open Questions

- Should nav capabilities remain flags, or should Reveal expose a URI/help surface for them as first-class concepts?
- Should some probe-like semantic audits live as `check` rules instead of nav flags?
- Is there a clean split where core Reveal owns generic SQL/HTTP safety checks, while project adapters own lifecycle/domain-specific forensics?

---

## Update Log

### 2026-05-05

Initial tracker created after reviewing:
- root README
- `docs/AGENT_HELP.md`
- `reveal/cli/parser.py`
- `reveal/file_handler.py`
- `reveal/adapters/ast/nav_*.py`
- `reveal/mcp_server.py`

Key conclusion:
- Reveal already has significant probe-style capability.
- The largest near-term gap is discoverability.
- The largest real feature gaps are SQL/HTTP semantic auditing and specialized lifecycle audits.

### 2026-05-05 (later) — Priority 0 partial pass

Validation actually run, not just planned:

- ✅ Validation Checklist > Feature Presence: confirmed `--boundary`, `--sideeffects`, `--deps`, `--mutations` all produce sensible output on flat PHP (`reveal file.php :1-80 --boundary` etc.). `--sideeffects` returned "no classified side effects" on the test slice — worth keeping an eye on whether PHP side-effect classification is firing as broadly as Python.
- ✅ MCP tool count drift fixed: README, `WHY_REVEAL.md`, and `WHAT_IS_REVEAL_GOOD_FOR.md` were all describing five MCP tools; actual count is six (`reveal_nav` was missing). All three updated. `MCP_SETUP.md` was already correct.
- ✅ README now exposes nav flags directly — new "Deep-dive code navigation" block with both Python and PHP examples, including `:120-340 --boundary`.
- ✅ `WHAT_IS_REVEAL_GOOD_FOR.md` §5 expanded with `--boundary`, `--sideeffects`, `--deps` examples plus a dedicated flat-PHP block.

Still open after this pass:
- D2: `help://nav` topic not yet added (separate implementation slice)
- D1 residual: `WHY_REVEAL.md` "Top Capabilities" list still has no nav entry — only the MCP bullet was touched
- D3 residual: no `reveal_nav(..., 'boundary')` MCP-style call example in docs
- F1–F5: untouched as planned (P1–P3)

Investigation completed. The original "PHP `--sideeffects` returns nothing" finding decomposed into three separate root causes:

**F6.a — Taxonomy gaps in `nav_effects._TAXONOMY`** (fixed 2026-05-05).
Several common PHP I/O builtins were missing from the classifier: `getenv`, `putenv`, `session_start` / `session_destroy` / `session_*`, `setcookie` / `setrawcookie`, `mail`, `trigger_error`, `apc_fetch` / `apc_delete`, `readfile`, `tmpfile`, `pdo->` / `new pdo`, `phpinfo`. New `env` and `session` kinds added to the taxonomy. 11 new tests in `TestClassifyCall`. Verified end-to-end against a synthetic PHP file (8 of 10 effect sites now classify) and the original sociamonials repro slice (`getenv` calls now show up correctly).

**F6.b — Substring-match false positives** (mitigated 2026-05-05).
Adding bare `'header'` to the http kind caused user wrappers like `printHeader` and `printSubheader` to misclassify as http (substring match is greedy). Removed `header` from the taxonomy with an in-code comment. The legitimate `header()` calls remain unclassified until the classifier moves from substring matching to an exact-or-boundary model. Tracking the underlying matcher upgrade as **F6.b-followup** — out of scope for this pass.

**F6.c — `range_calls` doesn't pick up object instantiation or method calls on local variables in PHP** (~~open~~ **fixed 2026-05-05 bright-pulsar-0505**).
On a synthetic file with `new PDO(...)` and `$pdo->prepare(...)`, only the bare-function calls were returned by `range_calls`; the object construction and the method dispatch did not appear. Root cause: `CALL_NODE_TYPES` in `reveal/treesitter.py` did not include `member_call_expression` or `object_creation_expression`, the two PHP node kinds for these forms. Fix: added both node types to `CALL_NODE_TYPES`, plus two new helpers in `nav_calls.py`:
- `_extract_member_call_callee` emits `"<receiver>-><name>"` (e.g. `$pdo->prepare`, `$stmt->execute`) so existing taxonomy patterns like `'->execute'`, `'->fetch'`, `'pdo->'` match.
- `_extract_object_creation_callee` emits `"new <Name>"` (e.g. `new PDO`) so the `'new pdo'` taxonomy pattern matches.

Verified end-to-end on `audit_db()` synthetic — all 5 calls now detected, 4 classify (`getenv` → env, `new PDO` → db, `$pdo->prepare` → db via `pdo->`, `$stmt->execute` → db, `$stmt->fetch` → db). 6 new tests in `TestPhpMemberAndObjectCalls`. Full reveal test suite: 8601 passed, 0 failures.

Net effect of this pass on D1/D3 claims: PHP `--sideeffects` now does meaningful work on flat procedural code (env reads, sessions, cookies, mail, trigger_error, apc cache, file reads). The discoverability story in the README and `WHAT_IS_REVEAL_GOOD_FOR.md` is now backed by working behaviour, not just nominal flag presence.

### 2026-05-05 (later still) — Python validation on a real codebase (peyton/topstep)

Validated all six nav flags on a 180-line Python function (`arbiter/bot.py scan_cycle`) in the peyton trading-bot project. Results:

- ✅ `--boundary`, `--deps`, `--mutations`, `--ifmap`, `--around` all produce sensible, useful output on a real codebase. `--ifmap` in particular reads cleanly with line ranges per branch.
- ⚠️ `--sideeffects` caught 3 `log` events (`event_log.emit_*` at L393/L433/L445) but **missed a real DB write**: `services.trade_db.save_eval_state(...)` at L386 and `services.trade_db.load_eval()` at L389. Same root cause as the PHP F6.a gap — the taxonomy is hand-coded and project-specific wrapper names (`save_*_state`, `load_eval`, `emit_*`) aren't in the patterns. The classifier *did* catch `event_log.emit_*` (likely via `'log'` substring on the receiver) but won't catch `trade_db.save_*` because the substring `db` only matches if the kind pattern includes it, and `save_eval_state` doesn't contain any current taxonomy keyword.

Filing as **F6.d — Python sideeffects taxonomy is canonical-name-only** (open).

The scope of F6.d is broader than F6.a (which was just adding missing PHP builtins to an existing classifier) — it surfaces a design question:

1. **Option A: keep taxonomy canonical-only.** Document that `--sideeffects` only catches stdlib/framework-canonical names (`open`, `getenv`, `urlopen`, `cursor.execute`, `requests.get`, etc.) and is intentionally blind to project wrappers. Users wanting to audit a domain wrapper run `--deps` and follow the call.
2. **Option B: receiver-based heuristics.** Add patterns that match on receiver names commonly used as I/O handles: `*_db.*`, `db.*`, `conn.*`, `cursor.*`, `cache.*`, `event_log.*`, `logger.*`. Higher recall, more false positives.
3. **Option C: per-project taxonomy extension.** Allow a project-local config (e.g. `.reveal/sideeffects.yaml`) to add patterns. This is the highest-leverage option but biggest scope — a whole config surface.

Recommendation: pair F6.d with the F6.b-followup (exact-or-boundary matching). Once matching is more precise, Option B becomes safer because false-positive risk drops. Then a small Option C surface (just a list of additional `kind: pattern` strings) gives the escape hatch.

Concrete examples observed in peyton that the canonical taxonomy misses:
- `services.trade_db.save_eval_state(...)` — db write
- `services.trade_db.load_eval()` — db read
- `services.exchange.get_open_position()` — http/api call
- `services.market_data.is_feed_stale()` — http/api call
- `services.market_data.get_bars(limit=...)` — http/api call
- `services.ghost.*` (ghost-soak tracking) — log/file write

These are all `services.<wrapper>.<verb>` shapes, which suggests a fairly tractable receiver-pattern rule once F6.b-followup lands.

**Tests run this validation pass:**
```bash
cd ~/src/projects/zack/topstep && reveal arbiter/bot.py scan_cycle --boundary
cd ~/src/projects/zack/topstep && reveal arbiter/bot.py scan_cycle --sideeffects
cd ~/src/projects/zack/topstep && reveal arbiter/bot.py scan_cycle --deps
cd ~/src/projects/zack/topstep && reveal arbiter/bot.py scan_cycle --mutations
cd ~/src/projects/zack/topstep && reveal arbiter/bot.py scan_cycle --ifmap
cd ~/src/projects/zack/topstep && reveal arbiter/bot.py :393 --around
```

This validates the D1/D3 claim that nav flags work on Python the same as on PHP — and reframes F6 from "PHP-specific" to "side-effect classifier is taxonomy-limited on every language".
