"""Tests for help rendering adapter."""

import unittest
import sys
import io
from pathlib import Path
from contextlib import redirect_stdout

# Add parent directory to path to import reveal
sys.path.insert(0, str(Path(__file__).parent.parent))

from reveal.rendering.adapters.help import (
    _render_help_list_mode,
    _render_help_static_guide,
    _render_help_adapter_summary,
    _render_help_section,
    _render_help_adapter_specific,
    _render_adapter_schema,
    _select_index_entries,
    render_help,
    help_error_exit_code,
)


def capture_stdout(func, *args, **kwargs):
    """Capture stdout from a function call."""
    output = io.StringIO()
    with redirect_stdout(output):
        func(*args, **kwargs)
    return output.getvalue()


class TestSelectIndexEntries(unittest.TestCase):
    """Test grouping + dedup of guide entries for the help index."""

    def test_groups_by_category(self):
        entries = [
            {'topic': 'agent', 'file': 'AGENT_HELP.md', 'description': 'd', 'category': 'ai_guides', 'token_estimate': '~40,000'},
            {'topic': 'ux', 'file': 'guides/UX_GUIDE.md', 'description': 'd', 'category': 'best_practices', 'token_estimate': '~3,000'},
        ]
        grouped = _select_index_entries(entries)
        self.assertIn('ai_guides', grouped)
        self.assertIn('best_practices', grouped)
        self.assertEqual(len(grouped['ai_guides']), 1)
        self.assertEqual(grouped['ai_guides'][0]['topic'], 'agent')

    def test_dedupes_by_file_prefers_shortest_topic(self):
        """When two topics point at the same file, the index lists one (shortest topic)."""
        entries = [
            {'topic': 'mcp-setup', 'file': 'guides/MCP_SETUP.md', 'description': 'd', 'category': 'ai_guides', 'token_estimate': '~2,000'},
            {'topic': 'mcp', 'file': 'guides/MCP_SETUP.md', 'description': 'd', 'category': 'ai_guides', 'token_estimate': '~2,000'},
        ]
        grouped = _select_index_entries(entries)
        self.assertEqual(len(grouped['ai_guides']), 1)
        self.assertEqual(grouped['ai_guides'][0]['topic'], 'mcp')

    def test_uncategorized_entries_excluded(self):
        """Entries with empty category are not shown in the index."""
        entries = [
            {'topic': 'orphan', 'file': 'X.md', 'description': '', 'category': '', 'token_estimate': ''},
        ]
        self.assertEqual(_select_index_entries(entries), {})


class TestAdapterStability(unittest.TestCase):
    """Stability badge is derived from each adapter's own STABILITY attr, never
    a hand-maintained set — a new adapter can't silently mislabel (BACK-688)."""

    def setUp(self):
        import reveal.adapters  # noqa: F401 — trigger all @register_adapter
        from reveal.adapters.base import _ADAPTER_REGISTRY
        self.registry = _ADAPTER_REGISTRY

    def test_badge_derived_from_registry(self):
        from reveal.rendering.adapters.help import _get_stability_badge
        # Stable and project adapters keep their distinct badges.
        self.assertEqual(_get_stability_badge('ast'), '🟢')
        self.assertEqual(_get_stability_badge('claude'), '🎓')
        self.assertEqual(_get_stability_badge('ssl'), '🟡')

    def test_codex_and_depends_are_beta_not_experimental(self):
        # Regression: both fell through the old hand-maintained sets and rendered
        # 🔴 Experimental despite shipping guides/schemas (BACK-688).
        from reveal.adapters.base import Stability
        from reveal.rendering.adapters.help import _adapter_stability, _get_stability_badge
        for scheme in ('codex', 'depends'):
            self.assertEqual(_adapter_stability(scheme), Stability.BETA)
            self.assertEqual(_get_stability_badge(scheme), '🟡')

    def test_no_public_adapter_is_accidentally_experimental(self):
        # Nothing shipped in-tree should carry the 🔴 badge by omission. A truly
        # experimental adapter must declare STABILITY = Stability.EXPERIMENTAL.
        from reveal.adapters.base import Stability
        from reveal.rendering.adapters.help import _adapter_stability
        internal = {'demo', 'test'}
        experimental = [
            s for s in self.registry
            if s not in internal and _adapter_stability(s) == Stability.EXPERIMENTAL
        ]
        self.assertEqual(experimental, [])

    def test_unknown_scheme_defaults_to_beta(self):
        from reveal.adapters.base import Stability
        from reveal.rendering.adapters.help import _adapter_stability
        self.assertEqual(_adapter_stability('nonexistent-scheme'), Stability.BETA)


