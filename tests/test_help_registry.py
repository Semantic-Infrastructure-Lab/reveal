"""Tests for help:// static guide registry integrity.

Prevents three failure modes:
  1. Dead links — STATIC_HELP entry points to a file that doesn't exist on disk.
  2. Orphaned docs — a user-facing markdown file exists but has no help:// route.
  3. Silent help-index regressions — a guide is categorized (help_category) but
     missing help_description, or declares an unknown help_category, or claims
     help_topic that no STATIC_HELP/auto-discovery entry resolves to.

When adding a new guide under reveal/docs/, either:
  a) Add it to HelpAdapter.STATIC_HELP in reveal/adapters/help.py, OR
  b) Add its relative path to _INTENTIONALLY_EXCLUDED below with a reason.
"""
import unittest
from pathlib import Path

from reveal.adapters.help import HelpAdapter, VALID_HELP_CATEGORIES, _read_help_frontmatter

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

    def test_progressive_disclosure_large_guide(self):
        """Large guides (>200 lines) are truncated with a breadcrumb and /full hint."""
        adapter = HelpAdapter()
        result = adapter.get_element('ast')
        self.assertIsNotNone(result)
        content = result['content']
        self.assertIn('── Full guide: reveal help://ast/full', content,
                      'Truncated view must include /full access hint')
        self.assertIn('lines total. Sections:', content,
                      'Truncated view must include section breadcrumb')
        # Should NOT contain the full guide (which ends with Version History / FAQ)
        self.assertNotIn('## Version History', content,
                         'Truncated view should not include late sections')

    def test_progressive_disclosure_full_bypass(self):
        """help://ast/full returns the complete guide, bypassing truncation."""
        adapter = HelpAdapter()
        result = adapter.get_element('ast/full')
        self.assertIsNotNone(result)
        content = result['content']
        self.assertIn('## Version History', content,
                      '/full must return the complete guide')
        self.assertNotIn('reveal help://ast/full', content,
                         '/full must not append breadcrumb footer')

    def test_progressive_disclosure_small_guide_passthrough(self):
        """Small guides (<=200 lines) are returned in full without truncation."""
        adapter = HelpAdapter()
        result = adapter.get_element('nav')
        self.assertIsNotNone(result)
        content = result['content']
        self.assertNotIn('Full guide:', content,
                         'Short guides must not have a truncation footer')

    def test_full_only_topics_never_truncated(self):
        """agent and anti-patterns are always returned in full (they are mega-docs)."""
        adapter = HelpAdapter()
        for topic in ('agent', 'anti-patterns'):
            result = adapter.get_element(topic)
            self.assertIsNotNone(result, f'help://{topic} must resolve')
            content = result['content']
            self.assertNotIn('Full guide:', content,
                             f'help://{topic} must never be truncated')
            self.assertGreater(len(content.splitlines()), 200,
                               f'help://{topic} must return full content')

    def test_quick_start_shows_multiple_sections(self):
        """quick-start truncation shows enough content to be useful (at least 2 sections)."""
        adapter = HelpAdapter()
        result = adapter.get_element('quick-start')
        self.assertIsNotNone(result)
        content = result['content']
        # Should show more than just "Installation"
        section_count = sum(1 for line in content.splitlines() if line.startswith('## '))
        self.assertGreater(section_count, 1,
                           'quick-start must show at least 2 sections to be useful')


class TestHelpFrontmatterMetadata(unittest.TestCase):
    """Validate the help_* frontmatter fields that drive the help:// index.

    These tests turn what used to be silent fallbacks ('Static guide' default
    description, missing categories) into structural errors. They are the
    enforcement layer that makes frontmatter the single source of truth.
    """

    def _all_guide_entries(self):
        """Build the merged registry the same way HelpAdapter does."""
        return HelpAdapter()._discover_and_merge_guides()

    def test_categorized_guides_have_descriptions(self):
        """Any guide that declares help_category must also declare help_description.

        Without this, the index falls back to 'Static guide' — exactly the
        silent failure the frontmatter migration was meant to eliminate.
        """
        entries = self._all_guide_entries()
        missing = []
        for entry in entries.values():
            if entry.category and not entry.description:
                missing.append(f'  help://{entry.topic} → {entry.file}')
        self.assertFalse(
            missing,
            'Guides with help_category but no help_description (silent fallback):\n'
            + '\n'.join(missing)
            + '\nAdd help_description to the frontmatter.'
        )

    def test_help_categories_are_valid(self):
        """Every help_category value must be in VALID_HELP_CATEGORIES."""
        entries = self._all_guide_entries()
        bad = []
        for entry in entries.values():
            if entry.category and entry.category not in VALID_HELP_CATEGORIES:
                bad.append(
                    f'  help://{entry.topic} → {entry.file} declares '
                    f'help_category={entry.category!r} (not in {sorted(VALID_HELP_CATEGORIES)})'
                )
        self.assertFalse(
            bad,
            'Guides with unknown help_category values:\n' + '\n'.join(bad)
        )

    def test_each_category_has_at_least_one_guide(self):
        """Every valid category should have at least one categorized guide.

        Catches the case where renaming a category leaves a section in
        VALID_HELP_CATEGORIES but no guide opts into it.
        """
        entries = self._all_guide_entries()
        seen = {e.category for e in entries.values() if e.category}
        missing = VALID_HELP_CATEGORIES - seen
        self.assertFalse(
            missing,
            f'Categories in VALID_HELP_CATEGORIES with no guides assigned: {sorted(missing)}'
        )

    def test_categorized_guides_have_token_estimate(self):
        """Categorized guides should declare help_token_estimate.

        Missing values fall back to '~2,000' which is misleading for large
        guides (e.g. AGENT_HELP.md is ~12,000).
        """
        entries = self._all_guide_entries()
        missing = []
        for entry in entries.values():
            if entry.category and not entry.token_estimate:
                missing.append(f'  help://{entry.topic} → {entry.file}')
        self.assertFalse(
            missing,
            'Categorized guides without help_token_estimate (defaults to ~2,000):\n'
            + '\n'.join(missing)
        )

    def test_help_topic_resolves(self):
        """If a file declares help_topic, that topic must exist in the registry.

        Catches typos (help_topic: aget) and stale declarations after STATIC_HELP renames.
        """
        entries = self._all_guide_entries()
        files_with_canonical = {}
        for md in _DOCS_ROOT.rglob('*.md'):
            fm = _read_help_frontmatter(md)
            canonical = fm.get('help_topic')
            if canonical:
                files_with_canonical[str(md.relative_to(_DOCS_ROOT))] = canonical

        unresolved = []
        topics = set(entries.keys())
        for file, canonical in files_with_canonical.items():
            if canonical not in topics:
                unresolved.append(f'  {file} declares help_topic={canonical!r} but no topic resolves to it')
        self.assertFalse(unresolved, 'Unresolved help_topic declarations:\n' + '\n'.join(unresolved))


