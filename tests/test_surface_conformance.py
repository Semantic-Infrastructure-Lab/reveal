"""BACK-1319: cross-language surface:// conformance table.

One tiny file per language exercising one call per I/O category. The failure
mode this pins: a category that a scanner never implements reports 0, and on a
scanned language an empty result reads as a confirmed "nothing here". Each row
asserts the category is non-empty, so a category can not silently be zero again.
"""

import importlib

import pytest

# (language, extension, category, code, expected substrings of entry names)
ROWS = [
    ('python', 'py', 'subprocess',
     'import subprocess, os\n'
     'def f():\n'
     '    subprocess.run(["ls"])\n'
     '    os.system("ls")\n',
     ['subprocess.run', 'os.system']),
    ('go', 'go', 'subprocess',
     'package main\n'
     'import "os/exec"\n'
     'func f() { exec.Command("ls").Run() }\n',
     ['exec.Command']),
    ('java', 'java', 'subprocess',
     'class A { void f() throws Exception {\n'
     '  new ProcessBuilder("ls").start();\n'
     '  Runtime.getRuntime().exec("ls");\n'
     '} }\n',
     ['ProcessBuilder', 'Runtime.exec']),
    ('kotlin', 'kt', 'subprocess',
     'fun f() {\n'
     '  ProcessBuilder("ls").start()\n'
     '  Runtime.getRuntime().exec("ls")\n'
     '}\n',
     ['ProcessBuilder', 'Runtime.exec']),
    ('ruby', 'rb', 'subprocess',
     'def f\n'
     '  system("ls")\n'
     '  `ls`\n'
     '  Open3.capture2("ls")\n'
     'end\n',
     ['system', '`...`', 'Open3.capture2']),
    ('rust', 'rs', 'subprocess',
     'use std::process::Command;\n'
     'fn f() { Command::new("ls").output().unwrap(); }\n',
     ['Command::new']),
    ('csharp', 'cs', 'subprocess',
     'using System.Diagnostics;\n'
     'class A { void F() {\n'
     '  Process.Start("ls");\n'
     '  var p = new ProcessStartInfo("ls");\n'
     '} }\n',
     ['Process.Start', 'ProcessStartInfo']),
    ('swift', 'swift', 'subprocess',
     'import Foundation\n'
     'func f() {\n'
     '  let p = Process()\n'
     '  try? p.run()\n'
     '}\n',
     ['Process']),
]

MODULES = {
    'python': ('reveal.adapters.ast.nav_surface', 'scan_file_surface'),
    'go': ('reveal.adapters.ast.nav_surface_go', 'scan_file_surface_go'),
    'java': ('reveal.adapters.ast.nav_surface_java', 'scan_file_surface_java'),
    'kotlin': ('reveal.adapters.ast.nav_surface_kotlin', 'scan_file_surface_kotlin'),
    'ruby': ('reveal.adapters.ast.nav_surface_ruby', 'scan_file_surface_ruby'),
    'rust': ('reveal.adapters.ast.nav_surface_rust', 'scan_file_surface_rust'),
    'csharp': ('reveal.adapters.ast.nav_surface_csharp', 'scan_file_surface_csharp'),
    'swift': ('reveal.adapters.ast.nav_surface_swift', 'scan_file_surface_swift'),
}


def _scan(lang, ext, code, tmp_path):
    mod, fn = MODULES[lang]
    scanner = getattr(importlib.import_module(mod), fn)
    path = tmp_path / f'sample.{ext}'
    path.write_text(code, encoding='utf-8')
    return scanner(str(path))


@pytest.mark.parametrize('lang,ext,category,code,expected', ROWS,
                         ids=[f'{r[0]}-{r[2]}' for r in ROWS])
def test_category_detected(lang, ext, category, code, expected, tmp_path):
    entries = _scan(lang, ext, code, tmp_path)[category]
    names = sorted(e['name'] for e in entries)
    assert names, f'{lang}: {category} is empty'
    for want in expected:
        assert any(want in n for n in names), f'{lang}: {want!r} not in {names}'


# Lookalikes that must NOT register: over-matching is the failure mode of a
# name-based table.
NEGATIVE_ROWS = [
    ('python', 'py',
     'import subprocess\n'
     'def run(x): return x\n'
     'class C:\n'
     '    def system(self): pass\n'
     'def f(c):\n'
     '    run(1)\n'
     '    c.system()\n'
     '    subprocess.list2cmdline(["a"])\n'),
    ('rust', 'rs',
     'use clap::Command;\n'
     'fn f() { let _ = Command::new("app"); }\n'),
    ('ruby', 'rb',
     'def f\n'
     '  Process.pid\n'
     '  IO.read("x")\n'
     '  obj.system("x")\n'
     'end\n'),
    ('go', 'go',
     'package main\n'
     'func f(c cfg) { c.Command("x") }\n'),
    ('java', 'java',
     'class A { void f(Runtime r) { r.availableProcessors(); Runtime.getRuntime().totalMemory(); } }\n'),
]


@pytest.mark.parametrize('lang,ext,code', NEGATIVE_ROWS, ids=[r[0] for r in NEGATIVE_ROWS])
def test_lookalikes_not_subprocess(lang, ext, code, tmp_path):
    assert _scan(lang, ext, code, tmp_path)['subprocess'] == []


def test_python_import_alias_and_from_import_resolve(tmp_path):
    code = ('import subprocess as sp\n'
            'from os import system as sh\n'
            'def f():\n'
            '    sp.check_output(["ls"])\n'
            '    sh("ls")\n')
    names = sorted(e['name'] for e in _scan('python', 'py', code, tmp_path)['subprocess'])
    assert names == ['os.system', 'subprocess.check_output']


def test_rust_bare_command_with_process_import_grouped(tmp_path):
    code = 'use std::process::{Command, Stdio};\nfn f() { Command::new("ls"); }\n'
    assert len(_scan('rust', 'rs', code, tmp_path)['subprocess']) == 1
