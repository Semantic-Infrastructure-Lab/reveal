# Git Adapter Guide (git://)

**Adapter**: `git://`
**Purpose**: Git repository inspection with history, blame, and file tracking
**Type**: Repository adapter
**Output Formats**: text, json, grep

## Table of Contents

1. [Quick Start](#quick-start)
2. [URI Syntax](#uri-syntax)
3. [Progressive Disclosure](#progressive-disclosure)
4. [Repository Overview](#repository-overview)
5. [Branch & Tag History](#branch-tag-history)
6. [Commit Inspection](#commit-inspection)
7. [File Operations](#file-operations)
8. [File History](#file-history)
9. [Blame Analysis](#blame-analysis)
10. [Semantic Blame](#semantic-blame)
11. [Query Parameters](#query-parameters)
12. [Commit Filtering](#commit-filtering)
13. [Result Control](#result-control)
14. [Output Types](#output-types)
15. [Workflows](#workflows)
16. [Integration Examples](#integration-examples)
17. [Performance & Best Practices](#performance-best-practices)
18. [Troubleshooting](#troubleshooting)
19. [Limitations](#limitations)
20. [Tips & Best Practices](#tips-best-practices)
21. [Related Documentation](#related-documentation)
22. [FAQ](#faq)

---

## Quick Start

```bash
# 1. Install dependency (if not already installed)
pip install reveal-cli[git]
# OR
pip install pygit2>=1.14.0

# 2. Repository overview (branches, tags, recent commits)
reveal git://.

# 3. Branch history
reveal git://.@main
reveal git://.@develop

# 4. Tag history
reveal git://.@v1.0.0
reveal git://.@latest

# 5. Specific commit
reveal git://.@abc1234

# 6. File at specific ref
reveal git://README.md@main
reveal git://src/app.py@v1.0

# 7. File history (50 most recent commits)
reveal git://src/app.py?type=history

# 8. File blame (who wrote what)
reveal git://src/app.py?type=blame

# 9. Semantic blame (who wrote this function)
reveal git://src/app.py?type=blame&element=load_config

# 10. Filter commits by author
reveal git://.@main?author=John

# 11. Search commit messages
reveal git://.?message~=bug
```

**Why use git://?**
- **Token efficient**: ~200 tokens for repository overview vs 10000+ for `git log` output
- **Progressive disclosure**: Repository → Branch → Commit → File → History/Blame
- **Semantic blame**: Answer "who wrote this function?" not just "who wrote line 42?"
- **Commit filtering**: Query by author, email, message, date range
- **Read-only**: Safe for CI/CD and production repositories

---

## URI Syntax

```
git://<path>[/<subpath>][@<ref>][?<query>]
```

### Components

| Component | Required | Default | Description |
|-----------|----------|---------|-------------|
| `path` | No | `.` (current directory) | Repository path |
| `subpath` | No | (none) | File or directory within repository |
| `ref` | No | `HEAD` | Git reference (commit, branch, tag, HEAD~N) |
| `query` | No | (none) | Query parameters (?type=history, ?author=John) |

### Reference Syntax

Use `@<ref>` to specify Git references:

| Reference | Example | Description |
|-----------|---------|-------------|
| Branch | `@main`, `@develop` | Branch name |
| Tag | `@v1.0.0`, `@latest` | Tag name |
| Commit hash | `@abc1234`, `@abc1234567890abcd` | Full or short hash |
| Relative | `@HEAD~1`, `@HEAD~10` | Relative to HEAD |
| Date | `@HEAD@{2.days.ago}` | Time-based reference |

### Query Syntax

Use `?key=value` for query parameters:

```bash
# Single parameter
git://src/app.py?type=history

# Multiple parameters (& separator)
git://src/app.py?type=blame&detail=full

# Filter with operators
git://.?author=John&message~=bug

# Result control
git://.@main?limit=100&sort=date
```

---

## Progressive Disclosure

The git:// adapter follows a progressive disclosure pattern:

```
Repository Overview
  ↓
Branch/Tag History
  ↓
Commit Details
  ↓
File Contents
  ↓
File History / Blame
```

**Pattern**: Start broad, drill into specifics

```bash
# 1. Start with repository overview
reveal git://.
# Shows: branches (10), tags (10), recent commits (10)

# 2. Drill into specific branch
reveal git://.@main
# Shows: branch commit, history (20 commits)

# 3. Examine specific commit
reveal git://.@abc1234
# Shows: commit details, changed files, diff stats

# 4. View file at that commit
reveal git://src/app.py@abc1234
# Shows: file contents at that point in time

# 5. Trace file history
reveal git://src/app.py?type=history
# Shows: 50 commits that touched this file

# 6. Attribution analysis
reveal git://src/app.py?type=blame
# Shows: who wrote what (contributors + key hunks)
```

---

## Repository Overview

```bash
reveal git://.
reveal git://path/to/repo
```

**Returns** (~200 tokens):

```
Repository: /home/user/projects/myproject
Type: git_repository

HEAD:
  Branch: main
  Commit: abc1234567890abcdef (Mon Feb 13 15:42:30 2025)
  Author: John Doe <john@example.com>
  Message: feat: Add new feature

Branches (10 total, showing 10):
  main - abc1234 (13 hours ago) - feat: Add new feature
  develop - def5678 (2 days ago) - fix: Bug fix
  feature/login - ghi9012 (1 week ago) - wip: Login implementation
  hotfix/security - jkl3456 (2 weeks ago) - security: Patch vulnerability
  (6 more branches...)

Tags (5 total, showing 5):
  v1.2.0 - mno7890 (1 month ago) - Release v1.2.0
  v1.1.0 - pqr1234 (2 months ago) - Release v1.1.0
  v1.0.0 - stu5678 (3 months ago) - Release v1.0.0

Recent Commits (10):
  abc1234 (13 hours ago) - John Doe - feat: Add new feature
  def5678 (2 days ago) - Jane Smith - fix: Bug fix in auth
  ghi9012 (1 week ago) - Bob Jones - docs: Update README
  jkl3456 (2 weeks ago) - Alice Brown - refactor: Code cleanup
  (6 more commits...)

Next Steps:
  reveal git://.@main              # Main branch history
  reveal git://.@v1.2.0            # Tag history
  reveal git://src/app.py?type=history  # File history
  reveal git://src/app.py?type=blame    # File attribution
```

**What you get**:
- **HEAD info**: Current branch, commit, author, message
- **Branches**: 10 most recent (with commit, date, message)
- **Tags**: 10 most recent (with commit, date, message)
- **Recent commits**: 10 most recent across all branches
- **Next steps**: Suggested follow-up commands

**Use cases**:
- Quick repository orientation
- See active branches
- Find latest tags/releases
- Understand recent activity

---

## Branch & Tag History

### Branch History

```bash
reveal git://.@main
reveal git://.@develop
```

**Returns** (~300 tokens):

```
Git Reference: main
Type: git_ref

Commit: abc1234567890abcdef
Author: John Doe <john@example.com>
Date: Mon Feb 13 15:42:30 2025
Message: feat: Add new feature

History (20 commits, showing 20):

  1. abc1234 (13 hours ago) - John Doe
     feat: Add new feature
     Files changed: 3 (+45, -12)

  2. def5678 (2 days ago) - Jane Smith
     fix: Bug fix in auth module
     Files changed: 2 (+8, -3)

  3. ghi9012 (1 week ago) - Bob Jones
     docs: Update README with examples
     Files changed: 1 (+23, -5)

  (17 more commits...)

Next Steps:
  reveal git://.@abc1234            # Specific commit details
  reveal git://.@main?limit=100     # More commits
  reveal git://.@main?author=John   # Filter by author
```

**Query parameters**:
- `?limit=N` - Show N commits (default: 20)
- `?author=Name` - Filter by author name
- `?message~=pattern` - Filter by commit message

### Tag History

```bash
reveal git://.@v1.0.0
reveal git://.@latest
```

**Returns**: Same as branch history, but for commits reachable from tag.

---

## Commit Inspection

```bash
reveal git://.@abc1234
reveal git://.@HEAD~5
```

**Returns** (~400 tokens):

```
Commit: abc1234567890abcdef
Type: git_ref

Details:
  Author: John Doe <john@example.com>
  Date: Mon Feb 13 15:42:30 2025
  Message: feat: Add new feature

           Implemented authentication flow with JWT tokens.
           Added tests and documentation.

  Parents: def5678901234abcdef
  Tree: ghi9012345678abcdef

Changed Files (3):
  src/auth.py - modified (+45, -12)
  tests/test_auth.py - added (+78, -0)
  docs/auth.md - modified (+15, -3)

Stats:
  Total: 3 files changed
  Insertions: +138
  Deletions: -15

Next Steps:
  reveal git://src/auth.py@abc1234      # View file at this commit
  reveal git://src/auth.py?type=history # File history
  reveal git://.@def5678                # Parent commit
```

**What you get**:
- Commit metadata (hash, author, date, message)
- Parent commits (for merges)
- Changed files with diff stats (+/-)
- Total insertions/deletions
- Suggestions for follow-up

---

## File Operations

### View File at Ref

```bash
reveal git://README.md@main
reveal git://src/app.py@v1.0.0
reveal git://config/settings.py@HEAD~5
```

**Returns** (~500-2000 tokens depending on file size):

```
File: src/app.py
Ref: main
Type: git_file

Commit: abc1234567890abcdef
Author: John Doe <john@example.com>
Date: Mon Feb 13 15:42:30 2025

Size: 2,345 bytes
Lines: 89

Content:
────────────────────────────────────────
  1  """Application entry point."""
  2  import os
  3  from flask import Flask
  4
  5  def create_app():
  6      """Create Flask application."""
  7      app = Flask(__name__)
  8      app.config.from_object('config.Config')
  9      return app
 10
 11  if __name__ == '__main__':
 12      app = create_app()
 13      app.run(debug=True)
────────────────────────────────────────

Next Steps:
  reveal git://src/app.py?type=history  # File history
  reveal git://src/app.py?type=blame    # Who wrote what
```

**Use cases**:
- View file at specific tag (e.g., production version)
- Compare file across commits
- Extract historical configuration
- Understand code at specific point in time

---

## File History

```bash
reveal git://src/app.py?type=history
reveal git://README.md?type=history&limit=100
```

**Returns** (~800 tokens for 50 commits):

```
File History: src/app.py
Ref: HEAD
Type: git_file_history

Commits (50 total, showing 50):

  1. abc1234 (13 hours ago) - John Doe
     feat: Add authentication
     +45, -12 lines

  2. def5678 (2 days ago) - Jane Smith
     refactor: Extract config loading
     +23, -8 lines

  3. ghi9012 (1 week ago) - Bob Jones
     fix: Handle edge case in startup
     +5, -2 lines

  4. jkl3456 (2 weeks ago) - Alice Brown
     docs: Add docstrings
     +12, -0 lines

  (46 more commits...)

Summary:
  Total commits: 50
  Contributors: 8
  Lines added: +342
  Lines deleted: -156
  First commit: 6 months ago
  Last commit: 13 hours ago

Next Steps:
  reveal git://src/app.py?type=blame    # Who wrote what
  reveal git://src/app.py@abc1234       # View at specific commit
  reveal git://.@abc1234                # Full commit details
```

**Query parameters**:
- `?limit=N` - Show N commits (default: 50)
- `?author=Name` - Filter by author
- `?message~=pattern` - Filter by message

**Use cases**:
- Understand file evolution
- Find when feature was added
- Identify main contributors
- Track changes over time

---

## Blame Analysis

### Summary Blame (Default)

```bash
reveal git://src/app.py?type=blame
```

**Returns** (~500 tokens):

```
File Blame: src/app.py
Ref: HEAD
Type: git_file_blame

Lines: 89
Contributors: 4

Top Contributors:
  1. John Doe (45 lines, 50.6%) - Last: 13 hours ago
     john@example.com
     Commits: 8

  2. Jane Smith (28 lines, 31.5%) - Last: 2 days ago
     jane@example.com
     Commits: 5

  3. Bob Jones (12 lines, 13.5%) - Last: 1 week ago
     bob@example.com
     Commits: 3

  4. Alice Brown (4 lines, 4.5%) - Last: 2 weeks ago
     alice@example.com
     Commits: 1

Key Hunks (significant changes):

  Lines 1-15 (15 lines) - John Doe - 6 months ago
    abc1234 - Initial implementation
    "Application entry point with basic Flask setup"

  Lines 18-42 (25 lines) - Jane Smith - 2 days ago
    def5678 - Add authentication
    "Implemented JWT token auth with refresh logic"

  Lines 45-68 (24 lines) - John Doe - 13 hours ago
    ghi9012 - Add error handling
    "Comprehensive error handling for all endpoints"

Next Steps:
  reveal git://src/app.py?type=blame&detail=full     # Line-by-line
  reveal git://src/app.py?type=blame&element=create_app  # Semantic blame
  reveal git://src/app.py?type=history                # File history
```

### Detailed Blame (Line-by-Line)

```bash
reveal git://src/app.py?type=blame&detail=full
```

**Returns** (~1500 tokens for 89-line file):

```
File Blame (Detailed): src/app.py
Type: git_file_blame

Lines: 89
Contributors: 4

Line-by-Line Attribution:
────────────────────────────────────────
abc1234 | John Doe | 6 months ago
  1  """Application entry point."""
  2  import os
  3  from flask import Flask
  4

def5678 | Jane Smith | 2 days ago
  5  def create_app():
  6      """Create Flask application."""
  7      app = Flask(__name__)

abc1234 | John Doe | 6 months ago
  8      app.config.from_object('config.Config')
  9      return app
 10

ghi9012 | John Doe | 13 hours ago
 11  if __name__ == '__main__':
 12      app = create_app()
 13      app.run(debug=True)
────────────────────────────────────────

Next Steps:
  reveal git://src/app.py?type=history  # File history
  reveal git://.@abc1234                # Commit details
```

**Use cases**:
- Find who wrote specific lines
- Understand code ownership
- Track when lines were added
- Attribution for documentation

---

## Semantic Blame

**Answer**: "Who wrote this function?" (not just "who wrote line 42?")

```bash
reveal git://src/app.py?type=blame&element=create_app
reveal git://src/auth.py?type=blame&element=AuthHandler
reveal git://models.py?type=blame&element=User.save
```

**Returns** (~300 tokens):

```
Semantic Blame: create_app function
File: src/app.py
Type: git_file_blame

Element: create_app (function)
Lines: 5-9 (5 lines)

Attribution:
  Primary Author: Jane Smith (3 lines, 60%)
    jane@example.com
    Last modified: 2 days ago
    Commit: def5678 - Add authentication

  Contributing Authors:
    John Doe (2 lines, 40%)
      john@example.com
      Last modified: 6 months ago
      Commit: abc1234 - Initial implementation

Code:
────────────────────────────────────────
def5678 | Jane Smith | 2 days ago
  5  def create_app():
  6      """Create Flask application."""
  7      app = Flask(__name__)

abc1234 | John Doe | 6 months ago
  8      app.config.from_object('config.Config')
  9      return app
────────────────────────────────────────

Next Steps:
  reveal git://src/app.py?type=blame&detail=full  # Full file blame
  reveal git://.@def5678                          # Jane's commit
  reveal git://.@abc1234                          # John's commit
```

**How it works**:
- Uses AST analysis to find function/class boundaries
- Attributes lines within that semantic element
- Shows primary author (most lines) + contributors
- Works with Python functions, classes, methods

**Supported elements**:
- ✅ Python functions: `element=function_name`
- ✅ Python classes: `element=ClassName`
- ✅ Python methods: `element=ClassName.method_name`
- ❌ Other languages: Falls back to full file blame

**Use cases**:
- Code review: "Who owns this function?"
- Knowledge transfer: "Who should I ask about this?"
- Documentation: "Who wrote this API?"
- Refactoring: "Who understands this code best?"

---

## Query Parameters

### Operational Parameters

| Parameter | Type | Values | Description |
|-----------|------|--------|-------------|
| `type` | string | `history`, `blame` | Operation type for files |
| `detail` | string | `full`, `summary` | Blame detail level (default: summary) |
| `element` | string | function/class name | Semantic blame target |

### Filter Parameters

| Parameter | Type | Operators | Description |
|-----------|------|-----------|-------------|
| `author` | string | `=`, `~=` | Filter by author name (case-insensitive) |
| `email` | string | `=`, `~=` | Filter by author email |
| `message` | string | `=`, `~=` | Filter by commit message |
| `hash` | string | `=`, `.=` | Filter by commit hash prefix |

### Result Control Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 (refs), 50 (history) | Maximum results |
| `offset` | integer | 0 | Skip N results |
| `sort` | string | `date` | Sort order (date, author, message) |

### Examples

```bash
# File history (default: 50 commits)
reveal git://src/app.py?type=history

# File history (last 100 commits)
reveal git://src/app.py?type=history&limit=100

# Blame summary (default)
reveal git://src/app.py?type=blame

# Blame detailed (line-by-line)
reveal git://src/app.py?type=blame&detail=full

# Semantic blame (specific function)
reveal git://src/app.py?type=blame&element=create_app

# Filter by author
reveal git://.@main?author=John

# Filter by message (regex)
reveal git://.?message~=bug

# Multiple filters (AND logic)
reveal git://.?author=John&message~=fix

# Pagination
reveal git://.@main?limit=50&offset=100
```

---

## Commit Filtering

Filter commits by author, email, message, or hash:

### Author Filtering

```bash
# Exact match (case-insensitive)
reveal git://.?author=John

# Regex match (case-insensitive)
reveal git://.?author~=john

# Multiple authors (OR logic with regex)
reveal git://.?author~=John|Jane

# Branch + author filter
reveal git://.@main?author=John
```

### Email Filtering

```bash
# Exact match
reveal git://.?email=john@example.com

# Domain match (regex)
reveal git://.?email~=@example.com

# Multiple domains
reveal git://.?email~=@(example|test).com
```

### Message Filtering

```bash
# Exact match (case-sensitive)
reveal git://.?message=Initial commit

# Contains (case-insensitive regex)
reveal git://.?message~=bug

# Multiple keywords (OR logic)
reveal git://.?message~=bug|fix|patch

# Complex pattern
reveal git://.?message~=feat.*auth
```

### Hash Filtering

```bash
# Prefix match
reveal git://.?hash=abc123

# Range match (Git's hash range operator)
reveal git://.?hash=abc123..def456
```

### Combining Filters

```bash
# Author AND message (AND logic)
reveal git://.?author=John&message~=bug

# Author AND email domain
reveal git://.?author=John&email~=@example.com

# Complex: author + message + branch
reveal git://.@main?author=John&message~=fix.*auth
```

### Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `=` | Exact match (case-insensitive for author/email) | `author=John` |
| `~=` | Regex match (case-insensitive) | `message~=bug` |
| `!=` | Not equal | `author!=bot` |
| `>` | Greater than (for dates) | `date>2025-01-01` |
| `<` | Less than | `date<2025-02-01` |
| `>=`, `<=` | Greater/less or equal | `date>=2025-01-01` |
| `.=` | Starts with | `hash.=abc` |

---

## Result Control

Control result pagination and sorting:

### Limit

```bash
# Default limits
reveal git://.               # 10 items per category
reveal git://.@main          # 20 commits
reveal git://file?type=history  # 50 commits

# Custom limits
reveal git://.@main?limit=100
reveal git://file?type=history&limit=200
```

### Offset (Pagination)

```bash
# Skip first 50 commits
reveal git://.@main?offset=50

# Page 2 (50 commits per page)
reveal git://.@main?limit=50&offset=50

# Page 3
reveal git://.@main?limit=50&offset=100
```

### Sort

```bash
# Sort by date (default)
reveal git://.@main?sort=date

# Sort by author
reveal git://.@main?sort=author

# Sort by message
reveal git://.@main?sort=message
```

### Combining Result Control

```bash
# Page 2 of John's commits, sorted by date
reveal git://.@main?author=John&limit=50&offset=50&sort=date

# Last 100 bug fixes
reveal git://.?message~=bug&limit=100&sort=date
```

---

## Output Types

### 1. git_repository

**Use case**: Repository overview

**Schema**:
```json
{
  "contract_version": "1.0",
  "type": "git_repository",
  "source": "/home/user/projects/myproject",
  "source_type": "repository",
  "path": "/home/user/projects/myproject",
  "head": {
    "branch": "main",
    "commit": "abc1234567890abcdef",
    "author": "John Doe <john@example.com>",
    "date": "Mon Feb 13 15:42:30 2025",
    "message": "feat: Add new feature"
  },
  "branches": {
    "count": 10,
    "items": [
      {"name": "main", "commit": "abc1234", "date": "13 hours ago", "message": "feat: Add new feature"},
      {"name": "develop", "commit": "def5678", "date": "2 days ago", "message": "fix: Bug fix"}
    ]
  },
  "tags": {
    "count": 5,
    "items": [
      {"name": "v1.2.0", "commit": "mno7890", "date": "1 month ago", "message": "Release v1.2.0"}
    ]
  },
  "commits": {
    "count": 10,
    "items": [
      {"hash": "abc1234", "author": "John Doe", "date": "13 hours ago", "message": "feat: Add new feature"}
    ]
  }
}
```

### 2. git_ref

**Use case**: Branch/tag/commit history

**Schema**:
```json
{
  "contract_version": "1.0",
  "type": "git_ref",
  "source": "main",
  "source_type": "branch",
  "ref": "main",
  "commit": {
    "hash": "abc1234567890abcdef",
    "author": "John Doe <john@example.com>",
    "date": "Mon Feb 13 15:42:30 2025",
    "message": "feat: Add new feature",
    "parents": ["def5678901234abcdef"]
  },
  "history": [
    {"hash": "abc1234", "author": "John Doe", "date": "13 hours ago", "message": "feat: Add new feature", "stats": {"files": 3, "insertions": 45, "deletions": 12}}
  ]
}
```

### 3. git_file

**Use case**: File contents at ref

**Schema**:
```json
{
  "contract_version": "1.0",
  "type": "git_file",
  "source": "src/app.py@main",
  "source_type": "file",
  "path": "src/app.py",
  "ref": "main",
  "commit": "abc1234567890abcdef",
  "size": 2345,
  "lines": 89,
  "content": "\"\"\"Application entry point.\"\"\"\nimport os\n..."
}
```

### 4. git_file_history

**Use case**: File commit history

**Schema**:
```json
{
  "contract_version": "1.0",
  "type": "git_file_history",
  "source": "src/app.py",
  "source_type": "file",
  "path": "src/app.py",
  "ref": "HEAD",
  "count": 50,
  "commits": [
    {"hash": "abc1234", "author": "John Doe", "date": "13 hours ago", "message": "feat: Add authentication", "stats": {"insertions": 45, "deletions": 12}}
  ]
}
```

### 5. git_file_blame

**Use case**: File attribution

**Schema**:
```json
{
  "contract_version": "1.0",
  "type": "git_file_blame",
  "source": "src/app.py",
  "source_type": "file",
  "path": "src/app.py",
  "ref": "HEAD",
  "lines": 89,
  "element": null,
  "contributors": [
    {"name": "John Doe", "email": "john@example.com", "lines": 45, "percentage": 50.6, "commits": 8, "last_commit": "13 hours ago"}
  ],
  "hunks": [
    {"lines": "1-15", "author": "John Doe", "date": "6 months ago", "commit": "abc1234", "message": "Initial implementation"}
  ]
}
```

---

## Workflows

### Workflow 1: Repository Exploration

**Scenario**: Orient yourself in an unfamiliar repository

```bash
# 1. Get repository overview
reveal git://.

# 2. Check main branch activity
reveal git://.@main

# 3. View recent release
reveal git://.@v1.0.0

# 4. Find configuration files
reveal git://config/ @main

# 5. Read main entry point
reveal git://src/main.py@main

# 6. Understand authentication module
reveal git://src/auth.py?type=history

# 7. Find who wrote auth logic
reveal git://src/auth.py?type=blame
```

**Output**: Complete understanding of repository structure, activity, and ownership

---

### Workflow 2: Code Review Preparation

**Scenario**: Review changes before merging feature branch

```bash
# 1. Compare feature branch to main
reveal git://.@feature/login?limit=50

# 2. Filter commits by feature author
reveal git://.@feature/login?author=Jane

# 3. Review specific file changes
reveal git://src/auth.py@feature/login

# 4. Compare with main branch version
reveal git://src/auth.py@main

# 5. Check file history for context
reveal git://src/auth.py?type=history&limit=20

# 6. See who else worked on this file
reveal git://src/auth.py?type=blame
```

**Output**: Full context for code review with history and attribution

---

### Workflow 3: Bug Investigation

**Scenario**: Find when a bug was introduced

```bash
# 1. Search commits mentioning "bug" or "fix"
reveal git://.?message~=bug|fix&limit=100

# 2. Filter by affected file
reveal git://src/payment.py?type=history

# 3. Find suspicious commit
reveal git://.@abc1234

# 4. View file before the change
reveal git://src/payment.py@abc1234~1

# 5. View file after the change
reveal git://src/payment.py@abc1234

# 6. Check who made the change
reveal git://src/payment.py?type=blame&element=process_payment
```

**Output**: Identify bug introduction commit and responsible code

---

### Workflow 4: Knowledge Transfer

**Scenario**: New developer needs to understand codebase ownership

```bash
# 1. Get repository overview (active contributors)
reveal git://.

# 2. Find main contributors to core module
reveal git://src/core/?type=blame

# 3. Identify API expert (most commits in api/)
reveal git://.?author=*&message~=api&limit=100

# 4. Check database expert
reveal git://db/migrations/?type=history

# 5. Create ownership map
reveal git://src/auth.py?type=blame  # Auth expert
reveal git://src/api.py?type=blame   # API expert
reveal git://src/db.py?type=blame    # DB expert
```

**Output**: Map of code ownership and expertise

---

### Workflow 5: Release Notes Generation

**Scenario**: Generate release notes from commits

```bash
# 1. Get all commits since last release
reveal git://.?message~=feat|fix|breaking&limit=200

# 2. Group by type (features, fixes, breaking)
reveal git://.?message~=^feat&limit=100 > features.txt
reveal git://.?message~=^fix&limit=100 > fixes.txt
reveal git://.?message~=^breaking&limit=100 > breaking.txt

# 3. Get commit details
reveal git://.@abc1234

# 4. Extract files changed
reveal git://.@main?limit=100 --format=json | \
  jq '.history[] | {hash, message, files: .stats.files}'
```

**Output**: Structured data for release notes

---

### Workflow 6: Dependency Analysis

**Scenario**: Understand who maintains critical dependencies

```bash
# 1. Find all commits touching requirements.txt
reveal git://requirements.txt?type=history

# 2. Identify dependency updaters
reveal git://requirements.txt?type=blame

# 3. Check for security-related changes
reveal git://requirements.txt?type=history --format=json | \
  jq '.commits[] | select(.message | test("security|cve|vuln"; "i"))'

# 4. Find who last updated specific dependency
reveal git://requirements.txt?type=blame&detail=full | grep "flask=="
```

**Output**: Dependency maintenance history and ownership

---

## Integration Examples

### Integration 1: Combine with jq

```bash
# Extract commit hashes
reveal git://.@main --format=json | \
  jq -r '.history[].hash'

# Find largest commits (by files changed)
reveal git://.@main --format=json | \
  jq '.history | sort_by(.stats.files) | reverse | .[0:10] | .[] | {hash, files: .stats.files, message}'

# Get contributor statistics
reveal git://.@main?limit=1000 --format=json | \
  jq '[.history[] | .author] | group_by(.) | map({author: .[0], commits: length}) | sort_by(.commits) | reverse'

# Find commits with most changes
reveal git://.@main --format=json | \
  jq '.history | sort_by(.stats.insertions + .stats.deletions) | reverse | .[0:5]'
```

### Integration 2: Generate Contribution Report

```bash
#!/bin/bash
# contributor-report.sh - Generate contributor statistics

BRANCH=${1:-main}
LIMIT=${2:-1000}

echo "Analyzing $BRANCH (last $LIMIT commits)..."

# Get commit data
DATA=$(reveal git://.@$BRANCH?limit=$LIMIT --format=json)

# Top contributors
echo "Top Contributors:"
echo "$DATA" | jq -r '
  [.history[] | {author: .author, email: .email}] |
  group_by(.author) |
  map({author: .[0].author, email: .[0].email, commits: length}) |
  sort_by(.commits) | reverse |
  .[] |
  "  \(.commits) commits - \(.author) <\(.email)>"
'

# Commit types (feat, fix, docs, etc.)
echo -e "\nCommit Types:"
echo "$DATA" | jq -r '
  [.history[] | .message | capture("^(?<type>\\w+):") | .type] |
  group_by(.) |
  map({type: .[0], count: length}) |
  sort_by(.count) | reverse |
  .[] |
  "  \(.count) \(.type)"
'

# Activity timeline
echo -e "\nActivity by Month:"
echo "$DATA" | jq -r '
  [.history[] | .date | split(" ")[1,2,4] | join(" ")] |
  group_by(.) |
  map({month: .[0], commits: length}) |
  sort_by(.month) |
  .[] |
  "  \(.month): \(.commits) commits"
'
```

### Integration 3: Find Code Hotspots

```bash
#!/bin/bash
# code-hotspots.sh - Find most-changed files

BRANCH=${1:-main}
LIMIT=${2:-500}

echo "Finding code hotspots on $BRANCH..."

# Get all commits with file changes
reveal git://.@$BRANCH?limit=$LIMIT --format=json | \
  jq -r '
    [.history[] | .changed_files[]? | .path] |
    group_by(.) |
    map({file: .[0], changes: length}) |
    sort_by(.changes) | reverse |
    .[] |
    "\(.changes) changes - \(.file)"
  ' | head -20

echo -e "\nThese files change frequently - potential refactoring targets"
```

### Integration 4: Automated Release Notes

```bash
#!/bin/bash
# release-notes.sh - Generate release notes from commits

LAST_TAG=$(git describe --tags --abbrev=0)
echo "Generating release notes since $LAST_TAG..."

# Features
echo "## Features"
reveal git://.?message~=^feat:&limit=100 --format=json | \
  jq -r '.history[] | "- \(.message | split("\n")[0] | sub("^feat: "; ""))"'

# Fixes
echo -e "\n## Bug Fixes"
reveal git://.?message~=^fix:&limit=100 --format=json | \
  jq -r '.history[] | "- \(.message | split("\n")[0] | sub("^fix: "; ""))"'

# Breaking Changes
echo -e "\n## Breaking Changes"
reveal git://.?message~=BREAKING&limit=100 --format=json | \
  jq -r '.history[] | "- \(.message | split("\n")[0])"'

# Contributors
echo -e "\n## Contributors"
reveal git://.?limit=100 --format=json | \
  jq -r '[.history[] | .author] | unique | .[] | "- \(.)"'
```

### Integration 5: Python Integration

```python
#!/usr/bin/env python3
import subprocess
import json
from datetime import datetime
from collections import Counter

def get_git_data(ref='main', limit=1000):
    """Get git commit data using reveal."""
    result = subprocess.run(
        ['reveal', f'git://.@{ref}?limit={limit}', '--format=json'],
        capture_output=True,
        text=True
    )
    return json.loads(result.stdout)

def analyze_commits(data):
    """Analyze commit patterns."""
    commits = data.get('history', [])

    # Contributor stats
    authors = Counter(c['author'] for c in commits)

    # Commit type stats (from conventional commits)
    types = Counter()
    for commit in commits:
        msg = commit['message']
        if ':' in msg:
            commit_type = msg.split(':')[0].strip()
            types[commit_type] += 1

    # Activity by day of week
    days = Counter()
    for commit in commits:
        # Parse date and get day of week
        # Simplified - would need proper date parsing
        days['weekday'] += 1

    return {
        'total_commits': len(commits),
        'contributors': dict(authors.most_common(10)),
        'commit_types': dict(types.most_common()),
        'first_commit': commits[-1] if commits else None,
        'last_commit': commits[0] if commits else None
    }

if __name__ == '__main__':
    print("Analyzing repository...")
    data = get_git_data('main', limit=1000)
    stats = analyze_commits(data)

    print(f"\nTotal commits: {stats['total_commits']}")
    print("\nTop contributors:")
    for author, count in stats['contributors'].items():
        print(f"  {count:3d} commits - {author}")

    print("\nCommit types:")
    for ctype, count in stats['commit_types'].items():
        print(f"  {count:3d} {ctype}")
```

### Integration 6: CI/CD Integration

```bash
#!/bin/bash
# .github/workflows/commit-checks.sh
# Validate commit messages in CI/CD

set -e

echo "Checking commits since main..."

# Get commits in this PR/branch
COMMITS=$(reveal git://.?limit=50 --format=json)

# Check for conventional commit format
INVALID=$(echo "$COMMITS" | jq -r '
  [.history[] | select(.message | test("^(feat|fix|docs|style|refactor|test|chore):") | not)] |
  .[] |
  "\(.hash): \(.message | split("\n")[0])"
')

if [ -n "$INVALID" ]; then
  echo "❌ Invalid commit messages found:"
  echo "$INVALID"
  echo ""
  echo "Commits must follow Conventional Commits format:"
  echo "  feat: add new feature"
  echo "  fix: correct bug"
  echo "  docs: update documentation"
  exit 1
fi

echo "✅ All commit messages valid"
```

---

## Performance & Best Practices

### Token Efficiency

git:// is optimized for AI agent consumption:

| Operation | git log Output | reveal Output | Savings |
|-----------|---------------|---------------|---------|
| Repository overview | ~10000 tokens | ~200 tokens | **98%** |
| Branch history (20) | ~5000 tokens | ~300 tokens | **94%** |
| File history (50) | ~8000 tokens | ~800 tokens | **90%** |
| Blame summary | ~3000 tokens | ~500 tokens | **83%** |

**Why?**
- ✅ Structured JSON (not unstructured text)
- ✅ Progressive disclosure (overview → details)
- ✅ Semantic summarization (key hunks, not all lines)
- ✅ Token limits built-in (10/20/50 defaults)

### Performance Tips

1. **Use default limits**
   - Repository overview: 10 items per category (adequate for orientation)
   - Branch history: 20 commits (covers ~1-2 weeks typically)
   - File history: 50 commits (covers major changes)

2. **Progressive disclosure**
   ```bash
   # Start broad
   reveal git://.

   # Then specific
   reveal git://.@main

   # Then detailed
   reveal git://src/app.py?type=history
   ```

3. **Use summary blame (default)**
   ```bash
   # Summary: ~500 tokens
   reveal git://src/app.py?type=blame

   # Full: ~1500 tokens (only when needed)
   reveal git://src/app.py?type=blame&detail=full
   ```

4. **Filter early**
   ```bash
   # Without filter: 1000 commits scanned
   reveal git://.@main?limit=1000

   # With filter: Only matching commits scanned
   reveal git://.@main?author=John&limit=100
   ```

5. **Cache repository overview**
   ```python
   # Cache for 5 minutes in monitoring scripts
   cache_key = f"git_overview_{repo_path}"
   if cache_key not in cache or cache_age > 300:
       cache[cache_key] = get_git_overview()
   ```

### Best Practices

1. **Read-only operations**
   - git:// adapter is read-only by design
   - Safe for CI/CD and production analysis
   - No risk of modifying repository

2. **Use semantic blame for functions**
   ```bash
   # Instead of grepping line numbers
   reveal git://src/app.py?type=blame&element=create_app

   # Not: grep -n "def create_app" && reveal git://src/app.py?type=blame&detail=full
   ```

3. **Combine filters for precision**
   ```bash
   # Good: Specific query
   reveal git://.@main?author=John&message~=auth&limit=50

   # Bad: Overly broad
   reveal git://.@main?limit=1000 | grep -i john | grep -i auth
   ```

4. **Use JSON output for parsing**
   ```bash
   # Parse structured data
   reveal git://.@main --format=json | jq '.history[0].hash'

   # Not: parse text output
   reveal git://.@main | awk '/hash:/ {print $2}'
   ```

5. **Leverage progressive disclosure**
   ```bash
   # Don't: Read entire file history for quick check
   reveal git://src/app.py?type=history&limit=1000

   # Do: Start small, expand if needed
   reveal git://src/app.py?type=history  # Default 50
   ```

---

## Troubleshooting

### Error: "pygit2 module not found"

**Problem**: pygit2 dependency not installed

**Solution**:
```bash
# Install with git extras
pip install reveal-cli[git]

# OR install pygit2 directly
pip install pygit2>=1.14.0

# Note: pygit2 has system dependencies (libgit2)
# On Ubuntu/Debian:
sudo apt-get install libgit2-dev

# On macOS:
brew install libgit2
```

### Error: "Not a git repository"

**Problem**: Path is not a Git repository

**Solution**:
```bash
# Check if current directory is a git repo
git status

# If not, initialize or clone
git init
# OR
git clone https://github.com/user/repo.git

# Specify correct path
reveal git://path/to/repo
```

### Error: "Failed to open repository"

**Problem**: Repository is corrupted or inaccessible

**Solution**:
```bash
# Check repository integrity
git fsck

# Fix common issues
git gc

# If corrupted, re-clone
mv repo repo.bak
git clone <url> repo
```

### Error: "Reference not found: @branch"

**Problem**: Branch/tag/commit doesn't exist

**Solution**:
```bash
# List available branches
reveal git://.

# Check branch name
git branch -a

# Use correct ref
reveal git://.@main  # Not master if renamed
```

### Issue: Blame shows wrong function

**Problem**: Semantic blame can't find element

**Solution**:
```bash
# Check function name exactly
grep "def function_name" src/app.py

# Use exact name (case-sensitive)
reveal git://src/app.py?type=blame&element=function_name

# For classes, use ClassName not classname
reveal git://src/models.py?type=blame&element=User

# For methods, use ClassName.method_name
reveal git://src/models.py?type=blame&element=User.save
```

---

## Limitations

1. **Requires pygit2**
   - Not included in base reveal install
   - Has system dependencies (libgit2)
   - Install: `pip install reveal-cli[git]`

2. **Read-only operations**
   - No write operations (by design, for safety)
   - Cannot commit, push, merge, etc.
   - Use git CLI for modifications

3. **Semantic blame: Python only**
   - Semantic blame (`element=`) works with Python files
   - Uses AST to find function/class boundaries
   - Other languages: Falls back to full file blame
   - Future: May support more languages

4. **Performance with large repositories**
   - Very large repos (100k+ commits) can be slow
   - Use filters to reduce scan scope
   - Consider shallow clones for analysis

5. **Binary files**
   - Binary files show metadata only (no content)
   - Use `git show` for binary inspection
   - History and blame work for binary files

6. **Merge commits**
   - Merge commits show multiple parents
   - Diff stats may not reflect actual changes
   - Use `git show <hash>` for merge details

7. **Submodules**
   - Submodules are not recursively inspected
   - Shows submodule commit hash only
   - Inspect submodules separately

---

## Tips & Best Practices

### 1. Start with Overview

```bash
# Always orient yourself first
reveal git://.

# Then drill into specifics
reveal git://.@main
reveal git://src/app.py?type=history
```

### 2. Use Semantic Blame for Code Review

```bash
# Answer "who owns this function?"
reveal git://src/api.py?type=blame&element=handle_request

# Not: "who wrote line 42?"
reveal git://src/api.py?type=blame&detail=full | grep "42:"
```

### 3. Filter for Precision

```bash
# Good: Specific query
reveal git://.?author=John&message~=auth

# Bad: Scan everything, filter later
reveal git://.?limit=10000 | grep john
```

### 4. Use JSON for Scripting

```bash
# Parse structured output
reveal git://.@main --format=json | \
  jq '.history[] | select(.stats.insertions > 100)'
```

### 5. Progressive Blame

```bash
# Start with summary
reveal git://src/app.py?type=blame

# Drill into specific function if needed
reveal git://src/app.py?type=blame&element=create_app

# Full detail only when necessary
reveal git://src/app.py?type=blame&detail=full
```

### 6. Combine with Other Adapters

```bash
# Find complex functions, then blame them
reveal ast://src/**/*.py?complexity>10 --format=json | \
  jq -r '.matches[].path' | while read file; do
    echo "=== $file ==="
    reveal git://$file?type=blame
  done
```

### 7. Cache for Monitoring

```python
# Cache git overview (changes infrequently)
@cache(ttl=300)  # 5 minutes
def get_repo_stats():
    return get_git_data('.')
```

### 8. Use Refs Liberally

```bash
# Compare production vs development
reveal git://config/prod.yaml@production
reveal git://config/prod.yaml@develop

# View code at last release
reveal git://src/app.py@v1.0.0
```

---

## Related Documentation

- **AST Adapter**: `docs/AST_ADAPTER_GUIDE.md` - Code structure analysis (find complex functions)
- **Diff Adapter**: `docs/DIFF_ADAPTER_GUIDE.md` - Compare files/directories across refs
- **Stats Adapter**: `docs/STATS_ADAPTER_GUIDE.md` - Codebase metrics and hotspots
- **Python Adapter**: `docs/PYTHON_ADAPTER_GUIDE.md` - Runtime inspection
- **Reveal Overview**: `README.md` - Full reveal documentation

---

## FAQ

### Q: What Git versions are supported?

**A**: All modern Git versions (2.0+). reveal uses pygit2/libgit2 which supports Git 2.0+ features. Tested with Git 2.30+.

### Q: Can I use this on GitHub/GitLab without cloning?

**A**: No. git:// requires local repository access. Clone first:

```bash
git clone https://github.com/user/repo.git
cd repo
reveal git://.
```

### Q: How do I find who introduced a bug?

**A**:

```bash
# 1. Find commits mentioning "bug" or "fix"
reveal git://.?message~=bug|fix&limit=100

# 2. Check file history
reveal git://src/buggy.py?type=history

# 3. Blame specific function
reveal git://src/buggy.py?type=blame&element=buggy_function

# 4. View commit that changed it
reveal git://.@suspicious_hash
```

### Q: Can I search across all branches?

**A**: No directly. git:// queries one ref at a time. To search all branches:

```bash
# Get branch list
reveal git://. --format=json | jq -r '.branches.items[].name' | \
  while read branch; do
    echo "=== $branch ==="
    reveal git://.@$branch?message~=search_term
  done
```

### Q: How does semantic blame work?

**A**: Uses AST (Abstract Syntax Tree) to find function/class boundaries in Python files:

1. Parses Python file to AST
2. Finds function/class definition
3. Gets line range for that element
4. Runs blame on just those lines
5. Summarizes attribution

**Supported**: Python functions, classes, methods
**Not supported**: Other languages (yet)

### Q: What if pygit2 installation fails?

**A**: pygit2 requires libgit2 system library:

```bash
# Ubuntu/Debian
sudo apt-get install libgit2-dev python3-dev
pip install pygit2

# macOS
brew install libgit2
pip install pygit2

# Verify installation
python -c "import pygit2; print(pygit2.__version__)"
```

### Q: Can I analyze private repositories?

**A**: Yes, if you have local access. reveal works with local clones:

```bash
# Clone private repo with credentials
git clone https://token@github.com/private/repo.git
cd repo
reveal git://.
```

### Q: How do I export data for analysis?

**A**: Use JSON output:

```bash
# Export commit data
reveal git://.@main?limit=1000 --format=json > commits.json

# Analyze with jq, Python, R, etc.
cat commits.json | jq '.history[] | {date, author, message}'
```

### Q: What's the difference between git:// and git log?

**A**:
- **git log**: Unstructured text output, verbose, hard to parse
- **git://**: Structured JSON, token-efficient, designed for AI agents and scripts
- **git://**: Progressive disclosure (overview → details)
- **git://**: Semantic operations (blame function, not line)

### Q: Can I compare two refs?

**A**: Not directly. Use two queries + diff tool:

```bash
# View file at two refs
reveal git://config.yaml@main > main.txt
reveal git://config.yaml@develop > develop.txt
diff main.txt develop.txt

# Or use diff:// adapter
reveal diff://config.yaml@main..develop
```

### Q: How accurate is the blame attribution?

**A**: Very accurate. reveal uses libgit2's blame engine (same as `git blame`). Semantic blame finds the actual function/class boundaries using AST analysis.

### Q: Can I get commit diffs?

**A**: Commit metadata includes diff stats (files changed, +/-, lines). For full diffs:

```bash
# Get diff stats
reveal git://.@abc1234

# For full diff, use git:
git show abc1234
```

### Q: What about merge commits?

**A**: Merge commits show:
- Multiple parents
- Combined diff stats
- Merge message

For detailed merge analysis, use `git show <merge_commit>`.

### Q: How do I find hotspots (frequently changed files)?

**A**:

```bash
# Get commits with file changes
reveal git://.@main?limit=1000 --format=json | \
  jq -r '[.history[].changed_files[]?.path] | group_by(.) | map({file: .[0], changes: length}) | sort_by(.changes) | reverse | .[]'
```

---

## Version History

- **v1.0** (2025-02-14): Initial comprehensive guide
  - All 5 output types documented
  - Progressive disclosure pattern
  - Semantic blame for Python
  - Commit filtering with operators
  - 6 complete workflows
  - Integration examples (jq, Python, CI/CD)
  - Performance optimization tips
  - 107 references consolidated
