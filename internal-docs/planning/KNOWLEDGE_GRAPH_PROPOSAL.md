---
title: "Reveal Knowledge Graph Proposal"
date: 2026-01-01
updated: 2026-01-02
session_id: prairie-snow-0101
project: reveal
type: planning-document
beth_topics:
  - reveal
  - knowledge-graphs
  - front-matter
  - schema-validation
  - progressive-disclosure
related_docs:
  - ./KNOWLEDGE_GRAPH_ARCHITECTURE.md
  - ./KNOWLEDGE_GRAPH_GUIDE.md
  - ../../ROADMAP.md
  - ../archive/ARCHITECTURE_ADAPTER_DEPRECATION.md
status: approved
decision: option-a-generic-features
updates:
  - date: 2026-01-02
    session: garnet-ember-0102
    change: "architecture:// adapter deprecated, removed from roadmap"
---

# Reveal Knowledge Graph Proposal

**Purpose**: Decision document for positioning Reveal as a generic knowledge graph tool
**Date**: 2026-01-01
**Session**: prairie-snow-0101
**Decision**: Option A (Generic Features) - APPROVED

---

## The Question

**Should Reveal expand to support "Beth-like" knowledge graph features?**

More specifically:
- Front matter validation
- Related documents exploration
- Metadata querying
- Link integrity checking

**Answer**: **YES** - but as **generic patterns**, not Beth-specific features.

---

## Current State

### What Reveal Does Today (v0.28.0)

✅ **Extracts front matter** from markdown:
```bash
reveal file.md --frontmatter
# Shows: beth_topics, related_docs, session_id, etc.
```

✅ **Outputs JSON** for programmatic use:
```bash
reveal file.md --frontmatter --format=json | jq '.structure.frontmatter.data'
```

### What's Missing

❌ **No validation**: Can't check if front matter follows a schema
❌ **No link following**: Extracts `related_docs` but doesn't follow paths
❌ **No metadata queries**: Can't find "all files with beth_topics=reveal"
❌ **No quality checks**: Can't audit front matter completeness

**Gap**: Reveal extracts metadata but provides no tools to **validate** or **explore** it.

---

## The Insight

**Front matter + document linking is a UNIVERSAL pattern**, not Beth-specific:

| Tool | Pattern | Reveal Support Today |
|------|---------|---------------------|
| **Beth** | `beth_topics`, `related_docs`, PageRank scoring | ✅ Extracts, ❌ Validates |
| **Obsidian** | Properties, `[[wiki-links]]`, graph view | ✅ Extracts, ❌ Validates |
| **Hugo** | `tags`, `categories`, `series`, taxonomy | ✅ Extracts, ❌ Validates |
| **Jekyll** | YAML front matter, collections | ✅ Extracts, ❌ Validates |
| **Roam** | Page links, backlinks | ❌ No front matter |
| **Logseq** | Properties, bidirectional links | ✅ Extracts, ❌ Validates |

**Opportunity**: Position Reveal as the **CLI tool for knowledge graph construction** - not just code structure.

---

## Proposed Features (Generic, Not Beth-Specific)

### 1. Schema-Based Validation ⭐ HIGH VALUE

**Generic abstraction**: Any schema (Beth, Hugo, Obsidian, custom)

```bash
# Built-in schemas
reveal file.md --validate-schema beth
reveal file.md --validate-schema hugo
reveal file.md --validate-schema obsidian

# Custom schema
reveal file.md --validate-schema .reveal-schema.yaml
```

**Schema file format**:
```yaml
name: "Beth Schema"
required_fields: [session_id, beth_topics]
field_types:
  session_id: string
  beth_topics: list
validation_rules:
  - code: F003
    check: "'topics' not in fields or 'beth_topics' in fields"
```

**Use cases**:
- Hugo: Validate `title` and `date` before build
- Beth: Catch `topics` vs `beth_topics` mistakes
- Obsidian: Ensure properties conform to vault standards
- Custom: Any metadata schema you define

**Implementation**: 2-3 weeks, ships with `beth.yaml`, `hugo.yaml`, `obsidian.yaml`

---

### 2. Related Documents Viewer ⭐ MEDIUM VALUE

**Generic abstraction**: Follow any link field (configurable)

```bash
# Show immediate related docs
reveal file.md --related

# Follow links recursively (max depth 2)
reveal file.md --related --depth 2
```

**Configuration** (`.revealrc`):
```yaml
related_fields:
  - related_docs   # Beth-style
  - related        # Hugo-style
  - see_also       # Custom
```

