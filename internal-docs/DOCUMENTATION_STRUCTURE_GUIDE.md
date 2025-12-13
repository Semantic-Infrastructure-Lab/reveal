# Reveal - Documentation Structure Guide

**Last Updated:** 2025-12-12 (cyber-phoenix-1212)
**Based On:** TIA's proven two-tier pattern from `SIL_ECOSYSTEM_PROJECT_LAYOUT.md`

---

## The Two-Tier Pattern

Reveal follows **Pattern B (Lightweight TIA Tracking)** - a mature, stable project with minimal TIA oversight:

### Tier 1: Production Repository (This Repo)
**Location:** `/home/scottsen/src/projects/reveal/external-git/`
**Purpose:** Clean production code, official documentation, publishable artifacts
**Git:** Public GitHub repository
**Rules:**
- ✅ Production code, tests, release artifacts
- ✅ Official user-facing documentation
- ✅ Architecture and API documentation
- ❌ NO session artifacts (analysis, progress reports, internal notes)
- ❌ NO research/planning documents (except `internal-docs/planning/`)

### Tier 2: TIA Workspace (Optional)
**Location:** `/home/scottsen/src/tia/projects/reveal/` (created only when needed)
**Purpose:** Active research sessions, architectural exploration, analysis
**Contents:**
- Session-specific analysis documents
- Research notes and experiments
- TIA project metadata (`project.yaml`)
- Temporary artifacts from multi-session work

**Pattern B Characteristic:** Reveal doesn't have a permanent TIA workspace because it's mature and stable. Workspace only created during active research sessions.

---

## Directory Structure (Production Repo)

```
reveal/
├── docs/                          # 📚 Official Documentation (PUBLIC)
│   ├── *.md                       # Audits, investigations, reference material
│   └── archive/                   # Historical completed work
│
├── internal-docs/                 # 🔒 Development Documentation (PUBLIC but internal-facing)
│   ├── planning/                  # Future features, roadmaps, specs
│   │   ├── PENDING_WORK.md       # 📌 Master index of ALL pending work
│   │   ├── README.md             # Planning index (lists active/shipped/archived)
│   │   ├── DUPLICATE_DETECTION_*.md
│   │   ├── CODE_QUALITY_*.md
│   │   └── *_SPEC.md             # Feature specifications
│   ├── archive/                   # Completed planning docs (shipped features)
│   └── releasing/                 # Release process documentation
│
├── scripts/                       # 🛠️ Development Tools
│   ├── analyze_*.py              # Analysis and validation scripts
│   └── *.sh                      # Build/release automation
│
├── reveal/                        # 📦 Source Code
├── tests/                         # ✅ Test Suite
├── README.md                      # Main project README
├── CHANGELOG.md                   # Version history
├── CONTRIBUTING.md                # Contribution guidelines
├── ROADMAP.md                     # High-level roadmap
├── RELEASING.md                   # Release process
└── .gitignore                     # ⚠️ CRITICAL: Blocks session artifacts
```

---

## Documentation Homes (What Goes Where)

### docs/ - Official Documentation

**Purpose:** Public-facing reference material, investigations, audits

**Contents:**
- Engineering audits (`REVEAL_ENGINEERING_REVIEW_2025-12-12.md`)
- Root cause analyses (`ROOT_CAUSE_ANALYSIS_MARKDOWN_BUGS.md`)
- Self-audits (`REVEAL_SELF_AUDIT_2025-12-11.md`)
- User guides and tutorials
- Architecture overviews (for users, not developers)

**Rules:**
- Permanent reference material
- Well-written, ready for external eyes
- No work-in-progress documents
- Archive old audits to `docs/archive/` when superseded

**Examples:**
```
docs/
├── REVEAL_ENGINEERING_REVIEW_2025-12-12.md   # Engineering audit
├── ROOT_CAUSE_ANALYSIS_MARKDOWN_BUGS.md       # Investigation
├── REVEAL_SELF_AUDIT_2025-12-11.md            # Self-assessment
└── archive/
    └── launch-2025-12-08/                     # Historical milestones
```

---

### internal-docs/planning/ - Future Work

**Purpose:** Active planning documents, feature specifications, roadmaps

**Contents:**
- Feature specifications (`*_SPEC.md`)
- Implementation roadmaps (`*_ROADMAP.md`)
- Architecture analysis (`*_ARCHITECTURE.md`)
- Design documents (`*_DESIGN.md`)
- **PENDING_WORK.md** (master index)

**Rules:**
- Work-in-progress is OK
- Should be structured and clear (other developers will read)
- Update `README.md` to index active/shipped/archived plans
- Move to `internal-docs/archive/` when feature ships

