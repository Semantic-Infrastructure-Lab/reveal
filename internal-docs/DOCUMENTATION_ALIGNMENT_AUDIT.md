# Reveal Documentation Alignment Audit

**Date:** 2026-01-03
**Session:** cloudy-steam-0103
**Auditor:** TIA (Chief Semantic Agent)
**Status:** CRITICAL MISALIGNMENTS FOUND

---

## Executive Summary

Comprehensive audit of Reveal's documentation revealed **5 critical misalignments** between actual implementation, planning documents, and public-facing documentation. The most serious issue is a **strategic direction mismatch** between the current roadmap (knowledge-graph focused) and the most powerful expansion path (cross-resource URI composition).

**Impact:**
- Users see incomplete schema list in CHANGELOG/ROADMAP
- Broken documentation references to non-existent planning docs
- Roadmap pursuing less impactful features than alternatives
- v0.29.0 work complete but not released/tagged

---

## Critical Issues Found

### Issue #1: v0.29.0 Incomplete Schema Documentation ⚠️ HIGH

**Problem:** CHANGELOG and ROADMAP only mention 3 schemas, but 5 exist.

**Evidence:**
```bash
$ ls reveal/schemas/frontmatter/*.yaml
beth.yaml
hugo.yaml
jekyll.yaml  ← Missing from CHANGELOG/ROADMAP
mkdocs.yaml  ← Missing from CHANGELOG/ROADMAP
obsidian.yaml
```

**Documentation State:**
- ✅ **README.md:** CORRECT - Lists all 5 schemas
- ❌ **CHANGELOG.md:** WRONG - Only lists beth, hugo, obsidian
- ❌ **ROADMAP.md:** WRONG - Only lists beth, hugo, obsidian

**Impact:**
- Users unaware of Jekyll/MkDocs schemas
- GitHub Pages users (1M+) missing Jekyll schema
- Python docs users missing MkDocs schema

**Fix Required:**
- Update CHANGELOG.md v0.29.0 section
- Update ROADMAP.md v0.29.0 section
- Add Jekyll/MkDocs details to both docs

---

### Issue #2: Broken Planning Document References ⚠️ MEDIUM

**Problem:** ROADMAP.md references non-existent planning documents.

**Evidence:**
```bash
# ROADMAP.md mentions these files:
internal-docs/planning/KNOWLEDGE_GRAPH_ARCHITECTURE.md  ← DOES NOT EXIST
internal-docs/planning/KNOWLEDGE_GRAPH_GUIDE.md         ← DOES NOT EXIST

# Referenced 3 times in roadmap (lines 237, 274, 298)
```

**Files That DO Exist:**
```
ADAPTER_DEVELOPER_GUIDE.md
ADVANCED_URI_SCHEMES.md
PRACTICAL_CODE_ANALYSIS_ADAPTERS.md
URI_ADAPTERS_MASTER_SPEC.md
... (13 planning docs total)
```

**Impact:**
- Broken documentation trail
- Contributors can't find design rationale
- Knowledge graph features lack design docs

**Fix Required:**
- Either create the missing docs OR
- Remove references and point to existing docs OR
- Update references to correct file names

---

### Issue #3: Strategic Direction Mismatch 🔴 CRITICAL

**Problem:** Roadmap prioritizes knowledge-graph features over more powerful cross-resource URI composition.

**Current Roadmap (v0.30-v0.32):**
- v0.30.0: Link Following & Knowledge Graph Navigation
- v0.31.0: markdown:// adapter + metadata queries
- v0.32.0: Polish for v1.0

