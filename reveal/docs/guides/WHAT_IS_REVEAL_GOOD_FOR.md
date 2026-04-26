---
title: What Reveal Is Good For
category: reference
---
# What Reveal Is Good For

**Short answer:** Reveal is best when you need to understand, review, or investigate complex technical systems without dumping raw files into your brain or an AI model.

It is especially strong at:

- exploring unfamiliar codebases quickly
- giving AI agents disciplined, token-budgeted context
- tracing impact before refactors
- reviewing pull requests structurally instead of textually
- navigating large functions and legacy files
- checking code, docs, infrastructure, and data from one CLI

If you already know Reveal is "structure before content, always," this guide answers the next question: **what kinds of work does that actually help with?**

---

## The Shortlist

If you only want the high-confidence answer, Reveal is best at these five jobs:

1. **Exploring unfamiliar codebases quickly**
2. **Preparing disciplined context for AI agents**
3. **Estimating refactor blast radius before you touch code**
4. **Reviewing pull requests structurally, not just textually**
5. **Investigating cross-domain problems that span code, docs, config, TLS, and data**

Those are the use cases where Reveal most consistently saves time and reduces wasted context.

---

## The Best-Fit Use Cases

### 1. Learning a codebase without reading everything

This is Reveal's most common and most reliable use case.

Instead of opening random files and hoping you guessed right, Reveal lets you move through a codebase in a controlled sequence:

```bash
reveal .
reveal src/
reveal src/auth.py
reveal src/auth.py validate_token
```

Why it is good for this:

- starts with directory and file structure, not raw content
- shows functions, classes, imports, size, and nesting before code
- lets you extract only the function or section you actually need
- works the same way for humans and AI agents

Use Reveal for this when:

- you are new to a repository
- you are onboarding to a service or subsystem
- you need to find the important files before reading implementation
- you want an agent to inspect a codebase without wasting context

It is less about "show me the file" and more about "show me the shape of the system first."

---

### 2. Giving AI agents the right context instead of "just read the repo"

Reveal is unusually good at agent workflows because it makes progressive disclosure enforceable rather than optional.

The strongest command here is `pack`:

```bash
reveal pack src/ --budget 8000
reveal pack src/ --since main --budget 8000
reveal pack src/ --since main --budget 8000 --content
reveal pack src/ --focus auth --budget 6000
```

Why it is good for this:

- selects files by priority instead of dumping everything
- boosts changed files for PR review with `--since`
- fits output to a token or line budget
- can emit file structure directly with `--content`
- reduces the chance that an agent spends its context on low-value files

Use Reveal for this when:

- preparing context for Claude Code, Cursor, Windsurf, or MCP clients
- handing a subsystem to another agent
- reviewing a PR with an agent
- bootstrapping a model into a large repository

Related strengths:

- `reveal-mcp` gives agents direct tool access without shell subprocess overhead
- `help://schemas` and `help://examples` let agents discover capabilities programmatically

Why this matters in practice:

- the docs position token budgeting as a first-class workflow constraint, not an afterthought
- the MCP server exposes purpose-built tools for structure, elements, queries, checks, and pack
- field selection and item limits make adapter output easier to fit into strict budgets

This is one of Reveal's clearest differentiators.

---

### 3. Refactor pre-flight: impact radius, coupling, and reverse dependencies

Reveal is very good at answering "what else will this touch?"

The two key tools are `calls://` and `depends://`:

```bash
reveal 'calls://src/?target=validate_token&depth=3'
reveal 'calls://src/?rank=callers&top=20'
reveal depends://src/auth/tokens.py
reveal 'depends://src?top=20'
```

Why it is good for this:

- shows who calls a function across files
- ranks architectural hotspots by caller count
- finds dead-code candidates with `?uncalled`
- shows which modules depend on a file before you change it
- helps you estimate blast radius before renames, extractions, or deletions

Use Reveal for this when:

- renaming a utility or shared function
- splitting a module
- extracting a service or package
- checking whether a file is safe to delete
- finding the modules with the highest structural gravity

Important nuance:

- `calls://` is static, name-based analysis, so it is best for impact estimation and relative coupling, not perfect runtime truth
- `depends://` answers module import impact, which complements function-level call graph analysis

Reveal is especially good here because it gives you both:

- **function-level impact** with `calls://`
- **module-level impact** with `depends://`
- **structural debt signals** with `imports://` and `deps`

---

### 4. PR review and CI gating

Reveal is a good fit when you want review workflows to focus on structural change, complexity movement, and actual risk.

