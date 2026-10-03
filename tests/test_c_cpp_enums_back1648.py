"""BACK-1648: C/C++ enums, unions and C++ namespaces were in no structure category, so
`enum E { };` was invisible to the outline and `reveal f.cpp E` said "not found" (a file
of only enums printed its raw source). They are categories now, counting definitions
only: `enum Color c` in a parameter or member is a mention (BACK-1627). The not-found
hint lists every addressable category, not functions and classes only.
"""

import os
import subprocess
import sys

import pytest

from reveal.registry import get_analyzer

_CPP = ('namespace app {\nenum Color { Red, Green };\nenum class Mode : int { A, B };\n'
        'union U { int i; float f; };\nstruct S { enum Color c; };\nvoid f(enum Color c) {}\n}\n')
_C = ('enum Color { Red };\nunion U { int i; };\nstruct S { enum Color c; union U u; };\n'
      'void f(enum Color c) {}\n')


def _reveal(cwd, *argv):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', REVEAL_NO_UPDATE_CHECK='1')
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding='utf-8', timeout=60)


def _structure(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding='utf-8')
    return get_analyzer(str(path))(str(path)).get_structure()


@pytest.mark.parametrize('name, source, expected', [
    ('en.cpp', _CPP, {'enums': ['Color', 'Mode'], 'unions': ['U'], 'namespaces': ['app']}),
    ('en.c', _C, {'enums': ['Color'], 'unions': ['U']}),
])
def test_definitions_are_listed_and_mentions_are_not(tmp_path, name, source, expected):
    structure = _structure(tmp_path, name, source)
    for category, names in expected.items():
        assert [entry['name'] for entry in structure.get(category, [])] == names


@pytest.mark.parametrize('name, source, element, line', [
    ('en.cpp', _CPP, 'Mode', 'enum class Mode : int { A, B };'),
    ('en.cpp', _CPP, 'U', 'union U { int i; float f; };'),
    ('en.cpp', _CPP, 'app.Color', 'enum Color { Red, Green };'),
    ('en.c', _C, 'Color', 'enum Color { Red };'),
])
def test_extracts_by_name_without_matching_mentions(tmp_path, name, source, element, line):
    (tmp_path / name).write_text(source, encoding='utf-8')
    run = _reveal(tmp_path, name, element)
    assert run.returncode == 0, run.stderr
    assert line in run.stdout
    assert 'matches' not in run.stderr


def test_not_found_hint_names_structs_and_enums(tmp_path):
    (tmp_path / 'en.c').write_text(_C, encoding='utf-8')
    run = _reveal(tmp_path, 'en.c', 'Nope')
    assert run.returncode != 0
    assert 'Available: f, S, Color, U' in run.stderr
