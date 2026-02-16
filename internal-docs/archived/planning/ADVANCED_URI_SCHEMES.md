# Advanced URI Schemes for Reveal

**Version:** Conceptual (Post v1.0)
**Date:** 2025-12-02 (Updated 2026-01-06)
**Status:** Long-term Vision Document

> **Timeline:** These schemes are planned for **v1.1+ (post Q1 2027)**. See `external-git/ROADMAP.md` for authoritative timeline.

**For near-term features**, see:
- **[PRACTICAL_CODE_ANALYSIS_ADAPTERS.md](./PRACTICAL_CODE_ANALYSIS_ADAPTERS.md)** - Architecture validation, enhanced AST
- **`external-git/ROADMAP.md`** - Authoritative release timeline

**This document** covers **advanced/meta** URI schemes for post-v1.0 phases:
- `query://` - Cross-resource queries
- `graph://` - Relationship visualization
- `time://` - Temporal exploration (Git history)
- `semantic://` - Embeddings-based code search
- `trace://` - Execution trace exploration
- `live://` - Real-time monitoring

---

## 🎯 Vision

Extend reveal's URI adapter architecture beyond basic resource types (files, databases, APIs) to enable **meta-resource exploration** - querying across resources, time-travel, semantic search, and real-time monitoring.

**Core Principle:** Every URI scheme maintains reveal's progressive disclosure pattern and token-efficient output.

---

## 🧠 Design Philosophy

### Implementation Independence

All URI schemes described here should be **reveal-native implementations**:
- ✅ Self-contained adapters in reveal codebase
- ✅ Use reveal's existing analyzer infrastructure where applicable
- ✅ No external dependencies on TIA or other systems
- ✅ Leverage optional dependencies model: `reveal-cli[advanced]`

### Key Constraints

1. **Progressive Disclosure:** All adapters must show structure first, details on demand
2. **Token Efficiency:** Outputs optimized for AI agent consumption
3. **Composability:** URIs can reference other URIs
4. **Security:** No credential leakage, safe by default
5. **Performance:** Fast structure queries (<100ms), lazy detail loading

---

## 📐 Advanced URI Schemes

### 1. ast:// - AST Query Interface

**Purpose:** Treat codebase as queryable graph database

**Syntax:**
```
ast://<path>[?query_params][#element]
```

**Examples:**
```bash
# Basic structure (like current reveal)
reveal ast://./src

# Query by complexity
reveal ast://./src?complexity>10

# Find all functions calling a specific function
reveal ast://./lib?calls=authenticate

# Find all classes implementing an interface
reveal ast://.?implements=BaseAdapter

# Extract call graph
reveal ast://./src/auth#login --call-graph
```

**Implementation Notes:**
- Build on reveal's existing tree-sitter infrastructure
- Add query engine that filters AST nodes by properties
- Call graph analysis via static analysis (no TIA dependency)
- Output follows reveal's tree format

**Query Parameters:**
- `complexity>N` - Cyclomatic complexity threshold
- `lines>N` - Function length threshold
- `calls=function_name` - Find callers/callees
- `implements=interface` - Find implementations
- `type=function|class|method` - Filter by element type
- `pattern=regex` - Match by pattern

**Output Structure:**
```
AST Query: ./src?calls=authenticate
Results: 12 functions

Callers of authenticate():
  src/auth/login.py:45        login_user() [8 lines, complexity: 3]
  src/api/endpoints.py:89     verify_request() [23 lines, complexity: 7]
  src/middleware/auth.py:23   check_token() [15 lines, complexity: 4]
  ... 9 more

Next: reveal ast://src/auth/login.py:45  # Drill into specific function
```

**Phase 1 Implementation:**
- Basic query parser
- Complexity, lines, type filters
- Integration with existing Python/JS/Rust analyzers

**Phase 2 Enhancements:**
- Call graph generation
- Cross-file dependency analysis
- Pattern matching and semantic queries

---

### 2. diff:// - Comparative Resource Exploration

**Purpose:** Compare two resources and show only differences

**Syntax:**
```
diff://<resource1> vs <resource2>[?options]
```