```bash
reveal review main..HEAD
reveal review main..HEAD --select B,S
reveal diff://git://main/.:git://HEAD/.
reveal diff://git://main/.:git://HEAD/. --format json
```

Why it is good for this:

- `review` composes structural diff, checks, hotspots, and recommendations
- `diff://` tracks functions and classes added, removed, and modified
- changed functions can carry `complexity_before`, `complexity_after`, and `complexity_delta`
- commands return CI-friendly exit codes and JSON

Use Reveal for this when:

- reviewing a feature branch
- checking whether a PR made code materially more complex
- building a lightweight review gate in CI
- triaging where reviewer attention should go first

This is especially valuable when ordinary text diffs are too noisy to answer:

- what changed structurally?
- what got riskier?
- what became more complex?

It is also a strong fit for automation because the docs support:

- PR quality gates
- changed-files quality gates
- complexity gates
- hotspot tracking
- dead-code checks
- SSL health checks in CI

If the question is "can I turn this into a repeatable gate?" Reveal is often a good candidate.

---

### 5. Navigating giant functions and legacy files

Reveal is good for code that is too big, too nested, or too awkward to understand by reading top to bottom.

```bash
reveal app.py process_batch --outline
reveal app.py :123 --around
reveal app.py process_batch --ifmap
reveal app.py process_batch --catchmap
reveal app.py process_batch --flowto
reveal app.py process_batch --varflow result
reveal app.py process_batch --mutations --range 20-80
reveal app.py :123 --scope
```

Why it is good for this:

- `--around` gives exact nearby context from a line number or stack trace
- `--scope` shows enclosing function / class / block ancestry
- `--ifmap` and `--catchmap` turn control flow into a readable skeleton
- `--flowto` gives a reachability verdict for a range
- `--varflow`, `--deps`, and `--mutations` help with extraction and debugging

Use Reveal for this when:

- debugging a large handler or controller
- working in legacy Python or PHP
- extracting part of a long function safely
- understanding whether a value is read, written, or propagated through a range

This is one of Reveal's strongest "I need to understand this right now" workflows.

It is also one of the areas where Reveal feels most unlike ordinary grep-based tooling, because the output is structured around control flow and scope rather than raw text search.

---

### 6. Codebase health, orientation, and dependency debt

Reveal is useful before deep investigation because it can give you a concise picture of a codebase's shape and current health.

```bash
reveal overview .
reveal hotspots src/
reveal deps .
reveal 'imports://src?circular'
reveal 'imports://src?violations'
reveal stats://src/
```

Why it is good for this:

- `overview` gives a one-glance dashboard
- `hotspots` points to concentrated complexity and churn
- `deps` surfaces circular imports, unused imports, and top importers
- `imports://` adds lower-level graph queries and layer checks
- `stats://` provides project metrics and quality signals

Use Reveal for this when:

- sizing up a repository before making changes
- looking for refactor targets
- checking architecture drift
- trying to reduce structural debt before a release

This is a good "where should I look first?" workflow.

The `stats://` docs are explicit about its sweet spot:

- refactoring candidates
- technical debt tracking
- architecture comparison
- code review prioritization
- CI/CD quality enforcement

That makes Reveal useful not only for inspection, but for deciding **where effort should go next**.

---

### 7. Treating documentation as a queryable knowledge graph

Reveal is not only for code. It is also good for documentation systems with frontmatter, internal links, and large markdown corpora.

```bash
reveal 'markdown://docs/?aggregate=type'
reveal 'markdown://docs/?link-graph'
reveal 'markdown://docs/?body-contains=retry&type=procedure'
reveal check docs/ --select L
reveal check docs/ --select F
```

Why it is good for this:

- combines frontmatter metadata and full-text search
- builds bidirectional link graphs
- finds orphaned or weakly connected docs
- validates frontmatter and link hygiene
- helps you manage docs as a system rather than isolated files

Use Reveal for this when:

- cleaning up internal docs
- auditing a documentation set before publishing
- finding missing procedures or coverage gaps
- maintaining wiki-like markdown knowledge bases

This is also the area where Reveal's help system benefits from its own markdown tooling: the same markdown graph and metadata features that help with docs maintenance help keep the help corpus itself usable.

---

### 8. Infrastructure triage from the same CLI

Reveal is unusually good when the problem crosses code and operations boundaries.

```bash
reveal health ./src ssl://api.example.com domain://example.com
reveal ssl://api.example.com
reveal domain://example.com
reveal /etc/nginx/conf.d/users/myuser.conf --check
reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme
reveal autossl:///var/cpanel/logs/autossl/
reveal letsencrypt:///etc/letsencrypt/live/
```

