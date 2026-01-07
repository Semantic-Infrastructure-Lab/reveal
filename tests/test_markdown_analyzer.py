"""Tests for Markdown analyzer."""

import unittest
import tempfile
import os
import datetime
from reveal.analyzers.markdown import MarkdownAnalyzer


class TestMarkdownAnalyzer(unittest.TestCase):
    """Test Markdown analyzer."""

    def create_temp_markdown(self, content: str) -> str:
        """Helper: Create temp markdown file."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "test.md")
        with open(path, 'w') as f:
            f.write(content)
        return path

    def teardown_file(self, path: str):
        """Helper: Clean up temp file."""
        os.unlink(path)
        os.rmdir(os.path.dirname(path))

    def test_heading_extraction(self):
        """Test extraction of markdown headings."""
        content = """# Title

Some text here.

## Section 1

Content for section 1.

### Subsection 1.1

More content.

## Section 2

Final section.
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('headings', structure)
            headings = structure['headings']

            self.assertEqual(len(headings), 4)

            # Check levels
            self.assertEqual(headings[0]['level'], 1)
            self.assertEqual(headings[0]['name'], 'Title')

            self.assertEqual(headings[1]['level'], 2)
            self.assertEqual(headings[1]['name'], 'Section 1')

            self.assertEqual(headings[2]['level'], 3)
            self.assertEqual(headings[2]['name'], 'Subsection 1.1')

        finally:
            self.teardown_file(path)

    def test_headings_with_code_fence(self):
        """Test that # in code fences are ignored."""
        content = """# Real Heading

```python
# This is a comment, not a heading
def foo():
    pass
```

## Another Real Heading
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure()

            headings = structure['headings']
            # Should only find 2 headings, not the # comment in code
            self.assertEqual(len(headings), 2)
            self.assertEqual(headings[0]['name'], 'Real Heading')
            self.assertEqual(headings[1]['name'], 'Another Real Heading')

        finally:
            self.teardown_file(path)

    def test_link_extraction(self):
        """Test extraction of links."""
        content = """# Links Test

Here is [internal link](./other.md) and [external link](https://example.com).

Also [email](mailto:test@example.com) links.
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_links=True)

            self.assertIn('links', structure)
            links = structure['links']

            self.assertEqual(len(links), 3)

            # Check link types
            types = {l['type'] for l in links}
            self.assertIn('internal', types)
            self.assertIn('external', types)
            self.assertIn('email', types)

        finally:
            self.teardown_file(path)

    def test_link_type_filter(self):
        """Test filtering links by type."""
        content = """[internal](./foo.md)
[external](https://google.com)
[email](mailto:x@y.com)
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)

            # Filter to external only
            structure = analyzer.get_structure(extract_links=True, link_type='external')
            links = structure['links']

            self.assertEqual(len(links), 1)
            self.assertEqual(links[0]['type'], 'external')

        finally:
            self.teardown_file(path)

    def test_link_domain_filter(self):
        """Test filtering links by domain."""
        content = """[google](https://google.com/search)
[github](https://github.com/repo)
[local](./file.md)
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)

            # Filter by domain
            structure = analyzer.get_structure(extract_links=True, domain='github')
            links = structure['links']

            self.assertEqual(len(links), 1)
            self.assertIn('github', links[0]['url'])

        finally:
            self.teardown_file(path)

    def test_code_block_extraction(self):
        """Test extraction of code blocks."""
        content = """# Code Examples

```python
def hello():
    print("Hello")
```

Some text.

```javascript
console.log("Hi");
```

"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_code=True)

            self.assertIn('code_blocks', structure)
            blocks = structure['code_blocks']

            self.assertEqual(len(blocks), 2)

            # Check languages
            self.assertEqual(blocks[0]['language'], 'python')
            self.assertEqual(blocks[1]['language'], 'javascript')

            # Check source content
            self.assertIn('def hello', blocks[0]['source'])

        finally:
            self.teardown_file(path)

    def test_code_block_language_filter(self):
        """Test filtering code blocks by language."""
        content = """```python
x = 1
```

```bash
echo hi
```

```python
y = 2
```
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_code=True, language='python')
            blocks = structure['code_blocks']

            self.assertEqual(len(blocks), 2)
            for block in blocks:
                self.assertEqual(block['language'], 'python')

        finally:
            self.teardown_file(path)

    def test_inline_code_extraction(self):
        """Test extraction of inline code."""
        content = """Use `pip install` to install and `python main.py` to run."""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_code=True, inline_code=True)

            blocks = structure['code_blocks']
            inline_blocks = [b for b in blocks if b['type'] == 'inline']

            self.assertEqual(len(inline_blocks), 2)
            self.assertIn('pip install', [b['source'] for b in inline_blocks])

        finally:
            self.teardown_file(path)

    def test_extract_section(self):
        """Test extraction of a specific section by heading."""
        content = """# Title

Intro text.

## Section A

Content for A.

More A content.

## Section B

Content for B.
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            section = analyzer.extract_element('section', 'Section A')

            self.assertIsNotNone(section)
            self.assertIn('Content for A', section['source'])
            self.assertNotIn('Content for B', section['source'])

        finally:
            self.teardown_file(path)

    def test_extract_section_case_insensitive(self):
        """Test section extraction is case insensitive."""
        content = """## My Section

