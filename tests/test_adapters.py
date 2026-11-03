"""Tests for URI adapters (env://, ast://, help://)."""

import unittest
import sys
import os
from pathlib import Path

# Add parent directory to path to import reveal
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from reveal.adapters.env import EnvAdapter
from reveal.adapters.ast import AstAdapter
from reveal.adapters.help import HelpAdapter
from reveal.adapters.base import get_adapter_class, list_supported_schemes

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


class TestAdapterRegistry(unittest.TestCase):
    """Test adapter registration and discovery."""

    def test_adapter_registration(self):
        """Adapters should auto-register on import."""
        schemes = list_supported_schemes()

        self.assertIn('env', schemes)
        self.assertIn('ast', schemes)
        self.assertIn('help', schemes)
        self.assertNotIn('python', schemes)  # removed, BACK-2225

    def test_get_adapter_class(self):
        """Should retrieve adapter class by scheme."""
        env_adapter = get_adapter_class('env')
        self.assertEqual(env_adapter, EnvAdapter)

        ast_adapter = get_adapter_class('ast')
        self.assertEqual(ast_adapter, AstAdapter)

        help_adapter = get_adapter_class('help')
        self.assertEqual(help_adapter, HelpAdapter)

    def test_unknown_scheme(self):
        """Should return None for unknown scheme."""
        unknown = get_adapter_class('unknown')
        self.assertIsNone(unknown)


class TestEnvAdapter(unittest.TestCase):
    """Test environment variable adapter."""

    def test_get_structure(self):
        """Should return environment variables grouped by category."""
        adapter = EnvAdapter()
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'environment')
        self.assertIn('total_count', result)
        self.assertIn('categories', result)
        self.assertIsInstance(result['categories'], dict)

    def test_get_element(self):
        """Should retrieve specific environment variable."""
        adapter = EnvAdapter()

        # Test with PATH (should exist on all systems)
        result = adapter.get_element('PATH')
        if result:  # PATH might not exist in some test environments
            self.assertEqual(result['name'], 'PATH')
            self.assertIn('value', result)
            self.assertIn('category', result)

    def test_get_help(self):
        """Should provide help documentation."""
        help_data = EnvAdapter.get_help()

        self.assertIsInstance(help_data, dict)
        self.assertEqual(help_data['name'], 'env')
        self.assertIn('description', help_data)
        self.assertIn('examples', help_data)
        self.assertIn('syntax', help_data)


