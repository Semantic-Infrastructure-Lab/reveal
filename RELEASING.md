# Reveal Release Process

**Automated release script that handles everything!**

## Quick Start

```bash
# Release a new version (e.g., 0.10.0)
./scripts/release.sh 0.10.0
```

That's it! The script handles:
- ✅ Pre-flight checks (clean repo, on master, etc.)
- ✅ Version bump in `pyproject.toml`
- ✅ CHANGELOG validation
- ✅ Git commit and tag
- ✅ Push to GitHub
- ✅ Create GitHub release
- ✅ Auto-publish to PyPI (via GitHub Actions)

---

## Prerequisites

### One-Time Setup

1. **GitHub CLI installed and authenticated:**
   ```bash
   # Install GitHub CLI
   # macOS:
   brew install gh

   # Linux:
   # See: https://github.com/cli/cli/blob/trunk/docs/install_linux.md

   # Authenticate
   gh auth login
   ```

2. **PyPI API Token configured as GitHub Secret:**
   - Generate token at: https://pypi.org/manage/account/token/
   - Scope: "Entire account" or project-specific
   - Add to GitHub: Settings → Secrets → Actions → `PYPI_API_TOKEN`

3. **Python build tools installed:**
   ```bash
   pip install --upgrade build twine
   ```

---

## Release Workflow

### Step 1: Prepare CHANGELOG

Before running the release script, update `CHANGELOG.md`:

```markdown
## [0.10.0] - 2025-11-27

### Added
- New feature X that does Y
- Support for Z file type

### Changed
- Improved performance of ABC
- Updated documentation for clarity

### Fixed
- Bug where DEF didn't work correctly
```

**Format:** Follow [Keep a Changelog](https://keepachangelog.com/) conventions.

### Step 2: Run Release Script

```bash
./scripts/release.sh 0.10.0
```

The script will:
1. ✅ Verify you're on `master` branch
2. ✅ Check for uncommitted changes
3. ✅ Verify version doesn't already exist
4. ✅ Pull latest from origin
5. ✅ Check CHANGELOG has entry for new version
6. ✅ Update version in `pyproject.toml`
7. ✅ Build and verify package
8. ✅ Create git commit: `chore: Bump version to X.Y.Z`
9. ✅ Create git tag: `vX.Y.Z`
10. ✅ Push commit and tag to GitHub
11. ✅ Create GitHub release with CHANGELOG notes
12. 🤖 GitHub Actions automatically publishes to PyPI

### Step 3: Monitor & Verify

1. **Watch GitHub Actions:**
   https://github.com/scottsen/reveal/actions

   The "Publish to PyPI" workflow should complete in ~1-2 minutes.

2. **Verify PyPI:**
   ```bash
   # Check if version is live
   pip index versions reveal-cli

   # Test installation
   pip install --upgrade reveal-cli
   reveal --version
   ```

3. **Verify GitHub Release:**
   https://github.com/scottsen/reveal/releases

---

## What If Something Goes Wrong?

### Scenario 1: Script Fails Before Push

**Situation:** Script failed during pre-flight checks or build.

**Solution:**
- Fix the issue (e.g., commit changes, fix tests)
- Run the script again

**Safe:** Nothing was pushed to GitHub yet.

### Scenario 2: Push Succeeded, GitHub Release Failed

**Situation:** Commit and tag were pushed, but GitHub release creation failed.

**Solution:**
```bash
# Create the release manually
gh release create v0.10.0 \
  --title "v0.10.0" \
  --notes "See CHANGELOG.md for details"
```

This will trigger the PyPI publish workflow.

### Scenario 3: GitHub Actions Workflow Failed

**Situation:** Release created, but PyPI publish failed.

**Check the logs:**
```bash
# View recent workflow runs
gh run list --limit 5

# View specific run logs
gh run view <run-id> --log-failed
```

**Common issues:**
- Missing `PYPI_API_TOKEN` secret
- Token expired or invalid
- Network issues (temporary, retry via GitHub UI)

**Manual publish (if needed):**
```bash
# Build locally
python3 -m build

# Upload to PyPI
twine upload dist/reveal_cli-0.10.0*
```

### Scenario 4: Need to Undo a Release

**If release was pushed but you need to undo:**

```bash
# Delete GitHub release
gh release delete v0.10.0

# Delete git tag locally and remotely
git tag -d v0.10.0
git push origin :refs/tags/v0.10.0

# Revert version bump commit
git revert HEAD
git push origin master
```

**Note:** You **cannot** delete PyPI releases, but you can "yank" them:
```bash
# Yank from PyPI (hides from pip install but doesn't delete)
twine upload --skip-existing dist/*  # If needed
# Then on PyPI web UI: Settings → "Yank this release"
```

---

## Manual Release (Without Script)

If you prefer manual control:

```bash
# 1. Update CHANGELOG.md
vim CHANGELOG.md

# 2. Update version in pyproject.toml
vim pyproject.toml

# 3. Commit changes
git add pyproject.toml CHANGELOG.md
git commit -m "chore: Bump version to 0.10.0"

# 4. Create tag
git tag -a v0.10.0 -m "Release v0.10.0"

# 5. Push
git push origin master
git push origin v0.10.0

# 6. Create GitHub release
gh release create v0.10.0 \
  --title "v0.10.0" \
  --notes "$(sed -n '/## \[0.10.0\]/,/## \[/p' CHANGELOG.md | sed '$d')"

# 7. GitHub Actions will auto-publish to PyPI
```

---

## GitHub Actions Workflow

The automated publish workflow (`.github/workflows/publish-to-pypi.yml`) triggers when:
- ✅ A GitHub release is **published** (not just created as draft)
- ✅ Manual trigger via GitHub Actions UI

**What it does:**
1. Checks out code
2. Sets up Python 3.11
3. Installs build dependencies
4. Builds distribution (`python -m build`)
5. Validates distribution (`twine check`)
6. Publishes to PyPI using `PYPI_API_TOKEN` secret

**Logs:** https://github.com/scottsen/reveal/actions

---

## Version Numbering

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.0.0): Breaking API changes
- **MINOR** (0.10.0): New features, backward compatible
- **PATCH** (0.9.1): Bug fixes, backward compatible

