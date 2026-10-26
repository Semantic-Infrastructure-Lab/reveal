"""imports with a pinned ``&root=`` spells a target outside the root from the requested directory (BACK-2184).

``import '../assets/x.css'`` in ``src/a.ts`` resolves to a file above ``&root=proj/src``. The display rule
spelled a path from the requested directory only when it lay under the scan root, so this target fell
through to its host path: ``?importers`` listed it as ``file: /home/<user>/.../assets/x.css``, and so did
``?rank=fan-in`` and the default view's ``resolved``. Whether such an edge should exist under a pinned
root is a separate question (the task's design note); the host path was a leak either way. It is now
``../assets/x.css``, the path from the requested directory, as a file outside the requested path under
the default ``&scope=root`` already was.
"""
import json

from conftest import _run_reveal_in


def _project(tmp_path):
    proj = tmp_path / 'proj'
    (proj / 'src').mkdir(parents=True)
    (proj / 'assets').mkdir()
    (proj / 'package.json').write_text('{"name": "p"}\n', encoding='utf-8')
    (proj / 'assets' / 'x.css').write_text('a {}\n', encoding='utf-8')
    (proj / 'src' / 'a.ts').write_text("import '../assets/x.css';\nimport { b } from './b';\n", encoding='utf-8')
    (proj / 'src' / 'b.ts').write_text('export const b = 1;\n', encoding='utf-8')
    return proj


def _json(tmp_path, uri):
    result = _run_reveal_in(tmp_path, uri, '--format', 'json')
    assert result.returncode == 0, (uri, result.stderr)
    assert str(tmp_path) not in result.stdout and tmp_path.as_posix() not in result.stdout, (uri, result.stdout)
    return json.loads(result.stdout)


def test_importers_name_a_target_above_a_pinned_root_relative(tmp_path):
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/src?importers&root=proj/src')
    assert {e['file']: e['importers'] for e in data['entries']} == {'../assets/x.css': ['a.ts'], 'b.ts': ['a.ts']}


def test_the_fan_in_ranking_names_a_target_above_a_pinned_root_relative(tmp_path):
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/src?rank=fan-in&root=proj/src')
    assert sorted(e['file'] for e in data['entries']) == ['../assets/x.css', 'a.ts', 'b.ts']


def test_the_default_view_resolves_a_target_above_a_pinned_root_relative(tmp_path):
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/src?root=proj/src')
    assert {s['line']: s['resolved'] for s in data['files']['a.ts']} == {1: '../assets/x.css', 2: 'b.ts'}


def test_the_project_root_answer_keeps_its_spelling(tmp_path):
    """Negative control: under the default scope the same target is under the scan root and was already
    spelled from the requested directory; the in-root target keeps its name."""
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/src')
    assert {s['line']: s['resolved'] for s in data['files']['a.ts']} == {1: '../assets/x.css', 2: 'b.ts'}
    importers = _json(tmp_path, 'imports://proj/src?importers')
    assert {e['file']: e['importers'] for e in importers['entries']} == {'b.ts': ['a.ts']}
