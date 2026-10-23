"""?uncalled over JavaScript/TypeScript says its dead-code reading is measured low (BACK-1899).

The meta confidence is call-extraction recall. For ?uncalled over JS/TS/TSX it read 0.9997 over claims
a source review found 0 of 20 (three.js), 12 of 20 (VS Code) and 1 of 20 (Excalidraw) dead, so the
number is withheld and W-CALLS-11 names the measurement (plan rule 8).
"""
import json

import pytest

from conftest import _run_reveal_direct

TS = 'export function used() { return helper(); }\nfunction helper() { return 1; }\nfunction orphan() { return 2; }\n'
PY = 'def used():\n    return helper()\n\n\ndef helper():\n    return 1\n\n\ndef orphan():\n    return 2\n'


def meta_of(tmp_path, files, query):
    root = tmp_path / 'proj'
    root.mkdir()
    for name, text in files.items():
        (root / name).write_text(text, encoding='utf-8')
    out = _run_reveal_direct(f'calls://{root}?{query}', '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)['meta']


def codes(meta):
    return [w.get('code') for w in meta['warnings']]


@pytest.mark.parametrize('name', ['app.ts', 'app.tsx', 'app.js'])
def test_uncalled_over_js_ts_withholds_confidence_and_names_the_measurement(tmp_path, name):
    meta = meta_of(tmp_path, {name: TS}, 'uncalled=true')
    assert meta.get('confidence') is None
    warning = next(w for w in meta['warnings'] if w.get('code') == 'W-CALLS-11')
    assert warning['type'] == 'not_measured'
    assert warning['languages'] == [{'app.ts': 'typescript', 'app.tsx': 'tsx', 'app.js': 'javascript'}[name]]
    assert '0 of 20' in warning['message'] and 'review list' in warning['message']


def test_uncalled_over_python_keeps_its_confidence(tmp_path):
    """Negative control: the other languages' answers do not change."""
    meta = meta_of(tmp_path, {'app.py': PY}, 'uncalled=true')
    assert isinstance(meta['confidence'], float)
    assert 'W-CALLS-11' not in codes(meta)


def test_callers_over_js_ts_keeps_its_confidence(tmp_path):
    """Negative control: the figure is about the dead-code reading, not call extraction."""
    meta = meta_of(tmp_path, {'app.ts': TS}, 'callers=helper')
    assert isinstance(meta['confidence'], float)
    assert 'W-CALLS-11' not in codes(meta)


def test_a_mixed_scan_names_only_the_js_ts_languages(tmp_path):
    meta = meta_of(tmp_path, {'app.ts': TS, 'tool.py': PY}, 'uncalled=true')
    assert meta.get('confidence') is None
    warning = next(w for w in meta['warnings'] if w.get('code') == 'W-CALLS-11')
    assert warning['languages'] == ['typescript']
