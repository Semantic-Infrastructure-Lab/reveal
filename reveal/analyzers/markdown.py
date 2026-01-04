"""Markdown file analyzer with rich entity extraction using tree-sitter."""

import re
import yaml
import logging
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse
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

        # Determine mode: filtering (only requested features) vs navigation (headings + features)
        specific_features_requested = extract_links or extract_code
        navigation_mode = head is not None or tail is not None or range is not None
        outline_mode = kwargs.get('outline', False)

        # Include headings when:
        # - No specific features requested (default: show structure)
        # - Navigation mode active (head/tail/range with features)
        # - Outline mode active (requires headings for hierarchy)
        if not specific_features_requested or navigation_mode or outline_mode:
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
        """Extract all links from markdown using tree-sitter AST.

        Args:
            link_type: Filter by type (internal, external, email, all)
            domain: Filter by domain (for external links)

        Returns:
            List of link dicts with line, column, text, url, type, etc.
        """
        if not self.tree:
            # Fallback to regex if tree-sitter fails
            return self._extract_links_regex(link_type, domain)

        links = []
        link_nodes = self._find_nodes_by_type('link')

        for node in link_nodes:
            text = self._extract_link_text(node)
            url = self._extract_link_destination(node)

            if text and url:
                link_info = self._build_link_info(node, text, url)

                if self._link_matches_filters(link_info, link_type, domain):
                    links.append(link_info)

        return links

    def _extract_link_text(self, node) -> Optional[str]:
        """Extract text from a link node's link_text child.

        Args:
            node: Tree-sitter link node

        Returns:
            Link text or None if not found
        """
        for child in node.children:
            if child.type == 'link_text':
                for text_node in child.children:
                    if text_node.type == 'text':
                        return text_node.text.decode('utf-8')
        return None

    def _extract_link_destination(self, node) -> Optional[str]:
        """Extract URL from a link node's link_destination child.

        Args:
            node: Tree-sitter link node

        Returns:
            Link URL or None if not found
        """
        for child in node.children:
            if child.type == 'link_destination':
                for text_node in child.children:
                    if text_node.type == 'text':
                        return text_node.text.decode('utf-8')
        return None

    def _build_link_info(self, node, text: str, url: str) -> Dict[str, Any]:
        """Build link info dict with position and classification.

        Args:
            node: Tree-sitter link node
            text: Link text
            url: Link URL

        Returns:
            Dict with link metadata
        """
        line = node.start_point[0] + 1
        column = node.start_point[1] + 1

        link_info = self._classify_link(url, text, line)
        link_info['column'] = column
        return link_info

    def _link_matches_filters(self, link_info: Dict[str, Any],
                              link_type: Optional[str],
                              domain: Optional[str]) -> bool:
        """Check if link matches type and domain filters.

        Args:
            link_info: Link metadata dict
            link_type: Type filter (internal, external, email, all)
            domain: Domain filter (for external links)

        Returns:
            True if link matches filters
        """
        # Apply type filter
        if link_type and link_type != 'all':
            if link_info['type'] != link_type:
                return False

        # Apply domain filter (only for external links)
        if domain:
            if link_info['type'] == 'external':
                return domain in link_info['url']
            else:
                return False  # Domain filter only applies to external links

        return True

    def _extract_links_regex(self, link_type: Optional[str] = None,
                            domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fallback regex-based link extraction.

        Note: This doesn't provide column positions - only used if tree-sitter fails.
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
                link_info['column'] = 1  # No column tracking in regex fallback

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

            # Parse URL to extract components
            parsed = urlparse(url)
            link_info['protocol'] = parsed.scheme
            link_info['domain'] = parsed.netloc
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
        """Extract code blocks from markdown using tree-sitter AST.

        Args:
            language: Filter by programming language
            include_inline: Include inline code snippets

        Returns:
            List of code block dicts with line, language, source, etc.
        """
        if not self.tree:
            # Fallback to state machine if tree-sitter fails
            return self._extract_code_blocks_state_machine(language, include_inline)

        code_blocks = []

        # Extract fenced code blocks using tree-sitter
        fence_nodes = self._find_nodes_by_type('fenced_code_block')

        for node in fence_nodes:
            # Extract language from info_string and code from code_fence_content
            block_lang = 'text'  # Default
            source = ''

            for child in node.children:
                if child.type == 'info_string':
                    # Language tag (e.g., 'python', 'javascript')
                    # info_string has a text child
                    for text_node in child.children:
                        if text_node.type == 'text':
                            block_lang = text_node.text.decode('utf-8')
                            break
                elif child.type == 'code_fence_content':
                    # The actual code content
                    source = child.text.decode('utf-8')

            # Apply language filter
            if language and block_lang != language:
                continue

            # Get position (tree-sitter is 0-indexed)
            line_start = node.start_point[0] + 1
            line_end = node.end_point[0] + 1
            line_count = source.count('\n') + 1 if source else 0

            code_blocks.append({
                'line_start': line_start,
                'line_end': line_end,
                'language': block_lang,
                'source': source,
                'line_count': line_count,
                'type': 'fenced',
            })

        # Extract inline code if requested
        if include_inline:
            inline_blocks = self._extract_inline_code_ast(language)
            code_blocks.extend(inline_blocks)

        return code_blocks

    def _extract_code_blocks_state_machine(self, language: Optional[str] = None,
                                          include_inline: bool = False) -> List[Dict[str, Any]]:
        """Fallback state machine-based code block extraction.

        Note: Only used if tree-sitter fails.
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

    def _extract_inline_code_ast(self, language: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract inline code snippets using tree-sitter AST.

        Args:
            language: Language filter (not applicable to inline code)

        Returns:
            List of inline code dicts with line, column, source, etc.
        """
        if not self.tree:
            # Fallback to regex
            return self._extract_inline_code(language)

        inline_blocks = []

        # Find all code_span nodes
        code_span_nodes = self._find_nodes_by_type('code_span')

        for node in code_span_nodes:
            # Extract the code text
            source = ''
            for child in node.children:
                if child.type == 'text':
                    source = child.text.decode('utf-8')
                    break

            if source:
                # Get position (tree-sitter is 0-indexed)
                line = node.start_point[0] + 1
                column = node.start_point[1] + 1

                inline_blocks.append({
                    'line': line,
                    'column': column,
                    'language': 'inline',
                    'source': source,
                    'type': 'inline',
                })

        return inline_blocks

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

        except yaml.YAMLError as e:
            # Malformed YAML - return None (graceful degradation)
            logging.debug(f"Failed to parse YAML frontmatter: {e}")
            return None
        except Exception as e:
            # Any other error - graceful degradation
            logging.debug(f"Unexpected error parsing frontmatter: {e}")
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
