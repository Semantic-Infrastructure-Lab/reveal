# MySQL Adapter: Timestamp Context Improvements

**Status**: Planning
**Priority**: High
**Impact**: User Experience, Data Accuracy
**Date**: 2026-02-09
**Author**: TIA (via dogfooding session: violet-flash-0209)

## Executive Summary

During dogfooding the `mysql://` adapter against production Sociamonials database, we identified **critical gaps in timestamp context** that make it hard to interpret metrics accurately. While reveal does better than raw MySQL commands, it falls short of industry monitoring tools like Datadog/Prometheus.

**Current Score**: 7/10
**Target Score**: 10/10

---

## Problem Statement

### Critical Question: "When are these metrics from?"

Users need to know:
1. **When was this snapshot taken?** (snapshot_time)
2. **When did the server start?** (server_start_time)
3. **What time period do cumulative metrics cover?** (measurement_window)
4. **Have metrics been reset?** (reset detection)

**Current State**: Inconsistent across endpoints
- `/performance` ✅ has measurement_window + server_start_time + uptime_seconds
- `/innodb` ✅ has measurement_window + server_start_time + uptime_seconds
- `/indexes` ⚠️ has measurement_window BUT ambiguous "or performance_schema enable"
- `/storage` ❌ NO timestamp context at all
- `/connections` ❌ NO timestamp context at all
- `/errors` ✅ has measurement_window + server_start_time + uptime_seconds

---

## Detailed Analysis

### What Reveal Does RIGHT ✅

**1. Uses MySQL's Clock (Not Local Machine)**
```python
mysql_time = self._execute_single("SELECT UNIX_TIMESTAMP() as timestamp")
server_start_timestamp = mysql_timestamp - uptime_seconds
```
- Avoids timezone/drift issues
- Accurate across remote connections
- Industry best practice

**2. Triple Time Context (Where Implemented)**
```json
{
  "measurement_window": "23d 23h (since server start)",
  "server_start_time": "2026-01-16T21:25:33+00:00",
  "uptime_seconds": 2071522
}
```
- Human-readable (measurement_window)
- Machine-parseable (server_start_time ISO 8601)
- Programmatic (uptime_seconds)

**3. Inline Clarification on Metrics**
```json
"slow_queries_total": "1297 (since server start)",
"buffer_pool_reads": "92303529 (since server start)"
```

### What's MISSING or BROKEN ❌

#### 1. Storage Endpoint = Zero Timestamp Context
**File**: `reveal/adapters/mysql/storage.py:42-45`

```python
return {
    'type': 'storage',
    'databases': db_sizes,
}
```

**Problem**: No way to know:
- When was this data collected?
- How stale is it?
- Can't track growth trends

**Impact**: Medium-High
- User assumes data is "current" but could be minutes old
- Can't correlate with other time-based metrics
- Can't detect stale connections

#### 2. Connections Endpoint = Zero Timestamp Context
**File**: `reveal/adapters/mysql/adapter.py:616-620`

```python
return {
    'type': 'connections',
    'total_connections': len(processlist),
    'by_state': by_state,
    'long_running_queries': long_running,
}
```

**Problem**: Long-running queries show `"time": 1257` (seconds)
- Since when? Server start? Query start? Unclear!
- No snapshot time to anchor interpretation

**Impact**: High
- "1257 seconds" could mean different things depending on context
- Can't calculate actual query duration without snapshot time
- Critical for debugging slow query issues

#### 3. Index Metrics = Ambiguous Reset Window
**File**: `reveal/adapters/mysql/adapter.py:902-905`

```python
'measurement_window': f'{uptime_days}d {uptime_hours}h (since server start or performance_schema enable)',
'note': 'Counters are cumulative since server start or last performance_schema reset',
```

**Problem**: Two possible starting points
- "since server start" → known (we have server_start_time)
- "or performance_schema enable" → UNKNOWN timestamp
- "or last performance_schema reset" → UNKNOWN timestamp

**Impact**: Medium
- User can't trust index usage numbers without knowing reset status
- "50 unused indexes" might be because performance_schema was just enabled
- False positives/negatives on index recommendations

#### 4. Missing "Snapshot Taken At" Timestamp
**Problem**: All endpoints missing current observation time

**Impact**: Medium-High
- Can't detect stale data
- Can't correlate metrics collected at different times
- Can't calculate rates accurately (need t1 and t2)

---

## Recommended Solution

### Phase 1: Add snapshot_time to ALL Endpoints (HIGH PRIORITY)

