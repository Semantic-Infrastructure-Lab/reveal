"""BACK-2570: when the import analysis behind call resolution stopped at its file cap, calls says so.

``imports://`` discloses its cap (``metadata.scan_budget``); the callee and caller resolution read the same
analysis and, for a file past the cap (no bindings), fall back to bare-name matching without a word.
The cap is lowered here (``path_scope``'s keyword default) so a handful of files exercise it.
"""

import pytest

import reveal.analyzers  # noqa: F401 -- registers the analyzers
from reveal.adapters.calls.adapter import CallsAdapter
from reveal.analyzers.imports import service

CODE = 'W-CALLS-13'


@pytest.fixture
def project(tmp_path):
    for name in 'abcde':
        (tmp_path / f'{name}.py').write_text(f'def helper_{name}(x):\n    return x\n', encoding='utf-8')
    (tmp_path / 'main.py').write_text(
        'from a import helper_a\nfrom b import helper_b\n\ndef run():\n    helper_a(1)\n    helper_b(2)\n', encoding='utf-8')
    return tmp_path


@pytest.fixture
def cap(monkeypatch):
    def set_cap(limit):
        monkeypatch.setitem(service.path_scope.__kwdefaults__, 'cap', limit)
    return set_cap


def _warnings(project, query):
    result = dict(CallsAdapter(str(project), query).get_structure())
    return [w for w in result.get('meta', {}).get('warnings', []) if w.get('code') == CODE]


@pytest.mark.parametrize('query', ['callers=helper_a', 'callees=run&depth=2', 'rank=callers'])
def test_a_capped_analysis_is_disclosed_by_every_mode_that_reads_it(project, cap, query):
    cap(3)
    (warning,) = _warnings(project, query)
    assert warning['type'] == 'analysis_capped'
    assert 'scan cap is 3' in warning['message'] and 'bare name' in warning['message']


@pytest.mark.parametrize('query', ['callers=helper_a', 'callees=run&depth=2', 'rank=callers'])
def test_an_uncapped_analysis_says_nothing(project, query):
    assert _warnings(project, query) == []


def test_a_project_whose_calls_go_through_no_import_says_nothing(tmp_path, cap):
    cap(2)  # capped, but no call is bound by an import, so the analysis is never read
    for name in 'abcd':
        (tmp_path / f'{name}.py').write_text(f'def f_{name}():\n    return g_{name}()\n\ndef g_{name}():\n    return 1\n',
                                             encoding='utf-8')
    assert _warnings(tmp_path, 'callers=g_a') == []
