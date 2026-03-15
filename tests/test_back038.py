"""Tests for BACK-038: json:// ?flatten type mismatch fix + ?flatten&data-only flag.

Issues fixed:
1. _TYPE_RENDERERS used hyphens (json-flatten) but adapter output underscores
   (json_flatten) → renderer never fired, output was raw JSON dict.
   Fix: normalize underscore→hyphen in render_json_result before lookup.
2. ?flatten output includes header lines (# File, # Path) that break jq piping.
   Fix: ?flatten&data-only omits header and, for --format json, outputs only
   the lines array.
"""

import json
import pytest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from reveal.adapters.json.adapter import JsonAdapter
from reveal.adapters.json.introspection import get_flatten_result
from reveal.rendering.adapters.json_adapter import render_json_result


def _capture(fn, *args, **kwargs):
    buf = StringIO()
    with patch('sys.stdout', buf):
        fn(*args, **kwargs)
    return buf.getvalue()


# ─── get_flatten_result: data_only flag ──────────────────────────────────────

class TestGetFlattenResultDataOnly:
    def test_data_only_sets_flag(self, tmp_path):
        result = get_flatten_result({'a': 1}, tmp_path / 'f.json', [], data_only=True)
        assert result['data_only'] is True

    def test_no_data_only_by_default(self, tmp_path):
        result = get_flatten_result({'a': 1}, tmp_path / 'f.json', [])
        assert 'data_only' not in result

    def test_lines_present_regardless(self, tmp_path):
        result = get_flatten_result({'a': 1}, tmp_path / 'f.json', [], data_only=True)
        assert isinstance(result['lines'], list)
        assert len(result['lines']) > 0


# ─── JsonAdapter: ?flatten&data-only detection ───────────────────────────────

class TestJsonAdapterFlattenDataOnly:
    def test_flatten_data_only_recognized_as_legacy(self, tmp_path):
        f = tmp_path / 'x.json'
        f.write_text('{"key": "value"}')
        adapter = JsonAdapter(str(f), 'flatten&data-only')
        # _is_legacy_query() should return True
        assert adapter._is_legacy_query() is True

    def test_gron_data_only_recognized_as_legacy(self, tmp_path):
        f = tmp_path / 'x.json'
        f.write_text('{"key": "value"}')
        adapter = JsonAdapter(str(f), 'gron&data-only')
        assert adapter._is_legacy_query() is True

    def test_flatten_data_only_sets_data_only_in_result(self, tmp_path):
        f = tmp_path / 'x.json'
        f.write_text('{"key": "value"}')
        adapter = JsonAdapter(str(f), 'flatten&data-only')
        result = adapter.get_structure()
        assert result.get('data_only') is True
        assert result['type'] == 'json_flatten'

    def test_plain_flatten_no_data_only(self, tmp_path):
        f = tmp_path / 'x.json'
        f.write_text('{"key": "value"}')
        adapter = JsonAdapter(str(f), 'flatten')
        result = adapter.get_structure()
        assert 'data_only' not in result


# ─── Renderer: type normalization ─────────────────────────────────────────────

class TestRenderJsonTypeNormalization:
    def test_underscore_type_fires_flatten_renderer(self):
        """json_flatten (underscore) should now invoke the dedicated renderer."""
        data = {
            'type': 'json_flatten',
            'file': '/path/x.json',
            'path': '(root)',
            'lines': ['json.key = "v"'],
        }
        out = _capture(render_json_result, data, 'text')
        # Should get the formatted output, not raw JSON dump
        assert 'json.key = "v"' in out
        # Header present (not data-only)
        assert '# File:' in out

    def test_hyphen_type_still_fires_flatten_renderer(self):
        """json-flatten (hyphen, legacy test fixture form) still works."""
        data = {
            'type': 'json-flatten',
            'file': '/path/x.json',
            'path': '(root)',
            'lines': ['json.x = 1'],
        }
        out = _capture(render_json_result, data, 'text')
        assert 'json.x = 1' in out
        assert '# File:' in out

    def test_underscore_type_normalizes_for_other_types(self):
        """json_schema, json_type etc. should also normalize correctly."""
        data = {
            'type': 'json_type',
            'file': '/path/x.json',
            'path': '(root)',
            'value_type': 'Object',
        }
        out = _capture(render_json_result, data, 'text')
        assert 'Object' in out
        # Should not fall through to raw JSON (which would include 'source_type')
        # The dedicated renderer prints value_type without wrapping


