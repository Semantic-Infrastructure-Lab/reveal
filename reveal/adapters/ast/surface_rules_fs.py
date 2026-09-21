"""`fs` rule table (BACK-1333): calls and constructors that write to the filesystem.

Behavior carried over from the per-language scanners it replaces, so the corpus parity
sweep stays site-for-site. Reads are not surface. Every row keeps the old entry shape
(`type: fs_write`).

Not yet rule-driven: Python (open-mode and `.write` heuristics), TypeScript/JavaScript and
PHP (binding resolution, BACK-1335) and C++ (an `ofstream` declaration is not a call or
`new`, so it needs a declaration fact).
"""

from .surface_rules_model import Call, New, Rule

_C = 'fs'
_T = 'fs_write'


def _row(lang, match, name, example, counter_examples=()):
    return Rule(_C, lang, match, name, example=example, counter_examples=counter_examples,
                entry_type=_T)


RULES = (
    # ── Go ──────────────────────────────────────────────────────────────────
    _row('go', Call(receiver='os', name=('WriteFile', 'Create', 'OpenFile', 'Mkdir', 'MkdirAll')),
         '{receiver}.{name}',
         'package main\nimport "os"\nfunc f() { os.WriteFile("a", nil, 0644) }\n',
         ('package main\nimport "os"\nfunc f() { os.ReadFile("a"); os.Getenv("A") }\n',
          'package main\nfunc f(o x) { o.WriteFile("a") }\n')),
    _row('go', Call(receiver='ioutil', name='WriteFile'), '{receiver}.{name}',
         'package main\nimport "io/ioutil"\nfunc f() { ioutil.WriteFile("a", nil, 0644) }\n'),

    # ── Java ────────────────────────────────────────────────────────────────
    _row('java', Call(receiver='Files', name=('write', 'newBufferedWriter')), 'Files.{name}',
         'class A { void f() throws Exception { Files.write(p, b); } }\n',
         ('class A { void f() throws Exception { Files.readAllBytes(p); other.write(b); } }\n',)),
    _row('java', New(type=('FileWriter', 'FileOutputStream', 'PrintWriter')), 'new {type}()',
         'class A { void f() throws Exception { new FileWriter("a"); } }\n',
         ('class A { void f() { new StringWriter(); } }\n',)),

    # ── Kotlin ──────────────────────────────────────────────────────────────
    # PrintWriter is left out (unlike Java): `PrintWriter(System.out)` is a common non-file use.
    _row('kotlin', Call(receiver='', name=('FileWriter', 'FileOutputStream')), '{name}()',
         'fun f() {\n  FileWriter("a")\n}\n'),
    _row('kotlin', Call(receiver='Files',
                        name=('write', 'writeString', 'newBufferedWriter', 'newOutputStream')),
         'Files.{name}',
         'fun f() {\n  Files.write(p, b)\n}\n',
         ('fun f() {\n  Files.readAllBytes(p)\n  out.write(b)\n}\n',)),
    # `bare=False`: an unqualified `writeText(..)` is a local helper, not the kotlin.io extension.
    _row('kotlin', Call(name=('writeText', 'writeBytes', 'appendText', 'appendBytes'), bare=False),
         'File.{name}',
         'fun f(file: File) {\n  file.writeText("x")\n}\n',
         ('fun f() {\n  writeText("x")\n}\n',)),

    # ── C# ──────────────────────────────────────────────────────────────────
    _row('csharp', Call(receiver='File', name=('WriteAllText', 'WriteAllBytes', 'AppendAllText')),
         'File.{name}',
         'class A { void F() { File.WriteAllText("a", "b"); } }\n',
         ('class A { void F() { File.ReadAllText("a"); } }\n',)),
    _row('csharp', New(type=('StreamWriter', 'FileStream')), 'new {type}()',
         'class A { void F() { var s = new StreamWriter("a"); } }\n'),

    # ── Rust ────────────────────────────────────────────────────────────────
    _row('rust', Call(receiver_endswith='fs', name='write'), '{path}',
         'fn f() { std::fs::write("a", b"x").unwrap(); }\n',
         ('fn f() { std::fs::read("a").unwrap(); }\n',)),
    _row('rust', Call(receiver_endswith='File', name='create'), '{path}',
         'use std::fs::File;\nfn f() { File::create("a").unwrap(); }\n'),

    # ── Ruby (new: the scanner had no fs detector) ──────────────────────────
    _row('ruby', Call(receiver='File', name=('write', 'binwrite')), '{receiver}.{name}',
         'def f\n  File.write("a", "b")\nend\n',
         ('def f\n  File.read("a")\n  out.write("b")\nend\n',)),
    _row('ruby', Call(receiver='IO', name=('write', 'binwrite')), '{receiver}.{name}',
         'def f\n  IO.write("a", "b")\nend\n'),
    _row('ruby', Call(receiver='FileUtils', name=('mkdir_p', 'touch')), '{receiver}.{name}',
         'def f\n  FileUtils.mkdir_p("a")\nend\n'),

    # ── Swift (new: the scanner had no fs detector) ─────────────────────────
    # `data.write(to:)` needs argument-label matching (a bare `.write` also matches
    # FileHandle/streams), so only FileManager's create calls are covered here.
    _row('swift', Call(receiver='FileManager.default', name=('createFile', 'createDirectory')),
         'FileManager.{name}',
         'import Foundation\nfunc f() {\n  FileManager.default.createFile(atPath: p, contents: d)\n}\n',
         ('import Foundation\nfunc f() {\n  FileManager.default.fileExists(atPath: p)\n}\n',)),
)

TABLES = {_C: RULES}
