#!/usr/bin/env bash
#
# Reveal Release Script
#
# Usage: ./scripts/release.sh <version> [--resume] [--dry-run]
# Example: ./scripts/release.sh 0.10.0
#
# Flags:
#   --resume   Tag exists but no GitHub release (interrupted release). Moves
#              the tag to HEAD, then creates the GitHub release. Runs tests.
#   --dry-run  Validate everything (pre-flight, changelog, self-check, tests)
#              but skip all git/push/release operations.
#
# This script handles the complete release process:
# 1. Pre-flight checks (clean repo, on master, etc.)
# 2. CHANGELOG validation
# 3. Version bump in pyproject.toml (before tests, so version-match tests pass)
# 4. Reveal self-check (V007/V011/V012/V013)
# 5. Test suite
# 6. Build package
# 7. Git commit and tag
# 8. Push to GitHub
# 9. Create GitHub release (triggers auto-publish to PyPI)
# 10. Poll PyPI to confirm publish landed
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
error() {
    echo -e "${RED}ERROR: $1${NC}" >&2
    exit 1
}

success() {
    echo -e "${GREEN}✓ $1${NC}"
}

info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

warn() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# ============================================================================
# ARGUMENT PARSING
# ============================================================================

NEW_VERSION=""
RESUME_MODE=false
DRY_RUN=false

for arg in "$@"; do
    case $arg in
        --resume)  RESUME_MODE=true ;;
        --dry-run) DRY_RUN=true ;;
        --*)       error "Unknown flag: $arg\nUsage: $0 <version> [--resume] [--dry-run]" ;;
        *)
            if [ -n "$NEW_VERSION" ]; then
                error "Unexpected argument: $arg"
            fi
            NEW_VERSION="$arg"
            ;;
    esac
done

if [ -z "$NEW_VERSION" ]; then
    error "Usage: $0 <version> [--resume] [--dry-run]\nExample: $0 0.10.0"
fi

# Validate version format (semantic versioning)
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    error "Invalid version format: $NEW_VERSION\nMust be semantic versioning (e.g., 0.10.0)"
fi

DRY_RUN_PREFIX=""
$DRY_RUN && DRY_RUN_PREFIX="[DRY RUN] "

echo "=========================================="
echo "  Reveal Release Script"
echo "  Version: $NEW_VERSION"
$DRY_RUN && echo "  Mode: DRY RUN — no git/push/release ops"
$RESUME_MODE && echo "  Mode: RESUME — will retag and create release"
echo "=========================================="
echo

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================

info "Running pre-flight checks..."

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ] || [ ! -d "reveal" ]; then
    error "Must be run from the reveal project root directory"
fi

# Check if on master branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "master" ]; then
    error "Must be on master branch (currently on: $CURRENT_BRANCH)"
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    error "Uncommitted changes detected. Commit or stash them first.\n$(git status --short)"
fi

# Check if version tag already exists
TAG_EXISTS=false
if git rev-parse "v$NEW_VERSION" >/dev/null 2>&1; then
    TAG_EXISTS=true
    if $RESUME_MODE; then
        # Tag exists — check if GitHub release also exists
        if gh release view "v$NEW_VERSION" >/dev/null 2>&1; then
            warn "Tag AND GitHub release for v$NEW_VERSION already exist."
            warn "If publish failed, check: gh run list"
            error "Release appears complete. Verify PyPI: pip index versions reveal-cli"
        fi
        warn "Tag v$NEW_VERSION exists but no GitHub release — resuming interrupted release"
        warn "Will move tag to HEAD, then create GitHub release"
    else
        error "Version v$NEW_VERSION already exists as a git tag.\n\nIf the release was interrupted after tagging, use:\n  $0 $NEW_VERSION --resume"
    fi
fi

# Check if GitHub CLI is installed
if ! command -v gh &> /dev/null; then
    error "GitHub CLI (gh) not found. Install it: https://cli.github.com/"
fi

# Check if authenticated with GitHub
if ! gh auth status &> /dev/null; then
    error "Not authenticated with GitHub. Run: gh auth login"
fi

# Pull latest changes (skip in resume mode — we intentionally have commits ahead of tag)
if ! $RESUME_MODE; then
    info "Pulling latest changes from origin..."
    git pull --ff-only origin master || error "Failed to pull from origin (hint: repo may have diverged — rebase manually)"
