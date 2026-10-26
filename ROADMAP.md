# Reveal Roadmap
> **Last updated**: 2026-10-25

Where reveal is going and what will change for the people who use it. What has already
shipped is in [CHANGELOG.md](CHANGELOG.md); measured accuracy per language is in
[VALIDATION.md](VALIDATION.md); how to help is in [CONTRIBUTING.md](CONTRIBUTING.md).

---

## What reveal is for

Reveal shows the structure of code, docs and data before their content, so an AI agent or
an engineer reads only what a question needs. It is for agents and engineers who need to
understand a codebase, and it works as a set of primitives that due-diligence and review
work can build on.

Everything reveal does sits on one ladder, and the docs teach it in this order:

| Rung | Question | Code | Docs and data |
|---|---|---|---|
| 0. Orient | What is here? | `reveal DIR`, `reveal overview DIR` | `reveal DIR --ext md` |
| 1. Structure | What does this contain? | `reveal FILE` | `reveal DOC.md` |
| 2. Content | Show me this one thing | `reveal FILE NAME`, `reveal FILE :N-M`, `--grep` | `reveal DOC.md "Heading"` |
| 3. Relations | What connects to it? | `calls`, `imports`, `git` | `markdown` links and backlinks |
| 4. Behaviour | What does this function touch? | `--boundary` and the element flags | |
| 5. Judgment inputs | Where are risk, debt and boundaries? | `metrics`, `check`, `surface`, `contracts`, `patches`, `diff` | `check` (links, front matter) |

### The core tier: a promise

About 90% of real use is five operations: extract an element (`reveal FILE NAME`), extract
a markdown section (`reveal DOC.md "Heading"`), `--grep`, outline a file (`reveal FILE`), and
read a line range (`reveal FILE :N-M`). A bug in one of them outranks all other work, and
none of the changes below touches them.

Their bar is `tests/test_core_tier_golden.py`: text output pinned byte for byte across the
tier-1 languages and markdown, in three views (breadcrumbs off, a first run with
breadcrumbs on, and a later run once the show-once hints are spent), and each operation's
`--format json` carrying the same items as its text. A golden diff is a change agents will
see: accept an intended one with `REVEAL_UPDATE_GOLDEN=1 pytest tests/test_core_tier_golden.py -n0`
and review the diff like code.

---

## Current focus: one name per question, answers you can trust

Two problems shape the current work.

1. **Too many ways in, and some disagreed.** A newcomer met about 70 entry points for about
   15 capabilities: URI adapters, subcommands that were second spellings of adapters, 22
   element flags and 17 discovery entry points. In several places two names for the same
   question gave different numbers, because each counted with its own unstated rule.
2. **Most fixes were the same few bugs, repeated.** Across 0.122-0.129, fixes outnumbered
   features about five to one, and they fell into about 15 recurring classes with five
   causes: flags reaching adapters by seven different paths, results that could not say
   "failed" or "truncated" (so a failure read as a clean zero), shared code copied instead
   of called, per-language tables typed by hand, and help that nothing ever ran.

### How we work

- **Remove the cause, don't add a guard.** Removing a second implementation retired its bug
  class every time we did it; a guard over a listed set of cases leaked just outside its
  list. Each cause gets a ratchet first (a check that counts violations and lets the count
  only fall), then the removal.
- **Every number states its rule.** A count with a scope or counting choice names it in the
  text and the JSON output.
- **Honest beats complete.** Failure, truncation and unsupported input are visible in the
  answer. No confidence is printed without a measurement behind it. A heuristic whose error
  rate cannot be bounded is narrowed or retired, not tuned: `calls ?uncalled` (dead-code
  candidates) is retiring for that reason, after labelled samples found 0 or 1 real dead
  function in 20 candidates on most libraries measured ([VALIDATION.md](VALIDATION.md)). Use
  `?callers=NAME` to ask whether one function is used, and your language's own dead-code tool
  for the rest.
