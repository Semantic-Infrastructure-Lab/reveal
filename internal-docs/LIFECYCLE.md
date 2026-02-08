# Internal Documentation Lifecycle Policy

**Purpose**: Define when internal docs are active, archived, or removed
**Last Updated**: 2026-02-06

---

## Document Lifecycle States

### 1. Active (Main Directories)

**Status**: Currently relevant, referenced by ongoing work
**Location**: `internal-docs/{category}/`
**Examples**:
- Planning docs for upcoming features
- Active refactoring plans
- Recent research/analysis

**Retention**: Keep until work completed or findings implemented

---

### 2. Archived (archived/ Subdirectories)

**Status**: Work completed, kept for historical reference
**Location**: `internal-docs/archived/{category}/`
**Examples**:
- Completed planning docs (feature shipped)
- Dogfooding reports (findings addressed)
- Superseded analysis (newer version exists)

**When to archive**:
- **Planning docs**: After feature implemented and shipped
- **Research docs**: 6 months after findings implemented
- **Refactoring docs**: After refactoring completed and verified
- **Case studies**: When bug fixed and prevention measures in place

**Retention**: Keep indefinitely for historical reference

---

### 3. Removed (Deleted)

**Status**: Obsolete, incorrect, or no longer relevant
**Location**: N/A (deleted from repo)
**Examples**:
- Incorrect analysis that was corrected
- Speculative planning that was abandoned
- Duplicate content

**When to remove**:
- Analysis proven incorrect
- Planning abandoned completely
- Better version replaces old doc
- Content moved to user-facing docs

**Process**: Create git commit explaining removal reason

---

### Special Case: Session Artifacts

**Status**: Development artifacts (not tracked in git)
**Location**: Ignored by `.gitignore` (patterns: `*_SUMMARY.md`, `*_COMPLETE.md`, `*_ANALYSIS.md`, etc.)
**Examples**:
- Session completion summaries
- Session analysis reports
- Session implementation plans

**Why ignored**: These belong in TIA session tracking (`~/src/tia/sessions/`), not in the reveal repository. They document the development process, not the product.

**If found in repo**: Remove them - they were accidentally created in wrong location
```bash
rm internal-docs/*_SUMMARY.md  # Session artifacts belong in TIA
```

---

## Category-Specific Guidelines

### Planning (`internal-docs/planning/`)

**Active duration**: Until feature implemented
**Archive trigger**: Feature ships in release
**Example lifecycle**:
1. Create: `FEATURE_NAME_2026-02-06.md`
2. Active: During implementation
3. Archive: After release in CHANGELOG
4. Location: `archived/planning/FEATURE_NAME_2026-02-06.md`

### Research (`internal-docs/research/`)

**Active duration**: Until findings implemented or 6 months
**Archive trigger**: Findings addressed or time-based
**Example lifecycle**:
1. Create: `DOGFOODING_REPORT_2026-02-06.md`
2. Active: While addressing findings
3. Archive: 6 months later or when findings implemented
4. Location: `archived/research/DOGFOODING_REPORT_2026-02-06.md`

### Refactoring (`internal-docs/refactoring/`)

**Active duration**: Until refactoring completed
**Archive trigger**: Changes merged and verified
**Example lifecycle**:
1. Create: `REFACTORING_ACTION_PLAN.md`
2. Active: During refactoring
3. Archive: After completion
4. Location: `archived/refactoring/REFACTORING_ACTION_PLAN.md`

### Case Studies (`internal-docs/case-studies/`)

**Active duration**: Until prevention measures implemented
**Archive trigger**: Prevention completed and documented
**Example lifecycle**:
1. Create: `BUG_PREVENTION.md`
2. Active: While implementing prevention
3. Archive: Prevention in place and verified
4. Location: `archived/case-studies/BUG_PREVENTION.md`

### Marketing (`internal-docs/marketing/`)

**Active duration**: Until campaign executed or strategy updated
**Archive trigger**: Campaign complete or superseded
**Special note**: Marketing docs may stay active longer (12+ months)

---

## Archive Process

### Step 1: Verify Completion
- [ ] Work referenced in doc is complete
- [ ] No active references from other docs
- [ ] README.md updated

### Step 2: Move to Archive
```bash
git mv internal-docs/{category}/DOC.md internal-docs/archived/{category}/
```

### Step 3: Update README
- Remove from active section
- Add archive note if significant
- Update related docs links

### Step 4: Commit
```bash
git commit -m "docs: Archive DOC.md (completed YYYY-MM-DD)"
```

---

## Archive Directory Structure

```
internal-docs/archived/
├── case-studies/        # Completed bug analysis
├── planning/            # Shipped features
├── refactoring/         # Completed refactorings
├── research/            # Addressed findings
└── marketing/           # Completed campaigns
```

---

## Review Schedule

**Quarterly Review** (every 3 months):
- Review active docs for archive candidates
- Check archive for docs to remove (if obsolete)
- Update README inventories

**Annual Review** (once per year):
- Deep audit of all internal docs
- Remove truly obsolete archived docs
- Consolidate duplicate content

---

## Examples

### Example 1: Planning Doc Lifecycle

**Created**: `ADAPTER_UX_CONSISTENCY_2026-02-06.md`
- **Phase**: Planning
- **Duration**: Active during implementation (3-6 months)
- **Archive trigger**: All 5 phases completed and released
- **Final location**: `archived/planning/ADAPTER_UX_CONSISTENCY_2026-02-06.md`

