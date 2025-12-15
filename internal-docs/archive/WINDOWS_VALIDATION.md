# Windows Validation Checklist

Before releasing a new version to PyPI, use this checklist to ensure Windows compatibility.

## ✅ Pre-Release Validation

### 1. **Run Tests Locally**
```bash
# Run full test suite (should pass on your development machine)
pytest tests/ -v

# Run Windows-specific tests
pytest tests/test_windows_compat.py -v
```
**Expected:** All 85+ tests pass

---

### 2. **Push to GitHub (Triggers CI)**
```bash
git push origin master
```

**Then watch CI results:**
- Go to: https://github.com/Semantic-Infrastructure-Lab/reveal/actions
- Wait for "Tests" workflow to complete (~3-5 minutes)
- **Must see:** ✅ Green checkmarks for all platforms

**What CI tests:**
- Windows (windows-latest) + Python 3.8, 3.12
- Linux (ubuntu-latest) + Python 3.8, 3.12
- macOS (macos-latest) + Python 3.8, 3.12

---

### 3. **Manual Windows Smoke Test (Optional)**

If you have access to a Windows machine or VM:

```powershell
# Install from local build
pip install -e .

# Test cache directory location
python -c "import os; from pathlib import Path; print(Path(os.getenv('LOCALAPPDATA')) / 'reveal')"

# Test CLI
reveal --version
reveal --list-supported

# Test environment adapter
reveal env://USERNAME
reveal env://USERPROFILE
```

**Expected:**
- Cache dir: `C:\Users\YourName\AppData\Local\reveal`
- USERNAME/USERPROFILE show up as "System" category

---

### 4. **Create Release (After CI Passes)**

```bash
# Bump version in pyproject.toml first!
# Example: 0.13.2 → 0.13.3

# Commit version bump
git add pyproject.toml
git commit -m "chore: bump version to 0.13.3"
git push

# Create GitHub release (triggers PyPI publish)
gh release create v0.13.3 \
  --title "v0.13.3 - Windows Compatibility" \
  --notes "
## Windows Compatibility Improvements

- ✅ Cache directory now uses Windows-native paths (\`%LOCALAPPDATA%\\reveal\`)
- ✅ Environment variables properly categorized (USERPROFILE, USERNAME, etc.)
- ✅ Cross-platform testing in CI (Windows/Linux/macOS)
- ✅ PyPI metadata declares Windows support

## What's Changed
- Cache directory uses platform-appropriate locations
- Added 16 Windows environment variables to SYSTEM_VARS
- Added comprehensive Windows compatibility tests
- Updated PyPI classifiers for explicit OS support

See full changelog: https://github.com/Semantic-Infrastructure-Lab/reveal/compare/v0.13.2...v0.13.3
"
```

---

### 5. **Post-Release Verification**

```bash
# Wait 2-3 minutes for PyPI to process

# Install from PyPI in clean environment
pip install --upgrade reveal-cli

# Verify version
reveal --version  # Should show new version

# Check PyPI page
open https://pypi.org/project/reveal-cli/
# Should show: "Operating System :: Microsoft :: Windows" badge
```

---

## 🚨 What to Do If Tests Fail

### CI Fails on Windows

**Symptoms:** Red X on Windows job in GitHub Actions

**Steps:**
1. Click the failed job to see error details
2. Identify which test failed
3. Fix the code or test
4. Push again (CI re-runs automatically)

**Common issues:**
- Path separator issues (use `pathlib.Path` everywhere)
- Missing environment variables (provide fallbacks)
- Platform-specific APIs (wrap in `sys.platform` checks)

---

### Cannot Publish to PyPI

**Symptoms:** `publish-to-pypi.yml` workflow never runs or fails

**Possible causes:**
1. Tests failed (check CI status)
2. Release wasn't published properly (check releases page)
3. PyPI trusted publishing not configured

**Solution:**
- Ensure all CI checks pass before creating release
- Verify `needs: test` in publish-to-pypi.yml
- Check PyPI publishing settings: https://pypi.org/manage/account/publishing/

---

## 📊 Metrics to Monitor

After release, monitor for Windows-specific issues:

### PyPI Download Stats
```bash
# Check downloads by platform (after ~1 week)
# Look for Windows vs Linux/macOS ratio
```

### GitHub Issues
- Watch for issues tagged "Windows" or "platform-specific"
- Response time < 48 hours for Windows bugs

### CI Success Rate
- Track Windows CI pass rate
- Aim for 100% (same as Linux)

---

## 🔄 Continuous Validation

**Every commit:**
- CI runs on Windows automatically
- No manual intervention needed

**Before each release:**
1. ✅ All CI checks pass
2. ✅ Version bumped in pyproject.toml
3. ✅ Release notes mention Windows if relevant
4. ✅ PyPI publish succeeds

**After each release:**
- Monitor for Windows-specific bug reports
- Test on actual Windows machine if possible

---

## 📚 References

- **CI Workflows:** `.github/workflows/test.yml`, `.github/workflows/publish-to-pypi.yml`
- **Windows Tests:** `tests/test_windows_compat.py`
- **Previous Analysis:** `sessions/pouring-tide-1201/README_2025-12-01_06-47.md`

---

**Last Updated:** 2025-12-01
**Status:** ✅ Windows compatibility fully validated
