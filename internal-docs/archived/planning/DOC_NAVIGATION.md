---
date: 2026-01-15
purpose: Navigation guide for internal documentation
audience: New maintainers, contributors
---

# Internal Documentation Navigation Guide

**Lost? Start here.**

---

## By Question

| Your Question | Document to Read |
|---------------|------------------|
| **What is Reveal's strategy?** | planning/POSITIONING_STRATEGY.md |
| **What should I build next?** | planning/PRIORITIES.md |
| **Why was decision X made?** | research/TLDR_FEEDBACK_ANALYSIS.md (example) |
| **What are the quality standards?** | ARCHITECTURAL_DILIGENCE.md |
| **How do V-rules work?** | VALIDATION_ROADMAP.md |
| **How do I release?** | releasing/PROCESS_NOTES.md |
| **What's the git adapter design?** | planning/GIT_ADAPTER_DESIGN.md |
| **How do AST queries work?** | planning/AST_QUERY_PATTERNS.md |

---

## By Document Type

### Strategic Planning (WHY)
- **POSITIONING_STRATEGY.md** - Product positioning, value prop, thesis statement
  - Use when: Writing external docs, making strategic decisions, evaluating features

### Execution Planning (WHAT, WHEN)
- **PRIORITIES.md** - Authoritative roadmap, feature tiers, single source of truth
  - Use when: Planning sprints, prioritizing work, checking feature status

- **GIT_ADAPTER_DESIGN.md** - Comprehensive git:// adapter specification
  - Use when: Implementing git features

- **AST_QUERY_PATTERNS.md** - AST query patterns and cookbook
  - Use when: Working with ast:// adapter

### Research & Analysis (RATIONALE)
- **research/TLDR_FEEDBACK_ANALYSIS.md** - tldr-pages comparison analysis
  - Use when: Understanding ecosystem patterns, evaluating similar feedback

- **research/MARKDOWN_SUPPORT_ISSUES.md** - Markdown analyzer gaps
  - Use when: Working on markdown features

- **research/JAVA_ANALYZER_COMPARISON.md** - Tree-sitter vs custom parser
  - Use when: Making analyzer architecture decisions

- **research/POPULAR_REPOS_TESTING*.md** - Real-world validation results
  - Use when: Checking production readiness

### Standards & Process (HOW)
- **ARCHITECTURAL_DILIGENCE.md** - Development quality standards and gates
  - Use when: Writing code, reviewing PRs

- **VALIDATION_ROADMAP.md** - V-rules strategy and implementation status
  - Use when: Adding validation rules, understanding self-checks

- **RUFF_ALIGNMENT.md** - Linting/style alignment with Ruff
  - Use when: Deciding rule coverage

- **releasing/PROCESS_NOTES.md** - Release procedure
  - Use when: Cutting a release

---

## By Workflow

### "I'm new to the project"
1. Start: README.md (this file)
2. Strategy: planning/POSITIONING_STRATEGY.md (understand mission)
3. Roadmap: planning/PRIORITIES.md (see what's planned)
4. Standards: ARCHITECTURAL_DILIGENCE.md (coding expectations)

### "I want to implement a feature"
1. Check: planning/PRIORITIES.md (is it on roadmap? what tier?)
2. Context: planning/POSITIONING_STRATEGY.md (does it align with strategy?)
3. Design: Relevant planning doc (e.g., GIT_ADAPTER_DESIGN.md)
4. Standards: ARCHITECTURAL_DILIGENCE.md (quality gates)

### "I want to understand a decision"
1. Strategic decision: planning/POSITIONING_STRATEGY.md
2. Feature decision: planning/PRIORITIES.md
3. Technical decision: research/ docs (look for analysis)
4. Process decision: ARCHITECTURAL_DILIGENCE.md or releasing/

### "I'm writing external docs"
1. Positioning: planning/POSITIONING_STRATEGY.md (thesis, value prop)
2. Features: planning/PRIORITIES.md (what's shipped, what's coming)
3. Avoid: Don't reference internal planning, TIA, Beth in public docs

---

## Document Relationships

```
POSITIONING_STRATEGY.md (WHY)
        ↓
    informs
        ↓
PRIORITIES.md (WHAT, WHEN)
        ↓
    references
        ↓
research/*.md (RATIONALE)
        ↓
    constrained by
        ↓
ARCHITECTURAL_DILIGENCE.md (HOW)
```

**Single Source of Truth Principle**:
- Strategy → POSITIONING_STRATEGY.md
- Roadmap → PRIORITIES.md
- Standards → ARCHITECTURAL_DILIGENCE.md
- Validation → VALIDATION_ROADMAP.md

**No duplication**: If multiple docs need same info, one owns it, others reference it.

---

## Anti-Patterns (Don't Do This)

❌ **Updating feature status in multiple places**
   - ✅ Do: Update PRIORITIES.md only

❌ **Writing strategic rationale in PRIORITIES.md**
   - ✅ Do: POSITIONING_STRATEGY.md for WHY, PRIORITIES.md for WHAT

❌ **Duplicating implementation details across docs**
   - ✅ Do: Write once in appropriate doc, reference from others

❌ **Treating research docs as roadmap**
   - ✅ Do: Extract decisions to PRIORITIES.md, keep research as archive

---

## Quick Reference Table

| Document | Lines | Type | Update Frequency |
|----------|-------|------|------------------|
| POSITIONING_STRATEGY.md | 436 | Strategic | Quarterly |
| PRIORITIES.md | 487 | Roadmap | Monthly |
| TLDR_FEEDBACK_ANALYSIS.md | 489 | Research | Archive (stable) |
| ARCHITECTURAL_DILIGENCE.md | 974 | Standards | Rarely |
| VALIDATION_ROADMAP.md | 613 | Process | Per V-rule release |
| GIT_ADAPTER_DESIGN.md | 1380 | Design | During implementation |

---

**Last updated**: 2026-01-15
**Maintainer**: Scott (with TIA)