class TestRenderHelpListMode(unittest.TestCase):
    """Test help topic list rendering."""

    def test_empty_data(self):
        """Should handle empty data gracefully."""
        output = capture_stdout(_render_help_list_mode, {})
        self.assertIn('Reveal Help System', output)
        self.assertIn('Progressive, explorable documentation', output)
        self.assertIn('reveal help://<topic>', output)

    def test_with_adapters(self):
        """Should render adapters section."""
        data = {
            'adapters': [
                {'scheme': 'ast', 'has_help': True, 'description': 'AST queries'},
                {'scheme': 'python', 'has_help': True, 'description': 'Python modules'},
            ]
        }
        output = capture_stdout(_render_help_list_mode, data)
        self.assertIn('DYNAMIC CONTENT', output)
        self.assertIn('URI Adapters (2 registered)', output)
        self.assertIn('ast://', output)
        self.assertIn('AST queries', output)
        self.assertIn('python://', output)
        self.assertIn('Python modules', output)

    def test_adapter_without_help_filtered(self):
        """Should only show adapters with help."""
        data = {
            'adapters': [
                {'scheme': 'ast', 'has_help': True, 'description': 'AST queries'},
                {'scheme': 'other', 'has_help': False, 'description': 'Other'},
            ]
        }
        output = capture_stdout(_render_help_list_mode, data)
        self.assertIn('URI Adapters (1 registered)', output)
        self.assertIn('ast://', output)
        self.assertNotIn('other://', output)

    def test_with_static_guides(self):
        """Should render static guides section using metadata from each entry."""
        data = {
            'static_guides': [
                {'topic': 'agent', 'file': 'AGENT_HELP.md',
                 'description': 'Complete agent guide', 'category': 'ai_guides',
                 'token_estimate': '~40,000'},
                {'topic': 'python-guide', 'file': 'adapters/PYTHON_ADAPTER_GUIDE.md',
                 'description': 'Python adapter deep dive', 'category': 'feature_guides',
                 'token_estimate': '~2,500'},
                {'topic': 'anti-patterns', 'file': 'AGENT_HELP.md',
                 'description': 'Common mistakes', 'category': 'best_practices',
                 'token_estimate': '~40,000'},
            ]
        }
        output = capture_stdout(_render_help_list_mode, data)
        self.assertIn('STATIC GUIDES', output)
        self.assertIn('For AI Agents', output)
        self.assertIn('agent', output)
        self.assertIn('~40,000', output)
        self.assertIn('--agent-help flag', output)  # _TOPIC_ANNOTATIONS for 'agent'
        self.assertIn('Feature Guides', output)
        self.assertIn('python-guide', output)
        self.assertIn('Best Practices', output)
        self.assertIn('anti-patterns', output)

    def test_static_guide_entries_have_details_line(self):
        """BACK-929: guide entries must carry the same actionable 'Details:
        reveal help://<topic>' pointer that adapter entries already get --
        previously only adapters had it, an asymmetry with no reason behind
        it."""
        data = {
            'static_guides': [
                {'topic': 'python-guide', 'file': 'adapters/PYTHON_ADAPTER_GUIDE.md',
                 'description': 'Python adapter deep dive', 'category': 'feature_guides',
                 'token_estimate': '~2,500'},
            ]
        }
        output = capture_stdout(_render_help_list_mode, data)
        self.assertIn('Details: reveal help://python-guide', output)

    def test_navigation_tips(self):
        """Should include navigation tips."""
        output = capture_stdout(_render_help_list_mode, {})
        self.assertIn('Navigation Tips', output)
        self.assertIn('reveal help://', output)
        self.assertIn('reveal --agent-help', output)
        self.assertIn('reveal help://adapters', output)
        self.assertIn('reveal help://schemas', output)
        self.assertIn('reveal help://examples', output)


class TestRenderHelpStaticGuide(unittest.TestCase):
    """Test static guide rendering."""

    def test_renders_content(self):
        """Should render static guide content."""
        data = {
            'topic': 'agent',
            'file': 'agent.md',
            'content': '# Agent Guide\n\nSome content here.'
        }
        output = capture_stdout(_render_help_static_guide, data)
        self.assertIn('Source: agent.md', output)
        self.assertIn('Type: Static Guide', output)
        self.assertIn('reveal help://agent', output)
        self.assertIn('# Agent Guide', output)
        self.assertIn('Some content here.', output)

    def test_error_handling(self):
        """Should handle error data and exit."""
        data = {
            'error': True,
            'message': 'File not found'
        }
        with self.assertRaises(SystemExit):
            _render_help_static_guide(data)

    def test_renders_note_cross_signpost(self):
        """BACK-847: help://schema (singular) must cross-signpost help://schemas
        (plural, unrelated) in text output, not just JSON."""
        data = {
            'topic': 'schema',
            'file': 'guides/SCHEMA_VALIDATION_HELP.md',
            'content': '# Schema Validation',
            'note': 'Looking for machine-readable adapter query schemas '
                     'instead? That is help://schemas/all (plural).',
            'next': ['reveal help://schemas/all'],
        }
        output = capture_stdout(_render_help_static_guide, data)
        self.assertIn('help://schemas/all (plural)', output)
        self.assertIn('## Next', output)

    def test_no_note_key_omits_note_line(self):
        """No 'note' key -> no 'Note:' line (most static guides have none)."""
        data = {
            'topic': 'agent',
            'file': 'agent.md',
            'content': '# Agent Guide',
        }
        output = capture_stdout(_render_help_static_guide, data)
        self.assertNotIn('Note:', output)


class TestRenderHelpAdapterSummary(unittest.TestCase):
    """Test adapter summary rendering."""

    def test_renders_adapter_list(self):
        """Should render list of all adapters."""
        data = {
            'count': 2,
            'adapters': {
                'ast': {
                    'description': 'Query code by AST',
                    'syntax': 'ast://path/filter',
                    'example': 'ast://. lines>50'
                },
                'python': {
                    'description': 'Explore Python modules',
                    'syntax': 'python://module.path',
                }
            }
        }
        output = capture_stdout(_render_help_adapter_summary, data)
        self.assertIn('URI Adapters (2 total)', output)
        self.assertIn('## ast://', output)
        self.assertIn('Query code by AST', output)
        self.assertIn('Syntax: ast://path/filter', output)
        self.assertIn('Example: ast://. lines>50', output)
        self.assertIn('## python://', output)
        self.assertIn('Explore Python modules', output)

    def test_adapter_without_example(self):
        """Should handle adapters without examples."""
        data = {
            'count': 1,
            'adapters': {
                'env': {
                    'description': 'Environment variables',
                    'syntax': 'env://VAR',
                }
            }
        }
        output = capture_stdout(_render_help_adapter_summary, data)
        self.assertIn('env://', output)
        self.assertIn('Environment variables', output)
        self.assertNotIn('Example:', output)


