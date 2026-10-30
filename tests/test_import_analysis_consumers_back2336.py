"""Analysis consumers can work when the imports URI adapter is unavailable."""
from pathlib import Path

import pytest

from reveal.adapters.imports import ImportsAdapter
from reveal.adapters.architecture import ArchitectureAdapter
from reveal.adapters.overview import OverviewAdapter
from reveal.adapters.depends import DependsAdapter
from reveal.adapters.pack import _build_pack_import_graph
from reveal.diff.architecture_diff import _snapshot

pytestmark = pytest.mark.component


@pytest.fixture
def tree(tmp_path):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="service-consumer"\n', encoding='utf-8')
    (tmp_path / 'a.py').write_text('import bb\ndef run():\n    return bb.value()\n', encoding='utf-8')
    (tmp_path / 'bb.py').write_text('def value():\n    return 1\n', encoding='utf-8')
    return tmp_path


@pytest.fixture
def no_uri_adapter(monkeypatch):
    def unavailable(*args, **kwargs):
        raise AssertionError('an analysis consumer constructed the URI adapter')
    monkeypatch.setattr(ImportsAdapter, '__init__', unavailable)


def test_architecture_uses_real_service_artifact(tree, no_uri_adapter):
    answer = ArchitectureAdapter(str(tree)).get_structure()
    assert any(Path(row['file']).name == 'bb.py' and row['fan_in'] == 1
               for row in answer['map']['fan_in']['rows'])
    assert not answer.get('meta', {}).get('errors')


def test_overview_uses_real_service_artifact(tree, no_uri_adapter):
    answer = OverviewAdapter(str(tree)).get_structure()
    assert any(Path(row['file']).name == 'bb.py' and row['fan_in'] == 1
               for row in answer['map']['fan_in']['rows'])
    assert not any('ImportsAdapter' in e['message'] for e in answer.get('meta', {}).get('errors', []))


def test_depends_uses_real_service_artifact(tree, no_uri_adapter):
    answer = DependsAdapter(str(tree / 'bb.py')).get_structure()
    assert {Path(row['file']).name for row in answer['dependents']} == {'a.py'}


def test_pack_uses_real_service_artifact(tree, no_uri_adapter):
    failures = []
    graph, scanned = _build_pack_import_graph(tree, failures)
    assert failures == []
    assert graph.reverse_deps[tree / 'bb.py'] == {tree / 'a.py'}
    assert scanned == {tree / 'a.py', tree / 'bb.py'}


def test_comparison_uses_real_service_artifact(tree, no_uri_adapter):
    answer = _snapshot(tree, 10)
    assert answer['completeness']['imports'] == 'complete'
    assert any(Path(row['file']).name == 'bb.py' and row['fan_in'] == 1
               for row in answer['fan_in_out'])


def test_existing_uri_adapter_remains_a_presentation_sibling(tree):
    answer = ImportsAdapter(str(tree), 'rank=fan-in&scope=path').get_structure()
    assert any(row['file'] == 'bb.py' and row['fan_in'] == 1 for row in answer['entries'])