**Use cases**:
- Beth: Explore session relationships
- Obsidian: See note network (without GUI)
- Hugo: Navigate post series
- Research: Citation networks

**Constraint**: Max depth 2 (avoids becoming graph crawler)

**Implementation**: 2-3 weeks, configurable link fields

---

### 3. Markdown URI Adapter ⭐ HIGH VALUE

**Generic abstraction**: Query markdown files by front matter

```bash
# Find files by field value
reveal markdown://sessions/?beth_topics=reveal
reveal markdown://content/?tags=python
reveal markdown://vault/?status=draft

# Missing field check
reveal markdown://?!beth_topics

# Multiple criteria
reveal markdown://?type=session&beth_topics=reveal
```

**Use cases**:
- Beth: Find sessions by topic (without Beth index)
- Hugo: Find posts by tag/category
- Obsidian: Query notes by property
- Generic: Any metadata-based file discovery

**Implementation**: 3-4 weeks, follows existing URI adapter pattern

---

### 4. Quality Checks ⭐ MEDIUM VALUE

**Generic abstraction**: Configurable quality metrics

```bash
# Single file check
reveal file.md --check-metadata

# Aggregate report
reveal docs/**/*.md --check-metadata --summary
```

**Metrics** (configurable):
- Front matter presence
- Required fields (schema-based)
- Link density (related_docs count)
- Topic coverage

**Use cases**:
- Beth: Audit session README quality
- Hugo: Pre-build validation
- Obsidian: Find orphan notes
- CI/CD: Quality gates

**Implementation**: 2 weeks, leverages validation framework

---

## What Reveal Should NOT Do

### ❌ Full Graph Traversal (Corpus-Wide)

**Why not**: Requires stateful index, violates reveal's architecture

**Instead**: Max depth 2 for `--related` (local exploration only)

**Who does this**: Beth, Obsidian graph view, Neo4j

---

### ❌ PageRank / Authority Scoring

**Why not**: Requires corpus-wide analysis, algorithm complexity

**Instead**: Provide raw material (metadata, links) for scoring systems

**Who does this**: Beth (PageRank), Google, academic citation tools

---

### ❌ Semantic Search

**Why not**: Requires NLP, embeddings, similarity scoring

**Instead**: Exact metadata matching (`reveal markdown://?field=value`)

**Who does this**: Beth, Obsidian search, dedicated search engines

---

## Architectural Principles

### 1. **Stateless by Design**

Reveal operates on **explicit inputs** (files, globs, URIs), never maintains an index.

✅ **Can do**: Validate file, follow explicit links, query directory tree
❌ **Cannot do**: Find all backlinks, compute PageRank, build full graph

---

### 2. **Generic Core, Specific Examples**

Don't build "Beth mode" - build **generic features** with **Beth examples**.

❌ **Anti-pattern**: `reveal --beth-validate`, `reveal --obsidian-graph`
✅ **Better**: `reveal --validate-schema beth`, `reveal --related` (works for all)

---

### 3. **Examples Over Configuration**

Ship with **reference schemas** (Beth, Hugo, Obsidian), users customize.

**Ships with reveal**:
- `reveal/schemas/beth.yaml`
- `reveal/schemas/hugo.yaml`
- `reveal/schemas/obsidian.yaml`

**User creates**: `.reveal-schema.yaml` in project root

---

### 4. **Progressive Disclosure for Knowledge Graphs**

Extend reveal's core pattern to relationships:

| Level | Code | Knowledge Graph |
|-------|------|-----------------|
| **Orient** | `reveal file.py` | `reveal file.md --frontmatter` |
| **Navigate** | `reveal file.py --outline` | `reveal file.md --related` |
| **Focus** | `reveal file.py function` | `reveal file.md --validate` |

---

## Implementation Roadmap

### Phase 1: Schema Validation (v0.29.0) - Jan 2025

**Effort**: 2-3 weeks
**Features**:
- Schema file format
- Built-in schemas (beth, hugo, obsidian)
- `--validate-schema` CLI flag
- Validation rules engine
- Error reporting

**Deliverable**: `reveal file.md --validate-schema beth`

---

### Phase 2: Link Following (v0.30.0) - Feb 2025

**Effort**: 2-3 weeks
**Features**:
- `--related` CLI flag
- `--depth N` parameter (max 2)
- `.revealrc` config
- Link field detection
- Tree view output

