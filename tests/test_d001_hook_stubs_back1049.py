"""BACK-1049: D001 must not report intentional no-op extension-point hooks.

reveal/treesitter.py has a base-class family of hooks whose whole body is a
docstring plus ``return []`` / ``return None``.  They are identical after
normalization by design (each is a distinct override point), so reporting them
as copy-paste duplicates is noise.  Real duplicates must still be reported,
including a one-statement body that actually computes something.
"""

import pytest

from reveal.analyzers.python import PythonAnalyzer
from reveal.rules.duplicates import _bodies
from reveal.rules.duplicates.D001 import D001

pytestmark = pytest.mark.component

HOOKS = '''class Base:
    def _extract_bases(self, node):
        """Hook: languages override this to report base classes.

        No-op by default.
        """
        return []

    def _extract_decorators(self, node):
        """Hook: languages override this to report decorators.

        No-op by default.
        """
        return []

    def _find_special(self, name):
        """Hook: resolve a language-specific name.

        No-op by default.
        """
        return None

    def _other_special(self, name):
        """Hook: resolve another language-specific name.

        No-op by default.
        """
        return None
'''

REAL_DUPLICATES = '''class Svc:
    def first(self, key, default):
        """Look a key up."""
        value = self._lookup(key)
        if value is None:
            return default
        return value

    def second(self, key, default):
        """Look a key up, again."""
        value = self._lookup(key)
        if value is None:
            return default
        return value
'''

ONE_LINE_REAL = '''class Svc:
    def a(self, key, default):
        """A."""
        return self._registry.get(key, default)

    def b(self, key, default):
        """B."""
        return self._registry.get(key, default)
'''


def _detect(tmp_path, source, name="m.py"):
    path = tmp_path / name
    path.write_text(source, encoding='utf-8')
    structure = PythonAnalyzer(str(path)).get_structure()
    return D001().check(str(path), structure, source)


def test_noop_hooks_are_not_duplicates(tmp_path):
    assert _detect(tmp_path, HOOKS) == []


def test_real_duplicate_functions_still_reported(tmp_path):
    (det,) = _detect(tmp_path, REAL_DUPLICATES)
    assert "'second' identical to 'first'" in det.message


def test_identical_single_statement_that_computes_is_still_reported(tmp_path):
    (det,) = _detect(tmp_path, ONE_LINE_REAL)
    assert "'b' identical to 'a'" in det.message


def test_hooks_do_not_hide_a_real_duplicate_beside_them(tmp_path):
    findings = _detect(tmp_path, HOOKS + "\n" + REAL_DUPLICATES.replace("class Svc", "class Svc2"))
    assert [d.message.split("'")[1] for d in findings] == ["second"]



@pytest.mark.parametrize("body", [
    "return []", "return {}", "return None", "return ()", "return 0", "return False", "return True",
    'return ""', "return", "pass", "...", "return null;", "return false;", "return;", "{\nreturn null;\n}",
])
def test_trivial_hook_body_recognized(body):
    assert _bodies.is_trivial_hook_body(body)


@pytest.mark.parametrize("body", [
    "return self.x", "return [1]", "return foo()", "return None\nreturn []", "x = 1", "return -1", "",
])
def test_non_trivial_body_not_a_hook(body):
    assert not _bodies.is_trivial_hook_body(body)
