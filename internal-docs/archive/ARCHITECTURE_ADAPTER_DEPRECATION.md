---
title: "Architecture:// Adapter Deprecation Decision"
date: 2026-01-02
session_id: garnet-ember-0102
project: reveal
type: decision-document
status: deprecated
beth_topics:
  - reveal
  - roadmap
  - architecture
  - deprecation
  - planning
related_docs:
  - ../../ROADMAP.md
  - ../planning/KNOWLEDGE_GRAPH_PROPOSAL.md
---

# Architecture:// Adapter Deprecation

**Decision**: DEPRECATED - Feature removed from roadmap
**Date**: 2026-01-02
**Session**: garnet-ember-0102
**Decided by**: Scott (SIL founder)

---

## Summary

The `architecture://` URI adapter originally planned for v0.30.0 has been **deprecated and removed from the roadmap**. Layer violation detection is already adequately handled by the I003 rule (shipped in v0.28.0). A dedicated URI adapter was deemed too narrow in scope and lower value compared to knowledge graph features.

---

## What Was Planned

### Original v0.30.0 Scope

**`architecture://` adapter** - Architecture rule validation:
```bash
reveal architecture://src               # Check all architecture rules
reveal 'architecture://src?violations'   # List violations only
reveal architecture://src/routes         # Check specific layer
```

**Planned Features:**
- Layer boundary enforcement (presentation → service → data)
- Custom dependency rules via `.reveal.yaml` (architecture section)
- Pattern compliance validation
- CI/CD integration for architecture governance

**Estimated Implementation:** 3-4 weeks

---

## Why It Was Deprecated

### 1. I003 Already Handles Core Use Case

**I003 shipped in v0.28.0** and provides layer violation detection:

```yaml
# .reveal.yaml
architecture:
  layers:
    - name: "services"
      paths: ["src/services/**"]
      allow_imports: ["src/repositories"]
      deny_imports: ["src/api"]
```

```bash
# Already works today:
reveal src/services/user.py --check
# Output: I003: Layer violation - services can't import from api
```

**architecture:// would have added:**
- Query interface (`architecture://src?violations`)
- Dedicated URI adapter for architecture checks
- Slightly nicer output formatting

**This is a convenience wrapper, not a new capability.**

---

### 2. No Value Rating in Proposal

The KNOWLEDGE_GRAPH_PROPOSAL.md explicitly rated features:

| Feature | Value Rating |
|---------|-------------|
| Schema Validation | ⭐ **HIGH** |
| Markdown URI Adapter | ⭐ **HIGH** |
| Related Documents | ⭐ MEDIUM |
| Quality Checks | ⭐ MEDIUM |
| **architecture://** | ❓ **NONE** |

**Red flag:** No explicit value assessment suggests insufficient planning/demand.

---

### 3. No Design Document

Unlike knowledge graph features (which have detailed designs), architecture:// had:
- ❌ No design document
- ❌ No user research
- ❌ No clear differentiation from I003
- ❌ ROADMAP noted: "ARCHITECTURE_ADAPTER_PLAN.md (to be created)"

**Starting implementation without a design is risky.**

---

### 4. Narrow Target Audience

**Who would use it:**
- ✅ Large teams with formal architecture rules
- ✅ Projects with explicit `.reveal.yaml` layer definitions

**Who would NOT use it:**
- ❌ Small projects without formal architecture
- ❌ Documentation-focused users (Hugo, Obsidian, Beth)
- ❌ Individual developers exploring codebases
- ❌ Anyone without `.reveal.yaml` layer config

**Market size:** Niche compared to knowledge graph features (millions of Hugo/Obsidian/Beth users).

---

### 5. Competes with Existing Tools

**Architecture validation space is crowded:**
- ArchUnit (Java)
- NDepend (.NET)
- Dependency Cruiser (JavaScript)
- ESLint no-restricted-imports (JavaScript)
- Golang linters (staticcheck, golangci-lint)

**Reveal's differentiation is progressive disclosure and knowledge graphs, not architecture governance.**

