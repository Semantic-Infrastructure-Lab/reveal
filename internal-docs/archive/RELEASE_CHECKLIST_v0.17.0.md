# Release Checklist: v0.17.0

**Status:** ✅ READY TO SHIP
**Date:** 2025-12-07
**Type:** Minor release (feature addition)

---

## Pre-Release Verification

### ✅ Code Quality
- [x] All 118 tests passing
- [x] No regressions detected
- [x] Coverage: 35% overall, 76% for new python.py
- [x] No critical TODOs or FIXMEs
- [x] BrokenPipeError fixed and tested
- [x] Cross-platform compatibility (Linux verified, macOS/Windows code reviewed)

### ✅ Documentation
- [x] CHANGELOG.md complete with v0.17.0 section
- [x] README.md updated (line counts corrected, python:// examples)
- [x] AGENT_HELP.md rewritten (85% reduction, teaches help://)
- [x] AGENT_HELP_FULL.md updated (python:// docs, token warnings)
- [x] All examples tested and working
- [x] help://python self-documentation verified

### ✅ Version Consistency
- [x] pyproject.toml: 0.17.0
- [x] __init__.py: reads from pyproject.toml (correct)
- [x] CHANGELOG.md: [0.17.0] - 2025-12-07
- [x] AGENT_HELP.md: Version: 0.17.0
- [x] AGENT_HELP_FULL.md: Version: 0.17.0

### ✅ Files Ready to Commit
```
Modified (8 files):
  CHANGELOG.md                    # v0.17.0 release notes
  README.md                       # Updated line counts, python:// examples
  pyproject.toml                  # Version: 0.17.0
  reveal/AGENT_HELP.md           # Complete rewrite (336 lines)
  reveal/AGENT_HELP_FULL.md      # Python:// docs added (1,215 lines)
  reveal/adapters/__init__.py    # Register python adapter
  reveal/main.py                 # BrokenPipeError fix
  tests/test_adapters.py         # 15 new Python adapter tests

New (1 file):
  reveal/adapters/python.py      # Python runtime adapter (478 lines)

Generated (for reference, not committed):
  .git-commit-message.txt        # Pre-written commit message
  RELEASE_CHECKLIST_v0.17.0.md   # This file
```

### ✅ Testing
- [x] Unit tests: 118/118 passing
- [x] Manual testing: All python:// endpoints verified
- [x] help:// system tested
- [x] Piping tested (head/tail/grep)
- [x] JSON output tested
- [x] Examples from CHANGELOG tested

---

## Release Commands

### 1. Review Changes
```bash
cd /home/scottsen/src/projects/reveal/external-git
git status
git diff --stat
```

### 2. Stage & Commit
```bash
# Stage all changes
git add CHANGELOG.md README.md pyproject.toml
git add reveal/AGENT_HELP.md reveal/AGENT_HELP_FULL.md
git add reveal/adapters/python.py reveal/adapters/__init__.py
git add reveal/main.py tests/test_adapters.py

# Commit with prepared message
git commit -F .git-commit-message.txt

# Or commit with short message
git commit -m "feat(v0.17.0): python runtime adapter, help system redesign, pipeline fixes

- Add python:// adapter with 8 endpoints (version, env, venv, packages, imports, bytecode)
- Redesign help system: --agent-help 85% smaller, teaches help:// pattern
- Fix BrokenPipeError when piping output
- 15 comprehensive tests, 76% coverage
- Complete documentation updates"
```

### 3. Tag Release
```bash
git tag -a v0.17.0 -m "Release v0.17.0: Python Runtime Adapter

Major Features:
- Python runtime inspection adapter (python://)
- Help system redesign (token-efficient discovery)
- BrokenPipeError fix for piping support

See CHANGELOG.md for complete details."
```

### 4. Push to GitHub
```bash
# Push commits
git push origin master

# Push tags
git push origin v0.17.0
```

### 5. Create GitHub Release
1. Go to: https://github.com/Semantic-Infrastructure-Lab/reveal/releases/new
2. Select tag: v0.17.0
3. Title: "v0.17.0 - Python Runtime Adapter"
4. Description: Copy from CHANGELOG.md (lines 10-196)
5. Click "Publish release"
6. **CI will automatically publish to PyPI via trusted publishing**

### 6. Verify PyPI Publication
```bash
# Wait 2-3 minutes for CI, then check
pip install --upgrade reveal-cli

# Verify version
python -c "import reveal; print(reveal.__version__)"
# Should show: 0.17.0

# Test new features
reveal python://
reveal help://python
```

---

## Post-Release

### Cleanup (Optional)
```bash
# Remove release artifacts
rm .git-commit-message.txt
rm RELEASE_CHECKLIST_v0.17.0.md

# Update planning docs status
# Edit: internal-docs/planning/README.md
# Change status to: "✅ Complete - v0.17.0 (Dec 2025)"
```

### Announce (Optional)
- Tweet/blog about new python:// adapter
- Update project documentation site
- Notify users in Discord/Slack channels

### Next Steps (v0.18.0 Planning)
- Implement Phase 2: python://imports/graph, circular detection
- Improve CLI test coverage (main.py 16% → 40%+)
- Consider additional language adapters (node://, rust://)

---

## Rollback Plan

If issues discovered after release:

### Minor Issue
1. Create hotfix branch
2. Fix issue
3. Release v0.17.1

### Major Issue
1. Yank release from PyPI (if critical bug)
```bash
# Yank (doesn't delete, just marks as unavailable)
pip install twine
twine upload --repository pypi --skip-existing dist/*
# Then mark as yanked on PyPI web interface
```

2. Create v0.17.1 with fix
3. Announce issue and fix

---

## Risk Assessment

**LOW RISK** - All checks passing, well-tested, backwards compatible

**Potential Issues:**
- ⚠️  pkg_resources deprecation warnings (known, non-blocking)
- ⚠️  Platform-specific edge cases (Windows/macOS untested locally)
- ⚠️  Very old Python versions (<3.8) - not supported

**Mitigation:**
- Comprehensive test suite (118 tests)
- Fallback to importlib.metadata if pkg_resources unavailable
- CI runs on multiple platforms
- Python >=3.8 requirement specified

---

## Success Criteria

Release considered successful when:
- [x] All tests passing
- [ ] PyPI shows v0.17.0
- [ ] CI build passes on GitHub
- [ ] Installation works: `pip install reveal-cli==0.17.0`
- [ ] `reveal python://` works on fresh install
- [ ] No critical bugs reported in first 24 hours

---

**READY TO SHIP! 🚀**

All checks passed. No blockers identified. Release with confidence.
