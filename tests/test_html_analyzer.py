"""Tests for HTML analyzer."""

import unittest
import tempfile
import os
from pathlib import Path

from reveal.analyzers.html import HTMLAnalyzer


class TestHTMLAnalyzer(unittest.TestCase):
    """Test HTML analyzer functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_temp_html(self, content: str, filename: str = "test.html") -> str:
        """Create temporary HTML file."""
        path = os.path.join(self.temp_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    # ========================================
    # Basic Structure Tests
    # ========================================

    def test_basic_html_structure(self):
        """Test basic HTML structure extraction."""
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <title>Test Page</title>
    <meta name="description" content="Test description">
</head>
<body>
    <nav>Navigation</nav>
    <main>Content</main>
    <footer>Footer</footer>
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['type'], 'html')
        self.assertEqual(structure['document']['language'], 'en')
        self.assertEqual(structure['document']['doctype'], 'html')
        self.assertEqual(structure['head']['title'], 'Test Page')
        self.assertIn('nav', structure['body']['semantic'])
        self.assertIn('main', structure['body']['semantic'])
        self.assertIn('footer', structure['body']['semantic'])

    def test_minimal_html(self):
        """Test minimal HTML without head/body."""
        html = "<html><h1>Hello</h1></html>"

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['type'], 'html')
        # Should not crash on missing head/body

    def test_html_statistics(self):
        """Test HTML statistics (links, images, forms, tables)."""
        html = """
<html><body>
    <a href="/">Link 1</a>
    <a href="/page">Link 2</a>
    <img src="image.png" alt="Image">
    <form><input type="text"></form>
    <table><tr><td>Data</td></tr></table>
</body></html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['stats']['links'], 2)
        self.assertEqual(structure['stats']['images'], 1)
        self.assertEqual(structure['stats']['forms'], 1)
        self.assertEqual(structure['stats']['tables'], 1)

    # ========================================
    # Template Detection Tests
    # ========================================

    def test_jinja2_template_detection(self):
        """Test Jinja2 template detection."""
        html = """
<html>
<head><title>{% block title %}Default{% endblock %}</title></head>
<body>
    <h1>{{ page.title }}</h1>
    <p>{{ user.name }}</p>
    {% if user.authenticated %}
        <p>Welcome {{ user.username }}</p>
    {% endif %}
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)

        self.assertEqual(analyzer.template_type, 'jinja2')

        structure = analyzer.get_structure()
        self.assertIn('template', structure)
        self.assertEqual(structure['template']['type'], 'jinja2')
        self.assertIn('page.title', structure['template']['variables'])
        self.assertIn('user.name', structure['template']['variables'])

    def test_jinja2_blocks(self):
        """Test Jinja2 block extraction."""
        html = """
<html>
<head>
    {% block head %}
    <title>{% block title %}Site{% endblock %}</title>
    {% endblock %}
</head>
<body>
    {% block content %}
    Default content
    {% endblock %}
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        structure = analyzer.get_structure()

        blocks = structure['template']['blocks']
        block_names = [b['name'] for b in blocks]
        self.assertIn('head', block_names)
        self.assertIn('title', block_names)
        self.assertIn('content', block_names)

    def test_go_template_detection(self):
        """Test Go template detection."""
        html = """
<html>
<body>
    <h1>{{ .Title }}</h1>
    <p>{{ .Content }}</p>
    {{- range .Items }}
        <li>{{ .Name }}</li>
    {{- end }}
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)

        self.assertEqual(analyzer.template_type, 'go-template')

        structure = analyzer.get_structure()
        self.assertEqual(structure['template']['type'], 'go-template')
        self.assertIn('.Title', structure['template']['variables'])
        self.assertIn('.Content', structure['template']['variables'])

    def test_handlebars_template_detection(self):
        """Test Handlebars template detection."""
        html = """
