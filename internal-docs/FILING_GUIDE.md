# Documentation Filing Guide

**Purpose**: Guidelines for where to place different types of documentation to maintain organization.

**Created**: 2026-02-09
**Last Updated**: 2026-02-09

---

## Directory Structure

```
reveal/external-git/
├── internal-docs/                  # Internal development documentation (in git)
│   ├── case-studies/               # Bug analysis, post-mortems, real-world usage
│   ├── marketing/                  # Marketing intelligence, positioning
│   ├── planning/                   # Feature planning, roadmaps, priorities
│   ├── refactoring/                # Code quality reviews, refactoring plans
│   ├── research/                   # Dogfooding, experiments, test plans
│   └── archived/                   # Completed work (not in git)
├── reveal/docs/                    # User-facing documentation (in git)
│   ├── QUICK_START.md              # User guides
│   ├── RECIPES.md                  # User guides
│   ├── ADAPTER_AUTHORING_GUIDE.md  # Developer guides
│   └── ...
└── *.md (root level)               # Project meta files only (see below)
```

---

## Filing Rules by Document Type

### Session Artifacts

**Examples**: Session READMEs (e.g., `README_2026-02-09_16-55.md`)

**Where**:
- ❌ NOT in project root
- ✅ Keep in session directory: `/home/scottsen/src/tia/sessions/<session-name>/`
- ✅ Or delete after session (if captured in git commits/internal-docs)

**Why**: Session artifacts are temporary work products, not project documentation.

---

### Dogfooding Reports

**Examples**: `DOGFOODING_REPORT_2026-02-07.md`, `DOGFOODING_SESSION_RESULTS.md`

**Where**: `internal-docs/research/`

**Naming**: `DOGFOODING_REPORT_YYYY-MM-DD.md`

**Why**: Dogfooding is research activity. Date-based naming allows multiple reports to coexist.

---

### Strategic Analysis & Planning

**Examples**: `STRATEGIC_PRIORITIES_ANALYSIS.md`, `CURRENT_PRIORITIES.md`, `ADAPTER_UX_CONSISTENCY.md`

**Where**: `internal-docs/planning/`

**Naming**:
- If evergreen (ongoing): `DOCUMENT_NAME.md` (e.g., `CURRENT_PRIORITIES.md`)
- If dated analysis: `DOCUMENT_NAME_YYYY-MM-DD.md`

**Why**: Strategic planning docs help maintainers understand next steps and priorities.

---

### Bug Analysis & Case Studies

**Examples**: `BUG_FIX_SUMMARY.md`, `BUG_PREVENTION.md`, `VEINBORN_CASE_STUDY.md`

**Where**: `internal-docs/case-studies/`

**Naming**: `DESCRIPTIVE_NAME_YYYY-MM-DD.md` or `DESCRIPTIVE_NAME.md`

**Why**: Case studies document lessons learned from real-world usage or bug fixes.

---

### Test Plans & Research

**Examples**: `V_SERIES_TEST_PLAN.md`, `VALIDATION_REPORT.md`, `POPULAR_REPOS_TESTING.md`

**Where**: `internal-docs/research/`

**Naming**: `DESCRIPTIVE_NAME_YYYY-MM-DD.md` or `DESCRIPTIVE_NAME.md`

**Why**: Test plans and research findings inform future development decisions.

---

### Code Quality & Refactoring

**Examples**: `CODE_QUALITY_REVIEW.md`, `REFACTORING_ACTION_PLAN.md`, `ARCHITECTURE_IMPROVEMENTS.md`

**Where**: `internal-docs/refactoring/`

**Naming**: `DESCRIPTIVE_NAME_YYYY-MM-DD.md` or `DESCRIPTIVE_NAME.md`

**Why**: Refactoring docs track technical debt and code quality improvements.

---

### User-Facing Guides

**Examples**: `QUICK_START.md`, `RECIPES.md`, `ADAPTER_AUTHORING_GUIDE.md`