Content here.
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)

            # Different case should still work
            section = analyzer.extract_element('section', 'my section')
            self.assertIsNotNone(section)

            section2 = analyzer.extract_element('section', 'MY SECTION')
            self.assertIsNotNone(section2)

        finally:
            self.teardown_file(path)

    def test_empty_markdown(self):
        """Test with empty markdown file."""
        content = ""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertEqual(structure.get('headings', []), [])

        finally:
            self.teardown_file(path)

    def test_headings_all_levels(self):
        """Test heading levels 1-6."""
        content = """# H1
## H2
### H3
#### H4
##### H5
###### H6
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure()

            headings = structure['headings']
            self.assertEqual(len(headings), 6)

            for i, h in enumerate(headings, 1):
                self.assertEqual(h['level'], i)
                self.assertEqual(h['name'], f'H{i}')

        finally:
            self.teardown_file(path)

    def test_semantic_slicing_head(self):
        """Test --head slicing on structure."""
        content = """# H1
## H2
## H3
## H4
## H5
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(head=2)

            headings = structure['headings']
            self.assertEqual(len(headings), 2)
            self.assertEqual(headings[0]['name'], 'H1')
            self.assertEqual(headings[1]['name'], 'H2')

        finally:
            self.teardown_file(path)

    def test_semantic_slicing_tail(self):
        """Test --tail slicing on structure."""
        content = """# H1
## H2
## H3
## H4
## H5
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(tail=2)

            headings = structure['headings']
            self.assertEqual(len(headings), 2)
            self.assertEqual(headings[0]['name'], 'H4')
            self.assertEqual(headings[1]['name'], 'H5')

        finally:
            self.teardown_file(path)

    def test_external_link_domain_extraction(self):
        """Test domain extraction from external links."""
        content = """[Test](https://subdomain.example.com/path/to/page)"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_links=True)

            links = structure['links']
            self.assertEqual(links[0]['domain'], 'subdomain.example.com')

        finally:
            self.teardown_file(path)

    def test_broken_link_detection(self):
        """Test detection of broken internal links."""
        content = """[Broken](./nonexistent-file.md)"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_links=True)

            links = structure['links']
            # Link to nonexistent file should be marked broken
            self.assertTrue(links[0]['broken'])

        finally:
            self.teardown_file(path)

    def test_code_block_no_language(self):
        """Test code block without language specifier."""
        content = """```
plain code here
```
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_code=True)

            blocks = structure['code_blocks']
            self.assertEqual(len(blocks), 1)
            self.assertEqual(blocks[0]['language'], 'text')

        finally:
            self.teardown_file(path)

    def test_line_numbers_in_structure(self):
        """Test that line numbers are accurate."""
        content = """# First

## Second

## Third
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure()

            headings = structure['headings']
            self.assertEqual(headings[0]['line'], 1)
            self.assertEqual(headings[1]['line'], 3)
            self.assertEqual(headings[2]['line'], 5)

        finally:
            self.teardown_file(path)

    def test_frontmatter_extraction_basic(self):
        """Test extraction of basic YAML front matter."""
        content = """---
