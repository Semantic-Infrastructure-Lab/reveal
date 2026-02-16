# Reveal Dogfooding Report - 2026-01-19 (Session 2)

**Session**: lingering-tide-0119
**Focus**: Validation and UX review

---

## Bugs Found and Fixed

### 1. PowerShell Function Name Duplicated (FIXED ✅)

**Severity**: Medium
**File**: `reveal/analyzers/powershell.py`

**Symptom** (before fix):
```
Functions (1):
  :1      Get-DataGet-Data { [4 lines, depth:0]
```

**Root Cause**:
- `_get_signature()` falls back to returning full first line when no `(` found
- PowerShell syntax: `function Get-Data {` has no parens
- Returns "Get-Data {" as signature
- Formatter does `name + signature` = "Get-Data" + "Get-Data {" = "Get-DataGet-Data {"

**Fix Applied**:
- Added `_get_signature()` override to PowerShellAnalyzer
- Extracts param blocks properly: `function Name { param($x)... }` → ` param($x)`
- Returns empty string for functions without params

**After fix**:
```
Functions (1):
  :1      Get-Data param([string]$Path) [4 lines, depth:0]
```

---

### 2. XML Text Output Empty (FIXED ✅)

**Severity**: Medium
**Files**: `reveal/display/structure.py`, `reveal/display/formatting.py`

**Symptom** (before fix):
```
File: test.xml (168B, 8 lines)

Children (2):
```
(No children listed, just the count)

**Root Cause**:
- XML items have `tag` field, not `name`
- XML items have no `line` field
- `_format_standard_items()` looks for `name` and `line`, finds neither
- Result: prints nothing for each item

**Fix Applied**:
- Added `_format_xml_children()` function with nested display
- Shows tags, attributes, text content, and child counts
- Recursive display up to depth 3

**After fix**:
```
Children (2):
  <database host="localhost" port="5432"> (2 children)
    <name> → "mydb"
    <user> → "admin"
  <cache enabled="true">
```

---

### 3. CSV Display Bug (FIXED ✅)

**Fixed in this session**

Added:
- Skip non-list/non-dict items in text renderer
- `_format_csv_schema()` for proper column display
- Handles scalar values (column_count, row_count) in JSON renderer

---

## UX Issues

### 4. Missing Line Numbers Show `:?`

**Severity**: Low
**Affects**: INI, XML, any format without line numbers

**Symptom**:
```
Sections (2):
  :?      database
  :?      cache
```

**Issue**: The `:?` prefix is awkward and provides no value.

**Fix Options**:
1. Omit line prefix when line is unknown
2. Calculate actual line numbers (INI sections do have lines)

---

### 5. `--languages` Count Confusing

**Severity**: Low

**Current**:
```
Total: 86 languages supported
```

**Issue**: README says "40+ languages built-in. 165+ via tree-sitter" but `--languages` shows 86 with no distinction.

**Fix Option**: Separate output showing:
- 42 with dedicated analyzers
- 44 via tree-sitter basic support
- 165+ available in tree-sitter-language-pack

---

### 6. No `--adapters` Flag

**Severity**: Low

**Issue**: Have `--languages` but no `--adapters`. Must use `reveal help://adapters`.

**Fix**: Add `--adapters` flag for consistency.

---

### 7. `:LINE` Error Message Unclear

**Severity**: Low

**Current**:
```
Error: Element ':192' not found in file.py
```

**Issue**: `:192` looks like a line reference, not an element name. Confusing.

**Better**:
```
Error: No function or class found at line 192 in file.py
Hint: Line-based extraction (:LINE) finds the element containing that line
```

---

## Documentation Issues (Fixed)

### PRIORITIES.md Updates
- Marked file format gaps as COMPLETE (CSV, XML, INI, PowerShell, Batch all work)
- Added claude:// adapter to list (14 total now)
- Moved 5 formats from "Planned" to "Current"

---

## Test Results

| Test Suite | Result |
|------------|--------|
| CSV/XML/INI tests | 54 passed |
| Structure/rendering tests | 67 passed |
| Breadcrumb tests | 88 passed |
| README validation | 1 passed |

---

## Recommendations

### Priority Fixes
1. **PowerShell signature** - Quick fix, affects UX
2. **XML text renderer** - Add `_format_xml_children()`

### Nice to Have
3. Add `--adapters` flag
4. Improve `:LINE` error message
5. Omit `:?` line prefix when unknown

---

## Files Modified This Session

| File | Change |
|------|--------|
| `reveal/display/structure.py` | Skip non-list categories, add CSV/XML handling |
| `reveal/display/formatting.py` | Add `_format_csv_schema()`, `_format_xml_children()` |
| `reveal/analyzers/powershell.py` | Add `_get_signature()` override for param handling |
| `internal-docs/planning/PRIORITIES.md` | Update status of file formats, adapters |

