"""Integration tests for CLI flags across file types.

Tests that all CLI flags (--outline, --head, --tail) work with all file types
without causing TypeError. This prevents LSP violations where analyzers
don't accept the parameters that the CLI layer passes.
"""

import unittest
import tempfile
import subprocess
import sys
import os
from pathlib import Path


class TestCLIFlagsIntegration(unittest.TestCase):
    """Test CLI flags work with different file types."""

    def run_reveal(self, file_path, *args):
        """Run reveal command and return result."""
        cmd = [sys.executable, "-m", "reveal.main", str(file_path)] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return result

    def test_json_with_outline(self):
        """JSON files should accept --outline flag without error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"name": "test", "version": "1.0"}')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--outline")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
            self.assertIn("name", result.stdout)
        finally:
            os.unlink(temp_file)

    def test_yaml_with_outline(self):
        """YAML files should accept --outline flag without error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('name: test\nversion: 1.0\n')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--outline")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
            self.assertIn("name", result.stdout)
        finally:
            os.unlink(temp_file)

    def test_json_with_head(self):
        """JSON files should accept --head flag without error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"a": 1, "b": 2, "c": 3, "d": 4}')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--head", "2")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
        finally:
            os.unlink(temp_file)

    def test_yaml_with_tail(self):
        """YAML files should accept --tail flag without error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('a: 1\nb: 2\nc: 3\nd: 4\n')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--tail", "2")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
        finally:
            os.unlink(temp_file)

    def test_toml_with_outline(self):
        """TOML files should accept --outline flag."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write('[database]\nhost = "localhost"\n[cache]\nenabled = true\n')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--outline")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
        finally:
            os.unlink(temp_file)

    def test_dockerfile_with_head(self):
        """Dockerfile should accept --head flag."""
        # Create Dockerfile with proper name (no extension)
        temp_dir = tempfile.mkdtemp()
        temp_file = Path(temp_dir) / 'Dockerfile'
        temp_file.write_text('FROM python:3.9\nRUN pip install requests\nCOPY . /app\n')

        try:
            result = self.run_reveal(temp_file, "--head", "2")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
        finally:
            temp_file.unlink()
            Path(temp_dir).rmdir()

    def test_python_with_outline(self):
        """Python files should work with --outline (baseline test)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('class Foo:\n    def bar(self): pass\n')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--outline")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
            self.assertIn("Foo", result.stdout)
        finally:
            os.unlink(temp_file)

    def test_markdown_with_outline(self):
        """Markdown files should work with --outline."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('# Title\n## Section\n### Subsection\n')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--outline")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
        finally:
            os.unlink(temp_file)


class TestCLIFlagsCombinations(unittest.TestCase):
    """Test multiple flags combined."""

    def run_reveal(self, file_path, *args):
        """Run reveal command and return result."""
        cmd = [sys.executable, "-m", "reveal.main", str(file_path)] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return result

    def test_json_outline_and_format(self):
        """Test multiple flags together."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"name": "test"}')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--outline", "--format", "json")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
        finally:
            os.unlink(temp_file)


class TestHTMLCLIFlags(unittest.TestCase):
    """Test HTML-specific CLI flags."""

    def run_reveal(self, file_path, *args):
        """Run reveal command and return result."""
        cmd = [sys.executable, "-m", "reveal.main", str(file_path)] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return result

    def test_html_default_display(self):
        """Test HTML file displays without error (default view)."""
        html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <title>Test Page</title>
    <meta name="description" content="Test description">
</head>
<body>
    <nav><a href="/">Home</a></nav>
    <main><h1>Welcome</h1></main>
</body>
</html>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html)
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file)
            self.assertEqual(result.returncode, 0,
                           f"HTML default display failed with: {result.stderr}")
            # Should complete without AttributeError
            self.assertNotIn("AttributeError", result.stderr)
            self.assertNotIn("'str' object has no attribute 'get'", result.stderr)
        finally:
            os.unlink(temp_file)

    def test_html_metadata_flag(self):
        """Test HTML --metadata flag extracts SEO information."""
        html = '''<!DOCTYPE html>
<html>
<head>
    <title>SEO Test Page</title>
    <meta name="description" content="A comprehensive test">
    <meta property="og:title" content="OG Title">
    <meta name="twitter:card" content="summary">
    <link rel="stylesheet" href="styles.css">
    <script src="app.js"></script>
</head>
<body>
    <h1>Content</h1>
</body>
</html>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html)
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--metadata")
            self.assertEqual(result.returncode, 0,
                           f"HTML --metadata failed with: {result.stderr}")

            # Should contain metadata information
            self.assertIn("Metadata", result.stdout)
            self.assertIn("SEO Test Page", result.stdout)
            self.assertIn("description", result.stdout)
        finally:
            os.unlink(temp_file)

    def test_html_scripts_flag(self):
        """Test HTML --scripts flag extracts inline and external scripts."""
        html = '''<!DOCTYPE html>
