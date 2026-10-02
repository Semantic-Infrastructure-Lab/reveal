"""BACK-1614: json://?sort= over values that don't compare says it did not sort,
instead of returning source order as if sorted."""

import json

from reveal.adapters.json.adapter import JsonAdapter
from reveal.adapters.json.renderer import JsonRenderer


def test_incomparable_sort_is_disclosed(tmp_path, capsys):
    data = tmp_path / 'mixed.json'
    data.write_text(json.dumps([{'a': 1}, {'a': 'x'}, {'a': 3}]), encoding='utf-8')
    result = JsonAdapter(str(data), 'sort=a').get_structure()
    assert [v['a'] for v in result['value']] == [1, 'x', 3]  # source order
    warning, = result['warnings']
    assert warning['type'] == 'sort_failed' and "Not sorted by 'a'" in warning['message']
    JsonRenderer.render_structure(result, 'text')
    assert "⚠ Not sorted by 'a'" in capsys.readouterr().out


def test_comparable_sort_has_no_warning(tmp_path):
    data = tmp_path / 'nums.json'
    data.write_text(json.dumps([{'a': 3}, {'a': 1}]), encoding='utf-8')
    result = JsonAdapter(str(data), 'sort=a').get_structure()
    assert [v['a'] for v in result['value']] == [1, 3]
    assert 'warnings' not in result