**Current Active Plans (as of 2025-12-12):**
```
internal-docs/planning/
├── README.md                                # Index of all plans
├── PENDING_WORK.md                          # 📌 Master index (entry point)
│
├── DUPLICATE_DETECTION_DESIGN.md            # Track 1: Duplicate detection
├── DUPLICATE_DETECTION_GUIDE.md
├── DUPLICATE_DETECTION_OPTIMIZATION.md
├── DUPLICATE_DETECTION_SUMMARY.md
│
├── CODE_QUALITY_ARCHITECTURE.md             # Track 2: Quality refactoring
├── CODE_QUALITY_REFACTORING.md
│
├── NGINX_ADAPTER_ENHANCEMENTS.md            # Other features
├── PYTHON_ADAPTER_SPEC.md
└── PYTHON_ADAPTER_ROADMAP.md
```

**Workflow:**
1. Create feature spec in `planning/`
2. Update `planning/README.md` to list it under "Active Plans"
3. Implement feature
4. When shipped:
   - Move spec to `internal-docs/archive/`
   - Update `planning/README.md` to list under "Shipped"
   - Update top-level `CHANGELOG.md`

---

### internal-docs/archive/ - Completed Work

**Purpose:** Historical planning documents for shipped features

**Contents:**
- Completed feature specifications
- Old improvement plans
- Version-specific checklists
- Historical analysis documents

**Rules:**
- Don't delete old planning docs, archive them
- Useful for understanding why decisions were made
- Can reference in future work

**Examples:**
```
internal-docs/archive/
├── IMPROVEMENT_PLAN.md                      # Completed improvements
├── RELEASE_CHECKLIST_v0.17.0.md            # Historical release process
├── REVEAL_ENHANCEMENT_PROPOSALS.md          # Implemented proposals
└── WINDOWS_VALIDATION.md                    # Completed validation
```

---

### scripts/ - Development Tools

**Purpose:** Automation, analysis, and development utilities

**Contents:**
- Analysis scripts (`analyze_duplicate_detection.py`)
- Build automation (`check_cross_platform.sh`)
- Validation tools (`validate_v0.X.0.sh`)
- Release helpers (`test_pypi_rocky.sh`)

**Rules:**
- Should be runnable without explanation
- Include docstrings/comments explaining what they do
- Add to `CONTRIBUTING.md` if developers should know about them

**Examples:**
```
scripts/
├── analyze_duplicate_detection.py           # Statistical analysis tool
├── check_cross_platform.sh                  # Platform compatibility
└── validate_v0.4.0.sh                       # Version validation
```

---

## Critical: The .gitignore Pattern

**Problem:** Session artifacts from TIA shouldn't leak into production repo

**Solution:** Block session artifact patterns in `.gitignore`

**Current Reveal .gitignore (lines 1-32):**
```gitignore
# ============================================================
# TIA Session Artifacts (belong in ~/src/tia/projects/reveal/)
# ============================================================

# Session documentation patterns
*_SUMMARY.md
*_COMPLETE.md
*_ANALYSIS.md
*_ASSESSMENT_*.md
*_PLAN.md
*_PROGRESS.md
*_REPORT.md
*_STATUS_REPORT.md
*_IMPLEMENTATION_*.md
*_FINDINGS.md
*_RESULTS.md
*_SESSION_*.md

# Internal planning docs
NEXT_STEPS.md
INTERNAL_*.md
MEETING_*.md
DRAFT_*.md

# TIA directories
.tia/
.beth/
analysis/
research/
sessions/
internal/
planning/              # ⚠️ THIS BLOCKS internal-docs/planning/
```

**Issue Identified:** Line 32 (`planning/`) blocks `internal-docs/planning/` files from being tracked

---

## Recommended .gitignore Fix

**Problem:** Current pattern too broad - blocks legitimate planning docs

**Solution:** Make patterns more specific

**Recommended Change:**

```gitignore
# BEFORE (line 25-32):
# TIA directories
.tia/
.beth/
analysis/
research/
sessions/
internal/
planning/              # ❌ Too broad!

# AFTER:
# TIA directories (session artifacts)
.tia/
.beth/
**/sessions/**/       # Session directories anywhere
/.analysis/           # Root-level analysis (planning is in internal-docs/)
/.research/           # Root-level research
/.planning/           # Root-level planning (but allow internal-docs/planning/)
/internal/            # Root-level internal (but allow internal-docs/)
```

**Alternative:** Force-add legitimate planning docs

```bash
# If you want to keep broad ignore but track specific files
git add -f internal-docs/planning/*.md
```

**Recommendation:** Use more specific patterns. Broad ignores like `planning/` are error-prone.

---

## Document Naming Conventions

### Permanent Documents (goes in docs/ or internal-docs/)

