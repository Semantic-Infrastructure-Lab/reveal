---
title: "reveal health — Unified Health Check"
type: guide
---

# reveal health — Unified Health Check

Unified health check across all resource types. Routes automatically based on
target type — no need to know which adapter to use.

## Usage

```
reveal health TARGET [TARGET ...]
```

## CLI Flags

| Flag | Description |
|------|-------------|
| `--format json` | Machine-readable output |
| `--verbose` | Show detailed check results |

## Target Types (Auto-detected)

| Target | What it checks |
|--------|----------------|
| `./path` or `/path` | Directory quality (violations, hotspots) |
| `ssl://example.com` | SSL certificate validity, expiry, chain |
| `mysql://host` | MySQL connectivity, replication health |
| `domain://example.com` | DNS, registrar, HTTPS availability |

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All checks pass |
| `1` | Warnings (non-critical issues) |
| `2` | Failures (action required) |

## Examples

```bash
reveal health .                         # Local directory health
reveal health ssl://example.com         # SSL cert health
reveal health domain://example.com      # Domain + DNS health

# Composable: check multiple targets
reveal health ./src ssl://api.example.com mysql://localhost

# CI/CD: fail on warnings or failures
reveal health . --format json | jq '.exit_code == 0'
```

## See Also

- `reveal review` — Code review workflow
- `reveal check` — Quality rules only
- `reveal health --help` — Full flag reference
