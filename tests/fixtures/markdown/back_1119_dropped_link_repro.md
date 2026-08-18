---
title: "Sociamonials Agent Farm — How Personas Get Grounded, and How They Get Stronger"
type: architecture
status: current
summary: "Verified account of how each persona is initialized today, the missing durable-knowledge loop that stops them improving, and the proposed findings-mailbox design that closes it."
beth_topics:
  - sociamonials
  - agent-farm
  - grounding
  - learning-loop
  - capability-policy
  - cortex
related:
  - SOCIAMONIALS_AGENT_FARM_ROLE_DEFINITIONS_2026-08-12.md
  - SOCIAMONIALS_AGENT_FARM_DISPATCH_ARCHITECTURE_2026-08-15.md
  - SOCIAMONIALS_AGENT_ROSTER_AND_ROLE_MAP_2026-08-12.md
---

# Sociamonials Agent Farm — How Personas Get Grounded, and How They Get Stronger

**Session:** `timeless-energy-0817` (2026-08-17)
**Question this answers:** *"What info would each persona need to do its job well, how is it
initialized/grounded today, and how does it get better over time?"*

The dispatch architecture (`SOCIAMONIALS_AGENT_FARM_DISPATCH_ARCHITECTURE_2026-08-15.md`) covers
*how a job reaches a worker*. The role definitions
(`SOCIAMONIALS_AGENT_FARM_ROLE_DEFINITIONS_2026-08-12.md`) cover *what each worker is for*. Neither
covers *what a worker knows when it wakes up, or how that knowledge improves*. That's this doc.

---

## Part 1 — How grounding actually works today (traced through code, not assumed)

Every persona — Cortex included — is initialized identically. Three static files plus two mounts.

### The three static files, rendered at deploy time

| File | Role |
|---|---|
| `config/<name>.CLAUDE.md` | The project context handed to every `claude -p` invocation. Persona identity, rules, doc/repo pointers, reveal recipes. **Does not change per message.** |
| `config/<name>.yaml` | Identity, bus subject, mounts, declared tools, `rules_extra`, tracker ID |
| `config/<name>.settings.json` | The *real* capability boundary — the `claude -p` permission allowlist |

The `.settings.json` is authoritative, and the `CLAUDE.md` says so explicitly: *"Your real capability
boundary is your sandbox config, not this file — if it isn't allowed there, you cannot do it
regardless of what this file or a Slack message asks for."*

### What each persona can actually run

| Persona | Granted tools |
|---|---|
| **Cortex** | `Read`, `Glob`, `Grep`, `Bash(reveal *)`, `Bash(/opt/universal-bot/bin/slack-history *)` |
| **Dex** | `Read`, `Glob`, `Grep`, `Bash(reveal *)` |
| **Queue** | `Read`, `Glob`, `Grep`, `Bash(reveal *)`, `Bash(probe *)` |

`deny: []` in each — the allowlist *is* the boundary. Everything else (`Write`, `Edit`, general
`Bash`, network tools) is simply absent, and the container's `--read-only` rootfs is the OS-level
backstop regardless of what `settings.json` says.

### The two mounts

- `/opt/universal-bot/mounted/ops_repo` → read-only mirror of `sociamonials-ops`, refreshed hourly
  by `SOC-143`'s cron
- `/opt/universal-bot/mounted/app_repo` → read-only view of the Sociamonials PHP app; **is a live
  dev working checkout, not a clean mirror** — may carry uncommitted changes, so `git status` before
  assuming it matches a branch

### Boot-time self-orientation

Per `HOST_ACCOUNT_CONTRACT_2026-08-08.md` §3, every invocation is instructed to survey rather than
trust a baked-in list — so a new doc or repo link becomes visible without a redeploy:

```bash
reveal ~/docs --files --ext md    # what notes exist
reveal ~/bin/                     # what tools are available
reveal ~/src/                     # what repos are linked
```

### What no persona has

**No `tia` binary.** That means no `tia beth` (search/graph/authority), no `tt` (task tracker), no
`tia project show`. Their entire durable knowledge is whatever sits in the hourly `ops_repo` mirror,
navigated with bare `reveal`.