**Good Names:**
- `FEATURE_NAME_SPEC.md` (specifications)
- `FEATURE_NAME_DESIGN.md` (design documents)
- `FEATURE_NAME_ROADMAP.md` (implementation plans)
- `FEATURE_NAME_ARCHITECTURE.md` (architecture analysis)
- `PROJECT_ENGINEERING_REVIEW_YYYY-MM-DD.md` (audits with date)
- `PROJECT_SELF_AUDIT_YYYY-MM-DD.md` (self-assessments)

**Avoid:**
- Generic session names (`*_SUMMARY.md`, `*_ANALYSIS.md`, `*_STATUS.md`)
- These are blocked by .gitignore as session artifacts
- Be specific: `DUPLICATE_DETECTION_DESIGN.md` not `DESIGN_ANALYSIS.md`

### Index Documents

**Master Indices:**
- `PENDING_WORK.md` - Single source of truth for all pending work
- `README.md` (in each directory) - Index of what's in this directory
- `DOCUMENTATION_MAP.md` (optional) - Complete documentation map

**Best Practice:** Always have a README.md or index file explaining what's in a directory

---

## Workflow: From Session to Permanent Doc

### Phase 1: Session Work (TIA Workspace)

When actively researching/implementing:

1. **Create TIA session:** `tia session create <name>`
2. **Work in session directory:** `/home/scottsen/src/tia/sessions/<session>/`
3. **Generate session artifacts:**
   - `README_YYYY-MM-DD_HH-MM.md` (session summary)
   - `*_ANALYSIS.md`, `*_SUMMARY.md` (temporary docs)
   - Working drafts, experiments, research notes

### Phase 2: Consolidation (Session → Production)

When session work is complete:

1. **Identify permanent artifacts:**
   - Comprehensive guides → `internal-docs/planning/`
   - Engineering reviews → `docs/`
   - Analysis tools → `scripts/`

2. **Rename and organize:**
   ```bash
   # Session artifact (temporary name)
   REVEAL_DUPLICATE_DETECTION_SUMMARY.md

   # Permanent document (specific name)
   internal-docs/planning/DUPLICATE_DETECTION_SUMMARY.md
   ```

3. **Update indices:**
   - Add to `internal-docs/planning/README.md`
   - Add to `PENDING_WORK.md` (if work pending)
   - Update `ROADMAP.md` (if feature planned)

4. **Create session README:** Use `tia-save` to generate permanent session summary

### Phase 3: Shipping (Planning → Archive)

When feature is implemented and shipped:

1. **Move planning docs:**
   ```bash
   git mv internal-docs/planning/FEATURE_SPEC.md \
          internal-docs/archive/FEATURE_SPEC.md
   ```

2. **Update indices:**
   - Move from "Active Plans" to "Shipped" in `planning/README.md`
   - Add entry to `CHANGELOG.md`
   - Update `ROADMAP.md`

3. **Keep design docs accessible:**
   - Archive planning docs, but keep architecture docs in production
   - Future work may reference design decisions

---

## Real Example: Duplicate Detection Work

### Session Artifacts (infernal-throne-1212)
**Location:** `/home/scottsen/src/tia/sessions/infernal-throne-1212/`

```
infernal-throne-1212/
├── README_2025-12-12_16-09.md                    # Session summary
├── CLAUDE.md                                      # Session instructions
└── /tmp/                                          # Working artifacts
    ├── DUPLICATE_DETECTION_OPTIMIZATION_GUIDE.md
    ├── REVEAL_DUPLICATE_DETECTION_COMPLETE_GUIDE.md
    ├── REVEAL_DUPLICATE_DETECTION_SUMMARY.md
    ├── UNIVERSAL_DUPLICATE_DETECTION_DESIGN.md
    └── analyze_duplicate_detection.py
```

### Consolidated to Production (cyber-phoenix-1212)
**Location:** `/home/scottsen/src/projects/reveal/external-git/`

```
reveal/
├── internal-docs/planning/
│   ├── DUPLICATE_DETECTION_DESIGN.md             # From UNIVERSAL_*_DESIGN.md
│   ├── DUPLICATE_DETECTION_GUIDE.md              # From REVEAL_*_GUIDE.md
│   ├── DUPLICATE_DETECTION_OPTIMIZATION.md       # From DUPLICATE_*_GUIDE.md
│   ├── DUPLICATE_DETECTION_SUMMARY.md            # From REVEAL_*_SUMMARY.md
│   ├── PENDING_WORK.md                           # Master index (references all 4)
│   └── README.md                                 # Updated to list feature
└── scripts/
    └── analyze_duplicate_detection.py            # Analysis tool
```

