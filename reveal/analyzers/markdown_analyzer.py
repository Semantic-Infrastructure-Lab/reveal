"""Markdown file analyzer."""

import re
from typing import Dict, Any, List
from .base import BaseAnalyzer


class MarkdownAnalyzer(BaseAnalyzer):
    """Analyzer for Markdown files."""

    def analyze_structure(self) -> Dict[str, Any]:
        """Analyze Markdown structure."""
        headings = []
        paragraph_count = 0
        code_block_count = 0
        list_count = 0

        in_code_block = False
        current_paragraph = False

        for line in self.lines:
            stripped = line.strip()

            # Code blocks
            if stripped.startswith('```'):
                in_code_block = not in_code_block
                if in_code_block:
                    code_block_count += 1
                continue

            if in_code_block:
                continue

            # Headings
            if stripped.startswith('#'):
                match = re.match(r'^(#{1,3})\s+(.+)$', stripped)
                if match:
                    level = len(match.group(1))
                    title = match.group(2)
                    headings.append((level, title))
                    current_paragraph = False
                continue

            # Lists
            if re.match(r'^\s*[-*+]\s+', line) or re.match(r'^\s*\d+\.\s+', line):
                list_count += 1
                current_paragraph = False
                continue

            # Paragraphs
            if stripped and not current_paragraph:
                paragraph_count += 1
                current_paragraph = True
            elif not stripped:
                current_paragraph = False

        return {
            'headings': headings,
            'paragraph_count': paragraph_count,
            'code_block_count': code_block_count,
            'list_count': list_count
        }

    def generate_preview(self) -> List[tuple[int, str]]:
        """Generate Markdown preview."""
        preview = []
        in_frontmatter = False
        frontmatter_start = False
        first_heading_found = False
        lines_after_heading = 0
        in_code_block = False

        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()

            # Frontmatter detection
            if i == 1 and stripped == '---':
                in_frontmatter = True
                frontmatter_start = True
                preview.append((i, line))
                continue

            if in_frontmatter:
                preview.append((i, line))
                if stripped == '---':
                    in_frontmatter = False
                continue

            # Code blocks
            if stripped.startswith('```'):
                in_code_block = not in_code_block
                if in_code_block:
                    preview.append((i, f"[Code block: {stripped[3:] or 'unknown'}]"))
                continue

            if in_code_block:
                continue

            # First heading + paragraph
            if stripped.startswith('#'):
                preview.append((i, line))
                first_heading_found = True
                lines_after_heading = 0
                continue

            if first_heading_found and lines_after_heading < 5:
                if stripped:
                    preview.append((i, line))
                lines_after_heading += 1

            if len(preview) >= 20:
                break

        return preview[:30]
