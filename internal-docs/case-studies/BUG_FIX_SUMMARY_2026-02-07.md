---
session: solar-observatory-0207
date: 2026-02-07
activity: Bug fixes from dogfooding
status: complete
---

# Bug Fix Summary: Reveal Dogfooding Issues

## Issues Fixed

### 1. ✅ Git URI Format Confusion (High Priority)

**Problem**: Users expected `diff://file.py:git://HEAD~1:file.py` but git adapter requires `git://file.py@HEAD~1` format.

**Root Cause**: 
- Git CLI uses `ref:path` format (`git show HEAD~1:file.py`)
- Reveal git adapter uses `path@ref` format (`git://file.py@HEAD~1`)
- Diff adapter URI parsing created ambiguity with `:` separator

**Solution**:
1. Added helpful error detection for `ref:path` pattern
2. Provides corrected URI format in error message
3. Added git:// examples to diff adapter schema
4. Documented both modern (`path@ref`) and legacy (`ref/path`) formats

**Changes**:
- `reveal/adapters/diff.py`:
  - Added git:// URI format validation in `_resolve_uri`
  - Added git:// URI format validation in `_resolve_git_adapter`
  - Added 2 new example queries showing git:// usage
  - Added 2 notes about git URI format

**Error Message Before**:
```
Error: Failed to get file from git: fatal: path 'reveal:adapters/diff.py' does not exist in 'HEAD~1'
```

**Error Message After**:
```
Error: Git URI format error. Got 'git://HEAD~1:reveal/adapters/diff.py' but git:// URIs must use:
  1. Modern format:  git://path@ref  (e.g., git://app.py@HEAD~1)
  2. Legacy format:  git://ref/path  (e.g., git://HEAD~1/app.py)
Hint: Try 'git://reveal/adapters/diff.py@HEAD~1' or fix the separator
```

**Tests**: All 34 diff adapter tests pass ✅

**Commit**: `dd2a8f9 - fix(diff): Add git:// URI format validation and examples`

---

### 2. ✅ Query Parameter Documentation Gap

**Problem**: No central reference for which adapters support query parameters and what they do.

**Solution**: Created comprehensive `QUERY_PARAMETER_REFERENCE.md` documentation.

**Content**:
- Quick reference table for all adapters
- Detailed documentation for each adapter with query params:
  - **imports://** - `unused`, `circular`, `violations`
  - **git://** - `type`, `detail`, `element`, `author`, `email`, `message`, `hash`
  - **json://** - `schema`, field filters
  - **markdown://** - field filters (frontmatter)
  - **stats://** - `hotspots`, `code_only`
  - **ast://** - `lines`
  - **claude://** - `summary`, `tools`, `errors`
- Universal query operators (`=`, `~=`, `>`, `<`, `..`, `!`, `*`)
- Examples for every parameter
- Best practices and usage patterns
- Clarified which adapters use element paths vs query params

**Changes**:
- Created `reveal/docs/QUERY_PARAMETER_REFERENCE.md` (363 lines)
- Updated `reveal/docs/README.md` to link to new reference

**Commits**:
- `0555617 - docs: Add comprehensive query parameter reference`
- `834b085 - docs: Add query parameter reference to docs index`

---

## Test Results

**Diff Adapter Tests**: 34/34 passed ✅
**Adapter Integration Tests**: 83/83 passed ✅
**Query Parser**: All tests passing (fixed in previous session)

---

## Impact

### User Experience
- **Clear error messages** guide users to correct git URI format
- **Comprehensive documentation** eliminates guesswork about query parameters
- **Reduced friction** when using diff adapter with git references

### Documentation
- **363 lines** of new query parameter documentation
- **7 adapters** with query params fully documented
- **30+ examples** showing query parameter usage

### Code Quality
- **Better error handling** with actionable hints
- **No breaking changes** - all existing tests pass
- **Backward compatible** - both git URI formats still work

---

## Lessons Learned

### URI Format Expectations
- Users expect familiar CLI patterns (git uses `ref:path`)
- Reveal uses different patterns (`path@ref`) for good reasons (URL compatibility)
- **Solution**: Detect common mistakes and provide helpful error messages

### Documentation Discoverability
- Feature exists (query parameters) but users don't know about them
- Scattered across adapter schemas, not in central reference
- **Solution**: Comprehensive reference docs with quick lookup table

### Error Message Quality
- Generic errors like "path does not exist" don't help users
- Specific format errors should suggest corrections
- **Solution**: Detect patterns and provide actionable hints

---

## Next Steps

### Immediate (from previous session)
- **diff adapter test expansion** - 27% coverage, expand to ~82%
- **MySQL adapter tests** - 20% coverage

### Future Improvements
1. **Support git CLI format** - Add `git://REF:path` as alias for `git://path@REF`
2. **Query parameter autocomplete** - Add shell completion for query params
3. **Query builder UI** - Interactive query builder for complex filters

---

## Files Changed

**Modified** (1):
- `reveal/adapters/diff.py` (+34 lines, -1 line)
  - Git URI format validation
  - Helpful error messages
  - Example queries
  - Documentation notes

**Created** (1):
- `reveal/docs/QUERY_PARAMETER_REFERENCE.md` (363 lines)
  - Comprehensive query parameter reference
  - All adapters documented
  - Universal operator reference

**Updated** (1):
- `reveal/docs/README.md` (+1 line)
  - Added query parameter reference link

---

## Session Statistics

**Duration**: ~2 hours
**Commits**: 3
**Files Modified**: 3
**Lines Added**: ~400
**Tests**: 117 passing (34 diff + 83 adapters)
**Issues Fixed**: 2
**Documentation Created**: 363 lines

---

**Session Status**: ✅ COMPLETE
**Project**: Reveal (external-git)
**Repository**: `/home/scottsen/src/projects/reveal/external-git`
**Next Session**: Consider diff adapter test expansion or continue with other dogfooding improvements
