"""Comprehensive tests for URL rules (U501, U502).

U501: Insecure GitHub URL detector
U502: URL consistency detector (vs pyproject.toml)
"""

import unittest
import tempfile
import os
from pathlib import Path

from reveal.rules.urls.U501 import U501
from reveal.rules.urls.U502 import U502
from reveal.rules.base import Severity


class TestU501InsecureGitHubURLs(unittest.TestCase):
    """Test U501: Insecure GitHub URL detector."""

    def setUp(self):
        """Set up test fixtures."""
        self.rule = U501()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "U501")
        self.assertEqual(self.rule.severity, Severity.LOW)
        self.assertIn("http://", self.rule.message.lower())
        self.assertIn("github", self.rule.message.lower())

    def test_insecure_github_com_detected(self):
        """Test that http://github.com URLs are detected."""
        content = """
# Documentation

Check out the project: http://github.com/user/repo
"""
        detections = self.rule.check("test.md", None, content)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, "U501")
        self.assertIn("http://github.com/user/repo", detections[0].message)
        self.assertIn("https://github.com/user/repo", detections[0].suggestion)
        self.assertEqual(detections[0].line, 4)  # Line 4: blank, doc header, blank, content

    def test_insecure_www_github_com_detected(self):
        """Test that http://www.github.com URLs are detected."""
        content = "Visit: http://www.github.com/example/project"
        detections = self.rule.check("test.txt", None, content)

        # May match both GITHUB_HTTP_PATTERN and GITHUB_SUBDOMAIN_PATTERN
        self.assertGreaterEqual(len(detections), 1)
        self.assertIn("http://www.github.com", detections[0].message)

    def test_insecure_github_io_detected(self):
        """Test that http://*.github.io URLs are detected."""
        content = "Homepage: http://username.github.io/project"
        detections = self.rule.check("README.md", None, content)

        self.assertEqual(len(detections), 1)
        self.assertIn("http://username.github.io", detections[0].message)
        self.assertIn("https://username.github.io", detections[0].suggestion)

    def test_secure_urls_not_detected(self):
        """Test that https:// URLs are not flagged."""
        content = """
Secure URLs (should pass):
- https://github.com/user/repo
- https://www.github.com/user/repo
- https://username.github.io/project
"""
        detections = self.rule.check("test.md", None, content)

        self.assertEqual(len(detections), 0)

    def test_multiple_insecure_urls_in_one_line(self):
        """Test multiple insecure URLs on same line."""
        content = "Links: http://github.com/user1/repo1 and http://github.com/user2/repo2"
        detections = self.rule.check("test.txt", None, content)

        self.assertEqual(len(detections), 2)
        self.assertIn("user1", detections[0].message)
        self.assertIn("user2", detections[1].message)

    def test_multiple_insecure_urls_different_lines(self):
        """Test multiple insecure URLs on different lines."""
        content = """
Line 1: http://github.com/org/project1
Line 2: http://example.github.io/docs
Line 3: https://github.com/org/project3 (secure, ok)
Line 4: http://github.com/org/project4
"""
        detections = self.rule.check("test.md", None, content)

        self.assertEqual(len(detections), 3)
        # Verify line numbers
        self.assertEqual(detections[0].line, 2)
        self.assertEqual(detections[1].line, 3)
        self.assertEqual(detections[2].line, 5)

    def test_non_github_urls_ignored(self):
        """Test that non-GitHub URLs are ignored."""
        content = """
Not GitHub:
- http://example.com
- http://gitlab.com/user/repo
- http://bitbucket.org/user/repo
"""
        detections = self.rule.check("test.md", None, content)

        self.assertEqual(len(detections), 0)

    def test_column_position_accurate(self):
        """Test that column position is accurate."""
        content = "    Indented link: http://github.com/user/repo here"
        detections = self.rule.check("test.txt", None, content)

        self.assertEqual(len(detections), 1)
        # Column should point to start of URL (1-indexed)
        self.assertGreater(detections[0].column, 0)
        self.assertLess(detections[0].column, len(content))

    def test_url_in_markdown_link(self):
        """Test URLs inside markdown link syntax."""
        content = "[Project](http://github.com/user/repo) documentation"
        detections = self.rule.check("README.md", None, content)

        self.assertEqual(len(detections), 1)
        self.assertIn("http://github.com/user/repo", detections[0].message)

    def test_url_in_code_block(self):
        """Test URLs in code blocks (still detected)."""
        content = """
```bash
git clone http://github.com/user/repo.git
```
"""
        detections = self.rule.check("docs.md", None, content)

        # Should still detect (rule doesn't skip code blocks)
        self.assertEqual(len(detections), 1)

    def test_uri_check_insecure_github_com(self):
        """Test _check_uri with insecure github.com URI."""
        uri = "http://github.com/user/repo"
        detections = self.rule.check(uri, None, "")

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].file_path, uri)
        self.assertEqual(detections[0].line, 0)
        self.assertIn("https://github.com/user/repo", detections[0].suggestion)

    def test_uri_check_insecure_github_io(self):
        """Test _check_uri with insecure github.io URI."""
        uri = "http://username.github.io/project"
        detections = self.rule.check(uri, None, "")

        self.assertEqual(len(detections), 1)
        self.assertIn("https://username.github.io", detections[0].suggestion)

    def test_uri_check_secure_url(self):
        """Test _check_uri with secure https:// URI."""
        uri = "https://github.com/user/repo"
        detections = self.rule.check(uri, None, "")

        self.assertEqual(len(detections), 0)

    def test_uri_check_non_github(self):
        """Test _check_uri with non-GitHub http:// URI."""
        uri = "http://example.com"
        detections = self.rule.check(uri, None, "")

        self.assertEqual(len(detections), 0)

    def test_context_preserved(self):
        """Test that context line is preserved in detection."""
        content = "Check out: http://github.com/user/repo for details"
        detections = self.rule.check("test.md", None, content)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].context, content.strip())

    def test_case_insensitive_matching(self):
        """Test that URL matching is case insensitive."""
        content = """
http://GitHub.com/user/repo
http://GITHUB.COM/user/repo
http://username.GitHub.IO/project
"""
        detections = self.rule.check("test.txt", None, content)

        # All three should be detected
        self.assertEqual(len(detections), 3)

    def test_url_with_query_parameters(self):
        """Test URLs with query parameters."""
        content = "http://github.com/user/repo?tab=readme"
        detections = self.rule.check("test.md", None, content)

        self.assertEqual(len(detections), 1)
        self.assertIn("http://github.com/user/repo", detections[0].message)

    def test_url_with_anchor(self):
        """Test URLs with anchors."""
        content = "http://github.com/user/repo#section"
        detections = self.rule.check("test.md", None, content)

        self.assertEqual(len(detections), 1)
        self.assertIn("http://github.com/user/repo", detections[0].message)

    def test_empty_content(self):
        """Test with empty content."""
        detections = self.rule.check("test.md", None, "")

        self.assertEqual(len(detections), 0)

    def test_file_patterns_all_files(self):
        """Test that rule applies to all file types."""
        self.assertIn('*', self.rule.file_patterns)