title: Test Document
author: Test Author
date: 2025-12-13
---

# Heading

Content here.
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_frontmatter=True)

            self.assertIn('frontmatter', structure)
            fm = structure['frontmatter']

            self.assertIsNotNone(fm)
            self.assertIn('data', fm)
            self.assertEqual(fm['data']['title'], 'Test Document')
            self.assertEqual(fm['data']['author'], 'Test Author')
            # YAML parses dates as date objects
            import datetime
            self.assertEqual(fm['data']['date'], datetime.date(2025, 12, 13))
            self.assertEqual(fm['line_start'], 1)
            self.assertEqual(fm['line_end'], 5)

        finally:
            self.teardown_file(path)

    def test_frontmatter_complex_nested_fields(self):
        """Test extraction of complex nested front matter structures."""
        content = """---
title: Complex Example
project: reveal
tags:
  - testing
  - metadata
  - nested-structures
related_docs:
  - path/to/doc1.md
  - path/to/doc2.md
author:
  name: Test Author
  email: test@example.com
category: documentation
created: 2025-12-13
---

# Complex Example Document

Content with complex front matter.
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_frontmatter=True)

            self.assertIn('frontmatter', structure)
            fm = structure['frontmatter']

            self.assertIsNotNone(fm)
            data = fm['data']

            # Check complex nested fields
            self.assertEqual(data['title'], 'Complex Example')
            self.assertEqual(data['project'], 'reveal')
            self.assertEqual(data['tags'], ['testing', 'metadata', 'nested-structures'])
            self.assertEqual(data['related_docs'], ['path/to/doc1.md', 'path/to/doc2.md'])
            self.assertEqual(data['category'], 'documentation')
            self.assertEqual(data['created'], datetime.date(2025, 12, 13))
            # Check nested object
            self.assertIsInstance(data['author'], dict)
            self.assertEqual(data['author']['name'], 'Test Author')
            self.assertEqual(data['author']['email'], 'test@example.com')

        finally:
            self.teardown_file(path)

    def test_frontmatter_no_frontmatter(self):
        """Test handling when no front matter is present."""
        content = """# Regular Markdown

No front matter here.
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_frontmatter=True)

            self.assertIn('frontmatter', structure)
            self.assertIsNone(structure['frontmatter'])

        finally:
            self.teardown_file(path)

    def test_frontmatter_malformed_yaml(self):
        """Test graceful handling of malformed YAML."""
        content = """---
title: Test
invalid yaml structure:
  - item1
  - item2
  missing colon here
tags: [unclosed bracket
---

# Content
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_frontmatter=True)

            # Should gracefully return None for malformed YAML
            self.assertIn('frontmatter', structure)
            self.assertIsNone(structure['frontmatter'])

        finally:
            self.teardown_file(path)

    def test_frontmatter_not_at_start(self):
        """Test that front matter not at file start is ignored."""
        content = """# Heading First

---
title: This should be ignored
---

Content.
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_frontmatter=True)

            # Should not extract front matter that's not at file start
            self.assertIn('frontmatter', structure)
            self.assertIsNone(structure['frontmatter'])

        finally:
            self.teardown_file(path)

    def test_frontmatter_missing_closing(self):
        """Test handling of front matter with missing closing delimiter."""
        content = """---
title: Test Document
author: Test Author

# Heading

Content without closing front matter delimiter.
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_frontmatter=True)

            # Should gracefully return None when closing --- is missing
            self.assertIn('frontmatter', structure)
            self.assertIsNone(structure['frontmatter'])

        finally:
            self.teardown_file(path)

    def test_frontmatter_complex_nested(self):
        """Test extraction of complex nested YAML structures."""
        content = """---
title: Complex Document
metadata:
  status: active
  priority: high
  nested:
    deep: value
    list:
      - item1
      - item2
authors:
  - name: Author 1
    email: author1@example.com
  - name: Author 2
    email: author2@example.com
---

