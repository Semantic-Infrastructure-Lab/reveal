"""CSV/TSV file analyzer.

Handles comma-separated values and tab-separated values files.
Provides schema inference and data quality metrics.
"""

import csv
import logging
from typing import Dict, List, Any, Optional
from ..base import FileAnalyzer
from ..registry import register

logger = logging.getLogger(__name__)


@register('.csv', name='CSV', icon='📊')
@register('.tsv', name='TSV', icon='📊')
class CsvAnalyzer(FileAnalyzer):
    """CSV/TSV file analyzer.

    Analyzes tabular data files with comma or tab delimiters.
    Common uses: data exports, ETL pipelines, ML datasets, spreadsheet exports.

    Structure view shows:
    - Column names and count
    - Row count
    - Inferred data types per column
    - Missing value counts
    - Sample values from each column

    Extract by row number to view specific records.
    """

    def _infer_type(self, values: List[str]) -> str:
        """Infer data type from sample values.

        Args:
            values: List of string values (non-empty, non-null)

        Returns:
            Type name: 'integer', 'float', 'boolean', 'string'
        """
        if not values:
            return 'unknown'

        # Sample up to 100 values for type inference
        sample = values[:100]

        # Try integer
        try:
            all(int(v) for v in sample if v.strip())
            return 'integer'
        except (ValueError, AttributeError):
            pass

        # Try float
        try:
            all(float(v) for v in sample if v.strip())
            return 'float'
        except (ValueError, AttributeError):
            pass

        # Try boolean
        bool_values = {'true', 'false', 'yes', 'no', '0', '1', 't', 'f', 'y', 'n'}
        if all(v.strip().lower() in bool_values for v in sample if v.strip()):
            return 'boolean'

        return 'string'

    def _get_delimiter(self, content: str) -> str:
        """Detect delimiter from file content.

        Args:
            content: File content

        Returns:
            Delimiter character (',' or '\t')
        """
        # Use csv.Sniffer to detect delimiter
        try:
            sniffer = csv.Sniffer()
            sample = '\n'.join(content.split('\n')[:5])  # First 5 lines
            dialect = sniffer.sniff(sample)
            return dialect.delimiter
        except Exception:
            # Fallback: check file extension
            if str(self.path).endswith('.tsv'):
                return '\t'
            return ','

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, Any]:
        """Extract CSV schema and statistics.

        Args:
            head: Show first N rows
            tail: Show last N rows
            range: Show rows in range (start, end) - 1-indexed
            **kwargs: Additional parameters (unused)

        Returns:
            Dict with schema, statistics, and sample rows
        """
        delimiter = self._get_delimiter(self.content)

        # Parse CSV
        reader = csv.reader(self.lines, delimiter=delimiter)

        try:
            # Get header row
            header = next(reader)
            columns = [col.strip() for col in header]

            # Read all data rows
            rows = []
            for row in reader:
                if row:  # Skip empty rows
                    rows.append(row)

            if not rows:
                return {
                    'columns': columns,
                    'row_count': 0,
                    'schema': [],
                    'message': 'Empty CSV file (header only)'
                }

            # Collect column statistics
            schema = []
            for col_idx, col_name in enumerate(columns):
                # Get all values for this column
                col_values = [row[col_idx] if col_idx < len(row) else ''
                             for row in rows]

                # Count missing/empty values
                missing_count = sum(1 for v in col_values if not v or not v.strip())
                non_empty_values = [v for v in col_values if v and v.strip()]

                # Infer type from non-empty values
                inferred_type = self._infer_type(non_empty_values)

                # Get unique value count and sample
                unique_values = list(set(non_empty_values))[:5]

                schema.append({
                    'name': col_name,
                    'type': inferred_type,
                    'missing': missing_count,
                    'missing_pct': round(missing_count / len(rows) * 100, 1),
                    'unique_count': len(set(col_values)),
                    'sample_values': unique_values[:3]
                })

            # Apply filtering if requested
            sample_rows = rows
            if head is not None:
                sample_rows = rows[:head]
            elif tail is not None:
                sample_rows = rows[-tail:]
            elif range is not None:
                start, end = range
                sample_rows = rows[start-1:end]  # Convert to 0-indexed
            else:
                # Default: show first 5 rows
                sample_rows = rows[:5]

            return {
                'columns': columns,
                'column_count': len(columns),
                'row_count': len(rows),
                'schema': schema,
                'sample_rows': [dict(zip(columns, row)) for row in sample_rows],
                'delimiter': 'comma' if delimiter == ',' else 'tab'
            }

        except StopIteration:
            # No header row
            return {
                'row_count': 0,
                'message': 'CSV file appears to be empty or malformed'
            }
        except Exception as e:
            logger.debug(f"Error parsing CSV {self.path}: {e}")
            return {
                'error': str(e),
                'message': 'Failed to parse CSV file'
            }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get a specific row by number.

        Args:
            element_name: Row number (1-indexed)
            **kwargs: Additional parameters (unused)

        Returns:
            Dict with row data or None if not found
        """
        try:
            row_num = int(element_name)
        except ValueError:
            return None

        delimiter = self._get_delimiter(self.content)
        reader = csv.reader(self.lines, delimiter=delimiter)

        try:
            header = next(reader)
            columns = [col.strip() for col in header]

            # Skip to requested row
            for idx, row in enumerate(reader, start=1):
                if idx == row_num:
                    return {
                        'row_number': row_num,
                        'data': dict(zip(columns, row))
                    }

            return None  # Row not found

        except StopIteration:
            return None