**Where**: `reveal/docs/`

**Naming**: `DESCRIPTIVE_NAME.md` (all caps for consistency)

**Why**: User-facing docs help end users and developers use Reveal effectively.

---

### Project Meta Files (Root Level ONLY)

**Allowed at root**:
- `README.md` - Project introduction (required for GitHub)
- `CHANGELOG.md` - Version history (required for releases)
- `CONTRIBUTING.md` - Contributor guide (GitHub convention)
- `INSTALL.md` - Installation instructions
- `RELEASING.md` - Release process (for maintainers)
- `ROADMAP.md` - Public roadmap
- `SECURITY.md` - Security policy (GitHub convention)
- `STABILITY.md` - Stability guarantees
- `LICENSE` - License file

**NOT allowed at root**:
- Session READMEs
- Dogfooding reports
- Strategic analysis docs
- Bug fix summaries
- Test plans
- Any other internal documentation

---

## Filing Workflow

### When creating new documentation:

1. **Determine document type** (see rules above)
2. **Choose appropriate directory**
3. **Use consistent naming**:
   - Date-based: `NAME_YYYY-MM-DD.md` for point-in-time snapshots
   - Evergreen: `NAME.md` for ongoing/updated docs
4. **Add frontmatter** (optional but recommended):
   ```yaml
   ---
   session: session-name-0209
   date: 2026-02-09
   type: dogfooding|planning|case-study|research
   status: complete|in-progress|draft
   ---
   ```
5. **Update parent README** if directory has one (e.g., `internal-docs/README.md`)

---

## Archiving Completed Work

**When**: After work is complete and superseded by newer docs

**Where**: `internal-docs/archived/<subdirectory>/`

**Example**:
- `internal-docs/planning/PHASE2_PLAN.md` (active)
- `internal-docs/archived/planning/PHASE1_PLAN.md` (completed)

**Why**: Keeps active directories focused on current work, preserves history.

---

## Quick Decision Tree

```
Is this a session artifact (README_*.md)?
  └─ YES → Delete or keep in TIA session directory
  └─ NO ↓

Is this user-facing documentation?
  └─ YES → reveal/docs/
  └─ NO ↓

Is this a project meta file (README, CHANGELOG, etc.)?
  └─ YES → Root level (external-git/)
  └─ NO ↓

What type of internal doc?
  ├─ Dogfooding report → internal-docs/research/
  ├─ Strategic planning → internal-docs/planning/
  ├─ Bug analysis → internal-docs/case-studies/
  ├─ Test plan → internal-docs/research/
  ├─ Code quality review → internal-docs/refactoring/
  └─ Marketing → internal-docs/marketing/
```

---

## Maintenance

- **Quarterly review**: Check for misplaced docs at root level
- **After sessions**: Move session artifacts to proper locations
- **Before releases**: Ensure CHANGELOG and ROADMAP are updated
- **Archive old docs**: Move completed work to `internal-docs/archived/`

---

## Examples from Recent Consolidation (2026-02-09)

**Misplaced** → **Correct Location**:
- `README_2026-02-09_16-55.md` (root) → Deleted (session artifact)
- `DOGFOODING_SESSION_RESULTS.md` (root) → `internal-docs/research/DOGFOODING_REPORT_2026-02-07.md`
- `STRATEGIC_PRIORITIES_ANALYSIS.md` (root) → `internal-docs/planning/STRATEGIC_PRIORITIES_ANALYSIS_2026-02-07.md`
- `BUG_FIX_SUMMARY.md` (root) → `internal-docs/case-studies/BUG_FIX_SUMMARY_2026-02-07.md`
- `V_SERIES_TEST_PLAN.md` (root) → `internal-docs/research/V_SERIES_TEST_PLAN_2026-02-07.md`

---

**Session**: temporal-lens-0209
**Related**: [LIFECYCLE.md](LIFECYCLE.md) - Document lifecycle policy