<html>
<body>
    <h1>{{title}}</h1>
    {{#if user}}
        <p>Hello {{user.name}}</p>
    {{/if}}
    {{#each items}}
        <li>{{this}}</li>
    {{/each}}
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)

        self.assertEqual(analyzer.template_type, 'handlebars')

    def test_erb_template_detection(self):
        """Test ERB template detection."""
        html = """
<html>
<body>
    <h1><%= @title %></h1>
    <% @items.each do |item| %>
        <li><%= item %></li>
    <% end %>
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)

        self.assertEqual(analyzer.template_type, 'erb')

    def test_php_template_detection(self):
        """Test PHP template detection."""
        html = """
<html>
<body>
    <h1><?php echo $title; ?></h1>
    <?php foreach ($items as $item): ?>
        <li><?php echo $item; ?></li>
    <?php endforeach; ?>
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)

        self.assertEqual(analyzer.template_type, 'php')

    def test_no_template_detection(self):
        """Test that plain HTML doesn't detect templates."""
        html = """
<html>
<head><title>Plain HTML</title></head>
<body><p>No templates here</p></body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)

        self.assertIsNone(analyzer.template_type)

    # ========================================
    # Link Extraction Tests
    # ========================================

    def test_link_extraction(self):
        """Test link extraction."""
        html = """
<html><body>
    <a href="/">Home</a>
    <a href="/about">About</a>
    <a href="https://example.com">External</a>
    <a href="#section">Anchor</a>
    <a href="mailto:test@example.com">Email</a>
    <a href="tel:+1234567890">Phone</a>
</body></html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(links=True)
        links = result['links']

        self.assertEqual(len(links), 6)

        # Check link types
        types = [link['type'] for link in links]
        self.assertIn('internal', types)
        self.assertIn('external', types)
        self.assertIn('anchor', types)
        self.assertIn('mailto', types)
        self.assertIn('tel', types)

    def test_link_type_filtering(self):
        """Test filtering links by type."""
        html = """
<html><body>
    <a href="/">Home</a>
    <a href="/about">About</a>
    <a href="https://example.com">External</a>
    <a href="#section">Anchor</a>
</body></html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)

        # Filter for internal links only
        result = analyzer.get_structure(links=True, link_type='internal')
        links = result['links']

        self.assertEqual(len(links), 2)
        for link in links:
            self.assertEqual(link['type'], 'internal')

    def test_link_domain_filtering(self):
        """Test filtering links by domain."""
        html = """
<html><body>
    <a href="https://example.com/page1">Example 1</a>
    <a href="https://example.com/page2">Example 2</a>
    <a href="https://other.com/page">Other</a>
</body></html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)

        # Filter for example.com domain
        result = analyzer.get_structure(links=True, domain='example.com')
        links = result['links']

        self.assertEqual(len(links), 2)
        for link in links:
            self.assertIn('example.com', link['url'])

    def test_link_text_extraction(self):
        """Test that link text is extracted."""
        html = """
<html><body>
    <a href="/page">Link Text</a>
    <a href="/page2"><strong>Bold</strong> text</a>
</body></html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(links=True)
        links = result['links']

        self.assertEqual(links[0]['text'], 'Link Text')
        self.assertEqual(links[1]['text'], 'Bold text')

    def test_broken_link_detection_relative(self):
        """Test broken link detection for relative paths."""
        html = """
<html><body>
    <a href="exists.html">Exists</a>
    <a href="missing.html">Missing</a>
</body></html>"""

        # Create the test HTML and one linked file
        path = self.create_temp_html(html)
        self.create_temp_html("<html><body>Exists</body></html>", "exists.html")

        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(links=True, broken=True)
        links = result['links']

        # Check broken status
        exists_link = [l for l in links if 'exists.html' in l['url']][0]
        missing_link = [l for l in links if 'missing.html' in l['url']][0]

        self.assertNotIn('broken', exists_link)
        self.assertTrue(missing_link.get('broken', False))

    # ========================================
    # Metadata Extraction Tests
    # ========================================

    def test_metadata_extraction(self):
        """Test metadata extraction."""
        html = """
<html>
<head>
    <title>Test Page</title>
    <meta name="description" content="Test description">
    <meta name="keywords" content="test, keywords">
    <meta property="og:title" content="OG Title">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary">
    <link rel="canonical" href="https://example.com/page">
    <link rel="stylesheet" href="/style.css">
    <script src="/script.js"></script>
    <script>console.log('inline');</script>
</head>
<body></body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(metadata=True)
        metadata = result['metadata']

        self.assertEqual(metadata['title'], 'Test Page')
        self.assertEqual(metadata['meta']['description'], 'Test description')
        self.assertEqual(metadata['meta']['keywords'], 'test, keywords')
        self.assertEqual(metadata['meta']['og:title'], 'OG Title')
        self.assertEqual(metadata['meta']['og:type'], 'website')
        self.assertEqual(metadata['meta']['twitter:card'], 'summary')
        self.assertEqual(metadata['canonical'], 'https://example.com/page')
        self.assertIn('/style.css', metadata['stylesheets'])
        self.assertEqual(len(metadata['scripts']), 2)

    def test_metadata_charset(self):
        """Test charset extraction in metadata."""
        html = """
<html>
<head>
    <meta charset="UTF-8">
    <title>Test</title>
</head>
<body></body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(metadata=True)
        metadata = result['metadata']

        self.assertEqual(metadata['meta']['charset'], 'UTF-8')

    # ========================================
    # Semantic Element Tests
    # ========================================

    def test_semantic_navigation_extraction(self):
        """Test extracting navigation semantic elements."""
        html = """
<html><body>
    <nav id="main-nav" class="primary">
        <a href="/">Home</a>
    </nav>
    <header class="site-header">
        Header content
    </header>
</body></html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(semantic='navigation')
        elements = result['semantic']

        self.assertEqual(len(elements), 2)  # nav + header

        nav_elem = [e for e in elements if e['tag'] == 'nav'][0]
        self.assertEqual(nav_elem['id'], 'main-nav')
        self.assertEqual(nav_elem['class'], 'primary')

    def test_semantic_content_extraction(self):
        """Test extracting content semantic elements."""
        html = """
<html><body>
    <main>Main content</main>
    <article>Article content</article>
    <section>Section content</section>
</body></html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(semantic='content')
        elements = result['semantic']

        self.assertEqual(len(elements), 3)
        tags = [e['tag'] for e in elements]
        self.assertIn('main', tags)
        self.assertIn('article', tags)
        self.assertIn('section', tags)

    def test_semantic_forms_extraction(self):
        """Test extracting form elements."""
        html = """
<html><body>
    <form id="search-form" method="GET" action="/search">
        <input type="text" name="q">
        <button type="submit">Search</button>
    </form>
    <form id="contact-form">
        Contact form
    </form>
</body></html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(semantic='forms')
        elements = result['semantic']

        self.assertEqual(len(elements), 2)
        form_ids = [e.get('id') for e in elements]
        self.assertIn('search-form', form_ids)
        self.assertIn('contact-form', form_ids)

    def test_semantic_media_extraction(self):
        """Test extracting media elements."""
        html = """
<html><body>
    <img src="image.png" alt="Image">
    <video src="video.mp4">Video</video>
    <audio src="audio.mp3">Audio</audio>
</body></html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(semantic='media')
        elements = result['semantic']

        self.assertEqual(len(elements), 3)
        tags = [e['tag'] for e in elements]
        self.assertIn('img', tags)
        self.assertIn('video', tags)
        self.assertIn('audio', tags)

    # ========================================
    # Element Extraction Tests
    # ========================================

    def test_extract_element_by_id(self):
        """Test extracting element by ID."""
        html = """
<html><body>
    <div id="main-content" class="container">
        <h1>Title</h1>
        <p>Content</p>
    </div>
</body></html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        element = analyzer.extract_element('main-content')

        self.assertIsNotNone(element)
        self.assertEqual(element['tag'], 'div')
        self.assertEqual(element['attributes']['id'], 'main-content')
        self.assertIn('Title', element['text'])

    def test_extract_element_by_css_selector(self):
        """Test extracting element by CSS selector."""
        html = """
<html><body>
    <div class="hero">Hero section</div>
    <div class="content">Content section</div>
</body></html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        element = analyzer.extract_element('.hero')

        self.assertIsNotNone(element)
        self.assertEqual(element['tag'], 'div')
        self.assertIn('hero', element['attributes']['class'])

    def test_extract_element_by_tag(self):
        """Test extracting element by tag name."""
        html = """
<html><body>
    <form id="search">
        <input type="text">
    </form>
</body></html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        element = analyzer.extract_element('form')

        self.assertIsNotNone(element)
        self.assertEqual(element['tag'], 'form')
        self.assertEqual(element['attributes']['id'], 'search')

    def test_extract_element_not_found(self):
        """Test extracting non-existent element."""
        html = """<html><body><p>Test</p></body></html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        element = analyzer.extract_element('nonexistent')

        self.assertIsNone(element)

    # ========================================
    # Script and Style Extraction Tests
    # ========================================

    def test_script_extraction(self):
        """Test script extraction."""
        html = """
<html>
<head>
    <script src="/external.js"></script>
    <script>console.log('inline');</script>
</head>
<body></body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(scripts='all')
        scripts = result['scripts']

        self.assertEqual(len(scripts), 2)

        external = [s for s in scripts if s['type'] == 'external'][0]
        inline = [s for s in scripts if s['type'] == 'inline'][0]

        self.assertEqual(external['src'], '/external.js')
        self.assertIn('console.log', inline['preview'])

    def test_script_filtering_inline(self):
        """Test filtering for inline scripts only."""
        html = """
<html>
<head>
    <script src="/external.js"></script>
    <script>console.log('inline');</script>
</head>
<body></body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(scripts='inline')
        scripts = result['scripts']

        self.assertEqual(len(scripts), 1)
        self.assertEqual(scripts[0]['type'], 'inline')

    def test_script_filtering_external(self):
        """Test filtering for external scripts only."""
        html = """
<html>
<head>
    <script src="/external.js"></script>
    <script>console.log('inline');</script>
</head>
<body></body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(scripts='external')
        scripts = result['scripts']

        self.assertEqual(len(scripts), 1)
        self.assertEqual(scripts[0]['type'], 'external')

    def test_style_extraction(self):
        """Test stylesheet extraction."""
        html = """
<html>
<head>
    <link rel="stylesheet" href="/external.css">
    <style>body { color: red; }</style>
</head>
<body></body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(styles='all')
        styles = result['styles']

        self.assertEqual(len(styles), 2)

        external = [s for s in styles if s['type'] == 'external'][0]
        inline = [s for s in styles if s['type'] == 'inline'][0]

        self.assertEqual(external['href'], '/external.css')
        self.assertIn('color: red', inline['preview'])

    # ========================================
    # Line Extraction Tests
    # ========================================

    def test_head_lines(self):
        """Test extracting first N lines."""
        html = """<html>
<head><title>Test</title></head>
<body>
<p>Line 4</p>
<p>Line 5</p>
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(head=3)

        self.assertEqual(result['type'], 'html')
        lines = result['content'].split('\n')
        self.assertEqual(len(lines), 3)

    def test_tail_lines(self):
        """Test extracting last N lines."""
        html = """<html>
<head><title>Test</title></head>
<body>
<p>Line 4</p>
<p>Line 5</p>
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(tail=2)

        self.assertEqual(result['type'], 'html')
        lines = result['content'].split('\n')
        self.assertEqual(len(lines), 2)

    def test_range_lines(self):
        """Test extracting line range."""
        html = """<html>
<head><title>Test</title></head>
<body>
<p>Line 4</p>
<p>Line 5</p>
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        result = analyzer.get_structure(range=(2, 4))

        self.assertEqual(result['type'], 'html')
        content = result['content']
        self.assertIn('<head>', content)
        self.assertIn('<body>', content)

    # ========================================
    # Edge Cases and Error Handling
    # ========================================

    def test_malformed_html(self):
        """Test handling malformed HTML."""
        html = """
<html>
<head><title>Test
<body>
<p>Unclosed paragraph
<div>Unclosed div"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        structure = analyzer.get_structure()

        # Should not crash
        self.assertEqual(structure['type'], 'html')

    def test_empty_html(self):
        """Test handling empty HTML."""
        html = ""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['type'], 'html')

    def test_html_with_comments(self):
        """Test HTML with comments."""
        html = """
<html>
<head>
    <!-- This is a comment -->
    <title>Test</title>
</head>
<body>
    <!-- Another comment -->
    <p>Content</p>
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        structure = analyzer.get_structure()

        # Should parse successfully
        self.assertEqual(structure['head']['title'], 'Test')

    # ========================================
    # Display/Rendering Tests
    # ========================================

    def test_default_display_no_crash(self):
        """Test that HTML default structure displays without error.

        This test prevents regression of the bug where HTML structure categories
        (type, document, head, body, stats, template) were being passed to
        _format_standard_items() which expected lists of dicts, causing:
        AttributeError: 'str' object has no attribute 'get'
        """
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <title>Test Page</title>
    <meta name="description" content="Test description">
</head>
<body>
    <nav><a href="/">Home</a></nav>
    <main>
        <h1>Welcome</h1>
        <p>Content here</p>
    </main>
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        structure = analyzer.get_structure()

        # Verify structure has expected categories
        self.assertEqual(structure['type'], 'html')
        self.assertIn('document', structure)
        self.assertIn('head', structure)
        self.assertIn('body', structure)
        self.assertIn('stats', structure)

        # Test that rendering doesn't crash
        # Import here to avoid circular dependencies
        from reveal.display.structure import _render_text_categories
        from pathlib import Path
        import io
        import sys

        # Capture output to verify it runs without error
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            # This should not raise AttributeError
            _render_text_categories(structure, Path(path), 'text')
            output = sys.stdout.getvalue()

            # Should complete without error (even if output is minimal)
            # HTML internal categories are skipped in display
            self.assertIsInstance(output, str)
        finally:
            sys.stdout = old_stdout

    def test_display_with_metadata_flag(self):
        """Test HTML display with --metadata flag formatting."""
        html = """<!DOCTYPE html>
<html>
<head>
    <title>SEO Test</title>
    <meta name="description" content="A test page">
    <meta property="og:title" content="OG Title">
    <link rel="stylesheet" href="styles.css">
    <script src="app.js"></script>
</head>
<body>
    <h1>Test</h1>
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)

        # Get metadata structure (what --metadata flag returns)
        structure = analyzer.get_structure(metadata=True)

        # Should return metadata category
        self.assertIn('metadata', structure)
        metadata = structure['metadata']

        # Metadata is a dict with title, meta, stylesheets, scripts
        self.assertIsInstance(metadata, dict)
        self.assertIn('title', metadata)
        self.assertEqual(metadata['title'], 'SEO Test')

        # Verify formatting doesn't crash
        from reveal.display.structure import _render_text_categories
        from pathlib import Path
        import io
        import sys

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            _render_text_categories(structure, Path(path), 'text')
            output = sys.stdout.getvalue()

            # Should contain metadata information
            self.assertIn('Metadata', output)
        finally:
            sys.stdout = old_stdout

    # ========================================
    # Edge Case Tests
    # ========================================

    def test_parser_fallback_on_invalid_xml(self):
        """Test fallback to html.parser when lxml fails on invalid XML-like HTML."""
        # Create HTML that might trigger lxml issues but is valid HTML
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Parser Test</title>
</head>
<body>
    <!-- Unclosed tags that HTML parser handles but XML parser might not -->
    <p>Paragraph without closing
    <br>
    <img src="test.png">
    <hr>
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        structure = analyzer.get_structure()

        # Should parse successfully with either parser
        self.assertEqual(structure['type'], 'html')
        self.assertEqual(structure['head']['title'], 'Parser Test')

    def test_extremely_nested_html(self):
        """Test HTML with deeply nested elements."""
        # Create deeply nested structure
        nested = "<div>" * 50 + "Deep content" + "</div>" * 50
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Nested Test</title>
</head>
<body>
    {nested}
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        structure = analyzer.get_structure()

        # Should handle deep nesting without crashing
        self.assertEqual(structure['type'], 'html')
        self.assertEqual(structure['head']['title'], 'Nested Test')

    def test_html_with_special_characters(self):
        """Test HTML with Unicode and special characters."""
        html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <title>特殊字符测试 — Special Chars & Entities</title>
    <meta name="description" content="Testing: <>&quot;'">
</head>
<body>
    <p>Emoji test: 🎉 🚀 ✅</p>
    <p>Math symbols: ∑ ∫ ∞ ≠ ≤ ≥</p>
    <p>Entities: &lt;div&gt; &amp; &copy; &reg;</p>
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        structure = analyzer.get_structure()

        # Should handle Unicode and special characters
        self.assertEqual(structure['type'], 'html')
        self.assertIn('特殊字符测试', structure['head']['title'])

    def test_html_with_no_head_or_body(self):
        """Test minimalist HTML without explicit head/body tags."""
        html = """<!DOCTYPE html>
<html>
<title>Minimal</title>
<h1>Hello World</h1>
<p>No explicit head or body tags</p>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        structure = analyzer.get_structure()

        # Browser-like parsers auto-create head/body
        self.assertEqual(structure['type'], 'html')
        # BeautifulSoup should auto-create structure
        self.assertIsInstance(structure, dict)

    def test_html_with_multiple_templates_detected(self):
        """Test HTML that might match multiple template patterns."""
        html = """<!DOCTYPE html>
<html>
<head>
    <title>{{ .Title }} - {% block title %}Default{% endblock %}</title>
</head>
<body>
    <p>Go: {{ .Content }}</p>
    <p>Jinja2: {{ content }}</p>
    <p>Handlebars: {{name}}</p>
    <p>ERB: <%= user.name %></p>
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)
        structure = analyzer.get_structure()

        # Should detect at least one template type
        # (implementation picks first match)
        self.assertIn('template', structure)
        self.assertIn('type', structure['template'])
        # Template type should be one of the supported ones
        self.assertIn(structure['template']['type'],
                     ['jinja2', 'go-template', 'handlebars', 'erb', 'php'])

    def test_html_with_large_inline_content(self):
        """Test HTML with very large inline scripts/styles."""
        large_script = "var data = [" + ",".join([str(i) for i in range(1000)]) + "];"
        large_style = "\n".join([f".class{i} {{ color: #{i:06x}; }}" for i in range(100)])

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Large Inline Test</title>
    <style>
    {large_style}
    </style>
    <script>
    {large_script}
    </script>
</head>
<body>
    <h1>Test</h1>
</body>
</html>"""

        path = self.create_temp_html(html)
        analyzer = HTMLAnalyzer(path)

        # Test scripts extraction
        structure = analyzer.get_structure(scripts='inline')
        self.assertIn('scripts', structure)

        scripts = structure['scripts']
        self.assertEqual(len(scripts), 1)

        # Should have preview (truncated)
        self.assertIn('preview', scripts[0])
        # Preview should be truncated, not full content
        preview = scripts[0]['preview']
        self.assertLess(len(preview), len(large_script))


if __name__ == '__main__':
    unittest.main()
