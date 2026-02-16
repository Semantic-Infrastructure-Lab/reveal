---
date: 2026-01-15
author: TIA (with Scott)
source: Strategic product feedback on positioning
status: Internal Planning Artifact
audience: Maintainers, Product Direction
priority: Critical
type: Strategic Planning
visibility: INTERNAL ONLY - NOT FOR EXTERNAL DOCS
---

# Reveal Positioning Strategy

⚠️ **WARNING: INTERNAL PLANNING DOCUMENT**

This document contains strategic hypotheses and positioning ideas. **DO NOT** copy this language directly into external documentation (README, website, etc.) without validation.

**Why this warning exists:** The kiyuda-0115 session leaked positioning language into external docs as if it were proven reality. This created marketing fluff that didn't match actual usage patterns.

**Use this document for:** Strategic discussions, evaluating feature alignment, exploring messaging options
**Do NOT use for:** README content, PyPI descriptions, website copy (without validation)

---

## Document Purpose

**What this document IS**:
- Strategic positioning and value proposition
- Analysis of Reveal's core strengths
- Product identity and messaging
- "Why" and "how to talk about it"

**What this document is NOT**:
- Feature roadmap (see planning/PRIORITIES.md)
- Technical implementation details (see research/TLDR_FEEDBACK_ANALYSIS.md)
- Development standards (see ARCHITECTURAL_DILIGENCE.md)

**When to use this document**:
- Writing external messaging (README, blog posts, talks)
- Making strategic decisions about product direction
- Evaluating feature proposals against mission
- Explaining Reveal to new contributors or users

---

## Strategic Context

**The Gap**: External feedback identified that Reveal's *capabilities* exceed its *perceived necessity*. This isn't a feature problem - it's a positioning problem.

**Key insight**: "People don't wake up thinking 'I need semantic structure.' They wake up thinking 'I don't trust this AI output.'"

**Opportunity**: Bridge the gap between what Reveal does (structure) and what users need (trust).

---

## Core Strengths (What Makes Reveal Already Good)

> **Source**: Analysis of Reveal's design decisions and architectural choices

### 1. Progressive Disclosure is Enforced by UX ⭐⭐⭐⭐⭐

**Not a slogan - it's a constraint**: Structure-first interaction
- Directory → outline
- File → semantic structure
- Symbol → exact code

**You cannot accidentally drown in code.**

**Why this is strong**: Most tools *allow* good behavior; Reveal *defaults* you into it.

**Meta-strength**: This is the design principle everything else builds on.

---

### 2. One Command, Many Semantic Modes ⭐⭐⭐⭐

```bash
reveal <target>  # Works for everything
```

No mode-switching. No subcommands. Same interface for:
- Directories, files, symbols
- Non-file resources (via adapters)

**Why this is strong**: Cognitive overhead is minimal. You explore instead of "operating a tool."

---

### 3. Output is Intentionally Composable ⭐⭐⭐⭐⭐

Default `filename:line` format is deliberate:
- Plugs into editors (vim, VSCode)
- Works with git diffs
- Pipes to grep/ripgrep
- Integrates with CI logs
- Feeds AI pipelines

**Why this is strong**: Respects existing workflows instead of replacing them. **Systems-thinking design decision.**

---

### 4. Adapters = Semantic Inspection Engine ⭐⭐⭐⭐

URI-style adapters (`help://`, `ast://`, `stats://`, `json://`, `env://`, `mysql://`) mean:

> **Reveal is not a "file viewer", it's a semantic lens over resources.**

Files are just one adapter.

**Why this is strong**: Architecturally expandable without bloating core UX.

**Underrated feature**: This is the foundation for ecosystem growth.

---

### 5. Rules are Explainable, Not Opaque ⭐⭐⭐⭐

`--check`, `--rules`, `--explain <RULE>` design:
- List rules
- Select rules
- Explain rules

Not just "fail/pass" - encourages *understanding* code quality.

**Why this is strong**: Rare in static analysis tools. Educational, not just enforcement.

---

### 6. AI-Era Design Without AI Dependency ⭐⭐⭐⭐⭐

Explicitly supports:
- Structured output
- Reduced context size
- Agent-oriented help modes

But:
- Doesn't require AI
- Doesn't hide logic behind models
- Remains deterministic

