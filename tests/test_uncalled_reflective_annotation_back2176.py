"""?uncalled sees Java methods dispatched by an annotation the project reads reflectively (BACK-2176).

Guava's `FreshValueGenerator` collects `getDeclaredMethods()` and keeps those with
`isAnnotationPresent(Generates.class)`; the `@Generates` methods are never named by a call.
A project-declared annotation type that code reads through the reflection API marks its
methods as entry points. Annotations the project does not declare, or never reads, do not.
"""
import json

from conftest import _run_reveal_direct

MARKER = 'package p;\n@interface Generates {}\n'
READER = ('package p;\nimport java.lang.reflect.Method;\n'
          'class Reader {\n  boolean wanted(Method m) { return m.isAnnotationPresent(Generates.class); }\n}\n')
USER = ('package p;\nclass Gen {\n  @Generates int makeInt() { return 1; }\n  int plain() { return 2; }\n}\n')
UNREAD = 'package p;\n@interface Tag {}\n'
TAGGED = 'package p;\nclass T {\n  @Tag int tagged() { return 1; }\n}\n'
FOREIGN_READER = ('package p;\nimport java.lang.reflect.Method;\n'
                  'class R2 {\n  boolean f(Method m) { return m.isAnnotationPresent(Outside.class); }\n}\n')
FOREIGN_USER = 'package p;\nclass U {\n  @Outside int outsider() { return 1; }\n}\n'


def uncalled(tmp_path, files):
    root = tmp_path / 'proj'
    root.mkdir()
    for name, text in files.items():
        (root / name).write_text(text, encoding='utf-8')
    out = _run_reveal_direct(f'calls://{root}?uncalled=true', '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    return sorted(e['name'] for e in json.loads(out.stdout)['entries'])


def test_method_with_a_reflectively_read_project_annotation_is_an_entry_point(tmp_path):
    names = uncalled(tmp_path, {'Generates.java': MARKER, 'Reader.java': READER, 'Gen.java': USER})
    assert 'makeInt' not in names


def test_control_unannotated_method_stays_reported(tmp_path):
    names = uncalled(tmp_path, {'Generates.java': MARKER, 'Reader.java': READER, 'Gen.java': USER})
    assert 'plain' in names


def test_control_annotation_nobody_reads_reflectively_stays_reported(tmp_path):
    assert 'tagged' in uncalled(tmp_path, {'Tag.java': UNREAD, 'T.java': TAGGED})


def test_control_reflected_annotation_the_project_does_not_declare_stays_reported(tmp_path):
    assert 'outsider' in uncalled(tmp_path, {'R2.java': FOREIGN_READER, 'U.java': FOREIGN_USER})
