"""?uncalled prints no confidence in any language (BACK-2195, D8).

The meta confidence is call-extraction recall (BACK-1198). Over `?uncalled` it read as the
trustworthiness of a dead-code list: Go printed 0.9989 over claims measured at about 13% precision.
`?uncalled` is retired (D8) and until the cut it answers unchanged in shape, but it no longer prints a
number it cannot back. The W-CALLS-5 caveat says so; W-CALLS-11 keeps naming the measured figures for
the families that have them.
"""
import json

import pytest

from conftest import _run_reveal_direct

SOURCES = {
    'app.go': 'package main\n\nfunc used() int { return helper() }\n\nfunc helper() int { return 1 }\n\nfunc orphan() int { return 2 }\n',
    'app.py': 'def used():\n    return helper()\n\n\ndef helper():\n    return 1\n\n\ndef orphan():\n    return 2\n',
    'app.rb': "def used\n  helper\nend\n\ndef helper\n  1\nend\n\ndef orphan\n  2\nend\n",
    'app.ts': 'export function used() { return helper(); }\nfunction helper() { return 1; }\nfunction orphan() { return 2; }\n',
}


def meta_of(tmp_path, name, query):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / name).write_text(SOURCES[name], encoding='utf-8')
    out = _run_reveal_direct(f'calls://{root}?{query}', '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)['meta']


@pytest.mark.parametrize('name', sorted(SOURCES))
def test_uncalled_withholds_the_confidence_in_every_language(tmp_path, name):
    assert meta_of(tmp_path, name, 'uncalled=true').get('confidence') is None


@pytest.mark.parametrize('name', sorted(SOURCES))
def test_callers_keep_their_confidence(tmp_path, name):
    """Negative control: the number is call-extraction recall, which `?callers` is."""
    assert isinstance(meta_of(tmp_path, name, 'callers=helper')['confidence'], float)


def test_the_derived_signal_caveat_no_longer_points_at_a_confidence_above(tmp_path):
    warnings = meta_of(tmp_path, 'app.go', 'uncalled=true')['warnings']
    caveat = next(w for w in warnings if w.get('code') == 'W-CALLS-5')
    assert 'confidence above' not in caveat['message']
    assert 'no confidence' in caveat['message']
