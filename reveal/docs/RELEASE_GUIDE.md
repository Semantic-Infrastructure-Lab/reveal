# Reveal Release Guide
**Audience:** Maintainers
**Token cost:** ~800 tokens

---

## 🎯 Recommended: Use the Automated Script

```bash
./scripts/release.sh 0.24.1
```

The script handles everything correctly:
- ✅ Pre-flight checks (clean repo, on master, tests pass)
- ✅ Version bump in `pyproject.toml`
- ✅ CHANGELOG validation
- ✅ Package build and verification
- ✅ Git commit and tag
- ✅ Push to GitHub
- ✅ **Create GitHub Release** (triggers PyPI auto-publish)

**Why the script?** It never forgets the critical step: creating the GitHub Release.

---

## 📋 Manual Release Steps

**Only if the script fails or you need manual control:**

### Prerequisites
```bash
# Ensure gh CLI is installed and authenticated
gh auth status

# Ensure on master with clean working directory
git checkout master
git pull origin master
git status  # Should be clean
```

### Step 1: Update Version and CHANGELOG

Edit `pyproject.toml`:
```toml
version = "0.24.1"  # Update this
```

Edit `CHANGELOG.md`:
```markdown
## [0.24.1] - 2025-12-17

### Fixed
- Description of what was fixed

### Added
- Description of what was added
```

### Step 2: Build and Verify

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build package
python -m build

# Verify package
twine check dist/*
```

### Step 3: Commit and Tag

```bash
# Stage changes
git add pyproject.toml CHANGELOG.md

# Commit (include other changed files if needed)
git commit -m "Release v0.24.1: Description

Detailed explanation of changes...
"

# Create annotated tag
git tag -a v0.24.1 -m "v0.24.1 - Brief description"
```

### Step 4: Push to GitHub

```bash
# Push commit
git push origin master

# Push tag
git push origin v0.24.1
```

### Step 5: Create GitHub Release ⚠️ CRITICAL

**This is the step that triggers PyPI auto-publish!**

```bash
# Create GitHub Release
gh release create v0.24.1 \
  --title "v0.24.1 - Brief Title" \
  --notes "## What's Changed

- Feature or fix description
- Another change

**Install/Upgrade:**
\`\`\`bash
pip install --upgrade reveal-cli
\`\`\`

Full changelog: [CHANGELOG.md](https://github.com/Semantic-Infrastructure-Lab/reveal/blob/master/CHANGELOG.md)"
```

**Or use the GitHub web UI:**
1. Go to: https://github.com/Semantic-Infrastructure-Lab/reveal/releases/new
2. Choose tag: `v0.24.1`
3. Fill in title and description
4. Click "Publish release"

### Step 6: Monitor and Verify

```bash
# Watch GitHub Actions workflow
gh run list --limit 1

# Wait ~1-2 minutes, then check PyPI
pip index versions reveal-cli

# Should show:
# reveal-cli (0.24.1)
#   LATEST: 0.24.1
```

---

## 🚨 Common Mistakes

### ❌ Only Pushing the Tag
```bash
git push origin v0.24.1  # This alone won't work!
```
**Problem:** No GitHub Release = No PyPI publish
**Fix:** Must create GitHub Release (Step 5)

### ❌ Manual twine upload
```bash
twine upload dist/*  # Don't do this!
```
**Problem:** Defeats the Trusted Publishing setup
**Fix:** Let GitHub Actions handle PyPI (triggered by Release creation)

### ❌ Forgetting CHANGELOG
**Problem:** Users don't know what changed
**Fix:** Always update CHANGELOG.md before release

---

## 🔍 Troubleshooting

### GitHub Actions Failed
```bash
# View workflow logs
gh run view --log-failed

# Common fix: Re-run the workflow
gh run rerun <run-id>
```

### Wrong Version Pushed
```bash
# Delete GitHub release
gh release delete v0.24.1 --yes

# Delete tag locally and remotely
git tag -d v0.24.1
git push origin :refs/tags/v0.24.1

# Fix version and try again
```

### "File Already Exists" on PyPI
**Problem:** Version already published (PyPI versions are immutable)
**Fix:** Bump to next patch version (e.g., 0.24.2) and release again

---

## 📚 Resources

- **Full documentation:** `RELEASING.md` in repo root
- **Release script:** `scripts/release.sh`
- **PyPI project:** https://pypi.org/project/reveal-cli/
- **GitHub Actions:** https://github.com/Semantic-Infrastructure-Lab/reveal/actions
- **Workflow file:** `.github/workflows/publish-to-pypi.yml`

---

## 🎓 How It Works

1. **GitHub Release Creation** → Triggers workflow (`.github/workflows/publish-to-pypi.yml`)
2. **Workflow builds package** → Using `python -m build`
3. **Workflow publishes to PyPI** → Using Trusted Publishing (no tokens!)
4. **Users get update** → Via `pip install --upgrade reveal-cli`

**Key insight:** The GitHub Release is not just documentation—it's the trigger for the entire publish pipeline.