- **Every language, not just Python.** A change to an engine is measured per language
  before it ships, and no language may get worse. Each capability-language pair is in one
  of three tiers: *gated* (independent oracle, checked on change), *measured* (published
  figure) or *structure-only* (graph and judgment claims decline in the output).
- **The help moves with the code** and is run in CI.

**Next, in priority order**

1. **The first screen teaches only current names.** The README, `--agent-help` and
   `help://quick` teach only spellings that are not retiring (a ratchet reads the retired-names
   table and fails the build if one comes back); `--adapters` marks retired schemes from the
   same table.
2. **Call-graph recall back to its baseline for JavaScript and TypeScript.** Two precision
   fixes for function values moved what counts as a caller; the real functions they dropped
   are recovered, and the baseline is rebuilt with each lost edge classified. Remaining:
   callbacks inside class fields (BACK-2230).
3. **One import graph.** The retired `depends`, `deps` and `calls ?modules` already answer
   through `imports`; finish per-language parity before the old names stop working (BACK-2063,
   BACK-2064, BACK-1054), measure through the public request path (BACK-2062), and keep the
   oracle-free graph invariants green in every language (BACK-1096).
4. **One quality family.** `metrics` absorbs `hotspots` (BACK-2069, BACK-2149); repeatable
   `--output FORMAT[=PATH]` sinks replace `--also-json` (BACK-2089); `overview` absorbs
   `architecture` (BACK-2070); commands share their parses instead of repeating them
   (BACK-1889, BACK-1890, BACK-1885).
5. **The rest of the result contract.** Typed outcomes at the remaining adapter and analyzer
   boundaries (BACK-1059, BACK-1857), one rendering layer (BACK-916), one scan-budget policy
   (BACK-1052).
6. **A smaller core and a public adapter framework.** The hosting-operations adapters move
   to a separate `reveal-ops` package installed through pip entry points, and a "write your
   own adapter" guide with one contract test every adapter passes (BACK-2162, BACK-2165).
   Help discovery folds into `help://` (BACK-1055).
7. **Measure what is still judgment.** Decide per heuristic output whether to measure,
   narrow or retire it (BACK-2202); precision oracles for the element flags from
   independent tools (BACK-2203); rule precision beyond Python (BACK-1095); more languages
   in the recall gate (BACK-1518); a language scorecard generated from data (BACK-1900).
8. **Docs that cannot drift.** Every example in the README, the agent guide and
   `help://examples` runs in CI (BACK-1365); consumers move to the new names before the cut
   (BACK-2071).

Not on this list: new adapters, new languages and new flags, which wait until the work
above lands.

---

## What changes for users

### One name per question

| Question | Use | Replaces |
|---|---|---|
| Where do I start? | `reveal overview DIR` | `architecture` (being absorbed) |
| Who calls this, what does it call? | `reveal calls DIR --callers F` / `--callees F --depth N [--detail]` | `trace`, `trace://`, `?root=`, `?target=` |
| Who imports this, what does it import? | `reveal imports DIR --importers [FILE]`, `--external`, `--circular`, `--unused` | `depends://`, `deps`, `calls ?modules` |
| Per-file size, complexity, churn, provenance | `reveal metrics DIR`, `?view=provenance` | `stats://`, `classify://`, file `hotspots` (being absorbed) |
| Rule findings, including only what a diff changed | `reveal check PATH`, `--changed RANGE` | `--check`, `review`, `health` on code |
| How honest is the test suite? | `reveal patches DIR --view pressure` | `testability` |
| Find elements by name | `--name PATTERN` | `--search` |

The element flags are next: about 22 become about 12, and no flag will share a name with a
command (`--deps` becomes `--inputs`, `--sideeffects` becomes `--effects`, `--returns`
becomes `--exits`, and so on).

### How a name retires

- **Now:** the old spelling still works and prints one line naming its replacement. The
  retired-names table in `reveal/cli/invocation.py` is the one list; `reveal --adapters` and
  this page follow it.
