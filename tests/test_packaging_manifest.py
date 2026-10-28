"""Test for MANIFEST.in accuracy - prevents packaging bugs.

This test would have caught the bug where MANIFEST.in referenced old paths
(reveal/AGENT_HELP.md) that were moved to reveal/docs/AGENT_HELP.md.
"""

import unittest
import subprocess
import tarfile
import tempfile
import shutil
import zipfile
from pathlib import Path

import pytest

from scripts.packaging_sources import stage_sources as _stage_sources

# BACK-1149: guards an internal invariant/output-contract (registry, schema, or cross-module consistency)
pytestmark = pytest.mark.contract


def _checkout_fingerprint(project_root: Path):
    """What a build in the checkout would disturb: the top-level names (the
    sdist staging dir reveal_cli-X.Y.Z/ appears and vanishes there) and the
    install metadata that reveal.version reads on every import."""
    pkg_info = project_root / 'reveal_cli.egg-info' / 'PKG-INFO'
    stamp = pkg_info.stat().st_mtime_ns if pkg_info.exists() else None
    return sorted(p.name for p in project_root.iterdir()), stamp


class TestPackagingManifest(unittest.TestCase):
    """Test that MANIFEST.in accurately includes all necessary files."""

    @classmethod
    def setUpClass(cls):
        """Build the package once for all tests."""
        cls.project_root = Path(__file__).parent.parent
        cls.temp_dir = Path(tempfile.mkdtemp())
        cls.checkout_before = _checkout_fingerprint(cls.project_root)

        # Build the package from a staged copy, never in the checkout
        stage = cls.temp_dir / 'src'
        out = cls.temp_dir / 'out'
        _stage_sources(cls.project_root, stage)
        result = subprocess.run(
            ['python', '-m', 'build', '--outdir', str(out)],
            cwd=stage,
            capture_output=True,
            text=True, encoding='utf-8', errors='replace'
        )

        if result.returncode != 0:
            raise RuntimeError(f"Package build failed: {result.stderr}")
        
        # Find the built tarball
        tarballs = list(out.glob('*.tar.gz'))
        if not tarballs:
            raise RuntimeError("No tarball found after build")
        
        cls.tarball = tarballs[0]

    @classmethod
    def tearDownClass(cls):
        """Clean up temp directory."""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_build_leaves_the_checkout_untouched(self):
        """The sdist build must not write into the checkout (BACK-1895).

        Building in place rewrites reveal_cli.egg-info/PKG-INFO, which every
        `import reveal` reads (reveal/version.py), and stages reveal_cli-X.Y.Z/
        in the repo root, which other tests walk. Both race with readers on
        other xdist workers: "Access is denied" on the PKG-INFO rename on
        Windows, FileNotFoundError mid-walk elsewhere."""
        self.assertEqual(self.checkout_before,
                         _checkout_fingerprint(self.project_root))

    def test_every_tracked_package_file_ships(self):
        """The sdist built from the staged copy holds every tracked file under
        reveal/, data files included (help_data/*.yaml, schemas/frontmatter).
        TestBuildWithoutGit checks the same without setuptools_scm's git file
        finder."""
        tracked = subprocess.run(
            ['git', 'ls-files', '-z', 'reveal'], cwd=self.project_root,
            capture_output=True, check=True,
        ).stdout.decode('utf-8').split('\0')
        with tarfile.open(self.tarball, 'r:gz') as tar:
            shipped = {n.split('/', 1)[1] for n in tar.getnames() if '/' in n}
        missing = sorted(f for f in tracked
                         if f and (self.project_root / f).is_file() and f not in shipped)
        self.assertEqual([], missing, f"tracked files missing from the sdist: {missing[:10]}")

    def test_agent_help_files_included(self):
        """AGENT_HELP.md must be included in distribution.

        Regression test: This file was moved to reveal/docs/ but MANIFEST.in
        still referenced reveal/AGENT_HELP*.md, causing it to be excluded.
        Note: AGENT_HELP_FULL.md was merged into AGENT_HELP.md in v0.39.0.
        """
        with tarfile.open(self.tarball, 'r:gz') as tar:
            names = tar.getnames()

            # Check for agent help file
            agent_help = [n for n in names if 'AGENT_HELP.md' in n]

            self.assertTrue(
                len(agent_help) > 0,
                "AGENT_HELP.md not found in package! Check MANIFEST.in"
            )

            # Verify it's in the correct location
            for name in agent_help:
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
        
        content = manifest_file.read_text(encoding='utf-8')

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


class TestBuildWithoutGit(unittest.TestCase):
    """A build from a tree with no git history (GitHub zip, a source tarball
    rebuilt by a distro) gets no help from setuptools_scm's file finder: every
    data file must be declared in package-data or MANIFEST.in (BACK-2154)."""

    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).parent.parent
        cls.temp_dir = Path(tempfile.mkdtemp())
        stage = cls.temp_dir / 'src'
        out = cls.temp_dir / 'out'
        _stage_sources(cls.project_root, stage, commit=False)
        result = subprocess.run(
            ['python', '-m', 'build', '--outdir', str(out)],
            cwd=stage, capture_output=True,
            text=True, encoding='utf-8', errors='replace', timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Package build failed: {result.stderr}")
        cls.tarball = next(out.glob('*.tar.gz'))
        cls.wheel = next(out.glob('*.whl'))
        cls.tracked = [f for f in subprocess.run(
            ['git', 'ls-files', '-z', 'reveal'], cwd=cls.project_root,
            capture_output=True, check=True,
        ).stdout.decode('utf-8').split('\0') if f and (cls.project_root / f).is_file()]

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'temp_dir') and cls.temp_dir.exists():
            shutil.rmtree(cls.temp_dir)

    def test_sdist_holds_every_tracked_package_file(self):
        with tarfile.open(self.tarball, 'r:gz') as tar:
            shipped = {n.split('/', 1)[1] for n in tar.getnames() if '/' in n}
        missing = sorted(f for f in self.tracked if f not in shipped)
        self.assertEqual([], missing, f"tracked files missing from a no-git sdist: {missing}")

    def test_wheel_holds_every_tracked_package_file(self):
        with zipfile.ZipFile(self.wheel) as whl:
            shipped = set(whl.namelist())
        missing = sorted(f for f in self.tracked if f not in shipped)
        self.assertEqual([], missing, f"tracked files missing from a no-git wheel: {missing}")


if __name__ == '__main__':
    unittest.main()