---

### 6. Knowledge Graph Features Have Higher ROI

**Strategic value comparison:**

| Dimension | architecture:// | Knowledge Graph Features |
|-----------|----------------|--------------------------|
| **Market size** | Niche (enterprise teams) | Broad (Hugo/Obsidian/Beth users) |
| **Differentiation** | Low (many competitors) | High (no good CLI tools) |
| **Implementation** | 3-4 weeks | 2-3 weeks per feature |
| **Value rating** | None | HIGH (2 features) |
| **Strategic fit** | Tangential | Core to vision expansion |

**Better ROI:** Focus on HIGH VALUE knowledge graph features.

---

## Decision Rationale

### Primary Reasons

1. **I003 sufficient**: Existing rule handles 90% of use case
2. **No demonstrated demand**: No users requesting this
3. **Lower strategic value**: Doesn't advance knowledge graph vision
4. **Resource allocation**: 3-4 weeks better spent on HIGH VALUE features
5. **Crowded market**: Many existing architecture validation tools

### Secondary Reasons

6. Narrow target audience (requires `.reveal.yaml`)
7. No design document (insufficient planning)
8. No value rating in proposal (lack of conviction)
9. Duplicates existing I003 functionality
10. Not aligned with Reveal's core differentiation

---

## What Happens Instead

### Updated v0.30.0 Scope

**Focus:** Link Following & Knowledge Graph Navigation

**Features:**
- `--related` flag for document relationship exploration
- Configurable link fields (related_docs, see_also, references)
- Tree view of document relationships
- Works with Beth, Hugo, Obsidian, custom patterns

**Implementation:** 2-3 weeks (vs 5-7 weeks with architecture://)

**Value:** ⭐ MEDIUM (vs ❓ NONE for architecture://)

---

## Future Consideration

### Could architecture:// Return?

**Possible scenarios for reconsidering:**

1. **User demand emerges**: 5+ users explicitly request this feature
2. **Enterprise adoption**: Large teams adopt Reveal and need advanced architecture governance
3. **Clear differentiation**: Find unique angle vs ArchUnit/NDepend
4. **Post-v1.0**: After knowledge graph features ship and core is stable

**Criteria for revival:**
- Must have demonstrated demand (not speculation)
- Must have clear design document
- Must differentiate from I003 in meaningful way
- Must not compete with higher-value features

**Timeline:** Earliest consideration would be post-v1.0 (Q4 2026+)

---

## Lessons Learned

### Planning Insights

1. **Value ratings matter**: Features without explicit HIGH/MEDIUM/LOW ratings are risky
2. **Design before roadmap**: Don't schedule features without design documents
3. **Beware of feature creep**: Adding "one more URI adapter" dilutes focus
4. **Check existing capabilities**: I003 already existed, reducing architecture:// value
5. **Strategic alignment**: Every feature should advance core vision

### Process Improvements

**For future feature proposals:**
- ✅ Require explicit value rating (HIGH/MEDIUM/LOW)
- ✅ Require design document before roadmap inclusion
- ✅ Check for overlap with existing features
- ✅ Validate against strategic vision
- ✅ Estimate market size / user demand

---

## References

**Roadmap Changes:**
- Removed from: `ROADMAP.md` v0.30.0 section
- Deprecation note added to v0.30.0

**Related Documents:**
- `internal-docs/planning/KNOWLEDGE_GRAPH_PROPOSAL.md` - Value ratings and strategic direction
- `reveal/rules/imports/I003.py` - Existing layer violation detection
- `ROADMAP.md` lines 197-216 - Updated v0.30.0 scope

**Session Context:**
- Session: garnet-ember-0102
- User question: "is architecture:// really the highest value feature?"
- Analysis revealed: No value rating, no design doc, I003 already exists
- Decision: Deprecate and focus on knowledge graph features

---

## Keywords

reveal, architecture, deprecation, roadmap, planning, I003, layer-violations, knowledge-graph, strategic-planning, feature-prioritization, value-assessment
