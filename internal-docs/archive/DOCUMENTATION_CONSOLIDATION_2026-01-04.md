# Reveal Documentation Consolidation Plan

**Session**: rainbow-palette-0104
**Date**: 2026-01-04
**Status**: Proposed
**Purpose**: Diligent cleanup to align docs with DOCUMENTATION_STRUCTURE_GUIDE

---

## Executive Summary

Reveal has comprehensive documentation (64 markdown files) but violates its own structure guide in several ways:
- ❌ **5 root-level session artifacts** should be in internal-docs/
- ❌ **1 untracked planning doc** blocked by .gitignore
- ❌ **Naming confusion** between user/planning guides
- ✅ **Core structure is sound** (docs/, reveal/, internal-docs/)

**Estimated cleanup effort**: 30 minutes

---

## Current Documentation Landscape

### Total: 64 Markdown Files

**Organized by location:**

```
Root Level (13)
├── README.md ✅
├── CHANGELOG.md ✅
├── CHANGELOG.archive.md ✅
├── CONTRIBUTING.md ✅
├── INSTALL.md ✅
├── RELEASING.md ✅
├── ROADMAP.md ✅ (has uncommitted changes)
├── SECURITY.md ✅
├── AI_DIFF_USAGE.md ❌ (should be in docs/)
├── CODE_REVIEW_IMPROVEMENTS.md ❌ (session artifact)
├── MYSQL_ADAPTER_TEST_RESULTS.md ❌ (session artifact)
├── POST_v0.29.0_CODE_QUALITY.md ❌ (session artifact)
└── RELEASE_READINESS_v0.29.0.md ❌ (session artifact)

docs/ (4 + 1 example)
├── LINK_VALIDATION_GUIDE.md ✅
├── PRODUCTION_TESTING_GUIDE.md ✅
├── SCHEMA_VALIDATION_GUIDE.md ✅
├── WHY_TYPED.md ✅
└── mysql-health-checks.example.yaml ✅

reveal/ (13 help files)
├── AGENT_HELP.md ✅
├── AGENT_HELP_FULL.md ✅
├── ANALYZER_PATTERNS.md ✅
├── ANTI_PATTERNS.md ✅
├── CONFIGURATION_GUIDE.md ✅
├── COOL_TRICKS.md ✅
├── DUPLICATE_DETECTION_GUIDE.md ⚠️ (naming collision)
├── HELP_SYSTEM_GUIDE.md ✅
├── HTML_GUIDE.md ✅
├── MARKDOWN_GUIDE.md ✅
├── RELEASE_GUIDE.md ✅
├── REVEAL_ADAPTER_GUIDE.md ✅
└── SCHEMA_VALIDATION_HELP.md ✅

reveal/adapters/ (2 + source files)
├── ADAPTER_AUTHORING_GUIDE.md ✅
└── PYTHON_ADAPTER_GUIDE.md ✅

internal-docs/ (6)
├── ARCHITECTURAL_DILIGENCE.md ✅
├── DOCUMENTATION_ALIGNMENT_AUDIT.md ✅
├── DOCUMENTATION_STRUCTURE_GUIDE.md ✅
├── NGINX_SUPPORT_DOCUMENTATION.md ✅
├── PHASES_3_4_AST_MIGRATION.md ✅
└── STRATEGIC_DOCUMENTATION_REVIEW.md ✅

internal-docs/planning/ (20)
├── README.md ✅
├── BREADCRUMB_IMPROVEMENTS_2026.md ❌ (untracked!)
├── AST_MIGRATION_ROADMAP.md ✅
├── CODE_QUALITY_*.md (2 files) ✅
├── CONTAINMENT_MODEL_DESIGN.md ✅
├── DIFF_ADAPTER_DESIGN.md ✅
├── DUPLICATE_DETECTION_*.md (4 files) ⚠️
├── ENHANCEMENTS.md ✅
├── FOUNDATION_QUALITY_PLAN.md ✅
├── IMPORTS_IMPLEMENTATION_PLAN.md ✅
├── INTENT_LENSES_DESIGN.md ✅
├── KNOWLEDGE_GRAPH_*.md (3 files) ✅
├── LINK_VALIDATION_SPEC.md ✅
├── NGINX_ADAPTER_ENHANCEMENTS.md ✅
└── TYPED_FEATURE_IDEAS.md ✅

internal-docs/archive/ (13 historical)
internal-docs/research/ (1)
validation_samples/ (1 + sample files)
```