**Strategic Analysis Shows:**
Priority should be:
1. **diff://** - Cross-resource comparison (highest ROI)
   - Works with ALL adapters (mysql://, file://, ast://, etc.)
   - Solves schema drift, refactoring validation
   - Foundation for composition pattern
   - 4-6 weeks effort

2. **time://** - Temporal exploration (developer delight)
   - Git integration for time-travel debugging
   - Composes with diff:// for powerful workflows
   - 4 weeks effort

3. **markdown://** - Metadata queries (incremental)
   - Only useful after diff:// + time:// exist
   - Becomes MORE powerful when composable
   - 2-3 weeks effort

**Evidence from ADVANCED_URI_SCHEMES.md:**
- Explicitly prioritizes: ast:// (✅ DONE) → diff:// → query://
- markdown:// listed as future specialized adapter
- Knowledge graph features not in advanced URI roadmap

**Impact:**
- Pursuing narrow features (markdown:// alone) over broad ones (diff://)
- Missing opportunity to prove composition model
- Delaying highest-value features

**Recommendation:**
- **Revise roadmap** to prioritize diff:// → time:// → markdown://
- Knowledge graph features still valuable but AFTER composition adapters
- This enables: `diff://time:markdown://docs@v1 vs markdown://docs@v2`

---

### Issue #4: Version Release Mismatch ⚠️ MEDIUM

**Problem:** v0.29.0 work is complete but not released/tagged.

**Evidence:**
```bash
$ reveal --version
reveal 0.28.0

# But CHANGELOG.md shows:
## [0.29.0] - 2026-01-03

# And ROADMAP.md says:
### v0.29.0 ✅ SHIPPED (Jan 2026)
```

**Git Status:**
- Latest commit: "feat(schemas): Implement front matter schema validation - Phase 1"
- v0.29.0 work done in photon-warrior-0103 session
- Ready for release but not tagged/pushed

**Impact:**
- Documentation claims v0.29.0 is shipped but it's not
- Users on v0.28.0 can't access Jekyll/MkDocs schemas
- PyPI still has v0.28.0

**Fix Required:**
- Either:
  - **Option A:** Tag and release v0.29.0 now
  - **Option B:** Move v0.29.0 to Unreleased section until tagged
  - **Option C:** Release as v0.30.0 (5-schema release)

**From Previous Session (photon-warrior-0103):**
> Status: Production-ready feature set, web-validated, comprehensively tested.
> Ready for v0.29.1 or v0.30.0 release.

---

### Issue #5: imports:// Adapter Status Unclear ⚠️ LOW

**Problem:** Conflicting information about imports:// implementation status.

**Evidence:**
```bash
# ROADMAP.md (v0.28.0) says:
- `imports://` adapter for multi-language import analysis ✅ SHIPPED

# PRACTICAL_CODE_ANALYSIS_ADAPTERS.md says:
### Priority 1: Immediate Need (v0.26-v0.27) 🔴
#### 1. `imports://` - Import Graph Analysis
**Status**: Not in existing roadmap - **Genuinely New**
```

**Resolution:**
- imports:// IS shipped in v0.28.0 (per roadmap)
- PRACTICAL_CODE_ANALYSIS_ADAPTERS.md is outdated (dated 2025-12-22)
- Need to update planning doc to reflect shipped status

---

## Alignment Matrix

| Document | v0.29.0 Schemas | Strategic Direction | Planning Refs | Version Status |
|----------|----------------|---------------------|---------------|----------------|
| **README.md** | ✅ 5 schemas | N/A | N/A | ❌ Says v0.29.0+ |
| **CHANGELOG.md** | ❌ 3 schemas | N/A | N/A | ❌ Says 2026-01-03 |
| **ROADMAP.md** | ❌ 3 schemas | ❌ KG focus | ❌ Broken links | ❌ Says SHIPPED |
| **Actual Code** | ✅ 5 schemas | N/A | N/A | ✅ v0.28.0 |
| **ADVANCED_URI_SCHEMES.md** | N/A | ✅ diff:// first | ✅ Valid | N/A |
| **PRACTICAL_ADAPTERS.md** | N/A | ⚠️ Outdated | ✅ Valid | ⚠️ Pre-v0.28 |

---

## Recommended Fixes (Priority Order)

### Immediate (Before Any Release)

1. **Update CHANGELOG.md v0.29.0 section**
   - Add Jekyll and MkDocs schemas
   - Update schema count: 3 → 5
   - Add dogfooding section (Hugo fix, Beth validation results)

2. **Update ROADMAP.md v0.29.0 section**
   - Add Jekyll and MkDocs schemas
   - Update schema count: 3 → 5
   - Add web-validation details

3. **Fix broken planning doc references**
   - Remove references to KNOWLEDGE_GRAPH_ARCHITECTURE.md
   - Remove references to KNOWLEDGE_GRAPH_GUIDE.md
   - OR create placeholder docs with TODOs

### Strategic (Before v0.30 Planning)

4. **Revise ROADMAP.md strategic direction**
   - v0.30.0: diff:// adapter (cross-resource comparison)
   - v0.31.0: time:// adapter (temporal exploration)
   - v0.32.0: markdown:// + knowledge graph (composable queries)
   - Rationale: Composition adapters unlock exponential value

5. **Update PRACTICAL_CODE_ANALYSIS_ADAPTERS.md**
   - Mark imports:// as ✅ SHIPPED (v0.28.0)
   - Update status dates
   - Align with current roadmap

### Release Decision

6. **Decide on v0.29.0 vs v0.30.0**
   - **Option A (v0.29.0):** Tag current code, quick release
   - **Option B (v0.30.0):** Market as "5 Built-in Schemas" major release
   - **Recommendation:** v0.30.0 for marketing impact

---

## Files Requiring Updates

### High Priority
- [ ] `CHANGELOG.md` - Add Jekyll/MkDocs to v0.29.0
- [ ] `ROADMAP.md` - Add Jekyll/MkDocs to v0.29.0
- [ ] `ROADMAP.md` - Fix broken planning doc refs
- [ ] `ROADMAP.md` - Revise v0.30-v0.32 strategic direction

### Medium Priority
- [ ] `internal-docs/planning/PRACTICAL_CODE_ANALYSIS_ADAPTERS.md` - Update status
- [ ] Create `KNOWLEDGE_GRAPH_ARCHITECTURE.md` OR remove references

### Low Priority
- [ ] Update all version references to align
- [ ] Add strategic rationale to roadmap decisions

---

## Strategic Recommendation

**Proposed Roadmap Revision:**

```markdown
### v0.30.0 (Q1 2026): 5 Built-in Schemas + Dogfooding 🚀

**Five Production-Ready Schemas:**
- ✅ beth - TIA session READMEs
- ✅ hugo - Static sites (dogfooded on SIF website)
- ✅ jekyll - GitHub Pages (1M+ users)
- ✅ mkdocs - Python documentation (FastAPI, NumPy patterns)
- ✅ obsidian - Knowledge bases

**Status:** READY TO SHIP (1,292 tests passing, web-validated)

---

### v0.31.0 (Q2 2026): diff:// Adapter - Cross-Resource Comparison

**Composition Foundation:**
```bash
diff://mysql://prod vs mysql://staging       # Schema drift
diff://file:v1:app.py vs file:main:app.py   # Refactoring
diff://ast:v1:./src vs ast:v2:./src         # Structure changes
```

**Why First:**
- Works with ALL existing adapters (10x leverage)
- Proves composition model for future adapters
- Solves real pain (schema evolution, refactoring validation)

**Effort:** 4-6 weeks

---

### v0.32.0 (Q3 2026): time:// Adapter - Temporal Exploration

**Time-Travel Debugging:**
```bash
time://mysql://prod@2025-11-01     # Schema 2 months ago
time://ast://./src@abc123          # Code at specific commit
diff://time:file:@v1 vs file:@v2   # Compositional power
```

**Why Second:**
- Composes with diff:// for powerful workflows
- Natural Git integration
- Foundation for semantic:// later

**Effort:** 4 weeks

---

### v0.33.0 (Q3 2026): markdown:// + Knowledge Graph Features

**Now Composable:**
```bash
markdown://docs/?beth_topics=reveal              # Metadata queries
diff://time:markdown://docs@v1 vs markdown://v2  # Compositional
```

**Knowledge Graph Features:**
- `--related` flag for document navigation
- Metadata quality checks
- Topic coverage analysis

**Why Third:**
- MORE powerful because it composes with diff:// and time://
- Incremental value on proven foundation

**Effort:** 3-4 weeks
```

**Result:** By v0.33.0, users can do:
```bash
reveal diff://time:markdown://sessions@2025-12-01 vs markdown://sessions \
  --related --depth 2 --validate-schema beth
```

This is 10x more powerful than markdown:// alone.

---

## Next Steps

1. **Review with Scott:** Approve strategic direction change
2. **Update documents:** Apply fixes to CHANGELOG, ROADMAP
3. **Release decision:** v0.29.0 or v0.30.0?
4. **Tag and release:** Complete v0.29/v0.30 ship

---

## Appendix: Document Inventory

**Public Documentation (external-git/):**
- README.md - User-facing feature guide
- CHANGELOG.md - Version history
- ROADMAP.md - Public roadmap
- docs/SCHEMA_VALIDATION_GUIDE.md - Schema validation reference
- docs/LINK_VALIDATION_GUIDE.md - Link validation reference
- reveal/AGENT_HELP.md - Agent-focused guide

**Planning Documentation (internal-docs/planning/):**
- ADVANCED_URI_SCHEMES.md - Future URI adapters
- PRACTICAL_CODE_ANALYSIS_ADAPTERS.md - Code analysis needs
- URI_ADAPTERS_MASTER_SPEC.md - Core adapter architecture
- ADAPTER_DEVELOPER_GUIDE.md - Creating custom adapters
- ... 9 more planning docs

**Status:** 13 planning docs exist, 2 referenced docs missing

---

**Audit Complete:** 2026-01-03
**Confidence Level:** VERY HIGH (comprehensive cross-reference analysis)
**Action Required:** IMMEDIATE (before any v0.29/v0.30 release)
