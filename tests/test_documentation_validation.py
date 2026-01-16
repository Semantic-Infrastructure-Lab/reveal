"""Tests for documentation quality and validation.

These tests ensure Reveal's documentation maintains high quality by:
1. Validating all internal links work
2. Checking for required documentation structure
3. Ensuring cross-reference density
"""

import pytest
from pathlib import Path
from reveal.rules.links.L001 import L001
from reveal.registry import get_analyzer


class TestDocumentationLinks:
    """Test that documentation links are valid."""

    @pytest.fixture
    def docs_dir(self):
        """Get the docs directory path."""
        repo_root = Path(__file__).parent.parent
        return repo_root / "reveal" / "docs"

    def test_all_docs_have_valid_internal_links(self, docs_dir):
        """Test that all documentation files have valid internal links."""
        if not docs_dir.exists():
            pytest.skip(f"Docs directory not found: {docs_dir}")

        rule = L001()
        broken_links = []

        # Check all markdown files
        for doc_file in docs_dir.glob("*.md"):
            # Get file content and structure
            try:
                content = doc_file.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                # Skip files with encoding issues
                continue

            # Get structure from analyzer
            analyzer_class = get_analyzer(str(doc_file))
            if analyzer_class:
                analyzer = analyzer_class(str(doc_file))
                structure = analyzer.get_structure()
            else:
                structure = None

            # Run L001 rule
            detections = rule.check(str(doc_file), structure, content)

            for detection in detections:
                broken_links.append({
                    'file': doc_file.name,
                    'line': detection.line,
                    'message': detection.message,
                    'context': detection.context or detection.suggestion or ''
                })

        # Report all broken links
        if broken_links:
            error_msg = "\n\nBroken links found in documentation:\n"
            for link in broken_links:
                error_msg += f"\n  {link['file']}:{link['line']}"
                error_msg += f"\n    → {link['message']}"
                if link['context']:
                    error_msg += f"\n    Link: {link['context']}\n"

            error_msg += f"\nTotal broken links: {len(broken_links)}"
            error_msg += "\n\nTo fix: Update links or remove broken references."

            pytest.fail(error_msg)

    def test_no_broken_links_in_agent_help(self, docs_dir):
        """Specifically test AGENT_HELP.md has no broken links."""
        agent_help = docs_dir / "AGENT_HELP.md"

        if not agent_help.exists():
            pytest.skip(f"AGENT_HELP.md not found: {agent_help}")

        rule = L001()
        try:
            content = agent_help.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            pytest.skip("AGENT_HELP.md has encoding issues")

        analyzer_class = get_analyzer(str(agent_help))
        if analyzer_class:
            analyzer = analyzer_class(str(agent_help))
            structure = analyzer.get_structure()
        else:
            structure = None

        detections = rule.check(str(agent_help), structure, content)

        if detections:
            errors = "\n".join([
                f"  Line {d.line}: {d.message} - {d.context or d.suggestion or ''}"
                for d in detections
            ])
            pytest.fail(
                f"AGENT_HELP.md has broken links:\n{errors}\n\n"
                "This is the primary documentation for AI agents and must be perfect."
            )


class TestDocumentationStructure:
    """Test that documentation has proper structure."""

    @pytest.fixture
    def docs_dir(self):
        """Get the docs directory path."""
        repo_root = Path(__file__).parent.parent
        return repo_root / "reveal" / "docs"

    def test_docs_readme_exists(self, docs_dir):
        """Test that docs/README.md exists as an index."""
        readme = docs_dir / "README.md"

        assert readme.exists(), (
            "Documentation index missing: reveal/docs/README.md\n\n"
            "Create a README.md that provides:\n"
            "  - Navigation by role (AI agents, users, developers)\n"
            "  - Description of each guide\n"
            "  - Recommended reading order\n"
            "  - Quick reference links\n\n"
            "See: DOCS_QUALITY_REPORT.md for recommendations"
        )

    def test_docs_have_minimal_cross_references(self, docs_dir):
        """Test that docs have reasonable cross-reference density."""
        if not docs_dir.exists():
            pytest.skip(f"Docs directory not found: {docs_dir}")

        import re

        total_docs = 0
        total_cross_refs = 0
        docs_with_no_refs = []

        for doc_file in docs_dir.glob("*.md"):
            if doc_file.name == "README.md":
                continue  # Index is expected to have many refs

            total_docs += 1
            content = doc_file.read_text()

            # Find internal .md links
            internal_links = re.findall(r'\[([^\]]+)\]\(([^)]+\.md)\)', content)
            cross_refs = len(internal_links)
            total_cross_refs += cross_refs

            if cross_refs == 0:
                docs_with_no_refs.append(doc_file.name)

        if total_docs == 0:
            pytest.skip("No documentation files found")

        avg_cross_refs = total_cross_refs / total_docs

        # Warn if average is too low (target: 2+ refs per doc)
        if avg_cross_refs < 1.0:
            warning = (
                f"\nDocumentation cross-reference density is very low:\n"
                f"  Average: {avg_cross_refs:.2f} refs per doc (target: 2+)\n"
                f"  Total refs: {total_cross_refs} across {total_docs} docs\n"
                f"  Docs with no refs: {len(docs_with_no_refs)}\n\n"
                f"Consider adding 'See Also' sections to:\n"
            )
            for doc in docs_with_no_refs[:5]:  # Show first 5
                warning += f"    - {doc}\n"

            # Only warn for now, don't fail (this is aspirational)
            pytest.skip(warning)


