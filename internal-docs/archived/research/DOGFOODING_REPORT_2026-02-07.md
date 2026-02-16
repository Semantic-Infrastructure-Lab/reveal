---
session: solar-observatory-0207
date: 2026-02-07
activity: Dogfooding Reveal on itself
status: complete
---

# Reveal Dogfooding Session Results

## What We Tested

### 1. ✅ Core Structure Exploration

**Command**: `reveal .`
- **Works**: Shows complete project structure with file counts
- **Output**: Clean, hierarchical view of directories and files
- **Token cost**: ~2.5K tokens for full project tree
- **Insight**: Progressive disclosure working well (truncated at 115 entries)

**Command**: `reveal reveal/adapters/`
- **Works**: Shows adapter directory structure
- **Output**: All adapter subdirectories and standalone adapter files
- **Token cost**: ~900 tokens

### 2. ✅ File Structure Inspection

**Command**: `reveal reveal/adapters/diff.py`
- **Works**: Shows imports, functions, classes with line counts and signatures
- **Output**: 23 imports, 20 functions, 2 classes clearly listed
- **Token cost**: ~900 tokens (vs ~7K for full file read)
- **Insight**: 7-8x token savings for structure-only view

### 3. ✅ Element Extraction

**Command**: `reveal reveal/adapters/diff.py get_schema`
- **Works**: Extracts specific function with line numbers
- **Output**: Shows function from line 184-287 with full source
- **Token cost**: ~1.7K tokens for 104-line function
- **Insight**: Precise extraction, breadcrumbs work (`reveal/adapters/diff.py:184-287`)

### 4. ✅ diff:// Adapter

**Command**: `reveal 'diff://reveal/adapters/diff.py:reveal/adapters/sqlite/adapter.py'`
- **Works**: Shows structural diff between two adapters
- **Output**: Summary (+5 functions, -15 functions, +1 class, -2 classes)
- **Output**: Detailed function-by-function changes with line numbers
- **Token cost**: ~1.5K tokens
- **Insight**: Great for comparing similar files/adapters

**Failed**: `reveal 'diff://file.py:git://HEAD~1:file.py'`
- **Issue**: git:// URI path format not working
- **Error**: "path 'reveal:adapters/diff.py' does not exist"
- **TODO**: Fix git adapter URI parsing or document correct format

### 5. ✅ stats:// Adapter

**Command**: `reveal 'stats://reveal/adapters/diff.py'`
- **Works**: Shows file metrics
- **Output**: 850 lines (638 code, 70 comments), 20 functions, 2 classes
- **Output**: Quality score: 95.0/100
- **Output**: Issues: 1 long function, 1 deep nesting
- **Token cost**: ~150 tokens
- **Insight**: Fast quality assessment

### 6. ✅ imports:// Adapter

**Command**: `reveal 'imports://reveal/adapters/diff.py'`
- **Works**: Shows import analysis summary
- **Output**: 23 imports, no circular dependencies
- **Token cost**: ~150 tokens

**Command**: `reveal 'imports://reveal/adapters/diff.py?unused'`
- **Works**: Query parameter filtering
- **Output**: "✅ No unused imports found!"
- **Insight**: Query parameters work well

### 7. ✅ env:// Adapter

**Command**: `reveal 'env://'`
- **Works**: Lists environment variables by category
- **Output**: System (9), Python (2), Custom (67) - 78 total
- **Output**: Sensitive values masked (API keys shown as `*** (sensitive)`)
- **Token cost**: ~1.4K tokens
- **Insight**: Good security practices (masking sensitive data)

### 8. ✅ Typed Output Format

**Command**: `reveal reveal/adapters/sqlite/adapter.py --typed`
- **Works**: Shows hierarchical navigation structure
- **Output**: Imports at top level, class with nested methods
- **Output**: Clear containment relationships (class → methods)
- **Token cost**: ~500 tokens
- **Insight**: Great for understanding class structure

### 9. ✅ Outline Mode

**Command**: `reveal reveal/adapters/sqlite/adapter.py --outline`
- **Works**: Tree view of class structure
- **Output**: Shows imports, then class with method tree (├─, └─ symbols)
- **Output**: Each method shows line count, depth, line number
- **Token cost**: ~450 tokens
- **Insight**: Most visual/readable for quick scanning

### 10. ✅ JSON Output Format