**Implementation**:
```python
def _get_snapshot_context(self) -> Dict[str, Any]:
    """Get standardized timing context for all metrics.

    Returns timing information using MySQL's clock for accuracy.
    All timestamps in UTC ISO 8601 format.
    """
    # Get MySQL's current timestamp (not local machine time)
    mysql_time = self._execute_single("SELECT UNIX_TIMESTAMP() as timestamp")
    snapshot_timestamp = int(mysql_time['timestamp'])
    snapshot_time = datetime.fromtimestamp(snapshot_timestamp, timezone.utc)

    # Get server uptime
    status_vars = {row['Variable_name']: row['Value']
                  for row in self._execute_query("SHOW GLOBAL STATUS")}
    uptime_seconds = int(status_vars.get('Uptime', 0))

    # Calculate server start time
    server_start_timestamp = snapshot_timestamp - uptime_seconds
    server_start_time = datetime.fromtimestamp(server_start_timestamp, timezone.utc)

    uptime_days = uptime_seconds // 86400
    uptime_hours = (uptime_seconds % 86400) // 3600

    return {
        'snapshot_time': snapshot_time.isoformat(),
        'server_start_time': server_start_time.isoformat(),
        'uptime_seconds': uptime_seconds,
        'measurement_window': f'{uptime_days}d {uptime_hours}h (since server start)',
    }
```

**Apply to ALL endpoints**:
```python
def _get_storage(self) -> Dict[str, Any]:
    """Get storage usage by database."""
    timing = self._get_snapshot_context()

    db_sizes = self._execute_query("""...""")

    return {
        'type': 'storage',
        **timing,  # Add snapshot_time, server_start_time, etc.
        'databases': db_sizes,
    }
```

### Phase 2: Detect and Report performance_schema Resets (MEDIUM PRIORITY)

**Goal**: Clarify index metrics ambiguity

```python
def _get_performance_schema_status(self) -> Dict[str, Any]:
    """Detect if performance_schema counters were reset recently.

    Returns:
        Dict with:
        - enabled: bool
        - counters_reset_detected: bool
        - likely_reset_time: Optional[str] (ISO timestamp if detected)
    """
    # Check if performance_schema is enabled
    ps_enabled = self._execute_single(
        "SELECT @@global.performance_schema as enabled"
    )['enabled']

    if not ps_enabled:
        return {
            'enabled': False,
            'counters_reset_detected': False,
            'likely_reset_time': None,
        }

    # Heuristic: If uptime is much longer than oldest performance_schema data,
    # counters were likely reset
    oldest_event = self._execute_single("""
        SELECT MIN(TIMER_START) / 1000000000000 as oldest_timestamp
        FROM performance_schema.events_statements_summary_by_digest
        WHERE TIMER_START > 0
    """)

    timing = self._get_snapshot_context()
    uptime_seconds = timing['uptime_seconds']

    if oldest_event and oldest_event['oldest_timestamp']:
        oldest_seconds_ago = timing['snapshot_time'] - oldest_event['oldest_timestamp']

        # If oldest event is much newer than server start (>1 hour gap), reset likely
        reset_detected = (uptime_seconds - oldest_seconds_ago) > 3600

        if reset_detected:
            reset_time = datetime.fromtimestamp(
                oldest_event['oldest_timestamp'], timezone.utc
            )
            return {
                'enabled': True,
                'counters_reset_detected': True,
                'likely_reset_time': reset_time.isoformat(),
            }

    return {
        'enabled': True,
        'counters_reset_detected': False,
        'likely_reset_time': None,
    }
```

**Use in index metrics**:
```python
def _get_indexes(self) -> Dict[str, Any]:
    timing = self._get_snapshot_context()
    ps_status = self._get_performance_schema_status()

    # Determine actual measurement basis
    if ps_status['counters_reset_detected']:
        measurement_basis = f"since reset at {ps_status['likely_reset_time']}"
        measurement_start_time = ps_status['likely_reset_time']
    else:
        measurement_basis = "since server start"
        measurement_start_time = timing['server_start_time']

    return {
        'type': 'indexes',
        **timing,
        'measurement_basis': measurement_basis,
        'measurement_start_time': measurement_start_time,
        'performance_schema_status': ps_status,
        'most_used': most_used,
        'unused': unused,
    }
```

### Phase 3: Standardize Timing Context Structure (LOW PRIORITY, NICE-TO-HAVE)

