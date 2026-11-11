# Reveal Roadmap
> **Last updated**: 2026-11-09

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
read a line range (`reveal FILE :N-M`). A bug in one of them outranks all other work. The
changes below leave their text output alone; their `--format json` gains the same envelope
every other answer carries, by addition (BACK-2601).

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

1. **Close the gaps that let a wrong answer through.** Gate imports on a multi-package Python
   repository (BACK-2575); make a damaged file exit like its URI spelling (BACK-2588); keep
   summaries computed over the whole scan, not the shown page (BACK-2592).
2. **One structure for every command.** Every noun gets both spellings (`reveal NOUN
   TARGET --option` and `NOUN://TARGET?option=value`) generated from one declaration, and a
   shared idea gets one option name with one meaning on every noun (BACK-2595, BACK-2597,
   BACK-2598). Counting rules shrink to one line in text output and stay in full in the
   JSON (BACK-2599). The model is accepted when a fresh agent, given one help screen, forms
   the right command on a fixed question set (BACK-2596). Every answer, path reads
   included, carries the same JSON envelope (BACK-2601). `check` shows medium and above,
   counts low findings in one line and exits 1 on high only, in a minor release before 1.0
   (BACK-2602). Old names keep working with a note until 1.0.
3. **One import graph.** The retired `depends`, `deps` and `calls ?modules` already answer
   through `imports`; finish per-language parity before the old names stop working (BACK-2079, BACK-2063);
   the public-path recall gate and the oracle-free graph invariants run in CI and stay green
   in every language.
4. **One quality family.** `metrics` absorbs the retiring `hotspots` noun (BACK-2149). Compact overview
   already uses one import analysis; the old dashboard assessment passes were removed.
5. **The rest of the result contract.** Typed outcomes at the remaining adapter and analyzer
   boundaries (BACK-2325, BACK-1857), one rendering layer (BACK-916), one scan-budget policy
   (BACK-1052).
6. **Measure what is still judgment.** Each heuristic output is measured, narrowed or
   retired, starting with the file hotspot score (BACK-2593);
   precision oracles for the element flags from independent tools (BACK-2203); rule precision beyond Python (BACK-1095); more languages
   in the recall gate (BACK-2079); each answer names its tier, and the language scorecard
   is generated from the same data (BACK-1900).
7. **Docs that cannot drift.** Every example in the README, the agent guide, the guides and
   `help://examples` now runs in CI; the ones that need a live host still skip until recorded
   host fixtures exist (BACK-1615). Help discovery folds into `help://` (BACK-1055). Consumers,
   the MCP tools included, move to the new names before the cut (BACK-2071).

**After 1.0.** 1.0 freezes names, exit codes and the JSON envelope. These follow it:

- **A smaller core and a public adapter framework.** The hosting-operations adapters move
  to a separate `reveal-ops` package installed through pip entry points, with a "write your
  own adapter" guide and one contract test every adapter passes (BACK-2162, BACK-2165).
  Until then they ship in the default install, noted as moving and outside the 1.0 freeze.
- **Shared parses.** Commands share their requested parses instead of repeating them
  (BACK-1889, BACK-1885).

Not on this list: new adapters, new languages and new flags, which wait until the work
above lands.

---

## What changes for users

### One name per question

| Question | Use | Replaces |
|---|---|---|
| Where do I start? | `reveal overview DIR` | retired `architecture` alias |
| Who calls this, what does it call? | `reveal calls DIR --callers F` / `--callees F --depth N [--detail]` | `trace`, `trace://`, `?root=`, `?target=` |
| Who imports this, what does it import? | `reveal imports DIR --importers [FILE]`, `--external`, `--circular`, `--unused` | `depends://`, `deps`, `calls ?modules` |
| Per-file size, complexity, churn, provenance | `reveal metrics DIR`, `?view=provenance` | `stats://`, `classify://`, file `hotspots` (being absorbed) |
| Rule findings, including only what a diff changed | `reveal check PATH`, `--changed RANGE` | `--check`, `review`, `health` on code |
| How honest is the test suite? | `reveal patches DIR --view pressure` | `testability` |
| Find elements by name | `--name PATTERN` | `--search` |

`overview` provides a compact project map in text and JSON; `overview --against REF`
compares a tracked ref with the live working tree. Follow its drill-down commands
for detailed quality, complexity, import relationships and history.

Element flags are becoming one option: `reveal PATH ELEMENT --view
boundary|effects|flow|exits|vars`. The first renames have shipped: `--deps` is replaced by
`--inputs`, `--mutations`/`--writes` by `--outputs`, and `--calls` by `--callsites`. Each
old flag keeps working with a note until the cut, and a view is checked in every
language before it absorbs a flag.

### How a name retires

- **Now:** the old spelling still works and prints one line naming its replacement. The
  retired-names table in `reveal/cli/invocation.py` is the one list; `reveal --adapters` and
  this page follow it.
- **At the cut release:** every old spelling exits 2 with its replacement named. The
  CHANGELOG entry for that release carries the full old-to-new table, generated from the
  same list. There is one breaking release, not one per change.
