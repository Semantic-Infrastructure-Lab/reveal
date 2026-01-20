# Reveal: The Complete Codebase Review Guide

**Author**: TIA (The Intelligent Agent)
**Created**: 2026-01-16
**Session**: yafimi-0116
**Version**: 1.0

---

## Executive Summary

Reveal is a **semantic code exploration tool** that enables comprehensive codebase review through **progressive disclosure**. Unlike traditional tools that force you to read entire files or run expensive static analysis, reveal provides specialized URI adapters that let you navigate code as a queryable database.

**Key Insight**: A complete codebase review using reveal is 25-150x more token-efficient than reading files directly, making it ideal for AI-assisted reviews, onboarding, refactoring, and quality assessment.

---

## Table of Contents

1. [URI Adapters: Your Review Toolkit](#uri-adapters-your-review-toolkit)
2. [Core Review Workflows](#core-review-workflows)
3. [The Complete Codebase Review Process](#the-complete-codebase-review-process)
4. [Advanced Multi-Adapter Patterns](#advanced-multi-adapter-patterns)
5. [Quality Gates & Metrics](#quality-gates-metrics)
6. [Token-Efficient AI Review Strategies](#token-efficient-ai-review-strategies)
7. [Real-World Review Scenarios](#real-world-review-scenarios)
8. [Quick Reference](#quick-reference)

---

## URI Adapters: Your Review Toolkit

Reveal provides URI adapters, each specialized for different aspects of codebase analysis. Think of them as **semantic lenses** into your code. Run `reveal --adapters` to see the current list.

### 1. **ast://** - Code Structure Query Engine
Query code as a database using filters for complexity, size, type, name patterns, and decorators.

**Codebase Review Usage:**
```bash
# Find refactoring candidates (high complexity)
reveal 'ast://./src?complexity>10'

# Find god functions (complex AND long)
reveal 'ast://./src?complexity>15&lines>100'

# Find all test functions
reveal 'ast://.?name=test_*&type=function'

# Find complex properties (code smell)
reveal 'ast://.?decorator=property&complexity>5'

# Find functions with too many parameters
reveal 'ast://./src?type=function' --format=json | \
  jq '.results[] | select(.signature | split(",") | length > 5)'
```

**Review Insight**: `ast://` reveals **structural debt** - complex functions, god objects, naming patterns, and architectural decisions made concrete.

---

### 2. **stats://** - Codebase Health Dashboard
Aggregate metrics: lines of code, function/class counts, average complexity, quality scores, and **hotspots** (worst files).

**Codebase Review Usage:**
```bash
# Overall codebase health
reveal stats://./src

# Find top 10 problem files
reveal stats://./src --hotspots

# Track complexity over time (baseline)
reveal stats://./src --format=json > baseline.json

# Per-file detailed metrics
reveal stats://./src/critical_module.py
```

**Review Insight**: `stats://` gives you **the 30,000-foot view** - where to focus your review effort. Hotspots tell you which 10% of files need 90% of the attention.

---

### 3. **imports://** - Dependency Graph Analysis
Detect unused imports, circular dependencies, and architectural layer violations.

**Codebase Review Usage:**
```bash
# Find unused imports (dead code indicator)
reveal 'imports://src?unused'

# Detect circular dependencies (architectural smell)
reveal 'imports://src?circular'

# Check for layer violations (requires config)
reveal 'imports://src?violations'

# All imports summary
reveal imports://src
```

**Review Insight**: `imports://` reveals **architectural debt** - tangled dependencies, unused code, and violations of intended layer structure.

---

### 4. **diff://** - Semantic Comparison
Compare files, directories, or even different git refs at a **structural** level, not line-by-line.

**Codebase Review Usage:**
```bash
# Compare two versions of a file
reveal diff://app.py:backup/app.py

# Compare entire directories
reveal diff://src/:backup/src/

# Compare git commits
reveal diff://git://HEAD~1/app.py:git://HEAD/app.py

# Compare branches (pre-merge assessment)
reveal diff://git://main/.:git://feature/.

# Compare specific function across versions
reveal diff://old.py:new.py/process_request

# Check uncommitted changes
reveal 'diff://git://HEAD/src/:src/'
```

**Review Insight**: `diff://` shows **what changed** semantically - added/removed functions, complexity deltas, structural evolution - without line-level noise.

---

### 5. **git://** - Version Control Explorer
Progressive disclosure for git repositories: branches, commits, file history, and **semantic blame** (who wrote this function).

**Codebase Review Usage:**
```bash
# Repository overview
reveal git://.

# Branch history
reveal git://.@main

# File at specific commit
reveal git://src/app.py@v1.0.0

# File commit history (who touched this?)
reveal git://src/app.py?type=history

# Blame summary (key contributors)
reveal git://src/app.py?type=blame

# Semantic blame (who wrote this function?)
reveal git://src/app.py?type=blame&element=load_config
```

**Review Insight**: `git://` reveals **ownership and evolution** - who knows this code, when it changed, and the archaeological context for decisions.

---

### 6. **python://** - Python Runtime Inspector
Diagnose Python environment issues: import shadowing, stale bytecode, package conflicts, virtual environment health.

**Codebase Review Usage:**
```bash
# Automated environment diagnostics
reveal python://doctor

# Check for stale bytecode (silent killer)
reveal python://debug/bytecode

# Detect import shadowing (local module hiding pip package)
reveal python://module/requests

# Analyze sys.path conflicts
reveal python://syspath

# List installed packages
reveal python://packages

# Check specific package installation
reveal python://packages/numpy
```

**Review Insight**: `python://` finds **environment-level bugs** that cause "works on my machine" problems - shadow imports, stale caches, version conflicts.

---

### 7. **json://** - JSON Structure Navigator
Explore JSON schema, navigate nested keys, and flatten for grep-ability (gron-style).

**Codebase Review Usage:**
```bash
# Understand unknown JSON structure
reveal json://config.json?schema

# Navigate to specific key
reveal json://package.json/scripts
reveal json://config.json/database/host

# Flatten for searching
reveal json://large-config.json?flatten | grep -i password

# Array access
reveal json://data.json/users/0
reveal json://data.json/users[0:3]
```

**Review Insight**: `json://` makes **config files reviewable** - understand structure without reading the whole file, find secrets, verify schema compliance.

---

### 8. **markdown://** - Documentation Query System
Query markdown files by front matter fields, extract links, code blocks, and analyze documentation structure.

**Codebase Review Usage:**
```bash
# Query docs by metadata
reveal 'markdown://docs/?tags=architecture'
reveal 'markdown://docs/?status=draft'

# Extract all links (find broken links)
reveal docs/README.md --links

# Extract code examples
reveal docs/GUIDE.md --code --language=python

# Get document structure
reveal docs/ARCHITECTURE.md --outline

# Front matter validation
reveal docs/*.md --validate-schema hugo
```

**Review Insight**: `markdown://` reveals **documentation quality** - broken links, missing metadata, code example accuracy, structural consistency.

---

### 9. **env://** - Environment Variable Inspector
View all environment variables or get specific values.

**Codebase Review Usage:**
```bash
# List all environment variables
reveal env://

# Get specific variable
reveal env://PATH
reveal env://DATABASE_URL

# Compare environments
reveal diff://env://:env://production

# Search for secrets in env
reveal env:// --format=json | jq 'to_entries[] | select(.key | contains("KEY"))'
```

**Review Insight**: `env://` exposes **runtime configuration** - what external dependencies exist, how the app is configured, potential secrets.

---

### 10. **mysql://** - MySQL Database Inspector
Explore MySQL databases: health metrics, connections, InnoDB status, replication, table schemas.

**Codebase Review Usage:**
```bash
# Database overview
reveal mysql://localhost

# Connection pool status
reveal mysql://localhost/connections

# InnoDB health
reveal mysql://localhost/innodb

# Replication status
reveal mysql://localhost/replication

# Table schema
reveal mysql://localhost/users

# Compare database schemas (drift detection)
reveal diff://mysql://prod/users:mysql://staging/users
```

**Review Insight**: `mysql://` reveals **data layer health** - connection issues, schema drift, replication lag, storage problems.

---

### 11. **sqlite://** - SQLite Database Explorer
Zero-dependency SQLite inspection: schema, tables, indexes, statistics.

**Codebase Review Usage:**
```bash
# Database schema overview
reveal sqlite:///path/to/app.db

# Table structure
reveal sqlite:///path/to/app.db/users

# All tables
reveal sqlite:///path/to/app.db --format=json | jq '.tables'
```

**Review Insight**: `sqlite://` makes **embedded databases visible** - schema evolution, data model, index strategy.

---

### 12. **reveal://** - Meta-Review (Dogfooding)
Use reveal to inspect reveal's own codebase - validate config, check completeness, extract implementations.

**Codebase Review Usage:**
```bash
# Self-referential extraction
reveal reveal://adapters/ast.py AstAdapter

# Extract quality rule implementation
reveal reveal://rules/complexity/C901.py detect

# Verify reveal configuration
reveal reveal://config

# Study reveal patterns
reveal 'ast://reveal:?decorator=register_adapter'
```

**Review Insight**: `reveal://` demonstrates **self-documenting architecture** - the tool documents itself, proving its own utility.

---

### 13. **help://** - Self-Documenting Help System
Progressive disclosure documentation: discover adapters, read guides, learn patterns.

**Codebase Review Usage:**
```bash
# What adapters exist?
reveal help://

# How do I use ast://?
reveal help://ast

# Advanced patterns
reveal help://tricks

# Common mistakes
reveal help://anti-patterns

# Full agent guide
reveal help://agent-guide
```

**Review Insight**: `help://` provides **just-in-time learning** - discover capabilities as you need them, not upfront.

---

## Core Review Workflows

### Workflow 1: Initial Codebase Assessment (The 30-Minute Review)

**Goal**: Understand a new codebase's health, structure, and hotspots.

```bash
# Step 1: Structure overview (~1 min)
reveal src/

# Step 2: Overall health metrics (~1 min)
reveal stats://./src

# Step 3: Find problem files (hotspots) (~2 min)
reveal stats://./src --hotspots

# Step 4: Find complex functions (~2 min)
reveal 'ast://./src?complexity>10'

# Step 5: Check for architectural issues (~3 min)
reveal 'imports://src?circular'
reveal 'imports://src?unused'

# Step 6: Run all quality checks (~5 min)
find src/ -name "*.py" | reveal --stdin --check

# Step 7: Git archaeology (who owns what) (~3 min)
reveal git://.

# Step 8: Python environment health (~2 min)
reveal python://doctor

# Step 9: Documentation quality (~2 min)
reveal docs/ --links | grep BROKEN

# Step 10: Config review (~2 min)
reveal json://config.json?schema
reveal env://
```

**Output**: You now know:
- Top 10 problem files (hotspots)
- All functions with complexity >10
- Circular dependencies
- Unused imports
- Quality violations
- Who owns critical modules
- Environment issues
- Documentation gaps
- Config structure

**Token cost (AI review)**: ~5,000 tokens (vs ~500,000 for reading all files)

---

### Workflow 2: Pre-Commit Review (The Quality Gate)

**Goal**: Validate changes before commit - catch complexity increases, new bugs, broken tests.

```bash
# Step 1: What changed?
git diff --name-only | reveal --stdin

# Step 2: Structural changes
git diff --name-only | reveal --stdin --outline

# Step 3: Quality check on changed files
git diff --name-only | grep '\.py$' | reveal --stdin --check

# Step 4: Find new complex functions
git diff --name-only | grep '\.py$' | while read f; do
  reveal "ast://$f?complexity>10"
done

# Step 5: Compare complexity (did we make it worse?)
for file in $(git diff --name-only | grep '\.py$'); do
  reveal "diff://git://HEAD/$file:$file"
done

# Step 6: Check for new unused imports
git diff --name-only | grep '\.py$' | while read f; do
  reveal "imports://$f?unused"
done
```

**Automate with git hook:**
```bash
#!/bin/bash
# .git/hooks/pre-commit

# Run reveal quality gate
git diff --cached --name-only | grep '\.py$' | reveal --stdin --check --select=B,S,C

if [ $? -ne 0 ]; then
  echo "❌ Quality gate failed. Fix issues or use --no-verify to skip."
  exit 1
fi
```

---

### Workflow 3: Pull Request Review (The Merge Decision)

**Goal**: Comprehensive review of branch changes - structural, quality, complexity deltas.

```bash
# Step 1: Branch comparison (high-level)
reveal diff://git://main/.:git://feature/.

# Step 2: List changed files
git diff --name-only origin/main

# Step 3: Structure of changed files
git diff --name-only origin/main | reveal --stdin --outline

# Step 4: Quality gate
git diff --name-only origin/main | grep '\.py$' | reveal --stdin --check

# Step 5: New complex functions
git diff --name-only origin/main | grep '\.py$' | while read f; do
  reveal "ast://$f?complexity>10"
done

# Step 6: Semantic diff (what actually changed?)
for file in $(git diff --name-only origin/main | grep '\.py$'); do
  echo "=== $file ==="
  reveal "diff://git://origin/main/$file:$file"
done

# Step 7: Check for new circular dependencies
reveal 'imports://src?circular'

# Step 8: Blame new functions (who wrote this?)
# (manual: for each new function, reveal git://path?type=blame&element=func_name)

# Step 9: Documentation updated?
git diff --name-only origin/main | grep '\.md$' | reveal --stdin --links
```

**Decision matrix:**
- ✅ **Approve**: No quality violations, complexity stable or decreased, no new cycles, docs updated
- ⚠️ **Request changes**: Quality violations, complexity increased significantly, new cycles
- ❌ **Reject**: Critical bugs (B-series), security issues (S-series), architectural violations

---

### Workflow 4: Refactoring Validation (The Did-We-Improve Check)

**Goal**: Prove that refactoring improved code quality - measure before/after.

```bash
# BEFORE REFACTORING

# Step 1: Baseline metrics
reveal stats://./src --format=json > before.json
reveal app.py --outline > before_structure.txt

# Step 2: Complexity snapshot
reveal 'ast://app.py?type=function' --format=json > before_complexity.json

# Step 3: Quality issues
reveal app.py --check > before_quality.txt

# AFTER REFACTORING

# Step 4: New metrics
reveal stats://./src --format=json > after.json

# Step 5: Compare
reveal diff://git://HEAD~1/app.py:app.py

# Step 6: Analyze improvements
jq -s '.[0].summary.avg_complexity as $old |
       .[1].summary.avg_complexity as $new |
       "Complexity: \($old) → \($new) (Δ: \(($new - $old) * 100 | round / 100))"' \
  before.json after.json

# Step 7: Quality validation
reveal app.py --check

# Step 8: Verify no regressions
reveal 'imports://src?circular'  # Should be same or fewer
reveal 'imports://src?unused'    # Should be same or fewer
```

**Success criteria:**
- Average complexity decreased
- Long functions (>50 lines) decreased
- Deep nesting (>4 levels) decreased
- Quality score increased
- No new circular dependencies
- No new quality violations

---

### Workflow 5: Security Audit (The Vulnerability Scan)

**Goal**: Find security issues, hardcoded secrets, insecure patterns.

```bash
# Step 1: Security-focused quality checks
find src/ -name "*.py" | reveal --stdin --check --select=B,S

# Step 2: Find bare except clauses (B001)
reveal 'ast://src?type=function' --format=json | \
  jq -r '.results[] | select(.code | contains("except:")) |
         "\(.file):\(.line) - \(.name)"'

# Step 3: Find hardcoded credentials (search in code)
# Manual: grep for API_KEY, PASSWORD, SECRET, etc.

# Step 4: Check Docker security
reveal Dockerfile --check --select=S

# Step 5: Check nginx config (N-series rules)
reveal /etc/nginx/nginx.conf --check --select=N

# Step 6: Environment variable audit (check for secrets)
reveal env:// --format=json | \
  jq -r 'to_entries[] | select(.key |
         test("KEY|SECRET|PASSWORD|TOKEN"; "i")) |
         "\(.key)=\(.value)"'

# Step 7: Find insecure HTTP links (U501)
find docs/ -name "*.md" | reveal --stdin --check --select=U

# Step 8: Database security (MySQL)
reveal mysql://localhost/connections  # Check for root logins
```

**Critical findings:**
- B001: Bare except (catches SystemExit)
- B005: Broken imports (supply chain risk)
- S701: Docker :latest tags (non-reproducible builds)
- N002: Missing SSL certificates
- U501: Insecure http:// links
- Hardcoded secrets in env://

---

### Workflow 6: Technical Debt Assessment (The Paydown Plan)

**Goal**: Quantify technical debt and prioritize paydown.

```bash
# Step 1: Identify hotspots (top 10% worst files)
reveal stats://./src --hotspots --format=json > hotspots.json

# Step 2: Find all high-complexity functions
reveal 'ast://./src?complexity>15' --format=json > complex_functions.json

# Step 3: Find all long functions (>100 lines)
reveal 'ast://./src?lines>100' --format=json > long_functions.json

# Step 4: Find god classes (>500 lines)
reveal 'ast://./src?type=class&lines>500' --format=json > god_classes.json

# Step 5: Duplicate function detection (D001)
find src/ -name "*.py" | reveal --stdin --check --select=D

# Step 6: Circular dependency graph
reveal 'imports://src?circular' --format=json > circular_deps.json

# Step 7: Unused code (orphaned files, unused imports)
reveal 'imports://src?unused' --format=json > unused_imports.json

# Step 8: Files too large (M101)
find src/ -name "*.py" | reveal --stdin --check --select=M

# Step 9: Calculate debt score
# Manual: combine metrics into priority matrix
```

**Prioritization matrix:**
1. **P0 (Critical)**: Hotspot score >80, complexity >30, security issues
2. **P1 (High)**: Hotspot score >60, complexity >20, circular deps
3. **P2 (Medium)**: Long functions, god classes, duplicates
4. **P3 (Low)**: Unused imports, line length, minor issues

**Output**: Ranked list of files/functions with effort estimates.

---

### Workflow 7: Documentation Completeness Audit

**Goal**: Ensure documentation exists, is accurate, and is connected.

```bash
# Step 1: Find all markdown files
find docs/ -name "*.md" | reveal --stdin

# Step 2: Check for broken links (L001, L002)
find docs/ -name "*.md" | reveal --stdin --check --select=L

# Step 3: Validate front matter (F-series)
find docs/ -name "*.md" | reveal --stdin --check --select=F

# Step 4: Extract all links for manual review
for f in docs/*.md; do
  echo "=== $f ==="
  reveal "$f" --links
done

# Step 5: Check code examples (extract and validate)
for f in docs/*.md; do
  echo "=== $f ==="
  reveal "$f" --code --language=python > /tmp/examples.py
  python -m py_compile /tmp/examples.py  # Check syntax
done

# Step 6: Cross-reference density (L005)
find docs/ -name "*.md" | reveal --stdin --check --select=L005

# Step 7: Missing index files (L004)
find docs/ -type d | while read dir; do
  if [ ! -f "$dir/index.md" ] && [ ! -f "$dir/README.md" ]; then
    echo "Missing index: $dir"
  fi
done

# Step 8: Related docs graph (visualize connections)
for f in docs/*.md; do
  reveal "$f" --related --related-flat
done
```

**Quality criteria:**
- No broken internal links
- All code examples are syntactically valid
- Front matter present and valid
- Cross-reference density >10%
- Every directory has index
- Related docs create a connected graph

---

### Workflow 8: Onboarding a New Developer (The Guided Tour)

**Goal**: Progressive disclosure walkthrough for new team members.

```bash
# Level 1: Project structure (~5 min)
reveal .

# Level 2: What's the codebase like? (~5 min)
reveal stats://./src
reveal stats://./src --hotspots

# Level 3: Where's the entry point? (~5 min)
reveal 'ast://.?name=main*'
reveal 'ast://.?name=*cli*'

# Level 4: Git archaeology (who owns what) (~10 min)
reveal git://.
reveal git://src/core/engine.py?type=blame

# Level 5: Deep dive on critical module (~15 min)
reveal src/core/engine.py --outline
reveal src/core/engine.py process_request  # Specific function
reveal git://src/core/engine.py?type=blame&element=process_request

# Level 6: Understand dependencies (~10 min)
reveal imports://src
reveal 'imports://src?circular'

# Level 7: Documentation tour (~10 min)
reveal docs/ --links
reveal docs/ARCHITECTURE.md

# Level 8: Environment setup (~5 min)
reveal python://doctor
reveal python://packages
reveal env://
```

**Token cost**: ~10,000 tokens (vs ~1,000,000 for reading all code)

**Learning velocity**: 10-15x faster than traditional code reading.

---

## The Complete Codebase Review Process

### Phase 1: Discovery (Orient)
**Goal**: Understand what exists, where it is, what it does.

```bash
# 1.1 Project structure
reveal .

# 1.2 Codebase stats
reveal stats://./src

# 1.3 Entry points
reveal 'ast://.?name=main*|*cli*|*app*'

# 1.4 Key modules (largest files)
reveal 'ast://./src?type=class' --format=json | \
  jq -r 'sort_by(.line_count) | reverse | .[0:10][]'
```

### Phase 2: Quality Assessment (Navigate)
**Goal**: Find issues, measure health, identify hotspots.

```bash
# 2.1 Hotspots (top 10 problem files)
reveal stats://./src --hotspots

# 2.2 Complexity analysis
reveal 'ast://./src?complexity>10'

# 2.3 Quality checks
find src/ -name "*.py" | reveal --stdin --check

# 2.4 Dependency analysis
reveal 'imports://src?circular'
reveal 'imports://src?unused'
```

### Phase 3: Deep Dive (Focus)
**Goal**: Understand specific modules, functions, and patterns.

```bash
# 3.1 Hotspot deep dive
reveal src/hotspot_file.py --outline
reveal src/hotspot_file.py --check
reveal 'ast://src/hotspot_file.py?complexity>5'

# 3.2 Function-level inspection
reveal src/hotspot_file.py complex_function

# 3.3 Git archaeology
reveal git://src/hotspot_file.py?type=blame&element=complex_function

# 3.4 Semantic diff (how did it get this way?)
reveal git://src/hotspot_file.py?type=history
```

### Phase 4: Action Plan (Execute)
**Goal**: Prioritize fixes, create tickets, assign owners.

```bash
# 4.1 Export findings
reveal stats://./src --hotspots --format=json > review_findings.json
reveal 'ast://./src?complexity>10' --format=json >> review_findings.json

# 4.2 Generate tasks (manual or scripted)
# For each hotspot, create task:
#   - File: hotspot.file
#   - Issue: hotspot.issues
#   - Owner: git blame most recent contributor
#   - Priority: hotspot.hotspot_score

# 4.3 Track progress (re-run stats over time)
reveal stats://./src --format=json > progress_week_1.json
# ... after fixes ...
reveal stats://./src --format=json > progress_week_2.json
```

---

## Advanced Multi-Adapter Patterns

### Pattern 1: The Complexity Drill-Down
**Combine**: `stats://` → `ast://` → `diff://` → `git://`

```bash
# 1. Find hotspots
reveal stats://./src --hotspots

# 2. Identify complex functions in hotspot
reveal 'ast://src/hotspot.py?complexity>10'

# 3. Compare to previous version (did we make it worse?)
reveal diff://git://HEAD~10/src/hotspot.py:src/hotspot.py

# 4. Who wrote the complex function?
reveal git://src/hotspot.py?type=blame&element=complex_function
```

### Pattern 2: The Import Archaeology
**Combine**: `imports://` → `ast://` → `git://`

```bash
# 1. Find circular dependencies
reveal 'imports://src?circular'

# 2. Identify functions involved in cycle
reveal 'ast://src/module_a.py?type=function'
reveal 'ast://src/module_b.py?type=function'

# 3. When was the cycle introduced?
reveal git://src/module_a.py?type=history
reveal git://src/module_b.py?type=history
```

### Pattern 3: The Config Drift Detector
**Combine**: `json://` → `diff://` → `env://`

```bash
# 1. Understand config structure
reveal json://config.json?schema

# 2. Compare environments
reveal diff://json://config.dev.json:json://config.prod.json

# 3. Check environment variables
reveal env://

# 4. Compare env across servers
reveal diff://env://:env://production
```

### Pattern 4: The Security Sweep
**Combine**: `ast://` → `git://` → `env://` → `mysql://`

```bash
# 1. Find bare excepts (B001)
reveal 'ast://src?type=function' | grep -A2 "except:"

# 2. Who wrote this insecure code?
reveal git://src/insecure.py?type=blame&element=bad_function

# 3. Check for secrets in env
reveal env:// | grep -iE 'key|secret|password'

# 4. Check database user privileges
reveal mysql://localhost/connections
```

### Pattern 5: The Documentation Validator
**Combine**: `markdown://` → `ast://` → `diff://`

```bash
# 1. Extract code examples from docs
reveal docs/API.md --code --language=python > /tmp/doc_examples.py

# 2. Verify examples match actual code
reveal 'ast://src/api.py?name=create_user'
# Compare to example manually

# 3. Check for broken links
reveal docs/*.md --links | grep BROKEN

# 4. Verify docs updated with code
for f in $(git diff --name-only HEAD~1 | grep '\.py$'); do
  # Check if corresponding doc was updated
  doc="${f%.py}.md"
  git diff --name-only HEAD~1 | grep -q "$doc" || echo "Doc missing: $doc"
done
```

---

## Quality Gates & Metrics

### Baseline Metrics (Save These)
```bash
# Overall health
reveal stats://./src --format=json > metrics_baseline.json

# Complexity distribution
reveal 'ast://./src?type=function' --format=json > complexity_baseline.json

# Quality issues
find src/ -name "*.py" | reveal --stdin --check --format=json > quality_baseline.json

# Dependency graph
reveal 'imports://src?circular' --format=json > circular_baseline.json
```

### Quality Thresholds (Enforce These)
```yaml
# .reveal.yaml (example quality gates)
thresholds:
  complexity:
    warn: 10
    error: 20
  line_count:
    warn: 50
    error: 100
  quality_score:
    warn: 60
    error: 40
  hotspot_score:
    warn: 60
    error: 80
```

### CI/CD Integration
```bash
#!/bin/bash
# .github/workflows/reveal-quality-gate.yml

# Run quality checks on changed files
git diff --name-only origin/main | grep '\.py$' | reveal --stdin --check --select=B,S,C

# Exit code: 0 = pass, 1 = fail (CI fails build)
exit $?
```

### Metrics Dashboard (Track Over Time)
```bash
# Weekly: capture metrics
reveal stats://./src --format=json > metrics/$(date +%Y-%m-%d).json

# Visualize trends (manual or scripted)
# - Average complexity over time
# - Number of hotspots over time
# - Quality score over time
# - Circular dependencies over time
```

---

## Token-Efficient AI Review Strategies

### Strategy 1: Progressive Disclosure for AI Agents

**Problem**: Reading entire codebases costs millions of tokens.

**Solution**: Use reveal's progressive disclosure to explore in layers.

```bash
# Layer 1: Structure (~100 tokens)
reveal src/

# Layer 2: Stats (~200 tokens)
reveal stats://./src

# Layer 3: Hotspots (~500 tokens)
reveal stats://./src --hotspots

# Layer 4: Specific file outline (~150 tokens)
reveal src/hotspot.py --outline

# Layer 5: Specific function (~50 tokens)
reveal src/hotspot.py complex_function
```

**Token savings**: 5 layers = ~1,000 tokens vs ~500,000 tokens for full read.

**Efficiency**: 500x improvement.

---

### Strategy 2: Query-Driven Exploration

**Pattern**: Ask questions, get precise answers.

```bash
# Question: "What are the most complex functions?"
reveal 'ast://./src?complexity>15' --format=json

# Question: "Are there any circular dependencies?"
reveal 'imports://src?circular'

# Question: "Who wrote this function?"
reveal git://src/app.py?type=blame&element=process

# Question: "What changed between these versions?"
reveal diff://v1.py:v2.py
```

**AI Prompt**: Instead of "Read app.py and tell me about it", use "Run reveal commands to explore app.py progressively."

---

### Strategy 3: Semantic Slicing for Context

**Use `--head`, `--tail`, `--range` for iterative exploration:**

```bash
# First 10 functions (entry points)
reveal app.py --head 10

# Last 5 functions (utilities)
reveal app.py --tail 5

# Specific range (debugging)
reveal conversation.jsonl --range 48-52
```

**Token savings**: Read 10 functions (~500 tokens) vs entire file (~5,000 tokens).

---

### Strategy 4: Format Transformation for Filtering

**Use `--format=json` with `jq` for precise extraction:**

```bash
# Extract only function names
reveal app.py --format=json | jq -r '.structure.functions[].name'

# Extract functions >50 lines
reveal app.py --format=json | \
  jq -r '.structure.functions[] | select(.line_count > 50) | .name'

# Extract complexity distribution
reveal 'ast://src?type=function' --format=json | \
  jq '[.results[].complexity] | group_by(.) |
      map({complexity: .[0], count: length})'
```

**AI Benefit**: AI can generate reveal + jq pipelines dynamically based on questions.

---

### Strategy 5: Multi-Pass Review

**Pass 1**: High-level (stats, hotspots)
**Pass 2**: Medium-level (ast queries, imports)
**Pass 3**: Deep-dive (specific files, functions)
**Pass 4**: Context (git blame, diffs)

**Token budget**: Allocate tokens across passes, not all upfront.

---

## Real-World Review Scenarios

### Scenario 1: M&A Technical Due Diligence

**Context**: Acquiring a company, need to assess codebase quality in 1 week.

**Process**:
```bash
# Day 1: Initial assessment
reveal stats://./src > due_diligence/stats.txt
reveal stats://./src --hotspots > due_diligence/hotspots.txt
reveal 'ast://./src?complexity>20' > due_diligence/complex_functions.txt

# Day 2: Dependency analysis
reveal 'imports://src?circular' > due_diligence/circular_deps.txt
reveal 'imports://src?unused' > due_diligence/unused_imports.txt

# Day 3: Security audit
find src/ -name "*.py" | reveal --stdin --check --select=B,S > due_diligence/security.txt

# Day 4: Database review
reveal mysql://prod > due_diligence/db_health.txt

# Day 5: Documentation audit
find docs/ -name "*.md" | reveal --stdin --check --select=L,F > due_diligence/docs_quality.txt

# Day 6: Git history (team velocity, key contributors)
reveal git://.

# Day 7: Report generation
# Aggregate findings, calculate risk score
```

**Risk score formula:**
- Hotspot count × 10
- Circular deps × 20
- Security issues × 50
- Average complexity × 5
- Quality score penalty: (100 - score) × 2

**Decision**: Acquire if risk score <500, negotiate discount if 500-1000, reject if >1000.

---

### Scenario 2: Legacy System Modernization

**Context**: 10-year-old Python 2.7 codebase, need to migrate to Python 3.11.

**Process**:
```bash
# Step 1: Assess current state
reveal stats://./src
reveal python://doctor  # Check for Python 2.7 patterns

# Step 2: Find Python 2-specific patterns
# (manual: search for print statements, xrange, unicode, etc.)

# Step 3: Identify migration hotspots
reveal stats://./src --hotspots

# Step 4: Create baseline
reveal stats://./src --format=json > migration_baseline.json

# Step 5: Migrate in phases (per hotspot)
# For each hotspot:
#   1. Fix Python 2/3 issues
#   2. Run tests
#   3. Compare: reveal diff://git://HEAD~1/file:file
#   4. Verify no complexity increase

# Step 6: Track progress
reveal stats://./src --format=json > migration_week_1.json
# Compare to baseline weekly

# Step 7: Final validation
reveal python://doctor  # Should be clean
reveal stats://./src    # Complexity should be same or better
find src/ -name "*.py" | reveal --stdin --check  # No new issues
```

**Success criteria**:
- All files migrated
- Average complexity unchanged or decreased
- No new quality issues
- All tests passing

---

### Scenario 3: Open Source Security Audit

**Context**: Auditing a popular OSS library before adopting it.

**Process**:
```bash
# Step 1: Initial scan
reveal stats://./src

# Step 2: Security-focused review
find src/ -name "*.py" | reveal --stdin --check --select=B,S

# Step 3: Check for hardcoded secrets
reveal env:// | grep -iE 'key|secret|token|password'

# Step 4: Dependency analysis (external imports)
reveal imports://src | grep -v "^from \."

# Step 5: Find eval/exec (code injection risk)
grep -r "eval\|exec" src/

# Step 6: Git history (recent security fixes?)
reveal git://.

# Step 7: Check maintainer activity
reveal git://.@main | head -20

# Step 8: Compare to alternatives
# Run same process on competitor libraries
```

**Red flags**:
- B001 (bare except) - hides errors
- B005 (broken imports) - supply chain risk
- Hardcoded secrets
- eval/exec usage
- Inactive maintainers (<1 commit/month)
- High complexity (avg >10)

---

### Scenario 4: Performance Optimization Campaign

**Context**: App is slow, need to find and fix bottlenecks.

**Process**:
```bash
# Step 1: Complexity hotspots (likely slow)
reveal 'ast://./src?complexity>20'

# Step 2: Long functions (likely slow)
reveal 'ast://./src?lines>100'

# Step 3: Nested loops (O(n²) candidates)
# Manual: search for nested for/while

# Step 4: Database queries (N+1 problems)
reveal mysql://localhost/slow_queries

# Step 5: Baseline performance
# Run profiler, save results

# Step 6: Optimize hotspots (one at a time)
# For each complex function:
#   1. Profile
#   2. Optimize
#   3. Compare: reveal diff://old.py:new.py
#   4. Verify complexity decreased
#   5. Benchmark

# Step 7: Track improvements
reveal stats://./src --format=json > perf_after.json
# Compare to baseline
```

**Optimization priorities**:
1. Functions with complexity >30 (algorithmic improvements)
2. Functions with >10 database queries (batching/caching)
3. Functions with nested loops (algorithmic improvements)
4. Functions called in hot path (profiler data)

---

## Quick Reference

### Essential Commands

| Task | Command |
|------|---------|
| **Codebase health** | `reveal stats://./src` |
| **Top 10 problem files** | `reveal stats://./src --hotspots` |
| **Complex functions** | `reveal 'ast://./src?complexity>10'` |
| **Quality check** | `find src/ -name "*.py" \| reveal --stdin --check` |
| **Circular dependencies** | `reveal 'imports://src?circular'` |
| **Unused imports** | `reveal 'imports://src?unused'` |
| **Git overview** | `reveal git://.` |
| **File history** | `reveal git://src/app.py?type=history` |
| **Semantic blame** | `reveal git://src/app.py?type=blame&element=func` |
| **Compare versions** | `reveal diff://old.py:new.py` |
| **Python env health** | `reveal python://doctor` |
| **Config schema** | `reveal json://config.json?schema` |
| **Doc broken links** | `find docs/ -name "*.md" \| reveal --stdin --check --select=L` |
| **Security audit** | `find src/ -name "*.py" \| reveal --stdin --check --select=B,S` |

### Quality Rule Categories

| Code | Category | Examples |
|------|----------|----------|
| **B** | Bugs | B001 (bare except), B002 (@staticmethod+self), B004 (@property no return) |
| **C** | Complexity | C901 (cyclomatic), C902 (length), C905 (nesting) |
| **D** | Duplicates | D001 (duplicate functions) |
| **E** | Errors | E501 (line length) |
| **F** | Front matter | F001-F005 (markdown metadata) |
| **I** | Imports | I001 (unused), I002 (circular), I003 (layer violations), I004 (shadowing) |
| **L** | Links | L001-L005 (broken links, missing index) |
| **M** | Maintainability | M101 (file too large), M102 (orphaned file), M103 (version mismatch) |
| **N** | Nginx | N001-N003 (config issues) |
| **R** | Refactoring | R913 (too many args) |
| **S** | Security | S701 (Docker :latest) |
| **U** | URLs | U501 (insecure http://) |
| **V** | Validation | V001-V007 (schema validation) |

### Adapter Quick Reference

| Adapter | Purpose | Example |
|---------|---------|---------|
| `ast://` | Query code structure | `ast://src?complexity>10` |
| `stats://` | Codebase metrics | `stats://src --hotspots` |
| `imports://` | Dependency analysis | `imports://src?circular` |
| `diff://` | Semantic comparison | `diff://old.py:new.py` |
| `git://` | Version control | `git://src/app.py?type=blame` |
| `python://` | Python env inspector | `python://doctor` |
| `json://` | JSON navigator | `json://config.json?schema` |
| `markdown://` | Doc query system | `markdown://docs?tags=api` |
| `env://` | Environment vars | `env://DATABASE_URL` |
| `mysql://` | MySQL inspector | `mysql://localhost/innodb` |
| `sqlite://` | SQLite explorer | `sqlite:///app.db/users` |
| `reveal://` | Meta-review | `reveal://adapters/ast.py` |
| `help://` | Documentation | `help://tricks` |

---

## Conclusion

Reveal transforms codebase review from a **token-expensive, time-consuming manual process** into a **query-driven, progressive exploration**.

**Key principles:**
1. **Orient → Navigate → Focus**: Structure first, details last
2. **Query, don't read**: Ask specific questions, get precise answers
3. **Multi-adapter synthesis**: Combine adapters for deeper insights
4. **Progressive disclosure**: Reveal information in layers
5. **Token efficiency**: 25-150x fewer tokens than traditional methods

**Next steps:**
1. Run the 30-minute assessment on your codebase
2. Set up pre-commit quality gates
3. Establish baseline metrics
4. Schedule weekly reviews
5. Track improvements over time

**Remember**: The best code review is the one that happens regularly, not the perfect review that never happens.

---

**Questions? Feedback?**
- GitHub: https://github.com/semantic-infrastructure-lab/reveal/issues
- Docs: `reveal help://`
- Tricks: `reveal help://tricks`

---

*Generated by TIA (The Intelligent Agent) | Session: yafimi-0116 | 2026-01-16*
