---
title: Reveal Release Process
type: documentation
category: maintainer
date: 2026-03-28
---

# Reveal Release Process

**Automated release script that handles everything!**

---

## Quick Start

```bash
./scripts/release.sh X.Y.Z
```

The script handles:
- Pre-flight checks (clean repo, on master, etc.)
- Version bump in `pyproject.toml`
- CHANGELOG validation
- Reveal self-check (V007/V011/V012/V013)
- Test suite
- Git commit and tag
- Push to GitHub
- Create GitHub release
- Auto-publish to PyPI (via GitHub Actions + Trusted Publishing)
- Poll PyPI to confirm publish landed

**Flags:**
- `--resume` — tag exists but no GitHub release (interrupted release); moves tag to HEAD and creates the release
- `--dry-run` — validate everything (pre-flight, changelog, self-check, tests) without any git/push/release ops

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

### Step 0: Pre-release Validation

Run reveal's self-check to catch documentation drift:

```bash
reveal reveal:// --check
```

This validates:
- **V007**: `AGENT_HELP.md` version matches `pyproject.toml`
- **V011**: `ROADMAP.md` mentions current version in "What We've Shipped"
- **V012**: Language count claims match registered analyzers
- **V013**: Adapter count claims match registered adapters

Fix any errors before proceeding.

### Step 1: Update All 4 Required Files

Before running the release script, **4 files must be updated** — CI checks validate all of them and will fail if any are missed:

| File | What to update |
|------|---------------|
| `CHANGELOG.md` | Add `[X.Y.Z] - YYYY-MM-DD` section with session list |
| `reveal/docs/AGENT_HELP.md` | Version line near the top → new version |
| `ROADMAP.md` | Add entry to "What We've Shipped" |
| `pyproject.toml` | **Pre-bump to new version** (same as AGENT_HELP) |

> **Why pre-bump `pyproject.toml`?** The release script runs `test_agent_help_is_current_version`
> which checks that `AGENT_HELP.md` matches `pyproject.toml`. The script bumps `pyproject.toml`
> *before* tests now (so both files agree), but pre-bumping is still the cleanest approach for
> a single prep commit. Commit all 4 files together:
> ```bash
> git add CHANGELOG.md reveal/docs/AGENT_HELP.md ROADMAP.md pyproject.toml
> git commit -m "chore: prep vX.Y.Z — CHANGELOG, version strings, ROADMAP shipped"
> ```
> Then run `./scripts/release.sh X.Y.Z` — it detects the pre-bump and skips the version commit.

#### Update CHANGELOG.md

Add a new version section:

```markdown
## [X.Y.Z] - YYYY-MM-DD (sessions session-name-MMDD, ...)

### Added
- New feature description

### Fixed
- Bug fix description
```

### Step 2: Run Release Script

```bash
./scripts/release.sh X.Y.Z
```

The script will:
1. Verify you're on `master` branch
2. Check for uncommitted changes
3. Verify version tag doesn't already exist
4. Pull latest from origin
5. Check CHANGELOG has entry for new version
6. Update version in `pyproject.toml` (or skip if pre-bumped)
7. Run reveal self-check
8. Run full test suite
9. Build and verify package
10. Create git commit and tag
11. Push to GitHub
12. Create GitHub release (triggers PyPI Actions workflow)
13. Poll PyPI until publish confirmed (~1-2 min)

### Step 3: Verify

The script polls PyPI automatically. If it times out, check manually:

```bash
# Watch GitHub Actions
gh run list --limit 5

# Check PyPI
pip index versions reveal-cli

# Test installation
pip install --upgrade reveal-cli
reveal --version
```

---

## Troubleshooting

### Script Fails Before Push

**Solution:** Fix the issue, run the script again. Nothing was pushed yet.

### Tag pushed, no GitHub release, new commits since

The most common interrupted-release scenario: the release script tagged and pushed, but
`gh release create` failed (or the script was killed). You then continued working and
added more commits.

