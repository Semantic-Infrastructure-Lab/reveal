# Reveal Enhancement Proposals

**Last Updated:** 2025-12-16
**Status:** Living document - updated as proposals move to implementation

This document catalogs enhancement ideas for Reveal beyond current active work. For immediate priorities, see `PENDING_WORK.md` and `ROADMAP.md`.

---

## Document Organization

**Where to look for what:**

1. **Shipped features** → See `ROADMAP.md` (What We've Shipped) and `CHANGELOG.md`
2. **Active development** → See `PENDING_WORK.md` (4 tracks: Duplicate Detection, Quality Refactoring, Testing, Link Validation)
3. **Near-term planned** → See `ROADMAP.md` (v0.24-v0.26: diff://, stats://, --watch)
4. **Future ideas** → This document (organized by theme)
5. **Long-term vision** → See `ADVANCED_URI_SCHEMES.md` (post-v1.0 roadmap)

---

## Recently Shipped (v0.23.x)

The following were proposals that are now shipped:

- ✅ `--copy` clipboard integration (v0.19.0)
- ✅ `json://` adapter for JSON navigation (v0.20.0)
- ✅ `ast://` query system (v0.23.0)
- ✅ `python://` runtime adapter (v0.17.0)
- ✅ Decorator extraction and queries (v0.23.0)
- ✅ Enhanced help system with `help://` (v0.17.0)
- ✅ `--typed` hierarchical structure (v0.23.0)
- ✅ Quality rules system with --check (v0.16.0)

**See:** `CHANGELOG.md` for full details

---

## In Active Development

**These are not proposals - they're active work:**

**Track 1:** Duplicate Detection (D001/D002 rules)
**Track 2:** Code Quality Refactoring (Phases 2-3)
**Track 3:** Testing Infrastructure (50%+ coverage)
**Track 4:** Link Validation (L-series rules, --recursive, framework profiles)

**See:** `PENDING_WORK.md` for details and status

---

## Confirmed for Near-Term (v0.25-v0.26)

**These are on ROADMAP, not proposals:**

- `diff://` adapter - Comparative exploration
- `stats://` adapter - Codebase health metrics
- `--watch` mode - Live file monitoring
- Color themes - Accessibility and preference
- Config file support - `~/.config/reveal/config.yaml`

**See:** `ROADMAP.md` for release targets

---

## Enhancement Proposals by Theme

These are ideas that haven't been scheduled yet. Organized by functional area.

### Theme 1: User Experience

#### 1.1 Interactive Mode

**Problem:** Repeatedly typing full commands during exploration

**Proposed:**
```bash
reveal -i ./src

reveal> list
Functions (234), Classes (28)

reveal> show UserManager
[class structure]

reveal> check
[quality issues]

reveal> extract create_user
[function code]
```

**Value:** Exploratory workflows, reduced typing, state preservation

**Complexity:** Medium (REPL, history, tab completion)

**Related:** Could integrate with --watch for live updates

---

#### 1.2 Quiet Mode

**Problem:** Breadcrumbs useful for learning, noisy for scripting

**Proposed:**
```bash
reveal app.py --quiet          # No breadcrumbs
reveal app.py -q               # Short form
```

**Value:** Clean output for pipes and scripts

**Complexity:** Low (suppress breadcrumb logic)

**Status:** Easy win, could ship in v0.25

---

### Theme 2: Integration & Ecosystem

#### 2.1 Git Pre-Commit Hook

**Problem:** Quality issues slip into commits

**Proposed:**
```bash
# Install hook
reveal --install-hook pre-commit

# Auto-generated .git/hooks/pre-commit:
#!/bin/bash
git diff --cached --name-only | reveal --stdin --check --select=B,S
if [ $? -ne 0 ]; then
  echo "Quality checks failed. Fix issues or use --no-verify"
  exit 1
fi
```

**Value:** Automated quality gates, shift-left

**Complexity:** Low (hook template generator)

---

#### 2.2 GitHub Action

**Problem:** No official CI/CD integration

**Proposed:**
```yaml
# .github/workflows/reveal.yml
- uses: semantic-infrastructure-lab/reveal-action@v1
  with:
    check: true
    select: B,S
    fail-on-issues: true
```

**Value:** PR quality gates, team visibility

**Complexity:** Medium (GitHub Action wrapper, reporting)

**Note:** JSON output already exists, just need the Action wrapper

---

#### 2.3 VS Code Extension

**Problem:** Context switching between editor and terminal

**Proposed Features:**
- Hover: Show function structure
- Command palette: "Reveal: Show Structure"
- Panel: Live structure view
- Quick fix: "Reveal: Check This File"

**Value:** IDE integration, lower friction

**Complexity:** High (VS Code API, language server protocol)

**Status:** Post-v1.0 (requires stable API)

---

### Theme 3: Remote & Distributed

#### 3.1 Remote File Support

**Problem:** Can't reveal files on remote servers directly

**Proposed:**
```bash
# SSH-based
reveal ssh://server/path/to/file.py

# With jump host
reveal ssh://jump:server/path/to/file.py

# Using SSH config
reveal ssh://prod/app/main.py
```

**Value:** Production debugging, no scp/rsync needed

**Complexity:** Medium (SSH transport, caching)

---

#### 3.2 HTTP/HTTPS Resource Support

**Problem:** Can't explore remote codebases

**Proposed:**
```bash
# GitHub raw content
reveal https://raw.githubusercontent.com/user/repo/main/src/app.py

# GitLab, Bitbucket, etc.
reveal https://gitlab.com/project/-/raw/main/src/app.py
```

**Value:** Explore code without cloning

**Complexity:** Medium (HTTP client, caching, auth)

**Related:** Could enable REST API exploration later

---

### Theme 4: Advanced Query & Analysis

**Note:** Many of these are covered in `ADVANCED_URI_SCHEMES.md` for post-v1.0

#### 4.1 SQL-like Queries

**Proposed:**
```bash
# SQL-like syntax
reveal 'query://./src WHERE lines > 50 AND complexity > 5'

# Select specific fields
reveal 'query://./src SELECT name, lines WHERE type = function'

# Aggregations
reveal 'query://./src SELECT file, COUNT(*) GROUP BY file'
```

**Value:** Powerful ad-hoc analysis without jq

**Complexity:** High (SQL parser, query planner)

**Status:** See `ADVANCED_URI_SCHEMES.md` - Phase 2 (post-v1.1)

---

#### 4.2 Graph Visualization

**Proposed:**
```bash
# Import graph
reveal graph://./src --imports

# Call graph
reveal graph://app.py:main --calls

# Output as Mermaid/DOT
reveal graph://./src --imports --format=mermaid
```

**Value:** Architecture understanding, refactoring planning

**Complexity:** High (graph construction, layout)

**Status:** See `ADVANCED_URI_SCHEMES.md` - Phase 2 (post-v1.1)

---

#### 4.3 Semantic Search

**Proposed:**
```bash
# Find code by intent, not text
reveal 'search://./src "exception handling"'
reveal 'search://./src "user authentication"'
```

**Implementation:** Local embeddings or API-based

**Value:** Natural language code discovery

**Complexity:** Very High (embedding model, vector search)

**Status:** See `ADVANCED_URI_SCHEMES.md` - Phase 3 (post-v1.2)

---

### Theme 5: Database & External Systems

**Note:** See ROADMAP.md for database adapter timeline

#### 5.1 Database Schema Exploration

**Proposed:**
```bash
pip install reveal-cli[database]

reveal postgres://prod users         # Table structure
reveal mysql://staging orders
reveal sqlite:///app.db
```

**Status:** Planned for post-v0.26

**Complexity:** Medium (SQL adapters, connection management)

**Existing Work:** MySQL adapter spec complete (unpublished)

---

#### 5.2 API & OpenAPI

**Proposed:**
```bash
reveal https://api.github.com            # REST API exploration
reveal openapi://petstore.swagger.io     # OpenAPI spec
reveal graphql://api.github.com/graphql  # GraphQL introspection
```

**Value:** API documentation, testing

**Complexity:** High (multiple protocols, auth)

**Status:** Long-term ecosystem goal

---

#### 5.3 Container Inspection

**Proposed:**
```bash
reveal docker://container-name           # Container inspection
reveal docker-compose://web              # Compose service details
```

**Value:** DevOps, debugging

**Complexity:** Medium (Docker API integration)

**Status:** Long-term ecosystem goal

---

### Theme 6: Plugin System

#### 6.1 Community Adapters

**Problem:** Can't extend reveal without forking

**Proposed:**
```python
# ~/.reveal/plugins/my_plugin.py
from reveal import register_adapter

@register_adapter('mydb')
class MyDBAdapter:
    def get_structure(self, **kwargs):
        ...
```

```bash
reveal mydb://localhost/mydb
```

**Value:** Community extensions, private tools

**Complexity:** Medium (plugin discovery, API stability)

**Blocker:** Requires v1.0 API freeze first

**Status:** Post-v1.0

---

## Proposals Archived / Rejected

### Config File Support

**Status:** Moved to ROADMAP.md for v0.27-v0.29

**Reason:** High value, straightforward implementation

---

### Watch Mode

**Status:** Moved to ROADMAP.md for v0.25-v0.26

**Reason:** High value, low complexity, user demand

---

### Color Themes

**Status:** Moved to ROADMAP.md for v0.27-v0.29

**Reason:** Accessibility important, medium priority

---

## How to Propose Enhancements

1. **Check existing docs first:**
   - `ROADMAP.md` - Is it already planned?
   - `PENDING_WORK.md` - Is someone working on it?
   - This file - Has it been proposed?
   - `ADVANCED_URI_SCHEMES.md` - Is it part of the long-term vision?

2. **Open a GitHub Discussion** (preferred for ideas)
   - https://github.com/Semantic-Infrastructure-Lab/reveal/discussions

3. **Open a GitHub Issue** (for concrete feature requests)
   - https://github.com/Semantic-Infrastructure-Lab/reveal/issues
   - Use template: Feature Request
   - Reference this document

4. **Contribute directly:**
   - See `CONTRIBUTING.md` for guidelines
   - Small features (< 100 lines): PR welcome
   - Large features: Discussion first

---

## Decision Framework

**How proposals get prioritized:**

1. **User pain point?** Real problems > nice-to-haves
2. **Complexity vs value?** High value, low complexity ships first
3. **Fits reveal philosophy?** Progressive disclosure, URI adapters, composability
4. **API stability?** Requires v1.0 freeze? → Post-v1.0
5. **Dependencies?** Needs other features first? → Later phases
6. **Ecosystem vs core?** Plugin system can handle? → Post-v1.0

**Current priorities:**
- Solve real pain points (Link validation)
- Improve quality and testing (Code refactoring, test coverage)
- Complete core adapters (diff://, stats://)
- Stabilize for v1.0 (API freeze, documentation)
- Then: Advanced features (query://, graph://, semantic://)

---

## Related Documentation

- `ROADMAP.md` - Official release roadmap
- `PENDING_WORK.md` - Active development tracks
- `ADVANCED_URI_SCHEMES.md` - Post-v1.0 URI adapter vision (1062 lines)
- `CHANGELOG.md` - What's been shipped
- `CONTRIBUTING.md` - How to contribute

---

**Last Review:** 2025-12-16 (kujofugo-1216)
**Next Review:** When v0.24 ships (expected Q1 2026)
**Maintainer:** Scott (Semantic Infrastructure Lab)
