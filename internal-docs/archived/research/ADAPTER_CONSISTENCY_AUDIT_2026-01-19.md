# Adapter Consistency Audit

**Date**: 2026-01-19
**Session**: xujuyodo-0119
**Scope**: Breadcrumb usage, config patterns, hardcoded values across all adapters

---

## Executive Summary

Audited all 15 adapters for consistency in:
1. **Breadcrumb patterns** (`see_also` in help) - 93% coverage
2. **Config integration** - MySQL adapter is exemplar; others lag
3. **Hardcoded values** - Several thresholds should be configurable

**Key Findings:**
- `imports://` adapter missing `see_also` breadcrumbs entirely
- `stats.py` quality thresholds are hardcoded (should follow mysql pattern)
- Git adapter limits documented but not user-overridable
- No inappropriate hardcoded paths found

---

## 1. Breadcrumb Analysis (`see_also`)

### What Makes Good Breadcrumbs

From `ADAPTER_AUTHORING_GUIDE.md:153-163`:
```python
'see_also': [
    'reveal help://myscheme-guide - Comprehensive guide with examples',
    'reveal help://related - Related adapter',
    'reveal --agent-help - General agent patterns'
]
```

Breadcrumbs should:
- Link to related adapters for similar tasks
- Point to comprehensive guides when available
- Include relevant CLI flags

### Adapter Coverage

| Adapter | Has `see_also` | Quality | Links To |
|---------|----------------|---------|----------|
| `env.py` | ✅ | Good | python, tricks, ast |
| `ast.py` | ✅ | Good | python, tricks, --check |
| `json_adapter.py` | ✅ | Good | file, ast, tricks |
| `help.py` | ✅ | Good | --agent-help variants |
| `reveal.py` | ✅ | Good | --rules, ast, help |
| `markdown.py` | ✅ | Good | --related, --frontmatter, knowledge-graph |
| `git/adapter.py` | ✅ | Good | diff, ast, stats |
| `claude/adapter.py` | ✅ | Adequate | json, adapters, TIA session |
| `python/help.py` | ✅ | Excellent | guide with multi-shot examples |
| `diff.yaml` | ✅ | Good | file, env, mysql |
| `stats.yaml` | ✅ | Good | ast, --check, tricks |
| `mysql.yaml` | ✅ | Good | health thresholds documented |
| `sqlite.yaml` | ✅ | Good | mysql, env, ast |
| **`imports.py`** | ❌ | **Missing** | N/A |

### Missing Breadcrumbs: imports.py

**File**: `reveal/adapters/imports.py:282-313`

Current `get_help()` returns no `see_also`:
```python
def get_help() -> Dict[str, Any]:
    return {
        'name': 'imports',
        'description': 'Import graph analysis...',
        'uri_scheme': 'imports://<path>',
        'examples': [...],
        'query_parameters': {...},
        'supported_languages': get_supported_languages(),
        'status': 'beta'
        # NO see_also!
    }
```

**Recommendation** - Add:
```python
'see_also': [
    'reveal help://ast - Query code structure by complexity',
    'reveal help://stats - Codebase metrics and hotspots',
    'reveal help://configuration - Layer violation config (.reveal.yaml)',
    'reveal file.py --check - Run quality checks including I001-I004'
]
```

---

## 2. Config Pattern Analysis

### The Gold Standard: MySQL Adapter

**File**: `reveal/adapters/mysql/adapter.py:730-754`

```python
def _get_health_config(self) -> Dict[str, Any]:
    """Load health check configuration.

    Config search order:
    1. ./.reveal/mysql-health-checks.yaml (project)
    2. ~/.config/reveal/mysql-health-checks.yaml (user)
    3. /etc/reveal/mysql-health-checks.yaml (system)
    4. Hardcoded defaults (fallback)
    """
    from reveal.config import load_config

    defaults = {
        'checks': [
            {'name': 'Table Scan Ratio', 'metric': 'table_scan_ratio',
             'pass_threshold': 10, 'warn_threshold': 25, ...},
            {'name': 'Buffer Hit Rate', 'metric': 'buffer_hit_rate',
             'pass_threshold': 99, 'warn_threshold': 95, ...},
            # ... more checks
        ]
    }

    return load_config('mysql-health-checks.yaml', defaults)
```

