"""Markdown file analyzer with rich entity extraction using tree-sitter."""

import re
import yaml
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Tuple, cast
from urllib.parse import urlparse
from pathlib import Path
from ..registry import register
from ..treesitter import TreeSitterAnalyzer
from ..structure_options import StructureOptions

# Cache for markdown_inline parse results, keyed by (path, mtime_ns).
# Avoids re-parsing the same file's inline content when multiple rules or
# calls analyze the same markdown file in a single --check run.
_inline_parse_cache: Dict[Tuple[str, int], Any] = {}


@dataclass
class RelatedTracker:
    """Tracks state during related document extraction."""
    depth: int = 1
    visited: Set[Path] = field(default_factory=set)
    file_count: int = 0
    limit: int = 100
    truncated: bool = False

    def should_continue(self) -> bool:
        """Check if we should continue processing more files."""
        return self.file_count < self.limit

    def increment(self) -> None:
        """Increment file counter."""
        self.file_count += 1
        if self.file_count >= self.limit:
            self.truncated = True

    def mark_visited(self, path: Path) -> bool:
        """Mark path as visited. Returns True if it was already visited."""
        if path in self.visited:
            return True
        self.visited.add(path)
        return False


@register('.md', '.markdown', name='Markdown', icon='')
class MarkdownAnalyzer(TreeSitterAnalyzer):
    """Markdown file analyzer using tree-sitter.

    Extracts headings, links, images, code blocks, and other entities.
    Uses tree-sitter for accurate parsing (e.g., ignores # inside code fences).
    """

    language = 'markdown'

    def __init__(self, path: str):
        """Initialize markdown analyzer with dual-parser support.

        Markdown grammar uses two parsers:
        - 'markdown' for block structure (headings, paragraphs, lists)
        - 'markdown_inline' for inline elements (links, emphasis, code spans)
        """
        super().__init__(path)

        # Parse inline content separately for link/code extraction.
        # Uses the same (path, mtime_ns) cache key as TreeSitterAnalyzer so
        # multiple rule passes on the same file share a single parse.
        self.inline_tree = None
        cache_key = getattr(self, '_cache_key', None)
        if cache_key is not None and cache_key in _inline_parse_cache:
            self.inline_tree = _inline_parse_cache[cache_key]
        else:
            try:
                from tree_sitter_language_pack import get_parser
                import warnings
                warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')

                inline_parser = get_parser('markdown_inline')
                self.inline_tree = inline_parser.parse(self.content.encode('utf-8'))
                if cache_key is not None:
                    _inline_parse_cache[cache_key] = self.inline_tree
            except Exception:
                # Inline parsing failed - fall back to regex for links/code
                pass

    def _find_nodes_in_tree(self, tree, node_type: str) -> List:
        """Find all nodes of a given type in a specific tree.

        Args:
            tree: Tree-sitter tree to search
            node_type: Type of node to find

        Returns:
            List of matching nodes
        """
        results = []

        def _traverse(node):
            if node.type == node_type:
                results.append(node)
            for child in node.children:
                _traverse(child)

        if tree and tree.root_node:
            _traverse(tree.root_node)

        return results

    def _should_include_headings(self, options: StructureOptions, outline_mode: bool) -> bool:
        """Determine if headings should be included in output.

        Args:
            options: StructureOptions containing extraction parameters
            outline_mode: Whether outline mode is active

        Returns:
            True if headings should be included
        """
        specific_features_requested = options.extract_links or options.extract_code
        navigation_mode = options.head is not None or options.tail is not None or options.range is not None

        # Include headings when:
        # - No specific features requested (default: show structure)
        # - Navigation mode active (head/tail/range with features)
        # - Outline mode active (requires headings for hierarchy)
        return not specific_features_requested or navigation_mode or outline_mode

    def _apply_slicing_to_results(self, result: Dict[str, Any],
                                   head: Optional[int], tail: Optional[int], range: Optional[tuple]) -> None:
        """Apply semantic slicing to all result categories except frontmatter.

        Args:
            result: Results dict to modify in place
            head: Show first N items
            tail: Show last N items
            range: Show items in range (start, end)
        """
        for category in result:
            if category != 'frontmatter':
                result[category] = self._apply_semantic_slice(
                    result[category], head, tail, range
                )

    @staticmethod
    def _build_md_options(options, head, tail, range, kwargs) -> 'StructureOptions':
        """Build StructureOptions from explicit params and kwargs."""
        if options is not None:
            return options
        if head is not None:
            kwargs['head'] = head
        if tail is not None:
            kwargs['tail'] = tail
        if range is not None:
            kwargs['range'] = range
        return StructureOptions.from_kwargs(**kwargs)

    def get_structure(self, options: Optional[StructureOptions] = None, head: Optional[int] = None, tail: Optional[int] = None, range: Optional[str] = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:  # type: ignore[override]
        """Extract markdown structure.

        Args:
            options: StructureOptions config object (recommended)
            head: Show first N semantic units (per category)
            tail: Show last N semantic units (per category)
            range: Show semantic units in range (start, end) - 1-indexed (per category)
            **kwargs: Additional options for backward compatibility

        Supported options (via StructureOptions or kwargs):
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
            extract_related: Include related documents from front matter
            related_depth: Depth for related docs (1=immediate, 0=unlimited)
            related_limit: Max files to traverse for related (default: 100)

        Returns:
            Dict with headings and optionally links/code/frontmatter/related

        Note: Slicing applies to each category independently
        (e.g., --head 5 shows first 5 headings AND first 5 links)
        """
        options = self._build_md_options(options, head, tail, range, kwargs)

        result: Dict[str, Any] = {
            'contract_version': '1.0',
            'type': 'markdown_structure',
            'source': str(self.path),
            'source_type': 'file',
        }

        # Extract front matter if requested (always first, not affected by slicing)
        if options.extract_frontmatter:
            result['frontmatter'] = self._extract_frontmatter()

        # Include headings based on mode
        outline_mode = options.extra.get('outline', False) or options.outline
        if self._should_include_headings(options, outline_mode):
            result['headings'] = self._extract_headings()

        # Extract links if requested
        if options.extract_links:
            result['links'] = self._extract_links(
                link_type=options.link_type,
                domain=options.domain
            )

        # Extract code blocks if requested
        if options.extract_code:
            result['code_blocks'] = self._extract_code_blocks(
                language=options.language,
                include_inline=options.inline_code
            )

        # Extract related documents if requested
        if options.extract_related:
            result['related'] = self._extract_related(
                depth=options.related_depth,
                limit=options.related_limit
            )

        # Apply semantic slicing to each category (but not frontmatter - it's unique)
        if options.head or options.tail or options.range:
            self._apply_slicing_to_results(result, options.head, options.tail, options.range)

        return result

    def _extract_headings(self) -> List[Dict[str, Any]]:
        """Extract markdown headings using tree-sitter.

        This correctly ignores # comments inside code fences by using the AST.
        """
        headings: List[Dict[str, Any]] = []

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
            # The second child is inline (heading content)
            for child in node.children:
                if 'marker' in child.type:
                    # atx_h1_marker, atx_h2_marker, etc.
                    level = int(child.type[5])  # Extract number from 'atx_h1_marker'
                elif child.type == 'inline':
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
        """Extract all links from markdown using tree-sitter inline parser.

        Args:
            link_type: Filter by type (internal, external, email, all)
            domain: Filter by domain (for external links)

        Returns:
            List of link dicts with line, column, text, url, type, etc.
        """
        if not self.inline_tree:
            # Fallback to regex if inline parser fails
            return self._extract_links_regex(link_type, domain)

        links = []
        # Use inline parser which properly parses links
        link_nodes = self._find_nodes_in_tree(self.inline_tree, 'inline_link')

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
            node: Tree-sitter inline_link node

        Returns:
            Link text or None if not found
        """
        for child in node.children:
            if child.type == 'link_text':
                # In inline grammar, link_text contains the text directly
                return cast(str, child.text.decode('utf-8'))
        return None

    def _extract_link_destination(self, node) -> Optional[str]:
        """Extract URL from a link node's link_destination child.

        Args:
            node: Tree-sitter inline_link node

        Returns:
            Link URL or None if not found
        """
        for child in node.children:
            if child.type == 'link_destination':
                # In inline grammar, link_destination contains the URL directly
                return cast(str, child.text.decode('utf-8'))
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

    def _heading_to_slug(self, heading: str) -> str:
        """Convert a heading to a URL-safe anchor slug.

        Uses GitHub-style slug generation:
        - Lowercase the heading
        - Replace spaces and underscores with hyphens
        - Remove special characters (except hyphens)
        - Collapse multiple hyphens into one

        Args:
            heading: The heading text

        Returns:
            URL-safe anchor slug
        """
        slug = heading.lower()
        # Replace spaces and underscores with hyphens
        slug = re.sub(r'[\s_]+', '-', slug)
        # Remove special characters except hyphens and alphanumerics
        slug = re.sub(r'[^\w-]', '', slug)
        # Collapse multiple hyphens
        slug = re.sub(r'-+', '-', slug)
        # Strip leading/trailing hyphens
        slug = slug.strip('-')
        return slug

    def _is_broken_link(self, url: str) -> bool:
        """Check if an internal link is broken.

        Handles both anchor links (#heading) and file links (path/to/file).

        Args:
            url: Internal link path or anchor

        Returns:
            True if link target doesn't exist
        """
        # Handle anchor links (same-document links)
        if url.startswith('#'):
            anchor = url[1:]  # Remove the leading #
            # Get all headings and check if any matches
            headings = self._extract_headings()
            for heading in headings:
                if self._heading_to_slug(heading['name']) == anchor:
                    return False
            return True

        # Handle file links - resolve relative to markdown file's directory
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

    def _extract_fence_language(self, node) -> str:
        """Extract language identifier from fenced code block node.

        Args:
            node: Fenced code block tree-sitter node

        Returns:
            Language identifier or 'text' if not specified
        """
        for child in node.children:
            if child.type == 'info_string':
                # Language tag (e.g., 'python', 'javascript')
                # In new grammar, info_string directly contains the language text
                lang = cast(str, child.text.decode('utf-8').strip())
                return lang if lang else 'text'
        return 'text'

    def _extract_fence_source(self, node) -> str:
        """Extract source code from fenced code block node.

        Args:
            node: Fenced code block tree-sitter node

        Returns:
            Source code string
        """
        for child in node.children:
            if child.type == 'code_fence_content':
                return cast(str, child.text.decode('utf-8'))
        return ''

    def _build_fenced_block_info(self, node, block_lang: str, source: str) -> Dict[str, Any]:
        """Build code block info dict from node and extracted data.

        Args:
            node: Fenced code block tree-sitter node
            block_lang: Language identifier
            source: Source code

        Returns:
            Dict with line_start, line_end, language, source, etc.
        """
        # Get position (tree-sitter is 0-indexed)
        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1
        line_count = source.count('\n') + 1 if source else 0

        return {
            'line_start': line_start,
            'line_end': line_end,
            'language': block_lang,
            'source': source,
            'line_count': line_count,
            'type': 'fenced',
        }

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
            block_lang = self._extract_fence_language(node)
            source = self._extract_fence_source(node)

            # Apply language filter
            if language and block_lang != language:
                continue

            code_blocks.append(self._build_fenced_block_info(node, block_lang, source))

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
        block_lines: List[str] = []

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
        """Extract inline code snippets using tree-sitter inline parser.

        Args:
            language: Language filter (not applicable to inline code)

        Returns:
            List of inline code dicts with line, column, source, etc.
        """
        if not self.inline_tree:
            # Fallback to regex
            return self._extract_inline_code(language)

        inline_blocks = []

        # Find all code_span nodes from inline parser
        code_span_nodes = self._find_nodes_in_tree(self.inline_tree, 'code_span')

        for node in code_span_nodes:
            # Extract the code text - in new grammar, code_span text includes backticks
            # So we need to strip them
            full_text = node.text.decode('utf-8')
            # Remove leading/trailing backticks
            source = full_text.strip('`').strip()

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
        topics:
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

            if metadata is None:
                # Empty front matter (---\n---) - valid but empty
                metadata = {}
            elif not isinstance(metadata, dict):
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

    def _normalize_related_entry(self, entry: Any) -> Optional[str]:
        """Normalize a related entry to a path string.

        Handles both simple string paths and structured dict entries with
        uri/path/href fields (common in structured documentation).

        Args:
            entry: Either a string path or dict with path in uri/path/href field

        Returns:
            Normalized path string, or None if no path could be extracted
        """
        if isinstance(entry, str):
            return entry
        if isinstance(entry, dict):
            # Try common path field names
            for fname in ('uri', 'path', 'href', 'url', 'file'):
                if fname in entry and isinstance(entry[fname], str):
                    path = cast(str, entry[fname])
                    # Strip doc:// prefix if present
                    if path.startswith('doc://'):
                        path = path[6:]  # Remove 'doc://'
                    return path
        return None

    def _process_related_path(
        self, rel_path: str, base_dir: Path, tracker: RelatedTracker
    ) -> Optional[Dict[str, Any]]:
        """Process a single related document path.

        Args:
            rel_path: Relative path to process
            base_dir: Base directory for resolving relative paths
            tracker: RelatedTracker instance for state management

        Returns:
            Dict with file info, or None if path should be skipped (URL or non-markdown)
        """
        # Check file limit
        if not tracker.should_continue():
            tracker.truncated = True
            return None

        # Skip URLs
        if rel_path.startswith(('http://', 'https://', 'mailto:')):
            return None

        # Resolve the path
        resolved = Path(rel_path) if rel_path.startswith('/') else (base_dir / rel_path).resolve()

        # Check if file exists
        if not resolved.exists():
            return {'path': rel_path, 'resolved_path': str(resolved), 'exists': False, 'headings': [], 'related': []}

        # Skip non-markdown files
        if resolved.suffix.lower() not in ('.md', '.markdown'):
            return None

        # Increment file count
        tracker.increment()

        # Extract headings from related file
        try:
            related_analyzer = MarkdownAnalyzer(str(resolved))
            headings = related_analyzer._extract_headings()
            result = {
                'path': rel_path, 'resolved_path': str(resolved), 'exists': True,
                'headings': [h.get('name', '') for h in headings[:10]], 'related': []
            }
            # depth=0 means unlimited, depth>1 means continue recursing
            if tracker.depth == 0 or tracker.depth > 1:
                next_depth = 0 if tracker.depth == 0 else tracker.depth - 1
                next_tracker = RelatedTracker(
                    depth=next_depth,
                    visited=tracker.visited,
                    file_count=tracker.file_count,
                    limit=tracker.limit,
                    truncated=tracker.truncated
                )
                result['related'] = related_analyzer._extract_related(tracker=next_tracker)
                # Update parent tracker with child's counts
                tracker.file_count = next_tracker.file_count
                tracker.truncated = next_tracker.truncated
            return result
        except Exception as e:
            logging.debug(f"Failed to analyze related file {resolved}: {e}")
            return {'path': rel_path, 'resolved_path': str(resolved), 'exists': True, 'error': str(e), 'headings': [], 'related': []}

    def _find_related_paths(self, frontmatter_data: Dict[str, Any]) -> List[str]:
        """Extract related document paths from frontmatter data.

        Looks for these fields: related, related_docs, see_also, references.

        Args:
            frontmatter_data: Frontmatter data dict

        Returns:
            List of related document paths
        """
        related_fields = ['related', 'related_docs', 'see_also', 'references']
        related_paths = []

        for fname in related_fields:
            value = frontmatter_data.get(fname)
            if value:
                if isinstance(value, list):
                    for item in value:
                        path = self._normalize_related_entry(item)
                        if path:
                            related_paths.append(path)
                elif isinstance(value, str):
                    related_paths.append(value)
                elif isinstance(value, dict):
                    path = self._normalize_related_entry(value)
                    if path:
                        related_paths.append(path)

        return related_paths

    def _extract_related(
        self, depth: int = 1, _visited: Optional[set] = None,
        _file_count: Optional[Dict[str, Any]] = None, limit: int = 100,
        tracker: Optional[RelatedTracker] = None
    ) -> List[Dict[str, Any]]:
        """Extract related documents from front matter.

        Args:
            depth: How deep to follow links (1=immediate, 0=unlimited) [deprecated, use tracker]
            _visited: Internal set to prevent cycles [deprecated, use tracker]
            _file_count: Internal counter for limit tracking [deprecated, use tracker]
            limit: Maximum number of files to traverse [deprecated, use tracker]
            tracker: RelatedTracker instance (recommended)

        Returns:
            List of related document info dicts with headings
        """
        # Support legacy call signature for backward compatibility
        if tracker is None:
            tracker = RelatedTracker(
                depth=depth,
                visited=_visited or set(),
                file_count=_file_count['count'] if _file_count else 0,
                limit=limit,
                truncated=_file_count.get('truncated', False) if _file_count else False
            )

        # Check limit before processing
        if not tracker.should_continue():
            tracker.truncated = True
            return []

        # Add current file to visited (skip if already visited)
        current_path = Path(self.path).resolve()
        if tracker.mark_visited(current_path):
            return []

        # Get front matter
        fm = self._extract_frontmatter()
        if not fm or not fm.get('data'):
            return []

        # Find related paths from frontmatter
        related_paths = self._find_related_paths(fm['data'])
        if not related_paths:
            return []

        # Process each related path
        base_dir = current_path.parent
        results = []
        for rel_path in related_paths:
            if not tracker.should_continue():
                tracker.truncated = True
                break
            result = self._process_related_path(rel_path, base_dir, tracker)
            if result is not None:
                results.append(result)

        # Update legacy _file_count dict if provided (backward compatibility)
        if _file_count is not None:
            _file_count['count'] = tracker.file_count
            _file_count['truncated'] = tracker.truncated

        return results

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

        if not start_line or heading_level is None:
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
