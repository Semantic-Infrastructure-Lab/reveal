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


def test_java_annotation_on_signature_line():
    content = "class A {\n    @Override public int a(int x) {\n        return x;\n    }\n}\n"
    body = _bodies.extract_function_body({'line': 2, 'line_end': 4}, content)
    assert body.strip().splitlines()[0].strip() == "return x;"


def test_typescript_decorated_method_body_starts_after_brace():
    content = "class A {\n    @Input()\n    a(x: number): number {\n        return x;\n    }\n}\n"
    body = _bodies.extract_function_body({'line': 2, 'line_end': 5}, content)
    assert body.strip().splitlines()[0].strip() == "return x;"


def test_one_line_def_without_terminator_keeps_old_behaviour():
    content = "@dec\ndef f(x): return x\n"
    assert _bodies.extract_function_body({'line': 1, 'line_end': 2}, content) == ""


def test_colon_inside_parentheses_does_not_close_signature():
    content = "def f(\n    a: int,\n    b: dict = {'k': 1},\n) -> int:\n    return a\n"
    assert _bodies.extract_function_body({'line': 1, 'line_end': 5}, content) == "    return a"


# Languages with no signature terminator (Ruby, Lua): a ``{`` or ``:`` line inside the
# body must not be taken as the end of the signature, or everything above it is
# dropped and methods that differ there are reported as duplicates (manager review).
RB_DIFFERENT_HEADS = '''class K
  def alpha(x)
    log_start(x)
    validate(x)
    opts = {
      a: 1,
    }
    run(opts)
  end

  def beta(x)
    totally_different(x)
    other_thing(x)
    opts = {
      a: 1,
    }
    run(opts)
  end
end
'''

LUA_DIFFERENT_HEADS = '''local function alpha(x)
  log_start(x)
  validate(x)
  local t = {
    a = 1,
  }
  return run(t)
end

local function beta(x)
  totally_different(x)
  other_thing(x)
  local t = {
    a = 1,
  }
  return run(t)
end
'''


@pytest.mark.parametrize('name,source', [('m.rb', RB_DIFFERENT_HEADS), ('m.lua', LUA_DIFFERENT_HEADS)])
def test_brace_line_inside_body_does_not_end_signature(tmp_path, name, source):
    assert _detect(tmp_path, source, name) == []


def test_allman_brace_on_next_line_is_part_of_signature():
    content = "@Override\npublic int a(int x)\n{\n    return x + 1;\n}\n"
    assert _bodies.extract_function_body({'line': 1, 'line_end': 5}, content) == "    return x + 1;\n}"
