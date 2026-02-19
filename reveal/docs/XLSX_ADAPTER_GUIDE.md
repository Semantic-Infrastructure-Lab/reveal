---
title: Excel (XLSX) Adapter Guide
category: guide
---
# Excel (XLSX) Adapter Guide

**Adapter**: `xlsx://`
**Status**: 🟢 Stable (v0.49.0+)
**Purpose**: Excel spreadsheet inspection, data extraction, and CSV export

---

## Quick Start

```bash
# View workbook overview (all sheets)
reveal file.xlsx

# Extract specific sheet (by name)
reveal xlsx://file.xlsx?sheet=Sales

# Extract cell range (A1 notation)
reveal xlsx://file.xlsx?sheet=Sales&range=A1:C10

# Export sheet as CSV
reveal xlsx://file.xlsx?sheet=Sales&format=csv

# Search across all sheets
reveal xlsx://file.xlsx?search=revenue
```

---

## Features

### Workbook Overview

**View all sheets in a workbook:**
```bash
reveal file.xlsx
```

**Output:**
```
Workbook: sales_report.xlsx (45.3 KB)

Sheets (3):
  Sheet1       500 rows × 12 columns    (A1:L500)
  Sales        1,234 rows × 8 columns   (A1:H1234)
  Summary      25 rows × 5 columns      (A1:E25)

Created: 2024-01-15
Modified: 2024-02-13
Author: Finance Team
```

### Sheet Extraction

**By name (case-insensitive):**
```bash
reveal xlsx://file.xlsx?sheet=Sales
reveal xlsx://file.xlsx?sheet=sales     # Case-insensitive
```

**By index (0-based):**
```bash
reveal xlsx://file.xlsx?sheet=0         # First sheet
reveal xlsx://file.xlsx?sheet=1         # Second sheet
```

**Output shows:**
- Sheet name and dimensions
- Column headers (first row)
- Sample data rows (configurable limit)
- Data types detected per column

### Cell Range Extraction

**A1 notation support:**
```bash
# Simple range
reveal xlsx://file.xlsx?sheet=Sales&range=A1:C10

# Single column
reveal xlsx://file.xlsx?sheet=Sales&range=B:B

# Single row
reveal xlsx://file.xlsx?sheet=Sales&range=5:5

# Large ranges (AA-ZZ columns supported)
reveal xlsx://file.xlsx?sheet=Data&range=A1:ZZ1000
```

**What you get:**
- Exact cell values in specified range
- Preserves empty cells (shown as `null` in JSON, empty in text)
- Column headers if range includes row 1

### CSV Export

**Export any sheet to CSV format:**
```bash
# Full sheet
reveal xlsx://file.xlsx?sheet=Sales&format=csv

# Specific range
reveal xlsx://file.xlsx?sheet=Sales&range=A1:E100&format=csv

# Pipe to file
reveal xlsx://file.xlsx?sheet=Sales&format=csv > sales.csv
```

**CSV output characteristics:**
- RFC 4180 compliant
- Double-quoted fields with embedded commas/quotes
- UTF-8 encoding
- CRLF line endings (Excel compatible)

### Search Across Sheets

**Find data across entire workbook:**
```bash
# Simple search (case-insensitive)
reveal xlsx://file.xlsx?search=revenue

# Multiple matches show sheet + cell location
```

**Output:**
```
Search results for "revenue" in sales_report.xlsx:

Sales sheet:
  A1: Revenue
  C15: Total Revenue: $1,234,567
  H99: Revenue Growth

Summary sheet:
  B3: Q1 Revenue
  B4: Q2 Revenue
```

---

## Query Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `sheet` | string\|int | Sheet name (case-insensitive) or 0-based index | `?sheet=Sales` or `?sheet=0` |
| `range` | string | Excel range in A1 notation | `?range=A1:C10` |
| `format` | string | Output format: `text` (default), `json`, `csv` | `?format=csv` |
| `search` | string | Search term (case-insensitive) | `?search=revenue` |
| `limit` | int | Max rows to display (default: 25) | `?limit=100` |

**Parameter combinations:**
```bash
# Sheet + range
xlsx://file.xlsx?sheet=Sales&range=A1:E50

# Sheet + format
xlsx://file.xlsx?sheet=Sales&format=csv

# Sheet + range + format
xlsx://file.xlsx?sheet=Sales&range=A1:E50&format=csv

# Sheet + limit
xlsx://file.xlsx?sheet=Sales&limit=10

# Search only (no sheet needed)
xlsx://file.xlsx?search=revenue
```

---

## Output Formats

### Text Format (default)

**Human-readable table output:**
```bash
reveal xlsx://file.xlsx?sheet=Sales
```

Output includes:
- Sheet metadata (name, dimensions, range)
- Column headers
- Formatted table with borders
- Row numbers
- Data type hints

### JSON Format

**Machine-readable structured output:**
```bash
reveal xlsx://file.xlsx?sheet=Sales --format json
```

