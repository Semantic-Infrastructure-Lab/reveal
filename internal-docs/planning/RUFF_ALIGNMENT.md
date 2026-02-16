# Ruff Alignment Status

**Last Updated**: 2026-01-05
**Session**: chosen-valley-0105

## Philosophy

Reveal's `--check` rules are **not intended to replace Ruff**. They exist to support Reveal's primary mission: progressive disclosure for AI agents. Rules should focus on structural/navigational issues that affect code comprehension, not comprehensive linting.

## Alignment Status

### Aligned Rules

| Reveal | Ruff | Status |
|--------|------|--------|
| E501 | E501 | Aligned - line length detection |
| C901 | C901 | Aligned - McCabe complexity (fixed v0.30.0) |
| I001 | F401 | Aligned - unused imports (fixed 2026-01-05) |
| R913 | PLR0913 | Aligned - too many arguments |

### Reveal-Unique Rules (No Ruff Equivalent)

These rules serve Reveal's mission and have no direct Ruff counterpart:

| Rule | Purpose |
|------|---------|
| I002 | Circular dependency detection |
| D001-D002 | Duplicate code detection |
| M101-M103 | File/function size limits |
| L001-L003 | Internal link validation |
| V001-V011 | Schema/documentation validation |
| N001-N003 | Nginx configuration analysis |
| C902 | Function too long (line count) |
| B002-B004 | Property/staticmethod patterns |

### Out of Scope

| Category | Why |
|----------|-----|
| Security (S*) | Defer to Bandit/Ruff - not core to exploration |
| F541 (f-string placeholders) | Pure style - Ruff handles better |
| Comprehensive bug patterns | Ruff has 20+ B rules - not our focus |

## Fixes Made

### I001 (2026-01-05)

**Problem**: Only flagged imports when ALL names were unused. Missed partial unused imports.

```python
# Before: No detection (List is used, so entire import ignored)
from typing import Dict, List  # Dict unused
```

**Fix**: Now flags each unused name individually, matching Ruff F401 behavior.

**Files Changed**:
- `reveal/rules/imports/I001.py` - Changed `_check_from_import` to return `List[Detection]`
- `tests/test_rules.py` - Updated test expectations

### C901 (2026-01-05, v0.30.0)

**Problem**: Used naive keyword counting instead of McCabe algorithm. Reported ~2x higher than Ruff.

**Fix**: Added `mccabe>=0.7.0` dependency and proper AST-based complexity calculation.

## Validation

To verify alignment:

```bash
# Should report same counts
reveal reveal/ --check -r --select I001 2>&1 | grep -c "I001"
ruff check reveal/ --select=F401 --statistics 2>/dev/null | head -1

# Compare specific file
reveal file.py --check --select E501,C901
ruff check file.py --select=E501,C901
```