**Goal**: Consistent structure across all endpoints

```python
# Current (inconsistent):
{
    "measurement_window": "23d 23h (since server start)",
    "server_start_time": "2026-01-16T21:25:33+00:00",
    "uptime_seconds": 2071522,
}

# Proposed (nested, clearer):
{
    "timing_context": {
        "snapshot_time": "2026-02-09T20:45:32+00:00",
        "server_start_time": "2026-01-16T21:25:33+00:00",
        "uptime_seconds": 2071522,
        "measurement_basis": "since_server_start",  # or "since_reset"
        "measurement_start_time": "2026-01-16T21:25:33+00:00"
    }
}
```

**Trade-off**: Breaking change vs. clarity
- **Option A**: Add to existing structure (backward compatible)
- **Option B**: Nested structure (cleaner, breaking change)
- **Recommendation**: Option A for v0.49, Option B for v1.0

---

## Expected Output Examples

### Before (Current - Storage Endpoint)
```json
{
  "type": "storage",
  "databases": [
    {"db_name": "sociamon_sociamon", "size_gb": 183.52}
  ]
}
```
**Problem**: No idea when this was measured!

### After (Proposed)
```json
{
  "type": "storage",
  "snapshot_time": "2026-02-09T20:45:32+00:00",
  "server_start_time": "2026-01-16T21:25:33+00:00",
  "uptime_seconds": 2071522,
  "measurement_window": "23d 23h (since server start)",
  "databases": [
    {"db_name": "sociamon_sociamon", "size_gb": 183.52}
  ]
}
```
**Benefit**: Clear timestamp context, can track growth over time

### Before (Current - Connections Endpoint)
```json
{
  "type": "connections",
  "long_running_queries": [
    {"id": 26702137, "time": 1257}
  ]
}
```
**Problem**: 1257 seconds since... what?

### After (Proposed)
```json
{
  "type": "connections",
  "snapshot_time": "2026-02-09T20:45:32+00:00",
  "server_start_time": "2026-01-16T21:25:33+00:00",
  "uptime_seconds": 2071522,
  "measurement_window": "23d 23h (since server start)",
  "long_running_queries": [
    {
      "id": 26702137,
      "time": 1257,
      "query_start_time": "2026-02-09T20:24:35+00:00"
    }
  ]
}
```
**Benefit**: Can calculate exact query duration, detect stuck queries

### Before (Current - Index Endpoint)
```json
{
  "type": "indexes",
  "measurement_window": "23d 23h (since server start or performance_schema enable)",
  "note": "Counters are cumulative since server start or last performance_schema reset"
}
```
**Problem**: Ambiguous - which one is it?

### After (Proposed)
```json
{
  "type": "indexes",
  "snapshot_time": "2026-02-09T20:45:32+00:00",
  "server_start_time": "2026-01-16T21:25:33+00:00",
  "measurement_basis": "since_server_start",
  "measurement_start_time": "2026-01-16T21:25:33+00:00",
  "performance_schema_status": {
    "enabled": true,
    "counters_reset_detected": false,
    "likely_reset_time": null
  },
  "uptime_seconds": 2071522,
  "most_used": [...]
}
```
**Benefit**: Unambiguous, trust index recommendations

---

## Implementation Plan

### Phase 1 (v0.49 - Critical Fixes)
**Timeline**: 1-2 weeks
**Effort**: Low (helper function + apply to 5 endpoints)

- [ ] Create `_get_snapshot_context()` helper (1-2 hours)
- [ ] Add to `/storage` endpoint (30 min)
- [ ] Add to `/connections` endpoint (30 min)
- [ ] Add to `/databases` endpoint (30 min)
- [ ] Add to `/variables` endpoint (30 min)
- [ ] Add to `/health` endpoint (30 min)
- [ ] Update existing endpoints to use helper (refactor, 2 hours)
- [ ] Add tests for timestamp accuracy (2 hours)
- [ ] Update help documentation (1 hour)

**Total Effort**: ~10 hours

### Phase 2 (v0.50 - Performance Schema Detection)
**Timeline**: 2-3 weeks
**Effort**: Medium (detection logic + integration)

- [ ] Implement `_get_performance_schema_status()` (3 hours)
- [ ] Test against databases with/without resets (2 hours)
- [ ] Integrate into `/indexes` endpoint (2 hours)
- [ ] Update documentation with examples (1 hour)
- [ ] Add warning messages when reset detected (1 hour)

**Total Effort**: ~9 hours