Why it is good for this:

- checks code quality, certificates, DNS, and databases under one command model
- makes nginx, AutoSSL, and Let's Encrypt investigation queryable
- helps diagnose certificate serving mismatches and ACME failures
- gives unified exit codes for automation and monitoring

Use Reveal for this when:

- triaging SSL incidents
- auditing nginx vhosts and ACME challenge paths
- investigating cPanel or shared-hosting TLS issues
- combining app and infrastructure checks in one operational pass

Reveal is especially strong when the incident is not "just code" or "just ops," but the seam between them.

The infrastructure guides make that positioning unusually concrete:

- `ssl://` for certificate health, expiry, chain, SANs, and redirect checks
- `nginx://` and nginx file analysis for vhosts, ACLs, ACME paths, conflicts, and fleet audit
- `autossl://` and `letsencrypt://` for renewal and inventory workflows
- `health` for one command across code and infrastructure categories

---

### 9. Inspecting databases, JSON, env files, and spreadsheets without bespoke tooling

Reveal is a good fit when you need lightweight inspection across structured resources without switching mental models.

```bash
reveal mysql://prod/?type=replication
reveal sqlite:///tmp/app.db
reveal 'json://config.json?path=services.api'
reveal env://.env
reveal 'xlsx:///data/report.xlsx?powerpivot=relationships'
reveal 'xlsx:///data/report.xlsx?powerquery=list'
reveal 'xlsx:///data/report.xlsx?connections=show'
```

Why it is good for this:

- the same query style works across different resource types
- databases can be inspected structurally rather than only through ad hoc SQL shells
- JSON can be navigated and filtered without manual traversal
- env files can be validated and analyzed
- Excel workbooks can expose sheets, named ranges, Power Query, Power Pivot, and connections

Use Reveal for this when:

- inspecting a production schema or replication state
- reverse engineering a spreadsheet-backed BI workflow
- auditing workbook connections and SQL sources
- checking whether configuration or env files are sane

This is where "everything is a URI" becomes genuinely practical.

One especially distinctive case is spreadsheet reverse engineering:

- sheet inspection and range extraction
- CSV export for downstream tools
- search across workbooks
- named ranges and external connection discovery
- Power Query M extraction
- Power Pivot tables, DAX, and relationship graphs

That is a narrow use case, but it is not a gimmick. The docs support real workflows for it.

---

### 10. Auditing AI work history and agent workflows

Reveal is one of the few tools here that treats AI session history as first-class analyzable data.

```bash
reveal claude://sessions/
reveal 'claude://sessions/?search=validate_token'
reveal claude://session/my-session/files
reveal claude://session/my-session/workflow
reveal claude://config
```

Why it is good for this:

- shows what files a session read, edited, and wrote
- supports cross-session search
- lets you inspect workflow shape, tool usage, and errors
- can introspect Claude Code install state such as config, memory, agents, and hooks

Use Reveal for this when:

- auditing what an AI session actually changed
- finding previous work on the same problem
- debugging low-quality agent behavior
- understanding how teams are using AI tooling over time

This is a specialized use case, but Reveal is unusually strong at it.

The guide for `claude://` makes the intended use cases explicit:

- post-session review
- debugging failed sessions
- token optimization
- agent behavior analysis
- session comparison
- continuous monitoring of session quality

That makes it useful for both individual forensics and process improvement.

---

### 11. Learning Reveal itself through progressive help and discovery

Reveal is also good at teaching users and agents how to use Reveal without forcing them to read the entire documentation corpus first.

```bash
reveal help://
reveal help://ast
reveal help://tricks
reveal help://schemas
reveal help://schemas/ast --format json
reveal help://examples/quality --format json
reveal --discover
```

Why it is good for this:

- the help system is built around progressive disclosure, not a single monolithic manual
- `help://` supports low-token discovery by topic
- `help://schemas/<adapter>` exposes machine-readable adapter capability data
- `help://examples/<category>` exposes canonical task recipes
- `--discover` gives agents and tools a registry-level view of capabilities

Use Reveal for this when:

- teaching an AI agent what Reveal can do
- finding the right adapter or query pattern for a task
- building tooling on top of Reveal without hardcoding assumptions
- onboarding a user who needs just-in-time help instead of full manual reading

This matters because Reveal is not just "well documented"; it is designed to be discoverable from inside the tool.

That is a meaningful part of what Reveal is good for: not just answering questions about your systems, but helping humans and agents discover how to ask Reveal better questions.

---

