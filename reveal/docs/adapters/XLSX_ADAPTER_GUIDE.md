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
| `powerpivot` | string | Power Pivot data model mode (see below) | `?powerpivot=schema` |
| `powerquery` | string | Power Query M code mode: `list`, `show`, or query name | `?powerquery=list` |
| `names` | string | Show named ranges / defined names | `?names=list` |
| `connections` | string | External connections mode: `list` or `show` | `?connections=list` |

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

## Power Pivot Workbooks

Reveal detects Excel workbooks with an embedded Power Pivot / SSAS data model and
surfaces the model's structure via `?powerpivot=` query modes.

### Detection

Power Pivot workbooks are automatically detected at the overview level:

```bash
reveal model.xlsx
```
```
File: model.xlsx

Sheets (2): ...

⚡ Power Pivot model detected (xl/model/item.data)
   Tables: Sales, Product, Date, Customer
   Run with ?powerpivot=schema to explore the full model
```

### What Gets Extracted: Capability Matrix

Reveal uses a three-tier extraction strategy depending on what metadata is embedded
in the file. The tier is selected automatically — no configuration needed.

| Format | How to identify | Tables | Columns | DAX | Relationships |
|--------|----------------|--------|---------|-----|---------------|
| **Excel 2010** | `xl/customData/item1.data` + XMLA in `customXml/` | ✅ | ✅ | ✅ full expressions | ✅ |
| **Excel 2013+** | `xl/model/item.data` + XMLA in `customXml/` | ✅ | ✅ | ✅ full expressions | ✅ |
| **Modern / Power BI export** | `xl/model/item.data`, no XMLA | ✅ | ✅ (via pbixray) | ⚠️ if authored | ✅ (via pbixray) |
| **External SSAS/OLAP** | `xl/pivotCache/` with `cacheHierarchies` | ✅ names only | ❌ | ❌ | ❌ |
| **Power Query (DataMashup)** | `customXml/` contains `DataMashup` | ❌ | ❌ | ❌ | ❌ |

**Tier 1 — XMLA (Excel 2010 and 2013+)**: The old "Gemini" format stores a UTF-16
XMLA metadata envelope in `customXml/itemN.xml` alongside the binary VertiPaq data.
Reveal parses this directly — no dependencies beyond stdlib.

**Tier 2 — pbixray (modern Excel 365 / Power BI exports)**: Modern files have the
binary VertiPaq store but no XMLA envelope. If the optional `pbixray` library is
installed (`pip install pbixray`), reveal reads the `metadata.sqlitedb` embedded in
`xl/model/item.data` to get full columns and relationships. DAX measures are
extracted when present (many demo/sample files have none).

**Tier 3 — pivot cache fallback**: When neither XMLA nor pbixray is available,
reveal scans `xl/pivotCache/pivotCacheDefinition*.xml` for `cacheHierarchy`
elements to infer table names. Columns, DAX, and relationships are unavailable.

**Power Query (DataMashup)** — files whose `customXml/` contains a `DataMashup`
blob (M formula/query engine) are not Power Pivot workbooks. Use `?powerquery=list`
to extract M code (see Power Query section below).

### Query Modes

| Mode | Description |
|------|-------------|
| `?powerpivot=tables` | Table names + column counts |
| `?powerpivot=schema` | Full table + column listing + measure names |
| `?powerpivot=measures` | Measure names + owning table |
| `?powerpivot=dax` | Measure names + full DAX expressions |
| `?powerpivot=relationships` | Full relationship graph (from-table → to-table, join columns, cardinality) |

### Examples

```bash
# List all tables in the model
reveal xlsx://model.xlsx?powerpivot=tables

# Full schema: tables, columns, measures
reveal xlsx://model.xlsx?powerpivot=schema

# DAX expressions for all measures
reveal xlsx://model.xlsx?powerpivot=dax

# Relationship graph
reveal xlsx://model.xlsx?powerpivot=relationships
```

**`?powerpivot=schema` output (XMLA tier — full detail):**
```
Power Pivot Model: ContosoPnL.xlsx

Tables (4):
  Finance Data (10 columns)
    Fiscal Month, Profit Center, Account, Actual, Budget, Forecast, ... (10 total)
  Accounts (5 columns)
    Account, Line Item, Group, Sub Class, Class
  Executive Geography (9 columns)
    Profit Center, Exec Org, Exec Function Summary, ... (9 total)
  Date (5 columns)
    Date, Fiscal Year, Fiscal Qtr, Fiscal Month, Month

Measures (81):
  [Actual $]  Finance Data
  [Budget $]  Finance Data
  ...
```