# ─── Renderer: data-only flatten ─────────────────────────────────────────────

class TestRenderFlattenDataOnly:
    def test_data_only_text_omits_header(self):
        data = {
            'type': 'json_flatten',
            'file': '/path/x.json',
            'path': '(root)',
            'lines': ['json.key = "value"', 'json.n = 42'],
            'data_only': True,
        }
        out = _capture(render_json_result, data, 'text')
        assert '# File:' not in out
        assert '# Path:' not in out
        assert 'json.key = "value"' in out
        assert 'json.n = 42' in out

    def test_data_only_false_shows_header(self):
        data = {
            'type': 'json_flatten',
            'file': '/path/x.json',
            'path': '(root)',
            'lines': ['json.key = "value"'],
            'data_only': False,
        }
        out = _capture(render_json_result, data, 'text')
        assert '# File:' in out

    def test_data_only_json_format_outputs_only_lines_array(self):
        data = {
            'type': 'json_flatten',
            'file': '/path/x.json',
            'path': '(root)',
            'lines': ['json.key = "value"', 'json.n = 42'],
            'line_count': 2,
            'data_only': True,
        }
        out = _capture(render_json_result, data, 'json')
        parsed = json.loads(out)
        # Should be just the array, not the full dict
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0] == 'json.key = "value"'

    def test_normal_flatten_json_format_outputs_full_dict(self):
        data = {
            'type': 'json_flatten',
            'file': '/path/x.json',
            'path': '(root)',
            'lines': ['json.key = "value"'],
            'line_count': 1,
        }
        out = _capture(render_json_result, data, 'json')
        parsed = json.loads(out)
        # Should be the full dict (normal format=json behavior)
        assert isinstance(parsed, dict)
        assert parsed['type'] == 'json_flatten'


# ─── End-to-end: adapter → renderer ──────────────────────────────────────────

class TestFlattenEndToEnd:
    def test_flatten_renders_lines_not_raw_dict(self, tmp_path):
        """Regression test: before fix, ?flatten output raw JSON dict, not lines."""
        f = tmp_path / 'x.json'
        f.write_text('{"name": "alice", "score": 100}')
        adapter = JsonAdapter(str(f), 'flatten')
        result = adapter.get_structure()
        out = _capture(render_json_result, result, 'text')
        # Lines should be printed, not raw dict fields
        assert 'name' in out
        assert '# File:' in out
        # Should NOT be a raw JSON dict (which would show contract_version etc.)
        assert 'contract_version' not in out

    def test_flatten_data_only_no_header(self, tmp_path):
        f = tmp_path / 'x.json'
        f.write_text('{"name": "alice"}')
        adapter = JsonAdapter(str(f), 'flatten&data-only')
        result = adapter.get_structure()
        out = _capture(render_json_result, result, 'text')
        assert '# File:' not in out
        assert 'name' in out

    def test_flatten_data_only_json_gives_lines_array(self, tmp_path):
        f = tmp_path / 'x.json'
        f.write_text('{"name": "alice", "score": 100}')
        adapter = JsonAdapter(str(f), 'flatten&data-only')
        result = adapter.get_structure()
        out = _capture(render_json_result, result, 'json')
        parsed = json.loads(out)
        assert isinstance(parsed, list)
        assert any('name' in line for line in parsed)