fi

success "Pre-flight checks passed"
echo

# ============================================================================
# CURRENT VERSION CHECK
# ============================================================================

CURRENT_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
info "Current version in pyproject.toml: $CURRENT_VERSION"
info "Target release version: $NEW_VERSION"
echo

# Verify new version is >= current version
if ! python3 - <<EOF
import sys
from packaging.version import Version
cur = Version("$CURRENT_VERSION")
new = Version("$NEW_VERSION")
sys.exit(0 if new >= cur else 1)
EOF
then
    error "New version ($NEW_VERSION) must be >= current version ($CURRENT_VERSION) — cannot release a lower version"
fi

info "Proceeding with release v$NEW_VERSION"
echo

# ============================================================================
# CHANGELOG CHECK
# ============================================================================

info "Checking CHANGELOG.md..."

if ! grep -q "## \[$NEW_VERSION\]" CHANGELOG.md && ! grep -q "## $NEW_VERSION" CHANGELOG.md; then
    warn "CHANGELOG.md does not contain an entry for version $NEW_VERSION"
    echo
    echo "Please add a CHANGELOG entry with the following format:"
    echo
    echo "## [$NEW_VERSION] - $(date +%Y-%m-%d)"
    echo
    echo "### Added"
    echo "- New feature description"
    echo
    echo "### Changed"
    echo "- What changed"
    echo

    error "CHANGELOG.md must contain version $NEW_VERSION before release"
fi

success "CHANGELOG.md contains entry for v$NEW_VERSION"
echo

# ============================================================================
# VERSION BUMP (before self-check and tests so version-match assertions pass)
# ============================================================================

CURRENT_VERSION_IN_FILE=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
if [ "$CURRENT_VERSION_IN_FILE" = "$NEW_VERSION" ]; then
    info "Version already at $NEW_VERSION in pyproject.toml (pre-bumped)"
elif $DRY_RUN; then
    info "${DRY_RUN_PREFIX}Would bump pyproject.toml: $CURRENT_VERSION_IN_FILE → $NEW_VERSION"
else
    info "Bumping pyproject.toml: $CURRENT_VERSION_IN_FILE → $NEW_VERSION..."
    sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" pyproject.toml

    # Verify the change
    NEW_VERSION_CHECK=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
    if [ "$NEW_VERSION_CHECK" != "$NEW_VERSION" ]; then
        error "Failed to update version in pyproject.toml"
    fi

    # If tests fail or the script exits early, roll back pyproject.toml so the
    # repo stays clean. The trap is cleared after tests pass (see below).
    trap 'warn "Rolling back pyproject.toml to $CURRENT_VERSION"; sed -i "s/^version = \".*\"/version = \"$CURRENT_VERSION\"/" pyproject.toml' EXIT

    success "Version bumped to $NEW_VERSION"
fi
echo

# ============================================================================
# REVEAL SELF-CHECK
# ============================================================================

info "Running reveal self-check (V007/V011/V012/V013)..."

if ! command -v reveal &> /dev/null; then
    warn "reveal not found in PATH — skipping self-check (install with: pip install -e .)"
else
    reveal reveal:// --check || error "reveal self-check failed — fix documentation issues before releasing"
    success "Reveal self-check passed"
fi
echo

# ============================================================================
# TESTS
# ============================================================================

info "Running test suite..."

python3 -m pytest tests/ -q --tb=short || error "Tests failed — fix failures before releasing"

success "All tests passed"

# Tests passed — version bump is permanent; disable the rollback trap
trap - EXIT
echo

# ============================================================================
# BUILD
# ============================================================================

if $DRY_RUN; then
    info "${DRY_RUN_PREFIX}Would build package (skipping)"