**Examples:**
```bash
# Compare database schemas
reveal diff://mysql://prod vs mysql://staging

# Compare API versions
reveal diff://https://api.v1.example.com vs https://api.v2.example.com

# Compare file versions (Git integration)
reveal diff://file:v1.2.0:src/app.py vs file:main:src/app.py

# Compare directory structures
reveal diff://./old-version vs ./new-version

# Compare AST structures (detect refactoring)
reveal diff://ast:v1:./src vs ast:v2:./src
```

**Implementation Notes:**
- Adapter that wraps two other adapters
- Structural diff algorithm (not line-by-line)
- Categorize changes: added, removed, modified
- Smart diffing based on resource type

**Query Parameters:**
- `ignore=field1,field2` - Skip specific fields
- `only=type1,type2` - Show only specific types
- `threshold=N` - Minimum difference significance

**Output Structure:**
```
Diff: mysql://prod vs mysql://staging

Schema Differences (3):
  ✅ users              (identical in both)
  ⚠️  posts             (schema changed)
     + created_at_tz    (added in prod)
     ~ status           (type changed: VARCHAR → ENUM)
  ❌ analytics          (only in prod)

Summary:
  Tables: 12 identical, 1 modified, 1 added
  Columns: 98 identical, 2 modified, 1 added

Next: reveal diff://mysql://prod/posts vs mysql://staging/posts --details
```

**Phase 1 Implementation:**
- Diff adapter wrapper
- File and directory diffing
- Basic database schema diffing

**Phase 2 Enhancements:**
- Semantic diffing (detect renames, moves)
- API contract diffing (breaking vs non-breaking)
- Git integration for temporal diffs

---

### 3. query:// - Cross-Resource Queries

**Purpose:** Execute queries across multiple heterogeneous resources

**Syntax:**
```
query://"<search_term>" --in <resource_list> [--options]
```

**Examples:**
```bash
# Find identifier across all resources
reveal query://"user_id" --in mysql://prod,ast://./src,docker://app

# Find inconsistencies between code and database
reveal query://validate --code ast://./models --db mysql://prod

# Security audit across systems
reveal query://secrets --in ast://.,docker://config,mysql://prod/env

# Dependency tracking
reveal query://library=requests --in ast://.,requirements.txt,docker://

# Schema consistency check
reveal query://columns table=users --in mysql://prod,postgresql://backup
```

**Implementation Notes:**
- Query planner that routes to multiple adapters
- Result aggregator that merges outputs
- Consistency checker for validation queries
- Pattern detection across resource types

**Query Types:**
1. **Search Queries:** Find literal matches
2. **Validation Queries:** Check consistency
3. **Security Queries:** Find vulnerabilities
4. **Dependency Queries:** Track relationships

**Output Structure:**
```
Query: "user_id" across all resources

Found in 47 locations:

Database: mysql://prod (3 tables)
  users.id              PRIMARY KEY, AUTO_INCREMENT
  posts.user_id         FOREIGN KEY → users.id
  comments.user_id      FOREIGN KEY → users.id

Code: ast://./src (15 references)
  src/models/user.py:23      User.user_id (property)
  src/auth/session.py:45     authenticate(user_id: int)
  src/api/users.py:67        get_user_by_id(user_id: int)
  ... 12 more

Environment: docker://app (1 variable)
  USER_ID_HEADER        X-User-ID

Consistency Check:
  ✅ Type consistent (int everywhere)
  ⚠️  Naming inconsistent (user_id vs userId in 3 places)

Next: reveal query://"user_id" --show-flow  # Show data flow diagram
```

**Phase 1 Implementation:**
- Basic search across file, database, docker
- Simple aggregation and formatting
- Literal string matching

**Phase 2 Enhancements:**
- Validation queries (consistency checking)
- Security pattern detection
- Data flow analysis

---

### 4. time:// - Temporal Resource Exploration

**Purpose:** Explore resources at different points in time

**Syntax:**
```
time://<resource>@<timestamp|tag|commit>
```

**Examples:**
```bash
# Database schema as it was yesterday
reveal time://mysql://prod@2025-12-01

# Code structure at specific commit
reveal time://ast://./src@abc123

# API structure 3 months ago (requires API versioning)
reveal time://https://api.example.com@2025-09-01

# File as it was at tag
reveal time://file://src/app.py@v1.2.0

# Find when element was introduced
reveal time://mysql://prod --find-first table=analytics
```

