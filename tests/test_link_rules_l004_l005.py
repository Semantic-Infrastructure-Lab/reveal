"""Tests for link validation rules L004 and L005.

L004: Documentation directory missing index
L005: Documentation has low cross-reference density
"""

import pytest
import tempfile
import os
from pathlib import Path

from reveal.rules.links.L004 import L004
from reveal.rules.links.L005 import L005


class TestL004:
    """Test L004: Documentation directory missing index."""

    def test_l004_initialization(self):
        """L004 rule initializes correctly."""
        rule = L004()
        assert rule.code == "L004"
        assert "index" in rule.message.lower() or "missing" in rule.message.lower()
        assert '.md' in rule.file_patterns

    def test_l004_skips_non_docs_directory(self):
        """L004 doesn't check files outside docs/ directories."""
        rule = L004()
        detections = rule.check("/some/path/src/file.md", None, "# Content")
        assert len(detections) == 0

    def test_l004_skips_docs_with_readme(self):
        """L004 passes when docs/ has README.md."""
        rule = L004()

        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = Path(tmpdir) / "docs"
            docs_dir.mkdir()

            # Create README.md
            readme = docs_dir / "README.md"
            readme.write_text("# Documentation Index\n")

            # Create another md file to check
            guide = docs_dir / "guide.md"
            guide.write_text("# Guide\n")

            detections = rule.check(str(guide), None, "# Guide\n")
            assert len(detections) == 0

    def test_l004_skips_docs_with_index(self):
        """L004 passes when docs/ has INDEX.md."""
        rule = L004()

        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = Path(tmpdir) / "docs"
            docs_dir.mkdir()

            # Create INDEX.md instead of README.md
            index = docs_dir / "INDEX.md"
            index.write_text("# Documentation Index\n")

            # Create another md file to check
            guide = docs_dir / "guide.md"
            guide.write_text("# Guide\n")

            detections = rule.check(str(guide), None, "# Guide\n")
            assert len(detections) == 0

    def test_l004_detects_missing_index(self):
        """L004 detects docs/ without README.md or INDEX.md."""
        rule = L004()

        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = Path(tmpdir) / "docs"
            docs_dir.mkdir()

            # Create only a guide, no README or INDEX
            guide = docs_dir / "guide.md"
            guide.write_text("# Guide\n")

            detections = rule.check(str(guide), None, "# Guide\n")
            # Should detect missing index
            assert len(detections) == 1
            assert "index" in detections[0].message.lower() or "missing" in detections[0].message.lower()

    def test_l004_suggestion_is_helpful(self):
        """L004 provides helpful suggestion for adding index."""
        rule = L004()

        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = Path(tmpdir) / "docs"
            docs_dir.mkdir()

            guide = docs_dir / "guide.md"
            guide.write_text("# Guide\n")

            detections = rule.check(str(guide), None, "# Guide\n")
            if detections:
                suggestion = detections[0].suggestion
                assert "README.md" in suggestion
                assert "Navigation" in suggestion or "entry point" in suggestion.lower()


class TestL005:
    """Test L005: Documentation cross-reference density checker."""

    def test_l005_initialization(self):
        """L005 rule initializes correctly."""
        rule = L005()
        assert rule.code == "L005"
        assert "cross-reference" in rule.message.lower() or "density" in rule.message.lower()
        assert '.md' in rule.file_patterns

    def test_l005_skips_non_docs_directory(self):
        """L005 doesn't check files outside docs/ directories."""
        rule = L005()
        content = "# Guide\nNo links here."
        detections = rule.check("/some/path/src/file.md", None, content)
        assert len(detections) == 0

    def test_l005_skips_readme_files(self):
        """L005 skips README.md (index files expected to have structure)."""
        rule = L005()
        content = "# Documentation\nNo cross-references needed in index."
        detections = rule.check("/project/docs/README.md", None, content)
        assert len(detections) == 0

    def test_l005_skips_changelog(self):
        """L005 skips CHANGELOG.md (not expected to have cross-refs)."""
        rule = L005()
        content = "# Changelog\n## v1.0.0\n- Initial release"
        detections = rule.check("/project/docs/CHANGELOG.md", None, content)
        assert len(detections) == 0

    def test_l005_passes_with_sufficient_refs(self):
        """L005 passes when doc has 2+ cross-references."""
        rule = L005()
        content = """# Guide

This guide covers usage. See [Getting Started](./GETTING_STARTED.md) for setup.

For advanced usage, check [Advanced Guide](./ADVANCED.md).

Also see [FAQ](./FAQ.md) for common questions.
"""
        detections = rule.check("/project/docs/GUIDE.md", None, content)
        assert len(detections) == 0

    def test_l005_detects_low_cross_refs(self):
        """L005 detects docs with insufficient cross-references."""
        rule = L005()
        content = """# Standalone Guide

This guide has no links to other documentation.
Just standalone content with no cross-references.
"""
        detections = rule.check("/project/docs/STANDALONE.md", None, content)
        assert len(detections) == 1
        assert "cross-reference" in detections[0].message.lower()

    def test_l005_counts_internal_links_only(self):
        """L005 only counts internal .md links, not external."""
        rule = L005()
        content = """# Guide

External link: [Python](https://python.org)
Another external: [MDN](https://developer.mozilla.org)
HTTP link to md: [External MD](https://example.com/doc.md)

Only one internal link: [Setup](./SETUP.md)
"""
        # Only 1 internal link, minimum is 2
        detections = rule.check("/project/docs/GUIDE.md", None, content)
        assert len(detections) == 1

    def test_l005_excludes_self_references(self):
        """L005 doesn't count self-references."""
        rule = L005()
        content = """# Guide

Link to self: [This Guide](./GUIDE.md)
Another self: [Guide](./GUIDE.md)
One real ref: [Other](./OTHER.md)
"""
        # Self-references don't count, so only 1 real ref
        detections = rule.check("/project/docs/GUIDE.md", None, content)
        assert len(detections) == 1

    def test_l005_count_internal_md_links_method(self):
        """Test _count_internal_md_links helper method."""
        rule = L005()
        current_file = Path("/project/docs/GUIDE.md")

        # Test with various link types
        content = """
[Internal](./other.md)
[Another Internal](../docs/another.md)
[External](https://example.com)
[External MD](https://example.com/doc.md)
[Self](./GUIDE.md)
"""
        count = rule._count_internal_md_links(content, current_file)
        assert count == 2  # other.md and another.md, not external or self

    def test_l005_suggestion_includes_see_also(self):
        """L005 suggestion recommends adding See Also section."""
        rule = L005()
        content = "# Guide\nNo cross-references."

        detections = rule.check("/project/docs/GUIDE.md", None, content)
        if detections:
            suggestion = detections[0].suggestion
            assert "See Also" in suggestion or "Related" in suggestion


class TestL004L005Integration:
    """Integration tests for L004 and L005 together."""

    def test_both_rules_work_on_same_file(self):
        """Both L004 and L005 can check the same documentation file."""
        l004 = L004()
        l005 = L005()

        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = Path(tmpdir) / "docs"
            docs_dir.mkdir()

            # Create guide without README (L004 violation)
            # and without cross-refs (L005 violation)
            guide = docs_dir / "guide.md"
            guide.write_text("# Guide\nJust content, no links.")

            # L004 should detect missing index
            l004_detections = l004.check(str(guide), None, "# Guide\nJust content.")

            # L005 should detect low cross-refs
            l005_detections = l005.check(str(guide), None, "# Guide\nJust content.")

            # Both should find issues
            assert len(l004_detections) >= 1  # Missing index
            assert len(l005_detections) >= 1  # Low cross-refs
