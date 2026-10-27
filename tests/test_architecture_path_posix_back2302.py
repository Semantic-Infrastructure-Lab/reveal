"""``architecture://`` names its target with '/' on every OS (BACK-2302).

The ordinary (non-diff) report wrote ``'path': str(path)``, and the request-error
result of ``against=`` wrote ``source=self.path`` (``str(Path(resource))``), so on
Windows a nested target came back as ``pkg\\sub``; the ``architecture_diff`` sibling
already spelled it with ``as_spelled`` (BACK-2282). Linux cannot produce that spelling
from a real tree, so each case hands the adapter a target that already spells it the
Windows way and stubs the analysis, as ``tests/test_calls_records_posix_back2189.py``
does for the calls records.
"""

import pytest

from reveal.adapters import architecture
from reveal.adapters import imports as imports_adapter
from reveal.adapters.architecture import ArchitectureAdapter

NATIVE = 'pkg\\sub'


@pytest.fixture
def stub_analysis(monkeypatch):
    """No walk: the report is built from empty facts, so only the target's spelling shows."""
    monkeypatch.setattr(architecture, '_run_combined_analysis', lambda *_a, **_k: ([], {}))
    monkeypatch.setattr(architecture, '_run_complex_functions', lambda *_a, **_k: [])
    monkeypatch.setattr(architecture, '_run_scope', lambda *_a, **_k: {})
    monkeypatch.setattr(imports_adapter, 'detect_autoload_regime', lambda *_a, **_k: None)


@pytest.mark.parametrize('query', ['', 'no_imports=true'])
def test_report_path_and_source_use_forward_slashes(stub_analysis, query):
    result = ArchitectureAdapter(NATIVE, query).get_structure()

    assert result['path'] == 'pkg/sub', result
    assert result['source'] == 'pkg/sub', result


def test_forward_slash_target_is_unchanged(stub_analysis):
    """Negative control: a target already spelled with '/' is reported exactly as before."""
    result = ArchitectureAdapter('pkg/sub').get_structure()

    assert result['path'] == 'pkg/sub'
    assert result['source'] == 'pkg/sub'


def test_real_directory_report_keeps_its_spelling_and_type(tmp_path):
    """Negative control on a real tree: the absolute target is unchanged and still a directory."""
    (tmp_path / 'mod.py').write_text('def f():\n    return 1\n', encoding='utf-8')

    result = ArchitectureAdapter(str(tmp_path), 'no_imports=true').get_structure()

    assert result['path'] == tmp_path.as_posix()
    assert result['source_type'] == 'directory'


def test_against_request_error_source_uses_forward_slashes(tmp_path, monkeypatch):
    """The ``against=`` request-error result is the other builder in this module that names the target."""
    monkeypatch.chdir(tmp_path)

    result = ArchitectureAdapter(NATIVE, 'against=HEAD').get_structure()

    assert result['type'] == 'architecture_diff'
    assert result['meta']['errors'][0]['code'] == 'invalid_request', result
    assert result['source'] == 'pkg/sub', result