**Why this is strong**: Future-proof without being fragile. Works for humans today, agents tomorrow.

**This is the strategic positioning opportunity** - bridges both worlds.

---

### 7. Language Breadth Without Configuration Tax ⭐⭐⭐⭐

Zero-config. 38+ languages. Tree-sitter expansion (165+ languages).

You don't "set it up." You just point it at things.

**Why this is strong**: Lowers adoption friction - often more important than raw power.

---

### 8. Optimizes for Understanding, Not Editing ⭐⭐⭐⭐⭐

Reveal explicitly does **NOT**:
- Edit, refactor, run, transform

Exists purely to answer: **"What am I looking at?"**

**Why this is strong**: Understanding is the dominant cost in software work, and most tools underinvest in it.

**Design stance**: Code should be explored the way humans reason: shape → structure → detail.

---

## The Positioning Gap

### Current Framing (Implicit)
> "A tool for exploring structure."

**Serves**: Power users, developers who already understand semantic analysis
**Limits**: Most people don't realize they need this until they hit a pain point
**Problem**: Doesn't capture the *why* - why does structure matter?

### Proposed Reframing (Explicit)
> **"A tool for restoring trust and legibility in AI-assisted work."**

**Serves**: Anyone working with AI outputs, agents, generated code
**Captures**: The actual pain people feel daily
**Leverages**: All 8 core strengths above, especially #6 (AI-era design)

### The Synthesis (Best of Both)
> **"Reveal treats code as navigable structure, not text - enforcing progressive disclosure as the default way to understand systems. In the AI era, this becomes a trust mechanism: verify AI changes, audit agent actions, track provenance."**

**This framing**:
- ✅ Honors existing strengths (progressive disclosure, understanding-first)
- ✅ Names the pain (trust, legibility, AI safety)
- ✅ Positions for growth (AI adoption wave)
- ✅ Stays true to mission (inspection, not modification)

### Alternative Positioning Options

**"Google Maps for code"** - Zoom levels metaphor (casual, memorable)
**"Structure-first navigation"** - Technical, accurate
**"Semantic lens / code compressor"** - AI-era framing
**"Read-only interface to codebases"** - Emphasizes inspection-only

**Recommended**: Lead with trust/legibility, use "Google Maps" as secondary metaphor.

---

## Why This Matters Now

**The moment**: AI adoption is creating trust failures faster than trust solutions.

