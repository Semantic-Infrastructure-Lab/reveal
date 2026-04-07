---
title: "XLSX & Power BI Expansion: Gap Analysis and Roadmap"
type: architecture
beth_topics:
  - reveal
  - xlsx
  - powerbi
  - pbix
  - pbit
  - bim
  - power-query
  - datamashup
  - named-ranges
  - pivot-tables
  - vba
  - xlsb
  - dax
---

# XLSX & Power BI Expansion: Gap Analysis and Roadmap

**Session:** pulsing-cluster-0318 | **Date:** 2026-03-18
**Status:** Research complete, implementation pending
**Related:** [XLSX_ADAPTER_GUIDE.md](XLSX_ADAPTER_GUIDE.md)

---

## Executive Summary

As of v0.65.0, reveal has strong support for Excel xlsx/xlsm files — sheet data, Power Pivot models (XMLA), and a three-tier Power Pivot extraction strategy. This document catalogs what structured metadata remains **unexploited** both within existing file types and across new file formats we don't yet handle.

**Key finding:** Most high-value gaps can be filled with stdlib (`zipfile`, `xml.etree`, `json`, `base64`) or libraries already present (`openpyxl`, `pbixray`). Only VBA extraction (oletools) and xlsb (pyxlsb) require new dependencies.

---

## Current Capability Baseline

**Supported formats:** `.xlsx`, `.xlsm` only
**What works today:**

| Feature | Status | Query Param |
|---------|--------|-------------|
| Workbook overview (all sheets, dimensions) | ✅ Full | default |
| Sheet data (rows/cols/range) | ✅ Full | `?sheet=`, `?range=` |
| Cross-sheet search | ✅ Full | `?search=` |
| Power Pivot tables (XMLA) | ✅ Full | `?powerpivot=tables` |
| Power Pivot schema (XMLA) | ✅ Full | `?powerpivot=schema` |
| Power Pivot DAX measures (XMLA) | ✅ Full | `?powerpivot=dax` |
| Power Pivot relationships (XMLA) | ✅ Full | `?powerpivot=relationships` |
| Power Pivot (modern/no XMLA) via pbixray | ⚠️ Planned (Tier 2) | `?powerpivot=*` |
| Power Pivot (modern fallback) | ✅ Tables only | `?powerpivot=tables` |
| Large sheet guard (>50 MB) | ✅ Full | — |
| Column count from dimension ref | ✅ Full | — |
| CSV export | ✅ Full | `?format=csv` |

---

## Gap 1: Power Query M Code (within xlsx/xlsm)

### What It Is
Power Query (Get & Transform) lets Excel users define ETL queries in the **M language**. These queries pull from databases, web APIs, CSV files, other Excel files, etc. — they are the data pipeline definition for the workbook.

### Where It Lives
Inside a `customXml/itemN.xml` file whose schema attribute matches `http://schemas.microsoft.com/DataMashup`. **Do not assume it's always `item1.xml`** — iterate all `customXml/item*.xml` files and check the schema.

### Format
The `<DataMashup>` element contains **base64-encoded binary** that is itself an inner ZIP. The inner ZIP contains:
```
Formulas/Section1.m          # All queries in one M script
Config/Package.json          # Package metadata (version, etc.)
[QueryName].m                # Sometimes individual query files
```

### How to Extract
Pure stdlib — no external libraries needed:

```python
import zipfile, base64, io

with zipfile.ZipFile(xlsx_path) as outer:
    for name in outer.namelist():
        if name.startswith("customXml/item") and name.endswith(".xml"):
            xml = outer.read(name)
            if b"DataMashup" in xml:
                # Parse DataMashup element, get base64 content
                # Decode base64 → decompress inner ZIP
                # Read Formulas/Section1.m
                ...
```

**Alternative:** `pbixray` exposes `get_power_query()` returning a DataFrame with columns `TableName` and `Expression`. But this requires pbixray to be installed and works via xlsx file path (pbixray handles xlsx too).

**Third option:** `excel-datamashup` library (GitHub: Vladinator/excel-datamashup) — dedicated parser for the binary DataMashup format.

### What We'd Surface
- Query names
- Full M expression per query (potentially 10–200+ lines each)
- Inferred data sources (file paths, connection strings embedded in M)
- Query dependency order (each query can reference others)

### Reveal Implementation
```
reveal file.xlsx?powerquery=list        # names + line counts
reveal file.xlsx?powerquery=show        # all M code, one query per block
reveal file.xlsx?powerquery=QueryName   # M code for specific query
```

