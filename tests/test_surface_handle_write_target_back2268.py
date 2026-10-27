"""Python surface `fs`: a file handle's `.write(data)` reports what it writes to (BACK-2268).

Before this fix `f.write(data)` reported its first argument, the payload, as `target`
('content', "json.dumps(record) + '\\n'"), so the row named the data and never the file. Now:

- a handle bound in the same function by `with open(PATH...) as f`, `f = open(PATH...)`,
  `with p.open('w') as f` (reported as `p`, like `p.write_text`) or
  `with tempfile.NamedTemporaryFile(...) as f` reports that path, printed as the `open()` row
  for the handle prints it (a temporary file, which has no path argument, reports the call that
  made it);
- a handle that cannot be traced (a parameter, an attribute such as `self.fh`, a name bound
  more than once, a handle returned from a call) reports the handle expression ('f',
  'self.fh') instead of the payload.

Controls that must not change: the `open()` row itself, `Path.write_text`/`write_bytes`
(BACK-1697), `print(..., file=f)` (not an fs row), a stream wrapper's delegating `.write`
(BACK-1338), and other languages' scanners.
"""

import json
import textwrap

from conftest import _run_reveal_direct
from reveal.adapters.ast.nav_surface import scan_file_surface


def _fs(tmp_path, src):
    path = tmp_path / 'mod.py'
    path.write_text(textwrap.dedent(src), encoding='utf-8')
    return sorted((e['line'], e['name'], e.get('target')) for e in scan_file_surface(str(path))['fs'])


def test_with_open_handle_reports_the_open_path(tmp_path):
    rows = _fs(tmp_path, '''\
        import json

        def log(record, path):
            with open(path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record) + '\\n')
            with open("out.txt", "w") as g:
                g.writelines(["a", "b"])
    ''')
    assert rows == [
        (4, 'open', 'path'),
        (5, 'f.write', 'path'),
        (6, 'open', 'out.txt'),
        (7, 'g.writelines', 'out.txt'),
    ]


def test_assigned_open_handle_reports_the_open_path(tmp_path):
    rows = _fs(tmp_path, '''\
        def save(data):
            fh = open("data.bin", mode="wb")
            fh.write(data)
            fh.close()
    ''')
    assert rows == [(2, 'open', 'data.bin'), (3, 'fh.write', 'data.bin')]


def test_named_temporary_file_reports_the_call_that_made_it(tmp_path):
    rows = _fs(tmp_path, '''\
        import tempfile
        from tempfile import NamedTemporaryFile as NTF

        def stage(content):
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(content)
            with NTF('w') as g:
                g.write(content)
    ''')
    assert rows == [
        (6, 'f.write', 'tempfile.NamedTemporaryFile(...)'),
        (8, 'g.write', 'NTF(...)'),
    ]


def test_pathlib_open_reports_its_receiver_like_write_text(tmp_path):
    # Only a literal writing mode marks a pathlib open: sftp/zip/project `.open(path, mode)`
    # methods take the path first, and a bare `.open()` reads.
    rows = _fs(tmp_path, '''\
        from pathlib import Path

        def f(path, data, conftest):
            with path.open('w', encoding='utf-8') as a:
                a.write(data)
            with Path("p.txt").open(mode="ab") as b:
                b.write(data)
            with self.sftp.open(path, "wb") as c:
                c.write(data)
            with conftest.open() as d:
                d.write(data)
    ''')
    assert rows == [
        (5, 'a.write', 'path'),
        (7, 'b.write', 'p.txt'),
        (9, 'c.write', 'c'),
        (11, 'd.write', 'd'),
    ]


def test_module_level_and_async_with(tmp_path):
    rows = _fs(tmp_path, '''\
        with open("module.log", "a") as log:
            log.write("start")

        async def run(data):
            async with open("async.txt", "w") as af:
                af.write(data)
    ''')
    assert rows == [
        (1, 'open', 'module.log'),
        (2, 'log.write', 'module.log'),
        (5, 'open', 'async.txt'),
        (6, 'af.write', 'async.txt'),
    ]


