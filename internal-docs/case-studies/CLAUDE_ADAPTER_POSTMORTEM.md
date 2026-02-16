# claude:// Adapter Post-Mortem

**Date**: 2026-01-19
**Session**: mint-palette-0119
**Status**: Core Bugs Fixed (see updates below)
**Updated**: 2026-01-19 (kabawose-0119)

## Purpose

Document the experience of using `reveal claude://` in a real session to find where Claude (the agent) used reveal and encountered failures.

## What We Tried To Do

1. Use `reveal claude://session/<name>?errors` to find sessions where reveal tool calls failed
2. Cross-reference errors to understand patterns of reveal usage failures

## What Went Poorly

### 1. Renderer Registration Bug ✅ FIXED

**Problem**: The claude adapter was registered but the renderer was not.

```
$ reveal claude://
Error: No renderer registered for scheme 'claude'
This is a bug - adapter is registered but renderer is not.
```

**Root Cause**: The installed PyPI version (0.32.0) doesn't include the `ClaudeRenderer` class that exists in the development version.

**Symptoms**:
- `ClaudeAdapter` exists in adapters list
- `claude` missing from renderers list
- Direct `claude://` URIs fail with cryptic error

**Workaround**: `PYTHONPATH=/path/to/dev:$PYTHONPATH reveal claude://...`

**Fix**: Fixed in v0.39.0 - `ClaudeRenderer` is now properly registered via `@register_renderer(ClaudeRenderer)` decorator.

### 2. Version Mismatch Confusion

The editable install (`pip install -e`) didn't properly override the existing installed version, leading to:
- `reveal --version` showing one version
- `pip show reveal-cli` showing another
- Actual runtime using yet another version from site-packages

**Lesson**: For reveal development, use `PYTHONPATH` override or ensure clean uninstall before dev install.

### 3. Error Detection Too Narrow ✅ FIXED

The `_get_errors()` function originally only looked for:
- Tool results containing "error" or "failed" in the content

It missed:
- Exit codes > 0 from Bash commands
- Tracebacks in output
- "not found" errors
- Schema validation errors

**Example**: Searching for `reveal` errors with grep found 115 matches in `zealous-carnage-0118`, but `?errors` query returned 0 errors.

**Root Cause Found**: The function was checking `type == 'assistant'` but tool results are in `type == 'user'` messages!

**Fix** (kabawose-0119):
1. Changed to check `type == 'user'` messages for tool results
2. Now detects errors via:
   - `is_error: true` flag (definitive)
   - Exit codes > 0 (definitive for Bash)
   - Traceback/Exception at line start (strong signal)
3. Also fixed `_track_tool_results()` and `_is_tool_error()` which had the same bug

### 4. No Filter for Specific Tool Failures ✅ FIXED

Wanted: "Show me all Bash tool calls where reveal was invoked and failed"

Got: `?tools=Bash` shows all Bash calls, `?errors` shows all errors, but no way to combine: "Bash errors involving reveal".

**Fix** (kabawose-0119): Composite queries now support this:
```
reveal claude://session/name?tools=Bash&errors&contains=reveal
```

### 5. Session Discovery Is Manual ✅ PARTIALLY FIXED

To find which sessions had reveal failures, had to:
1. List all session directories manually
2. Grep through JSONL files
3. Parse grep output

**Fix** (kabawose-0119): `reveal claude://` now lists 20 most recent sessions with metadata.

Cross-session search (`reveal claude://search?pattern=...`) is still a future feature.

## What Would Be Cool

### 1. Enhanced Error Detection ✅ IMPLEMENTED

```yaml
errors:
  - exit_code > 0 (Bash)      # ✅ Implemented
  - is_error: true            # ✅ Implemented
  - content contains traceback # ✅ Implemented (pattern matching)
  - content matches error patterns # ✅ Implemented
```

### 2. Composite Queries ✅ IMPLEMENTED

```
claude://session/name?tools=Bash&contains=reveal&errors
```

Filter to: Bash tool calls that contain "reveal" and resulted in errors.

### 3. Cross-Session Search (Future)

```
reveal claude://search?query=reveal+error
reveal claude://errors?pattern=reveal
```

Aggregate errors across sessions.

### 4. Tool-Specific Error Extractors (Partially Implemented)

Different tools have different error signatures:
- **Bash**: ✅ Exit code detection implemented
- **Read**: "File not found", permission errors
- **Edit**: "old_string not found"
- **Grep**: No matches (context-dependent)

### 5. Error Context ✅ IMPLEMENTED

Include preceding tool calls and assistant reasoning when showing errors:
```
context: {
  tool_name: 'Bash',
  tool_input_preview: 'cd /path && reveal file.py',
  thinking_preview: '...the relevant decision...'
}
```

### 6. Session-to-Session Linking

READMEs reference prior sessions. Could traverse:
```
reveal claude://session/current/chain  # Show session continuity chain
```

## Bugs Found During This Session

1. ✅ **Renderer not registered** - Fixed in v0.39.0
2. ✅ **Error detection too narrow** - Fixed in kabawose-0119 (wrong message type + improved detection)
3. ✅ **No `reveal claude://` alone** - Fixed in kabawose-0119 (now lists sessions + usage)

## Next Steps

1. [x] Release version with ClaudeRenderer (v0.39.0)
2. [x] Expand error detection patterns in `_get_errors()` (kabawose-0119)
3. [x] Add composite query support (kabawose-0119) - `?tools=Bash&contains=reveal&errors`
4. [x] Add error context (kabawose-0119) - Shows tool_name, tool_input, thinking
5. [x] Bare `reveal claude://` lists sessions (kabawose-0119)
6. [ ] Consider cross-session search feature (future)
7. [ ] Session-to-session linking via chain traversal (future)

## Session Context

This investigation was attempting to audit Claude's usage of reveal across sessions to find patterns of failures. The intent was to improve reveal based on real agent usage patterns.

The irony: The tool we wanted to use to audit reveal (claude://) itself had bugs that blocked the investigation.
