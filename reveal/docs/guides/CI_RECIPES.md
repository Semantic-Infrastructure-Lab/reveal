---
title: "Reveal CI/CD Recipes"
type: guide
help_topic: ci
help_description: "CI/CD integration recipes (GitHub Actions, GitLab CI, quality gates)"
help_category: feature_guides
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

Runs `reveal check --changed` on every PR. Fails if a changed file has quality findings.

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

      - name: PR check (rules on the changed files)
        run: reveal check --changed origin/${{ github.base_ref }}..HEAD
        # Exits 1 if quality issues are found in the changed files
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

Fails the build if any function in the PR got more than 5 complexity points harder, or a new
function arrives with complexity above 5 (an added function's delta is its whole complexity).

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

      - run: pip install reveal-cli   # jq is preinstalled on ubuntu-latest; otherwise: sudo apt-get install -y jq

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
              jq '.diff.functions[] | select(.complexity_delta > 5) | {function: .name, type: .type, file: .file, delta: .complexity_delta}'
            exit 1
          fi
```

Every entry carries the `file` it came from (added and removed entries too). To gate only on
regressions of existing code, select `.type == "modified" and .complexity_delta > 5`.

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
          reveal metrics://src/ --format json > metrics.json
          cat metrics.json | jq '{
            quality_score: .summary.avg_quality_score,
            total_functions: .summary.total_functions,
            avg_complexity: .summary.avg_complexity
          }'

      - uses: actions/upload-artifact@v4
        with:
          name: quality-metrics
          path: metrics.json
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
        # Exits 1 if a cert expires within 30 days, 2 if one is expired or invalid
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
    - reveal check --changed origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME..HEAD
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

# PR review (run before committing)
review:
	reveal check --changed main..HEAD

# Quality check (fail on any issues)
check:
	reveal check src/

# Complexity hotspots (informational)
hotspots:
	reveal hotspots src/ --top 20

# Health dashboard (code, then certificates and DNS)
health:
	reveal check ./src
	reveal health ssl://api.yoursite.com domain://yoursite.com

# Pack PR context for AI review (raise --budget until every changed file is listed;
# a changed file larger than the remaining budget is dropped)
pack:
	reveal pack src/ --since main --budget 30000 --content
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Completed, nothing matched the findings gate |
| 1 | Findings (rule violations, health warnings/failures, an expiring cert) |
| 2 | Request rejected before analysis (usage error, missing path); also an `ssl:// --check` failure (an expired or invalid cert) |
| 3 | Incomplete: a file could not be parsed/checked, a health target could not be reached, or a requested `--output json=PATH` could not be written (beats 1) |

`ssl:// --check` uses 0 pass / 1 warning / 2 failure, so an expired cert exits 2 there, while `reveal health`
reports the same cert as a failed check and exits 3. A critical rule violation under `check` is still 1.
`check` and `health` fail on findings by default. `hotspots` and `pack` are informational:
they exit 0 unless the request is rejected (2) or the run is incomplete (3), and `hotspots`
exits 1 only with `--fail-on findings`. Treat 3 as a failure too: it means the finding count
may be wrong. Each command's `--help` ends with its own exit-code block.

---

## Tips

**Speed up CI**: `reveal check` and `reveal check --changed` are fast (typically < 5 seconds for medium codebases). No indexing required.

**Baseline first**: Run `reveal hotspots src/` on your main branch before adding the complexity gate — this lets you set a realistic threshold rather than failing immediately.

**Advisory vs blocking**: add `--fail-on none` for first-time adoption (findings are reported but the run exits 0; an incomplete scan still exits 3), then drop it once the team is used to the output.

**Caching**: reveal keeps no index you have to build. It does keep a parse cache in `~/.reveal/cache/` (`REVEAL_CACHE_DIR` moves it, `REVEAL_DISK_CACHE=0` turns it off); persisting that directory between CI runs is optional.

---

## See Also

- [RECIPES.md](RECIPES.md) — General task recipes (CI is one application of these).
- [SUBCOMMANDS_GUIDE.md](SUBCOMMANDS_GUIDE.md) — Reference for `check`, `health`, `pack`, `hotspots`.
- [../QUICK_START.md](../QUICK_START.md) — First-run orientation before wiring into CI.
