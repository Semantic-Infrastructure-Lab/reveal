"""imports://<file> spells every path from the file's own directory, never as a host path (BACK-2183).

A file target was its own display base: ``relative_to(<the file>)`` fails for every other path, so a
sibling's ``resolved`` (``from . import b``), a cycle member next to the file and the file's own
directory as a component fell back to the absolute host path, while a target above the file took the
``../`` branch: two spellings in one answer, and the analyst's filesystem layout in the JSON. Every
imports view of a file target now reads paths from the file's directory, and the file itself is still
named (BACK-1488), never ``.``.
"""
import json

from conftest import _run_reveal_in


def _project(tmp_path):
    """proj/pkg/a.py imports a sibling (b), a sibling package (sub) and a module above it (top);
    b imports a back, so a and b form a cycle."""
    proj = tmp_path / 'proj'
    (proj / 'pkg' / 'sub').mkdir(parents=True)
    (proj / 'pyproject.toml').write_text('[project]\nname = "proj"\n', encoding='utf-8')
    (proj / 'top.py').write_text('', encoding='utf-8')
    (proj / 'pkg' / '__init__.py').write_text('', encoding='utf-8')
    (proj / 'pkg' / 'sub' / '__init__.py').write_text('', encoding='utf-8')
    (proj / 'pkg' / 'sub' / 'c.py').write_text('x = 1\n', encoding='utf-8')
    (proj / 'pkg' / 'a.py').write_text('from . import b\nfrom .sub import c\nimport top\n', encoding='utf-8')
    (proj / 'pkg' / 'b.py').write_text('from . import a\n', encoding='utf-8')
    return proj


def _json(tmp_path, uri):
    result = _run_reveal_in(tmp_path, uri, '--format', 'json')
    assert result.returncode == 0, (uri, result.stderr)
    assert str(tmp_path) not in result.stdout and tmp_path.as_posix() not in result.stdout, (uri, result.stdout)
    return json.loads(result.stdout)


def test_a_file_target_spells_a_sibling_and_a_sibling_package_from_its_directory(tmp_path):
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/pkg/a.py')
    resolved = {s['line']: s['resolved'] for s in data['files']['a.py']}
    assert resolved == {1: 'b.py', 2: 'sub/__init__.py', 3: '../top.py'}


def test_a_file_target_cycle_names_its_sibling_member_relative(tmp_path):
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/pkg/a.py?circular')
    assert data['cycles'] == [['a.py', 'b.py']]
    assert data['cycle_paths'] == [['a.py', 'b.py', 'a.py']]


def test_a_file_target_component_is_its_own_directory(tmp_path):
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/pkg/a.py?components')
    assert [(c['component'], c['top_bridge']) for c in data['components']] == [('.', 'a.py')]


def test_the_file_itself_is_still_named_not_dot(tmp_path):
    """Negative control (BACK-1488): the requested file is named, in the files key, rows and ranking."""
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/pkg/a.py?rank=fan-in')
    assert [e['file'] for e in data['entries']] == ['a.py']
    assert _json(tmp_path, 'imports://proj/pkg/a.py?importers')['target'] == 'a.py'


def test_a_directory_target_keeps_its_spelling(tmp_path):
    """Negative control: the directory form of the same request already spelled every path relative."""
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/pkg')
    resolved = {(f, s['line']): s['resolved'] for f, stmts in data['files'].items() for s in stmts}
    assert resolved == {('a.py', 1): 'b.py', ('a.py', 2): 'sub/__init__.py', ('a.py', 3): '../top.py',
                        ('b.py', 1): 'a.py'}
