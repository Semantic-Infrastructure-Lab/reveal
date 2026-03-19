#!/bin/bash
# Download real-world xlsx fixtures for testing the xlsx:// adapter.
# Run from any directory. Files are placed relative to this script.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PP="$DIR/powerpivot"
mkdir -p "$PP"

echo "==> General xlsx fixtures"
curl -L -o "$DIR/AdventureWorks_Sales.xlsx" \
  "https://raw.githubusercontent.com/microsoft/powerbi-desktop-samples/main/AdventureWorks%20Sales%20Sample/AdventureWorks%20Sales.xlsx"
curl -L -o "$DIR/AdventureWorksDW.xlsx" \
  "https://raw.githubusercontent.com/PacktPublishing/Microsoft-Power-BI-Quick-Start-Guide/master/Data%20Sources/AdventureWorksDW.XLSX"
curl -L -o "$DIR/Financial_Sample.xlsx" \
  "https://raw.githubusercontent.com/theoyinbooke/30Days-of-Learning-Data-Analysis-Using-Power-BI-for-Students/main/Financial%20Sample.xlsx"

echo "==> PowerPivot fixtures (full XMLA — Contoso)"
TMP=$(mktemp -d)
trap "rm -rf $TMP" EXIT

curl -L -o "$TMP/contoso2010.zip" \
  "https://download.microsoft.com/download/b/e/c/becf5873-6b88-4920-9096-2c10ba98de60/ContosoPnL_Excel2010.zip"
unzip -q -o "$TMP/contoso2010.zip" -d "$TMP/c2010"
cp "$TMP/c2010/ContosoPnL_Excel2010/ContosoPnL_Excel2010.xlsx" "$PP/Contoso_PnL_Excel2010.xlsx"

curl -L -o "$TMP/contoso2013.zip" \
  "https://download.microsoft.com/download/b/e/c/becf5873-6b88-4920-9096-2c10ba98de60/ContosoPnL_Excel2013.zip"
unzip -q -o "$TMP/contoso2013.zip" -d "$TMP/c2013"
cp "$TMP/c2013/ContosoPnL_Excel2013/ContosoPnL_Excel2013.xlsx" "$PP/Contoso_PnL_Excel2013.xlsx"

echo "==> PowerPivot fixtures (pivot cache fallback — Power BI samples)"
BASE="https://raw.githubusercontent.com/microsoft/powerbi-desktop-samples/main/powerbi-service-samples"
curl -L -o "$PP/Human_Resources.xlsx"        "$BASE/Human%20Resources%20Sample-no-PV.xlsx"
curl -L -o "$PP/Retail_Analysis.xlsx"        "$BASE/Retail%20Analysis%20Sample-no-PV.xlsx"
curl -L -o "$PP/Sales_Marketing.xlsx"        "$BASE/Sales%20and%20Marketing%20Sample-no-PV.xlsx"
curl -L -o "$PP/Customer_Profitability.xlsx" "$BASE/Customer%20Profitability%20Sample-no-PV.xlsx"

COUNT=$(ls "$DIR"/*.xlsx "$PP"/*.xlsx 2>/dev/null | wc -l)
echo "Done. $COUNT fixtures ready."