**Deliverable**: `reveal file.md --related --depth 2`

**Update (2026-01-02):** The `architecture://` adapter originally planned for v0.30.0 has been deprecated. Layer violation detection is adequately handled by the I003 rule (shipped in v0.28.0). See `../archive/ARCHITECTURE_ADAPTER_DEPRECATION.md` for decision rationale.

---

### Phase 3: Metadata Queries (v0.31.0) - Mar 2025

**Effort**: 3-4 weeks
**Features**:
- `markdown://` URI adapter
- Query parser
- Field filtering
- Wildcard support
- Integration with other features

**Deliverable**: `reveal markdown://?beth_topics=reveal`

---

### Phase 4: Quality Checks (v0.32.0) - Apr 2025

**Effort**: 2 weeks
**Features**:
- `--check-metadata` flag
- Aggregate reporting
- Configurable metrics
- Schema integration

**Deliverable**: `reveal docs/**/*.md --check-metadata --summary`

---

### Phase 5: Documentation (v0.33.0) - May 2025

**Effort**: 1-2 weeks
**Deliverables**:
- `KNOWLEDGE_GRAPH_GUIDE.md` (user guide)
- `BETH_INTEGRATION_GUIDE.md` (Beth examples)
- `OBSIDIAN_INTEGRATION_GUIDE.md` (Obsidian examples)
- `HUGO_INTEGRATION_GUIDE.md` (Hugo examples)
- Update `AGENT_HELP.md`

---

## Success Metrics

### Adoption
- 3+ different schemas actively used
- 10+ custom schemas created by users
- 5+ blog posts about Reveal for knowledge graphs

### Technical
- Schema validation: <50ms
- `--related --depth 2`: <500ms for 10 files
- `markdown://` queries: <2s for 1000 files

### Quality
- 200+ tests for new features
- 100% coverage on validation logic
- Zero breaking changes

---

## Benefits for Beth/TIA

Even though features are generic, Beth benefits:

### 1. **Better Session READMEs**

```bash
# Catch mistakes before commit
reveal README.md --validate-schema beth

# Pre-commit hook
reveal README.md --validate-schema beth || exit 1
```

### 2. **Local Exploration Without Beth Index**

```bash
# Find related sessions (no Beth needed)
reveal markdown://sessions/?beth_topics=reveal

# Explore session graph
reveal README.md --related --depth 2
```

### 3. **Quality Enforcement**

```bash
# Audit all session READMEs
reveal sessions/**/*.md --check-metadata --summary

# Output:
# 3,377 sessions checked:
#   ✅ 3,200 have beth_topics (94.8%)
#   ⚠️  177 missing beth_topics
#   ⚠️  1,200 have 0 related_docs (low connectivity)
```

### 4. **CI/CD Integration**

```yaml
# .github/workflows/validate-sessions.yml
- name: Validate session metadata
  run: |
    for session in sessions/*/README*.md; do
      reveal "$session" --validate-schema beth || exit 1
    done
```

---

## Benefits Beyond Beth

### Hugo Users

```bash
# Pre-build validation
hugo-check:
  reveal content/**/*.md --validate-schema hugo --summary
```

### Obsidian Users

```bash
# CLI for vault quality
obsidian-audit:
  reveal vault/**/*.md --validate-schema obsidian --check-metadata
```

### Generic Documentation

```bash
# Custom schema for any project
reveal docs/**/*.md --validate-schema .reveal-schema.yaml
```

---

## Positioning

### Current Positioning

**"Reveal is a code structure exploration tool"**
- Primary use case: Navigate large codebases
- Users: Developers, AI agents
- Value prop: 10-150x token reduction

### New Positioning

**"Reveal is a progressive disclosure tool for code AND knowledge"**
- Primary use cases: Code exploration + knowledge graph construction
- Users: Developers, researchers, technical writers, AI agents
- Value props:
  - 10-150x token reduction (code)
  - Schema validation (quality)
  - Link exploration (relationships)
  - Metadata queries (discovery)

### Messaging

**Tagline**: "Progressive disclosure for code and knowledge graphs"

**Homepage**:
- "Explore codebases without reading full files" (existing)
- "Build and validate knowledge graphs in markdown" (new)
- "Schema validation for Hugo, Jekyll, Obsidian, and custom formats" (new)

**Target audiences**:
1. **Developers** (existing): Code exploration, progressive disclosure
2. **Technical writers** (new): Hugo/Jekyll validation, link checking
3. **Researchers** (new): Knowledge graph construction, citation networks
4. **AI agents** (existing + new): Efficient code + metadata access

