# Reveal Release Process - Internal Notes

**Last Updated:** 2025-11-27
**Current Version:** 0.11.1

---

## 📋 Quick Checklist

**Before Release:**
```bash
# 1. Verify tests pass
pytest -v

# 2. Verify version bumped
grep "^version" pyproject.toml

# 3. Verify CHANGELOG updated
grep "## \[X.Y.Z\]" CHANGELOG.md

# 4. Clean git status
git status

# 5. On master branch
git branch --show-current
```

**Release:**
```bash
# Option A: Automated (recommended)
./scripts/release.sh X.Y.Z

# Option B: Manual (if version already bumped)
git push origin master
git tag vX.Y.Z && git push origin vX.Y.Z
gh release create vX.Y.Z --title "vX.Y.Z" --notes "See CHANGELOG"
```

---

## 🚨 Common Gotchas

### 1. Version Already Bumped
**Symptom:** Already committed version bump
**Solution:** Use manual process (Option B above)
**Prevention:** Use release script BEFORE manual version bump

### 2. CHANGELOG Missing Entry
**Symptom:** Script fails validation
**Solution:** Add `## [X.Y.Z] - YYYY-MM-DD` entry
**Prevention:** Update CHANGELOG in `[Unreleased]` section as you develop

### 3. GitHub Actions Fails
**Symptom:** Release created but PyPI fails
**Solution:** Manual publish: `python -m build && twine upload dist/*`
**Check:** Verify `PYPI_API_TOKEN` secret exists and is current

### 4. Test Failures
**Symptom:** pytest has failures
**Solution:** Fix tests BEFORE release (100% pass rate required)

### 5. Dirty Git Working Directory
**Symptom:** "uncommitted changes" error
**Solution:** Commit or stash changes first

---

## 📝 Release History Learnings

### v0.11.1 (2025-11-27) - Test Suite Fixes
- ✅ Comprehensive test cleanup (6 obsolete files removed)
- ✅ Fixed nginx analyzer tests (temp file API)
- ⚠️ **Learning:** Release script expects to bump version itself
- **Takeaway:** If version already bumped, use manual process

### v0.11.0 (2025-11-26) - URI Adapters
- ✅ Smooth automated release
- ✅ GitHub Actions published automatically
- **Takeaway:** Automated script works great when followed exactly

---

## 🔧 Emergency Rollback

```bash
# 1. Delete GitHub release
gh release delete vX.Y.Z

# 2. Delete git tag
git tag -d vX.Y.Z
git push origin :refs/tags/vX.Y.Z

# 3. Revert version commit
git revert HEAD && git push

# 4. Yank from PyPI (can't delete, only hide)
# https://pypi.org/project/reveal-cli/ → Settings → Yank
```

**Note:** PyPI releases cannot be deleted, only yanked

---

## 💡 Best Practices

1. **Always run tests first** - `pytest -v` must be 100%
2. **Update CHANGELOG as you develop** - Use `[Unreleased]` section
3. **Semantic versioning:**
   - Patch (X.Y.Z+1): Bug fixes
   - Minor (X.Y+1.0): New features
   - Major (X+1.0.0): Breaking changes
4. **Test on TestPyPI for major changes**
5. **Keep release notes user-focused**

---

## 🔗 Related Docs

- [RELEASING.md](../../RELEASING.md) - Complete release guide
- [PUBLISHING.md](../../PUBLISHING.md) - PyPI details
- [.github/workflows/publish-to-pypi.yml](../../.github/workflows/publish-to-pypi.yml) - Automation

---

**Maintained by:** Scott Senkeresty
