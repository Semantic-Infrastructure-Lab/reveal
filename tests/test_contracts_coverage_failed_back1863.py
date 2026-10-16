"""contracts coverage.analyzed_files does not count a file whose analysis raised (BACK-1863)."""
import pytest

from reveal.adapters.ast import analysis
from reveal.adapters.contracts import ContractsAdapter

pytestmark = pytest.mark.component


def _structure(tmp_path, monkeypatch, fail):
    (tmp_path / 'ok.py').write_text('class A:\n    pass\n', encoding='utf-8')
    (tmp_path / 'bad.py').write_text('class B:\n    pass\n', encoding='utf-8')
    real = analysis.create_element_dict

    def boom(file_path, *args, **kwargs):
        if fail and file_path.endswith('bad.py'):
            raise ValueError('synthetic analyzer bug')
        return real(file_path, *args, **kwargs)

    monkeypatch.setattr(analysis, 'create_element_dict', boom)
    return ContractsAdapter(str(tmp_path)).get_structure()


def test_a_failed_file_is_not_counted_as_analyzed(tmp_path, monkeypatch):
    result = _structure(tmp_path, monkeypatch, fail=True)
    assert result['coverage']['total_code_files'] == 2
    assert result['coverage']['analyzed_files'] == 1


def test_no_failure_counts_every_supported_file(tmp_path, monkeypatch):
    result = _structure(tmp_path, monkeypatch, fail=False)
    assert result['coverage']['analyzed_files'] == 2
