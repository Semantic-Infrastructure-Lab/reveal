---
title: MySQL Adapter Guide (mysql://)
category: guide
---
# MySQL Adapter Guide (mysql://)

**Adapter**: `mysql://`
**Purpose**: MySQL database inspection with health monitoring, performance analysis, and replication status
**Type**: Database adapter
**Output Formats**: text, json

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
pip install "reveal-cli[database]"

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
  jq '{time: .snapshot_time, total_gb: ([.databases[].size_gb] | add)}'
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
Uptime: 15d 23h 20m

Connection Health: ✅
  Current: 12 / 151 max (7.9%)

Performance:
  QPS: 155.8 queries/sec
  Slow Queries: 234 total (0.00% of all queries since server start)
  Threads Running: 3

InnoDB Health: ✅
  Buffer Pool Hit Rate: 99.87% (since server start)
  Row Lock Waits: 12 (since server start)
  Deadlocks: 0 (since server start)

Replication: Slave
  Lag: 2s

Storage:
  Total: 45.67 GB across 2 databases
  Largest: production (38.45 GB)

Health Status: ✅ HEALTHY
Issues:
  • No issues detected

Next Steps:
  reveal mysql://localhost/connections       # Connection details
  reveal mysql://localhost/performance       # Query performance
  reveal mysql://localhost/innodb            # InnoDB details
  reveal mysql://localhost --check           # Run health checks
```

The text view omits some fields the JSON carries: server start time, peak connection use (`max_used_ever`, `max_used_pct`), replication thread state (`io_running`, `sql_running`) and `resource_limits` (open files). The health issues are connection use above 80%, a buffer pool hit rate below 99%, and replication lag above 60 seconds. One or two issues give `⚠️ WARNING`; three give `❌ CRITICAL`.

**Key Sections**:
- **Connection Health**: Current usage and the configured maximum (peak use and rejection detection are in the JSON)
- **Performance**: QPS, slow queries, active threads
- **InnoDB Health**: Buffer pool hit rate, locks, deadlocks
- **Replication**: Role (master/slave/standalone) and lag
- **Storage**: Total size, database count, largest database
- **Resource limits** (JSON `resource_limits`): open files against the limit
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
| `tables` | Table I/O statistics and hotspots | Find the busiest tables |
| `databases` | Database list | Enumerate all databases |
| `indexes` | Index usage statistics | Find unused indexes, optimize queries |
| `slow-queries` | Slow query log analysis | Analyze slow query patterns (requires slow_log) |

An element name that is not in this table does not fail: the overview is returned (and, with no reachable server, its connection error).

### Element Examples

#### 1. Connections

```bash
reveal mysql://localhost/connections
```

**Returns**:
```
MySQL Connections
Measurement window: 15d 23h (since server start)

Total Connections: 1

By State:
  executing: 1

Long-Running Queries (>5s): 0
```

**Use cases**:
- Debug connection pool exhaustion
- Find long-running queries blocking resources
- Identify connection states
- Monitor active query count

#### 2. Performance

```bash
reveal mysql://localhost/performance
```

**Returns**:
```
MySQL Performance
Measurement window: 15d 23h (since server start)

QPS: 155.80
Slow Queries: 234 (since server start)
Sort Merge Passes: 0 (since server start)

Full Table Scans: ❌ 90.00%
  High scan ratio (>25%) or Handler_read_rnd_next indicates missing indexes

Thread Cache: ✅ 1.20% miss rate
  Miss rate >10% suggests increasing thread_cache_size

Temp Tables: ✅ 9.00% on disk
  Ratio >25% suggests increasing tmp_table_size or max_heap_table_size
```

JSON keys: `queries_per_second`, `slow_queries_total`, `full_table_scans` (`select_scan_ratio`, `status`, `select_scan`, `select_range`, `handler_read_rnd_next`, `note`), `thread_cache_efficiency` (`miss_rate`, ...), `temp_tables` (`disk_ratio`, ...) and `sort_merge_passes`, plus the timing fields. There is no query-cache section.

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
MySQL InnoDB
Measurement window: 15d 23h (since server start)

Buffer Pool Hit Rate: 99.87%
  Reads: 1300000 (since server start)
  Read Requests: 1000000000 (since server start)
Row Lock Waits: 12 (since server start)
Row Lock Time (avg): 8 ms
Deadlocks: 0 (since server start)
```

JSON keys: `buffer_pool_hit_rate`, `buffer_pool_reads`, `buffer_pool_read_requests`, `row_lock_waits`, `row_lock_time_avg`, `deadlocks`, plus the timing fields. Buffer pool size, pending I/O and row counters are not reported.

**Use cases**:
- Optimize buffer pool size (target >99% hit rate)
- Debug lock contention issues
- Track deadlocks

#### 4. Replication

```bash
reveal mysql://localhost/replication
```

**Returns** (a replica):
```
MySQL Replication: Slave

Master: db1.internal:3306
IO Running: Yes
SQL Running: Yes
Seconds Behind Master: 2
Last Error: None
```

A server that serves replicas prints `MySQL Replication: Master`, `Slaves: N` and one `server_id=... host=...` line per replica; a server with neither prints `MySQL Replication: Standalone` and `No replication configured`. JSON keys for a replica: `role`, `master_host`, `master_port`, `io_running` and `sql_running` (the strings `Yes`/`No`), `seconds_behind_master`, `last_error`. The result carries no health verdict; the lag threshold lives in the overview and in `--check`.

**Use cases**:
- Monitor replication lag
- Verify replication threads are running
- Debug replication errors

#### 5. Storage

```bash
reveal mysql://localhost/storage
```

**Returns**:
```
MySQL Storage
Measurement window: 15d 23h (since server start)

  production: 38.45 GB (120 tables, 30.1 data / 8.35 index)
  analytics: 7.22 GB (40 tables, 6.0 data / 1.22 index)
```

JSON: `databases` is a list of `{db_name, table_count, size_gb, data_gb, index_gb}`, largest first, plus the timing fields. The total, the database count and the largest database are on the overview (`.storage`), not here.

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
MySQL Storage: production
Measurement window: 15d 23h (since server start)

  orders (InnoDB): 512.3 MB, 1200000 rows
  users (InnoDB): 64.0 MB, 80000 rows
```

JSON: `database` and `tables`, a list of `{table_name, engine, table_rows, size_mb}`, largest first. Sizes are in MB and carry no percentages.

**Use cases**:
- Identify largest tables in a database
- Find candidates for archiving
- Analyze table growth patterns

#### 7. Indexes

```bash
reveal mysql://localhost/indexes
```

**Returns**:
```
MySQL Index Usage
Measurement basis: since_server_start (since 2026-10-11T07:35:53+00:00)
Performance Schema: enabled

Most Used Indexes (top 2):
  production.users.idx_email: 12345678 accesses (99.99% read)
  production.orders.idx_user_id: 9876543 accesses (100.0% read)

Unused Indexes: 2
  production.legacy_users.idx_old_field
  production.products.idx_deprecated
```

The JSON carries `measurement_basis`, `measurement_start_time`, `performance_schema_status` (`enabled`, `counters_reset_detected`, `likely_reset_time`), `most_used` (top 20), `unused` (first 50) and `unused_count`. When `counters_reset_detected` is true the basis becomes `since_reset` and `measurement_start_time` is the likely reset time, so fresh counters are not read as "unused".

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
MySQL Slow Queries (last 24 hours)

Summary:
  Total: 234
  Avg time: 18.3s (min 5s, max 127s)
  Rows examined: 45678901

Top Queries (1):
  [127s] app_user[app_user] @ [10.0.1.23] - 12345678 rows examined
    SELECT * FROM users u JOIN orders o ON u.id = o.user_id WHERE ...
```

The JSON has `period`, `summary` and `top_queries` (up to 20, each with `start_time`, `user_host`, `query_time_seconds`, `lock_time_seconds`, `rows_sent`, `rows_examined`, `query_preview`). Without a readable `mysql.slow_log` table it returns `error` and `message: "Slow query log may not be enabled or accessible"`.

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

```
MySQL Health Check: ⚠️ WARNING

Summary: 4/7 passed, 3 warnings, 0 failures

⚠️ Warnings:
  • Table Scan Ratio: 12.50% (threshold: <10%, severity: high)
  • Temp Disk Ratio: 32.10% (threshold: <25%, severity: medium)
  • Max Used Connections %: 85.30% (threshold: <80%, severity: critical)

✅ Passed:
  • Thread Cache Miss Rate: 3.20% (threshold: <10%)
  • Open Files %: 23.40% (threshold: <75%)
  • Current Connection %: 45.20% (threshold: <80%)
  • Buffer Hit Rate: 99.87% (threshold: >99%)

Exit code: 1
```

Checks are grouped by status; a failure group prints first. Only warnings and failures show their severity.

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
| `2` | Failure | One or more failures, or the server could not be reached (the JSON then has `error` and no checks) |

**Use in CI/CD**:

```bash
#!/bin/bash
reveal mysql://prod.db.com --check --only-failures --format=json
rc=$?

if [ $rc -eq 0 ]; then
  echo "✅ All health checks passed"
elif [ $rc -eq 1 ]; then
  echo "⚠️ Health warnings detected"
  exit 1
elif [ $rc -eq 2 ]; then
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
  jq '{table_scan_ratio: .full_table_scans.select_scan_ratio, thread_cache_miss_rate: .thread_cache_efficiency.miss_rate, temp_tables_to_disk_ratio: .temp_tables.disk_ratio}'
```

**Returns**:
```json
{
  "table_scan_ratio": "12.50%",
  "thread_cache_miss_rate": "3.20%",
  "temp_tables_to_disk_ratio": "18.70%"
}
```

#### 1. Table Scan Ratio

**Formula**: `Select_scan / (Select_scan + Select_range) * 100` (zero when both counters are zero)

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
# Check current thread_cache_size (the /variables element lists only max_connections,
# innodb_buffer_pool_size, query_cache_size, tmp_table_size and max_heap_table_size)
mysql -e "SHOW VARIABLES LIKE 'thread_cache_size'"

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
  jq '{time: .snapshot_time, total_gb: ([.databases[].size_gb] | add)}' > feb1.json
# {"time": "2025-02-01T08:00:00+00:00", "total_gb": 42.34}

# Snapshot 2 (Feb 14)
reveal mysql://localhost/storage --format=json | \
  jq '{time: .snapshot_time, total_gb: ([.databases[].size_gb] | add)}' > feb14.json
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
| `--format=<type>` | Output format (text, json) | `reveal mysql://localhost --format=json` |
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

# Search the report
reveal mysql://localhost | grep -i "buffer"
```

---

## Output Types

### 1. mysql_health

**Use case**: Database health overview (`mysql://host`)

**Schema**:
```json
{
  "contract_version": "1.1",
  "type": "mysql_server",
  "source": "localhost:3306",
  "source_type": "database",
  "snapshot_time": "2026-10-27T06:55:53+00:00",
  "server": "localhost:3306",
  "version": "8.0.35-0ubuntu0.22.04.1",
  "uptime": "15d 23h 20m",
  "server_start_time": "2026-10-11T07:35:53+00:00",
  "connection_health": {
    "current": 12,
    "max": 151,
    "percentage": "7.9%",
    "max_used_ever": 45,
    "max_used_pct": "29.8%",
    "status": "✅",
    "max_used_status": "✅",
    "note": "If max_used_pct was 100%, connections were rejected (since server start)"
  },
  "performance": {
    "qps": "155.8",
    "slow_queries": "234 total (0.00% of all queries since server start)",
    "threads_running": 3
  },
  "innodb_health": {
    "buffer_pool_hit_rate": "99.87% (since server start)",
    "status": "✅",
    "row_lock_waits": "12 (since server start)",
    "deadlocks": "0 (since server start)"
  },
  "replication": {"role": "Slave", "lag": 2, "io_running": true, "sql_running": true},
  "storage": {"total_size_gb": 45.67, "database_count": 2, "largest_db": "production (38.45 GB)"},
  "resource_limits": {
    "open_files": {"current": 234, "limit": 10000, "percentage": "2.3%", "status": "✅", "note": "..."}
  },
  "health_status": "✅ HEALTHY",
  "health_issues": ["No issues detected"],
  "next_steps": ["reveal mysql://localhost/connections       # Connection details"]
}
```

Status fields are emoji (`✅`, `⚠️`, `❌`), not words. A standalone server reports `"replication": {"role": "Standalone"}`, a master `{"role": "Master", "slaves": N}`, and a replica whose lag is unknown `"lag": "Unknown"`.

### 2. replication element

**Use case**: Replication monitoring (`mysql://host/replication`)

**Schema** (a plain object; the element results carry no `contract_version`):
```json
{
  "type": "replication",
  "role": "Slave",
  "master_host": "db1.internal",
  "master_port": 3306,
  "io_running": "Yes",
  "sql_running": "Yes",
  "seconds_behind_master": 2,
  "last_error": "None"
}
```

A master returns `{"type": "replication", "role": "Master", "slaves": [{"server_id": ..., "host": ...}]}`; a standalone server returns `{"type": "replication", "role": "Standalone", "message": "No replication configured"}`.

### 3. storage element

**Use case**: Storage analysis (`mysql://host/storage`)

**Schema**:
```json
{
  "type": "storage",
  "snapshot_time": "2026-10-27T06:55:53+00:00",
  "server_start_time": "2026-10-11T07:35:53+00:00",
  "uptime_seconds": 1380000,
  "measurement_window": "15d 23h (since server start)",
  "databases": [
    {"db_name": "production", "table_count": 120, "size_gb": 38.45, "data_gb": 30.1, "index_gb": 8.35}
  ]
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
reveal mysql://localhost/performance --format=json | jq '.full_table_scans'
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
    total_gb: ([.databases[].size_gb] | add),
    databases: .database_count
  }'

# 5. Monitor replication lag (if slave)
reveal mysql:///replication --format=json | \
  jq '{lag: .seconds_behind_master, io: .io_running, sql: .sql_running}'

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
    total_gb: ([.databases[].size_gb] | add),
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
    perf_schema: .performance_schema_status,
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
RESULT=$(reveal mysql://${DB_HOST} --check --format=json) || true   # exit 1/2 is data here, not a script error

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
CURRENT_SIZE=$(echo "$CURRENT" | jq -r '[.databases[].size_gb] | add')
CURRENT_TIME=$(echo "$CURRENT" | jq -r '.snapshot_time')

# Read previous snapshot
if [ -f storage_previous.json ]; then
  PREV_SIZE=$(jq -r '[.databases[].size_gb] | add' storage_previous.json)
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
   - Extract one metric: `mysql://localhost/innodb --format=json | jq '.buffer_pool_hit_rate'`

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

### Error: "pymysql is required for mysql:// adapter"

**Problem**: pymysql dependency not installed (the error also prints `Install with: pip install "reveal-cli[database]"`)

**Solution**:
```bash
# Install with database extras
pip install "reveal-cli[database]"
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
# The file REPLACES the built-in seven checks (no merge): copy all seven entries and edit thresholds
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
   - Install with: `pip install "reveal-cli[database]"`

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
  jq '{time: .snapshot_time, total_gb: ([.databases[].size_gb] | add)}' \
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
reveal mysql://localhost/innodb --format=json | jq '.buffer_pool_hit_rate'  # ~50 tokens
```

---

## Related Documentation

- **AST Adapter**: `docs/adapters/AST_ADAPTER_GUIDE.md` - Code structure analysis
- **JSON Adapter**: `docs/adapters/JSON_ADAPTER_GUIDE.md` - JSON file inspection
- **SQLite Adapter**: `docs/adapters/SQLITE_ADAPTER_GUIDE.md` - SQLite database inspection
- **Python Adapter**: `docs/adapters/PYTHON_ADAPTER_GUIDE.md` - Python runtime inspection
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

1. **uptime > 1 week**: `reveal mysql://localhost/indexes --format=json | jq .measurement_window`
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

## See Also

- [QUICK_START.md](../QUICK_START.md) - Getting started with reveal
- [CONFIGURATION_GUIDE.md](../guides/CONFIGURATION_GUIDE.md) - Configuring reveal for your project
