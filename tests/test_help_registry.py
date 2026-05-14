"""Tests for help:// static guide registry integrity.

Prevents two failure modes:
  1. Dead links — STATIC_HELP entry points to a file that doesn't exist on disk.
  2. Orphaned docs — a user-facing markdown file exists but has no help:// route.

When adding a new guide under reveal/docs/, either:
  a) Add it to HelpAdapter.STATIC_HELP in reveal/adapters/help.py, OR
  b) Add its relative path to _INTENTIONALLY_EXCLUDED below with a reason.
"""
import unittest
from pathlib import Path

from reveal.adapters.help import HelpAdapter

# Docs that live under reveal/docs/ but are intentionally not in help://.
# Key: path relative to reveal/docs/. Value: reason for exclusion.
_INTENTIONALLY_EXCLUDED = {
    'BENCHMARKS.md': 'performance data, not a user guide',
    'INDEX.md': 'table-of-contents meta-file, not standalone content',
    'README.md': 'mirrors top-level package README, not a guide',
}

_DOCS_ROOT = Path(__file__).parent.parent / 'reveal' / 'docs'


class TestHelpRegistry(unittest.TestCase):
    """Validate HelpAdapter.STATIC_HELP registration."""

    def _registered_files(self) -> set:
        return set(HelpAdapter.STATIC_HELP.values())

    def test_no_dead_links(self):
        """Every path in STATIC_HELP must exist on disk."""
        dead = []
        for topic, rel_path in HelpAdapter.STATIC_HELP.items():
            full = _DOCS_ROOT / rel_path
            if not full.exists():
                dead.append(f'  help://{topic} → {rel_path} (missing)')
        self.assertFalse(
            dead,
            'STATIC_HELP contains entries pointing to missing files:\n'
            + '\n'.join(dead)
            + '\nEither create the file or remove the entry.'
        )

    def test_all_adapter_guides_reachable(self):
        """Every file under docs/adapters/ must be reachable via help://."""
        registered = self._registered_files()
        orphans = []
        for md in sorted((_DOCS_ROOT / 'adapters').glob('*.md')):
            rel = str(md.relative_to(_DOCS_ROOT))
            if rel not in registered and rel not in _INTENTIONALLY_EXCLUDED:
                orphans.append(f'  {rel}')
        self.assertFalse(
            orphans,
            'Adapter guides with no help:// route:\n'
            + '\n'.join(orphans)
            + '\nAdd an entry to HelpAdapter.STATIC_HELP or _INTENTIONALLY_EXCLUDED.'
        )

    def test_all_user_guides_reachable(self):
        """Every file under docs/guides/ must be reachable via help://."""
        registered = self._registered_files()
        orphans = []
        for md in sorted((_DOCS_ROOT / 'guides').glob('*.md')):
            rel = str(md.relative_to(_DOCS_ROOT))
            if rel not in registered and rel not in _INTENTIONALLY_EXCLUDED:
                orphans.append(f'  {rel}')
        self.assertFalse(
            orphans,
            'User guides with no help:// route:\n'
            + '\n'.join(orphans)
            + '\nAdd an entry to HelpAdapter.STATIC_HELP or _INTENTIONALLY_EXCLUDED.'
        )

    def test_all_development_docs_reachable(self):
        """Every file under docs/development/ must be reachable via help://."""
        registered = self._registered_files()
        orphans = []
        for md in sorted((_DOCS_ROOT / 'development').glob('*.md')):
            rel = str(md.relative_to(_DOCS_ROOT))
            if rel not in registered and rel not in _INTENTIONALLY_EXCLUDED:
                orphans.append(f'  {rel}')
        self.assertFalse(
            orphans,
            'Development docs with no help:// route:\n'
            + '\n'.join(orphans)
            + '\nAdd an entry to HelpAdapter.STATIC_HELP or _INTENTIONALLY_EXCLUDED.'
        )

    def test_top_level_docs_accounted_for(self):
        """Every top-level doc under docs/ is either registered or explicitly excluded."""
        registered = self._registered_files()
        orphans = []
        for md in sorted(_DOCS_ROOT.glob('*.md')):
            rel = str(md.relative_to(_DOCS_ROOT))
            if rel not in registered and rel not in _INTENTIONALLY_EXCLUDED:
                orphans.append(f'  {rel}')
        self.assertFalse(
            orphans,
            'Top-level docs with no help:// route and not in exclusion list:\n'
            + '\n'.join(orphans)
            + '\nAdd to HelpAdapter.STATIC_HELP or _INTENTIONALLY_EXCLUDED.'
        )

    def test_help_nav_resolves(self):
        """Spot-check: help://nav must resolve to NAV_GUIDE.md on disk."""
        rel = HelpAdapter.STATIC_HELP.get('nav')
        self.assertIsNotNone(rel, 'help://nav not registered')
        self.assertTrue((_DOCS_ROOT / rel).exists(), f'NAV_GUIDE.md missing at {rel}')

    def test_help_ast_resolves(self):
        """Spot-check: help://ast must resolve to AST_ADAPTER_GUIDE.md on disk."""
        rel = HelpAdapter.STATIC_HELP.get('ast')
        self.assertIsNotNone(rel, 'help://ast not registered')
        self.assertTrue((_DOCS_ROOT / rel).exists(), f'AST guide missing at {rel}')


if __name__ == '__main__':
    unittest.main()
