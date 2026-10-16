"""calls://, trace://, contracts:// and testability:// disclose a file whose analysis raised (BACK-1860).

BACK-1856 put the failure on ``StructureList.skipped`` and into ast:// and imports; these
consumers only read the list, so the file was a stderr line and the answer read complete.
"""
import pytest

from reveal.adapters.ast import analysis
from reveal.adapters.calls import CallsAdapter
from reveal.adapters.calls.index import build_callers_index
from reveal.adapters.contracts import ContractsAdapter
from reveal.adapters.testability import TestabilityAdapter
from reveal.adapters.trace import TraceAdapter


@pytest.fixture
def tree(tmp_path, monkeypatch):
    (tmp_path / 'ok.py').write_text('def a():\n    return b()\n\n\ndef b():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'bad.py').write_text('def c():\n    return a()\n', encoding='utf-8')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_ok.py').write_text(
        'from unittest import mock\n\n\ndef test_a():\n    with mock.patch("ok.b"):\n        pass\n',
        encoding='utf-8')
    real = analysis.create_element_dict

    def boom(file_path, *args, **kwargs):
        if file_path.endswith('bad.py'):
            raise ValueError('synthetic analyzer bug')
        return real(file_path, *args, **kwargs)

    monkeypatch.setattr(analysis, 'create_element_dict', boom)
    return tmp_path


def _failed(warnings):
    return [w for w in warnings if isinstance(w, dict) and w.get('type') == 'analysis_failed']


def _assert_names_bad_py(warnings):
    (warning,) = _failed(warnings)
    assert warning['count'] == 1
    assert warning['files'][0].endswith('bad.py')
    assert 'ValueError' in warning['message']


@pytest.mark.parametrize('query', [
    'target=a', 'callees=a', 'root=a', 'uncalled', 'rank=callers', 'modules'])
def test_calls_modes_warn_about_the_skipped_file(tree, query):
    result = CallsAdapter(str(tree), query).get_structure()
    _assert_names_bad_py(result['meta']['warnings'])
    assert 'analysis_skipped' not in result, 'the carrier key is consumed, not leaked into the data'


def test_calls_cached_index_keeps_its_skipped_files(tree):
    first = build_callers_index(str(tree))
    again = build_callers_index(str(tree))
    assert again is first
    assert [f.rsplit('/', 1)[-1] for f, _ in again.skipped] == ['bad.py']


def test_calls_clean_tree_has_no_analysis_warning(tmp_path):
    (tmp_path / 'ok.py').write_text('def a():\n    return 1\n', encoding='utf-8')
    result = CallsAdapter(str(tmp_path), 'target=a').get_structure()
    assert not _failed(result['meta']['warnings'])


def test_trace_warns_about_the_skipped_file(tree):
    result = TraceAdapter(str(tree), 'from=a').get_structure()
    assert any('could not be analyzed' in w and 'bad.py' in w for w in result['warnings'])


def test_contracts_warns_about_the_skipped_file(tree):
    result = ContractsAdapter(str(tree)).get_structure()
    _assert_names_bad_py(result['meta']['warnings'])
    assert 'analysis_skipped' not in result


def test_testability_warns_about_the_skipped_file(tree):
    result = TestabilityAdapter(str(tree), f'tests={tree / "tests"}').get_structure()
    _assert_names_bad_py(result['meta']['warnings'])
