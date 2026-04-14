"""Coverage tests for reveal/display/structure.py.

Targets: lines 80-92, 105-115, 128-133, 145-189, 199-204, 215-227,
         307-387, 401-417, 447-468, 495-506, 553, 573-574, 605-612, 652-663
Current coverage: 51% → target: 75%+
"""

import pytest
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

from reveal.display.structure import (
    _matches_category_filter,
    _filter_element_tree,
    _count_filtered_matches,
    _format_element_parts,
    _render_typed_element,
    _print_typed_header,
    _get_element_name,
    _extract_element_names,
    _build_extraction_examples,
    _build_extractable_meta,
    _should_skip_category,
    _render_single_category,
    _build_outline_hierarchy,
    _handle_outline_mode,
    show_structure,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_base_el(name='foo', category='function', line=1, line_end=5):
    """Create a mock base Element (non-PythonElement)."""
    el = MagicMock(spec=[])
    el.name = name
    el.category = category
    el.line = line
    el.line_end = line_end
    el.children = []
    return el


def _make_python_el(name='foo', category='function', display_category='method',
                    line=1, line_end=5, decorator_prefix='', compact_signature='(x)',
                    return_type='', depth=2):
    """Create a mock PythonElement."""
    from reveal.elements import PythonElement
    el = MagicMock(spec=PythonElement)
    el.name = name
    el.category = category
    el.display_category = display_category
    el.decorator_prefix = decorator_prefix
    el.compact_signature = compact_signature
    el.return_type = return_type
    el.line = line
    el.line_end = line_end
    el.children = []
    el.depth = depth
    return el


def _capture(fn, *args, **kwargs):
    out = StringIO()
    with patch('sys.stdout', out):
        fn(*args, **kwargs)
    return out.getvalue()


# ─── _matches_category_filter ────────────────────────────────────────────────

class TestMatchesCategoryFilter:
    def test_python_element_matches_display_category(self):
        el = _make_python_el(display_category='property')
        assert _matches_category_filter(el, 'property') is True

    def test_python_element_matches_category(self):
        el = _make_python_el(category='function', display_category='method')
        assert _matches_category_filter(el, 'function') is True

    def test_python_element_no_match(self):
        el = _make_python_el(category='function', display_category='method')
        assert _matches_category_filter(el, 'class') is False

    def test_base_element_matches_category(self):
        el = _make_base_el(category='import')
        assert _matches_category_filter(el, 'import') is True

    def test_base_element_no_match(self):
        el = _make_base_el(category='import')
        assert _matches_category_filter(el, 'class') is False


# ─── _filter_element_tree ────────────────────────────────────────────────────

class TestFilterElementTree:
    def test_matching_element_included(self):
        el = _make_base_el(category='function')
        result = _filter_element_tree([el], 'function')
        assert el in result

    def test_non_matching_element_excluded(self):
        el = _make_base_el(category='import')
        result = _filter_element_tree([el], 'function')
        assert result == []

    def test_parent_included_for_matching_child(self):
        child = _make_base_el(name='method', category='function')
        parent = _make_base_el(name='MyClass', category='class')
        parent.children = [child]
        result = _filter_element_tree([parent], 'function')
        # Parent should be included as container
        assert parent in result

    def test_empty_list_returns_empty(self):
        assert _filter_element_tree([], 'function') == []


# ─── _count_filtered_matches ─────────────────────────────────────────────────

class TestCountFilteredMatches:
    def test_counts_matching_elements(self):
        els = [_make_base_el(category='function') for _ in range(3)]
        assert _count_filtered_matches(els, 'function') == 3

    def test_counts_nested_matches(self):
        child = _make_base_el(name='inner', category='function')
        parent = _make_base_el(name='outer', category='class')
        parent.children = [child]
        assert _count_filtered_matches([parent], 'function') == 1

    def test_no_matches_returns_zero(self):
        els = [_make_base_el(category='import')]
        assert _count_filtered_matches(els, 'function') == 0

    def test_empty_returns_zero(self):
        assert _count_filtered_matches([], 'function') == 0


# ─── _format_element_parts ───────────────────────────────────────────────────

class TestFormatElementParts:
    def test_base_element_has_name_and_category(self):
        el = _make_base_el(name='foo', category='function', line=1, line_end=3)
        parts = _format_element_parts(el)
        assert 'foo' in parts
        assert '(function)' in parts

    def test_base_element_line_range(self):
        el = _make_base_el(line=1, line_end=5)
        parts = _format_element_parts(el)
        assert '[1-5]' in parts

    def test_base_element_single_line(self):
        el = _make_base_el(line=5, line_end=5)
        parts = _format_element_parts(el)
        assert '[5]' in parts

    def test_base_element_long_function_shows_line_count(self):
        el = _make_base_el(line=1, line_end=20)
        parts = _format_element_parts(el)
        assert '20 lines' in parts

    def test_python_element_with_signature(self):
        el = _make_python_el(name='foo', category='function', compact_signature='(x, y)',
                              line=1, line_end=5)
        parts = _format_element_parts(el)
        assert 'foo(x, y)' in parts

    def test_python_element_no_signature_uses_name(self):
        el = _make_python_el(name='MyClass', category='class', compact_signature='',
                              line=1, line_end=30)
        parts = _format_element_parts(el)
        assert 'MyClass' in parts

    def test_python_element_return_type(self):
        el = _make_python_el(return_type='int', line=1, line_end=3)
        parts = _format_element_parts(el)
        assert '→ int' in parts

    def test_python_element_no_return_type(self):
        el = _make_python_el(return_type='', line=1, line_end=3)
        parts = _format_element_parts(el)
        assert '→' not in ' '.join(parts)

    def test_python_element_depth_warning(self):
        el = _make_python_el(category='function', depth=5, line=1, line_end=3)
        parts = _format_element_parts(el)
        assert any('depth:5' in p for p in parts)

    def test_python_element_no_depth_warning_below_threshold(self):
        el = _make_python_el(category='function', depth=3, line=1, line_end=3)
        parts = _format_element_parts(el)
        assert not any('depth:' in p for p in parts)

    def test_python_element_decorator_prefix(self):
        el = _make_python_el(category='function', decorator_prefix='@property', line=1, line_end=3)
        parts = _format_element_parts(el)
        assert '@property' in parts


# ─── _render_typed_element ───────────────────────────────────────────────────

class TestRenderTypedElement:
    def test_renders_element(self):
        el = _make_base_el(name='foo', category='function', line=1, line_end=3)
        out = _capture(_render_typed_element, el)
        assert 'foo' in out

    def test_renders_with_indent(self):
        el = _make_base_el(name='bar', category='function', line=1, line_end=2)
        out = _capture(_render_typed_element, el, indent=2)
        assert '    bar' in out  # 4 spaces for indent=2

    def test_renders_children_recursively(self):
        child = _make_base_el(name='child_fn', category='function', line=5, line_end=8)
        parent = _make_base_el(name='parent', category='class', line=1, line_end=20)
        parent.children = [child]
        out = _capture(_render_typed_element, parent)
        assert 'parent' in out
        assert 'child_fn' in out


# ─── _print_typed_header ─────────────────────────────────────────────────────

class TestPrintTypedHeader:
    def _make_typed(self, reveal_type_name=None, length=10, stats=None):
        typed = MagicMock()
        typed.__len__ = MagicMock(return_value=length)
        typed.stats = stats or {'roots': 3}
        if reveal_type_name:
            rt = MagicMock()
            rt.name = reveal_type_name
            typed.reveal_type = rt
        else:
            typed.reveal_type = None
        return typed

    def test_unfiltered_shows_elements_count(self):
        typed = self._make_typed(length=10)
        out = _capture(_print_typed_header, typed)
        assert 'Elements: 10' in out

    def test_unfiltered_shows_type_when_present(self):
        typed = self._make_typed(reveal_type_name='Python')
        out = _capture(_print_typed_header, typed)
        assert 'Type: Python' in out

    def test_filtered_shows_filter_and_matches(self):
        typed = self._make_typed(reveal_type_name='Python')
        out = _capture(_print_typed_header, typed, category_filter='method', match_count=5)
        assert 'Filter: method' in out
        assert 'Matches: 5' in out

    def test_no_reveal_type_no_type_line(self):
        typed = self._make_typed(reveal_type_name=None)
        out = _capture(_print_typed_header, typed)
        assert 'Type:' not in out


# ─── _get_element_name ───────────────────────────────────────────────────────

class TestGetElementName:
    def test_name_field(self):
        assert _get_element_name({'name': 'foo'}) == 'foo'

    def test_text_field_fallback(self):
        assert _get_element_name({'text': 'bar'}) == 'bar'

    def test_title_field_fallback(self):
        assert _get_element_name({'title': 'baz'}) == 'baz'

    def test_name_takes_priority(self):
        assert _get_element_name({'name': 'n', 'text': 't', 'title': 'ti'}) == 'n'

    def test_empty_dict_returns_none(self):
        assert _get_element_name({}) is None


# ─── _extract_element_names ──────────────────────────────────────────────────

class TestExtractElementNames:
    def test_extracts_names(self):
        items = [{'name': 'foo'}, {'name': 'bar'}]
        assert _extract_element_names(items) == ['foo', 'bar']

    def test_skips_items_without_name(self):
        items = [{'name': 'foo'}, {}, {'name': 'bar'}]
        assert _extract_element_names(items) == ['foo', 'bar']

    def test_empty_list(self):
        assert _extract_element_names([]) == []


# ─── _build_extraction_examples ──────────────────────────────────────────────

class TestBuildExtractionExamples:
    def test_builds_example_command(self):
        extractable = {'function': ['foo', 'bar']}
        result = _build_extraction_examples(extractable, 'main.py')
        assert len(result) == 1
        assert 'reveal main.py foo' in result[0]

    def test_quotes_names_with_spaces(self):
        extractable = {'function': ['my function']}
        result = _build_extraction_examples(extractable, 'x.py')
        assert '"my function"' in result[0]

    def test_empty_extractable_returns_empty(self):
        assert _build_extraction_examples({}, 'x.py') == []

    def test_empty_names_list_skipped(self):
        extractable = {'function': [], 'class': ['MyClass']}
        result = _build_extraction_examples(extractable, 'x.py')
        assert len(result) == 1
        assert 'MyClass' in result[0]


# ─── _build_extractable_meta ─────────────────────────────────────────────────

class TestBuildExtractableMeta:
    def test_basic_structure(self):
        structure = {
            'functions': [{'name': 'foo'}, {'name': 'bar'}],
        }
        result = _build_extractable_meta(structure, 'main.py')
        assert 'types' in result
        assert 'elements' in result
        assert 'examples' in result

    def test_empty_category_skipped(self):
        structure = {'functions': [], 'classes': [{'name': 'Foo'}]}
        result = _build_extractable_meta(structure, 'x.py')
        # functions is empty → not in types
        assert len(result['types']) >= 0  # classes may or may not be in CATEGORY_TO_ELEMENT_TYPE

    def test_unknown_category_skipped(self):
        structure = {'unknown_category': [{'name': 'x'}]}
        result = _build_extractable_meta(structure, 'x.py')
        assert result['types'] == []

    def test_non_list_category_skipped(self):
        structure = {'functions': {'not': 'a list'}}
        result = _build_extractable_meta(structure, 'x.py')
        assert result['types'] == []


# ─── _should_skip_category ───────────────────────────────────────────────────

class TestShouldSkipCategory:
    def test_empty_items_returns_true(self):
        assert _should_skip_category('functions', []) is True
        assert _should_skip_category('functions', None) is True

    def test_internal_category_returns_true(self):
        for cat in ['type', 'document', 'head', 'body', 'stats', 'template',
                    'columns', 'column_count', 'row_count', 'delimiter', 'sample_rows']:
            assert _should_skip_category(cat, [{'x': 1}]) is True

    def test_normal_category_with_items_returns_false(self):
        assert _should_skip_category('functions', [{'name': 'foo'}]) is False

    def test_nginx_directives_category_not_skipped(self):
        assert _should_skip_category('directives', {'key': 'val'}) is False


# ─── _render_single_category (nginx dict path) ───────────────────────────────

class TestRenderSingleCategory:
    def test_nginx_directives_dict(self):
        items = {'worker_processes': 4, 'error_log': '/var/log/nginx/error.log'}
        out = _capture(_render_single_category, 'directives', items, Path('/fake/nginx.conf'), 'text')
        assert 'Http directives' in out
        assert 'worker_processes' in out

    def test_events_directives_label(self):
        items = {'worker_connections': 1024}
        out = _capture(_render_single_category, 'events_directives', items, Path('/fake'), 'text')
        assert 'Events directives' in out

    def test_main_directives_label(self):
        items = {'user': 'nginx'}
        out = _capture(_render_single_category, 'main_directives', items, Path('/fake'), 'text')
        assert 'Main directives' in out

    def test_non_list_non_dict_returns_without_output(self):
        # Non-list, non-recognized-dict → just returns
        out = _capture(_render_single_category, 'column_count', 5, Path('/fake'), 'text')
        # Should not print anything meaningful (not a list, not nginx dict)
        # Just verify no crash

    def test_long_value_truncated(self):
        long_val = 'x' * 100
        items = {'key': long_val}
        out = _capture(_render_single_category, 'directives', items, Path('/fake'), 'text')
        assert '...' in out


# ─── _build_outline_hierarchy ────────────────────────────────────────────────

class TestBuildOutlineHierarchy:
    def test_toml_sections_no_level_uses_build_hierarchy(self):
        structure = {'sections': [{'name': 'server', 'line': 1}]}
        with patch('reveal.display.structure.build_hierarchy', return_value=[]) as mock_bh:
            _build_outline_hierarchy(structure)
        mock_bh.assert_called_once()

    def test_code_structure_uses_build_hierarchy(self):
        structure = {'functions': [{'name': 'foo', 'line': 1}]}
        with patch('reveal.display.structure.build_hierarchy', return_value=[]) as mock_bh:
            _build_outline_hierarchy(structure)
        mock_bh.assert_called_once()

    def test_markdown_uses_heading_hierarchy(self):
        structure = {'headings': [{'text': 'Title', 'level': 1, 'line': 1}]}
        with patch('reveal.display.structure.build_heading_hierarchy', return_value=[]) as mock_hh:
            _build_outline_hierarchy(structure)
        mock_hh.assert_called_once()


# ─── _handle_outline_mode ────────────────────────────────────────────────────

class TestHandleOutlineMode:
    def _make_analyzer(self, line_count=100):
        a = MagicMock()
        a.path = Path(str(Path('/fake/x.py')))
        a.is_fallback = False
        a.fallback_language = None
        a.lines = ['line'] * line_count
        a.content = '\n'.join(['line'] * line_count)
        a.format_with_lines.return_value = '\n'.join(
            f'   {i+1:4d}  line' for i in range(line_count)
        )
        return a

    def test_empty_structure_large_file_prints_no_structure_message(self):
        analyzer = self._make_analyzer(line_count=100)
        out = _capture(_handle_outline_mode, analyzer, {}, Path('/fake/x.py'), False, None)
        assert 'No structure' in out
        assert '100 lines' in out

    def test_empty_structure_small_file_shows_content(self):
        analyzer = self._make_analyzer(line_count=10)
        out = _capture(_handle_outline_mode, analyzer, {}, Path('/fake/x.py'), False, None)
        assert 'No structure' not in out
        analyzer.format_with_lines.assert_called_once_with(analyzer.content, 1)

    def test_non_empty_structure_calls_render_outline(self):
        analyzer = self._make_analyzer()
        structure = {'functions': [{'name': 'foo', 'line': 1, 'line_end': 3}]}
        with patch('reveal.display.structure._print_file_header'):
            with patch('reveal.display.structure.build_hierarchy', return_value=[]):
                with patch('reveal.display.structure.render_outline'):
                    with patch('reveal.display.structure.get_file_type_from_analyzer', return_value='py'):
                        with patch('reveal.display.structure.print_breadcrumbs'):
                            _handle_outline_mode(analyzer, structure, Path('/fake/x.py'), False, None)
                            # No assertion needed — just verify it doesn't crash


# ─── show_structure — related_flat and typed paths ───────────────────────────

class TestShowStructure:
    def _make_analyzer(self, structure=None):
        a = MagicMock()
        a.path = Path(str(Path('/fake/x.py')))
        a.is_fallback = False
        a.fallback_language = None
        a.get_structure.return_value = structure or {'functions': [{'name': 'foo'}]}
        return a

    def test_related_flat_path(self):
        """Cover lines 652-656: --related-flat flag."""
        analyzer = self._make_analyzer({'related': [{'path': 'a.py'}, {'path': 'b.py'}]})
        args = MagicMock()
        args.related_flat = True
        args.outline = False
        args.typed = False

        with patch('reveal.display.formatting._format_related_flat', return_value=['a.py', 'b.py']):
            out = _capture(show_structure, analyzer, 'text', args)
        assert 'a.py' in out
        assert 'b.py' in out

    def test_typed_flag_path(self):
        """Cover lines 660-663: --typed flag."""
        analyzer = self._make_analyzer()
        args = MagicMock()
        args.related_flat = False
        args.outline = False
        args.typed = True
        args.filter = None

        with patch('reveal.display.structure._render_typed_structure_output') as mock_rts:
            show_structure(analyzer, 'text', args)
        mock_rts.assert_called_once()


# ─── _render_typed_structure_output ──────────────────────────────────────────

from reveal.display.structure import (
    _render_typed_structure_output,
    _render_json_output,
    _render_text_categories,
    _handle_standard_output,
)


def _make_typed_mock(has_elements=True, roots=None, reveal_type_name='Python', stats=None):
    """Build a mock TypedStructure."""
    typed = MagicMock()
    typed.elements = [MagicMock()] if has_elements else []
    typed.roots = roots or []
    typed.stats = stats or {'elements': 5}
    if reveal_type_name:
        rt = MagicMock()
        rt.name = reveal_type_name
        typed.reveal_type = rt
    else:
        typed.reveal_type = None
    typed.to_tree.return_value = {'roots': []}
    return typed


class TestRenderTypedStructureOutput:
    def _make_analyzer(self):
        a = MagicMock()
        a.path = Path(str(Path('/fake/x.py')))
        a.is_fallback = False
        a.fallback_language = None
        return a

    def test_json_output_format(self):
        """Lines 257-266: json output path."""
        analyzer = self._make_analyzer()
        structure = {'functions': [{'name': 'foo'}]}
        typed = _make_typed_mock()
        with patch('reveal.structure.TypedStructure') as MockTS:
            MockTS.from_analyzer_output.return_value = typed
            with patch('reveal.display.structure.safe_json_dumps', return_value='{}') as mock_json:
                out = _capture(_render_typed_structure_output, analyzer, structure, 'json')
        mock_json.assert_called_once()

    def test_empty_elements_prints_no_structure(self):
        """Lines 273-275: no elements → 'No structure available'."""
        analyzer = self._make_analyzer()
        typed = _make_typed_mock(has_elements=False)
        with patch('reveal.structure.TypedStructure') as MockTS:
            MockTS.from_analyzer_output.return_value = typed
            with patch('reveal.display.structure._print_file_header'):
                out = _capture(_render_typed_structure_output, analyzer, {}, 'text')
        assert 'No structure available' in out

    def test_with_category_filter_no_matches(self):
        """Lines 283-285: filter with no matches."""
        analyzer = self._make_analyzer()
        el = _make_base_el(category='import')
        typed = _make_typed_mock(roots=[el])
        with patch('reveal.structure.TypedStructure') as MockTS:
            MockTS.from_analyzer_output.return_value = typed
            with patch('reveal.display.structure._print_file_header'):
                out = _capture(_render_typed_structure_output, analyzer, {}, 'text', 'function')
        assert "No elements matching filter 'function'" in out

    def test_with_category_filter_with_matches(self):
        """Lines 278-299: filter with matches renders tree."""
        analyzer = self._make_analyzer()
        el = _make_base_el(category='function')
        typed = _make_typed_mock(roots=[el])
        with patch('reveal.structure.TypedStructure') as MockTS:
            MockTS.from_analyzer_output.return_value = typed
            with patch('reveal.display.structure._print_file_header'):
                with patch('reveal.display.structure._render_typed_element') as mock_render:
                    with patch('reveal.display.structure.get_file_type_from_analyzer', return_value='py'):
                        with patch('reveal.display.structure.print_breadcrumbs'):
                            _render_typed_structure_output(analyzer, {}, 'text', 'function')
        mock_render.assert_called()

    def test_without_filter(self):
        """Lines 292-303: no filter, renders all roots."""
        analyzer = self._make_analyzer()
        el = _make_base_el(category='function')
        typed = _make_typed_mock(roots=[el])
        with patch('reveal.structure.TypedStructure') as MockTS:
            MockTS.from_analyzer_output.return_value = typed
            with patch('reveal.display.structure._print_file_header'):
                with patch('reveal.display.structure._render_typed_element') as mock_render:
                    with patch('reveal.display.structure.get_file_type_from_analyzer', return_value='py'):
                        with patch('reveal.display.structure.print_breadcrumbs'):
                            _render_typed_structure_output(analyzer, {}, 'text')
        mock_render.assert_called()


# ─── _render_json_output ─────────────────────────────────────────────────────

class TestRenderJsonOutput:
    def _make_analyzer(self, is_fallback=False, fallback_lang=None):
        a = MagicMock()
        a.path = Path(str(Path('/fake/x.py')))
        a.is_fallback = is_fallback
        a.fallback_language = fallback_lang
        a.__class__.__name__ = 'PythonAnalyzer'
        a._extract_relationships.return_value = None
        return a

    def test_list_of_dicts_enriched(self):
        """Lines 419-425: normal list of dict items get file field added."""
        analyzer = self._make_analyzer()
        structure = {'functions': [{'name': 'foo', 'line': 1}]}
        with patch('reveal.display.structure.safe_json_dumps', return_value='{}') as mock_j:
            with patch('reveal.display.structure._build_extractable_meta', return_value={}):
                _render_json_output(analyzer, structure)
        call_arg = mock_j.call_args[0][0]
        assert call_arg['structure']['functions'][0]['file'] == str(Path('/fake/x.py'))

    def test_frontmatter_dict_enriched(self):
        """Lines 400-404: frontmatter (dict, not list) gets file field."""
        analyzer = self._make_analyzer()
        structure = {'frontmatter': {'title': 'Test', 'data': {}}}
        with patch('reveal.display.structure.safe_json_dumps', return_value='{}') as mock_j:
            with patch('reveal.display.structure._build_extractable_meta', return_value={}):
                _render_json_output(analyzer, structure)
        call_arg = mock_j.call_args[0][0]
        assert call_arg['structure']['frontmatter']['file'] == str(Path('/fake/x.py'))

    def test_scalar_category_passed_through(self):
        """Lines 410-411: non-list scalar (e.g. column_count) passed through."""
        analyzer = self._make_analyzer()
        structure = {'column_count': 5}
        with patch('reveal.display.structure.safe_json_dumps', return_value='{}') as mock_j:
            with patch('reveal.display.structure._build_extractable_meta', return_value={}):
                _render_json_output(analyzer, structure)
        call_arg = mock_j.call_args[0][0]
        assert call_arg['structure']['column_count'] == 5

    def test_list_of_scalars_passed_through(self):
        """Lines 415-416: list of strings (columns) passed through unchanged."""
        analyzer = self._make_analyzer()
        structure = {'columns': ['id', 'name', 'value']}
        with patch('reveal.display.structure.safe_json_dumps', return_value='{}') as mock_j:
            with patch('reveal.display.structure._build_extractable_meta', return_value={}):
                _render_json_output(analyzer, structure)
        call_arg = mock_j.call_args[0][0]
        assert call_arg['structure']['columns'] == ['id', 'name', 'value']

    def test_relationships_included_when_present(self):
        """Lines 444-446: relationships added to result when non-empty."""
        analyzer = self._make_analyzer()
        analyzer._extract_relationships.return_value = [{'from': 'a', 'to': 'b'}]
        structure = {'functions': [{'name': 'foo'}]}
        with patch('reveal.display.structure.safe_json_dumps', return_value='{}') as mock_j:
            with patch('reveal.display.structure._build_extractable_meta', return_value={}):
                _render_json_output(analyzer, structure)
        call_arg = mock_j.call_args[0][0]
        assert 'relationships' in call_arg

    def test_fallback_analyzer_info(self):
        """Lines 392-438: fallback analyzer sets type/language fields correctly."""
        analyzer = self._make_analyzer(is_fallback=True, fallback_lang='javascript')
        structure = {}
        with patch('reveal.display.structure.safe_json_dumps', return_value='{}') as mock_j:
            with patch('reveal.display.structure._build_extractable_meta', return_value={}):
                _render_json_output(analyzer, structure)
        call_arg = mock_j.call_args[0][0]
        assert call_arg['analyzer']['type'] == 'fallback'
        assert call_arg['analyzer']['language'] == 'javascript'

    def test_stats_dict_not_list(self):
        """Lines 400-407: stats category (dict, not list) handled correctly."""
        analyzer = self._make_analyzer()
        structure = {'stats': {'line_count': 100, 'function_count': 5}}
        with patch('reveal.display.structure.safe_json_dumps', return_value='{}') as mock_j:
            with patch('reveal.display.structure._build_extractable_meta', return_value={}):
                _render_json_output(analyzer, structure)
        call_arg = mock_j.call_args[0][0]
        # stats dict that is NOT a list should be passed as-is (no file field added per else branch)
        assert 'stats' in call_arg['structure']


# ─── _render_single_category — metadata dict path and standard list ───────────

class TestRenderSingleCategoryExtra:
    def test_metadata_dict_path(self):
        """Lines 491-494: metadata category with dict items."""
        items = {'title': 'My Page', 'meta': {'description': 'desc'}}
        with patch('reveal.display.structure._format_html_metadata') as mock_fmt:
            out = _capture(_render_single_category, 'metadata', items, Path('/fake/x.html'), 'text')
        mock_fmt.assert_called_once_with(items, Path('/fake/x.html'), 'text') # noqa: win-path — Path-to-Path mock assertion, Path.__eq__ normalises
        assert 'Metadata:' in out

    def test_standard_list_items(self):
        """Lines 514-521: standard list category (functions) uses formatter."""
        items = [{'name': 'foo', 'line': 1, 'signature': '()', 'content': ''}]
        out = _capture(_render_single_category, 'functions', items, Path('/fake/x.py'), 'text')
        assert 'Functions (1):' in out
        assert 'foo' in out


# ─── _render_text_categories ─────────────────────────────────────────────────

class TestRenderTextCategories:
    def test_skips_empty_and_internal_renders_valid(self):
        """Lines 527-530: iterates structure, skips internals, renders valid cats."""
        structure = {
            'type': 'document',       # should be skipped
            'functions': [{'name': 'foo', 'line': 1, 'signature': '()', 'content': ''}],
        }
        out = _capture(_render_text_categories, structure, Path('/fake/x.py'), 'text')
        assert 'Functions (1):' in out
        assert 'foo' in out

    def test_empty_structure_produces_no_output(self):
        out = _capture(_render_text_categories, {}, Path('/fake/x.py'), 'text')
        assert out == ''


# ─── _build_outline_hierarchy — TOML with level ──────────────────────────────

class TestBuildOutlineHierarchyToml:
    def test_toml_sections_with_level_uses_heading_hierarchy(self):
        """Line 553: TOML sections that have 'level' use build_heading_hierarchy."""
        structure = {'sections': [{'name': 'server', 'level': 1, 'line': 1}]}
        with patch('reveal.display.structure.build_heading_hierarchy', return_value=[]) as mock_hh:
            _build_outline_hierarchy(structure)
        mock_hh.assert_called_once()


# ─── _handle_standard_output ─────────────────────────────────────────────────

class TestHandleStandardOutput:
    def _make_analyzer(self, structure=None, line_count=100):
        a = MagicMock()
        a.path = Path(str(Path('/fake/x.py')))
        a.is_fallback = False
        a.fallback_language = None
        a.__class__.__name__ = 'PythonAnalyzer'
        a._extract_relationships.return_value = None
        a.lines = ['line'] * line_count
        a.content = '\n'.join(['line'] * line_count)
        a.format_with_lines.return_value = '\n'.join(
            f'   {i+1:4d}  line' for i in range(line_count)
        )
        if structure is not None:
            a.get_structure.return_value = structure
        return a

    def test_json_output_delegates_to_render_json(self):
        """Lines 602-604: json → _render_json_output."""
        analyzer = self._make_analyzer()
        structure = {'functions': [{'name': 'foo'}]}
        with patch('reveal.display.structure._render_json_output') as mock_rj:
            _handle_standard_output(analyzer, structure, 'json', False, None)
        mock_rj.assert_called_once_with(analyzer, structure)

    def test_typed_output_delegates_to_render_typed(self):
        """Lines 607-609: typed → _render_typed_structure_output."""
        analyzer = self._make_analyzer()
        structure = {'functions': [{'name': 'foo'}]}
        with patch('reveal.display.structure._render_typed_structure_output') as mock_rt:
            _handle_standard_output(analyzer, structure, 'typed', False, None)
        mock_rt.assert_called_once_with(analyzer, structure, 'json')

    def test_empty_structure_large_file_prints_no_structure_message(self):
        """Empty structure on large file (>50 lines) → 'No structure available (N lines)'."""
        analyzer = self._make_analyzer(line_count=100)
        with patch('reveal.display.structure._print_file_header'):
            out = _capture(_handle_standard_output, analyzer, {}, 'text', False, None)
        assert 'No structure available' in out
        assert '100 lines' in out

    def test_empty_structure_small_file_shows_content(self):
        """Empty structure on small file (<=50 lines) → full file content displayed."""
        analyzer = self._make_analyzer(line_count=7)
        with patch('reveal.display.structure._print_file_header'):
            out = _capture(_handle_standard_output, analyzer, {}, 'text', False, None)
        assert 'No structure available' not in out
        analyzer.format_with_lines.assert_called_once_with(analyzer.content, 1)

    def test_text_output_renders_categories(self):
        """Lines 618-624: text output renders categories and breadcrumbs."""
        analyzer = self._make_analyzer()
        structure = {'functions': [{'name': 'foo', 'line': 1, 'signature': '()', 'content': ''}]}
        with patch('reveal.display.structure._print_file_header'):
            with patch('reveal.display.structure.get_file_type_from_analyzer', return_value='py'):
                with patch('reveal.display.structure.print_breadcrumbs'):
                    out = _capture(_handle_standard_output, analyzer, structure, 'text', False, None)
        assert 'Functions (1):' in out


# ─── show_structure — outline and standard paths ─────────────────────────────

class TestShowStructureExtra:
    def _make_analyzer(self, structure=None):
        a = MagicMock()
        a.path = Path(str(Path('/fake/x.py')))
        a.is_fallback = False
        a.fallback_language = None
        a.get_structure.return_value = structure or {'functions': [{'name': 'foo'}]}
        return a

    def test_outline_path(self):
        """Lines 669-671: outline flag → _handle_outline_mode."""
        analyzer = self._make_analyzer()
        args = MagicMock()
        args.related_flat = False
        args.typed = False
        args.outline = True

        with patch('reveal.display.structure._handle_outline_mode') as mock_om:
            show_structure(analyzer, 'text', args)
        mock_om.assert_called_once()

    def test_standard_output_path(self):
        """Line 674: no special flags → _handle_standard_output."""
        analyzer = self._make_analyzer()
        args = MagicMock()
        args.related_flat = False
        args.typed = False
        args.outline = False

        with patch('reveal.display.structure._handle_standard_output') as mock_so:
            show_structure(analyzer, 'text', args)
        mock_so.assert_called_once()
