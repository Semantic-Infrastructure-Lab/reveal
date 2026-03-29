"""Tests for display/metadata.py — _format_display_key, _print_file_header, show_metadata."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from reveal.display.metadata import _format_display_key, _print_file_header, show_metadata


# ============================================================================
# _format_display_key
# ============================================================================

class TestFormatDisplayKey:
    def test_count_suffix_stripped(self):
        assert _format_display_key('parts_count') == 'Parts'

    def test_count_suffix_with_multiword(self):
        assert _format_display_key('sheet_count') == 'Sheet'

    def test_regular_key_title_cased(self):
        assert _format_display_key('encoding') == 'Encoding'

    def test_snake_case_converted(self):
        assert _format_display_key('created_at') == 'Created At'

    def test_single_word(self):
        assert _format_display_key('size') == 'Size'


# ============================================================================
# _print_file_header
# ============================================================================

class TestPrintFileHeader:
    def test_existing_file_shows_size_and_lines(self, tmp_path, capsys):
        f = tmp_path / 'test.py'
        f.write_text('line1\nline2\nline3\n')
        _print_file_header(f)
        captured = capsys.readouterr()
        assert 'test.py' in captured.out
        assert 'lines' in captured.out.lower() or 'B' in captured.out

    def test_nonexistent_file_prints_just_name(self, capsys):
        _print_file_header(Path('/tmp/does_not_exist_xyz.py'))
        captured = capsys.readouterr()
        assert 'does_not_exist_xyz.py' in captured.out

    def test_fallback_indicator_shown(self, tmp_path, capsys):
        f = tmp_path / 'script.sh'
        f.write_text('#!/bin/bash\n')
        _print_file_header(f, is_fallback=True, fallback_lang='bash')
        captured = capsys.readouterr()
        assert 'fallback: bash' in captured.out

    def test_no_fallback_indicator_when_not_set(self, tmp_path, capsys):
        f = tmp_path / 'app.py'
        f.write_text('x = 1\n')
        _print_file_header(f)
        captured = capsys.readouterr()
        assert 'fallback' not in captured.out

    def test_large_file_shows_kb(self, tmp_path, capsys):
        f = tmp_path / 'big.py'
        f.write_bytes(b'x' * 2048)  # 2KB
        _print_file_header(f)
        captured = capsys.readouterr()
        assert 'KB' in captured.out

    def test_size_bytes_for_small_file(self, tmp_path, capsys):
        f = tmp_path / 'tiny.py'
        f.write_bytes(b'x' * 100)
        _print_file_header(f)
        captured = capsys.readouterr()
        assert 'B' in captured.out

    def test_output_ends_with_blank_line(self, tmp_path, capsys):
        f = tmp_path / 'app.py'
        f.write_text('x = 1\n')
        _print_file_header(f)
        captured = capsys.readouterr()
        # print(f"{header}\n") adds a trailing newline
        assert captured.out.endswith('\n')


# ============================================================================
# show_metadata
# ============================================================================

class TestShowMetadata:
    def _make_analyzer(self, meta: dict):
        analyzer = MagicMock()
        analyzer.get_metadata.return_value = meta
        return analyzer

    def test_json_format_dumps_metadata(self, capsys):
        meta = {
            'name': 'app.py',
            'path': '/tmp/app.py',
            'size': 100,
            'size_human': '100B',
            'lines': 10,
        }
        analyzer = self._make_analyzer(meta)
        with patch('reveal.display.metadata.print_breadcrumbs'):
            show_metadata(analyzer, output_format='json')
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed['name'] == 'app.py'

    def test_human_format_prints_name(self, capsys):
        meta = {
            'name': 'app.py',
            'path': '/tmp/app.py',
            'size': 100,
            'size_human': '100B',
            'lines': 5,
        }
        analyzer = self._make_analyzer(meta)
        with patch('reveal.display.metadata.print_breadcrumbs'):
            show_metadata(analyzer, output_format='human')
        captured = capsys.readouterr()
        assert 'app.py' in captured.out
        assert '100B' in captured.out
        assert 'Lines' in captured.out or 'lines' in captured.out.lower()

    def test_human_format_shows_encoding_when_present(self, capsys):
        meta = {
            'name': 'f.txt',
            'path': '/tmp/f.txt',
            'size': 10,
            'size_human': '10B',
            'lines': 1,
            'encoding': 'utf-8',
        }
        analyzer = self._make_analyzer(meta)
        with patch('reveal.display.metadata.print_breadcrumbs'):
            show_metadata(analyzer, output_format='human')
        captured = capsys.readouterr()
        assert 'utf-8' in captured.out

    def test_human_format_omits_encoding_when_absent(self, capsys):
        meta = {
            'name': 'f.py',
            'path': '/tmp/f.py',
            'size': 10,
            'size_human': '10B',
        }
        analyzer = self._make_analyzer(meta)
        with patch('reveal.display.metadata.print_breadcrumbs'):
            show_metadata(analyzer, output_format='human')
        captured = capsys.readouterr()
        assert 'Encoding' not in captured.out

    def test_human_format_shows_extra_fields(self, capsys):
        meta = {
            'name': 'doc.xlsx',
            'path': '/tmp/doc.xlsx',
            'size': 5000,
            'size_human': '5.0KB',
            'parts_count': 3,
        }
        analyzer = self._make_analyzer(meta)
        with patch('reveal.display.metadata.print_breadcrumbs'):
            show_metadata(analyzer, output_format='human')
        captured = capsys.readouterr()
        # 'parts_count' should be formatted as 'Parts' with the int value
        assert 'Parts' in captured.out
        assert '3' in captured.out

    def test_integer_extra_field_formatted_with_commas(self, capsys):
        meta = {
            'name': 'big.xlsx',
            'path': '/tmp/big.xlsx',
            'size': 1000000,
            'size_human': '1.0MB',
            'row_count': 50000,
        }
        analyzer = self._make_analyzer(meta)
        with patch('reveal.display.metadata.print_breadcrumbs'):
            show_metadata(analyzer, output_format='human')
        captured = capsys.readouterr()
        assert '50,000' in captured.out
