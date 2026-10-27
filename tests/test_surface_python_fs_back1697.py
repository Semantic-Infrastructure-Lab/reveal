"""Python surface `fs`: shutil copies and the target of `Path.write_text`/`write_bytes` (BACK-1697).

`open(path, 'w')` reports the path it writes as `target`. Before this fix `shutil.copy(src, dst)`
was not reported at all, and `Path('out.txt').write_text('x')` reported the text written ('x') as
the target; `write_bytes` did the same with the bytes. Now the shutil calls that create or replace
a file or tree report their destination, and the pathlib writers report the path they write to.

Controls that must not change: `open(..., 'w')`, a handle's `.write(data)` (whose target is the
handle since BACK-2268, never the data), shutil calls that do not write a file (`rmtree`, `which`, `copymode`), a
dict's `.copy()`, and a project's own `copy()` with no shutil import.
"""

import json
import textwrap

from conftest import _run_reveal_direct
from reveal.adapters.ast.nav_surface import scan_file_surface


def _fs(tmp_path, src):
    path = tmp_path / 'mod.py'
    path.write_text(textwrap.dedent(src), encoding='utf-8')
    return sorted((e['line'], e['name'], e.get('target')) for e in scan_file_surface(str(path))['fs'])


def test_shutil_copy_family_reports_destination(tmp_path):
    rows = _fs(tmp_path, '''\
        import shutil

        def f(src, out_dir):
            shutil.copy("src.txt", "dst.txt")
            shutil.copy2(src, out_dir)
            shutil.copyfile("a.txt", dst="b.txt")
            shutil.copytree("tree", "tree2")
            shutil.move(src, "moved.txt")
    ''')
    assert rows == [
        (4, 'shutil.copy', 'dst.txt'),
        (5, 'shutil.copy2', 'out_dir'),
        (6, 'shutil.copyfile', 'b.txt'),
        (7, 'shutil.copytree', 'tree2'),
        (8, 'shutil.move', 'moved.txt'),
    ]


def test_shutil_reached_through_an_import_alias(tmp_path):
    rows = _fs(tmp_path, '''\
        import shutil as sh
        from shutil import copyfile as cf

        def f():
            sh.copy("a", "b")
            cf("c", "d")
    ''')
    assert rows == [(5, 'sh.copy', 'b'), (6, 'cf', 'd')]


def test_pathlib_writers_report_the_path_not_the_payload(tmp_path):
    rows = _fs(tmp_path, '''\
        from pathlib import Path

        class Store:
            def save(self, data, base):
                Path("out.txt").write_text("x")
                Path("out.bin").write_bytes(b"x")
                self._path.write_text(data)
                (base / "a.json").write_text(data, encoding="utf-8")
    ''')
    assert rows == [
        (5, "Path('out.txt').write_text", 'out.txt'),
        (6, "Path('out.bin').write_bytes", 'out.bin'),
        (7, 'self._path.write_text', 'self._path'),
        (8, "(base / 'a.json').write_text", "base / 'a.json'"),
    ]


def test_controls_unchanged(tmp_path):
    rows = _fs(tmp_path, '''\
        import shutil

        def copy(a, b):
            return a

        def f(d, fh, data):
            open("o.txt", "w")
            fh.write(data)
            shutil.rmtree("gone")
            shutil.which("git")
            shutil.copymode("a", "b")
            d.copy()
            copy("x", "y")
            open("r.txt").read()
    ''')
    assert rows == [(7, 'open', 'o.txt'), (8, 'fh.write', 'fh')]


def test_surface_uri_reports_shutil_copy_and_write_text_target(tmp_path):
    (tmp_path / 'mod.py').write_text(textwrap.dedent('''\
        import shutil
        from pathlib import Path

        def f():
            shutil.copy("src.txt", "dst.txt")
            Path("out.txt").write_text("x")
    '''), encoding='utf-8')
    result = _run_reveal_direct(f'surface://{tmp_path.as_posix()}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    fs = json.loads(result.stdout)['surfaces']['fs']
    assert [(e['line'], e['name'], e['target']) for e in fs] == [
        (5, 'shutil.copy', 'dst.txt'),
        (6, "Path('out.txt').write_text", 'out.txt'),
    ]
