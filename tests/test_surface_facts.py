"""BACK-1330: neutral fact extraction for surface:// (Call / Import / New / Subshell).

Two kinds of test:
  * shape tests: one small sample per language, asserting the exact facts emitted, so
    every language yields the same four fact shapes;
  * the rule layer's coverage check (every reported site has a fact on its line) lives in
    tests/test_surface_rules.py, generated from the rule tables.
"""

import pytest

from reveal.adapters.ast.surface_facts import (
    LANGUAGES, Call, Import, New, Subshell, extract_facts, extract_file_facts,
)

def _calls(facts):
    return [(f.path, f.args) for f in facts if isinstance(f, Call)]


def test_every_surface_language_has_an_extractor():
    assert set(LANGUAGES) >= {'python', 'go', 'rust', 'java', 'kotlin', 'csharp', 'cpp',
                              'php', 'ruby', 'swift', 'typescript'}


SHAPES = [
    ('python', 'import os, subprocess as sp\nfrom a.b import c as d\nsp.run("ls", x)\n',
     [Import('os', (), '', 1), Import('subprocess', (), 'sp', 1), Import('a.b', ('c',), 'd', 2),
      Call('sp', 'run', ('ls', None), 3, '.')]),
    ('go', 'package main\nimport (\n"os/exec"\nstr "strings"\n)\nfunc f(){ exec.Command("ls", "-l") }\n',
     [Import('os/exec', (), '', 3), Import('strings', (), 'str', 4),
      Call('exec', 'Command', ('ls', '-l'), 6, '.')]),
    ('rust', 'use std::process::Command;\nuse a::{b, c as d};\nfn f(){ Command::new("ls"); }\n',
     [Import('std::process::Command', (), '', 1), Import('a::b', (), '', 2),
      Import('a::c', (), 'd', 2), Call('Command', 'new', ('ls',), 3, '::')]),
    ('java', 'import java.io.File;\nclass A { void f(){ new ProcessBuilder("ls"); } }\n',
     [Import('java.io.File', (), '', 1), New('ProcessBuilder', ('ls',), 2)]),
    ('kotlin', 'import java.io.File as F\nfun f(){ ProcessBuilder("ls") }\n',
     [Import('java.io.File', (), 'F', 1), Call('', 'ProcessBuilder', ('ls',), 2, '.')]),
    ('csharp', 'using System.Diagnostics;\nclass A { void f(){ Process.Start("ls"); new Foo("x"); } }\n',
     [Import('System.Diagnostics', (), '', 1), Call('Process', 'Start', ('ls',), 2, '.'),
      New('Foo', ('x',), 2)]),
    ('cpp', '#include <cstdlib>\nvoid f(){ system("ls"); a::b("x"); }\n',
     [Import('cstdlib', (), '', 1), Call('', 'system', ('ls',), 2, '.'),
      Call('a', 'b', ('x',), 2, '::')]),
    ('php', '<?php\nuse Foo\\Bar as B;\nfunction f(){ exec("ls"); $a->b("x"); A::c("y"); `ls`; }\n',
     [Import('Foo\\Bar', (), 'B', 2), Call('', 'exec', ('ls',), 3, '.'),
      Call('$a', 'b', ('x',), 3, '->'), Call('A', 'c', ('y',), 3, '::'), Subshell(3)]),
    ('ruby', 'def f; system("ls"); Open3.capture2("ls"); %x(ls); end\n',
     [Call('', 'system', ('ls',), 1, '.'), Call('Open3', 'capture2', ('ls',), 1, '.'), Subshell(1)]),
    ('swift', 'import Foundation\nfunc f(){ Process(); a.b("x") }\n',
     [Import('Foundation', (), '', 1), Call('', 'Process', (), 2, '.'), Call('a', 'b', ('x',), 2, '.')]),
    ('typescript', 'import { spawn } from "child_process";\nfunction f(){ spawn("ls"); new Foo("x") }\n',
     [Import('child_process', ('spawn',), '', 1), Call('', 'spawn', ('ls',), 2, '.'),
      New('Foo', ('x',), 2)]),
]


@pytest.mark.parametrize('lang,code,expected', SHAPES, ids=[s[0] for s in SHAPES])
def test_fact_shapes(lang, code, expected):
    assert extract_facts(code, lang) == expected


def test_shapes_cover_every_language():
    assert {s[0] for s in SHAPES} >= set(LANGUAGES) - {'tsx'}


INTERPOLATION = [
    ('typescript', 'function f(){ run(`ls ${d}`); run(`ls`) }'),
    ('kotlin', 'fun f(){ run("ls $d"); run("ls") }'),
    ('swift', 'func f(){ run("ls \\(d)"); run("ls") }'),
    ('php', '<?php run("ls $d"); run("ls");'),
    ('ruby', 'def f; run("ls #{d}"); run("ls"); end'),
    ('csharp', 'class A{void f(){ run($"ls {d}"); run("ls"); }}'),
    ('python', 'run(f"ls {d}")\nrun("ls")\n'),
]


@pytest.mark.parametrize('lang,code', INTERPOLATION, ids=[i[0] for i in INTERPOLATION])
def test_interpolated_string_arg_is_not_a_literal(lang, code):
    """A silently-wrong literal ('ls ') would let a rule match an argument it never saw."""
    assert [a for p, a in _calls(extract_facts(code, lang)) if p == 'run'] == [(None,), ('ls',)]


def test_chained_call_keeps_only_the_final_member():
    """Same collapse as calls:// (BACK-415): a call on a call result is `.member`."""
    facts = extract_facts('class A { void f(){ Runtime.getRuntime().exec("ls"); } }\n', 'java')
    assert ('exec', ('ls',)) in _calls(facts)


def test_qualified_ignores_line_breaks_inside_a_chain():
    src = 'class A { void f() throws Exception {\n  Runtime.getRuntime()\n      .exec("ls");\n} }\n'
    call = [f for f in extract_facts(src, 'java') if isinstance(f, Call) and f.name == 'exec'][0]
    assert call.qualified == 'Runtime.getRuntime().exec'
    assert call.chained


def test_lookalike_is_still_a_plain_call_fact():
    """Facts are neutral: `clap::Command::new` and `process::Command::new` look alike here.
    Telling them apart is the rule layer's job, via the Import facts."""
    src = 'use clap::Command;\nfn f(){ Command::new("app"); }\n'
    facts = extract_facts(src, 'rust')
    assert Import('clap::Command', (), '', 1) in facts
    assert Call('Command', 'new', ('app',), 2, '::') in facts


def test_extract_file_facts_dispatch_and_decline(tmp_path):
    ok = tmp_path / 'a.go'
    ok.write_text('package main\nfunc f(){ g("x") }\n')
    assert extract_file_facts(str(ok)) == [Call('', 'g', ('x',), 2, '.')]
    other = tmp_path / 'a.txt'
    other.write_text('x')
    assert extract_file_facts(str(other)) is None
    bad = tmp_path / 'bad.py'
    bad.write_text('def (:\n')
    assert extract_file_facts(str(bad)) is None