**Implementation Notes:**
- Requires Git integration for code resources
- Database schema history via migration tracking or schema_history table
- API versioning via archive.org or internal versioning system
- Wrapper adapter that adds temporal dimension to any resource

**Time Specifiers:**
- `@YYYY-MM-DD` - Specific date
- `@commit-hash` - Git commit
- `@tag-name` - Git tag
- `@HH:MM` - Time today
- `@1h-ago`, `@3d-ago` - Relative time

**Output Structure:**
```
Resource: mysql://prod@2025-11-01
Schema as of: 2025-11-01 00:00:00 (30 days ago)

Tables (10):
  users              (existed, unchanged)
  posts              (existed, 2 columns different)
  comments           (existed, unchanged)
  ❌ analytics       (did not exist yet)

Changes since then:
  + analytics table  (added 2025-11-15)
  ~ posts.status     (modified 2025-11-08)

Next: reveal diff://time:mysql://prod@2025-11-01 vs mysql://prod
```

**Phase 1 Implementation:**
- Git-backed file and AST queries
- Database migration history parsing
- Basic timestamp resolution

**Phase 2 Enhancements:**
- Schema evolution tracking
- Automatic migration detection
- Time-based diff and blame

---

### 5. graph:// - Relationship Graph Exploration

**Purpose:** Visualize and explore relationships between elements

**Syntax:**
```
graph://<resource>[?type=<graph_type>][&options]
```

**Examples:**
```bash
# Database foreign key relationships
reveal graph://mysql://prod?type=foreign_keys

# Function call graph
reveal graph://ast://./src?type=calls

# Import dependency graph
reveal graph://ast://.?type=imports&depth=3

# Service dependency graph
reveal graph://docker-compose://.?type=services

# Cross-resource dependency graph
reveal graph://mysql://prod+ast://./src?type=data_flow
```

**Implementation Notes:**
- Graph builder that extracts relationships
- Multiple graph types per resource
- Output as tree (text) or export formats (dot, mermaid)
- Progressive disclosure: high-level → drill down

**Graph Types:**
- `foreign_keys` - Database relationships
- `calls` - Function call graph
- `imports` - Module dependencies
- `services` - Container dependencies
- `data_flow` - Cross-resource data flow

**Output Structure:**
```
Dependency Graph: mysql://prod (foreign_keys)

Root Tables (no dependencies):
  users
  categories

Mid-level Tables:
  posts              → users (user_id)
                     → categories (category_id)

  tags               → posts (post_id)

Leaf Tables (high dependency):
  comments           → posts (post_id)
                     → users (user_id)
  likes              → posts (post_id)
                     → users (user_id)

Metrics:
  Circular dependencies: None ✅
  Max depth: 3 levels
  Hotspot: users (referenced by 5 tables)

Next: reveal graph://mysql://prod?type=foreign_keys --export dot
```

**Phase 1 Implementation:**
- Basic graph extraction (foreign keys, imports)
- Tree-based visualization
- Cycle detection

**Phase 2 Enhancements:**
- Export to Graphviz/Mermaid
- Cross-resource graphs
- Interactive graph exploration

---

### 6. trace:// - Execution Trace Exploration

**Purpose:** Apply progressive disclosure to runtime/profiling data

**Syntax:**
```
trace://<trace_file|service>[?options]
```

**Examples:**
```bash
# Python profiler output
reveal trace://profile.json

# Pytest results
reveal trace://pytest-results.xml

# SQL query execution plan
reveal trace://mysql://prod/explain?query="SELECT * FROM users"

# Distributed trace (future: requires tracing backend)
reveal trace://jaeger://trace_id

# Strace output
reveal trace://strace.log
```

**Implementation Notes:**
- Parsers for common trace formats (cProfile, pytest, strace)
- Hierarchical trace structure
- Hot path identification
- Progressive disclosure: summary → hot paths → details

**Query Parameters:**
- `threshold=Nms` - Show only operations > N milliseconds
- `type=function|sql|syscall` - Filter by trace type
- `depth=N` - Limit call depth

