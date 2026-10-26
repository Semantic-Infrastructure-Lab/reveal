"""?uncalled over JS/TS, Java and PHP says its dead-code reading is measured low (BACK-1899).

The meta confidence is call-extraction recall. For ?uncalled over JS/TS/TSX it read 0.9997 over claims
a source review found 0 of 20 (three.js), 12 of 20 (VS Code) and 1 of 20 (Excalidraw) dead, so the
number is withheld and W-CALLS-11 names the measurement (plan rule 8). Java (1 of 20 Elasticsearch, 1 of 20
Guava) and PHP (1 of 20 WordPress) were measured the same way, re-drawn after BACK-2170 and BACK-2171.
"""
import json

import pytest

from conftest import _run_reveal_direct

TS = 'export function used() { return helper(); }\nfunction helper() { return 1; }\nfunction orphan() { return 2; }\n'
JAVA = 'class A {\n  int used() { return helper(); }\n  int helper() { return 1; }\n  int orphan() { return 2; }\n}\n'
PHP = '<?php\nfunction used() { return helper(); }\nfunction helper() { return 1; }\nfunction orphan() { return 2; }\n'
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


def test_uncalled_over_python_has_no_confidence_and_no_measured_low_warning(tmp_path):
    """Python has no measured-low figure, so no W-CALLS-11; the confidence is withheld everywhere (BACK-2195)."""
    meta = meta_of(tmp_path, {'app.py': PY}, 'uncalled=true')
    assert meta.get('confidence') is None
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


@pytest.mark.parametrize('name,text,language,figure', [
    ('A.java', JAVA, 'java', '1 of 20 (Elasticsearch server'),
    ('app.php', PHP, 'php', '1 of 20 (WordPress)'),
])
def test_uncalled_over_java_and_php_withholds_confidence_and_states_only_its_own_figures(
        tmp_path, name, text, language, figure):
    meta = meta_of(tmp_path, {name: text}, 'uncalled=true')
    assert meta.get('confidence') is None
    warning = next(w for w in meta['warnings'] if w.get('code') == 'W-CALLS-11')
    assert warning['languages'] == [language]
    assert figure in warning['message'] and 'review list' in warning['message']
    assert 'three.js' not in warning['message'] or language == 'javascript'
    others = {'java': 'WordPress', 'php': 'Guava'}[language]
    assert others not in warning['message']


@pytest.mark.parametrize('name,text', [('A.java', JAVA), ('app.php', PHP)])
def test_callers_over_java_and_php_keeps_its_confidence(tmp_path, name, text):
    """Negative control: the figure is about the dead-code reading, not call extraction."""
    meta = meta_of(tmp_path, {name: text}, 'callers=helper')
    assert isinstance(meta['confidence'], float)
    assert 'W-CALLS-11' not in codes(meta)
