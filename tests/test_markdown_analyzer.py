"""Tests for Markdown analyzer."""

import unittest
import tempfile
import os
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


if __name__ == '__main__':
    unittest.main()