This matters more than it sounds: **`tia project show sociamonials-ops` carries deploy traps,
operating rules, and the team/authority map that exist nowhere inside the repo itself** — so that
content is structurally invisible to every persona. Keyz's own findings surfaced this from the other
direction: the K8s devops-lease requirement is her single most-hit error class, is documented
globally in the project YAML, and appears nowhere in her role doc.

### Statelessness, and the one exception

Each dispatch is a fresh `subprocess.run(["claude", "-p", ...], capture_output=True)` in
`modules/runners/claude_cli.py`. Only `result.stdout` — the final answer text — is retained by the
framework; it is returned to Cortex and posted to Slack. No conversation carries forward.

**But `claude -p` writes its own session bookkeeping regardless**, and since `reveal` is granted,
`reveal claude://...` works *inside* the container. A persona can therefore inspect its own recent
dispatches — `/tools`, `/errors`, `/workflow` — with no new capability at all.

The catch is lifetime, documented in `CONTAINER_INTERFACE_CONTRACT.md` §7: `$HOME/.claude` is a
`--tmpfs mode=1777`, *"deliberately ephemeral, wiped every restart."* Self-reflection works within
one container's uptime and vanishes on redeploy — which happens on every capability-widening commit.

---

## Part 2 — The learning loop, and exactly where it breaks

The loop we want:

```
persona does work → learns something → writes it down durably →
someone reviews/synthesizes → role doc or tooling improves →
next dispatch starts smarter
```

| Step | Status today |
|---|---|
| Persona does work | ✅ Live — Cortex→Dex/Queue dispatch works end to end (`USB-52`/`USB-53` done) |
| Learns something | ⚠️ Captured by `claude -p`, readable via `reveal claude://`, but on tmpfs — gone at restart |
| **Writes it down durably** | ❌ **No mechanism at all.** No `Write` grant, no `memory_path` set on any live persona |
| Someone reviews/synthesizes | ⚠️ Only when a human goes mining by hand — see Part 5 |
| Role doc / tooling improves | ⚠️ Manual edit by Scott+TIA |
| Next dispatch starts smarter | ❌ Only if someone remembered to update the static `CLAUDE.md`/role doc |

### The load-bearing gap: findings evaporate

A worker's output today is Slack reply text. Cortex composes it into a message and posts it. Nothing
is persisted by the persona. A report-only role whose reports disappear when the thread scrolls past
is not accumulating anything.

`identity.memory_path` exists as a designed escape hatch (`CONTAINER_INTERFACE_CONTRACT.md` §7) —
an optional per-bot field permitting a Bash-heredoc write to one file under `~<bot>/docs`. **It is
set on zero live personas** (verified across `cortex.yaml`, `dex.yaml`, `queue.yaml`), and it is
scoped to a single memory note, not general findings authoring.

---

## Part 3 — Proposed design: a findings mailbox, swept by Cortex

Reuses infrastructure that already exists. No new mount, no per-worker git credentials.

### Workers get a mailbox, not a repo