class TestAstAdapter(unittest.TestCase):
    """Test AST query adapter."""

    @classmethod
    def setUpClass(cls):
        cls.test_file = Path(__file__).parent / 'test_adapters.py'
        # Cache results for dir-scan tests — narrowed to single file so they
        # don't re-scan the entire tests/ directory (~100 files) each time.
        cls._struct_all = AstAdapter(str(cls.test_file), None).get_structure()
        cls._struct_class_or_func = AstAdapter(str(cls.test_file), 'type=class|function').get_structure()
        cls._struct_class = AstAdapter(str(cls.test_file), 'type=class').get_structure()

    def setUp(self):
        pass  # test_file and cached results provided by setUpClass

    def test_parse_query(self):
        """Should parse query string into filters."""
        adapter = AstAdapter('.', 'lines>50')

        self.assertIn('lines', adapter.query)
        self.assertEqual(adapter.query['lines']['op'], '>')
        self.assertEqual(adapter.query['lines']['value'], 50)

    def test_parse_multiple_filters(self):
        """Should parse multiple filters."""
        adapter = AstAdapter('.', 'lines>20&complexity<5')

        self.assertIn('lines', adapter.query)
        self.assertIn('complexity', adapter.query)

    def test_parse_operators(self):
        """Should handle all comparison operators."""
        test_cases = [
            ('lines>50', '>'),
            ('lines<50', '<'),
            ('lines>=50', '>='),
            ('lines<=50', '<='),
            ('complexity==5', '=='),
        ]

        for query_str, expected_op in test_cases:
            adapter = AstAdapter('.', query_str)
            field = query_str.split(expected_op.replace('=', '\\='))[0]

            # Get the actual field name (might be remapped)
            if 'lines' in query_str:
                self.assertEqual(adapter.query['lines']['op'], expected_op)
            elif 'complexity' in query_str:
                self.assertEqual(adapter.query['complexity']['op'], expected_op)

    def test_get_structure(self):
        """Should return AST query results."""
        result = self._struct_all

        self.assertEqual(result['type'], 'ast_query')
        self.assertIn('total_files', result)
        self.assertIn('total_results', result)
        self.assertIn('results', result)
        self.assertIsInstance(result['results'], list)

    def test_filter_by_complexity(self):
        """Should filter by complexity."""
        # Find functions with complexity > 1 in this file
        adapter = AstAdapter(str(self.test_file), 'complexity>1')
        result = adapter.get_structure()

        # Should find some functions
        self.assertGreater(result['total_results'], 0)

        # All results should have complexity > 1
        for elem in result['results']:
            if 'complexity' in elem:
                self.assertGreater(elem['complexity'], 1)

    def test_get_help(self):
        """Should provide comprehensive help documentation."""
        help_data = AstAdapter.get_help()

        self.assertIsInstance(help_data, dict)
        self.assertEqual(help_data['name'], 'ast')
        self.assertIn('description', help_data)
        self.assertIn('syntax', help_data)
        self.assertIn('operators', help_data)
        self.assertIn('filters', help_data)
        self.assertIn('examples', help_data)
        self.assertIn('notes', help_data)

        # Check operators
        self.assertIn('>', help_data['operators'])
        self.assertIn('<', help_data['operators'])

        # Check filters
        self.assertIn('lines', help_data['filters'])
        self.assertIn('complexity', help_data['filters'])

    def test_type_filter_or_logic_pipe(self):
        """Should support OR logic with | in type filter."""
        adapter = AstAdapter(str(self.test_file), 'type=class|function')

        # OR detected at parse time, should have 'in' operator
        self.assertEqual(adapter.query['type']['op'], 'in')
        # Values are raw strings at parse time (normalized during filtering)
        self.assertIn('class', adapter.query['type']['value'])
        self.assertIn('function', adapter.query['type']['value'])

    def test_type_filter_or_logic_comma(self):
        """Should support OR logic with , in type filter."""
        adapter = AstAdapter(str(self.test_file), 'type=class,function')

        # OR detected at parse time, should have 'in' operator
        self.assertEqual(adapter.query['type']['op'], 'in')
        # Values are raw strings at parse time (normalized during filtering)
        self.assertIn('class', adapter.query['type']['value'])
        self.assertIn('function', adapter.query['type']['value'])

    def test_type_filter_or_logic_results(self):
        """Should return both classes and functions with OR filter."""
        result = self._struct_class_or_func

        # Should find both classes and functions
        categories = {elem.get('category') for elem in result['results']}
        self.assertIn('classes', categories)
        self.assertIn('functions', categories)

    def test_class_line_count(self):
        """Should correctly calculate line count for classes."""
        result = self._struct_class

        # All classes should have non-zero line counts
        for elem in result['results']:
            if elem.get('category') == 'classes':
                self.assertGreater(elem.get('line_count', 0), 0,
                    f"Class {elem.get('name')} has 0 line_count")

    def test_not_equals_operator(self):
        """Should support != operator for filtering."""
        adapter = AstAdapter(str(self.test_file), 'type!=function')

        # Should parse != operator
        self.assertEqual(adapter.query['type']['op'], '!=')
        self.assertEqual(adapter.query['type']['value'], 'function')

    def test_regex_operator(self):
        """Should support ~= operator for regex matching."""
        adapter = AstAdapter(str(self.test_file), 'name~=^test_')

        # Should parse ~= operator
        self.assertEqual(adapter.query['name']['op'], '~=')
        self.assertEqual(adapter.query['name']['value'], '^test_')

    def test_range_operator(self):
        """Should support .. operator for range filtering."""
        adapter = AstAdapter(str(self.test_file), 'lines=10..100')

        # Should parse .. operator
        self.assertEqual(adapter.query['lines']['op'], '..')
        self.assertEqual(adapter.query['lines']['value'], '10..100')

    def test_result_control_limit(self):
        """Should support limit parameter for result pagination."""
        adapter = AstAdapter(str(self.test_file), 'type=function&limit=3')

        # Should parse limit
        self.assertEqual(adapter.result_control.limit, 3)
        self.assertEqual(adapter.result_control.offset, 0)  # Default offset is 0, not None

        # Should apply limit
        result = adapter.get_structure()
        self.assertLessEqual(result['displayed_results'], 3)
        self.assertLessEqual(len(result['results']), 3)

    def test_result_control_offset(self):
        """Should support offset parameter for result pagination."""
        adapter = AstAdapter(str(self.test_file), 'type=function&offset=2')

        # Should parse offset
        self.assertEqual(adapter.result_control.offset, 2)
        self.assertIsNone(adapter.result_control.limit)

    def test_result_control_sort_ascending(self):
        """Should support sort parameter for ascending sort."""
        adapter = AstAdapter(str(self.test_file), 'type=function&sort=name')

        # Should parse sort
        self.assertEqual(adapter.result_control.sort_field, 'name')
        self.assertFalse(adapter.result_control.sort_descending)

    def test_result_control_sort_descending(self):
        """Should support sort=-field for descending sort."""
        adapter = AstAdapter(str(self.test_file), 'type=function&sort=-lines')

        # Should parse descending sort
        self.assertEqual(adapter.result_control.sort_field, 'lines')
        self.assertTrue(adapter.result_control.sort_descending)

    def test_result_control_combined(self):
        """Should support combined result control parameters."""
        adapter = AstAdapter(str(self.test_file), 'type=function&sort=-complexity&limit=5&offset=2')

        # Should parse all parameters
        self.assertEqual(adapter.result_control.sort_field, 'complexity')
        self.assertTrue(adapter.result_control.sort_descending)
        self.assertEqual(adapter.result_control.limit, 5)
        self.assertEqual(adapter.result_control.offset, 2)

        # Query should not include result control params
        self.assertIn('type', adapter.query)
        self.assertNotIn('sort', adapter.query)
        self.assertNotIn('limit', adapter.query)
        self.assertNotIn('offset', adapter.query)


