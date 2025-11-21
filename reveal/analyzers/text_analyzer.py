"""Text file analyzer."""

from typing import Dict, Any, List
from .base import BaseAnalyzer


class TextAnalyzer(BaseAnalyzer):
    """Analyzer for plain text files."""

    def analyze_structure(self) -> Dict[str, Any]:
        """Analyze text structure."""
        line_count = len(self.lines)
        word_count = sum(len(line.split()) for line in self.lines)

        # Try to guess file type
        estimated_type = 'text'
        content = '\n'.join(self.lines)

        if '<html' in content.lower() or '<body' in content.lower():
            estimated_type = 'html'
        elif '<?xml' in content.lower():
            estimated_type = 'xml'

        return {
            'line_count': line_count,
            'word_count': word_count,
            'estimated_type': estimated_type
        }

    def generate_preview(self) -> List[tuple[int, str]]:
        """Generate text preview (first 20 lines)."""
        preview = []
        for i, line in enumerate(self.lines[:20], 1):
            preview.append((i, line))
        return preview