### Phase 3 (v1.0 - Breaking Changes for Consistency)
**Timeline**: v1.0 release
**Effort**: High (breaking change, migration guide)

- [ ] Design nested `timing_context` structure (1 hour)
- [ ] Update all endpoints (4 hours)
- [ ] Update tests (3 hours)
- [ ] Write migration guide (2 hours)
- [ ] Update all documentation examples (3 hours)

**Total Effort**: ~13 hours

---

## Testing Requirements

### Unit Tests
```python
def test_snapshot_context_uses_mysql_clock():
    """Verify snapshot time comes from MySQL, not local machine."""
    # Test with mocked MySQL time vs system time
    pass

def test_storage_includes_snapshot_time():
    """Verify storage endpoint has snapshot_time field."""
    pass

def test_connections_includes_snapshot_time():
    """Verify connections endpoint has snapshot_time field."""
    pass

def test_performance_schema_reset_detection():
    """Test detection of performance_schema counter resets."""
    # Mock: uptime 30 days, oldest p_s event 1 day ago → reset detected
    pass
```

### Integration Tests
- Test against real MySQL 8.0 instances
- Test with performance_schema enabled/disabled
- Test after manual `TRUNCATE TABLE performance_schema.events_statements_summary_by_digest`
- Test timezone handling (UTC consistency)

---

## Documentation Updates Needed

### Help System
- Update `reveal help://mysql` with snapshot_time examples
- Add section on "Understanding Timing Context"
- Explain performance_schema reset detection

### Markdown Guides
- Update `MYSQL_ADAPTER_GUIDE.md` (if exists)
- Add timing context to all example outputs
- Add troubleshooting section for stale metrics

### CHANGELOG.md
```markdown
## [0.49.0] - 2026-02-XX

### Added
- mysql:// adapter: Add `snapshot_time` to all endpoints for accurate timestamp context
- mysql:// adapter: Add `_get_snapshot_context()` helper for consistent timing data

### Fixed
- mysql:// /storage endpoint now includes snapshot_time and server_start_time
- mysql:// /connections endpoint now includes snapshot_time for accurate query duration calculation

### Changed
- mysql:// All timing uses MySQL's clock (not local machine) for consistency
```

---

## Success Metrics

### Before (Current State)
- 3/8 endpoints have full timestamp context
- 0/8 endpoints have snapshot_time
- Index metrics have ambiguous reset window
- User confusion about metric staleness

### After (Target State)
- 8/8 endpoints have full timestamp context ✅
- 8/8 endpoints have snapshot_time ✅
- Index metrics clearly state reset status ✅
- Zero user confusion about timing ✅

**Score Improvement**: 7/10 → 10/10

---

## Comparison with Industry Tools

| Feature | Datadog | Prometheus | New Relic | reveal (current) | reveal (proposed) |
|---------|---------|------------|-----------|------------------|-------------------|
| Snapshot Time | ✅ | ✅ | ✅ | ❌ | ✅ |
| Server Start Time | ✅ | ✅ | ✅ | ⚠️ (some) | ✅ |
| Measurement Basis | ✅ | ✅ | ✅ | ⚠️ (ambiguous) | ✅ |
| Reset Detection | ✅ | ✅ | ✅ | ❌ | ✅ |
| Consistent Structure | ✅ | ✅ | ✅ | ❌ | ✅ |

---

## Related Issues

- None yet (this is the first documentation)

## References

- Dogfooding session: `violet-flash-0209` (2026-02-09)
- MySQL Performance Schema docs: https://dev.mysql.com/doc/refman/8.0/en/performance-schema.html
- ISO 8601 timestamp standard: https://en.wikipedia.org/wiki/ISO_8601

---

## Appendix: Code Locations

### Endpoints Needing Updates
- `reveal/adapters/mysql/storage.py:42` - `get_storage()`
- `reveal/adapters/mysql/adapter.py:590` - `_get_connections()`
- `reveal/adapters/mysql/adapter.py:857` - `_get_indexes()` (ambiguous)

### Endpoints Already Good
- `reveal/adapters/mysql/adapter.py:622` - `_get_performance()` ✅
- `reveal/adapters/mysql/adapter.py:694` - `_get_innodb()` ✅
- `reveal/adapters/mysql/adapter.py:800` - `_get_errors()` ✅

### Test Patterns to Follow
- `tests/adapters/test_mysql_adapter.py` (if exists)
- Use `unittest.mock` for MySQL clock mocking
