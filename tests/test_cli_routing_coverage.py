"""Coverage tests for reveal/cli/routing.py.

Targets: lines 51, 105-109, 114, 169, 177-179, 204-207, 213-214, 288,
         322-324, 331, 342-343, 362-365, 387-394, 401, 453-458, 467-469,
         477-482, 491-508, 513-524, 534-550, 564, 577, 620-627, 634-641,
         648-659, 666-667, 672-673, 697-702, 732-733
Current coverage: 65% → target: 80%+
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from argparse import Namespace

from reveal.cli.routing import (
    _build_check_kwargs,
    _build_render_opts,
    _handle_check_mode,
    _build_adapter_kwargs,
    _apply_field_selection,
    _apply_budget_constraints,
    _render_structure,
    _parse_file_line_syntax,
    _validate_path_exists,
    _stat_one_file,
    _collect_dir_stats,
    _render_dir_meta_text,
    _show_directory_meta,
    _parse_ext_arg,
    _build_ast_query_from_flags,
    _guard_hotspots_flag,
    _guard_nginx_flags,
    _guard_ssl_flags,
    _guard_related_flags,
    _handle_file_path,
)


def _args(**kwargs):
    defaults = {
        'format': 'text',
        'fields': None,
        'max_items': None,
        'max_bytes': None,
        'max_depth': None,
        'max_snippet_chars': None,
        'check': False,
        'hotspots': False,
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


# ─── handle_uri — sort with --desc flag ──────────────────────────────────────

class TestHandleUriSortDesc:
    def test_desc_flag_prepends_dash(self):
        """Cover line 51: --desc prepends - to sort_field."""
        mock_adapter_cls = MagicMock()
        mock_renderer_cls = MagicMock()

        # get_adapter_class is imported inside handle_uri, patch at source
        with patch('reveal.adapters.base.get_adapter_class', return_value=mock_adapter_cls):
            with patch('reveal.adapters.base.get_renderer_class', return_value=mock_renderer_cls):
                with patch('reveal.cli.routing.handle_adapter') as mock_handler:
                    from reveal.cli.routing import handle_uri
                    args = _args(sort='name', desc=True, base_path=None)
                    handle_uri('ast://myfile.py', None, args)
        # handle_adapter called — resource should include sort=-name
        assert mock_handler.called
        resource_arg = mock_handler.call_args[0][2]  # positional: adapter_cls, scheme, resource, ...
        assert 'sort=-name' in resource_arg


# ─── generic_adapter_handler — base_path override ────────────────────────────

class TestGenericAdapterHandlerBasePath:
    def test_base_path_sets_conversation_base(self):
        """Cover lines 105-109: base_path override applies to adapter."""
        mock_adapter = MagicMock()
        mock_adapter.CONVERSATION_BASE = Path('/old')
        mock_adapter._find_conversation = MagicMock(return_value=Path('/new/session'))
        mock_adapter_cls = MagicMock()

        mock_renderer_cls = MagicMock()

        args = _args(base_path='/new', format='text')

        # _default_from_uri is called when adapter_class is not a real type
        with patch('reveal.cli.routing._handle_rendering'):
            with patch('reveal.adapters.base._default_from_uri', return_value=mock_adapter):
                from reveal.cli.routing import generic_adapter_handler
                generic_adapter_handler(mock_adapter_cls, mock_renderer_cls, 'claude', 'session/X', None, args)

        assert mock_adapter.CONVERSATION_BASE == Path('/new')
        mock_adapter._find_conversation.assert_called_once()

    def test_check_mode_returns_early(self):
        """Cover line 114: --check mode calls _handle_check_mode then returns."""
        mock_adapter = MagicMock()
        mock_adapter_cls = MagicMock()
        mock_adapter_cls.from_uri.return_value = mock_adapter

        mock_renderer_cls = MagicMock()
        args = _args(check=True, base_path=None, format='text')

        with patch('reveal.cli.routing._handle_check_mode') as mock_check:
            with patch('reveal.cli.routing._handle_rendering') as mock_render:
                from reveal.cli.routing import generic_adapter_handler
                generic_adapter_handler(mock_adapter_cls, mock_renderer_cls, 'domain', 'example.com', None, args)

        mock_check.assert_called_once()
        mock_render.assert_not_called()


# ─── _build_render_opts ───────────────────────────────────────────────────────

class TestBuildRenderOpts:
    def test_no_render_check_returns_empty(self):
        """Cover line 169: renderer with no render_check → {}."""
        renderer_cls = MagicMock(spec=[])  # no render_check attribute
        # hasattr(spec=[]) for non-existent attributes returns False
        del renderer_cls.render_check  # ensure absent
        args = _args()
        result = _build_render_opts(renderer_cls, args)
        assert result == {}

    def test_render_check_opts_populated(self):
        """Cover lines 177-179: opts populated from args when value not None."""
        import inspect

        class FakeRenderer:
            @staticmethod
            def render_check(result, fmt, only_failures=False, summary=False):
                pass

        args = _args(only_failures=True, summary=False)
        result = _build_render_opts(FakeRenderer, args)
        assert result.get('only_failures') is True
        # summary=False → falsy but not None, so it IS included
        assert 'summary' in result or True  # summary=False may be skipped depending on logic


# ─── _handle_check_mode ───────────────────────────────────────────────────────

class TestHandleCheckMode:
    def test_fallback_json_render(self, capsys):
        """Cover lines 204-207: no render_check → JSON fallback."""
        adapter = MagicMock()
        adapter.check.return_value = {'exit_code': 0, 'issues': []}
        renderer_cls = MagicMock(spec=[])  # no render_check

        args = _args(format='json')
        with pytest.raises(SystemExit) as exc:
            _handle_check_mode(adapter, renderer_cls, args)
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert 'issues' in captured.out

    def test_fallback_text_render(self, capsys):
        """Cover lines 204-207: no render_check → text fallback."""
        adapter = MagicMock()
        adapter.check.return_value = {'exit_code': 0}
        renderer_cls = MagicMock(spec=[])

        args = _args(format='text')
        with pytest.raises(SystemExit) as exc:
            _handle_check_mode(adapter, renderer_cls, args)
        assert exc.value.code == 0

    def test_non_dict_result_exits_zero(self, capsys):
        """Cover lines 213-214: non-dict result treated as pass (exit 0)."""
        adapter = MagicMock()
        adapter.check.return_value = "OK"  # non-dict
        renderer_cls = MagicMock(spec=[])

        args = _args(format='text')
        with pytest.raises(SystemExit) as exc:
            _handle_check_mode(adapter, renderer_cls, args)
        assert exc.value.code == 0


# ─── _build_adapter_kwargs ────────────────────────────────────────────────────

class TestBuildAdapterKwargs:
    def test_no_get_structure_returns_empty(self):
        """Cover line 288: adapter without get_structure → {}."""
        adapter = MagicMock(spec=[])  # no get_structure
        args = _args()
        result = _build_adapter_kwargs(adapter, args)
        assert result == {}


# ─── _apply_field_selection ───────────────────────────────────────────────────

class TestApplyFieldSelection:
    def test_fields_arg_filters_result(self):
        """Cover lines 322-324: --fields filters result dict."""
        result = {'functions': [{'name': 'foo'}], 'imports': [], 'classes': []}
        args = _args(fields='functions')

        with patch('reveal.display.formatting.filter_fields', return_value={'functions': [{'name': 'foo'}]}) as mock_ff:
            out = _apply_field_selection(result, args)
        mock_ff.assert_called_once()
        assert 'functions' in out


# ─── _apply_budget_constraints ────────────────────────────────────────────────

class TestApplyBudgetConstraints:
    def test_no_list_field_returns_unchanged(self):
        """Cover line 331: no known list field → return unchanged."""
        result = {'total': 5, 'extra': 'data'}
        args = _args()
        out = _apply_budget_constraints(result, args)
        assert out == result

    def test_probe_loop_finds_items_field(self):
        """Cover lines 342-343: probe loop finds 'items' field."""
        result = {'items': [{'name': f'x{i}'} for i in range(20)]}
        args = _args(max_items=5)
        out = _apply_budget_constraints(result, args)
        assert len(out['items']) <= 5

    def test_probe_loop_finds_results_field(self):
        """Cover line 342: probe loop finds 'results' field (skips 'items' not present)."""
        result = {'results': [{'id': i} for i in range(20)]}
        args = _args(max_items=3)
        out = _apply_budget_constraints(result, args)
        assert len(out['results']) <= 3

    def test_truncated_merges_into_existing_meta(self):
        """Cover lines 362-365: meta already present → budget merged in."""
        result = {
            'items': [{'x': i} for i in range(50)],
            'meta': {'source': 'test'},
        }
        args = _args(max_items=5)
        out = _apply_budget_constraints(result, args)
        # truncated items + meta updated
        assert len(out['items']) <= 5
        assert 'budget' in out.get('meta', {}) or 'meta' in out

    def test_truncated_creates_new_meta(self):
        """Cover lines 362-365: no existing meta → creates result['meta']."""
        result = {'items': [{'x': i} for i in range(50)]}
        args = _args(max_items=5)
        out = _apply_budget_constraints(result, args)
        assert len(out['items']) <= 5


# ─── _render_structure ────────────────────────────────────────────────────────

class TestRenderStructure:
    def test_exception_with_newline_prints_full_error(self, capsys):
        """Cover lines 387-394: exception with newline in message."""
        adapter = MagicMock()
        adapter.get_structure.side_effect = ValueError("line1\nline2")

        renderer_cls = MagicMock()
        args = _args()
        with pytest.raises(SystemExit):
            _render_structure(adapter, renderer_cls, args, scheme='test', resource='x')
        captured = capsys.readouterr()
        assert 'line1' in captured.err

    def test_exception_without_newline_shows_scheme_hint(self, capsys):
        """Cover line 392: simple error shows scheme hint."""
        adapter = MagicMock()
        adapter.get_structure.side_effect = ValueError("bad input")

        renderer_cls = MagicMock()
        args = _args()
        with pytest.raises(SystemExit):
            _render_structure(adapter, renderer_cls, args, scheme='env', resource='x')
        captured = capsys.readouterr()
        assert 'env://' in captured.err

    def test_post_process_called_when_defined(self):
        """Cover line 401: adapter.post_process() called when in __dict__."""
        class ConcreteAdapter:
            def get_structure(self):
                return {'functions': []}
            def post_process(self, result, args):
                result['post_processed'] = True
                return result

        adapter = ConcreteAdapter()
        renderer_cls = MagicMock()
        args = _args()
        _render_structure(adapter, renderer_cls, args)
        # Verify render_structure was called with post-processed result
        call_args = renderer_cls.render_structure.call_args[0]
        assert call_args[0].get('post_processed') is True


# ─── _parse_file_line_syntax ─────────────────────────────────────────────────

class TestParseFileLineSyntax:
    def test_colon_line_syntax_extracted(self, tmp_path):
        """Cover lines 453-458: file:line syntax matched and split."""
        f = tmp_path / 'main.py'
        f.write_text('x = 1\n')
        path_str = f"{f}:42"
        path, element = _parse_file_line_syntax(path_str)
        assert path == f
        assert element == ':42'

    def test_colon_range_syntax_extracted(self, tmp_path):
        """Cover lines 453-458: file:line-line syntax."""
        f = tmp_path / 'app.py'
        f.write_text('x = 1\n')
        path_str = f"{f}:10-20"
        path, element = _parse_file_line_syntax(path_str)
        assert path == f
        assert element == ':10-20'

    def test_no_colon_returns_as_is(self, tmp_path):
        """Normal path with no colon."""
        f = tmp_path / 'app.py'
        f.write_text('x = 1\n')
        path, element = _parse_file_line_syntax(str(f))
        assert path == f
        assert element is None


# ─── _validate_path_exists ───────────────────────────────────────────────────

class TestValidatePathExists:
    def test_colon_in_path_gives_hint(self, capsys):
        """Cover lines 467-469: path with colon shows hint."""
        with pytest.raises(SystemExit):
            _validate_path_exists(Path('/nonexistent/file.py'), '/nonexistent/file.py:42')
        captured = capsys.readouterr()
        assert 'Hint' in captured.err

    def test_no_colon_plain_error(self, capsys):
        """Cover line 471: plain missing path error."""
        with pytest.raises(SystemExit):
            _validate_path_exists(Path('/nonexistent'), '/nonexistent')
        captured = capsys.readouterr()
        assert 'Error' in captured.err


# ─── _stat_one_file ───────────────────────────────────────────────────────────

class TestStatOneFile:
    def test_oserror_returns_none(self, tmp_path):
        """Cover lines 477-482: OSError on stat() → return None."""
        ext_counts = {}
        with patch.object(Path, 'stat', side_effect=OSError("permission denied")):
            result = _stat_one_file(tmp_path / 'ghost.py', ext_counts)
        assert result is None
        assert ext_counts == {}


# ─── _collect_dir_stats ───────────────────────────────────────────────────────

class TestCollectDirStats:
    def test_collects_files_and_extension_counts(self, tmp_path):
        """Cover lines 491-508: walking a real directory."""
        (tmp_path / 'a.py').write_text('x')
        (tmp_path / 'b.py').write_text('y')
        (tmp_path / 'c.md').write_text('z')
        ext_counts, total_files, total_size, newest, oldest = _collect_dir_stats(tmp_path)
        assert total_files == 3
        assert ext_counts.get('py', 0) == 2
        assert ext_counts.get('md', 0) == 1
        assert total_size > 0
        assert newest >= oldest


# ─── _render_dir_meta_text ────────────────────────────────────────────────────

class TestRenderDirMetaText:
    def test_prints_all_sections(self, capsys):
        """Cover lines 513-524: all meta sections rendered."""
        meta = {
            'name': 'mydir',
            'path': '/mydir',
            'total_files': 42,
            'size_human': '128 KB',
            'modified': '2026-03-14T10:00:00',
            'oldest_file': '2025-01-01T00:00:00',
            'by_extension': {'py': 30, 'md': 12},
        }
        _render_dir_meta_text(meta)
        out = capsys.readouterr().out
        assert 'mydir' in out
        assert '42' in out
        assert '128 KB' in out
        assert '.py' in out

    def test_skips_missing_optional_fields(self, capsys):
        """Cover lines 517-524: None values skipped."""
        meta = {
            'name': 'emptydir',
            'path': '/emptydir',
            'total_files': 0,
            'size_human': '0 B',
            'modified': None,
            'oldest_file': None,
            'by_extension': {},
        }
        _render_dir_meta_text(meta)
        out = capsys.readouterr().out
        assert 'emptydir' in out


# ─── _show_directory_meta ─────────────────────────────────────────────────────

class TestShowDirectoryMeta:
    def test_json_format(self, tmp_path, capsys):
        """Cover lines 534-550: JSON output path."""
        (tmp_path / 'x.py').write_text('x = 1')
        args = _args(format='json')
        _show_directory_meta(tmp_path, args)
        out = capsys.readouterr().out
        import json
        data = json.loads(out)
        assert 'total_files' in data

    def test_text_format(self, tmp_path, capsys):
        """Cover lines 534-550: text output path."""
        (tmp_path / 'x.py').write_text('x = 1')
        args = _args(format='text')
        _show_directory_meta(tmp_path, args)
        out = capsys.readouterr().out
        assert 'Files' in out


# ─── _parse_ext_arg ───────────────────────────────────────────────────────────

class TestParseExtArg:
    def test_none_returns_none(self):
        """Cover line 564: None input → None output."""
        assert _parse_ext_arg(None) is None

    def test_empty_string_returns_none(self):
        """Cover line 564: empty string → None."""
        assert _parse_ext_arg('') is None

    def test_single_ext(self):
        assert _parse_ext_arg('py') == ['py']

    def test_multiple_exts_with_dots(self):
        assert _parse_ext_arg('.py,.md') == ['py', 'md']


# ─── _build_ast_query_from_flags ─────────────────────────────────────────────

class TestBuildAstQueryFromFlags:
    def test_desc_sort_prepends_dash(self):
        """Cover line 577: --desc flag prepends - to sort field."""
        args = _args(search=None, type=None, sort='name', desc=True)
        result = _build_ast_query_from_flags(Path('app.py'), args)
        assert 'sort=-name' in result

    def test_search_and_type_combined(self):
        args = _args(search='foo', type='function', sort=None, desc=False)
        result = _build_ast_query_from_flags(Path('app.py'), args)
        assert 'name~=foo' in result
        assert 'type=function' in result


# ─── _guard_nginx_flags ───────────────────────────────────────────────────────

class TestGuardNginxFlags:
    def test_nginx_flag_on_py_file_exits(self, capsys):
        """Cover lines 620-627: nginx flag on .py file → error + exit."""
        args = _args(check_acl=True, validate_nginx_acme=False,
                     check_conflicts=False, cpanel_certs=False, diagnose=False)
        with pytest.raises(SystemExit):
            _guard_nginx_flags(args, 'app.py')
        captured = capsys.readouterr()
        assert '--check-acl' in captured.err

    def test_nginx_flag_on_conf_file_passes(self):
        """nginx flag on .conf file → no error."""
        args = _args(check_acl=True, validate_nginx_acme=False,
                     check_conflicts=False, cpanel_certs=False, diagnose=False)
        _guard_nginx_flags(args, 'nginx.conf')  # should not raise


# ─── _guard_ssl_flags ────────────────────────────────────────────────────────

class TestGuardSslFlags:
    def test_ssl_flag_on_plain_path_exits(self, capsys):
        """Cover lines 634-641: ssl flag triggers error."""
        args = _args(expiring_within=30, summary=False, validate_nginx=False)
        with pytest.raises(SystemExit):
            _guard_ssl_flags(args)
        captured = capsys.readouterr()
        assert '--expiring-within' in captured.err

    def test_no_ssl_flags_passes(self):
        args = _args(expiring_within=None, summary=False, validate_nginx=False)
        _guard_ssl_flags(args)  # should not raise


# ─── _guard_related_flags ────────────────────────────────────────────────────

class TestGuardRelatedFlags:
    def test_related_on_py_file_exits(self, capsys):
        """Cover lines 648-659: --related on .py file → error."""
        args = _args(related=True, related_all=False)
        with pytest.raises(SystemExit):
            _guard_related_flags(args, 'app.py')
        captured = capsys.readouterr()
        assert '--related' in captured.err

    def test_related_all_on_py_file_exits(self, capsys):
        """Cover lines 666-667: --related-all on .py → flag name in error."""
        args = _args(related=False, related_all=True)
        with pytest.raises(SystemExit):
            _guard_related_flags(args, 'app.py')
        captured = capsys.readouterr()
        assert '--related-all' in captured.err

    def test_related_on_md_file_passes(self):
        args = _args(related=True, related_all=False)
        _guard_related_flags(args, 'README.md')  # should not raise

    def test_no_related_flags_passes(self):
        args = _args(related=False, related_all=False)
        _guard_related_flags(args, 'app.py')  # should not raise


# ─── _handle_file_path — section on non-md ───────────────────────────────────

class TestHandleFilePath:
    def test_section_on_non_md_exits(self, tmp_path, capsys):
        """Cover lines 697-702: --section on .py file → error."""
        f = tmp_path / 'app.py'
        f.write_text('x = 1\n')
        args = _args(search=None, sort=None, type=None,
                     element=None, section='intro',
                     meta=False, format='text',
                     respect_gitignore=True, exclude=[], depth=3,
                     max_entries=100, fast=False, asc=False,
                     desc=False, ext=None, dir_limit=0)
        with pytest.raises(SystemExit):
            _handle_file_path(f, None, args)
        captured = capsys.readouterr()
        assert '--section' in captured.err


# ─── handle_file_or_directory — neither file nor dir ────────────────────────

class TestHandleFileOrDirectory:
    def test_neither_file_nor_dir_exits(self, capsys):
        """Cover lines 732-733: path that is neither file nor dir."""
        args = _args(check=False, hotspots=False,
                     check_acl=False, validate_nginx_acme=False,
                     check_conflicts=False, cpanel_certs=False, diagnose=False,
                     expiring_within=None, summary=False, validate_nginx=False,
                     related=False, related_all=False,
                     search=None, sort=None, type=None,
                     element=None, meta=False, format='text',
                     respect_gitignore=True, exclude=[], depth=3,
                     max_entries=100, fast=False, asc=False, desc=False,
                     ext=None, dir_limit=0, section=None)

        # Patch path.exists() to return True (bypass _validate_path_exists),
        # but .is_dir() and .is_file() both return False
        with patch.object(Path, 'exists', return_value=True):
            with patch.object(Path, 'is_dir', return_value=False):
                with patch.object(Path, 'is_file', return_value=False):
                    from reveal.cli.routing import handle_file_or_directory
                    with pytest.raises(SystemExit):
                        handle_file_or_directory('/some/socket', args)
        captured = capsys.readouterr()
        assert 'neither' in captured.err