- **At the cut release:** every old spelling exits 2 with its replacement named. The
  CHANGELOG entry for that release carries the full old-to-new table, generated from the
  same list. There is one breaking release, not one per change.
- **Hosting-operations adapters** (`cpanel`, `autossl`, `letsencrypt`, the nginx live probes,
  `mysql`, `ssl`, `domain`) move to a separate `reveal-ops` package at the cut, published
  before that release; an old scheme then exits 2 and says how to install it. nginx config analysis and its rules stay in core. `python://`
  is removed; `env://` stays.

### Exit codes

One contract for every command: 0 completed, 1 completed with findings when a findings gate
is on, 2 invalid invocation or resource, 3 analysis or output failed or was incomplete.
Incomplete wins over findings. `check` gates on findings by default; `--fail-on none`
reports them without exit 1.

---

## What We've Shipped

The release process adds an entry here for each version; the three most recent are kept.
Everything is in [CHANGELOG.md](CHANGELOG.md), and unreleased work on master is under its
`[Unreleased]` heading.

### v0.131.0 — Silent answers refused or disclosed, special modes and `--stdin`, install hints, cross-platform self-checks

- ✅ A command that cannot honor an argument says so: a mode that reads no path, a flag that reads no element, 23 per-file flags and `--stdin --section` refuse a second path or section and exit 2 instead of answering for the first (BACK-1751, 1728, 1687, 1715, 1735, 1773, 1764, 1765).
- ✅ Wrong answers that looked clean now decline or disclose: `diff://` on resources it cannot compare and on every element category (BACK-1689, 1732), a recovered parse no longer claims clean-parse trust (BACK-1729), unbalanced nginx braces lower confidence (BACK-1768), files lost to a dead pool worker are reported as lost everywhere (BACK-1726, 1752-1754, 1681, 1717, 1718).
- ✅ `git://` scopes to the directory asked for, relative or absolute, and resolves a target to its own repository (BACK-1690, 1654, 1760); line numbers count `\n` only (BACK-1722); `imports://` and I002 find cycles through `from pkg import submodule` (BACK-1723).
- ✅ Install hints name `reveal-cli` and a real extra, `reveal-cli[all]` installs every runtime extra, and `help://install` exists (BACK-1699, 1117, 1116); C# parses on a fresh language-pack 1.21 install (BACK-1746).
- ✅ Self-checks catch the cross-platform failure classes locally: V036-V042 in `reveal reveal:// --check`, the one-hop V026, and Windows test shards balanced by recorded cost; the push gate is the lints plus the 3.12 suite (BACK-1705, 1707, 1720, 1739, 1745, 1747).
- ⚠️ Scripts that passed extra paths to element-less flags, special modes or `--stdin --section` now get exit 2; line numbers on files containing form feeds or other non-`\n` separators shift by design — see CHANGELOG "Changed".

### v0.130.0 — Reliability seams, one failed and one cut outcome, core-path goldens, namespaces and nesting, help accuracy

- ✅ An error from any URI adapter exits 1 and is reported once, and a cut list says so with one marker, printed once (BACK-1059, 1543, 1547); the silent-except ratchet went from 123 to 0 (BACK-1614), and an unknown `?sort=` field is reported on every sorting adapter (BACK-1644).
- ✅ Shared seams replaced copies: one walker with gitignore-syntax `--exclude`/`REVEAL_IGNORE` everywhere (BACK-1223, 1576), one parser source with `GrammarUnavailable` (BACK-1045), paths spelled as the user typed them and with `/` on Windows (BACK-1366), one root finder (BACK-1372), and one parsed Invocation behind a flag ledger (BACK-1058, 1539).
- ✅ The five core operations have golden text tests and text/JSON parity (BACK-1601); `--grep` shows each hit's line and is 3-8x faster over a directory (BACK-1602, 1558-1563).
- ✅ Rust `mod`, PHP/C#/C++ namespaces and C/C++ enums and unions are listed and extract by name, `Parent.Child` resolves in every language, and `--outline` nests Go receiver and Rust impl methods under their type (BACK-1636, 1648, 1632, 1649); GraphQL operations and fragments are listed (BACK-1416).
- ✅ Help says what ships: guides open on a runnable command, `--language-info` states each analyzer's conformance level, MCP tool descriptions match behaviour, and data-adapter help promises only what returns (BACK-1613, 1421, 1612, 1608).
- ⚠️ JSON shape changes for scripts: an element diff's verdict moved from `type` to `change` (BACK-1637), `--fields` selects by one rule on every adapter (BACK-1607), and `--grep` groups carry `hits` (BACK-1602) — see CHANGELOG "Changed".