**JSON structure:**
```json
{
  "adapter": "xlsx",
  "file_path": "/path/to/file.xlsx",
  "sheet_name": "Sales",
  "dimensions": {
    "rows": 1234,
    "columns": 8,
    "range": "A1:H1234"
  },
  "columns": [
    "Date", "Product", "Quantity", "Price", "Total", "Region", "Salesperson", "Notes"
  ],
  "rows": [
    ["2024-01-01", "Widget A", 150, 29.99, 4498.5, "North", "John", "Rush order"],
    ["2024-01-02", "Widget B", 75, 39.99, 2999.25, "South", "Jane", ""]
  ],
  "data_types": {
    "Date": "date",
    "Quantity": "int",
    "Price": "float",
    "Total": "float"
  }
}
```

### CSV Format

**Excel-compatible CSV:**
```bash
reveal xlsx://file.xlsx?sheet=Sales&format=csv
```

Output characteristics:
- First row = column headers
- Quoted fields (handles commas, quotes, newlines)
- UTF-8 encoding
- CRLF line endings

---

## Element Extraction

**Extract individual sheets by name:**
```bash
# Standard element syntax
reveal file.xlsx Sheet1
reveal file.xlsx Sales

# Case-insensitive
reveal file.xlsx sales
```

**Equivalent to:**
```bash
reveal xlsx://file.xlsx?sheet=Sheet1
```

---

## Common Workflows

### Workflow 1: Quick Data Inspection

**Scenario:** New Excel file, need to understand its structure.

```bash
# Step 1: See what sheets exist
reveal report.xlsx

# Output shows:
#   Sales       1,234 rows × 8 columns
#   Returns     89 rows × 6 columns
#   Summary     25 rows × 5 columns

# Step 2: Inspect specific sheet
reveal report.xlsx Sales

# Step 3: Look at specific range
reveal xlsx://report.xlsx?sheet=Sales&range=A1:E25
```

### Workflow 2: CSV Export for Analysis

**Scenario:** Export Excel data for use in other tools.

```bash
# Export full sheet
reveal xlsx://data.xlsx?sheet=Transactions&format=csv > transactions.csv

# Export specific range only
reveal xlsx://data.xlsx?sheet=Summary&range=A1:D100&format=csv > summary.csv

# Verify export
wc -l transactions.csv
head -5 transactions.csv
```

### Workflow 3: Multi-File Data Search

**Scenario:** Find all mentions of "Q4 Revenue" across multiple reports.

```bash
# Search each file
find reports/ -name "*.xlsx" | while read f; do
  echo "=== $f ==="
  reveal "xlsx://$f?search=Q4 Revenue"
done

# Or use reveal's stdin mode
find reports/ -name "*.xlsx" | reveal --stdin xlsx://?search=Q4%20Revenue
```

### Workflow 4: Automated Report Extraction

**Scenario:** Extract same sheet from multiple files.

```bash
# Extract Sales sheet from all monthly reports
for month in jan feb mar apr; do
  reveal xlsx://reports/${month}_report.xlsx?sheet=Sales&format=csv > ${month}_sales.csv
done

# Combine into single file
echo "Month,Date,Product,Amount" > all_sales.csv
for csv in *_sales.csv; do
  tail -n +2 "$csv" >> all_sales.csv
done
```

### Workflow 5: Data Quality Check

**Scenario:** Verify data completeness before processing.

```bash
# Get sheet overview
reveal report.xlsx?sheet=Data --format json | jq '{
  file: .file_path,
  sheet: .sheet_name,
  rows: .dimensions.rows,
  columns: .dimensions.columns,
  column_names: .columns,
  empty_cells: [.rows[][] | select(. == null or . == "")] | length
}'

# Check for expected columns
reveal report.xlsx?sheet=Data --format json | jq '.columns | contains(["Date", "Amount", "Status"])'
```

---

## Performance Characteristics

### File Size Handling

| File Size | Load Time | Memory Usage | Recommended Approach |
|-----------|-----------|--------------|----------------------|
| < 1 MB | < 100ms | ~5 MB | Direct access |
| 1-10 MB | 100ms-1s | ~20 MB | Direct access |
| 10-50 MB | 1-5s | ~100 MB | Use `range=` for specific cells |
| > 50 MB | 5s+ | ~500 MB+ | Extract to CSV first, process externally |

### Large File Strategies

**For files > 50 MB:**
```bash
# Don't: Load entire sheet
reveal huge_file.xlsx?sheet=Data  # Slow, memory-intensive

# Do: Extract specific range
reveal huge_file.xlsx?sheet=Data&range=A1:Z1000  # Fast

# Do: Export to CSV for external processing
reveal huge_file.xlsx?sheet=Data&format=csv | split -l 10000 - chunk_
```

**Row limits:**
```bash
# Preview first 10 rows
reveal file.xlsx?sheet=Sales&limit=10

# Preview last 10 rows (not supported - use CSV + tail)
reveal file.xlsx?sheet=Sales&format=csv | tail -11
```

