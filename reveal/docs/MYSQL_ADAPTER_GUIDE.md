# MySQL Adapter Guide (mysql://)

**Adapter**: `mysql://`
**Purpose**: MySQL database inspection with health monitoring, performance analysis, and replication status
**Type**: Database adapter
**Output Formats**: text, json, grep

## Table of Contents

1. [Quick Start](#quick-start)
2. [URI Syntax](#uri-syntax)
3. [Credential Resolution](#credential-resolution)
4. [Database Overview](#database-overview)
5. [Elements (Progressive Disclosure)](#elements-progressive-disclosure)
6. [Health Checks](#health-checks)
7. [Performance Analysis](#performance-analysis)
8. [Index Usage Analysis](#index-usage-analysis)
9. [Time Context & Snapshots](#time-context--snapshots)
10. [Query Parameters](#query-parameters)
11. [CLI Flags](#cli-flags)
12. [Output Types](#output-types)
13. [Workflows](#workflows)
14. [Integration Examples](#integration-examples)
15. [Performance & Best Practices](#performance--best-practices)
16. [Troubleshooting](#troubleshooting)
17. [Limitations](#limitations)
18. [Tips & Best Practices](#tips--best-practices)
19. [Related Documentation](#related-documentation)
20. [FAQ](#faq)

---

## Quick Start

```bash
# 1. Install dependency (if not already installed)
pip install reveal-cli[database]
# OR
pip install pymysql

# 2. Configure credentials (recommended: ~/.my.cnf)
cat > ~/.my.cnf <<EOF
[client]
host = localhost
port = 3306
user = myuser
password = mypassword
EOF
chmod 600 ~/.my.cnf

# 3. Quick health overview (uses ~/.my.cnf)
reveal mysql://

# 4. Health checks with thresholds
reveal mysql://localhost --check

# 5. Explore specific elements
reveal mysql://localhost/connections
reveal mysql://localhost/performance
reveal mysql://localhost/innodb
reveal mysql://localhost/replication
reveal mysql://localhost/storage

# 6. Remote database inspection
reveal mysql://user:pass@prod.example.com:3306/innodb

# 7. Find unused indexes
reveal mysql://localhost/indexes --format=json | jq '.unused[]'

# 8. Monitor storage growth
reveal mysql://localhost/storage --format=json | \
  jq '{time: .snapshot_time, total_gb: .total_size_gb, largest: .largest_db}'
```

**Why use mysql://?**
- **Token efficient**: ~100 tokens for health snapshot vs 5000+ for raw SQL output
- **DBA-friendly**: Industry-standard tuning ratios, not raw counters
- **Time-accurate**: All metrics include snapshot timestamps (uses MySQL server clock)
- **Progressive disclosure**: Start with overview, drill into specific areas
- **Health checks**: Automated pass/warn/fail thresholds for production monitoring
- **Index analysis**: Find unused indexes with performance_schema reset detection

---

## URI Syntax

```
mysql://[user:password@]host[:port][/element]
```

### Components

| Component | Required | Default | Description |
|-----------|----------|---------|-------------|
| `user` | No | From credentials | MySQL username |
| `password` | No | From credentials | MySQL password |
| `host` | No | `localhost` | MySQL server hostname/IP |
| `port` | No | `3306` | MySQL server port |
| `element` | No | (overview) | Specific element to inspect |

### Credential Resolution Order

1. **URI credentials**: `mysql://user:pass@host:3306`
2. **Environment variables**: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`
3. **~/.my.cnf**: `[client]` section (RECOMMENDED for production)

### Examples

```bash
# Auto-connect using ~/.my.cnf (simplest)
reveal mysql://

# Explicit host only (use ~/.my.cnf for credentials)
reveal mysql://localhost

# Full credentials in URI
reveal mysql://myuser:mypass@localhost:3306

# Remote database with element
reveal mysql://prod.example.com/innodb

# Element only (use ~/.my.cnf for connection)
reveal mysql:///storage
```

---

## Credential Resolution

### Method 1: ~/.my.cnf (RECOMMENDED)

**Best for**: Production databases, shared credentials, security

```bash
# Create ~/.my.cnf with credentials
cat > ~/.my.cnf <<EOF
[client]
host = prod.example.com
port = 3306
user = readonly_user
password = secure_password
EOF

# Secure the file (MySQL requires this)
chmod 600 ~/.my.cnf

# Use without credentials in URI
reveal mysql://
reveal mysql:///connections
reveal mysql:// --check
```

**Why use ~/.my.cnf?**
- ✅ No credentials in command history
- ✅ Same config as `mysql` CLI tool
- ✅ Secure file permissions (600)
- ✅ Works with all reveal commands
- ✅ Production validated (tested with 189GB MySQL 8.0.35)

### Method 2: Environment Variables

**Best for**: CI/CD pipelines, containerized environments

```bash
# Set credentials via environment
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
export MYSQL_USER=myuser
export MYSQL_PASSWORD=mypass
export MYSQL_DATABASE=mydb  # optional

# Use without URI credentials
reveal mysql://
reveal mysql://localhost/performance
```

### Method 3: URI Credentials

**Best for**: One-off queries, testing, different servers

```bash
# Full credentials in URI
reveal mysql://user:pass@host:3306

# Password with special characters (URL-encode)
reveal mysql://user:p%40ssw0rd%21@host:3306

# Different users for different queries
reveal mysql://readonly@prod.db.com/storage
reveal mysql://admin@prod.db.com --check
```

**⚠️ Warning**: URI credentials appear in shell history and process lists.

---

## Database Overview

The default view (`mysql://host`) provides a DBA-friendly health snapshot:

```bash
reveal mysql://localhost
```

**Returns** (~100 tokens):

```
MySQL Server: localhost:3306
Version: 8.0.35-0ubuntu0.22.04.1
Uptime: 15d 7h 23m
Server Start: 2025-01-29T08:30:00+00:00

Connection Health:
  Current: 12/151 (7.9%)
  Max Used: 45/151 (29.8%) - No connection rejections since server start
  Note: If max_used_pct was 100%, connections were rejected

Performance:
  QPS: 156.3
  Slow Queries: 234 total (0.12% of all queries since server start)
  Threads Running: 3

InnoDB Health:
  Buffer Pool Hit Rate: 99.87% (since server start)
  Status: healthy
  Row Lock Waits: 12 (since server start)
  Deadlocks: 0 (since server start)

Replication:
  Role: Slave
  Lag: 2s
  IO Running: true
  SQL Running: true

Storage:
  Total Size: 45.67 GB
  Database Count: 8
  Largest DB: production (38.45 GB)

Resource Limits:
  Open Files: 234/10000 (2.3%)
  Note: Approaching limit (>75%) can cause "too many open files" errors

Health Status: ⚠️ WARNING
Health Issues:
  - Replication lag (2s)

Next Steps:
  reveal mysql://localhost/connections       # Connection details
  reveal mysql://localhost/performance       # Query performance
  reveal mysql://localhost/innodb            # InnoDB details
  reveal mysql://localhost --check           # Run health checks
```

**Key Sections**:
- **Connection Health**: Current usage, max usage, rejection detection
- **Performance**: QPS, slow queries, active threads
- **InnoDB Health**: Buffer pool hit rate, locks, deadlocks
- **Replication**: Role (master/slave/standalone), lag, thread status
- **Storage**: Total size, database count, largest database
- **Resource Limits**: Open files, approaching threshold warnings
- **Health Status**: Overall assessment (✅ HEALTHY / ⚠️ WARNING / ❌ CRITICAL)
- **Next Steps**: Suggested follow-up commands

---

## Elements (Progressive Disclosure)

Use `/element` to drill into specific areas:

### Available Elements

| Element | Description | Use Case |
|---------|-------------|----------|
| `connections` | Connection pool and processlist | Debug connection exhaustion, find blocking queries |
| `performance` | Query performance metrics | Identify slow queries, analyze QPS |
| `innodb` | InnoDB buffer pool and engine status | Optimize buffer pool, check lock waits |
| `replication` | Replication status and lag | Monitor slave health, check replication threads |
| `storage` | Database and table sizes | Track storage growth, find largest tables |
| `storage/<db>` | Specific database tables | Analyze individual database size breakdown |
| `errors` | Error indicators | Check for connection errors, aborted clients |
| `variables` | Server configuration variables | Review key settings (max_connections, buffer pool) |
| `health` | Comprehensive health check | Full health overview (same as default view) |
| `databases` | Database list | Enumerate all databases |
| `indexes` | Index usage statistics | Find unused indexes, optimize queries |
| `slow-queries` | Slow query log analysis | Analyze slow query patterns (requires slow_log) |

### Element Examples

#### 1. Connections

```bash
reveal mysql://localhost/connections
```

**Returns**:
```
Snapshot Time: 2025-02-14T08:45:23+00:00
Server Start: 2025-01-29T08:30:00+00:00
Uptime: 15d 23h 15m

Total Connections: 45

By State:
  Sleep: 38
  Query: 5
  Sending data: 2

Long Running Queries (>5s):
  ID: 12345
  User: app_user
  DB: production
  Time: 127s
  State: Sending data
  Query: SELECT * FROM large_table WHERE...
```

**Use cases**:
- Debug connection pool exhaustion
- Find long-running queries blocking resources
- Identify connection states (Sleep, Query, Sending data)
- Monitor active query count

#### 2. Performance

```bash
reveal mysql://localhost/performance
```

**Returns**:
```
Snapshot Time: 2025-02-14T08:45:23+00:00
Server Start: 2025-01-29T08:30:00+00:00
Measurement Window: 15d 23h 15m

Query Performance:
  Total Questions: 12,456,789
  QPS: 156.3 (avg since server start)
  Slow Queries: 234 (0.12% of all queries)
  Threads Running: 3

DBA Tuning Ratios:
  Table Scan Ratio: 12.5% (✅ PASS <25%)
    - Full table scans / queries ratio
    - Lower is better (use indexes instead of scans)

  Thread Cache Miss Rate: 3.2% (✅ PASS <10%)
    - Thread creation overhead
    - Lower is better (cache more threads)

  Temp Tables to Disk: 18.7% (✅ PASS <25%)
    - Temp tables written to disk vs memory
    - Lower is better (increase tmp_table_size)

Query Cache (if enabled):
  Hit Rate: 85.3%
  Prunes: 1,234 (cache evictions)
```

**Use cases**:
- Identify slow query patterns
- Check if indexes are being used (table scan ratio)
- Optimize thread cache size
- Tune temporary table settings

#### 3. InnoDB

```bash
reveal mysql://localhost/innodb
```

**Returns**:
```
Snapshot Time: 2025-02-14T08:45:23+00:00
Server Start: 2025-01-29T08:30:00+00:00

InnoDB Buffer Pool:
  Size: 8.00 GB
  Hit Rate: 99.87% (since server start)
  Reads: 1,234,567
  Read Requests: 987,654,321
  Status: ✅ healthy (>99% is excellent)

Lock Information:
  Current Waits: 0
  Row Lock Waits: 12 (since server start)
  Avg Wait Time: 1.2 seconds
  Deadlocks: 0 (since server start)

Pending I/O:
  Reads: 0
  Writes: 2
  Log Flushes: 0

Data:
  Rows Read: 45,678,901
  Rows Inserted: 123,456
  Rows Updated: 234,567
  Rows Deleted: 12,345
```

**Use cases**:
- Optimize buffer pool size (target >99% hit rate)
- Debug lock contention issues
- Monitor I/O performance
- Track data modification patterns

#### 4. Replication

```bash
reveal mysql://localhost/replication
```

**Returns**:
```
Snapshot Time: 2025-02-14T08:45:23+00:00

Replication Status:
  Role: Slave
  Lag: 2 seconds
  IO Thread: Running ✅
  SQL Thread: Running ✅

  Master Info:
    Master Host: master.example.com
    Master Port: 3306
    Master Log File: mysql-bin.000123
    Master Log Position: 456789012

  Relay Info:
    Relay Log File: relay-bin.000045
    Relay Log Position: 234567890

  Last Error: (none)

Health Status: ⚠️ WARNING (lag > 60s threshold)
```

**Use cases**:
- Monitor replication lag
- Verify replication threads are running
- Debug replication errors
- Track master/slave position

#### 5. Storage

```bash
reveal mysql://localhost/storage
```

**Returns**:
```
Snapshot Time: 2025-02-14T08:45:23+00:00
Server Start: 2025-01-29T08:30:00+00:00

Total Storage: 45.67 GB
Database Count: 8

Databases by Size:
  production: 38.45 GB
  analytics: 5.23 GB
  staging: 1.45 GB
  development: 0.34 GB
  test: 0.12 GB
  backup: 0.05 GB
  logs: 0.02 GB
  temp: 0.01 GB

Largest Database: production (38.45 GB)
```

**Use cases**:
- Track storage growth trends
- Identify largest databases
- Plan capacity
- Find databases to archive/purge

#### 6. Storage (Specific Database)

```bash
reveal mysql://localhost/storage/production
```

**Returns**:
```
Snapshot Time: 2025-02-14T08:45:23+00:00

Database: production
Total Size: 38.45 GB

Tables by Size:
  users: 12.34 GB (32.1%)
  orders: 10.23 GB (26.6%)
  products: 8.45 GB (22.0%)
  logs: 4.56 GB (11.9%)
  sessions: 1.87 GB (4.9%)
  cache: 0.78 GB (2.0%)
  metadata: 0.22 GB (0.6%)
```

**Use cases**:
- Identify largest tables in a database
- Find candidates for archiving
- Analyze table growth patterns
- Optimize storage allocation

#### 7. Indexes

```bash
reveal mysql://localhost/indexes
```

**Returns**:
```
Snapshot Time: 2025-02-14T08:45:23+00:00
Server Start: 2025-01-29T08:30:00+00:00
Measurement Basis: since_server_start
Measurement Start: 2025-01-29T08:30:00+00:00

Performance Schema Status:
  Counters Reset Detected: false
  Note: Metrics are accurate since server start

Most Used Indexes (Top 20):
  DB: production | Table: users | Index: idx_email
    Total Accesses: 12,345,678
    Read Accesses: 12,345,600 (99.99%)
    Write Accesses: 78 (0.01%)

  DB: production | Table: orders | Index: idx_user_id
    Total Accesses: 9,876,543
    Read Accesses: 9,876,500 (99.99%)
    Write Accesses: 43 (0.01%)

Unused Indexes (50):
  DB: production | Table: legacy_users | Index: idx_old_field
  DB: production | Table: products | Index: idx_deprecated
  DB: staging | Table: test_data | Index: idx_unused

Unused Count: 50 indexes

Note: If counters_reset_detected is true, measurement basis becomes
      'since_reset' with reset timestamp in measurement_start_time.
      This prevents misinterpretation of fresh counters as "unused".
```

**Use cases**:
- Find unused indexes consuming storage and write overhead
- Identify most-used indexes for optimization
- Detect performance_schema counter resets automatically
- Make informed index removal decisions with confidence

#### 8. Slow Queries

```bash
reveal mysql://localhost/slow-queries
```

**Returns** (requires slow query log enabled):
```
Period: 24 hours

Summary:
  Total Slow Queries: 234
  Min Time: 5.2s
  Max Time: 127.5s
  Avg Time: 18.3s
  Total Rows Examined: 45,678,901

Top 20 Slow Queries:
  Start: 2025-02-14T08:30:15+00:00
  User: app_user@10.0.1.23
  Time: 127.5s
  Lock Time: 0.2s
  Rows Sent: 10
  Rows Examined: 12,345,678
  Query: SELECT * FROM users u JOIN orders o ON u.id = o.user_id WHERE...
```

**Use cases**:
- Identify slowest queries in last 24 hours
- Analyze row examination patterns
- Find queries needing optimization
- Track slow query trends

---

## Health Checks

Use `--check` flag to run automated health checks with pass/warn/fail thresholds:

```bash
reveal mysql://localhost --check
```

**Returns**:
```
Health Check Results

Status: ⚠️ WARNING
Exit Code: 1
Summary: 7 total, 5 passed, 2 warnings, 0 failures

Checks:
  ✅ PASS - Table Scan Ratio: 12.5% (threshold: <10%)
     Severity: high

  ✅ PASS - Thread Cache Miss Rate: 3.2% (threshold: <10%)
     Severity: medium

  ⚠️ WARN - Temp Disk Ratio: 32.1% (threshold: <25%)
     Severity: medium

  ⚠️ WARN - Max Used Connections %: 85.3% (threshold: <80%)
     Severity: critical

  ✅ PASS - Open Files %: 23.4% (threshold: <75%)
     Severity: critical

  ✅ PASS - Current Connection %: 45.2% (threshold: <80%)
     Severity: high

  ✅ PASS - Buffer Hit Rate: 99.87% (threshold: >99%)
     Severity: high
```

### Show Only Failures

```bash
reveal mysql://localhost --check --only-failures
```

**Returns**: Only checks with `warning` or `failure` status (hides passed checks)

### Health Check Configuration

Health checks are configurable via YAML files:

**Locations** (in order of precedence):
1. `./.reveal/mysql-health-checks.yaml` (project)
2. `~/.config/reveal/mysql-health-checks.yaml` (user)
3. `/etc/reveal/mysql-health-checks.yaml` (system)
4. Built-in defaults (fallback)

**Example config** (`~/.config/reveal/mysql-health-checks.yaml`):

```yaml
checks:
  - name: Table Scan Ratio
    metric: table_scan_ratio
    pass_threshold: 10
    warn_threshold: 25
    severity: high
    operator: '<'

  - name: Thread Cache Miss Rate
    metric: thread_cache_miss_rate
    pass_threshold: 10
    warn_threshold: 25
    severity: medium
    operator: '<'

  - name: Temp Disk Ratio
    metric: temp_disk_ratio
    pass_threshold: 25
    warn_threshold: 50
    severity: medium
    operator: '<'

  - name: Max Used Connections %
    metric: max_used_connections_pct
    pass_threshold: 80
    warn_threshold: 100
    severity: critical
    operator: '<'

  - name: Open Files %
    metric: open_files_pct
    pass_threshold: 75
    warn_threshold: 90
    severity: critical
    operator: '<'

  - name: Current Connection %
    metric: connection_pct
    pass_threshold: 80
    warn_threshold: 95
    severity: high
    operator: '<'

  - name: Buffer Hit Rate
    metric: buffer_hit_rate
    pass_threshold: 99
    warn_threshold: 95
    severity: high
    operator: '>'
```

### Available Metrics

| Metric | Description | Good Value | Operator |
|--------|-------------|------------|----------|
| `table_scan_ratio` | Full table scans vs indexed queries | <10% | `<` |
| `thread_cache_miss_rate` | Thread creation overhead | <10% | `<` |
| `temp_disk_ratio` | Temp tables written to disk | <25% | `<` |
| `max_used_connections_pct` | Peak connection usage | <80% | `<` |
| `open_files_pct` | Open file handle usage | <75% | `<` |
| `connection_pct` | Current connection usage | <80% | `<` |
| `buffer_hit_rate` | InnoDB buffer pool efficiency | >99% | `>` |

### Exit Codes

| Code | Status | Meaning |
|------|--------|---------|
| `0` | Pass | All checks passed |
| `1` | Warning | One or more warnings |
| `2` | Failure | One or more failures |

**Use in CI/CD**:

```bash
#!/bin/bash
reveal mysql://prod.db.com --check --only-failures --format=json

if [ $? -eq 0 ]; then
  echo "✅ All health checks passed"
elif [ $? -eq 1 ]; then
  echo "⚠️ Health warnings detected"
  exit 1
elif [ $? -eq 2 ]; then
  echo "❌ Health check failures"
  exit 2
fi
```

---

## Performance Analysis

### DBA Tuning Ratios

The `/performance` element includes industry-standard DBA tuning ratios:

```bash
reveal mysql://localhost/performance --format=json | \
  jq '.tuning_ratios'
```

**Returns**:
```json
{
  "table_scan_ratio": "12.5%",
  "thread_cache_miss_rate": "3.2%",
  "temp_tables_to_disk_ratio": "18.7%"
}
```

#### 1. Table Scan Ratio

**Formula**: `(Handler_read_rnd_next + Handler_read_rnd) / (Handler_read_rnd_next + Handler_read_rnd + Handler_read_first + Handler_read_key + Handler_read_next)`

**Interpretation**:
- **<10%**: ✅ Excellent - Queries are using indexes
- **10-25%**: ⚠️ Warning - Some queries doing full table scans
- **>25%**: ❌ Critical - Many queries not using indexes

**How to fix**:
```bash
# Find queries doing table scans
reveal mysql://localhost/slow-queries --format=json | \
  jq '.top_queries[] | select(.rows_examined > 10000)'

# Check index usage
reveal mysql://localhost/indexes --format=json | \
  jq '.unused[]'

# Add missing indexes
# mysql> CREATE INDEX idx_column ON table(column);
```

#### 2. Thread Cache Miss Rate

**Formula**: `Threads_created / Connections * 100`

**Interpretation**:
- **<10%**: ✅ Excellent - Thread cache is effective
- **10-25%**: ⚠️ Warning - Consider increasing thread_cache_size
- **>25%**: ❌ Critical - Thread creation overhead is high

**How to fix**:
```bash
# Check current thread_cache_size
reveal mysql://localhost/variables --format=json | \
  jq '.variables.thread_cache_size'

# Increase thread cache (MySQL config)
# [mysqld]
# thread_cache_size = 128
```

#### 3. Temp Tables to Disk Ratio

**Formula**: `Created_tmp_disk_tables / Created_tmp_tables * 100`

**Interpretation**:
- **<25%**: ✅ Excellent - Most temp tables fit in memory
- **25-50%**: ⚠️ Warning - Increase tmp_table_size or max_heap_table_size
- **>50%**: ❌ Critical - Many temp tables spilling to disk

**How to fix**:
```bash
# Check current settings
reveal mysql://localhost/variables --format=json | \
  jq '.variables | {tmp_table_size, max_heap_table_size}'

# Increase temp table size (MySQL config)
# [mysqld]
# tmp_table_size = 64M
# max_heap_table_size = 64M
```

---

## Index Usage Analysis

The `/indexes` element provides index usage statistics with automatic performance_schema counter reset detection:

```bash
reveal mysql://localhost/indexes
```

### Reset Detection

MySQL's `performance_schema` counters can be reset manually (`TRUNCATE TABLE performance_schema.*`). This causes index usage counters to restart from zero, potentially making actually-used indexes appear "unused".

**reveal detects this automatically**:

- **No reset detected**: `measurement_basis = "since_server_start"`
  - Counters are accurate since server boot
  - Safe to identify truly unused indexes

- **Reset detected**: `measurement_basis = "since_reset"`
  - Counters were reset after server start
  - Shows `likely_reset_time` timestamp
  - Interpret "unused" carefully (may have been used before reset)

**Detection logic**: If `performance_schema` oldest event is >1 hour newer than server start, counters were likely reset.

### Finding Unused Indexes

```bash
# List all unused indexes
reveal mysql://localhost/indexes --format=json | \
  jq -r '.unused[] | "\(.object_schema).\(.object_name).\(.index_name)"'

# Check if counters were reset
reveal mysql://localhost/indexes --format=json | \
  jq '{
    reset_detected: .performance_schema_status.counters_reset_detected,
    measurement_basis: .measurement_basis,
    measurement_start: .measurement_start_time
  }'

# Output:
# {
#   "reset_detected": false,
#   "measurement_basis": "since_server_start",
#   "measurement_start": "2025-01-29T08:30:00+00:00"
# }
```

### Most Used Indexes

```bash
# Top 10 most-used indexes
reveal mysql://localhost/indexes --format=json | \
  jq '.most_used[:10][] | {
    table: "\(.object_schema).\(.object_name)",
    index: .index_name,
    accesses: .total_accesses,
    read_pct: .read_pct
  }'
```

### Safe Index Removal Workflow

```bash
# 1. Verify no reset detected
reveal mysql://localhost/indexes --format=json | \
  jq '.performance_schema_status.counters_reset_detected'
# Should be: false

# 2. Check server uptime (want >1 week for confidence)
reveal mysql://localhost --format=json | \
  jq '.uptime, .server_start_time'

# 3. Find unused indexes
reveal mysql://localhost/indexes --format=json | \
  jq -r '.unused[] | "\(.object_schema).\(.object_name).\(.index_name)"'

# 4. Review specific index (ensure it's not a unique constraint)
# mysql> SHOW CREATE TABLE production.users;

# 5. Remove if safe (TEST IN STAGING FIRST)
# mysql> DROP INDEX idx_old_field ON production.legacy_users;
```

---

## Time Context & Snapshots

All mysql:// endpoints include **snapshot timing context** to ensure accurate interpretation of metrics:

### Timing Fields

| Field | Description | Example |
|-------|-------------|---------|
| `snapshot_time` | When data was collected (ISO 8601) | `2025-02-14T08:45:23+00:00` |
| `server_start_time` | When MySQL server booted (ISO 8601) | `2025-01-29T08:30:00+00:00` |
| `uptime_seconds` | Server uptime in seconds | `1389180` |
| `measurement_window` | Human-readable uptime | `15d 23h 15m` |

### Why Time Context Matters

**Example**: Storage growth tracking

```bash
# Snapshot 1 (Feb 1)
reveal mysql://localhost/storage --format=json | \
  jq '{time: .snapshot_time, total_gb: .total_size_gb}' > feb1.json
# {"time": "2025-02-01T08:00:00+00:00", "total_gb": 42.34}

# Snapshot 2 (Feb 14)
reveal mysql://localhost/storage --format=json | \
  jq '{time: .snapshot_time, total_gb: .total_size_gb}' > feb14.json
# {"time": "2025-02-14T08:00:00+00:00", "total_gb": 45.67}

# Calculate growth rate
echo "Growth: $(echo '45.67 - 42.34' | bc) GB in 13 days"
# Growth: 3.33 GB in 13 days
# Rate: 0.26 GB/day
```

### Clock Accuracy

reveal uses **MySQL's server clock** (`UNIX_TIMESTAMP()`) instead of local machine time:

**Why?**
- ✅ Correct for remote databases (no timezone issues)
- ✅ No clock drift between client and server
- ✅ Consistent across all endpoints
- ✅ Accurate for distributed monitoring

**Example**: Remote database monitoring

```bash
# Local machine: PST (UTC-8)
# MySQL server: Tokyo (UTC+9)

reveal mysql://tokyo.example.com/storage --format=json | \
  jq '.snapshot_time'
# "2025-02-14T17:45:23+00:00"  <- Correct UTC time from MySQL server

# WITHOUT server clock, would be off by 17 hours!
```

---

## Query Parameters

The mysql:// adapter does not use query parameters. All configuration is done via:
- URI elements (`/connections`, `/performance`, etc.)
- CLI flags (`--check`, `--only-failures`)
- Configuration files (`mysql-health-checks.yaml`)

---

## CLI Flags

### Standard Flags

| Flag | Description | Example |
|------|-------------|---------|
| `--format=<type>` | Output format (text, json, grep) | `reveal mysql://localhost --format=json` |
| `--check` | Run health checks with thresholds | `reveal mysql://localhost --check` |
| `--only-failures` | Show only warnings/failures | `reveal mysql://localhost --check --only-failures` |
| `--advanced` | Reserved for future enhanced checks | `reveal mysql://localhost --check --advanced` |

### Examples

```bash
# JSON output for parsing
reveal mysql://localhost --format=json

# Health checks only (text output)
reveal mysql://localhost --check

# Health checks (JSON) with only failures
reveal mysql://localhost --check --only-failures --format=json

# Grep-friendly output
reveal mysql://localhost --format=grep | grep -i "buffer"
```

---

## Output Types

### 1. mysql_health

**Use case**: Database health overview

**Schema**:
```json
{
  "contract_version": "1.0",
  "type": "mysql_health",
  "source": "localhost:3306",
  "source_type": "database",
  "snapshot_time": "2025-02-14T08:45:23+00:00",
  "server": "localhost:3306",
  "version": "8.0.35-0ubuntu0.22.04.1",
  "uptime": "15d 7h 23m",
  "server_start_time": "2025-01-29T08:30:00+00:00",
  "connection_health": {
    "current": 12,
    "max": 151,
    "percentage": "7.9%",
    "max_used": 45,
    "max_used_pct": "29.8%"
  },
  "performance": {
    "qps": "156.3",
    "slow_queries": "234 total (0.12% since start)",
    "threads_running": 3
  },
  "innodb_health": {
    "buffer_pool_hit_rate": "99.87%",
    "status": "healthy",
    "row_lock_waits": "12",
    "deadlocks": "0"
  },
  "replication": {
    "role": "Slave",
    "lag": 2,
    "io_running": true,
    "sql_running": true
  },
  "storage": {
    "total_size_gb": 45.67,
    "database_count": 8,
    "largest_db": "production (38.45 GB)"
  },
  "resource_limits": {
    "open_files": {
      "current": 234,
      "limit": 10000,
      "percentage": "2.3%"
    }
  },
  "health_status": "⚠️ WARNING",
  "health_issues": ["Replication lag (2s)"]
}
```

### 2. mysql_replication

**Use case**: Replication monitoring

**Schema**:
```json
{
  "contract_version": "1.0",
  "type": "mysql_replication",
  "source": "localhost:3306",
  "source_type": "database",
  "snapshot_time": "2025-02-14T08:45:23+00:00",
  "io_running": true,
  "sql_running": true,
  "lag_seconds": 2,
  "master_log_file": "mysql-bin.000123",
  "relay_log_file": "relay-bin.000045"
}
```

### 3. mysql_storage

**Use case**: Storage analysis

**Schema**:
```json
{
  "contract_version": "1.0",
  "type": "mysql_storage",
  "source": "localhost:3306",
  "source_type": "database",
  "snapshot_time": "2025-02-14T08:45:23+00:00",
  "databases": [
    {"name": "production", "size_gb": 38.45},
    {"name": "analytics", "size_gb": 5.23}
  ],
  "total_size_gb": 45.67
}
```

---

## Workflows

### Workflow 1: Quick Health Check

**Scenario**: Need to quickly assess database health

```bash
# 1. Get health overview
reveal mysql://localhost

# 2. Run automated health checks
reveal mysql://localhost --check

# 3. If issues found, investigate specific areas
reveal mysql://localhost/replication  # Check replication lag
reveal mysql://localhost/connections  # Check connection pool
reveal mysql://localhost/innodb       # Check buffer pool
```

**Output**: Health status, specific issues, pass/warn/fail checks

---

### Workflow 2: Debug Slow Performance

**Scenario**: Database is slow, need to find bottleneck

```bash
# 1. Check performance overview
reveal mysql://localhost/performance

# 2. Check InnoDB buffer pool hit rate (should be >99%)
reveal mysql://localhost/innodb

# 3. Find long-running queries
reveal mysql://localhost/connections

# 4. Analyze slow queries (last 24 hours)
reveal mysql://localhost/slow-queries

# 5. Check for blocking (row locks)
reveal mysql://localhost/innodb --format=json | jq '.row_lock_waits'

# 6. Review tuning ratios
reveal mysql://localhost/performance --format=json | jq '.tuning_ratios'
```

**Common findings**:
- Low buffer pool hit rate → Increase `innodb_buffer_pool_size`
- High table scan ratio → Add missing indexes
- High temp disk ratio → Increase `tmp_table_size`
- Long-running queries → Optimize queries

---

### Workflow 3: Production Database Monitoring (Remote)

**Scenario**: Monitor production database via ~/.my.cnf

```bash
# 1. Configure ~/.my.cnf with production credentials
cat > ~/.my.cnf <<EOF
[client]
host = prod.example.com
port = 3306
user = readonly_user
password = secure_password
EOF
chmod 600 ~/.my.cnf

# 2. Auto-connect for health overview
reveal mysql://

# 3. Run automated health checks
reveal mysql:// --check --only-failures

# 4. Check storage growth trends
reveal mysql:///storage --format=json | \
  jq '{
    time: .snapshot_time,
    total_gb: .total_size_gb,
    databases: .database_count,
    largest: .largest_db
  }'

# 5. Monitor replication lag (if slave)
reveal mysql:///replication --format=json | \
  jq '{lag: .lag, io: .io_running, sql: .sql_running}'

# 6. Find unused indexes (after 1+ week uptime)
reveal mysql:///indexes --format=json | \
  jq '{
    reset_detected: .performance_schema_status.counters_reset_detected,
    unused_count: .unused_count,
    uptime: .measurement_window
  }'
```

**Production tips**:
- ✅ Use `~/.my.cnf` for secure credentials
- ✅ Monitor with `--check --only-failures` (automated)
- ✅ Track storage growth daily (capture `snapshot_time`)
- ✅ Check replication lag < 60s
- ✅ Wait 1+ week uptime before removing unused indexes

---

### Workflow 4: Track Storage Growth Over Time

**Scenario**: Monitor database growth trends with accurate timestamps

```bash
# 1. Capture daily snapshots with timestamps
reveal mysql://localhost/storage --format=json | \
  jq '{
    snapshot_time: .snapshot_time,
    server_start: .server_start_time,
    total_gb: .total_size_gb,
    databases: [.databases[] | {name: .db_name, size_gb: .size_gb}]
  }' >> storage_history.jsonl

# 2. Compare snapshots at different times
cat storage_history.jsonl | jq -s '
  [.[] | {
    date: (.snapshot_time | split("T")[0]),
    total_gb: .total_gb
  }]
'

# 3. Calculate growth rate
cat storage_history.jsonl | jq -s '
  . as $snapshots |
  ($snapshots[-1].total_gb - $snapshots[0].total_gb) as $growth |
  ($snapshots[-1].snapshot_time | fromdateiso8601) -
  ($snapshots[0].snapshot_time | fromdateiso8601) as $days |
  {
    start_date: $snapshots[0].snapshot_time,
    end_date: $snapshots[-1].snapshot_time,
    growth_gb: $growth,
    days: ($days / 86400),
    rate_gb_per_day: ($growth / ($days / 86400))
  }
'

# 4. Find fastest-growing databases
cat storage_history.jsonl | jq -s '
  [.[-1].databases[] as $current |
   .[-7].databases[] as $week_ago |
   select($current.name == $week_ago.name) |
   {
     database: $current.name,
     current_gb: $current.size_gb,
     week_ago_gb: $week_ago.size_gb,
     growth_gb: ($current.size_gb - $week_ago.size_gb),
     growth_pct: (($current.size_gb - $week_ago.size_gb) / $week_ago.size_gb * 100)
   }
  ] | sort_by(.growth_gb) | reverse
'
```

**Why snapshot_time matters**:
- ✅ Accurate time-series analysis (no clock drift)
- ✅ Compare snapshots from different days/weeks
- ✅ Calculate growth rates correctly
- ✅ Works with remote databases (uses server clock)

---

### Workflow 5: Index Usage Analysis with Reset Detection

**Scenario**: Find unused indexes with confidence about data freshness

```bash
# 1. Check performance_schema status
reveal mysql://localhost/indexes --format=json | \
  jq '{
    reset_detected: .performance_schema_status.counters_reset_detected,
    measurement_basis: .measurement_basis,
    measurement_start: .measurement_start_time,
    uptime: .measurement_window
  }'

# Output:
# {
#   "reset_detected": false,
#   "measurement_basis": "since_server_start",
#   "measurement_start": "2025-01-29T08:30:00+00:00",
#   "uptime": "15d 23h 15m"
# }

# 2. If reset_detected is false AND uptime > 1 week:
#    Safe to identify unused indexes

# 3. Find unused indexes
reveal mysql://localhost/indexes --format=json | \
  jq -r '.unused[] |
    "\(.object_schema).\(.object_name).\(.index_name)"'

# 4. Check if unused index is a unique constraint
# mysql> SHOW CREATE TABLE production.users;

# 5. If safe to remove (TEST IN STAGING FIRST):
# mysql> DROP INDEX idx_old_field ON production.legacy_users;

# 6. If reset_detected is true:
#    Wait until uptime > measurement threshold before trusting "unused"
reveal mysql://localhost/indexes --format=json | \
  jq '{
    reset_detected: .performance_schema_status.counters_reset_detected,
    server_uptime: .uptime_seconds,
    oldest_event: .performance_schema_status.oldest_event_timestamp,
    interpretation: "Counters were reset - wait longer before removing unused indexes"
  }'
```

**Confidence thresholds**:
- **< 1 day uptime**: Too early, don't trust "unused"
- **1-7 days uptime**: Low confidence, monitor longer
- **> 1 week uptime**: High confidence (no reset detected)
- **> 1 month uptime**: Very high confidence

---

### Workflow 6: CI/CD Health Validation

**Scenario**: Automated database health checks in deployment pipeline

```bash
#!/bin/bash
# deploy-health-check.sh

set -e

DB_HOST="$1"
THRESHOLD="$2"  # pass, warning, failure

echo "🔍 Running MySQL health checks on ${DB_HOST}..."

# Run health checks (JSON output)
RESULT=$(reveal mysql://${DB_HOST} --check --format=json)

# Extract status and exit code
STATUS=$(echo "$RESULT" | jq -r '.status')
EXIT_CODE=$(echo "$RESULT" | jq -r '.exit_code')
FAILURES=$(echo "$RESULT" | jq -r '.checks[] | select(.status == "failure")')
WARNINGS=$(echo "$RESULT" | jq -r '.checks[] | select(.status == "warning")')

echo "Status: ${STATUS}"
echo "Exit Code: ${EXIT_CODE}"

# Show failures
if [ -n "$FAILURES" ]; then
  echo "❌ FAILURES:"
  echo "$RESULT" | jq -r '.checks[] |
    select(.status == "failure") |
    "  - \(.name): \(.value) (threshold: \(.threshold))"'
fi

# Show warnings
if [ -n "$WARNINGS" ]; then
  echo "⚠️ WARNINGS:"
  echo "$RESULT" | jq -r '.checks[] |
    select(.status == "warning") |
    "  - \(.name): \(.value) (threshold: \(.threshold))"'
fi

# Fail deployment based on threshold
if [ "$THRESHOLD" = "pass" ] && [ "$EXIT_CODE" -ne 0 ]; then
  echo "❌ Deployment blocked: Health checks must all pass"
  exit 1
elif [ "$THRESHOLD" = "warning" ] && [ "$EXIT_CODE" -eq 2 ]; then
  echo "❌ Deployment blocked: Health check failures detected"
  exit 1
fi

echo "✅ Health checks passed (threshold: ${THRESHOLD})"
exit 0
```

**Usage**:

```bash
# Strict: require all checks pass
./deploy-health-check.sh prod.example.com pass

# Moderate: allow warnings, block failures
./deploy-health-check.sh prod.example.com warning

# Permissive: only alert (don't block)
./deploy-health-check.sh prod.example.com failure || echo "⚠️ Health issues detected"
```

---

## Integration Examples

### Integration 1: Combine with jq

```bash
# Extract specific metrics
reveal mysql://localhost --format=json | \
  jq '{
    version: .version,
    uptime: .uptime,
    connections: .connection_health.percentage,
    buffer_hit_rate: .innodb_health.buffer_pool_hit_rate,
    health: .health_status
  }'

# Find slow queries over 30s
reveal mysql://localhost/connections --format=json | \
  jq '.long_running_queries[] | select(.time > 30)'

# Compare storage across databases
reveal mysql://localhost/storage --format=json | \
  jq '.databases | sort_by(.size_gb) | reverse | .[:5]'
```

### Integration 2: Monitoring Script

```bash
#!/bin/bash
# mysql-monitor.sh - Monitor MySQL health every 5 minutes

while true; do
  TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Capture health snapshot
  reveal mysql://localhost --format=json | \
    jq --arg ts "$TIMESTAMP" '{
      timestamp: $ts,
      qps: .performance.qps,
      connections_pct: .connection_health.percentage,
      buffer_hit_rate: .innodb_health.buffer_pool_hit_rate,
      replication_lag: .replication.lag,
      health_status: .health_status
    }' >> mysql_health_log.jsonl

  # Alert on issues
  HEALTH=$(reveal mysql://localhost --format=json | jq -r '.health_status')
  if [[ "$HEALTH" != *"HEALTHY"* ]]; then
    echo "⚠️ MySQL health issue: $HEALTH"
    # Send alert (email, Slack, PagerDuty, etc.)
  fi

  sleep 300  # 5 minutes
done
```

### Integration 3: Grafana Dashboard Data

```bash
# Export metrics for Grafana
reveal mysql://localhost --format=json | \
  jq '{
    qps: .performance.qps,
    connections_current: .connection_health.current,
    connections_max: .connection_health.max,
    connections_pct: (.connection_health.percentage | rtrimstr("%") | tonumber),
    buffer_hit_rate: (.innodb_health.buffer_pool_hit_rate | split("%")[0] | tonumber),
    storage_gb: .storage.total_size_gb,
    replication_lag: .replication.lag,
    slow_queries: (.performance.slow_queries | split(" ")[0] | tonumber)
  }' > grafana_metrics.json

# Send to Prometheus pushgateway
# curl -X POST http://pushgateway:9091/metrics/job/mysql_health \
#   --data-binary @grafana_metrics.json
```

### Integration 4: Storage Growth Alert

```bash
#!/bin/bash
# storage-growth-alert.sh - Alert on rapid storage growth

THRESHOLD_GB_PER_DAY=1.0

# Get current storage
CURRENT=$(reveal mysql://localhost/storage --format=json)
CURRENT_SIZE=$(echo "$CURRENT" | jq -r '.total_size_gb')
CURRENT_TIME=$(echo "$CURRENT" | jq -r '.snapshot_time')

# Read previous snapshot
if [ -f storage_previous.json ]; then
  PREV_SIZE=$(jq -r '.total_size_gb' storage_previous.json)
  PREV_TIME=$(jq -r '.snapshot_time' storage_previous.json)

  # Calculate growth rate (GB/day)
  GROWTH=$(echo "$CURRENT_SIZE - $PREV_SIZE" | bc)
  DAYS=$(echo "($(date -d "$CURRENT_TIME" +%s) - $(date -d "$PREV_TIME" +%s)) / 86400" | bc)
  RATE=$(echo "scale=2; $GROWTH / $DAYS" | bc)

  echo "Storage growth: ${GROWTH} GB in ${DAYS} days (${RATE} GB/day)"

  # Alert if exceeding threshold
  if (( $(echo "$RATE > $THRESHOLD_GB_PER_DAY" | bc -l) )); then
    echo "⚠️ ALERT: Storage growing faster than ${THRESHOLD_GB_PER_DAY} GB/day"
    # Send alert
  fi
fi

# Save current as previous
echo "$CURRENT" > storage_previous.json
```

### Integration 5: Python Integration

```python
#!/usr/bin/env python3
import subprocess
import json
from datetime import datetime

def get_mysql_health(host='localhost'):
    """Get MySQL health using reveal."""
    result = subprocess.run(
        ['reveal', f'mysql://{host}', '--format=json'],
        capture_output=True,
        text=True
    )
    return json.loads(result.stdout)

def check_mysql_health(host='localhost', max_conn_pct=80, min_buffer_rate=99):
    """Check MySQL health against thresholds."""
    health = get_mysql_health(host)

    issues = []

    # Check connection usage
    conn_pct = float(health['connection_health']['percentage'].rstrip('%'))
    if conn_pct > max_conn_pct:
        issues.append(f"High connection usage: {conn_pct:.1f}%")

    # Check buffer pool hit rate
    buffer_rate = float(health['innodb_health']['buffer_pool_hit_rate'].split('%')[0])
    if buffer_rate < min_buffer_rate:
        issues.append(f"Low buffer hit rate: {buffer_rate:.2f}%")

    # Check replication lag
    if health['replication'].get('role') == 'Slave':
        lag = health['replication'].get('lag')
        if lag and lag != 'Unknown' and int(lag) > 60:
            issues.append(f"Replication lag: {lag}s")

    return {
        'healthy': len(issues) == 0,
        'issues': issues,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'health_data': health
    }

if __name__ == '__main__':
    result = check_mysql_health()

    if result['healthy']:
        print("✅ MySQL is healthy")
    else:
        print(f"⚠️ MySQL health issues:")
        for issue in result['issues']:
            print(f"  - {issue}")
```

### Integration 6: Index Cleanup Script

```bash
#!/bin/bash
# mysql-index-cleanup.sh - Safe unused index removal

DB_HOST="$1"
MIN_UPTIME_DAYS=7

echo "🔍 Analyzing index usage on ${DB_HOST}..."

# Get index data
INDEXES=$(reveal mysql://${DB_HOST}/indexes --format=json)

# Check if safe to proceed
RESET_DETECTED=$(echo "$INDEXES" | jq -r '.performance_schema_status.counters_reset_detected')
UPTIME_SECS=$(echo "$INDEXES" | jq -r '.uptime_seconds')
UPTIME_DAYS=$(echo "$UPTIME_SECS / 86400" | bc)

echo "Uptime: ${UPTIME_DAYS} days"
echo "Reset detected: ${RESET_DETECTED}"

if [ "$RESET_DETECTED" = "true" ]; then
  echo "⚠️ Performance schema counters were reset - index data may be incomplete"
  echo "Recommendation: Wait for longer uptime before removing indexes"
  exit 1
fi

if [ "$UPTIME_DAYS" -lt "$MIN_UPTIME_DAYS" ]; then
  echo "⚠️ Uptime (${UPTIME_DAYS}d) < minimum (${MIN_UPTIME_DAYS}d)"
  echo "Recommendation: Wait for longer uptime for confident index analysis"
  exit 1
fi

# Generate removal script (don't execute automatically)
echo "$INDEXES" | jq -r '.unused[] |
  "-- DROP INDEX \(.index_name) ON \(.object_schema).\(.object_name);"
' > unused_indexes_drop.sql

echo ""
echo "✅ Analysis complete. Unused indexes written to: unused_indexes_drop.sql"
echo ""
echo "⚠️ IMPORTANT:"
echo "1. Review unused_indexes_drop.sql carefully"
echo "2. Check if indexes are UNIQUE constraints (don't drop those)"
echo "3. Test in staging environment first"
echo "4. Execute during maintenance window"
echo "5. Monitor performance after removal"
```

---

## Performance & Best Practices

### Token Efficiency

mysql:// is designed for AI agent consumption:

| Operation | Raw SQL Output | reveal Output | Savings |
|-----------|---------------|---------------|---------|
| Health overview | ~5000 tokens | ~100 tokens | **98%** |
| Connection list | ~2000 tokens | ~150 tokens | **92%** |
| InnoDB status | ~8000 tokens | ~200 tokens | **97%** |
| Storage sizes | ~1000 tokens | ~100 tokens | **90%** |

**Why?**
- ✅ DBA-relevant signals only (not raw counters)
- ✅ Pre-calculated ratios (table scan ratio vs raw handler counts)
- ✅ Structured JSON (not unstructured text)
- ✅ Time context included (snapshot_time, uptime)

### Performance Tips

1. **Use ~/.my.cnf for credentials**
   - Faster than environment variable lookup
   - More secure than URI credentials
   - Same config as mysql CLI

2. **Cache health snapshots**
   - Health data is expensive to collect (multiple queries)
   - Cache for 30-60 seconds in monitoring scripts
   - Use `snapshot_time` field to track freshness

3. **Use --only-failures for health checks**
   - Reduces output size
   - Faster to parse
   - Focus on issues only

4. **Progressive disclosure**
   - Start with overview: `mysql://localhost`
   - Drill into specific area: `mysql://localhost/innodb`
   - Extract one metric: `mysql://localhost/innodb --format=json | jq '.buffer_hit_rate'`

5. **Batch monitoring**
   - Use JSON output for parsing: `--format=json`
   - Extract multiple metrics at once (fewer queries)
   - Log to JSONL for time-series analysis

### Production Best Practices

1. **Read-only operations**
   - mysql:// adapter is read-only by design
   - Safe for production databases
   - No risk of accidental modifications

2. **Credential security**
   - ✅ Use ~/.my.cnf (600 permissions)
   - ✅ Use dedicated readonly user
   - ❌ Avoid credentials in shell history
   - ❌ Avoid hardcoded passwords in scripts

3. **Health check thresholds**
   - Tune thresholds for your workload
   - Use custom config: `~/.config/reveal/mysql-health-checks.yaml`
   - Test thresholds in staging first

4. **Index removal caution**
   - Wait 1+ week uptime before trusting "unused"
   - Check `counters_reset_detected` flag
   - Test in staging first
   - Monitor performance after removal
   - Keep backups

5. **Storage monitoring**
   - Track daily with `snapshot_time`
   - Alert on growth rate > threshold
   - Plan capacity 3-6 months ahead
   - Archive old data before hitting limits

---

## Troubleshooting

### Error: "pymysql module not found"

**Problem**: pymysql dependency not installed

**Solution**:
```bash
# Install with database extras
pip install reveal-cli[database]

# OR install pymysql directly
pip install pymysql
```

### Error: "Access denied for user"

**Problem**: Incorrect credentials or permissions

**Solution**:
```bash
# Check ~/.my.cnf format
cat ~/.my.cnf
# Should have:
# [client]
# host = localhost
# user = myuser
# password = mypass

# Verify permissions
chmod 600 ~/.my.cnf

# Test with mysql CLI
mysql --defaults-file=~/.my.cnf -e "SELECT 1"

# Check user permissions (as admin)
# mysql> SHOW GRANTS FOR 'myuser'@'localhost';
```

### Error: "Can't connect to MySQL server"

**Problem**: Server not reachable or wrong host/port

**Solution**:
```bash
# Check if MySQL is running
systemctl status mysql

# Test connection manually
mysql -h localhost -P 3306 -u myuser -p

# Check firewall (if remote)
telnet prod.example.com 3306

# Verify host in ~/.my.cnf
cat ~/.my.cnf | grep host
```

### Warning: "performance_schema counters reset detected"

**Problem**: performance_schema was reset, index metrics may be incomplete

**Solution**:
```bash
# Check reset status
reveal mysql://localhost/indexes --format=json | \
  jq '{
    reset_detected: .performance_schema_status.counters_reset_detected,
    measurement_basis: .measurement_basis,
    measurement_start: .measurement_start_time
  }'

# If reset_detected is true:
# - Wait for more uptime (>1 week recommended)
# - Don't remove "unused" indexes yet (may have been used before reset)
# - Re-check after more server uptime

# Check who reset counters (audit logs)
# mysql> SELECT * FROM performance_schema.setup_instruments
#        WHERE ENABLED='NO';
```

### Issue: Health checks always pass/fail

**Problem**: Thresholds not tuned for your workload

**Solution**:
```bash
# Copy default config
mkdir -p ~/.config/reveal
cat > ~/.config/reveal/mysql-health-checks.yaml <<EOF
checks:
  - name: Table Scan Ratio
    metric: table_scan_ratio
    pass_threshold: 15    # Relaxed from 10
    warn_threshold: 30    # Relaxed from 25
    severity: high
    operator: '<'

  # ... add other checks with custom thresholds
EOF

# Test new thresholds
reveal mysql://localhost --check
```

---

## Limitations

1. **Requires pymysql**
   - Not included in base reveal install
   - Install with: `pip install pymysql` or `pip install reveal-cli[database]`

2. **Read-only operations**
   - No write/modify capabilities (by design, for safety)
   - Cannot create indexes, alter tables, etc.
   - Use mysql CLI for modifications

3. **Slow query log**
   - `/slow-queries` requires slow_log table enabled
   - Not enabled by default in all MySQL installations
   - Enable with: `SET GLOBAL slow_query_log = 'ON'`

4. **Performance schema**
   - `/indexes` requires performance_schema enabled
   - Enabled by default in MySQL 5.7+, but can be disabled
   - Check with: `SHOW VARIABLES LIKE 'performance_schema'`

5. **Permissions required**
   - Need SELECT on all databases for full functionality
   - Need REPLICATION CLIENT for replication status
   - Need PROCESS for processlist
   - Recommended: Use dedicated readonly user with appropriate grants

6. **Connection overhead**
   - Each reveal command creates new connection
   - For high-frequency monitoring, consider caching or connection pooling
   - Use batch queries when possible (JSON output + jq)

7. **Time-series data**
   - reveal provides snapshots, not historical data
   - For trending, log outputs to JSONL or send to monitoring system
   - Use `snapshot_time` field for accurate time-series analysis

---

## Tips & Best Practices

### 1. Start with Overview, Then Drill Down

```bash
# Always start with overview
reveal mysql://localhost

# Then drill into specific area based on issues
reveal mysql://localhost/connections  # If high connection usage
reveal mysql://localhost/innodb       # If low buffer hit rate
reveal mysql://localhost/replication  # If replication lag
```

### 2. Use ~/.my.cnf for Production

```bash
# One-time setup
cat > ~/.my.cnf <<EOF
[client]
host = prod.example.com
port = 3306
user = readonly_user
password = secure_password
EOF
chmod 600 ~/.my.cnf

# Then all commands become simple
reveal mysql://
reveal mysql:// --check
reveal mysql:///storage
```

### 3. Monitor Health Checks Regularly

```bash
# In cron or systemd timer
*/5 * * * * reveal mysql://prod.db.com --check --only-failures || \
  echo "MySQL health issues detected" | mail -s "Alert" admin@example.com
```

### 4. Track Storage Growth

```bash
# Daily snapshot
reveal mysql://localhost/storage --format=json | \
  jq '{time: .snapshot_time, total_gb: .total_size_gb}' \
  >> storage_history.jsonl

# Weekly report
tail -7 storage_history.jsonl | jq -s '
  {
    start: .[0],
    end: .[-1],
    growth_gb: (.[-1].total_gb - .[0].total_gb)
  }
'
```

### 5. Use JSON Output for Parsing

```bash
# Extract specific metrics
reveal mysql://localhost --format=json | \
  jq '{qps: .performance.qps, buffer_rate: .innodb_health.buffer_pool_hit_rate}'

# Filter data
reveal mysql://localhost/connections --format=json | \
  jq '.long_running_queries[] | select(.time > 60)'
```

### 6. Verify Index Safety Before Removal

```bash
# Check uptime
reveal mysql://localhost/indexes --format=json | \
  jq '{uptime: .measurement_window, reset: .performance_schema_status.counters_reset_detected}'

# If uptime > 1 week AND reset = false, safe to proceed
reveal mysql://localhost/indexes --format=json | \
  jq -r '.unused[] | "\(.object_schema).\(.object_name).\(.index_name)"'
```

### 7. Configure Custom Health Thresholds

```bash
# Create custom config for your workload
cat > ~/.config/reveal/mysql-health-checks.yaml <<EOF
checks:
  - name: Connection Usage
    metric: connection_pct
    pass_threshold: 70    # Your custom threshold
    warn_threshold: 85
    severity: high
    operator: '<'
EOF

reveal mysql://localhost --check
```

### 8. Use Progressive Disclosure

```bash
# Minimize token usage
reveal mysql://localhost               # ~100 tokens
reveal mysql://localhost/innodb        # ~200 tokens
reveal mysql://localhost/innodb --format=json | jq '.buffer_hit_rate'  # ~50 tokens
```

---

## Related Documentation

- **AST Adapter**: `docs/AST_ADAPTER_GUIDE.md` - Code structure analysis
- **JSON Adapter**: `docs/JSON_ADAPTER_GUIDE.md` - JSON file inspection
- **SQLite Adapter**: `docs/SQLITE_ADAPTER_GUIDE.md` - SQLite database inspection
- **Python Adapter**: `docs/PYTHON_ADAPTER_GUIDE.md` - Python runtime inspection
- **Reveal Overview**: `README.md` - Full reveal documentation

---

## FAQ

### Q: Do I need root/admin MySQL access?

**A**: No. reveal works with read-only users. Recommended grants:

```sql
CREATE USER 'reveal_user'@'%' IDENTIFIED BY 'secure_password';
GRANT SELECT ON *.* TO 'reveal_user'@'%';
GRANT REPLICATION CLIENT ON *.* TO 'reveal_user'@'%';
GRANT PROCESS ON *.* TO 'reveal_user'@'%';
FLUSH PRIVILEGES;
```

### Q: Can I use this on production databases?

**A**: Yes. reveal is read-only and production-validated (tested on 189GB MySQL 8.0.35). Use ~/.my.cnf for secure credentials.

### Q: How often should I run health checks?

**A**: Every 5-15 minutes is reasonable. Cache results for faster dashboards. Don't run more than once per minute (unnecessary overhead).

### Q: What if performance_schema is disabled?

**A**: Most features work without performance_schema. Only `/indexes` requires it. Enable with:

```sql
# In /etc/mysql/my.cnf
[mysqld]
performance_schema = ON

# Then restart MySQL
systemctl restart mysql
```

### Q: Can I monitor remote databases?

**A**: Yes. Use full URI with credentials or configure ~/.my.cnf with remote host. Works with SSL/TLS connections.

```bash
# Remote with URI credentials
reveal mysql://user:pass@remote.example.com:3306

# Remote with ~/.my.cnf
# [client]
# host = remote.example.com
reveal mysql://
```

### Q: How do I know if indexes are truly unused?

**A**: Check three things:

1. **uptime > 1 week**: `reveal mysql://localhost/indexes | grep "Uptime"`
2. **reset_detected = false**: `reveal mysql://localhost/indexes --format=json | jq '.performance_schema_status.counters_reset_detected'`
3. **Test in staging**: Drop index in staging, monitor for 1 week

Never drop indexes without testing in staging first.

### Q: What's the difference between mysql:// and sqlite://?

**A**:
- **mysql://**: Network database server, health monitoring, replication, production DBs
- **sqlite://**: Local file database, embedded systems, mobile apps, development

Both are read-only inspection adapters with progressive disclosure patterns.

### Q: Can I export data for Grafana/Prometheus?

**A**: Yes. Use JSON output + transformation:

```bash
# Export metrics
reveal mysql://localhost --format=json | \
  jq '{qps: .performance.qps, connections: .connection_health.percentage}' \
  > metrics.json

# Push to Prometheus pushgateway
curl -X POST http://pushgateway:9091/metrics/job/mysql \
  --data-binary @metrics.json
```

### Q: How do I debug "Access denied" errors?

**A**: Check credentials and permissions:

```bash
# Test with mysql CLI
mysql --defaults-file=~/.my.cnf -e "SELECT 1"

# Check user exists
# mysql> SELECT User, Host FROM mysql.user WHERE User='myuser';

# Check grants
# mysql> SHOW GRANTS FOR 'myuser'@'localhost';
```

### Q: What if slow_log table doesn't exist?

**A**: Enable slow query log:

```sql
-- Enable slow query log
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL log_output = 'TABLE';  -- Log to mysql.slow_log
SET GLOBAL long_query_time = 2;   -- Queries > 2s are "slow"

-- Verify
SHOW VARIABLES LIKE 'slow_query%';
```

### Q: Can I customize health check thresholds?

**A**: Yes. Create `~/.config/reveal/mysql-health-checks.yaml` with custom thresholds. See [Health Checks](#health-checks) section for examples.

### Q: How accurate are the timestamps?

**A**: Very accurate. reveal uses MySQL server's clock (`UNIX_TIMESTAMP()`) instead of local machine time. This ensures:
- ✅ Correct for remote databases
- ✅ No timezone issues
- ✅ No clock drift between client/server

### Q: What MySQL versions are supported?

**A**: MySQL 5.7+ and MySQL 8.0+ are fully supported. MariaDB 10.x also works (minor differences in some metrics).

---

## Version History

- **v1.0** (2025-02-14): Initial comprehensive guide
  - All 12 elements documented
  - Health checks with configurable thresholds
  - Index usage analysis with reset detection
  - Time context and snapshot accuracy
  - 6 complete workflows
  - Integration examples (jq, Python, monitoring)
  - Production best practices
