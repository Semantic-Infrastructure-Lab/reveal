---
title: Reveal Release Process
type: documentation
category: maintainer
date: 2025-12-14
---

# Reveal Release Process

**Automated release script that handles everything!**

---

## Quick Start

```bash
./scripts/release.sh 0.18.0
```

The script handles:
- Pre-flight checks (clean repo, on master, etc.)
- Version bump in `pyproject.toml`
- CHANGELOG validation
- Git commit and tag
- Push to GitHub
- Create GitHub release
- Auto-publish to PyPI (via GitHub Actions + Trusted Publishing)

---

## Prerequisites

### One-Time Setup

1. **GitHub CLI:**
   ```bash
   # macOS
   brew install gh

   # Linux: https://github.com/cli/cli/blob/trunk/docs/install_linux.md

   # Authenticate
   gh auth login
   ```

2. **PyPI Trusted Publishing (Already Configured):**

   Reveal uses PyPI Trusted Publishing - more secure than API tokens!

   - Configured at: https://pypi.org/manage/project/reveal-cli/settings/publishing/
   - Publisher: `scottsen/reveal` with workflow `publish-to-pypi.yml`
   - No tokens to manage or rotate

3. **Python Build Tools:**
   ```bash
   pip install --upgrade build twine
   ```

---

## Release Workflow

### Step 1: Prepare CHANGELOG

Update `CHANGELOG.md` before running the release script:

```markdown
## [0.18.0] - 2025-12-09

### Added
- `--copy` flag to copy output to clipboard
- `help://tricks` documentation topic

### Changed
- Improved help system discoverability
```

### Step 2: Run Release Script

```bash
./scripts/release.sh 0.18.0
```

The script will:
1. Verify you're on `master` branch
2. Check for uncommitted changes
3. Verify version doesn't already exist
4. Pull latest from origin
5. Check CHANGELOG has entry for new version
6. Update version in `pyproject.toml`
7. Build and verify package
8. Create git commit and tag
9. Push to GitHub
10. Create GitHub release
11. GitHub Actions publishes to PyPI automatically

### Step 3: Verify

```bash
# Watch GitHub Actions
gh run list --limit 5

# Check PyPI (after ~1-2 minutes)
pip index versions reveal-cli

# Test installation
pip install --upgrade reveal-cli
reveal --version
```

---

## Troubleshooting

### Script Fails Before Push

**Solution:** Fix the issue, run the script again. Nothing was pushed yet.

### GitHub Release Failed After Push

```bash
# Create release manually
gh release create v0.18.0 --title "v0.18.0" --notes "See CHANGELOG.md"
```

### GitHub Actions Workflow Failed

```bash
# View logs
gh run list --limit 5
gh run view <run-id> --log-failed
```

**Common issues:**
- Trusted publishing not configured
- Workflow permission issues (`id-token: write`)
- Network issues (re-run via GitHub UI)

### Workflow File Issues (Tag Points to Wrong Commit)

GitHub Actions runs from the **TAGGED commit**, not from HEAD!

```bash
# Diagnose
git show v0.18.0:.github/workflows/publish-to-pypi.yml | head -20

# Fix: Delete and recreate tag at correct commit
gh release delete v0.18.0 --yes
git tag -d v0.18.0
git push --delete origin v0.18.0
git tag v0.18.0
git push origin v0.18.0
gh release create v0.18.0 --title "v0.18.0" --notes "See CHANGELOG.md"
```

### "File Already Exists" Error

Version already on PyPI. Bump version and release again:
```bash
./scripts/release.sh 0.18.1
```

### Need to Undo a Release

```bash
# Delete GitHub release
gh release delete v0.18.0

# Delete tag
git tag -d v0.18.0
git push origin :refs/tags/v0.18.0

# Revert commit
git revert HEAD
git push origin master
```

**Note:** PyPI releases can't be deleted, only "yanked" (hidden from pip install).

---

## Manual Release

If you prefer manual control:

```bash
# 1. Update version
vim pyproject.toml CHANGELOG.md

# 2. Commit
git add pyproject.toml CHANGELOG.md
git commit -m "chore: Bump version to 0.18.0"

# 3. Tag and push
git tag v0.18.0
git push origin master
git push origin v0.18.0

# 4. Create release (triggers PyPI publish)
gh release create v0.18.0 --title "v0.18.0" --notes "See CHANGELOG.md"
```

---

## Testing on TestPyPI

Before releasing to production:

```bash
# Build
python -m build

# Upload to TestPyPI (need token from https://test.pypi.org/manage/account/token/)
twine upload --repository testpypi dist/*

# Test installation
pip install --index-url https://test.pypi.org/simple/ reveal-cli
reveal --version
```

---

## Version Numbering

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR.MINOR.PATCH** (e.g., `0.18.0`)
- **MAJOR** - Breaking changes
- **MINOR** - New features
- **PATCH** - Bug fixes

**Current status:** Pre-1.0 (breaking changes allowed in minor versions)

---

## Release Checklist

**Before release:**
- [ ] **Version check**: `git tag | grep vX.Y.Z` returns nothing (version doesn't exist)
- [ ] All features merged to master
- [ ] Tests passing
- [ ] CHANGELOG.md updated with correct NEW version
- [ ] `pyproject.toml` version matches CHANGELOG
- [ ] Clean git status
- [ ] On master branch, pulled latest

**After creating tag (before release):**
- [ ] Verify tag points to correct commit: `git show vX.Y.Z:.github/workflows/publish-to-pypi.yml | head -20`

**After release:**
- [ ] GitHub Actions completed
- [ ] PyPI shows new version
- [ ] `pip install --upgrade reveal-cli` works
- [ ] `reveal --version` shows correct version

---

## Quick Reference

```bash
# Automated release
./scripts/release.sh X.Y.Z

# Check versions
pip index versions reveal-cli

# View releases
gh release list

# Monitor Actions
gh run list --limit 5

# Manual PyPI upload
python -m build && twine upload dist/*
```

---

## Resources

- **PyPI:** https://pypi.org/project/reveal-cli/
- **GitHub Actions:** https://github.com/Semantic-Infrastructure-Lab/reveal/actions
- **Script:** `scripts/release.sh`

---

**Last updated:** 2025-12-09
