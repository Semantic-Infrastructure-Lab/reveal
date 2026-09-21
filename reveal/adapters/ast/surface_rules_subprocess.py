"""`subprocess` rule table (BACK-1331 pilot; behavior from BACK-1319).

One row per call shape that launches a process. Every row carries an example that must
match and, where a lookalike exists, counter-examples that must not: over-matching is the
failure mode of a name-based table (clap's `Command::new`, Ruby's `Process.pid`, ...).

Not yet rule-driven: TypeScript/JavaScript and PHP still detect subprocess in their own
scanners (they need binding-resolution hooks, BACK-1335).
"""

from .surface_rules_model import Call, ImportedFrom, New, Rule, Subshell

_C = 'subprocess'

_PYTHON_LOOKALIKES = (
    'import subprocess\n'
    'def run(x): return x\n'
    'class C:\n'
    '    def system(self): pass\n'
    'def f(c):\n'
    '    run(1)\n'
    '    c.system()\n'
    '    subprocess.list2cmdline(["a"])\n',
)

_KOTLIN_JAVA_RUNTIME = 'Runtime.getRuntime().exec'

RULES = (
    # ── Python: matched on the import-resolved dotted name ──────────────────
    Rule(_C, 'python',
         Call(resolved=True, receiver='subprocess',
              name=('run', 'Popen', 'call', 'check_call', 'check_output',
                    'getoutput', 'getstatusoutput')),
         '{path}',
         example='import subprocess\ndef f():\n    subprocess.run(["ls"])\n',
         counter_examples=_PYTHON_LOOKALIKES),
    Rule(_C, 'python',
         Call(resolved=True, receiver='os',
              name=('system', 'popen', 'exec*', 'spawn*', 'posix_spawn*')),
         '{path}',
         example='import os\ndef f():\n    os.system("ls")\n'),
    Rule(_C, 'python', Call(resolved=True, receiver='pty', name='spawn'), '{path}',
         example='import pty\ndef f():\n    pty.spawn("sh")\n'),
    Rule(_C, 'python',
         Call(resolved=True, receiver='asyncio',
              name=('create_subprocess_exec', 'create_subprocess_shell')),
         '{path}',
         example=('import asyncio\nasync def f():\n'
                  '    await asyncio.create_subprocess_exec("ls")\n')),

    # ── Go ──────────────────────────────────────────────────────────────────
    # `exec.Command` is a launch only when the file imports `os/exec`: another package
    # named `exec` (a k8s exec helper, a test double) is a lookalike. An aliased import
    # (`e "os/exec"`) satisfies the import but not `receiver='exec'`; it was never matched.
    Rule(_C, 'go', Call(receiver='exec', name=('Command', 'CommandContext')), '{path}',
         requires=ImportedFrom('os/exec'),
         example='package main\nimport "os/exec"\nfunc f() { exec.Command("ls").Run() }\n',
         counter_examples=(
             'package main\nfunc f(c cfg) { c.Command("x") }\n',
             'package main\nimport "k8s.io/utils/exec"\nfunc f() { exec.Command("x") }\n',
         )),

    # ── Java ────────────────────────────────────────────────────────────────
    Rule(_C, 'java', New(type='ProcessBuilder'), 'new {type}()',
         example='class A { void f() throws Exception { new ProcessBuilder("ls").start(); } }\n'),
    Rule(_C, 'java', Call(qualified=_KOTLIN_JAVA_RUNTIME), 'Runtime.exec',
         example='class A { void f() throws Exception { Runtime.getRuntime().exec("ls"); } }\n',
         counter_examples=(
             'class A { void f(Runtime r) { r.availableProcessors(); '
             'Runtime.getRuntime().totalMemory(); } }\n',)),

    # ── Kotlin ──────────────────────────────────────────────────────────────
    Rule(_C, 'kotlin', Call(receiver='', name='ProcessBuilder'), '{name}()',
         example='fun f() {\n  ProcessBuilder("ls").start()\n}\n'),
    Rule(_C, 'kotlin', Call(qualified=_KOTLIN_JAVA_RUNTIME), 'Runtime.exec',
         example='fun f() {\n  Runtime.getRuntime().exec("ls")\n}\n'),

    # ── Ruby ────────────────────────────────────────────────────────────────
    Rule(_C, 'ruby', Call(receiver='', name=('system', 'exec', 'spawn')), '{name}',
         example='def f\n  system("ls")\nend\n',
         counter_examples=(
             'def f\n  Process.pid\n  IO.read("x")\n  obj.system("x")\nend\n',
             # a call on a call result is not a bare `exec` (a Postgres connection, on the corpus)
             'def f\n  ActiveRecord::Base.connection.raw_connection.exec("SELECT 1")\nend\n',
         )),
    Rule(_C, 'ruby', Call(receiver='Kernel', name=('system', 'exec', 'spawn')), '{receiver}.{name}',
         example='def f\n  Kernel.system("ls")\nend\n'),
    Rule(_C, 'ruby', Call(receiver='Process', name=('spawn', 'exec')), '{receiver}.{name}',
         example='def f\n  Process.spawn("ls")\nend\n'),
    Rule(_C, 'ruby', Call(receiver='IO', name='popen'), '{receiver}.{name}',
         example='def f\n  IO.popen("ls")\nend\n'),
    Rule(_C, 'ruby', Call(receiver='Open3'), '{receiver}.{name}',   # every Open3 method launches
         example='def f\n  Open3.capture2("ls")\nend\n'),
    Rule(_C, 'ruby', Subshell(), '`...`',
         example='def f\n  `ls`\nend\n'),

    # ── Rust ────────────────────────────────────────────────────────────────
    # A bare `Command::new` is a launch only when the file imports it from a `process`
    # module: clap's `Command::new("app")` is a CLI builder.
    Rule(_C, 'rust', Call(receiver_endswith='process::Command', name='new'), 'Command::new',
         example='fn f() { std::process::Command::new("ls").output().unwrap(); }\n'),
    Rule(_C, 'rust', Call(receiver='Command', name='new'), 'Command::new',
         requires=ImportedFrom('process::Command'),
         example=('use std::process::{Command, Stdio};\n'
                  'fn f() { Command::new("ls").output().unwrap(); }\n'),
         counter_examples=(
             'use clap::Command;\nfn f() { let _ = Command::new("app"); }\n',
             # a commented-out import is not an import
             'fn f() { Command::new("a"); }\n// use std::process::Command;\n',
         )),

    # ── C# ──────────────────────────────────────────────────────────────────
    Rule(_C, 'csharp', Call(receiver='Process', name='Start'), 'Process.Start',
         example='using System.Diagnostics;\nclass A { void F() { Process.Start("ls"); } }\n'),
    Rule(_C, 'csharp', New(type=('Process', 'ProcessStartInfo')), 'new {type}()',
         example=('using System.Diagnostics;\n'
                  'class A { void F() { var p = new ProcessStartInfo("ls"); } }\n')),

    # ── C++ ─────────────────────────────────────────────────────────────────
    # Free functions only: a method (`o.system()`) or another namespace's (`foo::system()`)
    # is not the libc launch.
    Rule(_C, 'cpp',
         Call(receiver='', name=('system', 'popen', '_popen', 'posix_spawn', 'posix_spawnp',
                                 'execl', 'execlp', 'execle', 'execv', 'execvp', 'execve')),
         '{path}',
         example='#include <cstdlib>\nvoid f() { system("ls"); }\n',
         counter_examples=(
             'void f(Obj o) { o.system("x"); foo::system("x"); o.execvp("x"); }\n',)),
    Rule(_C, 'cpp', Call(receiver='std', name='system'), '{path}',
         example='#include <cstdlib>\nvoid f() { std::system("ls"); }\n'),

    # ── Swift ───────────────────────────────────────────────────────────────
    Rule(_C, 'swift', Call(receiver='', name=('Process', 'NSTask')), '{name}()',
         example='import Foundation\nfunc f() {\n  let p = Process()\n}\n'),
    Rule(_C, 'swift', Call(receiver='Process', name='run'), 'Process.run',
         example=('import Foundation\nfunc f() throws {\n'
                  '  try Process.run(url, arguments: [])\n}\n')),
)

TABLES = {_C: RULES}