def test_several_handles_and_nested_with_items(tmp_path):
    rows = _fs(tmp_path, '''\
        def split(rows):
            with open("a.txt", "w") as f, open("b.txt", "w") as g:
                f.write(rows[0])
                g.write(rows[1])
            with open("c.txt", "w") as f:
                f.write(rows[2])
                with open("d.txt", "w") as f:
                    f.write(rows[3])
    ''')
    # Two with-blocks binding `f` one after the other each trace to their own path. Line 6 sits
    # in a body that binds `f` again (line 7): the trace is not flow-sensitive (a loop could run
    # the rebinding first), so it reports the name rather than risk the wrong path.
    assert rows == [
        (2, 'open', 'a.txt'),
        (2, 'open', 'b.txt'),
        (3, 'f.write', 'a.txt'),
        (4, 'g.write', 'b.txt'),
        (5, 'open', 'c.txt'),
        (6, 'f.write', 'f'),
        (7, 'open', 'd.txt'),
        (8, 'f.write', 'd.txt'),
    ]


def test_handle_rebound_inside_the_with_body_falls_back_to_the_name(tmp_path):
    rows = _fs(tmp_path, '''\
        def f(other):
            with open("a.txt", "w") as f:
                f.write("1")
                f = other
                f.write("2")
            with open("b.txt", "w") as g:
                with open("c.txt", "w") as g:
                    pass
                g.write("3")
    ''')
    assert rows == [
        (2, 'open', 'a.txt'),
        (3, 'f.write', 'f'),
        (5, 'f.write', 'f'),
        (6, 'open', 'b.txt'),
        (7, 'open', 'c.txt'),
        (9, 'g.write', 'g'),
    ]


def test_assigned_handle_bound_twice_falls_back_to_the_name(tmp_path):
    rows = _fs(tmp_path, '''\
        def f(flag):
            if flag:
                out = open("a.txt", "w")
            else:
                out = open("b.txt", "w")
            out.write("x")
    ''')
    assert rows == [(3, 'open', 'a.txt'), (5, 'open', 'b.txt'), (6, 'out.write', 'out')]


def test_untraceable_handles_report_the_handle_expression(tmp_path):
    rows = _fs(tmp_path, '''\
        import os

        class Sink:
            def emit(self, data, fh):
                self.fh.write(data)
                fh.write(data)
                os.fdopen(3, "w").write(data)
                handle = make_handle()
                handle.write(data)
                for out in self.outs:
                    out.writelines(data)
    ''')
    assert rows == [
        (5, 'self.fh.write', 'self.fh'),
        (6, 'fh.write', 'fh'),
        (7, "os.fdopen(3, 'w').write", "os.fdopen(3, 'w')"),
        (9, 'handle.write', 'handle'),
        (11, 'out.writelines', 'out'),
    ]


def test_a_parameter_shadowing_an_outer_handle_is_not_traced(tmp_path):
    rows = _fs(tmp_path, '''\
        with open("outer.txt", "w") as f:
            def inner(f):
                f.write("x")
            f.write("y")
    ''')
    assert rows == [(1, 'open', 'outer.txt'), (3, 'f.write', 'f'), (4, 'f.write', 'outer.txt')]


def test_a_handle_from_another_function_is_not_traced(tmp_path):
    rows = _fs(tmp_path, '''\
        def opener():
            f = open("mine.txt", "w")
            return f

        def user(f):
            f.write("x")
    ''')
    assert rows == [(2, 'open', 'mine.txt'), (6, 'f.write', 'f')]


def test_controls_unchanged(tmp_path):
    rows = _fs(tmp_path, '''\
        from pathlib import Path

        class Tee:
            def write(self, data):
                self.original.write(data)

        def f(data):
            with open("p.txt", "w") as f:
                print(data, file=f)
            Path("x.txt").write_text(data)
            open("y.txt", "w").write(data)
    ''')
    assert rows == [
        (8, 'open', 'p.txt'),
        (10, "Path('x.txt').write_text", 'x.txt'),
        (11, 'open', 'y.txt'),
    ]


def test_long_traced_path_is_truncated_like_the_open_row(tmp_path):
    rows = _fs(tmp_path, '''\
        def save(data):
            with open(build_a_very_long_path(alpha_argument, beta_argument, gamma_argument), "w") as f:
                f.write(data)
    ''')
    assert rows[0][2] == rows[1][2]
    assert len(rows[1][2]) == 60 and rows[1][2].endswith('…')


def test_surface_uri_reports_the_handle_path(tmp_path):
    (tmp_path / 'mod.py').write_text(textwrap.dedent('''\
        def save(path, text):
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
    '''), encoding='utf-8')
    result = _run_reveal_direct(f'surface://{tmp_path.as_posix()}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    fs = json.loads(result.stdout)['surfaces']['fs']
    assert [(e['line'], e['name'], e['target']) for e in fs] == [(2, 'open', 'path'), (3, 'f.write', 'path')]