class TestRenderHelpSection(unittest.TestCase):
    """Test help section rendering."""

    def test_workflows_section(self):
        """Should render workflows section."""
        data = {
            'adapter': 'ast',
            'section': 'workflows',
            'content': [
                {
                    'name': 'Find Complex Functions',
                    'scenario': 'Identify functions needing refactoring',
                    'steps': ['Step 1', 'Step 2']
                }
            ]
        }
        output = capture_stdout(_render_help_section, data)
        self.assertIn('ast:// - workflows', output)
        self.assertIn('Find Complex Functions', output)
        self.assertIn('Scenario: Identify functions needing refactoring', output)
        self.assertIn('Step 1', output)
        self.assertIn('Step 2', output)

    def test_try_now_section(self):
        """Should render try-now section."""
        data = {
            'adapter': 'python',
            'section': 'try-now',
            'content': ['reveal python://os', 'reveal python://sys']
        }
        output = capture_stdout(_render_help_section, data)
        self.assertIn('python:// - try-now', output)
        self.assertIn('Run these in your current directory:', output)
        self.assertIn('reveal python://os', output)
        self.assertIn('reveal python://sys', output)

    def test_anti_patterns_section(self):
        """Should render anti-patterns section."""
        data = {
            'adapter': 'ast',
            'section': 'anti-patterns',
            'content': [
                {
                    'bad': 'grep -r "def"',
                    'good': 'ast://. type=function',
                    'why': 'Grep misses context'
                }
            ]
        }
        output = capture_stdout(_render_help_section, data)
        self.assertIn('ast:// - anti-patterns', output)
        self.assertIn('X grep -r "def"', output)
        self.assertIn('* ast://. type=function', output)
        self.assertIn('Why: Grep misses context', output)

    def test_section_breadcrumbs(self):
        """Should include breadcrumbs back to full help."""
        data = {
            'adapter': 'ast',
            'section': 'workflows',
            'content': []
        }
        output = capture_stdout(_render_help_section, data)
        self.assertIn('See Full Help', output)
        self.assertIn('reveal help://ast', output)

    def test_error_handling(self):
        """Should handle error data and exit."""
        data = {
            'error': True,
            'message': 'Section not found'
        }
        with self.assertRaises(SystemExit):
            _render_help_section(data)


