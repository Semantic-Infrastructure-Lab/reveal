"""Extended tests for V009: Documentation cross-reference validation.

These tests complement the existing tests in test_validation_rules.py by focusing
on edge cases and uncovered code paths to boost coverage from 65% to 80%+.
"""

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from reveal.rules.validation.V009 import V009


class TestV009ExtendedCoverage(unittest.TestCase):
    """Extended tests for V009 to cover additional code paths."""

    def setUp(self):
        self.rule = V009()

    def test_extract_links_with_multiple_links(self):
        """Should extract multiple markdown links from content."""
        content = """
# Documentation

See [guide](docs/guide.md) and [reference](docs/ref.md) for details.
Also check [example](../examples/demo.md).
"""
        links = self.rule._extract_markdown_links(content)

        # Should extract 3 internal links
        self.assertEqual(len(links), 3)
        self.assertEqual(links[0]['text'], 'guide')
        self.assertEqual(links[0]['target'], 'docs/guide.md')
        self.assertEqual(links[1]['text'], 'reference')
        self.assertEqual(links[2]['text'], 'example')

    def test_extract_links_filters_external_http(self):
        """Should filter out external http links."""
        content = """
[internal](docs/guide.md)
[external](http://example.com)
[also external](https://example.com)
"""
        links = self.rule._extract_markdown_links(content)

        # Should only extract internal link
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]['target'], 'docs/guide.md')

    def test_extract_links_filters_anchor_only(self):
        """Should filter out anchor-only links."""
        content = """
[section](#heading)
[internal](docs/guide.md)
[anchor with file](guide.md#section)
"""
        links = self.rule._extract_markdown_links(content)

        # Should extract 2 links (not anchor-only #heading)
        self.assertEqual(len(links), 2)
        self.assertNotIn('#heading', [l['target'] for l in links])

    def test_extract_links_filters_mailto(self):
        """Should filter out mailto links."""
        content = """
[email](mailto:test@example.com)
[internal](docs/guide.md)
"""
        links = self.rule._extract_markdown_links(content)

        # Should only extract internal link
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]['target'], 'docs/guide.md')

    def test_process_link_removes_anchor_fragment(self):
        """Should remove anchor fragments from link targets."""
        match = self.rule._extract_markdown_links(
            "[guide](docs/guide.md#section)"
        )[0]

        self.assertEqual(match['target'], 'docs/guide.md#section')
        self.assertEqual(match['target_clean'], 'docs/guide.md')

    def test_process_link_skips_anchor_only_after_split(self):
        """Should skip links that become empty after removing anchor."""
        content = "[anchor](#section-only)"
        links = self.rule._extract_markdown_links(content)

        # Should be filtered out
        self.assertEqual(len(links), 0)

    def test_is_external_link_http(self):
        """Should detect http links as external."""
        self.assertTrue(self.rule._is_external_link('http://example.com'))
        self.assertTrue(self.rule._is_external_link('http://example.com/path'))

    def test_is_external_link_https(self):
        """Should detect https links as external."""
        self.assertTrue(self.rule._is_external_link('https://example.com'))
        self.assertTrue(self.rule._is_external_link('https://example.com/path'))

    def test_is_external_link_relative(self):
        """Should not detect relative links as external."""
        self.assertFalse(self.rule._is_external_link('docs/guide.md'))
        self.assertFalse(self.rule._is_external_link('../other.md'))
        self.assertFalse(self.rule._is_external_link('/absolute/path.md'))

    @patch('reveal.rules.validation.V009.find_reveal_root')
    def test_check_with_broken_link(self, mock_find_root):
        """Should detect broken internal links."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reveal_root = project_root / 'reveal'
            reveal_root.mkdir()

            # Create source file
            source_file = project_root / 'docs' / 'README.md'
            source_file.parent.mkdir(parents=True)
            source_file.write_text('[broken](guide.md)')

            mock_find_root.return_value = reveal_root

            # Check should detect broken link
            detections = self.rule.check(
                file_path='reveal://docs/README.md',
                structure=None,
                content='[broken](guide.md)'
            )

            self.assertEqual(len(detections), 1)
            self.assertIn('Broken link', detections[0].message)
            self.assertIn('guide.md', detections[0].message)

    @patch('reveal.rules.validation.V009.find_reveal_root')
    def test_check_with_valid_link(self, mock_find_root):
        """Should not detect valid internal links."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reveal_root = project_root / 'reveal'
            reveal_root.mkdir()

            # Create source file and target
            source_file = project_root / 'docs' / 'README.md'
            source_file.parent.mkdir(parents=True)
            target_file = source_file.parent / 'guide.md'
            target_file.write_text('# Guide')
            source_file.write_text('[guide](guide.md)')

            mock_find_root.return_value = reveal_root

            # Check should not detect broken link
            detections = self.rule.check(
                file_path='reveal://docs/README.md',
                structure=None,
                content='[guide](guide.md)'
            )

            self.assertEqual(len(detections), 0)

    def test_uri_to_path_invalid_uri(self):
        """Should return None for non-reveal:// URIs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir) / 'reveal'
            project_root = Path(tmpdir)

            result = self.rule._uri_to_path(
                'file:///other.md',
                reveal_root,
                project_root
            )

            self.assertIsNone(result)

    def test_uri_to_path_prefers_project_root(self):
        """Should try project_root before reveal_root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reveal_root = project_root / 'reveal'
            reveal_root.mkdir()

            # Create file in project_root
            project_file = project_root / 'README.md'
            project_file.write_text('# Project')

            # Also create in reveal_root (should prefer project)
            reveal_file = reveal_root / 'README.md'
            reveal_file.write_text('# Reveal')

            result = self.rule._uri_to_path(
                'reveal://README.md',
                reveal_root,
                project_root
            )

            self.assertEqual(result, project_file)

    def test_uri_to_path_falls_back_to_reveal_root(self):
        """Should fall back to reveal_root if not in project_root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reveal_root = project_root / 'reveal'
            reveal_root.mkdir()

            # Only create file in reveal_root
            reveal_file = reveal_root / 'CHANGELOG.md'
            reveal_file.write_text('# Changes')

            result = self.rule._uri_to_path(
                'reveal://CHANGELOG.md',
                reveal_root,
                project_root
            )

            self.assertEqual(result, reveal_file)

    def test_uri_to_path_returns_first_candidate_if_missing(self):
        """Should return first candidate even if file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reveal_root = project_root / 'reveal'
            reveal_root.mkdir()

            # Don't create any files
            result = self.rule._uri_to_path(
                'reveal://nonexistent.md',
                reveal_root,
                project_root
            )

            # Should return project_root candidate (first)
            expected = project_root / 'nonexistent.md'
            self.assertEqual(result, expected)

    def test_resolve_link_absolute_path(self):
        """Should resolve absolute paths from project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            source_file = project_root / 'docs' / 'README.md'
            source_file.parent.mkdir(parents=True)

            # Create target at project root
            target = project_root / 'guide.md'
            target.write_text('# Guide')

            result = self.rule._resolve_link(
                source_file,
                '/guide.md',
                project_root
            )

            self.assertEqual(result, target)

    def test_resolve_link_relative_path(self):
        """Should resolve relative paths from source directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            source_file = project_root / 'docs' / 'README.md'
            source_file.parent.mkdir(parents=True)

            # Create target relative to source
            target = source_file.parent / 'guide.md'
            target.write_text('# Guide')

            result = self.rule._resolve_link(
                source_file,
                'guide.md',
                project_root
            )

            self.assertEqual(result, target)

    def test_resolve_link_parent_relative_path(self):
        """Should resolve ../ relative paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            source_file = project_root / 'docs' / 'api' / 'README.md'
            source_file.parent.mkdir(parents=True)

            # Create target in parent directory
            target = project_root / 'docs' / 'guide.md'
            target.write_text('# Guide')

            result = self.rule._resolve_link(
                source_file,
                '../guide.md',
                project_root
            )

            self.assertEqual(result, target)

    def test_resolve_link_outside_project_root(self):
        """Should return None for links outside project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / 'project'
            project_root.mkdir()
            source_file = project_root / 'README.md'
            source_file.write_text('# Source')

            # Try to resolve link outside project
            result = self.rule._resolve_link(
                source_file,
                '../../outside.md',
                project_root
            )

            self.assertIsNone(result)

    def test_resolve_link_exception_handling(self):
        """Should handle exceptions gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            source_file = project_root / 'README.md'

            # Use invalid link that might cause exception
            result = self.rule._resolve_link(
                source_file,
                '\x00invalid',
                project_root
            )

            self.assertIsNone(result)

    @patch('reveal.rules.validation.V009.find_reveal_root')
    def test_validate_link_calculates_line_number(self, mock_find_root):
        """Should calculate correct line number for broken link."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reveal_root = project_root / 'reveal'
            reveal_root.mkdir()

            # Create source file
            source_file = project_root / 'README.md'
            source_file.write_text("""# Title

First paragraph.

[broken link](nonexistent.md)
""")

            mock_find_root.return_value = reveal_root

            detections = self.rule.check(
                file_path='reveal://README.md',
                structure=None,
                content=source_file.read_text()
            )

            # Should detect on line 5
            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].line, 5)

    @patch('reveal.rules.validation.V009.find_reveal_root')
    def test_get_file_path_context_no_reveal_root(self, mock_find_root):
        """Should return None when reveal root not found."""
        mock_find_root.return_value = None

        detections = self.rule.check(
            file_path='reveal://README.md',
            structure=None,
            content='[link](other.md)'
        )

        # Should return empty (can't validate without reveal root)
        self.assertEqual(len(detections), 0)


if __name__ == '__main__':
    unittest.main()
