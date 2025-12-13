"""Markdown file analyzer with rich entity extraction using tree-sitter."""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from ..base import register
from ..treesitter import TreeSitterAnalyzer


@register('.md', '.markdown', name='Markdown', icon='')
class MarkdownAnalyzer(TreeSitterAnalyzer):
    """Markdown file analyzer using tree-sitter.

    Extracts headings, links, images, code blocks, and other entities.
    Uses tree-sitter for accurate parsing (e.g., ignores # inside code fences).
    """

    language = 'markdown'

    def get_structure(self, head: int = None, tail: int = None,
                     range: tuple = None,
                     extract_links: bool = False,
                     link_type: Optional[str] = None,
                     domain: Optional[str] = None,
                     extract_code: bool = False,
                     language: Optional[str] = None,
                     inline_code: bool = False,
                     extract_frontmatter: bool = False,
                     **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract markdown structure.

        Args:
            head: Show first N semantic units (per category)
            tail: Show last N semantic units (per category)
            range: Show semantic units in range (start, end) - 1-indexed (per category)
            extract_links: Include link extraction
            link_type: Filter links by type (internal, external, email)
            domain: Filter links by domain
            extract_code: Include code block extraction
            language: Filter code blocks by language
            inline_code: Include inline code snippets
            extract_frontmatter: Include YAML front matter extraction
            **kwargs: Additional parameters (unused)

        Returns:
            Dict with headings and optionally links/code/frontmatter

        Note: Slicing applies to each category independently
        (e.g., --head 5 shows first 5 headings AND first 5 links)
        """
        result = {}

        # Extract front matter if requested (always first, not affected by slicing)
        if extract_frontmatter:
            result['frontmatter'] = self._extract_frontmatter()

        # Determine if specific features requested
        # Note: frontmatter is metadata, not structure, so it doesn't exclude headings
        specific_features_requested = extract_links or extract_code

        # Only include headings if no specific features requested (default case)
        # OR if outline mode is active (Issue #3 dependency)
        # OR if only frontmatter was requested (frontmatter + headings is the default combo)
        outline_mode = kwargs.get('outline', False)

        if not specific_features_requested or outline_mode or (extract_frontmatter and not extract_links and not extract_code):
            result['headings'] = self._extract_headings()

        # Extract links if requested
        if extract_links:
            result['links'] = self._extract_links(link_type=link_type, domain=domain)

        # Extract code blocks if requested
        if extract_code:
            result['code_blocks'] = self._extract_code_blocks(
                language=language,
                include_inline=inline_code
            )

        # Apply semantic slicing to each category (but not frontmatter - it's unique)
        if head or tail or range:
            for category in result:
                if category != 'frontmatter':
                    result[category] = self._apply_semantic_slice(
                        result[category], head, tail, range
                    )

        return result

    def _extract_headings(self) -> List[Dict[str, Any]]:
        """Extract markdown headings using tree-sitter.

        This correctly ignores # comments inside code fences by using the AST.
        """
        headings = []

        if not self.tree:
            # Fallback to regex if tree-sitter fails
            return self._extract_headings_regex()

        # Find all atx_heading nodes (# syntax headings)
        heading_nodes = self._find_nodes_by_type('atx_heading')

        for node in heading_nodes:
            # Get the heading level (count # symbols)
            level = None
            title = None

            # The first child is usually the marker (atx_h1_marker, atx_h2_marker, etc.)
            # The second child is heading_content
            for child in node.children:
                if 'marker' in child.type:
                    # atx_h1_marker, atx_h2_marker, etc.
                    level = int(child.type[5])  # Extract number from 'atx_h1_marker'
                elif child.type == 'heading_content':
                    title = child.text.decode('utf-8').strip()

            if level and title:
                headings.append({
                    'line': node.start_point[0] + 1,  # tree-sitter uses 0-indexed
                    'level': level,
                    'name': title,
                })

        return headings

    def _extract_headings_regex(self) -> List[Dict[str, Any]]:
        """Fallback regex-based heading extraction.

        Note: This has the code fence bug - only used if tree-sitter fails.
        """
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

        return headings

    def _extract_links(self, link_type: Optional[str] = None,
                      domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract all links from markdown.

        Args:
            link_type: Filter by type (internal, external, email, all)
            domain: Filter by domain (for external links)

        Returns:
            List of link dicts with line, text, url, type, etc.
        """
        links = []

        # Match [text](url) pattern
        link_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'

        for i, line in enumerate(self.lines, 1):
            for match in re.finditer(link_pattern, line):
                text = match.group(1)
                url = match.group(2)

                # Classify link
                link_info = self._classify_link(url, text, i)

                # Apply type filter
                if link_type and link_type != 'all':
                    if link_info['type'] != link_type:
                        continue

                # Apply domain filter (for external links)
                if domain:
                    if link_info['type'] == 'external':
                        if domain not in url:
                            continue
                    else:
                        continue  # Domain filter only applies to external links

                links.append(link_info)

        return links

    def _classify_link(self, url: str, text: str, line: int) -> Dict[str, Any]:
        """Classify a link and extract metadata.

        Args:
            url: Link URL
            text: Link text
            line: Line number

        Returns:
            Dict with link metadata
        """
        link_info = {
            'line': line,
            'text': text,
            'url': url,
        }

        # Classify link type
        if url.startswith('mailto:'):
            link_info['type'] = 'email'
            link_info['email'] = url.replace('mailto:', '')
        elif url.startswith(('http://', 'https://')):
            link_info['type'] = 'external'
            link_info['protocol'] = 'https' if url.startswith('https') else 'http'

            # Extract domain
            domain_match = re.match(r'https?://([^/]+)', url)
            if domain_match:
                link_info['domain'] = domain_match.group(1)
        else:
            link_info['type'] = 'internal'
            link_info['target'] = url

            # Check if link is broken (file doesn't exist)
            link_info['broken'] = self._is_broken_link(url)

        return link_info

    def _is_broken_link(self, url: str) -> bool:
        """Check if an internal link is broken.

        Args:
            url: Internal link path

        Returns:
            True if link target doesn't exist
        """
        # Resolve relative to markdown file's directory
        base_dir = self.path.parent
        target = base_dir / url

        # Try both as-is and with common extensions
        if target.exists():
            return False

        # Try with .md extension if not already present
        if not target.suffix:
            if (target.parent / f"{target.name}.md").exists():
                return False

        return True

    def _extract_code_blocks(self, language: Optional[str] = None,
                            include_inline: bool = False) -> List[Dict[str, Any]]:
        """Extract code blocks from markdown.

        Args:
            language: Filter by programming language
            include_inline: Include inline code snippets

        Returns:
            List of code block dicts with line, language, source, etc.
        """
        code_blocks = []

        # Extract fenced code blocks (```language)
        in_block = False
        block_start = None
        block_lang = None
        block_lines = []

        for i, line in enumerate(self.lines, 1):
            # Start of code block
            if line.strip().startswith('```'):
                if not in_block:
                    # Beginning of block
                    in_block = True
                    block_start = i
                    # Extract language tag (everything after ```)
                    lang_tag = line.strip()[3:].strip()
                    block_lang = lang_tag if lang_tag else 'text'
                    block_lines = []
                else:
                    # End of block
                    in_block = False

                    # Apply language filter
                    if language and block_lang != language:
                        continue

                    # Calculate line count
                    line_count = len(block_lines)

                    code_blocks.append({
                        'line_start': block_start,
                        'line_end': i,
                        'language': block_lang,
                        'source': '\n'.join(block_lines),
                        'line_count': line_count,
                        'type': 'fenced',
                    })
            elif in_block:
                # Inside code block - accumulate lines
                block_lines.append(line)

        # Extract inline code if requested
        if include_inline:
            inline_blocks = self._extract_inline_code(language)
            code_blocks.extend(inline_blocks)

        return code_blocks

    def _extract_inline_code(self, language: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract inline code snippets (`code`).

        Args:
            language: Language filter (not applicable to inline code)

        Returns:
            List of inline code dicts
        """
        inline_blocks = []

        # Match `code` pattern (single backticks)
        inline_pattern = r'`([^`]+)`'

        for i, line in enumerate(self.lines, 1):
            for match in re.finditer(inline_pattern, line):
                code_text = match.group(1)

                # Skip if it looks like a fenced code block marker
                if code_text.startswith('``'):
                    continue

                inline_blocks.append({
                    'line': i,
                    'language': 'inline',
                    'source': code_text,
                    'type': 'inline',
                    'column': match.start() + 1,
                })

        return inline_blocks

    def _extract_frontmatter(self) -> Optional[Dict[str, Any]]:
        """Extract YAML front matter from markdown file.

        Front matter is YAML metadata at the start of the file, delimited by ---:

        ---
        title: Document Title
        beth_topics:
          - topic1
          - topic2
        tags: [tag1, tag2]
        ---

        Returns:
            Dict with front matter metadata, or None if not present/malformed
        """
        content = '\n'.join(self.lines)

        # Front matter must start at beginning of file
        if not content.startswith('---'):
            return None

        # Find closing delimiter (must be at start of line)
        # Look for \n---\n pattern (closing delimiter on its own line)
        end_marker = content.find('\n---\n', 3)
        if end_marker == -1:
            # Also try end of file case
            end_marker = content.find('\n---', 3)
            if end_marker == -1 or end_marker + 4 < len(content):
                # Not at end of file, invalid front matter
                return None

        try:
            # Extract YAML content (skip opening ---)
            frontmatter_text = content[4:end_marker]

            # Parse YAML
            metadata = yaml.safe_load(frontmatter_text)

            if not isinstance(metadata, dict):
                # Invalid front matter (not a dict)
                return None

            # Calculate line range
            line_start = 1
            line_end = content[:end_marker].count('\n') + 2  # +2 for closing ---

            # Add metadata about the front matter block itself
            result = {
                'data': metadata,
                'line_start': line_start,
                'line_end': line_end,
                'raw': frontmatter_text.strip(),
            }

            return result

        except yaml.YAMLError:
            # Malformed YAML - return None (graceful degradation)
            return None
        except Exception:
            # Any other error - graceful degradation
            return None

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