### v0.129.0 — Result-control flags honored or rejected, .gitignore correctness, member/route resolution, cache keyed on code

- ✅ `--limit`, `--head/--tail/--range`, `--format` and `--also-json` are applied or rejected with a note, never silently dropped: unsupported `sort=`/`limit=`/`offset=` warn and run (BACK-1385, 1425, 1496, 1497).
- ✅ Every walker skips what git ignores and no longer drops tracked files; `--no-gitignore` works everywhere (BACK-1386, 1485). A package marker above the nearest `.git` belongs to another project (BACK-1434).
- ✅ Element/member resolution: C++ out-of-line methods and operators, ambiguous names disclose every definition, and enums/traits/type aliases/`#private` JS methods/config elements are listed and extractable (BACK-1400, 1409–1412).
- ✅ `surface://` reads Rails `routes.draw`, WordPress REST routes and Spring/C# controller prefixes, and discloses error-recovered regions (BACK-1417, 1418, 1480).
- ✅ The disk cache is keyed on the code that built it, not just the version, so an edit cannot serve stale results (BACK-1294, BACK-1328); a huge file's outline is capped and says so (BACK-1424).
- ⚠️ Changes a script may notice: an unsupported `--format` or `--also-json` exits 2 instead of printing text (BACK-1425); git-ignored files drop out of every walker, so counts fall (BACK-1386); the text outline stops at 500 items per category (`--format json` is uncapped, BACK-1424).

---

## Validation

