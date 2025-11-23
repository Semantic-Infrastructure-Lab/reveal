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
    """
    Format breadcrumb suggestions - progressive revelation hints.

    Shows users what other reveal options are available to explore.
    """
    if is_end:
        return "→ (end) ← Back to --level 2"

    breadcrumbs = {
        0: [
            "→ Next: --level 1 (structure)",
            "  Options: --grep PATTERN (filter), --help (all options)"
        ],
        1: [
            "→ Next: --level 2 (preview with context)",
            "  Options: --grep PATTERN (filter content), --level 0 (metadata)",
            "  Tip: Structure shows line references - use those with --level 3"
        ],
        2: [
            "→ Next: --level 3 (full content)",
            "  Options: --grep PATTERN --context N (show ±N lines around matches)",
            "  Tip: Use line numbers from this output with other tools"
        ],
        3: [
            "← Back: --level 2 (preview), --level 1 (structure), --level 0 (metadata)",
            "  Options: --grep PATTERN --context N (filter while viewing all)"
        ]
    }

    lines = breadcrumbs.get(level, [])
    return "\n".join(lines) if lines else ""


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

        # Show installation hint if available
        if 'install' in structure:
            lines.append(f"💡 Install with: {structure['install']}")
            lines.append("   Or: pip install 'reveal-cli[treesitter]'")
            lines.append("")

        lines.append("→ Try --level 3 for raw content")
        return lines

    if summary.type == 'yaml':
        top_level_keys = structure.get('top_level_keys', [])
        if top_level_keys:
            lines.append(f"Top-level keys ({len(top_level_keys)}):")
            for key in top_level_keys:
                if isinstance(key, dict):
                    # New format with line numbers
                    loc = f"{summary.path}:{key['line']}" if summary.path else f"L{key['line']:04d}"
                    lines.append(f"  {loc:30}  {key['name']}")
                else:
                    # Backward compat (old format without line numbers)
                    lines.append(f"  {key}")

        lines.append("")
        lines.append(f"Nesting depth:   {structure.get('nesting_depth', 0)}")
        lines.append(f"Anchors:         {structure.get('anchor_count', 0)}")
        lines.append(f"Aliases:         {structure.get('alias_count', 0)}")

    elif summary.type == 'json':
        top_level_keys = structure.get('top_level_keys', [])
        if top_level_keys:
            lines.append(f"Top-level keys ({len(top_level_keys)}):")
            for key in top_level_keys:
                if isinstance(key, dict):
                    # New format with line numbers
                    loc = f"{summary.path}:{key['line']}" if summary.path else f"L{key['line']:04d}"
                    lines.append(f"  {loc:30}  {key['name']}")
                else:
                    # Backward compat (old format without line numbers)
                    lines.append(f"  {key}")

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

    elif summary.type == 'toml':
        top_level_keys = structure.get('top_level_keys', [])
        sections = structure.get('sections', [])

        if top_level_keys:
            lines.append(f"Top-level keys ({len(top_level_keys)}):")
            for key in top_level_keys:
                if isinstance(key, dict):
                    # New format with line numbers
                    loc = f"{summary.path}:{key['line']}" if summary.path else f"L{key['line']:04d}"
                    lines.append(f"  {loc:30}  {key['name']}")
                else:
                    # Backward compat
                    lines.append(f"  {key}")
            lines.append("")

        if sections:
            lines.append(f"Sections ({len(sections)}):")
            for section in sections:
                if isinstance(section, dict):
                    loc = f"{summary.path}:{section['line']}" if summary.path else f"L{section['line']:04d}"
                    subsections = section.get('subsections', 0)
                    subsection_info = f" ({subsections} subsections)" if subsections > 0 else ""
                    lines.append(f"  {loc:30}  [{section['name']}]{subsection_info}")
                else:
                    lines.append(f"  {section}")
            lines.append("")

        lines.append(f"Nesting depth:   {structure.get('nesting_depth', 0)}")

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
                if isinstance(cls, dict):
                    # New format with line numbers
                    loc = f"{summary.path}:{cls['line']}" if summary.path else f"L{cls['line']:04d}"
                    lines.append(f"  {loc:30}  {cls['name']}")
                else:
                    # Backward compat (old format without line numbers)
                    lines.append(f"  {cls}")

        functions = structure.get('functions', [])
        if functions:
            lines.append("")
            lines.append(f"Functions ({len(functions)}):")
            for func in functions:
                if isinstance(func, dict):
                    # New format with line numbers
                    loc = f"{summary.path}:{func['line']}" if summary.path else f"L{func['line']:04d}"
                    lines.append(f"  {loc:30}  {func['name']}")
                else:
                    # Backward compat
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
