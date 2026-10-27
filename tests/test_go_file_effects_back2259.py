"""Go `os`/`ioutil`/`filepath` file calls missing from the sideeffects `file` kind (BACK-2259).

`os.WriteFile` (the Go 1.16 replacement for `ioutil.WriteFile`, which was listed) was not
classified, while `os.ReadFile` and `os.Create` were. On the client-go recall corpus six of the
eight oracle `file` lines reveal missed were `os.WriteFile`; the other two were `os.Symlink` and
`os.Chmod`. The siblings below are the rest of `os`'s file-tree calls: the Go 1.16 `ioutil`
replacements (`os.CreateTemp`, `os.MkdirTemp`, `os.ReadDir`), `os.RemoveAll` beside the listed
`os.Remove`, and the permission/link/truncate calls the Node `fs` verb list already counts.

Metadata lookups (`os.Stat`, `os.Lstat`, `os.Readlink`), `os.DirFS` (builds an `fs.FS`, does
no I/O) and `ioutil.ReadAll` (reads any `io.Reader`) stay unclassified; the negative controls pin
that, and that a non-`os` receiver with the same verb is not matched.
"""

import json
import textwrap

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.ast.nav_effects import classify_call

NEWLY_FILE = (
    'os.WriteFile', 'os.RemoveAll', 'os.CreateTemp', 'os.MkdirTemp', 'os.ReadDir',
    'os.Truncate', 'os.Chmod', 'os.Chown', 'os.Lchown', 'os.Chtimes', 'os.Symlink', 'os.Link',
    'os.CopyFS', 'ioutil.ReadDir', 'ioutil.TempFile', 'ioutil.TempDir',
    'filepath.Walk', 'filepath.WalkDir',
)

ALREADY_FILE = (
    'os.ReadFile', 'os.Create', 'os.Open', 'os.OpenFile', 'os.Remove', 'os.Rename',
    'os.Mkdir', 'os.MkdirAll', 'ioutil.ReadFile', 'ioutil.WriteFile',
)

NOT_FILE = (
    'os.Stat', 'os.Lstat', 'os.Readlink', 'os.DirFS', 'os.Getwd', 'os.Chdir',
    'ioutil.ReadAll', 'cfg.WriteFile', 'store.Chmod', 'w.Walk',
)


@pytest.mark.parametrize('callee', NEWLY_FILE)
def test_go_file_call_is_classified_file(callee):
    assert classify_call(callee, 'go') == 'file'


@pytest.mark.parametrize('callee', ALREADY_FILE)
def test_go_file_calls_already_classified_stay_file(callee):
    assert classify_call(callee, 'go') == 'file'


@pytest.mark.parametrize('callee', NOT_FILE)
def test_go_non_file_calls_stay_unclassified(callee):
    assert classify_call(callee, 'go') is None


def test_go_sideeffects_reports_os_writefile(tmp_path):
    # The task's repro, end to end: the WriteFile line was the only one missing.
    src = tmp_path / 'a.go'
    src.write_text(textwrap.dedent('''\
        package main

        import "os"

        func writer() {
        \tos.WriteFile("x", []byte("y"), 0644)
        \tos.ReadFile("x")
        \tos.Create("z")
        \tos.Stat("x")
        }
    '''), encoding='utf-8')
    result = _run_reveal_direct(str(src), 'writer', '--sideeffects', '--format', 'json')
    assert result.returncode == 0, result.stderr
    findings = json.loads(result.stdout)['findings']
    assert [(f['line'], f['kind'], f['callee']) for f in findings] == [
        (6, 'file', 'os.WriteFile'),
        (7, 'file', 'os.ReadFile'),
        (8, 'file', 'os.Create'),
    ]
