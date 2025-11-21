"""Output formatting utilities."""

from typing import List, Optional, Dict, Any
from .core import FileSummary


def format_header(section: str, level: int, grep_pattern: Optional[str] = None) -> str:
    """Format section header."""
    header = f"=== {section.upper()} (Level {level})"
    if grep_pattern:
        header += f", Filtered: \"{grep_pattern}\""
    header += " ==="
    return header


def format_line_number(line_num: int, max_num: int = 9999) -> str:
    """Format line number with left padding."""
    width = len(str(max_num))
    return f"{line_num:0{width}d}"


def format_breadcrumb(level: int, is_end: bool = False) -> str:
    """Format breadcrumb suggestion."""
    if is_end:
        return "→ (end) ← Back to --level 2"

    suggestions = {
        0: "→ Try --level 1 for structure",
        1: "→ Try --level 2 for preview",
        2: "→ Try --level 3 for full content"
    }

    return suggestions.get(level, "")


def format_metadata(summary: FileSummary) -> List[str]:
    """Format Level 0 metadata output."""
    lines = []
    lines.append(format_header("METADATA", 0))
    lines.append("")
    lines.append(f"File name:       {summary.path.name}")
    lines.append(f"Detected type:   {summary.type}")
    lines.append(f"Size (bytes):    {summary.size:,}")
    lines.append(f"Modified:        {summary.modified.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Line count:      {summary.linecount:,}")
    lines.append(f"SHA256:          {summary.sha256}")

    if summary.parse_error:
        lines.append("")
        lines.append(f"Note:            {summary.parse_error}")

    lines.append("")
    lines.append(format_breadcrumb(0))

    return lines


def format_structure(summary: FileSummary, structure: Dict[str, Any], grep_pattern: Optional[str] = None) -> List[str]:
    """Format Level 1 structure output."""
    lines = []
    lines.append(format_header("STRUCTURE", 1, grep_pattern))
    lines.append("")

    if 'error' in structure:
        lines.append(f"Parse error: {structure['error']}")
        lines.append("")
        lines.append("→ Try --level 3 for raw content")
        return lines

    if summary.type == 'yaml':
        lines.append("Top-level keys:")
        for i, key in enumerate(structure.get('top_level_keys', []), 1):
            lines.append(f"  {format_line_number(i, len(structure.get('top_level_keys', [])))}  {key}")

        lines.append("")
        lines.append(f"Nesting depth:   {structure.get('nesting_depth', 0)}")
        lines.append(f"Anchors:         {structure.get('anchor_count', 0)}")
        lines.append(f"Aliases:         {structure.get('alias_count', 0)}")

    elif summary.type == 'json':
        lines.append("Top-level keys:")
        for i, key in enumerate(structure.get('top_level_keys', []), 1):
            lines.append(f"  {format_line_number(i, len(structure.get('top_level_keys', [])))}  {key}")

        lines.append("")
        lines.append(f"Object count:    {structure.get('object_count', 0)}")
        lines.append(f"Array count:     {structure.get('array_count', 0)}")
        lines.append(f"Max depth:       {structure.get('max_depth', 0)}")

        value_types = structure.get('value_types', {})
        if value_types:
            lines.append("")
            lines.append("Value types:")
            for vtype, count in value_types.items():
                lines.append(f"  {vtype}: {count}")

    elif summary.type == 'markdown':
        headings = structure.get('headings', [])
        lines.append(f"Headings (H1-H3): {len(headings)}")
        for level, title in headings:
            indent = "  " * level
            lines.append(f"  {indent}H{level}: {title}")

        lines.append("")
        lines.append(f"Paragraphs:      {structure.get('paragraph_count', 0)}")
        lines.append(f"Code blocks:     {structure.get('code_block_count', 0)}")
        lines.append(f"Lists:           {structure.get('list_count', 0)}")

    elif summary.type == 'python':
        imports = structure.get('imports', [])
        if imports:
            lines.append(f"Imports ({len(imports)}):")
            for imp in imports[:10]:  # Limit to first 10
                lines.append(f"  {imp}")
            if len(imports) > 10:
                lines.append(f"  ... and {len(imports) - 10} more")

        classes = structure.get('classes', [])
        if classes:
            lines.append("")
            lines.append(f"Classes ({len(classes)}):")
            for cls in classes:
                lines.append(f"  {cls}")

        functions = structure.get('functions', [])
        if functions:
            lines.append("")
            lines.append(f"Functions ({len(functions)}):")
            for func in functions:
                lines.append(f"  {func}")

        assignments = structure.get('assignments', [])
        if assignments:
            lines.append("")
            lines.append(f"Top-level assignments ({len(assignments)}):")
            for assign in assignments[:10]:
                lines.append(f"  {assign}")

    elif summary.type == 'text':
        lines.append(f"Line count:      {structure.get('line_count', 0)}")
        lines.append(f"Word count:      {structure.get('word_count', 0)}")
        lines.append(f"Estimated type:  {structure.get('estimated_type', 'text')}")

    lines.append("")
    lines.append(format_breadcrumb(1))

    return lines


def format_preview(summary: FileSummary, preview: List[tuple[int, str]], grep_pattern: Optional[str] = None) -> List[str]:
    """Format Level 2 preview output."""
    lines = []
    lines.append(format_header("PREVIEW", 2, grep_pattern))
    lines.append("")

    max_line_num = max((ln for ln, _ in preview), default=1)

    for line_num, content in preview:
        lines.append(f"{format_line_number(line_num, max_line_num)}  {content}")

    lines.append("")
    lines.append(format_breadcrumb(2))

    return lines


def format_full_content(summary: FileSummary, lines_to_show: List[tuple[int, str]], grep_pattern: Optional[str] = None, is_end: bool = False) -> List[str]:
    """Format Level 3 full content output."""
    output = []
    output.append(format_header("FULL CONTENT", 3, grep_pattern))
    output.append("")

    if not lines_to_show:
        output.append("(no content)")
        output.append("")
        output.append(format_breadcrumb(3, is_end=True))
        return output

    max_line_num = max((ln for ln, _ in lines_to_show), default=1)

    for line_num, content in lines_to_show:
        output.append(f"{format_line_number(line_num, max_line_num)}  {content}")

    output.append("")
    output.append(format_breadcrumb(3, is_end=is_end))

    return output
