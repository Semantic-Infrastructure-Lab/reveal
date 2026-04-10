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
check_step "V-Series Validation (Reveal's Metadata)" 1 9

if reveal reveal:// --check --select V; then
    echo -e "${GREEN}✓ V-series validation passed${NC}"
else
    echo -e "${RED}✗ V-series validation FAILED${NC}"
    FAILURES=$((FAILURES + 1))
fi

# 2. Self-Validation Quality
check_step "Self-Validation Code Quality (V007, V009, V011)" 2 9

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
check_step "Test Suite (All Tests)" 3 9

if pytest tests/ -v; then
    echo -e "${GREEN}✓ All tests passed${NC}"
else
    echo -e "${RED}✗ Tests FAILED${NC}"
    FAILURES=$((FAILURES + 1))
fi

# 4. Test Coverage
check_step "Test Coverage (≥70%)" 4 9

if pytest tests/ --cov=reveal --cov-report=term-missing --cov-fail-under=70; then
    echo -e "${GREEN}✓ Coverage requirement met${NC}"
else
    echo -e "${RED}✗ Coverage below 70%${NC}"
    FAILURES=$((FAILURES + 1))
fi

# 5. Documentation Validation
check_step "Documentation Links (No Broken Links)" 5 9

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

# 6. Doc Hygiene (broken links, internal-docs refs, TIA leaks)
check_step "Doc Hygiene (Links + Leak Detection)" 6 9

if python3 "$SCRIPT_DIR/check_doc_hygiene.py"; then
    echo -e "${GREEN}✓ Doc hygiene passed${NC}"
else
    echo -e "${RED}✗ Doc hygiene issues found${NC}"
    FAILURES=$((FAILURES + 1))
fi

# 7. Version Consistency
check_step "Version Consistency (All Files Synchronized)" 7 9

if reveal reveal:// --check --select V007; then
    echo -e "${GREEN}✓ Version consistent across all files${NC}"
else
    echo -e "${RED}✗ Version mismatch detected${NC}"
    FAILURES=$((FAILURES + 1))
fi

# 8. Release Readiness
check_step "Release Readiness (CHANGELOG + ROADMAP)" 8 9

if reveal reveal:// --check --select V011; then
    echo -e "${GREEN}✓ Release documentation ready${NC}"
else
    echo -e "${RED}✗ Release documentation not ready${NC}"
    FAILURES=$((FAILURES + 1))
fi

# 9. Build Test
check_step "Build Test (Package Creation)" 9 9

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
