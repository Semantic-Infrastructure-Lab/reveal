"""Markdown file analyzer."""

import re
from typing import Dict, List, Any, Optional
from ..base import FileAnalyzer, register


@register('.md', '.markdown', name='Markdown', icon='📝')
class MarkdownAnalyzer(FileAnalyzer):
    """Markdown file analyzer.

    Extracts sections based on headings.
    """

    def get_structure(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract markdown headings."""
        headings = []

        for i, line in enumerate(self.lines, 1):
            # Match heading syntax: # Heading, ## Heading, etc.
            match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()

                headings.append({
                    'line': i,
                    'level': level,
                    'name': title,
                })

        return {'headings': headings}

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a markdown section.

        Args:
            element_type: 'section' or 'heading'
            name: Heading text to find

        Returns:
            Dict with section content
        """
        # Find the heading
        start_line = None
        heading_level = None

        for i, line in enumerate(self.lines, 1):
            match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if match:
                title = match.group(2).strip()
                if title.lower() == name.lower():
                    start_line = i
                    heading_level = len(match.group(1))
                    break

        if not start_line:
            return super().extract_element(element_type, name)

        # Find the end of this section (next heading of same or higher level)
        end_line = len(self.lines)
        for i in range(start_line, len(self.lines)):
            line = self.lines[i]
            match = re.match(r'^(#{1,6})\s+', line)
            if match:
                level = len(match.group(1))
                if level <= heading_level:
                    end_line = i
                    break

        # Extract the section
        source = '\n'.join(self.lines[start_line-1:end_line])

        return {
            'name': name,
            'line_start': start_line,
            'line_end': end_line,
            'source': source,
        }
