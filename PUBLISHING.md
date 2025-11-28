# Publishing to PyPI

> **📖 For the complete release process, see [RELEASING.md](RELEASING.md)**
>
> This document covers PyPI-specific publishing details.

## TL;DR - Quick Release

**Automated (Recommended):**
```bash
./scripts/release.sh 0.11.1
```

See [RELEASING.md](RELEASING.md) for complete workflow.

---

## How Publishing Works

Publishing to PyPI is **fully automated** via GitHub Actions:

```
Create GitHub Release → GitHub Actions → PyPI Published
   (manual/script)        (automatic)      (automatic)
```

**Workflow:** `.github/workflows/publish-to-pypi.yml`

**Triggers on:**
- ✅ GitHub Release published
- ✅ Manual workflow dispatch

**What it does:**
1. Builds package (`python -m build`)
2. Validates (`twine check dist/*`)
3. Publishes to PyPI using `PYPI_API_TOKEN` secret

**Result:** Package live on PyPI in ~1-2 minutes

---

## Prerequisites (One-Time Setup)

### 1. PyPI API Token

**Get token:**
- Go to: https://pypi.org/manage/account/token/
- Scope: "Entire account" or project `reveal-cli`
- Copy the token (starts with `pypi-`)

**Add to GitHub:**
1. Go to: https://github.com/scottsen/reveal/settings/secrets/actions
2. Click "New repository secret"
3. Name: `PYPI_API_TOKEN`
4. Value: Your token
5. Save

### 2. GitHub CLI

```bash
# macOS
brew install gh

# Linux
# See: https://github.com/cli/cli/blob/trunk/docs/install_linux.md

# Authenticate
gh auth login
```

### 3. Python Build Tools

```bash
pip install --upgrade build twine
```

---

## Publishing Methods

### Method 1: Automated Script (Recommended)

**See [RELEASING.md](RELEASING.md) for full details.**

```bash
./scripts/release.sh 0.11.1
```

Handles version bump, changelog, git tags, GitHub release, and triggers PyPI publish.

### Method 2: Manual GitHub Release

If you've already committed version changes:

```bash
# Push commits
git push origin master

# Create and push tag
git tag v0.11.1
git push origin v0.11.1

# Create GitHub release (triggers PyPI publish)
gh release create v0.11.1 \
  --title "v0.11.1" \
  --notes "See CHANGELOG.md"
```

### Method 3: Manual PyPI Upload (Emergency Only)

If GitHub Actions fails:

```bash
# Build
rm -rf dist/
python -m build

# Validate
twine check dist/*

# Upload
twine upload dist/*
# Username: __token__
# Password: <your PyPI token>
```

---

## Testing on TestPyPI (Optional)

Before releasing to production, test on TestPyPI:

### 1. Get TestPyPI Token
- https://test.pypi.org/manage/account/token/

### 2. Build and Upload
```bash
# Build
python -m build

# Upload to TestPyPI
twine upload --repository testpypi dist/*
# Username: __token__
# Password: <your TestPyPI token>
```

### 3. Test Installation
```bash
pip install --index-url https://test.pypi.org/simple/ reveal-cli
reveal --version
```

---

## Troubleshooting

### GitHub Actions Fails to Publish

**Check workflow logs:**
```bash
gh run list --limit 5
gh run view <run-id> --log-failed
```

**Common issues:**
- Missing `PYPI_API_TOKEN` secret → Add in GitHub settings
- Token expired → Generate new token
- Network issues → Re-run workflow manually

**Manual fallback:**
```bash
python -m build
twine upload dist/*
```

### "File already exists" Error

**Cause:** Version already published to PyPI

**Solution:** Bump version number:
```bash
# Edit pyproject.toml
version = "0.11.2"  # Increment

# Release new version
./scripts/release.sh 0.11.2
```

**Note:** You cannot replace PyPI versions. Can only "yank" (hide from pip):
- Go to https://pypi.org/project/reveal-cli/
- Manage → Yank release

### Verify Package Contents

```bash
# Build locally
python -m build

# Check wheel contents
python -m zipfile -l dist/reveal_cli-*.whl

# Should see:
# - reveal/ (main package)
# - reveal/analyzers/
# - reveal/adapters/
# - All .py files
```

---

## Version Numbering

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR.MINOR.PATCH** (e.g., `1.2.3`)
- **MAJOR** - Breaking changes
- **MINOR** - New features (backward compatible)
- **PATCH** - Bug fixes

**Examples:**
- `0.11.0` → `0.11.1` - Bug fixes (this release)
- `0.11.1` → `0.12.0` - PostgreSQL adapter (new feature)
- `0.12.0` → `1.0.0` - Stable API freeze

---

## Quick Reference

```bash
# Automated release
./scripts/release.sh X.Y.Z

# Manual release
git push origin master
git tag vX.Y.Z
git push origin vX.Y.Z
gh release create vX.Y.Z --title "vX.Y.Z" --notes "..."

# Check PyPI
pip index versions reveal-cli

# View releases
gh release list

# Monitor GitHub Actions
gh run list --limit 5
```

---

## Resources

- **Main Release Guide:** [RELEASING.md](RELEASING.md)
- **PyPI Project:** https://pypi.org/project/reveal-cli/
- **TestPyPI:** https://test.pypi.org/
- **GitHub Actions:** https://github.com/scottsen/reveal/actions
- **Python Packaging:** https://packaging.python.org/
- **Twine Docs:** https://twine.readthedocs.io/

---

**Last Updated:** 2025-11-27