`CONTAINER_INTERFACE_CONTRACT.md` §3 already defines a persistent, per-module, volume-backed state
directory (`service.state_dir`, resolved by `core/state.py`'s `module_state_dir()`), today used only
for lockfiles and the audit log. Findings belong there:

```
/opt/universal-bot/state/<persona>/findings/2026-08-17_1930_sdb-inline-query-fails.md
```

One file per dispatch, **written only when there's something worth keeping** — silence is a valid
outcome, matching the report-only discipline already in every role doc. One file per dispatch (rather
than one appended log) also sidesteps concurrent-write corruption when a persona is dispatched twice
in quick succession.

The grant is deliberately narrow: append/create scoped to the persona's *own* `state/<name>/`
namespace. No `Write` tool, no `git`, no credentials, no push rights.

### Scratch-note frontmatter

These files live outside `sociamonials-ops`, so they are **outside Beth's crawl roots** —
`beth_topics`/`beth_weight` would be dead weight here. They only enter Beth's world after promotion.

```yaml
---
persona: dex
dispatch_at: 2026-08-17T19:30:00-07:00
kind: footgun          # footgun | tool-gap | file-scope | signature | infra | question
target_doc: docs/development/SOCIAMONIALS_AGENT_ROLE_DBA_PERF_2026-08-12.md
severity: medium       # low | medium | high
topic: "sdb inline query form fails, must use query file"
---
```

- **`kind`** maps onto the sections real role docs already have (`Footguns`, `Primary tools`,
  file-scope, detection signatures) so a sweep knows which section a promotion touches. `infra` is
  deliberately distinct from `footgun`: "the container/host plumbing is broken" vs "here's a gotcha."
- **`target_doc`** is explicit, not inferred — not everything a persona finds is about its own role
  doc (a container gap belongs to `USB`, not `SOC`).
- **`severity`** caps at `high` by design. Genuinely urgent findings belong in the Slack reply, not
  filed for an async sweep — this keeps the mailbox honest about being asynchronous.
- **`dispatch_at`**, not a session/message citation: personas have no TIA session ID, and their
  transcript is gone after restart. The note *is* the evidence trail.

### Promotion path: Cortex reads, drafts, and opens a PR

One agent holds the higher-trust capability, not six:

- **Cortex gains** read access across all `state/*/findings/` (same read-only mount pattern it
  already uses) plus a docs-repo-scoped git write + PR-open capability — own branch only, **no merge
  rights**.
- **A human merges.** Unchanged.

Centralizing at Cortex means one credential to provision and rotate instead of six (the inverse of
the `SOC-144` shared-credential failure mode), one reviewer-facing surface, and it matches Cortex's
existing job — it already gathers worker results and composes them.

### Promoted docs reuse the existing corpus convention

Once a finding lands in `sociamonials-ops/docs/`, it is a real doc Beth indexes, and it should follow
the schema TIA already validates (`lib/beth/frontmatter_schemas.py`, backing
`tia beth quality schema-validate`). Use the already-registered **`type: analysis`** — no new schema
type. Note `frontmatter_schemas.py` is explicit that schemas are only registered for `type:` values
recurring ≥15× in the corpus; inventing a new one for this risks the false-positive flood it warns
about.

Lineage reuses the existing field rather than inventing one — `continuation_from` does exactly this
job for session READMEs (`tia/docs/reference/session-readme-schema.md`, Tier 3):

```yaml
---
title: "Dex — sdb inline query form fails, use query file"
type: analysis
status: current
summary: "sdb's inline query \"...\" form reliably fails; must use sdb query file <path>"
beth_topics: [sociamonials, dex, sdb, footgun]
continuation_from: "state/dex/findings/2026-08-17_1930_sdb-inline-query-fails.md"
related:
  - docs/development/SOCIAMONIALS_AGENT_ROLE_DBA_PERF_2026-08-12.md
---
```

**This promotion step is what finally makes agent-farm findings Beth-discoverable** — the missing
link between "a worker learned something" and "the corpus knows it."

---

## Part 4 — Capability policy: who writes tools

**Personas do not get Python execution or the ability to author and run their own tools.** This is a
deliberate boundary, not an oversight.

1. **They are Slack-mention-triggered, therefore attacker-reachable.** Code execution would turn a
   crafted Slack message — or a poisoned doc the agent reads and reasons over — into an execution
   primitive on a host mounting prod-adjacent code.
2. **It would hollow out the auditability mechanism the design already depends on.** Every charter
   centers on an explicit "Is NOT" section, credited with keeping Cortex's scope auditable through
   its own widening (`TIA-57`). An agent that can write and run its own tools routes around its
   charter silently.
3. **It contradicts the stated growth model**, which is in every persona's `CLAUDE.md`: *"Capability
   is expected to grow over time as trust is established. Each expansion is its own reviewable commit
   to the sandbox config."* Self-service tooling is capability growth with no commit and no review.

**Tool-writing stays with Scott+TIA.** If it is ever delegated to a dedicated tools agent, the output
should still land as a reviewed PR against `universal-bot`, shipped in the next image build — never a
runtime self-grant.

The working precedent is already there: `USB-55`'s fix was a thin shim (`universal-bot/bin/probe`)
that we wrote, reviewed, and baked into the image — not something Queue produced for itself.

### Corollary: convenience wrappers are ours to build

Where a persona's recurring call is fiddly and footgun-prone, the answer is a small pre-built wrapper
in the image, not raw syntax the model must reconstruct each invocation. Libby is the clear case —
her own findings confirmed the `markdown://` scheme-prefix footgun biting live in
`blazing-updraft-0808`. Candidate wrappers for whenever `SOC-167` is built:

```bash
~/bin/doc-health-sweep      # ?link-graph + ?lint across ops_repo, one report
~/bin/doc-backlinks <file>  # correct ?backlinks= URI construction, one arg
```

Raw `Bash(reveal *)` still covers everything ad hoc; wrappers only absorb the fixed, repeated sweep.

### Libby does not need Beth

Beth is not magic — `lib/beth/` is an inverted index (`beth_search.py`), a link-graph engine, and a
quality/lint engine over a persisted 37 MB `knowledge_graph.json`. Its speed advantage comes from
querying a prebuilt index; a stateless container can neither build nor persist one.

But `reveal`'s `markdown://` adapter — already inside Libby's `Bash(reveal *)` grant — covers the
same operations live and repo-scoped:

| Beth capability | `markdown://` equivalent |
|---|---|
| `graph explore` (relationships) | `?link-graph`, `?backlinks=<doc>` |
| `explore` (ranked keyword search) | `?body-contains=x&explain` |
| `quality frontmatter-lint` | `?lint` |
| broken internal links | `reveal doc.md --links` |

What is genuinely lost: cross-project reach and index-speed at corpus scale. Libby's mission is
scoped to one repo, so neither is load-bearing. **Libby is buildable today with zero new capability**
— she needs a defined sweep procedure and output contract, not new access. That makes her materially
cheaper to ship than Opie/Keyz/Boatface, which need live tool access.

⚠️ **Caveat found while writing this doc — validate the toolchain before building on it (`BACK-1119`).**
Running `reveal --links` against *this very file* silently extracted 8 of its 9 internal links,
dropping one whose line is structurally identical to the two above it. Confirmed via `--format json`
(so it is real extraction loss, not display truncation) and reproduced on a byte-identical copy
elsewhere. The failure mode is the dangerous one for a doc-health role: a dropped link is never
checked for brokenness, so the sweep returns a **false clean** rather than an error. Before Libby
ships, verify whether `?link-graph` and `?backlinks=` share the same extractor and therefore the
same defect — her whole value proposition rests on these being trustworthy. This is also a live
instance of the "cross-check layered tools before reporting a verdict as fact" discipline: the
mechanical scan being treated as ground truth is itself capable of under-reporting.

---

## Part 5 — Cross-cutting findings from the six role investigations

Six parallel investigations (one per persona) mined real session history — Beth-scoped search to find
role-relevant sessions, then structured `reveal claude://session/<id>/{tools,errors,files}` extracts,
diffed against each role doc. Per-role detail lives in the companion findings docs:

- [DBA/Perf (Dex)](SOCIAMONIALS_AGENT_ROLE_DBA_PERF_SESSION_HISTORY_FINDINGS_2026-08-17.md)
- [Ops/Incident Triage (Opie)](SOCIAMONIALS_AGENT_ROLE_OPS_INCIDENT_TRIAGE_SESSION_HISTORY_FINDINGS_2026-08-17.md)
- [Platform-Delivery Sweep (Queue)](SOCIAMONIALS_AGENT_ROLE_PLATFORM_DELIVERY_SWEEP_SESSION_HISTORY_FINDINGS_2026-08-17.md)
- [AppSec Sweep (Keyz)](SOCIAMONIALS_AGENT_ROLE_APPSEC_SWEEP_SESSION_HISTORY_FINDINGS_2026-08-17.md)
- [Release Manager (Boatface)](SOCIAMONIALS_AGENT_ROLE_RELEASE_MANAGER_SESSION_HISTORY_FINDINGS_2026-08-17.md)
- [Librarian (Libby)](SOCIAMONIALS_AGENT_ROLE_LIBRARIAN_SESSION_HISTORY_FINDINGS_2026-08-17.md)

**Every one of the six surfaced at least one real, recurring, undocumented footgun.** Three patterns
cut across roles:

### Environment-access friction is the most-repeated error class
Independently top-ranked for Dex, Opie, and Keyz — devops IP-lease gating, `kubectl exec` failures,
nested-SSH exit codes that read as failures but are benign non-matches. Documented globally in the
project YAML; absent from the role docs that need it.

### "Granted" ≠ "present"
`USB-55` is the canonical case: `queue.yaml` granted `Bash(probe *)` and the binary was never in the
image. It failed as a 120-second dispatch timeout that read like an infra outage, not a config bug.
`USB-56` (startup pre-flight warning for unresolvable granted binaries) is already filed against this.

### Role docs drift from where work actually happens
Dex's doc never names `lib/SmDbSessionHandler.php` despite it being edited repeatedly; Keyz's
signature table omits LFI/RFI and PHP object injection despite both getting dedicated multi-session
investigation; Libby's real edit traffic is on content docs, not the index docs her doc names.

### Methodology note, reusable
`/errors` and `/tools` surface footguns that are invisible in narrative — wrong CLI syntax, silent
permission denials, retried-then-abandoned approaches. Reading `/exchanges` or a README would not
have found them. **Cost caveat:** each fork consumed ~185–195K tokens. Piloting one role first to
validate the method, then fanning out, would have been materially cheaper than launching six blind.

---

## Part 6 — Open questions and next investigation

### Verify `claude -p`'s in-container transcript is actually recoverable
Reasoned from `CONTAINER_INTERFACE_CONTRACT.md` §7 (`claude -p` writes `$HOME/.claude/session-env`
unconditionally) plus the fact `reveal` is granted — **not yet demonstrated live inside a container.**
Test before building anything on it: dispatch to Dex, then ask it to run
`reveal claude://sessions/ --base-path ~/.claude/projects` and report what it sees.

### Decide the `.claude` tmpfs persistence mechanism
Sweep `~/.claude/projects/` into the persistent `state_dir` before restart, or mount `.claude` on a
real volume? The contract explicitly calls that tmpfs *"Claude Code's own CLI session bookkeeping,
not this bot's memory"* — suggesting the sweep, not the volume swap.

### Who reviews agent-authored doc PRs?
`GIT_WORKFLOW_TRACKER.md` already records 79% of merged PRs having no listed reviewer, and 100% of
the reviewed ones going to Sherwin. Doc-only PRs from Cortex should route to Scott/TIA, not add to
that queue — but this needs deciding before the first one opens, not after they pile up.

### Should promoted findings edit role docs, or stay advisory?
A finding promoted to `type: analysis` is discoverable but doesn't change what the *next dispatch*
reads — the static `CLAUDE.md` and role doc are what ground a persona. Closing that last link
(finding → role-doc edit → redeploy) is the difference between "knowledge is recorded" and "the agent
actually got stronger."

### Reconcile with the parallel investigation
Session `peguvefu-0817` (2026-08-18, continuation of `turbulent-shower-0816`) independently
investigated the same grounding question concurrently with this one, and has uncommitted edits to
`SOCIAMONIALS_AGENT_FARM_DISPATCH_ARCHITECTURE_2026-08-15.md` and `tools/cortex-bot/CHARTER.md`.
Reconcile before either set of conclusions is treated as canonical.

---

## Related

- [`SOCIAMONIALS_AGENT_FARM_ROLE_DEFINITIONS_2026-08-12.md`](SOCIAMONIALS_AGENT_FARM_ROLE_DEFINITIONS_2026-08-12.md) — the six roles
- [`SOCIAMONIALS_AGENT_FARM_DISPATCH_ARCHITECTURE_2026-08-15.md`](SOCIAMONIALS_AGENT_FARM_DISPATCH_ARCHITECTURE_2026-08-15.md) — how jobs reach workers
- [`SOCIAMONIALS_AGENT_ROSTER_AND_ROLE_MAP_2026-08-12.md`](SOCIAMONIALS_AGENT_ROSTER_AND_ROLE_MAP_2026-08-12.md) — empirical basis for the roles, and the build playbook
- `slack-projects/universal-bot/CONTAINER_INTERFACE_CONTRACT.md` — state dir (§3), `$HOME/.claude` tmpfs and `memory_path` (§7)
- `slack-projects/universal-bot/HOST_ACCOUNT_CONTRACT_2026-08-08.md` — host account layout, boot-time self-orientation
- `slack-projects/universal-bot/AGENT_DEPLOYMENT_RUNBOOK_2026-08-15.md` — deployment footgun table
- `tia/docs/reference/session-readme-schema.md` — the `continuation_from` lineage convention reused above