**Use `--resume`:**
```bash
./scripts/release.sh X.Y.Z --resume
```

`--resume` will:
1. Detect the existing tag and missing GitHub release
2. Run the full test suite (covers the new commits)
3. Delete the old tag (local + remote) and retag at HEAD
4. Create the GitHub release → triggers PyPI publish

### GitHub Release Failed After Push (no new commits)

If no new commits landed since the tag, just create the release manually:
```bash
gh release create vX.Y.Z --title "vX.Y.Z" --notes "See CHANGELOG.md"
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

GitHub Actions runs from the **TAGGED commit**, not from HEAD! If the tag points to a
commit before the workflow file was fixed, the old broken workflow runs.

```bash
# Diagnose: check which workflow file the tag sees
git show vX.Y.Z:.github/workflows/publish-to-pypi.yml | head -20

# Fix: use --resume to move the tag to HEAD
./scripts/release.sh X.Y.Z --resume
```

### "File Already Exists" Error

Version already on PyPI. Bump version and release again:
```bash
./scripts/release.sh X.Y.(Z+1)
```

### Need to Undo a Release

```bash
# Delete GitHub release
gh release delete vX.Y.Z

# Delete tag (local + remote)
git tag -d vX.Y.Z
git push origin :refs/tags/vX.Y.Z

# Revert commit
git revert HEAD
git push origin master
```

**Note:** PyPI releases can't be deleted, only "yanked" (hidden from pip install):
```bash
# Yank from PyPI (marks as broken, pip won't install unless pinned)
# Do this via https://pypi.org/manage/project/reveal-cli/releases/
```

---

## Manual Release

If you prefer manual control:

```bash
# 1. Update version
vim pyproject.toml CHANGELOG.md

# 2. Commit
git add pyproject.toml CHANGELOG.md
git commit -m "chore: Bump version to X.Y.Z"

# 3. Tag and push
git tag vX.Y.Z
git push origin master
git push origin vX.Y.Z

# 4. Create release (triggers PyPI publish)
gh release create vX.Y.Z --title "vX.Y.Z" --notes "See CHANGELOG.md"
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

**Before release — 4-file prep commit:**
- [ ] `CHANGELOG.md` — `[X.Y.Z] - YYYY-MM-DD` section with session list
- [ ] `reveal/docs/AGENT_HELP.md` — version line bumped to new version
- [ ] `ROADMAP.md` — new version added to "What We've Shipped" section
- [ ] `pyproject.toml` — **pre-bumped to new version** (all 4 committed together)

**Pre-flight:**
- [ ] **Self-check passes**: `reveal reveal:// --check` (no errors)
- [ ] **Version check**: `git tag | grep vX.Y.Z` returns nothing (or use `--resume` if it exists)
- [ ] All features merged to master
- [ ] Tests passing: `pytest`
- [ ] Clean git status
- [ ] On master branch, pulled latest

**After creating tag (before release):**
- [ ] Verify tag points to correct commit: `git show vX.Y.Z:.github/workflows/publish-to-pypi.yml | head -5`

**After release:**
- [ ] Script confirms PyPI publish (or check manually with `pip index versions reveal-cli`)
- [ ] `pip install --upgrade reveal-cli` works
- [ ] `reveal --version` shows correct version

---

## Quick Reference

```bash
# Standard release
./scripts/release.sh X.Y.Z

# Resume interrupted release (tag exists, no GitHub release)
./scripts/release.sh X.Y.Z --resume

# Validate without releasing
./scripts/release.sh X.Y.Z --dry-run

# Check versions on PyPI
pip index versions reveal-cli

# View releases
gh release list

# Monitor Actions
gh run list --limit 5
```

---

## Resources

- **PyPI:** https://pypi.org/project/reveal-cli/
- **GitHub Actions:** https://github.com/Semantic-Infrastructure-Lab/reveal/actions
- **Script:** `scripts/release.sh`

---

**Last updated:** 2026-03-28