class TestHelpAdapter(unittest.TestCase):
    """Test help meta-adapter."""

    def test_get_structure(self):
        """Should list all available help topics."""
        adapter = HelpAdapter()
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'help')
        self.assertIn('available_topics', result)
        self.assertIn('adapters', result)
        self.assertIn('static_guides', result)

        # Should include all registered adapters
        topics = result['available_topics']
        self.assertIn('env', topics)
        self.assertIn('ast', topics)
        self.assertIn('help', topics)

    def test_get_adapter_help(self):
        """Should retrieve help for specific adapter."""
        adapter = HelpAdapter()

        # ast and env are registered in STATIC_HELP, so they return static guides
        ast_help = adapter.get_element('ast')
        self.assertIsNotNone(ast_help)
        self.assertEqual(ast_help['type'], 'static_guide')
        self.assertEqual(ast_help['topic'], 'ast')
        self.assertIn('content', ast_help)

        env_help = adapter.get_element('env')
        self.assertIsNotNone(env_help)
        self.assertEqual(env_help['type'], 'static_guide')
        self.assertEqual(env_help['topic'], 'env')

    def test_get_all_adapters(self):
        """Should provide summary of all adapters."""
        adapter = HelpAdapter()
        result = adapter.get_element('adapters')

        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'adapter_summary')
        self.assertIn('adapters', result)
        self.assertIn('ast', result['adapters'])
        self.assertIn('env', result['adapters'])

    def test_unknown_topic(self):
        """Should return None for unknown topic."""
        adapter = HelpAdapter()
        result = adapter.get_element('unknown_topic')

        self.assertIsNone(result)

    def test_get_help(self):
        """Should provide help about help (meta!)."""
        help_data = HelpAdapter.get_help()

        self.assertIsInstance(help_data, dict)
        self.assertEqual(help_data['name'], 'help')
        self.assertIn('description', help_data)
        self.assertIn('examples', help_data)

    # --- help://schemas/* ---

    def test_schemas_bare_returns_listing(self):
        """help://schemas returns listing dict (not an error)."""
        adapter = HelpAdapter()
        result = adapter.get_element('schemas')
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'adapter_schema_index')
        self.assertNotIn('error', result)
        self.assertIn('available_adapters', result)
        self.assertIn('ast', result['available_adapters'])
        self.assertIn('ssl', result['available_adapters'])

    def test_schemas_trailing_slash_returns_listing(self):
        """help://schemas/ (trailing slash) behaves same as bare schemas."""
        adapter = HelpAdapter()
        result = adapter.get_element('schemas/')
        self.assertIsNotNone(result)
        self.assertIn('available_adapters', result)

    def test_schemas_adapter_returns_schema(self):
        """help://schemas/ast returns full ast schema."""
        adapter = HelpAdapter()
        result = adapter.get_element('schemas/ast')
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'adapter_schema')
        self.assertEqual(result['adapter'], 'ast')
        self.assertIn('query_params', result)
        self.assertIn('output_types', result)
        self.assertIn('example_queries', result)
        self.assertIn('notes', result)

    def test_schemas_rendered_listing(self):
        """Rendered help://schemas listing contains expected headers."""
        import io
        from contextlib import redirect_stdout
        from reveal.rendering.adapters.help import render_help

        adapter = HelpAdapter()
        result = adapter.get_element('schemas')
        buf = io.StringIO()
        with redirect_stdout(buf):
            render_help(result, 'text')
        output = buf.getvalue()
        self.assertIn('Adapter Schemas', output)
        self.assertIn('ast', output)
        self.assertIn('ssl', output)

    def test_schemas_rendered_adapter(self):
        """Rendered help://schemas/ast contains expected sections."""
        import io
        from contextlib import redirect_stdout
        from reveal.rendering.adapters.help import render_help

        adapter = HelpAdapter()
        result = adapter.get_element('schemas/ast')
        buf = io.StringIO()
        with redirect_stdout(buf):
            render_help(result, 'text')
        output = buf.getvalue()
        self.assertIn('ast:// Schema', output)
        self.assertIn('Query Parameters', output)
        self.assertIn('Output Types', output)
        self.assertIn('Example Queries', output)
        self.assertIn('Notes', output)

    def test_schemas_unknown_adapter_has_error(self):
        """help://schemas/unknown returns error dict with available_adapters."""
        adapter = HelpAdapter()
        result = adapter.get_element('schemas/unknown_adapter_xyz')
        self.assertIsNotNone(result)
        self.assertIn('error', result)
        self.assertIn('available_adapters', result)
        self.assertEqual(result['adapter'], 'unknown_adapter_xyz')

    def test_schemas_unknown_adapter_renders_to_stderr(self):
        """Rendering help://schemas/unknown exits with error (not listing)."""
        import io
        import sys
        from contextlib import redirect_stderr
        from reveal.rendering.adapters.help import render_help

        adapter = HelpAdapter()
        result = adapter.get_element('schemas/unknown_adapter_xyz')
        buf = io.StringIO()
        with redirect_stderr(buf):
            try:
                render_help(result, 'text')
            except SystemExit as e:
                self.assertEqual(e.code, 1)
        self.assertIn('unknown_adapter_xyz', buf.getvalue())

    # --- help://examples/* ---

    def test_examples_bare_returns_success_index_with_tasks(self):
        """help://examples returns a success-typed index listing available tasks (BACK-998)."""
        adapter = HelpAdapter()
        result = adapter.get_element('examples')
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'query_recipes_index')
        self.assertNotIn('error', result)
        self.assertIn('available_tasks', result)
        self.assertIn('quality', result['available_tasks'])
        self.assertIn('security', result['available_tasks'])

    def test_examples_unknown_task_returns_error(self):
        """help://examples/<bogus> still returns the error shape (only the bare listing changed)."""
        adapter = HelpAdapter()
        result = adapter.get_element('examples/nonexistent-task')
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'query_recipes')
        self.assertIn('error', result)

    def test_examples_task_returns_recipes(self):
        """help://examples/quality returns valid recipe list."""
        adapter = HelpAdapter()
        result = adapter.get_element('examples/quality')
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'query_recipes')
        self.assertEqual(result['task'], 'quality')
        self.assertIn('recipes', result)
        self.assertGreater(len(result['recipes']), 0)
        for recipe in result['recipes']:
            self.assertIn('goal', recipe)
            self.assertIn('query', recipe)
            self.assertIn('output_type', recipe)

    def test_examples_all_tasks_valid(self):
        """All help://examples/<task> routes return valid data."""
        adapter = HelpAdapter()
        tasks = ['security', 'codebase', 'due-diligence', 'debugging', 'infrastructure', 'quality', 'documentation']
        for task in tasks:
            result = adapter.get_element(f'examples/{task}')
            self.assertIsNotNone(result, f'examples/{task} returned None')
            self.assertEqual(result['type'], 'query_recipes', f'examples/{task} wrong type')
            self.assertGreater(len(result.get('recipes', [])), 0, f'examples/{task} has no recipes')

    def test_due_diligence_unused_recipe_has_derived_signal_caveat(self):
        """The unused-code question keeps the static-call caveat after recipe reordering."""
        result = HelpAdapter().get_element('examples/due-diligence')
        recipes = [r for r in result['recipes'] if '--select D,I' in r['query']]
        self.assertEqual(len(recipes), 1)
        recipe = recipes[0]
        self.assertNotIn('uncalled', recipe['query'])
        self.assertIn('?callers=NAME', recipe['description'])
        self.assertIn('not proof of dead code', recipe['description'])

    def test_examples_rendered(self):
        """Rendered help://examples/quality shows recipes."""
        import io
        from contextlib import redirect_stdout
        from reveal.rendering.adapters.help import render_help

        adapter = HelpAdapter()
        result = adapter.get_element('examples/quality')
        buf = io.StringIO()
        with redirect_stdout(buf):
            render_help(result, 'text')
        output = buf.getvalue()
        self.assertIn('Query Recipes: quality', output)
        self.assertIn('Recipes', output)
        self.assertIn('Find', output)

    # --- help://search?search=* (BACK-1023) ---

    def test_search_finds_adapter_by_synonym_not_in_scheme_name(self):
        """'find callers' has no adapter named that, but should surface calls://
        (the motivating BACK-1023 routing miss: help://quick's table only
        matches 'find dead code', not 'find callers')."""
        adapter = HelpAdapter()
        result = adapter.get_element("search?search=find callers")
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'help_search')
        self.assertEqual(result['query'], 'find callers')
        schemes = {h.get('scheme') for h in result['hits'] if h['type'] == 'adapter'}
        self.assertIn('calls', schemes)

    def test_search_path_form_equivalent_to_query_form(self):
        """help://search/<term> is accepted as an alias for ?q=<term>."""
        adapter = HelpAdapter()
        result = adapter.get_element('search/find callers')
        self.assertEqual(result['type'], 'help_search')
        self.assertEqual(result['query'], 'find callers')

    def test_search_empty_term_returns_usage_error(self):
        """Bare help://search (no term) is a usage error, not a crash or empty result."""
        adapter = HelpAdapter()
        result = adapter.get_element('search')
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'help_search')
        self.assertIn('error', result)

    def test_search_no_match_returns_empty_hits_not_none(self):
        """A term with no hits is a valid zero-result search, not a lookup failure."""
        adapter = HelpAdapter()
        result = adapter.get_element('search?search=zzznonexistentqqqterm')
        self.assertIsNotNone(result)
        self.assertEqual(result['count'], 0)
        self.assertEqual(result['hits'], [])
        self.assertIn('next', result)

    def test_search_tokens_match_regardless_of_word_order(self):
        """'tests coverage' (reordered/pluralized) must match the same corpus
        content as 'test coverage' -- phrase-only substring matching found
        live during dogfooding returned zero hits for this exact case."""
        adapter = HelpAdapter()
        result = adapter.get_element('search?search=tests coverage')
        self.assertGreater(result['count'], 0)

    def test_search_ranks_adapter_above_incidental_guide_mention(self):
        """A broad single-word query ('complexity') must surface the adapter
        that actually answers it (ast:// / hotspots://) ahead of guides that
        merely mention the word in passing -- found live during dogfooding:
        unranked results buried the adapter under alphabetically-first guides
        like adapter-authoring's docstring example."""
        adapter = HelpAdapter()
        result = adapter.get_element('search?search=complexity')
        self.assertGreater(len(result['hits']), 0)
        self.assertEqual(result['hits'][0]['type'], 'adapter')

    def test_search_name_match_outranks_description_only_match(self):
        """A query matching an adapter's own scheme name ranks above one that
        only matches inside its description."""
        adapter = HelpAdapter()
        result = adapter.get_element('search?search=deps')
        schemes = [h.get('scheme') for h in result['hits'] if h['type'] == 'adapter']
        self.assertIn('deps', schemes)
        self.assertEqual(schemes[0], 'deps')

    def test_search_hits_capped_at_20(self):
        """A broad term (many matches) is capped, not an unbounded dump."""
        adapter = HelpAdapter()
        result = adapter.get_element('search?search=e')  # matches nearly everything
        self.assertLessEqual(len(result['hits']), 20)

    def test_search_rendered_text(self):
        """Rendered help://search text output shows hits and doesn't fall through
        to the generic adapter-specific template (the bug found while manually
        verifying this feature: JSON worked, text silently didn't)."""
        import io
        from contextlib import redirect_stdout
        from reveal.rendering.adapters.help import render_help

        adapter = HelpAdapter()
        result = adapter.get_element('search?search=find callers')
        buf = io.StringIO()
        with redirect_stdout(buf):
            render_help(result, 'text')
        output = buf.getvalue()
        self.assertIn("Help Search: 'find callers'", output)
        self.assertIn('calls', output)


