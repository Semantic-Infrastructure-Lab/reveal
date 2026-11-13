"""Absence uses the same published path in its identity and owned message."""
import json

import pytest

from conftest import _run_reveal_in
from reveal.adapters.calls.adapter import CallsAdapter


@pytest.mark.parametrize('selector', ['callers=missing', 'callees=missing', 'target=missing&depth=2', 'root=missing'])
@pytest.mark.parametrize('incomplete', [False, True])
def test_windows_spelling_preserves_absence_and_incomplete_exits(tmp_path, monkeypatch, selector, incomplete):
    (tmp_path / 'app.py').write_text('def present():\n    return 1\n', encoding='utf-8')
    original = CallsAdapter._answer
    def answer(self, result_type, data, **kwargs):
        data['path'] = r'C:\fixture\src'
        if incomplete:
            data['analysis_skipped'] = [('lost.py', 'PermissionError: denied')]
        return original(self, result_type, data, **kwargs)
    monkeypatch.setattr(CallsAdapter, '_answer', answer)
    result = _run_reveal_in(tmp_path, 'calls://.?'+selector, '--format', 'json')
    body = json.loads(result.stdout)
    assert body['path'] == 'C:/fixture/src'
    assert result.returncode == (3 if incomplete else 2), result.stderr
    if incomplete:
        assert 'error' not in body
        assert any(w['type'] == 'analysis_failed' for w in body['meta']['warnings'])
    else:
        assert body['error'] == "Function 'missing' not found in C:/fixture/src"
        assert not body['meta']['errors']