**Session → Production Transformation:**
1. ✅ Renamed for clarity (removed `REVEAL_` prefix, descriptive names)
2. ✅ Organized by feature area (all duplicate detection docs together)
3. ✅ Tools moved to appropriate directory (`scripts/`)
4. ✅ Index updated (`PENDING_WORK.md`, `planning/README.md`)
5. ✅ Session summary preserved in TIA workspace

---

## Best Practices Summary

### ✅ DO

1. **Keep production repo clean**
   - Only permanent, well-written documentation
   - No session artifacts, no work-in-progress clutter
   - Everything should be ready for public consumption

2. **Use specific, descriptive names**
   - `DUPLICATE_DETECTION_DESIGN.md` ✅
   - `DESIGN_ANALYSIS.md` ❌ (blocked by .gitignore)

3. **Maintain indices**
   - `PENDING_WORK.md` = master index
   - `planning/README.md` = planning index
   - `ROADMAP.md` = high-level roadmap

4. **Archive completed work**
   - Don't delete, move to `archive/`
   - Useful for understanding historical decisions

5. **Update .gitignore carefully**
   - Be specific with patterns
   - Document why patterns exist
   - Test before committing

### ❌ DON'T

1. **Mix session artifacts with production docs**
   - Session summaries belong in TIA workspace
   - Production docs belong in production repo

2. **Use generic names blocked by .gitignore**
   - `*_ANALYSIS.md`, `*_SUMMARY.md`, `*_PLAN.md` are session patterns
   - Use specific feature names instead

3. **Ignore directory-level organization**
   - Every directory should have a clear purpose
   - Use `README.md` to explain what's there

4. **Let planning docs rot**
   - Update `PENDING_WORK.md` as work progresses
   - Move to archive when shipped
   - Keep indices current

5. **Block legitimate docs with overly broad .gitignore**
   - `planning/` blocks `internal-docs/planning/` ❌
   - `/.planning/` blocks only root-level `planning/` ✅

---

## Quick Reference Commands

### Check What's Ignored

```bash
# See if a file is ignored and why
git check-ignore -v internal-docs/planning/PENDING_WORK.md

# List all ignored files
git status --ignored

# See ignored files in specific directory
git status --ignored internal-docs/planning/
```

### Force-Add Ignored Files

```bash
# Add specific file despite .gitignore
git add -f internal-docs/planning/PENDING_WORK.md

# Add all planning docs
git add -f internal-docs/planning/*.md
```

### Check Git Tracking

```bash
# See which files are tracked
git ls-files internal-docs/planning/

# See untracked files
git ls-files --others --exclude-standard

# See both tracked and untracked
git ls-files --others --exclude-standard && git ls-files
```

---

## Integration with TIA

### When TIA Workspace is Created

For active multi-session work, create TIA workspace:

```bash
# TIA workspace location
/home/scottsen/src/tia/projects/reveal/

# Contents
project.yaml              # TIA project metadata
analysis/                 # Session analysis documents
research/                 # Research notes
README.md                 # Workspace overview
```

### Session-to-Production Flow

```bash
# 1. Work in TIA session
cd ~/src/tia/sessions/cosmic-phoenix-1212/
# ... create docs, research, implement ...

# 2. Consolidate to production repo
cd ~/src/projects/reveal/external-git/
cp ~/src/tia/sessions/cosmic-phoenix-1212/FEATURE_DESIGN.md \
   internal-docs/planning/FEATURE_DESIGN.md

# 3. Update indices
vim internal-docs/planning/README.md  # Add feature
vim internal-docs/planning/PENDING_WORK.md  # Link to docs

# 4. Commit
git add internal-docs/planning/FEATURE_DESIGN.md
git add internal-docs/planning/README.md
git add internal-docs/planning/PENDING_WORK.md
git commit -m "docs: Add FEATURE_DESIGN planning document"
```

---

## Conclusion

**The Diligent Structure:**

1. **Two-Tier Separation:** Session artifacts (TIA) vs. production docs (repo)
2. **Clear Homes:** Each document type has a clear location
3. **Active Indices:** `PENDING_WORK.md`, `README.md` guide navigation
4. **Careful .gitignore:** Block session patterns, not legitimate docs
5. **Archive, Don't Delete:** Keep historical context

**Result:** Clean, navigable documentation that serves both developers (planning) and users (guides) without clutter.

---

**References:**
- TIA Pattern: `/home/scottsen/src/tia/projects/SIL/docs/SIL_ECOSYSTEM_PROJECT_LAYOUT.md`
- Reveal Structure: This guide
- Session Examples: infernal-throne-1212, wise-goddess-1212, cyber-phoenix-1212

**Last Updated:** 2025-12-12 (cyber-phoenix-1212)
**Maintained By:** Reveal project maintainers