class TestHelpDiscovery(unittest.TestCase):
    """Test that all adapters expose help."""

    def test_all_adapters_have_help(self):
        """All registered adapters should have get_help() method."""
        schemes = list_supported_schemes()

        for scheme in schemes:
            adapter_class = get_adapter_class(scheme)
            self.assertTrue(
                hasattr(adapter_class, 'get_help'),
                f"{scheme}:// adapter should have get_help() method"
            )

            # Try calling it
            help_data = adapter_class.get_help()
            if help_data:  # Some might return None
                self.assertIsInstance(help_data, dict)
                self.assertIn('name', help_data)


if __name__ == '__main__':
    unittest.main()


def test_ast_sort_by_lines_alias_and_unknown_sort_field(tmp_path):
    """BACK-1423: `sort=-lines` (the help://examples/quality recipe) matched no
    field and silently returned the results unsorted; an unknown sort field
    gave no warning."""
    from reveal.adapters.ast.adapter import AstAdapter
    (tmp_path / 'm.py').write_text(
        'def short():\n    return 1\n\n'
        'def long():\n    a = 1\n    b = 2\n    c = 3\n    return a + b + c\n\n'
        'def mid():\n    x = 1\n    return x\n', encoding='utf-8')
    result = AstAdapter(str(tmp_path), 'type=function&sort=-lines').get_structure()
    assert [e['name'] for e in result['results']] == ['long', 'mid', 'short']
    assert not [w for w in result['meta']['warnings'] if w.get('type') == 'unknown_sort_field']
    result = AstAdapter(str(tmp_path), 'type=function&sort=-bogus').get_structure()
    warning = [w for w in result['meta']['warnings'] if w.get('type') == 'unknown_sort_field']
    assert warning and 'line_count' in warning[0]['message']