### 12. Building composable command-line workflows

Reveal is good for people who like Unix-style pipelines, but want higher-level building blocks than `grep`, `sed`, and `awk` alone.

```bash
reveal nginx.conf --extract domains | sed 's/^/ssl:\/\//' | reveal --stdin --check
reveal 'calls://src/?target=main&format=dot' | dot -Tsvg > callgraph.svg
reveal 'depends://src?format=dot' | dot -Tsvg > depends.svg
reveal @domains.txt --check
```

Why it is good for this:

- adapters emit structured, pipeable output
- one adapter's result can become another adapter's input
- batch workflows work with `@file`, `--stdin`, JSON, and exit codes
- GraphViz export makes architecture diagrams scriptable

Use Reveal for this when:

- automating repeated investigations
- building quick internal diagnostics
- generating architecture visuals
- combining infrastructure extraction with follow-up checks

---

## Strong Secondary Use Cases

These are good fits, but less central than the top-tier workflows above:

- quick inspection of JSON, env files, SQLite, and MySQL resources
- documentation quality audits and link validation
- architecture diagrams via GraphViz output from `calls://` or `depends://`
- release validation and schema drift checks with `diff://`
- budget-constrained adapter output using `--fields`, `--max-items`, and `--max-snippet-chars`

These matter because they extend the same model into more domains, even if they are not the first reason most users will adopt Reveal.

---

## Who Gets the Most Value

Reveal is especially good for:

- engineers joining or inheriting unfamiliar systems
- AI-assisted coding workflows where context discipline matters
- maintainers reviewing pull requests and architectural drift
- teams doing refactors in mature codebases
- operators working across app, config, DNS, TLS, and hosting layers
- documentation-heavy teams with frontmatter and link-rich markdown
- analysts or engineers reverse engineering Excel and workbook-based systems

---

## When Reveal Is Less Ideal

Reveal is not the best tool when you need to:

- modify code directly
- auto-fix quality issues
- run arbitrary runtime debugging inside a live process
- replace specialized language servers or full IDE refactors
- replace full observability stacks or production APM
- prove exact runtime behavior from static analysis alone

In practice:

- use Reveal to narrow the search space and identify the important parts
- then use your editor, debugger, runtime tooling, or domain-specific tool for the final step

Reveal is usually the **front half** of the workflow: orient, filter, scope, compare, package, and inspect. It is not usually the final execution tool.

---

## A Good Rule of Thumb

Reveal is most useful when the problem looks like one of these:

- "What should I read first?"
- "What changed structurally?"
- "What else depends on this?"
- "Why is this function hard to reason about?"
- "How do I give an AI agent the right context?"
- "How do I discover which Reveal feature or adapter I should use?"
- "What is the health of this codebase or environment?"
- "How do these docs, configs, or spreadsheets connect?"

If that is the question, Reveal is probably a strong fit.

---

## Why These Use Cases Fit Reveal

Reveal tends to outperform simpler utilities when all of these are true:

- the system is large enough that raw reading is expensive
- you do not yet know which file, function, resource, or document matters most
- structure is more valuable than full content at the beginning
- the answer needs to be narrowed progressively
- the result may need to be handed to an AI agent or automation step

That is why Reveal shows up repeatedly in:

- onboarding
- review
- refactoring
- incident triage
- documentation maintenance
- context packaging
- cross-domain investigation

---

## If You Want a Starting Point

Start with the workflow that matches your job:

| Goal | Start Here |
|------|------------|
| Learn a repo | `reveal .` → `reveal src/` → `reveal file.py` |
| Find risky code | `reveal overview .` and `reveal hotspots .` |
| Review a PR | `reveal review main..HEAD` |
| Estimate refactor blast radius | `reveal 'calls://src/?target=func'` and `reveal depends://path/to/module.py` |
| Prepare AI context | `reveal pack src/ --since main --budget 8000 --content` |
| Discover Reveal capabilities | `reveal help://` or `reveal help://schemas` |
| Investigate docs | `reveal 'markdown://docs/?link-graph'` |
| Check infra health | `reveal health ./src ssl://site domain://site` |
| Explore workbook internals | `reveal 'xlsx:///file.xlsx?powerpivot=schema'` |
| Audit Claude sessions | `reveal claude://sessions/` |

For next steps:

- [Quick Start](../QUICK_START.md)
- [Why Reveal](../WHY_REVEAL.md)
- [Recipes](RECIPES.md)
- [Subcommands](SUBCOMMANDS_GUIDE.md)
- [Agent Help](../AGENT_HELP.md)