---

## Decision Points

### Option A: Generic Knowledge Graph Features (Recommended)

**Pros**:
- Broader appeal (Hugo, Obsidian, Jekyll users)
- Positions Reveal as generic tool (not TIA-specific)
- Natural extension of existing front matter support
- Maintains architectural purity (stateless)

**Cons**:
- More design work (generic abstractions)
- Longer timeline (5 releases vs 2)
- Need to support multiple schemas

**Recommendation**: ✅ **YES** - this is the right strategic direction

---

### Option B: Beth-Specific Features Only

**Pros**:
- Faster implementation (no generic abstraction)
- Directly serves TIA needs
- Simpler design

**Cons**:
- Limits Reveal's appeal
- Creates Beth dependency perception
- Missed opportunity for broader adoption

**Recommendation**: ❌ **NO** - too narrow

---

### Option C: No Knowledge Graph Features

**Pros**:
- Simplest (keep reveal focused on code)
- No new development needed

**Cons**:
- Leaves gap between extraction and validation
- Missed opportunity (front matter already supported)
- Users will build these tools themselves anyway

**Recommendation**: ❌ **NO** - opportunity cost too high

---

## Recommended Path Forward

### 1. **Adopt Generic Knowledge Graph Features** (Option A)

Build features that work for **any metadata schema**, ship with **Beth/Hugo/Obsidian examples**.

### 2. **5-Phase Roadmap** (Jan-May 2025)

- Phase 1: Schema validation
- Phase 2: Link following
- Phase 3: Metadata queries
- Phase 4: Quality checks
- Phase 5: Documentation

### 3. **Maintain Architectural Principles**

- Stateless design (no corpus index)
- Max depth 2 for link following
- Schema-agnostic core, schema-aware extensions

### 4. **Document Patterns, Not Tools**

Create guides showing how to use Reveal for:
- Beth-style knowledge graphs
- Obsidian vaults
- Hugo static sites
- Custom schemas

---

## Next Steps

### Immediate

1. **Review this proposal** - Discuss, refine, approve/reject
2. **If approved**: Start Phase 1 design
3. **If rejected**: Document rationale, close proposal

### Phase 1 Design (If Approved)

1. Schema file format specification
2. Built-in schemas (beth, hugo, obsidian)
3. Validation rules DSL
4. Implementation plan
5. Tests specification

### Timeline

- **Week 1 (Jan 2-8)**: Design review + Phase 1 spec
- **Week 2-3 (Jan 9-22)**: Phase 1 implementation
- **Week 4 (Jan 23-29)**: Testing + docs
- **Feb 1**: Release v0.29.0 with schema validation

---

## Appendices

### Appendix A: Created Documents

1. **`REVEAL_KNOWLEDGE_GRAPH_ARCHITECTURE.md`**
   - Full technical architecture
   - Generic patterns analysis
   - Architectural principles
   - Feature designs (detailed)
   - Reference implementations
   - 5-phase roadmap

2. **`KNOWLEDGE_GRAPH_GUIDE.md`**
   - User-facing guide (ships with reveal)
   - Quick start examples
   - Use cases (Hugo, Obsidian, Beth, custom)
   - Workflows + best practices
   - Troubleshooting

3. **`REVEAL_KNOWLEDGE_GRAPH_PROPOSAL.md`** (this document)
   - Executive summary
   - Decision points
   - Recommended path
   - Next steps

### Appendix B: Reference Links

- Session `stormy-gust-1213`: Front matter implementation (Dec 2025)
- `/home/scottsen/src/projects/SIL/docs/BETH_FRONT_MATTER_GUIDE.md`: Beth schema
- `/home/scottsen/src/projects/SIL/docs/research/information-architecture/REVEAL_BETH_PROGRESSIVE_KNOWLEDGE_SYSTEM.md`: Integration architecture

---

## Summary

**Question**: Should Reveal support knowledge graph features?

**Answer**: **YES** - as **generic patterns** (not Beth-specific).

**Why**: Front matter + linking is universal across Hugo, Obsidian, Jekyll, Beth, etc.

**How**: 5 phases (schema validation, link following, metadata queries, quality checks, docs)

**When**: Jan-May 2025 (5 releases)

**Impact**: Positions Reveal as the **CLI tool for knowledge graph construction**, not just code exploration.

**Next**: Review proposal → Design Phase 1 → Implement schema validation
