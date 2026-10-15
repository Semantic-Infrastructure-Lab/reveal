"""Independent mixed-framework measurement and failed-prerequisite controls."""
from pathlib import Path
from unittest.mock import Mock

import pytest

from test_recall_gate import _load, compiler_oracle  # optional compiler fixture

_load('fetch_corpus')
matrix = _load('framework_matrix')
TOOLCHAIN = {'typescript_version': '5.9.3', 'node_version': '22.14.0'}
pytestmark = pytest.mark.component


def test_component_and_contract_answers_are_independent(tmp_path, compiler_oracle, monkeypatch):
    path = tmp_path / 'App.tsx'
    path.write_text('interface Props { name: string; }\nfunction App(){ return <UI.Button><Renamed/><div/></UI.Button>; }\n', encoding='utf-8')
    answer = matrix.check_file(path, ['jsx', 'interfaces'], TOOLCHAIN)
    assert answer['jsx']['expected'] == answer['jsx']['actual'] == 2
    assert answer['interfaces']['actual'] == 1
    original = matrix.analyze_file
    def dropped(path):
        result = original(path)
        result['jsx_references'] = result['jsx_references'][1:]
        return result
    monkeypatch.setattr(matrix, 'analyze_file', dropped)
    with pytest.raises(RuntimeError, match='mismatch'):
        matrix.check_file(path, ['jsx'], TOOLCHAIN)


def test_compiler_scope_owner_sample_catches_wrong_reveal_owner(tmp_path, compiler_oracle, monkeypatch):
    path = tmp_path / 'Owners.tsx'
    path.write_text('const App = () => <Button/>;\n'
                    'const Wrapped = forwardRef((props, ref) => <Button/>);\n'
                    'class Panel extends React.Component { render(){ return <Button/>; } }\n',
                    encoding='utf-8')
    answer = matrix.check_file(path, ['jsx-owner'], TOOLCHAIN)['jsx-owner']
    assert answer['expected'] == answer['actual'] == 3
    original = matrix.jsx_component_references
    def wrong_owner(analyzer, elements):
        rows = original(analyzer, elements)
        rows[0]['owner'] = '<module>'
        return rows
    monkeypatch.setattr(matrix, 'jsx_component_references', wrong_owner)
    with pytest.raises(RuntimeError, match='mismatch'):
        matrix.check_file(path, ['jsx-owner'], TOOLCHAIN)


def test_compiler_scope_owner_covers_callbacks_wrappers_and_test_blocks(tmp_path, compiler_oracle):
    """BACK-1832: the owner check used to drop every use the oracle could not name, which left only the
    easy shapes. Each of these is a shape the owner rule had to be fixed for (BACK-1829, BACK-1832)."""
    path = tmp_path / 'Shapes.tsx'
    path.write_text(
        'function Key() { return null }\n'
        'const Plain = () => <Key/>;\n'                                                   # 2: variable arrow
        'const Memo = React.memo(() => <Key/>);\n'                                        # 3: wrapper, qualified
        'const Fwd = forwardRef((p, ref) => <Key/>);\n'                                   # 4: wrapper
        'const List = ({ xs }) => {\n'
        '  const keys = xs.map((x) => (\n'
        '    <Key/>\n'                                                                    # 7: callback computing a value
        '  ));\n'
        '  const pick = useCallback(() => { return <Key/>; }, []);\n'                     # 9: hook callback
        '  return xs.filter((x) => xs.some((y) => <Key/>));\n'                            # 10: nested callbacks
        '};\n'
        'class Panel { render() { return <Key/>; } }\n'                                   # 12: method
        'describe("w", () => {\n'
        '  it("renders", () => {\n'
        '    run(<Key/>);\n'                                                              # 15: innermost test block
        '  });\n'
        '});\n'
        'export default function () { return <Key/>; }\n'                                  # 18: unnamed default export
        'register(<Key/>);\n',                                                            # 19: module level
        encoding='utf-8')
    answer = matrix.check_file(path, ['jsx-owner'], TOOLCHAIN)['jsx-owner']
    assert answer['expected'] == answer['actual'] == 10
    owners = {r['line']: r['owner'] for r in matrix._compiler_answer(path, TOOLCHAIN, 'jsx')['references']}
    assert owners == {2: 'Plain', 3: 'Memo', 4: 'Fwd', 7: 'List', 9: 'List', 10: 'List',
                      12: 'render', 15: 'it(renders)', 18: '<anonymous>', 19: '<module>'}


