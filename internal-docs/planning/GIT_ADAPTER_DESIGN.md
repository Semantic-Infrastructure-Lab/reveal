# git:// Adapter Design Document

**Version:** 1.0.0
**Date:** 2026-01-13
**Status:** Design Document
**Author:** TIA (riholuxi-0113)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Vision & Goals](#vision--goals)
3. [Architecture Overview](#architecture-overview)
4. [Python Git Library Selection](#python-git-library-selection)
5. [URI Syntax & Patterns](#uri-syntax--patterns)
6. [Implementation Specification](#implementation-specification)
7. [Progressive Disclosure Strategy](#progressive-disclosure-strategy)
8. [Integration with Reveal Ecosystem](#integration-with-reveal-ecosystem)
9. [Performance Targets](#performance-targets)
10. [Development Roadmap](#development-roadmap)
11. [Security Considerations](#security-considerations)
12. [Testing Strategy](#testing-strategy)
13. [Documentation & Help](#documentation--help)

---

## Executive Summary

The `git://` adapter brings Git repository inspection into reveal's progressive disclosure framework, enabling developers and AI agents to explore Git history, branches, commits, and file changes with the same token-efficient patterns used across all reveal adapters.

**Core Value Propositions:**
- **Structure-first exploration** of Git repositories (branch tree → commits → file changes)
- **Time-travel queries** for code archaeology (`git://path@commit`)
- **Integration with existing adapters** (`diff://git:file@v1 vs git:file@v2`)
- **AI agent optimization** - 25x token reduction vs raw git commands

**Implementation Strategy:**
- Use **pygit2** (libgit2 bindings) for performance and pure implementation
- Follow reveal's adapter protocol (`ResourceAdapter` base class)
- Ship as optional dependency: `pip install reveal-cli[git]`
- Phased rollout: basic queries (v1.2) → advanced queries (v1.3)

---

## Vision & Goals

### Primary Goals

1. **Enable temporal code exploration** - Navigate repository history as naturally as navigating file structures
2. **Integrate with reveal's ecosystem** - Compose with diff://, ast://, time:// adapters
3. **Support AI agent workflows** - Provide context-efficient output for LLM reasoning
4. **Maintain reveal's UX patterns** - Progressive disclosure, token efficiency, clear breadcrumbs

### Non-Goals (Out of Scope)

- ❌ Replace Git CLI for write operations (commits, pushes, merges)
- ❌ Provide Git GUI functionality
- ❌ Support all Git plumbing commands
- ❌ Repository management (init, clone, remote setup)

**Focus:** Read-only inspection and exploration

---

## Architecture Overview

### Component Structure

```
reveal/
├── adapters/
│   ├── git/
│   │   ├── __init__.py          # Public API
│   │   ├── adapter.py           # GitAdapter class
│   │   ├── repository.py        # Repository introspection
│   │   ├── commit.py            # Commit exploration
│   │   ├── tree.py              # Tree/blob navigation
│   │   ├── diff.py              # Diff generation
│   │   └── help.py              # Help documentation
│   └── base.py                  # ResourceAdapter base
├── rules/
│   └── git/                     # Git-specific quality rules (future)
│       ├── G001.py              # Large files in history
│       ├── G002.py              # Commit message quality
│       └── G003.py              # Branch hygiene
└── rendering/
    └── adapters/
        └── git.py               # Git-specific output formatting
```

### Integration Points

```
git:// adapter
    ↓
├─ Composes with diff:// → diff://git:file@v1 vs git:file@v2
├─ Composes with ast:// → ast://git:path@commit
├─ Composes with time:// → time://git:path@tag
└─ Uses reveal's core:
    ├─ ResourceAdapter protocol
    ├─ Display system (tree format)
    └─ Help system (help://git)
```

---

## Python Git Library Selection

### Evaluation Summary

| Library | GitPython | pygit2 | Dulwich |
|---------|-----------|--------|---------|
| **Implementation** | Wrapper around git CLI | libgit2 bindings (C) | Pure Python |
| **Performance** | Medium (subprocess) | High (native) | Low-Medium |
| **Dependencies** | Requires git binary | libgit2 (C library) | None (pure Python) |
| **License** | BSD-3-Clause | GPLv2 + linking exception | Apache 2.0 or GPLv2+ |
| **API Style** | Pythonic, high-level | Lower-level, comprehensive | Pure Python, portable |
| **Maturity** | Very mature, widely used | Mature, well-maintained | Mature |
| **Install Complexity** | Low | Medium (libgit2 pins) | Low |

### Decision: **pygit2**

**Rationale:**
1. **Performance** - Native C bindings for fast repository inspection
2. **Comprehensive API** - Full access to Git objects (commits, trees, blobs, refs)
3. **No subprocess overhead** - Direct libgit2 calls vs spawning git processes
4. **Widely deployed** - Used by production systems, proven reliability
5. **License compatible** - GPLv2 + linking exception allows our use case

**Trade-offs Accepted:**
- ⚠️ Installation requires libgit2 (manageable via optional dependencies)
- ⚠️ More verbose API than GitPython (but more control)
- ⚠️ Version pinning to libgit2 releases (standard for bindings)

**Fallback Strategy:**
- If libgit2 unavailable, provide helpful error with installation instructions
- Consider Dulwich as fallback in future (pure Python, easier install)
- Ship as optional: `pip install reveal-cli[git]`

### Installation Strategy

```toml
# pyproject.toml
[project.optional-dependencies]
git = [
    "pygit2>=1.14.0",  # Stable version with Python 3.11-3.14 support
]

advanced = [
    "pygit2>=1.14.0",
    "networkx>=3.0",   # For graph analysis
]
```

**User Experience:**
```bash
# User tries git:// without pygit2 installed
$ reveal git://path

⚠️  git:// adapter requires pygit2
Install with: pip install reveal-cli[git]

Alternative: pip install pygit2>=1.14.0
For more info: reveal help://git
```

---

## URI Syntax & Patterns

### Core Syntax

```
git://<path>[/<subpath>][@<ref>][?<query>][#<element>]
```

**Components:**
- `<path>` - Repository path (`.` for current, absolute, or relative)
- `<subpath>` - File/directory within repository (optional)
- `@<ref>` - Git reference: commit hash, branch name, tag (optional, defaults to HEAD)
- `?<query>` - Query parameters for filtering (optional)
- `#<element>` - Specific element (commit, blob) (optional)

### Usage Examples

#### Basic Repository Inspection

```bash
# Repository structure (branches, tags, summary)
reveal git://.

# Specific repository
reveal git:///path/to/repo

# Remote repository (if cloned locally)
reveal git://~/projects/myapp
```

**Output Preview:**
```
Repository: /home/user/projects/myapp
Current Branch: main (3 commits ahead of origin/main)
Status: Clean working tree

Branches (5):
  * main                    → abc1234 "Add feature X" (2 hours ago)
    develop                 → def5678 "Fix bug Y" (1 day ago)
    feature/new-api         → 789abcd "WIP: API refactor" (3 days ago)
    ... 2 more

Tags (12):
    v1.2.0                  → abc1234 (2 weeks ago)
    v1.1.0                  → xyz9876 (1 month ago)
    ... 10 more

Recent Commits (5):
  abc1234  main    Add feature X             (2 hours ago, Alice)
  def5678  main    Fix bug Y                 (1 day ago, Bob)
  ... 3 more

Next:
  reveal git://. --branches     # Detailed branch info
  reveal git://.@main           # Explore main branch
  reveal git://.?since=1w       # Recent activity
```

#### Branch Exploration

```bash
# List all branches with details
reveal git://.?branches

# Specific branch history
reveal git://.@develop

# Branch comparison
reveal diff://git:.@main vs git:.@develop
```

#### Commit Inspection

```bash
# Specific commit
reveal git://.@abc1234

# Commit with full details
reveal git://.@abc1234 --details

# Find commits by author
reveal git://.?author="Alice"

# Find commits by message pattern
reveal git://.?message="fix bug"
```

**Output Preview:**
```
Commit: abc1234def567890
Branch: main
Author: Alice <alice@example.com>
Date: 2026-01-13 14:05:42 -0700

Message:
  Add feature X

  Implements user-requested feature for dashboard analytics.
  Includes tests and documentation updates.

Changes (3 files):
  M  src/dashboard/analytics.py     (+45, -12)
  M  tests/test_analytics.py        (+32, -0)
  A  docs/analytics.md               (+156, -0)

Stats:
  Insertions: +233
  Deletions: -12
  Files changed: 3

Next:
  reveal git://src/dashboard/analytics.py@abc1234   # View file at commit
  reveal diff://git:src@abc1234^ vs git:src@abc1234  # Show changes
```

#### File History

```bash
# File at specific commit
reveal git://src/app.py@abc1234

# File history
reveal git://src/app.py?history

# File blame
reveal git://src/app.py?blame

# Show changes to file
reveal diff://git:src/app.py@v1.0 vs git:src/app.py@v2.0
```

#### Time-Based Queries

```bash
# Commits since date
reveal git://.?since=2026-01-01

# Commits in date range
reveal git://.?since=2026-01-01&until=2026-01-10

# Recent activity
reveal git://.?since=1w  # Last week
reveal git://.?since=3d  # Last 3 days
```

#### Advanced Queries

```bash
# Commits affecting specific files
reveal git://.?path=src/auth/*.py

# Merge commits only
reveal git://.?merges

# Non-merge commits only
reveal git://.?no-merges

# Commits by multiple authors
reveal git://.?author="Alice|Bob"

# Complex query
reveal git://.?since=1m&author="Alice"&path=src/&no-merges
```

---

## Implementation Specification

### Core Classes

#### 1. GitAdapter (Main Entry Point)

```python
# reveal/adapters/git/adapter.py
from reveal.adapters.base import ResourceAdapter, register_adapter
from typing import Dict, Any, Optional
import pygit2

@register_adapter('git')
class GitAdapter(ResourceAdapter):
    """
    Git repository inspection adapter.

    Provides progressive disclosure of Git repository structure:
    - Repository → Branches/Tags → Commits → Files → Diffs

    Examples:
        git://.                    # Repository structure
        git://.@main               # Branch history
        git://.@abc1234            # Specific commit
        git://path/file.py@tag     # File at tag
        git://.?since=1w           # Recent commits
    """

    def __init__(self, path: str = '.', ref: str = None, subpath: str = None):
        """
        Initialize Git adapter.

        Args:
            path: Repository path (default: current directory)
            ref: Git reference (commit, branch, tag)
            subpath: Path within repository (file or directory)
        """
        self.path = path
        self.ref = ref or 'HEAD'
        self.subpath = subpath
        self.repo = None

    def _open_repository(self) -> pygit2.Repository:
        """Open pygit2 repository. Lazy initialization."""
        if self.repo is None:
            try:
                self.repo = pygit2.Repository(pygit2.discover_repository(self.path))
            except pygit2.GitError as e:
                raise ValueError(f"Not a git repository: {self.path}") from e
        return self.repo

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """
        Get repository structure using progressive disclosure.

        Returns different views based on what's specified:
        - No ref: Repository overview (branches, tags, recent commits)
        - With ref: Commit details or file contents
        - With subpath: File history or directory tree
        """
        repo = self._open_repository()

        if self.subpath:
            return self._get_file_structure(repo, **kwargs)
        elif self.ref != 'HEAD':
            return self._get_ref_structure(repo, **kwargs)
        else:
            return self._get_repository_overview(repo, **kwargs)

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Extract specific element (commit, file, branch).

        Args:
            element_name: Name of element (commit hash, branch name, file path)
        """
        repo = self._open_repository()

        # Try as commit
        try:
            commit = repo.revparse_single(element_name)
            return self._format_commit(commit)
        except (KeyError, pygit2.GitError):
            pass

        # Try as file path
        if '/' in element_name or '.' in element_name:
            return self._get_file_at_ref(repo, element_name, self.ref)

        return None

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for git:// adapter."""
        return {
            'name': 'git',
            'description': 'Explore Git repositories with progressive disclosure',
            'syntax': 'git://<path>[/<subpath>][@<ref>][?<query>]',
            'examples': [
                {'uri': 'git://.', 'description': 'Repository overview'},
                {'uri': 'git://.@main', 'description': 'Branch history'},
                {'uri': 'git://.@abc1234', 'description': 'Specific commit'},
                {'uri': 'git://src/app.py@v1.0', 'description': 'File at tag'},
                {'uri': 'git://.?since=1w', 'description': 'Recent commits'},
            ],
            'query_parameters': {
                'since': 'Show commits since date/relative time (e.g., 1w, 2026-01-01)',
                'until': 'Show commits until date',
                'author': 'Filter by author name/email (supports regex)',
                'message': 'Filter by commit message (supports regex)',
                'path': 'Filter by file path',
                'merges': 'Show only merge commits',
                'no-merges': 'Exclude merge commits',
            },
            'notes': [
                'Requires pygit2: pip install reveal-cli[git]',
                'Read-only inspection (no write operations)',
                'Supports all Git references (commit, branch, tag, HEAD~N)',
                'Composes with diff:// and time:// adapters',
            ],
            'see_also': [
                'reveal help://git-guide - Comprehensive guide with examples',
                'reveal help://diff - Compare Git references',
                'reveal diff://git:file@v1 vs git:file@v2 - File comparison',
            ]
        }

    # Private implementation methods

    def _get_repository_overview(self, repo: pygit2.Repository, **kwargs) -> Dict[str, Any]:
        """Generate repository overview structure."""
        return {
            'type': 'repository',
            'path': repo.workdir or repo.path,
            'head': self._get_head_info(repo),
            'branches': self._list_branches(repo),
            'tags': self._list_tags(repo),
            'recent_commits': self._get_recent_commits(repo, limit=5),
            'status': self._get_status(repo),
        }

    def _get_ref_structure(self, repo: pygit2.Repository, **kwargs) -> Dict[str, Any]:
        """Get structure for specific ref (commit/branch/tag)."""
        try:
            commit = repo.revparse_single(self.ref)
            return self._format_commit(commit, detailed=True)
        except (KeyError, pygit2.GitError) as e:
            raise ValueError(f"Invalid ref: {self.ref}") from e

    def _get_file_structure(self, repo: pygit2.Repository, **kwargs) -> Dict[str, Any]:
        """Get structure for specific file/directory."""
        query_type = kwargs.get('query', {}).get('type')

        if query_type == 'history':
            return self._get_file_history(repo, self.subpath)
        elif query_type == 'blame':
            return self._get_file_blame(repo, self.subpath)
        else:
            return self._get_file_at_ref(repo, self.subpath, self.ref)

    def _get_head_info(self, repo: pygit2.Repository) -> Dict[str, Any]:
        """Get HEAD information."""
        if repo.head_is_unborn:
            return {'branch': None, 'commit': None, 'detached': False}

        return {
            'branch': repo.head.shorthand if not repo.head_is_detached else None,
            'commit': str(repo.head.target),
            'detached': repo.head_is_detached,
        }

    def _list_branches(self, repo: pygit2.Repository, limit: int = 10) -> list:
        """List repository branches."""
        branches = []
        for branch in repo.branches.local:
            branch_obj = repo.branches.get(branch)
            commit = repo[branch_obj.target]
            branches.append({
                'name': branch,
                'commit': str(commit.id)[:7],
                'message': commit.message.split('\n')[0],
                'author': commit.author.name,
                'timestamp': commit.commit_time,
            })
        return sorted(branches, key=lambda b: b['timestamp'], reverse=True)[:limit]

    def _list_tags(self, repo: pygit2.Repository, limit: int = 10) -> list:
        """List repository tags."""
        tags = []
        for tag_name in repo.references:
            if tag_name.startswith('refs/tags/'):
                ref = repo.references.get(tag_name)
                target = repo[ref.target]
                tags.append({
                    'name': tag_name.replace('refs/tags/', ''),
                    'commit': str(target.id)[:7],
                    'timestamp': target.commit_time if hasattr(target, 'commit_time') else 0,
                })
        return sorted(tags, key=lambda t: t['timestamp'], reverse=True)[:limit]

    def _get_recent_commits(self, repo: pygit2.Repository, limit: int = 5) -> list:
        """Get recent commits."""
        commits = []
        for commit in repo.walk(repo.head.target, pygit2.GIT_SORT_TIME):
            commits.append({
                'id': str(commit.id)[:7],
                'message': commit.message.split('\n')[0],
                'author': commit.author.name,
                'timestamp': commit.commit_time,
            })
            if len(commits) >= limit:
                break
        return commits

    def _get_status(self, repo: pygit2.Repository) -> Dict[str, Any]:
        """Get working tree status."""
        status = repo.status()
        return {
            'clean': len(status) == 0,
            'modified': [f for f, s in status.items() if s & pygit2.GIT_STATUS_WT_MODIFIED],
            'added': [f for f, s in status.items() if s & pygit2.GIT_STATUS_INDEX_NEW],
            'deleted': [f for f, s in status.items() if s & pygit2.GIT_STATUS_WT_DELETED],
            'untracked': [f for f, s in status.items() if s & pygit2.GIT_STATUS_WT_NEW],
        }

    def _format_commit(self, commit, detailed: bool = False) -> Dict[str, Any]:
        """Format commit information."""
        result = {
            'id': str(commit.id),
            'short_id': str(commit.id)[:7],
            'message': commit.message,
            'author': {
                'name': commit.author.name,
                'email': commit.author.email,
                'time': commit.author.time,
            },
            'committer': {
                'name': commit.committer.name,
                'email': commit.committer.email,
                'time': commit.committer.time,
            },
        }

        if detailed:
            result['parents'] = [str(p.id) for p in commit.parents]
            result['tree'] = str(commit.tree_id)
            # Add diff information
            if commit.parents:
                parent = commit.parents[0]
                diff = parent.tree.diff_to_tree(commit.tree)
                result['changes'] = self._format_diff_stats(diff)

        return result

    def _format_diff_stats(self, diff) -> Dict[str, Any]:
        """Format diff statistics."""
        stats = diff.stats
        return {
            'files_changed': stats.files_changed,
            'insertions': stats.insertions,
            'deletions': stats.deletions,
            'files': [
                {
                    'path': delta.new_file.path,
                    'status': delta.status_char(),
                    'additions': patch.line_stats[1] if hasattr(patch, 'line_stats') else 0,
                    'deletions': patch.line_stats[2] if hasattr(patch, 'line_stats') else 0,
                }
                for patch in diff
                for delta in [patch.delta]
            ]
        }

    def _get_file_at_ref(self, repo: pygit2.Repository, path: str, ref: str) -> Dict[str, Any]:
        """Get file contents at specific ref."""
        commit = repo.revparse_single(ref)
        try:
            entry = commit.tree[path]
            blob = repo[entry.id]
            return {
                'type': 'file',
                'path': path,
                'ref': ref,
                'commit': str(commit.id)[:7],
                'size': blob.size,
                'content': blob.data.decode('utf-8', errors='replace'),
                'is_binary': blob.is_binary,
            }
        except KeyError:
            raise ValueError(f"File not found: {path} at {ref}")

    def _get_file_history(self, repo: pygit2.Repository, path: str) -> Dict[str, Any]:
        """Get file commit history."""
        commits = []
        for commit in repo.walk(repo.head.target, pygit2.GIT_SORT_TIME):
            if path in commit.tree:
                commits.append({
                    'id': str(commit.id)[:7],
                    'message': commit.message.split('\n')[0],
                    'author': commit.author.name,
                    'timestamp': commit.commit_time,
                })

        return {
            'type': 'file_history',
            'path': path,
            'commits': commits,
        }

    def _get_file_blame(self, repo: pygit2.Repository, path: str) -> Dict[str, Any]:
        """Get file blame information."""
        # Placeholder - pygit2 blame support
        return {
            'type': 'blame',
            'path': path,
            'lines': [],  # TODO: Implement blame
        }
```

---

## Progressive Disclosure Strategy

### Level 1: Repository Overview (Default)

**Command:** `reveal git://.`

**Output Preview:**
```
Repository: /home/user/project
Branch: main (3 commits ahead)
Status: Clean

Branches (5): main*, develop, feature/x, ...
Tags (12): v1.2.0, v1.1.0, ...
Recent (5 commits):
  abc1234  Add feature X  (2h ago)
  def5678  Fix bug Y      (1d ago)
  ...

Next: reveal git://.@main  # Explore branch
```

**Token Count:** ~250 tokens (vs 2000+ for raw `git log`)

### Level 2: Branch/Commit Exploration

**Command:** `reveal git://.@main`

**Output Preview:**
```
Branch: main
Commit: abc1234 "Add feature X"
Author: Alice (2h ago)

Changes (3 files):
  M src/dashboard/analytics.py  (+45, -12)
  M tests/test_analytics.py     (+32)
  A docs/analytics.md            (+156)

Next: reveal git://src/dashboard/analytics.py@abc1234
```

**Token Count:** ~300 tokens

### Level 3: File Inspection

**Command:** `reveal git://src/app.py@abc1234`

**Output Preview:**
```
File: src/app.py at abc1234
Size: 4.2KB (123 lines)

[Full file content shown]

Next:
  reveal git://src/app.py?history  # File commits
  reveal diff://git:src/app.py@abc1234^ vs git:src/app.py@abc1234
```

**Token Count:** Variable (file content + ~100 overhead)

---

## Integration with Reveal Ecosystem

### 1. Compose with diff:// Adapter

```bash
# Compare file across commits
reveal diff://git:src/app.py@v1.0 vs git:src/app.py@v2.0

# Compare branches
reveal diff://git:.@main vs git:.@develop

# Compare working tree to commit
reveal diff://src/app.py vs git:src/app.py@HEAD
```

**Implementation:**
- diff:// adapter already handles URI-based resources
- git:// returns file content at specified ref
- diff:// generates structural diff

### 2. Compose with ast:// Adapter

```bash
# AST of file at specific commit
reveal ast://git:src/app.py@abc1234

# Find complex functions in old version
reveal ast://git:src/@v1.0?complexity>10
```

**Implementation:**
- ast:// reads file content via git:// adapter
- Parses and analyzes historical code state
- Enables "code archaeology" queries

### 3. Compose with time:// Adapter (Future)

```bash
# File as it was 1 week ago
reveal time://git:src/app.py@1w-ago

# Repository state 3 months ago
reveal time://git:.@3m-ago
```

### 4. Enhanced --check Integration

```bash
# Check file at commit for issues
reveal git://src/app.py@abc1234 --check

# Check historical code quality
reveal git://src/@v1.0 --check --select C901,C902
```

---

## Performance Targets

### Structure Queries

| Operation | Target | Rationale |
|-----------|--------|-----------|
| Repository overview | <100ms | Branch/tag listing |
| Commit details | <50ms | Single commit lookup |
| File at ref | <200ms | Blob retrieval + decode |
| Recent commits (10) | <150ms | Walk HEAD with limit |

### Detail Queries

| Operation | Target | Rationale |
|-----------|--------|-----------|
| Full commit history | <500ms | Walk all commits |
| File history | <300ms | Path-specific walk |
| Diff generation | <400ms | Tree comparison |
| Blame | <600ms | Line-by-line attribution |

### Optimization Strategies

1. **Lazy repository opening** - Only open when needed
2. **Commit walk limits** - Default to recent 50, paginate beyond
3. **Blob streaming** - Don't load huge files into memory
4. **Caching** - Cache repository handles, parsed commits
5. **Parallel queries** - Use pygit2's thread safety for multi-ref queries

---

## Development Roadmap

### Phase 1: Core Adapter (v1.2 - Target: Feb 2027)

**Duration:** 3-4 weeks

**Deliverables:**
- [ ] GitAdapter base implementation
- [ ] Repository overview (branches, tags, commits)
- [ ] Commit inspection (single commit details)
- [ ] File at ref (retrieve historical file)
- [ ] Basic query params (since, until, author)
- [ ] Help documentation (help://git)
- [ ] Test suite (>70% coverage)
- [ ] Installation guide for pygit2

**Success Criteria:**
- `reveal git://.` shows repository overview
- `reveal git://.@abc1234` shows commit details
- `reveal git://src/app.py@main` retrieves file
- All operations <200ms on medium repo (1000 commits)

### Phase 2: Advanced Queries (v1.3 - Target: Mar 2027)

**Duration:** 2-3 weeks

**Deliverables:**
- [ ] File history (`?history` query)
- [ ] Path filtering (`?path=src/**/*.py`)
- [ ] Author filtering with regex
- [ ] Merge commit filtering (`?merges`, `?no-merges`)
- [ ] Commit message search (`?message="pattern"`)
- [ ] Enhanced output formatting
- [ ] Comprehensive guide (GIT_ADAPTER_GUIDE.md)

**Success Criteria:**
- Complex queries work: `git://.?since=1m&author="Alice"&path=src/`
- File history retrieval <300ms
- Documentation includes 20+ real-world examples

### Phase 3: Integration & Composition (v1.4 - Target: Apr 2027)

**Duration:** 2 weeks

**Deliverables:**
- [ ] diff:// composition working
- [ ] ast:// composition working
- [ ] --check integration for historical files
- [ ] Quality rules (G001-G003)
- [ ] Performance benchmarks
- [ ] CI/CD integration examples

**Success Criteria:**
- `diff://git:file@v1 vs git:file@v2` works
- `ast://git:src/@abc1234?complexity>10` works
- Documentation includes CI/CD patterns

### Phase 4: Advanced Features (v1.5+ - Target: May+ 2027)

**Future Enhancements:**
- [ ] Blame support (`?blame`)
- [ ] Graph visualization (`?graph`)
- [ ] Submodule support
- [ ] Sparse checkout optimization
- [ ] Remote repository inspection (if cloned)
- [ ] Tag annotation details
- [ ] GPG signature verification

---

## Security Considerations

### Read-Only by Design

**Principle:** Git adapter NEVER writes to repository

**Enforcement:**
- No pygit2 write operations (commit, push, merge, rebase)
- Repository opened in read-only mode where possible
- Error if write operation attempted

### Sensitive Data

**Risks:**
- Commit messages may contain sensitive info
- File contents at refs may include secrets
- Author emails are exposed

**Mitigations:**
- Document read-only nature prominently
- Warn users about sensitive data in help
- Consider `--redact` flag for email addresses (future)

### Repository Access

**Assumptions:**
- User has filesystem read access to repository
- No authentication for remote repositories (out of scope)
- Works on local clones only

---

## Testing Strategy

### Unit Tests

**Coverage Target:** >75%

```python
# tests/test_git_adapter.py
class TestGitAdapter:
    def test_repository_overview(self, mock_repo):
        adapter = GitAdapter('.')
        structure = adapter.get_structure()
        assert structure['type'] == 'repository'
        assert 'branches' in structure
        assert 'tags' in structure

    def test_commit_details(self, mock_repo):
        adapter = GitAdapter('.', ref='abc1234')
        structure = adapter.get_structure()
        assert structure['short_id'] == 'abc1234'
        assert 'author' in structure

    def test_file_at_ref(self, mock_repo):
        adapter = GitAdapter('.', subpath='src/app.py', ref='main')
        structure = adapter.get_structure()
        assert structure['type'] == 'file'
        assert structure['path'] == 'src/app.py'
```

### Integration Tests

```python
# tests/integration/test_git_integration.py
def test_real_repository_inspection():
    """Test on actual git repository (reveal itself)."""
    adapter = GitAdapter('.')
    structure = adapter.get_structure()
    assert len(structure['branches']) > 0
    assert structure['head']['branch'] is not None

def test_diff_composition():
    """Test git:// composition with diff://"""
    # Test actual diff between two git refs
    pass
```

### Performance Tests

```python
# tests/test_git_performance.py
def test_repository_overview_performance():
    """Ensure <100ms for repository overview."""
    import time
    adapter = GitAdapter('.')
    start = time.time()
    adapter.get_structure()
    duration = time.time() - start
    assert duration < 0.1  # 100ms

def test_commit_walk_performance():
    """Ensure <500ms for 100 commit walk."""
    # Test commit history retrieval performance
    pass
```

---

## Documentation & Help

### Help System Integration

```bash
# Inline help
reveal help://git

# Comprehensive guide
reveal help://git-guide

# Quick reference
reveal help://git-queries
```

### Documentation Structure

```
external-git/reveal/docs/
├── GIT_ADAPTER_GUIDE.md         # Comprehensive guide (multi-shot examples)
├── GIT_QUICK_REFERENCE.md       # Cheat sheet
└── GIT_INTEGRATION_PATTERNS.md  # Composition examples
```

### Example Documentation Content

**GIT_ADAPTER_GUIDE.md** (Excerpt):

```markdown
# Git Adapter - Complete Guide

## Quick Start

```bash
# See repository structure
reveal git://.

# Inspect specific commit
reveal git://.@abc1234

# Get file at tag
reveal git://src/app.py@v1.0
```

## Multi-Shot Examples

### Example 1: Finding When a Bug Was Introduced

**Problem:** You need to find which commit introduced a specific bug.

**Step 1:** Get recent commits
```bash
$ reveal git://.?since=1w
Recent commits (15):
  abc1234  Fix dashboard crash  (2h ago, Alice)
  def5678  Update dependencies  (1d ago, Bob)
  ...
```

**Step 2:** Inspect suspicious commit
```bash
$ reveal git://.@def5678
Commit: def5678
Message: Update dependencies
Changes:
  M requirements.txt  (+5, -3)
  M src/dashboard.py  (+2, -1)
```

**Step 3:** Compare versions
```bash
$ reveal diff://git:src/dashboard.py@def5678^ vs git:src/dashboard.py@def5678
- import pandas as pd  # v1.2.0
+ import pandas as pd  # v2.0.0  ⚠️ Breaking change
```

**Interpretation:** Dependency update introduced breaking change

**Next Steps:**
- Pin pandas version or update code
- Check other files using pandas API
```

---

## Appendix: Query Parameter Reference

| Parameter | Type | Example | Description |
|-----------|------|---------|-------------|
| `since` | date/relative | `?since=2026-01-01` | Commits since date |
| | | `?since=1w` | Last week |
| | | `?since=3d` | Last 3 days |
| `until` | date | `?until=2026-01-10` | Commits until date |
| `author` | string/regex | `?author="Alice"` | Filter by author |
| | | `?author="Alice\|Bob"` | Multiple authors |
| `message` | string/regex | `?message="fix bug"` | Filter by message |
| `path` | path pattern | `?path=src/*.py` | Commits affecting path |
| `merges` | flag | `?merges` | Show only merge commits |
| `no-merges` | flag | `?no-merges` | Exclude merge commits |
| `history` | flag | `?history` | File commit history |
| `blame` | flag | `?blame` | File line-by-line blame |

---

## Appendix: Composition Patterns

### Pattern 1: Historical Code Quality Analysis

```bash
# Check code quality at v1.0
reveal git://src/@v1.0 --check

# Compare quality between versions
reveal git://src/@v1.0 --check --format json > v1.json
reveal git://src/@v2.0 --check --format json > v2.json
diff v1.json v2.json
```

### Pattern 2: API Evolution Tracking

```bash
# AST of API at different versions
reveal ast://git:src/api.py@v1.0
reveal ast://git:src/api.py@v2.0

# Compare function signatures
reveal diff://ast:git:src/api.py@v1.0 vs ast:git:src/api.py@v2.0
```

### Pattern 3: Security Audit of Historical Code

```bash
# Check old versions for secrets
reveal git://src/@v1.0 --check --select S701

# Find when secret was introduced
reveal git://src/config.py?history | grep "API_KEY"
```

---

## Issues Encountered During Design Process

**Context:** During this design session (riholuxi-0113), I initially used `reveal` correctly but then fell back to non-reveal commands (find, grep, ls). This section documents why, as a learning opportunity for improving reveal.

### Issue 1: Search for Non-Existent URI Scheme

**What Happened:**
```bash
# I tried this:
tia search all "git://"

# Expected: Find documentation about planned git:// adapter
# Got: No results (0 matches)
```

**Why I Fell Back:**
- `tia search all` searches for **literal text**, not concepts
- "git://" as a literal string wasn't in any files (it was written as `git://` in markdown)
- I should have used: `tia beth explore "git adapter"` for **concept discovery**

**Lesson for Reveal:**
- ✅ This is expected behavior - search is literal, beth is semantic
- 📝 Could improve: Help message when search finds nothing: "Try: tia beth explore 'git adapter' for concept search"

### Issue 2: Unknown Path Structure

**What Happened:**
```bash
# I ran this:
find /home/scottsen/src/projects/reveal -name "*.md" -type f | grep -iE "(git|design|doc)"

# Instead of:
reveal /home/scottsen/src/projects/reveal
reveal /home/scottsen/src/projects/reveal/internal-docs
```

**Why I Fell Back:**
- I didn't know if the reveal project had `internal-docs/` vs `docs/` vs `planning/`
- `find` + `grep` felt "safer" when structure is unknown
- I should have used `reveal` first to **discover structure**, then navigate

**Lesson for Reveal:**
- ✅ Reveal is perfect for this - I just didn't use it
- 📝 Mental model issue: Agents (including me) reach for `find` when uncertain
- 🎯 **Design implication for git:// adapter**: Must handle "I don't know the structure" case gracefully

**What I Should Have Done:**
```bash
# Step 1: See structure
reveal /home/scottsen/src/projects/reveal

# Step 2: Navigate to internal docs
reveal /home/scottsen/src/projects/reveal/internal-docs

# Step 3: Find markdown files
reveal /home/scottsen/src/projects/reveal/internal-docs --pattern "*.md"
```

### Issue 3: Grepping Python Files for Classes

**What Happened:**
```bash
# I ran this:
find /home/scottsen/src/projects/reveal -name "*.py" | xargs grep -l "class.*Git"

# Instead of:
reveal /home/scottsen/src/projects/reveal/external-git/reveal/adapters --outline
# Then inspect specific files
```

**Why I Fell Back:**
- Looking for a **pattern** (`class.*Git`) across many files
- Felt like a job for `grep -r`, not reveal
- Didn't think about using reveal's structure view first

**Lesson for Reveal:**
- ⚠️ This is a **gap**: Reveal doesn't have pattern search across files
- 🎯 **Feature idea**: `reveal://pattern:src?regex="class.*Git"` (future semantic:// adapter)
- 📝 For now, grep is appropriate for regex pattern search
- ✅ But I should have used reveal to **understand structure first**, then grep

**What I Should Have Done:**
```bash
# Step 1: See what adapters exist (structure first)
reveal /home/scottsen/src/projects/reveal/external-git/reveal/adapters --outline

# Step 2: Look for Git-related files by name
reveal /home/scottsen/src/projects/reveal/external-git/reveal/adapters | grep -i git

# Step 3: If needed, grep for patterns
grep -r "class.*Git" /home/scottsen/src/projects/reveal/external-git/reveal/adapters
```

### Issue 4: Bash ls Instead of Reveal

**What Happened:**
```bash
# I ran this:
ls -la /home/scottsen/src/projects/reveal/internal-docs/

# Instead of:
reveal /home/scottsen/src/projects/reveal/internal-docs
```

**Why I Fell Back:**
- Quick directory listing felt like an `ls` job
- Habit: Terminal users reach for `ls` reflexively
- Didn't need structure, just "what's in here"

**Lesson for Reveal:**
- ✅ Reveal output would have been better (structured, sorted by type)
- 📝 Mental model issue: `ls` is muscle memory for "quick peek"
- 🎯 **Design implication**: Reveal must be as fast as `ls` for this pattern to change

**Comparison:**
```bash
# ls output (raw, timestamps, permissions)
drwxrwxr-x 6 scottsen scottsen  4096 Jan 13 13:46 .
drwxrwxr-x 6 scottsen scottsen  4096 Jan 13 13:45 ..
-rw------- 1 scottsen scottsen 32100 Dec 31 23:52 ARCHITECTURAL_DILIGENCE.md
...

# reveal output (structured, token-efficient)
internal-docs/
├── archive/
├── planning/
├── releasing/
├── research/
├── ARCHITECTURAL_DILIGENCE.md
└── README.md
```

**Reveal is objectively better here** - I just defaulted to habit.

---

## Design Implications for git:// Adapter

These issues inform the git:// adapter design:

### 1. Structure-First Discovery Must Be Intuitive

**Problem:** I reached for `find` because I didn't know the structure.

**Solution for git://:**
```bash
# Default behavior: Show repository structure overview
reveal git://.

# Output must clearly guide next steps
Next:
  reveal git://.@main           # Explore branch
  reveal git://src/             # Explore directory
  reveal git://.?since=1w       # Recent commits
```

**Design Principle:** First command shows "what's possible", not "everything".

### 2. Handle Unknown References Gracefully

**Problem:** Users won't know commit hashes, branch names upfront.

**Solution:**
```bash
# If user tries invalid ref:
$ reveal git://.@invalid-branch

❌ Invalid ref: invalid-branch

Available branches:
  main, develop, feature/x

Suggestion:
  reveal git://.                # See all branches
  reveal git://.@main           # Use valid branch
```

**Design Principle:** Errors teach, don't just reject.

### 3. Progressive Disclosure Prevents "Find/Grep" Fallback

**Problem:** When structure is unknown, agents fall back to `find/grep`.

**Solution:** Make structure discovery so fast and clear that `find` feels unnecessary.

```bash
# Fast structure view
reveal git://.                  # <100ms, shows branches/tags/recent commits

# Navigate progressively
reveal git://.@main             # <50ms, shows commit details
reveal git://src/app.py@main   # <200ms, shows file
```

**Design Principle:** Speed + clarity > exhaustive detail.

### 4. Query System for Pattern Discovery

**Problem:** I used `grep` for pattern search (`class.*Git`).

**Future Enhancement:**
```bash
# Phase 2: Pattern search in git history
reveal git://.?grep="class.*Git"

# Phase 3: Semantic search
reveal semantic://git:.?pattern="authentication code"
```

**Design Principle:** Reveal should eventually support pattern search, but grep is fine for now.

---

## Summary: When to Use What

| Task | Tool | Rationale |
|------|------|-----------|
| **Unknown structure** | `reveal path/` | Structure-first discovery |
| **Navigate known structure** | `reveal path/file` | Progressive disclosure |
| **Literal text search** | `tia search all "text"` | Fast, indexed search |
| **Concept discovery** | `tia beth explore "concept"` | Semantic search |
| **Regex pattern search** | `grep -r "pattern"` | Reveal doesn't support regex yet |
| **Quick directory peek** | `reveal path/` (not `ls`) | Better structure, same speed |
| **File metadata** | `ls -la` (acceptable) | Permissions, timestamps |

**Key Insight:** I fell back to non-reveal commands due to:
1. **Habit** (ls, find, grep are muscle memory)
2. **Uncertainty** (didn't know structure, felt "safer" with find)
3. **Feature gaps** (reveal doesn't do regex search yet)

**None of these are reveal's fault** - they're mental model issues and future feature opportunities.

---

## Glossary

- **Ref** - Git reference (commit hash, branch, tag, HEAD)
- **Subpath** - File or directory path within repository
- **Progressive Disclosure** - Show overview first, details on demand
- **Composition** - Combining git:// with other adapters (diff://, ast://)
- **Token Efficiency** - Optimizing output for AI agent context windows
- **Structure-First Discovery** - Use reveal to understand layout before searching

---

## References

### External Documentation
- **pygit2 Documentation**: https://www.pygit2.org/
- **libgit2 API**: https://libgit2.org/libgit2/
- **Git Internals**: https://git-scm.com/book/en/v2/Git-Internals-Plumbing-and-Porcelain

### Internal Documentation
- **ADAPTER_AUTHORING_GUIDE.md** - How to create adapters
- **REVEAL_ADAPTER_GUIDE.md** - reveal:// reference implementation
- **ADVANCED_URI_SCHEMES.md** - Advanced adapter concepts
- **ARCHITECTURAL_DILIGENCE.md** - Reveal development standards

---

**Last Updated:** 2026-01-13
**Status:** Design Document (Ready for Implementation)
**Next Review:** After Phase 1 completion (Feb 2027)
