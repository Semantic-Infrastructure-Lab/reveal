# Reveal v0.2.0 Pre-Release Validation

**Purpose:** Validate reveal v0.2.0 is production-ready before merging to master and publishing to PyPI.

**When to run:** Next session, with fresh eyes and clean environment.

**How to run:**
```bash
cd /home/scottsen/src/projects/reveal
git checkout clean-redesign
./validate_v0.2.0.sh
```

---

## Automated Test Suite

The `validate_v0.2.0.sh` script runs comprehensive automated tests:

### ✅ Phase 1: Installation & Setup
- [ ] Package installs correctly with `pip install -e .[treesitter]`
- [ ] Version is 0.2.0 in both `__init__.py` and `pyproject.toml`

### ✅ Phase 2: Core Functionality
- [ ] `--help` displays correctly
- [ ] Directory tree view works (`reveal reveal/`)
- [ ] Python file structure extraction works
- [ ] **Function signature bug is FIXED** (no `def` prefix in signatures)
- [ ] Element extraction works (`reveal file.py ClassName`)

### ✅ Phase 3: Multi-Language Support
- [ ] Markdown files work
- [ ] JSON/YAML analyzers import correctly
- [ ] Rust files work (if TreeSitter installed)

### ✅ Phase 4: Edge Cases
- [ ] Non-existent file errors gracefully
- [ ] Unsupported file types handled gracefully

### ✅ Phase 5: Code Quality
- [ ] **No engineering debt naming** (`*_new.*`, `*_old.*`, `*_v2.*`)
- [ ] No references to `analyzers_new` or `new_cli` in code
- [ ] Version numbers consistent across all files

### ✅ Phase 6: TreeSitter (Optional)
- [ ] TreeSitter installed and working
- [ ] Multi-language support enabled

---

## Manual Validation Checklist

Beyond automated tests, manually verify:

### 📦 Package Quality
- [ ] README.md accurately describes v0.2.0 behavior
- [ ] Examples in README all work
- [ ] `pyproject.toml` entry point is `reveal.main:main` (not `new_cli`)
- [ ] No old code in main reveal/ directory (archived in `_archive_old_v0.1/`)

### 🧪 Real-World Usage Tests
Test on various file types from actual projects:

```bash
# Test on TIA codebase
reveal /home/scottsen/src/tia/lib/ai/services/inference_service.py
reveal /home/scottsen/src/tia/lib/ai/services/inference_service.py InferenceService

# Test on reveal itself (dogfooding)
reveal reveal/
reveal reveal/base.py
reveal reveal/treesitter.py TreeSitterAnalyzer

# Test Markdown
reveal README.md
reveal README.md "Quick Start"

# Test directory depth
reveal . --depth 1
reveal . --depth 3
```

### 🎨 Output Quality
- [ ] Output is clean and readable
- [ ] File paths use consistent `filename:line` format
- [ ] Navigation hints are helpful (`→ reveal file.py <element>`)
- [ ] No duplicate text in function signatures
- [ ] Icons display correctly (📄, 📁, etc.)

### 🚨 Error Messages
Intentionally cause errors and verify messages are helpful:

```bash
reveal /nonexistent/file.py          # Should: Clear "not found" message
reveal file.txt                      # Should: "No analyzer" or graceful fallback
reveal file.py nonexistent_function  # Should: "Element not found"
```

### 📚 Documentation Review
- [ ] README matches actual behavior
- [ ] Installation instructions are correct
- [ ] Examples all work as shown
- [ ] No references to old "levels" system
- [ ] Feature list is accurate

### 🔍 Code Review
Quick scan for any remaining issues:

```bash
# Check for any TODO/FIXME
grep -r "TODO\|FIXME\|XXX\|HACK" reveal/ --include="*.py" | grep -v _archive

# Check for any debug prints
grep -r "print(" reveal/ --include="*.py" | grep -v _archive | grep -v "def __repr__"

# Verify no old imports
grep -r "from reveal.new_cli\|from reveal.analyzers_new" reveal/ --include="*.py"
```

---

## Performance Sanity Check

Not formal benchmarks, but verify it feels fast:

```bash
# Should be near-instant
time reveal reveal/base.py

# Should be fast (< 1 second for small dir)
time reveal reveal/

# Should handle large directories reasonably
time reveal /home/scottsen/src/tia/ --depth 2
```

If any command takes > 5 seconds, investigate why.

---

## Decision Matrix

After running all tests:

| Scenario | Action |
|----------|--------|
| ✅ All automated tests pass + manual checks OK | **Proceed to release** |
| ⚠️ Minor issues (typos, docs) | Fix, re-validate, then release |
| ❌ Core functionality broken | **DO NOT RELEASE** - fix and re-test |
| ❌ Signature bug still present | **DO NOT RELEASE** - major regression |

---

## Release Procedure (After Validation Passes)

```bash
# 1. Merge to master
git checkout master
git merge clean-redesign
git push origin master

# 2. Tag release
git tag -a v0.2.0 -m "Release v0.2.0 - Clean redesign with TreeSitter support"
git push origin v0.2.0

# 3. Build package
python3 -m build
# Creates: dist/reveal-cli-0.2.0.tar.gz and dist/reveal_cli-0.2.0-py3-none-any.whl

# 4. Test package install
pip install dist/reveal_cli-0.2.0-py3-none-any.whl
reveal --help  # Verify works

# 5. Publish to PyPI
python3 -m twine upload dist/*
# Enter credentials when prompted

# 6. Verify on PyPI
pip install --upgrade reveal-cli
reveal --version  # Should show 0.2.0
```

---

## Rollback Plan (If Issues Found After Release)

If critical issues discovered after PyPI publication:

1. **Immediate:** Add warning to GitHub README
2. **Quick fix:** Release v0.2.1 with fix
3. **Last resort:** Yank v0.2.0 from PyPI (rare, only for severe issues)

```bash
# Yank a release (if absolutely necessary)
twine upload --repository pypi --skip-existing dist/*
# Then manually yank on PyPI web interface
```

---

## Success Criteria

✅ All automated tests pass  
✅ Manual tests confirm quality  
✅ Documentation is accurate  
✅ No engineering debt naming  
✅ Ready for users and contributors  

If all criteria met: **Ship it!** 🚀

---

## Notes for Next Session

- Run `./validate_v0.2.0.sh` first thing
- If TreeSitter not installed, run: `pip install tree-sitter==0.21.3 tree-sitter-languages>=1.10.0`
- Test on at least 3 different file types from real projects
- Check GitHub issues for any user-reported problems with clean-redesign branch
- Fresh perspective - don't assume anything works, verify everything

**Remember:** Better to delay release by a day than ship broken code to PyPI!