---

## Issues Identified

### 🔴 Critical: Session Artifacts in Root

**Problem**: 5 files violate "production repo should be clean" rule from DOCUMENTATION_STRUCTURE_GUIDE.md

**Files:**

1. **CODE_REVIEW_IMPROVEMENTS.md**
   - Created: Unknown (no date)
   - Content: Code quality improvement proposals
   - Action: Move to `internal-docs/planning/CODE_QUALITY_REFACTORING_IDEAS.md` or archive

2. **POST_v0.29.0_CODE_QUALITY.md**
   - Created: 2026-01-03
   - Content: Post-release quality analysis
   - Action: Move to `internal-docs/archive/POST_v0.29.0_CODE_QUALITY.md`

3. **MYSQL_ADAPTER_TEST_RESULTS.md**
   - Created: 2025-12-17 (brave-flame-1217)
   - Content: Session test results
   - Action: Move to `internal-docs/archive/MYSQL_ADAPTER_TEST_RESULTS.md`

4. **RELEASE_READINESS_v0.29.0.md**
   - Created: 2026-01-03
   - Content: Version-specific release checklist
   - Action: Move to `internal-docs/archive/RELEASE_READINESS_v0.29.0.md`

5. **AI_DIFF_USAGE.md**
   - Created: Unknown (sacred-sphinx-0104 session)
   - Content: **High-quality user guide** for diff:// adapter
   - Action: Move to `docs/DIFF_ADAPTER_GUIDE.md` (this is NOT a session artifact, it's production-ready)

**Impact**: Clutters root directory, violates project structure standards

---

### 🟡 Medium: Untracked Planning Doc

**Problem**: `internal-docs/planning/BREADCRUMB_IMPROVEMENTS_2026.md` is untracked (blocked by .gitignore)

**Evidence:**
```bash
$ git status --short
?? internal-docs/planning/BREADCRUMB_IMPROVEMENTS_2026.md
```

**Root Cause**: .gitignore line 32 has overly broad `planning/` pattern

**Impact**: Important planning document won't be committed

**Solution**: Force-add the file OR fix .gitignore pattern

---

### 🟡 Medium: Naming Confusion

**Problem**: Two different "DUPLICATE_DETECTION_GUIDE.md" files

**Files:**
1. `reveal/DUPLICATE_DETECTION_GUIDE.md` (488 lines)
   - User-facing quick start guide
   - Packaged with tool for `reveal help://duplicate-detection`
   - Starts with "Quick Start" section

2. `internal-docs/planning/DUPLICATE_DETECTION_GUIDE.md` (542 lines)
   - Complete architectural guide
   - Starts with "Vision: One System, All File Types"
   - Includes three-layer abstraction architecture

**Comparison**: Files are DIFFERENT (not duplicates) but naming is confusing

**Impact**: Confusing for maintainers, unclear which to update

**Solution Options:**
- **Option A**: Rename reveal/ file to `DUPLICATE_DETECTION_QUICKSTART.md`
- **Option B**: Rename planning/ file to `DUPLICATE_DETECTION_ARCHITECTURE.md`
- **Option C**: Keep as-is (different directories = different audiences)

**Recommendation**: Option B (rename planning doc to ARCHITECTURE) - preserves user-facing name

---

### 🟢 Low: Minor Inconsistencies

**Adapter Guides in Three Locations:**
- `reveal/REVEAL_ADAPTER_GUIDE.md` (user help)
- `reveal/adapters/ADAPTER_AUTHORING_GUIDE.md` (developer guide in source)
- `reveal/adapters/PYTHON_ADAPTER_GUIDE.md` (developer guide in source)

**Assessment**: This is intentional separation (user vs developer docs), NOT redundancy

---

## Proposed Actions

### Phase 1: Archive Session Artifacts (5 min)

**Move root-level session artifacts to archive:**

```bash
cd /home/scottsen/src/projects/reveal/external-git

# Archive session artifacts
git mv CODE_REVIEW_IMPROVEMENTS.md internal-docs/archive/
git mv POST_v0.29.0_CODE_QUALITY.md internal-docs/archive/
git mv MYSQL_ADAPTER_TEST_RESULTS.md internal-docs/archive/
git mv RELEASE_READINESS_v0.29.0.md internal-docs/archive/
```

**Rationale**: These are historical session artifacts with no ongoing relevance to users or developers

---

### Phase 2: Promote User Guide (5 min)

**Move AI_DIFF_USAGE.md to docs/ with proper name:**

```bash
# This is a high-quality user guide, not a session artifact
git mv AI_DIFF_USAGE.md docs/DIFF_ADAPTER_GUIDE.md
```

**Update references:**
- Check `internal-docs/planning/README.md` (line 32 references AI_DIFF_USAGE.md)
- Update to `docs/DIFF_ADAPTER_GUIDE.md`

**Rationale**: This is production-ready user documentation, belongs in docs/ for discoverability

---

### Phase 3: Fix Untracked Planning Doc (10 min)

**Option A: Force-add (quick fix):**
```bash
git add -f internal-docs/planning/BREADCRUMB_IMPROVEMENTS_2026.md
```

**Option B: Fix .gitignore (proper fix):**
```bash
# Edit .gitignore line 32
# BEFORE:
planning/

# AFTER:
/.planning/         # Only ignore root-level planning/
**/sessions/**/     # Ignore session directories anywhere
```

**Recommendation**: Use Option A now (force-add), defer Option B to future cleanup

**Rationale**: Get the file tracked immediately, comprehensive .gitignore fix can be separate work

---

### Phase 4: Resolve Naming Confusion (5 min)

**Rename planning guide to clarify purpose:**

```bash
git mv internal-docs/planning/DUPLICATE_DETECTION_GUIDE.md \
       internal-docs/planning/DUPLICATE_DETECTION_ARCHITECTURE.md
```

**Update references:**
- `internal-docs/planning/README.md` line 188-191
- Change from "DUPLICATE_DETECTION_GUIDE.md - User guide" to "DUPLICATE_DETECTION_ARCHITECTURE.md - Complete architecture"

**Rationale**:
- User-facing guide stays in reveal/ (correct location for help system)
- Planning guide gets clearer name reflecting its architectural scope
- No confusion about which file to update

---

### Phase 5: Update Indices (5 min)

**Update planning README:**
```markdown
# internal-docs/planning/README.md

### Historical Plans (Reference Only)

**Duplicate Detection:**
- [DUPLICATE_DETECTION_DESIGN.md](./DUPLICATE_DETECTION_DESIGN.md) - System architecture
- [DUPLICATE_DETECTION_ARCHITECTURE.md](./DUPLICATE_DETECTION_ARCHITECTURE.md) - Complete architectural guide (was: GUIDE)
- [DUPLICATE_DETECTION_OPTIMIZATION.md](./DUPLICATE_DETECTION_OPTIMIZATION.md) - Mathematical framework
- [DUPLICATE_DETECTION_OVERVIEW.md](./DUPLICATE_DETECTION_OVERVIEW.md) - Visual overview
```

**Update diff adapter reference:**
```markdown
### 🚧 diff:// Adapter (v0.30.0)

**Documents:**
- `../../docs/DIFF_ADAPTER_GUIDE.md` - AI agent integration guide (was: AI_DIFF_USAGE.md)
- See ROADMAP.md for feature details
```

---

## Validation Checklist

After consolidation, verify:

```bash
# ✅ No session artifacts in root
ls -la *.md | grep -E "(TEST_RESULTS|READINESS|IMPROVEMENTS|POST_)"
# Should return nothing

# ✅ AI_DIFF_USAGE.md moved to docs/
ls docs/DIFF_ADAPTER_GUIDE.md
# Should exist

# ✅ Planning doc is tracked
git ls-files | grep BREADCRUMB_IMPROVEMENTS_2026
# Should return the file

# ✅ No duplicate GUIDE naming
find . -name "*DUPLICATE_DETECTION_GUIDE.md" | wc -l
# Should return 1 (only reveal/)

# ✅ References updated
grep -r "AI_DIFF_USAGE" internal-docs/
# Should return nothing

grep -r "DUPLICATE_DETECTION_GUIDE.md" internal-docs/planning/README.md
# Should return nothing (now ARCHITECTURE)
```

---

## Impact Assessment

### Documentation Clarity: ⬆️ HIGH

**Before**: Session artifacts mixed with production docs, unclear naming
**After**: Clean separation, obvious homes for each doc type

### Maintainability: ⬆️ MEDIUM

**Before**: Confusion about which duplicate guide to update
**After**: Clear naming (QUICKSTART vs ARCHITECTURE)

### Discoverability: ⬆️ MEDIUM

**Before**: AI_DIFF_USAGE.md hidden in root
**After**: DIFF_ADAPTER_GUIDE.md in docs/ with other guides

### Git Tracking: ⬆️ HIGH

**Before**: Important planning doc untracked
**After**: All planning docs properly tracked

---

## Alternative: Defer Archive Cleanup

If immediate consolidation is too disruptive, **minimum viable cleanup**:

1. ✅ Move AI_DIFF_USAGE.md to docs/ (promotes good content)
2. ✅ Track BREADCRUMB_IMPROVEMENTS_2026.md (prevents loss)
3. ⏳ Defer root-level cleanup (low urgency)
4. ⏳ Defer naming changes (low impact)

**Estimated effort**: 5 minutes

---

## Next Steps

### Recommended Sequence

1. **Now (rainbow-palette-0104)**: Execute Phases 1-5 (30 minutes total)
2. **Validation**: Run validation checklist
3. **Commit**: Single commit "docs: Consolidate documentation per structure guide"
4. **Future**: Consider comprehensive .gitignore cleanup (separate session)

### Risk Assessment

**Low Risk Changes:**
- ✅ Moving session artifacts to archive (no references)
- ✅ Promoting AI_DIFF_USAGE.md to docs/ (1 reference to update)
- ✅ Tracking BREADCRUMB_IMPROVEMENTS_2026.md (no changes)

**Medium Risk Changes:**
- ⚠️ Renaming DUPLICATE_DETECTION_GUIDE (must update references)

**Mitigation**: Review all references before renaming

---

## Alignment with DOCUMENTATION_STRUCTURE_GUIDE

This plan implements recommendations from `internal-docs/DOCUMENTATION_STRUCTURE_GUIDE.md`:

- ✅ **"Keep production repo clean"** (Phase 1: archive session artifacts)
- ✅ **"Use specific, descriptive names"** (Phase 4: ARCHITECTURE vs GUIDE)
- ✅ **"Maintain indices"** (Phase 5: update README.md)
- ✅ **"Don't mix session artifacts with production docs"** (Phases 1-2)
- ✅ **"Fix .gitignore carefully"** (Phase 3: force-add or targeted fix)

---

## Success Metrics

**After consolidation:**
- ✅ Root directory: Only 8 canonical docs (README, CHANGELOG, CONTRIBUTING, INSTALL, RELEASING, ROADMAP, SECURITY, CHANGELOG.archive)
- ✅ docs/: User guides grouped together (5 guides + 1 example)
- ✅ internal-docs/planning/: All planning docs tracked
- ✅ No naming collisions
- ✅ All references updated

**Result**: Documentation structure matches the guide, diligent and maintainable

---

**Author**: TIA (rainbow-palette-0104)
**Based On**: Analysis of 64 markdown files using reveal
**References**: internal-docs/DOCUMENTATION_STRUCTURE_GUIDE.md