# Content
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_frontmatter=True)

            self.assertIn('frontmatter', structure)
            fm = structure['frontmatter']

            self.assertIsNotNone(fm)
            data = fm['data']

            # Check nested structures
            self.assertEqual(data['title'], 'Complex Document')
            self.assertEqual(data['metadata']['status'], 'active')
            self.assertEqual(data['metadata']['priority'], 'high')
            self.assertEqual(data['metadata']['nested']['deep'], 'value')
            self.assertEqual(data['metadata']['nested']['list'], ['item1', 'item2'])
            self.assertEqual(len(data['authors']), 2)
            self.assertEqual(data['authors'][0]['name'], 'Author 1')
            self.assertEqual(data['authors'][1]['email'], 'author2@example.com')

        finally:
            self.teardown_file(path)

    def test_frontmatter_with_headings(self):
        """Test that both front matter and headings can be extracted together."""
        content = """---
title: Test Document
beth_topics:
  - testing
---

# Main Title

## Section 1

Content.

## Section 2

More content.
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_frontmatter=True)

            # Both frontmatter and headings should be present
            self.assertIn('frontmatter', structure)
            self.assertIn('headings', structure)

            fm = structure['frontmatter']
            self.assertIsNotNone(fm)
            self.assertEqual(fm['data']['title'], 'Test Document')
            self.assertEqual(fm['data']['beth_topics'], ['testing'])

            headings = structure['headings']
            self.assertEqual(len(headings), 3)
            self.assertEqual(headings[0]['name'], 'Main Title')
            self.assertEqual(headings[1]['name'], 'Section 1')
            self.assertEqual(headings[2]['name'], 'Section 2')

        finally:
            self.teardown_file(path)

    def test_frontmatter_json_output(self):
        """Test front matter in JSON output structure."""
        content = """---
title: JSON Test
tags: [test1, test2]
---

# Content
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_frontmatter=True)

            # Verify JSON-compatible structure
            fm = structure['frontmatter']
            self.assertIsInstance(fm, dict)
            self.assertIsInstance(fm['data'], dict)
            self.assertIsInstance(fm['line_start'], int)
            self.assertIsInstance(fm['line_end'], int)
            self.assertIsInstance(fm['raw'], str)

            # Verify raw YAML is preserved
            self.assertIn('title: JSON Test', fm['raw'])
            self.assertIn('tags: [test1, test2]', fm['raw'])

        finally:
            self.teardown_file(path)


class TestMarkdownRegexFallback(unittest.TestCase):
    """Test regex fallback for heading extraction."""

    def test_regex_extraction(self):
        """Test the regex fallback method directly."""
        content = """# H1
## H2
### H3
"""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "test.md")
        with open(path, 'w') as f:
            f.write(content)

        try:
            analyzer = MarkdownAnalyzer(path)
            # Call regex method directly
            headings = analyzer._extract_headings_regex()

            self.assertEqual(len(headings), 3)
            self.assertEqual(headings[0]['level'], 1)
            self.assertEqual(headings[1]['level'], 2)
            self.assertEqual(headings[2]['level'], 3)

        finally:
            os.unlink(path)
            os.rmdir(temp_dir)


class TestMarkdownLinkHelpers(unittest.TestCase):
    """Test refactored link helper functions."""

    def create_temp_markdown(self, content: str) -> str:
        """Helper: Create temp markdown file."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "test.md")
        with open(path, 'w') as f:
            f.write(content)
        return path

    def test_extract_link_text_helper(self):
        """Test _extract_link_text helper extracts text from link nodes."""
        content = "[Example Link](https://example.com)"
        path = self.create_temp_markdown(content)

        try:
            analyzer = MarkdownAnalyzer(path)
            links = analyzer._extract_links()

            # Verify link was extracted
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0]['text'], 'Example Link')

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_extract_link_destination_helper(self):
        """Test _extract_link_destination helper extracts URLs from link nodes."""
        content = "[Example](https://example.com/path/to/page)"
        path = self.create_temp_markdown(content)

        try:
            analyzer = MarkdownAnalyzer(path)
            links = analyzer._extract_links()

            # Verify URL was extracted correctly
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0]['url'], 'https://example.com/path/to/page')

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_build_link_info_helper_with_external_link(self):
        """Test _build_link_info helper builds metadata for external links."""
        content = "[External](https://example.com)"
        path = self.create_temp_markdown(content)

        try:
            analyzer = MarkdownAnalyzer(path)
            links = analyzer._extract_links()

            # Verify link info includes metadata
            self.assertEqual(len(links), 1)
            link = links[0]
            self.assertEqual(link['type'], 'external')
            self.assertIn('line', link)
            self.assertIn('column', link)
            self.assertEqual(link['url'], 'https://example.com')

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_build_link_info_helper_with_internal_link(self):
        """Test _build_link_info helper builds metadata for internal links."""
        content = "[Internal](#section)"
        path = self.create_temp_markdown(content)

        try:
            analyzer = MarkdownAnalyzer(path)
            links = analyzer._extract_links()

            # Verify link info includes metadata
            self.assertEqual(len(links), 1)
            link = links[0]
            self.assertEqual(link['type'], 'internal')
            self.assertEqual(link['url'], '#section')

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_link_matches_filters_with_type_filter(self):
        """Test _link_matches_filters helper filters by link type."""
        content = """
