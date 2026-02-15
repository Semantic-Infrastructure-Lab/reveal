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

    def test_l005_includes_suggestions_when_available(self, tmp_path):
        """L005 includes specific doc suggestions when related files exist."""
        rule = L005()

        # Create a docs directory with related files
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create related documentation that should be suggested
        (docs_dir / "ANTI_PATTERNS.md").write_text("# Anti Patterns Guide")
        (docs_dir / "COOL_TRICKS.md").write_text("# Cool Tricks")

        # Create the file we're checking (contains keywords that trigger suggestions)
        guide_file = docs_dir / "AGENT_HELP.md"
        content = "# Agent Help\nThis guide covers AI agents and LLMs.\nNo cross-references yet."

        detections = rule.check(str(guide_file), None, content)

        # Should detect low cross-refs and include suggestions
        assert len(detections) == 1
        suggestion = detections[0].suggestion
        # Should suggest the related docs that exist
        assert "ANTI_PATTERNS.md" in suggestion or "COOL_TRICKS.md" in suggestion
        assert "Consider adding references to:" in suggestion

    def test_l005_excludes_current_file_from_suggestions(self, tmp_path):
        """L005 doesn't suggest the current file as a reference."""
        rule = L005()

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create the file we're checking
        guide_file = docs_dir / "ANTI_PATTERNS.md"

        # Create related files, including one with same name (shouldn't be suggested)
        (docs_dir / "AGENT_HELP.md").write_text("# Agent Help")
        (docs_dir / "COOL_TRICKS.md").write_text("# Cool Tricks")

        # Content with keywords that would trigger suggestions
        content = "# Anti Patterns\nCommon anti-patterns to avoid in AI agents.\nNo cross-references yet."

        detections = rule.check(str(guide_file), None, content)

        if detections:
            suggestion = detections[0].suggestion
            # Should NOT suggest itself (ANTI_PATTERNS.md)
            # The suggestion should include other files but not ANTI_PATTERNS.md
            lines = suggestion.split('\n')
            for line in lines:
                if 'ANTI_PATTERNS.md' in line and line.strip().startswith('- ['):
                    # Found a suggestion line with current file name - this is wrong
                    assert False, f"Should not suggest current file, but found: {line}"

    def test_l005_removes_duplicate_suggestions(self, tmp_path):
        """L005 removes duplicate suggestions while preserving order."""
        rule = L005()

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create files that multiple patterns would suggest
        (docs_dir / "AGENT_HELP.md").write_text("# Agent Help")
        (docs_dir / "COOL_TRICKS.md").write_text("# Cool Tricks")
        (docs_dir / "ANTI_PATTERNS.md").write_text("# Anti Patterns")

        guide_file = docs_dir / "MIXED_GUIDE.md"

        # Content with keywords from multiple patterns that suggest the same docs
        content = """# Mixed Guide
This is a guide about agents and AI.
It also covers anti-patterns and things to avoid.
Tutorial on best practices.
"""

        detections = rule.check(str(guide_file), None, content)

        if detections:
            suggestion = detections[0].suggestion
            # Extract just the "Consider adding references to:" section
            if "Consider adding references to:" in suggestion:
                start = suggestion.index("Consider adding references to:")
                # Find the end of the suggestion list (before "Add a 'See Also'" section)
                end = suggestion.index("Add a 'See Also'") if "Add a 'See Also'" in suggestion else len(suggestion)
                suggestion_section = suggestion[start:end]

                # Count how many times each file appears in the actual suggestions
                # (not in the example template)
                for filename in ["AGENT_HELP.md", "COOL_TRICKS.md", "ANTI_PATTERNS.md"]:
                    # Count the lines that start with "  - [filename]"
                    pattern = f"- [{filename}]"
                    count = suggestion_section.count(pattern)
                    assert count <= 1, f"{filename} appears {count} times in suggestions (expected <= 1)"


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
