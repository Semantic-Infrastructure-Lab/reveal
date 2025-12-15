#!/usr/bin/env bash
#
# Reveal Release Script
#
# Usage: ./scripts/release.sh <version>
# Example: ./scripts/release.sh 0.10.0
#
# This script handles the complete release process:
# 1. Pre-flight checks (clean repo, tests pass, etc.)
# 2. Version bump in pyproject.toml
# 3. CHANGELOG reminder/validation
# 4. Git commit and tag
# 5. Push to GitHub
# 6. Create GitHub release (triggers auto-publish to PyPI)
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

# Check if version argument provided
if [ $# -ne 1 ]; then
    error "Usage: $0 <version>\nExample: $0 0.10.0"
fi

NEW_VERSION="$1"

# Validate version format (semantic versioning)
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    error "Invalid version format: $NEW_VERSION\nMust be semantic versioning (e.g., 0.10.0)"
fi

echo "=========================================="
echo "  Reveal Release Script"
echo "  Version: $NEW_VERSION"
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

# Check if version already exists as a tag
if git rev-parse "v$NEW_VERSION" >/dev/null 2>&1; then
    error "Version v$NEW_VERSION already exists as a git tag"
fi

# Check if GitHub CLI is installed
if ! command -v gh &> /dev/null; then
    error "GitHub CLI (gh) not found. Install it: https://cli.github.com/"
fi

# Check if authenticated with GitHub
if ! gh auth status &> /dev/null; then
    error "Not authenticated with GitHub. Run: gh auth login"
fi

# Pull latest changes
info "Pulling latest changes from origin..."
git pull origin master || error "Failed to pull from origin"

success "Pre-flight checks passed"
echo

# ============================================================================
# CURRENT VERSION CHECK
# ============================================================================

CURRENT_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
info "Current version: $CURRENT_VERSION"
info "New version: $NEW_VERSION"
echo

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
# VERSION BUMP
# ============================================================================

info "Updating version in pyproject.toml..."

# Update version in pyproject.toml
sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" pyproject.toml

# Verify the change
NEW_VERSION_CHECK=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
if [ "$NEW_VERSION_CHECK" != "$NEW_VERSION" ]; then
    error "Failed to update version in pyproject.toml"
fi

success "Version updated to $NEW_VERSION in pyproject.toml"
echo

# ============================================================================
# BUILD AND TEST
# ============================================================================

info "Building package to verify it works..."

# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build
python3 -m build || error "Build failed"

# Check the built distribution
twine check dist/* || error "Distribution check failed"

success "Package built successfully"
echo

# ============================================================================
# GIT COMMIT AND TAG
# ============================================================================

info "Creating git commit and tag..."

# Stage changes
git add pyproject.toml CHANGELOG.md

# Commit
git commit -m "chore: Bump version to $NEW_VERSION" || error "Failed to create commit"

# Create annotated tag
git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION

See CHANGELOG.md for details." || error "Failed to create tag"

success "Created commit and tag v$NEW_VERSION"
echo

# ============================================================================
# PUSH TO GITHUB
# ============================================================================

info "Pushing to GitHub..."

# Push commit and tag
git push origin master || error "Failed to push commit"
git push origin "v$NEW_VERSION" || error "Failed to push tag"

success "Pushed to GitHub"
echo

# ============================================================================
# CREATE GITHUB RELEASE
# ============================================================================

info "Creating GitHub release..."

# Extract CHANGELOG section for this version
CHANGELOG_SECTION=$(awk "/## \[?$NEW_VERSION\]?/,/## \[?[0-9]/" CHANGELOG.md | sed '1d;$d' | sed '/^$/d')

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
# DONE
# ============================================================================

echo "=========================================="
echo -e "${GREEN}  ✓ Release v$NEW_VERSION Complete!${NC}"
echo "=========================================="
echo
echo "Next steps:"
echo "1. Monitor GitHub Actions: https://github.com/Semantic-Infrastructure-Lab/reveal/actions"
echo "2. Verify PyPI publish: https://pypi.org/project/reveal-cli/$NEW_VERSION/"
echo "3. Test installation: pip install --upgrade reveal-cli"
echo
info "The GitHub Actions workflow will automatically publish to PyPI"
info "This usually takes 1-2 minutes"
echo