**Output Structure:**
```
Trace: profile.json
Total Runtime: 3.247s

Hot Paths (> 100ms):
  authenticate()           847ms  (26.1%)
  ├─ validate_token()      512ms  (60.4% of parent)
  ├─ check_permissions()   203ms  (24.0%)
  └─ log_access()          132ms  (15.6%)

  fetch_user_data()        654ms  (20.1%)
  ├─ db.query()            587ms  (89.8%)  ⚠️  SLOW QUERY
  └─ cache.get()            67ms  (10.2%)

  render_template()        421ms  (13.0%)

Bottlenecks:
  1. db.query() in fetch_user_data() - 587ms (consider indexing)
  2. validate_token() - 512ms (cache tokens?)

Next: reveal trace://profile.json --function fetch_user_data
```

**Phase 1 Implementation:**
- cProfile/pstats parser
- Pytest XML parser
- Basic SQL EXPLAIN parser
- Hot path identification

**Phase 2 Enhancements:**
- Distributed tracing integration
- Flame graph generation
- Performance regression detection

---

### 7. semantic:// - Semantic Code Search

**Purpose:** Search by meaning/intent, not literal text

**Status:** 🔄 **Updated 2025-12-22** - Merged with audit-driven behavior pattern proposal

**Two-Phase Approach:**
1. **Phase 1** (Practical): AST-based behavior patterns (no ML dependencies)
2. **Phase 2** (Advanced): Embeddings-based similarity search (requires ML)

---

#### Phase 1: Behavior Pattern Search (AST-Based)

**Purpose:** Find code by what it **does** (system calls, API usage), not what it's named

**Syntax:**
```bash
semantic://<resource>?<behavior_pattern>
```

**Built-in Patterns** (AST-based detection):

| Pattern | Detects | Use Case |
|---------|---------|----------|
| `opens_file` | `open()`, `Path().read_text()`, file operations | Security audit, I/O analysis |
| `makes_http_call` | `requests.*`, `httpx.*`, `urllib.*` | Network dependency mapping |
| `executes_sql` | SQL queries (raw or ORM) | SQL injection audit |
| `uses_subprocess` | `subprocess.*`, `os.system()` | Command injection audit |
| `sleeps` | `time.sleep()`, `asyncio.sleep()` | Performance analysis |
| `uses_random` | `random.*`, `secrets.*` | Non-determinism detection |
| `uses_datetime` | `datetime.now()`, `time.time()` | Time-dependent code |
| `raises_exception` | `raise Exception` | Error handling audit |

**Examples:**
```bash
# Security audit: Find all file operations
reveal 'semantic://app?opens_file'

# Find all HTTP calls (network dependencies)
reveal 'semantic://app?makes_http_call'

# Find SQL queries (potential injection)
reveal 'semantic://app?executes_sql'

# Find shell commands (command injection risk)
reveal 'semantic://app?uses_subprocess'

# Performance: Find blocking sleeps
reveal 'semantic://app?sleeps'
```

**Configuration** (`.reveal.yaml` - project-specific patterns):
```yaml
semantic:
  # Built-in patterns (AST-based, fast, no ML)
  patterns:
    - name: opens_file
      detect: ["open(", "Path().read_text(", "Path().write_bytes("]

    - name: executes_sql
      detect: ["execute(", "executemany(", "cursor.execute"]

  # Custom patterns (your project's patterns)
  custom_patterns:
    - name: uses_stripe_api
      description: "Functions that call Stripe API"
      patterns:
        - "stripe\\..*\\("
        - "Stripe.*"

    - name: uses_email
      description: "Functions that send email"
      patterns:
        - "send.*email"
        - "smtp\\."
        - "EmailMessage"
```

**Output Structure:**
```
Semantic Search (Behavior): opens_file

Functions that open files: 12

app/repositories/sticker_repository.py:
  load_stickers [line 45]
    → open('stickers.json', 'r')

  save_stickers [line 78]
    → open('stickers.json', 'w')

app/services/backup_service.py:
  create_backup [line 102]
    → Path('backup.zip').write_bytes(data)

Recommendation:
  Consider using context managers (with statement) for all file operations
  Found 3 functions using open() without context manager
```