### Example 2: Research Doc Lifecycle

**Created**: `DOGFOODING_REPORT_2026-01-19.md`
- **Phase**: Research
- **Duration**: Active while addressing findings
- **Archive trigger**: 6 months or findings implemented
- **Final location**: `archived/research/DOGFOODING_REPORT_2026-01-19.md`

### Example 3: Refactoring Doc Lifecycle

**Created**: `REFACTORING_ACTION_PLAN.md`
- **Phase**: Refactoring
- **Duration**: Active during refactoring work
- **Archive trigger**: All actions completed and merged
- **Final location**: `archived/refactoring/REFACTORING_ACTION_PLAN.md`

---

## Documentation Consolidation

### Purpose

Regular consolidation ensures internal docs remain discoverable, accurate, and maintainable. As projects evolve, documentation accumulates and can become fragmented or outdated.

### Consolidation Triggers

**When to consolidate**:
- After completing major feature work (e.g., Phase 1-5 completion)
- When README.md inventory falls out of sync
- When multiple docs cover overlapping topics
- After project milestones or releases

### Consolidation Process

#### Step 1: Inventory Current State
```bash
# List all markdown files
find internal-docs -name "*.md" -type f | sort

# Check git tracking status
git ls-files internal-docs/

# Identify untracked session artifacts (ignored by .gitignore)
git status internal-docs/
```

#### Step 2: Identify Stale Documents

Review each document for:
- [ ] Completion status (work finished?)
- [ ] Currency (information still accurate?)
- [ ] Relevance (still applicable?)
- [ ] Dependencies (referenced by other docs?)

**Archive if**: Work complete, kept for historical reference
**Remove if**: Obsolete, incorrect, or superseded
**Update if**: Active but needs refresh

#### Step 3: Update Documentation Inventory

1. Update `internal-docs/README.md` with any new documents
2. Remove archived/deleted documents from active inventory
3. Update directory structure diagram if changed
4. Verify all document links are valid

#### Step 4: Archive Completed Work

For documents ready to archive:
```bash
# If tracked in git (not session artifacts):
git mv internal-docs/{category}/DOC.md internal-docs/archived/{category}/
git commit -m "docs: Archive DOC.md (completed YYYY-MM-DD)"

# If untracked session artifacts:
rm internal-docs/{category}/*_SUMMARY.md  # These belong in TIA sessions
```

#### Step 5: Update Cross-References

- Search for references to archived/removed docs
- Update links in README.md
- Update references in related documents

---

## Identifying Stale Documents

### Signals a Document is Stale

**Planning documents**:
- ✅ All tasks/phases marked complete
- ✅ Features shipped in CHANGELOG
- ✅ Referenced in "Completed" sections of other docs

**Research documents**:
- 📅 More than 6 months old
- ✅ Findings addressed in code/docs
- ✅ Superseded by newer research

**Refactoring documents**:
- ✅ All action items completed
- ✅ Changes merged and verified
- ✅ Test coverage improved

**Case studies**:
- ✅ Prevention measures implemented
- ✅ Tests added to catch regression
- ✅ Documented in code comments

### Quick Staleness Check

For each document, ask:
1. **Is the work complete?** - Check commit history, CHANGELOG
2. **Is it still referenced?** - Grep for document name in other files
3. **Is it current?** - Check last modified date vs current priorities
4. **Is it accurate?** - Verify technical details still correct

---

## Review Schedule (Detailed)

### Quarterly Review Checklist

**Every 3 months** (suggested: Feb, May, Aug, Nov):

- [ ] **Inventory check**: Run `git ls-files internal-docs/` and compare to README.md
- [ ] **Staleness review**: Check each active doc against staleness signals
- [ ] **Archive candidates**: Identify completed work ready to archive
- [ ] **Link validation**: Verify all cross-references still valid
- [ ] **README update**: Refresh document inventory and descriptions
- [ ] **Duplicate check**: Look for overlapping content
- [ ] **Priority alignment**: Verify CURRENT_PRIORITIES matches reality

### Annual Review Checklist

**Once per year** (suggested: January):

- [ ] **Deep audit**: Read every active document for accuracy
- [ ] **Archive review**: Check archived docs for removal candidates
- [ ] **Duplicate consolidation**: Merge overlapping content
- [ ] **Link audit**: Check all internal and external links
- [ ] **Category structure**: Verify directory structure still makes sense
- [ ] **LIFECYCLE policy**: Review and update this document
- [ ] **Documentation debt**: Identify gaps in documentation coverage

### Ad-Hoc Reviews

**After major milestones**:
- Feature releases (update planning docs)
- Test coverage improvements (update refactoring docs)
- Bug fixes (update case studies)
- Architecture changes (update technical docs)

---

## Benefits of This Policy

✅ **Clarity**: Clear when docs are active vs historical
✅ **Discoverability**: Active docs stay visible, archive available for reference
✅ **Maintainability**: Regular review prevents doc rot
✅ **Historical record**: Archive preserves decision history
✅ **Clean organization**: Active directories stay focused

---

## Questions?

Contact maintainers or open an issue to discuss lifecycle policy changes.

---

**Status**: ✅ ACTIVE POLICY
**Last Updated**: 2026-02-08 (Session: vilalo-0208)
**Previous Update**: 2026-02-06
