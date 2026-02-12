"""JSONL (JSON Lines) file analyzer.

Handles conversation logs, streaming data, and other line-delimited JSON formats.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from ..base import FileAnalyzer
from ..registry import register

logger = logging.getLogger(__name__)


@register('.jsonl', name='JSONL', icon='📜')
class JsonlAnalyzer(FileAnalyzer):
    """JSONL file analyzer.

    Analyzes JSON Lines format where each line is a complete JSON object.
    Common uses: conversation logs, streaming data, event logs.

    Structure view shows:
    - Total record count
    - Record types distribution
    - Sample of first few records

    Extract by record number to view specific entries.
    """

    def _build_preview(self, obj: Dict[str, Any]) -> str:
        """Build a preview string for a JSONL record.

        Args:
            obj: Parsed JSON object

        Returns:
            Preview string showing key content
        """
        # For conversation logs, show role and snippet
        if 'message' in obj and isinstance(obj['message'], dict):
            preview = self._preview_conversation_message(obj['message'])
            if preview:
                return preview

        # Fallback: show top-level keys
        keys = list(obj.keys())[:5]
        return f"keys: {', '.join(keys)}"

    def _preview_conversation_message(self, message: Dict[str, Any]) -> str:
        """Extract preview from conversation message format.

        Args:
            message: Message dict with role/content

        Returns:
            Preview string or empty if not applicable
        """
        parts = []

        # Add role if present
        role = message.get('role', '')
        if role:
            parts.append(f"role={role}")

        # Get content preview
        content = message.get('content', '')
        if isinstance(content, str):
            snippet = content[:50].replace('\n', ' ')
            if len(content) > 50:
                snippet += '...'
            parts.append(f'"{snippet}"')
        elif isinstance(content, list) and content:
            # Claude API format with content blocks
            first_block = content[0]
            if isinstance(first_block, dict) and 'text' in first_block:
                text = first_block['text'][:50].replace('\n', ' ')
                if len(first_block['text']) > 50:
                    text += '...'
                parts.append(f'"{text}"')

        return ' | '.join(parts) if parts else ''

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract JSONL record summary.

        Args:
            head: Show first N records
            tail: Show last N records
            range: Show records in range (start, end) - 1-indexed
            **kwargs: Additional parameters (unused)

        Returns:
            Dict with 'records' key containing record summaries

        Default (no args): Shows first 10 records as samples
        """
        DEFAULT_LIMIT = 10  # Show first 10 when no args specified

        # First pass: parse all records and track metadata
        all_records = []
        record_types = {}
        total_records = 0

        for i, line in enumerate(self.lines, 1):
            line = line.strip()
            if not line:  # Skip empty lines
                continue

            try:
                obj = json.loads(line)
                total_records += 1

                # Track record type if present
                rec_type = obj.get('type', 'record')
                record_types[rec_type] = record_types.get(rec_type, 0) + 1

                # Store all records for slicing
                preview = self._build_preview(obj)
                all_records.append({
                    'line': i,
                    'name': f"{rec_type} #{total_records}",
                    'preview': preview,
                })

            except json.JSONDecodeError as e:
                # Track malformed records
                all_records.append({
                    'line': i,
                    'name': '⚠️ Invalid JSON',
                    'preview': f'Parse error: {str(e)[:50]}',
                })

        # Apply semantic slicing using base class helper
        if head or tail or range:
            # User explicitly requested slicing - apply it
            selected_records = self._apply_semantic_slice(all_records, head, tail, range)
        else:
            # Default: show first 10 as samples
            selected_records = all_records[:DEFAULT_LIMIT]

        # Add summary as metadata (always included)
        summary = {
            'line': 0,
            'name': f'📊 Summary: {total_records} records',
            'preview': ', '.join(f'{k}: {v}' for k, v in
                                sorted(record_types.items(), key=lambda x: -x[1])),
        }

        return {
            'records': [summary] + selected_records,
        }

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a specific JSONL record.

        Args:
            element_type: 'record'
            name: Record number (1-based) or type filter like "user", "assistant"

        Returns:
            Dict with record content
        """
        # Try to parse as record number
        try:
            record_num = int(name)
            return self._extract_by_number(record_num)
        except ValueError:
            # Not a number, try as type filter instead
            logger.debug(f"'{name}' is not a record number, trying as type filter")
            pass

        # Try as type filter
        if element_type == 'record':
            return self._extract_by_type(name)

        return super().extract_element(element_type, name)

    def _extract_by_number(self, record_num: int) -> Optional[Dict[str, Any]]:
        """Extract record by number (1-based)."""
        current = 0

        for i, line in enumerate(self.lines, 1):
            line = line.strip()
            if not line:
                continue

            current += 1
            if current == record_num:
                try:
                    obj = json.loads(line)
                    # Pretty print the JSON
                    pretty = json.dumps(obj, indent=2)

                    return {
                        'name': f'Record {record_num}',
                        'line_start': i,
                        'line_end': i,
                        'source': pretty,
                    }
                except json.JSONDecodeError:
                    return {
                        'name': f'Record {record_num} (invalid JSON)',
                        'line_start': i,
                        'line_end': i,
                        'source': line,
                    }

        return None

    def _extract_by_type(self, type_filter: str) -> Optional[Dict[str, Any]]:
        """Extract all records of a specific type."""
        matches = []

        for i, line in enumerate(self.lines, 1):
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
                rec_type = obj.get('type', '')

                if rec_type == type_filter:
                    matches.append((i, obj))

            except json.JSONDecodeError:
                # Malformed JSON line, skip it
                logger.debug(f"Skipping malformed JSON at line {i}")
                continue

        if not matches:
            return None

        # Return first 10 matches
        lines = []
        start_line = matches[0][0]
        end_line = matches[-1][0]

        for line_num, obj in matches[:10]:
            lines.append(f"# Line {line_num}")
            lines.append(json.dumps(obj, indent=2))
            lines.append("")

        if len(matches) > 10:
            lines.append(f"# ... and {len(matches) - 10} more records")

        return {
            'name': f'{type_filter} records ({len(matches)} total)',
            'line_start': start_line,
            'line_end': end_line,
            'source': '\n'.join(lines),
        }
