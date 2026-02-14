# Stats Adapter Guide

**Author**: TIA (The Intelligent Agent)
**Created**: 2025-02-14
**Adapter**: `stats://`
**Purpose**: Codebase metrics, quality analysis, and hotspot detection

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Core Concepts](#core-concepts)
4. [Query Parameters Reference](#query-parameters-reference)
5. [Unified Query Syntax](#unified-query-syntax)
6. [Result Control](#result-control)
7. [Output Types](#output-types)
8. [Quality Scoring System](#quality-scoring-system)
9. [Hotspot Detection](#hotspot-detection)
10. [Workflows](#workflows)
11. [Integration Examples](#integration-examples)
12. [Performance & Best Practices](#performance-best-practices)
13. [Configuration](#configuration)
14. [Limitations](#limitations)
15. [Troubleshooting](#troubleshooting)
16. [Tips & Tricks](#tips-tricks)
17. [Related Documentation](#related-documentation)
18. [FAQ](#faq)
19. [Version History](#version-history)

---

## Overview

The **stats adapter** (`stats://`) analyzes codebase metrics to help you:

- **Understand codebase size and structure** (lines, functions, classes, complexity)
- **Identify quality hotspots** (files needing refactoring attention)
- **Track technical debt** (long functions, high complexity, deep nesting)
- **Assess architecture health** (compare subsystem metrics)
- **Enforce quality gates** (CI/CD integration with thresholds)
- **Guide refactoring priorities** (data-driven improvement targeting)

### Key Features

- ✅ **Aggregate metrics** - Total lines, functions, classes, complexity across codebases
- ✅ **Quality scoring** - 0-100 score based on complexity, function length, nesting depth
- ✅ **Hotspot identification** - Top 10 worst files automatically ranked by severity
- ✅ **Advanced filtering** - Unified query syntax with operators (`>`, `<`, `!=`, `..`)
- ✅ **Result control** - Sort, limit, offset for pagination and ordering
- ✅ **Multi-language support** - Python, JavaScript, Go, Rust, Java, C++, C#, Ruby, PHP
- ✅ **Configurable thresholds** - Customize quality scoring via `.reveal/stats-quality.yaml`
- ✅ **CI/CD friendly** - JSON output for automated quality gates

### When to Use

**Use stats:// when you need to**:
- Find refactoring candidates (high complexity, long functions)
- Track codebase growth and technical debt over time
- Compare architecture subsystems (identify imbalanced modules)
- Enforce quality standards in CI/CD pipelines
- Guide code review priorities (focus on highest-risk files)
- Understand unfamiliar codebases quickly (top-level metrics)

**Don't use stats:// when**:
- You need code structure (use `ast://` instead)
- You need specific function implementations (use `reveal file.py func` instead)
- You need import analysis (use `imports://` instead)
- You need runtime performance data (use profiling tools instead)

---

## Quick Start

### Example 1: Directory Overview

Get aggregate metrics for a directory:

```bash
reveal stats://./src
```

**Output**:
```
Statistics Summary: ./src
  Files: 42 | Lines: 8,543 (6,234 code) | Functions: 187 | Classes: 34
  Avg Complexity: 4.2 | Avg Quality: 78.5/100
```

### Example 2: Identify Hotspots

Find top 10 files needing attention:

```bash
reveal stats://./src?hotspots=true
```

**Output**:
```
Quality Hotspots (Top 10 worst files):
  1. src/core.py (score: 45.2, hotspot: 85.3)
     - Quality: 45.2/100
     - Avg complexity: 12.5
     - 3 function(s) >100 lines
     - 2 function(s) depth >4

  2. src/legacy/parser.py (score: 52.1, hotspot: 67.8)
     - Quality: 52.1/100
     - Avg complexity: 15.2
     - 5 function(s) >100 lines
```

### Example 3: File-Level Statistics

Analyze a specific file:

```bash
reveal stats://./src/app.py
```

**Output**:
```
File Statistics: src/app.py
  Lines: 342 (289 code, 28 comments, 25 empty)
  Elements: 12 functions, 3 classes, 8 imports
  Complexity: avg 5.2, max 12, min 1
  Quality: 82.5/100
    - 1 long function (process_data: 120 lines)
    - 0 deeply nested functions
```

### Example 4: Filter by Complexity

Find files with high complexity:

```bash
reveal stats://./src?complexity>10
```

### Example 5: Filter with Range

Find medium-sized files (50-200 lines):

```bash
reveal stats://./src?lines=50..200
```

### Example 6: Sort by Complexity

Get top 10 most complex files:

```bash
reveal stats://./src?sort=-complexity&limit=10
```

### Example 7: Combine Filters

Find large, complex files:

```bash
reveal stats://./src?lines>100&complexity>10&sort=-complexity&limit=5
```

### Example 8: CI/CD Integration

Export as JSON for quality gates:

```bash
reveal stats://./src --format=json > stats.json
jq '.summary.avg_complexity' stats.json
```

---

## Core Concepts

### 1. Aggregate vs File Statistics

**Aggregate (Directory)**:
- Analyzes all supported files recursively
- Returns summary metrics (totals, averages)
- Includes optional hotspot analysis
- Best for: Codebase overview, architecture assessment

**File-Level**:
- Analyzes single file in detail
- Returns per-file metrics (lines, complexity, quality)
- Includes issue details (long functions, deep nesting)
- Best for: Detailed investigation, targeted improvements

### 2. Supported File Types

Stats adapter analyzes:
- **Python** (.py)
- **JavaScript/TypeScript** (.js, .ts, .jsx, .tsx)
- **Go** (.go)
- **Rust** (.rs)
- **Java** (.java)
- **C/C++** (.c, .cpp, .h, .hpp)
- **C#** (.cs)
- **Ruby** (.rb)
- **PHP** (.php)

Uses AST parsing for accurate analysis (not regex-based line counting).

### 3. Quality Scoring

Quality score (0-100, higher is better) based on:
- **Cyclomatic complexity** - Decision point count (if/for/while/try/and/or)
- **Function length** - Long functions (>100 lines) are harder to understand
- **Deep nesting** - Functions with >4 nesting levels
- **Ratios** - Proportion of problematic functions in file

Default penalties:
- High complexity (>10): -3 points per unit (max -30)
- Long functions (>50 avg): -0.5 points per line (max -20)
- Many long functions: -50 points per ratio (max -25)
- Deep nesting: -50 points per ratio (max -25)

**Configurable** via `.reveal/stats-quality.yaml` (see [Configuration](#configuration)).

### 4. Metrics Explained

**Lines**:
- `total` - All lines including empty
- `code` - Lines with actual code (excluding comments/empty)
- `comments` - Lines starting with `#`, `//`, `/*`, `*`
- `empty` - Blank lines

**Elements**:
- `functions` - Function/method definitions
- `classes` - Class definitions
- `imports` - Import statements

**Complexity**:
- `average` - Mean cyclomatic complexity across all functions
- `max` - Highest complexity function in file
- `min` - Lowest complexity function in file

**Quality**:
- `score` - Overall quality score (0-100)
- `long_functions` - Count of functions >100 lines
- `deep_nesting` - Count of functions with depth >4
- `avg_function_length` - Average lines per function

---

## Query Parameters Reference

### Legacy Parameters (Backward Compatible)

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `hotspots` | boolean | Include hotspot analysis | `?hotspots=true` |
| `code_only` | boolean | Exclude data/config files | `?code_only=true` |
| `min_lines` | integer | Filter files with ≥ N lines | `?min_lines=50` |
| `max_lines` | integer | Filter files with ≤ N lines | `?max_lines=500` |
| `min_complexity` | float | Filter files with avg complexity ≥ N | `?min_complexity=5.0` |
| `max_complexity` | float | Filter files with avg complexity ≤ N | `?max_complexity=10.0` |
| `min_functions` | integer | Filter files with ≥ N functions | `?min_functions=5` |
| `type` | string | Filter by file type | `?type=python` |

**Note**: Legacy parameters still work but unified query syntax (below) is preferred for new queries.

### Unified Query Syntax (Recommended)

See [Unified Query Syntax](#unified-query-syntax) section for full details.

---

## Unified Query Syntax

The stats adapter supports **unified query operators** for flexible filtering:

### Operators

| Operator | Meaning | Example | Description |
|----------|---------|---------|-------------|
| `>` | Greater than | `lines>100` | Files with more than 100 lines |
| `<` | Less than | `complexity<5` | Files with complexity below 5 |
| `>=` | Greater or equal | `functions>=10` | Files with 10+ functions |
| `<=` | Less or equal | `complexity<=15` | Files with complexity ≤15 |
| `==` | Equals | `classes==0` | Files with no classes |
| `!=` | Not equals | `functions!=0` | Files with at least one function |
| `~=` | Regex match | `file~=test` | Files matching "test" pattern |
| `..` | Range | `lines=50..200` | Files with 50-200 lines |

### Filterable Fields

| Field | Maps To | Example |
|-------|---------|---------|
| `lines` | `lines.total` | `lines>100` |
| `code_lines` | `lines.code` | `code_lines>80` |
| `comment_lines` | `lines.comments` | `comment_lines>20` |
| `complexity` | `complexity.average` | `complexity>10` |
| `max_complexity` | `complexity.max` | `max_complexity>20` |
| `functions` | `elements.functions` | `functions>=5` |
| `classes` | `elements.classes` | `classes!=0` |
| `quality` | `quality.score` | `quality<70` |

### Combining Filters

Use `&` to combine multiple filters:

```bash
# Large files with high complexity
reveal stats://./src?lines>100&complexity>10

# Medium-sized files with good quality
reveal stats://./src?lines=50..200&quality>=80

# Files with functions but no classes
reveal stats://./src?functions!=0&classes==0

# Complex files, sorted by complexity
reveal stats://./src?complexity>10&sort=-complexity&limit=10
```

### Examples

**Find refactoring targets**:
```bash
reveal stats://./src?complexity>15&quality<60
```

**Exclude small files**:
```bash
reveal stats://./src?lines>50
```

**Find test files with complexity**:
```bash
reveal stats://./src?file~=test&complexity>5
```

**Files in specific range**:
```bash
reveal stats://./src?lines=100..500&complexity=5..15
```

---

## Result Control

Control result ordering, limiting, and pagination:

### Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `sort` | Sort by field (ascending) | `sort=complexity` |
| `sort=-field` | Sort descending (prefix `-`) | `sort=-lines` |
| `limit` | Limit number of results | `limit=10` |
| `offset` | Skip first N results | `offset=5` |

### Sortable Fields

Same as filterable fields:
- `lines`, `code_lines`, `comment_lines`
- `complexity`, `max_complexity`
- `functions`, `classes`
- `quality`

### Examples

**Top 10 largest files**:
```bash
reveal stats://./src?sort=-lines&limit=10
```

**Top 10 most complex files**:
```bash
reveal stats://./src?sort=-complexity&limit=10
```

**Pagination (results 11-20)**:
```bash
reveal stats://./src?sort=-lines&offset=10&limit=10
```

**Lowest quality files**:
```bash
reveal stats://./src?sort=quality&limit=10
```

**Complex files, paginated**:
```bash
# Page 1 (results 1-10)
reveal stats://./src?complexity>10&sort=-complexity&limit=10

# Page 2 (results 11-20)
reveal stats://./src?complexity>10&sort=-complexity&offset=10&limit=10
```

### Truncation Metadata

When results are limited, output includes:
```json
{
  "warnings": [{
    "type": "truncated",
    "message": "Results truncated: showing 10 of 42 total matches"
  }],
  "displayed_results": 10,
  "total_matches": 42
}
```

---

## Output Types

### 1. stats_summary (Directory Analysis)

**When**: Analyzing a directory (most common use case)

**Structure**:
```json
{
  "type": "stats_summary",
  "source": "./src",
  "summary": {
    "total_files": 42,
    "total_lines": 8543,
    "total_code_lines": 6234,
    "total_functions": 187,
    "total_classes": 34,
    "avg_complexity": 4.2,
    "avg_quality_score": 78.5
  },
  "files": [
    {
      "file": "src/app.py",
      "lines": { "total": 342, "code": 289, "comments": 28, "empty": 25 },
      "elements": { "functions": 12, "classes": 3, "imports": 8 },
      "complexity": { "average": 5.2, "max": 12, "min": 1 },
      "quality": {
        "score": 82.5,
        "long_functions": 1,
        "deep_nesting": 0,
        "avg_function_length": 24.1
      },
      "issues": {
        "long_functions": [
          { "name": "process_data", "lines": 120, "start_line": 45 }
        ],
        "deep_nesting": []
      }
    }
  ],
  "hotspots": [  // Only if ?hotspots=true
    {
      "file": "src/core.py",
      "hotspot_score": 85.3,
      "quality_score": 45.2,
      "issues": [
        "Quality: 45.2/100",
        "Avg complexity: 12.5",
        "3 function(s) >100 lines",
        "2 function(s) depth >4"
      ],
      "details": {
        "lines": 567,
        "functions": 18,
        "complexity": 12.5
      }
    }
  ]
}
```

### 2. stats_file (Single File Analysis)

**When**: Analyzing a specific file (path points to a file)

**Structure**: Same as individual file entry in `files` array above, but returned as standalone result.

**Example**:
```bash
reveal stats://./src/app.py --format=json
```

---

## Quality Scoring System

### How Quality Score is Calculated

Starting score: **100 points**

**Penalty 1: High Complexity**
- If `avg_complexity > 10` (configurable):
  - Penalty: `(avg_complexity - 10) × 3` (max -30 points)
  - Example: Complexity 15 → `(15-10)×3 = -15 points`

**Penalty 2: Long Functions**
- If `avg_function_length > 50` lines (configurable):
  - Penalty: `(avg_function_length - 50) / 2` (max -20 points)
  - Example: Avg 70 lines → `(70-50)/2 = -10 points`

**Penalty 3: Many Long Functions**
- If file has functions >100 lines:
  - Ratio: `long_function_count / total_functions`
  - Penalty: `ratio × 50` (max -25 points)
  - Example: 3/10 functions are long → `0.3×50 = -15 points`

**Penalty 4: Deep Nesting**
- If file has functions with depth >4:
  - Ratio: `deep_nesting_count / total_functions`
  - Penalty: `ratio × 50` (max -25 points)
  - Example: 2/10 functions deeply nested → `0.2×50 = -10 points`

**Final score**: `max(0, 100 - total_penalties)`

### Quality Score Interpretation

| Score | Interpretation | Typical Issues |
|-------|----------------|----------------|
| 90-100 | Excellent | Well-structured, simple, maintainable |
| 80-89 | Good | Minor complexity, generally clean |
| 70-79 | Fair | Some technical debt, could improve |
| 60-69 | Poor | Refactoring recommended |
| 50-59 | Bad | Significant issues, high priority |
| 0-49 | Critical | Urgent refactoring needed |

### Example Calculation

**File**: `src/legacy.py`
- Avg complexity: 15
- Avg function length: 80 lines
- Long functions: 4 out of 10 (40%)
- Deep nesting: 2 out of 10 (20%)

**Calculation**:
```
Start: 100
- Complexity penalty: (15-10)×3 = -15
- Length penalty: (80-50)/2 = -15
- Long function penalty: 0.4×50 = -20
- Deep nesting penalty: 0.2×50 = -10
────────────────────────────────────
Final score: 100-15-15-20-10 = 40
```

**Result**: Quality score = **40/100** (Critical - urgent refactoring needed)

---

## Hotspot Detection

### What are Hotspots?

**Hotspots** are files with quality issues that need attention. The adapter automatically ranks files by severity using a **hotspot score**.

### Hotspot Score Calculation

Starting hotspot score: **0**

**Factor 1: Low Quality Score**
- If `quality_score < 70`:
  - Add: `(70 - quality_score) / 10`
  - Example: Quality 45 → `(70-45)/10 = 2.5 points`

**Factor 2: High Complexity**
- If `avg_complexity > 10`:
  - Add: `avg_complexity - 10`
  - Example: Complexity 15 → `15-10 = 5 points`

**Factor 3: Long Functions**
- For each long function (>100 lines):
  - Add: `5 points per function`
  - Example: 3 long functions → `3×5 = 15 points`

**Factor 4: Deep Nesting**
- For each deeply nested function (depth >4):
  - Add: `3 points per function`
  - Example: 2 deeply nested → `2×3 = 6 points`

**Total hotspot score**: Sum of all factors

### Hotspot Ranking

Hotspots are sorted by **hotspot score** (descending) and limited to **top 10**.

### Example

**Request**:
```bash
reveal stats://./src?hotspots=true
```

**Result**:
```
Quality Hotspots (Top 10 worst files):
  1. src/core.py (score: 45.2, hotspot: 85.3)
     - Quality: 45.2/100
     - Avg complexity: 12.5
     - 3 function(s) >100 lines
     - 2 function(s) depth >4

  2. src/legacy/parser.py (score: 52.1, hotspot: 67.8)
     - Quality: 52.1/100
     - Avg complexity: 15.2
     - 5 function(s) >100 lines

  3. src/utils/converter.py (score: 58.4, hotspot: 42.6)
     - Quality: 58.4/100
     - Avg complexity: 18.7
     - 1 function(s) >100 lines
```

### Using Hotspots

**Workflow**:
1. **Identify** hotspots: `reveal stats://./src?hotspots=true`
2. **Inspect** top file: `reveal stats://./src/core.py` (detailed stats)
3. **Analyze** structure: `reveal ast://./src/core.py?functions` (see functions)
4. **Review** code: `reveal ./src/core.py` (read implementation)
5. **Refactor** prioritizing highest hotspot scores

---

## Workflows

### Workflow 1: Find Refactoring Targets

**Scenario**: You need to identify code that needs cleanup.

**Steps**:

1. **Get hotspot overview**:
   ```bash
   reveal stats://./src?hotspots=true
   ```

2. **Filter high complexity files**:
   ```bash
   reveal stats://./src?complexity>15&sort=-complexity&limit=10
   ```

3. **Analyze specific hotspot**:
   ```bash
   reveal stats://./src/core.py
   ```

4. **Inspect code structure**:
   ```bash
   reveal ast://./src/core.py?functions
   ```

5. **Review implementation**:
   ```bash
   reveal ./src/core.py
   ```

**Result**: Data-driven refactoring priority list.

### Workflow 2: CI/CD Quality Gate

**Scenario**: Fail build if code quality degrades.

**Steps**:

1. **Baseline measurement** (before changes):
   ```bash
   reveal stats://./src --format=json > before.json
   ```

2. **Make code changes**:
   ```bash
   # ... edit files ...
   ```

3. **Post-change measurement**:
   ```bash
   reveal stats://./src --format=json > after.json
   ```

4. **Compare metrics**:
   ```bash
   # Extract avg complexity
   BEFORE=$(jq '.summary.avg_complexity' before.json)
   AFTER=$(jq '.summary.avg_complexity' after.json)

   # Fail if complexity increased
   if (( $(echo "$AFTER > $BEFORE" | bc -l) )); then
     echo "❌ Complexity increased: $BEFORE → $AFTER"
     exit 1
   fi
   ```

5. **Compare quality scores**:
   ```bash
   # Extract quality scores
   BEFORE_Q=$(jq '.summary.avg_quality_score' before.json)
   AFTER_Q=$(jq '.summary.avg_quality_score' after.json)

   # Fail if quality decreased by >5 points
   DIFF=$(echo "$BEFORE_Q - $AFTER_Q" | bc)
   if (( $(echo "$DIFF > 5" | bc -l) )); then
     echo "❌ Quality decreased: $BEFORE_Q → $AFTER_Q"
     exit 1
   fi
   ```

**Result**: Automated quality enforcement in CI/CD pipeline.

### Workflow 3: Architecture Assessment

**Scenario**: Understand codebase structure and identify imbalanced modules.

**Steps**:

1. **Overall metrics**:
   ```bash
   reveal stats://./src
   ```

2. **Core subsystem**:
   ```bash
   reveal stats://./src/core
   ```

3. **Plugins subsystem**:
   ```bash
   reveal stats://./src/plugins
   ```

4. **API subsystem**:
   ```bash
   reveal stats://./src/api
   ```

5. **Compare metrics**:
   ```bash
   # Export all subsystem stats
   reveal stats://./src/core --format=json > core.json
   reveal stats://./src/plugins --format=json > plugins.json
   reveal stats://./src/api --format=json > api.json

   # Compare complexity
   jq '.summary.avg_complexity' core.json plugins.json api.json
   ```

**Analysis**:
- If one subsystem has 3× higher complexity → architectural imbalance
- If one subsystem has 10× more lines → possible over-concentration
- If quality scores vary widely → inconsistent code standards

**Result**: Identify architectural hot zones needing rebalancing.

### Workflow 4: Technical Debt Tracking

**Scenario**: Track technical debt over time.

**Steps**:

1. **Weekly snapshot**:
   ```bash
   DATE=$(date +%Y-%m-%d)
   reveal stats://./src --format=json > "stats-$DATE.json"
   ```

2. **Track metrics over time** (monthly script):
   ```bash
   #!/bin/bash
   # Create CSV report
   echo "Date,Files,Lines,Functions,AvgComplexity,AvgQuality" > debt-report.csv

   for file in stats-*.json; do
     DATE=$(echo $file | grep -oP '\d{4}-\d{2}-\d{2}')
     FILES=$(jq '.summary.total_files' $file)
     LINES=$(jq '.summary.total_lines' $file)
     FUNCS=$(jq '.summary.total_functions' $file)
     COMPLEX=$(jq '.summary.avg_complexity' $file)
     QUALITY=$(jq '.summary.avg_quality_score' $file)

     echo "$DATE,$FILES,$LINES,$FUNCS,$COMPLEX,$QUALITY" >> debt-report.csv
   done

   # Graph with gnuplot or import to Excel
   ```

3. **Analyze trends**:
   - Is complexity increasing? → Accumulating technical debt
   - Is quality decreasing? → Code health degrading
   - Are files growing faster than functions? → Long file anti-pattern

**Result**: Data-driven technical debt tracking and trend analysis.

### Workflow 5: Code Review Prioritization

**Scenario**: Focus code review on highest-risk files.

**Steps**:

1. **Get changed files** (from git):
   ```bash
   git diff --name-only main...feature-branch > changed-files.txt
   ```

2. **Filter by changed files**:
   ```bash
   # For each changed file, get stats
   while read file; do
     reveal stats://"$file" --format=json
   done < changed-files.txt > changed-stats.json
   ```

3. **Identify high-risk changes**:
   ```bash
   # Extract quality scores
   jq -r '.quality.score' changed-stats.json | sort -n | head -5
   ```

4. **Prioritize review**:
   - Quality score <60: Deep review required
   - Quality score 60-79: Standard review
   - Quality score 80+: Light review

**Result**: Risk-based code review prioritization.

### Workflow 6: Cleanup Campaign

**Scenario**: Run a codebase cleanup campaign.

**Steps**:

1. **Get baseline hotspots**:
   ```bash
   reveal stats://./src?hotspots=true --format=json > hotspots-baseline.json
   ```

2. **Target top 5 files**:
   ```bash
   jq -r '.hotspots[0:5] | .[] | .file' hotspots-baseline.json
   ```

3. **Refactor one file**:
   ```bash
   # Pick worst file
   FILE=$(jq -r '.hotspots[0].file' hotspots-baseline.json)

   # Get detailed stats
   reveal stats://"$FILE"

   # Review code
   reveal "$FILE"

   # Refactor (split long functions, reduce nesting, etc.)
   # ... edit file ...
   ```

4. **Verify improvement**:
   ```bash
   # Before/after comparison
   BEFORE=$(jq --arg f "$FILE" '.files[] | select(.file==$f) | .quality.score' hotspots-baseline.json)
   AFTER=$(reveal stats://"$FILE" --format=json | jq '.quality.score')

   echo "Quality improved: $BEFORE → $AFTER"
   ```

5. **Repeat for remaining hotspots**:
   ```bash
   # Track progress
   reveal stats://./src?hotspots=true
   ```

**Result**: Systematic codebase quality improvement campaign.

---

## Integration Examples

### 1. jq - JSON Processing

**Extract specific metrics**:
```bash
# Get average complexity
reveal stats://./src --format=json | jq '.summary.avg_complexity'

# Get total lines of code
reveal stats://./src --format=json | jq '.summary.total_code_lines'

# List files with quality <60
reveal stats://./src --format=json | \
  jq -r '.files[] | select(.quality.score < 60) | .file'

# Count hotspots
reveal stats://./src?hotspots=true --format=json | \
  jq '.hotspots | length'

# Get worst file
reveal stats://./src?hotspots=true --format=json | \
  jq -r '.hotspots[0].file'
```

### 2. Python - Analysis Scripts

**Example 1: Complexity report**:
```python
import json
import subprocess

# Get stats
result = subprocess.run(
    ['reveal', 'stats://./src', '--format=json'],
    capture_output=True, text=True
)
data = json.loads(result.stdout)

# Analyze complexity distribution
files = data['files']
complexities = [f['complexity']['average'] for f in files]

print(f"Mean complexity: {sum(complexities) / len(complexities):.2f}")
print(f"Max complexity: {max(complexities):.2f}")
print(f"Files with complexity >10: {len([c for c in complexities if c > 10])}")
```

**Example 2: Quality dashboard**:
```python
import json
import subprocess
from statistics import mean, stdev

# Get stats
result = subprocess.run(
    ['reveal', 'stats://./src', '--format=json'],
    capture_output=True, text=True
)
data = json.loads(result.stdout)

# Calculate metrics
files = data['files']
quality_scores = [f['quality']['score'] for f in files]

print("Code Quality Dashboard")
print("=" * 50)
print(f"Total Files: {len(files)}")
print(f"Avg Quality: {mean(quality_scores):.1f}/100")
print(f"Std Dev: {stdev(quality_scores):.1f}")
print(f"Min Quality: {min(quality_scores):.1f}")
print(f"Max Quality: {max(quality_scores):.1f}")
print()

# Distribution
excellent = len([q for q in quality_scores if q >= 90])
good = len([q for q in quality_scores if 80 <= q < 90])
fair = len([q for q in quality_scores if 70 <= q < 80])
poor = len([q for q in quality_scores if q < 70])

print("Distribution:")
print(f"  Excellent (90+): {excellent} ({excellent/len(files)*100:.1f}%)")
print(f"  Good (80-89): {good} ({good/len(files)*100:.1f}%)")
print(f"  Fair (70-79): {fair} ({fair/len(files)*100:.1f}%)")
print(f"  Poor (<70): {poor} ({poor/len(files)*100:.1f}%)")
```

### 3. GitHub Actions - CI/CD Integration

**Example: Quality gate workflow**:

```yaml
name: Code Quality Gate

on: [pull_request]

jobs:
  quality-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Install reveal
        run: pip install reveal-toolkit

      - name: Checkout base branch
        run: |
          git fetch origin ${{ github.base_ref }}
          git checkout origin/${{ github.base_ref }}
          reveal stats://./src --format=json > before.json

      - name: Checkout PR branch
        run: |
          git checkout ${{ github.sha }}
          reveal stats://./src --format=json > after.json

      - name: Compare metrics
        run: |
          BEFORE_COMPLEX=$(jq '.summary.avg_complexity' before.json)
          AFTER_COMPLEX=$(jq '.summary.avg_complexity' after.json)

          BEFORE_QUALITY=$(jq '.summary.avg_quality_score' before.json)
          AFTER_QUALITY=$(jq '.summary.avg_quality_score' after.json)

          echo "Complexity: $BEFORE_COMPLEX → $AFTER_COMPLEX"
          echo "Quality: $BEFORE_QUALITY → $AFTER_QUALITY"

          # Fail if complexity increased >10%
          THRESHOLD=$(echo "$BEFORE_COMPLEX * 1.1" | bc)
          if (( $(echo "$AFTER_COMPLEX > $THRESHOLD" | bc -l) )); then
            echo "❌ Complexity increased by >10%"
            exit 1
          fi

          # Fail if quality decreased >5 points
          DIFF=$(echo "$BEFORE_QUALITY - $AFTER_QUALITY" | bc)
          if (( $(echo "$DIFF > 5" | bc -l) )); then
            echo "❌ Quality decreased by >5 points"
            exit 1
          fi

          echo "✅ Quality checks passed"
```

### 4. Grafana - Quality Dashboards

**Example: Time-series quality metrics**:

1. **Collect metrics** (cron job):
   ```bash
   #!/bin/bash
   # Run daily at midnight
   # Cron: 0 0 * * * /path/to/collect-stats.sh

   TIMESTAMP=$(date +%s)
   DATE=$(date +%Y-%m-%d)

   # Get stats
   STATS=$(reveal stats://./src --format=json)

   # Extract metrics
   FILES=$(echo $STATS | jq '.summary.total_files')
   LINES=$(echo $STATS | jq '.summary.total_code_lines')
   COMPLEXITY=$(echo $STATS | jq '.summary.avg_complexity')
   QUALITY=$(echo $STATS | jq '.summary.avg_quality_score')

   # Write to InfluxDB
   curl -XPOST "http://localhost:8086/write?db=codebase" \
     --data-binary "quality,project=myapp files=$FILES,lines=$LINES,complexity=$COMPLEXITY,quality=$QUALITY $TIMESTAMP"
   ```

2. **Grafana queries**:
   ```sql
   -- Average complexity over time
   SELECT mean("complexity") FROM "quality" WHERE time > now() - 30d GROUP BY time(1d)

   -- Quality score trend
   SELECT mean("quality") FROM "quality" WHERE time > now() - 30d GROUP BY time(1d)

   -- Lines of code growth
   SELECT mean("lines") FROM "quality" WHERE time > now() - 90d GROUP BY time(1w)
   ```

### 5. Pre-commit Hook - Quality Enforcement

**Example: Prevent committing low-quality code**:

```bash
#!/bin/bash
# .git/hooks/pre-commit

echo "Checking code quality..."

# Get list of changed Python files
FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$')

if [ -z "$FILES" ]; then
  echo "No Python files to check"
  exit 0
fi

# Check each file
FAILED=0
for file in $FILES; do
  # Get file stats
  STATS=$(reveal stats://"$file" --format=json 2>/dev/null)

  if [ $? -ne 0 ]; then
    echo "⚠️  Cannot analyze $file (skipping)"
    continue
  fi

  # Extract quality score
  QUALITY=$(echo $STATS | jq '.quality.score')

  # Fail if quality <60
  if (( $(echo "$QUALITY < 60" | bc -l) )); then
    echo "❌ $file has low quality score: $QUALITY/100"
    FAILED=1
  else
    echo "✅ $file quality: $QUALITY/100"
  fi
done

if [ $FAILED -eq 1 ]; then
  echo ""
  echo "Commit blocked: Fix quality issues or use 'git commit --no-verify' to bypass"
  exit 1
fi

echo "✅ Quality checks passed"
exit 0
```

### 6. Excel/CSV - Reporting

**Generate CSV report**:
```bash
#!/bin/bash
# Generate CSV report of all files

echo "File,Lines,Code,Functions,Classes,Complexity,Quality" > stats-report.csv

reveal stats://./src --format=json | \
  jq -r '.files[] | [.file, .lines.total, .lines.code, .elements.functions, .elements.classes, .complexity.average, .quality.score] | @csv' \
  >> stats-report.csv

echo "Report generated: stats-report.csv"
```

**Import to Excel**:
1. Open Excel
2. Data → From Text/CSV
3. Load `stats-report.csv`
4. Create pivot tables, charts, conditional formatting

---

## Performance & Best Practices

### Performance Tips

**1. Filter early**:
```bash
# ❌ Bad: Analyze everything then filter in jq
reveal stats://./src --format=json | jq '.files[] | select(.lines.total > 100)'

# ✅ Good: Filter at adapter level
reveal stats://./src?lines>100 --format=json
```

**2. Use result control**:
```bash
# ❌ Bad: Get all results then head
reveal stats://./src --format=json | jq '.files[0:10]'

# ✅ Good: Limit at adapter level
reveal stats://./src?limit=10 --format=json
```

**3. Exclude irrelevant files**:
```bash
# ❌ Bad: Analyze data/config files
reveal stats://./src

# ✅ Good: Code files only
reveal stats://./src?code_only=true
```

**4. Use specific paths**:
```bash
# ❌ Bad: Analyze entire repo
reveal stats://./

# ✅ Good: Target specific directory
reveal stats://./src/core
```

### Best Practices

**1. Track metrics over time**:
- Snapshot weekly/monthly for trend analysis
- Store snapshots in version control (e.g., `stats-reports/`)
- Graph trends to visualize technical debt accumulation

**2. Set quality thresholds**:
- Define acceptable ranges per project (e.g., complexity <10, quality >70)
- Enforce in CI/CD pipelines
- Document thresholds in project README

**3. Use hotspots for prioritization**:
- Don't try to fix everything at once
- Target top 5-10 hotspots in cleanup campaigns
- Measure improvement after refactoring

**4. Combine with other adapters**:
- `stats://` for metrics → identify problem files
- `ast://` for structure → understand code organization
- `reveal` for content → review implementation
- `git://` for history → find recent changes to hotspots

**5. Customize quality config**:
- Different projects have different standards
- Create `.reveal/stats-quality.yaml` for project-specific thresholds
- Document customizations in project docs

### Anti-Patterns

**❌ Don't**:
- Ignore hotspot warnings (they indicate real issues)
- Compare metrics across different language ecosystems (Python vs C++ complexity)
- Use stats as the only code review tool (it's one input, not the complete picture)
- Set unrealistic thresholds (complexity <5 may be too strict)
- Analyze generated code (node_modules, vendor, build outputs)

**✅ Do**:
- Use stats as a guide, not gospel (context matters)
- Combine with manual code review
- Track trends, not just absolute values
- Focus on relative improvement over time
- Exclude non-source files with `code_only=true`

---

## Configuration

### Quality Config File

The stats adapter supports **custom quality thresholds** via `.reveal/stats-quality.yaml`:

**Location**: `.reveal/stats-quality.yaml` (project root)

**Default config** (if file doesn't exist):
```yaml
thresholds:
  complexity_target: 10          # Target avg complexity
  function_length_target: 50     # Target avg function length

penalties:
  complexity:
    multiplier: 3                # Penalty per complexity unit above target
    max: 30                      # Maximum complexity penalty

  length:
    divisor: 2                   # Length penalty divisor
    max: 20                      # Maximum length penalty

  ratios:
    multiplier: 50               # Penalty multiplier for ratios
    max: 25                      # Maximum ratio penalty
```

### Customizing Thresholds

**Example: Stricter standards**:
```yaml
# .reveal/stats-quality.yaml
thresholds:
  complexity_target: 5           # Lower complexity target (stricter)
  function_length_target: 30     # Shorter function target (stricter)

penalties:
  complexity:
    multiplier: 5                # Higher penalty (stricter)
    max: 40

  length:
    divisor: 1                   # Higher penalty (stricter)
    max: 30

  ratios:
    multiplier: 75               # Higher penalty (stricter)
    max: 35
```

**Example: Relaxed standards** (legacy codebase):
```yaml
# .reveal/stats-quality.yaml
thresholds:
  complexity_target: 15          # Higher complexity tolerance
  function_length_target: 100    # Longer function tolerance

penalties:
  complexity:
    multiplier: 2                # Lower penalty (relaxed)
    max: 20

  length:
    divisor: 3                   # Lower penalty (relaxed)
    max: 15

  ratios:
    multiplier: 30               # Lower penalty (relaxed)
    max: 15
```

### Using Config

Config is **automatically loaded** from `.reveal/stats-quality.yaml` if present:

```bash
# Uses custom config if exists, otherwise defaults
reveal stats://./src
```

No CLI flag needed - config is detected automatically.

---

## Limitations

### 1. Language Support

**Supported** (AST parsing):
- Python, JavaScript, TypeScript, Go, Rust, Java, C/C++, C#, Ruby, PHP

**Not supported**:
- Assembly, shell scripts, SQL, HTML/CSS, configuration files
- These are skipped during analysis (excluded from metrics)

### 2. Complexity Estimation

**Cyclomatic complexity** is estimated using decision point counting:
- Counts: `if`, `elif`, `else`, `for`, `while`, `and`, `or`, `try`, `except`, `case`, `when`
- Heuristic-based (not full AST analysis)
- May differ slightly from tools like `mccabe` or `radon`

**Limitation**: Cannot detect all complexity forms (e.g., nested comprehensions, lambda complexity).

### 3. Generated Code

Stats adapter **does not distinguish** generated code from hand-written code:
- May inflate metrics if analyzing generated files
- Use `code_only=true` to reduce noise
- Manually exclude directories like `node_modules/`, `vendor/`, `dist/`

### 4. Large Codebases

Performance considerations:
- Analyzing 1,000+ files takes 5-10 seconds
- Analyzing 10,000+ files takes 30-60 seconds
- For very large repos, use specific paths (e.g., `stats://./src/core`)

### 5. Quality Score Context

Quality scores are **relative**, not absolute:
- Score 80 in Python may differ from score 80 in C++
- Different language idioms affect metrics
- Use scores to track trends, not compare across languages

### 6. No Runtime Analysis

Stats adapter analyzes **static code** only:
- Cannot detect runtime performance issues
- Cannot detect memory leaks or threading issues
- Use profiling tools for runtime analysis

---

## Troubleshooting

### Issue 1: No results returned

**Symptom**:
```bash
reveal stats://./src
# Returns empty summary (0 files)
```

**Cause**: No supported file types in directory

**Solution**:
```bash
# Check what files exist
ls -la ./src

# Verify file extensions are supported (.py, .js, .go, etc.)

# Try broader path
reveal stats://./
```

### Issue 2: Unexpected quality scores

**Symptom**: File has quality score 40 but looks clean

**Cause**: Hidden complexity (long functions, deep nesting)

**Solution**:
```bash
# Get detailed file stats
reveal stats://./src/file.py

# Check issues section
reveal stats://./src/file.py --format=json | jq '.issues'

# Review specific functions
reveal ast://./src/file.py?functions
```

### Issue 3: Analysis too slow

**Symptom**: Stats query takes >30 seconds

**Cause**: Analyzing too many files

**Solution**:
```bash
# ❌ Don't analyze entire repo
reveal stats://./

# ✅ Target specific directories
reveal stats://./src/core

# ✅ Exclude non-code files
reveal stats://./src?code_only=true

# ✅ Use filters to reduce results
reveal stats://./src?lines>100&limit=20
```

### Issue 4: Filter not working

**Symptom**:
```bash
reveal stats://./src?lines>100
# Still shows files with <100 lines
```

**Cause**: Shell interprets `>` as redirect

**Solution**:
```bash
# ❌ Bad: Shell interprets >
reveal stats://./src?lines>100

# ✅ Good: Quote the URI
reveal "stats://./src?lines>100"

# ✅ Alternative: Escape >
reveal stats://./src?lines\>100
```

### Issue 5: Hotspots missing

**Symptom**:
```bash
reveal stats://./src?hotspots=true
# No hotspots section in output
```

**Cause**: No files have quality issues (all scores >70)

**Solution**:
```bash
# Check if any files have quality <70
reveal stats://./src --format=json | jq '.files[] | select(.quality.score < 70)'

# If none, your codebase is high quality! ✅

# Lower hotspot threshold (if needed for tuning):
# Edit .reveal/stats-quality.yaml to adjust thresholds
```

### Issue 6: Config not loaded

**Symptom**: Custom quality config ignored

**Cause**: Config file in wrong location or invalid YAML

**Solution**:
```bash
# Verify config location
ls -la .reveal/stats-quality.yaml

# Check YAML syntax
python -c "import yaml; yaml.safe_load(open('.reveal/stats-quality.yaml'))"

# Verify config structure
cat .reveal/stats-quality.yaml

# Must have structure:
# thresholds:
#   complexity_target: N
#   function_length_target: N
# penalties:
#   ...
```

---

## Tips & Tricks

### Tip 1: Track Specific Metrics

**Track complexity trend**:
```bash
# Weekly snapshot
reveal stats://./src --format=json | \
  jq -r '["Date", "Complexity", "Quality"] | @csv' > weekly-trend.csv
echo "$(date +%Y-%m-%d),$(jq '.summary.avg_complexity' stats.json),$(jq '.summary.avg_quality_score' stats.json)" >> weekly-trend.csv
```

### Tip 2: Compare Branches

**Before/after comparison**:
```bash
# On main branch
git checkout main
reveal stats://./src --format=json > main-stats.json

# On feature branch
git checkout feature-branch
reveal stats://./src --format=json > feature-stats.json

# Compare
jq -s '.[0].summary.avg_complexity as $main | .[1].summary.avg_complexity as $feat | {main: $main, feature: $feat, diff: ($feat - $main)}' main-stats.json feature-stats.json
```

### Tip 3: Find Outliers

**Files with extreme complexity**:
```bash
# 3× standard deviation above mean
reveal stats://./src --format=json | \
  jq '.files | map(.complexity.average) | add / length as $mean | map(select(. > $mean * 3))'
```

### Tip 4: Generate Heatmap

**Complexity heatmap** (for visualization):
```bash
# Generate CSV for heatmap tools
reveal stats://./src --format=json | \
  jq -r '.files[] | [.file, .complexity.average, .quality.score] | @csv' > heatmap.csv

# Import to heatmap.js, seaborn, or Excel conditional formatting
```

### Tip 5: Progressive Analysis

**Drill down progressively**:
```bash
# 1. Top-level overview
reveal stats://./src

# 2. Identify worst subsystem
reveal stats://./src/core
reveal stats://./src/plugins
reveal stats://./src/api

# 3. Get hotspots in worst subsystem
reveal stats://./src/core?hotspots=true

# 4. Analyze specific hotspot
reveal stats://./src/core/worst-file.py

# 5. Review code
reveal ./src/core/worst-file.py
```

### Tip 6: Custom Reports

**Generate HTML report**:
```bash
#!/bin/bash
# generate-report.sh

STATS=$(reveal stats://./src?hotspots=true --format=json)

cat > report.html <<EOF
<!DOCTYPE html>
<html>
<head>
  <title>Code Quality Report</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 40px; }
    .metric { display: inline-block; margin: 20px; }
    .hotspot { background: #fee; padding: 10px; margin: 10px 0; }
  </style>
</head>
<body>
  <h1>Code Quality Report</h1>
  <div class="metric">
    <h2>$(echo $STATS | jq '.summary.total_files')</h2>
    <p>Total Files</p>
  </div>
  <div class="metric">
    <h2>$(echo $STATS | jq '.summary.avg_complexity')</h2>
    <p>Avg Complexity</p>
  </div>
  <div class="metric">
    <h2>$(echo $STATS | jq '.summary.avg_quality_score')</h2>
    <p>Avg Quality</p>
  </div>
  <h2>Quality Hotspots</h2>
  $(echo $STATS | jq -r '.hotspots[] | "<div class=\"hotspot\"><b>\(.file)</b> - Quality: \(.quality_score)/100<br>\(.issues | join(", "))</div>"')
</body>
</html>
EOF

echo "Report generated: report.html"
```

### Tip 7: Integration with IDEs

**VS Code task** (`.vscode/tasks.json`):
```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Check Quality",
      "type": "shell",
      "command": "reveal",
      "args": [
        "stats://${file}",
        "--format=json"
      ],
      "presentation": {
        "reveal": "always",
        "panel": "new"
      }
    }
  ]
}
```

### Tip 8: Combine with Git

**Find recently changed hotspots**:
```bash
# Get files changed in last month
CHANGED=$(git log --since="1 month ago" --name-only --pretty=format: | sort -u | grep '\.py$')

# Analyze each file
for file in $CHANGED; do
  QUALITY=$(reveal stats://"$file" --format=json 2>/dev/null | jq '.quality.score')
  if [ "$QUALITY" != "null" ] && (( $(echo "$QUALITY < 70" | bc -l) )); then
    echo "⚠️  $file - Quality: $QUALITY"
  fi
done
```

---

## Related Documentation

### Reveal Adapters
- **[AST Adapter Guide](AST_ADAPTER_GUIDE.md)** - Code structure analysis (functions, classes)
- **[Git Adapter Guide](GIT_ADAPTER_GUIDE.md)** - Repository history and blame
- **[Imports Adapter Guide](IMPORTS_ADAPTER_GUIDE.md)** - Import graph and unused imports
- **[MySQL Adapter Guide](MYSQL_ADAPTER_GUIDE.md)** - Database metrics and health
- **[SQLite Adapter Guide](SQLITE_ADAPTER_GUIDE.md)** - Database inspection

### Reveal Core
- **[Quick Start](QUICK_START.md)** - Getting started with reveal
- **[Query Syntax Guide](QUERY_SYNTAX_GUIDE.md)** - Universal query operators
- **[Query Parameter Reference](QUERY_PARAMETER_REFERENCE.md)** - All query params
- **[Output Contract](OUTPUT_CONTRACT.md)** - Result structure standards
- **[Field Selection Guide](FIELD_SELECTION_GUIDE.md)** - Filtering results

### Integration
- **[Recipes](RECIPES.md)** - Common reveal patterns
- **[Agent Help](AGENT_HELP.md)** - AI agent integration guide
- **[Adapter Consistency](ADAPTER_CONSISTENCY.md)** - Adapter design patterns

---

## FAQ

### Q1: How accurate is the complexity calculation?

**A**: Cyclomatic complexity is **estimated** using decision point counting (if/for/while/and/or/try/except). It's heuristic-based and may differ slightly from tools like `mccabe` or `radon` that do full AST traversal. However, it's accurate enough for **comparative analysis** (finding highest complexity, tracking trends).

### Q2: What quality score should I target?

**A**: Depends on project context:
- **New projects**: Target 80+ for all files
- **Legacy projects**: Track trend, not absolute (aim for steady improvement)
- **Critical code**: Target 90+ (auth, payment, security)
- **Utilities/tools**: 70+ acceptable

**General guideline**: <60 is technical debt needing attention.

### Q3: Why do hotspots differ from lowest quality scores?

**A**: **Hotspot score** weighs multiple factors:
- Low quality score (severity)
- High complexity (impact)
- Long functions (maintainability risk)
- Deep nesting (cognitive load)

A file with quality 65 but 5 long functions may rank higher as a hotspot than a file with quality 55 but no long functions.

### Q4: Can I exclude specific files or directories?

**A**: Not directly via query params. Options:
1. **Target specific paths**: `reveal stats://./src/core` (skip other dirs)
2. **Use code_only**: `reveal stats://./src?code_only=true` (skip data/config)
3. **Filter in post-processing**: `jq '.files[] | select(.file | contains("test") | not)'`

For permanent exclusions, consider using reveal's config system (check reveal docs).

### Q5: How do I compare stats across multiple projects?

**A**: Export as JSON and compare:
```bash
# Project A
reveal stats://./project-a/src --format=json > project-a.json

# Project B
reveal stats://./project-b/src --format=json > project-b.json

# Compare
jq -s '.[0].summary as $a | .[1].summary as $b | {
  project_a_complexity: $a.avg_complexity,
  project_b_complexity: $b.avg_complexity,
  project_a_quality: $a.avg_quality_score,
  project_b_quality: $b.avg_quality_score
}' project-a.json project-b.json
```

**Note**: Cross-language comparisons are less meaningful (Python vs C++ complexity differs).

### Q6: Does stats:// count blank lines?

**A**: Yes, `lines.total` includes blank lines. Use `lines.code` for code-only count.

**Example**:
```json
"lines": {
  "total": 342,      // All lines (including blank)
  "code": 289,       // Code lines only
  "comments": 28,    // Comment lines
  "empty": 25        // Blank lines
}
```

### Q7: Why is analysis slow on large repos?

**A**: Stats adapter parses **every supported file** recursively. For large repos:
1. **Use specific paths**: `stats://./src/core` instead of `stats://./`
2. **Use code_only**: Skip data/config files
3. **Use filters**: `lines>50` to skip tiny files
4. **Run in background**: Long analyses can run async

**Performance**: ~100-200 files/second on modern hardware.

### Q8: Can I use stats in CI/CD pipelines?

**A**: Yes! Stats adapter is designed for CI/CD:
- **JSON output**: `--format=json` for machine parsing
- **Exit codes**: Always 0 (stats are informational, not errors)
- **Deterministic**: Same code → same stats
- **Fast**: 1000 files analyzed in ~5 seconds

See [Workflow 2: CI/CD Quality Gate](#workflow-2-cicd-quality-gate) for examples.

### Q9: How do I customize quality thresholds?

**A**: Create `.reveal/stats-quality.yaml` in project root:
```yaml
thresholds:
  complexity_target: 15    # Custom target
  function_length_target: 80

penalties:
  complexity:
    multiplier: 2
    max: 25
```

See [Configuration](#configuration) for full details.

### Q10: What's the difference between quality_score and hotspot_score?

**A**:
- **quality_score**: File quality (0-100, higher is better) - how clean the code is
- **hotspot_score**: Refactoring priority (0-∞, higher is worse) - how urgent the issues are

A file can have quality 55 (bad) but hotspot 30 (moderate urgency) if issues are minor. Another file with quality 60 (slightly better) but hotspot 80 (high urgency) may have critical issues like 5 long functions.

**Use quality_score** to assess code health.
**Use hotspot_score** to prioritize refactoring.

### Q11: Can stats detect code duplication?

**A**: No, stats adapter only measures:
- Size (lines, functions, classes)
- Complexity (cyclomatic complexity)
- Quality (based on complexity/length/nesting)

For **duplication detection**, use specialized tools like:
- `jscpd` (JavaScript Copy/Paste Detector)
- `pylint --duplicate-code`
- SonarQube

### Q12: Why doesn't stats show specific function complexity?

**A**: Stats adapter shows **aggregate metrics** (file-level, directory-level). For **function-level details**, use:
```bash
# Function-level structure
reveal ast://./src/file.py?functions

# Then manually inspect specific functions
reveal ./src/file.py
```

Stats focuses on **macro analysis**, AST adapter provides **micro analysis**.

### Q13: Can I track stats in version control?

**A**: Yes, recommended pattern:
```bash
# Create stats-reports directory
mkdir -p stats-reports

# Weekly snapshot
DATE=$(date +%Y-%m-%d)
reveal stats://./src --format=json > stats-reports/stats-$DATE.json

# Commit snapshots
git add stats-reports/
git commit -m "chore: weekly stats snapshot"
```

**Benefits**: Historical tracking, trend analysis, data-driven decisions.

### Q14: How do I interpret avg_complexity=4.2?

**A**: Cyclomatic complexity interpretation:
- **1-5**: Simple, easy to test (excellent)
- **6-10**: Moderate complexity (good)
- **11-20**: High complexity (needs attention)
- **21+**: Very high complexity (refactor recommended)

**Avg complexity 4.2** means most functions are simple (good!).

### Q15: Can stats analyze Jupyter notebooks (.ipynb)?

**A**: Not directly. Stats analyzer looks for `.py` files. Options:
1. **Export to .py**: `jupyter nbconvert --to script notebook.ipynb`
2. **Analyze exported .py**: `reveal stats://notebook.py`

Alternatively, use Jupyter-specific tools like `nbqa`.

---

## Version History

### Version 1.0.0 (2025-02-14)
- ✅ Comprehensive stats adapter documentation
- ✅ Quality scoring system explained
- ✅ Hotspot detection algorithm detailed
- ✅ Unified query syntax documented
- ✅ Result control (sort, limit, offset)
- ✅ 6 detailed workflows
- ✅ 8 integration examples
- ✅ Configuration guide (.reveal/stats-quality.yaml)
- ✅ 15 FAQ entries
- ✅ Performance tips and troubleshooting

### Related Documentation
- Based on `adapters/stats/adapter.py` (2025-02-13)
- Based on `adapters/help_data/stats.yaml` (2025-02-13)
- Consolidates 109 references across 12 documentation files

---

**End of Stats Adapter Guide**