**Command**: `reveal reveal/adapters/sqlite/adapter.py --format json`
- **Works**: Machine-readable structured output
- **Output**: Contains: analyzer, file, meta, structure, type keys
- **Output**: Functions have: line, line_end, name, signature, line_count, depth, complexity
- **Token cost**: ~3K tokens (full structure)
- **Insight**: Good for scripting/automation

### 11. ❌ Query Parameters on File Structure

**Command**: `reveal reveal/adapters/diff.py '?type=function&depth=0'`
- **Failed**: "Element '?type=function&depth=0' not found"
- **Issue**: Query parameter syntax not supported for file structure
- **Workaround**: Use `--filter` flag with `--typed` output
- **TODO**: Either support query params or document why not

## Insights

### What Works Really Well

1. **Progressive Disclosure**: Structure view → Element extraction saves massive tokens
2. **Adapter Composability**: diff://, stats://, imports:// all work seamlessly
3. **Security**: Sensitive env vars automatically masked
4. **Output Formats**: Multiple formats (text, typed, outline, json) for different use cases
5. **Breadcrumbs**: Line references make it easy to drill down (e.g., `file.py:184-287`)
6. **Query Parameters**: Work well for imports adapter (`?unused`, `?circular`)

### Gaps/Issues Found

1. **git:// URI Integration**: Path format unclear/broken for diff adapter
2. **Query Params Inconsistency**: Work for some adapters (imports), not for files
3. **Missing Test Files**: Claude adapter test file in non-standard location

### Token Economics Validated

| Operation | Tokens | Use Case |
|-----------|--------|----------|
| Full file read (850 lines) | ~7,000 | Implementation details needed |
| Structure view | ~900 | Understanding code organization |
| Element extraction | ~1,700 | Single function/class |
| Outline view | ~450 | Quick scan of structure |
| Stats view | ~150 | Quality assessment |
| Diff view | ~1,500 | Compare two files |

**Savings**: 7-8x token reduction for structure-first exploration

## Test Coverage Status

**Adapters with dedicated test files** (11):
- ✅ diff_adapter (test_diff_adapter.py)
- ✅ domain_adapter (test_domain_adapter.py)
- ✅ git_adapter (test_git_adapter.py)
- ✅ json_adapter (test_json_adapter.py)
- ✅ markdown_adapter (test_markdown_adapter.py)
- ✅ mysql_adapter (test_mysql_adapter.py)
- ✅ python_adapter (test_python_adapter.py)
- ✅ reveal_adapter (test_reveal_adapter.py)
- ✅ sqlite_adapter (test_sqlite_adapter.py)
- ✅ ssl_adapter (test_ssl_adapter.py)
- ✅ stats_adapter (test_stats_adapter.py)

**Adapter test file in non-standard location** (1):
- 🟡 claude (tests/adapters/test_claude_adapter.py)

**Not adapters** (data files):
- help_data/ (YAML configuration files)

## Recommendations

### Immediate Fixes

1. **Fix git:// URI format** - Document or fix path parsing for git references
   - Example: `diff://file.py:git://HEAD~1:file.py` should work
   - Currently fails with "path 'reveal:adapters/diff.py' does not exist"

2. **Clarify query parameter support** - Document which adapters support `?param` syntax
   - Works: imports:// (`?unused`, `?circular`)
   - Doesn't work: File structure queries (`?type=function`)
   - Document in adapter help or AGENT_HELP.md

3. **Move claude adapter tests** - Standardize test file location
   - Current: `tests/adapters/test_claude_adapter.py`
   - Expected: `tests/test_claude_adapter.py`
   - Or document why different location

### Documentation Improvements

1. **Add dogfooding guide** - Create guide showing common exploration patterns
   - Structure first (`reveal dir/`)
   - Then file (`reveal file.py`)
   - Then element (`reveal file.py function`)
   - Then adapters (`stats://`, `diff://`, etc.)

2. **Update AGENT_HELP.md** - Add token cost estimates for each operation
   - Helps AI agents make informed decisions about tool usage

3. **Query parameter reference** - Create unified reference for all adapters
   - Which adapters support what queries
   - Example queries for each adapter

## Next Steps

Per original plan:
1. **diff adapter test expansion** - 27% coverage, expand to match sqlite (82% increase)
2. **Fix git:// URI integration** - Enable diff with git references
3. **Document query parameter support** - Clarify which adapters support what