def test_intrinsic_and_template_text_have_no_reveal_component_edges(tmp_path):
    path = tmp_path / 'Angular.tsx'
    path.write_text('const template = "<Button/>";\nfunction App(){return <div><my-widget/><Custom-Element/></div>;}\n', encoding='utf-8')
    assert matrix.analyze_file(str(path))['jsx_references'] == []
    path.write_text('function App(){return <Button/>;}\n', encoding='utf-8')
    assert matrix.analyze_file(str(path))['jsx_references'][0]['callee'] == 'Button'


def test_intrinsic_and_template_text_do_not_become_component_edges(tmp_path, compiler_oracle):
    path = tmp_path / 'Angular.tsx'
    path.write_text('const template = "<Button/>";\nfunction App(){return <div><my-widget/><Custom-Element/></div>;}\n', encoding='utf-8')
    assert matrix._compiler_answer(path, TOOLCHAIN, 'jsx')['references'] == []
    assert matrix.analyze_file(str(path))['jsx_references'] == []
    with pytest.raises(RuntimeError, match='zero population'):
        matrix.check_file(path, ['jsx'], TOOLCHAIN)


def test_server_contract_and_configuration_populations(tmp_path, monkeypatch):
    server = tmp_path / 'server.py'
    server.write_text('from abc import ABC\nclass Service(ABC):\n    pass\n', encoding='utf-8')
    assert matrix.check_file(server, ['python-abcs'], {})['python-abcs']['actual'] == 1
    config = tmp_path / 'package.json'
    config.write_text('{"name": "fixture", "dependencies": {"react": "x"}}', encoding='utf-8')
    assert matrix.check_file(config, ['json-config'], {})['json-config']['actual'] == 2
    fake = Mock(return_value=Mock(get_structure=Mock(return_value={'keys': [{'name': 'name'}]})))
    monkeypatch.setattr(matrix, 'get_analyzer', lambda _: fake)
    with pytest.raises(RuntimeError, match='mismatch'):
        matrix.check_file(config, ['json-config'], {})


def test_missing_source_and_empty_selected_checks_fail(tmp_path):
    with pytest.raises(RuntimeError, match='Missing selected source'):
        matrix.check_file(tmp_path / 'missing.tsx', ['jsx'], TOOLCHAIN)
    path = tmp_path / 'source.py'
    path.write_text('pass\n', encoding='utf-8')
    with pytest.raises(RuntimeError, match='No framework checks'):
        matrix.check_file(path, [], TOOLCHAIN)


def test_changed_source_pin_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(matrix.subprocess, 'run', lambda *a, **k: Mock(stdout='wrong-sha\n'))
    with pytest.raises(RuntimeError, match='pin mismatch'):
        matrix.source_root({'corpus': 'fixture'}, {'corpora': [{'id': 'fixture', 'language': 'tsx', 'sha': 'expected'}]}, tmp_path)


@pytest.mark.parametrize('suffix', ['vue', 'svelte'])
def test_unavailable_template_analyzers_remain_explicit(suffix, tmp_path):
    path = tmp_path / f'App.{suffix}'
    path.write_text('<Button/>', encoding='utf-8')
    assert matrix.get_analyzer(str(path)) is None


def test_angular_decorator_template_is_structure_without_jsx_relationships(tmp_path, compiler_oracle):
    path = tmp_path / 'angular.ts'
    path.write_text("import {Component} from '@angular/core';\n@Component({selector: 'app-root', template: '<Button/>'})\nexport class App { render() { return 'ok'; } }\n", encoding='utf-8')
    result = matrix.analyze_file(str(path))
    assert any(e['name'] == 'App' for e in result['elements'])
    assert result['jsx_references'] == []
    assert matrix._compiler_answer(path, TOOLCHAIN, 'jsx')['references'] == []


def test_known_route_convention_exclusions_and_supported_route_control(tmp_path):
    from reveal.adapters.surface import _scan_surface
    (tmp_path / 'routes.ts').write_text("import {route} from '@react-router/dev/routes';\nexport default [route('home', './home.tsx')];\n", encoding='utf-8')
    (tmp_path / 'urls.py').write_text("from django.urls import path, re_path\nurlpatterns = [path('home/', view), re_path(r'^item/$', view)]\n", encoding='utf-8')
    (tmp_path / 'api.py').write_text("from fastapi import FastAPI\napp = FastAPI()\n@app.get('/supported')\ndef supported():\n    return {}\n", encoding='utf-8')
    routes = _scan_surface(tmp_path)['surfaces']['http']
    assert [r['path'] for r in routes] == ['/supported']
