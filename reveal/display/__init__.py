"""Display package for file structure rendering.

This package handles rendering file analysis results to various output formats.
"""

from .structure import show_structure
from .metadata import show_metadata, _print_file_header
from .outline import build_hierarchy, build_heading_hierarchy, render_outline
from .element import extract_element
from .formatting import (
    _format_frontmatter,
    _format_links,
    _format_code_blocks,
    _format_related,
    _format_standard_items,
    _build_analyzer_kwargs,
)

__all__ = [
    'show_structure',
    'show_metadata',
    '_print_file_header',
    'build_hierarchy',
    'build_heading_hierarchy',
    'render_outline',
    'extract_element',
    '_format_frontmatter',
    '_format_links',
    '_format_code_blocks',
    '_format_related',
    '_format_standard_items',
    '_build_analyzer_kwargs',
]