**`?powerpivot=schema` output (pivot cache fallback — table names only):**
```
Power Pivot Model: report.xlsx

Tables (6):
  SalesFact
  Product
  Date
  ...

(Schema limited — XMLA absent; table names from pivotCache only)
```

**`?powerpivot=relationships` output:**
```
Relationships (3):
  Finance Data
    [Account] (Many)  ->  Accounts[Account] (One)
    [Profit Center] (Many)  ->  Executive Geography[Profit Center] (One)
    [CalculatedColumn1] (Many)  ->  Date[Date] (One)
```

### Optional: pbixray for Modern Files

To unlock full column and relationship extraction from modern Excel 365 / Power BI
export files (Tier 2), install `pbixray`:

```bash
pip install pbixray
```

Without it, modern files fall back to Tier 3 (table names only). With it, reveal
automatically uses `pbixray` for any file that has `xl/model/item.data` but no XMLA
envelope. No configuration needed — detection is automatic.

`pbixray` requires a compiled C extension (`xpress9`). Pre-built wheels are available
for x86_64 Linux on PyPI. ARM/other platforms may need to build from source.

### Use with MCP

```
reveal_query("xlsx://model.xlsx?powerpivot=tables")
reveal_query("xlsx://model.xlsx?powerpivot=relationships")
```

---

## Power Query (M Code)

Power Query (also called "Get & Transform") embeds M language queries in the workbook. These define the ETL pipeline — where data comes from and how it's shaped. Reveal extracts this using stdlib only (no extra dependencies); the DataMashup inner ZIP is parsed directly.

### How It Works

Power Query M code is stored in a `customXml/itemN.xml` file that contains a base64-encoded inner ZIP. The ZIP contains `Formulas/Section1.m` with all query definitions. The workbook overview will show "📦 Power Query detected" when queries are present.

### Query Modes

| Mode | Description |
|------|-------------|
| `?powerquery=list` | Query names and line counts (default) |
| `?powerquery=show` | Full M code for all queries |
| `?powerquery=<name>` | M code for a specific named query |

### Examples

```bash
# List all Power Query queries in the workbook
reveal xlsx://file.xlsx?powerquery=list

# Show full M code for all queries
reveal xlsx://file.xlsx?powerquery=show

# Show M code for a specific query
reveal xlsx://file.xlsx?powerquery=SalesData

# Quoted names with spaces still work (case-insensitive match)
reveal xlsx://file.xlsx?powerquery=Sales Data
```

### Sample Output

```
Power Query: report.xlsx

Queries (5):
  Customer  (8 lines)
  Product   (6 lines)
  SalesData (12 lines)
  DateDim   (5 lines)
  Calendar  (3 lines)

Run with ?powerquery=show to see all M code
Run with ?powerquery=<name> to see a specific query
```

---

## Named Ranges

Named ranges (Excel "Defined Names") give human-readable names to cell ranges, formulas, or constants. They are the semantic API of the workbook — how formulas reference data.

Extracted from `xl/workbook.xml` `<definedNames>` using stdlib XML parsing (no openpyxl needed).

### Examples

```bash
# List all named ranges
reveal xlsx://file.xlsx?names=list
```

### Sample Output

```
Named Ranges: model.xlsx

  Name        Scope    Reference
  ----------  -------  --------------------
  TaxRate     global   0.08
  SalesRange  global   Sheet1!$A$1:$Z$500
  _Print_Area sheet:0  Sheet1!$A$1:$T$100   (hidden)
```

Scope: `global` = workbook-wide; `sheet:N` = visible only within that sheet (0-based index).
Hidden ranges (internal Excel bookkeeping) are flagged with `(hidden)`.

---

## External Data Connections

Connections reveal where the workbook pulls data from: ODBC databases, OLE DB, web queries, text files, or Power Query connections. Extracted from `xl/connections.xml`.

### Connection Modes

| Mode | Description |
|------|-------------|
| `?connections=list` | Connection names, types, and source summary (default) |
| `?connections=show` | Full connection strings, SQL commands, and refresh settings |

### Examples

```bash
# List all connections
reveal xlsx://file.xlsx?connections=list

# Full connection details (connection strings and SQL)
reveal xlsx://file.xlsx?connections=show
```

