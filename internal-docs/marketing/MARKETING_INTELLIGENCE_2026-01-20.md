# Reveal Marketing Intelligence Meta-Document

**Session**: dizisi-0120
**Created**: 2026-01-20
**Purpose**: Comprehensive capture of all reveal information for marketing voice development

---

## Table of Contents

1. [Core Positioning](#core-positioning)
2. [The Elevator Pitches](#the-elevator-pitches)
3. [Feature Inventory](#feature-inventory)
4. [Token Efficiency Data](#token-efficiency-data)
5. [Messaging Angles](#messaging-angles)
6. [Real-World Stories](#real-world-stories)
7. [Competitive Differentiation](#competitive-differentiation)
8. [Voice & Philosophy](#voice--philosophy)
9. [Documentation Inventory](#documentation-inventory)
10. [Gap Analysis](#gap-analysis)
11. [Raw Materials](#raw-materials)

---

## Core Positioning

### The One-Liner
**"Stop Reading Code. Start Understanding It."**

### The Problem Statement
AI agents read entire files when they only need structure. A 7,500-token file read to understand one 50-token function. This is insane—not because agents are bad, but because our tools are designed for humans with eyes, not agents with context windows.

### The Solution
Reveal provides **progressive disclosure** for code: structure first (50 tokens), then drill down to specifics (50 more). Same understanding, 50-150x fewer tokens.

### The Pattern
**Orient → Navigate → Focus**
```bash
reveal src/           # What exists? (50 tokens)
reveal src/auth.py    # What's inside? (100 tokens)
reveal src/auth.py login  # Show me that function (50 tokens)
```

### The Bigger Picture
Reveal is **Layer 1-3** of a 7-layer semantic operating system. It's proof that semantic infrastructure works—that progressive disclosure, knowledge graphs, and composable tools can deliver 25x efficiency gains in production.

---

## The Elevator Pitches

### 5-Second Pitch
"Reveal shows AI agents code structure instead of raw files. 50 tokens instead of 7,500."

### 30-Second Pitch
"When you ask Claude to fix a bug, it reads entire files—thousands of tokens for a one-line fix. Reveal changes this. It shows structure first: 'This file has 8 functions, here they are.' Then you extract just what you need. Same understanding, 50x fewer tokens. That's the difference between an agent that forgets what you said 10 minutes ago and one that can refactor your entire codebase."

### 2-Minute Pitch
"AI agents are amazing at reasoning but terrible at not reading everything. Ask Claude to fix an auth bug and it reads auth.py (3,200 tokens), config.py (1,800 tokens), utils.py (2,100 tokens). It finds the bug on line 47. You just spent 7,100 tokens on a one-line typo.

Reveal fixes this with progressive disclosure—a UX pattern from the 80s we somehow forgot to build for AI. Instead of dumping raw text, it shows structure:

```bash
reveal auth.py        # 100 tokens: see 8 functions, their complexity, locations
reveal auth.py login  # 50 tokens: extract just that function
```

150 tokens instead of 7,500. And it's not just files—Reveal has 15 URI adapters. Query code complexity with `ast://`, check SSL certificates with `ssl://`, analyze nginx configs, detect circular dependencies. Every resource gets the same pattern: orient, navigate, focus.

The result? Measured across 300+ sessions: 25-30x token reduction. Agents that can explore freely instead of drowning. Sessions that last hours instead of minutes. This isn't about saving money on tokens—it's about making AI actually capable of bigger tasks."

---

## Feature Inventory

### Current Version: v0.42.0 (Changelog) / v0.32.0 (PyPI)

### Core Capabilities

#### File Analysis (42 Languages)
- **Programming**: Python, JavaScript, TypeScript, Go, Rust, Java, C, C++, C#, Ruby, PHP, Lua, Scala, GDScript
- **Scripts**: Bash, PowerShell, Windows Batch (.bat/.cmd)
- **Config**: YAML, JSON, TOML, INI/Properties, Dockerfile, Nginx
- **Data**: CSV/TSV, XML, JSONL, Jupyter notebooks
- **Documents**: Markdown (with section extraction)
- **Plus**: TreeSitter fallback for 30+ more

#### URI Adapters (15+)
| Adapter | Purpose | Example |
|---------|---------|---------|
| `ast://` | Query code by complexity/name/size | `reveal 'ast://./src?complexity>10'` |
| `stats://` | Codebase metrics | `reveal stats://./src` |
| `imports://` | Dependency analysis, circular detection | `reveal 'imports://.?circular'` |
| `diff://` | Semantic structural diff | `reveal 'diff://old.py:new.py'` |
| `python://` | Python environment debugging | `reveal python://doctor` |
| `json://` | JSON navigation and queries | `reveal json://config.json/database` |
| `ssl://` | SSL certificate inspection | `reveal ssl://example.com --check` |
| `git://` | Git repository inspection | `reveal git://.` |
| `env://` | Environment variables | `reveal env://PATH` |
| `help://` | Built-in documentation | `reveal help://` |
| `reveal://` | Self-introspection | `reveal reveal://adapters` |
| `claude://` | Claude session analysis | `reveal claude://session/name` |
| `sqlite://` | SQLite database schema | `reveal sqlite://data.db` |
| `mysql://` | MySQL database schema | `reveal mysql://localhost/mydb` |

#### Quality Rules (43+ Rules)
- **B** - Bugs: bare except (B001), @staticmethod with self (B003), silent exception handlers (B006)
- **C** - Complexity: cyclomatic complexity (C901), function length (C902)
- **S** - Security: hardcoded secrets, insecure URLs, Docker :latest tags
- **E** - Style: line length (E501)
- **D** - Duplicates: copy-pasted code
- **N** - Nginx: duplicate upstreams (N001), missing SSL headers (N002), mixed SSL (N003), ACME path inconsistency (N004)
- **M** - Maintainability: hardcoded lists (M104)
- **I** - Imports: architectural violations
- **R** - Refactoring candidates

#### Recent Features (v0.39-v0.42)

**v0.42.0** - Universal `--stdin` URI support
- Batch process any URI scheme: `echo -e "ssl://a.com\nssl://b.com" | reveal --stdin`
- Mix files and URIs in single batch

**v0.41.0** - SSL adapter + N004 rule
- `ssl://` adapter for certificate inspection
- N004: Detects ACME challenge path inconsistencies (prevented real cert outage)
- Content-based nginx detection

**v0.40.0** - Tree view improvements
- `--dir-limit`: Per-directory entry limit (solves node_modules problem)
- `--adapters`: List all URI adapters
- M104: Hardcoded list detection

**v0.39.0** - Major analyzer expansion
- Windows Batch (.bat/.cmd) analyzer
- CSV/TSV analyzer with schema inference
- INI/Properties analyzer
- XML analyzer (Maven, Spring, Android)
- PowerShell analyzer
- B006: Silent exception handler detection
- `--section` flag for markdown
- `--capabilities` endpoint for agent introspection
- Hierarchical extraction: `Class.method` syntax
- `:LINE` and `@N` ordinal extraction

#### Extraction Syntaxes
```bash
reveal file.py function_name      # By name
reveal file.py MyClass.method     # Hierarchical
reveal file.py :73                # By line number
reveal file.py :73-91             # Line range
reveal file.py @3                 # 3rd element (ordinal)
reveal file.py function:2         # 2nd function (typed ordinal)
reveal doc.md "Installation"      # Section by heading
reveal doc.md --section "Setup"   # Section with flag
```

#### Output Formats
```bash
reveal file.py                    # Human-readable text
reveal file.py --format=json      # JSON structure
reveal file.py --format=grep      # Pipeable (file:line:name)
reveal file.py --copy             # Copy to clipboard
reveal file.py --outline          # Hierarchical view
```

#### Agent Integration
- `--agent-help`: Quick reference (~2,400 tokens)
- `--agent-help-full`: Complete guide (~12,000 tokens)
- `help://`: Progressive discovery system (50-500 tokens as needed)
- `--capabilities`: Pre-analysis introspection
- `meta.extractable`: Post-analysis discoverability in JSON

---

## Token Efficiency Data

### Measured Results

| Workflow | Traditional | With Reveal | Reduction |
|----------|-------------|-------------|-----------|
| Understand file structure | 7,500 tokens | 50 tokens | **150x** |
| Extract one function | 7,500 tokens | 45 tokens | **166x** |
| Code exploration | 35,000 tokens | 600 tokens | **58x** |
| Pattern discovery | 50,000 tokens | 2,200 tokens | **22x** |
| Doc navigation | 25,000 tokens | 1,250 tokens | **20x** |
| **Average across workflows** | **36,667 tokens** | **1,350 tokens** | **27x** |

### Context Window Impact

| Scenario | Without Reveal | With Reveal |
|----------|----------------|-------------|
| Files explorable (100K context) | ~13 files | ~2,000 explorations |
| Session duration | Minutes | Hours |
| Codebase size handleable | Small projects | Enterprise scale |

### Economic Impact (per 1000 agents)

| Metric | Traditional | With Reveal | Savings |
|--------|-------------|-------------|---------|
| Annual cost | $54,750 | $7,670 | **$47,080** |
| Energy (kWh/year) | ~2M | ~280K | **86% reduction** |

---

## Messaging Angles

### For AI Agent Users (Claude Code, Cursor, Copilot)

**Pain**: "My context window fills up. Claude forgets what I said 10 minutes ago. Complex refactors fail halfway through."

**Message**: "The solution isn't smarter AI—it's better tools. Reveal gives AI agents what humans get for free: the ability to see structure before diving into details."

**Proof**: "With 100K context: Without reveal = ~15 files before exhaustion. With reveal = ~500 files of structural understanding. That's the difference between 'I can help with small fixes' and 'I can refactor your entire authentication system.'"

### For DevOps/Infrastructure

**Pain**: "Nginx config errors take down production. SSL certs expire unexpectedly. Environment drift causes outages."

**Messages**:
- `reveal nginx.conf --check` - "Caught 3 critical issues before deployment"
- `reveal ssl://example.com --check` - "Check certificate health in CI/CD"
- `reveal python://doctor` - "Find stale .pyc files in 0.3 seconds vs 30 minutes of confusion"

**Story**: N004 rule exists because a real 209-cert outage happened due to ACME path inconsistencies. Reveal now catches this automatically.

### For Code Review

**Pain**: "PR reviews take forever. Reading entire files to understand small changes."

**Message**:
```bash
git diff --name-only origin/main | reveal --stdin --outline
git diff --name-only | grep '\.py$' | reveal --stdin --check
```
"Instant overview of all changes. Quality issues in changed files. No file reading required."

### For Codebase Onboarding

**Pain**: "New to a codebase. Where do I even start?"

**Message**:
```bash
reveal stats://./src          # Codebase health overview
reveal 'imports://.?circular' # Find architectural issues
reveal 'ast://.?complexity>10' # Find dragons
```
"Understand a codebase in minutes, not days."

### For Token Cost Optimization

**Pain**: "AI API costs are killing our budget."

**Message**: "At scale (100 reviews/month × 50 files × 7,500 tokens): Traditional = $75/month. With Reveal = $1.50/month. Same understanding, $73.50 saved."

---

## Real-World Stories

### The Meta Moment
"When I was building the `python://` adapter, I triggered a module shadowing bug. My local `types.py` was hiding Python's built-in `types` module. So I used Reveal to diagnose Reveal:
```bash
reveal python://module/types
```
A tool that debugs itself using its own diagnostic capabilities. That's when I knew we had something special."

### The v0.23.1 Release
"Four prompts. The agent loaded context, tested features on the codebase, updated versions, ran 465 tests, committed, tagged, pushed, triggered PyPI release. Total human typing: 25 words. This wasn't a demo—it's a real release, now live on PyPI."

### The Nginx Incident
"Remember that time your nginx config had two upstreams pointing to the same backend on the wrong port, and your $8K/month revenue site served 404s for 6 hours? Yeah, me too. `reveal nginx.conf --check` caught this in staging."

### The 209-Cert Outage
The N004 rule ("ACME challenge path inconsistency") exists because of a real production incident at sociamonials—209 SSL certificates failed to renew because server blocks had different root paths for `/.well-known/acme-challenge/`. Reveal now detects this pattern automatically.

### The Stale Bytecode Mystery
"You know that bug where your code changes don't work? Stale `.pyc` bytecode.
```bash
reveal python://debug/bytecode
```
Found 3 stale bytecode files in 0.3 seconds vs 30 minutes of confusion."

---

## Competitive Differentiation

### vs grep/find/cat
- **grep**: Text search, no structure understanding
- **find**: File discovery, no content analysis
- **cat**: Full file dump, no progressive disclosure
- **Reveal**: Structure-first, semantic understanding, progressive detail

### vs IDE Code Navigation
- **IDE**: Requires GUI, human-centric, not agent-accessible
- **Reveal**: CLI-native, agent-first design, programmatic access

### vs Tree-sitter directly
- **Tree-sitter**: Low-level AST, requires language expertise
- **Reveal**: High-level structure, unified interface across 42 languages

### vs LangChain/AutoGPT file tools
- **Existing tools**: Ad-hoc file loaders, don't compose
- **Reveal**: Unified protocol, progressive disclosure pattern, URI-based resources

### Unique Capabilities
1. **URI adapters**: Query databases, check SSL certs, analyze nginx—same pattern everywhere
2. **Quality rules**: 43+ built-in checks for bugs, complexity, security
3. **Agent-first UX**: Breadcrumbs suggest reveal commands, not "open in editor"
4. **Batch processing**: `--stdin` works with any content, including URIs
5. **Self-documenting**: `help://` system, `--capabilities` endpoint

---

## Voice & Philosophy

### Glass Box vs Black Box
"The dominant AI systems are black boxes. You can't see their reasoning. You can't audit their decisions. When they're wrong—and they're wrong a lot—you have no way to understand why.

Progressive disclosure is part of a different philosophy: glass box systems where structure is visible, reasoning is traceable, and you can inspect what's happening at every level."

### Semantic Infrastructure
"Reveal isn't working alone. It's one component in a semantic stack. When you treat meaning as a first-class concern—not text, not syntax, but semantic structure—you can build tools that compose naturally and amplify each other's value."

### The Missing Layer
"This isn't a bug in your agent. It's a missing layer in our infrastructure. Human developers scan, orient, then dive into what matters. AI agents can't skim. They read everything. Progressive disclosure—a UX pattern from the 1980s—we somehow forgot to build for AI agents."

### Why This Should Be a Standard
"Every agent framework solves this problem ad-hoc. LangChain has file loaders. AutoGPT has browsing tools. Cursor has codebase indexing. Each reinvents partial solutions that don't compose.

What's missing is a protocol—a shared convention for agent-readable resources. The pattern is simple: Orientation (what's here?), Navigation (what can I explore?), Extraction (give me exactly this). Any resource that exposes these three capabilities becomes agent-friendly."

---

## Documentation Inventory

### Marketing Articles (sil-website/docs/articles/)
| File | Lines | Focus | Status |
|------|-------|-------|--------|
| reveal-introduction.md | 599 | Philosophy, 7-layer stack, Beth synergy | Published, needs version update |
| reveal-for-ai-agents.md | 420 | Claude/Cursor/Copilot integration | Draft, needs version update |
| reveal-for-claude-code.md | 322 | Claude Code specific | Draft, needs version update |
| reveal-quickstart.md | 135 | 3-minute quick start | Draft |

### System Page (sil-website/docs/systems/)
| File | Lines | Focus | Status |
|------|-------|-------|--------|
| reveal.md | 361 | Product overview, economics | Published, needs v0.42 features |

### Research Documents (sil-website/docs/research/)
| File | Lines | Focus | Status |
|------|-------|-------|--------|
| PROGRESSIVE_DISCLOSURE_GUIDE.md | 933 | Deep implementation guide | Canonical |
| REVEAL_BETH_PROGRESSIVE_KNOWLEDGE_SYSTEM.md | 563 | Reveal + Beth synergy | Canonical |
| progressive-disclosure-system.md | 343 | Additional research | Research |

### Essays (sil-website/docs/essays/)
| File | Lines | Focus | Status |
|------|-------|-------|--------|
| PROGRESSIVE_DISCLOSURE_FOR_AI_AGENTS.md | 347 | Public essay | Published |

### Internal Docs (reveal project)
| File | Location | Focus |
|------|----------|-------|
| CHANGELOG.md | external-git/ | Version history |
| BUG_PREVENTION.md | internal-docs/case-studies/ | Bug analysis process |
| QUICK_START.md | external-git/ | 5-minute guide |
| AGENT_HELP.md | external-git/ | Agent reference |

---

## Gap Analysis

### Critical Gaps

#### 1. Version Mismatch (HIGH PRIORITY)
- Marketing docs reference v0.23-v0.31
- Current version is v0.42.0
- ~20 versions of features undocumented for marketing

#### 2. Missing Feature Documentation
Features not in marketing materials:
- `ssl://` adapter (compelling DevOps story)
- `--dir-limit` flag (solves node_modules pain)
- `--adapters` discovery
- N004 nginx rule (production incident prevention)
- Windows Batch analyzer
- CSV/TSV analyzer
- XML analyzer
- PowerShell analyzer
- INI/Properties analyzer
- `--capabilities` endpoint
- Hierarchical extraction syntax
- Universal `--stdin` URI support

#### 3. Missing Case Studies
- Only one internal case study
- No published customer/user stories
- Production incidents should become marketing content

### Medium Priority Gaps

#### 4. Missing Integration Guides
- No CI/CD pipeline examples
- No team onboarding documentation
- No MCP server integration

#### 5. Inconsistent Token Metrics
- Different docs cite different ranges
- Need single source of truth
- Missing per-feature efficiency breakdowns

#### 6. Competitive Positioning
- No "why reveal vs X" documentation
- No comparison matrix

### Nice-to-Have

#### 7. Video/Demo Content
- No video demonstrations
- No animated examples

#### 8. Language-Specific Guides
- No Python-specific guide
- No JavaScript/TypeScript guide
- No DevOps-specific guide

---

## Raw Materials

### Quotable Lines

From reveal-introduction.md:
- "You know that moment when Claude reads your 7,500-line Python file to answer a simple question like 'what does the `load_config` function do?'"
- "AI agents are amazing at reasoning. They're terrible at not reading everything."
- "This is insane. Not because Claude is bad. Because our tools are designed for humans with eyes, not agents with context windows."

From PROGRESSIVE_DISCLOSURE_FOR_AI_AGENTS.md:
- "This isn't a bug in your agent. It's a missing layer in our infrastructure."
- "We gave agents human interfaces and wondered why they struggled."
- "The agents are here. The infrastructure is catching up."
- "If progressive disclosure is obviously right—and I think the 150x efficiency gain makes the case—why don't we have it everywhere?"

From systems/reveal.md:
- "That's it. No flags, no configuration, just works."
- "Developers and AI agents waste time reading entire files when they only need to understand structure."

### Key Statistics
- 42 built-in analyzers
- 2,475+ tests
- 76% coverage
- 43+ quality rules
- 15+ URI adapters
- 25-30x average token reduction (measured across 300+ sessions)
- 150x single-file efficiency gain
- $47K/year savings per 1000 agents

### Validation Metrics (v0.24.0 dogfooding)
| Metric | Result |
|--------|--------|
| Files scanned | 571+ |
| Test suite | 465 tests passing (100%) |
| Token reduction | 10-150x confirmed |
| Complex functions found | 1,122 |
| Quality rules | 28 rules |
| Analyzers | 14 language-specific + TreeSitter |
| URI adapters | 6 |
| Architecture | 64% core module reduction |
| Real bugs discovered | 1 (bare except clause) |
| Overall grade | A |

---

## Next Steps for Marketing

### Immediate Actions
1. Update all version numbers to v0.42.0
2. Document ssl:// adapter (DevOps story)
3. Document --dir-limit (developer pain point)
4. Turn N004/cert outage into case study

### Content to Create
1. "Reveal for DevOps" article (ssl://, nginx, python://)
2. "Reveal for Large Codebases" article (--dir-limit, stats://, imports://)
3. CI/CD integration guide
4. Video demo: "50 tokens vs 7,500"

### Voice Development Questions
- How technical should marketing be?
- Lead with efficiency numbers or philosophy?
- Emphasize AI agent market or broader developer market?
- Position as SIL product or standalone tool?

---

*This document captures the state of reveal marketing intelligence as of 2026-01-20. Use for voice development, gap prioritization, and content planning.*