class TestU502URLConsistency(unittest.TestCase):
    """Test U502: URL consistency detector."""

    def setUp(self):
        """Set up test fixtures."""
        self.rule = U502()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def create_file(self, filename: str, content: str) -> str:
        """Helper: Create file in temp directory."""
        path = os.path.join(self.temp_dir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "U502")
        self.assertEqual(self.rule.severity, Severity.MEDIUM)
        self.assertIn("canonical", self.rule.message.lower())

    def test_no_pyproject_toml_no_detections(self):
        """Test that files without pyproject.toml don't trigger detections."""
        content = "Visit: https://github.com/personal/repo"
        path = self.create_file("README.md", content)

        detections = self.rule.check(path, None, content)

        # No pyproject.toml found, so no detections
        self.assertEqual(len(detections), 0)

    def test_pyproject_toml_skipped(self):
        """Test that pyproject.toml itself is not checked."""
        content = """
[project.urls]
Homepage = "https://github.com/org/project"
Repository = "https://github.com/personal/wrong"
"""
        path = self.create_file("pyproject.toml", content)

        detections = self.rule.check(path, None, content)

        # pyproject.toml is skipped (it's the source of truth)
        self.assertEqual(len(detections), 0)

    def test_consistent_url_not_detected(self):
        """Test that URLs matching pyproject.toml are not flagged."""
        # Create pyproject.toml
        pyproject_content = """
[project]
name = "test-project"

[project.urls]
Homepage = "https://github.com/org/project"
Repository = "https://github.com/org/project"
"""
        self.create_file("pyproject.toml", pyproject_content)

        # Create file with matching URL
        readme_content = "Visit: https://github.com/org/project"
        readme_path = self.create_file("README.md", readme_content)

        detections = self.rule.check(readme_path, None, readme_content)

        self.assertEqual(len(detections), 0)

    def test_inconsistent_url_detected(self):
        """Test that URLs not matching pyproject.toml are detected."""
        # Create pyproject.toml
        pyproject_content = """
[project.urls]
Repository = "https://github.com/org/project"
"""
        self.create_file("pyproject.toml", pyproject_content)

        # Create file with different owner
        readme_content = "Fork: https://github.com/personal/project"
        readme_path = self.create_file("README.md", readme_content)

        detections = self.rule.check(readme_path, None, readme_content)

        self.assertEqual(len(detections), 1)
        self.assertIn("personal/project", detections[0].message)
        self.assertIn("org", detections[0].suggestion)  # Should suggest org (may be truncated)

    def test_multiple_canonical_urls(self):
        """Test with multiple canonical URLs in pyproject.toml."""
        pyproject_content = """
[project]
homepage = "https://github.com/org/main-project"
repository = "https://github.com/org/main-project"
documentation = "https://github.com/org/docs-project"
"""
        self.create_file("pyproject.toml", pyproject_content)

        # File with URL to main project (should pass)
        readme_content = "See: https://github.com/org/main-project"
        readme_path = self.create_file("README.md", readme_content)

        detections = self.rule.check(readme_path, None, readme_content)
        self.assertEqual(len(detections), 0)

        # File with URL to docs project (should also pass)
        docs_content = "Docs: https://github.com/org/docs-project"
        docs_path = self.create_file("docs/index.md", docs_content)

        detections = self.rule.check(docs_path, None, docs_content)
        self.assertEqual(len(detections), 0)

    def test_git_suffix_normalized(self):
        """Test that .git suffix is normalized."""
        pyproject_content = """
[project.urls]
Repository = "https://github.com/org/project"
"""
        self.create_file("pyproject.toml", pyproject_content)

        # URL with .git suffix should match
        content = "Clone: https://github.com/org/project.git"
        path = self.create_file("install.sh", content)

        detections = self.rule.check(path, None, content)

        # Should not detect (org/project.git matches org/project)
        self.assertEqual(len(detections), 0)

    def test_case_insensitive_matching(self):
        """Test that owner/repo matching is case insensitive."""
        pyproject_content = """
[project.urls]
Repository = "https://github.com/Org/Project"
"""
        self.create_file("pyproject.toml", pyproject_content)

        # Lowercase version should match
        content = "https://github.com/org/project"
        path = self.create_file("README.md", content)

        detections = self.rule.check(path, None, content)

        self.assertEqual(len(detections), 0)

    def test_line_and_column_numbers(self):
        """Test that line and column numbers are correct."""
        pyproject_content = """
[project.urls]
Repository = "https://github.com/org/project"
"""
        self.create_file("pyproject.toml", pyproject_content)

        content = """
Line 1 text
Line 2 has URL: https://github.com/wrong/repo here
Line 3 text
"""
        path = self.create_file("test.md", content)

        detections = self.rule.check(path, None, content)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].line, 3)  # Line 3 (blank line 1, text line 2, URL line 3)
        self.assertGreater(detections[0].column, 0)

    def test_http_urls_detected(self):
        """Test that http:// GitHub URLs are also checked."""
        pyproject_content = """
[project.urls]
Repository = "https://github.com/org/project"
"""
        self.create_file("pyproject.toml", pyproject_content)

        # http:// URL with wrong owner
        content = "Fork: http://github.com/personal/project"
        path = self.create_file("README.md", content)

        detections = self.rule.check(path, None, content)

        self.assertEqual(len(detections), 1)
        self.assertIn("personal/project", detections[0].message)

    def test_poetry_urls_section(self):
        """Test support for Poetry's tool.poetry.urls section."""
        pyproject_content = """
[tool.poetry]
name = "test-project"

[tool.poetry.urls]
Homepage = "https://github.com/org/poetry-project"
Repository = "https://github.com/org/poetry-project"
"""
        self.create_file("pyproject.toml", pyproject_content)

        # Matching URL should not be flagged
        content = "Project: https://github.com/org/poetry-project"
        path = self.create_file("README.md", content)

        detections = self.rule.check(path, None, content)

        self.assertEqual(len(detections), 0)

    def test_suggestion_matches_repo_name(self):
        """Test that suggestion matches the found repo name when possible."""
        pyproject_content = """
[project.urls]
Repository = "https://github.com/org/my-project"
"""
        self.create_file("pyproject.toml", pyproject_content)

        # Personal fork with same repo name
        content = "Fork: https://github.com/personal/my-project"
        path = self.create_file("README.md", content)

        detections = self.rule.check(path, None, content)

        self.assertEqual(len(detections), 1)
        # Suggestion should reference the canonical org
        self.assertIn("org", detections[0].suggestion)
        # Note: suggestion may be truncated, so we only check for org

    def test_multiple_inconsistent_urls_same_file(self):
        """Test multiple inconsistent URLs in same file."""
        pyproject_content = """
[project.urls]
Repository = "https://github.com/org/project"
"""
        self.create_file("pyproject.toml", pyproject_content)

        content = """
Fork 1: https://github.com/user1/project
Fork 2: https://github.com/user2/project
Canonical: https://github.com/org/project (this is ok)
"""
        path = self.create_file("README.md", content)

        detections = self.rule.check(path, None, content)

        # Should detect both inconsistent URLs
        self.assertEqual(len(detections), 2)
        self.assertIn("user1", detections[0].message)
        self.assertIn("user2", detections[1].message)

    def test_non_github_urls_ignored(self):
        """Test that non-GitHub URLs are ignored."""
        pyproject_content = """
[project.urls]
Repository = "https://github.com/org/project"
"""
        self.create_file("pyproject.toml", pyproject_content)

        content = """
- https://gitlab.com/other/repo
- https://example.com
"""
        path = self.create_file("README.md", content)

        detections = self.rule.check(path, None, content)

        # Non-GitHub URLs are ignored
        self.assertEqual(len(detections), 0)

    def test_file_patterns(self):
        """Test that rule applies to appropriate file types."""
        patterns = self.rule.file_patterns
        self.assertIn('.py', patterns)
        self.assertIn('.md', patterns)
        self.assertIn('.rst', patterns)
        self.assertIn('.yaml', patterns)
        self.assertIn('.sh', patterns)

    def test_context_truncated_for_long_lines(self):
        """Test that context is truncated for very long lines."""
        pyproject_content = """
[project.urls]
Repository = "https://github.com/org/project"
"""
        self.create_file("pyproject.toml", pyproject_content)

        # Very long line
        long_text = "x" * 200
        content = f"{long_text} https://github.com/wrong/repo {long_text}"
        path = self.create_file("test.md", content)

        detections = self.rule.check(path, None, content)

        self.assertEqual(len(detections), 1)
        # Context should be truncated to 100 chars
        self.assertLessEqual(len(detections[0].context), 100)


if __name__ == '__main__':
    unittest.main()
