"""Shared import service contracts on real small Python and C source trees."""
import subprocess
import sys
from dataclasses import FrozenInstanceError
import pytest
from reveal.analyzers.imports import service
from reveal.analyzers.imports.base import get_extractor
from reveal.analyzers.imports.types import ImportAnalysis, ImportGraph

pytestmark = pytest.mark.component


def test_service_does_not_load_resource_adapters():
    subprocess.run([sys.executable, '-c',
                    'import sys; import reveal.analyzers.imports.service; '
                    'assert not any(k.startswith("reveal.adapters") for k in sys.modules)'], check=True)


def test_primary_and_target_set_policies_remain_distinct(tmp_path):
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    for name in ('__init__', 'a', 'b'):
        (pkg / f'{name}.py').write_text('', encoding='utf-8')
    source = tmp_path / 'main.py'
    source.write_text('from pkg import a, b\n', encoding='utf-8')
    extractor = get_extractor(source)
    statement = extractor.extract_imports(source)[0]
    files = service.discover(service.ScanScope(tmp_path, frozenset({'.py'})))
    context = service.ResolutionContext(tmp_path, (tmp_path,), files.index)
    primary = service.resolve_primary(statement, extractor, context)
    targets = service.resolve_targets(statement, extractor, context)
    assert primary in targets
    assert {pkg / 'a.py', pkg / 'b.py'} <= set(targets)
    with pytest.raises(FrozenInstanceError):
        context.base_path = pkg


def test_resolution_preserves_partial_diagnostics_and_scoped_files(tmp_path):
    source = tmp_path / 'app.c'
    target = tmp_path / 'target.h'
    target.write_text('int probe(void);\n', encoding='utf-8')
    source.write_text('#include "target.h"\nint broken( {{{\n', encoding='utf-8')
    (tmp_path / 'irrelevant.py').write_text('import os\n', encoding='utf-8')
    extractor = get_extractor(source)
    imports = extractor.extract_imports(source)
    scope = service.ScanScope(tmp_path, frozenset({'.c', '.h'}))
    files = service.discover(scope)
    assert set(files.candidates) == {source, target} and not files.capped
    assert tmp_path / 'irrelevant.py' in files.index['irrelevant.py']
    artifact = ImportAnalysis(graph=ImportGraph.from_imports(imports),
                              scanned_files=set(files.candidates), files_failed=[source],
                              extractions={source: extractor.analysis}, diagnostics={'probe': ['partial']})
    result = service.resolve_graph(scope, files, artifact)
    assert result is artifact and result.graph.dependencies[source] == {target}
    assert result.files_failed == [source] and result.extractions[source].parse_failed
    assert result.diagnostics == {'probe': ['partial']}
    capped = service.discover(service.ScanScope(tmp_path, frozenset({'.c', '.h'}), cap=1))
    assert capped.capped and len(capped.candidates) == 1
    with pytest.raises(ValueError, match='extracted graph'):
        service.resolve_graph(scope, files, ImportAnalysis())
