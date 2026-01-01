# Architectural Diligence: Reveal Development Standards

**Version:** 1.0.0
**Date:** 2025-12-31
**Status:** Living Document
**Purpose:** Define the diligent path for reveal's development, maintenance, and quality assurance

---

## Table of Contents

1. [Core Principles](#core-principles)
2. [Architectural Boundaries](#architectural-boundaries)
3. [Quality Standards by Layer](#quality-standards-by-layer)
4. [Pre-Release Validation](#pre-release-validation)
5. [Decision Trees](#decision-trees)
6. [Development Workflows](#development-workflows)
7. [Self-Validation Strategy](#self-validation-strategy)
8. [Long-Term Vision](#long-term-vision)
9. [Appendices](#appendices)

---

## Core Principles

### 1. **Dogfooding with Purpose**
- **Use reveal to validate reveal** - All self-checks run through reveal's own tools
- **Don't ship dev-only tools** - Clear boundary between public API and internal development
- **Validate in production** - Self-validation tools are part of the shipped package (but scoped)

### 2. **Separation of Concerns**
- **Public tools** work on ANY codebase (users' primary value)
- **Self-validation tools** work on reveal:// only (our quality assurance)
- **Development scripts** never ship to users (release automation, analysis)

### 3. **Quality Before Velocity**
- **No release without validation** - Comprehensive pre-release checks required
- **Fix issues, don't defer** - Quality issues are blocking, not backlog items
- **Measure what matters** - Code quality metrics guide decisions

### 4. **Transparency and Documentation**
- **Architectural decisions are documented** - This file is the source of truth
- **Code placement is deliberate** - Every file has a clear purpose and location
- **Changes are justified** - Updates to this document require rationale

---

## Architectural Boundaries

### Layer 1: **PUBLIC CORE** (Ships to all users)

**Purpose:** Tools users apply to their own codebases
**Location:** `reveal/` package (except `reveal/rules/validation/` and `reveal/adapters/reveal.py`)
**Installation:** Included in `pip install reveal-cli`

```
reveal/
├── adapters/
│   ├── ast.py              # ast:// - Query code as database
│   ├── env.py              # env:// - Environment variables
│   ├── help.py             # help:// - Documentation system
│   ├── json_adapter.py     # json:// - JSON navigation
│   ├── mysql.py            # mysql:// - Database inspection
│   ├── python/             # python:// - Python runtime
│   └── stats.py            # stats:// - Codebase metrics
├── analyzers/
│   ├── python.py           # Python code analysis
│   ├── javascript.py       # JavaScript analysis
│   ├── markdown.py         # Markdown analysis
│   ├── (15 total)          # Language-specific analyzers
└── rules/
    ├── bugs/               # B001-B005 (5 rules)
    ├── complexity/         # C901-C905 (3 rules)
    ├── duplicates/         # D001-D002 (2 rules)
    ├── errors/             # E501 (1 rule)
    ├── infrastructure/     # N001-N003 (3 rules)
    ├── links/              # L001-L003 (3 rules)
    ├── maintainability/    # M101-M103 (3 rules)
    ├── refactoring/        # R913 (1 rule)
    ├── security/           # S701 (1 rule)
    └── urls/               # U501-U502 (2 rules)
```

**User Value:** HIGH - Core functionality, works on any codebase
**Quality Standard:** Production-grade, comprehensive tests, stable API
**Maintenance:** Breaking changes require major version bump

---

### Layer 2: **SELF-VALIDATION** (Ships, but reveal-specific)

**Purpose:** Validate reveal's own architecture and quality
**Location:** `reveal/rules/validation/` and `reveal/adapters/reveal.py`
**Installation:** Included in `pip install reveal-cli`

```
reveal/
├── adapters/
│   └── reveal.py           # reveal:// - Inspect reveal's internals
└── rules/
    └── validation/         # V001-V011 (10 rules, reveal-only)
        ├── V001.py         # Analyzer help completeness
        ├── V002.py         # Analyzer registration
        ├── V003.py         # Analyzer feature support
        ├── V004.py         # Test coverage requirements
        ├── V005.py         # Rule documentation
        ├── V006.py         # Rule registration
        ├── V007.py         # Version consistency
        ├── V008.py         # Adapter help documentation
        ├── V009.py         # Documentation cross-references
        └── V011.py         # Release readiness
```

**Activation Guard:** All V-series rules check `if file_path.startswith('reveal://'):`
**User Impact:** Zero runtime cost for users (rules return early for non-reveal URIs)
**Our Benefit:** Continuous validation of reveal's own quality

**Quality Standard:**
- ✅ Must pass all tests before release
- ✅ Must not impact user performance (early return pattern)
- ✅ Should be comprehensive (catch architecture violations)
- ⚠️ Can be reveal-specific (hardcoded paths to reveal's structure)

**Rationale for Shipping:**
1. **Dogfooding** - We use our own tools on ourselves
2. **Contributor experience** - Contributors can run `reveal reveal:// --check` immediately
3. **Small footprint** - ~2,000 lines / 23,000 total (8.7% of codebase)
4. **Zero user cost** - Guarded by URI check, no performance impact

---

### Layer 3: **DEVELOPMENT TOOLING** (NOT shipped)

**Purpose:** Release automation, analysis, contributor workflows
**Location:** `scripts/`, `internal-docs/`, `tests/`
**Installation:** Only available in git checkout, NOT in pip package

```
scripts/
├── release.sh              # Release automation (tag, build, publish)
├── pre-release-check.sh    # Comprehensive quality gate
├── analyze_duplicate_detection.py
└── (future) generate_coverage_report.py

internal-docs/
├── planning/               # Implementation plans (imports://, etc.)
├── archive/                # Historical design docs
├── ARCHITECTURAL_DILIGENCE.md  # This document
└── DOCUMENTATION_STRUCTURE_GUIDE.md

tests/
├── test_validation_rules.py    # V-series tests (87 tests)
├── test_complexity_rules.py    # C-series tests
└── (20+ test files)
```

**User Value:** ZERO - Users never interact with these
**Developer Value:** CRITICAL - Maintains project quality and consistency

**Quality Standard:**
- ✅ Scripts must be executable and tested
- ✅ Documentation must be current (update with code changes)
- ✅ Tests must maintain >70% coverage

**Exclusion Mechanism:**
```toml
# pyproject.toml
[tool.setuptools.packages.find]
exclude = ["tests*", "scripts*", "internal-docs*"]
```

---

## Quality Standards by Layer

### Public Core Quality Standards

**Code Quality:**
- ✅ All functions pass C901 (complexity ≤10), C902 (length ≤100 lines)
- ✅ All lines pass E501 (length ≤88 characters)
- ✅ No duplicate functions (D001 violations)
- ✅ No security issues (S701 violations)

**Test Coverage:**
- ✅ Minimum 70% overall coverage
- ✅ Critical paths: 90%+ coverage
- ✅ New features require tests before merge

**Documentation:**
- ✅ All adapters have `help://` documentation
- ✅ All analyzers have file pattern registration
- ✅ All rules have `--explain` output
- ✅ Breaking changes documented in CHANGELOG.md

**Performance:**
- ✅ Analyzer registration: <100ms
- ✅ File structure analysis: <1s for 10K line file
- ✅ Rule checking: <5s for 100 file project

**Validation:**
```bash
# Run on all public core files before commit
reveal reveal/analyzers/python.py --check
reveal reveal/rules/complexity/C901.py --check
reveal reveal/adapters/ast.py --check
```

---

### Self-Validation Quality Standards

**Code Quality:**
- ⚠️ V-series rules currently have complexity/length issues (acceptable)
- ✅ Must pass all V-series checks themselves: `reveal reveal:// --check --select V`
- ✅ Should minimize duplicate code (extract shared utilities)

**Current Known Issues:**
- V007.check(): 105 lines (exceeds 100 line limit) - **BLOCKING** for v0.28.0
- V007.check(): Complexity 47 (exceeds 10) - Refactor recommended
- V009.check(): Complexity 29 (exceeds 10) - Refactor recommended
- V011.check(): Complexity 27 (exceeds 10) - Refactor recommended
- `_find_reveal_root()`: Duplicated in V007, V009, V011 - **EXTRACT** to utility

**Test Coverage:**
- ✅ V009: 62% coverage (10 tests)
- ✅ V011: 72% coverage (12 tests)
- 🎯 Target: 70%+ for all V-series rules

**Release Gate:**
```bash
# Must pass before tagging release
reveal reveal:// --check --select V001,V002,V003,V004,V005,V006,V007,V008,V009,V011
```

---

### Development Tooling Quality Standards

**Scripts:**
- ✅ Must be executable (`chmod +x`)
- ✅ Must have clear error messages
- ✅ Must exit with non-zero on failure
- ✅ Should be idempotent (safe to re-run)

**Documentation:**
- ✅ Must be up-to-date (stale docs are worse than no docs)
- ✅ Must include examples
- ✅ Must link to related code/issues

**Tests:**
- ✅ Must run in CI
- ✅ Must pass locally before commit
- ✅ Should run in <60 seconds (fast feedback)

---

## Pre-Release Validation

### Comprehensive Quality Gate

**Before tagging ANY release, ALL of the following must pass:**

#### 1. **V-Series Validation** (Reveal's Metadata)
```bash
reveal reveal:// --check --select V
# Checks: Analyzers registered, rules documented, help complete, version consistent
```

#### 2. **Self-Validation Quality** (Reveal's Own Code)
```bash
# Check critical files for quality issues
reveal reveal/rules/validation/V007.py --check --select C901,C902,E501
reveal reveal/rules/validation/V009.py --check --select C901,C902,E501
reveal reveal/rules/validation/V011.py --check --select C901,C902,E501

# No BLOCKING issues (❌) allowed
# Warnings (⚠️) allowed but should be tracked
```

#### 3. **Test Suite** (All Tests Pass)
```bash
pytest tests/ -v
# All 87+ tests must pass
```

#### 4. **Test Coverage** (Minimum Threshold)
```bash
pytest tests/ --cov=reveal --cov-report=term-missing --cov-fail-under=70
# Overall coverage ≥70%
# New code should have ≥80% coverage
```

#### 5. **Documentation Validation** (No Broken Links)
```bash
reveal README.md --check --select L001
reveal CHANGELOG.md --check --select L001
reveal ROADMAP.md --check --select L001
# All internal links must resolve
```

#### 6. **Version Consistency** (All Files Synchronized)
```bash
reveal reveal:// --check --select V007
# Checks: pyproject.toml, CHANGELOG.md, ROADMAP.md, README.md, AGENT_HELP*.md
```

#### 7. **Release Readiness** (CHANGELOG + ROADMAP Updated)
```bash
reveal reveal:// --check --select V011
# Checks: CHANGELOG has dated entry, ROADMAP mentions version in "What We've Shipped"
```

#### 8. **Build Test** (Package Builds Successfully)
```bash
python -m build --sdist --wheel
# Must produce .tar.gz and .whl without errors
```

---

### Pre-Release Script

**Location:** `scripts/pre-release-check.sh` (to be created)

**Usage:**
```bash
./scripts/pre-release-check.sh
# Exit 0: All checks passed, ready to release
# Exit 1: One or more checks failed, fix before release
```

**Implementation:** See Appendix A for full script

---

## Decision Trees

### Decision Tree 1: "Where Does This Code Go?"

```
New code to add?
│
├─ Does it work on ANY codebase? (not just reveal)
│  ├─ YES → Layer 1: PUBLIC CORE
│  │         Location: reveal/analyzers/, reveal/adapters/, reveal/rules/{category}/
│  │         Examples: C901, L001, Python analyzer
│  │
│  └─ NO → Is it specific to reveal's architecture?
│           │
│           ├─ YES → Layer 2: SELF-VALIDATION
│           │         Location: reveal/rules/validation/, reveal/adapters/reveal.py
│           │         Examples: V007, V009, reveal:// adapter
│           │
│           └─ NO → Is it a development tool/script?
│                     │
│                     ├─ YES → Layer 3: DEVELOPMENT TOOLING
│                     │         Location: scripts/, internal-docs/
│                     │         Examples: release.sh, planning docs
│                     │
│                     └─ NO → Is it a test?
│                               │
│                               ├─ YES → tests/ (not shipped)
│                               └─ NO → Re-evaluate purpose
```

---

### Decision Tree 2: "Should This Be a V-Series Rule or a Script?"

```
Quality check to add?
│
├─ Should it block releases? (gate check)
│  ├─ YES → Can it be a reveal rule?
│  │         │
│  │         ├─ YES → V-series rule (e.g., V012 code quality)
│  │         │         Benefit: Dogfooding, runs in CI, user-visible
│  │         │
│  │         └─ NO → Development script (e.g., license audit)
│  │                   Benefit: Flexibility, external dependencies OK
│  │
│  └─ NO → Is it informational/diagnostic?
│            │
│            ├─ YES → Maybe an adapter or stats:// query
│            └─ NO → Maybe not needed
```

---

### Decision Tree 3: "Should This V-Rule Be Generalized?"

```
V-series rule under consideration
│
├─ Is the concept useful to OTHER projects?
│  ├─ YES → Can it work WITHOUT hardcoded reveal paths?
│  │         │
│  │         ├─ YES → Generalize to M-series or new category
│  │         │         Examples: V007 → M104 (version consistency)
│  │         │                   V009 → Already general (doc links)
│  │         │
│  │         └─ NO → Keep as V-series, document why
│  │                   Example: V001 (checks reveal's analyzer registry)
│  │
│  └─ NO → Keep as V-series (reveal-specific)
│            Example: V002 (analyzer registration check)
```

---

## Development Workflows

### Daily Development Workflow

**Before committing code:**
```bash
# 1. Run tests related to your changes
pytest tests/test_validation_rules.py -v

# 2. Check quality of files you modified
reveal reveal/rules/validation/V012.py --check

# 3. Ensure no new issues introduced
git diff --name-only | grep '.py$' | xargs -I {} reveal {} --check

# 4. Run full test suite (optional but recommended)
pytest tests/ -v
```

---

### Adding a New Analyzer

**Checklist:**
```bash
# 1. Create analyzer file
reveal/analyzers/my_language.py

# 2. Register in reveal/analyzers/__init__.py
from .my_language import MyLanguageAnalyzer
register_analyzer('my_language', MyLanguageAnalyzer, ['*.mylang'])

# 3. Add help documentation
# Include get_help() method in analyzer

# 4. Create tests
tests/test_my_language_analyzer.py

# 5. Validate
reveal reveal:// --check --select V001  # Analyzer help complete?
reveal reveal:// --check --select V002  # Analyzer registered?
reveal reveal:// --check --select V003  # Features implemented?

# 6. Test on real files
reveal example.mylang
reveal example.mylang --outline
```

---

### Adding a New Rule

**Checklist:**
```bash
# 1. Choose category
# B (bugs), C (complexity), D (duplicates), E (errors),
# L (links), M (maintainability), N (infrastructure),
# R (refactoring), S (security), U (urls), V (validation)

# 2. Create rule file
reveal/rules/{category}/X###.py

# 3. Implement BaseRule interface
class X###(BaseRule):
    code = "X###"
    message = "Clear description"
    severity = Severity.MEDIUM
    category = RulePrefix.CATEGORY

    def check(self, file_path, structure, content):
        # Implementation

# 4. Add tests
tests/test_{category}_rules.py

# 5. Validate
reveal --explain X###  # Documentation present?
pytest tests/test_{category}_rules.py -v

# 6. Update documentation
# Add to README.md rule count
# Add to CHANGELOG.md
```

---

### Adding a V-Series Rule (Self-Validation)

**Extra requirements beyond normal rule:**
```bash
# 1. Add reveal:// guard
def check(self, file_path, structure, content):
    if not file_path.startswith('reveal://'):
        return []  # Skip for user projects

# 2. Use _find_reveal_root() utility
reveal_root = self._find_reveal_root()
if not reveal_root:
    return []

# 3. Test on reveal://
reveal reveal:// --check --select V###

# 4. Add comprehensive tests
# Include edge cases: reveal root not found, files missing, etc.

# 5. Justify why it's V-series, not general
# Document in this file under "Self-Validation Strategy"
```

---

### Release Workflow

**Step-by-step process:**

```bash
# 1. Ensure on clean main branch
git checkout main
git pull origin main
git status  # Should be clean

# 2. Update version
# Edit: pyproject.toml, reveal/__init__.py
# Update: CHANGELOG.md (add date to [Unreleased] → [X.Y.Z] - YYYY-MM-DD)
# Update: ROADMAP.md ("Current version" + "What We've Shipped")
# Update: README.md (version badge if present)
# Update: reveal/AGENT_HELP.md, reveal/AGENT_HELP_FULL.md

# 3. Run pre-release validation
./scripts/pre-release-check.sh
# Must exit 0 (all checks passed)

# 4. Commit version bump
git add .
git commit -m "chore: Bump version to vX.Y.Z"

# 5. Tag release
git tag -a vX.Y.Z -m "Release vX.Y.Z"

# 6. Build package
python -m build --sdist --wheel

# 7. Test install locally
pip install dist/reveal_cli-X.Y.Z-py3-none-any.whl
reveal --version  # Should show X.Y.Z

# 8. Push to GitHub (triggers CI)
git push origin main
git push origin vX.Y.Z

# 9. Publish to PyPI (after CI passes)
python -m twine upload dist/*

# 10. Create GitHub release
gh release create vX.Y.Z --notes "See CHANGELOG.md"
```

---

## Self-Validation Strategy

### Current V-Series Rules (What They Check)

| Rule | Purpose | Rationale | Generalize? |
|------|---------|-----------|-------------|
| **V001** | Analyzer help documentation complete | Ensures discoverability via `help://` | ❌ Reveal-specific |
| **V002** | Analyzer file registered in `__init__.py` | Prevents orphaned analyzer files | ❌ Reveal-specific |
| **V003** | Analyzer implements standard features | Ensures consistent user experience | ❌ Reveal-specific |
| **V004** | Test coverage for analyzers | Prevents untested code paths | ⚠️ Could generalize (pytest-cov) |
| **V005** | Rule documentation via `--explain` | Ensures all rules are documented | ❌ Reveal-specific |
| **V006** | Rule registered in category `__init__.py` | Prevents orphaned rule files | ❌ Reveal-specific |
| **V007** | Version consistency across files | Prevents version drift in releases | ✅ **Should generalize** (M104) |
| **V008** | Adapter help documentation complete | Ensures adapter discoverability | ❌ Reveal-specific |
| **V009** | Documentation cross-references valid | Prevents broken internal links | ✅ **Already general** (works on any MD) |
| **V011** | Release readiness (CHANGELOG + ROADMAP) | Automates pre-release checklist | ⚠️ Could generalize (M105) |

---

### Proposed V-Series Rules (Future)

| Rule | Purpose | Priority | Notes |
|------|---------|----------|-------|
| **V010** | Planning doc freshness (<90 days) | Low | Optional, marked in fierce-squall-1231 |
| **V012** | Code quality gate (C901, C902, E501) | **HIGH** | Would catch our current issues |
| **V013** | Cross-file duplicate detection | Medium | Would catch `_find_reveal_root()` duplication |
| **V014** | Import graph consistency | Low | After imports:// implementation |

---

### Why Ship V-Series Rules to Users?

**Arguments FOR shipping:**
1. ✅ **Dogfooding** - We use the same tools as users
2. ✅ **Contributor onboarding** - `git clone` → `reveal reveal://` works immediately
3. ✅ **Zero user cost** - Early return pattern (no performance impact)
4. ✅ **Small footprint** - ~2,000 lines (8.7% of codebase)
5. ✅ **Transparency** - Users can see how we validate ourselves

**Arguments AGAINST shipping:**
1. ❌ **Code bloat** - Users install code they can't use
2. ❌ **Maintenance burden** - Every change affects public API
3. ❌ **Confusing** - Rules that only work on reveal:// might confuse users

**Decision:** **SHIP** V-series rules (current approach is correct)

**Rationale:**
- Pros outweigh cons (dogfooding + zero cost)
- Aligns with Python ecosystem norms (pytest, ruff, black all self-check)
- Small size doesn't justify splitting into separate package
- Guarded execution prevents user impact

---

### Generalization Roadmap

**v0.28.0 (Current):**
- ✅ V007, V009, V011 are reveal-specific (hardcoded paths)
- ✅ All V-series rules guarded by `if reveal://`

**v0.29.0 (Planned):**
- 🎯 Create V012 (code quality gate)
- 🎯 Extract `_find_reveal_root()` to shared utility
- 🎯 Refactor V007/V009/V011 to reduce complexity

**v0.30.0 (Future):**
- 🔄 Generalize V007 → M104 (configurable version consistency check)
  - Allow users to specify which files to check via `.reveal.yaml`
  - Parameterize file patterns (pyproject.toml, package.json, etc.)
- 🔄 Enhance V009 → Works on any project (already close, just remove guard)
- 🔄 Generalize V011 → M105 (configurable release readiness)
  - Allow users to specify CHANGELOG/ROADMAP patterns

**v1.0.0 (Long-term):**
- 🚀 V-series becomes reveal-specific architecture checks only
- 🚀 General-purpose checks moved to M-series or new categories
- 🚀 Plugin system allows users to add custom validation rules

---

## Long-Term Vision

### Year 1 (v0.28 - v0.35)

**Goals:**
- ✅ Establish quality gates (pre-release script)
- ✅ Achieve 80%+ test coverage
- ✅ Generalize useful V-rules (V007, V009, V011 → M-series)
- ✅ Implement imports:// adapter
- ✅ Add cross-file analysis capabilities
- 🎯 Explore Intent Lenses (community-curated relevance)

**Metrics:**
- Pre-release script blocks >0 bad releases
- Test coverage: 70% → 80%
- V-series rules: 10 → 15
- General rules: 30 → 40

**Related Planning:**
- [imports:// Implementation Plan](planning/IMPORTS_IMPLEMENTATION_PLAN.md)
- [Intent Lenses Design](planning/INTENT_LENSES_DESIGN.md)

---

### Year 2 (v0.36 - v1.0.0)

**Goals:**
- 🎯 Stabilize public API (v1.0.0 release)
- 🎯 Plugin system for custom rules
- 🎯 Language server protocol (LSP) integration
- 🎯 CI/CD integration guides (GitHub Actions, GitLab CI)
- 🎯 Intent Lenses (if prototype successful in v0.29-v0.30)
- 🎯 Community lens repository (tldr-style curation)

**Metrics:**
- Breaking changes: 0 (stable API)
- Plugin ecosystem: 5+ community plugins
- Adoption: 1000+ PyPI downloads/month
- Community lenses: 20+ curated patterns

---

### Year 3+ (v1.x - v2.0)

**Goals:**
- 🚀 Multi-language analysis (beyond tree-sitter)
- 🚀 Semantic code search (AST-based queries)
- 🚀 IDE integrations (VSCode, PyCharm)
- 🚀 Cloud-based analysis (reveal-as-a-service)

**Metrics:**
- Language support: 15 → 30+
- Enterprise adoption: 10+ companies
- Contributor community: 20+ active contributors

---

## Appendices

### Appendix A: Pre-Release Check Script

**File:** `scripts/pre-release-check.sh`

```bash
#!/bin/bash
# Comprehensive reveal pre-release validation
# Exit 0: Ready to release
# Exit 1: Issues found, fix before release

set -e  # Exit on first error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "╔════════════════════════════════════════════════════════╗"
echo "║  Reveal Pre-Release Validation                        ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

cd "$PROJECT_ROOT"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track failures
FAILURES=0

# Helper function
check_step() {
    local step_name="$1"
    local step_num="$2"
    local total_steps="$3"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "[$step_num/$total_steps] $step_name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# 1. V-Series Validation
check_step "V-Series Validation (Reveal's Metadata)" 1 8

if reveal reveal:// --check --select V; then
    echo -e "${GREEN}✓ V-series validation passed${NC}"
else
    echo -e "${RED}✗ V-series validation FAILED${NC}"
    FAILURES=$((FAILURES + 1))
fi

# 2. Self-Validation Quality
check_step "Self-Validation Code Quality (V007, V009, V011)" 2 8

for file in V007 V009 V011; do
    echo "Checking reveal/rules/validation/${file}.py..."
    if reveal "reveal/rules/validation/${file}.py" --check --select C901,C902,E501; then
        echo -e "${GREEN}✓ ${file}.py passed${NC}"
    else
        echo -e "${YELLOW}⚠ ${file}.py has quality issues (review manually)${NC}"
        # Don't fail build for warnings, but note them
    fi
done

# 3. Test Suite
check_step "Test Suite (All Tests)" 3 8

if pytest tests/ -v; then
    echo -e "${GREEN}✓ All tests passed${NC}"
else
    echo -e "${RED}✗ Tests FAILED${NC}"
    FAILURES=$((FAILURES + 1))
fi

# 4. Test Coverage
check_step "Test Coverage (≥70%)" 4 8

if pytest tests/ --cov=reveal --cov-report=term-missing --cov-fail-under=70; then
    echo -e "${GREEN}✓ Coverage requirement met${NC}"
else
    echo -e "${RED}✗ Coverage below 70%${NC}"
    FAILURES=$((FAILURES + 1))
fi

# 5. Documentation Validation
check_step "Documentation Links (No Broken Links)" 5 8

for doc in README.md CHANGELOG.md ROADMAP.md; do
    if [ -f "$doc" ]; then
        echo "Checking $doc..."
        if reveal "$doc" --check --select L001; then
            echo -e "${GREEN}✓ $doc links valid${NC}"
        else
            echo -e "${RED}✗ $doc has broken links${NC}"
            FAILURES=$((FAILURES + 1))
        fi
    fi
done

# 6. Version Consistency
check_step "Version Consistency (All Files Synchronized)" 6 8

if reveal reveal:// --check --select V007; then
    echo -e "${GREEN}✓ Version consistent across all files${NC}"
else
    echo -e "${RED}✗ Version mismatch detected${NC}"
    FAILURES=$((FAILURES + 1))
fi

# 7. Release Readiness
check_step "Release Readiness (CHANGELOG + ROADMAP)" 7 8

if reveal reveal:// --check --select V011; then
    echo -e "${GREEN}✓ Release documentation ready${NC}"
else
    echo -e "${RED}✗ Release documentation not ready${NC}"
    FAILURES=$((FAILURES + 1))
fi

# 8. Build Test
check_step "Build Test (Package Creation)" 8 8

if python -m build --sdist --wheel; then
    echo -e "${GREEN}✓ Package builds successfully${NC}"
else
    echo -e "${RED}✗ Build FAILED${NC}"
    FAILURES=$((FAILURES + 1))
fi

# Summary
echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║  Validation Summary                                    ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

if [ $FAILURES -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed! Ready to release.${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. git commit -m 'chore: Bump version to vX.Y.Z'"
    echo "  2. git tag -a vX.Y.Z -m 'Release vX.Y.Z'"
    echo "  3. git push origin main"
    echo "  4. git push origin vX.Y.Z"
    echo ""
    exit 0
else
    echo -e "${RED}✗ $FAILURES check(s) failed. Fix issues before releasing.${NC}"
    echo ""
    echo "Review failures above and re-run: ./scripts/pre-release-check.sh"
    echo ""
    exit 1
fi
```

---

### Appendix B: Code Placement Reference

**Quick reference table for "where does this go?"**

| What | Where | Shipped? | Example |
|------|-------|----------|---------|
| **Language analyzer** | `reveal/analyzers/` | ✅ Yes | `python.py`, `javascript.py` |
| **URI adapter** | `reveal/adapters/` | ✅ Yes | `ast.py`, `json_adapter.py` |
| **General rule** | `reveal/rules/{category}/` | ✅ Yes | `C901.py`, `L001.py` |
| **Reveal-specific rule** | `reveal/rules/validation/` | ✅ Yes | `V007.py`, `V009.py` |
| **Reveal-specific adapter** | `reveal/adapters/reveal.py` | ✅ Yes | `RevealAdapter` |
| **Core logic** | `reveal/` (root) | ✅ Yes | `main.py`, `registry.py` |
| **Test file** | `tests/` | ❌ No | `test_validation_rules.py` |
| **Development script** | `scripts/` | ❌ No | `release.sh` |
| **Planning doc** | `internal-docs/planning/` | ❌ No | `IMPORTS_PLAN.md` |
| **Architecture doc** | `internal-docs/` | ❌ No | This file |
| **Public guide** | `docs/` or `reveal/*.md` | ⚠️ Maybe | `LINK_VALIDATION_GUIDE.md` |

---

### Appendix C: Quality Issue Severity Levels

**How to interpret reveal's own quality issues:**

| Symbol | Severity | Meaning | Action Required |
|--------|----------|---------|-----------------|
| **❌** | Error | Exceeds hard limit | **BLOCKING** - Must fix before release |
| **⚠️** | Warning | Approaching limit | Refactor recommended, not blocking |
| **ℹ️** | Info | Minor issue | Fix if convenient, track in backlog |

**Examples:**
- ❌ C902: Function >100 lines → BLOCKING (exceeds hard limit)
- ⚠️ C901: Complexity >10 → Warning (should refactor)
- ℹ️ E501: Line >88 chars → Info (minor formatting)

**Current state (v0.27.1):**
- V007.py: ❌ 1 error (105 line function) - **MUST FIX** for v0.28.0
- V007.py: ⚠️ 2 warnings (complexity) - Refactor recommended
- V009.py: ⚠️ 2 warnings (complexity) - Refactor recommended
- V011.py: ⚠️ 2 warnings (complexity) - Refactor recommended

---

### Appendix D: Contribution Guidelines

**For external contributors:**

1. **Read this document** - Understand architectural boundaries
2. **Choose the right layer** - Use decision trees in Section 5
3. **Follow quality standards** - Match existing code quality
4. **Add tests** - Minimum 70% coverage for new code
5. **Update documentation** - CHANGELOG.md + relevant guides
6. **Run pre-release checks** - Even for small PRs
7. **Ask questions** - File an issue if unclear

**PR checklist:**
- [ ] Code is in the correct layer (public/self-validation/dev)
- [ ] Tests added (≥70% coverage)
- [ ] Documentation updated
- [ ] `reveal <changed-file> --check` passes
- [ ] `pytest tests/` passes
- [ ] CHANGELOG.md updated

---

### Appendix E: Update Schedule for This Document

**This document should be updated when:**

1. **New architectural layer added** - Update Section 2
2. **Quality standards change** - Update Section 3
3. **Pre-release process changes** - Update Section 4 + Appendix A
4. **New decision patterns emerge** - Update Section 5
5. **V-series rules added/generalized** - Update Section 7
6. **Version milestones reached** - Update Section 8

**Review schedule:**
- **Every release** - Validate current state matches document
- **Quarterly** - Review long-term vision progress
- **Annually** - Major revision for architectural shifts

**Change process:**
1. Propose changes in PR or issue
2. Discuss with maintainers
3. Update document with rationale
4. Link to related code changes

---

## Document History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0.0 | 2025-12-31 | Initial comprehensive diligence document | TIA |

---

**End of Document**

---

**Living Document Notice:** This document evolves with reveal. When reveal changes, update this document. When this document changes, update reveal. They should stay synchronized.

**Questions?** File an issue or discuss in `internal-docs/planning/`

**Suggestions?** PRs welcome! Architectural improvements are always considered.
