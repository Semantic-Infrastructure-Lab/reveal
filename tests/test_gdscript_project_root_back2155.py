"""GDScript ``res://`` and ``class_name`` resolve inside the nearest ``project.godot`` (BACK-2155).

Godot's ``res://`` is the directory holding the nearest ``project.godot``, and the global
``class_name`` registry is per project. A scan pinned at an aggregator root holding several
projects must not put one project's importer on another project's file.
"""
import pytest

from reveal.analyzers.imports import service

pytestmark = pytest.mark.component


def _write(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


def _edges(root):
    graph = service.analyze(service.path_scope(root)).analysis.graph
    return sorted((src.relative_to(root.resolve()).as_posix(), dst.relative_to(root.resolve()).as_posix())
                  for src, dsts in graph.dependencies.items() for dst in dsts)


def _two_projects(**extra):
    files = {}
    for proj in ('2d', '3d'):
        files[f'{proj}/project.godot'] = 'config_version=5\n'
        files[f'{proj}/test.gd'] = 'class_name Test\nextends Node\n'
        files[f'{proj}/base.gd'] = 'extends Node\n'
        files[f'{proj}/by_res.gd'] = 'extends "res://base.gd"\nvar t = preload("res://test.gd")\n'
        files[f'{proj}/by_class.gd'] = 'extends Test\n'
    files.update(extra)
    return files


def test_res_path_resolves_inside_each_project(tmp_path):
    _write(tmp_path, _two_projects())
    edges = _edges(tmp_path)
    for proj in ('2d', '3d'):
        assert (f'{proj}/by_res.gd', f'{proj}/base.gd') in edges
        assert (f'{proj}/by_res.gd', f'{proj}/test.gd') in edges
    assert [e for e in edges if e[0].startswith('2d/') and e[1].startswith('3d/')] == []
    assert [e for e in edges if e[0].startswith('3d/') and e[1].startswith('2d/')] == []


def test_res_path_prefers_project_over_stray_scan_root_file(tmp_path):
    _write(tmp_path, {
        'base.gd': 'extends Node\n',
        'p1/project.godot': 'config_version=5\n',
        'p1/base.gd': 'extends Node\n',
        'p1/main.gd': 'extends "res://base.gd"\n',
    })
    assert ('p1/main.gd', 'p1/base.gd') in _edges(tmp_path)
    assert ('p1/main.gd', 'base.gd') not in _edges(tmp_path)


def test_class_name_resolves_inside_each_project(tmp_path):
    _write(tmp_path, _two_projects())
    edges = _edges(tmp_path)
    assert ('2d/by_class.gd', '2d/test.gd') in edges
    assert ('3d/by_class.gd', '3d/test.gd') in edges


def test_class_name_declared_only_in_another_project_stays_unresolved(tmp_path):
    _write(tmp_path, {
        '2d/project.godot': 'config_version=5\n',
        '2d/main.gd': 'extends Test\n',
        '3d/project.godot': 'config_version=5\n',
        '3d/test.gd': 'class_name Test\nextends Node\n',
    })
    assert _edges(tmp_path) == []


def test_single_project_at_scan_root_is_unchanged(tmp_path):
    _write(tmp_path, {
        'project.godot': 'config_version=5\n',
        'base.gd': 'extends Node\n',
        'test.gd': 'class_name Test\nextends Node\n',
        'sub/main.gd': 'extends "res://base.gd"\nvar t = preload("res://test.gd")\n',
        'sub/by_class.gd': 'extends Test\n',
    })
    assert _edges(tmp_path) == [('sub/by_class.gd', 'test.gd'), ('sub/main.gd', 'base.gd'),
                                ('sub/main.gd', 'test.gd')]


def test_no_project_godot_falls_back_to_scan_root(tmp_path):
    _write(tmp_path, {
        'base.gd': 'extends Node\n',
        'test.gd': 'class_name Test\nextends Node\n',
        'sub/main.gd': 'extends "res://base.gd"\n',
        'sub/by_class.gd': 'extends Test\n',
    })
    assert _edges(tmp_path) == [('sub/by_class.gd', 'test.gd'), ('sub/main.gd', 'base.gd')]


def test_project_godot_marker_changes_nothing_for_other_languages(tmp_path):
    files = {'pkg/__init__.py': '', 'pkg/a.py': 'X = 1\n', 'pkg/b.py': 'from pkg import a\n'}
    plain = tmp_path / 'plain'
    marked = tmp_path / 'marked'
    _write(plain, files)
    _write(marked, dict(files, **{'project.godot': 'config_version=5\n', 'pkg/project.godot': ''}))
    assert _edges(plain)
    assert _edges(plain) == _edges(marked)