*Supported* ("the command runs on this language") is not *validated* ("we have shown the
answer is right"). A silent false negative, such as a load-bearing module reported with zero
importers, is the failure a reviewer cannot detect, because a wrong answer looks like a
checked one. So each cross-file signal is measured per language against an independent
ground-truth oracle (the real toolchain where one exists, otherwise a from-spec oracle that
shares no code with reveal), on real open-source codebases pinned to exact commits, and every
miss is root-caused. The figures, which signal was measured in which language, and how to
re-run every measurement are in [VALIDATION.md](VALIDATION.md); the pinned corpora are in
`tests/corpus/manifest.yaml`.

---

## Distribution

- **Windows code signing.** pip generates `reveal.exe` unsigned at install time, so machines
  with application control enabled can break on upgrade. Plan: apply to the SignPath
  Foundation for free open-source Authenticode signing, then sign the PyInstaller `--onedir`
  build in GitHub Actions (the build side exists in `windows-binary.yml`) and document it as
  the recommended Windows install. Details:
  [WINDOWS_SIGNING.md](reveal/docs/development/WINDOWS_SIGNING.md).

---

## Scope Test (What Belongs in Reveal)

Reveal exposes **structural data**; the consumer applies **judgment**. Run every proposed feature through this test before filing it. Requests captured during a specific engagement drift toward that engagement's use-case — name and scope by the *data*, not the *verdict*.

A feature belongs in reveal when **all** of these hold:

1. **It reveals data that structurally exists** in the artifact (imports, calls, blame, complexity, cert dates) — not a derived opinion.
2. **It's named after the data, not the consumer's activity.** `imports`, `surface`, `ownership` name data; `audit`, `dd`, `debt-in-dollars` name what the consumer concludes. If the name describes a verdict or a workflow, stop.
3. **It applies no domain or business judgment.** Deterministic, domain-agnostic rules (complexity > N, circular imports, hardcoded-secret patterns) are fine — those are universal code properties. "Is this AI real," "is this a DD red flag," "what's the debt in dollars" are not.
4. **It extends an existing primitive** (`surface` category, `calls://` / `git://` query) where it can, rather than adding a top-level subcommand named after a use-case.
5. **It's a single reveal, not an orchestrated playbook.** Pipes compose; reveal does not run named multi-step sequences on the consumer's behalf.

**Smell words in a proposed name:** *audit, assess, score, grade, verdict, rate, `*-in-dollars`*, or any consumer's process name (`dd`, `onboarding-review`). When you see them, the feature is usually a *consumer* of reveal's output and belongs in that consumer's tooling. Reframe to the data primitive it would have to read, and ship that instead.

This is the positive form of the list below.

---

## Explicitly Not Planned

These violate reveal's mission ("reveal reveals, doesn't modify") or fail the [Scope Test](#scope-test-what-belongs-in-reveal):

| Feature | Why Not |
|---------|---------|
| `--fix` auto-fix | Mission violation. Use Ruff/Black for formatting/fixes. |
| `reveal dd` & other consumer-workflow composites | Named after a consumer's process, not the data; orchestrates a named multi-step playbook. Reveal composes via pipes. Due diligence is a recipe over the core commands (`help://examples/due-diligence`), each step one question answered by one command. Decision: BACK-384. |
| `reveal debt --rate N` / debt-in-dollars scoring | A business opinion (dollar rate) layered on structural metrics. The inputs (`metrics`, `check`, `imports --circular`, `overview`) are JSON-exportable; compute the valuation in the consumer's script. Decision: BACK-385. |
| Vendor-specific `surface` sub-categories (`ai-provider`, `agent-framework`, etc.) | A curated vendor list names the *vendor identity*, not the *coupling type* — breaking the pattern of every other category (`network`, `db`, `sdk`, `env`). The data is already in `surface --type sdk`; the list would be stale the week a new framework ships. Use `reveal surface . --type sdk \| grep -E 'openai\|anthropic\|litellm'`. Decision: BACK-381/382. |
| A `--no-fail` flag on every command | Exit policy is one contract: `--fail-on none` reports findings without failing where a command gates on findings, and `\|\| true` is the Unix idiom elsewhere. |
| `calls ?uncalled` dead-code lists | Retiring: bare-name matching cannot reach useful precision across languages. Use `?callers=NAME` for one function and the language's own tools (vulture, knip, staticcheck, rustc's `dead_code`) for the rest. |
| `semantic://` embedding search | Requires ML infrastructure; over-engineered |
| Runtime execution traces (recorded runs) | Wrong domain (debugging tools). `calls --callees F --detail` is a static call-graph narrative, not a runtime trace. |
| `live://` real-time monitoring | Wrong domain (observability tools) |
| `ssh://user@host/adapter://` meta-adapter (SSH proxy mode) | Wrong layer: SSH is a transport, not a resource. Use `ProxyJump` in `~/.ssh/config`. |
| PostgreSQL, Docker and LSP adapters, `--watch` mode | Diminishing returns or other tools do it well (`docker inspect`, IDEs, `watch reveal file.py`). Not before the current focus lands. |
| Parquet/Arrow | Binary formats, not human-readable. Use pandas. |

---

## Languages and adapters

These lists change with every release, so this page does not copy them:
- `reveal --languages`: every language, with explicit analyzers vs tree-sitter fallback.
- `reveal --adapters` (and `help://adapters`): every URI scheme, with retired ones marked.
- [VALIDATION.md](VALIDATION.md): which signal is measured in which language.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add analyzers, adapters, or rules. Good
first contributions: language analyzer improvements, pattern detection rules, documentation
and examples. A proposal for a new feature should pass the [Scope Test](#scope-test-what-belongs-in-reveal)
first.