**Current status:** Pre-1.0 (0.x.x)
- Breaking changes allowed in minor versions
- Once stable: Release 1.0.0

---

## Release Checklist

Before running `./scripts/release.sh X.Y.Z`:

- [ ] All features/fixes merged to master
- [ ] Tests passing locally
- [ ] CHANGELOG.md updated with version entry
- [ ] Documentation updated (if needed)
- [ ] README.md reflects new features (if added)
- [ ] Clean git status (`git status` shows nothing)
- [ ] On master branch
- [ ] Pulled latest from origin

After release:
- [ ] GitHub Actions completed successfully
- [ ] PyPI shows new version
- [ ] `pip install --upgrade reveal-cli` works
- [ ] `reveal --version` shows correct version
- [ ] GitHub release notes look good

---

## Tips & Best Practices

### 1. **Test in Development Install First**

Before releasing:
```bash
# Install in editable mode
pip install -e .

# Test the changes
reveal --version
reveal --help
# ... test your new features
```

### 2. **Use Pre-Releases for Testing**

For major changes, consider a pre-release:
```bash
./scripts/release.sh 0.10.0-rc1  # Release candidate
./scripts/release.sh 0.10.0-beta.1  # Beta
```

Then final release:
```bash
./scripts/release.sh 0.10.0  # Final
```

### 3. **Keep CHANGELOG Current**

Update CHANGELOG.md as you develop, not just before release:
```bash
# Add to "Unreleased" section as you work
## [Unreleased]

### Added
- New feature X
```

Then before release, change `[Unreleased]` to `[0.10.0] - 2025-11-27`.

### 4. **Review the Diff Before Release**

```bash
# See what changed since last release
git log v0.9.0..HEAD --oneline

# See file changes
git diff v0.9.0..HEAD --stat
```

---

## Quick Reference

```bash
# Release new version
./scripts/release.sh 0.10.0

# Check PyPI versions
pip index versions reveal-cli

# View recent releases
gh release list

# View GitHub Actions status
gh run list --limit 5

# Manual PyPI upload (if needed)
python3 -m build && twine upload dist/*

# Delete a release (emergency only)
gh release delete v0.10.0
git push origin :refs/tags/v0.10.0
```

---

## Questions?

- **Issues:** https://github.com/scottsen/reveal/issues
- **Discussions:** https://github.com/scottsen/reveal/discussions
- **Workflow logs:** https://github.com/scottsen/reveal/actions

---

**Last updated:** 2025-11-26
**Script location:** `scripts/release.sh`