**Use Cases:**
1. **Security Audit**: Find all file/SQL/subprocess operations
2. **Performance Analysis**: Find sleeps, random, datetime usage
3. **Dependency Audit**: Find all HTTP calls, external APIs
4. **Refactoring**: Find all uses of deprecated patterns

**Implementation Notes:**
- AST-based pattern matching (uses tree-sitter)
- No ML dependencies required
- Fast (<500ms for medium codebase)
- Configurable patterns via `.reveal.yaml`
- Language-agnostic (Python, JS, Go, Rust support)

**Validation**: SDMS audit - found all file/HTTP/SQL operations for security review

---

#### Phase 2: Embeddings-Based Similarity (ML-Based)

**Purpose:** Find code by natural language description or semantic similarity

**Syntax:**
```
semantic://"<description>" --in <resource>
```

**Examples:**
```bash
# Find authentication code (not just grep "auth")
reveal semantic://"user authentication" --in ast://./src

# Find similar functions
reveal semantic://like:src/auth/login.py#authenticate

# Find by behavior description
reveal semantic://"functions that make HTTP requests"

# Find by intent
reveal semantic://"database migration code"
```

**Implementation Notes:**
- Requires embeddings model (e.g., sentence-transformers)
- Index codebase with semantic embeddings
- Query using natural language
- Optional dependency: `reveal-cli[semantic]`

**Embeddings Backend Options:**
1. Local model (sentence-transformers)
2. OpenAI embeddings API
3. Pre-computed embeddings cache

**Output Structure:**
```
Semantic Search (Embeddings): "user authentication"
Model: all-MiniLM-L6-v2 (local)

Found 15 semantically similar functions:

High Confidence (score > 0.85):
  src/auth/login.py:45           authenticate()      (0.94)
    "Validates user credentials and creates session"

  src/auth/oauth.py:123          verify_oauth_token() (0.88)
    "Validates OAuth2 token and extracts user identity"

  src/api/middleware.py:67       check_api_key()     (0.86)
    "Validates API key and authenticates request"

Medium Confidence (score 0.70-0.85):
  src/auth/session.py:89         validate_session()  (0.79)
  src/auth/password.py:34        verify_password()   (0.75)
  ... 3 more

Next: reveal semantic://like:src/auth/login.py#authenticate --explain
```

**Phase 2 Enhancements:**
- Multi-language support
- Documentation search
- Cross-resource semantic queries
- Fine-tuned embeddings for code

---

#### Unified Implementation Roadmap

**Phase 1 (Practical - v1.2)**:
- Built-in behavior patterns (AST-based)
- Custom pattern configuration
- Security/performance use cases
- **No ML dependencies** (fast, lightweight)
- Effort: 3-4 weeks

**Phase 2 (Advanced - v1.3+)**:
- Embeddings-based search
- Natural language queries
- Semantic similarity scoring
- **Requires ML dependencies** (sentence-transformers, faiss)
- Effort: 6+ weeks

**Design Decision**: Start with practical patterns (Phase 1), add ML later (Phase 2)
- Phase 1 delivers immediate value (security/performance audits)
- Phase 2 adds advanced search for complex queries
- Progressive enhancement: works without ML, better with it

**Source**: Merged existing plan (embeddings) + SDMS audit proposal (behavior patterns)

---

### 8. live:// - Real-Time Resource Monitoring

**Purpose:** Stream live changes/events from resources

**Syntax:**
```
live://<resource>[/stream][?options]
```

**Examples:**
```bash
# Watch database queries
reveal live://mysql://prod/queries --tail 10

# Monitor API requests
reveal live://https://api.example.com/traffic

# Watch container logs
reveal live://docker://app/logs --follow

# Monitor file changes
reveal live://file://./src --watch

# Watch Git repository
reveal live://git://. --events
```

**Implementation Notes:**
- Streaming adapter protocol
- Buffering and rate limiting
- Progressive disclosure of streaming data
- Output compatible with reveal's tree format

**Stream Types:**
- `queries` - Database query log
- `traffic` - HTTP request log
- `logs` - Container/service logs
- `events` - System events (file changes, commits)

