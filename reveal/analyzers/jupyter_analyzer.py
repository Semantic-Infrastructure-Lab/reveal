"""Jupyter Notebook (.ipynb) analyzer."""

import json
from typing import Dict, Any, List, Tuple, Optional
from ..base import FileAnalyzer
from ..registry import register


@register('.ipynb', name='Jupyter', icon='')
class JupyterAnalyzer(FileAnalyzer):
    """Analyzer for Jupyter Notebook files"""

    def __init__(self, path: str):
        super().__init__(path)
        self.parse_error = None
        self.notebook_data = None
        self.cells = []
        self.metadata = {}

        try:
            self.notebook_data = json.loads(self.content)
            self.cells = self.notebook_data.get('cells', [])
            self.metadata = self.notebook_data.get('metadata', {})
        except Exception as e:
            self.parse_error = str(e)

    def _get_cell_first_line(self, source: Any) -> str:
        """Extract and truncate first line from cell source.

        Args:
            source: Cell source (string or list)

        Returns:
            First line (truncated to 50 chars if needed)
        """
        if not source:
            return ""

        first_line = (source[0] if isinstance(source, list) else source).strip()
        if len(first_line) > 50:
            first_line = first_line[:50] + "..."
        return first_line

    def _get_cell_display_name(self, cell_type: str, first_line: str,
                              execution_count: Optional[int], idx: int) -> str:
        """Get display name for a cell.

        Args:
            cell_type: Type of cell (markdown, code, etc.)
            first_line: First line of cell content
            execution_count: Execution count for code cells
            idx: Cell index

        Returns:
            Display name
        """
        if cell_type == 'markdown':
            return first_line if first_line else f"Markdown cell #{idx + 1}"
        elif cell_type == 'code':
            exec_info = f"[{execution_count}]" if execution_count else "[not executed]"
            return f"Code {exec_info}: {first_line}" if first_line else f"Code cell #{idx + 1}"
        else:
            return f"{cell_type} cell #{idx + 1}"

    def _create_cell_summary(self, cell: Dict[str, Any], idx: int) -> Dict[str, Any]:
        """Create summary for a single cell.

        Args:
            cell: Cell data
            idx: Cell index

        Returns:
            Cell summary dict
        """
        cell_type = cell.get('cell_type', 'unknown')
        source = cell.get('source', [])
        cell_line = self._find_cell_line(idx)

        first_line = self._get_cell_first_line(source)
        execution_count = cell.get('execution_count', None)
        outputs_count = len(cell.get('outputs', []))

        name = self._get_cell_display_name(cell_type, first_line, execution_count, idx)

        return {
            'line': cell_line,
            'name': name,
            'type': cell_type,
            'execution_count': execution_count,
            'outputs_count': outputs_count,
        }

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        """Analyze Jupyter notebook structure."""
        if self.parse_error:
            return {
                'error': self.parse_error,
                'cells': [],
                'cell_counts': {},
                'kernel': 'unknown',
                'language': 'unknown',
                'total_cells': 0
            }

        # Get cell summaries
        cell_summaries = [self._create_cell_summary(cell, idx)
                         for idx, cell in enumerate(self.cells)]

        # Return only the cells list for display
        result = {
            'contract_version': '1.0',
            'type': 'jupyter_structure',
            'source': str(self.path),
            'source_type': 'file',
        }
        if cell_summaries:
            result['cells'] = cell_summaries

        return result

    def _find_cell_line(self, cell_index: int) -> int:
        """
        Find approximate line number where a cell starts in the JSON.

        This searches for cell markers in the original source.
        """
        # Look for "cell_type" string followed by the type for this cell
        if cell_index < len(self.cells):
            cell = self.cells[cell_index]
            cell_type = cell.get('cell_type', '')

            # Count how many cells of this type we've seen before
            cells_before = sum(1 for c in self.cells[:cell_index] if c.get('cell_type') == cell_type)

            # Search for the nth occurrence of this cell_type in the file
            count = 0
            search_str = f'"cell_type": "{cell_type}"'
            for i, line in enumerate(self.lines, 1):
                if search_str in line:
                    if count == cells_before:
                        return i
                    count += 1

        return 1  # Fallback

    def generate_preview(self) -> List[Tuple[int, str]]:
        """Generate Jupyter notebook preview."""
        preview = []

        if self.parse_error:
            # Fallback to first 20 lines of JSON
            for i, line in enumerate(self.lines[:20], 1):
                preview.append((i, line))
            return preview

        # Show metadata section
        if self.metadata:
            kernelspec = self.metadata.get('kernelspec', {})
            kernel = kernelspec.get('display_name', kernelspec.get('name', 'unknown'))
            lang_info = self.metadata.get('language_info', {})
            language = lang_info.get('name', 'unknown')

            preview.append((1, f"Kernel: {kernel}"))
            preview.append((1, f"Language: {language}"))
            preview.append((1, ""))

        # Show preview of each cell
        for idx, cell in enumerate(self.cells[:10]):  # Limit to first 10 cells
            preview.extend(self._format_cell_preview(idx, cell))

        if len(self.cells) > 10:
            preview.append((1, f"... ({len(self.cells) - 10} more cells)"))

        return preview

    def _format_cell_preview(self, idx: int, cell: dict) -> List[tuple]:
        """Build preview lines for a single cell."""
        entries = []
        cell_type = cell.get('cell_type', 'unknown')
        source = cell.get('source', [])
        execution_count = cell.get('execution_count', None)
        cell_line = self._find_cell_line(idx)

        header = f"[{idx + 1}] {cell_type.upper()}"
        if execution_count is not None:
            header += f" (exec: {execution_count})"
        entries.append((cell_line, header))
        entries.append((cell_line, "─" * 60))

        if source:
            source_lines = source if isinstance(source, list) else [source]
            for i, line in enumerate(source_lines[:5]):
                entries.append((cell_line + i + 1, line.rstrip('\n')))
            if len(source_lines) > 5:
                entries.append((cell_line + 6, f"... ({len(source_lines) - 5} more lines)"))

        outputs = cell.get('outputs', [])
        if outputs:
            entries.append((cell_line, f"Outputs: {len(outputs)} items"))
            if outputs[0]:
                output_type = outputs[0].get('output_type', 'unknown')
                entries.append((cell_line, f"  └─ {output_type}"))

        entries.append((cell_line, ""))  # blank line between cells
        return entries

    def format_structure(self, structure: Dict[str, Any]) -> List[str]:
        """Format structure output for Jupyter notebooks."""
        if structure.get('error'):
            return [f"Error parsing notebook: {structure['error']}"]

        lines = []

        # Overview
        lines.append(f"Kernel: {structure['kernel']}")
        lines.append(f"Language: {structure['language']}")
        lines.append(f"Total Cells: {structure['total_cells']}")
        lines.append("")

        # Cell type breakdown
        if structure['cell_counts']:
            lines.append("Cell Types:")
            for cell_type, count in sorted(structure['cell_counts'].items()):
                lines.append(f"  {cell_type}: {count}")
            lines.append("")

        # Cell listing
        if structure['cells']:
            lines.append("Cells:")
            for cell in structure['cells']:
                loc = f"Line {cell['line']}" if cell.get('line') else ""
                cell_info = f"[{cell['index'] + 1}] {cell['type']}"

                if cell['execution_count'] is not None:
                    cell_info += f" (exec: {cell['execution_count']})"
                if cell['outputs_count'] > 0:
                    cell_info += f" [{cell['outputs_count']} outputs]"

                # Show first line of content
                if cell['first_line']:
                    cell_info += f" - {cell['first_line']}"

                if loc:
                    lines.append(f"  {loc:<30}  {cell_info}")
                else:
                    lines.append(f"  {cell_info}")

        return lines