- **Hosting-operations adapters** (`cpanel`, `autossl`, `letsencrypt`, the nginx live probes,
  `mysql`, `ssl`, `domain`) ship in 1.0, noted as moving and outside its freeze. They move
  to a separate `reveal-ops` package in a later release, published before core drops them;
  an old scheme then exits 2 and says how to install it. nginx config analysis and its rules stay in core. `python://`
  is retired outright (removed, not moved); `env://` stays.

### Exit codes

One contract for every command: 0 completed, 1 completed with findings when a findings gate
is on, 2 invalid invocation or resource, 3 analysis or output failed or was incomplete.
Incomplete wins over findings. `check` gates on findings by default (on high-severity
findings only once BACK-2602 lands); `--fail-on none` reports them without exit 1.

---

## What We've Shipped

The release process adds an entry here for each version; the three most recent are kept.
Everything is in [CHANGELOG.md](CHANGELOG.md), and unreleased work on master is under its
`[Unreleased]` heading.

### v0.134.0 — Exit 2 for "not there", exit 3 for incomplete, accurate imports for Kotlin, Scala, Java, Go and Rust

- ✅ Commands agree on exit codes: `2` means the path, element, topic or request is not there or cannot be answered, `3` means the answer is incomplete, including an unreadable file under `--grep` (BACK-2528, 2527, 2492, 2533).
- ✅ Function nesting depth reads one lower in every language; `check`'s I002 reports one finding per file in a cycle, and I005 and D001 stop flagging correct Rust and cross-function code (BACK-2490, 2491, 2156).
- ✅ Import analysis is more accurate: Java full-package resolution and Maven modules, Kotlin and Scala names and packages, Go `go.work` and `replace` modules, Rust workspace crates and one-segment `use`, GDScript project roots (BACK-1712, 2549, 2557, 2552, 2562, 2155).
- ✅ `calls ?callees=` no longer credits an external call (`json.loads`) to a same-named project function, and `?callers=` names every definition of an ambiguous name (BACK-2553, 2479).
- ✅ A fresh install reads Zig correctly on `tree-sitter-language-pack` 1.25.0, and an outline that comes back empty says so instead of printing a bare header (BACK-2540, 2541).
- ⚠️ reveal needs Python 3.11 or newer, `python://` is removed, and scripts that tested for exit 1 on a missing path or relied on the old nesting depth need the changes under "Behavior changes" in CHANGELOG.md.

### v0.133.0 — Exit codes on json, ast, markdown and imports, compact overview, trustworthy caller ranking

- ✅ `json://`, `ast://` and `markdown://` queries exit 2 for an invalid request and 3 when a required read or parse failed, where they used to report success with matches missing (BACK-2361, 2367, 2414, 2415).
- ✅ `imports DIR` ignores parse failures outside DIR; `has_cycles` is `null` ("Unknown") when a scan file failed and no cycle was seen (BACK-2438, 2439).
- ✅ `overview` is a compact project map, and `overview PATH --against REF` compares a ref with the working tree without false changes on Go, Rust and TypeScript projects (BACK-2374, 2376, 2432, 2436).
- ✅ `calls ?rank=callers` ranks only functions defined under the path; test layout follows `test_layout.additional_paths` (BACK-2433, 2417, 2398).
- ✅ Element navigation has new names: `--flow`, `--inputs`, `--outputs`, `--callsites`; old spellings run with a note (BACK-2364, 2363).
- ⚠️ Scripts that relied on the old exit codes, on `has_cycles` being a boolean, or on `architecture` output need the changes under "Behavior changes" in CHANGELOG.md.

### v0.132.0 — One exit contract, one imports engine, named command forms, retired names noted

- ✅ One exit contract on the declared commands: 0 complete, 1 gated findings, 2 invalid invocation, 3 required analysis or output failed or incomplete; `--fail-on none|findings` on `check`, `review` and `health` (BACK-2051, 2052, 2066).
- ✅ `imports` is the one import-graph engine: `depends://`, `deps` and `calls ?modules` read it, function-level imports are edges tagged with their scope, every count states its edge rule (BACK-1054, 2077, 2078).
- ✅ `calls`, `imports`, `metrics`, `patches`, `pack`, `overview`, `hotspots`, `contracts`, `architecture`, `surface` and `testability` answer the same through `reveal NOUN` and `NOUN://` (equal JSON and exit code); `check --changed RANGE` checks a git range.
- ✅ Measured: the pinned-corpus recall gate scores imports and Python callers through the public request path, and `scripts/graph_invariants.py` checks oracle-free graph invariants on all 24 pinned corpora.
- ✅ Old spellings (`trace`, `deps`, `calls ?root=` and `?target=`, `stats://`, `classify://`, `health` on a code path) still run and print a replaced-by note from the one `RETIREMENTS` table; they error at the cut release.
- ⚠️ Exit codes of `review`, `health`, `calls` and `check --also-json` changed, `imports` and `calls` count some edges differently, and the nine `reveal.cli.commands.<noun>` modules moved to `reveal.adapters.<noun>` — see the "Behavior changes" section of CHANGELOG.md.

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