<html>
<head>
    <title>Scripts Test</title>
    <script src="external.js"></script>
    <script>
    console.log('inline script');
    alert('test');
    </script>
</head>
<body>
    <script src="app.js" defer></script>
</body>
</html>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html)
            temp_file = f.name

        try:
            # Test --scripts all
            result = self.run_reveal(temp_file, "--scripts", "all")
            self.assertEqual(result.returncode, 0,
                           f"HTML --scripts all failed with: {result.stderr}")
            self.assertIn("Scripts", result.stdout)
            self.assertIn("external.js", result.stdout)
            self.assertIn("inline", result.stdout)

            # Test --scripts external
            result = self.run_reveal(temp_file, "--scripts", "external")
            self.assertEqual(result.returncode, 0,
                           f"HTML --scripts external failed with: {result.stderr}")
            self.assertIn("external.js", result.stdout)

            # Test --scripts inline
            result = self.run_reveal(temp_file, "--scripts", "inline")
            self.assertEqual(result.returncode, 0,
                           f"HTML --scripts inline failed with: {result.stderr}")
            self.assertIn("inline", result.stdout)
        finally:
            os.unlink(temp_file)

    def test_html_styles_flag(self):
        """Test HTML --styles flag extracts stylesheets."""
        html = '''<!DOCTYPE html>
<html>
<head>
    <title>Styles Test</title>
    <link rel="stylesheet" href="main.css">
    <link rel="stylesheet" href="theme.css" media="screen">
    <style>
    body { margin: 0; padding: 0; }
    .container { width: 100%; }
    </style>
</head>
<body>
    <h1>Test</h1>
</body>
</html>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html)
            temp_file = f.name

        try:
            # Test --styles all
            result = self.run_reveal(temp_file, "--styles", "all")
            self.assertEqual(result.returncode, 0,
                           f"HTML --styles all failed with: {result.stderr}")
            self.assertIn("Styles", result.stdout)
            self.assertIn("main.css", result.stdout)

            # Test --styles external
            result = self.run_reveal(temp_file, "--styles", "external")
            self.assertEqual(result.returncode, 0,
                           f"HTML --styles external failed with: {result.stderr}")
            self.assertIn("main.css", result.stdout)

            # Test --styles inline
            result = self.run_reveal(temp_file, "--styles", "inline")
            self.assertEqual(result.returncode, 0,
                           f"HTML --styles inline failed with: {result.stderr}")
            self.assertIn("inline", result.stdout)
        finally:
            os.unlink(temp_file)

    def test_html_semantic_flag(self):
        """Test HTML --semantic flag extracts semantic elements."""
        html = '''<!DOCTYPE html>
<html>
<head>
    <title>Semantic Test</title>
</head>
<body>
    <nav id="main-nav">
        <a href="/">Home</a>
        <a href="/about">About</a>
    </nav>
    <main>
        <article>
            <h1>Article Title</h1>
            <section>Content section</section>
        </article>
    </main>
    <aside>Sidebar content</aside>
    <footer>Footer content</footer>
</body>
</html>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html)
            temp_file = f.name

        try:
            # Test --semantic navigation
            result = self.run_reveal(temp_file, "--semantic", "navigation")
            self.assertEqual(result.returncode, 0,
                           f"HTML --semantic navigation failed with: {result.stderr}")
            self.assertIn("Semantic", result.stdout)
            self.assertIn("nav", result.stdout)

            # Test --semantic content
            result = self.run_reveal(temp_file, "--semantic", "content")
            self.assertEqual(result.returncode, 0,
                           f"HTML --semantic content failed with: {result.stderr}")
            self.assertIn("main", result.stdout)
        finally:
            os.unlink(temp_file)


if __name__ == '__main__':
    unittest.main()