[External Link](https://example.com)
[Internal Link](#section)
[Email](mailto:test@example.com)
"""
        path = self.create_temp_markdown(content)

        try:
            analyzer = MarkdownAnalyzer(path)

            # Filter for external links only
            external_links = analyzer._extract_links(link_type='external')
            self.assertEqual(len(external_links), 1)
            self.assertEqual(external_links[0]['type'], 'external')

            # Filter for internal links only
            internal_links = analyzer._extract_links(link_type='internal')
            self.assertEqual(len(internal_links), 1)
            self.assertEqual(internal_links[0]['type'], 'internal')

            # Filter for email links only
            email_links = analyzer._extract_links(link_type='email')
            self.assertEqual(len(email_links), 1)
            self.assertEqual(email_links[0]['type'], 'email')

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_link_matches_filters_with_domain_filter(self):
        """Test _link_matches_filters helper filters by domain."""
        content = """
[Example](https://example.com/page)
[GitHub](https://github.com/user/repo)
[Internal](#section)
"""
        path = self.create_temp_markdown(content)

        try:
            analyzer = MarkdownAnalyzer(path)

            # Filter for example.com domain
            example_links = analyzer._extract_links(domain='example.com')
            self.assertEqual(len(example_links), 1)
            self.assertIn('example.com', example_links[0]['url'])

            # Filter for github.com domain
            github_links = analyzer._extract_links(domain='github.com')
            self.assertEqual(len(github_links), 1)
            self.assertIn('github.com', github_links[0]['url'])

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_link_matches_filters_with_combined_filters(self):
        """Test _link_matches_filters with both type and domain filters."""
        content = """
[Example](https://example.com/page)
[GitHub](https://github.com/user/repo)
[Internal](#section)
"""
        path = self.create_temp_markdown(content)

        try:
            analyzer = MarkdownAnalyzer(path)

            # Filter for external links from github.com
            github_links = analyzer._extract_links(
                link_type='external',
                domain='github.com'
            )
            self.assertEqual(len(github_links), 1)
            self.assertEqual(github_links[0]['type'], 'external')
            self.assertIn('github.com', github_links[0]['url'])

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_link_helpers_preserve_line_numbers(self):
        """Test that refactored helpers preserve accurate line numbers."""
        content = """# Title

[First Link](https://first.com)

Some text here.

[Second Link](https://second.com)
"""
        path = self.create_temp_markdown(content)

        try:
            analyzer = MarkdownAnalyzer(path)
            links = analyzer._extract_links()

            # Verify line numbers are correct
            self.assertEqual(len(links), 2)
            self.assertEqual(links[0]['line'], 3)  # First link on line 3
            self.assertEqual(links[1]['line'], 7)  # Second link on line 7

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_link_helpers_handle_multiple_links_per_line(self):
        """Test that helpers handle multiple links on same line."""
        content = "[First](https://first.com) and [Second](https://second.com)"
        path = self.create_temp_markdown(content)

        try:
            analyzer = MarkdownAnalyzer(path)
            links = analyzer._extract_links()

            # Should extract both links
            self.assertEqual(len(links), 2)
            self.assertEqual(links[0]['url'], 'https://first.com')
            self.assertEqual(links[1]['url'], 'https://second.com')
            # Both should be on same line
            self.assertEqual(links[0]['line'], links[1]['line'])

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))


class TestMarkdownRelatedDocs(unittest.TestCase):
    """Tests for the --related feature that extracts related documents from front matter."""

    def setUp(self):
        """Create a temp directory for test files."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def create_temp_markdown(self, filename: str, content: str) -> str:
        """Create a temp markdown file with given content."""
        path = os.path.join(self.temp_dir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_related_extraction_basic(self):
        """Test basic related document extraction from front matter."""
        # Create a related file
        related_path = self.create_temp_markdown('related.md', '''# Related Doc

## Section 1

Some content.
''')

        # Create main file with related field
        main_content = f'''---
title: Main Doc
related:
  - ./related.md
---

# Main Document

Content here.
'''
        main_path = self.create_temp_markdown('main.md', main_content)

        analyzer = MarkdownAnalyzer(main_path)
        structure = analyzer.get_structure(extract_related=True)

        self.assertIn('related', structure)
        related = structure['related']
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]['path'], './related.md')
        self.assertTrue(related[0]['exists'])
        self.assertIn('Related Doc', related[0]['headings'])

    def test_related_extraction_multiple_fields(self):
        """Test extraction from multiple related fields (related, related_docs, see_also)."""
        # Create related files
        self.create_temp_markdown('doc1.md', '# Doc 1')
        self.create_temp_markdown('doc2.md', '# Doc 2')
        self.create_temp_markdown('doc3.md', '# Doc 3')

        main_content = '''---
title: Main
related:
  - ./doc1.md
related_docs:
  - ./doc2.md
see_also:
  - ./doc3.md
---

# Main
'''
        main_path = self.create_temp_markdown('main.md', main_content)

        analyzer = MarkdownAnalyzer(main_path)
        structure = analyzer.get_structure(extract_related=True)

        related = structure['related']
        self.assertEqual(len(related), 3)
        paths = [r['path'] for r in related]
        self.assertIn('./doc1.md', paths)
        self.assertIn('./doc2.md', paths)
        self.assertIn('./doc3.md', paths)

    def test_related_missing_file(self):
        """Test that missing related files are marked as not found."""
        main_content = '''---
title: Main
related:
  - ./nonexistent.md
---

# Main
'''
        main_path = self.create_temp_markdown('main.md', main_content)

        analyzer = MarkdownAnalyzer(main_path)
        structure = analyzer.get_structure(extract_related=True)

        related = structure['related']
        self.assertEqual(len(related), 1)
        self.assertFalse(related[0]['exists'])
        self.assertEqual(related[0]['headings'], [])

    def test_related_depth_2(self):
        """Test recursive related document extraction with depth=2."""
        # Create chain: main -> doc1 -> doc2
        self.create_temp_markdown('doc2.md', '# Doc 2\n\n## Section')

        doc1_content = '''---
title: Doc 1
related:
  - ./doc2.md
---

# Doc 1
'''
        self.create_temp_markdown('doc1.md', doc1_content)

        main_content = '''---
title: Main
related:
  - ./doc1.md
---

# Main
'''
        main_path = self.create_temp_markdown('main.md', main_content)

        analyzer = MarkdownAnalyzer(main_path)
        structure = analyzer.get_structure(extract_related=True, related_depth=2)

        related = structure['related']
        self.assertEqual(len(related), 1)

        # Check that doc1's related docs are included
        doc1_related = related[0]['related']
        self.assertEqual(len(doc1_related), 1)
        self.assertEqual(doc1_related[0]['path'], './doc2.md')
        self.assertTrue(doc1_related[0]['exists'])

    def test_related_cycle_detection(self):
        """Test that circular references don't cause infinite loops."""
        # Create cycle: main -> doc1 -> main
        doc1_content = '''---
title: Doc 1
related:
  - ./main.md
---

# Doc 1
'''
        self.create_temp_markdown('doc1.md', doc1_content)

        main_content = '''---
title: Main
related:
  - ./doc1.md
---

# Main
'''
        main_path = self.create_temp_markdown('main.md', main_content)

        analyzer = MarkdownAnalyzer(main_path)
        # This should complete without infinite loop
        structure = analyzer.get_structure(extract_related=True, related_depth=2)

        related = structure['related']
        self.assertEqual(len(related), 1)
        # doc1's related should not include main again (cycle detected)

    def test_related_no_frontmatter(self):
        """Test that files without front matter return empty related list."""
        main_content = '''# Main Document

No front matter here.
'''
        main_path = self.create_temp_markdown('main.md', main_content)

        analyzer = MarkdownAnalyzer(main_path)
        structure = analyzer.get_structure(extract_related=True)

        self.assertIn('related', structure)
        self.assertEqual(structure['related'], [])

    def test_related_skips_urls(self):
        """Test that URLs are skipped in related docs."""
        main_content = '''---
title: Main
related:
  - https://example.com/doc.md
  - ./local.md
---

# Main
'''
        self.create_temp_markdown('local.md', '# Local')
        main_path = self.create_temp_markdown('main.md', main_content)

        analyzer = MarkdownAnalyzer(main_path)
        structure = analyzer.get_structure(extract_related=True)

        related = structure['related']
        # Should only have the local file, not the URL
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]['path'], './local.md')

    def test_related_skips_non_markdown(self):
        """Test that non-markdown files are skipped."""
        self.create_temp_markdown('doc.txt', 'Not markdown')  # Wrong extension

        main_content = '''---
title: Main
related:
  - ./doc.txt
---

# Main
'''
        main_path = self.create_temp_markdown('main.md', main_content)

        analyzer = MarkdownAnalyzer(main_path)
        structure = analyzer.get_structure(extract_related=True)

        # .txt file should be skipped entirely
        self.assertEqual(structure['related'], [])

    def test_related_depth_3(self):
        """Test related document extraction at depth 3."""
        # Create chain: main -> doc1 -> doc2 -> doc3
        doc3_content = '''---
title: Doc 3
---

# Doc 3
## Final Level
'''
        self.create_temp_markdown('doc3.md', doc3_content)

        doc2_content = '''---
title: Doc 2
related:
  - ./doc3.md
---

# Doc 2
## Second Level
'''
        self.create_temp_markdown('doc2.md', doc2_content)

        doc1_content = '''---
title: Doc 1
related:
  - ./doc2.md
---

# Doc 1
## First Level
'''
        self.create_temp_markdown('doc1.md', doc1_content)

        main_content = '''---
title: Main
related:
  - ./doc1.md
---

# Main Document
'''
        main_path = self.create_temp_markdown('main.md', main_content)

        analyzer = MarkdownAnalyzer(main_path)
        structure = analyzer.get_structure(extract_related=True, related_depth=3)

        # Verify chain: main -> doc1 -> doc2 -> doc3
        related = structure['related']
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]['path'], './doc1.md')

        # doc1's related (depth 2)
        doc1_related = related[0]['related']
        self.assertEqual(len(doc1_related), 1)
        self.assertEqual(doc1_related[0]['path'], './doc2.md')

        # doc2's related (depth 3)
        doc2_related = doc1_related[0]['related']
        self.assertEqual(len(doc2_related), 1)
        self.assertEqual(doc2_related[0]['path'], './doc3.md')

    def test_related_depth_0_unlimited(self):
        """Test that depth=0 means unlimited traversal (until exhausted)."""
        # Create chain: main -> doc1 -> doc2 -> doc3 -> doc4
        doc4_content = '''---
title: Doc 4
---

# Doc 4
'''
        self.create_temp_markdown('doc4.md', doc4_content)

        doc3_content = '''---
title: Doc 3
related:
  - ./doc4.md
---

# Doc 3
'''
        self.create_temp_markdown('doc3.md', doc3_content)

        doc2_content = '''---
title: Doc 2
related:
  - ./doc3.md
---

# Doc 2
'''
        self.create_temp_markdown('doc2.md', doc2_content)

        doc1_content = '''---
title: Doc 1
related:
  - ./doc2.md
---

# Doc 1
'''
        self.create_temp_markdown('doc1.md', doc1_content)

        main_content = '''---
title: Main
related:
  - ./doc1.md
---

# Main
'''
        main_path = self.create_temp_markdown('main.md', main_content)

        analyzer = MarkdownAnalyzer(main_path)
        # depth=0 should follow all links
        structure = analyzer.get_structure(extract_related=True, related_depth=0)

        # Traverse the chain
        related = structure['related']
        self.assertEqual(len(related), 1)

        # Follow to doc4 (4 levels deep)
        level1 = related[0]['related']
        self.assertEqual(len(level1), 1)

        level2 = level1[0]['related']
        self.assertEqual(len(level2), 1)

        level3 = level2[0]['related']
        self.assertEqual(len(level3), 1)
        self.assertEqual(level3[0]['path'], './doc4.md')

    def test_related_limit_stops_at_n(self):
        """Test that related_limit stops traversal at N files."""
        # Create many interconnected docs
        for i in range(10):
            next_doc = f'./doc{i+1}.md' if i < 9 else None
            related_line = f'related:\n  - {next_doc}' if next_doc else ''
            content = f'''---
title: Doc {i}
{related_line}
---

# Doc {i}
'''
            self.create_temp_markdown(f'doc{i}.md', content)

        main_content = '''---
title: Main
related:
  - ./doc0.md
---

# Main
'''
        main_path = self.create_temp_markdown('main.md', main_content)

        analyzer = MarkdownAnalyzer(main_path)
        # Limit to 3 files
        structure = analyzer.get_structure(extract_related=True, related_depth=0, related_limit=3)

        # Count total files found (should be <= 3)
        def count_related(items):
            total = len(items)
            for item in items:
                total += count_related(item.get('related', []))
            return total

        total = count_related(structure['related'])
        self.assertLessEqual(total, 3)

    def test_related_dict_format_entries(self):
        """Test that structured dict entries in related field are handled.

        Some docs use dict format like:
            related:
              - uri: doc://path/to/doc.md
                title: Document Title
                description: Some description
        """
        # Create related doc
        related_content = '''---
title: Related Doc
---

# Related Doc

Some content.
'''
        self.create_temp_markdown('related_doc.md', related_content)

        # Main doc with dict-format related entries
        main_content = '''---
title: Main Doc
related:
  - uri: ./related_doc.md
    title: Related Document
    description: A related document
  - path: ./missing.md
    title: Missing Doc
  - href: ./related_doc.md
    title: Another reference
---

# Main Doc

Content here.
'''
        main_path = self.create_temp_markdown('main.md', main_content)

        analyzer = MarkdownAnalyzer(main_path)
        structure = analyzer.get_structure(extract_related=True)

        # Should extract 3 related entries (2 pointing to same file, 1 missing)
        self.assertEqual(len(structure['related']), 3)

        # First entry (uri field) - exists
        self.assertEqual(structure['related'][0]['path'], './related_doc.md')
        self.assertTrue(structure['related'][0]['exists'])

        # Second entry (path field) - missing
        self.assertEqual(structure['related'][1]['path'], './missing.md')
        self.assertFalse(structure['related'][1]['exists'])

        # Third entry (href field) - exists
        self.assertEqual(structure['related'][2]['path'], './related_doc.md')
        self.assertTrue(structure['related'][2]['exists'])

    def test_related_dict_format_with_doc_prefix(self):
        """Test that doc:// prefixes in uri fields are stripped."""
        # Create related doc
        related_content = '''---
title: Infrastructure Doc
---

# Infrastructure Doc
'''
        self.create_temp_markdown('infrastructure.md', related_content)

        # Main doc with doc:// prefixed URIs
        main_content = '''---
title: Main Doc
related:
  - uri: doc://infrastructure.md
    title: Infrastructure
    relationship: core
---

# Main Doc
'''
        main_path = self.create_temp_markdown('main.md', main_content)

        analyzer = MarkdownAnalyzer(main_path)
        structure = analyzer.get_structure(extract_related=True)

        # doc:// prefix should be stripped, path should be 'infrastructure.md'
        self.assertEqual(len(structure['related']), 1)
        self.assertEqual(structure['related'][0]['path'], 'infrastructure.md')
        self.assertTrue(structure['related'][0]['exists'])


if __name__ == '__main__':
    unittest.main()
