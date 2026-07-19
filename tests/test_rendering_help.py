"""Tests for help rendering adapter."""

import unittest
import sys
import io
from pathlib import Path
from contextlib import redirect_stdout

# Add parent directory to path to import reveal
sys.path.insert(0, str(Path(__file__).parent.parent))

from reveal.rendering.adapters.help import (
    _render_help_breadcrumbs,
    _render_help_list_mode,
    _render_help_static_guide,
    _render_help_adapter_summary,
    _render_help_section,
    _render_help_adapter_specific,
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


class TestRenderHelpBreadcrumbs(unittest.TestCase):
    """Test breadcrumb rendering."""

    def test_no_scheme_empty(self):
        """Empty scheme should render nothing."""
        output = capture_stdout(_render_help_breadcrumbs, '', {})
        self.assertEqual(output, '')

    def test_none_scheme_empty(self):
        """None scheme should render nothing."""
        output = capture_stdout(_render_help_breadcrumbs, None, {})
        self.assertEqual(output, '')

    def test_ast_scheme_breadcrumbs(self):
        """AST scheme should show related adapters (calls + diff — core code analysis pair)."""
        output = capture_stdout(_render_help_breadcrumbs, 'ast', {})
        self.assertIn('---', output)
        self.assertIn('Next Steps', output)
        self.assertIn('help://calls', output)
        self.assertIn('help://diff', output)
        self.assertIn('Go Deeper', output)
        self.assertIn('help://tricks', output)
        self.assertIn('help://anti-patterns', output)

    def test_python_scheme_breadcrumbs(self):
        """Python scheme should show related adapters."""
        output = capture_stdout(_render_help_breadcrumbs, 'python', {})
        self.assertIn('Next Steps', output)
        self.assertIn('help://ast', output)
        self.assertIn('help://env', output)

    def test_env_scheme_breadcrumbs(self):
        """Env scheme should show related adapters."""
        output = capture_stdout(_render_help_breadcrumbs, 'env', {})
        self.assertIn('Next Steps', output)
        self.assertIn('help://python', output)

    def test_json_scheme_breadcrumbs(self):
        """JSON scheme should show related adapters."""
        output = capture_stdout(_render_help_breadcrumbs, 'json', {})
        self.assertIn('Next Steps', output)
        self.assertIn('help://ast', output)

    def test_help_scheme_breadcrumbs(self):
        """Help scheme should show related adapters."""
        output = capture_stdout(_render_help_breadcrumbs, 'help', {})
        self.assertIn('Next Steps', output)
        self.assertIn('help://ast', output)
        self.assertIn('help://python', output)

    def test_unknown_scheme_no_related(self):
        """Unknown scheme should still show Go Deeper section."""
        output = capture_stdout(_render_help_breadcrumbs, 'unknown', {})
        self.assertIn('---', output)
        self.assertIn('Go Deeper', output)
        # Should NOT have Next Steps since no related adapters
        self.assertNotIn('Next Steps', output)


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

    def test_includes_breadcrumbs(self):
        """Should include breadcrumbs at end."""
        data = {
            'scheme': 'ast',
            'description': 'AST queries'
        }
        output = capture_stdout(_render_help_adapter_specific, data)
        self.assertIn('---', output)
        self.assertIn('Go Deeper', output)
        self.assertIn('help://tricks', output)

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

    def test_related_adapters_expanded(self):
        """Breadcrumbs should now cover all major adapters."""
        from reveal.rendering.adapters.help import _render_help_breadcrumbs
        # ssl should point to domain and nginx (infrastructure cluster)
        output = capture_stdout(_render_help_breadcrumbs, 'ssl', {})
        self.assertIn('help://domain', output)
        self.assertIn('help://nginx', output)
        # sqlite should point to mysql
        output = capture_stdout(_render_help_breadcrumbs, 'sqlite', {})
        self.assertIn('help://mysql', output)
        # claude should point to git
        output = capture_stdout(_render_help_breadcrumbs, 'claude', {})
        self.assertIn('help://git', output)


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