### Priority: **HIGH**
Power Query is the dominant ETL story for Excel-centric data workflows. Understanding M code is as valuable as understanding DAX. Many xlsx files have Power Query but no Power Pivot model.

---

## Gap 2: Named Ranges / Defined Names (within xlsx/xlsm)

### What It Is
Named ranges assign human-readable names to cell ranges, formulas, or constants (e.g., `TaxRate = 0.08`, `SalesData = Sheet1!$A$1:$Z$500`). They are the "API" of the workbook — how formulas reference data semantically.

### Where It Lives
`xl/workbook.xml` → `<definedNames>` → `<definedName name="X" ...>reference</definedName>`

Scope: `localSheetId` attribute = sheet-scoped (private); absent = global.

### How to Extract
`openpyxl` (already a dependency) supports this directly:

```python
wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
for name, defn in wb.defined_names.items():
    print(name, defn.attr_text, defn.localSheetId)
    for sheet_title, cell_range in defn.destinations:
        print(f"  → {sheet_title}!{cell_range}")
```

### What We'd Surface
- Name, scope (global or sheet-local)
- Reference (cell range, formula, or constant)
- Whether it points to a range vs. a formula expression

### Reveal Implementation
```
reveal file.xlsx?names=list             # all defined names
reveal file.xlsx?names=TaxRate          # specific named range
```

### Priority: **HIGH**
Named ranges are fundamental workbook structure — they reveal how formulas reference data. Useful in every large workbook. Zero new dependencies.

---

## Gap 3: Standard Pivot Tables (within xlsx/xlsm)

### What It Is
Standard Excel pivot tables (not Power Pivot) are cached summaries of sheet data. The metadata reveals which fields are rows, columns, values, and filters — the analytical structure of the data.

**Note:** Power Pivot (SSAS data model) is completely separate — reveal already handles that via `?powerpivot=`. This is about **regular** pivot tables built on worksheet ranges.

### Where It Lives
- `xl/pivotTables/pivotTable1.xml` — table structure, field assignments
- `xl/pivotCache/pivotCacheDefinition1.xml` — field names, data types
- Linked: the pivotTable XML references the cache via `cacheId`

### How to Extract
`openpyxl` has partial support (read-only, internal API):

```python
for ws in wb.worksheets:
    for pt in ws._pivots:
        print(pt.name)                              # pivot table name
        print(pt.location.ref)                      # placement in sheet
        for f in pt.cache.cacheFields:              # field definitions
            print(f.name)
        for df in pt.dataFields:                    # value fields
            print(df.name, df.subtotal)             # with aggregation
```

Alternatively, raw XML parsing on `xl/pivotTables/` and `xl/pivotCache/` for more reliable access.

### What We'd Surface
- Table name and location
- Source data range
- Row fields, column fields, data/value fields (with aggregation function: SUM, COUNT, AVG, etc.)
- Filter/page fields

### Reveal Implementation
```
reveal file.xlsx?pivots=list            # all pivot tables, names + locations
reveal file.xlsx?pivots=SalesByRegion   # specific pivot table structure
```

### Priority: **MEDIUM**
Pivot tables reveal analytical intent. Common in finance/ops worksheets. Uses existing `openpyxl` dependency.

---

## Gap 4: External Data Connections (within xlsx/xlsm)

### What It Is
Connections to external data sources: ODBC databases, OLE DB, web queries, SharePoint lists, text files, Power Query connections. Reveals where the workbook pulls its data from.

### Where It Lives
`xl/connections.xml` — list of `<connection>` elements. Each has:
- `name` — connection name
- `type` — 1=ODBC, 2=OLE DB, 3=Web, 4=Text, 5=ADO, 100=Power Query
- `connectionString` — full connection string (may contain server/database/credentials)
- `command` — SQL query or table name
- `commandType` — 1=table name, 2=SQL query, 3=cube name

`xl/queryTables/queryTable*.xml` — links sheet ranges to connections via `connectionId`.

### How to Extract
No library support — raw XML parsing:

```python
with zipfile.ZipFile(xlsx_path) as zf:
    if "xl/connections.xml" in zf.namelist():
        tree = ET.parse(zf.open("xl/connections.xml"))
        # walk <connection> elements
```

### What We'd Surface
- Connection name, type, source (server/database/file/URL)
- SQL command or table name
- Whether it refreshes on open

