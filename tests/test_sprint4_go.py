"""A projected package importer cannot depend on its own file."""
from reveal.adapters.depends import DependsAdapter
import pytest

pytestmark = pytest.mark.component


def test_external_test_package_has_other_dependents_without_its_own_file(tmp_path):
    (tmp_path / 'go.mod').write_text('module example.org/project\n\ngo 1.20\n', encoding='utf-8')
    (tmp_path / 'pkg').mkdir(); (tmp_path / 'use').mkdir()
    source = tmp_path / 'pkg/source.go'
    source.write_text('package pkg\nfunc Run() {}\n', encoding='utf-8')
    target = tmp_path / 'pkg/source_test.go'
    target.write_text('package pkg_test\nimport "example.org/project/pkg"\nfunc Test() {pkg.Run()}\n', encoding='utf-8')
    (tmp_path / 'use/use.go').write_text('package use\nimport "example.org/project/pkg"\nfunc Run() {pkg.Run()}\n', encoding='utf-8')
    result = DependsAdapter(str(target)).get_structure()
    assert [d['file'] for d in result['dependents']] == ['use/use.go']
    assert result['count'] == 1
    control = DependsAdapter(str(source)).get_structure()
    assert {d['file'] for d in control['dependents']} == {'pkg/source_test.go', 'use/use.go'}
