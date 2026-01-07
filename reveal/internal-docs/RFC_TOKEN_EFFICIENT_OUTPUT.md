# RFC: Token-Efficient Output Formatting

**Date**: 2026-01-06
**Status**: Draft
**Version**: 0.1

## Summary

Reveal's text output format repeats full file paths on every line, wasting 30-40% of output tokens. This RFC proposes eliminating redundant path repetition while maintaining tool compatibility.

## Problem Statement

### Measured Waste

| Scenario | Total Output | Path Waste | Efficiency |
|----------|-------------|------------|------------|
| AST query (122 results) | 15,814 bytes | 5,040 bytes | 68% |
| Single file (49 elements) | 5,521 bytes | 2,205 bytes | 61% |

### Root Cause

In grouped output, the file path appears twice:
1. In the "File:" header
2. On every element line below it

```
File: /home/user/project/src/components/api_client.py          # Path #1
  /home/user/project/src/components/api_client.py: 179  extract...  # Path #2 (redundant!)
  /home/user/project/src/components/api_client.py: 296  handle...   # Path #3 (redundant!)
  /home/user/project/src/components/api_client.py: 353  validate... # Path #4 (redundant!)
```

### Impact on AI Agents

- Claude Code, Copilot, and similar tools consume tokens proportional to output size
- 30-40% waste means 30-40% higher costs and slower responses
- Reveal is designed for AI agents - this defeats its purpose

## Proposed Solution

### Option A: Remove Redundant Paths (Recommended)

When output is grouped by file, don't repeat the path on element lines:

```
File: /home/user/project/src/components/api_client.py
  :179  extract_call_parameters [33 lines, complexity: 23]
  :296  handle_ai_errors [35 lines, complexity: 19]
  :353  validate_call_parameters [29 lines, complexity: 22]
```

**Savings**: 41% reduction (393 → 231 bytes for 3 elements)

**Pros**:
- Minimal change to output structure
- Full path still available in header
- Existing scripts parsing "File:" headers unaffected

**Cons**:
- Element lines no longer independently parseable (need context)

### Option B: Relative Paths + Root Header

Show root once, use relative paths throughout:

```
AST Query: /home/user/project/src

components/api_client.py:
  :179  extract_call_parameters [33 lines, complexity: 23]
  :296  handle_ai_errors [35 lines, complexity: 19]
```

**Savings**: 39% reduction

**Pros**:
- Very readable
- Works well for large directory queries

**Cons**:
- More complex path reconstruction

### Option C: Compact Format Flag

Add `--compact` or `--ai` flag for maximum efficiency:

```
# /home/user/project/src
components/api_client.py:179 extract_call_parameters 33L c:23
components/api_client.py:296 handle_ai_errors 35L c:19
```

**Savings**: 47% reduction

**Pros**:
- Maximum token efficiency
- Opt-in, doesn't break existing behavior

**Cons**:
- New format to maintain
- Cryptic for humans

## Recommendation

**Implement Option A first** - it's the simplest change with the biggest impact:

1. Modify `rendering/adapters/ast.py` line 65:
   ```python
   # Before
   print(f"  {file_path}:{line:>4}  {name} [{line_count} lines, complexity: {complexity}]")

   # After
   print(f"  :{line:>4}  {name} [{line_count} lines, complexity: {complexity}]")
   ```

2. Similar changes in `display/formatting.py` for `_format_standard_items`

3. Keep `--format grep` unchanged (already optimized for tools)

## Affected Files

- `reveal/rendering/adapters/ast.py:65-67` - AST query element output
- `reveal/display/formatting.py:345,350,355` - Standard item formatting
- `reveal/display/element.py:77,84` - Element extraction output

## Migration

This is a breaking change for anyone parsing the text output format expecting `path:line` on every line.

**Mitigation**:
- Document the change clearly in changelog
- Note that `--format grep` still provides `path:line:name` format
- Consider a deprecation period with `--legacy-paths` flag

## Testing

1. Verify `--format grep` unchanged
2. Verify `--format json` unchanged
3. Test element extraction breadcrumbs still work
4. Test IDE integration (if any relies on text format parsing)

## Future Work

- Consider Option B for directory queries where relative paths make sense
- Consider Option C as an explicit AI-optimization mode
- Profile token usage in real Claude Code sessions before/after

## Additional Findings

### Existing Flags

Reveal already has `--no-breadcrumbs` (aliases: `-q`, `--quiet`) which saves ~9%:

| Mode | Bytes | Savings |
|------|-------|---------|
| Default | 5,521 | - |
| --no-breadcrumbs | 5,027 | 9% |
| With path fix (estimate) | ~3,300 | 40% |
| Both combined | ~2,800 | 50% |

**Recommendation**: Document `--no-breadcrumbs` more prominently for AI agent users.

### JSON Format Overhead

Counterintuitively, JSON format is **larger** than text format:

| Format | Bytes | Notes |
|--------|-------|-------|
| Text | 5,027 | Path repetition issue |
| JSON | 12,315 | Structural overhead |
| Grep | 9,203 | Loses metadata |

JSON's structural overhead (brackets, quotes, key names) outweighs the path repetition savings. For AI agents that can parse text, **optimized text format is best**.

### Breadcrumbs Efficiency

Breadcrumbs repeat the full path 5 times in typical output:
- 495 bytes total breadcrumbs
- 230 bytes (46%) are path repetition

If breadcrumbs were made path-efficient:
```
# Current
Next: reveal /home/user/project/src/base_command.py <func>
      reveal /home/user/project/src/base_command.py --check

# Efficient (using "." for current file)
Next: reveal . <func>    # Extract specific element
      reveal . --check   # Check code quality
```

This is lower priority since `--no-breadcrumbs` exists.

## Appendix A: Format Comparison Summary

| Format | Tokens | Tool Compat | Metadata | Best For |
|--------|--------|-------------|----------|----------|
| Text (current) | High | Medium | Full | Humans |
| Text (optimized) | Low | Medium | Full | AI agents |
| JSON | Higher | High | Full | Scripting |
| Grep | Low | High | None | Pipelines |

## Appendix B: Measurement Script

```bash
# Measure path waste in any reveal output
reveal 'ast:///path?complexity>10' > output.txt
total=$(wc -c < output.txt)
base_path="/path"
waste=$(($(grep -o "$base_path" output.txt | wc -c)))
echo "Efficiency: $((100 - (waste * 100 / total)))%"
```

## Appendix C: Quick Win Checklist

1. [ ] Fix `rendering/adapters/ast.py` - grouped output path duplication
2. [ ] Fix `display/formatting.py` - single file output path duplication
3. [ ] Update AGENT_HELP.md to recommend `--no-breadcrumbs` for AI agents
4. [ ] Add `--ai` alias for `--no-breadcrumbs` (semantic clarity)
5. [ ] Consider breadcrumb path abbreviation (lower priority)