**Output Structure:**
```
Live Stream: mysql://prod/queries
Monitoring query log... (Ctrl+C to stop)

[12:45:32] SELECT * FROM users WHERE id = 42 (3ms)
[12:45:33] INSERT INTO posts (...) VALUES (...) (5ms)
[12:45:34] SELECT posts.* FROM posts
           JOIN users ON ... (127ms) ⚠️  SLOW

Hot queries (last 5 min):
  SELECT * FROM users WHERE id = ?        (847 times, avg 2ms)
  SELECT posts.* FROM posts WHERE ...     (234 times, avg 8ms)
  UPDATE users SET last_seen = ? ...      (156 times, avg 4ms)

Slow queries (> 100ms):
  SELECT posts.* FROM posts JOIN users... (127ms) - just now

Next: reveal trace://mysql://prod/explain?query="..." --optimize
```

**Phase 1 Implementation:**
- Docker logs streaming
- File watch (inotify)
- Basic MySQL query log parsing

**Phase 2 Enhancements:**
- API request monitoring
- Database slow query detection
- Performance anomaly detection

---

### 9. merge:// - Multi-Resource Composite Views

**Purpose:** Combine multiple resources into unified view

**Syntax:**
```
merge://<resource1>+<resource2>+...[?view=<view_type>]
```

**Examples:**
```bash
# Compare multiple environments
reveal merge://mysql://prod+mysql://staging+mysql://dev

# Full stack view
reveal merge://mysql://db+ast://backend+ast://frontend?view=architecture

# Multi-service architecture
reveal merge://ast://service1+ast://service2+docker-compose://.

# Combined deployment view
reveal merge://docker://+mysql://+redis://
```

**Implementation Notes:**
- Composite adapter that wraps multiple adapters
- View types determine how resources are combined
- Unified output format
- Detect relationships between merged resources

**View Types:**
- `compare` - Side-by-side comparison
- `architecture` - Unified architecture diagram
- `dependencies` - Cross-resource dependency graph
- `consistency` - Consistency checks

**Output Structure:**
```
Merged View: mysql://prod + mysql://staging + mysql://dev
View Type: compare

Tables (consistency check):
  users              ✅ ✅ ✅  (identical in all)
  posts              ✅ ⚠️ ❌  (schema differs)
     Prod:    status ENUM('draft','published','archived')
     Staging: status ENUM('draft','published')
     Dev:     status VARCHAR(20)

  analytics          ✅ ❌ ❌  (only in prod)

Summary:
  Identical: 8 tables
  Partial match: 3 tables
  Missing in some: 1 table

Next: reveal merge://mysql://prod/posts+mysql://staging/posts --diff
```

**Phase 1 Implementation:**
- Basic merge of 2 resources
- Comparison view
- Side-by-side display

**Phase 2 Enhancements:**
- Dependency detection between resources
- Architecture view
- Consistency validation

---

### 10. meta:// - Reveal Metadata and Capabilities

**Purpose:** Explore reveal itself and available adapters

**Syntax:**
```
meta://adapters|config|cache|health
```

**Examples:**
```bash
# List all available adapters
reveal meta://adapters

# Show configuration
reveal meta://config

# Show cache status (for semantic://, ast:// indexes)
reveal meta://cache

# Health check all adapters
reveal meta://health
```

**Output Structure:**
```
Reveal Metadata: Adapters

Core Adapters (always available):
  file://           FileAdapter v1.0 ✅
  python://         PythonAnalyzer v1.0 ✅
  javascript://     JavaScriptAnalyzer v1.0 ✅

Optional Adapters (installed):
  mysql://          MySQLAdapter v0.8 ✅
  postgresql://     PostgreSQLAdapter v0.8 ✅
  docker://         DockerAdapter v0.8 ✅

Optional Adapters (not installed):
  ast://            ASTQueryAdapter v0.9 ❌
     Install: pip install reveal-cli[advanced]

  semantic://       SemanticSearchAdapter v0.9 ❌
     Install: pip install reveal-cli[semantic]

Advanced Adapters (experimental):
  diff://           DiffAdapter v0.9 (alpha)
  query://          QueryAdapter v0.9 (alpha)
  graph://          GraphAdapter v0.9 (alpha)

Next: reveal meta://health  # Test all adapters
```

---

## 🗺️ Implementation Roadmap

### Phase 1: Foundation (Post v1.0)
**Goal:** Prove advanced URI concepts with 1-2 adapters