**Common pains** (users don't say "I need structure," they say):
- "I don't trust this output"
- "I can't tell what changed"
- "I don't know where this came from"
- "This agent did *something* and I can't explain it"
- "This repo/document/response is too big"

**Reveal already solves these** - but indirectly, through structure.

**The opportunity**: Name the pain explicitly, let Reveal answer immediately.

---

## Target Users & Their Needs

### 1. Engineers Onboarding to a Repo
**Pain**: "Get oriented quickly without reading everything"
**Reveal helps**: Map the repo, find entry points, locate key modules, drill into critical symbols
**Workflow**: `reveal .` → `reveal src/` → `reveal main.py` → `reveal main.py handle_request`

### 2. Code Reviewers (PR / Security / Architecture)
**Pain**: "Understand change scope and risk"
**Reveal helps**: Identify impacted files, see new/changed API surface, inspect only changed functions
**Workflow**: `reveal diff://git://main/.:git://feature/.` → inspect changed symbols

### 3. Maintainers / Tech Leads
**Pain**: "Keep the system coherent"
**Reveal helps**: Detect complexity growth, hotspots, duplication, suspicious patterns
**Workflow**: `reveal stats://./src --hotspots` → `reveal --check`

### 4. SRE / Production Triage
**Pain**: "Find the code path behind an incident"
**Reveal helps**: Quickly locate config, environment handling, connection setup, error boundaries
**Workflow**: `reveal env://` → `reveal api/handlers.py error_handler`

### 5. AI/Agent Workflows
**Pain**: "Provide accurate context without blowing tokens"
**Reveal helps**: Outline-first context, retrieve only relevant symbols
**Workflow**: Structure → filter → extract (10-25x token reduction)

---

## What Already Exists (Stronger Than We Claim)

### 1. Semantic Diff - KILLER FEATURE ✅ SHIPS v0.30.0

**Already implemented**: `diff://` adapter (v0.30.0+)

```bash
# Compare files structurally
reveal diff://before.py:after.py

# Compare git commits (what REALLY changed?)
reveal diff://git://HEAD~1/app.py:git://HEAD/app.py

# Pre-commit check (did I break something?)
reveal diff://git://HEAD/src/:src/

# Merge impact assessment
reveal diff://git://main/.:git://feature/.
```

**What it does**: Structural comparison, not line diffs
- Functions added/removed/modified
- Complexity changes
- Imports altered
- Works with ANY adapter (files, env, mysql, git)

**Why it's a killer feature**:
- People fear silent AI drift
- "What meaningfully changed?" is THE trust question
- Git diff shows lines, reveal shows *intent*

**Current problem**: This exists but isn't positioned as "the seatbelt for AI edits"

**Opportunity**: Rebrand as trust-repair tool

---

### 2. AI Agent Workflows - PARTIALLY EXISTS

**What exists**:
- `reveal --agent-help` (decision trees, patterns)
- `reveal help://agent` (comprehensive guide)
- `reveal help://agent-full` (all patterns)
- Progressive disclosure optimized for LLMs
- Token efficiency measurements (10-25x reduction)

**What's missing**:
- No agent *trace viewer* (ingest logs, show steps)
- No tool call visualization
- No collapse/expand for agent runs

**Gap**: Great for agents using reveal, not for *understanding* agents

---

### 3. Provenance - MISSING ❌

**What exists**: Nothing

**What's needed** (lightweight, not GenesisGraph):
- "This section came from X"
- "This file was generated by Y"
- "This output was transformed N times"

Simple annotations:
- Source file
- Command
- Timestamp
- Tool name

**Why it matters**: "Where did this come from?" is the trust question.

**Implementation sketch**:
```bash
# Add metadata to output
reveal app.py --annotate-source
# Output includes: generated_by, source_file, timestamp

# Track transformations
reveal app.py --track-provenance
# Output includes: transformation_chain, tools_used
```

---

## Feature Implications (What This Positioning Suggests)

> **Note**: For execution details and prioritization, see **planning/PRIORITIES.md** (single source of truth for roadmap)

### Features That Align With "Trust & Legibility" Positioning

**Zero-Code Opportunities** (Reframe existing features):
1. **Position diff:// as "AI Safety Net"** - Already exists (v0.30.0), needs marketing
   - "Before I merge AI changes, I run reveal diff"
   - "The seatbelt for AI edits"

**New Features to Consider**:
2. **Provenance hooks** - "Where did this come from?" (lightweight tracking)
3. **Agent trace viewer** - "What did my agent do?" (log visualization)
4. **Export formats** - Coordination tool (audit reports, summaries)

**Enhancements**:
5. **AI-aware defaults** - Auto-detect LLM output patterns

**See planning/PRIORITIES.md for**:
- Implementation details
- Effort estimates
- Tier assignments
- Current status
- Dependencies

---

### What NOT to Build (Mission Boundaries)

❌ **Ontology builders** - Wrong abstraction level
❌ **Schema editors** - Mission creep
❌ **AI generation inside Reveal** - Stay inspection-only
❌ **Configuration-heavy systems** - Complexity burden
❌ **Abstract "semantic modeling" UI** - Too generic
❌ **Big dashboards** - Violates CLI simplicity

**Why avoid**: Reveal wins by being fast, sharp, opinionated, and doing ONE thing better than anyone else.

**Design principle**: Inspection only, never modification.

---

## Strategic Positioning Matrix

### What Users Say vs What Reveal Solves

| User Pain | Current Framing | Better Framing |
|-----------|-----------------|----------------|
| "I don't trust this AI output" | "Explore structure" | "Verify AI changes structurally" |
| "What did the agent do?" | "Progressive disclosure" | "Audit agent actions" |
| "Where did this come from?" | "File analysis" | "Track provenance automatically" |
| "This output is too big" | "Semantic slicing" | "Collapse noise, see signal" |
| "Did this change break things?" | "Compare files" | "Safety net for AI edits" |

---

## Thesis Statement (For Writing/Pitching)

**Clean, defensible thesis**:

> *Reveal is strong because it treats code as a navigable structure rather than a blob of text, and enforces progressive disclosure as the default way of understanding systems. In the AI era, this becomes critical infrastructure for trust and verification.*

**Use this for**:
- Blog posts
- Conference talks
- GitHub README opening
- Funding pitches
- Product descriptions

---

## The North Star Test

**If Reveal succeeds, users will say:**

> **"Before I trust an AI output, I run it through Reveal."**

That's the bar. That's the identity.

**Supporting evidence**:
- They use `reveal diff://` before merging AI changes
- They run `--check` on generated code
- They ask "Did you reveal it?" in code reviews
- "Reveal everything before you ship" becomes a meme

---

## Comparison to Other Feedback

### tldr-pages Feedback (Technical Consistency)
**Theme**: Ecosystem enablement, contributor experience
**Focus**: Output contracts, plugin linters, stability taxonomy
**Audience**: Contributors, plugin authors
**Timeframe**: Build foundation for scale

### This Feedback (Strategic Positioning)
**Theme**: Product identity, trust-building
**Focus**: Naming pain, reframing value, killer features
**Audience**: End users (devs working with AI)
**Timeframe**: Capture mindshare NOW

**Are they compatible?** ✅ YES
- tldr feedback = *how to build ecosystem*
- This feedback = *why people adopt*
- Do both: Position for trust (this) + build for scale (tldr)

---

## From Strategy to Execution

> **This document defines STRATEGY (why, how to position).**
> **For EXECUTION (what to build, when), see planning/PRIORITIES.md**

### Immediate Strategic Actions (No Code)

1. **Update external positioning**
   - README.md lead: "Restore trust and legibility in AI-assisted work"
   - Reframe `diff://` as "AI safety net"
   - Add trust-focused use cases

2. **Create external one-pager**
   - Use thesis statement (above)
   - 3-5 key trust/verification scenarios
   - North star test

**Why separate**: Strategy changes are fast, execution is incremental.

**Next step**: Review planning/PRIORITIES.md for feature roadmap aligned with this positioning.

---

## Success Signals

**Adoption indicators**:
- "Before AI merge" workflow appears in tutorials
- GitHub issues mention "trust" and "verify"
- Users say "I check AI changes with reveal"
- "Reveal everything before you ship" becomes common phrase

**Product-market fit**:
- Developer tools integrate reveal (pre-commit hooks)
- AI tools recommend reveal (copilot, cursor, etc.)
- Trust-focused tools cite reveal as prior art

---

## Strategic Principles

**The Core Insight**:
> Reveal is already 70% of a compelling tool. The remaining 30% is not technical difficulty — it's naming the right pain.

**What This Means**:
- Don't build more features without strategic clarity
- Reframe existing features (diff://) before adding new ones
- Language and positioning matter as much as code

**Design Constraints** (Mission Boundaries):
- ✅ Inspection only, never modification
- ✅ Understanding-first, not execution
- ✅ Fast and sharp, not comprehensive and slow
- ✅ Opinionated defaults, not configuration-heavy

---

## Risks & Mitigation

### Risk 1: Accuracy Trust
**Problem**: If output isn't consistently accurate, trust collapses
**Mitigation**: V-rules for self-validation, comprehensive test suite (2008 tests), real-world validation

### Risk 2: Feature Dilution
**Problem**: Too many features dilute the core strength
**Mitigation**: Mission test (see PRIORITIES.md), clear "do NOT build" list

### Risk 3: Language Coverage Trap
**Problem**: Mediocre support for 165 languages worse than excellent support for 10
**Mitigation**: 38 fully-supported languages (excellent), 165 via tree-sitter (basic extraction)

### Risk 4: Adoption Depends on Habit
**Problem**: People forget to use it, revert to `cat`/IDE
**Mitigation**: Frictionless defaults, memorable workflows, integration (editor/CI/PR)

---

## Related Documentation

**For execution details**: planning/PRIORITIES.md (roadmap, features, timelines)
**For technical analysis**: research/TLDR_FEEDBACK_ANALYSIS.md (ecosystem patterns)
**For validation strategy**: VALIDATION_ROADMAP.md (quality gates)
**For architectural standards**: ARCHITECTURAL_DILIGENCE.md (development quality)

---

**Last updated**: 2026-01-15
**Next review**: After README.md repositioning ships
**Owner**: Scott (with TIA)
**Status**: Active strategy, ready for execution