class TestHelpErrorHandling(unittest.TestCase):
    """Unknown topic routing returns None cleanly, not a misleading error dict."""

    def test_unknown_topic_returns_none(self):
        """help://nonexistent → None (rendered as clean 'not found', not a traceback)."""
        adapter = HelpAdapter()
        result = adapter.get_element('nonexistent')
        self.assertIsNone(result, 'Unknown bare topic must return None')

    def test_unknown_topic_with_full_suffix_returns_none(self):
        """help://nonexistent/full must return None, not 'Unknown section full'."""
        adapter = HelpAdapter()
        result = adapter.get_element('nonexistent/full')
        self.assertIsNone(result,
            'Unknown topic/full must return None, not a misleading section-name error')

    def test_unknown_topic_with_section_returns_none(self):
        """help://nonexistent/workflows must return None cleanly."""
        adapter = HelpAdapter()
        result = adapter.get_element('nonexistent/workflows')
        self.assertIsNone(result)

    def test_known_guide_full_still_works(self):
        """help://ux/full must still return content after the routing fix."""
        adapter = HelpAdapter()
        result = adapter.get_element('ux/full')
        self.assertIsNotNone(result, 'help://ux/full must resolve')
        self.assertIn('content', result)
        self.assertIn('--name', result['content'])

    def test_known_adapter_section_still_works(self):
        """help://ast/workflows must still work (adapter in both help_topics and registry)."""
        adapter = HelpAdapter()
        result = adapter.get_element('ast/workflows')
        self.assertIsNotNone(result, 'help://ast/workflows must resolve')


class TestHelpContentCurrency(unittest.TestCase):
    """Spot-check that help:// content reflects current flag names."""

    def _get_content(self, topic: str) -> str:
        adapter = HelpAdapter()
        result = adapter.get_element(topic)
        self.assertIsNotNone(result, f'help://{topic} must resolve')
        return result.get('content', '')

    def test_ux_guide_uses_name_flag_as_primary(self):
        """help://ux/full must show --name as the primary structural filter flag."""
        content = self._get_content('ux/full')
        self.assertIn('--name', content,
                      'UX guide must document the --name flag')

    def test_ux_guide_documents_grep_flag(self):
        """help://ux/full must document --grep for text search."""
        content = self._get_content('ux/full')
        self.assertIn('--grep', content,
                      'UX guide must document the --grep flag')

    def test_agent_guide_uses_name_flag(self):
        """help://agent must mention --name (the canonical structural filter flag)."""
        content = self._get_content('agent')
        self.assertIn('--name', content,
                      'Agent guide must document --name flag')

    def test_agent_guide_documents_grep_flag(self):
        """help://agent must mention --grep for text search."""
        content = self._get_content('agent')
        self.assertIn('--grep', content,
                      'Agent guide must document --grep flag')

    def test_ux_guide_search_only_as_alias(self):
        """help://ux/full must not use --search as a standalone example (only as deprecated alias mention)."""
        content = self._get_content('ux/full')
        lines_with_search = [
            line for line in content.splitlines()
            if '--search' in line
            and 'alias' not in line.lower()
            and 'deprecated' not in line.lower()
            and 'was the old' not in line.lower()
            and 'renamed' not in line.lower()
            and 'becomes' not in line.lower()  # migration comments explaining the rename
        ]
        self.assertFalse(
            lines_with_search,
            f'--search appears as non-alias in ux/full:\n' + '\n'.join(f'  {l}' for l in lines_with_search)
        )


class TestCliHelpOutput(unittest.TestCase):
    """Validate --help flag output reflects current flag names and aliases."""

    def _get_help_output(self) -> str:
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, '-m', 'reveal.main', '--help'],
            capture_output=True, text=True,
            cwd=str(_DOCS_ROOT.parent.parent)
        )
        return result.stdout + result.stderr

    def test_name_flag_shown_as_primary_in_help(self):
        """--help must show --name as the primary flag, with --search as alias."""
        output = self._get_help_output()
        self.assertIn('--name PATTERN, --search PATTERN', output,
                      '--help must show --name as primary with --search as alias')

    def test_grep_flag_in_help(self):
        """--help must document --grep."""
        output = self._get_help_output()
        self.assertIn('--grep PATTERN', output,
                      '--help must document --grep flag')

    def test_search_deprecated_note_in_help(self):
        """--help must mention that --search is a deprecated alias."""
        output = self._get_help_output()
        self.assertIn('deprecated alias', output,
                      '--help must note that --search is deprecated')


if __name__ == '__main__':
    unittest.main()
