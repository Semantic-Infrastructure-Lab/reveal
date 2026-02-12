"""L005: Documentation cross-reference density checker.

Checks that documentation files have sufficient cross-references to related docs.
This improves documentation discoverability and navigation.
"""

import re
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class L005(BaseRule):
    """Validate documentation has sufficient cross-references."""

    code = "L005"
    message = "Documentation has low cross-reference density"
    category = RulePrefix.L
    severity = Severity.LOW
    file_patterns = ['.md', '.markdown']
    version = "1.0.0"

    # Minimum cross-references expected per doc (configurable)
    MIN_CROSS_REFS = 2

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check if documentation file has sufficient cross-references.

        A "cross-reference" is an internal link to another .md file in the
        same documentation set.

        Args:
            file_path: Path to markdown file
            structure: Parsed structure (contains links if available)
            content: File content

        Returns:
            List of detections if cross-references are insufficient
        """
        detections: List[Detection] = []
        path = Path(file_path)

        # Only check files in docs directories
        if 'docs' not in path.parts:
            return detections

        # Skip special files that are expected to have few refs
        skip_files = ['README.md', 'INDEX.md', 'CHANGELOG.md', 'LICENSE.md']
        if path.name in skip_files:
            return detections

        # Count internal markdown links
        internal_md_links = self._count_internal_md_links(content, path)

        if internal_md_links < self.MIN_CROSS_REFS:
            # Find similar docs to suggest references
            suggestions = self._suggest_related_docs(path, content)

            suggestion_text = (
                f"Found only {internal_md_links} cross-reference(s), "
                f"expected at least {self.MIN_CROSS_REFS}.\n\n"
                "Cross-references help users discover related documentation.\n\n"
            )

            if suggestions:
                suggestion_text += "Consider adding references to:\n"
                for doc_name, reason in suggestions[:5]:
                    suggestion_text += f"  - [{doc_name}](./{doc_name}) - {reason}\n"
                suggestion_text += "\n"

            suggestion_text += (
                "Add a 'See Also' or 'Related Documentation' section:\n\n"
                "  ## See Also\n"
                "  - [Related Guide](./RELATED_GUIDE.md) - Description\n"
                "  - [Another Doc](./OTHER_DOC.md) - Why it's relevant\n\n"
                "Benefits:\n"
                "  - Improves documentation discoverability\n"
                "  - Helps users find what they need faster\n"
                "  - Creates interconnected documentation web"
            )

            detections.append(Detection(
                rule_code=self.code,
                message=self.message,
                severity=self.severity,
                file_path=file_path,
                line=1,
                column=1,
                context=f"Only {internal_md_links} cross-reference(s) found",
                suggestion=suggestion_text
            ))

        return detections

    def _count_internal_md_links(self, content: str, current_file: Path) -> int:
        """Count internal .md links in content.

        Args:
            content: File content
            current_file: Path to current file

        Returns:
            Number of internal .md links
        """
        # Find all markdown links: [text](url)
        links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', content)

        count = 0
        for link_text, link_url in links:
            # Check if it's an internal markdown link
            if '.md' in link_url and not link_url.startswith('http'):
                # Exclude self-references
                if Path(link_url).name != current_file.name:
                    count += 1

        return count

    def _suggest_related_docs(self, current_file: Path, content: str) -> List[tuple]:
        """Suggest related documentation files based on content.

        Args:
            current_file: Path to current file
            content: File content

        Returns:
            List of (filename, reason) tuples
        """
        suggestions = []

        # Find docs directory
        docs_dir = None
        for i, part in enumerate(current_file.parts):
            if part == 'docs':
                docs_dir = Path(*current_file.parts[:i+1])
                break

        if not docs_dir or not docs_dir.exists():
            return suggestions

        # Common patterns to suggest related docs
        patterns = {
            'AGENT_HELP': {
                'keywords': ['agent', 'ai', 'llm', 'claude'],
                'suggests': [
                    ('ANTI_PATTERNS.md', 'Shows what to avoid'),
                    ('COOL_TRICKS.md', 'Advanced usage patterns'),
                    ('MARKDOWN_GUIDE.md', 'Markdown feature reference'),
                ]
            },
            'ANTI_PATTERNS': {
                'keywords': ['anti-pattern', 'bad', 'dont', 'avoid'],
                'suggests': [
                    ('AGENT_HELP.md', 'Shows correct patterns'),
                    ('COOL_TRICKS.md', 'Advanced techniques'),
                ]
            },
            'ADAPTER': {
                'keywords': ['adapter', 'custom', 'extend'],
                'suggests': [
                    ('ANALYZER_PATTERNS.md', 'Implementation patterns'),
                    ('HELP_SYSTEM_GUIDE.md', 'Adding help docs'),
                ]
            },
            'GUIDE': {
                'keywords': ['guide', 'how to', 'tutorial'],
                'suggests': [
                    ('CONFIGURATION_GUIDE.md', 'Configuration options'),
                    ('AGENT_HELP.md', 'Usage reference'),
                ]
            }
        }

        content_lower = content.lower()

        # Match patterns and collect suggestions
        for pattern_name, pattern_info in patterns.items():
            # Check if keywords appear in content
            if any(kw in content_lower for kw in pattern_info['keywords']):
                for doc_name, reason in pattern_info['suggests']:
                    # Only suggest docs that exist
                    if (docs_dir / doc_name).exists():
                        # Don't suggest current file
                        if doc_name != current_file.name:
                            suggestions.append((doc_name, reason))

        # Remove duplicates while preserving order
        seen = set()
        unique_suggestions = []
        for item in suggestions:
            if item[0] not in seen:
                seen.add(item[0])
                unique_suggestions.append(item)

        return unique_suggestions[:5]  # Return top 5