**Why This Is Good:**
- Sensible defaults work out-of-box
- Users can override per-project, per-user, or system-wide
- Config file location is documented in help
- Uses unified `load_config()` system

### Adapters NOT Using Config System

| Adapter | Hardcoded Values | Should Use Config? |
|---------|------------------|-------------------|
| `stats.py` | Quality score thresholds | **Yes** |
| `ast.py` | Line→complexity heuristic | Maybe (fallback only) |
| `git/adapter.py` | Result limits (10, 20) | Maybe (document if not) |

---

## 3. Hardcoded Values Audit

### 3.1 stats.py Quality Thresholds

**File**: `reveal/adapters/stats.py:456-476`

```python
def _calculate_quality_score(...) -> float:
    score = 100.0

    # Penalize high complexity (target: <10)
    if avg_complexity > 10:                          # HARDCODED
        score -= min(30, (avg_complexity - 10) * 3)  # HARDCODED

    # Penalize long functions (target: <50 lines avg)
    if avg_func_length > 50:                         # HARDCODED
        score -= min(20, (avg_func_length - 50) / 2) # HARDCODED

    # Penalize files with many long functions
    if total_functions > 0:
        long_func_ratio = long_func_count / total_functions
        score -= min(25, long_func_ratio * 50)       # HARDCODED

    # Penalize deep nesting
    if total_functions > 0:
        deep_nesting_ratio = deep_nesting_count / total_functions
        score -= min(25, deep_nesting_ratio * 50)    # HARDCODED
```

**Problem**: These thresholds are reasonable defaults but not configurable. Different codebases have different standards.

**Recommendation** - Follow mysql pattern:
```python
QUALITY_DEFAULTS = {
    'thresholds': {
        'complexity_target': 10,
        'function_length_target': 50,
        'deep_nesting_depth': 4,
    },
    'penalties': {
        'complexity_multiplier': 3,
        'complexity_max': 30,
        'length_divisor': 2,
        'length_max': 20,
        'ratio_multiplier': 50,
        'ratio_max': 25,
    }
}

def _get_quality_config(self) -> Dict[str, Any]:
    from reveal.config import load_config
    return load_config('stats-quality.yaml', QUALITY_DEFAULTS)
```

### 3.2 ast.py Line-to-Complexity Heuristic

**File**: `reveal/adapters/ast.py:461-473`

```python
def _estimate_complexity(self, element: Dict[str, Any]) -> int:
    """Fallback heuristic when tree-sitter complexity unavailable."""
    line_count = element.get('line_count', 0)

    if line_count <= 10:    return 1
    elif line_count <= 20:  return 2
    elif line_count <= 30:  return 3
    elif line_count <= 40:  return 5
    elif line_count <= 60:  return 7
    else:
        return line_count // 10
```

**Assessment**: This is a fallback heuristic, only used when tree-sitter can't calculate actual complexity. Lower priority for config since it's rarely invoked.

**Recommendation**: Document in code comments that these are intentionally simple fallbacks. Consider config only if users request it.

### 3.3 git/adapter.py Result Limits

**File**: `reveal/adapters/git/adapter.py`

```python
# Line 478: Hardcoded in get_structure()
recent_commits = self._get_recent_commits(repo, limit=10)

# Lines 489, 493: Hardcoded slicing
'recent': branches[:10],
'recent': tags[:10],

# Lines 787, 814, 850, 870: Default parameters
def _list_branches(self, repo, limit: int = 20): ...
def _list_tags(self, repo, limit: int = 20): ...
def _get_recent_commits(self, repo, limit: int = 10): ...
def _get_file_history(self, repo, path, start_commit, limit: int = 20): ...
```

**Assessment**: The help docs (line 455) mention `limit` as a query parameter, but:
- Overview slicing (`[:10]`) ignores query params
- Default structure call uses hardcoded `limit=10`

