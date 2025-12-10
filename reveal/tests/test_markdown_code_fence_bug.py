"""Test for markdown code fence bug.

Bug: Comments inside code fences are incorrectly detected as headings.
"""

import unittest
import tempfile
from pathlib import Path
from reveal.analyzers.markdown import MarkdownAnalyzer


class TestMarkdownCodeFenceBug(unittest.TestCase):
    """Test that # comments inside code fences are NOT detected as headings."""

    def test_code_fence_comments_not_headings(self):
        """# comments inside code blocks should NOT be detected as headings."""
        # Create test markdown with heading in code fence
        test_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.md', delete=False
        )

        test_file.write("# Real Heading\n\n")
        test_file.write("```bash\n")
        test_file.write("# This comment should NOT be a heading\n")
        test_file.write("```\n")
        test_file.close()

        analyzer = MarkdownAnalyzer(test_file.name)
        structure = analyzer.get_structure()

        # Should only find 1 heading (the real one), not 2
        self.assertEqual(len(structure['headings']), 1,
                        "Found more than 1 heading - code fence comments are being detected!")
        self.assertEqual(structure['headings'][0]['name'], 'Real Heading')

        Path(test_file.name).unlink(missing_ok=True)

    def test_multiple_code_fence_comments(self):
        """Multiple # comments in code fences should all be ignored."""
        test_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.md', delete=False
        )

        test_file.write("# Heading 1\n\n")
        test_file.write("```python\n")
        test_file.write("# Comment in Python\n")
        test_file.write("def foo():\n")
        test_file.write("    # Another comment\n")
        test_file.write("    pass\n")
        test_file.write("```\n\n")
        test_file.write("# Heading 2\n\n")
        test_file.write("```bash\n")
        test_file.write("# Bash comment\n")
        test_file.write("echo 'hello'\n")
        test_file.write("```\n")
        test_file.close()

        analyzer = MarkdownAnalyzer(test_file.name)
        structure = analyzer.get_structure()

        # Should only find 2 real headings
        self.assertEqual(len(structure['headings']), 2,
                        "Code fence comments are being detected as headings!")
        self.assertEqual(structure['headings'][0]['name'], 'Heading 1')
        self.assertEqual(structure['headings'][1]['name'], 'Heading 2')

        Path(test_file.name).unlink(missing_ok=True)

    def test_unclosed_fence_edge_case(self):
        """Test behavior with unclosed code fence (malformed markdown)."""
        test_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.md', delete=False
        )

        test_file.write("# Real Heading\n\n")
        test_file.write("```bash\n")
        test_file.write("# This fence is never closed\n")
        test_file.write("# So everything after is technically in a code block\n")
        test_file.close()

        analyzer = MarkdownAnalyzer(test_file.name)
        structure = analyzer.get_structure()

        # Should only find 1 heading (everything else is in unclosed fence)
        self.assertEqual(len(structure['headings']), 1,
                        "Comments in unclosed fence detected as headings!")

        Path(test_file.name).unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
