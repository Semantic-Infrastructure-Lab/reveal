"""Test for MANIFEST.in accuracy - prevents packaging bugs.

This test would have caught the bug where MANIFEST.in referenced old paths
(reveal/AGENT_HELP.md) that were moved to reveal/docs/AGENT_HELP.md.
"""

import unittest
import subprocess
import tarfile
import tempfile
import shutil
from pathlib import Path


class TestPackagingManifest(unittest.TestCase):
    """Test that MANIFEST.in accurately includes all necessary files."""

    @classmethod
    def setUpClass(cls):
        """Build the package once for all tests."""
        cls.project_root = Path(__file__).parent.parent
        cls.temp_dir = Path(tempfile.mkdtemp())
        
        # Build the package in temp directory
        result = subprocess.run(
            ['python', '-m', 'build', '--outdir', str(cls.temp_dir)],
            cwd=cls.project_root,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Package build failed: {result.stderr}")
        
        # Find the built tarball
        tarballs = list(cls.temp_dir.glob('*.tar.gz'))
        if not tarballs:
            raise RuntimeError("No tarball found after build")
        
        cls.tarball = tarballs[0]

    @classmethod
    def tearDownClass(cls):
        """Clean up temp directory."""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_agent_help_files_included(self):
        """AGENT_HELP*.md files must be included in distribution.
        
        Regression test: These files were moved to reveal/docs/ but MANIFEST.in
        still referenced reveal/AGENT_HELP*.md, causing them to be excluded.
        """
        with tarfile.open(self.tarball, 'r:gz') as tar:
            names = tar.getnames()
            
            # Check for both agent help files
            agent_help = [n for n in names if 'AGENT_HELP.md' in n]
            agent_help_full = [n for n in names if 'AGENT_HELP_FULL.md' in n]
            
            self.assertTrue(
                len(agent_help) > 0,
                "AGENT_HELP.md not found in package! Check MANIFEST.in"
            )
            self.assertTrue(
                len(agent_help_full) > 0,
                "AGENT_HELP_FULL.md not found in package! Check MANIFEST.in"
            )
            
            # Verify they're in the correct location
            for name in agent_help + agent_help_full:
                self.assertIn(
                    '/reveal/docs/',
                    name,
                    f"Help file {name} not in reveal/docs/ directory"
                )

    def test_all_docs_included(self):
        """All files in reveal/docs/ should be included."""
        docs_dir = self.project_root / 'reveal' / 'docs'
        if not docs_dir.exists():
            self.skipTest("reveal/docs/ directory not found")
        
        expected_docs = [f.name for f in docs_dir.glob('*.md')]
        
        with tarfile.open(self.tarball, 'r:gz') as tar:
            names = tar.getnames()
            included_docs = [
                Path(n).name for n in names 
                if '/reveal/docs/' in n and n.endswith('.md')
            ]
            
            missing = set(expected_docs) - set(included_docs)
            
            self.assertEqual(
                set(),
                missing,
                f"Documentation files missing from package: {missing}\n"
                f"Check MANIFEST.in includes reveal/docs/*.md"
            )

    def test_plugins_included(self):
        """Plugin definition files should be included."""
        with tarfile.open(self.tarball, 'r:gz') as tar:
            names = tar.getnames()
            plugins = [n for n in names if '/plugins/' in n and n.endswith(('.yaml', '.yml'))]
            
            self.assertGreater(
                len(plugins),
                0,
                "No plugin files found in package! Check MANIFEST.in"
            )

    def test_manifest_paths_exist(self):
        """All paths in MANIFEST.in should reference existing files/patterns.
        
        This catches bugs where MANIFEST.in references old paths that no longer exist.
        """
        manifest_file = self.project_root / 'MANIFEST.in'
        if not manifest_file.exists():
            self.skipTest("MANIFEST.in not found")
        
        content = manifest_file.read_text()
        
        # Parse include directives (simplified - doesn't handle all MANIFEST.in syntax)
        issues = []
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Check "include path/to/file.ext" directives
            if line.startswith('include ') and not line.startswith('include-package-data'):
                path = line.split('include ')[1].strip()
                full_path = self.project_root / path
                if not full_path.exists() and '*' not in path:
                    issues.append(f"Referenced file doesn't exist: {path}")
        
        self.assertEqual(
            [],
            issues,
            f"MANIFEST.in references non-existent paths:\n" + "\n".join(issues)
        )


if __name__ == '__main__':
    unittest.main()
