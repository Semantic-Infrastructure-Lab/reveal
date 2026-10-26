"""imports with ``&scope=path`` spells a target outside the requested path relative, not as a host path (BACK-2157).

``&scope=path`` makes the requested path the scan root (what architecture://, overview:// and pack pass).
An import that resolves above it (on the TypeScript corpus, ``fixtureUtils.ts`` importing
``build/vite/style.css`` and ``extensions/theme-defaults/themes/*.json``: 9 rows) was listed under its host
path in ``?importers``, ``?rank=fan-in`` and the default view's ``resolved``. Same display rule as
BACK-2184's pinned root; this is its own fixture so the two scan-root sources are each proven.
"""
import json

from conftest import _run_reveal_in


def _project(tmp_path):
    """The corpus shape: a source tree beside the build and extension trees it imports from."""
    proj = tmp_path / 'proj'
    (proj / 'src' / 'test').mkdir(parents=True)
    (proj / 'build' / 'vite').mkdir(parents=True)
    (proj / 'extensions' / 'themes').mkdir(parents=True)
    (proj / 'package.json').write_text('{"name": "p"}\n', encoding='utf-8')
    (proj / 'build' / 'vite' / 'style.css').write_text('a {}\n', encoding='utf-8')
    (proj / 'extensions' / 'themes' / 'dark.json').write_text('{}\n', encoding='utf-8')
    (proj / 'src' / 'test' / 'fixtureUtils.ts').write_text(
        "import '../../build/vite/style.css';\nimport dark from '../../extensions/themes/dark.json';\n"
        "import { b } from '../b';\n", encoding='utf-8')
    (proj / 'src' / 'b.ts').write_text('export const b = 1;\n', encoding='utf-8')
    return proj


def _json(tmp_path, uri):
    result = _run_reveal_in(tmp_path, uri, '--format', 'json')
    assert result.returncode == 0, (uri, result.stderr)
    assert str(tmp_path) not in result.stdout and tmp_path.as_posix() not in result.stdout, (uri, result.stdout)
    return json.loads(result.stdout)


OUTSIDE = ['../build/vite/style.css', '../extensions/themes/dark.json']


def test_scope_path_importers_name_targets_outside_the_path_relative(tmp_path):
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/src?importers&scope=path')
    assert {e['file']: e['importers'] for e in data['entries']} == {
        OUTSIDE[0]: ['test/fixtureUtils.ts'], OUTSIDE[1]: ['test/fixtureUtils.ts'], 'b.ts': ['test/fixtureUtils.ts']}


def test_scope_path_fan_in_names_targets_outside_the_path_relative(tmp_path):
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/src?rank=fan-in&scope=path')
    assert sorted(e['file'] for e in data['entries']) == sorted(OUTSIDE + ['b.ts', 'test/fixtureUtils.ts'])


def test_scope_path_default_view_resolves_targets_outside_the_path_relative(tmp_path):
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/src?scope=path')
    resolved = {s['line']: s['resolved'] for s in data['files']['test/fixtureUtils.ts']}
    assert resolved == {1: OUTSIDE[0], 2: OUTSIDE[1], 3: 'b.ts'}


def test_scope_root_keeps_its_rows(tmp_path):
    """Negative control: the default scope=root answer has no row above the requested path (the rows are
    the requested path's files) and spells the in-path target as before."""
    _project(tmp_path)
    data = _json(tmp_path, 'imports://proj/src?importers')
    assert {e['file']: e['importers'] for e in data['entries']} == {'b.ts': ['test/fixtureUtils.ts']}