### Sample Output — list

```
External Connections: report.xlsx

Connections (3):
  SalesDB  [ODBC]  DRIVER={SQL Server};SERVER=db01;DATABASE=Sales
  WebQuery [Web]   https://api.example.com/data
  Products [Power Query]

Run with ?connections=show for full connection strings and SQL
```

### Connection Types

| Type ID | Label |
|---------|-------|
| 1 | ODBC |
| 2 | OLE DB |
| 3 | Web |
| 4 | Text File |
| 5 | ADO |
| 100 | Power Query |

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
| > 50 MB | guarded | — | Sheet skipped with "too large to parse" message; other sheets unaffected |

**Large sheet guard:** Individual worksheet XML parts larger than 50 MB are skipped
during workbook overview. The sheet appears in the listing with a clear message
rather than silently showing `0 rows, 0 cols`. Other sheets in the same workbook
parse normally. To access a large sheet's data, extract a specific range:

```bash
reveal xlsx://huge_file.xlsx?sheet=FactSales&range=A1:Z1000
```

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
4. **Macros/VBA** - Not executed or extracted (xlsm VBA remains in the binary `vbaProject.bin` blob)
5. **Standard pivot tables** - Shown as static data only (regular Excel pivot tables, not Power Pivot). Power Pivot / SSAS data models are supported via `?powerpivot=` — see Power Pivot section above.
6. **Multiple sheets simultaneously** - One sheet per query
7. **Password-protected files** - Not supported
8. **Binary XLS files** - Only .xlsx/.xlsm (XML-based) supported; legacy `.xls` (BIFF format) is not
9. **Write operations** - Read-only (no editing)
10. **`.xlsb`, `.pbix`, `.pbit`, `.bim`** - Not supported as input formats

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

### v0.65.0 (2026-03-18, session cooling-current-0318)
- ✅ **Large sheet guard**: sheets > 50 MB show "too large to parse (N MB)" instead of silent `0 rows, 0 cols`
- ✅ **Column count fix**: derived from `dimension` ref tag instead of first-row cell count — fixes sparse rows and dynamic array spill zones
- ✅ **Real-world fixture coverage**: 8 new fixtures across `tests/fixtures/xlsx/` and `tests/fixtures/xlsx/powerpivot/` (general sheets, dynamic arrays, Contoso 2010/2013 XMLA, 4 Power BI service samples)
- ✅ **Power Pivot capability matrix validated** against real files: Excel 2010 (customData), Excel 2013+ (model/item.data + XMLA), modern Power BI exports (no XMLA), Power Query (DataMashup — not PowerPivot)
- ✅ `pbixray` identified as optional dependency for Tier 2 extraction (modern files): unlocks columns + relationships where only table names were previously available
- ✅ 117 tests total (4 new real-world fixture tests)

### v0.64.0+ (2026-03-17, sessions timeless-launch-0317, zifaxo-0317)
- ✅ `?powerpivot=relationships` — full relationship graph from SSAS ASSL model
- ✅ DAX regex fix: handles tableless `CREATE MEASURE` format (real-world files)
- ✅ External SSAS/OLAP workbook detection via `xl/pivotCache/` sentinel
- ✅ 113 tests total

### v0.64.0 (2026-03-17, session timeless-launch-0317)
- ✅ Power Pivot model extraction: `?powerpivot=tables/schema/measures/dax`
- ✅ Detects Excel 2010, 2013+, and Power BI export formats
- ✅ Pure stdlib — no new dependencies
- ✅ 44 new tests

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

- [QUICK_START.md](../QUICK_START.md) - General reveal usage
- [QUERY_SYNTAX_GUIDE.md](../guides/QUERY_SYNTAX_GUIDE.md) - Query parameters
- [FIELD_SELECTION_GUIDE.md](../guides/FIELD_SELECTION_GUIDE.md) - Token optimization with `--fields`
- [OUTPUT_CONTRACT.md](../development/OUTPUT_CONTRACT.md) - JSON output structure

---

## See Also

- **Office document support**: Also check `reveal file.docx` and `reveal file.pptx`
- **CSV analysis**: For CSV files, use `reveal file.csv` (dedicated CSV analyzer)
- **JSON data**: For JSON files, use `reveal json://file.json/path/to/key`

---

**Questions or issues?** See [CONTRIBUTING.md](../../../CONTRIBUTING.md) for how to report bugs or request features.
