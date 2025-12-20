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
    _get_guide_description,
    _render_help_static_guide,
    _render_help_adapter_summary,
    _render_help_section,
    _render_help_adapter_specific,
    render_help,
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
        """AST scheme should show related adapters."""
        output = capture_stdout(_render_help_breadcrumbs, 'ast', {})
        self.assertIn('---', output)
        self.assertIn('Next Steps', output)
        self.assertIn('help://python', output)
        self.assertIn('help://env', output)
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


class TestGetGuideDescription(unittest.TestCase):
    """Test guide description retrieval."""

    def test_agent_description(self):
        """Should return correct description for agent guide."""
        desc = _get_guide_description('agent')
        self.assertEqual(desc, 'Quick reference (task-based patterns)')

    def test_agent_full_description(self):
        """Should return correct description for agent-full guide."""
        desc = _get_guide_description('agent-full')
        self.assertEqual(desc, 'Comprehensive guide')

    def test_python_guide_description(self):
        """Should return correct description for python-guide."""
        desc = _get_guide_description('python-guide')
        self.assertEqual(desc, 'Python adapter deep dive')

    def test_anti_patterns_description(self):
        """Should return correct description for anti-patterns."""
        desc = _get_guide_description('anti-patterns')
        self.assertEqual(desc, 'Common mistakes to avoid')

    def test_tricks_description(self):
        """Should return correct description for tricks."""
        desc = _get_guide_description('tricks')
        self.assertEqual(desc, 'Cool tricks and hidden features')

    def test_markdown_description(self):
        """Should return correct description for markdown."""
        desc = _get_guide_description('markdown')
        self.assertEqual(desc, 'Markdown feature guide')

    def test_adapter_authoring_description(self):
        """Should return correct description for adapter-authoring."""
        desc = _get_guide_description('adapter-authoring')
        self.assertEqual(desc, 'Build your own adapters')

    def test_unknown_topic_default(self):
        """Should return default description for unknown topics."""
        desc = _get_guide_description('unknown-topic')
        self.assertEqual(desc, 'Static guide')


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
        """Should render static guides section."""
        data = {
            'static_guides': ['agent', 'agent-full', 'python-guide', 'anti-patterns']
        }
        output = capture_stdout(_render_help_list_mode, data)
        self.assertIn('STATIC GUIDES', output)
        self.assertIn('For AI Agents', output)
        self.assertIn('agent', output)
        self.assertIn('~2,200', output)  # Token estimate
        self.assertIn('--agent-help flag', output)  # Alias
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

    def test_agent_full_alias(self):
        """Should include -full suffix for agent-full topic."""
        data = {
            'topic': 'agent-full',
            'file': 'agent-full.md',
            'content': '# Full Guide'
        }
        output = capture_stdout(_render_help_static_guide, data)
        self.assertIn('--agent-help-full', output)

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


if __name__ == '__main__':
    unittest.main()