**Timeline:** 2-3 months

**Deliverables:**
- [ ] `ast://` adapter with basic queries
- [ ] `diff://` adapter for files and databases
- [ ] `meta://` adapter for introspection
- [ ] Query parameter framework
- [ ] Advanced adapter protocol extensions

**Success Metrics:**
- ast:// can query complexity, calls, implements
- diff:// works for file and mysql resources
- Documentation and examples published

---

### Phase 2: Query and Graph (Post v1.1)
**Goal:** Enable cross-resource analysis

**Timeline:** 2-3 months

**Deliverables:**
- [ ] `query://` adapter for cross-resource search
- [ ] `graph://` adapter for relationship visualization
- [ ] Query planner and result aggregator
- [ ] Export formats (dot, mermaid)

**Success Metrics:**
- query:// can find identifiers across 3+ resource types
- graph:// generates call graphs and foreign key diagrams
- Performance: queries complete in <1s for medium codebases

---

### Phase 3: Temporal and Semantic (Post v1.2)
**Goal:** Add intelligence and time dimension

**Timeline:** 3-4 months

**Deliverables:**
- [ ] `time://` adapter with Git integration
- [ ] `semantic://` adapter with embedding search
- [ ] Schema evolution tracking
- [ ] Semantic index builder

**Success Metrics:**
- time:// can show code/schema at any git commit
- semantic:// finds functions by natural language description
- Semantic search accuracy >80% for common queries

---

### Phase 4: Live and Trace (Post v1.3)
**Goal:** Real-time and runtime insights

**Timeline:** 2-3 months

**Deliverables:**
- [ ] `live://` adapter for streaming logs
- [ ] `trace://` adapter for profiling data
- [ ] Performance anomaly detection
- [ ] Hot path identification

**Success Metrics:**
- live:// streams container logs efficiently
- trace:// identifies performance bottlenecks
- Progressive disclosure of trace data

---

### Phase 5: Composition and Merge (Post v1.4)
**Goal:** Unified views of complex systems

**Timeline:** 2-3 months

**Deliverables:**
- [ ] `merge://` adapter for composite views
- [ ] Consistency checking framework
- [ ] Architecture diagram generation
- [ ] Full stack visualization

**Success Metrics:**
- merge:// combines 3+ resources coherently
- Consistency checks find schema mismatches
- Architecture views show service dependencies

---

## 🎯 Success Criteria

### Performance Targets
- **Structure queries:** <100ms for all URI schemes
- **Detail queries:** <500ms for most resources
- **Complex queries:** <2s for cross-resource queries
- **Memory usage:** <100MB for typical operations

### User Experience
- **Consistent UX:** All adapters follow progressive disclosure
- **Clear errors:** Helpful messages for missing dependencies
- **Documentation:** Every URI scheme has examples
- **Composability:** URIs can be chained/nested

### Adoption Metrics
- **Downloads:** Advanced features in 20% of installations
- **Usage:** ast:// and diff:// most popular advanced features
- **Feedback:** GitHub issues/discussions for new URI ideas
- **Community:** External contributions for new adapters

---

## 🔧 Technical Architecture

### Adapter Extensions

```python
# Advanced adapter protocol additions
class AdvancedResourceAdapter(ResourceAdapter):
    """Extended protocol for advanced adapters"""

    @abstractmethod
    def supports_queries(self) -> bool:
        """Does this adapter support query parameters?"""
        ...

    @abstractmethod
    def query(self, query_expr: str) -> Dict[str, Any]:
        """Execute query and return filtered results"""
        ...

    @abstractmethod
    def supports_composition(self) -> bool:
        """Can this adapter be composed with others?"""
        ...
```

### Query Language

**Simple query language for URI parameters:**

```
# Comparison operators
?field>value     # Greater than
?field<value     # Less than
?field=value     # Equals
?field~pattern   # Matches regex

# Logical operators
?field1>X&field2<Y    # AND
?field1>X|field2>Y    # OR

# Functions
?calls(function_name)
?implements(interface)
?contains(text)
```

### Composition Framework

**URI composition patterns:**

