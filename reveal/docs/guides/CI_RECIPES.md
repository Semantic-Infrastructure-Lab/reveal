---
title: "Reveal CI/CD Recipes"
type: guide
beth_topics:
  - reveal
  - ci-cd
  - github-actions
  - gitlab-ci
  - quality-gates
  - automation
---

# Reveal CI/CD Recipes

Ready-to-paste configurations for GitHub Actions, GitLab CI, and generic pipelines.
All use `pip install reveal-cli` — no Docker required.

---

## GitHub Actions

### PR Quality Gate

Runs `reveal review` on every PR. Fails if complexity increases or quality checks fail.

```yaml
# .github/workflows/reveal-review.yml
name: Code Review

on:
  pull_request:
    branches: [main, master]

jobs:
  reveal-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history needed for git diff

      - name: Install reveal
        run: pip install reveal-cli

      - name: PR review (diff + check + hotspots)
        run: reveal review origin/${{ github.base_ref }}..HEAD
        # Exits 1 if quality issues or complexity regressions found
```

### Changed-Files Quality Gate

Checks only the files changed in the PR. Faster than a full-repo scan; still exits 1 if any violations are found.

```yaml
# .github/workflows/changed-files-check.yml
name: Changed Files Check

on:
  pull_request:

jobs:
  check-changed:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install reveal
        run: pip install reveal-cli

      - name: Check changed files
        run: git diff --name-only origin/${{ github.base_ref }}...HEAD | reveal --stdin --check
        # Exits 1 if any changed file has violations
```

### Complexity Gate

Fails the build if any function in the PR got more than 5 complexity points harder.

```yaml
# .github/workflows/complexity-gate.yml
name: Complexity Gate

on:
  pull_request:

jobs:
  complexity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - run: pip install reveal-cli jq

      - name: Check complexity delta
        run: |
          # Get functions whose complexity increased by more than 5
          REGRESSIONS=$(reveal diff://git://origin/${{ github.base_ref }}/.:git://HEAD/. \
            --format json | \
            jq '[.diff.functions[] | select(.complexity_delta > 5)] | length')

          echo "Complexity regressions (delta > 5): $REGRESSIONS"
          if [ "$REGRESSIONS" -gt 0 ]; then
            echo "Failing: complexity increased in $REGRESSIONS function(s)"
            reveal diff://git://origin/${{ github.base_ref }}/.:git://HEAD/. \
              --format json | \
              jq '.diff.functions[] | select(.complexity_delta > 5) | {function: .name, file: .file, delta: .complexity_delta}'
            exit 1
          fi
```

### Hotspot Tracking

Reports the top 10 most complex functions on every push to main.

```yaml
# .github/workflows/hotspots.yml
name: Hotspot Report

on:
  push:
    branches: [main]

jobs:
  hotspots:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install reveal-cli

      - name: Top 10 complexity hotspots
        run: reveal hotspots src/ --top 10
        # Always exits 0 — informational only
```

### Quality Score Tracking

Saves quality metrics to a job artifact for trend tracking.

```yaml
# .github/workflows/quality-metrics.yml
name: Quality Metrics

on:
  push:
    branches: [main]

jobs:
  metrics:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install reveal-cli

      - name: Collect quality metrics
        run: |
          reveal stats://src/ --format json > metrics.json
          cat metrics.json | jq '{
            quality_score: .quality_score,
            total_functions: .total_functions,
            avg_complexity: .avg_complexity,
            hotspot_count: (.hotspots | length)
          }'

      - uses: actions/upload-artifact@v4
        with:
          name: quality-metrics
          path: metrics.json
```

### Dead Code Check

Flags uncalled functions introduced in a PR.

```yaml
# .github/workflows/dead-code.yml
name: Dead Code Check

on:
  pull_request:

jobs:
  dead-code:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install reveal-cli

      - name: Check for dead code
        run: |
          UNCALLED=$(reveal 'calls://src/?uncalled' --format json | \
            jq '[.uncalled[]] | length')
          echo "Uncalled functions: $UNCALLED"
          if [ "$UNCALLED" -gt 0 ]; then
            reveal 'calls://src/?uncalled'
            # Advisory only — change exit 0 to exit 1 to enforce
            exit 0
          fi
```

### SSL Certificate Health Check

Checks that all SSL certs in your nginx config are valid and not expiring soon.
Suitable for scheduled runs.

```yaml
# .github/workflows/ssl-health.yml
name: SSL Health

on:
  schedule:
    - cron: '0 9 * * 1'   # Monday mornings
  workflow_dispatch:

jobs:
  ssl-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install reveal-cli

      - name: Check SSL certificates
        run: |
          # Extract domains from nginx config and batch check them
          reveal nginx.conf --extract domains --canonical-only | \
            reveal --stdin --batch --check --expiring-within 30
        # Exits 1 if any cert is expired or expiring within 30 days
```

---

## GitLab CI

### PR Quality Gate

```yaml
# .gitlab-ci.yml
reveal-review:
  stage: test
  image: python:3.11
  before_script:
    - pip install reveal-cli
  script:
    - reveal review origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME..HEAD
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

### Complexity Gate

```yaml
complexity-gate:
  stage: test
  image: python:3.11
  before_script:
    - pip install reveal-cli
    - apt-get update -q && apt-get install -qy jq
  script:
    - |
      REGRESSIONS=$(reveal diff://git://origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME/.:git://HEAD/. \
        --format json | \
        jq '[.diff.functions[] | select(.complexity_delta > 5)] | length')
      echo "Complexity regressions: $REGRESSIONS"
      [ "$REGRESSIONS" -eq 0 ]
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

---

## Generic Makefile Targets

Add these to your `Makefile` for local use and CI parity:

```makefile
.PHONY: review check hotspots quality

# Full PR review (run before committing)
review:
	reveal review main..HEAD

# Quality check (fail on any issues)
check:
	reveal check src/

# Complexity hotspots (informational)
hotspots:
	reveal hotspots src/ --top 20

# Health dashboard (code + dependencies)
health:
	reveal health ./src ssl://api.yoursite.com domain://yoursite.com

# Pack PR context for AI review
pack:
	reveal pack src/ --since main --budget 8000 --content
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Clean — no issues found |
| 1 | Violations found (quality issues, complexity regressions, certs expiring soon) |
| 2 | Critical violations (expired certs, critical-severity rule failures) |

All reveal subcommands (`review`, `check`, `health`, `pack`) use these exit codes,
making them directly usable as CI gates with `|| exit 1`.

---

## Tips

**Speed up CI**: `reveal check` and `reveal review` are fast (typically < 5 seconds for medium codebases). No indexing required.

**Baseline first**: Run `reveal hotspots src/` on your main branch before adding the complexity gate — this lets you set a realistic threshold rather than failing immediately.

**Advisory vs blocking**: Use exit 0 for first-time adoption (shows issues without blocking), then move to exit 1 once the team is used to the output.

**Caching**: reveal has no index to cache — each run is fresh. This is intentional (no stale data) and keeps setup simple.
