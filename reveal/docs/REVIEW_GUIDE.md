---
title: "reveal review — PR Review Workflow"
type: guide
---

# reveal review — PR Review Workflow

Automated code review orchestrator. Runs quality checks, finds hotspots, and
reports complex functions — all in one pass.

## Usage

```
reveal review PATH                 # Review a directory
reveal review main..feature        # Review a git range (files changed vs main)
reveal review HEAD~3..HEAD         # Review last 3 commits
```

## CLI Flags

| Flag | Description |
|------|-------------|
| `--format json` | Machine-readable output for CI/CD gating |
| `--verbose` | Show detailed violation messages |

## Output Sections

1. **Structural changes** — files modified (git range mode only)
2. **Violations** — quality rule failures by severity (error / warning / info)
3. **Hotspots** — files with highest complexity or churn, with quality scores
4. **Complex functions** — functions above complexity threshold
5. **Recommendation** — pass/fail summary

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | No errors |
| `1` | Warnings only |
| `2` | Errors found |

## CI/CD Integration

```bash
# Gate on errors only
reveal review . --format json | jq '.sections.violations | map(select(.severity=="error")) | length == 0'

# Gate on any violations
reveal review main..HEAD --format json | jq '.overall_status == "pass"'
```

## Examples

```bash
reveal review .                     # Review current directory
reveal review ./src                 # Review src/ only
reveal review main..feature-branch  # PR review (git range)
reveal review . --verbose           # Show full violation details
reveal review . --format json       # For CI/CD
```

## See Also

- `reveal check` — Run quality rules on specific files
- `reveal health` — Health check for services/paths
- `reveal review --help` — Full flag reference
