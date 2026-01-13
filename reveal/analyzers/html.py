"""HTML analyzer with template support and progressive disclosure."""

import re
import logging
from typing import Dict, List, Any, Optional
from ..base import FileAnalyzer
from ..registry import register
from ..structure_options import StructureOptions

# Try to import BeautifulSoup4 - required for HTML parsing
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


@register('.html', '.htm', name='HTML', icon='')
class HTMLAnalyzer(FileAnalyzer):
    """HTML file analyzer with progressive disclosure.

    Extracts document structure, semantic elements, links, metadata, and template directives.
    Supports Jinja2, Go templates, Handlebars, and other template engines.
    """

    def __init__(self, path: str):
        super().__init__(path)

        if not BS4_AVAILABLE:
            raise ImportError(
                "BeautifulSoup4 is required for HTML analysis. "
                "Install with: pip install beautifulsoup4"
            )

        # Parse HTML with BeautifulSoup
        # Try lxml first (faster), fallback to html.parser (stdlib)
        try:
            self.soup = BeautifulSoup(self.content, 'lxml')
        except Exception as e:
            # lxml not installed or parsing failed, use stdlib parser
            logging.debug(f"lxml parser not available for {path}, using html.parser: {e}")
            self.soup = BeautifulSoup(self.content, 'html.parser')

        # Detect template type
        self.template_type = self._detect_template_type()

    def get_structure(self, options: Optional[StructureOptions] = None, head: Optional[int] = None, tail: Optional[int] = None, range: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Extract HTML structure progressively.

        Args:
            options: StructureOptions config object (recommended)
            head: Show first N lines
            tail: Show last N lines
            range: Line range (e.g., "10-20")
            **kwargs: Additional options for backward compatibility

        Supported options (via StructureOptions or kwargs):
            head: Show first N lines
            tail: Show last N lines
            range: Show line range (start, end)
            semantic: Extract semantic elements (navigation, content, forms, media, etc.)
            links: Extract all links (maps to extract_links in StructureOptions)
            link_type: Filter links by type (internal, external, anchor, mailto, tel)
            domain: Filter links by domain
            broken: Check for broken links (local files only)
            metadata: Extract head metadata (SEO, OpenGraph, Twitter cards)
            scripts: Extract script tags (inline, external, all)
            styles: Extract stylesheets (inline, external, all)
            outline: Show document outline (hierarchy view)

        Returns:
            Dict with HTML structure based on requested features
        """
        # Backward compatibility: convert kwargs to StructureOptions
        if options is None:
            # Merge explicit parameters into kwargs
            if head is not None:
                kwargs['head'] = head
            if tail is not None:
                kwargs['tail'] = tail
            if range is not None:
                kwargs['range'] = range

            options = StructureOptions.from_kwargs(**kwargs)
            # Handle 'links' kwarg mapping to 'extract_links'
            if 'links' in kwargs:
                options.extract_links = kwargs['links']

        # Handle line extraction (head/tail/range)
        if options.head or options.tail or options.range:
            return self._extract_lines(options.head, options.tail, options.range)

        # Specialized extractions (filtering mode)
        if options.metadata:
            return {'metadata': self._extract_metadata()}

        if options.extract_links:
            return {'links': self._extract_links(options.link_type, options.domain, options.broken)}

        if options.semantic:
            return {'semantic': self._extract_semantic_elements(options.semantic)}

        if options.scripts:
            return {'scripts': self._extract_scripts(options.scripts)}

        if options.styles:
            return {'styles': self._extract_styles(options.styles)}

        # Default: Full structure overview (progressive disclosure)
        return self._get_default_structure()

    def _get_default_structure(self) -> Dict[str, Any]:
        """Get default HTML structure (programmatic format for tests/API).

        Returns:
            Dict with structured HTML information
        """
        structure = {
            'type': 'html',
            'document': self._build_document_info(),
            'head': self._build_head_info(),
            'body': self._build_body_info(),
            'stats': self._build_stats(),
        }

        # Template information
        if template_info := self._build_template_info():
            structure['template'] = template_info

        return structure

    def _build_document_info(self) -> Dict[str, Any]:
        """Extract document-level information."""
        info = {}

        # Language from <html> tag
        html_tag = self.soup.find('html')
        if html_tag:
            if lang := html_tag.get('lang'):
                info['language'] = lang

        # DOCTYPE detection (from raw content)
        if doctype_match := re.search(r'<!DOCTYPE\s+(\w+)', self.content, re.IGNORECASE):
            info['doctype'] = doctype_match.group(1).lower()

        return info

    def _build_head_info(self) -> Dict[str, Any]:
        """Extract <head> section information."""
        info = {}

        if not self.soup.head:
            return info

        # Title
        if title := self.soup.head.title:
            info['title'] = title.string

        # Meta tags
        meta_tags = {}
        for meta in self.soup.head.find_all('meta'):
            if name := meta.get('name'):
                meta_tags[name] = meta.get('content', '')
            elif prop := meta.get('property'):
                meta_tags[prop] = meta.get('content', '')
            elif charset := meta.get('charset'):
                meta_tags['charset'] = charset
        if meta_tags:
            info['meta'] = meta_tags

        return info

    def _build_body_info(self) -> Dict[str, Any]:
        """Extract <body> section information."""
        info = {}

        # Semantic elements
        semantic_elements = []
        for tag in ['nav', 'header', 'main', 'article', 'section', 'aside', 'footer']:
            if self.soup.find(tag):
                semantic_elements.append(tag)
        if semantic_elements:
            info['semantic'] = semantic_elements

        return info

    def _build_stats(self) -> Dict[str, int]:
        """Gather statistics about HTML elements."""
        return {
            'links': len(self.soup.find_all('a')),
            'images': len(self.soup.find_all('img')),
            'forms': len(self.soup.find_all('form')),
            'tables': len(self.soup.find_all('table')),
        }

    def _build_template_info(self) -> Optional[Dict[str, Any]]:
        """Extract template engine information."""
        if not self.template_type:
            return None

        info = {'type': self.template_type}

        # Extract template variables based on type
        if self.template_type == 'jinja2':
            variables = self._extract_jinja2_variables()
            if variables:
                info['variables'] = variables
            blocks = self._find_template_blocks()
            if blocks:
                info['blocks'] = blocks
        elif self.template_type in ['go-template', 'handlebars']:
            variables = self._extract_template_variables(self.template_type)
            if variables:
                info['variables'] = variables

        return info

    def _detect_template_type(self) -> Optional[str]:
        """Detect template engine from content.

        Returns:
            Template type name or None
        """
        # Check more specific patterns first to avoid false positives

        # ERB (Ruby): <%= %> or <% %>
        if re.search(r'<%=?.*?%>', self.content):
            return 'erb'

        # PHP: <?php
        if re.search(r'<\?php', self.content):
            return 'php'

        # Go templates: {{ . }} or {{- .Field }} (check before Jinja2/Handlebars)
        if re.search(r'\{\{-?\s*\.', self.content):
            return 'go-template'

        # Handlebars: {{#if}}, {{#each}}, etc. (check before Jinja2)
        if re.search(r'\{\{#(if|each|with|unless)', self.content):
            return 'handlebars'

        # Jinja2 / Django: {% %} and {{ }} (most generic, check last)
        if re.search(r'\{%.*?%\}|\{\{.*?\}\}', self.content):
            return 'jinja2'

        return None

    def _find_template_variables(self) -> List[str]:
        """Find template variable references.

        Returns:
            Sorted list of unique variable names
        """
        if not self.template_type:
            return []

        variables = set()

        # Jinja2: {{ variable }}, {{ object.property }}
        if self.template_type == 'jinja2':
            for match in re.finditer(r'\{\{\s*([a-zA-Z_][\w.]*)', self.content):
                variables.add(match.group(1))

        # Go: {{ .Variable }}, {{ .Object.Property }}
        elif self.template_type == 'go-template':
            for match in re.finditer(r'\{\{-?\s*\.([a-zA-Z_][\w.]*)', self.content):
                variables.add(f'.{match.group(1)}')

        # Handlebars: {{variable}}, {{object.property}}
        elif self.template_type == 'handlebars':
            for match in re.finditer(r'\{\{\s*([a-zA-Z_][\w.]*)', self.content):
                variables.add(match.group(1))

        return sorted(list(variables))

    def _extract_jinja2_variables(self) -> List[str]:
        """Extract Jinja2 variables from template.

        Returns:
            List of unique variable names
        """
        variables = set()
        # Match {{ variable.name }} patterns
        for match in re.finditer(r'\{\{\s*([a-zA-Z_][\w.]*)', self.content):
            variables.add(match.group(1))
        return sorted(list(variables))

    def _extract_template_variables(self, template_type: str) -> List[str]:
        """Extract template variables based on template type.

        Args:
            template_type: Type of template (go-template, handlebars, etc.)

        Returns:
            List of unique variable names
        """
        variables = set()
        if template_type == 'go-template':
            # Match {{ .Variable }} patterns
            for match in re.finditer(r'\{\{\s*(\.[A-Z][\w.]*)', self.content):
                variables.add(match.group(1))
        elif template_type == 'handlebars':
            # Match {{variable}} patterns
            for match in re.finditer(r'\{\{\s*([a-zA-Z_][\w.]*)', self.content):
                variables.add(match.group(1))
        return sorted(list(variables))

    def _find_template_blocks(self) -> List[Dict[str, Any]]:
        """Find template block definitions.

        Returns:
            List of blocks with name and line number
        """
        if self.template_type != 'jinja2':
            return []

        blocks = []
        for i, line in enumerate(self.lines, 1):
            if match := re.search(r'\{%\s*block\s+(\w+)', line):
                blocks.append({
                    'name': match.group(1),
                    'line': i,
                })

        return blocks

    def _extract_metadata(self) -> Dict[str, Any]:
        """Extract head metadata (SEO, social, etc.).

        Returns:
            Dict with title, meta tags, canonical, stylesheets, scripts
        """
        metadata = {}

        head = self.soup.head
        if not head:
            return metadata

        # Title
        if head.title:
            metadata['title'] = head.title.string

        # Meta tags
        meta_tags = {}
        for meta in head.find_all('meta'):
            # Standard meta tags (name attribute)
            if name := meta.get('name'):
                meta_tags[name] = meta.get('content', '')
            # OpenGraph / Twitter (property attribute)
            elif prop := meta.get('property'):
                meta_tags[prop] = meta.get('content', '')
            # Charset
            elif charset := meta.get('charset'):
                meta_tags['charset'] = charset

        if meta_tags:
            metadata['meta'] = meta_tags

        # Canonical URL
        if canonical := head.find('link', rel='canonical'):
            metadata['canonical'] = canonical.get('href')

        # Stylesheets
        stylesheets = [
            link.get('href') for link in head.find_all('link', rel='stylesheet')
        ]
        if stylesheets:
            metadata['stylesheets'] = stylesheets

        # Scripts
        scripts = []
        for script in head.find_all('script'):
            script_info = {}
            if src := script.get('src'):
                script_info['src'] = src
                script_info['type'] = 'external'
            else:
                script_info['type'] = 'inline'
                # Include snippet of inline scripts
                script_text = script.string or ''
                if script_text:
                    script_info['preview'] = script_text[:100]
            scripts.append(script_info)

        if scripts:
            metadata['scripts'] = scripts

        return metadata

    def _extract_links(self,
                      link_type: Optional[str] = None,
                      domain: Optional[str] = None,
                      check_broken: bool = False) -> List[Dict[str, Any]]:
        """Extract and classify links.

        Args:
            link_type: Filter by type (internal, external, anchor, mailto, tel)
            domain: Filter by domain
            check_broken: Check if local links are broken

        Returns:
            List of links with URL, text, line number, and type
        """
        links = []

        for a_tag in self.soup.find_all('a'):
            href = a_tag.get('href', '')
            text = a_tag.get_text(separator=' ', strip=True)  # Preserve spaces between nested elements
            line = self._get_line_number(a_tag)

            # Classify link
            link_info = {
                'url': href,
                'text': text,
                'line': line,
                'type': self._classify_link_type(href),
            }

            # Filter by type
            if link_type and link_info['type'] != link_type:
                continue

            # Filter by domain
            if domain and domain not in href:
                continue

            # Check if broken (basic check for local files)
            if check_broken:
                is_broken = self._is_broken_link(href)
                if is_broken:
                    link_info['broken'] = True

            links.append(link_info)

        return links

    def _classify_link_type(self, href: str) -> str:
        """Classify link as internal, external, anchor, etc.

        Args:
            href: Link URL

        Returns:
            Link type string
        """
        if not href:
            return 'empty'
        if href.startswith('#'):
            return 'anchor'
        if href.startswith('mailto:'):
            return 'mailto'
        if href.startswith('tel:'):
            return 'tel'
        if href.startswith('http://') or href.startswith('https://'):
            return 'external'
        if href.startswith('/'):
            return 'internal'
        return 'relative'

    def _is_broken_link(self, href: str) -> bool:
        """Basic broken link check (local files only).

        Args:
            href: Link URL

        Returns:
            True if link appears broken, False otherwise
        """
        # Only check local/relative links
        if href.startswith('/') or (not href.startswith('http') and not href.startswith('#')):
            # Build target path relative to current file
            if href.startswith('/'):
                # Absolute path from root (can't check without knowing web root)
                return False
            else:
                # Relative path
                target = self.path.parent / href.lstrip('./')
                return not target.exists()
        return False

    def _extract_semantic_elements(self, element_type: str) -> List[Dict[str, Any]]:
        """Extract semantic HTML elements.

        Args:
            element_type: Type of elements (navigation, content, forms, media, interactive)

        Returns:
            List of semantic elements with tag, id, class, line, text
        """
        elements = []

        # Map element types to tags
        semantic_map = {
            'navigation': ['nav', 'header'],
            'content': ['main', 'article', 'section'],
            'aside': ['aside'],
            'footer': ['footer'],
            'forms': ['form'],
            'media': ['img', 'video', 'audio', 'picture'],
            'interactive': ['button', 'input', 'select', 'textarea'],
        }

        # Get tags for requested type (or use type as tag name directly)
        tags = semantic_map.get(element_type, [element_type])

        for tag in tags:
            for elem in self.soup.find_all(tag):
                elem_info = {
                    'tag': tag,
                    'line': self._get_line_number(elem),
                }

                if elem_id := elem.get('id'):
                    elem_info['id'] = elem_id

                if elem_class := elem.get('class'):
                    elem_info['class'] = ' '.join(elem_class)

                # Get text preview (first 100 chars)
                text = elem.get_text(strip=True)
                if text:
                    elem_info['text'] = text[:100]

                elements.append(elem_info)

        return elements

    def _extract_scripts(self, script_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract script tags.

        Args:
            script_type: Filter by type (inline, external, all)

        Returns:
            List of scripts
        """
        scripts = []

        for script in self.soup.find_all('script'):
            script_info = {
                'line': self._get_line_number(script),
            }

            if src := script.get('src'):
                script_info['type'] = 'external'
                script_info['src'] = src
            else:
                script_info['type'] = 'inline'
                script_text = script.string or ''
                if script_text:
                    script_info['preview'] = script_text.strip()[:200]

            # Filter by type
            if script_type and script_type != 'all' and script_info['type'] != script_type:
                continue

            scripts.append(script_info)

        return scripts

    def _extract_styles(self, style_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract stylesheets.

        Args:
            style_type: Filter by type (inline, external, all)

        Returns:
            List of stylesheets
        """
        styles = []

        # External stylesheets (link tags)
        for link in self.soup.find_all('link', rel='stylesheet'):
            if style_type and style_type != 'all' and style_type != 'external':
                continue

            styles.append({
                'type': 'external',
                'href': link.get('href'),
                'line': self._get_line_number(link),
            })

        # Inline styles (style tags)
        for style in self.soup.find_all('style'):
            if style_type and style_type != 'all' and style_type != 'inline':
                continue

            style_info = {
                'type': 'inline',
                'line': self._get_line_number(style),
            }

            style_text = style.string or ''
            if style_text:
                style_info['preview'] = style_text.strip()[:200]

            styles.append(style_info)

        return styles

    def _summarize_semantic_elements(self, body) -> Dict[str, int]:
        """Count semantic elements in body.

        Args:
            body: BeautifulSoup body element

        Returns:
            Dict mapping semantic tag names to counts
        """
        semantic_tags = ['nav', 'header', 'main', 'article', 'section', 'aside', 'footer']
        counts = {}

        for tag in semantic_tags:
            count = len(body.find_all(tag))
            if count > 0:
                counts[tag] = count

        return counts

    def _get_line_number(self, element) -> int:
        """Get approximate line number for element.

        Args:
            element: BeautifulSoup element

        Returns:
            Line number (1-indexed) or 0 if not found
        """
        # Simple approach: search for element string in content
        elem_str = str(element)

        # For very long elements, use just the opening tag
        if len(elem_str) > 200:
            # Extract opening tag
            tag_match = re.match(r'<[^>]+>', elem_str)
            if tag_match:
                elem_str = tag_match.group(0)

        # Search for this pattern in lines
        search_str = elem_str[:100]  # First 100 chars

        for i, line in enumerate(self.lines, 1):
            if search_str[:50] in line:
                return i

        return 0

    def _get_line_range(self, element) -> Optional[str]:
        """Get line range for element (start-end).

        Args:
            element: BeautifulSoup element

        Returns:
            Line range string like "5-42" or None
        """
        start = self._get_line_number(element)
        if not start:
            return None

        # Estimate end by counting newlines in element
        elem_str = str(element)
        elem_lines = elem_str.count('\n')
        end = start + elem_lines

        return f"{start}-{end}"

    def _extract_lines(self, head: int = None, tail: int = None,
                      range: tuple = None) -> Dict[str, Any]:
        """Extract specific lines from HTML.

        Args:
            head: First N lines
            tail: Last N lines
            range: Line range (start, end)

        Returns:
            Dict with content
        """
        if range:
            start, end = range
            content = '\n'.join(self.lines[start-1:end])
        elif head:
            content = '\n'.join(self.lines[:head])
        elif tail:
            content = '\n'.join(self.lines[-tail:])
        else:
            content = self.content

        return {
            'type': 'html',
            'content': content,
        }

    def extract_element(self, selector: str) -> Optional[Dict[str, Any]]:
        """Extract specific element by CSS selector, ID, or tag.

        Args:
            selector: CSS selector, #id, .class, or tag name

        Returns:
            Dict with element info or None if not found
        """
        element = None

        # Try as CSS selector first (if it looks like one)
        if selector.startswith('.') or selector.startswith('#') or ' ' in selector or '>' in selector:
            element = self.soup.select_one(selector)
        else:
            # Try as ID
            element = self.soup.find(id=selector.lstrip('#'))
            if not element:
                # Try as tag name
                element = self.soup.find(selector)

        if not element:
            return None

        return {
            'tag': element.name,
            'attributes': dict(element.attrs) if hasattr(element, 'attrs') else {},
            'content': str(element),
            'text': element.get_text(strip=True) if hasattr(element, 'get_text') else '',
            'line': self._get_line_number(element),
        }

    def _format_metadata_as_items(self) -> List[Dict[str, Any]]:
        """Format metadata as list of items for reveal rendering.

        Returns:
            List of dicts with 'line' and 'name' keys
        """
        items = []
        metadata = self._extract_metadata()

        # Title
        if 'title' in metadata:
            items.append({
                'line': 0,
                'name': f"Title: {metadata['title']}"
            })

        # Meta tags
        if 'meta' in metadata:
            for name, content in metadata['meta'].items():
                items.append({
                    'line': 0,
                    'name': f"Meta {name}: {content[:80]}..." if len(content) > 80 else f"Meta {name}: {content}"
                })

        # Canonical URL
        if 'canonical' in metadata:
            items.append({
                'line': 0,
                'name': f"Canonical: {metadata['canonical']}"
            })

        # Stylesheets
        if 'stylesheets' in metadata:
            for stylesheet in metadata['stylesheets']:
                items.append({
                    'line': 0,
                    'name': f"Stylesheet: {stylesheet}"
                })

        # Scripts
        if 'scripts' in metadata:
            for script in metadata['scripts']:
                if script['type'] == 'external':
                    items.append({
                        'line': 0,
                        'name': f"Script (external): {script['src']}"
                    })
                else:
                    preview = script.get('preview', '')
                    items.append({
                        'line': 0,
                        'name': f"Script (inline): {preview[:50]}..." if preview else "Script (inline)"
                    })

        return items

    def _format_semantic_as_items(self, semantic_type: str) -> List[Dict[str, Any]]:
        """Format semantic elements as list of items for reveal rendering.

        Args:
            semantic_type: Type of semantic elements to extract

        Returns:
            List of dicts with 'line' and 'name' keys
        """
        elements = self._extract_semantic_elements(semantic_type)
        items = []

        for elem in elements:
            tag = elem.get('tag', '')
            attrs = elem.get('attributes', {})
            elem_id = attrs.get('id', '')
            elem_class = ' '.join(attrs.get('class', [])) if isinstance(attrs.get('class'), list) else attrs.get('class', '')

            label = f"<{tag}>"
            if elem_id:
                label += f" #{elem_id}"
            elif elem_class:
                label += f" .{elem_class.split()[0] if elem_class else ''}"

            items.append({
                'line': elem.get('line', 0),
                'name': label
            })

        return items

    def _format_scripts_as_items(self, script_type: str) -> List[Dict[str, Any]]:
        """Format scripts as list of items for reveal rendering.

        Args:
            script_type: Type of scripts (inline, external, all)

        Returns:
            List of dicts with 'line' and 'name' keys
        """
        scripts = self._extract_scripts(script_type)
        items = []

        for script in scripts:
            if script['type'] == 'external':
                items.append({
                    'line': script.get('line', 0),
                    'name': f"External: {script['src']}"
                })
            else:
                preview = script.get('preview', '')
                items.append({
                    'line': script.get('line', 0),
                    'name': f"Inline: {preview[:60]}..." if preview else "Inline script"
                })

        return items

    def _format_styles_as_items(self, style_type: str) -> List[Dict[str, Any]]:
        """Format styles as list of items for reveal rendering.

        Args:
            style_type: Type of styles (inline, external, all)

        Returns:
            List of dicts with 'line' and 'name' keys
        """
        styles = self._extract_styles(style_type)
        items = []

        for style in styles:
            if style['type'] == 'external':
                items.append({
                    'line': style.get('line', 0),
                    'name': f"External: {style['href']}"
                })
            else:
                preview = style.get('preview', '')
                items.append({
                    'line': style.get('line', 0),
                    'name': f"Inline: {preview[:60]}..." if preview else "Inline styles"
                })

        return items