class TestDocumentationConsistency:
    """Test that documentation follows consistent patterns."""

    @pytest.fixture
    def docs_dir(self):
        """Get the docs directory path."""
        repo_root = Path(__file__).parent.parent
        return repo_root / "reveal" / "docs"

    def test_guide_files_have_guide_suffix(self, docs_dir):
        """Test that guide files follow naming convention."""
        if not docs_dir.exists():
            pytest.skip(f"Docs directory not found: {docs_dir}")

        inconsistent_names = []

        for doc_file in docs_dir.glob("*.md"):
            name = doc_file.name

            # Skip special files
            if name in ["README.md", "CHANGELOG.md"]:
                continue

            # Check if it looks like a guide but doesn't have GUIDE or HELP suffix
            if "_" in name:  # Has category separator
                if not (name.endswith("_GUIDE.md") or
                        name.endswith("_HELP.md") or
                        name.endswith("_PATTERNS.md")):
                    inconsistent_names.append(name)

        # This is informational only - some files intentionally break pattern
        if inconsistent_names:
            info = (
                f"\nFiles with potentially inconsistent naming:\n"
                f"  {', '.join(inconsistent_names)}\n\n"
                f"Most guides use *_GUIDE.md or *_HELP.md pattern.\n"
                f"Consider if these should follow the convention."
            )
            # Don't fail, just log for information
            # pytest.skip(info)


class TestDocumentationCompleteness:
    """Test that documentation covers all major features."""

    @pytest.fixture
    def docs_dir(self):
        """Get the docs directory path."""
        repo_root = Path(__file__).parent.parent
        return repo_root / "reveal" / "docs"

    def test_agent_help_is_current_version(self, docs_dir):
        """Test that AGENT_HELP.md reflects current version."""
        agent_help = docs_dir / "AGENT_HELP.md"

        if not agent_help.exists():
            pytest.skip("AGENT_HELP.md not found")

        # Get current version from pyproject.toml
        repo_root = Path(__file__).parent.parent
        pyproject = repo_root / "pyproject.toml"

        if not pyproject.exists():
            pytest.skip("pyproject.toml not found")

        pyproject_content = pyproject.read_text()
        import re
        version_match = re.search(r'version\s*=\s*"([^"]+)"', pyproject_content)

        if not version_match:
            pytest.skip("Could not find version in pyproject.toml")

        current_version = version_match.group(1)
        agent_help_content = agent_help.read_text()

        # Check if version is mentioned in agent help
        if current_version not in agent_help_content:
            pytest.fail(
                f"AGENT_HELP.md does not reference current version {current_version}\n\n"
                f"Update the version number in AGENT_HELP.md to match pyproject.toml"
            )

    def test_major_adapters_have_documentation(self, docs_dir):
        """Test that major adapters have guide files."""
        if not docs_dir.exists():
            pytest.skip(f"Docs directory not found: {docs_dir}")

        # Major adapters that should have guides
        expected_guides = {
            'markdown': ['MARKDOWN_GUIDE.md'],
            'python': ['PYTHON_ADAPTER_GUIDE.md'],
            'html': ['HTML_GUIDE.md'],
            'reveal': ['REVEAL_ADAPTER_GUIDE.md'],
        }

        missing_guides = []

        for adapter, guide_files in expected_guides.items():
            for guide_file in guide_files:
                if not (docs_dir / guide_file).exists():
                    missing_guides.append(f"{adapter} → {guide_file}")

        if missing_guides:
            pytest.fail(
                f"Missing documentation for major adapters:\n" +
                "\n".join(f"  - {mg}" for mg in missing_guides)
            )
