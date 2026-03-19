# xlsx Test Fixtures

Real-world `.xlsx` files for testing the `xlsx://` adapter against live data.
These are NOT committed to git — they are downloaded on demand (see below).

## Download Script

```bash
# From repo root
bash tests/fixtures/xlsx/download.sh
```

---

## General Fixtures (`tests/fixtures/xlsx/`)

| File | Source | Key Features | Size |
|------|--------|-------------|------|
| `AdventureWorks_Sales.xlsx` | [microsoft/powerbi-desktop-samples](https://github.com/microsoft/powerbi-desktop-samples) | 121K rows, 7 sheets, `Sales_data` sheet is 72 MB (triggers too-large guard) | 14 MB |
| `AdventureWorksDW.xlsx` | [PacktPublishing](https://github.com/PacktPublishing/Microsoft-Power-BI-Quick-Start-Guide) | 6 sheets, `FactInternetSales` is 58.5 MB (triggers too-large guard) | 12 MB |
| `Financial_Sample.xlsx` | [theoyinbooke/30Days](https://github.com/theoyinbooke/30Days-of-Learning-Data-Analysis-Using-Power-BI-for-Students) | 701 rows, 16 cols, real financial data | 82 KB |
| `dynamic_arrays.xlsx` | Generated (xlsxwriter) | SORT/FILTER/UNIQUE/SEQUENCE formulas, structured Table, sparse rows | 8 KB |

### What These Test

- **Too-large sheet guard**: `AdventureWorksDW.xlsx` (`FactInternetSales` 58.5 MB) and `AdventureWorks_Sales.xlsx` (`Sales_data` 72 MB) — both trigger the 50 MB limit and should show `too large to parse (N MB)` rather than `0 rows, 0 cols`
- **Column count from dimension ref**: `dynamic_arrays.xlsx` — row 1 has 7 header cells but dimension ref is `A1:P11` (16 cols). Validates that col count comes from the dimension tag, not first-row cell count
- **Real-world multi-sheet**: `AdventureWorksDW.xlsx` — 6 sheets, large dimension refs, accurate row/col counts
- **Large datasets**: `AdventureWorks_Sales.xlsx` — 121K rows verifies that shared strings and row counting work at scale

---

## PowerPivot Fixtures (`tests/fixtures/xlsx/powerpivot/`)

Two distinct categories based on what reveal can extract:

### Category A: Full XMLA — Tables + Columns + DAX + Relationships

These files contain `customXml/itemN.xml` with UTF-16 Gemini XMLA metadata alongside the binary `item.data` model. Reveal extracts everything.

| File | Format | Model Path | Tables | Measures | Relationships | Source |
|------|--------|-----------|--------|----------|---------------|--------|
| `Contoso_PnL_Excel2010.xlsx` | Excel 2010 | `xl/customData/item1.data` (5.8 MB) | 4 (Accounts, Executive Geography, Finance Data, Date) | 81 DAX measures | 3 (Finance Data → Accounts/ExecGeo/Date) | [Microsoft download id=38838](https://www.microsoft.com/en-us/download/details.aspx?id=38838) |
| `Contoso_PnL_Excel2013.xlsx` | Excel 2013 | `xl/model/item.data` (5.8 MB) | 4 (same model, different storage path) | 81 DAX measures | 3 (same relationships) | [Microsoft download id=38838](https://www.microsoft.com/en-us/download/details.aspx?id=38838) |

**What reveal can do with these:**
```bash
reveal "xlsx://Contoso_PnL_Excel2010.xlsx?powerpivot=schema"        # tables + columns
reveal "xlsx://Contoso_PnL_Excel2010.xlsx?powerpivot=dax"           # all 81 DAX measures with expressions
reveal "xlsx://Contoso_PnL_Excel2010.xlsx?powerpivot=relationships"  # 3 FK relationships
reveal "xlsx://Contoso_PnL_Excel2010.xlsx?powerpivot=tables"         # table list only
reveal "xlsx://Contoso_PnL_Excel2013.xlsx?powerpivot=schema"        # same model, 2013 storage format
```

**Contoso model structure:**
- `Finance Data` (10 cols) — fact table: Fiscal Month, Profit Center, Account, Actual, Budget, Forecast, Actual People, Budget People, Forecast People, CalculatedColumn1
- `Accounts` (5 cols) — dim: Account, Line Item, Group, Sub Class, Class
- `Executive Geography` (9 cols) — dim: Profit Center + 8 derived columns
- `Date` (5 cols) — dim: Date, Fiscal Year, Fiscal Qtr, Fiscal Month, Month
- Relationships: Finance Data[Account] → Accounts, Finance Data[Profit Center] → Exec Geo, Finance Data[CalculatedColumn1] → Date

### Category B: No XMLA — Table Names Only (pivot cache fallback)

These files have `xl/model/item.data` but no Gemini XMLA metadata in `customXml/`. Reveal falls back to scanning `pivotCacheDefinition` files for `cacheHierarchy` element names. Columns, DAX, and relationships are unavailable.

| File | Tables | Note | Source |
|------|--------|------|--------|
| `Human_Resources.xlsx` | 9 (AgeGroup, BU, Date, Employee, Ethnicity, FP, Gender, PayType, SeparationReason) | 9.8 MB model | [microsoft/powerbi-desktop-samples](https://github.com/microsoft/powerbi-desktop-samples/tree/main/powerbi-service-samples) |
| `Retail_Analysis.xlsx` | 5 (District, Item, Sales, Store, Time) | 12.7 MB model | same |
| `Sales_Marketing.xlsx` | 6 (Date, Geo, Manufacturer, Product, SalesFact, Sentiment) | 8.0 MB model | same |
| `Customer_Profitability.xlsx` | 0 (no pivot cache tables found) | 2.7 MB model | same |

**What reveal can do with these:**
```bash
reveal "xlsx://Human_Resources.xlsx?powerpivot=schema"  # table names only, no columns
reveal "xlsx://Human_Resources.xlsx?powerpivot=dax"     # empty + "XMLA absent" message
```

### Capability Matrix

| Capability | Excel 2010 (customData) | Excel 2013+ (model/item.data + XMLA) | Modern (model/item.data, no XMLA) |
|------------|------------------------|--------------------------------------|----------------------------------|
| Detect model | ✅ | ✅ | ✅ |
| Table names | ✅ | ✅ | ✅ (from pivot cache) |
| Column names | ✅ | ✅ | ❌ |
| DAX measures + expressions | ✅ | ✅ | ❌ |
| Relationships | ✅ | ✅ | ❌ |
| Power Query (DataMashup) | n/a | n/a | ❌ not detected |

---

## Download Script

```bash
#!/bin/bash
# tests/fixtures/xlsx/download.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Downloading general xlsx fixtures..."
curl -L -o "$DIR/AdventureWorks_Sales.xlsx" \
  "https://raw.githubusercontent.com/microsoft/powerbi-desktop-samples/main/AdventureWorks%20Sales%20Sample/AdventureWorks%20Sales.xlsx"
curl -L -o "$DIR/AdventureWorksDW.xlsx" \
  "https://raw.githubusercontent.com/PacktPublishing/Microsoft-Power-BI-Quick-Start-Guide/master/Data%20Sources/AdventureWorksDW.XLSX"
curl -L -o "$DIR/Financial_Sample.xlsx" \
  "https://raw.githubusercontent.com/theoyinbooke/30Days-of-Learning-Data-Analysis-Using-Power-BI-for-Students/main/Financial%20Sample.xlsx"

echo "Downloading PowerPivot fixtures..."
PP="$DIR/powerpivot"

# Contoso PnL (full XMLA — Excel 2010 format)
TMP=$(mktemp -d)
curl -L -o "$TMP/contoso2010.zip" \
  "https://download.microsoft.com/download/b/e/c/becf5873-6b88-4920-9096-2c10ba98de60/ContosoPnL_Excel2010.zip"
unzip -o "$TMP/contoso2010.zip" -d "$TMP"
cp "$TMP/ContosoPnL_Excel2010/ContosoPnL_Excel2010.xlsx" "$PP/Contoso_PnL_Excel2010.xlsx"

# Contoso PnL (full XMLA — Excel 2013 format)
curl -L -o "$TMP/contoso2013.zip" \
  "https://download.microsoft.com/download/b/e/c/becf5873-6b88-4920-9096-2c10ba98de60/ContosoPnL_Excel2013.zip"
unzip -o "$TMP/contoso2013.zip" -d "$TMP"
cp "$TMP/ContosoPnL_Excel2013/ContosoPnL_Excel2013.xlsx" "$PP/Contoso_PnL_Excel2013.xlsx"
rm -rf "$TMP"

# Power BI service samples (pivot cache fallback — no XMLA)
BASE="https://raw.githubusercontent.com/microsoft/powerbi-desktop-samples/main/powerbi-service-samples"
curl -L -o "$PP/Human_Resources.xlsx"       "$BASE/Human%20Resources%20Sample-no-PV.xlsx"
curl -L -o "$PP/Retail_Analysis.xlsx"       "$BASE/Retail%20Analysis%20Sample-no-PV.xlsx"
curl -L -o "$PP/Sales_Marketing.xlsx"       "$BASE/Sales%20and%20Marketing%20Sample-no-PV.xlsx"
curl -L -o "$PP/Customer_Profitability.xlsx" "$BASE/Customer%20Profitability%20Sample-no-PV.xlsx"

echo "Done. $(ls $DIR/*.xlsx $PP/*.xlsx | wc -l) fixtures ready."
```