```python
# Diff composition
diff://<resource1> vs <resource2>

# Merge composition
merge://<resource1>+<resource2>+...

# Time composition
time://<resource>@<timestamp>

# Query composition
query://<expr> --in <resource1>,<resource2>

# Nested composition
diff://time:mysql://prod@yesterday vs mysql://prod
```

---

## 💡 Design Patterns

### Progressive Disclosure
All advanced URI schemes maintain reveal's core pattern:
1. **Structure first:** High-level overview
2. **Drill down:** Navigate to specific elements
3. **Extract:** Get full details on demand

### Token Efficiency
Optimize output for AI agents:
- Concise summaries with counts
- Clear hierarchy (tree format)
- Actionable "Next" hints
- JSON output option for programmatic use

### Graceful Degradation
Advanced features should fail gracefully:
```bash
reveal ast://./src?semantic_search="auth"
# If semantic search not available:
# ⚠️  Semantic search requires: pip install reveal-cli[semantic]
# Falling back to literal search...
```

### Composition Over Configuration
Prefer composable URIs over complex config:
```bash
# Good: Composable
reveal diff://time:mysql://prod@yesterday vs mysql://prod

# Avoid: Complex flags
reveal mysql://prod --time yesterday --compare-to-current
```

---

## 🛠️ Implementation Priorities

### High Priority (MVP for each phase)
1. **ast://** - Builds on existing analyzers, high utility
2. **diff://** - Immediately useful, moderate complexity
3. **query://** - Game-changer for multi-resource analysis

### Medium Priority (High value, moderate effort)
4. **graph://** - Natural extension of relationship tracking
5. **time://** - Requires Git integration but very useful
6. **trace://** - Powerful for debugging

### Lower Priority (Nice to have)
7. **semantic://** - Complex, requires ML dependencies
8. **live://** - Niche use case, complex implementation
9. **merge://** - Subset of query:// functionality

### Optional (Research phase)
10. **meta://** - Useful but not essential

---

## 📊 Resource Requirements

### Development Effort
- **Phase 1:** 1 developer, 3 months
- **Phase 2:** 1-2 developers, 3 months
- **Phase 3:** 2 developers, 4 months (semantic is complex)
- **Phase 4:** 1 developer, 3 months
- **Phase 5:** 1-2 developers, 3 months

**Total:** ~16 months with 1-2 developers

### Optional Dependencies

```toml
[project.optional-dependencies]
advanced = [
    "gitpython>=3.1.0",        # For time:// and Git integration
    "networkx>=3.0",           # For graph:// analysis
]

semantic = [
    "sentence-transformers>=2.2.0",  # For semantic://
    "faiss-cpu>=1.7.0",              # Fast similarity search
]

monitoring = [
    "watchdog>=3.0.0",         # For live:// file watching
    "docker>=6.1.0",           # For live:// container logs
]
```

---

## 🚧 Open Questions

1. **Query Language:** Should we use a standard query language (GraphQL, SQL-like) or custom?
2. **Semantic Backend:** Local models vs API-based embeddings?
3. **Caching Strategy:** How to cache AST indexes, embeddings, etc.?
4. **Performance:** Can we keep <100ms structure queries for complex graphs?
5. **Composition Limits:** How deep can URI composition go before it's confusing?
6. **Security:** How to handle sensitive data in traces/logs?

---

## 📚 Related Documents

**Planning:**
- [URI_ADAPTERS_MASTER_SPEC.md](./URI_ADAPTERS_MASTER_SPEC.md) - Foundation adapter system
- [GITHUB_INTEGRATION_GUIDE.md](./GITHUB_INTEGRATION_GUIDE.md) - GitHub adapter specifics

**Public Docs:**
- [external-git/ROADMAP.md](../../external-git/ROADMAP.md) - Public roadmap
- [external-git/docs/ARCHITECTURE.md](../../external-git/docs/ARCHITECTURE.md) - Codebase guide

---

## 🎯 Next Steps

1. **Validate concepts:** Get feedback on URI scheme designs
2. **Prioritize:** Which schemes deliver most value soonest?
3. **Prototype:** Build proof-of-concept for ast:// adapter
4. **Document:** Create user-facing docs for advanced URIs
5. **Community:** Share ideas, gather use cases

---

**Last Updated:** 2025-12-02
**Status:** Conceptual - awaiting Phase 1 completion of basic URI adapters