### Security Note
Connection strings may contain credentials (username, sometimes password). Reveal should output these as-is (they're already in the file); this is valuable for security audits.

### Reveal Implementation
```
reveal file.xlsx?connections=list       # all connections, name + type + source
reveal file.xlsx?connections=show       # full connection strings + SQL
```

### Priority: **HIGH**
Connections reveal the complete data lineage of the workbook — where all data comes from. Zero new dependencies (stdlib only).

---

## Gap 5: VBA/Macro Extraction (xlsm files)

### What It Is
`.xlsm` files can contain VBA macro code. Currently reveal lists xlsm as "supported" but explicitly states "macros not executed or extracted." Extracting (not executing) VBA source code is safe and highly valuable — you can see what automation the workbook does, identify auto-execute macros, and flag suspicious patterns.

### Where It Lives
`xl/vbaProject.bin` — an OLE2 Compound File Binary (not a ZIP entry, embedded within the xlsx ZIP). VBA source code is P-code compressed within OLE2 streams.

### How to Extract
Requires `oletools` library (`pip install oletools`):

```python
from oletools.olevba import VBA_Parser

parser = VBA_Parser(str(xlsx_path))
for (filename, ole_stream, vba_filename, vba_code) in parser.extract_macros():
    print(f"# Module: {vba_filename}")
    print(vba_code)
```

**oletools also detects:**
- Auto-executable macros (`Auto_Open`, `Workbook_Open`, `Document_Open`)
- Suspicious API calls (`Shell`, `CreateObject`, `WScript.Shell`)

### What We'd Surface
- VBA module names and full source code
- Auto-execute macro detection (flagged with ⚠️)
- Module type (standard, class, form, sheet, workbook)

### Reveal Implementation
```
reveal file.xlsm?vba=list              # module names + line counts
reveal file.xlsm?vba=show             # all modules, full source
reveal file.xlsm?vba=Sheet1           # specific module
```

### Priority: **MEDIUM**
Highly valuable for security audits and understanding xlsm behavior. Requires new dependency (`oletools`). Should be optional (graceful degradation if not installed).

---

## Gap 6: `.xlsb` Binary Format

### What It Is
Excel Binary Workbook — a compressed binary format (BIFF12) used for large files where xlsx XML would be too slow. Same data as xlsx but without the human-readable XML layer. Often used for performance in large enterprise workbooks.

### Python Support
| Library | Capability |
|---------|------------|
| `pyxlsb` | Sheet names, cell values, limited formula text. No named ranges, connections, or Power Pivot. |
| `pyxlsb2` | Fork; keeps data in memory; also handles macro sheets. |
| `pandas.read_excel(engine='pyxlsb')` | Delegates to pyxlsb; data only. |

**openpyxl does NOT support xlsb.**

### What We'd Surface
- Sheet names and dimensions
- Cell data (rows/cols/ranges)
- Basic workbook metadata

**Not available from xlsb:** Power Pivot, named ranges, connections, pivot table metadata. The binary format hides these.

### Reveal Implementation
Requires new file type detection + adapter extension or separate adapter. Most functionality would mirror xlsx sheet-data queries.

```
reveal file.xlsb                        # workbook overview
reveal file.xlsb?sheet=Sales            # sheet data
```

### Priority: **LOW–MEDIUM**
Useful but limited — xlsb doesn't expose the rich structural metadata that makes xlsx valuable. Requires `pyxlsb` as a new optional dependency.

---

## Gap 7: `.pbix` Power BI Desktop Files

### What It Is
Power BI Desktop files contain a full BI solution: data model (tables, columns, DAX measures, M queries, relationships), report pages with visuals, and potentially loaded data. This is the richest BI artifact format.

### File Structure (ZIP)
```
DataModel          # Binary VertiPaq store — tables, columns, DAX, M, relationships
Report/Layout      # JSON (no extension) — report pages, visuals, positions, filters
Connections        # JSON — connection parameters
[Content_Types].xml
docProps/custom.xml # author, version metadata
SecurityBindings
```

### Python Support
`pbixray` (already installed at `/home/scottsen/.local/lib/python3.10/site-packages`) handles everything:

```python
from pbixray import PBIXRay

data = PBIXRay("file.pbix")
data.tables              # DataFrame: TableName
data.schema              # DataFrame: TableName, ColumnName, PandasDataType
data.dax_measures        # DataFrame: TableName, Name, Expression, DisplayFolder, Description
data.dax_columns         # DataFrame: TableName, Name, Expression (calculated columns)
data.get_power_query()   # DataFrame: TableName, Expression (M code)
data.get_m_parameters()  # DataFrame: ParameterName, Value, Type
data.relationships       # DataFrame: From/To Table/Column, IsActive, Cardinality, CrossFilteringBehavior
data.get_model_size()    # dict: model size stats
data.get_statistics()    # DataFrame: model statistics
```

**Report layout** — extract visuals and pages from `Report/Layout` JSON:
```python
with zipfile.ZipFile("file.pbix") as zf:
    layout = json.loads(zf.read("Report/Layout"))
    for page in layout["sections"]:
        print(page["displayName"])
        for visual in page.get("visualContainers", []):
            print(visual.get("config", {}))  # visual type, fields, title
```

### PBIR Format (New Default: 2026)
Power BI Service defaulted to PBIR in January 2026; Desktop followed in March 2026. PBIR stores everything as human-readable JSON files (not a single binary blob) — much easier to parse without pbixray. A separate adapter approach is warranted.

### What We'd Surface
From a `.pbix`:
- Data model: same as xlsx Power Pivot (tables, schema, DAX, M, relationships)
- Report pages: page names, visual types, visual titles, field bindings
- Model statistics and size

### Reveal Implementation
New adapter `pbix://` (or extension of xlsx adapter with file type detection):
```
reveal file.pbix                         # overview: model tables + report pages
reveal file.pbix?model=schema            # full table/column schema
reveal file.pbix?model=dax               # all DAX measures + expressions
reveal file.pbix?model=powerquery        # all M queries
reveal file.pbix?model=relationships     # relationship graph
reveal file.pbix?report=pages            # page names + visual count per page
reveal file.pbix?report=Salesoverview    # visuals on a specific page
```

### Priority: **HIGH**
pbixray is already installed. pbix files are the primary artifact for Power BI work — understanding the model and report structure from the CLI is extremely valuable. Most of the hard work (pbixray integration) is already done from the xlsx Tier 2 work.

---

## Gap 8: `.pbit` Power BI Template Files

### What It Is
Power BI Template — like a `.pbix` but with data stripped. Contains the full model schema and M queries but no data. Used for sharing report templates.

### File Structure (ZIP)
```
DataModelSchema    # UTF-16-LE encoded JSON — complete TMSL model definition
Report/Layout      # JSON — same as pbix (report pages + visuals)
Version
[Content_Types].xml
```

**Key advantage over pbix:** `DataModelSchema` is **plain JSON** (UTF-16-LE encoded), not binary VertiPaq. No pbixray needed — stdlib only.

### How to Extract
```python
with zipfile.ZipFile("file.pbit") as zf:
    raw = zf.read("DataModelSchema")
    schema = json.loads(raw.decode("utf-16-le"))  # critical: UTF-16-LE, not UTF-8
    # schema["model"]["tables"] → list of tables with measures, columns, partitions
    # schema["model"]["relationships"] → list of relationship objects
```

M query code lives in partition `source` expressions within the `tables` array.

### What We'd Surface
- Tables, columns, DAX measures, calculated columns, hierarchies
- M query expressions (as partition source code)
- Report pages and visuals (from `Report/Layout`)
- Model metadata

### Priority: **MEDIUM**
Pure stdlib, no new dependencies. pbit is less common than pbix but valuable when encountered. Easy win once pbix adapter exists.

---

## Gap 9: `.bim` Tabular Model Files

### What It Is
JSON artifact for SSAS Tabular, Azure Analysis Services, and Power BI Premium datasets. Used as the source-control format. The `DataModelSchema` in `.pbit` is essentially a BIM file.

### Format
Single JSON file following the TMSL schema:
```json
{
  "model": {
    "tables": [
      {
        "name": "Sales",
        "measures": [{"name": "Total Revenue", "expression": "SUMX(...)"}],
        "columns": [...],
        "partitions": [{"source": {"type": "m", "expression": "..."}}]
      }
    ],
    "relationships": [...],
    "roles": [...],
    "perspectives": [...]
  }
}
```

### How to Extract
Pure stdlib `json.load()`. The entire model is navigable as a Python dict.

### What We'd Surface
- Full model: tables, columns, measures (with DAX), calculated columns
- M queries (partition source expressions)
- Relationships, roles, perspectives, hierarchies
- KPIs, translation layers

### Reveal Implementation
New adapter `bim://` or extension of a tabular model adapter:
```
reveal file.bim                          # overview: tables + measure count
reveal file.bim?tables=Sales             # Sales table details
reveal file.bim?measures=all             # all DAX measures
reveal file.bim?relationships=all        # relationship graph
```

### Priority: **LOW**
Less commonly encountered in file systems. But when present, is the most structured and complete BI artifact. Zero new dependencies.

---

## Gap 10: DAX Dependency Analysis

### What It Is
Within a set of DAX measures, understanding which measures reference other measures or columns — building a dependency graph. Useful for impact analysis ("if I change measure X, what breaks?").

### Libraries
| Library | Source | Capability |
|---------|--------|------------|
| `daxparser` | `pip install daxparser` (bmsuisse/daxparser) | `get_columns_or_measures(dax_str)` — returns all column/measure references in a DAX expression. ANTLR-based. |
| `PyDAXLexer` | GitHub (jurgenfolz/PyDAXLexer) | Lex DAX; extract comments; identify references |

**Limitation:** No Python library does full DAX semantic analysis or type checking. These tools do lexing/tokenizing only. For production DAX analysis, DAX Studio remains authoritative.

### What We'd Surface
Per measure: which other measures and columns it depends on. Across a model: which measures are "leaf" (no dependencies) vs. "derived" (depends on others).

### Reveal Implementation
Extension of `?powerpivot=dax` mode:
```
reveal file.xlsx?powerpivot=dax&deps=true   # show dependencies alongside each measure
reveal file.xlsx?powerpivot=deps            # full dependency graph
```

### Priority: **LOW**
High value conceptually but `daxparser` has low adoption (32 weekly downloads) and unknown edge-case coverage. Revisit after pbixray Tier 2 and Power Query work stabilizes.

---

## Implementation Roadmap

### Phase 1: No-new-dependency wins (within xlsx/xlsm)

| Feature | Approach | Query Param |
|---------|----------|-------------|
| External connections | stdlib: zipfile + XML on `xl/connections.xml` | `?connections=` |
| Named ranges | openpyxl: `wb.defined_names` | `?names=` |
| Power Query M (basic) | stdlib: zipfile + base64 + inner-zip on DataMashup | `?powerquery=` |

### Phase 2: Existing dependency (pbixray already installed)

| Feature | Approach | File Type |
|---------|----------|-----------|
| Tier 2 Power Pivot (modern xlsx) | pbixray on `xl/model/item.data` | .xlsx |
| Power Query M via pbixray | `data.get_power_query()` | .xlsx, .pbix |
| `.pbix` full adapter | pbixray + `Report/Layout` JSON | .pbix |

### Phase 3: New file types, stdlib only

| Feature | Approach | Priority |
|---------|----------|---------|
| `.pbit` template adapter | zipfile + json (UTF-16-LE DataModelSchema) | Medium |
| `.bim` tabular model adapter | json stdlib | Low |

### Phase 4: New optional dependencies

| Feature | Library | Priority |
|---------|---------|---------|
| Standard pivot tables | openpyxl `ws._pivots` (already installed) | Medium |
| VBA/macro extraction (xlsm) | `oletools` (`olevba`) | Medium |
| `.xlsb` binary format | `pyxlsb` | Low |
| DAX dependency graph | `daxparser` | Low |

---

## Library Inventory

| Library | Status | Used For |
|---------|--------|----------|
| `zipfile` | stdlib | All zip-based formats |
| `xml.etree.ElementTree` | stdlib | XML parsing within xlsx |
| `base64` | stdlib | DataMashup inner-zip decode |
| `json` | stdlib | pbit DataModelSchema, pbix Report/Layout, bim |
| `openpyxl` | installed | Named ranges, pivot tables |
| `pbixray` 0.5.0 | installed | Modern xlsx Tier 2, pbix adapter, Power Query |
| `oletools` | NOT installed | VBA extraction from xlsm |
| `pyxlsb` | NOT installed | xlsb binary format |
| `daxparser` | NOT installed | DAX reference extraction |
| `excel-datamashup` | NOT installed | Alternative DataMashup parser |

---

## Notes on the PBIR Format (2026+)

Power BI Report Format (PBIR), which became the default for Power BI Service in January 2026 and Desktop in March 2026, stores everything as human-readable JSON files rather than a single binary blob. The structure is a folder with:

```
.pbip / .pbir          # project/report manifest
model.bim              # tabular model (JSON)
report/                # report pages as individual JSON files
```

This format is inherently more tool-friendly than pbix. When PBIR files appear in reveal's path, the `.bim` adapter handles the model, and individual JSON files in `report/` handle the layout. No pbixray needed.

---

*See also:* [XLSX_ADAPTER_GUIDE.md](XLSX_ADAPTER_GUIDE.md) — current xlsx capabilities, capability matrix, and implementation details.
