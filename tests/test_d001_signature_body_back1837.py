"""BACK-1837: D001 body extraction must start after the whole signature.

Python: a multi-line ``def`` header must not leak its continuation lines into the
body, or the trivial pass-only hook exemption fails.  Java: structure records start
at the annotation, so the signature line must not stay in the body either.
"""

import pytest

from reveal.analyzers.python import PythonAnalyzer
from reveal.rules.duplicates import _bodies
from reveal.rules.duplicates.D001 import D001

pytestmark = pytest.mark.component

PY_HOOKS = '''@app.task
def third(
    self,
    arg,
):
    pass


@app.task
def fourth(
    self,
    arg,
):
    pass
'''

PY_REAL = '''@app.task
def third(
    self,
    arg,
):
    total = 0
    for i in range(arg):
        total += i * 2
    return total


@app.task
def fourth(
    self,
    arg,
):
    total = 0
    for i in range(arg):
        total += i * 2
    return total
'''

JAVA_DUP = '''class Dup {
    @Override
    public int a(int x) {
        int total = 0;
        for (int i = 0; i < x; i++) { total += i * 2; }
        return total;
    }

    @Override
    public int b(int x) {
        int total = 0;
        for (int i = 0; i < x; i++) { total += i * 2; }
        return total;
    }
}
'''

JAVA_DIFFERENT = '''class Dup {
    @Override
    public int a(int x) {
        int total = 0;
        for (int i = 0; i < x; i++) { total += i * 2; }
        return total;
    }

    @Override
    public int b(int x) {
        int total = 1;
        for (int i = 0; i < x; i++) { total *= i + 3; }
        return total - 1;
    }
}
'''


def _detect(tmp_path, source, name):
    path = tmp_path / name
    path.write_text(source, encoding='utf-8')
    from reveal.registry import get_analyzer
    structure = get_analyzer(str(path))(str(path)).get_structure()
    return D001().check(str(path), structure, source)


def test_multiline_signature_pass_hooks_not_duplicates(tmp_path):
    assert _detect(tmp_path, PY_HOOKS, "h.py") == []


def test_multiline_signature_real_duplicates_still_reported(tmp_path):
    (det,) = _detect(tmp_path, PY_REAL, "r.py")
    assert "'fourth' identical to 'third'" in det.message


def test_java_annotated_duplicates_reported(tmp_path):
    (det,) = _detect(tmp_path, JAVA_DUP, "Dup.java")
    assert "'b' identical to 'a'" in det.message


def test_java_different_methods_not_reported(tmp_path):
    assert _detect(tmp_path, JAVA_DIFFERENT, "Dup.java") == []


def test_body_excludes_multiline_signature():
    content = PY_HOOKS
    func = {'line': 1, 'line_end': 6}
    assert _bodies.extract_function_body(func, content).strip() == "pass"
