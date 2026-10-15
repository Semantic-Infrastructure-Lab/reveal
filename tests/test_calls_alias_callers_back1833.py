"""BACK-1833: an import alias renames a bare call only; ``o.h()`` is still a method named h.

``trace`` and ``?root=`` already follow this rule (resolve.py).  The callers index used by
``calls://?target=`` applied the alias map to the tail of qualified calls too, so after
``from m import helper as h`` every ``o.h()`` and ``self.h()`` was listed as a caller of
``m.helper``.
"""
from pathlib import Path

import pytest

from reveal.adapters.calls.index import find_callers

pytestmark = pytest.mark.component


def _callers(directory, target='helper'):
    result = find_callers(str(directory), target)
    return {(Path(c['file']).name, c['caller'])
            for level in result['levels'] for c in level['callers']}


def _python(tmp_path):
    (tmp_path / 'm.py').write_text('def helper():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text(
        'from m import helper as h\n\n'
        'class Obj:\n'
        '    def h(self):\n        return 2\n'
        '    def self_h(self):\n        return self.h()\n\n'
        'def member(o):\n    return o.h()\n\n'
        'def direct():\n    return h()\n', encoding='utf-8')
    return tmp_path


def test_bare_alias_call_still_reaches_the_definition(tmp_path):
    assert ('app.py', 'direct') in _callers(_python(tmp_path))


def test_member_calls_named_like_the_alias_are_not_callers(tmp_path):
    callers = _callers(_python(tmp_path))
    assert ('app.py', 'member') not in callers
    assert ('app.py', 'self_h') not in callers


def test_member_calls_stay_callers_of_the_method(tmp_path):
    callers = _callers(_python(tmp_path), target='h')
    assert {('app.py', 'member'), ('app.py', 'self_h')} <= callers


def test_typescript_member_call_is_not_a_caller(tmp_path):
    (tmp_path / 'm.ts').write_text('export function helper() { return 1; }\n', encoding='utf-8')
    (tmp_path / 'app.ts').write_text(
        "import { helper as h } from './m';\n"
        'class Obj { h() { return 2; } }\n'
        'export function member(o: Obj) { return o.h(); }\n'
        'export function direct() { return h(); }\n', encoding='utf-8')
    callers = _callers(tmp_path)
    assert ('app.ts', 'direct') in callers
    assert ('app.ts', 'member') not in callers