---

## Limitations

### What XLSX Adapter Does NOT Support

1. **Formulas** - Only values shown (formula results, not formula text)
2. **Formatting** - No colors, fonts, borders, cell styles
3. **Charts/Images** - Not extracted
4. **Macros/VBA** - Not executed or extracted
5. **Pivot tables** - Shown as static data only
6. **Multiple sheets simultaneously** - One sheet per query
7. **Password-protected files** - Not supported
8. **Binary XLS files** - Only .xlsx (XML-based) supported
9. **Write operations** - Read-only (no editing)

### Known Edge Cases

**Merged cells:**
- Only top-left cell value shown
- Other cells in merge appear empty

**Date handling:**
- Excel serial dates auto-detected and formatted
- Custom date formats may appear as numbers

**Number precision:**
- Floating point precision matches Excel (15 significant digits)
- Very large numbers may lose precision

**Empty rows/columns:**
- Trailing empty rows/columns not included in dimensions
- Embedded empty rows/columns preserved

---

## Error Messages

**File not found:**
```
Error: File not found: /path/to/file.xlsx
```

**Sheet not found:**
```
Error: Sheet 'Salesss' not found in workbook
Available sheets: Sales, Returns, Summary
```

**Invalid range:**
```
Error: Invalid range 'A1:ZZZ10000'
Valid range format: A1:ZZ9999 (columns AA-ZZ supported)
```

**Corrupted file:**
```
Error: Failed to parse xlsx file (may be corrupted or not a valid .xlsx file)
```

---

## Tips & Best Practices

### Progressive Disclosure

**Start broad, drill down:**
```bash
# 1. What sheets exist?
reveal report.xlsx

# 2. What's in this sheet?
reveal report.xlsx Sales

# 3. Extract specific data
reveal xlsx://report.xlsx?sheet=Sales&range=A1:E100&format=csv
```

### Case-Insensitive Sheet Names

Sheet names are matched case-insensitively:
```bash
reveal file.xlsx?sheet=SALES    # Matches "Sales"
reveal file.xlsx?sheet=sales    # Matches "Sales"
reveal file.xlsx?sheet=Sales    # Matches "Sales"
```

### CSV Export Compatibility

Exported CSVs work with:
- Excel (import back)
- Google Sheets (import)
- Pandas: `pd.read_csv()`
- SQLite: `.import --csv`
- Most data tools (RFC 4180 compliant)

### Range Syntax Tips

```bash
# Single column (all rows)
?range=A:A

# Single row (all columns)
?range=5:5

# From start to column
?range=A1:C1048576

# Wide ranges (AA-ZZ supported)
?range=A1:ZZ100
```

---

## Integration with Other Tools

### With pandas

```python
import subprocess
import pandas as pd

# Export to CSV, load with pandas
csv_data = subprocess.check_output([
    'reveal', 'xlsx://report.xlsx?sheet=Sales&format=csv'
], text=True)

df = pd.read_csv(io.StringIO(csv_data))
```

### With jq

```bash
# Extract specific columns
reveal xlsx://file.xlsx?sheet=Sales --format json | \
  jq '.rows[] | [.[0], .[2], .[4]]'

# Filter rows
reveal xlsx://file.xlsx?sheet=Sales --format json | \
  jq '.rows[] | select(.[3] > 100)'
```

### With sqlite

```bash
# Export to CSV, import to SQLite
reveal xlsx://data.xlsx?sheet=Transactions&format=csv > transactions.csv
sqlite3 data.db ".import --csv transactions.csv transactions"
```

---

## Version History

### v0.49.0 (2024-02-10)
- ✅ Initial release
- ✅ Workbook overview and sheet listing
- ✅ Sheet extraction by name or index (case-insensitive)
- ✅ Cell range extraction with A1 notation (supports AA-ZZ columns)
- ✅ CSV export with `?format=csv`
- ✅ Search across sheets
- ✅ JSON output format
- ✅ 40+ comprehensive tests
- ✅ Performance tested up to 20K+ rows

---

## Related Documentation

- [QUICK_START.md](QUICK_START.md) - General reveal usage
- [QUERY_SYNTAX_GUIDE.md](QUERY_SYNTAX_GUIDE.md) - Query parameters
- [FIELD_SELECTION_GUIDE.md](FIELD_SELECTION_GUIDE.md) - Token optimization with `--fields`
- [OUTPUT_CONTRACT.md](OUTPUT_CONTRACT.md) - JSON output structure

---

## See Also

- **Office document support**: Also check `reveal file.docx` and `reveal file.pptx`
- **CSV analysis**: For CSV files, use `reveal file.csv` (dedicated CSV analyzer)
- **JSON data**: For JSON files, use `reveal json://file.json/path/to/key`

---

**Questions or issues?** See [CONTRIBUTING.md](../../CONTRIBUTING.md) for how to report bugs or request features.