else
    info "Building package to verify it works..."

    # Clean previous builds
    rm -rf dist/ build/ *.egg-info

    # Build
    python3 -m build || error "Build failed"

    # Check the built distribution
    twine check dist/* || error "Distribution check failed"

    success "Package built successfully"
fi
echo

# ============================================================================
# GIT COMMIT AND TAG
# ============================================================================

if $DRY_RUN; then
    info "${DRY_RUN_PREFIX}Would commit + tag v$NEW_VERSION (skipping all git ops)"
    echo
    echo "=========================================="
    echo -e "${GREEN}  ✓ Dry run complete — no changes made${NC}"
    echo "=========================================="
    echo
    echo "Run without --dry-run to perform the release."
    exit 0
fi

info "Creating git commit and tag..."

# Stage changes
git add pyproject.toml CHANGELOG.md

# Commit only if there are staged changes (version may have been pre-bumped)
if git diff --staged --quiet; then
    info "Version already at $NEW_VERSION, skipping bump commit..."
else
    git commit -m "chore: Bump version to $NEW_VERSION" || error "Failed to create commit"
fi

if $RESUME_MODE && $TAG_EXISTS; then
    info "Moving tag v$NEW_VERSION to HEAD (was at $(git rev-parse --short v$NEW_VERSION))..."
    git tag -d "v$NEW_VERSION" || error "Failed to delete local tag"
    git push --delete origin "v$NEW_VERSION" 2>/dev/null || warn "Remote tag v$NEW_VERSION not found — skipping remote delete (tag was local-only)"
fi

# Create annotated tag
git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION

See CHANGELOG.md for details." || error "Failed to create tag"

success "Created tag v$NEW_VERSION at HEAD ($(git rev-parse --short HEAD))"
echo

# ============================================================================
# PUSH TO GITHUB
# ============================================================================

info "Pushing to GitHub..."

git push origin master || error "Failed to push commit"
git push origin "v$NEW_VERSION" || error "Failed to push tag"

success "Pushed to GitHub"
echo

# ============================================================================
# CREATE GITHUB RELEASE
# ============================================================================

info "Creating GitHub release..."

# Extract CHANGELOG section for this version
CHANGELOG_SECTION=$(awk "/## \[?${NEW_VERSION//./\\.}\]?/{found=1; next} found && /## \[/{exit} found{print}" CHANGELOG.md)

if [ -z "$CHANGELOG_SECTION" ]; then
    warn "Could not extract CHANGELOG section for v$NEW_VERSION"
    CHANGELOG_SECTION="See [CHANGELOG.md](https://github.com/Semantic-Infrastructure-Lab/reveal/blob/master/CHANGELOG.md) for details."
fi

# Create release notes
RELEASE_NOTES="## Release v$NEW_VERSION

$CHANGELOG_SECTION

---

**Install/Upgrade:**
\`\`\`bash
pip install --upgrade reveal-cli
\`\`\`

**Documentation:** https://github.com/Semantic-Infrastructure-Lab/reveal
**Full Changelog:** https://github.com/Semantic-Infrastructure-Lab/reveal/blob/master/CHANGELOG.md"

# Create GitHub release (this triggers the publish-to-pypi workflow)
gh release create "v$NEW_VERSION" \
    --title "v$NEW_VERSION" \
    --notes "$RELEASE_NOTES" \
    || error "Failed to create GitHub release"

success "GitHub release created: https://github.com/Semantic-Infrastructure-Lab/reveal/releases/tag/v$NEW_VERSION"
echo

# ============================================================================
# WAIT FOR PYPI
# ============================================================================

info "Waiting for PyPI publish (usually 1-2 minutes)..."

PYPI_CONFIRMED=false
for i in {1..18}; do
    sleep 10
    if pip index versions reveal-cli 2>/dev/null | grep -q "Available versions:.*$NEW_VERSION"; then
        PYPI_CONFIRMED=true
        break
    fi
    info "Waiting... (${i}0s elapsed)"
done

echo

# ============================================================================
# DONE
# ============================================================================

echo "=========================================="
echo -e "${GREEN}  ✓ Release v$NEW_VERSION Complete!${NC}"
echo "=========================================="
echo

if $PYPI_CONFIRMED; then
    success "v$NEW_VERSION is live on PyPI"
else
    warn "PyPI publish not confirmed after 3 minutes — check Actions:"
    echo "  gh run list --limit 5"
    echo "  pip index versions reveal-cli"
fi

echo
echo "Monitor: https://github.com/Semantic-Infrastructure-Lab/reveal/actions"
echo "PyPI:    https://pypi.org/project/reveal-cli/$NEW_VERSION/"
echo "Install: pip install --upgrade reveal-cli"
echo