**Recommendation**:
1. Make overview respect `?limit=N` query param, OR
2. Document clearly that overview always shows "most recent 10"
3. Consider config: `git-adapter.yaml` with `default_limits.branches: 20`

### 3.4 Appropriate Hardcoded Paths

These paths are **correctly hardcoded**:

| Path | Adapter | Reason |
|------|---------|--------|
| `/etc/reveal/config.yaml` | reveal.py | Standard system config location |
| `/etc/reveal/mysql-health-checks.yaml` | mysql/adapter.py | Documented, overridable |
| `~/.claude/projects/` | claude/adapter.py | Actual Claude Code storage location |
| `~/.config/reveal/` | various | XDG standard |

No inappropriate hardcoded paths found.

---

## 4. Recommendations Summary

### Priority 1: Fix Missing Breadcrumbs (imports.py)

**Effort**: 5 minutes
**Impact**: Completes 100% breadcrumb coverage

```python
# Add to imports.py get_help() return dict:
'see_also': [
    'reveal help://ast - Query code structure',
    'reveal help://stats - Codebase metrics',
    'reveal help://configuration - Layer config',
    'reveal file.py --check - Import quality rules'
]
```

### Priority 2: Make stats.py Thresholds Configurable

**Effort**: 30 minutes
**Impact**: Allows per-project quality standards

Create `reveal/adapters/help_data/stats-quality.yaml`:
```yaml
# Quality scoring configuration
thresholds:
  complexity_target: 10      # Functions above this get penalized
  function_length_target: 50 # Lines; functions above this penalized
  deep_nesting_depth: 4      # Nesting beyond this penalized

penalties:
  complexity:
    multiplier: 3            # Points lost per unit above target
    max: 30                  # Maximum penalty
  length:
    divisor: 2               # Points lost = (excess / divisor)
    max: 20
  ratios:
    multiplier: 50           # For long_func_ratio, deep_nesting_ratio
    max: 25
```

### Priority 3: Clarify git Adapter Limits

**Effort**: 15 minutes
**Impact**: Better user expectations

Either:
- A) Support `git://.?limit=20` for overview, OR
- B) Add note to help: "Overview shows 10 most recent items; use element queries for more"

### Priority 4: Document ast.py Heuristic

**Effort**: 5 minutes
**Impact**: Code clarity

Add comment explaining the heuristic is intentionally simple fallback, rarely used with modern tree-sitter support.

---

## 5. Testing Checklist

After implementing changes:

- [ ] `reveal help://imports` shows see_also section
- [ ] `reveal help://` lists imports with proper description
- [ ] Stats config file loads from `.reveal/stats-quality.yaml`
- [ ] Stats defaults work when no config present
- [ ] Git help clarifies limit behavior
- [ ] All existing tests pass

---

## 6. Related Sessions

- `clearing-gale-0108`: v0.32.2 release, bug fixes
- `wrathful-eclipse-1223`: v0.26.0 element extraction
- `visible-pulsar-1211`: Markdown support analysis

---

## Appendix: Adapter Registry

All adapters examined:

```
adapters/
├── ast.py              # ✅ Breadcrumbs, no config needed
├── base.py             # Base class, documents see_also
├── diff.py             # ✅ Uses YAML help
├── env.py              # ✅ Breadcrumbs
├── help.py             # ✅ Breadcrumbs
├── imports.py          # ❌ MISSING BREADCRUMBS
├── json_adapter.py     # ✅ Breadcrumbs
├── markdown.py         # ✅ Breadcrumbs
├── mysql.py            # Wrapper, uses mysql/adapter.py
├── reveal.py           # ✅ Breadcrumbs, uses config
├── stats.py            # ✅ Breadcrumbs (YAML), needs config
├── claude/adapter.py   # ✅ Breadcrumbs
├── git/adapter.py      # ✅ Breadcrumbs, document limits
├── mysql/adapter.py    # ✅ EXEMPLAR config pattern
├── python/adapter.py   # ✅ Uses help.py
├── python/help.py      # ✅ Excellent breadcrumbs
└── sqlite/adapter.py   # ✅ Uses YAML help
```
