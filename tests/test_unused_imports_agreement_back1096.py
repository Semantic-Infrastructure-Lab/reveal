"""imports://?unused and I001 name the same unused imports (BACK-1096, audit item 7).

Two implementations answer "which imports of this file are never used"; the
audit restated their 2026-08 disagreement without re-running it.  They must
cite the same lines, and a language neither checks must say so rather than
agree on an empty list (BACK-1398).
"""
import pytest

import reveal.analyzers  # noqa: F401  (registers every analyzer)
from reveal.adapters.imports import ImportsAdapter
from reveal.cli.file_checker import check_and_collect_file
from reveal.rules import RuleRegistry

pytestmark = [pytest.mark.component]

# filename -> (source, lines holding an import nothing uses)
CHECKED = {
    'a.py': ('import os\nimport sys\nfrom json import loads\nimport re as rx\n\n'
             'print(sys.argv, loads, rx.compile("a"))\n', {1}),
    'b.js': ("import { a, b as c } from './m';\nimport d from './d';\nimport './side.css';\n\n"
             'console.log(a, c);\n', {2}),
    'c.go': ('package d\n\nimport (\n\t"fmt"\n\t"os"\n\tyaml "gopkg.in/yaml.v3"\n)\n\n'
             'func F() { fmt.Println(yaml.Marshal) }\n', {5}),
}
UNCHECKED = {
    'W.java': 'import java.util.List;\nimport java.util.Map;\n\nclass W { List<String> x; }\n',
}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')


def _imports_unused(path):
    result = ImportsAdapter(resource=str(path), query='unused').get_structure()
    return {u['line'] for u in result['unused']}, result['metadata']


def _i001_unused(path):
    RuleRegistry.discover()
    _, detections, status = check_and_collect_file(path, path.parent, ['I001'], None)
    assert status['status'] in ('ok', 'warning'), status
    return {d.line for d in detections}


@pytest.mark.parametrize('name', sorted(CHECKED))
def test_both_name_the_same_unused_import_lines(tmp_path, name):
    source, expected = CHECKED[name]
    path = tmp_path / name
    path.write_text(source, encoding='utf-8')
    from_imports, _ = _imports_unused(path)
    assert expected, 'positive control: the fixture has an unused import'
    assert from_imports == expected
    assert _i001_unused(path) == expected


@pytest.mark.parametrize('name', sorted(UNCHECKED))
def test_a_language_neither_checks_is_disclosed_not_agreed_empty(tmp_path, name):
    path = tmp_path / name
    path.write_text(UNCHECKED[name], encoding='utf-8')
    from_imports, meta = _imports_unused(path)
    assert from_imports == set() and _i001_unused(path) == set()
    assert meta['unused_not_checked_extensions'] == {path.suffix: 1}