class TestRenderHelpAdapterSpecific(unittest.TestCase):
    """Test adapter-specific help rendering."""

    def test_minimal_adapter_help(self):
        """Should render minimal adapter help."""
        data = {
            'scheme': 'test',
            'description': 'Test adapter'
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('# test:// - Test adapter', output)
        self.assertIn('**Source:** test.py adapter (dynamic)', output)
        self.assertIn('**Type:** URI Adapter', output)
        self.assertIn('**Access:** reveal help://test', output)

    def test_with_syntax(self):
        """Should render syntax if provided."""
        data = {
            'scheme': 'ast',
            'description': 'AST queries',
            'syntax': 'ast://path/filter'
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('**Syntax:** `ast://path/filter`', output)

    def test_with_operators(self):
        """Should render operators section."""
        data = {
            'scheme': 'ast',
            'description': 'AST queries',
            'operators': {
                '>': 'Greater than',
                '<': 'Less than',
                '=': 'Equal to'
            }
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('## Operators', output)
        self.assertIn('>    - Greater than', output)
        self.assertIn('<    - Less than', output)
        self.assertIn('=    - Equal to', output)

    def test_with_filters(self):
        """Should render filters section."""
        data = {
            'scheme': 'ast',
            'description': 'AST queries',
            'filters': {
                'lines': 'Line count',
                'complexity': 'Cyclomatic complexity'
            }
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('## Filters', output)
        self.assertIn('lines        - Line count', output)
        self.assertIn('complexity   - Cyclomatic complexity', output)

    def test_with_features(self):
        """Should render features section."""
        data = {
            'scheme': 'ast',
            'description': 'AST queries',
            'features': ['Feature 1', 'Feature 2']
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('## Features', output)
        self.assertIn('* Feature 1', output)
        self.assertIn('* Feature 2', output)

    def test_with_categories(self):
        """Should render categories section."""
        data = {
            'scheme': 'env',
            'description': 'Environment variables',
            'categories': {
                'PATH': 'System paths',
                'USER': 'User info'
            }
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('## Categories', output)
        self.assertIn('PATH         - System paths', output)
        self.assertIn('USER         - User info', output)

    def test_with_examples_dict(self):
        """Should render examples as dict."""
        data = {
            'scheme': 'ast',
            'description': 'AST queries',
            'examples': [
                {'uri': 'ast://. lines>50', 'description': 'Find large files'},
                {'uri': 'ast://. type=class', 'description': 'Find classes'}
            ]
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('## Examples', output)
        self.assertIn('ast://. lines>50', output)
        self.assertIn('-> Find large files', output)
        self.assertIn('ast://. type=class', output)
        self.assertIn('-> Find classes', output)

    def test_with_examples_string(self):
        """Should render examples as strings."""
        data = {
            'scheme': 'python',
            'description': 'Python modules',
            'examples': ['python://os', 'python://sys']
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('## Examples', output)
        self.assertIn('python://os', output)
        self.assertIn('python://sys', output)

    def test_with_try_now(self):
        """Should render try now section."""
        data = {
            'scheme': 'ast',
            'description': 'AST queries',
            'try_now': ['reveal ast://. lines>50', 'reveal ast://. type=function']
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('## Try Now', output)
        self.assertIn('Run these in your current directory:', output)
        self.assertIn('reveal ast://. lines>50', output)

    def test_with_workflows(self):
        """Should render workflows section."""
        data = {
            'scheme': 'ast',
            'description': 'AST queries',
            'workflows': [
                {
                    'name': 'Find Complex Code',
                    'scenario': 'Identify refactoring targets',
                    'steps': ['Step 1', 'Step 2']
                }
            ]
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('## Workflows', output)
        self.assertIn('**Find Complex Code**', output)
        self.assertIn('Scenario: Identify refactoring targets', output)
        self.assertIn('Step 1', output)

    def test_with_anti_patterns(self):
        """Should render anti-patterns section."""
        data = {
            'scheme': 'ast',
            'description': 'AST queries',
            'anti_patterns': [
                {
                    'bad': 'Bad approach',
                    'good': 'Good approach',
                    'why': 'Reason'
                }
            ]
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn("Don't Do This", output)
        self.assertIn('X Bad approach', output)
        self.assertIn('* Good approach', output)
        self.assertIn('Why: Reason', output)

    def test_with_notes(self):
        """Should render notes section."""
        data = {
            'scheme': 'ast',
            'description': 'AST queries',
            'notes': ['Note 1', 'Note 2']
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('## Notes', output)
        self.assertIn('* Note 1', output)
        self.assertIn('* Note 2', output)

    def test_with_output_formats(self):
        """Should render output formats."""
        data = {
            'scheme': 'ast',
            'description': 'AST queries',
            'output_formats': ['text', 'json', 'grep']
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('**Output formats:** text, json, grep', output)

    def test_with_see_also(self):
        """Should render see also section."""
        data = {
            'scheme': 'ast',
            'description': 'AST queries',
            'see_also': ['python://', 'help://tricks']
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('## See Also', output)
        self.assertIn('* python://', output)
        self.assertIn('* help://tricks', output)

    def test_renders_next_pointers(self):
        """BACK-926: 'next' pointers (now sourced from _related_adapters) render via _render_schema_next."""
        data = {
            'scheme': 'ast',
            'description': 'AST queries',
            'next': ['reveal help://calls', 'reveal help://diff'],
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('## Next', output)
        self.assertIn('reveal help://calls', output)
        self.assertIn('reveal help://diff', output)

    def test_no_next_renders_nothing_extra(self):
        """No 'next' key means _render_schema_next is a silent no-op."""
        data = {
            'scheme': 'ast',
            'description': 'AST queries',
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertNotIn('## Next', output)

    def test_error_handling(self):
        """Should handle error data and exit."""
        data = {
            'error': True,
            'message': 'Adapter not found'
        }
        with self.assertRaises(SystemExit):
            _render_help_adapter_specific(data)


class TestRenderHelp(unittest.TestCase):
    """Test main render_help entry point."""

    def test_json_output(self):
        """Should render JSON when requested."""
        data = {'type': 'test', 'content': 'data'}
        output = capture_stdout(render_help, data, 'json', False)
        self.assertIn('"type"', output)
        self.assertIn('"content"', output)
        self.assertIn('test', output)

    def test_list_mode(self):
        """Should render list mode."""
        data = {}
        output = capture_stdout(render_help, data, 'text', True)
        self.assertIn('Reveal Help System', output)
        self.assertIn('Progressive, explorable documentation', output)

    def test_static_guide_type(self):
        """Should dispatch to static guide renderer."""
        data = {
            'type': 'static_guide',
            'topic': 'agent',
            'file': 'agent.md',
            'content': 'Guide content'
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('Source: agent.md', output)
        self.assertIn('Guide content', output)

    def test_adapter_summary_type(self):
        """Should dispatch to adapter summary renderer."""
        data = {
            'type': 'adapter_summary',
            'count': 1,
            'adapters': {
                'test': {
                    'description': 'Test',
                    'syntax': 'test://'
                }
            }
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('URI Adapters (1 total)', output)

    def test_help_section_type(self):
        """Should dispatch to help section renderer."""
        data = {
            'type': 'help_section',
            'adapter': 'ast',
            'section': 'workflows',
            'content': []
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('ast:// - workflows', output)

    def test_default_adapter_specific(self):
        """Should default to adapter-specific renderer for unknown types."""
        data = {
            'type': 'unknown',
            'scheme': 'test',
            'description': 'Test adapter'
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('# test:// - Test adapter', output)

    def test_no_type_defaults_to_adapter_specific(self):
        """Should default to adapter-specific when type is missing."""
        data = {
            'scheme': 'test',
            'description': 'Test adapter'
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('# test:// - Test adapter', output)

    def test_json_real_error_exits_nonzero(self):
        """BACK-697: a genuine error dict must exit 1 in JSON, matching text mode."""
        data = {
            'type': 'adapter_schema',
            'adapter': 'nonexistent',
            'error': 'Unknown adapter',
            'message': "No adapter named 'nonexistent'",
            'available_adapters': ['ast', 'git'],
        }
        with self.assertRaises(SystemExit) as ctx:
            capture_stdout(render_help, data, 'json', False)
        self.assertEqual(ctx.exception.code, 1)

    def test_json_catalog_listing_exits_zero(self):
        """Bare help://examples is a navigational listing, not an error — exit 0."""
        data = {
            'type': 'query_recipes',
            'task': '',
            'error': 'No task specified',
            'message': 'Specify a task. Available: security',
            'available_tasks': ['security'],
        }
        output = capture_stdout(render_help, data, 'json', False)
        self.assertIn('"task"', output)

    def test_json_schema_catalog_listing_exits_zero(self):
        """Bare help://schemas listing (no 'error' key at all) must still exit 0."""
        data = {
            'type': 'adapter_schema',
            'adapter': '',
            'available_adapters': ['ast', 'git'],
        }
        output = capture_stdout(render_help, data, 'json', False)
        self.assertIn('"available_adapters"', output)

    def test_text_schema_catalog_listing_does_not_crash(self):
        """Bare help://schemas listing must render as a catalog, not raise KeyError.

        Regression: the adapter-side dict for a bare `help://schemas` lookup
        omitted the `error` key, so `_is_catalog_listing()` (which requires
        `'error' in data` before checking `type`/`adapter`/`available_adapters`)
        returned False and `_render_schema_error` crashed on `data['message']`.
        """
        data = {
            'type': 'adapter_schema',
            'adapter': '',
            'error': 'No adapter specified',
            'available_adapters': ['ast', 'git'],
            'usage': 'reveal help://schemas/<adapter>',
            'examples': ['reveal help://schemas/ast'],
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('Available Adapters', output)

    def test_text_schema_catalog_listing_renders_singular_cross_signpost(self):
        """BACK-847: bare help://schemas must point an agent at help://schema
        (singular, the unrelated front-matter guide) rather than leaving the
        namespace collision to silently misinform."""
        data = {
            'type': 'adapter_schema',
            'adapter': '',
            'error': 'No adapter specified',
            'available_adapters': ['ast', 'git'],
            'usage': 'reveal help://schemas/<adapter>',
            'examples': ['reveal help://schemas/ast'],
            'note': 'Looking for markdown front-matter validation instead? '
                     'That is help://schema (singular).',
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('help://schema (singular)', output)

    def test_text_schemas_all_renders_singular_cross_signpost(self):
        """BACK-847: help://schemas/all must also cross-signpost help://schema."""
        data = {
            'type': 'adapter_schema_all',
            'thin': False,
            'adapter_count': 1,
            'adapters': {'ast': {'scheme': 'ast', 'uri_syntax': 'ast://<path>', 'description': 'AST'}},
            'note': 'Looking for markdown front-matter validation instead? '
                     'That is help://schema (singular).',
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('help://schema (singular)', output)

    def test_text_schema_renders_next_pointers(self):
        """BACK-845: JSON carries schema_data['next'] but text discarded it.

        _summarize_schema builds a 'next' pointer list to guide an agent
        deeper (e.g. into the /full drill-down); the text renderer must
        show it, not just JSON.
        """
        data = {
            'type': 'adapter_schema',
            'adapter': 'ast',
            'description': 'Test adapter',
            'next': ['reveal help://schemas/ast/ast_query', 'reveal help://schemas/ast/full'],
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('## Next', output)
        self.assertIn('reveal help://schemas/ast/ast_query', output)
        self.assertIn('reveal help://schemas/ast/full', output)

    def test_text_schema_no_next_key_omits_section(self):
        """No 'next' pointers computed (e.g. no example overflow) -> no '## Next' section."""
        data = {
            'type': 'adapter_schema',
            'adapter': 'claude',
            'description': 'Test adapter',
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertNotIn('## Next', output)

    def test_text_output_type_schema_renders_next_pointer(self):
        """BACK-845: the /<output_type> drill-down also carries a 'next' pointer back up."""
        data = {
            'type': 'adapter_schema',
            'adapter': 'ast',
            'output_type': 'ast_query',
            'detail': {'description': 'one output type'},
            'next': ['reveal help://schemas/ast'],
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('## Next', output)
        self.assertIn('reveal help://schemas/ast', output)

    def test_text_schemas_all_renders_every_adapter(self):
        """BACK-840: help://schemas/all in text format lists every adapter block."""
        data = {
            'type': 'adapter_schema_all',
            'thin': False,
            'adapter_count': 2,
            'adapters': {
                'ast': {'scheme': 'ast', 'uri_syntax': 'ast://<path>', 'description': 'AST queries',
                        'output_types': ['element'], 'query_params': ['type']},
                'git': {'scheme': 'git', 'uri_syntax': 'git://<path>', 'description': 'Git history'},
            },
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('## ast://', output)
        self.assertIn('## git://', output)
        self.assertIn('Output types: element', output)

    def test_text_schemas_index_is_compact_one_line_per_adapter(self):
        """BACK-840: help://schemas/index is the thin rung — no per-adapter detail."""
        data = {
            'type': 'adapter_schema_all',
            'thin': True,
            'adapter_count': 1,
            'adapters': {
                'ast': {'scheme': 'ast', 'uri_syntax': 'ast://<path>', 'description': 'AST queries'},
            },
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('Index', output)
        self.assertIn('ast', output)
        self.assertNotIn('Output types:', output)

    def test_text_help_rules_renders_categories_and_unambiguous_total(self):
        """BACK-846: help://rules text view. The total is spelled out because the
        --rules flag's 'Total: N rules (M opt-in)' uses N = enabled, not the total."""
        data = {
            'type': 'help_rules',
            'title': 'Rules',
            'rule_count': 3,
            'enabled_count': 2,
            'categories': {
                'b': [
                    {'code': 'B001', 'severity': 'high', 'enabled': True, 'message': 'bare except'},
                    {'code': 'B002', 'severity': 'low', 'enabled': False, 'message': 'opt in rule'},
                ],
            },
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('## B (2)', output)
        self.assertIn('B001', output)
        self.assertIn('[opt-in]', output)
        self.assertIn('3 rules (2 enabled, 1 opt-in', output)

    def test_text_help_languages_renders_both_tiers(self):
        """BACK-846: help://languages text view separates explicit vs fallback."""
        data = {
            'type': 'help_languages',
            'title': 'Languages',
            'language_count': 2,
            'explicit': [
                {'name': 'Python', 'extension': '.py',
                 'conformance_level': 'tier1-verified', 'content_dependent': False},
            ],
            'fallback': [{'name': 'Zig', 'extensions': ['.zig']}],
            'ambiguous_extensions': {},
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('Explicit Analyzers (1)', output)
        self.assertIn('tier1-verified', output)
        self.assertIn('Tree-sitter Fallback (1)', output)
        self.assertIn('Zig', output)

    def test_help_error_exit_code_real_error(self):
        data = {'type': 'help_section', 'error': 'Unknown adapter', 'message': 'x'}
        self.assertEqual(help_error_exit_code(data), 1)

    def test_help_error_exit_code_catalog_listing(self):
        data = {
            'type': 'query_recipes',
            'task': '',
            'error': 'No task specified',
            'available_tasks': ['security'],
        }
        self.assertEqual(help_error_exit_code(data), 0)

    def test_help_error_exit_code_no_error_key(self):
        self.assertEqual(help_error_exit_code({'type': 'help_quick'}), 0)


class TestRenderAdapterSchemaOutputTypeDrilldown(unittest.TestCase):
    """help://schemas/<adapter>/<output_type> drill-down (BACK-838 schemas tiering)."""

    def test_renders_description_and_fields(self):
        """Regression: the drill-down dict nests content under 'detail' —
        rendering must reach into it, not read top-level keys (which are
        absent for this shape and previously rendered a blank page)."""
        data = {
            'type': 'adapter_schema',
            'adapter': 'claude',
            'output_type': 'claude_exchanges',
            'detail': {
                'type': 'claude_exchanges',
                'description': 'Each human prompt paired with its answer',
                'schema': {
                    'type': 'object',
                    'properties': {
                        'exchange_count': {'type': 'integer'},
                        'exchanges': {
                            'type': 'array',
                            'description': 'message_index, prompt, answer',
                        },
                    },
                },
            },
            'next': ['reveal help://schemas/claude'],
        }
        output = capture_stdout(_render_adapter_schema, data)
        self.assertIn('claude:// Schema', output)
        self.assertIn('claude_exchanges', output)
        self.assertIn('Each human prompt paired with its answer', output)
        self.assertIn('exchange_count: integer', output)
        self.assertIn('exchanges: array — message_index, prompt, answer', output)

    def test_unknown_output_type_still_errors(self):
        """The error shape (no 'detail' key) must keep going through the
        existing error renderer, not the new drill-down path."""
        data = {
            'type': 'adapter_schema',
            'adapter': 'ssl',
            'error': 'Unknown output type',
            'message': "No output type 'bogus' on ssl://. Available: ssl_certificate",
            'available_output_types': ['ssl_certificate'],
            'next': ['reveal help://schemas/ssl'],
        }
        with self.assertRaises(SystemExit):
            capture_stdout(_render_adapter_schema, data)


class TestHelpQuick(unittest.TestCase):
    """BACK-043: help://quick returns orientation cheat-sheet."""

    def _get_quick(self):
        from reveal.adapters.help import HelpAdapter
        a = HelpAdapter('help://quick')
        return a.get_element('quick')

    def test_type_is_help_quick(self):
        result = self._get_quick()
        self.assertEqual(result.get('type'), 'help_quick')

    def test_has_commands_list(self):
        result = self._get_quick()
        self.assertIn('commands', result)
        self.assertGreaterEqual(len(result['commands']), 5)

    def test_each_command_has_cmd_and_description(self):
        result = self._get_quick()
        for item in result['commands']:
            self.assertIn('cmd', item)
            self.assertIn('description', item)
            self.assertTrue(item['cmd'])
            self.assertTrue(item['description'])

    def test_has_next_steps(self):
        result = self._get_quick()
        self.assertIn('next_steps', result)
        self.assertTrue(result['next_steps'])

    def test_next_steps_points_to_examples_index(self):
        """BACK-690: quick teased one recipe (examples/security) but never
        the help://examples index of all task categories — must point to both."""
        result = self._get_quick()
        steps = ' '.join(result['next_steps'])
        self.assertIn('help://examples ', steps, 'missing pointer to the examples index')
        self.assertIn('help://examples/security', steps)

    def test_renderer_produces_output(self):
        result = self._get_quick()
        output = capture_stdout(render_help, result, 'text', False)
        self.assertIn('reveal', output.lower())
        # Should include at least one command
        self.assertTrue(any(c['cmd'] in output for c in result['commands']))

    def test_json_format_returns_raw(self):
        result = self._get_quick()
        output = capture_stdout(render_help, result, 'json', False)
        import json
        data = json.loads(output)
        self.assertEqual(data['type'], 'help_quick')

    def test_command_flags_are_recognized_by_cli(self):
        """BACK-329: no quick-ref command may use a flag the CLI parser rejects."""
        import re
        from reveal.cli.parser import create_argument_parser
        from reveal import __version__

        result = self._get_quick()
        parser = create_argument_parser(__version__)
        known_flags = {opt for action in parser._actions for opt in action.option_strings}

        sources = [(item['cmd'], 'commands') for item in result.get('commands', [])]
        sources += [(item['example'], 'decision_tree') for item in result.get('decision_tree', [])]

        for cmd, section in sources:
            for flag in re.findall(r'(--[\w-]+)', cmd):
                self.assertIn(
                    flag, known_flags,
                    f"help://quick {section} entry uses unrecognized flag {flag!r}: {cmd!r}",
                )


class TestHelpQuickRegistryDriven(unittest.TestCase):
    """BACK-390 M4: help://quick commands are derived from the adapter registry,
    not hand-maintained, so they can't drift and never omit registered adapters
    (including project-local plugins)."""

    def _get_quick(self):
        from reveal.adapters.help import HelpAdapter
        a = HelpAdapter('help://quick')
        return a.get_element('quick')

    def test_commands_include_a_ranked_adapter(self):
        # 'ast' is top-ranked in _QUICK_RANK and always registered — its
        # get_help()-derived command must appear, proving derivation happened.
        result = self._get_quick()
        cmds = [c['cmd'] for c in result['commands']]
        self.assertTrue(any('ast://' in c for c in cmds))

    def test_commands_reflect_live_get_help_description(self):
        # The description in the quick block must match the adapter's own
        # get_help() output, not a hardcoded copy that can drift.
        from reveal.adapters.help import HelpAdapter
        from reveal.adapters.registry import _ADAPTER_REGISTRY
        result = self._get_quick()
        ast_cmd = next(c for c in result['commands'] if 'ast://' in c['cmd'])
        live_description = _ADAPTER_REGISTRY['ast'].get_help()['description']
        self.assertEqual(ast_cmd['description'], live_description)

    def test_unregistered_scheme_never_appears(self):
        result = self._get_quick()
        cmds = ' '.join(c['cmd'] for c in result['commands'])
        self.assertNotIn('postgres://', cmds)

    def test_new_adapter_appears_without_rank_hint(self):
        # An adapter with no _QUICK_RANK entry should still be eligible
        # (sorts after ranked ones) rather than silently excluded — this is
        # the plugin-visibility guarantee M4 asked for.
        from reveal.adapters.help import HelpAdapter
        adapter = HelpAdapter()
        original_rank = dict(adapter._QUICK_RANK)
        original_count = adapter._QUICK_COMMAND_COUNT
        try:
            # Give every real ranked scheme a rank so far back that our
            # fake unranked one (default rank 100) would win a slot.
            adapter._QUICK_RANK = {k: 1000 for k in original_rank}
            adapter._QUICK_COMMAND_COUNT = len(original_rank) + 3
            commands = adapter._get_quick_commands()
        finally:
            adapter._QUICK_RANK = original_rank
            adapter._QUICK_COMMAND_COUNT = original_count
        cmds = ' '.join(c['cmd'] for c in commands)
        # Unranked real adapters (e.g. env, json, sqlite) should now be pulled
        # in ahead of nothing, proving unranked entries aren't dropped.
        self.assertTrue(any(s in cmds for s in ('env://', 'json://', 'sqlite://')))


class TestRenderHelpRelationships(unittest.TestCase):
    """Tests for help://relationships renderer."""

    def _get_relationships(self):
        from reveal.adapters.help import HelpAdapter
        adapter = HelpAdapter('relationships')
        return adapter.get_element('relationships')

    def test_relationships_type(self):
        result = self._get_relationships()
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'help_relationships')

    def test_relationships_has_clusters(self):
        result = self._get_relationships()
        clusters = result.get('clusters', [])
        self.assertGreaterEqual(len(clusters), 4)

    def test_relationships_has_power_pairs(self):
        result = self._get_relationships()
        power_pairs = result.get('power_pairs', [])
        self.assertGreaterEqual(len(power_pairs), 4)
        for pair in power_pairs:
            self.assertIn('adapters', pair)
            self.assertIn('description', pair)
            self.assertIn('example', pair)

    def test_relationships_clusters_have_required_keys(self):
        result = self._get_relationships()
        for cluster in result['clusters']:
            self.assertIn('name', cluster)
            self.assertIn('adapters', cluster)
            self.assertIn('pairs', cluster)
            self.assertGreater(len(cluster['adapters']), 0)

    def test_render_relationships_text_output(self):
        from reveal.rendering.adapters.help import _render_help_relationships
        result = self._get_relationships()
        output = capture_stdout(_render_help_relationships, result)
        self.assertIn('Adapter Ecosystem', output)
        self.assertIn('Code Analysis', output)
        self.assertIn('Infrastructure', output)
        self.assertIn('Power Pairs', output)
        self.assertIn('ast://', output)
        self.assertIn('calls://', output)
        self.assertIn('nginx://', output)
        self.assertIn('ssl://', output)

    def test_render_via_render_help_dispatch(self):
        result = self._get_relationships()
        output = capture_stdout(render_help, result, 'text', False)
        self.assertIn('Adapter Ecosystem', output)
        self.assertIn('Power Pairs', output)

    def test_json_format(self):
        import json
        result = self._get_relationships()
        output = capture_stdout(render_help, result, 'json', False)
        data = json.loads(output)
        self.assertEqual(data['type'], 'help_relationships')
        self.assertIn('clusters', data)
        self.assertIn('power_pairs', data)

    def test_all_adapters_in_relationships(self):
        """Every registered public adapter should appear in at least one cluster."""
        from reveal.adapters.base import _ADAPTER_REGISTRY
        from reveal.adapters.help import HelpAdapter
        result = self._get_relationships()
        adapters_in_clusters = {
            a for cluster in result['clusters']
            for a in cluster['adapters']
        }
        all_registered = set(_ADAPTER_REGISTRY.keys()) - HelpAdapter._INTERNAL_ADAPTERS
        missing = all_registered - adapters_in_clusters
        self.assertEqual(missing, set(), f"Registered adapters missing from relationship clusters: {missing}")

    def test_related_adapters_derived_from_relationship_pairs(self):
        """BACK-926: _related_adapters(scheme) is now derived straight from
        _get_adapter_relationships()'s pairs, so it can no longer disagree
        with that data the way the old hand-maintained `related` dict did
        (BACK-585 found it said stats -> [ast, diff] while relationships had
        no stats-diff pair at all).
        """
        from reveal.adapters.help import HelpAdapter
        adapter = HelpAdapter()
        # ssl should point to domain and nginx (infrastructure cluster)
        self.assertEqual(
            set(adapter._related_adapters('ssl')),
            {'reveal help://domain', 'reveal help://nginx'},
        )
        self.assertIn('reveal help://mysql', adapter._related_adapters('sqlite'))
        self.assertIn('reveal help://git', adapter._related_adapters('claude'))

    def test_every_public_adapter_has_resolvable_related_next_pointer(self):
        """BACK-585/BACK-926: every public adapter must get at least one
        'next' pointer from _related_adapters, and every such pointer must
        resolve to a real help:// topic — the correctness check the old
        presence-only breadcrumb test never made (it only checked *some*
        text was printed, not that the printed topic actually existed).
        """
        from reveal.adapters.help import HelpAdapter
        from reveal.adapters.base import _ADAPTER_REGISTRY
        adapter = HelpAdapter()
        topics = set(adapter._list_topics())
        public_schemes = set(_ADAPTER_REGISTRY.keys()) - HelpAdapter._INTERNAL_ADAPTERS
        for scheme in sorted(public_schemes):
            related = adapter._related_adapters(scheme)
            self.assertTrue(related, f"help://{scheme} has no related-adapter 'next' pointer")
            for pointer in related:
                self.assertTrue(pointer.startswith('reveal help://'), pointer)
                target = pointer.removeprefix('reveal help://')
                self.assertIn(target, topics, f"{pointer} does not resolve to a real help:// topic")


class TestSeeAlsoReachableThroughGuideShadow(unittest.TestCase):
    """BACK-936: help://<scheme> resolves to a same-named static guide for 23
    of 24 adapters, which used to mean get_help()'s 'see_also' was dead data
    with no reachable route at all (same class of bug BACK-926 fixed for
    'next' — a presence-only check would not have caught this, since
    get_help() itself worked fine when called directly; it just never ran
    through the live help:// dispatch path).
    """

    def test_shadowed_adapter_see_also_surfaces_on_its_guide(self):
        from reveal.adapters.help import HelpAdapter
        from reveal.adapters.base import _ADAPTER_REGISTRY
        adapter = HelpAdapter()
        checked_at_least_one = False
        for scheme, adapter_class in _ADAPTER_REGISTRY.items():
            if scheme not in adapter.help_topics:
                continue  # not shadowed by a guide -- not this bug's scenario
            if not hasattr(adapter_class, 'get_help'):
                continue
            expected = (adapter_class.get_help() or {}).get('see_also')
            if not expected:
                continue
            checked_at_least_one = True
            result = adapter._load_static_help(scheme)
            self.assertEqual(
                result.get('see_also'), expected,
                f"help://{scheme} (guide-shadowed) does not surface its "
                f"adapter's get_help()['see_also']",
            )
        self.assertTrue(checked_at_least_one, "no shadowed adapter with a see_also was found to test")

    def test_see_also_renders_as_text_for_a_shadowed_adapter(self):
        """Reachability, not just presence: the text renderer must actually
        print the section for a real help://<scheme> call, not just carry it
        in the data dict."""
        from reveal.adapters.help import HelpAdapter
        adapter = HelpAdapter()
        result = adapter._load_static_help('ast')
        self.assertIn('see_also', result)
        output = capture_stdout(render_help, result, 'text', False)
        self.assertIn('## See Also', output)

    def test_help_help_cross_signposts_bare_index(self):
        """BACK-930: 'help' is both the meta-guide explaining the help system
        and the help:// adapter's own scheme, so help://help must redirect an
        agent who actually wanted the bare topic index (reveal help://) --
        same collision class as BACK-847's schema/schemas pair. Also checks
        the curated 'next' pointer (help -> reveal) survives the redirect
        being added, since it's appended rather than overwritten."""
        from reveal.adapters.help import HelpAdapter
        adapter = HelpAdapter()
        result = adapter._load_static_help('help')
        self.assertIn('reveal help://', result.get('note', ''))
        self.assertEqual(result['next'][0], 'reveal help://')
        self.assertIn('reveal help://reveal', result['next'])
        output = capture_stdout(render_help, result, 'text', False)
        self.assertIn('Note:', output)

    def test_meta_guide_without_matching_scheme_gets_no_see_also(self):
        """No-op check: guides that aren't adapter scheme names (tricks,
        schema, ...) must not gain a spurious 'see_also' key."""
        from reveal.adapters.help import HelpAdapter
        from reveal.adapters.base import _ADAPTER_REGISTRY
        adapter = HelpAdapter()
        result = adapter._load_static_help('tricks')
        self.assertNotIn('tricks', _ADAPTER_REGISTRY)
        self.assertNotIn('see_also', result)


class TestAntiPatternsRendering(unittest.TestCase):
    """S1.3: help://anti-patterns text rendering must produce non-empty non-adapter output."""

    def test_static_help_type_dispatches_to_static_guide_renderer(self):
        """'static_help' type must render via static guide renderer, not fall through to adapter-specific."""
        data = {
            'type': 'static_help',
            'topic': 'anti-patterns',
            'content': '## Common Mistakes\n\nDo not do X.',
            'note': 'Extracted from AGENT_HELP.md — use help://agent for the complete guide.',
        }
        output = capture_stdout(render_help, data, 'text', False)
        self.assertIn('Common Mistakes', output)
        # adapter-specific renderer would show "# anti-patterns://" — confirm it does NOT
        self.assertNotIn('# anti-patterns://', output)

    def test_anti_patterns_real_content_renders_as_text(self):
        """help://anti-patterns full pipeline produces readable markdown text."""
        from reveal.adapters.help import HelpAdapter
        adapter = HelpAdapter('help://anti-patterns')
        result = adapter.get_element('anti-patterns')
        self.assertIsNotNone(result)
        output = capture_stdout(render_help, result, 'text', False)
        self.assertIn('Common Mistakes', output)
        self.assertGreater(len(output.strip()), 100)


class TestHelpQuickIndex(unittest.TestCase):
    """S1.4: help:// index SPECIAL TOPICS must list 'quick'; Navigation Tips must show help://quick."""

    def _get_index_output(self):
        from reveal.adapters.help import HelpAdapter
        adapter = HelpAdapter('help://')
        result = adapter.get_structure()
        return capture_stdout(render_help, result, 'text', True)

    def test_special_topics_lists_quick(self):
        output = self._get_index_output()
        self.assertIn('quick', output)

    def test_navigation_tips_bootstrap_shows_help_quick(self):
        output = self._get_index_output()
        self.assertIn('help://quick', output)

    def test_navigation_tips_bootstrap_still_shows_agent_help(self):
        output = self._get_index_output()
        self.assertIn('--agent-help', output)


class TestClaudeRowInQuickHelp(unittest.TestCase):
    """S1.2: help://quick claude decision_tree row must reference sessions/?search=."""

    def _get_quick(self):
        from reveal.adapters.help import HelpAdapter
        return HelpAdapter('help://quick').get_element('quick')

    def test_claude_row_example_uses_sessions_search(self):
        result = self._get_quick()
        claude_rows = [r for r in result['decision_tree'] if r['use'] == 'claude://']
        self.assertEqual(len(claude_rows), 1, 'Expected exactly one claude:// row in decision_tree')
        self.assertIn('?search=', claude_rows[0]['example'])

    def test_claude_row_want_describes_search(self):
        result = self._get_quick()
        claude_rows = [r for r in result['decision_tree'] if r['use'] == 'claude://']
        self.assertIn('search', claude_rows[0]['want'].lower())


class TestNoStaleAgentHelpDescriptions(unittest.TestCase):
    """S1.5: docs must not describe --agent-help as a 'quick reference'."""

    def _read(self, rel_path):
        import os
        base = os.path.join(os.path.dirname(__file__), '..', 'reveal', 'docs')
        with open(os.path.join(base, rel_path), encoding='utf-8') as f:
            return f.read()

    def _agent_help_contexts(self, text):
        """Return lines that mention --agent-help."""
        return [line for line in text.splitlines() if '--agent-help' in line]

    def test_readme_agent_help_not_quick_reference(self):
        text = self._read('README.md')
        for line in self._agent_help_contexts(text):
            self.assertNotIn('quick reference', line.lower(),
                             f'README.md calls --agent-help a quick reference: {line!r}')

    def test_quick_start_agent_help_not_quick_reference(self):
        text = self._read('QUICK_START.md')
        for line in self._agent_help_contexts(text):
            self.assertNotIn('quick reference', line.lower(),
                             f'QUICK_START.md calls --agent-help a quick reference: {line!r}')


if __name__ == '__main__':
    unittest.main()
